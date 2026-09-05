#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Shared, dependency-free helpers for the openRepoShape validators.

STANDARD LIBRARY ONLY, ON PURPOSE. This repository is meant to be forked into
an organisation that has no openxFactory, no codexFactory and, quite possibly,
no permission to `pip install` anything on the machine where the scaffold runs.
Everything here therefore uses `python3` and `git` and nothing else. That
constraint is what forces the small YAML reader below: PyYAML would be one
dependency, and one dependency is one more than "clone it and run it" allows.

WHAT THIS MODULE OWNS
  - `parse_yaml` / `load_yaml` — a deliberately SMALL, fail-closed reader for
    the YAML subset this standard's own files are written in.
  - `tree_digest` — the ONE definition of what "the digest of a commit" means
    here (see `TREE_DIGEST_DEFINITION` below; the choice is argued in README).
  - `tree_digest_from_gh` — the SAME definition, read from the forge's
    recursive tree listing instead of a local clone; how a `validate-pins.py`
    re-check answers for a neutral-product pin with no local checkout.
  - `file_sha256` — the per-file digest used by the shape pin's `files:` block,
    mirroring `neutral-product-pin`'s per-file `sha256` rows.
  - `NamingPolicy` — the classifier over `contracts/repository-naming.yaml`.
  - `Refusal` — the fail-closed exception every validator raises, carrying a
    remediation string, because a refusal that names what is wrong without
    naming what to run puts the exit in tribal memory instead of the message.

This file is COPIED into a scaffolded assembly root by `scaffold-project.py`
and its sha256 is recorded in that project's `contracts/shape-pin.yaml`, so an
edit to the copy is drift the project's own `validate-pins.py` reports.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

#: Exactly 40 hex, case-insensitive, normalised to lowercase before comparison.
#: 40 means 40 — an abbreviated oid, a branch name or a tag cannot pass, which
#: is `neutral-product-pin`'s "a tag can be moved" written as a regex.
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

#: A project id is the lowercase machine name; the GitHub topic is derived.
PROJECT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
TOPIC_PREFIX = "xf-project-"

#: The digest definition recorded in every pin this standard writes. Bumping
#: the algorithm bumps this string, so a pin never silently means something
#: else than it did when it was written.
TREE_DIGEST_DEFINITION = "sorted-ls-tree-r-v1"

#: Every neutral `open<Product>` repository lives under THIS organisation.
#: Domain repositories never author a neutral product, only pin the opensoft
#: original (README, "Working rules"), so an UNQUALIFIED `--pin
#: openGlass@<sha>` always resolves here — never under the pinning project's
#: own `--org`, which owns no neutral product at all. `--pin-owner` overrides
#: it for the rare pin on a fork of the neutral original.
NEUTRAL_PRODUCT_OWNER = "opensoft"

#: How a neutral product's tree is read when no local checkout answers for
#: it. `scaffold-project.py`'s own `pin_digest_from_gh` reads this exact
#: endpoint when it FIRST computes a `neutral-product-pin`'s digest;
#: `tree_digest_from_gh` below reads it again so a later re-check recomputes
#: the same number from the same shape of data.
GH_TREE_API = "repos/{repo}/git/trees/{commit}?recursive=1"

#: The GitHub repository-visibility values this standard accepts, everywhere
#: it accepts one: `scaffold-project.py --visibility`, `setup.sh
#: --visibility`, `adopt-project.py plan --visibility`, and the `visibility:`
#: field `validate-manifest.py` checks. ONE tuple, so a fourth value never has
#: to be added in four places and inevitably missed in a fifth. `internal` is
#: an enterprise org-internal repository (`gh repo create --internal`,
#: `gh repo view --json visibility` -> `INTERNAL`) — the same population as
#: PRIVATE and PUBLIC, not a narrower or wider one.
VISIBILITY_CHOICES = ("private", "public", "internal")

#: Every value this family lets a caller put on a `git` or `gh` command line.
#: Deliberately narrow: letters, digits, and the punctuation that real branch
#: names, paths, repository names and commits are spelled with.
SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9._/@+~-]{1,255}$")

#: The same guard for a value that is a FILESYSTEM PATH the operator named,
#: rather than a branch, a repository or a commit. A Windows path is
#: `D:\a\_temp\t\remotes\Atlas-spec.git` and a real home directory is
#: `C:\Users\Jane Doe\...`: a drive letter, a colon, backslashes and a
#: space, none of which `SAFE_ARG_RE` admits and NONE OF WHICH IS THE THREAT.
#: The threat is that `git` reads its own arguments, so a leading `-` is
#: refused by `checked_value` itself; and that a control character reaches a
#: command line, which this alphabet excludes by naming what it allows. The
#: colon is admitted only as a drive letter's, so a value cannot become git's
#: `host:path` scp syntax by accident.
SAFE_PATH_RE = re.compile(r"^(?:[A-Za-z]:)?[A-Za-z0-9._/@+~ \\-]{1,4096}$")

#: How to spell "run Python" in a message a person is meant to retype. On
#: Windows there is usually no `python3` on PATH at all — the python.org
#: installer ships `python.exe` and the `py` launcher — so a remediation
#: naming `python3` is a command that fails on the machine reading it.
#:
#: THE PLATFORM'S CONVENTIONAL COMMAND, not the running interpreter's
#: basename. A basename need not be on PATH at all: inside a virtualenv
#: `sys.executable` is `…/venv/bin/python`, and on a Debian box without
#: `python-is-python3` there is no `python` to type. `python3` is the command
#: every POSIX install of a supported Python answers to, and `python` is what
#: both python.org and the Microsoft Store put on PATH on Windows. A
#: remediation names the command its reader can type, not the binary that
#: happened to run.
PYTHON = "python" if os.name == "nt" else "python3"

REMEDIATION = (
    "Remediation: run `git submodule update --init --recursive`, then "
    f"`{PYTHON} scripts/validate-pins.py`. If the PIN itself is stale, advance "
    "the gitlink, `contracts/<leg>-pin.yaml` and every workflow `@<sha>` that "
    "names the leg in ONE commit (see README, 'The lockstep invariant')."
)


class Refusal(Exception):
    """A named, remediable refusal.

    `code` is machine-readable and `detail` is for humans; `str(exc)` renders
    code, detail and the remediation trailer together, so a caller that prints
    the exception cannot accidentally drop the remedy.
    """

    def __init__(self, code: str, detail: str, remediation: str = REMEDIATION):
        super().__init__(code, detail)
        self.code = code
        self.detail = detail
        self.remediation = remediation

    def __str__(self) -> str:  # pragma: no cover - trivial
        return f"REFUSED {self.code}: {self.detail}\n{self.remediation}"


class YamlError(Exception):
    """The reader met a construct it does not implement.

    Raising rather than guessing is the whole point: a validator that silently
    mis-reads its own contract file is worse than one that will not start.
    """


# ---------------------------------------------------------------------------
# The YAML subset reader
# ---------------------------------------------------------------------------
#
# SUPPORTED: one document (an optional leading `---`), block mappings, block
# sequences, `#` comments, single- and double-quoted scalars, plain scalars
# with int / float / bool / null coercion, single-level flow sequences and flow
# mappings (`[a, b]`, `{k: v}`), and literal / folded block scalars (`|`, `>`,
# with the `-` and `+` chomping indicators accepted and `-` honoured).
#
# REFUSED (raises YamlError): tabs used for indentation, anchors and aliases
# (`&`, `*`), tags (`!`), merge keys (`<<`), explicit keys (`? `), and more
# than one document. Each of those has a meaning this reader would have to
# invent, and an invented meaning in a validator is a wrong answer with a
# confident tone.

_DASH_RE = re.compile(r"^-(\s+|$)")


class _Rec:
    __slots__ = ("indent", "text", "dash", "line")

    def __init__(self, indent: int, text: str, dash: bool, line: int):
        self.indent = indent
        self.text = text
        self.dash = dash
        self.line = line


def _strip_comment(text: str) -> str:
    """Drop a trailing `#` comment that is not inside a quoted scalar."""
    out = []
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and quote == '"' and i + 1 < len(text):
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#" and (not out or out[-1] in " \t"):
            break
        else:
            out.append(ch)
        i += 1
    return "".join(out).rstrip()


def _split_key(text: str) -> tuple[str, str] | None:
    """Split `key: rest` on the first top-level `:` followed by space or EOL."""
    quote = None
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch in "[{":
            return None  # a flow collection cannot be a key in this subset
        elif ch == ":" and (i + 1 == len(text) or text[i + 1] in " \t"):
            return _unquote_key(text[:i].strip()), text[i + 1:].strip()
        i += 1
    return None


def _unquote_key(key: str) -> str:
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'":
        return str(_scalar(key))
    return key


#: The escape sequences a double-quoted scalar may carry, and the only ones
#: this reader resolves. Anything else keeps its backslash, because inventing
#: a meaning for `\q` is how a reader starts disagreeing with the writer.
DOUBLE_QUOTED_ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


def _unescape(body: str) -> str:
    """A double-quoted scalar's body, ONE PASS, LEFT TO RIGHT.

    NOT A CHAIN OF `str.replace` CALLS, and the reason is a Windows path. An
    adoption plan escapes each backslash it writes, so the source directory
    `D:\\a\\_temp\\t` reaches here doubled. Replacing the two-character `\\t`
    before the two-character `\\\\` matches the SECOND backslash of that pair
    and turns a directory named `t` into a TAB — the path then does not
    exist, and `adopt-project.py check` refuses a plan it wrote itself.
    Consuming the backslash and the character it escapes together is the only
    spelling that cannot read one escape's output as another escape's input.
    """
    out: list[str] = []
    index = 0
    while index < len(body):
        char = body[index]
        replacement = (DOUBLE_QUOTED_ESCAPES.get(body[index + 1])
                       if char == "\\" and index + 1 < len(body) else None)
        if replacement is None:
            out.append(char)
            index += 1
        else:
            out.append(replacement)
            index += 2
    return "".join(out)


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if text == "" or text in ("null", "~", "Null", "NULL"):
        return None
    if text[0] == "'" and text[-1] == "'" and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text[-1] == '"' and len(text) >= 2:
        return _unescape(text[1:-1])
    if text[0] in "&*!":
        raise YamlError(f"anchors, aliases and tags are not supported: {text!r}")
    if text in ("true", "True", "TRUE"):
        return True
    if text in ("false", "False", "FALSE"):
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _flow_value(text: str) -> Any:
    """A flow entry is itself a flow collection when it opens with `[` or `{`."""
    return _flow(text) if text[:1] in "[{" else _scalar(text)


def _flow(text: str) -> Any:
    text = text.strip()
    if text.startswith("[") and text.endswith("]"):
        body = text[1:-1].strip()
        return [] if not body else [_flow_value(p) for p in _split_flow(body)]
    if text.startswith("{") and text.endswith("}"):
        body = text[1:-1].strip()
        out: dict[str, Any] = {}
        if body:
            for part in _split_flow(body):
                kv = _split_key_flow(part)
                if kv is None:
                    raise YamlError(f"flow mapping entry without a key: {part!r}")
                out[kv[0]] = _flow_value(kv[1])
        return out
    raise YamlError(f"not a flow collection: {text!r}")


def _split_key_flow(text: str) -> tuple[str, str] | None:
    """`_split_key` for a flow-mapping entry, where the value MAY open a flow."""
    quote = None
    for i, ch in enumerate(text):
        if quote:
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            return None
        elif ch == ":" and (i + 1 == len(text) or text[i + 1] in " \t"):
            return _unquote_key(text[:i].strip()), text[i + 1:].strip()
    return None


def _split_flow(body: str) -> list[str]:
    parts, depth, quote, cur = [], 0, None, []
    for ch in body:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(cur).strip())
            cur = []
            continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p != ""]


def _tokenise(text: str) -> list[_Rec]:
    recs: list[_Rec] = []
    raw_lines = text.splitlines()
    i = 0
    seen_doc = False
    while i < len(raw_lines):
        raw = raw_lines[i]
        i += 1
        if "\t" in raw[: len(raw) - len(raw.lstrip())]:
            raise YamlError(f"line {i}: tab used for indentation")
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped in ("---", "..."):
            if stripped == "---":
                if seen_doc:
                    raise YamlError("multiple documents are not supported")
                seen_doc = True
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        content = _strip_comment(raw.strip())
        if not content:
            continue
        # Peel leading `- ` markers into DASH records so a sequence item's
        # content sits at its own column, which is where its sibling keys are.
        while True:
            m = _DASH_RE.match(content)
            if not m:
                break
            recs.append(_Rec(indent, "", True, i))
            indent += len(m.group(0))
            content = content[m.end():]
        if content == "":
            continue
        if content.startswith("? "):
            raise YamlError(f"line {i}: explicit keys are not supported")
        if content.startswith("<<"):
            raise YamlError(f"line {i}: merge keys are not supported")
        kv = _split_key(content)
        if kv is not None and kv[1][:1] in ("|", ">") and re.fullmatch(r"[|>][-+]?\d*", kv[1]):
            # A block scalar: swallow every following line more indented than
            # the key, and keep it as one string.
            chomp = kv[1]
            body: list[str] = []
            block_indent = None
            while i < len(raw_lines):
                nxt = raw_lines[i]
                if nxt.strip() == "":
                    body.append("")
                    i += 1
                    continue
                nxt_indent = len(nxt) - len(nxt.lstrip(" "))
                if nxt_indent <= indent:
                    break
                if block_indent is None:
                    block_indent = nxt_indent
                body.append(nxt[block_indent:])
                i += 1
            if chomp[0] == "|":
                joined = "\n".join(body)
            else:
                folded: list[str] = []
                for line in body:
                    if line == "":
                        folded.append("\n")
                    elif folded and folded[-1] not in ("", "\n"):
                        folded.append(" " + line)
                    else:
                        folded.append(line)
                joined = "".join(folded).strip("\n") if body and body[-1] == "" \
                    else "".join(folded)
            if not chomp.endswith("-"):
                joined = joined.rstrip("\n") + "\n"
            else:
                joined = joined.rstrip("\n")
            recs.append(_Rec(indent, "", False, i))
            recs[-1].text = "\x00BLOCK\x00" + kv[0] + "\x00" + joined
            continue
        recs.append(_Rec(indent, content, False, i))
    return recs


def _parse_nodes(recs: list[_Rec], i: int, indent: int) -> tuple[Any, int]:
    if i >= len(recs):
        return None, i
    if recs[i].dash:
        return _parse_sequence(recs, i, indent)
    return _parse_mapping(recs, i, indent)


def _parse_sequence(recs: list[_Rec], i: int, indent: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    while i < len(recs) and recs[i].dash and recs[i].indent == indent:
        i += 1
        if i < len(recs) and recs[i].indent > indent:
            rec = recs[i]
            if not rec.dash and not rec.text.startswith("\x00BLOCK\x00") \
                    and _split_key(rec.text) is None:
                # A plain or flow SCALAR item (`- openAvatar`, `- [a, b]`).
                value = _flow(rec.text) if rec.text[:1] in "[{" else _scalar(rec.text)
                i += 1
            else:
                value, i = _parse_nodes(recs, i, rec.indent)
        else:
            value = None
        items.append(value)
    return items, i


def _parse_mapping(recs: list[_Rec], i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(recs) and not recs[i].dash and recs[i].indent == indent:
        rec = recs[i]
        if rec.text.startswith("\x00BLOCK\x00"):
            _empty, _marker, key, body = rec.text.split("\x00", 3)
            out[key] = body
            i += 1
            continue
        kv = _split_key(rec.text)
        if kv is None:
            raise YamlError(f"line {rec.line}: expected `key: value`, got {rec.text!r}")
        key, rest = kv
        i += 1
        if rest == "":
            if i < len(recs) and recs[i].dash and recs[i].indent >= indent:
                out[key], i = _parse_sequence(recs, i, recs[i].indent)
            elif i < len(recs) and recs[i].indent > indent:
                out[key], i = _parse_nodes(recs, i, recs[i].indent)
            else:
                out[key] = None
        elif rest[0] in "[{":
            out[key] = _flow(rest)
        else:
            out[key] = _scalar(rest)
    return out, i


def parse_yaml(text: str) -> Any:
    """Parse the supported YAML subset. Raises `YamlError` on anything else."""
    recs = _tokenise(text)
    if not recs:
        return None
    value, end = _parse_nodes(recs, 0, recs[0].indent)
    if end != len(recs):
        raise YamlError(f"line {recs[end].line}: unexpected indentation")
    return value


def load_yaml(path: Path) -> Any:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise Refusal("yaml-unreadable", f"{path}: {exc}") from exc
    try:
        return parse_yaml(text)
    except YamlError as exc:
        raise Refusal("yaml-unparsable", f"{path}: {exc}") from exc


# ---------------------------------------------------------------------------
# git helpers and the digest definition
# ---------------------------------------------------------------------------


def git_out(args: list[str], cwd: Path, binary: bool = False) -> Any:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise Refusal(
            "git-failed",
            "`git {}` in {} exited {}: {}".format(
                " ".join(args), cwd, proc.returncode,
                proc.stderr.decode("utf-8", "replace").strip(),
            ),
        )
    return proc.stdout if binary else proc.stdout.decode("utf-8").strip()


def tree_digest(repo: Path, rev: str) -> str:
    """sha256 of the CANONICAL LISTING of the tree reachable from `rev`.

    Definition (`sorted-ls-tree-r-v1`), exactly:

        records = `git ls-tree -r -z <rev>` split on NUL, empty records dropped
        each record is `<mode> SP <type> SP <oid> TAB <path>`, path UNQUOTED
        sort the records bytewise ascending
        digest = sha256( b"".join(record + b"\\n" for record in records) )

    `-r` walks the whole tree and emits blobs and gitlinks but no tree entries;
    `-z` is what makes the path column raw bytes rather than something whose
    quoting depends on `core.quotePath`. Mode is included, so a permission
    change is drift; the oid is included, so any content change is drift; a
    submodule entry appears as `160000 commit <oid>`, so a leg's own pin moving
    is drift too. The output is therefore a complete content address of the
    tree, computed with sha256 rather than with git's object hash.
    """
    raw = git_out(["ls-tree", "-r", "-z", rev], cwd=repo, binary=True)
    records = sorted(r for r in raw.split(b"\x00") if r)
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
        digest.update(b"\n")
    return digest.hexdigest()


def tree_digest_from_gh(repository: str, commit: str) -> str:
    """The same `sorted-ls-tree-r-v1` digest, read from the forge's own
    recursive tree listing — no clone, no working tree, just `gh api`.

    A SHALLOW READ, not a clone: `git/trees/<commit>?recursive=1` returns one
    row per object with `mode`, `type`, `sha` and `path` — exactly the four
    columns `git ls-tree -r -z` emits, which is what makes the two readings
    the same number. Tree rows are dropped because `-r` emits none; a
    submodule arrives as `type: commit` with mode `160000` and is kept, as
    `ls-tree` keeps it. This mirrors `scaffold-project.py`'s own
    `pin_digest_from_gh`, which computes a `neutral-product-pin`'s digest
    this exact way the first time a project declares one; a validator that
    reads it back must agree with the tool that wrote it.

    Raises `Refusal` — `gh-not-found`, `gh-unreadable`, `gh-response-
    unreadable` or `gh-tree-truncated` — naming exactly what went wrong. A
    caller with an offline story to try first, and a SKIP to report if this
    also fails, always catches this rather than letting it reach a user
    directly: an unanswerable neutral-product pin is a gap in the check, not
    a reason to fail a project that only lacks a `gh` login.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", GH_TREE_API.format(repo=repository, commit=commit)],
            capture_output=True, text=True, check=False)
    except FileNotFoundError as exc:
        raise Refusal("gh-not-found",
                      f"the `gh` CLI is not on PATH: {exc}") from exc
    if proc.returncode != 0:
        raise Refusal(
            "gh-unreadable",
            f"`gh api` could not read {repository} @ {commit}: "
            f"{proc.stderr.strip()}",
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal("gh-response-unreadable",
                      f"{repository} @ {commit}: {exc}") from exc
    if payload.get("truncated"):
        raise Refusal(
            "gh-tree-truncated",
            f"the forge truncated its tree listing for {repository} @ "
            f"{commit}, so the digest would be computed over a PARTIAL tree",
        )
    records = sorted(
        f"{row['mode']} {row['type']} {row['sha']}\t{row['path']}".encode()
        for row in payload.get("tree") or [] if row.get("type") != "tree")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
        digest.update(b"\n")
    return digest.hexdigest()


FREE_PLAN_HINT = """\
NOTE {org} is on the GitHub FREE plan, where ORGANISATION Actions secrets are
     delivered only to PUBLIC repositories. {what} private, so org-level
     SHAPE_LEGS_APP_ID / SHAPE_LEGS_APP_PRIVATE_KEY resolve to EMPTY inside
     the workflow and the `validate` check degrades to `credential source:
     none` — green, because it skips the pin check rather than failing, which
     is the worst way to be wrong. Set them as REPOSITORY secrets instead:

         gh secret set SHAPE_LEGS_APP_ID --repo {repo} --body '<app id>'
         gh secret set SHAPE_LEGS_APP_PRIVATE_KEY --repo {repo} < key.pem

     or upgrade the organisation to Team, where the org secrets work as
     written. Measured on InkRouter, 2026-09-04: the App was installed and
     the org secrets existed at `visibility: all`, and both split pull
     requests still fetched no legs."""


def free_plan_secret_hint(org: str, repo: str, what: str) -> str | None:
    """The Free-plan repository-secret hint, or None if it does not apply.

    THE FAILURE THIS EXISTS FOR IS SILENT. On the Free plan an organisation
    secret is simply not delivered to a private repository — no error, no
    warning, `secrets.SHAPE_LEGS_APP_ID` is the empty string — so the App
    steps skip, the legs go unfetched, and `validate` reports SUCCESS with
    the lockstep pin check quietly skipped. Somebody who set the org secrets
    correctly, on an org where the App is correctly installed, gets a green
    check that verified nothing. That is worth one `gh api` call at create
    time.

    Returns None whenever the answer is not a confident "free": no `gh` on
    PATH, an unreadable or unparseable response, a plan the API did not name.
    A tool running offline or against a local remote must print nothing
    rather than guess — a wrong hint about credentials is worse than none.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", f"orgs/{org}", "--jq", ".plan.name"],
            capture_output=True, text=True, check=False)
    except (FileNotFoundError, OSError):
        return None
    if proc.returncode != 0:
        return None
    if proc.stdout.strip().lower() != "free":
        return None
    return FREE_PLAN_HINT.format(org=org, repo=repo, what=what)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


#: How to read the gitlink out of each listing, INDEX FIRST: the argv, which
#: column holds the oid once the tab is folded into the spaces, and which
#: holds the merge STAGE, if the listing has one. `ls-files -s` emits
#: `<mode> SP <oid> SP <stage> TAB <path>` and `ls-tree` emits
#: `<mode> SP <type> SP <oid> TAB <path>` — the same shape with a DIFFERENT
#: third column, so the two cannot share one index.
GITLINK_LISTINGS = (
    (["ls-files", "-s", "--"], 1, 2),
    (["ls-tree", "HEAD", "--"], 2, None),
)


def recorded_gitlink(repo: Path, path: str) -> str | None:
    """The commit the SUPERPROJECT records for the submodule at `path`.

    INDEX FIRST, HEAD SECOND. In a clean tree the two agree and the order is
    invisible; it decides the answer only when they disagree, and when they
    disagree the index is what the NEXT COMMIT will record. That is the moment
    this is asked: an operator bumps a leg (`git add <leg>` moves the gitlink
    in the index), edits the pin file to match, and runs the validator to find
    out whether the commit they are about to make is in lockstep. Answering
    from HEAD there reports the commit being REPLACED, which fails a correct
    bump and passes a stale pin. HEAD remains the fallback, for a path the
    commit records and the index does not hold at stage 0 — one the index
    never had, and one a conflicted merge holds only at stages 1, 2 and 3.
    """
    for args, oid_at, stage_at in GITLINK_LISTINGS:
        try:
            out = git_out([*args, path], cwd=repo)
        except Refusal:
            continue
        for line in out.splitlines():
            fields = line.replace("\t", " ").split()
            if len(fields) <= oid_at or fields[0] != "160000":
                continue
            # STAGE 0 OR NOTHING. A conflicted merge leaves the index holding
            # stages 1, 2 and 3 for the same path — base, ours and theirs —
            # and none of them is a commit anybody is about to make. Taking
            # whichever came first would answer with the merge base as often
            # as not, so an unmerged path falls through to HEAD instead.
            if stage_at is not None and fields[stage_at] != "0":
                continue
            return fields[oid_at].lower()
    return None


# ---------------------------------------------------------------------------
# The naming policy
# ---------------------------------------------------------------------------


#: How a `<Domainx><Product>` name is split into the domain stem and the
#: PRODUCT it claims descent from. The stem is greedy, so a name carrying two
#: `x<Upper>` splits (`MedxDataxChart`) is read at the RIGHTMOST one, which is
#: the same reading the family's own pattern gives.
DESCENDANT_SPLIT_PATTERN = r"^(?P<stem>[A-Za-z][A-Za-z0-9]*)x(?P<product>[A-Z][A-Za-z0-9]*)$"

#: `open<Product>` is the canonical referent and is what a manifest records.
#: `openx<Product>` is accepted as well because the neutral family itself
#: admits an x-stem (`openxFactory`) and `codexFactory` descends from exactly
#: that; a descendant that pinned the x-stem spelling has a referent, and
#: refusing it would be a spelling rule masquerading as a semantic one.
DESCENDANT_REFERENT_TEMPLATES = ("open{product}", "openx{product}")

#: Where a descendant RECORDS the pin chain it reaches its referent through
#: (2026-09-05). It is a key of a leg's `naming:` block in `project.yaml`, and
#: the policy file names it too (`referent.chain.record_field`) so a fork reads
#: the rule rather than this constant.
CHAIN_RECORD_FIELD = "referent_chain"

#: The key read in a LINK's own manifest when a link is verified: `openXdox`
#: is a link of `codexDox`'s chain because `openXdox`'s `project.yaml` declares
#: `neutral_product_pins: [openDox]`.
CHAIN_LINK_DECLARED_BY = "neutral_product_pins"

#: A recorded chain longer than this is BROKEN rather than walked. Overridable
#: from the policy data (`referent.chain.max_length`).
CHAIN_MAX_LENGTH = 8

#: The status of a link whose tree could not be read. It is a WARNING and
#: never changes the classification: the recorded declaration is the offline
#: fact, and verification is the stronger check available when the other tree
#: happens to be on the disk.
CHAIN_UNVERIFIED = "declared-unverified"

#: The env var naming a local checkout of a neutral product, so a CI job that
#: pre-seeds one checkout per pinned product can be read without a flag.
#: `<PRODUCT>` is the declared name, upper-cased, with every character outside
#: `[A-Z0-9_]` turned into `_` — `openGlass` -> `SHAPE_PIN_SOURCE_OPENGLASS`.
#: ONE variable answers both questions asked of such a checkout: the digest
#: `validate-pins.py` recomputes from it, and the chain-link declaration
#: `resolve_referent` verifies against it.
PIN_SOURCE_ENV_PREFIX = "SHAPE_PIN_SOURCE_"


def pin_source_env_name(product: str) -> str:
    return PIN_SOURCE_ENV_PREFIX + re.sub(r"[^A-Z0-9_]", "_", product.upper())


def form_id(family_id: str, role_id: str | None) -> str:
    """`("project-leg", "assembly")` -> `"project-leg/assembly"`."""
    return f"{family_id}/{role_id}" if role_id else family_id


class ReferentResolution:
    """WHETHER, and HOW, a `<Domainx><Product>` name reaches its referent.

    Five answers, and the classification depends on which one:

      `none`                 nothing is declared — the form is a bare claim
      `direct`               the referent itself is pinned (2026-09-02)
      `verified`             a recorded chain, every link read and agreeing
      `declared-unverified`  a recorded chain, at least one link's tree not
                             reachable. STILL A DESCENDANT: the declaration is
                             the offline fact and the tree is the stronger
                             check, available or not
      `broken`              a recorded chain that does not hold — it does not
                             start at a pin this project declares, does not
                             end at a referent this name could have, is longer
                             than the policy admits, repeats a link, or names
                             a link whose OWN manifest declares something else

    `warnings` are for a reader, never for an exit code; `reason` is the
    sentence `--explain` prints, and for `broken` it NAMES the link that broke,
    because "the chain is invalid" sends the reader to read four manifests.
    """

    REACHED = ("direct", "verified", CHAIN_UNVERIFIED)

    def __init__(self, status: str = "none", referent: str | None = None,
                 chain=(), reason: str = "", warnings=(), unverified=()):
        self.status = status
        self.referent = referent
        self.chain = tuple(chain)
        self.reason = reason
        self.warnings = tuple(warnings)
        self.unverified = tuple(unverified)

    @property
    def reached(self) -> bool:
        """Is the referent reached — by a direct pin or by a held chain?"""
        return self.status in self.REACHED

    @property
    def by_chain(self) -> bool:
        return self.status in ("verified", CHAIN_UNVERIFIED)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"ReferentResolution({self.status!r}, {self.referent!r}, "
                f"chain={list(self.chain)!r})")


class Classification(tuple):
    """`(family_id, role_id)`, carrying every OTHER form the name satisfies.

    A 2-tuple BY CONSTRUCTION: `classify()` has always returned one and every
    caller compares against `("project-leg", "assembly")`, so widening it would
    have been a silent break at every call site. What is new rides alongside —
    `also_matches`, the forms that were not chosen, and `reason`, the sentence
    `--explain` prints — because an overlap that is resolved without being
    RECORDED is exactly the failure this change exists to fix.
    """

    def __new__(cls, family: str, role: str | None,
                also_matches=(), reason: str = "",
                referent: ReferentResolution | None = None):
        self = super().__new__(cls, (family, role))
        self.family = family
        self.role = role
        self.also_matches = tuple(also_matches)
        self.reason = reason
        # HOW the referent was reached, when the name claimed one at all —
        # `None` for a name that is not in `<Domainx><Product>` form. A caller
        # that only ever compared the 2-tuple is unaffected; a caller that
        # needs to RECORD the chain (the manifest's `naming:` block) or to
        # WARN about an unverified link reads it here rather than re-deriving
        # it, which is how the writer and the checker stay one rule.
        self.referent = referent or ReferentResolution()
        return self

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"Classification({self.family!r}, {self.role!r}, "
                f"also_matches={list(self.also_matches)!r})")


class NamingPolicy:
    """Ordered classifier over `contracts/repository-naming.yaml`.

    ORDER IS SEMANTIC, AND TWO OF THE FIVE FORMS ARE UNAMBIGUOUS BY
    CONSTRUCTION. `open<Product>` and `<X>-Install` say what they are in their
    own characters: nothing else can spell them and nothing else needs to be
    consulted, so they win outright.

    A NEUTRAL PRODUCT MAY ELECT THE SHAPE, and that does not disturb the
    sentence above. Ruled by Brett Heap on 2026-09-05: "elect the shape for
    both, follow the pin chain, no family yet", for `openDox` and `openXdox`.
    The FORM still wins — `openDox` classifies as `neutral-product`, and no
    declaration turns it into a leg — and it ADDITIONALLY carries the role the
    project declares, where the family's `admits_declared_role:` lists that
    role AND the name also satisfies that `project-leg` form. Electing confers
    nothing, so `openDox` mounting `openDox-spec` and `openDox-code` is a fact
    about LAYOUT and not a claim about neutrality: the same reasoning that
    already lets a DECLARED domain descendant be an assembly root (2026-09-02).
    `<X>-Install` is admitted into no role and could not be — a hyphenated name
    satisfies no leg form at all — so it stays refused as any leg.

    THE DESCENDANT FORM IS DIFFERENT, and this is the ruling of 2026-09-02
    (Brett Heap): `<Domainx><Product>` is a CLAIM OF DESCENT, and a claim needs
    a REFERENT. The name is classified as a domain descendant only when the
    project declares a pin on the matching `open<Product>`. Without that pin
    the DECLARED ROLE wins — `MedxScribe` in a `MedxSoft` org is an ordinary
    project's assembly root, not a descendant of an `openScribe` that does not
    exist — and the descendant form is recorded in `also_matches` rather than
    thrown away. The check stays OFFLINE: a declared pin is a fact in the
    project's own tree, so no GitHub lookup is ever needed to classify a name.

    A DECLARED-ONLY FORM IS REPORTED ONLY WHEN IT IS ASKED FOR. The `family`
    holder form (2026-09-04) is spelled exactly like an assembly root — one
    CamelCase token — and what makes a repository a family is `family.yaml` in
    its own tree, not its characters. A family carrying `declared_only: true`
    is therefore skipped by `matches()` unless the caller passes that family's
    id as `declared_role`. That is not a convenience: without it, adding the
    form would have widened `also_matches` for every bare CamelCase name in
    every manifest already in the wild, and `validate-manifest.py` compares
    that list exactly.

    `matches()` still reports every form a name satisfies, in the data's
    precedence order, so an overlap stays visible instead of being resolved in
    silence.
    """

    def __init__(self, data: dict):
        self.data = data
        families = data.get("families") or []
        if not families:
            raise Refusal("policy-empty", "the naming policy declares no families")
        self.families = sorted(families, key=lambda f: f.get("precedence", 99))
        for family in self.families:
            family["_re"] = re.compile(family["pattern"])
            for role in family.get("roles") or []:
                role["_re"] = re.compile(role["pattern"])
            referent = family.get("referent") or {}
            family["_split_re"] = re.compile(
                referent.get("split_pattern") or DESCENDANT_SPLIT_PATTERN)
            templates = [referent.get("canonical_template")
                         or DESCENDANT_REFERENT_TEMPLATES[0]]
            templates += list(referent.get("also_accepted") or [])
            family["_referent_templates"] = tuple(templates)
        topic = data.get("topic") or {}
        self.topic_pattern = re.compile(topic.get("pattern", r"^xf-project-[a-z0-9-]+$"))
        self.topic_template = topic.get("template", "xf-project-{id}")

    @classmethod
    def load(cls, path: Path) -> "NamingPolicy":
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise Refusal("policy-unreadable", f"{path}: not a mapping")
        if data.get("kind") != "repository-naming-policy":
            raise Refusal(
                "policy-wrong-kind",
                f"{path}: kind is {data.get('kind')!r}, expected "
                "'repository-naming-policy'",
            )
        return cls(data)

    # -- the data ----------------------------------------------------------

    def family(self, family_id: str) -> dict | None:
        return next((f for f in self.families if f["id"] == family_id), None)

    def requires_referent(self, family_id: str) -> bool:
        """Does this family's form only CLAIM membership until something else
        is declared? Declared in the data, so a fork can read the rule."""
        family = self.family(family_id)
        return bool(family and family.get("requires_referent"))

    # -- referents ---------------------------------------------------------

    def descendant_referents(self, name: str) -> tuple[str, ...]:
        """The neutral products `name` would have to pin to BE a descendant.

        Empty when the name is not in `<Domainx><Product>` form at all. The
        first entry is canonical and is what a manifest records.
        """
        family = self.family("domain-descendant")
        if family is None or not family["_re"].match(name):
            return ()
        match = family["_split_re"].match(name)
        if not match:
            return ()
        product = match.groupdict().get("product")
        if not product:
            return ()
        return tuple(t.format(product=product)
                     for t in family["_referent_templates"])

    def descendant_referent(self, name: str) -> str | None:
        """The CANONICAL `open<Product>` a descendant-form name claims."""
        referents = self.descendant_referents(name)
        return referents[0] if referents else None

    def chain_rule(self) -> dict:
        """The `referent.chain:` block of the descendant family, as data.

        Empty when a fork's policy declares none, which switches the chain off
        without switching the referent rule off: the direct pin is the older
        rule and answers on its own.
        """
        family = self.family("domain-descendant") or {}
        return (family.get("referent") or {}).get("chain") or {}

    def resolve_referent(self, name: str, declared_pins=None,
                         referent_chain=None,
                         link_pins=None) -> ReferentResolution:
        """How `name` reaches its referent, given what is DECLARED about it.

        `declared_pins` is `project.yaml`'s `neutral_product_pins:`;
        `referent_chain` is the chain that manifest RECORDS (2026-09-05);
        `link_pins` maps a link's name to the pins ITS OWN manifest declares,
        for the links whose trees were reachable — a link absent from the
        mapping is `declared-unverified`, which is not a failure.

        A RECORDED CHAIN IS READ FIRST, because it is what the project says it
        relies on and a record nothing consults is not a record. The direct pin
        answers when no chain is recorded and whenever a recorded one does not
        hold, so no name that classified as a descendant on 2026-09-02 stops
        being one here: the chain only ever ADDS an answer.
        """
        referents = self.descendant_referents(name)
        if not referents:
            return ReferentResolution()
        pins = {repo_basename(str(pin)).casefold()
                for pin in (declared_pins or ()) if pin}
        direct = next((r for r in referents if r.casefold() in pins), None)

        def directly(extra_warnings=()) -> ReferentResolution:
            return ReferentResolution(
                "direct", direct, reason=f"declared pin on {direct}",
                warnings=extra_warnings)

        chain = [repo_basename(str(link)) for link in (referent_chain or ())
                 if str(link).strip()]
        if not chain:
            if direct is not None:
                return directly()
            return ReferentResolution(
                reason="no referent pin declared (it would need "
                       + " or ".join(referents) + ")")

        rule = self.chain_rule()
        rendered = " → ".join(chain)
        max_length = int(rule.get("max_length") or CHAIN_MAX_LENGTH)

        def broken(detail: str) -> ReferentResolution:
            said = f"the declared chain {rendered} is broken ({detail})"
            if direct is not None:
                # The direct pin was sufficient before any chain was recorded
                # and stays sufficient now. A broken chain beside it is a
                # RECORD to repair, reported as a warning, never an answer
                # taken away.
                return directly((f"{said}; the direct pin on {direct} is what "
                                 "classifies this name",))
            return ReferentResolution("broken", None, chain, reason=said)

        if len(chain) > max_length:
            return broken(f"it names {len(chain)} links and the policy admits "
                          f"at most {max_length}")
        seen = [link.casefold() for link in chain]
        if len(set(seen)) != len(seen):
            return broken("it repeats a link, so it is a cycle rather than a "
                          "chain")
        if chain[0].casefold() not in pins:
            return broken(f"it begins at {chain[0]}, which is not in this "
                          "project's `neutral_product_pins:` — the first "
                          "entry is the pin this project actually holds")
        final = next((r for r in referents
                      if r.casefold() == chain[-1].casefold()), None)
        if final is None:
            return broken(f"it ends at {chain[-1]}, but {name} would need "
                          + " or ".join(referents))

        # The link's pins are kept in the SPELLING ITS MANIFEST USES, so a
        # broken-link message quotes what the other tree actually says.
        available = {str(link).casefold():
                     {repo_basename(str(pin))
                      for pin in (pins_of or ()) if pin}
                     for link, pins_of in (link_pins or {}).items()
                     if pins_of is not None}
        warnings: list[str] = []
        unverified: list[str] = []
        for holder, held in zip(chain, chain[1:]):
            declared = available.get(holder.casefold())
            if declared is None:
                unverified.append(holder)
                warnings.append(
                    f"{CHAIN_UNVERIFIED}: {holder} declaring a pin on {held} "
                    f"is a fact in {holder}'s own tree, which is not "
                    f"reachable here (a sibling checkout, "
                    f"{pin_source_env_name(holder)}, or --link-source "
                    f"{holder}=<path> would let it be read). The recorded "
                    "chain still classifies.")
                continue
            if held.casefold() not in {pin.casefold() for pin in declared}:
                return broken(
                    f"{holder} declares "
                    + (", ".join(sorted(declared)) if declared else "no "
                       "neutral-product pin at all")
                    + f", not {held}")
        status = CHAIN_UNVERIFIED if unverified else "verified"
        return ReferentResolution(
            status, final, chain,
            reason=f"declared pin chain {rendered}"
                   + (f" ({len(unverified)} link"
                      + ("" if len(unverified) == 1 else "s")
                      + " declared-unverified)" if unverified else ""),
            warnings=warnings, unverified=unverified)

    # -- classification ----------------------------------------------------

    def declared_only(self, family_id: str) -> bool:
        """Is this form reported ONLY when the reader declares it?

        Declared in the data, like `requires_referent`, so a fork can read the
        rule rather than infer it from the classifier's behaviour.
        """
        family = self.family(family_id)
        return bool(family and family.get("declared_only"))

    def matches(self, name: str,
                declared_role: str | None = None) -> list[tuple[str, str | None]]:
        """Every (family_id, role_id) the name satisfies, in precedence order.

        A `declared_only` family is included only when `declared_role` is that
        family's own id — `matches("InkRouter")` is unchanged by the family
        form existing, and `matches("InkRouter", "family")` reports it.
        """
        found: list[tuple[str, str | None]] = []
        for family in self.families:
            if family.get("declared_only") and declared_role != family["id"]:
                continue
            roles = family.get("roles") or []
            hit = False
            for role in roles:
                if role["_re"].match(name):
                    found.append((family["id"], role["id"]))
                    hit = True
            if not hit and family["_re"].match(name):
                found.append((family["id"], None))
        return found

    def classify(self, name: str, declared_role: str | None = None,
                 declared_pins=None, referent_chain=None,
                 link_pins=None) -> Classification | None:
        """Classify `name`, given what the project DECLARES about itself.

        `declared_role` is one of {assembly, spec, code}; `declared_pins` is the
        set of neutral products the project declares a pin on; `referent_chain`
        is the chain of neutral-product pins the manifest RECORDS as reaching
        its referent, and `link_pins` is what the reachable links declare. All
        are optional and all are read from `project.yaml` where one exists.

        The order:
          1. `neutral-product` and 2. `install` — unambiguous by construction,
             carrying a DECLARED role their family ADMITS where the name also
             satisfies that leg form (2026-09-05).
          3. a DECLARED-ONLY form the caller asked for by name (`family`).
          4. `domain-descendant` — ONLY when a referent is REACHED, directly
             (2026-09-02) or through the recorded chain (2026-09-05).
          5. `project-leg` in the DECLARED role, when the name satisfies it.
          6. `project-leg` residual — the widest form, deliberately last.
        """
        matched = self.matches(name, declared_role)
        if not matched:
            return None
        by_family: dict[str, list[str | None]] = {}
        for family_id, role_id in matched:
            by_family.setdefault(family_id, []).append(role_id)
        resolution = self.resolve_referent(name, declared_pins, referent_chain,
                                           link_pins)

        def answer(family_id: str, role_id: str | None, reason: str,
                   matched_key: tuple | None = None) -> Classification:
            # `matched_key` is the entry of `matched` this answer CONSUMES. It
            # differs from the answer itself in exactly one case: a descendant
            # that takes its role from the declared one, where the consumed
            # entry is `("domain-descendant", None)`. Without it the family a
            # name was classified INTO would also be listed among the forms it
            # was not, which is a record contradicting itself.
            key = matched_key if matched_key is not None else (family_id, role_id)
            also = [form_id(f, r) for f, r in matched if (f, r) != key]
            return Classification(family_id, role_id, also, reason, resolution)

        # The leg roles the NAME satisfies, read once: the unambiguous forms
        # consult them too, because a role is only ever admitted where the name
        # can actually spell it.
        leg_roles = [r for r in (by_family.get("project-leg") or []) if r]
        for family_id in ("neutral-product", "install"):
            if family_id not in by_family:
                continue
            family = self.family(family_id) or {}
            # A NEUTRAL PRODUCT MAY ELECT THE SHAPE (Brett Heap, 2026-09-05).
            # The form is not being overridden — it is still the answer, and
            # the entry this CONSUMES is `(family_id, None)`, so
            # `project-leg/assembly` survives in `also_matches` exactly as it
            # did before. What is added is the ROLE the project declares, and
            # only where the family's data admits it and the name satisfies
            # that leg form. Electing confers nothing, so this records a
            # layout, not a claim; it is the same MECHANISM as the descendant
            # branch below, both reading `admits_declared_role:` — but this
            # branch is deliberately STRICTER about what an absent key means.
            # With no `admits_declared_role:` in the data this branch admits
            # NOTHING (`or ()`), because the admission itself is the
            # 2026-09-05 rule and the file must say so or grant nothing. The
            # descendant branch below falls back to `or ("assembly",)`
            # instead, because that key predates this ruling: it keeps the
            # 2026-09-02 behaviour for a policy file that never wrote the key
            # at all, and changing the fallback would be changing that
            # ruling's answer out from under a file silent about it.
            admitted = family.get("admits_declared_role") or ()
            if by_family[family_id][0] is None and declared_role is not None \
                    and declared_role in admitted and declared_role in leg_roles:
                title = str(family.get("title") or family_id).lower()
                return answer(
                    family_id, declared_role,
                    f"the {family_id} form is unambiguous by construction; it "
                    f"carries the {declared_role} role it declares — a {title} "
                    "may elect the shape (Brett Heap, 2026-09-05)",
                    (family_id, None))
            return answer(family_id, by_family[family_id][0],
                          f"the {family_id} form is unambiguous by "
                          "construction, so it needs nothing declared")

        # A declared-only form the caller ASKED for. It sits above the leg
        # forms in the decision even though its precedence is below them: the
        # precedence orders the residual reading of a bare name, and this is
        # not a residual reading — somebody said which question they were
        # asking, and `family.yaml` in that tree is what let them.
        if declared_role and self.declared_only(declared_role) \
                and declared_role in by_family:
            return answer(declared_role, by_family[declared_role][0],
                          f"the {declared_role} form, DECLARED — the name is "
                          "spelled like an assembly root and only the "
                          "declaration tells them apart")

        claimed = "domain-descendant" in by_family
        referents = self.descendant_referents(name) if claimed else ()
        # REACHED, not merely pinned (2026-09-05). A direct pin answers exactly
        # as it did before; a RECORDED chain that holds answers too, and a
        # chain with an unreadable link answers with a warning rather than
        # falling back — the declaration is the offline fact.
        declared = resolution.referent if resolution.reached else None
        if claimed and (declared or not self.requires_referent("domain-descendant")):
            # A DESCENDANT MAY CARRY LEGS (Brett Heap, 2026-09-02). The
            # descendant family declares no roles of its own, so the role a
            # descendant answers with is the one the project DECLARES, and
            # only where the name also satisfies that leg form. `MedxGlass`
            # pins `openGlass` AND mounts `MedxGlass-spec` and
            # `MedxGlass-code`: it is a descendant AND the assembly root.
            # Refusing that pair would have made the descendant ruling and the
            # three-repository shape mutually exclusive, which neither ruling
            # says and both organisations that have one need both of.
            family = self.family("domain-descendant") or {}
            admitted = family.get("admits_declared_role") or ("assembly",)
            role = by_family["domain-descendant"][0]
            if role is None and declared_role is not None \
                    and declared_role in leg_roles \
                    and declared_role in admitted:
                role = declared_role
            if declared and resolution.by_chain:
                reason = (f"descendant form reaching {declared} through the "
                          f"{resolution.reason} → domain descendant")
                if role:
                    reason += (f", carrying the {role} role it declares (a "
                               "descendant may carry legs)")
            elif declared:
                reason = (f"descendant form with a declared pin on {declared} "
                          "→ domain descendant")
                if role:
                    reason += (f", carrying the {role} role it declares (a "
                               "descendant may carry legs)")
            else:
                reason = "descendant form (this policy does not require a referent)"
            return answer("domain-descendant", role, reason,
                          ("domain-descendant", by_family["domain-descendant"][0]))

        chosen = None
        if declared_role is not None and declared_role in leg_roles:
            chosen, how = declared_role, "by declared role"
        elif leg_roles:
            chosen, how = leg_roles[0], "by its residual project-leg form"
        if chosen is not None:
            if claimed and resolution.status == "broken":
                # NAME THE LINK. "The chain is invalid" sends the reader to
                # read four manifests; `resolution.reason` says which one.
                reason = (f"descendant form, {resolution.reason} → {chosen} "
                          f"root {how}")
            elif claimed:
                reason = (f"descendant form, no referent pin declared (it would "
                          f"need {referents[0]}) → {chosen} root {how}")
            else:
                reason = f"project leg, {chosen} {how}"
            return answer("project-leg", chosen, reason)

        # Unreachable with the shipped patterns — every descendant-form name is
        # also a bare CamelCase token — but a policy file is data, and data can
        # be edited. An unresolved claim is reported as one rather than being
        # promoted to a classification by exhaustion.
        return answer("domain-descendant", by_family["domain-descendant"][0],
                      f"descendant form, no referent pin declared (it would need "
                      f"{referents[0] if referents else 'open<Product>'}) and the "
                      "name satisfies no other form")

    def topic_for(self, project_id: str) -> str:
        return self.topic_template.format(id=project_id)


def checked_value(what: str, value, pattern: re.Pattern = SAFE_ARG_RE) -> str:
    """Validate one caller-supplied value BEFORE it becomes a command argument.

    ARGUMENT INJECTION IS THE THREAT, not shell injection: every command here
    is a list with `shell=False`, so there is no shell to inject into — but
    `git` reads its own arguments, and a `--tracking-branch` of
    `--upload-pack=…` is a command, not a branch. A value that begins with `-`
    is therefore refused outright, and the rest must be spellable as a branch
    name, a path, a repository name or a commit.

    The values that reach here come from a command line, from `project.yaml`
    and — in `adopt-project.py` — from an adoption plan that an AI assistant
    may have written. The last of those is exactly why this is a check in the
    code rather than a note in the README.

    `pattern` is `SAFE_PATH_RE` for a value that is a FILESYSTEM PATH the
    operator named: a Windows path carries a drive colon and backslashes, and
    refusing those would refuse the platform rather than the threat. Whichever
    pattern is passed, a leading `-` and a value that is nothing but
    whitespace are refused here, before it is consulted.
    """
    text = str(value)
    if text.startswith("-") or not text.strip() or not pattern.fullmatch(text):
        raise Refusal(
            "unsafe-value",
            f"{what} is {text!r}, which is not a value this tool will put on "
            "a `git` or `gh` command line",
            "Remediation: a leading `-` is refused because git reads its own "
            "arguments (`--upload-pack=…` is a command, not a branch); the "
            f"rest must match {pattern.pattern}.")
    return text


def accepts_role(found, role: str) -> bool:
    """Is `found` an acceptable classification for a leg DECLARED as `role`?

    ONE definition, consulted by the scaffold, by `adopt-project.py` and by a
    project's own `validate-manifest.py`, because three copies of "which forms
    may be an assembly root" is how the second one starts disagreeing with the
    first.

    Three forms pass. The ordinary one is the project-leg family in exactly the
    declared role. The second is the 2026-09-02 ruling that a DECLARED domain
    descendant may be an assembly root carrying legs: `MedxGlass` pins
    `openGlass` and still mounts `MedxGlass-spec` and `MedxGlass-code`. The
    third is the 2026-09-05 ruling that a NEUTRAL PRODUCT may elect the shape
    and be its own assembly root: `openDox` mounts `openDox-spec` and
    `openDox-code`, and electing confers nothing, so that is a fact about
    layout and not a claim about neutrality.

    EVERY ONE OF THE THREE ADMITS A FACT, NEVER A CLAIM. `classify` returns
    `("domain-descendant", "assembly")` only when the pin is DECLARED, and
    `("neutral-product", "assembly")` only when the policy's
    `admits_declared_role:` admits the role AND the name satisfies the
    `project-leg/assembly` form — so by the time a tuple reaches here, the
    question this function asks has already been answered by the policy.

    `spec` and `code` are unreachable for the two CamelCase forms on purpose:
    `openDox-spec` and `MedxGlass-spec` carry the lowercase suffix and are
    ordinary project legs, which is why the check is `role == "assembly"`.
    """
    if found is None:
        return False
    if tuple(found) == ("project-leg", role):
        return True
    return role == "assembly" and tuple(found) in (
        ("domain-descendant", "assembly"), ("neutral-product", "assembly"))


def repo_basename(repository: str) -> str:
    """`opensoft/openRepoShape` -> `openRepoShape`; a bare name is returned."""
    return repository.rsplit("/", 1)[-1]


# ---------------------------------------------------------------------------
# Reading a CHAIN LINK's own declaration, offline
# ---------------------------------------------------------------------------
#
# A recorded chain (2026-09-05) says `codexDox` pins `openXdox` and `openXdox`
# pins `openDox`. The first half is a fact in codexDox's tree; the second is a
# fact in openXdox's, and these three helpers read it WHERE THAT TREE HAPPENS
# TO BE ON THE DISK and nowhere else. Nothing here fetches, clones or asks a
# host: a link that cannot be read locally is reported as declared-unverified
# by the caller, which is not a failure.
#
# The lookup order is the one `validate-pins.py` already uses for a neutral
# product's checkout, down to the same environment variable, because it is the
# same checkout answering a second question about the same product.


def link_manifest_path(path) -> Path | None:
    """`<dir>` -> `<dir>/project.yaml`; a file is taken as the manifest."""
    candidate = Path(path)
    if candidate.is_dir():
        candidate = candidate / "project.yaml"
    return candidate if candidate.is_file() else None


def declared_neutral_pins(manifest_path,
                          key: str = CHAIN_LINK_DECLARED_BY) -> set[str] | None:
    """The neutral products a manifest DECLARES a pin on, or None.

    None means "this tree could not answer" — no manifest, unreadable YAML, or
    a file that is not a mapping — and is deliberately distinct from the empty
    set, which means "this tree answered, and declares no pin at all". The
    first is unverified and the second breaks a chain that runs through it.
    """
    path = link_manifest_path(manifest_path)
    if path is None:
        return None
    try:
        data = load_yaml(path)
    except (YamlError, Refusal, OSError, UnicodeDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return {repo_basename(str(pin)) for pin in (data.get(key) or []) if pin}


def resolve_link_source(product: str, root: Path | None = None,
                        keyed_sources: dict | None = None,
                        default_source=None) -> tuple[Path | None, str | None]:
    """Where `product`'s own manifest can be read, if anywhere at all.

      1. `--link-source <product>=<path>` (case-insensitive on the name)
      2. `SHAPE_PIN_SOURCE_<PRODUCT>` in the environment
      3. a checkout sitting BESIDE this project (`../openXdox`)
      4. a bare `--link-source <path>` with no `product=` prefix
    """
    candidates: list[tuple[Path, str]] = []
    keyed = (keyed_sources or {}).get(product.casefold())
    if keyed is not None:
        candidates.append((Path(keyed), f"--link-source {product}=..."))
    env_name = pin_source_env_name(product)
    env_value = os.environ.get(env_name)
    if env_value:
        candidates.append((Path(env_value), f"${env_name}"))
    if root is not None:
        sibling = Path(root).resolve().parent / product
        candidates.append((sibling, f"sibling checkout ({sibling})"))
    if default_source is not None:
        candidates.append((Path(default_source), "--link-source"))
    for path, how in candidates:
        if link_manifest_path(path) is not None:
            return path, how
    return None, None


def link_pins_from_trees(links, root: Path | None = None,
                         keyed_sources: dict | None = None,
                         default_source=None,
                         key: str = CHAIN_LINK_DECLARED_BY) -> dict[str, set]:
    """`{link: the pins ITS manifest declares}` for the links that answered.

    A link whose tree is not on the disk is simply ABSENT from the mapping,
    which is what `NamingPolicy.resolve_referent` reads as declared-unverified.
    """
    found: dict[str, set] = {}
    for link in links:
        name = repo_basename(str(link))
        path, _how = resolve_link_source(name, root, keyed_sources,
                                         default_source)
        if path is None:
            continue
        pins = declared_neutral_pins(path, key)
        if pins is None:
            continue
        found[name.casefold()] = pins
    return found


def find_repo_root(start: Path) -> Path:
    path = Path(start).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise Refusal("not-a-git-repo", f"no .git found at or above {start}")


def die(exc: Refusal, stream=sys.stderr) -> int:
    print(str(exc), file=stream)
    return 2
