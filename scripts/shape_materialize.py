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

ONE EXCEPTION, `.gitattributes` (#471, ruled by Brett Heap 2026-10-12T22:48Z):
the shape's copy still goes beside, and one marked block of line-ending rules
for the pinned copies is APPENDED to the source's own file, because no file
beside it can reach them. "The shape's line endings" below says why and how.
"""

from __future__ import annotations

import argparse
import codecs
import datetime as _dt
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePath

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    CHAIN_RECORD_FIELD, PATH_CLIMBS, PATH_ITSELF, PATH_NOT_CANONICAL,
    SAFE_ARG_RE, NamingPolicy, Refusal, checked_value, double_quoted,
    file_sha256, path_spelling_fault,
)
# The reader's own parse and its own comment rule, for "The two lines a pin
# is moved by" below. `_strip_comment` is that module's private name and is
# imported on purpose: it is the reader's rule for where a comment starts.
from repo_shape import YamlError, _strip_comment, parse_yaml  # noqa: E402

# What a declared neutral-product pin is read with (#273): the forge's tree
# listing, the owner an unqualified name resolves under, and the digest; and
# which products share a `SHAPE_PIN_SOURCE_<PRODUCT>` variable, the one answer
# the project's own `validate-pins.py` reports on (#275), with two
# declarations ONE product when they share a pin file (`pin_product_key`).
# `scaffold_link_remedies` reads a chain with the same names: each link's
# variable (`pin_source_env_name`), whether another link shares it
# (`pin_source_env_shared`), and the link's name (`repo_basename`) (#661).
from repo_shape import (  # noqa: E402
    GH_TREE_API, NEUTRAL_PRODUCT_OWNER, PIN_SOURCE_ENV_PREFIX,
    pin_product_key, pin_source_env_collisions, pin_source_env_name,
    pin_source_env_shared, repo_basename, tree_digest,
)
# How a `--pin-source` that is not printable is named, the one spelling the
# scaffold's chain WARNING gives it too (#610).
from repo_shape import shown_path  # noqa: E402
# What git answers about where a `--pin-source` is, and why, in its own
# words, where it cannot (#800).
from repo_shape import git_out  # noqa: E402
# What the Free-plan secrets hint goes by (#660): GitHub's three
# visibilities, and the hint's own words, which stay in the pinned copy.
from repo_shape import FREE_PLAN_HINT, VISIBILITY_CHOICES  # noqa: E402
# The topic's fixed prefix, which GitHub's limit on a topic bounds an id by
# (#838).
from repo_shape import TOPIC_PREFIX  # noqa: E402

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
    THE START OF `main()`, and not at each `print`: `shape_advisory.printable`
    flattens its own text to ASCII on every console, as `shape-doctor.py`'s
    `ascii_text` did until #785, which a name cannot afford -- it would
    change what a UTF-8 terminal shows -- and a guard at each site is a
    guard the next `print` goes without.

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

    THE FORM IS THE PROJECT'S OWN VALIDATOR'S (#261), on every Python.
    `date.fromisoformat` reads `2026-W41-6` and `20261011` since Python 3.11,
    and the project's `validate-manifest.py` refuses both: its `elected_on`
    must match its own `DATE_RE`, asked here through the validator the
    template carries (`manifest_validator`) and not copied. A date is read
    only when that rule admits it AND it is a day on the calendar, so the
    answer is the same on 3.9 and 3.14.
    """
    text = str(elected_on)
    try:
        if not manifest_validator().DATE_RE.match(text):
            raise ValueError(f"{text!r} is not YYYY-MM-DD")
        return _dt.date.fromisoformat(text)
    except ValueError as exc:
        raise Refusal(
            "election-date-malformed",
            f"--elected-on {elected_on!r} is not a YYYY-MM-DD date "
            "(and a plan file's `elected_on:` carries the same form)",
            "Remediation: re-run with a zero-padded ISO date, e.g. "
            "--elected-on 2026-09-02 — not 2026-9-2, not an ISO week or "
            "basic-format date (`2026-W41-6`, `20261011`) that Python 3.11 "
            "and later reads and the project's own validator refuses, and "
            "not a word like 'yesterday'. The `reference:` the manifest "
            "records is chosen BY that date, so it has to be readable before "
            "anything is written.",
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
#: And again for the project's manifest validator, which `COPIED_VERBATIM` and
#: `EXECUTABLE` both carry and `manifest_validator` loads from the template.
MANIFEST_VALIDATOR = "scripts/validate-manifest.py"

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
    MANIFEST_VALIDATOR,
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
EXECUTABLE = ("scripts/validate-pins.py", MANIFEST_VALIDATOR,
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


#: THE PLAIN SCALAR: a text that begins with a letter, `_` or `.`, and holds
#: only letters, digits and `_./@:+-`. `adopt-project.py`'s `y` writes a
#: plan's text bare only where it is one and the reader reads it back
#: (#181), and `neutral_pin_entry` writes a pin's product bare only where
#: `y` would, so the rule is here, once, for both (#924). It ends at `\Z`,
#: not `$`: `$` also matches before a FINAL newline, and wrote a file named
#: `Icon\n` bare, over two lines of the plan (#199).
PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z_.][A-Za-z0-9_./@:+-]*\Z")


def neutral_pin_entry(product: str) -> str:
    """One `neutral_product_pins:` entry, as `scaffold-project.py` and
    `adopt-project.py execute` both write it: `product` bare where it is a
    plain scalar (`PLAIN_SCALAR_RE`) that the project's reader reads back as
    `product`, and `double_quoted` (#284) where it is not.

    ONE SPELLING, WHICHEVER TOOL MADE THE ROOT (#924). The scaffold wrote a
    product bare wherever the reader read it back, and adopt wrote it as `y`
    writes the plan's `product:`, so `--pin 0x1F@<commit>` was `- 0x1F` in a
    scaffolded manifest and `- "0x1F"` in an adopted one, and `1_000`,
    `1e3`, `3dGlass` and `-x` the same. The project's reader reads both back
    as typed, but a standard YAML reader (PyYAML's `safe_load`) took the
    scaffold's `0x1F` for 31 and its `1_000` for 1000. Both tools call this
    one function now, and it is adopt's rule: a name that begins with a
    digit or `-` is double-quoted, as `plan` quotes it in `product:`, and
    `openGlass`, `007` and `yes` are written as both tools wrote them. A
    bare `yes`, `on`, `.5` or `.inf` stays bare: the project's reader reads
    it back as typed, though PyYAML does not (#457's L2-14, #912).

    THE READER IS ASKED, as `family.py` asks it of a member's id (#259),
    rather than a list of the words it takes for something else: in the two
    places `y` asks it, after `key: ` and as a `- ` item (#181), and once
    more of the LIST ENTRY, as the manifest's list holds it:
    `  - - a` is a list of its own, where `id: - a` is the text (#715;
    `id: -` is refused since #393). A spelling the reader refuses is read
    back as nothing, so it is double-quoted too. A name it reads back bare,
    `openGlass` and every other plain name, is the line it always was;
    `007`, `2026`, `1.5`, `true` and `null` are double-quoted, and a
    double-quoted name always reads back.
    """
    if PLAIN_SCALAR_RE.match(product) and all(
            _reads_back(written, read) for written, read in (
                (f"key: {product}", {"key": product}),
                (f"- {product}", [product]),
                (f"neutral_product_pins:\n  - {product}",
                 {"neutral_product_pins": [product]}))):
        return product
    return double_quoted(product)


def _reads_back(written: str, read) -> bool:
    """Does the project's reader read `written`, a line or two of YAML, as
    `read`? A spelling it refuses is not read back as anything."""
    try:
        return parse_yaml(written + "\n") == read
    except YamlError:
        return False


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
#: The make targets of the shape's own `Makefile` that a person runs. A root
#: that kept the source's `Makefile` has none of them until the shape's copy
#: is merged into it (#480), and the collision follow-up says so.
#: `tests/test_adopt_e2e.py` holds this to the template's own targets.
SHAPE_MAKE_TARGETS = ("bootstrap", "validate", "pins", "park", "resume")


# ---------------------------------------------------------------------------
# The shape's line endings, in a source's OWN `.gitattributes` (#471)
# ---------------------------------------------------------------------------
#
# THE ONE FILE OF THE SOURCE'S THAT AN ADOPTION WRITES INTO, by Brett Heap's
# ruling of 2026-10-12T22:48Z. Every other collision is written BESIDE, under
# `shape/`, and left to a human to merge. `.gitattributes` cannot be: git
# reads attributes for a path from the `.gitattributes` files of its own
# directory and those above it, so `shape/.gitattributes` governs `shape/`
# alone, and a pinned copy at the root -- `Makefile`, `AGENTS-shape.md`,
# `scripts/bootstrap.py` -- answers to the source's file and nothing else. A
# source with `* text=auto` there, or with any `.gitattributes` at all under
# Git for Windows' default `core.autocrlf=true`, then checked every such copy
# out with CRLF on Windows, and the first `make bootstrap` reported
# shape-copy-drift on each: `validate-pins.py` digests the bytes on disk
# (#51). Adoption's first run on a Windows runner found it.
#
# So the split APPENDS one marked block to the source's file: a comment line,
# then `/<path> text eol=lf` for each pinned copy outside `shape/`. Later lines
# win in a `.gitattributes`, and each line names one file, so the block
# settles those copies' line endings and nothing else of the source's. None of
# the source's own lines is changed; a file that does not end in a newline
# gets one before the block, which is the only byte written that is not the
# block's. `adopt-project.py`'s verification counts the file as the source's
# bytes followed by exactly this block, and `update-shape.py apply --add`
# extends it when the standard adds a copy at the root later.
#
# EACH COPY IS NAMED WHERE GIT TRACKS IT (#807). A source may keep a
# symlinked directory in the root that the shape writes through (`.github ->
# ci`, a layout #504 accepts), and git tracks a copy written through it where
# the link leads: `ci/workflows/validate.yml`. A line naming only the link's
# spelling, `/.github/workflows/validate.yml`, governed nothing, so under the
# source's `* text=auto eol=crlf` a clone wrote that copy with CRLF, and
# `validate-pins.py` reported shape-copy-drift after `execute` had said
# `adoption verified`. So each copy is named where the symlinks inside the
# root lead it, a chain of them followed to its end, as `open()` followed
# them when the copy was written, and then, where that differs, by its pinned
# path on the next line. That second line governs nothing while the link is
# kept. It governs the copy once a person replaces the link with what it
# points at, which `update-shape.py` asks for before it rewrites a copy
# reached through one: without it that clone wrote the copy with CRLF, where
# main's had healed (#844's review). Where the links lead out of the root or
# cannot be followed, or to a name no line can spell literally, the copy has
# its pinned line alone, as before. The pin still names each copy by the path
# it was written at, which a clone opens through the same link.

#: The `.gitattributes` a source may already hold at its root.
ATTRIBUTES = ".gitattributes"

#: The comment line that opens the block, and that `extend_eol_block` finds it
#: by. Spelled once: three tools read it.
EOL_BLOCK_HEAD = ("# openRepoShape (#471): the pinned shape copies below check "
                  "out with LF everywhere, as contracts/shape-pin.yaml "
                  "records their bytes")

#: A path the block can name as a literal, anchored pattern. Every copy the
#: shape pins is spelled this way; a name with a space, a glob character or a
#: backslash would be read by git as something else, and is refused rather
#: than written.
EOL_PATH_RE = re.compile(r"[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*")


def eol_line(path: str) -> str:
    """The block's line for the pinned copy at `path`."""
    if not EOL_PATH_RE.fullmatch(path):
        raise Refusal(
            "materialize-attributes-path",
            f"{path!r} cannot be named as a literal path in a "
            f"`{ATTRIBUTES}` line",
            f"Remediation: this is a defect in {SHAPE_REPOSITORY}: every "
            "pinned copy has a plain name. Report it there.")
    return f"/{path} text eol=lf"


def eol_block_paths(shape_files, collision_dir: str,
                    tracked: dict | None = None) -> list[str]:
    """The paths the block names for the pinned copies a source's own root
    `.gitattributes` governs: each one not under `collision_dir`, where the
    shape's own copy of the file governs, in the pin's order.

    Each copy is named first as `tracked` maps its pinned path, where git
    tracks it through the root's symlinks, then by its pinned path where
    that differs (#807). One `tracked` maps to nothing, or to a name no line
    can spell literally, is named by its pinned path alone."""
    tracked = tracked or {}
    return list(dict.fromkeys(
        name for path in shape_files
        if not path.startswith(f"{collision_dir}/")
        for name in (_tracked_or_pinned(path, tracked.get(path)), path)))


def _tracked_or_pinned(pinned: str, tracked: str | None) -> str:
    """`tracked` where a block line can name it, else `pinned`."""
    return tracked if tracked and EOL_PATH_RE.fullmatch(tracked) else pinned


def eol_block(paths) -> str:
    """The block for `paths`: its head, then one line per copy."""
    return "".join(f"{line}\n"
                   for line in (EOL_BLOCK_HEAD, *map(eol_line, paths)))


def with_eol_block(existing: bytes, paths) -> bytes:
    """`existing`, a source's `.gitattributes`, with the block after it.

    Its bytes are kept as they are. One that does not end in a newline gets
    one first, or the head would be read as part of its last line."""
    gap = b"\n" if existing and not existing.endswith(b"\n") else b""
    return existing + gap + eol_block(paths).encode("utf-8")


def extend_eol_block(existing: bytes, paths) -> bytes | None:
    """`existing` with a line for each of `paths` the block lacks, put after
    its last line; None when `existing` holds no block.

    The block is the head line and the `/<path> text eol=lf` lines straight
    after it. Lines a human wrote after the block stay after the new ones.

    THE LAST HEAD IS THE BLOCK (#471's review, NIT-1). A source that already
    held a copy of the head line keeps it, and the split appends its own
    block after it, so the adoption's block is the last one; extending an
    earlier copy would put the new lines before rules of the source's that
    come after it, and a later `eol` rule would win over them.

    A WINDOWS CHECKOUT OF THE FILE MAY BE CRLF: the source's own rules
    govern `.gitattributes` too, and `* text=auto` there, or Git for
    Windows' `core.autocrlf=true`, writes it with CRLF. So lines are matched
    without their ending, and a new line takes the ending the block's last
    line has; git normalises the file when it is committed either way."""
    lines = existing.splitlines(keepends=True)
    bare = [line.rstrip(b"\r\n") for line in lines]
    head = EOL_BLOCK_HEAD.encode("utf-8")
    if head not in bare:
        return None
    start = len(bare) - 1 - bare[::-1].index(head)
    end, named = start + 1, set()
    while end < len(lines):
        match = re.fullmatch(rb"/(\S+) text eol=lf", bare[end])
        if not match:
            break
        named.add(match.group(1).decode("utf-8", "surrogateescape"))
        end += 1
    newline = b"\r\n" if lines[end - 1].endswith(b"\r\n") else b"\n"
    if not lines[end - 1].endswith(b"\n"):
        lines[end - 1] += newline
    new = []
    for path in paths:
        if path not in named:
            named.add(path)
            new.append(eol_line(path).encode("utf-8") + newline)
    return b"".join(lines[:end] + new + lines[end:])


#: The mode git records for a symlink.
LINK_MODE = "120000"


def _tracked_as_link(target: Path, rel: str) -> bool:
    """Whether the git index in `target` records `rel` as a symlink.

    THE INDEX, NOT THE DISK (#471's review, MUST-1). Git for Windows'
    default `core.symlinks=false` checks a tracked link out as a PLAIN FILE
    holding the path it leads to, so `is_symlink()` says no there, and an
    append wrote the block into the link itself: the split commit kept mode
    120000 over a blob that was now the old target followed by the block,
    and the verification called the source's file lost after both legs were
    pushed. A `target` that is no repository has no index to ask, and its
    disk is all there is."""
    try:
        listed = run(["git", "--literal-pathspecs", "-C", str(target),
                      "ls-files", "--stage", "-z", "--", rel])
    except CommandFailed:
        return False
    return any(entry.startswith(f"{LINK_MODE} ")
               for entry in listed.split("\0"))


def _append_eol_block(target: Path, result: "Materialized",
                      collision_dir: str) -> None:
    """Append the block to the source's own `.gitattributes`, when the
    shape's copy of that file had to be written beside it.

    A SYMLINK IS NOT WRITTEN THROUGH: what it leads to may be another file of
    the source's, or nothing in this repository, and git follows no
    `.gitattributes` that is a link anyway: a checkout reads only the link's
    own text, the path it leads to, as one line of rules, which names an
    attribute only where that text holds a space, a tab or a carriage
    return (#654, #906). It is left as it is, and the follow-up says so and
    lists the lines a regular file would need. A link is one on the disk OR
    in git's index (`_tracked_as_link`)."""
    if (ATTRIBUTES, f"{collision_dir}/{ATTRIBUTES}") not in result.collisions:
        return
    path = target / ATTRIBUTES
    if path.is_symlink() or not path.is_file() \
            or _tracked_as_link(target, ATTRIBUTES):
        return
    paths = eol_block_paths(result.shape_files, collision_dir,
                            {rel: _tracked_at(target, rel)
                             for rel in result.shape_files})
    path.write_bytes(with_eol_block(path.read_bytes(), paths))
    result.eol_block = paths


def _tracked_at(target: Path, rel: str) -> str | None:
    """Where git tracks the file written at `rel` under `target`: `rel` with
    each symlink on the way followed as `open()` followed them when it was
    written (`_followed`), so `ci/workflows/validate.yml` for a copy written
    through `.github -> ci` (#807). None where they lead out of `target` or
    cannot be followed."""
    try:
        return "/".join(_followed(target, rel, _ticked))
    except Refusal:
        return None


def collision_follow_up(intended: str, actual: str,
                        beside: dict | None = None, *,
                        attributes_link: bool = False) -> str:
    """The follow-up for ONE collision, in one place.

    Both callers say it: `adopt-project.py plan` PREDICTS the collisions from
    the plan's surviving root paths, and `execute` reports the ones that
    actually happened. Two spellings of the same instruction is how the plan a
    human approves stops matching the commit message they read afterwards.

    A `.gitattributes` THAT IS A SYMLINK gets no block (`_append_eol_block`),
    so `attributes_link` says which of two things happened, and the follow-up
    for a link says that nothing was appended, that git follows no
    `.gitattributes` that is a link, and the exact lines a regular file in
    its place needs (#471's review, SHOULD-2). `plan` knows it from the
    source tree's mode.

    THE MAKEFILE'S MERGE IS WHAT BRINGS THE SHAPE'S MAKE TARGETS (#480). Until
    it is made, `make bootstrap` in the root exits 2 with `No rule to make
    target 'bootstrap'`, so the follow-up says that, and what runs meanwhile:
    `python3 scripts/bootstrap.py`, unless that script went aside as well.
    `beside` maps each shape file written beside one the source kept to where
    it went, the whole list, and only the Makefile's follow-up reads it.
    Where the root's `scripts/bootstrap.py` is the source's own, that command
    runs the source's script and exits 0, so the follow-up names no command,
    and says both merges come first (#493's review, F2).

    AND A PINNED COPY'S FOLLOW-UP SAYS WHAT HAPPENS TO ITS ROW (#502). The
    shape pin has a row for a copied file at the path it landed on, so once
    the merged copy is removed that row names a file that is not there, and
    the project's own `validate-pins.py` is red until `update-shape.py
    apply` drops it. A rendered file, `README.md` among them, has no row.
    `.gitattributes`'s follow-up says it too, under the condition its merge
    already carries: the rest of the copy is merged only if the whole
    project should check out with LF, so the copy is removed only then
    (#471). It returned before that sentence, and a person who merged it
    and removed it was told nothing of the row `check` then reports. The
    follow-up for a `.gitattributes` that is a symlink does not say it: it
    never sends anyone to merge or remove the copy, which stays, pinned.
    """
    if intended == ATTRIBUTES and attributes_link:
        return _attributes_link_follow_up(intended, actual, beside)
    if intended == ATTRIBUTES:
        return (
            f"keep the block at the end of {intended} that opens with "
            f"`{EOL_BLOCK_HEAD}`: the source repository already has a "
            f"{intended}, so the shape's copy was written beside it as "
            f"{actual}, which governs only its own directory, and the split "
            f"appends one `text eol=lf` line to {intended} for each pinned "
            "copy outside it. That block is what makes every checkout, "
            "Windows included, write those copies with the bytes "
            "contracts/shape-pin.yaml records; without it a Windows clone "
            "reports shape-copy-drift on each one. None of the source's own "
            f"lines is changed. Merge the rest of {actual} into {intended} "
            "only if the whole project should check out with LF, and only "
            f"then remove {actual}: `update-shape.py check` reports its pin "
            "row `merged-away`, and `apply` drops the row")
    if intended in ASSISTANT_INSTRUCTIONS:
        return (
            f"add the line `{SHAPE_POINTER_LINE}` to the existing {intended} "
            f"rather than replacing it with {actual}: {intended} is what this "
            "project's agents ALREADY read, and "
            "`contracts/path-classification.yaml` keeps it at the root "
            "(`root-assistant-instructions`) because it addresses the whole "
            f"project. Then delete {actual}. Nothing was overwritten.")
    merge = (
        f"merge {actual} into {intended}: the source repository already has "
        "that name, so the shape's copy was written beside it and NOTHING was "
        "overwritten")
    if intended in COPIED_VERBATIM or any(rel == intended
                                          for _, rel in COPIED_FROM_SHAPE):
        merge += (f". Then remove {actual}: `update-shape.py check` reports "
                  "its pin row `merged-away`, and `apply` drops the row")
    if intended != "Makefile":
        return merge
    targets = ", ".join(f"`{target}`" for target in SHAPE_MAKE_TARGETS)
    script = (beside or {}).get(BOOTSTRAP)
    if script is None:
        return (f"{merge}. The shape's make targets ({targets}) arrive only "
                "with that merge; until then `python3 scripts/bootstrap.py` "
                "is what `make bootstrap` runs")
    return (f"{merge}. The shape's make targets ({targets}) arrive only with "
            f"that merge, and the root's {BOOTSTRAP} is the source's "
            f"own until {script} is merged into it as well, so neither `make "
            f"bootstrap` nor `python3 {BOOTSTRAP}` runs the shape's "
            "bootstrap before both merges are made")


def _attributes_link_follow_up(intended: str, actual: str,
                               beside: dict | None) -> str:
    """The follow-up for a source `.gitattributes` that is a symlink: no
    block was appended, for a link to a path nothing git reads gives the
    root's pinned copies a line ending, and these are the lines a regular
    file needs.

    The copies are the pinned ones that kept their own names, in the pin's
    order: every one `beside` does not send under the collision directory,
    as `eol_block_paths` reads them out of what was written."""
    pinned = [*COPIED_VERBATIM, *(rel for _, rel in COPIED_FROM_SHAPE)]
    lines = ", ".join(f"`{line}`" for line in eol_block(
        [path for path in pinned if path not in (beside or {})]).splitlines())
    return (
        f"{intended} is a symlink, so the split appended nothing to it (it "
        f"never writes through a link) and wrote the shape's copy beside it "
        f"as {actual}, which governs only its own directory. Git follows no "
        f"{intended} that is a symlink: a checkout reads only the link's own "
        "text, the path it leads to, as one line of rules, which names an "
        "attribute only where that text holds a space, a tab or a carriage "
        "return, so, for a link to a path, no line-ending rule reaches the "
        "pinned copies outside it: a Windows clone writes them with CRLF and "
        "reports shape-copy-drift on each one. To give every clone one, "
        f"replace the link with a regular {intended} holding the lines of "
        "the file it leads to that should still apply, then these, one per "
        f"line: {lines}. Adding the same lines to a clone's "
        "`.git/info/attributes` fixes that clone alone")


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


def adopt_makefile_block(spec_path: str, code_path: str) -> str:
    """What `adopt-project.py` appends to the assembly root's Makefile, and
    nothing else does. A scaffolded project's legs are empty, so nothing reads
    across them yet; an ADOPTED project's code leg holds tooling that used to
    read `contracts/` from beside it and now reads it from the other leg
    through the root.

    RENDERED WITH THE PLAN'S MOUNT PATHS (#522). It was one constant naming
    `spec/contracts`, so a project adopted with `--spec-path legs/spec`
    exported a `CONTRACTS_DIR` that does not exist, while `plan`'s own
    follow-up said the Makefile wires `$(CURDIR)/legs/spec/contracts`. The
    block is the adoption's own append, made once by `execute` and digested
    with the copy it is appended to (`_materialize` pins the bytes as
    written), so the per-project text is written here and nowhere by hand.
    A default adoption, `spec` and `code`, gets the bytes it always got
    (`ADOPT_MAKEFILE_BLOCK`).

    Both paths are `execute`'s checked mount paths: canonical, and in
    `checked_value`'s alphabet, which holds no character make reads as
    anything but itself (no `$`, `#`, space or line break).
    """
    return f"""
# --- adopted project: reading ACROSS the legs -------------------------------
# The spec leg owns `contracts/`; the code leg holds the tooling that reads
# them. Mounted here, `{spec_path}/contracts` is one relative path from `{code_path}/`, so
# the root exports it once and the code leg takes it from the environment
# rather than each script guessing at `../`.
CONTRACTS_DIR ?= $(CURDIR)/{spec_path}/contracts
export CONTRACTS_DIR

.PHONY: contracts-dir
contracts-dir:
\t@echo $(CONTRACTS_DIR)
"""


#: The block a DEFAULT adoption appends, the legs at `spec` and `code`:
#: byte for byte the block every adoption appended before #522.
ADOPT_MAKEFILE_BLOCK = adopt_makefile_block("spec", "code")


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


#: What a scaffold whose push was refused prints, and `FAMILY_RULESET_HINT`
#: what `family.py init` prints (#462). ONE EXIT, AND IT WORKS: an operator
#: holding the bypass right re-runs the same command with `--reuse-empty-repo`,
#: whose own pushes are the seed. Brett Heap ruled it on 2026-10-12, "Offer
#: only exits that work": the pull request these offered as a second exit had
#: no base, because the refused push was the first into a repository `gh repo
#: create` had just made without a README, and the seed branch it pushed made
#: that repository non-empty, so the re-run refused it. The re-run was
#: refused for the scaffold's own legs too, until "Re-run reuses empty legs"
#: and "Accept the scaffold's own seed": `--reuse-empty-repo` reuses each of
#: the three repositories while it has zero commits, and a leg whose one
#: commit is the seed this scaffold pushes, which is a leg pushed before a
#: later push was refused (`scaffold-project.py`'s `_reusable_remotes`).
#: Pushing a seed first is what the hint must not invite: it makes a
#: repository the re-run refuses.
#: The PR route is still NAMED, as one that cannot finish, so nobody reaches
#: for it again. `{tracking}` is the run's tracking branch, the branch the
#: refused push targeted (#324), and `{repo}` the repository it was refused
#: at; every caller passes both, after `checked_value` has admitted the
#: tracking branch, so neither is quoted here. `adopt-project.py` prints its
#: own, `ADOPT_RULESET_HINT`: a re-run into its legs is `leg-remote-exists`.
#: A call that leaves a field out fails
#: `tests/test_ruleset_hint_tracking_branch.py`.
RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. ONE exit finishes this scaffold: an operator holding the
bypass right re-runs it, the same command with --reuse-empty-repo added (after
`--` through setup.sh) and a new --work-dir or none. That run's own pushes are
the seed, so push nothing first: it reuses each repository this run left
empty, and a leg whose one commit is the seed this scaffold pushes, and it
refuses a repository that holds anything else. A seed branch and a pull
request cannot finish it: {repo} has no {tracking} for that pull request to
target.

NOTHING has been rolled back. What already exists is listed above; delete it
by hand if you want a clean re-run.
"""

#: `family.py init`'s, for the same reason and with the same two fields
#: (#462). The holder is the one repository `init` makes, so its refused push
#: leaves it empty, and `family.py init --reuse-empty-repo` reuses an empty
#: holder and refuses one with commits. The re-run lands elsewhere: the first
#: run's holder clone is still where it landed, and `init` refuses a holder
#: directory that is not empty (`family-target-exists`).
FAMILY_RULESET_HINT = """
If the organisation applies a ruleset requiring changes to arrive by pull
request, a direct push to the default branch is refused BY DESIGN and must not
be worked around. ONE exit finishes this family: an operator holding the
bypass right re-runs `family.py init`, the same command with
--reuse-empty-repo added and a new --into or --work-dir. That run's own push
is the seed, so push nothing first: it reuses the holder while it is empty,
and refuses it once it has a commit. A seed branch and a pull request cannot
finish it: {repo} has no {tracking} for that pull request to target.

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


def run(args: list[str], cwd: Path | None = None, capture: bool = True,
        env: dict | None = None) -> str:
    check_program(args)
    # UTF-8, whatever the locale: git writes a path as UTF-8, and the locale's
    # codec (ASCII under a POSIX `C` locale, the ANSI code page on Windows)
    # raises `UnicodeDecodeError` out of `subprocess.run` on one it cannot
    # read -- before `CommandFailed` exists, so the person gets a traceback
    # where `REFUSED <step>` and the ruleset hint belong (#217).
    # `env` names variables set OVER the caller's environment for this one
    # command, never instead of it: `scaffold-project.py`'s leg probe turns
    # git's terminal prompt off this way (#542).
    proc = subprocess.run(args, cwd=str(cwd) if cwd else None,
                          capture_output=capture, text=True,
                          encoding="utf-8", errors="replace", check=False,
                          env={**os.environ, **env} if env else None)
    if proc.returncode != 0:
        raise CommandFailed(args, cwd, proc.returncode,
                            (proc.stderr or "") + (proc.stdout or ""))
    return (proc.stdout or "").strip()


# ---------------------------------------------------------------------------
# A branch name, asked of git (#283)
# ---------------------------------------------------------------------------
#
# `checked_value` holds a `--tracking-branch` to an ALPHABET, which keeps an
# option and a shell word off a command line, and the alphabet is wider than
# the names git accepts as a branch: `~`, `a..b`, `x.lock`, `a/`, `/a`, `a//b`,
# `.a` and `a.` are all inside it, and `git init -b` refuses each. Nothing
# asked git, so `--dry-run` printed a plan and, against GitHub, the run
# created all three repositories before the first `git init -b` died.
#
# GIT IS THE AUTHORITY on what a branch name is (`git check-ref-format
# --branch`): it is ASKED, never copied here, so a rule git adds or relaxes is
# ours the day the person upgrades. The question is its own function, beside
# `refuse_bad_leg_paths` in what it is for: a value judged BEFORE a work
# directory or a remote exists, and by `--dry-run` too.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py` for the reason the leg-path
# rule does: that file is a SHAPE COPY every project digest-pins, and one
# function added there would put an `upstream-changed scripts/repo_shape.py`
# row in front of every project for a rule no project's own copy ever asks.

BRANCH_REMEDIATION = (
    "Remediation: pass a branch name git will create, such as `main` or "
    "`release/1.2`: no `..`, no `//`, no `~`, no `/` at either end, no `.` at "
    "the end, no part that starts with `.` or ends in `.lock`, and not "
    "`HEAD`. `git check-ref-format --branch <name>` is the check, and `git "
    "help check-ref-format` lists every rule.")

#: When git could not answer at all, the name was never judged, and a remedy
#: that says "pass another name" sends the person after the wrong thing.
BRANCH_UNCHECKED_REMEDIATION = (
    "Remediation: the name was not judged, because git could not answer the "
    "question for any name. Fix what git's own words above name (a `git` "
    "missing from PATH, a malformed global or system git config), check that "
    "`git check-ref-format --branch main` prints `main`, then run this again.")

#: A name every git creates as a branch. It is asked only after git refused
#: the person's name: a git that refuses this one too could not answer.
BRANCH_CONTROL = "main"

#: What git adds to a branch's last part to lock its ref while it makes it:
#: `refs/heads/<name>.lock`, a file in the same directory.
BRANCH_LOCK_SUFFIX = ".lock"

#: The remedy for a part too long for the disk (#689), whose own words are
#: the same for a flag and for a plan's key, so `adopt-project.py`'s `check`
#: prints it as it stands. `BRANCH_REMEDIATION` would send the person to
#: `git check-ref-format --branch`, which accepts every such name.
BRANCH_LENGTH_REMEDIATION = (
    "Remediation: shorten the part of the name the line above says is too "
    "long. Git keeps a branch as a file under `.git/refs/heads/`, each part "
    "before the last a directory and the last part the file, and it locks "
    f"the branch by first creating `<last part>{BRANCH_LOCK_SUFFIX}` beside "
    "it; most disks keep a file or directory name to 255 bytes, so the last "
    "part may be at most 250 bytes and every other part at most 255. "
    "`git check-ref-format` has no length limit, so it accepts such a name, "
    "and git fails only when it first writes the branch.")


def _ask_git_branch(name: str) -> str:
    """`git check-ref-format --branch <name>`, asked of NO repository and
    from no directory of the person's.

    `--branch` sets up the repository it finds, so asked in the operator's
    working directory it failed for EVERY name inside a repository git
    cannot open (a `.git` file naming a gitdir that is gone, a `.git/config`
    that does not parse) and in a directory removed under the person, where
    a scaffold without the question succeeds; and a repository it did open
    lent `@{-1}` its own reflog (review of a03abcf). An empty directory is
    no repository as `--git-dir` and is a directory that exists as the
    working directory, so the answer is the same wherever the person
    stands, and git, having no repository, has nothing to expand.
    """
    nowhere = tempfile.mkdtemp(prefix="openreposhape-branch-")
    try:
        return run(["git", f"--git-dir={nowhere}", "check-ref-format",
                    "--branch", name], cwd=Path(nowhere))
    finally:
        # Empty: git writes nothing there. A removal that fails (Windows can
        # hold a directory a moment after the process in it ended) must not
        # turn git's answer into a refusal.
        shutil.rmtree(nowhere, ignore_errors=True)


def _branch_verdict(what: str, value) -> tuple[str | None, str]:
    """`(problem, remediation)`: `branch_problem`'s sentence, and the remedy
    that fits it, which is about the NAME when git judged the name, about
    GIT when git could not answer, and about the DISK when a part of the
    name is too long for it (#689, `_branch_length_verdict`)."""
    text = str(value)
    refused = f"{what} is {text!r}, which is not a branch name git will create"
    unchecked = f"{what} is {text!r}, which could not be checked"
    if text.startswith("-"):
        return (f"{refused}: it begins with `-`, which git reads as an option",
                BRANCH_REMEDIATION)
    try:
        answer = _ask_git_branch(text)
    except CommandFailed as exc:
        said = f" ({exc.output})" if exc.output else ""
        # GIT'S REFUSAL, OR GIT'S FAILURE? Git's words are localised, so they
        # are not read: git is asked about a name it always creates, and a
        # git that refuses that too (a malformed global config, say) could
        # not answer for any name, so this one was never judged.
        try:
            _ask_git_branch(BRANCH_CONTROL)
        except (CommandFailed, OSError):
            return (f"{unchecked}: `git check-ref-format --branch` fails for "
                    f"`{BRANCH_CONTROL}` too, so git could not answer{said}",
                    BRANCH_UNCHECKED_REMEDIATION)
        return (f"{refused}: `git check-ref-format --branch` refuses it{said}",
                BRANCH_REMEDIATION)
    except ValueError as exc:
        # The value cannot be an argument at all (a NUL, a lone surrogate):
        # the answer is not git's, and the fault is the value's.
        return (f"{unchecked}: `git check-ref-format --branch` could not be "
                f"run ({exc})", BRANCH_REMEDIATION)
    except OSError as exc:
        # `git` itself is missing, or no empty directory could be made to ask
        # it from: the answer is not git's, and the fault is not the name's.
        return (f"{unchecked}: `git check-ref-format --branch` could not be "
                f"run ({exc})", BRANCH_UNCHECKED_REMEDIATION)
    if answer != text:
        return (f"{refused}: `git check-ref-format --branch` reads it as "
                f"{answer!r}, not as written", BRANCH_REMEDIATION)
    return _branch_length_verdict(what, text)


def _branch_length_verdict(what: str, text: str) -> tuple[str | None, str]:
    """`_branch_verdict`'s last question, asked of a name git accepted
    (#689): can the disk hold the files git makes for it?

    `git check-ref-format` has NO LENGTH LIMIT, so a tracking branch of 251
    to 255 characters, inside `checked_value`'s 255, passed it and passed
    `--dry-run`, and the real run died at the first commit with every remote
    already made: `fatal: cannot lock ref 'HEAD': Unable to create
    '.../refs/heads/aaa....lock': File name too long`. The limit is the
    disk's, not git's, so it is the one question here that is written down
    and not asked of git. Git keeps a branch as a file under `refs/heads/`:
    each part before the last is a directory and the last part is the file,
    which git locks by first creating `<last part>.lock` beside it. So the
    last part may be at most `NAME_MAX - len(".lock")` = 250 bytes and any
    other part `NAME_MAX` = 255 (measured: `<255 a's>/x` and `x/<250 a's>`
    are created, `x/<251 a's>` and `<251 a's>` are not). BYTES, as
    `refuse_unstorable_names` counts them, in the form the operating system
    is given (`os.fsencode`). One refusal, for the first part over its limit.
    """
    parts = text.split("/")
    for number, part in enumerate(parts, 1):
        last = number == len(parts)
        limit = NAME_MAX - (len(BRANCH_LOCK_SUFFIX) if last else 0)
        size = len(os.fsencode(part))
        if size <= limit:
            continue
        # BOTH ENDS, as `refuse_unstorable_names` shows a long name: the
        # tail is what tells two long names apart.
        shown = text if len(text) <= 27 else f"{text[:12]}...{text[-12:]}"
        if len(parts) == 1:
            which = "it"
        elif last:
            which = "its last part"
        else:
            which = f"its part {number}"
        return (f"{what} is {shown!r}, which is not a branch name git will "
                f"create: {which} is {size} bytes long, and may be at most "
                f"{limit}", BRANCH_LENGTH_REMEDIATION)
    return None, BRANCH_REMEDIATION


def branch_problem(what: str, value) -> str | None:
    """None when `git check-ref-format --branch` accepts `value` exactly as
    written and the disk can hold the files git makes for it (#689);
    otherwise the sentence that says what git made of it, or which part is
    too long.

    `what` names the value as the person met it (`--tracking-branch`,
    `tracking_branch`), the way `leg_path_problem` is given its flag. Git is
    asked with no repository in play (`_ask_git_branch`), so the verdict
    does not depend on the directory the person runs the tool from. A name
    git would EXPAND rather than echo (`@{-1}`) is refused too: the tool
    writes the name it was given, so a spelling that means another branch
    is not that branch. A leading `-` is refused without asking, so the value
    is never an option to the question itself; `checked_value` has refused it
    already for the tools that call that first. A git that cannot answer for
    any name says so ("could not be checked"); it does not blame the name.
    """
    return _branch_verdict(what, value)[0]


def refuse_bad_branch(refusal: str, what: str, value) -> None:
    """Raise `Refusal(refusal)` when git would not create `value` as a branch,
    or could not say.

    `refusal` is the caller's own code (`scaffold-bad-tracking-branch`), so
    each tool refuses in its own voice, as `refuse_bad_leg_paths` lets it.
    The remedy is `BRANCH_REMEDIATION` when git judged the name,
    `BRANCH_UNCHECKED_REMEDIATION` when git could not answer at all, and
    `BRANCH_LENGTH_REMEDIATION` when a part of the name is too long for the
    disk (#689).
    """
    problem, remediation = _branch_verdict(what, value)
    if problem:
        raise Refusal(refusal, problem, remediation)


# ---------------------------------------------------------------------------
# A tracking branch a person can read (#715)
# ---------------------------------------------------------------------------
#
# What `bump-leg.py` and `update-shape.py` ask of a manifest's
# `tracking_branch` before they compare it or hand it to `gh` (Brett Heap's
# option A on RV823's SHOULD-1, 2026-10-17): only what no person can see in
# it, never `checked_value`'s alphabet.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py` for the reason the leg-path
# rule and `refuse_bad_branch` do (RV823's round-2 SHOULD-1): that file is a
# SHAPE COPY every root digest-pins, and no root calls this. Both tools
# already import this module.

#: Why a branch name holding such a character is refused, in the words
#: `validate-manifest.py`'s `_branch_finding` and `bootstrap.py`'s `UNSEEN`
#: say it in (#715).
UNSEEN = "a character that does not print or is white space"


def readable_branch(what: str, value) -> str:
    """A BRANCH NAME read out of a manifest, refused only for what no person
    can see in it (#715; Brett Heap's option A on RV823's SHOULD-1).

    The rule is the root's own: `validate-manifest.py`'s `_branch_finding`
    and `bootstrap.py`'s `_argument_fault` refuse a branch holding a
    character for which `str.isprintable()` is false or `str.isspace()` is
    true, so `main` followed by U+00A0, which the reader reads as YAML does
    since #715, is never taken for `main`. Each of those two spells the rule
    itself rather than importing it: a root's validator and bootstrap run
    beside the `repo_shape.py` that root holds, which may be older than they
    are (the skew rule, `validate-manifest.py`'s `_library_takes_remedies`,
    #661), and an older one has no such function. The words are theirs: a
    NUL and a lone surrogate (#280) have their own, and any other such
    character is `UNSEEN`.

    It is NOT `checked_value`'s `SAFE_ARG_RE`. A name in any script, or one
    holding `&`, is a name git creates and the root's own gate passes.
    `bump-leg.py` only compares it and prints it, and `update-shape.py`
    compares it, hands it to `gh pr create --base` as one argument and
    prints it shell-quoted in the line a person pastes (#209). #823's first
    fix round read it through `checked_value`, and refused those names.

    A leading `-` is refused too, as `unsafe-value`: `update-shape.py` hands
    the name to `gh pr create --base`, where it could be read as an option,
    and git creates no branch whose name begins with one, so no root needs
    it. The refusal's words say only the second, which holds for both
    tools.
    """
    text = str(value)
    if text.startswith("-"):
        raise Refusal(
            "unsafe-value",
            f"{what} is {text!r}, which begins with `-`, and git creates no "
            "branch whose name begins with one",
            "Remediation: give it a branch name git can create, such as "
            "`main` or `release/1.2`.")
    char = next((c for c in text if not c.isprintable() or c.isspace()),
                None)
    if char is None:
        return text
    if char == "\x00":
        kind = "a NUL: no argument, file name or ref name can hold one"
    elif "\ud800" <= char <= "\udfff":
        kind = ("a lone surrogate: no UTF-8 file or console can hold it, so "
                "no branch name is spelled with one")
    else:
        kind = (f"{UNSEEN}: a person reading the name cannot tell it from the "
                "name without it")
    raise Refusal(
        "unseen-branch",
        f"{what} is {text!r}, which holds U+{ord(char):04X}, {kind}",
        "Remediation: give it a name with no such character, such as "
        "`main` or `release/1.2`, and run this again.")


# ---------------------------------------------------------------------------
# What a fetch for a branch's answer carries (#686, #898, #1037)
# ---------------------------------------------------------------------------
#
# `family.py bump` fetches a member's `origin` (#686), and `bump-leg.py` a
# leg's (#898), and each then asks one question of what is under
# `refs/remotes/origin/`: does a BRANCH of the remote reach the commit? So
# each fetch carries every branch and, so that `--prune` keeps what they
# keep, the repository's own refspecs that write there. Which of those it
# carries is ONE RULE, asked by both (#1037): #946 and #1027 wrote it in
# `family.py` alone, and the leg's fetch went on carrying every refspec of
# the leg's own that can bring a tag under `origin/`.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py`, which is a SHAPE COPY
# every root digest-pins, and no root's own copy fetches for a pin (see
# "Commit trailers" below for the same argument). This module is in no copy
# list and both tools already import it. Each tool still reads the
# repository's `remote.origin.fetch` its own way, and says why its own
# refspecs ride along.

#: What the fetch always asks of the remote: every branch, into the
#: namespace both tools read branches from, forced as a remote-tracking ref
#: is.
ORIGIN_BRANCHES = "+refs/heads/*:refs/remotes/origin/*"

#: The names `ORIGIN_BRANCHES` gives the branches (#905): a refspec of the
#: repository's own that gives another namespace these very names is not
#: carried (`origin_fetch_refspecs`).
ORIGIN_BRANCH_NAMES = ORIGIN_BRANCHES.partition(":")[2]

#: Where a repository keeps its tags: a refspec of the repository's own
#: whose source can name a ref here is not carried (`can_name_a_tag`,
#: #1009).
TAGS_PREFIX = "refs/tags/"


def can_name_a_tag(source: str) -> bool:
    """Whether a fetch refspec's `source` can name a tag of the remote, so
    that the fetch does not carry the repository's refspec that has it
    (`origin_fetch_refspecs`; #905, RV946's S1, #1009, #1037). Three ways,
    each measured on git 2.43:

    UNDER `refs/tags/`: `+refs/tags/*:refs/remotes/origin/*`, onto the
    branches' names, `+refs/tags/*:refs/remotes/origin/tags/*`, or one tag.

    A PATTERN WHOSE PART BEFORE THE `*` IS A START OF `refs/tags/`, `refs/*`
    or `*`: git matches a pattern against each ref's whole name and never
    completes it, so it takes the tags too, and a mirror into `origin/`
    (`+refs/*:refs/remotes/origin/*`) or into a folder there
    (`+refs/*:refs/remotes/origin/all/*`) brings every tag.

    NO PATTERN, AND NOT UNDER `refs/`: a short name, which git completes,
    trying the name itself, then `refs/<name>`, then `refs/tags/<name>`
    before `refs/heads/<name>`. With a branch and a tag `x`,
    `+x:refs/remotes/origin/x` took the tag; `+heads/main:` took the branch
    `main`, as `refs/heads/main` comes first, and names a tag only where the
    remote has none of the names before it. An exact object id
    (`+<40 hex>:refs/remotes/origin/pinned`) is no pattern and not under
    `refs/` either, and is left out with them: it names a commit and no
    branch, and under `origin/` it answered for one.

    A FULL NAME THAT IS NO PATTERN IS NOT LEFT OUT, though git falls back to
    a tag for it too: `+refs/heads/zz:refs/remotes/origin/zz` took the tag
    `refs/tags/refs/heads/zz` where the remote had no branch `zz`. Leaving
    out every full name would leave out the pull requests and the review
    refs the fetch keeps (#946's U184 rows).
    """
    fixed, star, _ = source.partition("*")
    if source.startswith(TAGS_PREFIX):
        return True
    if star:
        return TAGS_PREFIX.startswith(fixed)
    return not source.startswith("refs/")


def origin_fetch_refspecs(configured: list[str]) -> list[str]:
    """The refspecs a fetch for a branch's answer carries: `ORIGIN_BRANCHES`,
    then each value of the repository's own `remote.origin.fetch` in
    `configured` that no clause below leaves out, forced, in its order and
    without duplicates. `family.py`'s `_origin_fetch_refspecs` asks it of a
    member's mount (#686) and `bump-leg.py`'s `_leg_fetch_refspecs` of a leg
    (#898, #1037), each with `configured` read its own way.

    A NEGATIVE REFSPEC (`^refs/heads/wip`) IS SKIPPED: a narrowing refspec
    never decides reachability, and git applies a configured negative one
    only to a fetch with none on its command line (measured, git 2.43). A
    POSITIVE ONE IS FORCED, whether or not it was written with its `+`: a
    remote-tracking ref only mirrors the remote, and a refspec without it
    would fail the fetch on a ref force-pushed.

    THREE CLAUSES LEAVE A REFSPEC OUT, asked in this order, and the first
    that matches is the one that leaves it out: a destination OUTSIDE
    `refs/remotes/origin/`, A SOURCE THAT CAN NAME A TAG, and THE BRANCHES'
    GLOB.

    A DESTINATION OUTSIDE `refs/remotes/origin/`, a mirror's `+refs/*:refs/*`
    or `+refs/heads/*:refs/heads/*`, is never carried, so no refspec the
    fetch names writes outside it.

    A SOURCE THAT CAN NAME A TAG IS LEFT OUT, wherever under `origin/` it
    writes (#905, #459's U183, RV946's S1, #1009, #1037): a tag is not a
    branch, and under `origin/` it answers for one. `can_name_a_tag` says
    which sources can, three ways: one under `refs/tags/`; a pattern that
    takes the tags too, such as the mirror into `origin/`
    (`+refs/*:refs/remotes/origin/*`) or into a folder there
    (`+refs/*:refs/remotes/origin/all/*`); and one that is no pattern and
    not under `refs/`, a short name or an exact object id. A full name that
    is no pattern is not asked, though git falls back to a tag for it too
    (`can_name_a_tag` says why). Carried, it clashed with the first refspec
    wherever it put a tag on a branch's name: the fetch exited 128 ("Cannot
    fetch both refs/heads/feat and refs/tags/feat to
    refs/remotes/origin/feat"; for the mirror in a folder, a branch
    `all/tags/v1` and a tag `v1`) where `git fetch origin` exits 0, and the
    tool said its fetch had failed and sent the person to the network or
    the credential. Where no name was shared, the tags it put there
    answered for branches: both tools read every ref under
    `refs/remotes/origin/`, so a commit only a tag of the remote reaches was
    pinned, against the rule (#613) that a tag is not a branch (measured on
    git 2.43, each). #946 left out a source under `refs/tags/` and a mirror
    onto the branches' glob, so a mirror in a folder was still carried and
    failed both ways (#1009), and a leg's fetch left out neither until
    #1037. Left out, the fetch works and a tag there answers for nothing:
    the prune drops such a ref, as any ref under `origin/` no refspec of the
    fetch maps, and the repository's own next `git fetch origin` writes it
    back. A refspec that can name no tag and writes a folder of its own
    under `origin/` (pull requests, `+refs/pull/*/head:
    refs/remotes/origin/pr/*`) still rides along.

    THE BRANCHES' GLOB: ONE THAT GIVES ANOTHER NAMESPACE THE BRANCHES' NAMES
    IS LEFT OUT (#905, #459's U183), a refspec whose destination is the
    first refspec's own, `refs/remotes/origin/*`, and whose source is not
    under `refs/heads/`. The tags onto the branches' names and the mirror
    into `origin/` meet it too, and the clause before has left them out
    already; this one alone leaves out a source that can name no tag, such
    as pull requests onto the branches' names
    (`+refs/pull/*/head:refs/remotes/origin/*`). Carried, that clashed with
    the first refspec wherever a pull request and a branch share a name
    ("Cannot fetch both refs/heads/7 and refs/pull/7/head to
    refs/remotes/origin/7") where `git fetch origin` exits 0 (measured, git
    2.43).
    """
    refspecs = [ORIGIN_BRANCHES]
    for spec in (value.strip() for value in configured):
        if spec.startswith("^"):
            continue  # a narrowing refspec never decides reachability (p07)
        spec = spec if spec.startswith("+") else "+" + spec
        source, _, destination = spec[1:].partition(":")
        if not destination.startswith("refs/remotes/origin/"):
            continue
        if can_name_a_tag(source):
            continue  # a tag is not a branch (RV946's S1, #1009, #1037)
        if (destination == ORIGIN_BRANCH_NAMES
                and not source.startswith("refs/heads/")):
            continue  # it gives other refs the branches' names (U183)
        if spec not in refspecs:
            refspecs.append(spec)
    return refspecs


# ---------------------------------------------------------------------------
# What a run asks before its first write: the folders it makes (#609)
# ---------------------------------------------------------------------------
#
# `scaffold-project.py` and `family.py init` each make folders -- the work
# directory, `--local-remote-dir`, a family folder -- and write a working tree
# into one, and their dry runs asked about none of it. With a file standing
# where a folder must go the dry run exited 0 and the real run died in
# `mkdir` (`FileExistsError`) or in the target-exists question itself
# (`NotADirectoryError`), a traceback, exit 1. These are the questions both
# runs now ask, before anything is made, and the `mkdir` the real run makes
# after them. They live here and not in `scripts/repo_shape.py` for the reason
# `refuse_bad_branch` does: that file is a SHAPE COPY.

#: Said by every refusal of a folder asked about before anything is made.
FOLDER_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Move what stands in the way aside, or pass a path where a folder can be "
    "made. There is no --force.")

#: What a folder this user cannot write in is called, by
#: `folder_cannot_be_made` (a folder to make) and `target_in_the_way` (an
#: empty working tree) alike.
CANNOT_WRITE_IN = "is a folder this user cannot write in"

#: How `target_in_the_way` begins its answer for a working tree this user
#: cannot list (#930): `cannot be read: <the system's words>`.
CANNOT_READ = "cannot be read"

#: Said when the real run's own `mkdir` fails, after the question said yes:
#: the run has made folders by then, and no remote.
MKDIR_REMEDIATION = (
    "Remediation: no remote was created. Move what stands in the way aside, "
    "or pass a path where a folder can be made, then run this again. There "
    "is no --force.")


def _not_a_folder(path: Path) -> str | None:
    """Why the thing that stands at `path` is no folder to make one in or
    write into, or None when it is a folder (a link to one included).

    `stat()` INSIDE THE GUARD judges it, as `_digest_from_pin_source` does:
    a link to nothing, a link loop or a path this user cannot search is the
    system's own reason, where `is_dir()` would have said False or raised."""
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        return f"cannot be used as a folder: {exc.strerror or exc}"
    if stat.S_ISDIR(mode):
        return None
    return ("is a file, not a folder" if stat.S_ISREG(mode)
            else "is not a folder")


def folder_in_the_way(path: Path) -> tuple[Path, str] | None:
    """`(where, why)` when `path` cannot be made as a folder, with every
    folder above it, and written in: the one that stands in the way, and
    why. None when it can (#609). It makes nothing.

    The question `Path.mkdir(parents=True, exist_ok=True)` and the first
    write into the folder ask, put without making anything: the nearest of
    `path` and the folders above it that exists is the one that answers. A
    file there, or above it, is named, and so is a folder this user cannot
    write in (the system's own answer, `os.access`, where it has one; it
    says yes for root, and for any folder on Windows, as `mkdir` would). A
    `path` nothing stands at is asked of the folder above it.

    `folder_cannot_be_made` says it as one sentence, naming the folder as
    `shown_source` names a path (#692). `adopt-project.py` asks it of
    `--local-remote-dir` (#798), and names `where` its own way.
    """
    for here in (path, *path.parents):
        if not os.path.lexists(here):
            continue
        why = _not_a_folder(here)
        if why:
            return here, why
        if not os.access(here, os.W_OK | os.X_OK):
            return here, CANNOT_WRITE_IN
        return None
    return None


def folder_cannot_be_made(path: Path) -> str | None:
    """Why `path` cannot be made as a folder, with every folder above it, and
    written in, or None when it can (#609): `folder_in_the_way`'s answer, as
    `<where> <why>`. It makes nothing.

    THE FOLDER IS NAMED AS `shown_source` NAMES A PATH (#692): as it is, and
    as Python's `repr` spells it when a character in it is not printable.
    Printed raw, an ESC in a folder's name reached the terminal and a line
    break began a line of the person's choosing. A printable path is named
    byte for byte, so `why.endswith(CANNOT_WRITE_IN)` still holds."""
    found = folder_in_the_way(path)
    return f"{shown_source(found[0])} {found[1]}" if found else None


def _unwritable_remediation(choose: str) -> str:
    """What a refusal of a folder this user cannot write in says to do, for
    a folder to make and for a working tree alike: give this user write and
    search permission on it, or choose another folder by the flag `choose`.
    """
    return ("Remediation: nothing was created, and `--dry-run` refuses the "
            "same. Give this user write and search permission on that "
            f"folder, or choose another {choose}, and run this again.")


def _unreadable_remediation(choose: str) -> str:
    """What a refusal of a working tree this user cannot list says to do
    (#930), after `_unwritable_remediation`: the run cannot tell whether the
    folder holds a tree, so it names the permission that would let it ask,
    and the flag `choose` that chooses another folder."""
    return ("Remediation: nothing was created, and `--dry-run` refuses the "
            "same. This user cannot list that folder, so whether it holds a "
            "tree cannot be asked: give this user read, write and search "
            f"permission on it, or choose another {choose}, and run this "
            "again.")


def refuse_unmakeable_folder(refusal: str, named: str, path: Path,
                             choose: str | None = None) -> None:
    """Raise `Refusal(refusal)` when `folder_cannot_be_made(path)` says why.

    `refusal` is the caller's own code (`scaffold-folder-cannot-be-made`)
    and `named` how the person met the folder (`--work-dir`, `the family
    folder`), so each tool refuses in its own voice. Asked by the dry run
    and the real run alike, before anything is made.

    A FOLDER THIS USER CANNOT WRITE IN (`CANNOT_WRITE_IN`, the folder itself
    or one above it) is not told to "move what stands in the way aside": it
    is told what `_unwritable_remediation` says, naming the flag `choose`,
    which is `named` unless it is no flag (`the family folder`, met by
    `--into`). Every other answer keeps `FOLDER_REMEDIATION`.

    THE PATH IS NAMED AS `folder_cannot_be_made` NAMES IT (#692)."""
    why = folder_cannot_be_made(path)
    if why:
        raise Refusal(
            refusal, f"{named} {shown_source(path)} cannot be made: {why}",
            _unwritable_remediation(choose or named)
            if why.endswith(CANNOT_WRITE_IN) else FOLDER_REMEDIATION)


def make_folder(refusal: str, named: str, path: Path) -> None:
    """`path.mkdir(parents=True, exist_ok=True)`, and a refusal in the
    system's own words when it fails, never an `OSError` traceback.

    The real run's `mkdir`, after `refuse_unmakeable_folder` has said yes:
    what still fails here (a file made in the meantime, a permission
    `os.access` did not foresee) is the same refusal, before any remote is
    made. The path is named as `refuse_unmakeable_folder` names it (#692)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Refusal(refusal, f"{named} {shown_source(path)} cannot be "
                      f"made: {exc.strerror or exc}",
                      MKDIR_REMEDIATION) from exc


def target_in_the_way(target: Path) -> str | None:
    """Why a working tree cannot be written at `target`, which a run fills
    and never empties, or None when nothing is there or an empty folder is
    (#609). The caller's sentence is `<target> already exists and <why>`.

    A FILE THERE was a `NotADirectoryError` out of `target.iterdir()` in
    the real run, after its dry run exited 0. It is said here, and so is a
    folder that holds anything, which both tools always refused, and one
    this user cannot list.

    AN EMPTY FOLDER THIS USER CANNOT WRITE IN IS SAID TOO (L2-60), last: the
    emptiness check passed it, the dry run exited 0, and the real run made
    its remotes and then died in a `PermissionError` traceback at the first
    file it wrote there. It asks the question `folder_cannot_be_made` asks
    of a folder to make, `os.access(W_OK | X_OK)`: a folder with no `w`
    takes no file and one with no `x` cannot be entered, and a folder that
    holds something is still `is not empty`, whatever its mode."""
    if not os.path.lexists(target):
        return None
    why = _not_a_folder(target)
    if why:
        return why
    try:
        if any(target.iterdir()):
            return "is not empty"
    except OSError as exc:
        return f"{CANNOT_READ}: {exc.strerror or exc}"
    if not os.access(target, os.W_OK | os.X_OK):
        return CANNOT_WRITE_IN
    return None


def target_remediation(why: str, holds: str, choose: str) -> str:
    """The remediation of a `-target-exists` refusal, chosen by what
    `target_in_the_way` said, in the one place both tools ask it (#609).

    `holds` is the tool's own sentence for a tree that HOLDS something, a
    file included: choose an empty folder, there is no --force. It is wrong
    for an EMPTY folder whose only fault is its permissions
    (`CANNOT_WRITE_IN`, L2-60), which is told to be given write and search
    permission for this user, or to be replaced by another folder, named by
    `choose`, the flag the person met it by.

    AND FOR A FOLDER THIS USER CANNOT LIST (`CANNOT_READ`, #930). An empty
    folder at mode 000, 100, 200 or 300 was told "choose an empty
    --work-dir. There is no --force: re-running over a live tree is not a
    scaffold", a cause the run cannot see: it cannot tell an empty folder
    from a live tree there, and the one cause it can see is a permission.
    It is told what `_unreadable_remediation` says, naming `choose`."""
    if why == CANNOT_WRITE_IN:
        return _unwritable_remediation(choose)
    if why.startswith(f"{CANNOT_READ}: "):
        return _unreadable_remediation(choose)
    return holds


# ---------------------------------------------------------------------------
# What a run asks before its first write: whether a repository exists (#609)
# ---------------------------------------------------------------------------

#: The words of gh's answer for a repository GitHub does not have, on stderr
#: with exit 1: `gh repo view` asks GitHub's GraphQL API, which answers
#: `Could not resolve to a Repository with the name '<owner>/<name>'.`, and
#: gh prints it as `GraphQL: <message> (repository)` (gh 2.x; its
#: `FetchRepository` says the same when the API returns no repository).
GH_NOT_FOUND_WORDS = "Could not resolve to a Repository"

#: The same answer from `gh api`, which asks GitHub's REST API: gh prints a
#: REST error as `gh: <message> (HTTP <status>)` on stderr, with exit 1, and
#: GitHub's message for a 404 is `Not Found` (#660).
GH_API_NOT_FOUND_WORDS = "Not Found (HTTP 404)"

#: Said by every refusal of a `gh repo view` that failed otherwise.
GH_UNREADABLE_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Only gh's own answer that a repository does not exist (exit 1, "
    f"`{GH_NOT_FOUND_WORDS}`) lets a run go on as if it were not there; any "
    "other failure says nothing about whether it is. Check `gh auth status` "
    "(`gh auth login` where it names a token that is missing, bad or "
    "expired), or let a rate limit or an outage pass, then run this again.")


def gh_said_not_found(probe, words: str = GH_NOT_FOUND_WORDS) -> bool:
    """Is `probe`, a finished `gh` command, gh's own answer that what it asked
    for does not exist: exit 1 with gh's not-found `words` on stderr (#609)?

    The ONE reading of that answer, `refuse_unless_not_found`'s, with the
    words for each API gh asks: `GH_NOT_FOUND_WORDS` for `gh repo view`, and
    `GH_API_NOT_FOUND_WORDS` for `gh api`, which `organisation_plan` asks
    (#660). Every other failure, a bad login, a rate limit or an outage, is
    not this answer, whatever else it says.
    """
    return probe.returncode == 1 and words in (probe.stderr or "")


def refuse_unless_not_found(repository: str, probe) -> None:
    """A `gh repo view <repository>` that FAILED is gh's answer that the
    repository does not exist, and this returns; any other failure is
    refused as `remote-unreadable` (#609).

    ANY FAILURE USED TO MEAN "ABSENT". With a bad token (`HTTP 401: Bad
    credentials`), a rate limit or no network, both dry runs exited 0 and
    the real runs went on to `gh repo create`: the scaffold failed there,
    and `init` had made its family folder first. A repository that DOES
    exist, read through a passing failure, would have had the scaffold
    create and push both legs before its root met `gh repo create`. So only
    exit 1 with `GH_NOT_FOUND_WORDS` on stderr means absent; the refusal
    quotes the command, its exit and the first line gh said (stdout's when
    stderr is empty), as Python spells it when it is not printable.

    `probe` is the finished `subprocess.CompletedProcess` of the command;
    one that exited 0 is not asked about here.
    """
    if gh_said_not_found(probe):
        return
    lines = [line.strip()
             for line in (probe.stderr or probe.stdout or "").splitlines()
             if line.strip()]
    said = lines[0] if lines else ""
    if not said.isprintable():
        said = repr(said)
    command = " ".join(str(word) for word in probe.args)
    raise Refusal(
        "remote-unreadable",
        f"whether {repository} already exists on GitHub cannot be told: "
        f"`{command}` exited {probe.returncode}"
        + (f": {said}" if said else ""),
        GH_UNREADABLE_REMEDIATION)


# ---------------------------------------------------------------------------
# What the Free-plan secrets hint goes by (#602, #660)
# ---------------------------------------------------------------------------
#
# The `validate` workflow that reads SHAPE_LEGS_APP_ID and
# SHAPE_LEGS_APP_PRIVATE_KEY runs in ONE repository, the assembly root or the
# family holder, and on the GitHub Free plan an organisation secret is
# delivered only to a public repository. So `FREE_PLAN_HINT` holds when that
# repository is private or internal AND its organisation is on Free: two
# questions for GitHub, and either can go unanswered. AN UNANSWERED ONE IS
# SAID, NEVER GUESSED. Guessing private gives a public repository a false
# hint; guessing public, or a paid plan, hides a true one with nothing said.
# `free_plan_secret_hint` in `repo_shape.py` answers None alike for a paid
# plan and for one it could not read, as its docstring chooses, and that file
# is a shape copy every project digest-pins; so the three creating tools ask
# the plan here instead, and `FREE_PLAN_HINT`'s words are not changed.

#: What a creating tool prints where GitHub would not say what visibility the
#: repository its `validate` workflow runs in has (#602, from
#: `adopt-project.py`, whose words these are; the scaffold's reused root and
#: `family.py init`'s reused holder since #660): the question it could not
#: answer, what the Free-plan hint would then say, and how to answer it.
#: `{root}` is that repository.
ROOT_VISIBILITY_UNREAD = (
    "NOTE this run could not read {root}'s visibility from GitHub, so it "
    "cannot say whether the Free-plan secrets hint applies. It applies when "
    "{root} is private or internal and its organisation is on the GitHub Free "
    "plan: organisation secrets are then not delivered to it, so org-level "
    "SHAPE_LEGS_APP_ID / SHAPE_LEGS_APP_PRIVATE_KEY resolve to EMPTY in its "
    "`validate` workflow and must be set as REPOSITORY secrets on {root} "
    "instead. `gh repo view {root} --json visibility` says which it is.")

#: The same where the repository is private and GitHub would not name its
#: organisation's plan (#660); an internal one is told
#: `FREE_PLAN_UNREAD_INTERNAL` (#913). `{visibility}` is the repository's.
#: The last sentence rests on GitHub's REST page for `GET /orgs/{org}`: an
#: organisation's full details are shown to its owners.
FREE_PLAN_UNREAD = (
    "NOTE this run could not read {org}'s plan from GitHub, so it cannot say "
    "whether the Free-plan secrets hint applies. {root} is {visibility}, so "
    "it applies when {org} is on the GitHub Free plan: organisation secrets "
    "are then not delivered to {root}, so org-level SHAPE_LEGS_APP_ID / "
    "SHAPE_LEGS_APP_PRIVATE_KEY resolve to EMPTY in its `validate` workflow "
    "and must be set as REPOSITORY secrets on {root} instead. `gh api "
    "orgs/{org} --jq .plan.name`, run with an owner's login, says which plan "
    "it is on.")

#: `FREE_PLAN_UNREAD` for an INTERNAL repository (#913, L2-93). GitHub gives
#: internal visibility only to a repository of an organisation an enterprise
#: account owns ("About repositories", GitHub's documentation), and such an
#: organisation is not on the Free plan, so `FREE_PLAN_UNREAD`'s "it applies
#: when {org} is on the GitHub Free plan" named a condition that cannot hold
#: of it. The NOTE is printed where it always was; only its words say that
#: the plan is not what the hint hangs on.
FREE_PLAN_UNREAD_INTERNAL = (
    "NOTE this run could not read {org}'s plan from GitHub, but the "
    "Free-plan secrets hint does not hang on it: {root} is internal, which "
    "GitHub gives only to a repository of an organisation an enterprise "
    "account owns, and that organisation is not on the GitHub Free plan. "
    "Org-level SHAPE_LEGS_APP_ID / SHAPE_LEGS_APP_PRIVATE_KEY reach {root}'s "
    "`validate` workflow where each secret's repository access includes "
    "{root}.")

#: What a creating tool's plan says under its `gh repo create` row (#913,
#: L2-61). Only gh's not-found answer reads as absent (#609), and GitHub
#: gives that answer for a private repository the token cannot see too, so
#: the two cannot be told apart from gh's answer: the plan says that "not
#: found" is what this token can see, and what the real run then meets. The
#: two lines follow a row that ends "gh does not find" and its object.
NOT_FOUND_WITH_THIS_TOKEN = (
    "with this token: a private repository it cannot see is not found",
    "either, and `gh repo create` then fails for it")

#: What `repository_visibility_answer` answers where gh says GitHub has no
#: such repository (#913): exit 1 with `GH_NOT_FOUND_WORDS` on stderr, the
#: reading `refuse_unless_not_found` gives `gh repo view` (#609). GitHub
#: gives a private repository this token cannot see the same answer
#: (`NOT_FOUND_WITH_THIS_TOKEN`).
REPOSITORY_NOT_FOUND = "not-found"


def visibility_in(answer: str) -> str | None:
    """The visibility a `gh repo view --json visibility` answer names, one of
    `VISIBILITY_CHOICES` in any case, or None for anything else: not JSON,
    not an object, no field, or a word that is not one of GitHub's three.
    `repository_visibility` reads its answer with it, and `adopt-project.py`'s
    `_root_visibility` reads its own (#660)."""
    try:
        value = json.loads(answer)
    except ValueError:
        return None
    value = value.get("visibility") if isinstance(value, dict) else None
    seen = value.lower() if isinstance(value, str) else None
    return seen if seen in VISIBILITY_CHOICES else None


def repository_visibility_answer(repository: str) -> str | None:
    """`repository`'s visibility on GitHub, one of `VISIBILITY_CHOICES`;
    `REPOSITORY_NOT_FOUND` where gh's own answer is that this token finds no
    such repository (`gh_said_not_found`); or None when it cannot be read:
    `gh repo view` failed otherwise (a rate limit, a token an organisation's
    SAML enforcement refuses, an outage such as an `HTTP 502`) or answered
    anything `visibility_in` does not read as one of the three.

    THE ONE READER of the scaffold and `family.py` (#660), on the model of
    `adopt-project.py`'s `_root_visibility` (#602); `repository_visibility`
    is this reading with not-found taken as unread. NOT-FOUND IS TOLD APART
    (#913) for the scaffold's root under `--reuse-empty-repo`, whose
    visibility the legs it creates inherit: a root not there yet is the
    ordinary run, which creates it, and a root whose read failed is one
    whose visibility nobody knows, which the scaffold says before its plan.
    The command is run here rather than by `run`, as `organisation_plan`'s
    is, because gh's answer is read from its own stderr.

    A `gh` that cannot be started is NOT answered here: its `OSError`
    reaches the caller, because the scaffold refuses a missing `gh` as
    `gh-not-found` before it creates anything (#537), and `family.py`, which
    asks only after `gh` has made or edited the holder, takes it as unread.
    Never asked of a `--local-remote-dir` repository, which has no
    visibility.
    """
    probe = subprocess.run(
        ["gh", "repo", "view", repository, "--json", "visibility"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False)
    if probe.returncode != 0:
        return REPOSITORY_NOT_FOUND if gh_said_not_found(probe) else None
    return visibility_in(probe.stdout or "")


def repository_visibility(repository: str) -> str | None:
    """`repository`'s visibility on GitHub, one of `VISIBILITY_CHOICES`, or
    None when it cannot be read: `repository_visibility_answer`, with gh's
    not-found answer taken as unread too. Its callers ask it of a repository
    they have just found, or made, so not finding it is not "absent": it is
    a repository the token cannot see, or a read that went wrong (#660).
    A `gh` that cannot be started raises, as there.
    """
    seen = repository_visibility_answer(repository)
    return None if seen == REPOSITORY_NOT_FOUND else seen


def organisation_plan(org: str) -> str | None:
    """`"free"` when GitHub names `org`'s plan `free` (in any case, around any
    whitespace), `"other"` when it names another, `"not-an-organisation"`
    when gh says there is no organisation `org`, and None when GitHub names
    no plan (#660): `gh api orgs/<org>` failed otherwise (an organisation
    the token cannot see, a rate limit, an outage) or could not be started,
    or answered with no plan name, which is what `--jq .plan.name` prints
    where the field is absent from what the token was shown.

    NO ORGANISATION IS NOT AN UNREAD PLAN. GitHub answers `GET /orgs/<login>`
    with 404 where `<login>` is not an organisation, which is what a
    repository owned by a personal account gives, and a personal account
    has no organisation secrets for the hint to be about. gh's not-found
    answer is read by `gh_said_not_found`, the reading
    `refuse_unless_not_found` gives `gh repo view` (#609), so every other
    failure stays unread. The command is run here rather than by `run`,
    because that reading is of the finished command's own stderr, which
    `run` folds into one text with stdout.

    `free_plan_secret_hint` reads the same field and answers None for every
    case but `free`, as for a paid plan, so a private root whose plan could
    not be read was told nothing, the silent failure its own docstring says
    it exists for. Each creating tool asks this instead, through
    `free_plan_secrets_note`, and names an unread plan.
    """
    try:
        probe = subprocess.run(
            ["gh", "api", f"orgs/{org}", "--jq", ".plan.name"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
    except OSError:
        return None
    if gh_said_not_found(probe, GH_API_NOT_FOUND_WORDS):
        return "not-an-organisation"
    if probe.returncode != 0:
        return None
    name = (probe.stdout or "").strip().lower()
    if not name:
        return None
    return "free" if name == "free" else "other"


def free_plan_secrets_note(org: str, root: str,
                           visibility: str | None) -> str | None:
    """What a creating tool prints about the Free-plan secrets of `root`, the
    repository its `validate` workflow runs in, at `visibility` (None: GitHub
    did not say), or None where nothing applies (#602, #660).

    - Unread: `ROOT_VISIBILITY_UNREAD`, and the plan is not asked: that NOTE
      names both conditions, so it holds whatever the plan is.
    - Public: None. An organisation secret reaches it on every plan.
    - Private or internal: the plan is asked. On `free` it is `FREE_PLAN_HINT`,
      with `root` alone as the repository that is private, as the scaffold and
      adopt name it since #602 and `family.py init` since #660, and for an
      internal root saying it is internal, which the hint treats as private
      (#994); where the plan is unread, `FREE_PLAN_UNREAD`, or for an internal
      root `FREE_PLAN_UNREAD_INTERNAL`, which says the plan cannot be what
      makes the hint apply to it (#913); on any other plan, and where the owner
      is not an organisation, None.

    The scaffold passes the run's visibility for a root it created and
    GitHub's for one it reused, adopt GitHub's for the root it adopted, and
    `family.py` the run's for a holder it created and GitHub's for one it
    reused.
    """
    if visibility is None:
        return ROOT_VISIBILITY_UNREAD.format(root=root)
    if visibility not in ("private", "internal"):
        return None
    plan = organisation_plan(org)
    if plan == "free":
        # GitHub gives internal visibility only to an organisation an
        # enterprise account owns, which is not on Free (see
        # `FREE_PLAN_UNREAD_INTERNAL`), so an internal root on a plan read as
        # `free` should not arise. If it does, the hint holds of it as of a
        # private one (an organisation secret is delivered only to a public
        # repository), but `FREE_PLAN_HINT` reads "{what} private, so ...",
        # so `what` says the root is internal rather than calling it private
        # (#994); `repo_shape.py`'s pinned text is not touched.
        what = (f"{root} is internal, which this hint treats as"
                if visibility == "internal" else f"{root} is")
        return FREE_PLAN_HINT.format(org=org, repo=root, what=what)
    if plan is None and visibility == "internal":
        return FREE_PLAN_UNREAD_INTERNAL.format(org=org, root=root)
    if plan is None:
        return FREE_PLAN_UNREAD.format(org=org, root=root,
                                       visibility=visibility)
    return None


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

    THE FORCED ADD THE SCAFFOLD, `family.py` (`init`, and every `add`, `bump`
    and `remove` commit), `adopt-project.py`'S SEEDED LEG AND
    `update-shape.py` SHARE; the seeded leg reaches it through
    `git_init_commit`, as `stage_written` says. A file the shape
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

    A CALLER THAT WRITES INTO A CHECKOUT SOMEBODY WORKS IN CALLS THIS ALONE,
    NEVER AFTER A SWEEP. `stage_written` runs `git add -A` before it, and is
    for a caller that stages a tree this tool has just made, where every path
    is its own. In a checkout somebody may be working in, `-A` would stage
    their work beside the shape's, so such a caller names its paths and
    forces those and nothing else, and this function never sweeps: a caller
    that wants a sweep makes it first, as `stage_written` does. The rule
    began with `update-shape.py apply --add` (#202), whose plain `git add --`
    died on an ignored addition after the copies, the pin and the branch were
    already written. `family.py`'s commits took it up (#242), each in a
    holder somebody may be working in: `add` stages the gitlink,
    `.gitmodules` and `family.yaml`; `bump` the gitlink and `family.yaml`;
    `remove` `.gitmodules` and `family.yaml`, the gitlink's deletion already
    staged by its `git rm`. The next caller of that kind is bound by the same
    rule without being named here. Empty, this runs nothing.
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

    A CALLER THAT HAS JUST MADE THE TREE IT STAGES CALLS THIS.
    `git_init_commit` does (the scaffold's two legs and `adopt-project.py`'s
    seeded leg), and so do the scaffold's assembly root and `family.py init`'s
    holder. A caller that writes into a checkout somebody works in does not:
    `-A` would stage their work beside the shape's, so it calls the forced
    half, `force_stage`, on its own (#202, #242).
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


def argv_text(value: str) -> str:
    """`value` as the TEXT it was typed as, with each byte the locale could not
    read put back (#322).

    A command-line argument reaches Python as bytes decoded with the locale's
    codec. Under a POSIX `C` locale with UTF-8 mode off that is ASCII, and the
    two bytes of `é` arrive as the lone surrogates `\\udcc3\\udca9`
    (`surrogateescape` keeps a byte it cannot read as U+DC80..U+DCFF, so that
    `os.fsencode` can give it back). They are not text: `trailer_line` refused
    such a trailer as "not a trailer", and the commit helpers, handed one
    directly, wrote each as `?`.

    `os.fsencode` gives the bytes back and, if they are UTF-8, they are the
    text: `Jos\\udcc3\\udca9` becomes `José`, the value a UTF-8 locale hands
    over, so a trailer is one string whatever the locale. A value with no
    escaped byte, which is every ASCII trailer and everything a UTF-8 locale
    read, is returned as it is. One whose bytes are NOT UTF-8 (a Latin-1
    terminal's `\\xe9`) is returned as it is too, still holding its
    surrogate: it is no text, and `trailer_line` and `commit_trailers` refuse
    it by name rather than guess which code page was meant. Recovered BEFORE
    the grammar is asked, so bytes that spell a line separator or an
    invisible character (`\\xc2\\x85` is U+0085) are judged as that
    character.
    """
    if not any(_is_escaped_byte(char) for char in value):
        return value
    try:
        return os.fsencode(value).decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def utf8_writable(value: str) -> bool:
    """Can `value` be written into a commit message exactly, as UTF-8?

    False for a lone surrogate: a byte no character stands for, which an
    encoder would drop (`errors="replace"` writes `?`) or raise on.
    """
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def not_utf8_problem(value: str) -> str:
    """The sentence a refusal says about a trailer `utf8_writable` rejected.

    NAMED BY THE BYTES IT STANDS FOR where it can be, `b'Jos\\xe9'`, because
    the lone surrogate it holds prints differently on every stdout and an
    operator needs to see which byte it is.
    """
    try:
        named = repr(os.fsencode(value))
    except UnicodeEncodeError:
        named = ascii(value)
    return (f"the trailer {named} is not UTF-8 text: one of its bytes "
            "belongs to no character, and a commit message cannot carry it "
            "as typed. This tool refuses rather than replace it with a `?`. "
            "Type the trailer in UTF-8; a terminal, script or editor set to "
            "another code page (Latin-1, cp1252) wrote that byte.")


def argv_spelling(text: str) -> str:
    """`text`, spelled so a child process receives its UTF-8 bytes (#322).

    What a child gets for an argument is the BYTES `subprocess` encodes it
    to, and on POSIX that is `os.fsencode`: the locale's codec, which under a
    `C` locale with UTF-8 mode off is ASCII and refuses `é` outright
    (`UnicodeEncodeError`), and under a Latin-1 locale is one byte, which is
    not what a UTF-8 commit message holds. A commit message is UTF-8, so the
    argument is `os.fsdecode` of the text's UTF-8 bytes: the one string
    `os.fsencode` turns back into exactly those bytes under any locale, and
    the text itself under a UTF-8 one. Windows passes text to a child as
    UTF-16 and git converts it, and ASCII is the same in every codec this
    runs under, so both are returned as they are: no argument a commit was
    made with before changes.
    """
    if os.name == "nt" or text.isascii():
        return text
    return os.fsdecode(text.encode("utf-8"))


def trailer_line(text: str) -> str:
    """One `--trailer` value, validated where argparse can refuse it.

    ARGPARSE'S OWN ERROR PATH RATHER THAN A `Refusal`, and deliberately: a
    malformed trailer is a malformed COMMAND LINE, which is the one class of
    mistake argparse already reports with the usage line beside it. Both
    exits are 2, so a caller scripting on the exit code sees no difference;
    what it buys is that `--trailer 'Lane xfactory-1'` is refused before the
    tool has read a repository, copied a byte or checked out a branch.

    THE VALUE RETURNED IS THE TEXT (#322): see `argv_text`. `Co-Authored-By:
    José` typed under a `C` locale is the same trailer, the same string and
    the same bytes in the commit as under a UTF-8 one. One whose bytes are
    not UTF-8 is refused here, by name, before a repository is read.
    """
    value = argv_text(str(text))
    if not is_trailer(value):
        if not utf8_writable(value):
            raise argparse.ArgumentTypeError(not_utf8_problem(value))
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
#: all. `argv_text` has already turned the ones that spell UTF-8 back into
#: the characters they were typed as, so what is left is a byte that is no
#: character: git would be handed it straight back, or, on the pre-2.32 path
#: that appends trailers to the MESSAGE, the commit helpers' `errors=
#: "replace"` would write it as `?`. A SPACE is `Zs` and is not in this list.
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

    A TRAILER IS CARRIED AS TYPED OR REFUSED, NEVER REPLACED (#322). The
    commit helpers write the message on stdin as UTF-8 with `errors=
    "replace"` (#230), which writes a character UTF-8 cannot carry as `?` and
    says nothing: under a `C` locale with UTF-8 mode off `Co-Authored-By:
    José` reached the fallback below as `Jos\\udcc3\\udca9` and was committed
    as `Jos??`, the commit's record of who produced it altered. So each line
    is `argv_text`ed first, which makes that `José`, and one that still holds
    a byte that is no character is a `Refusal` naming the trailer, raised
    BEFORE a commit is made: `bump-leg.py` and `family.py` call this ahead of
    their stage, and `update-shape.py apply` rolls its branch and copies
    back. The `--trailer` arguments are `argv_spelling`s of the text, so the
    bytes git is handed are the UTF-8 ones under any locale.
    """
    lines = [argv_text(str(line)) for line in (trailers or ())]
    if not lines:
        return message, []
    for line in lines:
        if not utf8_writable(line):
            raise Refusal(
                "trailer-not-utf8", not_utf8_problem(line),
                "Remediation: pass the trailer as UTF-8 text, or leave it "
                "off; nothing was committed.")
    if git_takes_trailer_option():
        return message, [part for line in lines
                         for part in ("--trailer", argv_spelling(line))]
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
    writer meant. `update-shape.py` hands over `shlex.quote` for the same
    reason, now that every other argument on its NEXT line goes through it
    (#325). With none, the trailer is spelled inside double quotes — which is
    how `AGENTS.md`, `docs/cli.md` and the issue all write it — and no caller
    in this repository asks for that spelling any more.

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


# ---------------------------------------------------------------------------
# The two lines a pin is moved by (#323)
# ---------------------------------------------------------------------------
#
# `update-shape.py` moves `commit:` and `digests.tree_sha256:` in
# `contracts/shape-pin.yaml` and in a manifest's `shape:` block, and
# `bump-leg.py` moves them in a leg's `contracts/<role>-pin.yaml`: three
# rewriters, all of them LINE rewrites, because each file opens with
# paragraphs a YAML round trip would delete. What it is to rewrite one of
# those lines, and what it is to know the rewrite is right, is one answer
# here rather than three that agree until they do not.
#
# THE LINE KEEPS EVERYTHING BUT ITS VALUE. Each rewriter used to find its
# line by a fixed spelling (two spaces in front of `tree_sha256:`) and write
# it back as a fixed line, so a `digests:` child indented four spaces — which
# the reader and both validators accept — was refused as hand-edited, and a
# trailing `# comment` on either line was dropped without a word (#323, the
# same assumption #208 removed from the manifest's indentation).
#
# AND THE RESULT IS READ BACK. A line rewrite cannot carry every layout the
# reader accepts — a value on the line below its key is the one that comes up
# — so what it returns is read with `parse_yaml` and must give the target.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py`, which is a SHAPE COPY:
# anything added there would put an `upstream-changed scripts/repo_shape.py`
# row in front of every project in the estate for a helper none of them calls
# (see "Commit trailers" above for the same argument). This module is in no
# copy list and both tools already import it. `_strip_comment` is imported
# from there by its private name on purpose: it IS the reader's definition of
# where a comment starts, quotes included, and a second one is how a rewrite
# and a reader come to disagree about which part of a line is the value.


def is_nested_key(line: str, key: str) -> bool:
    """Is `line` an INDENTED `<key>:` line, a child of some block, at any
    depth? How a pin's `digests.tree_sha256` is found (#323): by the key, not
    by a fixed count of spaces in front of it. Spaces only: the reader refuses
    a tab as indentation."""
    return line.startswith(" ") and line.lstrip(" ").startswith(key + ":")


def with_scalar(line: str, key: str, value: str) -> str:
    """`line`, a `<indent><key>: <old value>[  # comment]` line, with only the
    old value replaced by `value` (double-quoted, as the scaffold writes it).

    The indentation, the key, the spacing between the colon and the value
    and a trailing comment, with the spacing in front of it, are the line's
    own. A line with no comment loses its trailing whitespace, as it always
    has. Callers FIND the line by `key`; one that is not that key's raises
    `ValueError`, which no caller reaches.
    """
    body = _strip_comment(line)
    indent = line[:len(line) - len(line.lstrip())]
    key_part = body[len(indent):]
    if not key_part.startswith(key + ":"):
        raise ValueError(f"not a `{key}:` line: {line!r}")
    after = key_part[len(key) + 1:]
    spacing = after[:len(after) - len(after.lstrip())] or " "
    tail = line[len(body):]
    return (f"{indent}{key}:{spacing}{double_quoted(value)}"
            f"{tail if tail.strip() else ''}")


def pin_values_in(text: str, within: tuple = ()) -> tuple[str, str]:
    """`commit` and `digests.tree_sha256` as the validators read them out of
    `text`, beneath the keys `within` (`("shape",)` for a manifest's block),
    or a `ValueError` saying why they cannot be read."""
    where = "".join(f"{name}." for name in within)
    try:
        node = parse_yaml(text)
    except YamlError as exc:
        raise ValueError(str(exc)) from exc
    for name in within:
        node = node.get(name) if isinstance(node, dict) else None
    commit = node.get("commit") if isinstance(node, dict) else None
    digests = node.get("digests") if isinstance(node, dict) else None
    tree = digests.get("tree_sha256") if isinstance(digests, dict) else None
    if commit is None or tree is None:
        raise ValueError(f"no `{where}commit` and `{where}digests."
                         "tree_sha256` where the validator reads them")
    return str(commit), str(tree)


def rewrite_fault(before: str, after: str, commit: str, tree: str,
                  within: tuple = ()) -> str | None:
    """Why `after` does not read back to `commit` and `tree`, or None.

    THE FAULT IS THIS TOOL'S ONLY WHEN IT IS: None also when `before` did not
    read either. A file that read correctly before the rewrite and does not
    after it was broken by the rewrite, and the caller's refusal says so. One
    that did not read before — unparsable, or no pin where the validator
    looks — was red before the command ran: that is left to the validators,
    which name the project's own line, and blaming this tool for it would be
    the same wrong answer turned around (#208).
    """
    try:
        found = pin_values_in(after, within)
        if found == (commit, tree):
            return None
        why = (f"it would read `commit: {found[0]}` and "
               f"`tree_sha256: {found[1]}`")
    except ValueError as exc:
        why = f"the reader would refuse it: {exc}"
    try:
        pin_values_in(before, within)
    except ValueError:
        return None
    return why


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

    `eol_block` is the copies named in the block appended to the source's own
    `.gitattributes` (#471), each where git tracks it and, where that
    differs, by its pinned path too (#807), and empty when none was: no source file of that name, one the plan did not
    keep in the root, or one that is a symlink.
    That file is the source's, so it is in neither list above.
    """

    def __init__(self) -> None:
        self.written: list[str] = []
        self.collisions: list[tuple[str, str]] = []
        self.shape_files: list[str] = []
        self.eol_block: list[str] = []

    def follow_ups(self) -> list[str]:
        beside = dict(self.collisions)
        return [collision_follow_up(intended, actual, beside)
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

    With a `collision_dir`, a `.gitattributes` the target already held gets
    the shape's line-ending block appended (#471, `_append_eol_block`).
    """
    result = _materialize(
        shape_root, shape_root / "templates" / "assembly-root", target, values,
        templated=TEMPLATED, verbatim=COPIED_VERBATIM,
        from_shape=COPIED_FROM_SHAPE, executable=EXECUTABLE,
        collision_dir=collision_dir, append=append, neutral_pins=neutral_pins,
        spell=spell)
    if collision_dir is not None:
        _append_eol_block(target, result, collision_dir)
    return result


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
    scaffold passes its `--pin` products (#197), and adopt the products
    its plan declares a pin on, whose files `execute` writes since #273.
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


# ---------------------------------------------------------------------------
# A declared neutral-product pin (#273)
# ---------------------------------------------------------------------------
#
# `scaffold-project.py --pin <product>@<40 hex>` read the argument, the digest
# and the collisions with functions of its own, and `adopt-project.py plan
# --pin` took a NAME only and wrote no pin file, so the adopted root's own
# `validate-pins.py` refused it as `neutral-pin-missing` on its first run.
# Brett Heap ruled on 2026-10-12 that adopt takes the argument scaffold takes
# and writes the file scaffold writes, so the reading moved here, beside the
# materializer that writes the file (`neutral_pin_path`), and both tools
# import it: one argument, one digest, one set of refusals, in one set of
# words. `scaffold-project.py` imports each under the name it always called it
# by, and its messages are these, unchanged.

#: The pin argument: `openGlass@<40 hex>`, optionally organisation-qualified.
PIN_ARG_RE = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)?)@(?P<commit>[0-9a-fA-F]{40})$")


def parse_pin(raw: str, owner: str = NEUTRAL_PRODUCT_OWNER) -> tuple[str, str, str]:
    """`openGlass@<sha>` -> (product, `<owner>/openGlass`, commit).

    THE COMMIT IS 40 HEX OR IT IS NOT A PIN. An abbreviated oid, a branch name
    or a tag cannot pass here for the same reason `contracts/<leg>-pin.yaml`
    refuses them: a tag can be moved and a commit cannot.

    AN UNQUALIFIED NAME RESOLVES UNDER `owner` (opensoft, unless `--pin-owner`
    said otherwise) — NEVER under the pinning project's own `--org`. Domain
    repositories never author a neutral product; they only pin the opensoft
    original, so `--org MedxSoft --pin openGlass@<sha>` must not go looking
    for `MedxSoft/openGlass`, which does not exist and was never the claim.

    A NAME WITH NO `@<commit>` IS REFUSED HERE TOO, by both tools: since #273
    `adopt-project.py plan --pin` writes the pin file as the scaffold does,
    and a name alone is a declaration with no referent.
    """
    match = PIN_ARG_RE.match(raw.strip())
    if not match:
        raise Refusal(
            "pin-malformed",
            f"--pin {raw!r} is not `[owner/]<openProduct>@<40 hex commit>`",
            "Remediation: pass the full 40-character commit, e.g. "
            "--pin openGlass@0123456789abcdef0123456789abcdef01234567 "
            f"(resolved under {NEUTRAL_PRODUCT_OWNER}/openGlass by default), "
            "or name the owner explicitly with --pin MedxSoft/openGlass@<sha> "
            "or --pin-owner MedxSoft. A tag or an abbreviated oid is refused: "
            "a tag can be moved.",
        )
    name = match.group("name")
    product = name.rsplit("/", 1)[-1]
    repository = name if "/" in name else f"{owner}/{product}"
    return product, repository, match.group("commit").lower()


def pin_digest_from_source(source: Path, commit: str, repository: str) -> str:
    """The `sorted-ls-tree-r-v1` digest, read from a clone on this machine.

    A SOURCE THAT CANNOT ANSWER IS `pin-source-unreadable`, HOWEVER IT FAILS
    (#339): exit 2, with the remediation below, before anything is created,
    `--dry-run` or not. `tree_digest` runs `git` IN the source, and a
    directory that is not a clone is git's own failure, a `Refusal`. A path
    `subprocess.run` cannot enter at all never reaches git: it is an
    `OSError` raised out of `cwd=`, `FileNotFoundError` for a source that is
    not there, `NotADirectoryError` for a file, `PermissionError` for one
    under a parent this user cannot enter, and nothing caught it, so
    `--pin-source <missing>` ended both tools in a traceback, exit 1, where
    a directory that is not a clone was this refusal.

    THE REASON IS `validate-pins.py`'S (#295, #312), and the sentence is the
    same one that file prints for the same source: "no such directory", "it
    is a file, not a directory", and for any other `OSError` the system's own
    reason (`strerror`: "Permission denied", "File name too long"). `stat()`
    INSIDE THE GUARD judges the path, and not `exists()`/`is_dir()`: before
    3.14 those swallow only a missing path and raise every other `OSError`,
    so a source under a parent this user cannot enter was still a traceback,
    and on 3.14 "no such directory" for a directory that is there. A source
    `stat()` can read but `cwd=` cannot enter (a directory with no search
    bit) fails in `tree_digest`, which the same guard answers.

    THE PATH IS NAMED AS TYPED, UNLESS IT IS NOT PRINTABLE (`shown_source`),
    and then as Python's `repr` spells it, wherever the refusal names it --
    git's own reason names the directory it ran in. Printed raw, an ESC in
    it reached the terminal, and a line break or a carriage return began a
    line of the person's choosing, a forged `REFUSED` among them; the
    traceback it replaced had shown the path as a `repr`. A printable path
    is named byte for byte as it always was.
    """
    try:
        return _digest_from_pin_source(source, commit)
    except (Refusal, OSError) as exc:
        if isinstance(exc, Refusal) and exc.code == PIN_SOURCE_NOT_A_CLONE:
            raise  # its own refusal, which names the top level (#800)
        why = (exc.detail if isinstance(exc, Refusal)
               else exc.strerror or str(exc))
        named = shown_source(source)
        raise Refusal(
            "pin-source-unreadable",
            f"{named} could not answer for {repository} @ {commit}: "
            f"{why.replace(str(source), named)}",
            "Remediation: point --pin-source at a clone of that repository "
            "that HAS the pinned commit (`git fetch --all` first), or drop "
            "--pin-source and let `gh api` read the forge.",
        ) from exc


def scaffold_link_remedies(chain) -> dict[str, str]:
    """What would let each chain link's own tree be read, in the scaffold's
    own sources: `{pin_product_key(link): the words}` for the
    `declared-unverified` WARNING about a tree that is not reachable (#610).

    That warning offered "a sibling checkout, SHAPE_PIN_SOURCE_<LINK>, or
    --link-source <link>=<path>": the naming validator's three, and two of
    them the scaffold does not have. It has no `--link-source`, and it reads
    no checkout beside anything (`link_pins_from_trees(chain, None, ...)`).
    It reads `SHAPE_PIN_SOURCE_<LINK>` for every link, unless another link
    of the chain shares the variable (#275), and its `--pin-source` for the
    FIRST link alone (#441), the pinned product's clone. A later link that
    shares its variable has neither, which only a hand-written chain can
    hold, and the warning says so.

    Keyed by `pin_product_key`, the key `_chain_link_findings` finds a
    holder's entry by (#444). Keyed by `casefold()`, `openß` and `openss`,
    two links of one chain, wrote one entry, and the first link was offered
    the later one's words.
    """
    links = [repo_basename(link) for link in chain]
    shared = pin_source_env_shared(links)
    remedies: dict[str, str] = {}
    for index, link in enumerate(links[:-1]):
        key = pin_product_key(link)
        sources = [] if key in shared else [pin_source_env_name(link)]
        if not index:
            sources.append(f"a --pin-source clone of {link} that holds its "
                           "project.yaml")
        if not sources:
            remedies[key] = (
                "the scaffold reads no source for it: "
                f"{pin_source_env_name(link)} is another link's too, and "
                "--pin-source is the first link's tree alone")
        elif len(sources) == 1:
            remedies[key] = f"{sources[0]} would let it be read"
        else:
            remedies[key] = (f"{sources[0]}, or {sources[1]}, "
                             "would let it be read")
    return remedies


def shown_source(source) -> str:
    """A `--pin-source` path as a refusal names it: as it is, unless a
    character in it is not printable (`str.isprintable`), and then as
    Python's `repr` spells it -- `\\x1b`, `\\n`, `\\r`, and `\\udcff` for a
    byte that is not UTF-8, as `sys.argv` keeps one -- which is how every
    other value a refusal here names is spelled (`--pin {raw!r}`). The
    question `adopt-project.py`'s `_shown` asks of a path it prints.

    It IS `repo_shape.shown_path` (#610), which the scaffold's
    `declared-unverified` WARNING spells the same `--pin-source` with, so
    the two lines about one path cannot spell it two ways."""
    return shown_path(source)


def _digest_from_pin_source(source: Path, commit: str) -> str:
    """`tree_digest` over `source`, with a path that is no directory said
    in `validate-pins.py`'s words (#339), and a directory that is no
    clone's top level refused `pin-source-not-a-clone` before anything is
    digested (#800). Any other `OSError`, from `stat()` or from git's
    `cwd=`, is left for `pin_digest_from_source` to name."""
    try:
        mode = source.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        raise Refusal("pin-source-missing", "no such directory") from None
    if not stat.S_ISDIR(mode):
        raise Refusal("pin-source-not-a-directory",
                      "it is a file, not a directory")
    _refuse_unless_a_clone_top_level(source)
    return tree_digest(source, commit)


# ---------------------------------------------------------------------------
# A `--pin-source` is a clone's top level (#800)
# ---------------------------------------------------------------------------
#
# `tree_digest` runs `git ls-tree -r` IN the `--pin-source`, and there, with
# no `--full-tree`, git lists only the part of the tree under the folder it
# runs in. So a folder inside a clone was read as a clone: `glass/sub`
# recorded the digest of `sub/` alone, a folder the commit does not hold
# recorded the sha256 of nothing, and `adopt-project.py plan` and the
# scaffold, `--dry-run` alike, wrote it with no word; `check` recomputed the
# same number there, or, inside a partial clone, NOTEd that it did not ask.
#
# SO GIT IS ASKED FIRST, before any digest is read: a working tree's top
# level, a linked worktree's among them, has an empty `rev-parse
# --show-prefix` outside the git directory, and a bare clone's git directory
# is the path itself. Any other path is `pin-source-not-a-clone`, naming the
# top level git finds, or saying that it finds none. What a top level digests
# is unchanged, byte for byte, and `repo_shape.tree_digest`, a pinned shape
# copy, is not changed. `adopt-project.py check` asks a recorded path the
# same question (`pin_source_not_top_level`) before a partial clone's NOTE.

#: The refusal of a `--pin-source` that is no clone's top level.
PIN_SOURCE_NOT_A_CLONE = "pin-source-not-a-clone"
#: What it says to pass where git names no top level to pass.
NO_TOP_LEVEL_REMEDIATION = (
    "Remediation: pass --pin-source the top level of a clone of the pinned "
    "product (`git rev-parse --show-toplevel` prints it in that clone's "
    "working tree), or drop --pin-source and let `gh api` read the forge.")


def _rev_parse(source: Path, *asked: str) -> str:
    """What `git rev-parse <asked>` prints in `source`, its last line break
    dropped and a path in it as `sys.argv` holds one. A git that fails is
    `git_out`'s refusal, naming the folder and git's reason, spelled."""
    printed = git_out(["rev-parse", *asked], cwd=source, binary=True)
    return os.fsdecode(printed).removesuffix("\n")


def pin_source_not_top_level(source: Path) -> tuple[str, Path | None] | None:
    """None where `source` is a clone's top level (#800). Otherwise `(why,
    top)`: why it is not, and the top level git finds for it, or None where
    git finds none to pass. A `source` `subprocess` cannot enter raises the
    `OSError` of `cwd=`, which is the caller's to name.

    The answers come in one question where they can: `--show-prefix` is
    printed last, so a folder whose name holds a line break is read whole."""
    try:
        bare, inside, prefix = _rev_parse(
            source, "--is-bare-repository", "--is-inside-git-dir",
            "--show-prefix").split("\n", 2)
        if bare == "true":
            top = Path(_rev_parse(source, "--absolute-git-dir"))
            if os.path.samefile(top, source):
                return None
            return (f"it is a folder inside the bare clone at "
                    f"{shown_source(top)}", top)
        if inside == "true":
            gitdir = Path(_rev_parse(source, "--absolute-git-dir"))
            return (f"it is inside {shown_source(gitdir)}, the git directory "
                    "of a clone, where git finds no top level", None)
        if not prefix:
            return None
        top = Path(_rev_parse(source, "--show-toplevel"))
    except Refusal as exc:
        return f"git finds no clone there: {exc.detail}", None
    return (f"it is a folder inside the clone at {shown_source(top)}, and a "
            "digest read there covers only what the commit holds under that "
            "folder", top)


def _refuse_unless_a_clone_top_level(source: Path) -> None:
    """`pin-source-not-a-clone` for a `source` that is no clone's top level
    (`pin_source_not_top_level`), naming the top level to pass instead."""
    found = pin_source_not_top_level(source)
    if found is None:
        return
    why, top = found
    raise Refusal(
        PIN_SOURCE_NOT_A_CLONE,
        f"--pin-source {shown_source(source)} is not a clone's top level: "
        f"{why}",
        NO_TOP_LEVEL_REMEDIATION if top is None else
        f"Remediation: pass --pin-source {shown_source(top)}, the clone's "
        "top level, where a pin's digest is read over its commit's whole "
        "tree.")


def _resolved_pin_source(source: Path) -> Path:
    """`source` made absolute, or AS TYPED when it cannot be (#339).

    A symlink loop is a `RuntimeError` out of `Path.resolve()` before 3.13
    and an `OSError` since, and either one ended the run in a traceback
    before `pin_digest_from_source` could ask. As typed, `stat()` there meets
    the loop and says "Too many levels of symbolic links". A path that is
    merely absent or unreadable resolves, so a valid source is read exactly
    as before.
    """
    try:
        return source.resolve()
    except (OSError, RuntimeError):
        return source


def pin_digest_from_gh(repository: str, commit: str) -> str:
    """The same digest, computed from the forge's own recursive tree listing.

    A SHALLOW READ, not a clone: `git/trees/<commit>?recursive=1` returns one
    row per object with `mode`, `type`, `sha` and `path` — exactly the four
    columns `git ls-tree -r -z` emits, which is what makes the two readings
    the same number. Tree rows are dropped because `-r` emits none; a
    submodule arrives as `type: commit` with mode `160000` and is kept, as
    `ls-tree` keeps it.

    NO `gh` ON PATH IS `gh-not-found`, as `repo_shape.tree_digest_from_gh`,
    the validator's twin of this reader, names it: exit 2, before anything
    is created, with `--pin-source` offered. It was a `FileNotFoundError`
    traceback, exit 1, out of `subprocess.run`, from the scaffold and, since
    #273 reads adopt's pins here, from `adopt-project.py plan --pin`, which
    needed no `gh` before.
    """
    try:
        proc = subprocess.run(
            ["gh", "api", GH_TREE_API.format(repo=repository, commit=commit)],
            # UTF-8 and STRICT, not `errors="replace"`: this JSON becomes a
            # digest, and a replaced byte would be a wrong digest with a
            # confident tone (#217).
            capture_output=True, text=True, encoding="utf-8", check=False)
    except FileNotFoundError as exc:
        raise _gh_not_on_path(repository, commit, exc) from exc
    if proc.returncode != 0:
        raise _gh_could_not_read(repository, commit, proc.stderr.strip())
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Refusal("pin-unreadable",
                      f"{repository} @ {commit}: {exc}") from exc
    if payload.get("truncated"):
        raise Refusal(
            "pin-tree-truncated",
            f"the forge truncated its tree listing for {repository} @ "
            f"{commit}, so the digest would be computed over a PARTIAL tree",
            "Remediation: clone that repository and pass --pin-source <path>. "
            "A digest over a partial tree is a wrong answer with a confident "
            "tone.",
        )
    import hashlib
    records = sorted(
        f"{row['mode']} {row['type']} {row['sha']}\t{row['path']}".encode()
        for row in payload.get("tree") or [] if row.get("type") != "tree")
    digest = hashlib.sha256()
    for record in records:
        digest.update(record)
        digest.update(b"\n")
    return digest.hexdigest()


def _gh_not_on_path(repository: str, commit: str,
                    exc: FileNotFoundError) -> Refusal:
    """`gh-not-found`, for a pin the forge was to be asked about: what
    each `gh` read here refuses with when `subprocess` finds no `gh`."""
    return Refusal(
        "gh-not-found",
        f"the `gh` CLI is not on PATH, so `gh api` cannot read "
        f"{repository} @ {commit}: {exc}",
        "Remediation: pass --pin-source <a local clone of that "
        "repository> to compute the digest with no network at all, or "
        "put `gh` on PATH and run this again (`openRepoShape "
        "--preflight` names each missing prerequisite and offers to "
        "install it, on a typed yes).")


def _gh_could_not_read(repository: str, commit: str, why: str) -> Refusal:
    """`pin-unreadable`, for a pin the forge did not answer for: what
    each `gh` read here refuses with, `why` being what `gh` said."""
    return Refusal(
        "pin-unreadable",
        f"`gh api` could not read {repository} @ {commit}: {why}",
        "Remediation: check the commit exists in that repository and that "
        "`gh auth status` can see it. An unqualified --pin resolves under "
        f"{NEUTRAL_PRODUCT_OWNER} by default (never the project's own "
        "--org) — if this product actually lives under a different "
        "owner, name it explicitly with --pin <owner>/<openProduct>@<sha> "
        "or --pin-owner <owner>. You can also pass --pin-source <local "
        "clone> to compute the digest with no network at all.")


# ---------------------------------------------------------------------------
# What a pin's id names: an annotated tag's own id is peeled (#651)
# ---------------------------------------------------------------------------
#
# `git rev-parse v1.2` prints a release tag's OWN id, 40 hex, so `PIN_ARG_RE`
# takes it, and nothing after that asked what it was. `tree_digest` reads it
# with `git ls-tree`, which peels a tag to its tree, so the digest was the
# commit's, and `--pin openGlass@<the tag's id>` wrote the TAG's id as the
# pin's `commit:`, under the pin file's own `revision_kind: commit` and "A
# COMMIT, NEVER A TAG": in the scaffold, its `--dry-run` and `adopt-project.py
# plan` alike. The root's `validate-pins.py` passed it, for the same reason,
# and a tree's id went the same way.
#
# PEELED, as `bump-leg.py --to` (#534), `family.py add --at` and `family.py
# bump --to` (#541, Brett Heap's ruling of 2026-10-14) peel one. A tag
# object's id fixes its content, so it names one commit for ever and, unlike
# a tag NAME, cannot be moved: it is as exact a pin as that commit. One line
# says so, and every value after it, the digest, the plan and the pin file,
# is the commit's. A tree, a blob or a tag of either names no commit at all,
# and is refused `pin-not-a-commit`, naming which, in `bump-leg.py`'s words.
#
# ASKED WHERE THE DIGEST IS READ: `git cat-file -t` in the `--pin-source`
# clone, or, with none, the forge's own GraphQL `object(oid:)`, whose
# `__typename` names the same four kinds; a tag of a tag is followed to the
# end. `adopt-project.py check` asks the clone `plan` read a digest from the
# same question (`commit_in_clone`).

#: What `git cat-file -t` calls the one kind a pin may name, and the one
#: that is peeled to it.
COMMIT_KIND, TAG_KIND = "commit", "tag"
#: The forge's GraphQL `__typename` for each kind `git cat-file -t` names.
GH_KINDS = {"Commit": COMMIT_KIND, "Tag": TAG_KIND, "Tree": "tree",
            "Blob": "blob"}
#: A whole object id, as the forge spells the one a tag names.
OBJECT_ID_RE = re.compile(r"[0-9a-f]{40}")
#: What the forge is asked about a pin's id: what kind of object it is, and
#: for a tag, the kind and id of what the tag names.
GH_OBJECT_QUERY = (
    "query($owner: String!, $name: String!, $oid: GitObjectID!) "
    "{ repository(owner: $owner, name: $name) { object(oid: $oid) "
    "{ __typename ... on Tag { target { __typename oid } } } } }")
#: What `pin-not-a-commit` tells a person to pass instead.
PIN_NOT_A_COMMIT_REMEDIATION = (
    "Remediation: pass a commit -- `git log --format=%H` in a clone of the "
    "product lists them -- or an annotated tag of one, whose own id is "
    "peeled to the commit it names, as `bump-leg.py --to` peels one. A "
    "tree's or a blob's id is part of a commit and never one, and a pin is "
    "a commit or it is nothing.")


def not_a_commit(kind: str, names: str | None) -> str:
    """How an id that names no commit is said (#651), in `bump-leg.py`'s
    words: `names a tree`, `is an annotated tag of a blob`, or `is an
    annotated tag that names no commit`. `kind` is what the id is, and
    `names` what the last tag it leads through names, if anything."""
    if kind != TAG_KIND:
        return f"names a {kind}"
    if names in ("tree", "blob"):
        return f"is an annotated tag of a {names}"
    return "is an annotated tag that names no commit"


def _git_answer(clone: Path, *args: str) -> str | None:
    """What `git <args>` prints in `clone`, or None where it fails or
    `subprocess` cannot enter `clone` at all."""
    try:
        proc = subprocess.run(["git", *args], cwd=str(clone),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              check=False)
    except OSError:
        return None
    return (proc.stdout.strip() or None) if proc.returncode == 0 else None


def commit_in_clone(clone: Path, oid: str) -> tuple[str, str]:
    """`(commit, "")` for the commit `oid` names in the clone at `clone`
    (#651): `oid` itself, or the commit an annotated tag's own id names,
    peeled through a tag of a tag (`<id>^{}`). `(oid, why)` for an id that
    names no commit, `why` as `not_a_commit` says it. And `(oid, "")` where
    the clone cannot say, no object with that id or no clone there, which
    the digest's reader then names in its own words
    (`pin-source-unreadable`)."""
    kind = _git_answer(clone, "cat-file", "-t", oid)
    if kind in (None, COMMIT_KIND):
        return oid, ""
    names = None
    if kind == TAG_KIND:
        peeled = (_git_answer(clone, "rev-parse", "-q", "--verify",
                              f"{oid}^{{}}") or "").lower()
        names = (_git_answer(clone, "cat-file", "-t", peeled) if peeled
                 else None)
        if names == COMMIT_KIND:
            return peeled, ""
    return oid, not_a_commit(kind, names)


def _gh_object(repository: str, commit: str, oid: str) -> dict:
    """What the forge says `oid` is in `repository`, through `gh api
    graphql`: `{"__typename": ..., "target": ...}`. A forge that cannot
    answer, holds no such object, or answers with no kind this reads, is
    `pin-unreadable` for the pin `commit`, as `pin_digest_from_gh` refuses
    one; no `gh` on PATH is its `gh-not-found`."""
    owner, name = repository.split("/", 1)
    try:
        proc = subprocess.run(
            ["gh", "api", "graphql", "-f", f"query={GH_OBJECT_QUERY}",
             "-f", f"owner={owner}", "-f", f"name={name}", "-f", f"oid={oid}"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", check=False)
    except FileNotFoundError as exc:
        raise _gh_not_on_path(repository, commit, exc) from exc
    if proc.returncode != 0:
        raise _gh_could_not_read(repository, commit, proc.stderr.strip())
    try:
        found = json.loads(proc.stdout)["data"]["repository"]["object"]
    except (ValueError, KeyError, TypeError) as exc:
        raise _gh_could_not_read(
            repository, commit,
            f"its answer about {oid} holds no `data.repository.object` "
            f"({exc!r})") from exc
    if found is None:
        raise _gh_could_not_read(
            repository, commit,
            f"the forge holds no object {oid} in {repository}")
    if not isinstance(found, dict) or found.get("__typename") not in GH_KINDS:
        raise _gh_could_not_read(
            repository, commit,
            f"its answer about {oid} names no kind of object: {found!r}")
    return found


def commit_on_forge(repository: str, oid: str) -> tuple[str, str]:
    """`commit_in_clone`'s answer, asked of the forge (#651): `(commit,
    "")` for the commit `oid` names in `repository`, itself or the one its
    annotated tags lead to, or `(oid, why)` for an id that names none. Each
    tag in a tag of a tag is one more question; a tag that names a commit,
    a tree or a blob is answered by the question that found it."""
    found = _gh_object(repository, oid, oid)
    kind = GH_KINDS[found["__typename"]]
    names, seen = kind, {oid}
    while names == TAG_KIND:
        target = found.get("target")
        target = target if isinstance(target, dict) else {}
        peeled = str(target.get("oid") or "").lower()
        names = GH_KINDS.get(target.get("__typename"))
        if OBJECT_ID_RE.fullmatch(peeled) is None or peeled in seen:
            names = None
        elif names == COMMIT_KIND:
            return peeled, ""
        elif names == TAG_KIND:
            seen.add(peeled)
            found = _gh_object(repository, oid, peeled)
    if kind == COMMIT_KIND:
        return oid, ""
    return oid, not_a_commit(kind, names)


#: How a pin file says its digest was read (`digest_source:`): from a clone
#: on this machine, or from the forge's own recursive tree listing.
DIGEST_FROM_CLONE = "local-clone"
DIGEST_FROM_GH = "gh-api-tree-recursive"


def declared_pin_values(args) -> dict[str, dict[str, str]]:
    """The template values for every `--pin`, with its digest resolved.

    The digest is the same `sorted-ls-tree-r-v1` number every other pin here
    carries, read either from a clone on this machine (`--pin-source`, and no
    network at all) or from the forge's own recursive tree listing.

    `args` is either tool's command line: `pin`, `pin_owner` and `pin_source`
    are the same three flags in `scaffold-project.py` and in
    `adopt-project.py plan`, which records these values in the plan so that
    `check` and `execute` read no network for them (#273).

    A CLONE IS RECORDED AS `local-clone`, AND ITS PATH IS NOT (#540). The
    path went into the committed pin file's `digest_source:` as it was
    typed, `local-clone (<path>)`, so an absolute `--pin-source` committed
    the directory a clone sat in on the machine that ran the tool, which is
    of no use to any other reader of the file. The path was also written
    bare (#450): one holding a line break wrote a line of its own choosing
    into the pin file, and the scaffold died in `write_lf` on one holding a
    byte that is not UTF-8, after all three repositories existed. What the
    field is for is which of the two ways the digest was read, so that is
    what it says; the refusals above still name the path the run was given.
    `adopt-project.py plan` records the path in its plan beside these
    values, `local-clone (<path>)`, so that `check` recomputes the digest in
    that clone (#449): the plan is a file on that machine, which nothing
    commits, and `execute` writes the pin file's field as this says it.

    THE COMMIT IS THE ONE THE ID NAMES (#651), asked where the digest is
    read, before it is (`_pinned_commit`): an annotated tag's own id is
    peeled to its commit, and a tree's, a blob's or a tag of either is
    refused `pin-not-a-commit`.
    """
    pins: dict[str, dict[str, str]] = {}
    for raw in args.pin:
        product, repository, commit = parse_pin(raw, args.pin_owner)
        commit = _pinned_commit(args, raw, repository, commit)
        if args.pin_source is not None:
            digest = pin_digest_from_source(
                _resolved_pin_source(args.pin_source), commit, repository)
            digest_source = DIGEST_FROM_CLONE
        else:
            digest = pin_digest_from_gh(repository, commit)
            digest_source = DIGEST_FROM_GH
        pins[product] = {
            "PIN_PRODUCT": product,
            "PIN_REPOSITORY": repository,
            "PIN_COMMIT": commit,
            "PIN_TREE_SHA256": digest,
            "PIN_DIGEST_SOURCE": digest_source,
        }
    return pins


def _pinned_commit(args, raw: str, repository: str, typed: str) -> str:
    """The commit the `--pin` `raw`, whose id is `typed`, pins (#651), asked
    where `declared_pin_values` reads its digest: in the `--pin-source`
    clone, or of the forge. A peeled tag is said in one line on stdout, as
    `bump-leg.py` says one, before the plan either tool prints; an id that
    names no commit is `pin-not-a-commit`, before any digest is read, and
    so before the scaffold creates anything or `plan` writes a plan."""
    if args.pin_source is not None:
        clone = _resolved_pin_source(args.pin_source)
        commit, why = commit_in_clone(clone, typed)
        where = f"the clone at {shown_source(clone)}"
    else:
        commit, why = commit_on_forge(repository, typed)
        where = f"{repository} on the forge"
    if why:
        raise Refusal("pin-not-a-commit",
                      f"--pin {raw.strip()} {why} in {where}, not a commit",
                      PIN_NOT_A_COMMIT_REMEDIATION)
    if commit != typed:
        print(f"--pin {repository} @ {typed[:12]} is an annotated tag; it "
              f"names commit {commit[:12]}, which is what the pin records")
    return commit


def declared_pin_products(args) -> dict[str, None]:
    """The products `declared_pin_values` keys its pins by, in its order and
    read by the same `parse_pin`, with no digest: so no `git` and no `gh`.

    #197: `_build_assembly_root` hands those pins to the materializer, which
    writes `neutral_pin_path(product)` for each, and the leg paths are asked
    about that file before `_identity` and `_declaration` run, which is
    before any digest is read. A malformed `--pin` is therefore refused
    here, by `parse_pin`'s own `pin-malformed`, rather than in
    `_declaration`; it was refused before anything was created either way.
    `adopt-project.py plan` asks its leg paths about the same files, from
    the same products, before it reads a digest (#273).
    """
    return dict.fromkeys(parse_pin(raw, args.pin_owner)[0] for raw in args.pin)


def pin_source_path(typed: str | None, *, nothing_made: str) -> Path | None:
    """`--pin-source` as the `Path` both tools read, or None when it was not
    given; a value that names no path is `pin-source-no-path`.

    AN EMPTY VALUE WAS THE DIRECTORY THE TOOL RAN IN. `Path("")` is
    `Path(".")`, so `--pin-source ''` read the current directory as the
    clone: the digest came from wherever the command was run, or
    `pin-source-unreadable` blamed `.`, a path nobody typed. #442 refuses
    an empty value in the naming gate (`link-source-no-path`) and in the
    root's `validate-pins.py` (`pin-source-no-path`); the two tools that
    make a project refuse it in the same words. A typed `.` still means
    the current directory.

    So both tools take the flag as TEXT and ask here, before anything
    exists and before any process starts, the scaffold's `--dry-run` alike:
    once `argparse` has made a `Path` of it, an empty value and a typed `.`
    are one. `nothing_made` begins the remediation in the tool's own words,
    as it does for `refuse_an_unread_pin_source`.
    """
    if typed is None:
        return None
    if not str(typed):
        raise Refusal(
            "pin-source-no-path",
            "`--pin-source ''` names no path. An empty path would be read as "
            "the directory this runs in.",
            f"Remediation: {nothing_made} Give the clone's path "
            "(`--pin-source <path>`), or `.` to mean this directory.")
    return Path(typed)


def folder_flag_path(typed, flag: str, code: str, *, names: str,
                     absent: str) -> Path | None:
    """A folder flag as the `Path` the tool reads, or None when it was not
    given; a value that names no path is refused as `code`.

    `pin_source_path`'s question, asked of the folders the scaffold and
    `family.py init` make things in (#972's review, S2): `--work-dir` and
    `--local-remote-dir` in both, and `init`'s `--into`. Each was parsed as
    a `Path`, and `Path("")` is `Path(".")`, so a flag passed empty was read
    as the directory the tool ran in, without a word: from the root of a
    checkout of openRepoShape, `init --into ''` planned the holder inside
    it, where no `--into` is refused as `family-landing-in-standard`. Each
    tool takes them as TEXT now and asks here, before anything exists and
    before any process starts, under `--dry-run` alike. A typed `.` still
    means the current directory, and a flag not given keeps its default.

    `names` says what the folder is for and `absent` what the run does with
    no flag, each in the tool's words, so the remedy names the three ways
    on: a path, `.`, or no flag at all.
    """
    if typed is None:
        return None
    if not str(typed):
        raise Refusal(
            code,
            f"`{flag} ''` names no path. An empty path would be read as the "
            "directory this runs in.",
            "Remediation: nothing was created, and `--dry-run` refuses the "
            f"same. Give {names} (`{flag} <dir>`), or `.` to mean this "
            f"directory; with no {flag}, {absent}.")
    return Path(typed)


def refuse_an_unread_pin_source(pin_source, pins, chain=None, *,
                                nothing_made: str) -> None:
    """`--pin-source` is read by this run, or this refuses it as
    `pin-source-unused` (#451): before anything exists and before any digest
    is read, so the scaffold's `--dry-run` refuses it too and `plan` writes
    no plan.

    ITS READERS ARE `declared_pin_values`, which reads each `--pin`'s digest
    there, and, in the scaffold, `link_pins_from_trees`, which reads the
    first `--referent-chain` link's declaration there when nothing keyed
    names that link's tree: a bare path is the first link's tree alone
    (#441), never a later link's. With neither, nothing read it, so nothing
    asked about it either: a path that does not exist was accepted,
    `--dry-run` said `nothing was created.` and `plan` wrote its plan, each
    exit 0 with no word that the flag had changed nothing. Typed meaning to
    pin, with the `--pin` forgotten, it made a project that declares no
    descent. The root's own `validate-pins.py` NOTES an unused
    `--pin-source` of its own (#295), a check that is run again and again;
    the two tools that make a project refuse one, before it is made, as
    they refuse each other value they cannot use.

    `pins` is the `--pin` list and `chain` the scaffold's `--referent-chain`
    links, or `None` for a tool that takes no chain (`adopt-project.py
    plan`), so the sentence names only flags the tool has. `nothing_made`
    begins the remediation in the tool's own words. The path is never read
    here, and is named as `shown_source` names it.
    """
    if pin_source is None or pins or chain:
        return
    if chain is None:
        given, reads = "no --pin", "each --pin's digest is read from"
    else:
        given = "no --pin and no --referent-chain"
        reads = ("each --pin's digest is read from, and the first "
                 "--referent-chain link's declaration")
    raise Refusal(
        "pin-source-unused",
        f"--pin-source {shown_source(pin_source)} was given with {given}, so "
        f"nothing reads it: it names the clone {reads}.",
        f"Remediation: {nothing_made} Add the --pin "
        "<openProduct>@<40 hex commit> that clone was given for, or drop "
        "--pin-source.")


#: What every refused `--pin` is told to do. The file a pin is written at is
#: `neutral_pin_path`'s, spelled for a placeholder product, never by hand. It
#: names `spec`, `code` and `shape` outright (#288): for a repository truly
#: called one of them, "name the product for the repository it pins" is no
#: remedy at all, because no spelling of that name can be pinned.
PIN_COLLISION_REMEDIATION = (
    "Remediation: nothing was created. A neutral product is named for the "
    "repository it pins, as `--pin openGlass@<40 hex commit>` names "
    f"{NEUTRAL_PRODUCT_OWNER}/openGlass by default, and its pin is written at "
    f"`{neutral_pin_path('<openProduct>')}`, the name lowercased, beside the "
    "pins the shape writes for its two legs and for itself, so `spec`, `code` "
    "and `shape`, in any case, are names no product can be pinned under. Pass "
    "each product once, by the name of the repository it pins."
)

#: What a refused pair of `--pin`s whose products share a source variable is
#: told to do (#275), after what `PIN_COLLISION_REMEDIATION` says when a file
#: collides too.
PIN_VARIABLE_REMEDIATION = (
    f"`{PIN_SOURCE_ENV_PREFIX}<PRODUCT>` names the local checkout of a "
    "product, and is its name upper-cased with every character outside `A-Z`, "
    "`0-9` and `_` turned into `_`, so names that differ only in `-`, `.` or "
    "`_` share one. The project's own `validate-pins.py` reports such a pair "
    "as `neutral-pin-source-collides`, and a variable two pins share is read "
    "for neither. Pass one product of each such group, or products whose "
    "names differ by more."
)


def pin_collisions(typed) -> list[str]:
    """One sentence for each file that a pin would be written over: a file
    the shape writes itself, or a file another pin is written at (#241).
    `[]` when no pin collides.

    `typed` is `(said, product)` for each pin, in the order the person gave
    them: `said` names the pin as they gave it (`--pin 'spec@<sha>'` on a
    command line, or the `pins:` entry of an adoption plan), and `product`
    is the name its file is spelled from. ONE LIST OF EVERY PIN, NEVER ONE
    KEYED BY PRODUCT, which collapses a repeat: each pin given is named, and
    a repeat is a collision whether or not its commits agree.

    THE QUESTION IS ASKED THROUGH THE MATERIALIZER'S OWN TWO DEFINITIONS: a
    pin's file is `neutral_pin_path(product)`, and the shape's own files are
    `assembly_root_paths()` with no pins. `neutral_pin_path` lowercases, so
    `Spec` is `spec` and `openGlass` and `OpenGlass` are one file, with no
    case rule of this function's own.
    """
    # Folded on both sides, as `path_overlap` folds the leg paths: a future
    # mixed-case shape file under `contracts/` is still one path with a
    # lowercased pin on the case-insensitive disk of macOS and Windows.
    shape_files = {shape_file.casefold()
                   for shape_file in assembly_root_paths()}
    written: dict[str, list[tuple[str, str]]] = {}
    for said, product in typed:
        written.setdefault(neutral_pin_path(product), []).append(
            (said, product))
    collisions = []
    for path, pins in written.items():
        in_shape = path.casefold() in shape_files
        if not in_shape and len(pins) == 1:
            continue
        products = list(dict.fromkeys(product for _, product in pins))
        said = (" and ".join(said for said, _ in pins)
                + (" writes the pin" if len(pins) == 1 else " write the pins")
                + " of the product" + ("s" if len(products) > 1 else "") + " "
                + " and ".join(f"`{product}`" for product in products))
        if in_shape:
            collisions.append(
                f"{said} at `{path}`, a file the shape writes into the "
                "assembly root itself: name the product for the repository it "
                "pins.")
        else:
            collisions.append(
                f"{said} at one file, `{path}`, which holds one pin: pass "
                "each product once.")
    return collisions


def pin_variable_collisions(typed) -> list[str]:
    """One sentence for each `SHAPE_PIN_SOURCE_<PRODUCT>` variable that two or
    more of the products pinned share, each pin named as `typed` names it,
    in the order each variable's first pin was (#275). `typed` is
    `pin_collisions`'s `(said, product)` list.

    `open-glass`, `open_glass` and `open.glass` are three pin files and three
    legal `--pin` names, and one variable: whichever checkout it names answers
    for all of them, and the project's own `validate-pins.py` reported the
    pin it was not a checkout of as `neutral-pin-source-unreadable`. The
    question is `repo_shape.pin_source_env_collisions`'s, so it is the one
    `validate-pins.py` answers, and it takes products as their pin files do
    (`pin_product_key`): the same product typed twice is #241's `one file`,
    said by `pin_collisions`, and is never a collision here. Each pin is
    named under its own product by that key too, and not by a casefold,
    which took `openß` and `openss`, two pin files, for one product and
    named each of the two pins twice.
    """
    said_of = {}
    for said, product in typed:
        said_of.setdefault(pin_product_key(product), []).append(said)
    out = []
    for variable, products in pin_source_env_collisions(
            product for _, product in typed).items():
        named = [said for product in products
                 for said in said_of[pin_product_key(product)]]
        out.append(
            " and ".join(named) + " name the products "
            + " and ".join(f"`{product}`" for product in products)
            + f", and one variable, `{variable}`, names the local checkout of "
            "each: it cannot say which it holds.")
    return out


def pin_collision_remediation(file_collision: bool,
                              variable_collision: bool) -> str:
    """The remediation for the collisions a refusal names: #241's alone for a
    file, the variable's alone, or both said once each (#275)."""
    if not variable_collision:
        return PIN_COLLISION_REMEDIATION
    if not file_collision:
        return f"Remediation: nothing was created. {PIN_VARIABLE_REMEDIATION}"
    return f"{PIN_COLLISION_REMEDIATION} {PIN_VARIABLE_REMEDIATION}"


def refuse_colliding_pins(pins, owner: str,
                          refusal: str = "scaffold-pin-collides") -> None:
    """No `--pin` is written where the shape writes a file of its own, and no
    two `--pin`s are written at one path, or this refuses (#241).

    `scaffold-project.py`'s `_build_assembly_root` hands the pins to the
    materializer, which writes each at `neutral_pin_path(product)` after the
    shape's own files and before the copy pin, and a second file at one path
    is `materialize-collision`: a pin over a leg's pin, or the copy pin over
    a pin named `shape`, or a pin over another pin. So each was met only
    after `_create_remotes` and `_seed_legs`. On main through 39ac59c, `--pin
    spec@<sha>` (`Spec@`, `code@`, `MedxSoft/code@`, `shape@`) and `--pin
    openGlass@<sha> --pin OpenGlass@<sha>` planned under `--dry-run`, then
    created all three repositories, pushed both legs, left the root with no
    commit and exited 2, and the corrected re-run was refused as
    `scaffold-remote-exists`. Against GitHub, each left three repositories
    for a run that made no project. `adopt-project.py plan` asks the same of
    its `--pin`s before it writes a plan (#273), as `refusal`
    `adopt-pin-collides`, and `check` asks it of the plan's `pins:` through
    `pin_collisions`.

    The product is read by `parse_pin` alone, so a malformed `--pin` is still
    its `pin-malformed`, and no digest is read: no `git` and no `gh`.

    THE RAW `--pin` LIST, NEVER `declared_pin_products`, which collapses a
    repeated product, as `declared_pin_values` does by keeping the last:
    `--pin openGlass@<A> --pin openGlass@<B>` planned one pin, wrote `<B>`
    and dropped `<A>` without a word. A declaration is a claim about what
    the project descends from, so a repeat is refused whether or not its
    commits agree: either way it is a typing error, and one of the two
    would be lost. Every argument is named as it was typed.

    IT RUNS BEFORE THE LEG-PATH COLLISION REFUSAL, which asks about
    `assembly_root_paths(<the --pin products>)`. With `--pin spec@<sha>`
    that list held `contracts/spec-pin.yaml` twice, and `--spec-path
    contracts` was told it contains that file "and 4 more" where there
    were three (#197's re-review, N1). Refused first, no pin path it lists
    is the shape's or listed twice.

    TWO PINS THAT SHARE A SOURCE VARIABLE ARE REFUSED HERE TOO (#275), in the
    same refusal and after the file collisions, by `pin_variable_collisions`:
    `--pin open-glass@<A> --pin open_glass@<B>` are two files and one
    `SHAPE_PIN_SOURCE_OPEN_GLASS`. This is refused so that no new project is
    made, and no plan written, with a variable it cannot use: the project's
    own `validate-pins.py` only NOTES such a pair in one that already
    declares it (`neutral-pin-source-collides`), since nothing it could have
    done then is wrong, but a pair made now is said no to before anything
    exists.
    """
    typed = [(f"--pin {raw!r}", parse_pin(raw, owner)[0]) for raw in pins]
    collisions = pin_collisions(typed)
    shared = pin_variable_collisions(typed)
    if collisions or shared:
        raise Refusal(refusal, " ".join(collisions + shared),
                      pin_collision_remediation(bool(collisions),
                                                bool(shared)))


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
# EXCEPT THE SEGMENTS, which a project's copy DOES ask (#189): its
# `validate-manifest.py` holds each path `project.yaml`'s `submodules:`
# records to the spelling Git records a path in, so
# `repo_shape.path_spelling_fault` answers that for both rules, and
# `_spelling_reason` below adds only what a TYPED path can get wrong -- a
# drive letter and a backslash, which on POSIX are characters of a name Git
# records -- and says every answer about a leg.
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
#
# LAST, A PATH THE PROJECT MUST READ BACK AS WRITTEN (#225). The assembly
# root's `project.yaml` holds each leg path on a `path:` line, and the leg's
# pin, `contracts/<role>-pin.yaml`, on a `submodule_path:` line. The project
# reads both with its own copy of `repo_shape`'s YAML reader. Written bare
# there, as the templates wrote them when #225 was found, `null`, `~`,
# `true`, `False`, `2026` and `1.5` are read as no value, a boolean or a
# number. Every one of those is in
# the alphabet above, so `--spec-path 2026` scaffolded three repositories
# whose first bootstrap then failed `manifest-leg-path: leg 'spec': path is
# 2026`, and `adopt-project.py execute` said `adoption verified` before the
# same bootstrap failed. Such a value is refused, with no spelling offered:
# there is none that names the same directory.
#
#   * THE TEMPLATES ARE READ, AND THE READER IS ASKED. The rule finds every
#     YAML template line that holds a leg path, renders the value into it
#     with `render`, as the scaffold and `execute` do, and asks the reader
#     what it gives back. It keeps no copy of the line and no list of the
#     reader's words: a copy goes stale the day a template quotes the
#     placeholder (#259), and a list the day the reader learns a word. Where
#     every such line is quoted, every value `checked_value` admits reads
#     back, and the rule refuses none, with no edit here.
#   * `yes`, `0x1F`, `1e3` and `.inf` are text to this reader today (YAML 1.1
#     or 1.2 would read some of them otherwise), so they are paths here, and
#     a reader that learned one would refuse it on a bare line with no edit.
#   * `tests/test_leg_path_yaml_scalars.py` finds the template lines on its
#     own and holds the rule's verdict to what each line reads back.

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
#: text (`007` is read as 7, `true` and `True` as one boolean, `1.50` as 1.5,
#: and `null`, `~` and nothing at all as one None), so a sentence that echoed
#: the parsed value would show something the file never said; it names the
#: KIND the reader made of it instead.
NOT_TEXT_KINDS = {bool: "true or false", int: "a number", float: "a number",
                  list: "a list", dict: "a mapping",
                  type(None): "no value at all"}

LEG_PATH_REMEDIATION = (
    "Remediation: nothing here rewrites a path for you, so correct the value "
    "yourself. A leg path is relative and POSIX: one or more plain segments "
    "such as `spec` or `legs/spec`, with no leading `/` or `./`, no trailing "
    "`/`, no `//`, no `..` and no backslash; no segment is one of Git's own "
    "names (`.git`, `git~1`, `.gitmodules`, in any case), ends in a dot or a "
    "space, or is a Windows device name (`CON`, `PRN`, `AUX`, `NUL`, "
    "`COM1`-`COM9`, `LPT1`-`LPT9`, with or without an extension); the whole "
    f"value matches {SAFE_ARG_RE.pattern} and does not begin with `-`; the "
    "project's YAML reader reads it back as the same text from every line "
    "the project writes it into (a bare line reads `null`, `~`, `true`, "
    "`False`, `2026` and `1.5` as something else); and the two legs take "
    "different paths, neither inside the other, whatever the case."
)


#: What each way a path's SEGMENTS can be misspelled means for a leg's mount
#: path. `path_spelling_fault` asks the segments; the empty and absolute
#: answers it also gives are `_spelling_reason`'s own, asked first, beside
#: the drive letter and the backslash only a typed path can get wrong.
LEG_SEGMENT_REASONS = {
    PATH_CLIMBS: ("it has a `..` segment, so it names a different place than "
                  "it spells and can climb out of the assembly root"),
    PATH_ITSELF: ("it names the assembly root itself, and a leg is mounted "
                  "INSIDE the root, not at it"),
    PATH_NOT_CANONICAL: (
        "Git records a mount without its `.` segments (a leading `./`), a "
        "trailing `/` or a doubled `/`, so the mount and its `.gitmodules` "
        "entry would name two different paths"),
}


def _spelling_reason(text: str) -> str | None:
    """Why `text` is not a CANONICAL spelling of a leg path, or None.

    The segments are `repo_shape.path_spelling_fault`'s, the rule a
    project's own validator also holds a recorded submodule path to (#189).
    """
    if not text:
        return "it is empty"
    if text.startswith("/") or WINDOWS_ABSOLUTE_RE.match(text):
        return ("it is absolute (`/spec` on every platform, `C:/spec` on "
                "Windows), and a leg is mounted INSIDE the assembly root, so "
                "its path is relative to it")
    if "\\" in text:
        return "it has a backslash, and a path here is written with `/`"
    return LEG_SEGMENT_REASONS.get(path_spelling_fault(text))


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


def refuse_an_unholdable_name(refusal: str, flag: str, name: str, *,
                              names: str, remediation: str) -> None:
    """`name`, typed as `flag`, is a name a Windows disk can make a folder
    of, or this refuses it as `refusal`: before anything exists, under
    `--dry-run` alike, and with no process started.

    ONE QUESTION FOR EVERY NAME A TOOL MAKES A FOLDER OF (#989). `family.py
    init` asked it of `--family` since #688 (`family-bad-holder-name`), and
    the scaffold never asked it of `--project`: `--project NUL` and `Con`,
    each one CamelCase token, which is all the naming policy asks, made the
    three repositories, the working trees and, under `--local-remote-dir`,
    the bare `NUL.git`, a root no Windows disk can clone. Each tool asks it
    here now, so the two cannot part again.

    THE QUESTION IS THE LEG PATH RULE'S (`_unmountable_reason`), asked of a
    path of one segment: a Windows device name, with or without an
    extension, in any case (`CON`, `Nul`, `com1`, `NUL.git`); a name ending
    in a dot or a space; one of Git's own names. Each tool asks it after its
    naming policy has said what the name may hold, so in practice a device
    name is the answer. A device name is the WHOLE name: `Nullable` and
    `NUL-spec` are folders Windows makes. As `refuse_bad_leg_paths` does,
    the caller gives its own code, the flag, what the name names (`names`,
    the sentence's middle: "which names <names>, and <reason>.") and its own
    remediation, so each tool refuses in its own voice."""
    reason = _unmountable_reason(name)
    if reason:
        raise Refusal(refusal,
                      f"{flag} is {name!r}, which names {names}, and "
                      f"{reason}.",
                      remediation)


#: The templates the rule below reads its lines from: the shape's own
#: `templates/`, which both tools render a project from (`SHAPE_ROOT /
#: "templates"`, and this file is `SHAPE_ROOT/scripts/`). A test points it
#: at a copy whose lines it has quoted or left bare.
LEG_PATH_TEMPLATES = Path(__file__).resolve().parents[1] / "templates"

#: The placeholders a leg path is rendered into.
LEG_PATH_PLACEHOLDERS = ("SPEC_PATH", "CODE_PATH")

#: What `_leg_path_lines` found under each templates directory it was asked.
_LEG_PATH_LINES: dict[Path, tuple[tuple[str, str, str], ...]] = {}


def _leg_path_lines(templates: Path) -> tuple[tuple[str, str, str], ...]:
    """Every line of every YAML template under `templates` that holds a leg
    path, as `(tree, file, line)`: `tree` is the template tree
    (`assembly-root`) and `file` the path the line is written to inside it
    (`contracts/spec-pin.yaml`).

    FOUND, NOT LISTED, the way `tests/test_leg_path_yaml_scalars.py` finds
    them, so a template that writes a leg path another way, or in another
    file, changes what this rule asks with no edit here. A Markdown
    template's `{{SPEC_PATH}}/` is prose no YAML reader reads, so only `.yaml`
    and `.yml` files are asked. The shallowest file comes first, so a
    sentence names `project.yaml` before the pins. Read once per process.
    """
    if templates in _LEG_PATH_LINES:
        return _LEG_PATH_LINES[templates]
    found = []
    for path in sorted(templates.rglob("*"),
                       key=lambda p: (len(p.parts), p.as_posix())):
        if path.suffix not in (".yaml", ".yml") or not path.is_file():
            continue
        tree, _, file = path.relative_to(templates).as_posix().partition("/")
        for line in path.read_text(encoding="utf-8").splitlines():
            if any("{{" + key + "}}" in line for key in LEG_PATH_PLACEHOLDERS):
                found.append((tree, file, line))
    _LEG_PATH_LINES[templates] = tuple(found)
    return _LEG_PATH_LINES[templates]


def _read_back(tree: str, file: str, rendered: str):
    """What the project's reader gives back from one rendered `key: value`
    line, read on its own: its scalar reads the same there as inside its
    block.

    A LINE THE READER REFUSES GIVES BACK THE REFUSAL, its `YamlError`, as
    `_reading_of` gives it for a manifest's line (#715). Uncaught, it was a
    traceback where the tool owes a refusal of the value: `checked_value`
    lets a leg path open with `@`, which opens no plain scalar (#393), so a
    bare leg-path line holding `--spec-path @x` is a line the project's
    reader refuses. All four such lines are quoted today (#259)."""
    try:
        read = parse_yaml(rendered + "\n")
    except YamlError as exc:
        return exc
    if not (isinstance(read, dict) and len(read) == 1):
        raise Refusal("template-leg-path-line",
                      f"templates/{tree}/{file}: `{rendered}` is not one "
                      "`key: value` line, which is the one form the leg-path "
                      "rule reads a leg path back from",
                      "Remediation: this is a defect in the shape's "
                      "templates, not in your invocation.")
    return next(iter(read.values()))


def _listed(names: list[str]) -> str:
    """`a`, `a and b`, `a, b and c`."""
    return (names[0] if len(names) == 1
            else ", ".join(names[:-1]) + " and " + names[-1])


def _read_as(value) -> str:
    """What the YAML reader made of a value, in words: `the number 1.5`.
    None is `NOT_TEXT_KINDS`' "no value at all", as for a leg path read out
    of a plan as no value (#181). A refusal (`_read_back`) is "nothing at
    all", in `_reading_in_words`' words (#715)."""
    if isinstance(value, YamlError):
        return _reading_in_words(value)
    if isinstance(value, bool):
        return f"the boolean {str(value).lower()}"
    if isinstance(value, (int, float)):
        return f"the number {value!r}"
    return NOT_TEXT_KINDS.get(type(value), repr(value))


def _misread_reason(text: str) -> str | None:
    """Why the project would read a leg path written as `text` back as
    something else, or None when every line it is written into reads back
    `text`.

    Each template line that holds a leg path is RENDERED with `text` by
    `render`, under its file's name, as the scaffold and `execute` render it,
    and read back by the reader the project ships (`parse_yaml`, which every
    assembly root carries a copy of). A bare line reads `2026` as a number; a
    quoted one (#259) reads it back. The sentence quotes each line that
    misreads, as rendered. Asked after `checked_value`, whose alphabet holds
    no space, quote, backslash, bracket, brace, `#`, `:`, `&`, `*` or `!`, so
    a quoted line always parses and a bare value is a plain scalar. The
    alphabet holds `@`, though, which opens no plain scalar (#393): a bare
    line of `@x` is refused, and the refusal is its reading (`_read_back`),
    said as "nothing at all" (#715).
    """
    values = dict.fromkeys(LEG_PATH_PLACEHOLDERS, text)
    misread: dict[tuple[str, str], list[str]] = {}
    reads = []
    for tree, file, line in _leg_path_lines(LEG_PATH_TEMPLATES):
        rendered = render(line, values, file).strip()
        read = _read_back(tree, file, rendered)
        if read != text:
            files = misread.setdefault((tree, rendered), [])
            if f"`{file}`" not in files:
                files.append(f"`{file}`")
            reads.append(read)
    if not misread:
        return None
    trees: dict[str, list[str]] = {}
    for (tree, rendered), files in misread.items():
        trees.setdefault(tree, []).append(
            f"as `{rendered}` in {_listed(files)}")
    where = "; ".join(
        f"the {tree.replace('-', ' ')} writes a leg path {' and '.join(lines)}"
        for tree, lines in trees.items())
    return (f"{where}, and the project's own YAML reader reads that as "
            f"{_read_as(reads[0])}, so its first bootstrap would fail")


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
    (`./.git` is not answered `.git`, nor `-x/` `-x`, nor `2026/` `2026`
    while a template line would read `2026` back as a number).
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
        checked = checked_value("leg path", candidate)
    except Refusal:
        return None
    return None if _misread_reason(checked) else checked


def leg_path_problem(what: str, value) -> str | None:
    """One leg's mount path: None when it is one `execute` will mount, else
    the sentence that says what is wrong with it and, where one exists, what
    to write instead.

    Asked in this order: the SPELLING (canonical or not), then the NAMES Git
    and Windows keep, then the alphabet `checked_value` allows on a command
    line, then whether the project reads it back as the text it is (#225),
    so that `plan`, `check` and `execute` refuse the same values.

    `what` is how the caller names the value -- `--spec-path`, or
    `legs.spec_path` for one read out of a plan -- so the sentence points at
    the thing the person has in front of them.
    """
    if not isinstance(value, str):
        # NOT "SO QUOTE IT" (#181). Quoted, the plan reads the same spelling
        # back as text, and since #259 `adopt-project.py execute` mounts the
        # leg at a directory of that very name (`2026/`, `true/`, `null/`),
        # which is the path meant only if it was meant. So the sentence asks
        # for the path meant, or for no key at all, and says nothing of
        # quotes. Only a value read out of a plan file gets here: `plan`'s
        # flags and the scaffold's are always text.
        kind = NOT_TEXT_KINDS.get(type(value), "something that is not text")
        return (f"{what} is not text: its value was read as {kind}, and a "
                "leg path is text: write the path you mean, or remove the key "
                "to mount the leg at its role's own name")
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
    misread = _misread_reason(value)
    if misread:
        return (f"{what} is {value!r}, which the project would not read back "
                f"as text: {misread}.")
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


# ---------------------------------------------------------------------------
# What a tool may write into the new project's manifest (#258, #261)
# ---------------------------------------------------------------------------
#
# `scaffold-project.py` and `adopt-project.py` fill `templates/assembly-root/`
# from values a person typed (`--id`, `--tracking-branch`, `--elected-by`,
# `--elected-on`, `--reference`, `--org`, `--name`) or edited into a plan
# (`visibility:`, `elected_by:`), and the new project then reads the result
# with two programs of its own: its YAML reader (`repo_shape`) and its
# `scripts/validate-manifest.py`. Neither tool asked either of them anything,
# so a value the project could not hold was found by the project's FIRST
# bootstrap, after the repositories existed:
#
#   * READ BACK AS SOMETHING ELSE (#258). The templates write `id:` and
#     `tracking_branch:` bare, so `--id null`, `--id true`, `--tracking-branch
#     true` and `--tracking-branch 007` became None, True and 7. The id left
#     the project's gate red; the branch was silent, each leg sitting on a
#     local `True` or `7` the remote does not have, with no upstream.
#   * REFUSED BY THE VALIDATOR (#261). A blank `--elected-by` or `--reference`,
#     `--elected-on 2026-W41-6` or `20261011` (which `date.fromisoformat` reads
#     from Python 3.11), `--org test+org`, a plan's `visibility: secret` or
#     `elected_by: null`: all accepted, and `adoption verified` or a scaffold
#     exit 0 followed by a bootstrap that said no.
#
# THE CURE IS TO ASK, BEFORE ANYTHING IS CREATED, AND TO REFUSE. The two
# questions below take the values a tool is about to record and put them
# through the very programs the project will use, so there is no second
# definition of either rule to keep in step:
#
#   `manifest_misreads`  renders each template line that carries one of the
#       values, reads that line with the project's reader (`repo_shape.
#       parse_yaml`, of which every project carries a copy) and refuses a
#       value that does not come back as the same text. The TEMPLATE says
#       which values are written bare and which quoted: a placeholder the
#       template quotes is asked as the quoted line it is, so the day the
#       templates quote `id:` and `tracking_branch:` (#259), those values
#       read back and this refuses nothing, with no edit here.
#   `manifest_invalid`   renders `project.yaml` from the whole substitution
#       table, reads it, and runs the validator the template ships
#       (`templates/assembly-root/scripts/validate-manifest.py`, loaded from
#       that file, never re-implemented) over it. Whatever the validator says,
#       now or after it learns another rule, is refused here in its words.
#
# REFUSED, NOT QUOTED OR CORRECTED, as #225, #181 and #251 refuse: a value
# the manifest cannot hold has no spelling that is the same value (`007` as a
# branch is a legal git name and a different number), and rewriting a
# person's value for them is the silent retyping this refuses. Quoting the
# templates is #259's decision, and one decision for every tool that renders
# them.
#
# IT LIVES HERE AND NOT IN `scripts/repo_shape.py` OR THE VALIDATOR, which are
# SHAPE COPIES: the materializer writes both into every project and
# `contracts/shape-pin.yaml` digests them, so a rule moved into either would
# put an `upstream-changed` row in front of every project in the estate for a
# question no project's own copy asks of itself. The validator is LOADED, so
# its definition stays the one place the rule is written.

import importlib.util  # noqa: E402
from repo_shape import YamlError, parse_yaml  # noqa: E402

#: The assembly root's template directory, and the two files in it these
#: questions read: the manifest, and the validator the project is given
#: (`MANIFEST_VALIDATOR`, named beside the copy lists that carry it).
ASSEMBLY_TEMPLATE = (Path(__file__).resolve().parent.parent / "templates"
                     / "assembly-root")
MANIFEST_TEMPLATE = "project.yaml"

#: The names this module asks of the validator: its `elected_on` pattern and
#: the function that makes every FINDING.
VALIDATOR_ASKS = ("DATE_RE", "_findings")

#: The templated files the project's reader reads: the manifest and the two
#: leg pins. The materializer's own list, so a templated YAML file added there
#: is asked about here without an edit.
TEMPLATED_YAML = tuple(rel for rel in TEMPLATED if rel.endswith(".yaml"))


def _placeholders_of(line: str) -> list[str]:
    """The names of the placeholders `render` finds in `line`.

    From `PLACEHOLDER_RE`, the pattern `render` itself uses to find one, and
    not from a second spelling of its alphabet: a template line this counted
    as one placeholder while `render` saw two would be rendered here with a
    one-key table and refused as `template-unsubstituted`. When the pattern
    is widened (#260 admits digits, for `{{SPEC_TREE_SHA256}}`) this follows.
    """
    return [token[2:-2] for token in PLACEHOLDER_RE.findall(line)]


#: The validator modules already loaded, by the file they were loaded from.
_VALIDATORS: dict = {}


def manifest_validator(template_dir: Path = ASSEMBLY_TEMPLATE):
    """The new project's own `scripts/validate-manifest.py`, as a module.

    LOADED FROM THE TEMPLATE IT IS COPIED FROM, so what is asked is the rule
    the project will apply and no second spelling of it exists. By path,
    because the filename has a hyphen and cannot be imported by name
    (`shape-doctor.py` loads the tools it asks the same way). The directory
    the validator puts at the front of `sys.path` for its own sibling imports
    is taken off again: `bootstrap` and `validate-pins` are modules of the
    project and must not shadow anything of this process's.

    NO BYTECODE IS WRITTEN. Importing a source file makes CPython write
    `scripts/__pycache__/` beside it, and this file is a TEMPLATE: a `.pyc`
    in `templates/assembly-root/` is a file nobody put there, which every
    reader of that tree then meets (`tests/test_scaffold_leg_path_collisions.py`
    reads each file under it as text). The same reason `shape-doctor.py` keeps
    the interpreter's cache out of a tree it only reads.
    """
    path = Path(template_dir) / MANIFEST_VALIDATOR
    module = _VALIDATORS.get(path)
    if module is None:
        spec = importlib.util.spec_from_file_location(
            "openreposhape_validate_manifest", path)
        module = importlib.util.module_from_spec(spec)
        saved_path, saved_flag = list(sys.path), sys.dont_write_bytecode
        sys.dont_write_bytecode = True
        try:
            spec.loader.exec_module(module)
        except Exception as exc:  # a missing, unreadable or broken file
            raise _validator_unusable(
                "could not be loaded", f"{type(exc).__name__}: {exc}"
            ) from exc
        finally:
            sys.path[:] = saved_path
            sys.dont_write_bytecode = saved_flag
        # What this module asks of it, so that a file that loads and lacks one
        # is the same refusal and not an `AttributeError` where it is used.
        for name in VALIDATOR_ASKS:
            if not hasattr(module, name):
                raise _validator_unusable(
                    "could not be used", f"it has no `{name}`")
        _VALIDATORS[path] = module
    return module


def _validator_unusable(what: str, why: str) -> Refusal:
    """The refusal for a template validator that cannot be asked, and not a
    traceback. It is a defect of the copy of the standard that was run and
    not of any value, and it is said so. Nothing was created, because the
    question is asked before anything exists; and a validator that cannot
    answer lets no manifest through unasked."""
    return Refusal(
        "manifest-validator-unusable",
        f"templates/assembly-root/{MANIFEST_VALIDATOR}, the validator this "
        f"run asks about the manifest it would write, {what}: {why}",
        "Remediation: this is a defect in the copy of this standard you ran, "
        "not in your values: the file is missing, unreadable or broken "
        "there, and nothing was created. Restore it from the standard's "
        "repository, or reinstall the standard, and run again.")


def _reading_in_words(reading) -> str:
    """What the project's reader made of a value, as a sentence says it."""
    if isinstance(reading, YamlError):
        return f"nothing at all, because it refuses the line ({reading})"
    if reading is None:
        return "no value at all"
    if isinstance(reading, bool):
        return "the boolean " + ("true" if reading else "false")
    if isinstance(reading, (int, float)):
        return f"the number {reading!r}"
    if isinstance(reading, str):
        return f"the text {reading!r}"
    return "a list" if isinstance(reading, list) else "a mapping"


def _line_shown(line: str) -> str:
    """`line` in backticks, or as Python spells it where it holds a character
    a terminal shows as something else, so that one finding stays one line."""
    return f"`{line}`" if line.isprintable() else repr(line)


def _reading_of(rendered: str):
    """What the project's reader makes of the one `key: value` line
    `rendered`: the value, the `YamlError` it raised, or the whole answer
    when it is not one key with one value (a value with a line break in it
    can carry a second key into the file)."""
    try:
        parsed = parse_yaml(rendered.lstrip() + "\n")
    except YamlError as exc:
        return exc
    if isinstance(parsed, dict) and len(parsed) == 1:
        return next(iter(parsed.values()))
    return parsed


def _misread_rows(values: dict, what: dict, template_dir: Path
                  ) -> dict[str, list[tuple]]:
    """For each placeholder of `what` whose value the project's reader would
    not read back as that same text: `(file, rendered line, reading)` for each
    template line that carries it."""
    found: dict[str, list] = {}
    for rel in TEMPLATED_YAML:
        text = (Path(template_dir) / rel).read_text(encoding="utf-8")
        for line in text.splitlines():
            keys = _placeholders_of(line)
            if (len(keys) != 1 or keys[0] not in what
                    or keys[0] not in values
                    or line.lstrip().startswith("#")):
                continue
            key, value = keys[0], str(values[keys[0]])
            rendered = render(line, {key: value}, rel).lstrip()
            reading = _reading_of(rendered)
            if not (isinstance(reading, str) and reading == value):
                found.setdefault(key, []).append((rel, rendered, reading))
    return found


def manifest_misreads(values: dict, what: dict,
                      template_dir: Path = ASSEMBLY_TEMPLATE) -> list[str]:
    """A sentence for each value the project's reader would read back as
    anything but that same text; `[]` when every one reads back.

    `values` is the substitution table; `what` names the placeholders to ask
    about and how the caller calls each (`{"PROJECT_ID": "--id"}`), and a
    placeholder it does not name is not asked: a block value
    (`NEUTRAL_PRODUCT_PINS`, a naming block) is not one line's scalar, and a
    value a rule of its own already judged is not asked twice.

    Each template line that carries exactly one of them is rendered with the
    value, as `render` writes it, and read as the project reads it.
    """
    return [
        f"{what[key]} is {str(values[key])!r}, which is written "
        + " and ".join(f"into {rel} as {_line_shown(line)}"
                       for rel, line, _ in rows)
        + ", where the project's own YAML reader reads it back as "
        + f"{_reading_in_words(rows[0][2])} and not as that text."
        for key, rows in _misread_rows(values, what, template_dir).items()]


def misread_placeholders(values: dict, what: dict,
                         template_dir: Path = ASSEMBLY_TEMPLATE
                         ) -> tuple[str, ...]:
    """The placeholders of `what` whose value `manifest_misreads` would refuse,
    for a caller that leaves those values to a misread rule of its own and
    must not have the validator's question asked a second time of them
    (`manifest_invalid`'s `not_text`)."""
    return tuple(_misread_rows(values, what, template_dir))


#: Which placeholder carries the value a finding of the validator is about,
#: for the ones a tool is handed a value for. A finding with no row is still
#: refused, in the validator's words and without a flag to point at.
FINDING_PLACEHOLDER = {
    "manifest-id": "PROJECT_ID", "manifest-topic": "PROJECT_ID",
    "manifest-name": "PROJECT_NAME", "manifest-elected-by": "ELECTED_BY",
    "manifest-elected-on": "ELECTED_ON", "manifest-reference": "REFERENCE",
    "manifest-visibility": "VISIBILITY", "manifest-leg-repository": "ORG",
}

_FINDING_RE = re.compile(r"^FINDING (?P<code>[a-z0-9-]+): (?P<detail>.*)$",
                         re.DOTALL)


def _code_of(finding: str) -> str | None:
    """The code of one `FINDING <code>: <detail>`, or None for a line that is
    not one."""
    match = _FINDING_RE.match(finding)
    return match.group("code") if match else None


def _sentences_of(findings: list[str], values: dict, what: dict,
                  not_text: tuple = ()) -> list[str]:
    """The FINDINGs of the validator as sentences: one for each value the
    caller handed over, naming it and holding every finding about it (`--org`
    is judged once for each of the three legs it names), and one for each
    finding that is about none of them. A finding about a placeholder in
    `not_text` is left out, as `manifest_invalid` says."""
    by_value: dict[str, list[str]] = {}
    sentences: list[str] = []
    for finding in findings:
        match = _FINDING_RE.match(finding)
        if match is None:
            sentences.append(finding)
            continue
        code, detail = match.group("code"), match.group("detail")
        said = f"{code}: {detail if detail.endswith('.') else detail + '.'}"
        key = FINDING_PLACEHOLDER.get(code)
        if key is not None and key in not_text:
            continue
        if key in what and key in values:
            by_value.setdefault(key, []).append(said)
        else:
            sentences.append("the manifest this run would write is one the "
                             f"project's own validate-manifest.py refuses: "
                             f"{said}")
    return [f"{what[key]} is {str(values[key])!r}, which the project's own "
            f"validate-manifest.py refuses: {' '.join(said)}"
            for key, said in by_value.items()] + sentences


def manifest_invalid(values: dict, policy: NamingPolicy, what: dict,
                     template_dir: Path = ASSEMBLY_TEMPLATE,
                     ignore: tuple = (), not_text: tuple = ()) -> list[str]:
    """A sentence for each FINDING the project's own validator would make of
    the `project.yaml` these `values` render; `[]` when it would pass.

    `ignore` is the codes of findings the CALLER already reports by a rule of
    its own in the same list (`adopt-project.py check` finds a leg path
    `plan-bad-leg-path` and must not say it a second time as the validator's
    `manifest-leg-path`); a caller that judges nothing earlier ignores none,
    so that a rule it did not apply still refuses.

    `not_text` is the placeholders whose value the caller READ as something
    that is not text (a plan's `id: 007` is the number 7, and `str` of it is
    what the template would write): that is a misread, which is judged in
    words that say what was read and never in the retyped text, so the
    validator's finding about such a value is left to that rule. A value the
    plan holds as no value at all is not one of these: `execute` writes it as
    blank, and the validator's finding about a blank is the one wanted.

    The WHOLE manifest is rendered and read, so a rule about how one value
    relates to another (`topic` to `id`, a leg's repository to its role) is
    asked as the project asks it. `values` must be the complete table;
    `policy` is the naming policy the project carries a copy of. A WARNING of
    the validator (a chain link it cannot check offline) is a note and never
    a refusal, exactly as the project's own exit code treats it, and so is
    its `  note` (a `SHAPE_PIN_SOURCE_<LINK>` the run guard passed over,
    #990). Where the project's own YAML reader refuses the file before the
    validator can be asked, each sentence is the reader's, naming the value
    on the line it refuses (`_unread_sentences`, #708).
    """
    return [sentence for _, sentence in _invalid_problems(
        values, policy, what, template_dir, ignore, not_text)]


#: The kinds of problem `manifest_value_problems` names, each spelled once
#: (#708): a value the project's reader reads back as something else, one
#: its validator refuses, and a manifest the reader refuses before the
#: validator can be asked, which `refuse_manifest_values` refuses under the
#: code `invalid` still.
KIND_MISREAD, KIND_INVALID, KIND_UNREADABLE = (
    "misread", "invalid", "unreadable")


def _invalid_problems(values: dict, policy: NamingPolicy, what: dict,
                      template_dir: Path, ignore: tuple,
                      not_text: tuple) -> list[tuple[str, str]]:
    """`manifest_invalid`'s sentences, each with its kind: `invalid` for a
    finding of the validator's, and `unreadable` where the project's own
    YAML reader refuses the file the validator would read (#708), whose
    words are the reader's and whose remedy is its own
    (`MANIFEST_UNREADABLE_REMEDIATION`)."""
    notes = _validator_notes(values, policy, template_dir, ignore)
    if isinstance(notes, YamlError):
        return [(KIND_UNREADABLE, sentence) for sentence
                in _unread_sentences(values, what, template_dir, notes)]
    return [(KIND_INVALID, sentence)
            for sentence in _sentences_of(notes, values, what, not_text)]


#: The placeholders that carry a value of `what` into the manifest where no
#: line holds that value's own placeholder (#708): the organisation is the
#: owner half of each leg's `repository:`, so the reader's refusal of such a
#: line is `--org`'s, as the validator's finding about it is
#: (`FINDING_PLACEHOLDER`'s `manifest-leg-repository`).
CARRIED_BY = {"ASSEMBLY_REPOSITORY": "ORG", "SPEC_REPOSITORY": "ORG",
              "CODE_REPOSITORY": "ORG"}


def _unread_sentences(values: dict, what: dict, template_dir: Path,
                      refusal: YamlError, manifest: str = MANIFEST_TEMPLATE,
                      carried_by: dict | None = None,
                      reader: str = "the project's own YAML reader"
                      ) -> list[str]:
    """A sentence for each value of `what` that a line of the manifest the
    project's own reader refuses carries, in the reader's words, and the
    reader's `refusal` of the whole file where no such line is found.

    `manifest`, `carried_by` (`CARRIED_BY` when None) and `reader`, the
    words that name the reader, are the project's unless the caller gives
    its own: `family.py init` asks it of the holder's `family.yaml`, whose
    `repository:` carries `--org` (#929).

    THE VALUE IS NAMED AGAIN (#708). Until #392 and #393 the reader took
    `repository: @x/Atlas` for text, so `--org @x` reached the validator,
    whose `manifest-leg-repository` names `--org`. Since then the reader
    refuses the file first, and the sentence named nothing: `plan --org
    @x` (a typo of `@opensoft`, where GitHub owners never begin with `@`)
    said only that the manifest was a file the reader refuses. So each
    template line that carries a value of `what` (by its own placeholder,
    or by one `CARRIED_BY` names) is rendered and read alone, as
    `_misread_rows` reads one, and a value is named where the reader
    refuses one of its lines.
    """
    carried_by = CARRIED_BY if carried_by is None else carried_by
    said: dict[str, list[str]] = {}
    template = (Path(template_dir) / manifest).read_text(encoding="utf-8")
    for line in template.splitlines():
        carried = {carried_by.get(key, key) for key in _placeholders_of(line)}
        named = [key for key in what if key in carried and key in values]
        if not named or line.lstrip().startswith("#"):
            continue
        reading = _reading_of(render(line, values, manifest))
        if isinstance(reading, YamlError):
            for key in named:
                said.setdefault(key, []).append(f"{reading}.")
    if not said:
        return ["the manifest this run would write is a file "
                f"{reader} refuses: {refusal}."]
    return [f"{what[key]} is {str(values[key])!r}, which {reader} refuses: "
            f"{' '.join(words)}" for key, words in said.items()]


def _validator_notes(values: dict, policy: NamingPolicy, template_dir: Path,
                     ignore: tuple) -> list[str] | YamlError:
    """The FINDINGs the project's own validator makes of the `project.yaml`
    these `values` render, less its WARNINGs, its `  note`s and the codes
    in `ignore`; or the `YamlError` its reader raised, where it cannot read
    that file. A `  note` is no finding, as the validator's own `main`
    counts it (#990): `_findings` returns its `link-source-collides` note
    beside the findings, and read as one, `manifest_invalid` gave it as a
    refusal and `manifest_judged` said None (RV1011's SHOULD-1)."""
    template = (Path(template_dir) / MANIFEST_TEMPLATE).read_text(
        encoding="utf-8")
    try:
        manifest = parse_yaml(render(template, values, MANIFEST_TEMPLATE))
    except YamlError as exc:
        return exc
    validator = manifest_validator(template_dir)
    try:
        notes = validator._findings(manifest, policy, None)
    except Exception as exc:  # the validator's own defect, never a finding
        raise _validator_unusable(
            "raised when it was asked", f"{type(exc).__name__}: {exc}"
        ) from exc
    return [note for note in notes
            if not note.startswith(("WARNING", "  note "))
            and _code_of(note) not in ignore]


def manifest_judged(values: dict, policy: NamingPolicy,
                    template_dir: Path = ASSEMBLY_TEMPLATE,
                    ignore: tuple = ()) -> frozenset[str] | None:
    """The placeholders whose value the project's own validator makes a
    finding about, in the `project.yaml` these `values` render (the
    question `manifest_invalid` asks, with the same `ignore`); an empty set
    when it makes none.

    None where it cannot be told of ANY value that the validator passes it:
    its reader refuses the whole file, or it makes a finding that is about
    no one placeholder (`FINDING_PLACEHOLDER`), whatever value caused it.
    A caller with a rule of its own about the same values (`adopt-project.py`
    #181's misread) leaves to the validator every value it judges, and every
    value at all where this is None, so that one value is never two
    findings and no sentence of that rule's says the validator passes a
    value it refuses.
    """
    notes = _validator_notes(values, policy, template_dir, ignore)
    if isinstance(notes, YamlError):
        return None
    judged = {FINDING_PLACEHOLDER.get(_code_of(note)) for note in notes}
    return None if None in judged else frozenset(judged)


#: The remediation, without the sentence only the caller can write (what was
#: or was not created, whether `--dry-run` refuses the same).
#:
#: WHAT IT SAYS IS ONLY WHAT HOLDS FOR EVERY VALUE THE RULE REFUSES: the
#: project's reader reads back something other than what was typed. What that
#: does next differs by value and by reader, and it is NOT always a failure.
#: `--tracking-branch 2026` and `1.5` scaffold, bootstrap and get their
#: upstream today, because every reader of `tracking_branch` does `str()` and
#: `str(2026)` is `2026` again (while `007` reads back as `7`, `1.50` as
#: `1.5` and `0` as `main`). So the text names only the failures that do hold
#: (an id that is not text fails the validator; `007` as a branch becomes the
#: branch `7`) and says that a number which survives `str()` works because of
#: the reader and is still a number to the project's own.
MANIFEST_MISREAD_REMEDIATION = (
    "Remediation: choose another value for each one named, as nothing here "
    "will retype it for you. The templates write these values unquoted, so "
    "the project's own YAML reader takes `null` and `~` for no value, `true` "
    "and `false` for booleans, and `007`, `2026` or `1.5` for numbers: what "
    "it reads back is not what was typed. What that does differs: an id "
    "that is not text fails the project's own validate-manifest.py, and "
    "`007` as a branch reads back as the branch `7`; `2026` or `1.5` as a "
    "branch happens to work today, because the tools that read it turn the "
    "number back into text, but it is still a number to the project's "
    "reader and not a name. A value the reader takes for text (`atlas`, "
    "`release-2026`, `v2`) passes.")
MANIFEST_INVALID_REMEDIATION = (
    "Remediation: choose a value the project's own validate-manifest.py "
    "accepts; the words after each value are the validator's own, and a "
    "project it refuses is one whose first bootstrap would fail.")
#: Where the project's own YAML reader refuses the manifest before its
#: validator can be asked (#708), the words are the reader's, and a sentence
#: may name no value (`_unread_sentences`), so the remedy says neither that
#: they are the validator's nor that a value is always named. Its first
#: sentence is `UNREADABLE_CHOICE`, which `family.py init`'s remedy for the
#: holder's reader opens with too (#929).
UNREADABLE_CHOICE = (
    "Remediation: choose another value for each one named; where none is "
    "named, the text the reader's words quote holds it.")
MANIFEST_UNREADABLE_REMEDIATION = (
    f"{UNREADABLE_CHOICE} The words are the project's own YAML reader's, "
    "which refuses the manifest this run would write before its "
    "validate-manifest.py can be asked, and a project whose manifest it "
    "refuses is one whose first bootstrap would fail.")
#: The remedy for each kind of problem, so a refusal names it by its kind
#: (#708), with no conditional nested in another.
KIND_REMEDIATIONS = {KIND_MISREAD: MANIFEST_MISREAD_REMEDIATION,
                     KIND_INVALID: MANIFEST_INVALID_REMEDIATION,
                     KIND_UNREADABLE: MANIFEST_UNREADABLE_REMEDIATION}


def manifest_value_problems(values: dict, policy: NamingPolicy, what: dict,
                            *, misreads: bool = True, ignore: tuple = (),
                            not_text: tuple = (),
                            template_dir: Path = ASSEMBLY_TEMPLATE
                            ) -> list[tuple[str, str]]:
    """`(kind, sentence)` for everything wrong with the values, `kind` being
    `misread`, `invalid` or `unreadable` (`_invalid_problems`); `[]` when
    the project would hold every one.

    A misread comes FIRST and alone: a value the reader turns into something
    else makes the manifest invalid in ways that are its consequence (`id:
    null` fails the validator as `id is None`), so the sentence about the
    value itself is the one worth reading. `misreads=False` asks only the
    validator's question, for a tool whose YAML-misread rule is its own.
    """
    if misreads:
        misread = manifest_misreads(values, what, template_dir)
        if misread:
            return [(KIND_MISREAD, sentence) for sentence in misread]
    return _invalid_problems(values, policy, what, template_dir, ignore,
                             not_text)


def refuse_manifest_values(prefix: str, values: dict, policy: NamingPolicy,
                           what: dict, tail: str, *,
                           misreads: bool = True) -> None:
    """Raise `Refusal(<prefix>-manifest-misread)` or `<prefix>-manifest-
    invalid`, naming every value, when the project could not hold them; the
    caller's own `prefix` (`scaffold`, `adopt`) says which tool refused, and
    its `tail` finishes the remediation with what only it knows. A manifest
    the project's reader refuses is `-invalid` still, the code a value it
    refuses had when the validator was the one to refuse it, with the
    reader's remedy (#708)."""
    problems = manifest_value_problems(values, policy, what,
                                       misreads=misreads)
    if problems:
        kind = problems[0][0]
        code = KIND_MISREAD if kind == KIND_MISREAD else KIND_INVALID
        raise Refusal(f"{prefix}-manifest-{code}",
                      " ".join(sentence for _, sentence in problems),
                      f"{KIND_REMEDIATIONS[kind]} {tail}")


# ---------------------------------------------------------------------------
# A repository's name is also a directory's (#261), and GitHub's (#838)
# ---------------------------------------------------------------------------
#
# `checked_value` holds a name to 255 characters, `SAFE_ARG_RE`'s limit, and
# the tools then make a directory of it: `<work-dir>/<name>` for each of the
# three, and under `--local-remote-dir` a bare `<name>.git` beside them. A
# name is at most 255 bytes on ext4, APFS and NTFS alike, so a `--project` of
# 247 to 250 characters passed every check and died in `Path.exists` with
# `OSError: File name too long`, a traceback and exit 1, where the first
# directory is asked about; the scaffold died the same way from 247, and from
# 251 characters in the work directory, where adopt's `check` had already
# refused the name `legs.spec` with `unsafe-value`.
#
# GITHUB KEEPS A NAME SHORTER STILL, AND A TOPIC AND AN OWNER TOO (#838). A
# repository's name is at most 100 characters and a topic at most 50, both
# documented on docs.github.com. For 39, the docs give the limit on a user's
# name (Enterprise Cloud's username considerations), and nothing for an
# organisation's; 39 is asked of both. No run of this repository has measured
# any of the three: none creates a real repository, and a probe against a real
# organisation is another lane's. Nothing asked them. A `--project` of 96 to
# 250 characters (250 makes the longest `-spec` a directory can be named), or
# an `--org` of 40 to 255, passed the plan and met GitHub's refusal at the
# first `gh repo create`, with nothing made yet. An id over 39 characters,
# which a `--project` of 40 or more gives by default, passed the plan, and the
# scaffold created and seeded all three repositories before `gh repo edit
# --add-topic` failed, last; `adopt-project.py execute` failed there after both
# legs and the split were pushed. Each is asked before anything is created now,
# and only where a GitHub repository will be made: under `--local-remote-dir`
# nothing goes to GitHub, the limit on a name is the disk's, and no topic is
# set. `setup-project.py` cannot import this module (it runs before there is a
# checkout to import it from), so it says the same numbers in its own `--help`,
# and `tests/test_github_name_limits.py` holds the two to one number.

#: The longest name a file or a directory may have, in bytes.
NAME_MAX = 255

#: The longest name GitHub gives a repository, in characters.
GITHUB_NAME_MAX = 100
#: The longest topic GitHub sets on a repository, in characters.
GITHUB_TOPIC_MAX = 50
#: The longest name GitHub gives a user or an organisation, in characters.
GITHUB_OWNER_MAX = 39
#: The longest `<Project>` GitHub can hold a project's repositories under:
#: `<Project>-spec` and `<Project>-code` are five characters longer.
GITHUB_PROJECT_MAX = GITHUB_NAME_MAX - len("-spec")
#: The longest id whose topic, `xf-project-<id>`, GitHub sets.
GITHUB_ID_MAX = GITHUB_TOPIC_MAX - len(TOPIC_PREFIX)

#: What GitHub keeps a project's names to, as a remediation says it: the
#: repositories' names, and the id, by the topic it gives. A name refused
#: for GitHub's limit says the id's too: the default id is the project name
#: lowercased, so whoever picks a shorter name learns both numbers at once.
GITHUB_LIMITS = (
    f"GitHub keeps a repository's name to at most {GITHUB_NAME_MAX} "
    f"characters, so a project name is at most {GITHUB_PROJECT_MAX}, and a "
    f"topic to at most {GITHUB_TOPIC_MAX}, so the id in the topic "
    f"`{TOPIC_PREFIX}<id>`, which is the project name lowercased unless --id "
    f"is given, is at most {GITHUB_ID_MAX}")


def _both_ends(name: str) -> str:
    """`name` as a refusal shows it: whole, or cut in the middle. BOTH ENDS:
    a name this long differs from the others by its tail, `-spec` or
    `-code`, which a cut at the front loses."""
    return name if len(name) <= 27 else f"{name[:12]}...{name[-12:]}"


def refuse_unstorable_names(refusal: str, directories: list[str],
                            bare: list[str] = (),
                            github: list[str] = ()) -> None:
    """Raise `Refusal(refusal)` when a repository name cannot be a directory
    name: each of `directories` is made as it stands under the work
    directory, each of `bare` as `<name>.git` under `--local-remote-dir`;
    or when GitHub will not give it to a repository: each of `github` is
    created there, by `gh repo create` (#838). The caller passes `github`
    only where GitHub is asked, never under `--local-remote-dir`."""
    problems, unstorable = [], set()
    for names, suffix, where in (
            (directories, "", "the directory this run makes for it under "
                              "its work directory"),
            (bare, ".git", "the bare repository's directory under "
                           "--local-remote-dir")):
        for name in names:
            size = len(f"{name}{suffix}".encode("utf-8"))
            if size > NAME_MAX:
                unstorable.add(name)
                problems.append(
                    f"{_both_ends(name)}{suffix} is {size} bytes long, and "
                    f"{where} may be at most {NAME_MAX}")
    # A name the disk cannot hold is not named again for GitHub's limit,
    # which it breaks too: the remediation below states both numbers.
    on_github = [f"{_both_ends(name)} is {len(name)} characters, and GitHub "
                 f"keeps a repository's name to at most {GITHUB_NAME_MAX}"
                 for name in github
                 if len(name) > GITHUB_NAME_MAX and name not in unstorable]
    if problems or on_github:
        # EACH LIMIT A NAME BROKE, AND ONLY THOSE: the disk's, GitHub's, or
        # both, for a name too long for either.
        limits = [f"a disk keeps a name of at most {NAME_MAX} bytes, which "
                  "under --local-remote-dir includes the `.git` each bare "
                  "repository adds"] if problems else []
        if on_github:
            limits.append(GITHUB_LIMITS)
        raise Refusal(
            refusal, "; ".join(problems + on_github) + ".",
            "Remediation: nothing was created. Use a shorter --project: the "
            "three repositories are named `<Project>`, `<Project>-spec` and "
            "`<Project>-code`, and " + "; and ".join(limits) + ".")


def refuse_a_topic_github_cannot_set(refusal: str, topic: str,
                                     project_id: str, named: str,
                                     remediation: str) -> None:
    """Raise `Refusal(refusal)` when GitHub will not set `topic`, the
    `xf-project-<id>` a run sets on each repository it makes: GitHub keeps a
    topic to `GITHUB_TOPIC_MAX` characters (#838). The topic is set LAST,
    after the repositories exist, so it is asked before any is made.

    `project_id` is the id the topic carries, `named` how the caller names
    it (the flag, or where its value came from), and `remediation` the
    caller's own way out. Asked only where GitHub is: under
    `--local-remote-dir` no topic is set. The id's own bound is read off
    the topic, so it is the policy's template that decides it."""
    if len(topic) <= GITHUB_TOPIC_MAX:
        return
    prefix = topic[:len(topic) - len(project_id)]
    raise Refusal(
        refusal,
        f"{named} is {_both_ends(project_id)}, {len(project_id)} characters, "
        f"so the topic this run sets on each repository, `{prefix}<id>`, is "
        f"{len(topic)}, and GitHub keeps a topic to at most "
        f"{GITHUB_TOPIC_MAX}: an id is at most "
        f"{GITHUB_TOPIC_MAX - len(prefix)} characters",
        remediation)


def refuse_an_owner_github_cannot_have(refusal: str, owner: str, named: str,
                                       remediation: str) -> None:
    """Raise `Refusal(refusal)` when `owner`, the organisation the run
    creates repositories in, is longer than any name GitHub gives a user or
    an organisation, `GITHUB_OWNER_MAX` characters (#838): no repository can
    be created under it. `named` is how the caller names it, and
    `remediation` its own way out. Asked only where GitHub is: under
    `--local-remote-dir` the organisation names no account."""
    if len(owner) <= GITHUB_OWNER_MAX:
        return
    raise Refusal(
        refusal,
        f"{named} is {_both_ends(owner)}, {len(owner)} characters, and "
        "GitHub keeps a user's or an organisation's name to at most "
        f"{GITHUB_OWNER_MAX}, so no repository can be created under it",
        remediation)


# An organisation's characters, as GitHub gives them (#863). `checked_value`
# admits `SAFE_ARG_RE`'s whole alphabet, and the manifest validator's
# `QUALIFIED_RE` takes `_` and `.` anywhere after an owner's first character,
# so `--org my_org.x`, `--org trail-` and `--org a--b` passed every plan and
# went on to `gh repo create my_org.x/<name>`. GitHub's documented rule for a
# user's or an organisation's name is ASCII letters, digits and single
# hyphens, with no hyphen at either end; it is not measured here. A leading
# hyphen is `checked_value`'s refusal already, so the rule left to ask is a
# character outside it, a trailing hyphen and two hyphens in a row. `_` IS
# LET BY: a GitHub Enterprise Managed User's login holds one
# (`<handle>_<shortcode>`), so a rule that refuses it may refuse a personal
# namespace that exists, and refusing it waits on a probe against a real
# account. The rule is asked by the tools' plans, beside the 39, and is not
# put in the pinned `scripts/repo_shape.py` or the two validators, so no
# project is re-pinned and a manifest that already names such an owner still
# reads as it did.

#: The characters this asks of an owner's name: GitHub's, and `_` (above).
GITHUB_OWNER_CHARACTERS = re.compile(r"[A-Za-z0-9_-]")


def refuse_an_owner_github_cannot_spell(refusal: str, owner: str, named: str,
                                        remediation: str) -> None:
    """Raise `Refusal(refusal)` when `owner`, the organisation the run
    creates repositories in, holds a character GitHub gives no user's or
    organisation's name, ends in a hyphen or holds two hyphens in a row
    (#863): no repository can be created under it. `named` is how the
    caller names it, and `remediation` its own way out. Asked only where
    GitHub is, beside `refuse_an_owner_github_cannot_have`: under
    `--local-remote-dir` the organisation names no account."""
    held = "".join(dict.fromkeys(
        char for char in owner if not GITHUB_OWNER_CHARACTERS.fullmatch(char)))
    problems = []
    if held:
        shown = [f"`{char}`" for char in held]
        problems.append("holding " + (
            f"{', '.join(shown[:-1])} or {shown[-1]}" if len(shown) > 1
            else shown[0]))
    if owner.endswith("-"):
        problems.append("ending in a hyphen")
    if "--" in owner:
        problems.append("with two hyphens in a row")
    if not problems:
        return
    # A VALUE PAST THE LENGTH BOUND IS SHOWN CUT, as
    # `refuse_an_owner_github_cannot_have` shows it (#871's review, N3):
    # `check` lists this refusal beside that one, which cuts it, and this
    # one printed all of a 255-character `org:`. `_both_ends` keeps the
    # tail, where a trailing hyphen is, and the problems above name every
    # character, wherever the cut took it from.
    shown = (repr(owner) if len(owner) <= GITHUB_OWNER_MAX
             else f"{_both_ends(owner)}, {len(owner)} characters")
    raise Refusal(
        refusal,
        f"{named} is {shown}, and GitHub gives no user or organisation a "
        f"name {', or '.join(problems)}, so no repository can be created "
        "under it",
        remediation)
