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

#: Every value this family lets a caller put on a `git` or `gh` command line.
#: Deliberately narrow: letters, digits, and the punctuation that real branch
#: names, paths, repository names and commits are spelled with.
SAFE_ARG_RE = re.compile(r"^[A-Za-z0-9._/@+~-]{1,255}$")

REMEDIATION = (
    "Remediation: run `git submodule update --init --recursive`, then "
    "`python3 scripts/validate-pins.py`. If the PIN itself is stale, advance "
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


def _scalar(raw: str) -> Any:
    text = raw.strip()
    if text == "" or text in ("null", "~", "Null", "NULL"):
        return None
    if text[0] == "'" and text[-1] == "'" and len(text) >= 2:
        return text[1:-1].replace("''", "'")
    if text[0] == '"' and text[-1] == '"' and len(text) >= 2:
        body = text[1:-1]
        for a, b in (("\\n", "\n"), ("\\t", "\t"), ('\\"', '"'), ("\\\\", "\\")):
            body = body.replace(a, b)
        return body
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


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def recorded_gitlink(repo: Path, path: str) -> str | None:
    """The commit the SUPERPROJECT records for the submodule at `path`.

    HEAD first, index second. HEAD is what a reviewer sees in the pull request;
    the index fallback exists so the validator still answers in a tree where
    the gitlink has been staged but not yet committed — which is precisely the
    moment the lockstep rule is about to be broken.
    """
    for args in (["ls-tree", "HEAD", "--", path], ["ls-files", "-s", "--", path]):
        try:
            out = git_out(args, cwd=repo)
        except Refusal:
            continue
        for line in out.splitlines():
            fields = line.replace("\t", " ").split()
            if len(fields) >= 3 and fields[0] == "160000":
                return fields[2].lower()
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


def form_id(family_id: str, role_id: str | None) -> str:
    """`("project-leg", "assembly")` -> `"project-leg/assembly"`."""
    return f"{family_id}/{role_id}" if role_id else family_id


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
                also_matches=(), reason: str = ""):
        self = super().__new__(cls, (family, role))
        self.family = family
        self.role = role
        self.also_matches = tuple(also_matches)
        self.reason = reason
        return self

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (f"Classification({self.family!r}, {self.role!r}, "
                f"also_matches={list(self.also_matches)!r})")


class NamingPolicy:
    """Ordered classifier over `contracts/repository-naming.yaml`.

    ORDER IS SEMANTIC, AND TWO OF THE FOUR FORMS ARE UNAMBIGUOUS BY
    CONSTRUCTION. `open<Product>` and `<X>-Install` say what they are in their
    own characters: nothing else can spell them and nothing else needs to be
    consulted, so they win outright.

    THE DESCENDANT FORM IS DIFFERENT, and this is the ruling of 2026-09-02
    (Brett Heap): `<Domainx><Product>` is a CLAIM OF DESCENT, and a claim needs
    a REFERENT. The name is classified as a domain descendant only when the
    project declares a pin on the matching `open<Product>`. Without that pin
    the DECLARED ROLE wins — `MedxScribe` in a `MedxSoft` org is an ordinary
    project's assembly root, not a descendant of an `openScribe` that does not
    exist — and the descendant form is recorded in `also_matches` rather than
    thrown away. The check stays OFFLINE: a declared pin is a fact in the
    project's own tree, so no GitHub lookup is ever needed to classify a name.

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

    # -- classification ----------------------------------------------------

    def matches(self, name: str) -> list[tuple[str, str | None]]:
        """Every (family_id, role_id) the name satisfies, in precedence order."""
        found: list[tuple[str, str | None]] = []
        for family in self.families:
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
                 declared_pins=None) -> Classification | None:
        """Classify `name`, given what the project DECLARES about itself.

        `declared_role` is one of {assembly, spec, code}; `declared_pins` is the
        set of neutral products the project declares a pin on. Both are
        optional and both are read from `project.yaml` where one exists.

        The order:
          1. `neutral-product` and 2. `install` — unambiguous by construction.
          3. `domain-descendant` — ONLY when a referent is declared.
          4. `project-leg` in the DECLARED role, when the name satisfies it.
          5. `project-leg` residual — the widest form, deliberately last.
        """
        matched = self.matches(name)
        if not matched:
            return None
        pins = {repo_basename(str(pin)).casefold()
                for pin in (declared_pins or ()) if pin}
        by_family: dict[str, list[str | None]] = {}
        for family_id, role_id in matched:
            by_family.setdefault(family_id, []).append(role_id)

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
            return Classification(family_id, role_id, also, reason)

        for family_id in ("neutral-product", "install"):
            if family_id in by_family:
                return answer(family_id, by_family[family_id][0],
                              f"the {family_id} form is unambiguous by "
                              "construction, so it needs nothing declared")

        claimed = "domain-descendant" in by_family
        referents = self.descendant_referents(name) if claimed else ()
        declared = next((r for r in referents if r.casefold() in pins), None)
        leg_roles = [r for r in (by_family.get("project-leg") or []) if r]
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
            if declared:
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
            if claimed:
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
    """
    text = str(value)
    if text.startswith("-") or not pattern.fullmatch(text):
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

    Two forms pass. The ordinary one is the project-leg family in exactly the
    declared role. The second is the 2026-09-02 ruling that a DECLARED domain
    descendant may be an assembly root carrying legs: `MedxGlass` pins
    `openGlass` and still mounts `MedxGlass-spec` and `MedxGlass-code`. The
    descendant classification is only ever returned when the pin is DECLARED
    (see `NamingPolicy.classify`), so this admits a fact, never a claim.
    """
    if found is None:
        return False
    if tuple(found) == ("project-leg", role):
        return True
    return role == "assembly" and tuple(found) == ("domain-descendant", "assembly")


def repo_basename(repository: str) -> str:
    """`opensoft/openRepoShape` -> `openRepoShape`; a bare name is returned."""
    return repository.rsplit("/", 1)[-1]


def find_repo_root(start: Path) -> Path:
    path = Path(start).resolve()
    for candidate in [path, *path.parents]:
        if (candidate / ".git").exists():
            return candidate
    raise Refusal("not-a-git-repo", f"no .git found at or above {start}")


def die(exc: Refusal, stream=sys.stderr) -> int:
    print(str(exc), file=stream)
    return 2
