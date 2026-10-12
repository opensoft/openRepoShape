#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize an assembly root out of `templates/assembly-root/`.

ONE MATERIALIZER, TWO CALLERS. `scaffold-project.py` builds an assembly root
in an empty directory; `adopt-project.py` builds one INSIDE a repository that
already exists and keeps its history. Those differ in exactly two ways — what
to do when a template file collides with a file the source repository already
has, and whether a Makefile needs the adopted project's `CONTRACTS_DIR` line —
so they differ by two arguments rather than by a second copy of the code.

The alternative was a second copy, and a second copy is how `shape-pin.yaml`
starts digesting a different set of files than the scaffold writes.

STANDARD LIBRARY ONLY, like everything else shipped here.

WHAT A COLLISION IS, AND WHY IT IS NOT AN OVERWRITE. Adopting in place means
the source repository's own `README.md`, `Makefile` and `.gitignore` are
already at the root and are part of its history. The shape's copies of those
names are NOT more important than the project's, and silently overwriting one
would put a byte in the split commit that no `git rm` accounts for — which is
precisely what `adopt-project.py --verify` would then report as a mismatch.
So a colliding template file is written BESIDE the original under
`collision_dir` (`shape/`) and the collision is reported for the plan's
`follow_ups:`. The human merges it; the tool never guesses. A copy whose own
path is taken -- the source keeps a `shape/README.md` of its own -- is
REFUSED, never written over (`copy_in_the_way`, #262).
"""

from __future__ import annotations

import argparse
import codecs
import datetime as _dt
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    CHAIN_RECORD_FIELD, SAFE_ARG_RE, NamingPolicy, Refusal, checked_value,
    double_quoted, file_sha256,
)

SHAPE_REPOSITORY = "opensoft/openRepoShape"


def root_key(path: PurePath, root: PurePath) -> str:
    """How a file the materializer wrote is NAMED, relative to the root.

    One spelling for both readers of it: the `path:` of a
    `contracts/shape-pin.yaml` row, and the list of what was written that the
    chmod pass matches against the copy lists.

    POSIX, ALWAYS, AND ON EVERY PLATFORM. Pin rows are POSIX paths; on Windows
    `str()` of a relative Path uses backslashes, and a key that does not match
    its own row reports every file as drift — `update-shape.py` looks the row
    up in a table keyed by `scripts/bootstrap.py` and finds nothing, so every
    copy in a directory reads as `unmapped` and `apply` refuses to re-sync a
    project that has not drifted at all. The row is also what a human reads
    and what `validate-pins.py` resolves against the root, and `Path(root,
    row)` opens a forward-slash row on Windows perfectly well — so the one
    spelling that works everywhere is the POSIX one.
    """
    return path.relative_to(root).as_posix()


def write_lf(path: Path, text: str) -> None:
    """Write text with LF line endings, on every platform.

    EVERY materialized file goes through this. `contracts/shape-pin.yaml`
    digests the bytes these writes land on, so a CRLF translation on Windows
    would give the same template a different sha256 there — the pin would
    claim "these are the shape's files" and be false on one platform. The
    shape's output is byte-identical everywhere, which is what makes the
    digest mean anything.

    `Path.write_text` grew a `newline=` parameter in 3.10 and this standard
    runs on 3.9, so the write is spelled with `open` instead.
    """
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def escape_what_stdout_cannot_encode(stream=None) -> None:
    """A character `stream` cannot encode is printed escaped, never raised on.

    WHAT WAS WRONG (#214). The tools that call this print names a person
    chose -- a source file, a `--source`, `--root`, `--out` or `--work-dir`
    path, a `--name`, an `--elected-by` -- with a plain `print`, and a stdout
    whose encoding cannot hold one raised `UnicodeEncodeError` in the middle
    of the report. On Windows that is any stdout that is not the console
    itself (a file, a pipe to `tee`, CI, an agent running the tool): Python
    gives it the ANSI code page, cp1252 on a Western-European install, and a
    Japanese file name is not in it. `adopt-project.py plan` had already
    written the plan, then exited 1 with a traceback before `plan written
    to` and before the questions it exists to ask.

    TWO HANDLERS RAISE ON SUCH A NAME, AND ONLY THOSE TWO ARE CHANGED.
    - `strict` (a POSIX locale that is not C or POSIX and not one Python
      coerces C to, so `en_US.UTF-8` but not `C.UTF-8`; and any
      `PYTHONIOENCODING=<codec>` that names no handler) becomes
      `backslashreplace`, the handler Python already gives stderr.
    - `surrogateescape` becomes `SURROGATEESCAPE_THEN_BACKSLASHREPLACE`,
      registered below. It is what CPython gives EVERY Windows stdout by
      default, the redirected cp1252 one included (`config_get_stdio_errors`
      in `Python/initconfig.c`: "On Windows, always use surrogateescape by
      default", 3.9 to 3.14), and what UTF-8 mode and the C, POSIX and
      `C.UTF-8` locales give. It covers only U+DC80..U+DCFF, the bytes a
      name that is not UTF-8 was read in with, so `日本.md` raised there
      exactly as under `strict`. The new handler writes such a byte back as
      that byte, which is surrogateescape's own rule, and writes anything
      else the encoding cannot hold as `backslashreplace` does.
    Each replacement writes what the handler it replaces would have
    written, byte for byte, and differs only where that one would have
    raised, so no run that succeeded prints anything different. Every other
    handler -- one an operator chose, `replace`, `backslashreplace` itself --
    is left as it was, and the ENCODING is never changed: a character the
    code page holds is still written in it.

    `backslashreplace` AND NOT `replace`: `\\u65e5\\u672c.md` still says which
    file it is, and two names that differ only outside the code page do not
    both print as `??.md`. (A backslash is not escaped, so a name that holds
    the six characters `\\u65e5` prints as one holding `日` does.) ONCE, AT
    THE START OF `main()`, and not at each `print`: `shape-doctor.py`'s
    `ascii_text` and `shape_advisory.printable` flatten their own text to
    ASCII on every console, which a name cannot afford -- it would change
    what a UTF-8 terminal shows -- and a guard at each site is a guard the
    next `print` goes without.

    GUARDED, because failing to set a handler is no reason to refuse the
    run: a stream a caller replaced may have no `reconfigure`, a closed or
    detached one raises `ValueError`, and `pythonw` has no stdout at all.
    """
    stream = sys.stdout if stream is None else stream
    errors = getattr(stream, "errors", None)
    if errors == "strict":
        handler = "backslashreplace"
    elif errors == "surrogateescape":
        handler = _registered_surrogateescape_then_backslashreplace()
    else:
        return
    try:
        stream.reconfigure(errors=handler)
    except (AttributeError, ValueError, OSError):
        pass


#: `reconfigure` takes a handler by NAME, so it is registered under one, and
#: under one that names this repository: a bare `surrogate-backslash` could
#: replace a handler some other code registered, or be replaced by it.
SURROGATEESCAPE_THEN_BACKSLASHREPLACE = (
    "openreposhape.surrogateescape-then-backslashreplace")


def _registered_surrogateescape_then_backslashreplace() -> str:
    """The handler's name, registered by the first call and by no other."""
    try:
        codecs.lookup_error(SURROGATEESCAPE_THEN_BACKSLASHREPLACE)
    except LookupError:
        codecs.register_error(SURROGATEESCAPE_THEN_BACKSLASHREPLACE,
                              _surrogateescape_then_backslashreplace)
    return SURROGATEESCAPE_THEN_BACKSLASHREPLACE


def _surrogateescape_then_backslashreplace(error):
    """`surrogateescape` for a byte it escaped, `backslashreplace` for the rest.

    The codec hands over a run of characters it cannot encode. This answers
    the longest stretch at the start of it that is all escaped bytes, with
    those bytes, or all something else, in `codecs.backslashreplace_errors`'
    own spelling, so a stdout that was `strict` and one that was
    `surrogateescape` escape a character identically. It says where it
    stopped, and the codec asks again for whatever is left. Encoding only:
    nothing here decodes through a stdout's handler.
    """
    if not isinstance(error, UnicodeEncodeError):
        raise error
    text, start = error.object, error.start
    escaped = _is_escaped_byte(text[start])
    end = start + 1
    while end < error.end and _is_escaped_byte(text[end]) == escaped:
        end += 1
    if escaped:
        return bytes(ord(char) - 0xDC00 for char in text[start:end]), end
    return codecs.backslashreplace_errors(UnicodeEncodeError(
        error.encoding, text, start, end, error.reason))


def _is_escaped_byte(char: str) -> bool:
    """`char` is a byte `surrogateescape` read in as U+DC80..U+DCFF."""
    return 0xDC80 <= ord(char) <= 0xDCFF


# ---------------------------------------------------------------------------
# A project's own validators run as children (#254)
# ---------------------------------------------------------------------------
#
# `bump-leg.py` and `update-shape.py apply` run the PROJECT'S copies of
# `validate-pins.py` and `validate-manifest.py` after they rewrite the pin.
# Those are digest-pinned shape copies: they print the display name with a
# plain `print` and never call `escape_what_stdout_cannot_encode`, and a child
# takes its stdout CONFIGURATION from its environment (`PYTHONIOENCODING`, then
# the locale), not from the `reconfigure` the parent did. So under a stdout
# whose code page cannot hold the name -- `PYTHONIOENCODING=cp1252`, or
# Windows' own default for any stdout that is not the console -- the validator
# raised `UnicodeEncodeError` at `print(f"manifest ok: {name} ...")`, exited 1,
# and the tool refused and rolled back a bump that was fine, blaming a gate
# that had nothing wrong with it. Both tools build the child's environment
# here, once, and pass it as `env=`.


#: What a validator whose output a tool CAPTURES is told to write in. UTF-8
#: holds every name, so the child cannot raise on one; `backslashreplace`
#: makes a lone surrogate (a byte of a file name that was not UTF-8) text
#: rather than a raise, and is a handler a child KNOWS. The tool decodes the
#: pipe as UTF-8 to match (`bump-leg.py`'s `run_validator`), whatever its own
#: locale is, and shows the words through its own escaped stdout.
CAPTURED_CHILD_IOENCODING = "utf-8:backslashreplace"

#: The built-in handlers that never raise on a character an encoding cannot
#: hold. `strict`, `surrogateescape` (which holds only U+DC80..U+DCFF) and
#: `surrogatepass` (UTF codecs only) are not among them.
_HANDLERS_THAT_NEVER_RAISE = frozenset({
    "backslashreplace", "ignore", "namereplace", "replace",
    "xmlcharrefreplace"})


def captured_child_environment() -> dict[str, str]:
    """The environment for a Python child whose output this process CAPTURES.

    `PYTHONIOENCODING` is set to `CAPTURED_CHILD_IOENCODING` and whatever the
    caller had is REPLACED, not respected: an operator's value describes the
    stream their own words land in, and the pipe a tool reads a child through
    is not it. Respecting `cp1252:strict` here would put the failure back, one
    pipe away from the console it was meant for. The pair has to be chosen
    together: the tool that captures the output decodes it as UTF-8 and prints
    it through ITS stdout, which `escape_what_stdout_cannot_encode` has made
    safe, so each stdout in the chain is written by one encoding it was told.

    Matches `shape-doctor.py`'s `run_validator`, which sets `utf-8` for the
    same two validators and reads them back as UTF-8; the handler is added.
    """
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = CAPTURED_CHILD_IOENCODING
    return env


def inherited_child_environment(stream=None) -> dict[str, str]:
    """The environment for a Python child that INHERITS this process's stdout.

    The child writes straight into the same pipe or file this process writes,
    so it has to write in the encoding this stdout is read in: UTF-8 bytes on
    a cp1252 pipe would be a different mistake. `PYTHONIOENCODING` is
    therefore set to the stream's OWN encoding and its own handler, which is
    what `escape_what_stdout_cannot_encode` leaves it with: an operator's
    `replace` (or any handler that never raises) is kept, so a run that
    printed `??` still prints `??`, and every other handler -- `strict`, which
    the helper has already changed to `backslashreplace` in this process, and
    `surrogateescape`, which it changed to a handler registered HERE -- is
    named `backslashreplace`. The child cannot use a handler only this process
    registered: `PYTHONIOENCODING=<encoding>:<unknown handler>` still starts,
    and fails with `LookupError: unknown error handler name` at the first
    character it cannot encode. Built-in names only.

    One difference from the in-process handler, and it is small: a byte of a
    file name that was not UTF-8, read in as U+DC80..U+DCFF, is written by the
    child as the text `\\udcff` where this process writes the byte back. A
    validator prints one only for a path it lists.

    A stream with no usable encoding (`pythonw` has no stdout) leaves the
    environment as it is: there is nothing the child inherits.
    """
    env = dict(os.environ)
    stream = sys.stdout if stream is None else stream
    try:
        encoding = codecs.lookup(stream.encoding).name
    except (AttributeError, LookupError, TypeError):
        return env
    errors = getattr(stream, "errors", None)
    if errors not in _HANDLERS_THAT_NEVER_RAISE:
        errors = "backslashreplace"
    env["PYTHONIOENCODING"] = f"{encoding}:{errors}"
    return env


def write_paths_listing(path: Path, paths: list[str]) -> None:
    """The listing `git filter-repo --paths-from-file` reads: one path to a
    line, LF, BYTE-EXACT.

    A path is bytes, and `adopt-project.py` keeps a byte of one that is not
    UTF-8 as a lone surrogate (`surrogateescape`, as `Source.tree` decodes
    it), which `write_lf`'s strict UTF-8 cannot encode: the write raised
    `UnicodeEncodeError` inside `_extract_leg`, after both leg repositories
    existed (#199). Encoded with `surrogateescape`, each such surrogate is
    the byte it stands for again, and filter-repo reads the file as bytes,
    so the line is the path git records. A path that is UTF-8 is written
    exactly as `write_lf` wrote it: the same text, LF on every platform.
    """
    path.write_bytes(("\n".join(paths) + "\n").encode("utf-8",
                                                      "surrogateescape"))

# ---------------------------------------------------------------------------
# The `reference:` an election followed, and why one default cannot serve
# ---------------------------------------------------------------------------
#
# The doctrine was ratified on 2026-09-02 and lives at openxFactory
# `docs/project-repo-schema.md`. Before that day it existed ONLY as the staged
# fragment, so the standard's own sentence is that "a project elected before
# that date recorded the staged fragment's path, and that is a valid reference
# for it". A single default therefore cannot be right for both: writing the
# ratified path into a project dated 2026-08-30 makes the manifest claim its
# election followed a document that did not yet exist on the day a human
# elected the shape — and the `reference:` is precisely the claim about which
# document that human read.
#
# So the DATE chooses, `--reference` still overrides, and neither tool has to
# remember the rule. `DEFAULT_REFERENCE` keeps its name and its value because
# it is what other modules import and what the ratified path is called; only
# the CHOOSING is new.

DEFAULT_REFERENCE = "openxFactory docs/project-repo-schema.md"
STAGED_REFERENCE = (
    "openxFactory ideation/staging/project-repo-schema/project-repo-schema.md"
)
#: The day `add-project-repo-schema` ratified. An election ON it followed the
#: ratified document; one strictly BEFORE it followed the staged fragment.
RATIFICATION_DATE = _dt.date(2026, 9, 2)


def election_date(elected_on: str) -> _dt.date:
    """`elected_on` as a date, or a refusal that names the flag.

    A date this cannot read is not one it will guess at: the guess would pick
    the reference, and the reference is a claim about a human's act.
    """
    try:
        return _dt.date.fromisoformat(str(elected_on))
    except ValueError as exc:
        raise Refusal(
            "election-date-malformed",
            f"--elected-on {elected_on!r} is not a date; it takes YYYY-MM-DD "
            "(and a plan file's `elected_on:` carries the same form)",
            "Remediation: re-run with a zero-padded ISO date, e.g. "
            "--elected-on 2026-09-02 — not 2026-9-2 and not a word like "
            "'yesterday'. The `reference:` the manifest records is chosen BY "
            "that date, so it has to be readable before anything is written.",
        ) from exc


def default_reference(elected_on: str) -> str:
    """The document an election on `elected_on` followed, absent an explicit
    `--reference`: the staged fragment before ratification, the ratified
    document on that day or after."""
    if election_date(elected_on) < RATIFICATION_DATE:
        return STAGED_REFERENCE
    return DEFAULT_REFERENCE

#: One name, used in three places below: the source path, the target path and
#: the chmod list. Spelling it three times is how the chmod list starts naming
#: a file the copy list no longer writes.
VALIDATE_NAMING = "scripts/validate-repository-naming.py"
#: The same reasoning, for the two names `COPIED_FROM_SHAPE` and
#: `FAMILY_COPIED_FROM_SHAPE` both copy out of openRepoShape's own tree, always
#: to the identical path -- one spelling for the pair, in both lists.
REPO_SHAPE = "scripts/repo_shape.py"
NAMING_POLICY_YAML = "contracts/repository-naming.yaml"
#: And again for the name `COPIED_VERBATIM`, `EXECUTABLE`,
#: `FAMILY_COPIED_VERBATIM` and `FAMILY_EXECUTABLE` all carry -- the exact
#: copy-list/chmod-list, assembly-root/family-root spread `VALIDATE_NAMING`
#: is named for above. `setup-project.py`'s own `BOOTSTRAP` names the same
#: file for the same reason; this module keeps its own copy of the name
#: rather than importing one across a boundary neither module crosses
#: otherwise.
BOOTSTRAP = "scripts/bootstrap.py"

#: Copied out of openRepoShape's OWN tree, so the project carries the standard
#: it was cut from rather than a link to it.
COPIED_FROM_SHAPE = (
    (REPO_SHAPE, REPO_SHAPE),
    (VALIDATE_NAMING, VALIDATE_NAMING),
    (NAMING_POLICY_YAML, NAMING_POLICY_YAML),
)
#: Copied VERBATIM out of the assembly-root template (no substitution).
COPIED_VERBATIM = (
    "scripts/validate-pins.py",
    "scripts/validate-manifest.py",
    BOOTSTRAP,
    "Makefile",
    ".gitignore",
    # WHAT THIS PROJECT'S BYTES ARE, said by the project (2026-09-05, #51).
    # The pin digests these copies as they sit on disk, so a clone that
    # translated line endings on checkout would make every row false on
    # exactly one platform — Git for Windows installs `core.autocrlf=true` by
    # default. `setup-project.py` clones with `core.autocrlf=false` for the
    # run it controls; this file covers the next person to clone the finished
    # project, who never ran anything of ours. PINNED like the rest, because a
    # file that says what the bytes are is worth nothing if it can be edited
    # without the pin noticing.
    ".gitattributes",
    ".github/workflows/validate.yml",
    # The AGENT-FACING rules of the shape (2026-09-04). PINNED, and verbatim
    # for the same reason the validators are: the sentence "never edit a file
    # with a row in shape-pin.yaml" is worthless if the file saying it can be
    # edited. Verbatim also means it carries no `{{placeholders}}` — it names
    # "the paths `project.yaml` names" instead — because one byte of rendered
    # project detail would make every project's copy digest differently and
    # `update-shape.py` unable to say whether it had drifted.
    "AGENTS-shape.md",
)
#: Rendered from the template with `{{PLACEHOLDER}}` substitution. These are
#: NOT digest-pinned in the shape pin: they are this project's own content.
TEMPLATED = (
    "README.md",
    "project.yaml",
    "contracts/spec-pin.yaml",
    "contracts/code-pin.yaml",
    # The project's OWN assistant instructions: a one-line pointer at
    # `AGENTS-shape.md`, the three repositories, and then the project's own
    # text. Rendered rather than pinned on purpose — an upstream fix must
    # never overwrite what a project's agents are told about the project.
    "AGENTS.md",
    "CLAUDE.md",
    # shape-pin.yaml is rendered LAST, because its `files:` block digests the
    # copies above after they have been written.
)
#: Rendered only when the project DECLARES a neutral-product pin, and written
#: once per declared pin at `neutral_pin_path(product)`.
NEUTRAL_PIN_TEMPLATE = "contracts/neutral-product-pin.yaml"
EXECUTABLE = ("scripts/validate-pins.py", "scripts/validate-manifest.py",
              BOOTSTRAP, VALIDATE_NAMING)
#: The copy pin, rendered LAST by `_materialize` over the copies it digests.
#: Named once because `assembly_root_paths` lists it beside the lists above,
#: and a second spelling is how that list would stop matching what is written.
SHAPE_PIN = "contracts/shape-pin.yaml"


def neutral_pin_path(product: str) -> str:
    """Where a declared neutral-product pin is written: `contracts/<product
    lowercased>-pin.yaml`, `contracts/openglass-pin.yaml` for `openGlass`.

    SPELLED ONCE, for `SHAPE_PIN`'s reason (#197). `_materialize` writes the
    pin here, `assembly_root_paths` lists it for a call that declares one,
    and `scaffold-project.py` refuses a leg path over it from that list. The
    refusal first read a list with no pin in it, so `--pin openGlass@<sha>
    --spec-path contracts/openglass-pin.yaml` planned under `--dry-run`, then
    created all three repositories and died at `git submodule add`. The
    validators a project carries spell it again: they ship into the project
    and import nothing from here.
    """
    return f"contracts/{product.lower()}-pin.yaml"


# ---------------------------------------------------------------------------
# The FAMILY root's own lists (2026-09-04)
# ---------------------------------------------------------------------------
#
# A family is a HOLDER, not a project: no legs, no leg pins, no manifest
# validator, and no naming CLI — `validate-family.py` asks the naming policy
# the one question a family has. So it gets its own four lists rather than
# reusing the assembly root's with exceptions, because "the same list minus
# three entries" is a list that starts agreeing with neither.

FAMILY_TEMPLATED = (
    "README.md",
    "family.yaml",
    "AGENTS.md",
    "CLAUDE.md",
    # shape-pin.yaml is rendered LAST by the materializer, over the copies.
)
FAMILY_COPIED_VERBATIM = (
    "scripts/validate-family.py",
    BOOTSTRAP,
    # The workstation utility (2026-09-09, #76): it clones each member BESIDE
    # the holder, on its tracking branch, and warns about the parent folder
    # without moving anything. Copied and pinned like the other two, which is
    # what carries it to an existing holder through `update-shape.py check` ->
    # `upstream-added` -> `apply --add scripts/siblings.py`.
    "scripts/siblings.py",
    "Makefile",
    ".gitignore",
    # The holder carries the same copy pin, so it carries the same statement
    # about its bytes, and for the same reason (2026-09-05, #51).
    ".gitattributes",
    ".github/workflows/validate.yml",
    # The holder's own agent-facing rules, pinned like the assembly root's and
    # for the same reason. It is a SEPARATE document rather than the same one:
    # a holder has no legs, no leg pins and no lockstep workflow refs, so half
    # of the assembly root's file would be instructions about things that are
    # not here — and a file that is right about the wrong repository is read
    # once and then not at all.
    "AGENTS-shape.md",
)
#: The family validator reads the naming policy through `repo_shape`, so those
#: two travel with it. It does NOT copy `validate-repository-naming.py`: the
#: family has one name to classify and asks the library directly.
FAMILY_COPIED_FROM_SHAPE = (
    (REPO_SHAPE, REPO_SHAPE),
    (NAMING_POLICY_YAML, NAMING_POLICY_YAML),
)
FAMILY_EXECUTABLE = (
    "scripts/validate-family.py",
    BOOTSTRAP,
    "scripts/siblings.py",
)

#: A `{{KEY}}` placeholder: capitals, digits and underscores between double
#: braces. The digits are what make `{{SPEC_TREE_SHA256}}` one, which the
#: pattern `[A-Z_]+` did not see (#260). A workflow's own `${{ github.x }}`
#: and a Python f-string's `{{commit}}` hold a space or a lower-case letter,
#: so neither is one. Every key of every substitution table is spelled this
#: way, because `render` replaces only what this pattern finds.
PLACEHOLDER_RE = re.compile(r"\{\{[A-Z0-9_]+\}\}")
#: The same placeholder, or one standing alone between a YAML template's
#: double quotes, `"{{ELECTED_BY}}"`, which is matched FIRST: group 1 is the
#: quoted placeholder, and a bare one leaves it None.
YAML_PLACEHOLDER_RE = re.compile(
    '"(' + PLACEHOLDER_RE.pattern + ')"|' + PLACEHOLDER_RE.pattern)

#: THE ONE READING OF THE LINE A FAMILY HOLDER'S README ENDS WITH.
#: `templates/family-root/README.md` closes with ``Shape: `<repository>` @
#: `<40 hex>`.`` — the standard the holder was cut from — and until #148
#: nothing rewrote it after the scaffold, so it drifted silently from
#: `contracts/shape-pin.yaml`: InkRouter's holder still named a commit four
#: re-pins old. `update-shape.py apply` now moves that sha with the pin and
#: `shape-doctor.py` reports a difference as a `note`, and BOTH read the line
#: through this one compiled pattern. It lives here, beside the template
#: lists that render it, because a change to the template's wording and a
#: change to the readers of it have to be one edit;
#: `tests/test_family.py` renders the template and asserts this matches
#: exactly one of the rendered README's lines, so the two cannot drift apart
#: in silence. The assembly-root README carries no such line and is expected
#: to match nothing.
#:
#: A MATCH IS NOT BY ITSELF THE LINE: the form also appears where a README
#: SHOWS the reader what a holder's last line looks like, and only the one
#: the file ENDS with is this root's claim about its own pin.
#: `readme_trailing_shape_line` is where that is decided, once, for both
#: readers.
#:
#: THE REPOSITORY IS THE SHAPE A REPOSITORY NAME HAS — an owner and a name of
#: letters, digits, dots, hyphens and underscores with one slash between them
#: — and not "anything that is not a backtick". Two defects closed by saying
#: so, both found on PR #152. Under `re.MULTILINE` the `^` and `$` anchors are
#: per line but a negated class is not, so a backtick-quoted name running over
#: a line break matched as ONE line spanning two — enough for a malformed
#: example to count as a second `Shape:` line and leave a holder's real one
#: `ambiguous` and unmoved. And both readers PRINT the name they read back to
#: whoever ran them (`update-shape.py`'s `other-repository` line does it
#: twice), so a name carrying an ESC would have played terminal control
#: sequences into that operator's terminal — out of a README this operator
#: need not have written, since `shape-doctor.py` reads other repositories'.
#: A crafted name is now not a `Shape:` line at all, which is `absent`:
#: untouched, unprinted, and not a rewrite this tool was talked into.
#:
#: `\r?` before the end anchor: a README checked out on Windows with
#: `core.autocrlf=true` holds CRLF, and the rewriter works on BYTES so that
#: everything but the 40 hex characters survives untouched — a reader that
#: normalised the line endings instead would rewrite every line of the file
#: to move one sha.
README_SHAPE_LINE_RE = re.compile(
    r"^Shape: `(?P<repository>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)` @ "
    r"`(?P<commit>[0-9a-f]{40})`\.\r?$",
    re.MULTILINE)


def readme_shape_lines(text: str) -> list:
    """Every line of `text` in that exact rendered form, in the order found.

    A LIST, NOT THE FIRST MATCH, because "more than one" is one of the
    answers a caller has to be able to give. A README carrying two such lines
    is one no rewriter may touch — choosing between them would be the tool
    deciding which of a project's own sentences is the true one — and the
    caller can only say that if it is told how many there are.
    """
    return list(README_SHAPE_LINE_RE.finditer(text))


def readme_trailing_shape_line(text: str) -> "re.Match | None":
    """The one match a rewriter may move — the line the FILE ENDS WITH.

    THE PATTERN IS ANCHORED TO A LINE, NOT TO THE END OF THE FILE, so it also
    finds the form where a README is SHOWING the reader what a holder's last
    line looks like. That example is prose ABOUT the standard, and a rewriter
    that moved its sha would be editing an illustration into saying something
    the illustration does not mean — the documentation equivalent of the drift
    #148 is about, made by the fix (Copilot, PR #152). What separates the two
    is position and only position: the template renders this line last, and
    `tests/test_family.py` asserts that a real rendered holder ends with it.

    TRAILING MEANS NOTHING BUT WHITESPACE AFTER IT. A text file ends with a
    newline and an editor may leave a blank line under it; neither of those
    makes the last sentence of a README a different sentence. Anything else —
    a heading, a paragraph, the rest of a fenced block — does.

    `None` when the README ends with something else, INCLUDING when it carries
    such a line higher up: the caller's answer there is that the trailing line
    is absent, not that it found one to move.
    """
    matches = readme_shape_lines(text)
    if matches and not text[matches[-1].end():].strip():
        return matches[-1]
    return None


#: The one line an existing assistant-instruction file needs, and the exact
#: bytes of the pointer the templated `AGENTS.md` opens with.
SHAPE_POINTER_LINE = ("Read AGENTS-shape.md first — the rules of this "
                      "repository's shape.")
#: The shape files whose collision follow-up is ADD A LINE, not MERGE
#: (2026-09-04). `contracts/path-classification.yaml`'s
#: `root-assistant-instructions` keeps a source's own `AGENTS.md`/`CLAUDE.md`
#: at the root because "it addresses the whole project", which is the same
#: reason the shape must not replace one: that file is what this project's
#: agents ALREADY read, and telling a human to "merge" two agent instruction
#: files is how the project's own instructions get lost inside the shape's.
ASSISTANT_INSTRUCTIONS = ("AGENTS.md", "CLAUDE.md")


def collision_follow_up(intended: str, actual: str) -> str:
    """The follow-up for ONE collision, in one place.

    Both callers say it: `adopt-project.py plan` PREDICTS the collisions from
    the plan's surviving root paths, and `execute` reports the ones that
    actually happened. Two spellings of the same instruction is how the plan a
    human approves stops matching the commit message they read afterwards.
    """
    if intended in ASSISTANT_INSTRUCTIONS:
        return (
            f"add the line `{SHAPE_POINTER_LINE}` to the existing {intended} "
            f"rather than replacing it with {actual}: {intended} is what this "
            "project's agents ALREADY read, and "
            "`contracts/path-classification.yaml` keeps it at the root "
            "(`root-assistant-instructions`) because it addresses the whole "
            f"project. Then delete {actual}. Nothing was overwritten.")
    return (
        f"merge {actual} into {intended}: the source repository already has "
        "that name, so the shape's copy was written beside it and NOTHING was "
        "overwritten")


def copy_in_the_way(target: Path, actual: str) -> str | None:
    """What stands where the shape's copy `actual` (`shape/README.md`) is to
    be written under `target`, in words; None when the way is free.

    `place` ASKED ABOUT THE PATH THE COPY STANDS IN FOR AND NEVER ABOUT THE
    COPY'S OWN (#262). A source that keeps its own `shape/` in the root has a
    real `shape/README.md`, and the shape's README was written over it, on
    the line after `adopt-project.py` said that nothing was overwritten; a
    directory `shape/Makefile/` raised `IsADirectoryError` and a file named
    `shape` raised `FileExistsError`, each after both legs were pushed.

    The copy is in the way when anything is AT its path, a symlink that leads
    nowhere included (it is written through, and a file lands where nothing
    was meant), or when something on the way to it is not a directory, which
    a symlink to one is. `adopt-project.py check` finds what a plan keeps
    there before any leg exists (`plan-root-blocks-shape-copy`); this is the
    same question asked of the disk, for a caller that skipped `check`.
    """
    parts = actual.split("/")
    for end in range(1, len(parts) + 1):
        here = target.joinpath(*parts[:end])
        if not (here.is_symlink() or here.exists()):
            return None   # nothing here, so nothing deeper either
        if end == len(parts):
            return (f"`{actual}` is already there"
                    f"{', a directory' if here.is_dir() else ''}")
        if not here.is_dir():
            return f"`{'/'.join(parts[:end])}` is not a directory"
    return None


#: Appended to the assembly root's Makefile by `adopt-project.py` ONLY. A
#: scaffolded project's legs are empty, so nothing reads across them yet; an
#: ADOPTED project's code leg holds tooling that used to read `contracts/`
#: from beside it and now reads it from the other leg through the root.
ADOPT_MAKEFILE_BLOCK = """
# --- adopted project: reading ACROSS the legs -------------------------------
# The spec leg owns `contracts/`; the code leg holds the tooling that reads
# them. Mounted here, `spec/contracts` is one relative path from `code/`, so
# the root exports it once and the code leg takes it from the environment
# rather than each script guessing at `../`.
CONTRACTS_DIR ?= $(CURDIR)/spec/contracts
export CONTRACTS_DIR

.PHONY: contracts-dir
contracts-dir:
\t@echo $(CONTRACTS_DIR)
"""


class CommandFailed(Exception):
    def __init__(self, args, cwd, code, output):
        super().__init__(" ".join(args))
        self.args_list = args
        self.cwd = cwd
        self.code = code
        self.output = output.strip()

    def loudly(self, what: str) -> str:
        where = f"    (in {self.cwd})\n" if self.cwd else ""
        return (
            f"REFUSED {what}. THE EXACT COMMAND WAS:\n"
            f"    {' '.join(self.args_list)}\n{where}"
            f"    exit {self.code}\n"
            f"--- output ---\n{self.output}\n--- end output ---"
        )


RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. Two legitimate exits:

  (1) have an operator holding the bypass right seed the default branch once,
      then re-run this scaffold; or
  (2) push a seed BRANCH and open a pull request:
          git -C {work} push -u origin main:seed/scaffold
          gh pr create --repo {repo} --base main --head seed/scaffold \\
              --title 'Seed the {role} leg' --body 'Scaffolded shape.'

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run.
"""


#: The ONLY programs anything here will execute. Every call is a fixed verb
#: with values from the command line as ARGUMENTS — never a shell string, so
#: `shell=False` keeps the arguments out of a shell — and this list keeps the
#: PROGRAM out of the caller's hands as well. The tools take a repository
#: name, a path and a commit from whoever runs them, including from an AI
#: assistant reading a plan file; the pair of constraints is what stops a
#: crafted value from becoming a command.
ALLOWED_PROGRAMS = ("git", "gh")


def check_program(args: list[str]) -> None:
    """Refuse to execute anything but the two tools this standard drives."""
    program = Path(args[0]).name if args else ""
    if program not in ALLOWED_PROGRAMS:
        raise Refusal(
            "program-not-allowed",
            f"refusing to execute {program!r}: this module runs only "
            + " and ".join(ALLOWED_PROGRAMS),
            "Remediation: this is a defect in the tool that built the command "
            "line, not in your invocation.")
    for argument in args:
        if not isinstance(argument, str):
            raise Refusal(
                "argument-not-a-string",
                f"a command argument is {argument!r}, not a string",
                "Remediation: this is a defect in the tool that built the "
                "command line.")


def run(args: list[str], cwd: Path | None = None, capture: bool = True) -> str:
    check_program(args)
    # UTF-8, whatever the locale: git writes a path as UTF-8, and the locale's
    # codec (ASCII under a POSIX `C` locale, the ANSI code page on Windows)
    # raises `UnicodeDecodeError` out of `subprocess.run` on one it cannot
    # read -- before `CommandFailed` exists, so the person gets a traceback
    # where `REFUSED <step>` and the ruleset hint belong (#217).
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True,
                          encoding="utf-8", errors="replace", check=False)
    if proc.returncode != 0:
        raise CommandFailed(args, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


#: `-F -` reads the message from STDIN. Every argument is then a literal, and
#: the one value a caller controls — the message, which carries a project's
#: display name and, in an adoption, every moved path out of a plan file —
#: never reaches the command line at all. `-m <message>` was safe too (there
#: is no shell, and the value sits after `-m`), but "safe because of where it
#: sits in argv" is an argument somebody has to re-derive every time they read
#: it, and not putting it there is one fewer thing to be right about.
COMMIT_COMMAND = ["git", "commit", "-q", "-F", "-"]


def env_commit(work: Path, message: str) -> None:
    """Commit with an identity that always resolves, reading the message
    from stdin.

    A scaffold that fails on a machine with no `user.email` configured fails
    for a reason that has nothing to do with the project being scaffolded, so
    a fallback identity is supplied rather than assumed.

    THE MESSAGE GOES TO GIT AS UTF-8, whatever the locale (#196). Text-mode
    stdin encodes with the locale's codec unless Python runs in UTF-8 mode
    -- cp1252 on a Windows without `PYTHONUTF8=1`, ASCII under a POSIX `C`
    locale with that mode off -- and git keeps the bytes it is given. An
    adoption's split message already carried an em dash, which reached git
    there as a cp1252 byte, and it names each entry path as the source spells
    it: `Übersicht.md` would land as another byte that is not UTF-8, and
    `文書.md` would raise `UnicodeEncodeError` after both legs are pushed.
    Every caller's message goes the same way: `scaffold-project.py`'s
    assembly commit, `scripts/family.py`'s holder commit, and each first
    commit `git_init_commit` makes (a scaffolded leg, a seeded one).

    `errors="replace"` works BOTH WAYS. Decoding, git's own output cannot
    raise. Encoding, a character UTF-8 cannot carry is written as `?`: the
    one such character a message can hold is a lone surrogate, the byte of a
    name that is not UTF-8 as `Source.tree` keeps it. `adopt-project.py`
    refuses one in a path it extracts (`entry_path_problem`), but a `root`
    or `drop` entry holding one is listed in the split message, so there the
    message names it with a `?` in place of that byte, a path that does not
    exist, rather than raising after both legs are pushed.
    """
    env = dict(os.environ)
    for key, fallback in (("GIT_AUTHOR_NAME", "openRepoShape scaffold"),
                          ("GIT_COMMITTER_NAME", "openRepoShape scaffold"),
                          ("GIT_AUTHOR_EMAIL", "scaffold@openreposhape.invalid"),
                          ("GIT_COMMITTER_EMAIL", "scaffold@openreposhape.invalid")):
        env.setdefault(key, fallback)
        if not env.get(key):
            env[key] = fallback
    check_program(COMMIT_COMMAND)
    proc = subprocess.run(COMMIT_COMMAND, cwd=str(work), input=message,
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=False, env=env)
    if proc.returncode != 0:
        raise CommandFailed(COMMIT_COMMAND, work, proc.returncode,
                            proc.stderr + proc.stdout)


def force_stage(work: Path, paths=()) -> None:
    """Stage exactly `paths`, FORCED past any ignore rule, and nothing else.

    THE FORCED ADD THE SCAFFOLD, `family.py init`, `adopt-project.py`'S
    SEEDED LEG AND `update-shape.py` SHARE; the seeded leg reaches it
    through `git_init_commit`, as `stage_written` says. A file the shape
    wrote and pinned has to reach the commit whatever the operator's own
    excludes say — a global `core.excludesFile`, `.git/info/exclude`, a
    `.gitignore` the project keeps — because a pin row naming a file the
    commit lacks is a red `validate-pins.py` on the next clone (#175). `-f`
    over the NAMED paths and never over `.`, for the reason `stage_written`
    gives. (`adopt-project.py` still spells two forced adds of its own,
    which predate this helper and do not call it.)

    EACH NAME IS TAKEN LITERALLY (`--literal-pathspecs`, #202). A pathspec
    is a glob to git, so a copy-list entry named `docs/guide[1].md` also
    matched an operator's `docs/guide1.md`, and `-f` forced that ignored
    file in beside it and into the commit — the "nothing else" this
    promises, broken by the one flag that exists to stage the named paths.
    No copy-list entry holds a glob character today; the day one does, it
    stages itself and no neighbour.

    TWO CALLERS, AND ONLY ONE OF THEM SWEEPS FIRST. `stage_written` runs
    `git add -A` before it, because it stages a tree this tool has just
    made. `update-shape.py apply --add` calls this ALONE (#202): it writes
    into a checkout somebody may be working in, where `-A` would stage their
    work beside the shape's, and its plain `git add --` died on an ignored
    addition after the copies, the pin and the branch were already written.
    Empty, this runs nothing.
    """
    paths = list(paths)
    if paths:
        run(["git", "--literal-pathspecs", "add", "-f", "--", *paths],
            cwd=work)


def stage_written(work: Path, written=()) -> None:
    """Stage the tree, then FORCE every path in `written` past any ignore rule.

    `git add -A -- .` HONOURS THE OPERATOR'S IGNORE RULES — a global
    `core.excludesFile`, `.git/info/exclude` — and a scaffold run on a machine
    whose excludes say `.*`, `contracts/` or `scripts/` exited 0 with a first
    commit that lacked `.gitattributes`, `.github/`, `.gitignore`,
    `contracts/*` and `scripts/*`, so the new project's first `make bootstrap`
    failed (#175, the scaffold side of #167). The files this tool wrote are
    therefore staged BY NAME with `-f`, after `-A` has staged everything else.

    ONLY THOSE PATHS, NEVER `-f .`: a file somebody else put in the tree and
    an ignore rule hides stays out, because forcing the whole tree would
    stage exactly what an ignore rule is written to keep out of a commit.
    `written` is what `place()` and `copy_tree` return — each path where it
    landed, in `root_key`'s POSIX spelling, which `git` takes as a pathspec
    on Windows too. Empty, this is `git add -A -- .` and nothing else.

    ONE HELPER, THREE CALLERS: `git_init_commit` (the scaffold's two legs and
    `adopt-project.py`'s seeded leg), the scaffold's assembly root and
    `family.py init`'s holder. The forced half is `force_stage`, which
    `update-shape.py apply --add` calls on its own (#202).
    """
    run(["git", "add", "-A", "--", "."], cwd=work)
    force_stage(work, written)


def git_init_commit(work: Path, message: str, branch: str,
                    written=()) -> str:
    """`git init`, stage, commit; returns the new HEAD.

    `written` is what `stage_written` forces past an ignore rule: the list
    `copy_tree` returned. A caller that passes none stages exactly what `git
    add -A` stages, and no more.
    """
    run(["git", "init", "-q", "-b", branch, str(work)])
    stage_written(work, written)
    env_commit(work, message)
    return run(["git", "rev-parse", "HEAD"], cwd=work)


# ---------------------------------------------------------------------------
# Is this the same repository? — IT MOVED (2026-09-12, #155)
# ---------------------------------------------------------------------------
#
# `same_repository`, `remote_key`, `join_remote`, `resolved_remote`,
# `redacted` and the regexes under them were written HERE on 2026-09-12 as a
# deliberate stopgap (#146, #147): a second copy of the rule
# `templates/family-root/scripts/siblings.py` refuses a working clone by,
# put in the one module `shape-doctor.py` could import without reading
# `templates/` and without moving a digest pin, and held to the first copy by
# a parity test. They are ONE definition in `scripts/repo_shape.py` now, which
# both tools import, and the parity test is an identity assertion.
#
# NOTHING IN THIS FILE EVER CALLED THEM — it held them for the doctor — so
# this is a pointer and no code. It is here because the next reader of #146 or
# #147 will come looking for the block those issues name.

# ---------------------------------------------------------------------------
# Commit trailers (2026-09-11, #111)
# ---------------------------------------------------------------------------
#
# WHAT WAS WRONG. `update-shape.py apply --branch` and `scripts/family.py
# bump` compose and write their own commits, and neither had any way to put a
# line on one. The lane-collision protocol wants `Lane: <name>` on every
# artifact a lane produces — the COMMIT included — and this estate's own
# convention adds `Co-Authored-By:`; four InkRouter re-pins landed on
# 2026-09-11 carrying neither, because both tools were run exactly as their
# own `NEXT` lines printed them and nothing in either wrote a trailer (#111).
# So both take a repeatable `--trailer`, and what a trailer IS, whether this
# host's git can be asked for one, and which environment variable names the
# lane are ONE implementation here rather than two that agree until they do
# not.
#
# AND NOT IN `scripts/repo_shape.py`, which is where this standard's other
# shared helpers sit. That file is a SHAPE COPY: the materializer below
# writes it into every assembly root and every family holder and
# `contracts/shape-pin.yaml` digests it — so one function added there would
# put an `upstream-changed scripts/repo_shape.py` row in front of every
# project in the estate on its next `update-shape.py check`, for a helper no
# project's own copy would ever call. `shape-doctor.py` makes exactly that
# argument about its own quoter. This module is in no copy list and is
# already imported by both tools that write these commits.

#: `<token>: <value>`, which is git's own trailer grammar narrowed to what a
#: tool can be handed on a command line: a token of letters, digits and
#: hyphens (`Co-Authored-By`), a colon, ONE space, and a value that is not
#: empty, is ONE line, carries no control character, and neither starts nor
#: ends in whitespace. Narrow BECAUSE THE VALUE ENDS UP IN A COMMIT MESSAGE
#: somebody else reads as a trailer: `git interpret-trailers` recognises a
#: block by exactly this shape, so a "trailer" missing the space after the
#: colon is a line that reads like one and is not.
#:
#: MATCHED WITH `.fullmatch`, AND THE CLASSES EXCLUDE THE CONTROL
#: CHARACTERS AN ASCII PATTERN CAN NAME, because "is ONE line" was neither
#: (Copilot, PR #112). The rest of that contract is `one_printable_line`
#: below, which is where the characters no character class should be asked
#: to enumerate are refused.
#: `re.match` with a pattern ending in `$` stops just before a FINAL
#: NEWLINE, so `--trailer "Lane: x\n"` was accepted whole and the newline
#: went into the commit message and into argv -- a second line inside a
#: value, which is a trailer nobody passed. And `[^\n]` in the middle is not
#: "one line": it admitted `\r`, `\v` and `\f` as well, each of which some
#: reader renders as a line break of its own. `shape-doctor.py`'s
#: `quote_arg` learnt the `.fullmatch` half of this on PR #102, against
#: `"Atlas\n"`; this is the same defect one file along.
TRAILER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]*: [^\s\x00-\x1f\x7f]"
                        r"(?:[^\x00-\x1f\x7f]*[^\s\x00-\x1f\x7f])?$")


def trailer_line(text: str) -> str:
    """One `--trailer` value, validated where argparse can refuse it.

    ARGPARSE'S OWN ERROR PATH RATHER THAN A `Refusal`, and deliberately: a
    malformed trailer is a malformed COMMAND LINE, which is the one class of
    mistake argparse already reports with the usage line beside it. Both
    exits are 2, so a caller scripting on the exit code sees no difference;
    what it buys is that `--trailer 'Lane xfactory-1'` is refused before the
    tool has read a repository, copied a byte or checked out a branch.
    """
    value = str(text)
    if not is_trailer(value):
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a `<Key>: <value>` trailer. It needs a token "
            "of letters, digits and hyphens, a colon, ONE space, and a "
            "non-empty value that is one line of text, carries no control, "
            "invisible or line-separator character, and does not end in "
            'whitespace — e.g. "Lane: xfactory-1" or '
            '"Co-Authored-By: Someone <someone@example.invalid>"')
    return value


#: The Unicode categories no line of a commit message may carry: `Cc` (every
#: control character, the C1 block `\x80`-`\x9f` as much as C0), `Cf` (the
#: invisible formatting ones — a zero-width joiner, a byte-order mark, a soft
#: hyphen), `Zl`/`Zp`, which are U+2028 LINE SEPARATOR and U+2029 PARAGRAPH
#: SEPARATOR themselves, and `Cs` — a LONE SURROGATE, which is what a byte
#: the locale could not decode becomes in `sys.argv`, and is not text at
#: all: git is handed that undecodable byte straight back, or, on the
#: pre-2.32 path that appends trailers to the MESSAGE, `subprocess` raises
#: `UnicodeEncodeError` on a value this tool had already accepted. A SPACE
#: is `Zs` and is not in this list.
UNPRINTABLE_CATEGORIES = ("Cc", "Cf", "Cs", "Zl", "Zp")


def one_printable_line(value: str) -> bool:
    r"""Is `value` ONE line, with nothing invisible or unwritable in it?

    `TRAILER_RE` CANNOT ANSWER THIS AND SHOULD NOT TRY (Copilot, PR #112).
    `[^\x00-\x1f\x7f]` reads as "no control character" and is not one: the
    C1 block sits above it, and so do U+2028, U+2029 and U+0085 NEXT LINE —
    every one of which Python's own `str.splitlines()` treats as a line
    boundary, so a value this called "one line" arrived as two in anything
    that read the message back that way. A character class large enough to
    name them all would be a second, worse copy of the Unicode tables.

    TWO CHECKS, EACH SAYING THE PROPERTY IN ITS OWN WORDS. `splitlines()` IS
    this interpreter's definition of a line boundary, so comparing its
    result against `[value]` asks the question directly rather than
    approximating it — and it is the check that moves when a future Python
    adds a boundary. `unicodedata.category` then catches what is invisible
    WITHOUT being a break: a zero-width joiner between two words makes two
    trailers that look identical to a reader and are not, which is exactly
    the confusion a trailer exists to avoid — and, in `Cs`, what is not text
    at all, because a byte the locale could not decode reaches `sys.argv` as
    a lone surrogate and no encoder will take it back.
    """
    if value.splitlines() != [value]:
        return False
    return not any(unicodedata.category(char) in UNPRINTABLE_CATEGORIES
                   for char in value)


def is_trailer(value: str) -> bool:
    """The WHOLE rule: the shape `TRAILER_RE` describes, and one printable
    line.

    ONE PREDICATE, TWO CALLERS, by construction rather than by agreement:
    `trailer_line` refuses what it rejects and `lane_trailer` offers nothing
    it rejects, so a lane line a printed next command carries is always a
    trailer that tool's own `--trailer` would accept. Two checks that merely
    agreed today would be one release away from a printed command that
    refuses itself.
    """
    return bool(TRAILER_RE.fullmatch(value)) and one_printable_line(value)


#: The nine bidirectional embedding, override and isolate controls, by code
#: point: U+202A..U+202E (LRE, RLE, PDF, LRO, RLO) and U+2066..U+2069 (LRI,
#: RLI, FSI, PDI). Each is `Cf`, and each sets the direction of the text
#: after it, so a line that holds one is shown in another order than it is
#: written. The marks U+200E, U+200F and U+061C are not among them: a mark
#: is one character of one direction, and sets no span's.
BIDI_CONTROLS = frozenset((*range(0x202A, 0x202F), *range(0x2066, 0x206A)))


def unwritable_reason(value: str) -> str | None:
    r"""Why `value` is not one line of text a file can hold, in words; None
    when it is (#255).

    `adopt-project.py` writes a value a person gave it -- `--elected-by`,
    `--reference`, the source's own path as a local clone URL -- into the
    assembly root's `project.yaml` and `README.md` through `write_lf`, which
    is strict UTF-8. Since #247 the plan keeps a lone surrogate (a byte that
    is not UTF-8, as `sys.argv` and `os.fsdecode` keep it) as `\udce9`, and
    the reader gives it back, so `plan` and `check` passed such a value and
    `write_lf` raised `UnicodeEncodeError` after both legs were pushed. This
    is the question asked of every such value before anything exists.

    `one_printable_line` LESS `Cf` OTHER THAN THE NINE `BIDI_CONTROLS`, AND
    THE EMPTY VALUE, because both are text a file holds and both were
    adopted before #247 and since. Such a `Cf` character is invisible, not
    unwritable: UTF-8 encodes it, the reader reads it back, and a name may
    need one -- a Persian name joins its parts with U+200C ZERO WIDTH
    NON-JOINER, which `one_printable_line` refuses. An empty `elected_by` is
    what `plan` records when `git config user.name` names nobody, and the
    manifest holds it as `""`. What is left is refused: a lone surrogate,
    which UTF-8 cannot encode; a line break, which ends the line the
    manifest's reader reads the value from (CR, U+0085 and U+2028 among
    them, as `str.splitlines` ends lines); a bidi embedding, override or
    isolate control, which a file holds but which shows the rest of the line
    it is written into -- the README's `Elected by` line, its date and
    reference among it -- in another order than it is written, as
    `double_quoted` in `scripts/repo_shape.py` spells one in the plan for
    the same reason; and any other control character, NUL among them, which
    YAML does not allow raw (TAB aside, and no name, date or reference holds
    one either).
    """
    if value.splitlines() not in ([], [value]):
        return "it holds a line break, and it is written as one line"
    for char in value:
        category = unicodedata.category(char)
        if category == "Cs":
            return ("it holds a byte that is not UTF-8"
                    if "\udc80" <= char <= "\udcff" else
                    "it holds a lone surrogate, which is no character")
        if ord(char) in BIDI_CONTROLS:
            return ("it holds a bidirectional control (an embedding, "
                    "override or isolate), which shows the rest of the line "
                    "in another order than it is written")
        if category in UNPRINTABLE_CATEGORIES and category != "Cf":
            return "it holds a control character"
    return None


#: The git that learned `commit --trailer` (2.32, 2021-06-06). An older one
#: still has `git interpret-trailers`, but not the commit option — so on that
#: host the trailer is appended to the message TEXT instead, which produces
#: the same commit. See `commit_trailers`.
TRAILER_OPTION_SINCE = (2, 32)

#: `git version 2.43.0` on Linux, `git version 2.45.1.windows.1`, `git
#: version 2.39.3 (Apple Git-146)`. TWO numbers, because two answer the
#: question and the third field is spelled differently on all three
#: platforms; anchored, so a number from anywhere else in the line cannot be
#: read as a version.
GIT_VERSION_RE = re.compile(r"^git version (\d+)\.(\d+)")

#: Probed once per process; see `git_takes_trailer_option`.
_trailer_option: bool | None = None


def git_takes_trailer_option(version: str | None = None) -> bool:
    """Does THIS host's `git commit` take `--trailer`?

    PROBED ONCE AND CACHED. Both callers write ONE commit per run, so the
    cost is one `git --version` either way; what the cache buys is that a
    tool cannot answer the question twice and differently inside one run.

    `version` IS THE PARSE, EXPOSED. Passed a string it parses that and
    caches nothing, so both branches are assertable on any host — the same
    thing `shape-doctor.py`'s `platform=` argument does for its quoter, and
    for the same reason: a branch that only ever runs on one machine is a
    branch nothing checks.

    CONSERVATIVE ON PURPOSE: a version line this cannot parse, a `git` that
    is not on PATH, a probe that fails for any reason at all — all read as
    "no", and "no" is the path that works on every git there is.
    """
    global _trailer_option
    if version is not None:
        found = GIT_VERSION_RE.match(version.strip())
        return bool(found) and (int(found.group(1)),
                                int(found.group(2))) >= TRAILER_OPTION_SINCE
    if _trailer_option is None:
        try:
            _trailer_option = git_takes_trailer_option(
                run(["git", "--version"]))
        except (CommandFailed, Refusal, OSError):
            _trailer_option = False
    return _trailer_option


def commit_trailers(message: str, trailers=()) -> tuple[str, list[str]]:
    """`(message, extra git-commit arguments)` that put `trailers` at the END
    of the commit message, in the order given, on whichever git this is.

    TWO PATHS, ONE RESULT. With `--trailer` available, git appends each line
    itself through `interpret-trailers`, which is the implementation that
    knows where a trailer block goes. Without it, the lines are appended to
    the message text after one blank line — and the commit that comes out is
    byte-identical to the one the option produces, because that is all the
    option had left to do for a message whose last paragraph is prose.

    THE MESSAGE STILL ARRIVES ON STDIN either way (`-F -`; see
    `COMMIT_COMMAND`), and the trailers are literal arguments after it. Both
    callers already commit with EXPLICIT PATHSPECS, so the returned arguments
    go BEFORE the `--` that starts them.

    NO TRAILERS IS NO CHANGE AT ALL: the message is handed back as it came
    and the argument list is empty, which is what keeps every commit these
    tools have ever written byte-identical when nobody passes the flag.
    """
    lines = [str(line) for line in (trailers or ())]
    if not lines:
        return message, []
    if git_takes_trailer_option():
        return message, [part for line in lines
                         for part in ("--trailer", line)]
    body = message if message.endswith("\n") else message + "\n"
    return body + "\n" + "\n".join(lines) + "\n", []


#: The environment variable that names the LANE a run belongs to — the one
#: `lanes-edit.sh` already reads. Read in ONE place so a printed next command
#: and the commit it asks for cannot disagree about which lane is running.
LANE_ENV = "LANES_LANE"

#: What a lane name may be AND STILL SURVIVE BEING PASTED. A next command is
#: a line somebody copies into a shell, and the trailer inside it is quoted
#: by whoever prints it — so a name carrying a quote character would break
#: the very quoting it sits inside, in front of whoever pasted it. Rather
#: than guess which printer is asking, a name outside this alphabet gets NO
#: trailer offered on the printed line; `--trailer` typed by hand still takes
#: anything `TRAILER_RE` accepts. Today's lane names (`openreposhape-2
#: (openRepoShape-2)`) are inside it. It is a POSITIVE alphabet of printable
#: ASCII, so it already excludes every character `one_printable_line`
#: refuses — no newline, tab or carriage return, no C1 control, no U+2028,
#: U+2029 or U+0085, nothing invisible — which is the point of checking the
#: RAW value below, and why no second guard is bolted on here.
LANE_NAME_RE = re.compile(r"[A-Za-z0-9 ()._:/@+-]+")


def lane_trailer(env: dict | None = None) -> str | None:
    """`Lane: <name>` when the environment names a lane, else `None`.

    UNSET OR ALL WHITESPACE IS `None`, and a caller prints nothing for it —
    which is what makes every line this standard printed yesterday
    byte-identical today for everybody who is not in a lane.

    THE VALUE IS CHECKED RAW, AND STRIPPING ONLY RECOGNISES "no lane"
    (Copilot, PR #112). Checking a `.strip()`ed name meant
    `LANES_LANE="xfactory-1\n"` was offered as `Lane: xfactory-1` — a name
    the contract says is not offered, trimmed into one that is, silently. So
    the alphabet above is asked about the bytes the environment actually
    carries, and a value with whitespace around it is NOT a lane name:
    `TRAILER_RE` refuses a value that starts or ends in whitespace, and a
    printed line that offered a trailer this tool's own `--trailer` would
    then refuse is worse than a line that offers none. The ONE thing
    stripping decides is whether an all-whitespace variable means "no lane",
    which it does — that is `LANES_LANE=` spelled with a space in it.
    """
    raw = str((os.environ if env is None else env).get(LANE_ENV) or "")
    if not raw.strip() or not LANE_NAME_RE.fullmatch(raw):
        return None
    line = f"Lane: {raw}"
    return line if is_trailer(line) else None


def lane_trailer_argument(quote=None, env: dict | None = None) -> str:
    """The ` --trailer <Lane: ...>` a printed next command carries, or `""`.

    `quote` IS THE CALLER'S OWN SPELLING FUNCTION, passed in rather than
    chosen here. `shape-doctor.py` hands over its platform-aware `quote_arg`,
    because every other value on those rows is spelled by that one function
    and a line half-quoted by two rules is a line no shell reads the way its
    writer meant. With none, the trailer is spelled inside double quotes —
    which is how `AGENTS.md`, `docs/cli.md` and the issue all write it, and
    is what `update-shape.py`'s own NEXT line, which quotes nothing, can
    carry without pretending to a quoting rule it does not have.

    ONE ARGUMENT, NOT TWO. `Co-Authored-By:` is the caller's to pass: it
    names a person or a model, which no environment variable knows, and a
    tool that invented one would be putting a name nobody chose on somebody
    else's commit.
    """
    line = lane_trailer(env)
    if not line:
        return ""
    spelled = quote(line) if quote else '"' + line + '"'
    return f" --trailer {spelled}"


def render(text: str, values: dict[str, str], source: str) -> str:
    """`text` with every `{{KEY}}` replaced by its value, or a refusal.

    A VALUE BETWEEN A YAML TEMPLATE'S DOUBLE QUOTES, `"{{ELECTED_BY}}"`, is
    spelled by `double_quoted`, the writer `repo_shape`'s reader takes back
    unchanged. Pasted raw, `--elected-by 'Robert "Bob" Smith'` wrote
    `"Robert "Bob" Smith"`, which is not YAML: the reader read it by
    accident until it learned where a quoted scalar ends (#250), and then
    refused the manifest of three repositories already created. A name ending
    in a backslash closed no quote, and `C:\\new` or `x" # y` were misread.
    The spelling is the value itself for any text without a quote, a
    backslash or a character `str.isprintable` refuses -- a commit, a digest,
    an ordinary name -- so no other template changes by a byte.

    ONE PASS, SO A VALUE IS NEVER READ AGAIN (#260). The keys used to be
    replaced one after another, each over the whole text, so the value an
    earlier key put in was scanned by every later key. `--elected-by
    '{{SPEC_PATH}}'` was recorded as `elected_by: "spec"` under `adoption
    verified`. `{{PROJECT}}`, a key that came earlier, or `{{NOPE}}`, which
    no key names, was left in the output and refused as a defect in the
    tool, after the legs were pushed. Now the template is read once, left to
    right, and each placeholder is replaced by its value as it is met. The
    text a value brings in is never searched, so it is written as typed.

    THE REFUSAL ASKS THE TEMPLATE, NOT THE OUTPUT. A placeholder the TEMPLATE
    holds and the table has no value for is the defect the remediation
    names, and it is refused before anything is written. The output is not
    searched: it now holds the person's own text, which may hold `{{` and
    is no defect of anybody's.
    """
    missing = sorted({token for token in PLACEHOLDER_RE.findall(text)
                      if token[2:-2] not in values})
    if missing:
        raise Refusal("template-unsubstituted",
                      f"{source}: no value for {missing}",
                      "Remediation: this is a defect in the substitution table "
                      "of the tool you ran, not in your invocation.")

    def value_of(placeholder: str) -> str:
        return str(values[placeholder[2:-2]])

    if not source.endswith((".yaml", ".yml")):
        return PLACEHOLDER_RE.sub(lambda match: value_of(match[0]), text)
    return YAML_PLACEHOLDER_RE.sub(
        lambda match: (double_quoted(value_of(match[1])) if match[1]
                       else value_of(match[0])), text)


def _local_strays(src: Path) -> frozenset[str]:
    """The files under `src` that THIS CHECKOUT holds and does not track.

    Each is named relative to `src` in POSIX spelling, and each is untracked
    AND ignored here: `.vscode/settings.json` an editor wrote into
    `templates/spec-root/`, a `__pycache__/x.pyc`. They are an operator's
    local artifacts, not template inputs, and `copy_tree` skips them (#175,
    Codex review of PR #185).

    WHY IT IS NEEDED NOW. Until `git_init_commit` began forcing what
    `copy_tree` wrote past an ignore rule (#175), a stray was harmless by
    accident: the template's own copied `.gitignore` made `git add -A` skip
    it. Forcing every path `copy_tree` returns made the walk's width
    matter. An unrestricted `rglob` copied the stray, put it in `written`,
    and `git add -f` committed it into the new leg and pushed it; a binary
    one, a `.pyc`, crashed the UTF-8 read before it got that far.

    THE DISCRIMINATOR IS THIS CHECKOUT'S OWN VIEW OF THE FILE. `git
    ls-files --others --ignored --exclude-standard` applies the tool's
    `.gitignore`, the template's nested one, `.git/info/exclude` and the
    operator's global excludes AS SEEN FROM THE TOOL'S CHECKOUT, and a file
    that checkout refuses to track is not an input of the template. A
    TRACKED file is never listed under `--others`, so the dot-file a global
    `.*` would hide (the template's `.gitignore`, #175's own case) is still
    copied and still forced; an untracked file nothing ignores, such as a
    template file a developer has not committed yet, is still copied.

    ONLY WHEN THIS CHECKOUT IS THE SHAPE'S. The rules are applied only when
    `src`'s git top level IS the shape root (`templates/<role>/` is two
    levels under it). Outside a work tree at all (a tarball install) git
    answers nothing and everything is copied, as before. Vendored inside
    some other repository, the top level is that repository's, whose ignore
    rules are not this tool's to apply, and everything is copied.

    NOT CHOSEN. `git add -f .`, forcing the tree: it stages exactly what an
    ignore rule is there to keep out, which `stage_written` already refuses.
    Filtering by the template's own `.gitignore`: that file is precisely
    what #175 forces past an operator's `.*`, so a copy filtered by it would
    drop the dot-files the shape ships. Building the list from `git
    ls-files` alone: it would leave out a template file that is not yet
    committed, and a tarball install has no index to ask.

    `git` failing to say where the top level is returns no strays, and so
    never raises; one that has found the top level and then cannot list the
    others raises `CommandFailed` rather than guess, because a guess is
    either a stray committed or a template file dropped.
    """
    toplevel = ["git", "-C", str(src), "rev-parse", "--show-toplevel"]
    check_program(toplevel)
    try:
        asked = subprocess.run(toplevel, capture_output=True, check=False)
        if asked.returncode != 0 or not os.path.samefile(
                os.fsdecode(asked.stdout.rstrip(b"\r\n")), src.parent.parent):
            return frozenset()
    except OSError:
        return frozenset()
    others = ["git", "-C", str(src), "ls-files", "-z", "--others",
              "--ignored", "--exclude-standard", "--", "."]
    check_program(others)
    listed = subprocess.run(others, capture_output=True, check=False)
    if listed.returncode != 0:
        raise CommandFailed(others, src, listed.returncode,
                            listed.stderr.decode("utf-8", "replace"))
    return frozenset(os.fsdecode(name) for name in listed.stdout.split(b"\x00")
                     if name)


def template_files(src: Path) -> list[str]:
    """Every file `copy_tree` copies out of the template tree `src`, in its
    order, relative to `src` in POSIX spelling: what a leg seeded from `src`
    holds.

    ONE LISTING, read by `copy_tree` and by `adopt-project.py check`, which
    follows a symlink the plan keeps into a seeded leg's mount and must find
    there what `execute` will have written (#183).
    """
    strays = _local_strays(src)
    return [rel for rel in (path.relative_to(src).as_posix()
                            for path in sorted(src.rglob("*"))
                            if not path.is_dir())
            if rel not in strays]


def copy_tree(src: Path, dst: Path, values: dict[str, str]) -> list[str]:
    """Copy a template tree, substituting placeholders in every text file.

    Returns every path it wrote, relative to `dst` and spelled by `root_key`,
    which is the list `git_init_commit` forces past an ignore rule (#175).

    A file this checkout holds untracked AND ignored (`_local_strays`) is
    neither copied nor returned, so an operator's `.vscode/settings.json` in
    `templates/spec-root/` is never forced into a new leg.
    """
    written: list[str] = []
    for rel in template_files(src):
        path, target = src / rel, dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        write_lf(target, render(path.read_text(encoding="utf-8"), values,
                                str(path)))
        written.append(root_key(target, dst))
    return written


def naming_block(policy: NamingPolicy, name: str, role: str,
                 pins, indent: str = "    ", chain=()) -> str:
    """The `naming:` block `project.yaml` records for one leg.

    It records the classification AND what was not chosen. A name in
    `<Domainx><Product>` form is a CLAIM of descent that needs a REFERENT
    (2026-09-02): with no declared pin on `open<Product>` the declared role
    wins, and the descendant form survives in `also_matches` so the next reader
    sees the overlap that was resolved rather than wondering whether anyone
    noticed it. WITH the pin the answer is `domain-descendant` in the declared
    `assembly` role, because a descendant may carry legs.

    An `open<Product>` root records the same shape for the same reason
    (2026-09-05): `form: neutral-product`, `role: assembly`,
    `also_matches: [project-leg/assembly]`. The form won and the role was
    ADDED to it, because a neutral product may elect the shape — and electing
    confers nothing, so the record is a layout, not a claim about neutrality.

    `chain` is the pin chain the project declares it reaches its referent
    through (2026-09-05) and is RECORDED here, under `referent_chain:`,
    because a chain that were re-derived on each read would be an inference
    rather than the declaration the classifier is meant to consult. Nothing
    here confers anything; it is a record.
    """
    found = policy.classify(name, role, pins, chain)
    lines = [
        f"{indent}naming:",
        f"{indent}  form: {found.family}",
        f"{indent}  role: {found.role or '~'}",
        f"{indent}  also_matches: [{', '.join(found.also_matches)}]",
    ]
    referents = policy.descendant_referents(name)
    if referents:
        # THESE TWO LINES FOLLOW THE FORM, not the family that won. They
        # record that the NAME also spells a claim of descent, and whether
        # that claim's referent is declared in this tree — regardless of
        # whether the classification actually asserts descent. So a neutral
        # product in `openx<Product>` form (`openxFactory`, `openxDox`) shows
        # the overlap here instead of hiding it, even though it classifies as
        # `neutral-product` and elects its own shape. The classification
        # itself is `form:` above, and only `form: domain-descendant` asserts
        # descent; these two lines are the record of what the SPELLING also
        # claims, not of what won.
        #
        # The CANONICAL spelling is what is recorded, whichever one is pinned.
        lines.append(f"{indent}  descendant_referent: {referents[0]}")
        lines.append(f"{indent}  referent_declared: "
                     + ("true" if found.referent.reached else "false"))
        if found.referent.chain:
            lines.append(f"{indent}  {CHAIN_RECORD_FIELD}: ["
                         + ", ".join(found.referent.chain) + "]")
    return "\n".join(lines)


def descendant_note(policy: NamingPolicy, name: str, role: str,
                    pins, chain=()) -> str | None:
    """The one line the plan prints when a name also matches the claim form."""
    found = policy.classify(name, role, pins, chain)
    if "domain-descendant" not in found.also_matches:
        return None
    referent = policy.descendant_referent(name)
    if found.referent.status == "broken":
        return (f"NOTE {name} also matches the descendant form; it is not a "
                f"descendant because {found.referent.reason}")
    return (f"NOTE {name} also matches the descendant form; it is not a "
            f"descendant because no pin on {referent} is declared — declare "
            f"`{neutral_pin_path(referent)}` later if it becomes one, "
            f"or record the chain that reaches it")


class Materialized:
    """What `materialize_assembly_root` wrote, and where it had to write it.

    `shape_files` is the ordered list of paths the shape pin digests, at the
    paths they ACTUALLY landed on — a pin that names a path nothing is at is
    a refusal in `validate-pins.py`, and rightly.
    """

    def __init__(self) -> None:
        self.written: list[str] = []
        self.collisions: list[tuple[str, str]] = []
        self.shape_files: list[str] = []

    def follow_ups(self) -> list[str]:
        return [collision_follow_up(intended, actual)
                for intended, actual in self.collisions]


def materialize_assembly_root(shape_root: Path, target: Path,
                              values: dict[str, str], *,
                              collision_dir: str | None = None,
                              append: dict[str, str] | None = None,
                              neutral_pins: dict[str, dict] | None = None,
                              spell=None) -> Materialized:
    """Write the assembly-root skeleton into `target`.

    `collision_dir` — where a template file goes when the target path is
    already taken. `None` means "there can be no collision" and a collision
    raises, which is the scaffold's case: it built the directory itself.

    `append` maps a template-relative path to text appended after rendering
    (the adopt tool's `CONTRACTS_DIR` block).

    `neutral_pins` maps a neutral product name to the values for its pin file,
    each rendered from `contracts/neutral-product-pin.yaml`.

    `spell` writes each path a refusal names (#183's `materialize-*`), as
    `first_and_more` takes one: between backticks when it is None, which is
    all the scaffold's own paths need. `adopt-project.py` passes its
    `_spelled`, because the source it adopts can hold a symlink to any name.
    """
    return _materialize(
        shape_root, shape_root / "templates" / "assembly-root", target, values,
        templated=TEMPLATED, verbatim=COPIED_VERBATIM,
        from_shape=COPIED_FROM_SHAPE, executable=EXECUTABLE,
        collision_dir=collision_dir, append=append, neutral_pins=neutral_pins,
        spell=spell)


def assembly_root_paths(neutral_pins=()) -> tuple[str, ...]:
    """Every path `materialize_assembly_root` writes when nothing is in the
    way, in the order it writes them. `neutral_pins` names the products of
    the `neutral_pins` that call is handed (iterating that mapping yields
    them); with none, no neutral-product pin is declared.

    READ FROM THE LISTS THAT CALL HANDS `_materialize`, plus the file each
    declared pin is written to (`neutral_pin_path`) and the pin it writes
    last, never kept by hand: `adopt-project.py` (#172) and
    `scaffold-project.py` (#197) refuse a leg mount path that overlaps one of
    these, and `adopt-project.py check` follows each of them through the
    symlinks a plan keeps in the root before any leg exists (#178). A second
    list would let the shape gain a file the refusal does not know about,
    or one that `check` does not follow. `EXECUTABLE` adds no path (it
    marks paths the lists already write), and a collision moves a path
    under the caller's `collision_dir`, which is the caller's to name.
    `tests/test_adopt_leg_path_collisions.py`,
    `tests/test_adopt_root_symlinks.py` and
    `tests/test_scaffold_leg_path_collisions.py` materialize into an empty
    directory and hold this to what was written, the last with pins too.
    """
    return (*TEMPLATED, *COPIED_VERBATIM,
            *(rel for _, rel in COPIED_FROM_SHAPE),
            *(neutral_pin_path(product) for product in neutral_pins),
            SHAPE_PIN)


# ---------------------------------------------------------------------------
# A leg's mount path overlaps nothing the shape writes (#172, #197)
# ---------------------------------------------------------------------------
#
# `adopt-project.py` asked this first (#172). `--spec-path contracts` is
# canonical, so #169 passed it, and `execute` made and pushed both legs,
# mounted one at `contracts`, wrote the shape's `contracts/spec-pin.yaml`
# INTO the mounted leg, and died staging the split.
#
# THE SHAPE HALF OF THAT RULE MOVED HERE, beside the list it reads, because
# `scaffold-project.py` asks the same question of its own two leg paths
# (#197), and a second copy of the relation or of the sentence is how two
# tools start refusing different paths. Two halves are adopt's alone and
# stayed there: the one that reads a SOURCE tree, a path an adoption plan
# keeps in the root, and the one about `shape/`, the directory only an
# adoption writes the shape's copies into.
#
# A mount path is refused when it EQUALS, CONTAINS or LIES INSIDE a path
# `assembly_root_paths` lists, compared WITHOUT REGARD TO CASE: a macOS or
# Windows disk keeps `Scripts` and `scripts` as one directory.

#: Said where an overlap holds only once case is ignored.
CASE_ASIDE = " once case is ignored, as a macOS or Windows disk does"
#: The exit every collision has; a root-kept one has a second.
MOVE_THE_LEG = "choose another path for the leg"


def path_overlap(leg: str, other: str) -> tuple[str, str] | None:
    """How the mount path `leg` stands to the path `other`: `(relation,
    aside)`, the relation `is`, `contains` or `is inside`, and the aside
    `CASE_ASIDE` when it holds only once case is ignored. None when the two
    do not overlap at all."""
    for mine, theirs, aside in ((leg, other, ""),
                                (leg.casefold(), other.casefold(), CASE_ASIDE)):
        if mine == theirs:
            return "is", aside
        if theirs.startswith(mine + "/"):
            return "contains", aside
        if mine.startswith(theirs + "/"):
            return "is inside", aside
    return None


def first_and_more(paths: list[str], spell=None) -> str:
    """`a` or `a` and 2 more: one path named, the rest counted. `spell`
    writes the named path, between backticks by default: the shape's own
    paths need nothing more. `adopt-project.py` passes its `_spelled` for a
    source path the plan keeps in the root, which can hold any character
    (#212)."""
    more = f" and {len(paths) - 1} more" if len(paths) > 1 else ""
    named = spell(paths[0]) if spell else f"`{paths[0]}`"
    return f"{named}{more}"


def shape_path_collisions(what: str, value: str,
                          collision_dir: str | None = None, *,
                          neutral_pins=()) -> list[str]:
    """Where the mount path `value` overlaps a path of `assembly_root_paths`:
    one sentence, naming the first path it overlaps and counting the rest,
    or none. `what` names the value as its caller does (`--spec-path`,
    `legs.spec_path`).

    `collision_dir` IS THE ONE THE CALLER HANDS `materialize_assembly_root`,
    so the two callers differ here by the argument they differ by there.
    `adopt-project.py` passes its `COLLISION_DIR`, `shape` with no slash,
    from `_shape_collisions`, which `plan`, `check` and `execute` all reach
    through `leg_path_collisions`. `execute` is the act that mounts the legs
    FIRST and materializes over them, so a shape file at a mount goes into
    the mounted leg or beside it under that directory, and the sentence
    names `execute` whichever of the three asks. Whether `value` overlaps
    `collision_dir` itself is the caller's question, not this one's.
    `scaffold-project.py` passes none (#197): it materializes into an empty
    directory and mounts the legs AFTER, so `git submodule add` meets a path
    the shape already wrote.

    `neutral_pins` IS THE SAME KIND OF ARGUMENT: the products whose pins the
    caller hands the materializer, so the paths asked about are
    `assembly_root_paths(neutral_pins)`, each pin's file among them. The
    scaffold passes its `--pin` products (#197); adopt hands the materializer
    no pin and passes none, so its list and its sentences are unchanged.
    """
    out: list[str] = []
    files = [path for path in assembly_root_paths(neutral_pins)
             if path_overlap(value, path)]
    if files:
        relation, aside = path_overlap(value, files[0])
        them = "them" if len(files) > 1 else "it"
        if collision_dir is None:
            consequence = (
                " before the legs are mounted, and Git cannot mount a leg at "
                "a path the root already holds, or beyond a file it holds on "
                "the way there")
        else:
            consequence = (
                f", and `execute` would write {them} into the mounted leg or "
                f"beside it under `{collision_dir}/`, leaving the root "
                f"without {them}")
        out.append(
            f"{what} {value!r} {relation} {first_and_more(files)}{aside}. "
            f"The shape writes {them} into the assembly root{consequence}: "
            f"{MOVE_THE_LEG}.")
    return out


def materialize_family_root(shape_root: Path, target: Path,
                            values: dict[str, str]) -> Materialized:
    """Write the FAMILY-root skeleton into `target`.

    A THIRD CALLER OF THE ONE MATERIALIZER, and the reason it was worth
    generalising rather than copying: a family root carries the same copy pin
    an assembly root does — `contracts/shape-pin.yaml`, per-file sha256 rows
    over the copies, `commit` and `tree_sha256` for the revision they came
    from — so `update-shape.py` re-syncs one exactly as it re-syncs the other.
    A second implementation of the digest-writing loop is how the two would
    start disagreeing about which files are pinned.

    No collision directory: `family.py init` builds the directory itself (or
    reuses an EMPTY repository, which by definition collides with nothing).
    """
    return _materialize(
        shape_root, shape_root / "templates" / "family-root", target, values,
        templated=FAMILY_TEMPLATED, verbatim=FAMILY_COPIED_VERBATIM,
        from_shape=FAMILY_COPIED_FROM_SHAPE, executable=FAMILY_EXECUTABLE)


# ---------------------------------------------------------------------------
# Writing only where the shape's files belong (#183)
# ---------------------------------------------------------------------------
#
# An adoption materializes INTO a clone of the source, and the plan can keep a
# symlink in the root at or above a path the shape writes. `.github -> ci`,
# with `ci/` in the same tree, is followed, and the workflow lands in `ci/`.
# A link that led out of the clone was followed too, and the shape's
# `validate.yml` went into a directory nobody named. A link round a loop, a
# link to nothing, or a checkout with `core.symlinks=false` (which writes each
# symlink as a plain FILE) ended in a Python traceback after both legs had
# been pushed. `adopt-project.py check` reports such a link before any leg
# exists. The refusals below apply the same rule where the files are
# written, for a caller that skipped `check`.
#
# A symlink AT a path the shape writes, whose destination is already there,
# is never written through: `place` sees the path taken and writes the
# shape's copy beside it, under the collision directory. A symlink at or above
# that COPY was followed, and the copy landed on whatever it led to: over the
# source's own `README.md` for `shape -> .`, or into a directory, in a
# traceback. Where a copy lands is `copy_in_the_way`'s question (#262), which
# `place` asks first, a symlink on the way or not; what is asked here is
# what still holds for the copy after it, as for any other path.

#: How many symlinks one lookup follows: Linux's own limit (MAXSYMLINKS),
#: past which `open()` gives up with ELOOP, whether the links go round a loop
#: or only chain that far. `adopt-project.py` follows the plan's tree and the
#: split commit's by the same count. macOS gives up after 32, so a chain of 33
#: to 40 passes here and fails there, as it did before #183.
SYMLINK_HOPS = 40
#: What a lookup that follows more than `SYMLINK_HOPS` symlinks has met. It
#: cannot tell a loop from a long chain, and need not: `open()` gives up on
#: both. `adopt-project.py`'s finding says it in the same words.
TOO_MANY_SYMLINKS = (f"more than {SYMLINK_HOPS}, round a loop or along a "
                     "chain longer than Linux's `open()` follows")

#: What each refusal below says to do. It is raised BEFORE the `mkdir` and the
#: write, so nothing was written at the path it names. It does not send the
#: reader to `adopt-project.py check`: `check` reports what is in the way
#: before any leg exists (a symlink as `plan-root-symlink`, #183; a plain
#: FILE where the shape needs a directory as `plan-root-blocks-shape`, #263),
#: and `execute` refuses it there, so this refusal is met only by a caller
#: that skipped `check`.
#: It names the work directory as #200's mount remediation does: by now
#: `execute` has cloned both legs into it, and a re-run cannot clone there.
UNWRITABLE_REMEDIATION = (
    "Remediation: nothing was written at that path. The shape writes its "
    "files only inside the directory it is given, only beneath directories, "
    "and through a symlink only when its relative target stays inside and "
    "leads where nothing is yet. What is in the way is the source "
    "repository's own: when adopting, send it to a leg or `drop` it in the "
    "plan, and run `execute` again with fresh leg repositories and an empty "
    "`--work-dir`, or none: a `--work-dir` this run was given still holds "
    "its clones of both legs, and the next run cannot clone into them.")

#: The parts of a path that name no entry of their own: `open()` takes each
#: of them only from a directory that is there.
NOT_A_NAME = ("", ".", "..")

#: The refusal for a path something in the way stops the shape writing.
BLOCKED = "materialize-blocked"


def _ticked(name: str) -> str:
    """`name` between backticks: how a refusal below names a path when its
    caller passes no `spell`, as `first_and_more` names one. The shape's own
    paths need nothing more. `adopt-project.py` passes its `_spelled`,
    because a source's symlink can lead to a name holding a line break or an
    ESC, and #212 keeps every refusal on its one line."""
    return f"`{name}`"


def _link_parts(here: Path, at: str, rel: str, target: Path, hops: int,
                name) -> list[tuple[str, str]]:
    """The target of the symlink `here` (spelled `at`) as path parts, each
    with `at`, or a refusal when it is one hop more than `open()` follows,
    it is empty, or it is absolute. `name` writes each path a refusal names.

    An empty target is not `.`: `open()` finds nothing through it, and the
    parts below would read it as the directory the link is in."""
    if hops > SYMLINK_HOPS:
        raise Refusal("materialize-symlink-loop",
                      f"{name(rel)} follows too many symlinks at {name(at)} "
                      f"in {target}: {TOO_MANY_SYMLINKS}",
                      UNWRITABLE_REMEDIATION)
    link = os.readlink(here)
    if not link:
        raise Refusal(BLOCKED,
                      f"{name(rel)} cannot be written: the symlink "
                      f"{name(at)} has an empty target, which leads nowhere",
                      UNWRITABLE_REMEDIATION)
    if os.path.isabs(link) or os.path.splitdrive(link)[0]:
        raise Refusal(
            "materialize-outside",
            f"{name(rel)} would be written through the symlink {name(at)}, "
            f"which leads to the absolute path {name(link)}; the shape "
            f"follows only a symlink whose relative target stays inside "
            f"{target}",
            UNWRITABLE_REMEDIATION)
    # Windows reads a link back in its own separator; a POSIX name may hold
    # a backslash, so only the platform's own separator is translated.
    return [(part, at) for part in link.replace(os.sep, "/").split("/")]


def _from_a_directory(target: Path, rel: str, done: list[str], part: str,
                      via: str, name) -> None:
    """Refuse `part`, a `..`, `.` or empty part of the target of the symlink
    `via`, where `open()` cannot take it: `..` above `target`, or any of
    them after something that is not a directory. `open()` takes them
    physically, so `a/..` fails where `a` is missing (FileNotFoundError) or
    a file (NotADirectoryError), and `ci/` where `ci` is missing
    (IsADirectoryError): each was a traceback after both legs."""
    if not done:
        if part == "..":
            raise Refusal(
                "materialize-outside",
                f"{name(rel)} would be written outside {target}: at the "
                f"symlink {name(via)} it climbs above it",
                UNWRITABLE_REMEDIATION)
        return
    here = target.joinpath(*done)
    if not here.is_dir():
        raise Refusal(
            BLOCKED,
            f"{name(rel)} cannot be written: the target of the symlink "
            f"{name(via)} goes on from {name(root_key(here, target))}, which "
            "is not a directory here",
            UNWRITABLE_REMEDIATION)


def _followed(target: Path, rel: str, name) -> list[str]:
    """`rel` under `target` with each symlink on the way followed, the way
    `open()` follows them: the parts it lands on, relative to `target`. A
    refusal when one leads out of `target`, when there are more of them than
    `open()` follows, or when one leads on from something that is not a
    directory."""
    parts = [(part, "") for part in rel.split("/")]
    done: list[str] = []
    hops = 0
    while parts:
        part, via = parts.pop(0)
        if part in NOT_A_NAME:
            _from_a_directory(target, rel, done, part, via, name)
            if part == "..":
                done.pop()
            continue
        here = target.joinpath(*done, part)
        if here.is_symlink():
            hops += 1
            parts = _link_parts(here, root_key(here, target), rel, target,
                                hops, name) + parts
        else:
            done.append(part)
    return done


def _blocker(target: Path, rel: str, landed: list[str],
             name) -> str | None:
    """What stands where `rel` needs a directory, or where a symlink at it
    leads, or None.

    `mkdir(parents=True)` makes a MISSING directory and everything below it,
    and passes through a directory or a symlink to one. It cannot pass a
    file, or a symlink that leads to no directory, and it raised a traceback
    there. A symlink at `rel` itself is written through only into a
    directory that is already there. No path reaches here with something
    already where it lands: `place` writes the shape's copy beside a path
    that is taken, and asks `copy_in_the_way` (#262) where the copy lands
    before it asks this.
    """
    parts = rel.split("/")
    for end in range(1, len(parts)):
        above = target.joinpath(*parts[:end])
        if above.is_dir():
            continue
        if above.is_symlink():
            return (f"{name(root_key(above, target))} is a symlink to "
                    f"{name(os.readlink(above))}, which is not a directory "
                    "here")
        if above.exists():
            return (f"{name(root_key(above, target))} is a file, not a "
                    "directory")
        return None
    path = target / rel
    if path.is_symlink() and not target.joinpath(*landed[:-1]).is_dir():
        return (f"the symlink {name(rel)} leads to {name(os.readlink(path))}, "
                "and there is no directory there to write it in")
    return None


def _refuse_unwritable(target: Path, rel: str, spell=None) -> None:
    """Refuse, before the `mkdir` and the write, a path the shape must not
    write at (outside `target`, or through too many symlinks) or cannot
    (#183). `spell` writes each path the refusal names, `_ticked` where it
    is None.
    `target` itself is the directory the caller gave, and is named as it
    is, as `materialize-collision` names it."""
    name = spell or _ticked
    blocker = _blocker(target, rel, _followed(target, rel, name), name)
    if blocker:
        raise Refusal(BLOCKED,
                      f"{name(rel)} cannot be written: {blocker}",
                      UNWRITABLE_REMEDIATION)


def _materialize(shape_root: Path, template_root: Path, target: Path,
                 values: dict[str, str], *, templated, verbatim, from_shape,
                 executable, collision_dir: str | None = None,
                 append: dict[str, str] | None = None,
                 neutral_pins: dict[str, dict] | None = None,
                 spell=None) -> Materialized:
    """The shared body. Four lists in, one `Materialized` out.

    The order is load-bearing and is the same for every root: templated files
    first, then the verbatim copies and the copies out of openRepoShape's own
    tree (those two are what the shape pin digests), then any neutral-product
    pins, then the executable bits, and LAST `contracts/shape-pin.yaml` —
    rendered over the paths the copies actually landed on, because a pin that
    names a path nothing is at is a refusal in the validator, and rightly.
    """
    result = Materialized()

    def place(rel: str, write) -> str:
        """Write `rel`, or, if it is taken, the same name under `collision_dir`."""
        path = target / rel
        if path.exists():
            if collision_dir is None:
                raise Refusal(
                    "materialize-collision",
                    f"{path} already exists and this materializer was given no "
                    "collision directory",
                    "Remediation: scaffold into an empty directory, or call "
                    "with collision_dir set (which is what adopt does).")
            actual = f"{collision_dir}/{rel}"
            in_the_way = copy_in_the_way(target, actual)
            if in_the_way:
                raise Refusal(
                    "materialize-copy-blocked",
                    f"the shape's copy of `{rel}` cannot be written to "
                    f"`{actual}`: {in_the_way}, and nothing was written there",
                    "Remediation: the shape writes its copy of a file the "
                    "root already holds under its collision directory, so "
                    "the source cannot keep its own path there. "
                    "`adopt-project.py check` reports a plan that does as "
                    "`plan-root-blocks-shape-copy`, before any leg exists. "
                    "Send that path to a leg or `drop` it in the plan, and "
                    "run `execute` again with fresh leg repositories and "
                    "an empty `--work-dir`, or none: this run made both "
                    "legs and cloned them into the work directory it was "
                    "given.")
            result.collisions.append((rel, actual))
            path = target / actual
        _refuse_unwritable(target, root_key(path, target), spell)
        path.parent.mkdir(parents=True, exist_ok=True)
        write(path)
        rel_written = root_key(path, target)
        result.written.append(rel_written)
        return rel_written

    for rel in templated:
        text = render((template_root / rel).read_text(encoding="utf-8"),
                      values, rel)
        text += (append or {}).get(rel, "")
        place(rel, lambda p, t=text: write_lf(p, t))
    for rel in verbatim:
        text = (template_root / rel).read_text(encoding="utf-8")
        text += (append or {}).get(rel, "")
        result.shape_files.append(
            place(rel, lambda p, t=text: write_lf(p, t)))
    for src, rel in from_shape:
        text = (shape_root / src).read_text(encoding="utf-8")
        result.shape_files.append(
            place(rel, lambda p, t=text: write_lf(p, t)))
    for product, pin_values in (neutral_pins or {}).items():
        rel = neutral_pin_path(product)
        text = render((template_root / NEUTRAL_PIN_TEMPLATE)
                      .read_text(encoding="utf-8"), {**values, **pin_values}, rel)
        place(rel, lambda p, t=text: write_lf(p, t))
    for rel in executable:
        actual = next((w for w in result.written if w.endswith(rel)), None)
        if actual:
            (target / actual).chmod(0o755)

    # The shape pin's `files:` block digests the copies just written, so it is
    # rendered LAST and over the paths they actually landed on.
    rows = "\n".join(f"  - path: {rel}\n    sha256: \"{file_sha256(target / rel)}\""
                     for rel in result.shape_files)
    text = render((template_root / SHAPE_PIN).read_text(encoding="utf-8"),
                  {**values, "SHAPE_FILES": rows}, SHAPE_PIN)
    place(SHAPE_PIN, lambda p, t=text: write_lf(p, t))
    return result


def copy_out(src: Path, dst: Path) -> None:
    """A byte copy that makes the parent directory first."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


# ---------------------------------------------------------------------------
# A leg's mount path is CANONICAL, or it is refused (#169, #179)
# ---------------------------------------------------------------------------
#
# `plan --spec-path spec/` used to be accepted, written into the plan and
# passed by `check`. `execute` then ran `git submodule add ... spec/`, which
# Git records at `spec`, and `git config -f .gitmodules submodule.spec/.url`,
# which writes a SECOND section literally named `spec/` that no mount owns: the
# registration the real mount carries still pointed at the operator's local
# work directory, and on `main` the run ended `adoption verified`. A broken
# assembly passed as a good one.
#
# THE FIX IS TO REFUSE, NEVER TO REWRITE. A plan is a file a human or an AI
# edits on purpose, and a value quietly changed on its way to `git` is a value
# nobody chose: `spec/` silently becoming `spec` would be right today and the
# next spelling would not be. So the three places that read a leg path --
# `plan` (the flag), `check` (a finding) and `execute` (a refusal) -- ask the
# ONE question below, and where a canonical spelling exists the answer NAMES it
# so the person is a retype away from a plan that passes.
#
# THE SCAFFOLD IS THE FOURTH READER (#179). `scaffold-project.py` writes
# `legs.spec_path` and `legs.code_path` into a new project and mounts the
# legs with the same two commands, and until it asked this question
# `--spec-path spec/` scaffolded a project whose recursive clone failed
# once the operator's work directory was gone. It refuses before it has
# created a work directory or a remote, with the same sentence.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py`, which is a SHAPE COPY:
# the materializer writes it into every project and
# `contracts/shape-pin.yaml` digests it, so about 250 lines added
# there would put an `upstream-changed scripts/repo_shape.py` row in front
# of every project in the estate for a rule no project's own copy ever
# asks (see "Commit trailers" above for the same argument). This module
# is in no copy list and both tools already import it.
#
#   CANONICAL = a relative POSIX path of one or more segments, each non-empty
#   and neither `.` nor `..`: no leading `/` or `./` (nor a drive letter), no
#   trailing `/`, no `//`, no backslash. The two legs also take DIFFERENT
#   paths, neither inside the other (`legs` and `legs/spec`): Git records one
#   gitlink at the outer path and cannot record a mount inside it. Two paths
#   that differ only in case are ONE path on a macOS or Windows disk, so
#   `Spec` and `spec`, or `Legs/spec` and `legs`, are equal or nested too.
#
# A canonical path can still be one Git cannot mount a leg at, so it is also
# refused, and offered no spelling (it names no place Git can record, and
# picking another for the person is the rewrite this refuses):
#
#   * a segment that is `.git`, `git~1` (its Windows 8.3 short name) or
#     `.gitmodules`, in any case. `git submodule add` refuses `.git`, `.GIT`,
#     `git~1` and `.gitmodules`, and at `legs/.git` it exits 0 and records NO
#     gitlink, so the run ends `adoption verified` over an assembly with no
#     mount for that leg;
#   * a segment Windows cannot check out as written: one ending in a dot or a
#     space, which it strips, or a device name (`CON`, `PRN`, `AUX`, `NUL`,
#     `COM1`-`COM9`, `LPT1`-`LPT9`, with or without an extension);
#   * a value `checked_value` would refuse (whitespace, non-ASCII text, a
#     leading `-`, `C:spec`, a shell metacharacter), so that `plan` and
#     `check` say what `execute` was always going to say instead of `check`
#     passing a plan `execute` then refuses. The alphabet is `checked_value`'s
#     own (`SAFE_ARG_RE`): it is asked here, not copied.

#: `D:\work\Thing` or `D:/work/Thing` — a Windows absolute path, in either
#: spelling. `_spelling_reason` below asks it whether a leg path is a drive
#: letter's. adopt-project.py imports it too, for two questions of its own:
#: `Source.open` tells a `--source` path the operator got wrong from a
#: repository name, and `_PlannedRoot` asks, on Windows only, whether a
#: symlink the plan keeps leads to an absolute place on that machine. Both
#: are adopt-project.py's, not this file's.
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")

#: Git's own names, casefolded: a leg cannot be mounted at a segment spelled
#: like one. `git~1` is how an NTFS disk shortens `.git`.
GIT_OWN_NAMES = frozenset({".git", "git~1", ".gitmodules"})

#: A Windows device name, with or without an extension: `CON`, `nul`,
#: `COM1.txt`. A file or directory called one cannot be created there.
WINDOWS_DEVICE_RE = re.compile(r"(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?",
                               re.IGNORECASE)

#: What a plan's non-text `spec_path` was read as. The YAML reader keeps no raw
#: text (`007` is read as 7, `true` and `True` as one boolean, `1.50` as 1.5),
#: so a sentence that echoed the parsed value would show something the file
#: never said; it names the KIND the reader made of it instead.
NOT_TEXT_KINDS = {bool: "true or false", int: "a number", float: "a number",
                  list: "a list", dict: "a mapping"}

LEG_PATH_REMEDIATION = (
    "Remediation: nothing here rewrites a path for you, so correct the value "
    "yourself. A leg path is relative and POSIX: one or more plain segments "
    "such as `spec` or `legs/spec`, with no leading `/` or `./`, no trailing "
    "`/`, no `//`, no `..` and no backslash; no segment is one of Git's own "
    "names (`.git`, `git~1`, `.gitmodules`, in any case), ends in a dot or a "
    "space, or is a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, "
    "`COM1`-`COM9`, `LPT1`-`LPT9`, with or without an extension); the whole "
    f"value matches {SAFE_ARG_RE.pattern} and does not begin with `-`; and "
    "the two legs take different paths, neither inside the other, whatever "
    "the case."
)


def _spelling_reason(text: str) -> str | None:
    """Why `text` is not a CANONICAL spelling of a leg path, or None."""
    if not text:
        return "it is empty"
    if text.startswith("/") or WINDOWS_ABSOLUTE_RE.match(text):
        return ("it is absolute (`/spec` on every platform, `C:/spec` on "
                "Windows), and a leg is mounted INSIDE the assembly root, so "
                "its path is relative to it")
    if "\\" in text:
        return "it has a backslash, and a path here is written with `/`"
    segments = text.split("/")
    if ".." in segments:
        return ("it has a `..` segment, so it names a different place than it "
                "spells and can climb out of the assembly root")
    if all(segment in ("", ".") for segment in segments):
        return ("it names the assembly root itself, and a leg is mounted "
                "INSIDE the root, not at it")
    if "" in segments or "." in segments:
        return ("Git records a mount without its `.` segments (a leading "
                "`./`), a trailing `/` or a doubled `/`, so the mount and its "
                "`.gitmodules` entry would name two different paths")
    return None


def _unmountable_reason(text: str) -> str | None:
    """Why a leg cannot be mounted at `text`, a path that is already
    canonical: a name Git keeps for itself, or one Windows cannot check out as
    written. None when it can."""
    for segment in text.split("/"):
        if segment.casefold() in GIT_OWN_NAMES:
            return (f"`{segment}` is one of Git's own names (`.git`, its "
                    "Windows short name `git~1`, `.gitmodules`, in any case), "
                    "and Git either refuses to mount a leg at it or records "
                    "no mount there")
        if segment.endswith((".", " ")):
            return (f"`{segment}` ends in a dot or a space, which Windows "
                    "strips, so the mount would be checked out there under "
                    "another name")
        if WINDOWS_DEVICE_RE.fullmatch(segment):
            return (f"`{segment}` is a Windows device name (with or without "
                    "an extension), which cannot be created there")
    return None


def _canonical_spelling(text: str) -> str | None:
    """The canonical spelling of `text`, where one exists, else None.

    Only a SPELLING is offered: dropping empty and `.` segments says the same
    relative path in the one form Git keeps. A backslash becomes `/` because
    that is the one thing a person who typed it can mean: on Git for Windows
    it IS a separator, while on POSIX it is an ordinary filename character and
    the same string names another path, so the `/` spelling is offered for
    retyping and is not a claim that the two are equal everywhere. An absolute
    path and one with a `..` have no such spelling -- they name another place,
    and picking it for the person is the rewrite this refuses -- and neither
    has a result this check, or `checked_value`, would itself refuse
    (`./.git` is not answered `.git`, nor `-x/` `-x`).
    """
    if text.startswith(("/", "\\")):
        return None
    kept = [s for s in text.replace("\\", "/").split("/")
            if s not in ("", ".")]
    if not kept or ".." in kept:
        return None
    candidate = "/".join(kept)
    if _unmountable_reason(candidate) is not None:
        return None
    try:
        return checked_value("leg path", candidate)
    except Refusal:
        return None


def leg_path_problem(what: str, value) -> str | None:
    """One leg's mount path: None when it is one `execute` will mount, else
    the sentence that says what is wrong with it and, where one exists, what
    to write instead.

    Asked in this order: the SPELLING (canonical or not), then the NAMES Git
    and Windows keep, then the alphabet `checked_value` allows on a command
    line, so that `plan`, `check` and `execute` refuse the same values.

    `what` is how the caller names the value -- `--spec-path`, or
    `legs.spec_path` for one read out of a plan -- so the sentence points at
    the thing the person has in front of them.
    """
    if not isinstance(value, str):
        kind = NOT_TEXT_KINDS.get(type(value), "something that is not text")
        return (f"{what} is not text: its value was read as {kind}, and a "
                "path is written as text, so quote it")
    spelling = _spelling_reason(value)
    if spelling:
        offered = _canonical_spelling(value)
        return (f"{what} is {value!r}, which is not a canonical leg path: "
                f"{spelling}." + (f" Write {offered!r}." if offered else ""))
    unmountable = _unmountable_reason(value)
    if unmountable:
        return (f"{what} is {value!r}, which a leg cannot be mounted at: "
                f"{unmountable}.")
    try:
        checked_value(what, value)
    except Refusal as exc:
        return f"{exc.detail}."
    return None


def leg_path_problems(spec: tuple, code: tuple) -> list[str]:
    """Everything wrong with the two leg paths, as sentences; `[]` when none.

    `spec` and `code` are `(what, value)` pairs. The pair is compared only
    when each path is fine on its own, because "equal" and "inside" are
    statements about paths and mean nothing for two strings that are not one.
    They are compared WITHOUT regard to case: a macOS or Windows disk keeps
    one of `Spec` and `spec`, and the second mount would collide there AFTER
    both leg repositories exist.
    """
    problems = [p for p in (leg_path_problem(*spec), leg_path_problem(*code))
                if p]
    if problems:
        return problems
    (spec_what, spec_path), (code_what, code_path) = spec, code
    if spec_path == code_path:
        return [f"{spec_what} and {code_what} are both {spec_path!r}, and two "
                "legs cannot be mounted at one path."]
    if spec_path.casefold() == code_path.casefold():
        return [f"{spec_what} {spec_path!r} and {code_what} {code_path!r} "
                "differ only in case, which a macOS or Windows disk keeps as "
                "ONE path, so two legs cannot be mounted at them."]
    for (inner_what, inner), (outer_what, outer) in ((spec, code),
                                                    (code, spec)):
        if inner.casefold().startswith(outer.casefold() + "/"):
            aside = ("" if inner.startswith(outer + "/") else
                     " once case is ignored, as a macOS or Windows disk does")
            return [f"{inner_what} {inner!r} is inside {outer_what} "
                    f"{outer!r}{aside}, and Git records ONE gitlink at the "
                    "outer path, so the inner leg cannot be mounted there."]
    return []


def refuse_bad_leg_paths(refusal: str, spec: tuple, code: tuple) -> None:
    """Raise `Refusal(refusal)` naming every problem found in the two paths.

    `refusal` is the caller's own code (`adopt-bad-leg-path`,
    `plan-bad-leg-path`, `scaffold-bad-leg-path`), so each tool refuses in
    its own voice and the person reads which tool said it.
    """
    problems = leg_path_problems(spec, code)
    if problems:
        raise Refusal(refusal, " ".join(problems), LEG_PATH_REMEDIATION)
