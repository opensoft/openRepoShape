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
  - `same_repository` and the remote-url arithmetic under it — the ONE
    definition of whether two remote spellings name one repository, which
    `shape-doctor.py` reports by and `scripts/siblings.py` refuses by.
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

#: Marks a `_Rec` built from a block scalar, carrying its key and body
#: instead of raw text. A NUL byte never appears in this reader's input (YAML
#: is text), so it cannot collide with a real key or value; spelled once
#: because `python:S1192` counts three repeats of the same literal.
_BLOCK_SENTINEL = "\x00BLOCK\x00"


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


#: A block scalar's HEADER: `|` or `>`, optionally with a chomping indicator
#: and an explicit indentation digit. Spelled once, beside the pair of
#: functions that read the body it introduces.
_BLOCK_HEADER_RE = re.compile(r"[|>][-+]?\d*")


def _significant_text(raw: str, line: int) -> str | None:
    """The stripped line, or `None` for a line that tokenises to nothing.

    Split out of `_tokenise` for #135. One refusal and both of this reader's
    "nothing here" cases are decided by the raw line ALONE, before any
    indentation, marker or key has been read: a tab in the indentation is
    refused outright, and a blank line or a whole-line comment carries no
    record at all.
    """
    if "\t" in raw[: len(raw) - len(raw.lstrip())]:
        raise YamlError(f"line {line}: tab used for indentation")
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    return stripped


def _document_marker(marker: str, seen_doc: bool) -> bool:
    """`seen_doc` after a `---` or `...` line. Split out of `_tokenise` (#135).

    A SECOND `---` opens a second document, which this reader refuses rather
    than guess which of them its caller meant. `...` ends a document and says
    nothing about how many there have been, so it leaves the flag where it is.
    """
    if marker == "---":
        if seen_doc:
            raise YamlError("multiple documents are not supported")
        return True
    return seen_doc


def _peel_dashes(recs: list[_Rec], indent: int, content: str,
                 line: int) -> tuple[int, str]:
    """Peel leading `- ` markers into DASH records so a sequence item's
    content sits at its own column, which is where its sibling keys are.

    Split out of `_tokenise` for #135. It returns the column and the text that
    are LEFT once every marker on the line has a record of its own, which is
    what the rest of the line is then read at.
    """
    while True:
        m = _DASH_RE.match(content)
        if not m:
            return indent, content
        recs.append(_Rec(indent, "", True, line))
        indent += len(m.group(0))
        content = content[m.end():]


def _refuse_unsupported(content: str, line: int) -> None:
    """The two constructs this reader will not guess at, refused by name.

    Split out of `_tokenise` for #135. An explicit key and a merge key each
    have a meaning the reader would have to invent, and an invented meaning in
    a validator is a wrong answer with a confident tone.
    """
    if content.startswith("? "):
        raise YamlError(f"line {line}: explicit keys are not supported")
    if content.startswith("<<"):
        raise YamlError(f"line {line}: merge keys are not supported")


def _opens_block_scalar(kv: tuple[str, str] | None) -> bool:
    """Does a split `key: rest` introduce a literal or folded block scalar?

    Split out of `_tokenise` for #135. `|`, `>`, `|-`, `>2` and the rest of
    that alphabet are HEADERS, and the value is the lines below them; a `rest`
    that merely BEGINS with one of those characters (`>= 3`) is an ordinary
    scalar and is read as one, which is why the whole of it must match.
    """
    return (kv is not None and kv[1][:1] in ("|", ">")
            and _BLOCK_HEADER_RE.fullmatch(kv[1]) is not None)


def _block_scalar_body(raw_lines: list[str], i: int,
                       indent: int) -> tuple[list[str], int]:
    """A block scalar's body lines, and the index of the line after them.

    Split out of `_tokenise` for #135. The body is every following line MORE
    INDENTED than the key, with the first such line's column taken as the
    block's own indentation and stripped from all of them. A blank line
    belongs to the body whatever its column, because it has none.
    """
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
    return body, i


def _fold_block_body(body: list[str]) -> str:
    """A FOLDED (`>`) block scalar's body, joined the way folding joins it.

    Split out of `_tokenise` for #135. A blank line is a newline of its own
    and every other line is joined to the one before it with a space; a body
    whose LAST line is blank is stripped of newlines at both ends, because the
    trailing one is the chomping indicator's to decide.
    """
    folded: list[str] = []
    for line in body:
        if line == "":
            folded.append("\n")
        elif folded and folded[-1] not in ("", "\n"):
            folded.append(" " + line)
        else:
            folded.append(line)
    if body and body[-1] == "":
        return "".join(folded).strip("\n")
    return "".join(folded)


def _block_scalar_text(header: str, body: list[str]) -> str:
    """A block scalar's body as the one string its key takes as a value.

    Split out of `_tokenise` for #135. `|` keeps every line break and `>`
    folds them; the `-` chomping indicator drops the trailing newline, and its
    absence leaves exactly one, which is YAML's clip behaviour.
    """
    if header[0] == "|":
        joined = "\n".join(body)
    else:
        joined = _fold_block_body(body)
    if header.endswith("-"):
        return joined.rstrip("\n")
    return joined.rstrip("\n") + "\n"


def _tokenise(text: str) -> list[_Rec]:
    """The `_Rec` stream `_parse_nodes` reads, one record per significant line.

    THE RULE THIS FUNCTION IMPLEMENTS IS THE ORDER, which is why each step of
    it is a named helper above (#135): a line that tokenises to nothing, a
    document marker, the `- ` markers peeled off the front, the two refusals,
    a block scalar's header and the body swallowed under it, and last an
    ordinary line kept as its own record.
    """
    recs: list[_Rec] = []
    raw_lines = text.splitlines()
    i = 0
    seen_doc = False
    while i < len(raw_lines):
        raw = raw_lines[i]
        i += 1
        stripped = _significant_text(raw, i)
        if stripped is None:
            continue
        if stripped in ("---", "..."):
            seen_doc = _document_marker(stripped, seen_doc)
            continue
        indent, content = _peel_dashes(
            recs, len(raw) - len(raw.lstrip(" ")), _strip_comment(stripped), i)
        if content == "":
            continue
        _refuse_unsupported(content, i)
        kv = _split_key(content)
        if _opens_block_scalar(kv):
            # A block scalar: swallow every following line more indented than
            # the key, and keep it as one string.
            body, i = _block_scalar_body(raw_lines, i, indent)
            recs.append(_Rec(indent, "", False, i))
            recs[-1].text = (_BLOCK_SENTINEL + kv[0] + "\x00"
                             + _block_scalar_text(kv[1], body))
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
            if not rec.dash and not rec.text.startswith(_BLOCK_SENTINEL) \
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


def _nested_value(recs: list[_Rec], i: int, indent: int) -> tuple[Any, int]:
    """The value of a `key:` with NOTHING after the colon, and the index past it.

    Split out of `_parse_mapping` for #135. A sequence may sit at the key's own
    column or deeper, because `- ` markers are conventionally written flush
    with the key they belong to, so it is admitted at `>= indent`. A nested
    mapping must be strictly deeper, or it is a SIBLING key rather than this
    key's value. Neither, and the key's value is null.
    """
    if i < len(recs) and recs[i].dash and recs[i].indent >= indent:
        return _parse_sequence(recs, i, recs[i].indent)
    if i < len(recs) and recs[i].indent > indent:
        return _parse_nodes(recs, i, recs[i].indent)
    return None, i


def _parse_mapping(recs: list[_Rec], i: int, indent: int) -> tuple[dict, int]:
    out: dict[str, Any] = {}
    while i < len(recs) and not recs[i].dash and recs[i].indent == indent:
        rec = recs[i]
        if rec.text.startswith(_BLOCK_SENTINEL):
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
            out[key], i = _nested_value(recs, i, indent)
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
    except OSError:  # FileNotFoundError (no `gh` on PATH) is already an OSError
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


#: The forms decided by the CHARACTERS ALONE: `open` in front, `-Install`
#: behind, `-wip` behind (2026-09-10, openRepoShape#81). They need nothing
#: declared — no role, no pin, no manifest — so `classify()` answers them
#: BEFORE the forms that do. The order WITHIN this tuple is inert, because no
#: name can satisfy two of them.
#:
#: IN CODE RATHER THAN IN THE POLICY DATA, deliberately, and it is the one
#: rule here that is. A `unambiguous_by_construction:` key read out of the
#: file would mean a NEW classifier reading an OLD copied policy — the two are
#: separate rows of a project's `shape-pin.yaml` and `update-shape.py` can
#: move one without the other — classifying every `open<Product>` as a project
#: leg, because a file silent about the key would grant nothing. So the list
#: lives with the code that consults it, and a fork that adds a form of its
#: own adds it here beside its pattern.
UNAMBIGUOUS_FORMS = ("neutral-product", "install", "workspace")

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


# ---------------------------------------------------------------------------
# The pieces a referent resolution is assembled from
# ---------------------------------------------------------------------------
#
# Split out of `NamingPolicy.resolve_referent` for #135, each answering one
# question that function used to answer inline. NONE OF THEM KNOWS WHAT A
# `ReferentResolution` IS, deliberately: a resolution is still built in
# exactly the places it was, so the reader who wants to know how a STATUS is
# chosen still finds the whole of that in one function.


def _pinned_basenames(declared_pins) -> set[str]:
    """The repositories a manifest's `neutral_product_pins:` name, casefolded.

    Casefolded because every comparison made against them — a referent
    template's output, a chain's first link — is written in whatever case its
    own file chose, and a pin is a fact about WHICH repository, not about how
    it was typed.
    """
    return {repo_basename(str(pin)).casefold()
            for pin in (declared_pins or ()) if pin}


def _chain_links(referent_chain) -> list[str]:
    """A recorded chain's links, as basenames, in the spelling it records.

    An empty or whitespace-only entry is not a link and is dropped, so a
    manifest that left a blank list item behind has not thereby recorded a
    chain that cannot hold.
    """
    return [repo_basename(str(link)) for link in (referent_chain or ())
            if str(link).strip()]


def _referent_in(referents, wanted) -> str | None:
    """The first of `referents` whose casefolded name is one of `wanted`."""
    return next((r for r in referents if r.casefold() in wanted), None)


def _link_declarations(link_pins) -> dict[str, set[str]]:
    """`{link: the pins ITS manifest declares}` for the links that answered.

    The pins are kept in the SPELLING THAT LINK'S MANIFEST USES, so a
    broken-link message quotes what the other tree actually says. A link whose
    tree could not be read is ABSENT rather than empty: the two mean opposite
    things — unverified, and declaring nothing at all — and the caller reads
    the difference.
    """
    return {str(link).casefold():
            {repo_basename(str(pin)) for pin in (pins_of or ()) if pin}
            for link, pins_of in (link_pins or {}).items()
            if pins_of is not None}


def _chain_link_findings(chain, link_pins) -> tuple:
    """What each link of a recorded chain says about the next one along it.

    Split out of `NamingPolicy.resolve_referent` for #135. Returns the detail
    of the FIRST contradiction — or `None` when there is none — beside the
    warnings and the links whose own trees could not be read. A link that did
    not answer is `declared-unverified` and never a failure: the recorded
    declaration is the offline fact, and reading the other tree is the
    stronger check, available or not.
    """
    available = _link_declarations(link_pins)
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
            return (f"{holder} declares "
                    + (", ".join(sorted(declared)) if declared else "no "
                       "neutral-product pin at all")
                    + f", not {held}", warnings, unverified)
    return None, warnings, unverified


def _unverified_note(unverified) -> str:
    """The parenthetical a held chain's reason carries when a link went unread.

    An independent statement rather than a ternary nested inside a ternary
    (python:S3358) — the plural "s" is decided before the note it belongs to
    is built, not while it is being built.
    """
    if not unverified:
        return ""
    plural = "" if len(unverified) == 1 else "s"
    return f" ({len(unverified)} link{plural} declared-unverified)"


# ---------------------------------------------------------------------------
# The pieces a classification is assembled from
# ---------------------------------------------------------------------------
#
# Split out of `NamingPolicy.classify` for #135. The two that decide a branch
# return an ANSWER'S INGREDIENTS — `(family_id, role_id, reason, matched_key)`
# — and never a `Classification`, because `classify`'s own `answer()` closure
# is the single place `also_matches` is computed: a branch that built its own
# classification would be a second place for that record to be got wrong.


def _forms_by_family(matched) -> dict:
    """`[(family, role), …]` grouped as `{family: [role, …]}`, order kept.

    `matches()` reports every form a name satisfies in the data's precedence
    order; this is that same list read BY FAMILY, which is how each branch of
    the classifier asks whether the form it decides is among them.
    """
    by_family: dict[str, list[str | None]] = {}
    for family_id, role_id in matched:
        by_family.setdefault(family_id, []).append(role_id)
    return by_family


def _leg_roles(by_family) -> list:
    """The leg roles the NAME satisfies, read once.

    Every branch of the classifier consults them, the unambiguous forms
    included, because a role is only ever admitted where the name can actually
    spell it: `openDox` may carry the `assembly` role it declares because
    `openDox` also satisfies `project-leg/assembly`, and `Widget-Install`
    carries none because a hyphenated name satisfies no leg form at all.
    """
    return [r for r in (by_family.get("project-leg") or []) if r]


def _other_forms(matched, key) -> list:
    """Every form the name satisfies EXCEPT the one an answer consumes.

    This is `Classification.also_matches`: an overlap resolved without being
    RECORDED is exactly the failure that field exists to prevent.
    """
    return [form_id(f, r) for f, r in matched if (f, r) != key]


def _descendant_reason(declared, resolution, role: str | None) -> str:
    """The sentence `--explain` prints for a descendant-form classification.

    HOW the referent was reached is the first half — through the recorded
    chain, by a direct pin, or not required at all by this policy — and the
    role the name also carries is the second. A policy that requires no
    referent never reaches that second half, because it has no referent to
    name and nothing was declared for it to carry.
    """
    if declared and resolution.by_chain:
        reason = (f"descendant form reaching {declared} through the "
                  f"{resolution.reason} → domain descendant")
    elif declared:
        reason = (f"descendant form with a declared pin on {declared} "
                  "→ domain descendant")
    else:
        return "descendant form (this policy does not require a referent)"
    if role:
        reason += (f", carrying the {role} role it declares (a "
                   "descendant may carry legs)")
    return reason


def _leg_answer(claimed: bool, leg_roles, declared_role, resolution,
                referents) -> tuple | None:
    """The answer for the residual `project-leg` reading, or None.

    The role is the DECLARED one where the name satisfies it, and the widest
    leg form it satisfies otherwise. The reason records what the name ALSO
    claimed, and for a broken chain it quotes `resolution.reason` rather than
    summarising it: NAME THE LINK — "the chain is invalid" sends the reader
    off to read four manifests, and that sentence says which one broke.
    """
    chosen = None
    if declared_role is not None and declared_role in leg_roles:
        chosen, how = declared_role, "by declared role"
    elif leg_roles:
        chosen, how = leg_roles[0], "by its residual project-leg form"
    if chosen is None:
        return None
    if claimed and resolution.status == "broken":
        reason = (f"descendant form, {resolution.reason} → {chosen} "
                  f"root {how}")
    elif claimed:
        reason = (f"descendant form, no referent pin declared (it would "
                  f"need {referents[0]}) → {chosen} root {how}")
    else:
        reason = f"project leg, {chosen} {how}"
    return ("project-leg", chosen, reason, None)


class NamingPolicy:
    """Ordered classifier over `contracts/repository-naming.yaml`.

    ORDER IS SEMANTIC, AND THREE OF THE SIX FORMS ARE UNAMBIGUOUS BY
    CONSTRUCTION. `open<Product>`, `<X>-Install` and `<user>-wip` say what
    they are in their own characters: nothing else can spell them and nothing
    else needs to be consulted, so they win outright. `UNAMBIGUOUS_FORMS` is
    the list, and says why it is in code rather than in the data.

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

    THE SIXTH FORM IS NOT A REPOSITORY OF A PROJECT AT ALL. `workspace`
    (2026-09-10, openRepoShape#81) is `<user>-wip`, the private repository one
    person owns to index their own unfinished work, and it is unambiguous by
    construction rather than declared-only: the literal `-wip` suffix is
    spelled by no other form, so it needs no `--role` and is admitted into no
    role — `accepts_role` refuses it as an assembly leg, which is how "nothing
    in this standard creates one" is enforced rather than merely written down.
    Adding it changed no existing name's answer for a reason the family form
    could not give: no form above admits a `-wip` suffix, so every name it
    classifies is a name that matched NOTHING before.

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
        pins = _pinned_basenames(declared_pins)
        direct = _referent_in(referents, pins)

        def directly(extra_warnings=()) -> ReferentResolution:
            return ReferentResolution(
                "direct", direct, reason=f"declared pin on {direct}",
                warnings=extra_warnings)

        chain = _chain_links(referent_chain)
        if not chain:
            if direct is not None:
                return directly()
            return ReferentResolution(
                reason="no referent pin declared (it would need "
                       + " or ".join(referents) + ")")

        rendered = " → ".join(chain)

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

        problem = self._chain_shape_problem(name, chain, pins, referents)
        if problem is not None:
            return broken(problem)
        final = _referent_in(referents, {chain[-1].casefold()})
        contradiction, warnings, unverified = _chain_link_findings(chain,
                                                                   link_pins)
        if contradiction is not None:
            return broken(contradiction)
        status = CHAIN_UNVERIFIED if unverified else "verified"
        return ReferentResolution(
            status, final, chain,
            reason=f"declared pin chain {rendered}"
                   + _unverified_note(unverified),
            warnings=warnings, unverified=unverified)

    def _chain_shape_problem(self, name: str, chain: list,
                             pins: set, referents) -> str | None:
        """What is wrong with a recorded chain's SHAPE, or None if nothing is.

        Split out of `resolve_referent` for #135, asking the four questions in
        the order that function asked them: is the chain longer than the
        policy admits, does it repeat a link, does it begin at a pin this
        project actually holds, and does it end at a referent this name could
        have. Each answer becomes the `detail` of a `broken` resolution, which
        is where the reader is told WHICH link broke rather than merely that
        one did.
        """
        max_length = int(self.chain_rule().get("max_length") or CHAIN_MAX_LENGTH)
        if len(chain) > max_length:
            return (f"it names {len(chain)} links and the policy admits "
                    f"at most {max_length}")
        seen = [link.casefold() for link in chain]
        if len(set(seen)) != len(seen):
            return "it repeats a link, so it is a cycle rather than a chain"
        if chain[0].casefold() not in pins:
            return (f"it begins at {chain[0]}, which is not in this "
                    "project's `neutral_product_pins:` — the first "
                    "entry is the pin this project actually holds")
        if _referent_in(referents, {chain[-1].casefold()}) is None:
            return (f"it ends at {chain[-1]}, but {name} would need "
                    + " or ".join(referents))
        return None

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
          1. `neutral-product`, 2. `install` and 3. `workspace` — unambiguous
             by construction (`UNAMBIGUOUS_FORMS`), carrying a DECLARED role
             their family ADMITS where the name also satisfies that leg form
             (2026-09-05). `install` and `workspace` admit none.
          4. a DECLARED-ONLY form the caller asked for by name (`family`).
          5. `domain-descendant` — ONLY when a referent is REACHED, directly
             (2026-09-02) or through the recorded chain (2026-09-05).
          6. `project-leg` in the DECLARED role, when the name satisfies it.
          7. `project-leg` residual — the widest form, deliberately last.
        """
        matched = self.matches(name, declared_role)
        if not matched:
            return None
        by_family = _forms_by_family(matched)
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
            return Classification(family_id, role_id,
                                  _other_forms(matched, key), reason, resolution)

        leg_roles = _leg_roles(by_family)
        unambiguous = self._unambiguous_answer(by_family, declared_role,
                                               leg_roles)
        if unambiguous is not None:
            return answer(*unambiguous)

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
            return answer(*self._descendant_answer(by_family, declared_role,
                                                   leg_roles, declared,
                                                   resolution))

        leg = _leg_answer(claimed, leg_roles, declared_role, resolution,
                          referents)
        if leg is not None:
            return answer(*leg)

        # Unreachable with the shipped patterns — every descendant-form name is
        # also a bare CamelCase token — but a policy file is data, and data can
        # be edited. An unresolved claim is reported as one rather than being
        # promoted to a classification by exhaustion.
        if claimed:
            return answer("domain-descendant", by_family["domain-descendant"][0],
                          f"descendant form, no referent pin declared (it would need "
                          f"{referents[0] if referents else 'open<Product>'}) and the "
                          "name satisfies no other form")

        # AND A FORM NO BRANCH ABOVE CLAIMED IS STILL REPORTED, not raised.
        # `matched` is not empty — some family's pattern said yes — so the
        # honest answer is its highest-precedence entry, with a reason saying
        # this classifier has no rule of its own for it. That is the path a
        # SEVENTH form reaches on the day it is added to the data and before
        # anybody writes its branch here: until `workspace` was wired into
        # `UNAMBIGUOUS_FORMS` (2026-09-10) the descendant line above raised
        # `KeyError: 'domain-descendant'` for `brett-wip`, which is a data file
        # crashing the tool that reads it instead of being read by it.
        family_id, role_id = matched[0]
        return answer(family_id, role_id,
                      f"the {family_id} form, by precedence; this classifier "
                      "has no rule of its own for it")

    def _unambiguous_answer(self, by_family, declared_role,
                            leg_roles) -> tuple | None:
        """The answer for a form decided by the CHARACTERS ALONE, or None.

        Split out of `classify` for #135. It returns an answer's INGREDIENTS —
        `(family_id, role_id, reason, matched_key)` — rather than a
        `Classification`, so `classify`'s own `answer()` closure stays the one
        place `also_matches` is computed and a classification is built.

        A NEUTRAL PRODUCT MAY ELECT THE SHAPE (Brett Heap, 2026-09-05). The
        form is not being overridden — it is still the answer, and the entry
        this CONSUMES is `(family_id, None)`, so `project-leg/assembly`
        survives in `also_matches` exactly as it did before. What is added is
        the ROLE the project declares, and only where the family's data admits
        it and the name satisfies that leg form. Electing confers nothing, so
        this records a layout, not a claim; it is the same MECHANISM as
        `_descendant_answer` below, both reading `admits_declared_role:` — but
        this one is deliberately STRICTER about what an absent key means. With
        no `admits_declared_role:` in the data it admits NOTHING (`or ()`),
        because the admission itself is the 2026-09-05 rule and the file must
        say so or grant nothing. `_descendant_answer` falls back to
        `or ("assembly",)` instead, because that key predates this ruling: it
        keeps the 2026-09-02 behaviour for a policy file that never wrote the
        key at all, and changing the fallback would be changing that ruling's
        answer out from under a file silent about it.
        """
        for family_id in UNAMBIGUOUS_FORMS:
            if family_id not in by_family:
                continue
            family = self.family(family_id) or {}
            admitted = family.get("admits_declared_role") or ()
            if by_family[family_id][0] is None and declared_role is not None \
                    and declared_role in admitted and declared_role in leg_roles:
                title = str(family.get("title") or family_id).lower()
                return (family_id, declared_role,
                        f"the {family_id} form is unambiguous by construction; it "
                        f"carries the {declared_role} role it declares — a {title} "
                        "may elect the shape (Brett Heap, 2026-09-05)",
                        (family_id, None))
            return (family_id, by_family[family_id][0],
                    f"the {family_id} form is unambiguous by "
                    "construction, so it needs nothing declared", None)
        return None

    def _descendant_answer(self, by_family, declared_role, leg_roles,
                           declared, resolution) -> tuple:
        """The answer for a descendant claim `classify` decided to honour.

        Split out of `classify` for #135, returning the same
        `(family_id, role_id, reason, matched_key)` ingredients as
        `_unambiguous_answer` above. TWO PATHS REACH IT, and
        `_descendant_reason` words both: a referent REACHED — by a direct pin
        or through a chain that holds, with `declared` naming it — and a
        policy whose descendant family does not require a referent at all,
        where `declared` is None and the reason says exactly that.

        A DESCENDANT MAY CARRY LEGS (Brett Heap, 2026-09-02). The descendant
        family declares no roles of its own, so the role a descendant answers
        with is the one the project DECLARES, and only where the name also
        satisfies that leg form. `MedxGlass` pins `openGlass` AND mounts
        `MedxGlass-spec` and `MedxGlass-code`: it is a descendant AND the
        assembly root. Refusing that pair would have made the descendant
        ruling and the three-repository shape mutually exclusive, which
        neither ruling says and both organisations that have one need both of.
        """
        family = self.family("domain-descendant") or {}
        admitted = family.get("admits_declared_role") or ("assembly",)
        role = by_family["domain-descendant"][0]
        if role is None and declared_role is not None \
                and declared_role in leg_roles \
                and declared_role in admitted:
            role = declared_role
        return ("domain-descendant", role,
                _descendant_reason(declared, resolution, role),
                ("domain-descendant", by_family["domain-descendant"][0]))

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
# Is this the SAME REPOSITORY? (2026-09-12, #146, #155, #149 and #157)
# ---------------------------------------------------------------------------
#
# ONE DEFINITION, BECAUSE TWO TOOLS ACT ON IT AND MUST NOT DISAGREE.
# `templates/family-root/scripts/siblings.py` REFUSES to fetch into a clone
# beside a family holder whose `origin` is not the member's remote (`WRONG
# ORIGIN`), and `shape-doctor.py`'s `members` row REPORTS whether that same
# directory is the member's working clone. While those two answered out of
# two copies of the rule, a fork beside the holder was counted by the report
# and skipped by the tool — about the same directory, which is the one thing
# a doctor must not do (#146).
#
# WHY HERE. The doctor imports nothing out of `templates/`: those files are
# the standard's PAYLOAD, materialized into somebody else's repository, and a
# report that imported them would be reading the copy it is meant to be
# comparing against. This module is the one file both may read — it is
# stdlib-only, `scaffold-project.py` copies it into every assembly root and
# `family.py init` into every family holder, where it lands beside
# `siblings.py` in `scripts/` and is imported by the same `sys.path` line
# `bootstrap.py` and `validate-family.py` already use. The cost is that this
# file is DIGEST-PINNED, so every estate reads `upstream-changed` for it until
# it re-pins; #147 paid for a second copy instead while a re-pin was in
# flight, and #155 is the change that was told to ride the next one.
#
# ONE BEHAVIOUR CHANGED WITH THE MOVE, AND ONLY ONE (#149): case folds for a
# remote that names a HOST and is PRESERVED for a filesystem path, so two bare
# repositories on a case-sensitive disk that differ only in case stop being
# called one repository. It is argued where it is decided, in
# `_remote_names_a_host` below. Everything else answered exactly what the two
# copies answered, spelling for spelling.
#
# ONE CHANGED AFTER IT, AND ONLY ONE (2026-09-13, #157): two remotes that are
# BOTH filesystem paths are one repository only when their normalised keys are
# EQUAL. The trailing `owner/repo` fallback used to match them too, which made
# `/srv/a/IRRS.git` and `/other/a/IRRS.git` one repository — two bare
# repositories under two roots, told apart by exactly the prefix the tail
# throws away. It is argued where it is decided, in `same_repository` below.
#
# NOTHING HERE FETCHES ANYTHING, ASKS GIT ANYTHING OR TOUCHES A DISK. Every
# function below is string arithmetic over remotes a caller has already read,
# which is what lets `tests/test_windows_paths.py` ask the Windows questions
# from Linux and `tests/test_shape_doctor.py` hold the whole rule to one
# table. IT IS ALSO WHY `remote_local_path` STOPS WHERE IT DOES (#157): it
# says which spelling names a path and what path it names, and the CALLER
# that has the disk resolves it — `os.path.realpath` lives in
# `siblings.py::same_repository_here` and its twin in the doctor, never
# here, because one directory reached through a symlink is a fact about a
# machine and not about a string. Those two ask THIS function first and the
# disk only if it says no, so resolving can add an answer and never take one
# away (Codex, PR #160).

#: ANY `<scheme>://` prefix, by PATTERN rather than by a list of the schemes
#: git happens to speak. Two reasons, in that order: a list has to be kept in
#: step with git's transports — `ssh`, `git`, `file`, `https`, `git+ssh` and
#: whatever an estate's own helper registers — and a list is also a list of
#: LITERALS, one of them the clear-text HTTP scheme, which a scanner reads as
#: a transport this file chose rather than as a string it strips (SonarCloud
#: python:S5332, on PR #79). Dropping it is what makes
#: `file:///srv/mirrors/Repo.git` and `/srv/mirrors/Repo.git` one answer, and
#: `ssh://git@example.com/Org/Repo.git` and the scp spelling
#: `git@example.com:Org/Repo.git` another.
REMOTE_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")

#: The same scheme with NOTHING AFTER IT, which is what one `..` too many
#: would leave behind if it were allowed to go on trimming.
REMOTE_SCHEME_ONLY_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:/*$")

#: A Windows drive, and the ONLY colon a filesystem path may carry: without
#: this, `D:\remotes\Repo.git` reads as git's `host:path` scp syntax and its
#: drive letter is eaten as a host. The same distinction `SAFE_PATH_RE` above
#: draws for a value on a command line, for the same reason.
REMOTE_DRIVE_RE = re.compile(r"^[A-Za-z]:$")


def _remote_body(url: str) -> str:
    """A remote with its scheme, its credential and its trailing `/` gone.

    THE PART EVERY QUESTION BELOW IS ASKED OF, taken off in one place rather
    than in each of them: `<scheme>://` because the transport is not the
    identity, `[user[:password]@]` because whoever fetches is not the
    repository, and `\\` for `/` because only the SPELLING of a separator is
    at stake. What is left is a host and a path, git's scp `host:path`, or a
    path on its own — which is exactly the question `_remote_names_a_host`
    then answers.

    AND THE EMPTY AUTHORITY IN FRONT OF A WINDOWS DRIVE GOES WITH THE SCHEME
    (2026-09-13, #157, Copilot). `file:///D:/mirrors/Fam.git` is the file url
    RFC 8089 blesses and git accepts, and taking `file://` off it leaves
    `/D:/mirrors/Fam.git` — a leading `/` that belongs to the URL and not to
    the path. Without this it is the one spelling of a Windows remote that
    does not fold to `D:\\mirrors\\Fam.git`'s key, and a person who mounted a
    member by its file url would be told their working clone is a stranger.
    It comes off here, where every question below is asked, rather than in
    whichever one noticed.

    ONLY WHEN A SCHEME WAS THERE TO LEAVE IT BEHIND, though, because that `/`
    is the URL's and a remote with no scheme never had one (Copilot, PR
    #160). `/D:/mirrors/IRRS.git` written as a PATH is a directory called
    `D:` under a POSIX root — absurd, and somebody's — and folding it into
    the Windows drive `D:/mirrors/IRRS.git` would report two paths that no
    single machine could even both hold as one repository.
    """
    stripped = url.strip().replace("\\", "/").rstrip("/")
    text = REMOTE_SCHEME_RE.sub("", stripped)
    if text != stripped and text.startswith("/") and REMOTE_DRIVE_RE.match(
            text[1:3]):
        text = text[1:]                  # file:///D:/mirrors/Fam.git
    if "@" in text.split("/", 1)[0]:      # git@github.com:Org/Repo.git
        text = text.split("@", 1)[1]
    return text


def _remote_names_a_host(url: str) -> bool:
    """Does this remote name a HOST rather than a filesystem PATH?

    THE CASE QUESTION, AND ONLY THE CASE QUESTION (2026-09-12, #149). A
    remote that names a host compares case-INSENSITIVELY: GitHub treats an
    owner and a repository name that way, so `https://GitHub.com/Org/Repo`
    and `https://github.com/org/repo` are one repository, and a report that
    called them two would send somebody to delete a good clone over a
    capitalisation. A FILESYSTEM PATH does not: `/srv/mirrors/IRRS.git` and
    `/srv/mirrors/irrs.git` are two different bare repositories on a
    case-sensitive host, and the estates that mount members from bare
    repositories on disk — every fixture in this suite, and any mirror-based
    family — are exactly the ones where a remote is a path.

    A REMOTE IS A PATH WHEN IT IS ONE OF THESE FOUR, and a host otherwise:

      * an ABSOLUTE path, `/srv/mirrors/Repo.git`;
      * `file:///srv/mirrors/Repo.git`, which is the same answer arrived at
        by a different road — that spelling carries an EMPTY authority, so
        the scheme leaves an absolute path and no host behind it;
      * a WINDOWS DRIVE, `D:\\a\\remotes\\Fam.git` — the one colon that is
        NOT scp syntax;
      * a RELATIVE path written `./` or `../`, which is the spelling git
        itself requires of a relative remote (Copilot and Codex, PR #156):
        a holder whose own `origin` is `../mirrors/Fam.git` is as much on a
        disk as one whose origin is absolute, and lowercasing it would put
        back the very false positive #149 is about.

    Everything else names a host: `<scheme>://<host>/…`, git's scp spelling
    `[user@]host:path`, and the bare `Org/Repo` a `family.yaml` `repository:`
    row is written as, which names a forge repository and no directory at all.

    THE BARE TWO-SEGMENT FORM IS READ AS A FORGE NAME, DELIBERATELY, and it
    is the one place this cannot be decided from the string: `mirrors/Fam.git`
    might be a directory under whatever the process is standing in, and
    nothing in it says so. `Org/Repo` is what every manifest in this standard
    writes and what `siblings.py::clone_url` turns into
    `https://github.com/Org/Repo.git`, so that is what an unanchored value is
    taken for — and a person who means a path from somewhere writes `./`,
    which git requires of them anyway.

    STRICT ON EVERY PLATFORM, DELIBERATELY. Windows and macOS filesystems are
    case-INsensitive by default, so a platform probe would make a report
    change its answer with the machine it ran on; "a path compares
    case-sensitively" is the honest rule, and the one #149 argues for.
    """
    text = _remote_body(url)
    if not text or text.startswith("/"):
        return False
    first = text.split("/", 1)[0]
    if first in (".", ".."):
        return False
    return REMOTE_DRIVE_RE.match(first) is None


def remote_key(url: str) -> str:
    """ONE remote spelling folded to the identity underneath it.

    A HUMAN'S OWN CLONE IS NOT REQUIRED TO SPELL A REMOTE THE WAY A MANIFEST
    OR `.gitmodules` DOES. `git@github.com:Org/Repo.git`,
    `https://github.com/Org/Repo` and `ssh://git@github.com/Org/Repo.git` are
    one repository, and a report that called them three would tell somebody
    their working clone is a stranger's over a punctuation difference. So the
    scheme, the credential prefix, the scp colon, a trailing `/` and a `.git`
    suffix all come off, and what is left — `host/owner/repo` — is the thing
    worth comparing. A bare `owner/repo`, which is how `family.yaml`'s
    `repository:` is written, folds to itself and is matched by its tail in
    `same_repository` below.

    THE CASE IS FOLDED ONLY FOR A REMOTE THAT NAMES A HOST, which
    `_remote_names_a_host` decides and #149 argues; a path keeps the case it
    was written in. It is asked of the remote AS IT WAS WRITTEN, because the
    scp colon this function is about to turn into a `/` is the one thing that
    tells a Windows drive from a host.
    """
    text = _remote_body(url)
    fold_case = _remote_names_a_host(url)
    if ":" in text.split("/", 1)[0]:     # the scp spelling's one separator
        text = text.replace(":", "/", 1)
    if text.lower().endswith(".git"):
        text = text[:-4]
    return (text.lower() if fold_case else text).strip("/")


def remote_is_a_path(base: str) -> bool:
    """Is this remote a FILESYSTEM PATH rather than a url?

    THE SEPARATOR QUESTION, which is a different one from the case question
    above: only a path may be WALKED with a backslash in it, because a url's
    separator is `/` on every platform, and `file:///srv/mirrors/Repo.git` is
    a url by that measure however absolute the path inside it is.

    THE COLON IS A DRIVE LETTER'S OR IT IS SCP SYNTAX.
    `D:\\a\\remotes\\Fam.git` is a path; `git@host:org/Repo.git` and
    `host:path/Repo.git` are urls in git's scp spelling; anything with a
    `<scheme>://` is a url outright.
    """
    if REMOTE_SCHEME_RE.match(base):
        return False
    head = base.replace("\\", "/").split("/", 1)[0]
    return ":" not in head or REMOTE_DRIVE_RE.match(head) is not None


def remote_local_path(url: str) -> str | None:
    """The path on A MACHINE this remote names, or None when it names none.

    THE STRING HALF OF A QUESTION THIS MODULE MAY NOT FINISH (2026-09-13,
    #157). `same_repository` answers for two filesystem paths by exact
    equality, so one directory reached through a SYMLINK — `/var/folders/…`
    and `/private/var/folders/…` are the same temporary directory on macOS,
    which is how this suite's own fixtures reach one — is two repositories to
    it. Only the machine holding that symlink can say otherwise, and nothing
    here is allowed to ask a disk anything. So this says which spelling names
    a path and what path it names, and the two callers that HAVE a disk —
    `templates/family-root/scripts/siblings.py::verify_sibling` and
    `shape-doctor.py::working_clone` — resolve it with `os.path.realpath`
    before they compare. The string rule stays in one place either way (#155).

    A PATH IS THE SAME FOUR-WAY QUESTION `_remote_names_a_host` DECIDES, asked
    once rather than twice, and what comes back is `_remote_body`'s spelling
    of it — the scheme gone, `\\` folded to `/`, the empty authority in front
    of a Windows drive dropped — which is the spelling every other question
    here is asked of. `file:///srv/mirrors/Repo.git` and
    `/srv/mirrors/Repo.git` name one directory, `file:///D:/mirrors/Fam.git`
    and `D:\\mirrors\\Fam.git` name another, and Windows opens a path spelled
    with either separator.

    NONE FOR A RELATIVE REMOTE, DELIBERATELY, though `./mirrors/Fam.git` is as
    much a path as an absolute one. `..` is resolved against the
    SUPERPROJECT'S REMOTE by git's own rule and by `join_remote` above — a
    caller that handed it to `realpath` would resolve it against whatever
    directory the process happens to be standing in, which is the trap
    `siblings.py::resolve_relative` exists to avoid.
    """
    if _remote_names_a_host(url):
        return None
    text = _remote_body(url)
    if text.startswith("/") or REMOTE_DRIVE_RE.match(text.split("/", 1)[0]):
        return text
    return None


def _up_one(flat: str) -> str | None:
    """`flat` with its last component dropped, or None when it has none.

    A `..` TOO MANY CONSUMES NOTHING. What is left after the last component
    can be a scheme (`https:/`), an scp host (`git@host:`) or nothing at all,
    and none of those is a directory a `..` may eat — a url like that is
    wrong wherever it is read, and the clone that fails prints it. The one
    case where nothing left IS an answer is a POSIX root: the parent of
    `/Repo.git` is `/`, so the empty string comes back and the next name
    appended makes `/Other.git`. A Windows DRIVE is a component of its own
    for the same reason, and is the one colon that is not scp syntax — so it
    is asked FIRST, because `D:` is also what a one-letter scheme looks like.
    """
    if "/" not in flat:
        return None
    head = flat.rsplit("/", 1)[0]
    if REMOTE_DRIVE_RE.match(head):
        return head
    if REMOTE_SCHEME_ONLY_RE.match(head) or head.endswith(":"):
        return None
    return head


def join_remote(base: str, url: str) -> str:
    """`base` with `url`'s `../` applied — PURE STRING ARITHMETIC.

    GIT'S OWN RULE FOR A RELATIVE SUBMODULE URL, which is textual and has no
    filesystem and no platform in it: one trailing component dropped per
    `..`, one appended per name, `.` ignored. A clone that took `../Repo.git`
    literally would fetch from wherever the process happens to be standing,
    which is why git resolves it against the SUPERPROJECT'S REMOTE instead.

    THE SEPARATOR IS THE BASE'S OWN. A local path on Windows arrives from
    `git remote get-url` as `D:\\a\\_temp\\remotes\\Fam.git` with no forward
    slash anywhere in it, so a walk that split on `/` alone would drop
    nothing and append to the whole string (the `windows-latest` failure on
    PR #79). The walk therefore normalises to `/` and hands the result back
    in the spelling the remote used: git accepts either, a human comparing
    this against `git remote -v` should not have to translate it, and
    `same_repository` folds both spellings to one answer anyway.
    """
    native_backslash = remote_is_a_path(base) and "\\" in base
    flat = (base.replace("\\", "/") if native_backslash else base).rstrip("/")
    for part in url.split("/"):
        if part == "..":
            up = _up_one(flat)
            if up is not None:
                flat = up
        elif part not in (".", ""):
            flat = f"{flat}/{part}"
    return flat.replace("/", "\\") if native_backslash else flat


def resolved_remote(url: str, base: str) -> str:
    """A submodule url spelled `../<Repo>.git`, against THIS remote.

    Absolute urls are handed straight back, and so is a relative one when
    there is no remote to resolve it against — a holder with no `origin`
    names nothing this can complete, and inventing a base would be worse than
    saying so. `siblings.py::resolve_relative` is the wrapper that reads the
    holder's own `origin` and hands it here as `base`; the doctor reads the
    root's and does the same.
    """
    if not url.startswith(("./", "../")):
        return url
    return join_remote(base, url) if base else url


#: A url's CREDENTIAL — `[user[:password]@]` in front of the host, and only
#: in a url that has a scheme, which is the spelling a token is ever written
#: in (`https://x-access-token:<pat>@github.com/Org/Repo.git`). The scp form
#: `git@host:Org/Repo.git` carries a user name and no secret — ssh takes no
#: password in a url — and is left legible.
CREDENTIAL_RE = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]*://)[^/@]*@")


def redacted(url: str) -> str:
    """A remote url with any credential in it replaced by `***`.

    A REPORT PRINTS WHAT IT FINDS, AND WHAT IT FINDS CAN BE A TOKEN. Git
    permits a credential in a remote url, people do put one there, and
    `shape-doctor.py --json` is pasted into issues and kept as a CI artifact
    — so a row that quoted `origin` verbatim would publish somebody's PAT to
    everywhere the report goes (Codex and Copilot, PR #147). The raw value is
    still what `same_repository` compares; this is what gets stored and
    printed, and the host and the path — the whole of what a person needs in
    order to see which repository it is — survive.
    """
    return CREDENTIAL_RE.sub(r"\1***@", url)


def same_repository(one: str, two: str) -> bool:
    """Do two remote spellings name the SAME repository?

    The normalised identities, and failing that — when either side names a
    FORGE — the TRAILING `owner/repo` of the second: a manifest records
    `Org/Repo` with no host in it at all, and a mirror or an enterprise host
    spells the same repository under a different one. Only the second
    argument's tail is tried, because that is the reference being matched
    against — the row, or the mount — and the first is whatever a clone on
    somebody's disk happens to say.

    THE TAIL IS A FORGE QUESTION, AND ONLY A FORGE QUESTION (2026-09-13,
    #157). When BOTH sides are filesystem PATHS there is no tail match at all
    and the normalised keys must be EQUAL, so `/srv/a/IRRS.git` and
    `/other/a/IRRS.git` are two repositories — and so, still, are
    `/srv/mirrors/IRRS.git` and `/srv/mirrors/irrs.git`, which is #149's case
    rule arrived at the same way. THE DIFFERENCE IS NOT ARBITRARY: in a forge
    name the two trailing components ARE the whole identity — `Org/Repo` is an
    owner and a repository and there is nothing in front of it to lose —
    while in a path everything in front of the tail is part of the identity,
    and a fallback that drops it calls two bare repositories under two roots
    one repository (Copilot, PR #156).

    A PATH AGAINST A FORGE NAME KEEPS THE MATCH, DELIBERATELY, because that is
    what the two callers below actually need: a member mounted from a MIRROR
    has an `origin` that is a path — `/srv/mirrors/InkRouter/IRRS.git` — and
    the reference it is matched against is either the bare `InkRouter/IRRS` a
    `family.yaml` row is written as or the
    `https://github.com/InkRouter/IRRS.git` that `siblings.py::clone_url`
    derives from it. Dropping that match would call every clone in a
    mirror-based estate `WRONG ORIGIN`, the InkRouter estate's own layout
    included. It folds case for the same reason it exists: the row was typed
    by a human and is case-insensitive at the forge, so comparing it strictly
    would report a legitimate mirror clone as a stranger over a
    capitalisation, which is the fault #149 is against and not for (Copilot
    and Codex, PR #156).

    WHICH LEAVES ONE DIRECTORY SPELLED TWO WAYS TO THE CALLERS, on purpose:
    `/var/folders/…` and `/private/var/folders/…` are one temporary directory
    on macOS, only the machine holding that symlink can say so, and nothing in
    this module may ask a disk anything. `remote_local_path` above is the
    string half, and `siblings.py::same_repository_here` and
    `shape-doctor.py::same_repository_here` are the `os.path.realpath` half —
    each of them THIS function first, and the disk only when it has said no.

    THE DEFINITION `make siblings` REFUSES BY AND THE DOCTOR REPORTS BY, one
    function imported by both: `templates/family-root/scripts/siblings.py`
    and `shape-doctor.py` each import this name, and
    `tests/test_shape_doctor.py` asserts they are the same object before it
    runs the table.
    """
    left, right = remote_key(one), remote_key(two)
    if left == right:
        return True
    if not (_remote_names_a_host(one) or _remote_names_a_host(two)):
        # TWO PATHS, AND THE KEYS ARE THE WHOLE ANSWER (#157).
        return False
    tail = right.split("/")
    if len(tail) < 2:
        return False
    suffix = "/".join(tail[-2:])
    return left.lower().endswith(suffix.lower())


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
