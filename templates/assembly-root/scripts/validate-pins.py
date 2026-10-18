#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""THE LOCKSTEP VALIDATOR — three things move in one commit, or this refuses.

For every leg of this project, THREE facts name the same commit and they are
advanced TOGETHER, in ONE commit, or not at all:

    1. the GITLINK      — the `160000` entry this repository records for the
                          submodule at the leg's path
    2. the PIN FILE     — `commit:` in `contracts/<role>-pin.yaml`
    3. every WORKFLOW `@<sha>` REFERENCE naming that leg's repository, in
       `.github/workflows/*.yml`

This is not a hypothesis. In the xFactory aggregation the same invariant
(gitlink, `review-lane-reusable.yml@<sha>`, and a `PIN` constant in a test) was
practice for months and written down nowhere; seven consecutive pin-syncs from
2026-08-25 moved the gitlink alone and left the `validate` check red on every
pull request until 2026-08-26 — unnoticed for a day because `validate` runs on
pull requests only, so `main` never reported it and the breakage surfaced on
somebody else's change. Shipping the check in the template is what turns that
into a one-time scaffold cost instead of a per-project tribal rule.

The DIGEST is checked too: the pin records the sha256 of the leg's tree at the
pinned commit under the `sorted-ls-tree-r-v1` definition, recomputed here from
the submodule's own object store. A gitlink and a pin file that agree on a
commit whose bytes are not the bytes the pin was written against is drift the
commit comparison alone cannot see.

NEUTRAL-PRODUCT PINS ARE RECHECKED TOO. `project.yaml`'s `neutral_product_pins:`
names every `open<Product>` this project declares descent from; each name's
`contracts/<product lowercased>-pin.yaml` is a claim of descent with a REFERENT
(2026-09-02) and this recomputes it the same way `scaffold-project.py` computed
it in the first place — OFFLINE from a local checkout when one is findable
(`--pin-source`, `SHAPE_PIN_SOURCE_<PRODUCT>`, or a checkout sitting beside this
assembly root), else from `gh api` when `gh` is authenticated. Neither is
available, this is a SKIP with a named notice, never a failure: a project with
no network and no local checkout of the product is not thereby lying about its
descent, and this check must never punish the absence of what would answer it.
A source somebody NAMED is the other way round (#295): a `--pin-source` or
`SHAPE_PIN_SOURCE_<PRODUCT>` that cannot answer is a FINDING, and a
`--pin-source` no declared pin used is a note.

EXIT CODES
    0  every leg's three facts agree, every digest recomputes, and no
       recheckable neutral-product pin disagrees
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — an uninitialized submodule,
       an unresolvable commit, an unreadable pin, manifest, workflow file or
       pinned shape copy (one that is not UTF-8, or that this user cannot
       open or reach, #712), or a `.github/workflows/` directory this user
       cannot list or search (#434). An unanswerable pin question is never an
       implicit pass.
       No git to run is one too (`git-not-runnable`, #412), a git that is
       missing, will not run or cannot be executed: the gitlinks and the
       digests are read through git.
"""

from __future__ import annotations

import argparse
import errno
import os
import re
import shlex
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
#: The interpreter the `pin-gitlink-mismatch` repair lines name (#478).
from repo_shape import PYTHON  # noqa: E402
from repo_shape import (  # noqa: E402
    COMMIT_RE, SHA256_RE, TREE_DIGEST_DEFINITION, Refusal, file_sha256,
    find_repo_root, git_out, load_yaml, pin_product_key,
    pin_source_env_collisions, pin_source_env_name, pin_source_env_shared,
    recorded_gitlink, repo_basename, tree_digest, tree_digest_from_gh,
)
#: The lockstep remedy, which is this validator's own (#370): see `main`.
from repo_shape import REMEDIATION  # noqa: E402

# `PIN_SOURCE_ENV_PREFIX` / `pin_source_env_name` live in `repo_shape` because
# the SAME checkout answers two questions about a neutral product: the digest
# recomputed here, and the chain-link declaration `NamingPolicy` verifies
# (2026-09-05). Two definitions of one variable name is how the second one
# starts disagreeing with the first.

#: `owner/repo[/path]@<40 hex>` as it appears in a `uses:` line.
WORKFLOW_REF_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?P<path>/[^@\s'\"]*)?"
    r"@(?P<sha>[0-9a-fA-F]{40})"
)

LOCKSTEP = (
    "THE LOCKSTEP RULE: a leg's gitlink, its `contracts/<role>-pin.yaml` "
    "`commit:`, and EVERY `.github/workflows/*.yml` reference of the form "
    "`<org>/<leg>/...@<sha>` are ONE invariant. Move all three in ONE commit "
    "or the next pull request is red on somebody else's change."
)

#: The findings THE LOCKSTEP RULE is about (#539): the three facts it names,
#: out of step, and the pin's digest of the commit they name. The rule ends
#: each of them, and the closing count only where one of them was found: a
#: lone `shape-copy-drift` is an edited copy, not a leg moved alone.
LOCKSTEP_CODES = frozenset({"pin-gitlink-mismatch", "pin-digest-mismatch",
                            "pin-workflow-ref-mismatch"})


class Curable(NamedTuple):
    """A `pin-digest-mismatch` or a `pin-workflow-ref-mismatch`, for
    `_end_curable_findings` (#539): where it is in `findings`, the leg, the
    commit its gitlink and its pin name, and a reference's own commit (None
    for a digest)."""

    index: int
    role: object
    path: str
    commit: str
    reference: str | None


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []
        #: Each finding's code, and the role of the leg whose `bump-leg.py`
        #: line puts it right, or None: in step with `findings` (#478).
        self.cleared_by: list[tuple[str, object]] = []
        #: Each `pin-gitlink-mismatch`, as `(its index in findings, role,
        #: path, gitlink, pin commit)`, for `_end_gitlink_mismatches` (#478).
        self.mismatches: list[tuple[int, object, str, str, str]] = []
        #: Each `pin-digest-mismatch` and `pin-workflow-ref-mismatch`, for
        #: `_end_curable_findings` (#539).
        self.curable: list[Curable] = []

    def finding(self, code: str, detail: str, leg=None) -> None:
        """`leg` is the role of the leg a `bump-leg.py` line moves when that
        line also clears this finding: the leg's gitlink against its pin,
        its pin's digest, and a workflow reference to its repository, the
        three facts it rewrites (#478)."""
        self.findings.append(f"FINDING {code}: {detail}")
        self.cleared_by.append((code, leg))

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")

    def skip(self, text: str) -> None:
        """An entry this run could not answer for, by design rather than by
        drift — printed, but never a FINDING and never the reason for a
        nonzero exit. A network absence is not evidence of anything."""
        self.notes.append(f"  skip {text}")

    def advise(self, text: str) -> None:
        """A NOTE: something a person should know that is no fault of the
        project's — printed beside the skips and, like them, never a FINDING
        and never the reason for a nonzero exit."""
        self.notes.append(f"  note {text}")

    def unused(self, text: str) -> None:
        """A `--pin-source` no declared pin read (#295): the person named a
        source that did not answer, and nothing about any pin is wrong for
        that. A note, as every one of those is."""
        self.advise(text)


class _Unreadable(NamedTuple):
    """One workflow file that could not be read (#359): the line that names it,
    whether it failed on its ENCODING (`True`) or on being opened, and, for
    one that could not be opened, whether the operating system refused a
    PERMISSION (#712): any other cause gets its own advice, not `chmod`."""

    line: str
    encoding: bool
    permission: bool = False


def _read_workflow(root: Path, path: Path) -> tuple[str, _Unreadable | None]:
    """`(text, None)` for a workflow file read as UTF-8, or `("", why)` for one
    that cannot be (#359).

    The line is `<path relative to root>: not UTF-8 at byte N (<reason>)`, in
    the words `repo_shape.load_yaml` gives the same failure (#192), so a file
    this script cannot read is named the way its other readers name one.
    POSIX, on every platform, and never the absolute path: the reader pastes
    it into git and into an editor that opens it from the root.
    A file this user cannot open (`OSError`) is the same line with the
    operating system's own reason, because it is the same unguarded read.
    The name is spelled as `_named` spells it (#712): a newline in it began a
    line of its own, and a bidi control reordered the line it was printed on.
    """
    rel = _named(root, path)
    try:
        return path.read_text(encoding="utf-8"), None
    except UnicodeDecodeError as exc:
        return "", _Unreadable(
            f"{rel}: not UTF-8 at byte {exc.start} ({exc.reason})", True)
    except OSError as exc:
        return "", _Unreadable(_cannot_read(rel, exc), False,
                               isinstance(exc, PermissionError))


def _workflow_unreadable(files: list[_Unreadable]) -> Refusal:
    """The ONE refusal for every workflow file that could not be read (#359).

    EVERY FILE IS NAMED, in one refusal, so the operator repairs them in one
    pass instead of meeting them one run at a time; `_workflow_refs` reads
    them all before it raises. The first line follows the id and the rest
    follow it, one file to a line, so `shape-doctor.py`, which quotes the
    first `REFUSED` line of this script's output, quotes a file's name.

    THE ADVICE FOLLOWS THE CAUSE (#712), as the directory's does (#434):
    "restore read access" was said of every `cannot be read` file, and a
    file whose `stat` or read failed with an I/O error or a name too long
    is not put right by a mode. A permission keeps its sentence; any other
    cause gets `OTHER_REASON`, the words `bump-leg.py` gives it (#383).
    """
    advice = ""
    if any(one.encoding for one in files):
        advice += (
            "In each `not UTF-8` line the byte is counted from 0 at the start "
            "of the file and is the first that is not UTF-8: re-save the file "
            "as UTF-8 (a UTF-16 file with a byte-order mark needs converting, "
            "not editing), or replace that byte with the character it was "
            "meant to be, and commit it. ")
    if any(one.permission for one in files):
        advice += (
            "A `cannot be read` file is not an encoding failure: this user "
            "cannot open it, so restore read access to it, and search access "
            "to every directory above it inside the root (a file in a "
            "directory this user can list but not search cannot be opened). ")
    if any(not one.encoding and not one.permission for one in files):
        advice += OTHER_REASON
    return Refusal(
        "workflow-unreadable",
        "\n".join(one.line for one in files),
        f"Remediation: {len(files)} workflow file(s) under "
        ".github/workflows/ cannot be read, and every one is named above. "
        "This validator reads every `.yml` and `.yaml` file there, whether or "
        "not it names a leg, and neither skips one nor reads one lossily: a "
        "workflow it skipped could hide a `@<sha>` reference that is out of "
        "lockstep, which is what it exists to find, and a lossy read would "
        "call green a tree that the project's other readers refuse. "
        + advice + RUN_AGAIN)


#: The `OSError`s that `Path.is_file()` and `Path.is_dir()` answered False to
#: on Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name to open: no such file, a part of the path that is
#: not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". Every other one was raised.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)


def _is_a(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `stat.S_ISDIR`),
    raising the `OSError` of a `stat` the operating system REFUSED (#434).

    NOT `Path.is_file()` OR `Path.is_dir()`, whose answer depends on the
    Python. Up to 3.13 they raised a refused `stat` (`PermissionError`) and
    answered False only when nothing was there; from 3.14 they call
    `os.path.isfile` and `isdir`, which answer False to ANY `OSError`. On
    3.14 a `.github/` this user cannot search read as "no workflows", and
    every file of a workflows directory it can list but not search read as
    "not a file": `pins ok` over workflows nobody read, which is the one
    thing this validator exists to prevent. Asked here, every Python answers
    as 3.9 to 3.13 did, and a refused `stat` is an error that is named. The
    same reason `_digest_from_source` gives for its own `stat()`.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    return kind(mode)


def _named(root: Path, path: Path) -> str:
    """`path` as this validator names a file (#712): relative to `root`, POSIX
    on every platform, as #633's `workflow-unreadable` lines are, and spelled
    by `_shown`, so a name holding a newline, a bidi or C1 control, an ESC or
    a byte that is not UTF-8 prints as `repr` spells it and stays on its
    line. A path that is not under the root (a role or a product spelled as
    an absolute path) is named whole, since `relative_to` would end the run
    in a `ValueError`."""
    try:
        return _shown(path.relative_to(root).as_posix())
    except ValueError:
        return _shown(str(path))


def _cannot_read(named: str, exc: OSError) -> str:
    """`<named>: cannot be read (<the operating system's reason>)`: the line
    for a file whose `stat` or open the operating system refused, in every
    refusal that names one (#359, #434, #712)."""
    return f"{named}: cannot be read ({exc.strerror or type(exc).__name__})"


#: What a file the operating system refused for ANOTHER reason than
#: permission is told (#712): an I/O error, a name longer than the
#: filesystem takes, a file replaced while this ran. No `chmod` puts one
#: right. `bump-leg.py`'s words for the same refusal (#383).
OTHER_REASON = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. ")

#: The sentence every refusal of a file or directory this validator cannot
#: read ends on, said once (#712).
RUN_AGAIN = "Then run the same command again."

#: What this validator reads, as `_unreadable_file`'s remedy says it.
FILES_READ = ("each leg's pin, the shape pin, each neutral-product pin, "
              "project.yaml and every copy the shape pin lists")


def _remedy(advice: str, reads: str = FILES_READ) -> str:
    """The remedy of a refusal of a file this validator must read and
    cannot (#712, #919): what it reads (`reads`), that one it cannot read is
    never a pass, `advice` for the cause, and `RUN_AGAIN`."""
    return (f"Remediation: this validator reads {reads}, and one it cannot "
            "read is a question it cannot answer, never a pass. " + advice
            + RUN_AGAIN)


def _unreadable_file(code: str, named: str, exc: OSError,
                     reads: str = FILES_READ) -> Refusal:
    """The refusal for a pin, the manifest or a pinned shape copy that this
    validator must read and the operating system will not let it (#712):
    its `stat` refused (a `contracts/` this user cannot search) or its open
    refused (a pin at mode 000).

    NAMED ONCE, RELATIVE TO THE ROOT. A pin this user could not open was
    `load_yaml`'s line, `<absolute path>: [Errno 13] Permission denied:
    '<absolute path>'`, under THE LOCKSTEP RULE's remedy, which moves a pin
    and says nothing of access. This is `_cannot_read`'s line, with a remedy
    of its own, so `main` adds no other.

    THE ADVICE FOLLOWS THE CAUSE, in `bump-leg.py`'s words for the same
    file (#383): a permission (`PermissionError`, which is `EACCES` and
    `EPERM`) is put right by the mode or the owner, and any other cause is
    `OTHER_REASON`, which is not told to `chmod`. `reads` names what the
    validator reads, a leg's checkout where that is what it cannot reach.
    """
    advice = (
        "Make what this user may not open readable by this user: `chmod u+r` "
        "on a file, `chmod u+rx` on a directory (and on every directory above "
        "it inside the root), or fix who owns it. "
        if isinstance(exc, PermissionError) else OTHER_REASON)
    return Refusal(code, _cannot_read(named, exc), _remedy(advice, reads))


def _is_file(root: Path, path: Path, code: str = "yaml-unreadable",
             named: str | None = None) -> bool:
    """Whether `path` is a file, asked as `_is_a` asks it, or `code`'s
    refusal naming it (`named`, else `_named`) where its `stat` was refused
    (#712). The four `is_file()` calls on a pin and the manifest, and the
    one on each shape copy, are this.

    `Path.is_file()` raised a refused `stat` out of the run on Python 3.9 to
    3.13, so a `contracts/` this user could not search ended in a
    `PermissionError` traceback, exit 1; on 3.14 it answered False, and the
    run refused `pin-missing`, a present file said not to exist, under the
    lockstep remedy. A name the operating system cannot take at all (a NUL
    in a role or a product) is no file, as `is_file()` answered it. Where
    this is False, each caller asks `_not_a_file` what stands there (#919)."""
    try:
        return _is_a(path, stat.S_ISREG)
    except OSError as exc:
        raise _unreadable_file(code, named or _named(root, path),
                               exc) from exc
    except ValueError:
        return False


def _is_there(path: Path) -> bool:
    """Whether anything is at `path` (a checkout's `.git`, a file or a
    directory), asked as `_is_a` asks it, raising the `OSError` of a `stat`
    the operating system refused (#712, after RV827's S1).

    NOT `Path.exists()`, which raised a refused `stat` out of the run up to
    Python 3.13, so a leg checkout or a checkout beside the root that this
    user cannot search ended in a `PermissionError` traceback, and which
    answers False to it from 3.14, so the leg read as an uninitialized
    submodule. A name the system cannot take at all is nothing there, as
    `exists()` answered it."""
    try:
        return _is_a(path, lambda _mode: True)
    except ValueError:
        return False


def _gitfile_opens(path: Path) -> bool:
    """Whether a leg's `.git` that is a regular file, a gitfile, can be
    opened (#919), asked as `_is_a` asks a `stat`: False where nothing is
    there to open (`_ABSENT_ERRNOS`, `_ABSENT_WINERRORS`), the `OSError` of
    an open the operating system REFUSED raised, and True for a `.git` that
    is no regular file, a checkout's own directory, which git reads itself.

    A GITFILE AT MODE 000 STATS, so `_is_there` read the leg as a checkout:
    git could not read where the leg's objects are, and the run ended in
    `pin-commit-unresolvable` under THE LOCKSTEP RULE, which says the
    pinned commit is missing (RV827's N6). Only a regular file is opened,
    since the open of a FIFO waits for a writer."""
    if not _is_a(path, stat.S_ISREG):
        return True
    try:
        path.open("rb").close()
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    return True


#: What a `stat` mode that is no regular file names (#919), as the line
#: about the file whose place it takes says it. A device is either kind.
_NOT_A_FILE_KINDS = (
    (stat.S_ISDIR, "a directory"), (stat.S_ISFIFO, "a FIFO"),
    (stat.S_ISSOCK, "a socket"), (stat.S_ISCHR, "a device"),
    (stat.S_ISBLK, "a device"))


def _named_kind(mode: int, link: str = "") -> str | None:
    """`is <link><kind>, not a file` for a `mode` that is no regular file,
    `is not a file` where `_NOT_A_FILE_KINDS` has no name for it, and None
    for a regular file, which stands in no file's place."""
    if stat.S_ISREG(mode):
        return None
    kind = next((name for test, name in _NOT_A_FILE_KINDS if test(mode)),
                None)
    return f"is {link}{kind}, not a file" if kind else "is not a file"


def _not_a_file(path: Path) -> str | None:
    """What stands at `path` where `_is_file` found no regular file there,
    as the words after its name (#919): `is a directory, not a file`, `is a
    FIFO, not a file`, `is a symlink to nothing, not a file`, `is a symlink
    loop, not a file`, `is a symlink to a directory, not a file`, and the
    same for a socket or a device. None where NOTHING is there (`lstat`
    finds no entry at the name, or the system cannot take the name at all),
    whose refusal keeps the words it always had.

    WHAT IS THERE WAS CALLED ABSENT: `_is_file` asks `stat`, which answers
    "not a regular file" for a directory or a FIFO and "nothing there" for a
    symlink that leads nowhere or to itself, so each was refused under "does
    not exist" and given a remedy that moves a pin, and a shape copy so
    replaced was "pinned but absent". `lstat` asks about the name itself.
    It runs only after `stat` answered, inside the guard, and opens nothing.
    """
    try:
        mode = path.lstat().st_mode
    except (OSError, ValueError):
        return None
    if not stat.S_ISLNK(mode):
        return _named_kind(mode)
    try:
        return _named_kind(path.stat().st_mode, "a symlink to ")
    except OSError as exc:
        loop = (exc.errno == errno.ELOOP
                or getattr(exc, "winerror", None) == 1921)
        return ("is a symlink loop, not a file" if loop
                else "is a symlink to nothing, not a file")


#: What a pin, the shape pin, a neutral-product pin or the manifest is told
#: where something that is not a file stands in its place (#919), after
#: `_remedy`'s first sentence. It is not the file moved or edited, so THE
#: LOCKSTEP RULE, `git submodule update` and a re-scaffold do not put it
#: right, and it may hold something nobody committed, so it is moved aside.
NOT_A_FILE = (
    "Something that is not a file stands in its place: move it aside, or "
    "take it away if nobody wants it, and restore the file from the "
    "project's history. ")

#: The line under a `shape-copy-missing` finding for a copy whose place
#: something that is not a file takes (#919), as `shape-copy-drift` has one.
COPY_NOT_A_FILE = (
    "A shape file's place is taken by something that is not a file. Move it "
    "aside, or take it away if nobody wants it, and restore the copy from "
    "the project's history.")


def _no_file(code: str, path: Path, said: str, absent: str,
             *remediation: str) -> Refusal:
    """`code`'s refusal where `_is_file` found no regular file at `path`
    (#919). `said` names the file. Where nothing is there it goes on with
    `absent`, and `remediation` is the refusal's own, if it has one: the
    words it always had, byte for byte. Where something that is not a file
    stands there, `_not_a_file` says what, and the remedy is `NOT_A_FILE`'s.

    A refusal that had no remedy of its own is built with none, as it
    always was, and not with an empty one: beside a `repo_shape.py` older
    than #370, `Refusal`'s own default is the lockstep remedy, and an empty
    one would print a blank line where it stood (#370, #610)."""
    what = _not_a_file(path)
    if what is None:
        return Refusal(code, said + absent, *remediation)
    return Refusal(code, f"{said} {what}", _remedy(NOT_A_FILE))


def _load(root: Path, path: Path):
    """`load_yaml(path)`, with every refusal it raises naming the file as
    `_named` does (#712).

    `load_yaml` names the path it was given, which is absolute here and in
    the platform's own spelling, raw. A file this user cannot open is
    `_unreadable_file`'s refusal, `yaml-unreadable`, the id it always had;
    any other keeps its id, its words and its remedy, with the path at its
    start named relative to the root. Asked of the refusal and not of new
    words in `repo_shape`, so a root whose `scripts/repo_shape.py` is older
    than this file names the file the same way (#370, #610): `load_yaml`
    has raised its refusal `from` the `OSError` since it was written."""
    try:
        return load_yaml(path)
    except Refusal as exc:
        if isinstance(exc.__cause__, OSError):
            raise _unreadable_file("yaml-unreadable", _named(root, path),
                                   exc.__cause__) from exc.__cause__
        absolute = f"{path}: "
        if not exc.detail.startswith(absolute):
            raise
        raise Refusal(exc.code, _named(root, path) + ": "
                      + exc.detail[len(absolute):], exc.remediation) from exc


def _workflows_unlistable(root: Path, workflows: Path,
                          exc: OSError) -> Refusal:
    """`workflow-unreadable` for the DIRECTORY, named as one (#434).

    The id a workflow file this user cannot open has (#359), so one id says
    "this validator cannot read the workflows" whatever the cause, in the
    words that file's line uses: `<path relative to root>: cannot be listed
    (<the operating system's reason>)`, POSIX and never absolute. The
    remediation is its own, because `_workflow_unreadable`'s counts files and
    a directory this user cannot list has none to count.

    The advice follows the cause. A refusal of permission (`PermissionError`,
    `EACCES` and `EPERM`) is put right by the mode or the owner, on the
    directory and on every one above it inside the root, since a `.github/`
    this user cannot search hides `workflows/` as surely as its own mode.
    Any other `OSError` (an I/O error, too many open files, a directory
    replaced while this ran) is not a permission and is not told to `chmod`.
    """
    advice = (
        "Restore read and search access to .github/workflows/ and to every "
        "directory above it inside the root (`chmod u+rx` on each, or fix who "
        "owns them). " if isinstance(exc, PermissionError) else
        "Where the operating system gave another reason, put a directory "
        "this user can list back in its place, and make sure nothing is "
        "changing it while this runs. ")
    return Refusal(
        "workflow-unreadable",
        f"{workflows.relative_to(root).as_posix()}: cannot be listed "
        f"({exc.strerror or type(exc).__name__})",
        "Remediation: this validator reads every `.yml` and `.yaml` file "
        "under .github/workflows/, whether or not it names a leg, and "
        "neither skips one nor reads one lossily: a workflow it skipped "
        "could hide a `@<sha>` reference that is out of lockstep, which is "
        "what it exists to find, and a directory it cannot list is one whose "
        "workflows it cannot read. " + advice + RUN_AGAIN)


def _workflow_refs(root: Path) -> list[tuple[Path, str, str]]:
    """Every (file, owner/repo, sha) `@<sha>` reference in the workflows, or
    ONE refusal naming each workflow file that cannot be read (#359), or the
    workflows directory when this user cannot list it (#434).

    EVERY FILE IS READ, whether or not it names a leg: the file is opened
    before it is known to hold a reference, so a UTF-16 workflow that names no
    leg used to stop the run in a `UnicodeDecodeError` (a `ValueError`, which
    `main()` does not catch: a traceback, exit 1 -- the code this validator
    uses for a finding). It is a REFUSAL, exit 2, `workflow-unreadable`, as a
    pin that is not UTF-8 is `yaml-unreadable`: the question cannot be asked.

    THE DIRECTORY IS THE SAME REFUSAL, BY ANOTHER CAUSE (#434). The three
    calls that reach a workflow had no handler either: `workflows.is_dir()`,
    `workflows.iterdir()` and `is_file()` on each child, and `main()` catches
    `Refusal` alone, so a `.github/workflows/` this user could not list, one
    it could list and not search, or a `.github/` it could not search ended
    the run in a `PermissionError` traceback, exit 1. A directory it cannot
    reach is refused by name, and so is each file whose `stat` is refused (the
    directory listable and not searchable): the same `cannot be read` line a
    file it cannot open gets, never a file skipped as "not a file", because a
    skipped workflow could hide a `@<sha>` reference that is out of lockstep.
    Only a name with nothing at it (`_is_a` is False) is "no workflows", as it
    always was.
    """
    out: list[tuple[Path, str, str]] = []
    unreadable: list[_Unreadable] = []
    workflows = root / ".github" / "workflows"
    try:
        if not _is_a(workflows, stat.S_ISDIR):
            return out
        children = sorted(workflows.iterdir())
    except OSError as exc:
        raise _workflows_unlistable(root, workflows, exc) from exc
    for path in children:
        if path.suffix not in (".yml", ".yaml"):
            continue
        try:
            if not _is_a(path, stat.S_ISREG):
                continue
        except OSError as exc:
            # The words `_read_workflow` gives a file it cannot open, the
            # name spelled and the cause kept for the advice (#712).
            unreadable.append(_Unreadable(
                _cannot_read(_named(root, path), exc), False,
                isinstance(exc, PermissionError)))
            continue
        text, problem = _read_workflow(root, path)
        if problem is not None:
            unreadable.append(problem)
            continue
        for match in WORKFLOW_REF_RE.finditer(text):
            out.append((path, match.group("repo"), match.group("sha").lower()))
    if unreadable:
        raise _workflow_unreadable(unreadable)
    return out


def _load_leg_pin(root: Path, role, path: str, repository: str,
                  report: Report) -> tuple[dict, str, str]:
    """Read `<role>-pin.yaml` and check its own fields, before any fact in it
    is compared against another.

    Split from `_check_leg` for #132: everything that answers "does the pin
    file itself look right" belongs together. Returns the pin, its path
    relative to `root` as `_named` spells it, and its `commit:` lowercased.

    A pin that cannot be reached or read is refused by name (#712): see
    `_is_file` and `_load`. Every name is spelled, the leg's role and
    repository in the lines below as the pin's path is. Something that is
    not a file in the pin's place is `pin-missing` naming what it is, with
    a remedy of its own (#919): see `_no_file`.
    """
    pin_path = root / "contracts" / f"{role}-pin.yaml"
    # POSIX, on every platform: a finding names a path in THIS repository,
    # and `str()` of a relative Path on Windows spells it with backslashes —
    # a path the reader cannot paste back into git.
    rel = _named(root, pin_path)
    if not _is_file(root, pin_path):
        raise _no_file(
            "pin-missing", pin_path,
            f"leg {role!r} declares {_shown(repository)} at {path!r} but "
            f"{rel}", " does not exist")
    pin = _load(root, pin_path)
    if not isinstance(pin, dict):
        raise Refusal("pin-unreadable", f"{rel}: not a mapping")

    if pin.get("kind") != "pinned_contract_manifest":
        report.finding("pin-wrong-kind",
                       f"{rel}: kind is {pin.get('kind')!r}, expected "
                       "'pinned_contract_manifest'")
    if pin.get("revision_kind") != "commit":
        report.finding(
            "pin-tag-only",
            f"{rel}: revision_kind is {pin.get('revision_kind')!r}. A tag can "
            "be moved and a commit cannot; a pin is a commit or it is nothing.",
        )
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "pin-tag-only",
            f"{rel}: `commit:` is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.",
        )
    commit = commit.lower()
    if pin.get("submodule_path") != path:
        report.finding("pin-path-mismatch",
                       f"{rel}: submodule_path is {pin.get('submodule_path')!r} "
                       f"but project.yaml puts the {_shown(str(role))} leg at "
                       f"{path!r}")
    if pin.get("source_repository") != repository:
        report.finding("pin-repository-mismatch",
                       f"{rel}: source_repository is "
                       f"{pin.get('source_repository')!r} but project.yaml "
                       f"declares {repository!r}")
    return pin, rel, commit


@contextmanager
def _git_runs(unread: str) -> Iterator[None]:
    """The `git-not-runnable` refusal, exit 2, for a check that reads this
    repository through git and could not start it (#412).

    `git_out` raises `FileNotFoundError` when there is no git on PATH,
    `PermissionError` when the `git` found there will not run, and a plain
    `OSError` (`ENOEXEC`) when it is no program this machine can execute, a
    binary for another architecture or a script with no shebang, and nothing
    here caught any of them: the run ended in a traceback, which exits 1, a
    FINDING's code, though nothing was found. The module's own exit codes
    make 1 "drift a reviewer can act on" and 2 "the question could not be
    asked ... never an implicit pass". So every call that runs git runs
    inside this, and `unread` says which check it was and what it could not
    read. ONE code, whichever check meets the missing git first; every one
    of them is the same fact about the machine.

    ONLY AN ERROR FROM STARTING GIT COUNTS, told apart two ways. The block
    is around the git calls alone, never around a whole check: a pin file or
    a submodule directory nobody may read is an `OSError` too, and it is not
    this, nor is telling that operator to put git on PATH any help. And
    inside a git call the class is not enough: `subprocess` raises the same
    `FileNotFoundError` or `PermissionError` when the DIRECTORY it was to run
    git in cannot be entered, and on POSIX names that directory in
    `filename` where a program that will not start names `git`. So the rule
    is the NAME: any `OSError` whose `filename` is `git` counts, `ENOEXEC`'s
    included, and an error that names a directory or any other file passes
    through unchanged, and so does any `OSError` that names none. The one
    nameless error that counts is a `FileNotFoundError` or a
    `PermissionError`: Windows' `CreateProcess` failures carry no filename,
    so a missing git there is `[WinError 2]` with `filename` None, and
    nothing says it was the directory.

    `recorded_gitlink`'s `except Refusal` is not in the way: an `OSError` is
    no `Refusal`, so a missing git reaches here instead of reading as "no
    gitlink recorded", which would be a false `pin-gitlink-absent`.
    """
    try:
        yield
    except OSError as exc:
        nameless = (exc.filename is None
                    and isinstance(exc, (FileNotFoundError, PermissionError)))
        if exc.filename != "git" and not nameless:
            raise
        raise Refusal(
            "git-not-runnable",
            f"{unread}: git could not be run ({exc.strerror or exc})",
            "Remediation: put git on PATH and run `scripts/validate-pins.py` "
            "again. This assembly root's lockstep gate reads each leg's "
            "gitlink and recomputes its pinned tree digest through git, so "
            "without it nothing says whether the pins agree, and a gate that "
            "cannot answer is never a pass.") from exc


def _gitlink_repairs(root: Path, role, gitlink: str, commit: str) -> str:
    """The two commands a `pin-gitlink-mismatch` ends on, when they can
    commit (#478; `_end_gitlink_mismatches` says when).

    WHICH COMMIT STAYS IS THE PERSON'S CALL, so both are named and neither
    is chosen. A gitlink moved and committed by hand (`git -C spec pull`,
    then `git add spec` in the root) wants the first, `--to` the gitlink's
    commit, if the move was meant and the second, `--to` the pin's, if it
    was not; a pin edited by hand reads the same with the two the other way
    round. Either is `bump-leg.py`, which puts all three facts at one commit
    in ONE commit and runs this validator before it commits: a gitlink put
    back by hand is the same single-fact move this check refuses. Its
    `--dry-run` comes first, as openRepoShape's AGENTS.md says of advancing
    a leg.

    FROM A CHECKOUT OF openRepoShape, as `validate-family.py` names
    `family.py`: no project carries `bump-leg.py`, and this file cannot know
    where the reader's checkout is, so the script is relative to one and the
    root, which it does know, is absolute and quoted.
    """
    return _two_repairs(root, role, "the first command keeps the gitlink's "
                        "commit and the second the pin's", gitlink, commit)


def _quoted(value) -> str:
    """`value` as one word of a command this validator prints: `shlex.quote`d,
    as every such word always was, unless a character in it is not printable,
    and then as `_shown` spells it (#712). Quoted, an ESC or a line break in
    a root's path or a leg's role reached the terminal as the control it is;
    spelled, the word cannot be pasted as the value it names, and no quoting
    could make it so."""
    text = str(value)
    return shlex.quote(text) if text.isprintable() else _shown(text)


def _bump_command(root: Path, role) -> str:
    """`bump-leg.py` for this root's leg `role`, up to its `--to` (#478),
    each word as `_quoted` spells it (#712)."""
    return (f"{PYTHON} scripts/bump-leg.py --root {_quoted(root)} "
            f"--leg {_quoted(role)} --to")


#: What a `bump-leg.py` line needs to commit, said once for every finding
#: that names one (#478, #539).
BUMP_COMMITS = ("on a branch other than the tracking branch, once this "
                "validator and validate-manifest.py pass on its rewrite (it "
                "rolls the bump back when either is red), and refuses a "
                "commit no branch of the leg's remote contains")


def _two_repairs(root: Path, role, choice: str, first: str,
                 second: str) -> str:
    """Two `bump-leg.py` lines for one leg, `--to` `first` and `--to`
    `second`, and `choice`, saying what each keeps: which commit stays is
    the person's call, so neither is chosen (#478, #539)."""
    bump = _bump_command(root, role)
    return ("Which commit stays is the person's call. From a checkout of "
            f"openRepoShape, {choice}; run either with `--dry-run` first. "
            f"Either puts all three at it in one commit, {BUMP_COMMITS}, so "
            f"push one made in the leg first:\n    {bump} {first}\n"
            f"    {bump} {second}")


def _digest_repair(root: Path, role, commit: str) -> str:
    """The one `bump-leg.py` line a lone `pin-digest-mismatch` ends on
    (#539): `--to` the commit the gitlink and the pin already name, which
    recomputes the digest from the leg's own objects and writes it into the
    pin, the one fact it moves. Never a hand edit of the digest, which is
    the drift this check exists to find."""
    return ("From a checkout of openRepoShape, this recomputes the digest "
            f"at {commit[:12]}, the commit the gitlink and the pin already "
            "name, from the leg's own objects and writes it into the pin; "
            "run it with `--dry-run` first. It commits "
            f"{BUMP_COMMITS}, so push that commit from the leg first if no "
            f"branch holds it:\n    {_bump_command(root, role)} {commit}")


def _reference_repairs(root: Path, role, gitlink: str,
                       reference: str) -> str:
    """The two `bump-leg.py` lines a lone `pin-workflow-ref-mismatch` ends
    on (#539), as `pin-gitlink-mismatch` ends on two (#478): a reference
    edited by hand wants the first, which puts it back at the commit the
    gitlink and the pin name, unless the edit was meant, and then the
    second moves the gitlink and the pin to the reference's commit."""
    return _two_repairs(
        root, role, "the first command keeps the commit the gitlink and the "
        "pin name and moves every reference to the leg's repository to it, "
        "and the second moves the gitlink and the pin to this reference's",
        gitlink, reference)


class Back(NamedTuple):
    """The one leg whose gitlink is off its pin while another leg is out of
    step (#677): its path, the commit its gitlink names, and whether its
    own `pin-digest-mismatch` stands, which is recomputed at the pin's
    commit and so outlasts the gitlink put back there."""

    path: str
    gitlink: str
    digest: bool


def _digest_stands(report: Report, role) -> bool:
    """Whether the leg `role`'s own `pin-digest-mismatch` was found."""
    return any(one.role == role and one.reference is None
               for one in report.curable)


def _put_back(paths: list[str]) -> str:
    """The step by hand a held-back line waits on while two legs are out of
    step (#478, #677): one of `paths`' gitlinks back at its pin, or the
    commit that moved them undone. No `bump-leg.py` line takes it, since
    the other leg rolls that line back.

    A LEG'S WORKFLOW REFERENCES GO BACK WITH ITS GITLINK: a reference moved
    with it stays at the move, and stands as that leg's finding beside the
    other leg's, which holds the next line back and asks for this step
    again. AN UNDO IS FOLLOWED BY `git submodule update` over the legs: it
    puts the gitlink back and leaves the leg checked out at the move, a
    root `bump-leg.py` refuses as dirty. Each path is spelled (#712)."""
    one = len(paths) == 1
    which, moved = ((f"{_shown(paths[0])}'s", "it") if one
                    else ("one leg's", "them"))
    legs = " ".join(_quoted(path) for path in paths)
    return (f"put {which} gitlink back at its pin (check that leg out at the "
            "pin's commit and commit its gitlink in this root, with every "
            "workflow reference to its repository at that commit too), or "
            f"undo the commit that moved {moved} and run `git submodule "
            f"update -- {legs}` in this root")


def _held_then(lines: str, whom: str, back: Back | None,
               other_legs: dict | None) -> str:
    """What a held-back finding says comes after its first step: `lines`
    for `whom`. Never a line while `back`'s own digest stands, since two
    legs are then out of step with no gitlink off; and in the gitlink's own
    finding (`other_legs`), how its move is kept if it was meant: the
    whole commit, which is the only `--to` `bump-leg.py` takes. `back`'s
    path is spelled (#712); `whom` comes spelled."""
    if back is not None and back.digest:
        return (f"names no line while {_shown(back.path)}'s own "
                "pin-digest-mismatch stands.")
    if back is not None and other_legs:
        after = ("after that line" if lines.endswith("line")
                 else "after one of them")
        named = _shown(back.path)
        return (f"names {lines} for {whom}, and if {named}'s move was "
                f"meant, bumping {named} to {back.gitlink} {after} keeps "
                "it.")
    return f"names {lines} for {whom}."


def _gitlink_repairs_held_back(paths: list[str], others: list[str],
                               lines: str = "the two bump-leg.py lines",
                               back: Back | None = None,
                               other_legs: dict[str, list[str]] | None = None
                               ) -> str:
    """Why a `pin-gitlink-mismatch` names no command, and what comes first
    (#478): `bump-leg.py` runs this validator before it commits and rolls
    the bump back when it is red, so no single line commits while another
    leg is off its pin or another finding stands. A `pin-digest-mismatch`
    held back by another finding says the same, naming `lines`, the one
    line it would end on (#539).

    `others` are findings no bump clears, and they are cleared first.
    ANOTHER LEG'S DIGEST OR WORKFLOW REFERENCE IS NOT ONE (#677): a bump of
    THAT leg clears it, and is rolled back while `back`, the one leg whose
    gitlink is off its pin, stays off, as a bump of `back` is while that
    finding stands. "First clear that finding" named a step no line could
    take, so both findings name the step two gitlinks off their pins name,
    by hand, for `back`. The gitlink's own finding is given `other_legs`,
    `{path: codes}`, and `lines` are then that leg's; the other leg's
    finding names its own `lines`, for itself by its path, since "that leg"
    would read as `back`. `_held_then` says what follows. Every path is
    spelled (#712).
    """
    what, first, whom = [], [], "that leg"
    if len(paths) > 1:
        what.append(" and ".join(_shown(path) for path in paths)
                    + (" are both" if len(paths) == 2 else " are all")
                    + " off their pins")
        whom = "the leg that is left"
    elif other_legs:
        whom = " and ".join(_shown(path) for path in other_legs)
    elif back is not None:
        what.append(f"{_shown(back.path)} is off its pin")
        whom = _shown(paths[0])
    what += [f"{_shown(path)} is out of step too ({', '.join(codes)})"
             for path, codes in (other_legs or {}).items()]
    if others:
        what.append("this validator also reports " + ", ".join(others))
        first.append("clear " + ("that finding" if len(others) == 1
                                 else "those findings"))
    if len(paths) > 1 or back is not None:
        first.append(_put_back(paths if len(paths) > 1 else [back.path]))
    return ("No single bump-leg.py line can commit while "
            + " and ".join(what) + ": bump-leg.py moves one leg and runs "
            "this validator before it commits, rolling the bump back when it "
            "is red. First " + ", and ".join(first) + "; this validator then "
            + _held_then(lines, whom, back, other_legs))


def _has_own_gate(root: Path) -> bool:
    """Whether `root` has a `scripts/validate-pins.py` of its own, the gate
    `bump-leg.py` runs before it commits and skips when it is absent
    (#478)."""
    return os.path.isfile(root / "scripts" / "validate-pins.py")


def _end_gitlink_mismatches(root: Path, report: Report) -> object:
    """What each `pin-gitlink-mismatch` ends on, once every check has run
    (#478). Returns the role of the leg whose two lines it named, or None.

    `bump-leg.py` RUNS THIS WHOLE VALIDATOR after its rewrite and before it
    commits, and rolls the bump back when it is red. So its two lines are
    named only where they can commit: ONE leg's gitlink is off its pin, and
    every other finding is one a bump of that leg clears (`Report.finding`'s
    `leg`). Two legs off, or any other finding, and either line is rolled
    back, so the finding names none and says what comes first instead:
    another leg's digest or workflow reference is that leg's to clear, and
    what comes first is this gitlink, put back by hand (#677).

    ONLY OVER A ROOT THAT HAS THIS GATE OF ITS OWN. `bump-leg.py` runs the
    root's `scripts/validate-pins.py` and skips an absent one, so this copy
    run against a root that has none cannot say what the bump's run will:
    the finding ends at THE LOCKSTEP RULE, as it did before #478, and the
    root's own gate is the thing to put back first.
    """
    if not report.mismatches or not _has_own_gate(root):
        return None
    roles = [role for _, role, _, _, _ in report.mismatches]
    others = _out_of_step(report)[1]
    other_legs = _other_legs(report, roles)
    if len(report.mismatches) == 1 and not others and not other_legs:
        index, role, _, gitlink, commit = report.mismatches[0]
        report.findings[index] += "\n  " + _gitlink_repairs(root, role,
                                                            gitlink, commit)
        return role
    paths = [path for _, _, path, _, _ in report.mismatches]
    lines, back = "the two bump-leg.py lines", None
    if other_legs:
        lines = ("the bump-leg.py line" if all(
            code == "pin-digest-mismatch" for codes in other_legs.values()
            for code in codes) else "the bump-leg.py lines")
        _, role, path, gitlink, _ = report.mismatches[0]
        back = Back(path, gitlink, _digest_stands(report, role))
    why = _gitlink_repairs_held_back(paths, others, lines, back, other_legs)
    for index, *_ in report.mismatches:
        report.findings[index] += "\n  " + why
    return None


def _other_legs(report: Report, roles: list) -> dict[str, list[str]]:
    """`{path: codes}` for each leg not in `roles` whose own digest or
    workflow reference is out of step, a finding only a bump of THAT leg
    clears, each code once and in the order found (#677)."""
    found: dict[str, list[str]] = {}
    for one in report.curable:
        if one.role is None or one.role in roles:
            continue
        codes = found.setdefault(one.path, [])
        code = report.cleared_by[one.index][0]
        if code not in codes:
            codes.append(code)
    return found


def _end_curable_findings(root: Path, report: Report, named) -> None:
    """What each `pin-digest-mismatch` and `pin-workflow-ref-mismatch` ends
    on, once every check has run (#539). `named` is the role of the leg
    whose `pin-gitlink-mismatch` names its two lines, or None.

    THEY ENDED AT THE LOCKSTEP RULE AND NAMED NO COMMAND, though
    `bump-leg.py --to` the commit the gitlink and the pin name cures both:
    it recomputes the pin's digest from the leg's own objects and moves
    every workflow reference to the leg's repository, in one commit. So a
    digest names that line, and a reference names it and the line `--to`
    its own commit, since an edit to the reference may have been meant:
    which commit stays is the person's call, as it is for a gitlink (#478).

    ONLY WHERE A LINE CAN COMMIT, by `_end_gitlink_mismatches`' rule: the
    root has this gate of its own, and every finding is the leg's own,
    which a bump of it clears. Where another finding stands with them and
    no other leg is out of step, the finding says to clear that first, in
    the words a held-back `pin-gitlink-mismatch` uses. Where the leg's own
    gitlink is off its pin, that finding's lines clear this one too, and
    this says so where they are named. Where ANOTHER leg's gitlink is off
    its pin, the step that comes first is putting it back by hand, and the
    finding says so in the words the gitlink's own uses, then names this
    leg's lines (#677), or, where that leg's own digest stands too, that it
    names none. Where another leg's own digest or reference is out of step
    with no gitlink off, no line can commit and the finding ends at THE
    LOCKSTEP RULE, as it did before: no bump-leg.py line clears either
    leg's finding first, so there is no first step this could name that
    the other's would not contradict.
    """
    if not report.curable or not _has_own_gate(root):
        return
    legs, untagged = _out_of_step(report)
    off = {role: Back(path, gitlink, _digest_stands(report, role))
           for _, role, path, gitlink, _ in report.mismatches}
    for one in report.curable:
        ending = _curable_ending(root, one, legs, untagged, off, named)
        if ending:
            report.findings[one.index] += "\n  " + ending


def _out_of_step(report: Report) -> tuple[list, list[str]]:
    """`(legs, codes)`: each leg a finding names as the one whose bump
    clears it, and the code of each finding no bump clears, each once and
    in the order found (#539)."""
    legs: list = []
    untagged: list[str] = []
    for code, leg in report.cleared_by:
        if leg is None and code not in untagged:
            untagged.append(code)
        elif leg is not None and leg not in legs:
            legs.append(leg)
    return legs, untagged


def _curable_ending(root: Path, one: Curable, legs: list,
                    untagged: list[str], off: dict, named) -> str:
    """What `_end_curable_findings` adds to the finding `one`, or `""`.
    `off` is `{role: Back}` of each leg whose gitlink is off its pin. The
    leg's path is spelled (#712)."""
    if one.role in off:
        return (f"Either bump-leg.py line under {_shown(one.path)}'s "
                "pin-gitlink-mismatch above clears this finding too."
                if one.role == named else "")
    # Every other leg out of step, as the `Back` of its gitlink off its pin,
    # or None where that leg's own digest or reference is out of step.
    back = [off.get(leg) for leg in legs if leg != one.role]
    if one.role is None or len(back) > 1 or None in back:
        return ""
    if untagged or back:
        return _gitlink_repairs_held_back(
            [one.path], untagged, "the bump-leg.py line"
            if one.reference is None else "the two bump-leg.py lines",
            back[0] if back else None)
    if one.reference is None:
        return _digest_repair(root, one.role, one.commit)
    return _reference_repairs(root, one.role, one.commit, one.reference)


def _check_gitlink_matches_pin(root: Path, role, path: str, commit: str,
                               rel: str, report: Report) -> str:
    """Fact 1 vs fact 2: the recorded gitlink against the pin file's
    `commit:`. Split from `_check_leg` for #132. Returns the gitlink so the
    caller can check it again against fact 3, the workflow references. The
    role and the path are spelled (#712).
    """
    role_named = _shown(str(role))
    with _git_runs(f"the {role_named} leg's gitlink recorded at {path!r} "
                   "could not be read"):
        gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        raise Refusal(
            "pin-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. The {role_named} "
            "leg is declared in project.yaml but this repository does not "
            "record it as a submodule.",
        )
    if gitlink != commit:
        report.finding(
            "pin-gitlink-mismatch",
            f"{_shown(path)}: gitlink {gitlink} != {rel} commit {commit}\n  "
            + LOCKSTEP,
            leg=role,
        )
        report.mismatches.append((len(report.findings) - 1, role, path,
                                  gitlink, commit))
    else:
        report.note(f"{_shown(path)}: gitlink == {rel} commit {commit[:12]}")
    return gitlink


def _check_pin_digest(root: Path, path: str, commit: str, pin: dict, rel: str,
                      report: Report, role=None) -> None:
    """The digest: split from `_check_leg` for #132. Recomputes the leg's
    tree sha256 at the pinned commit, because a gitlink and a pin file that
    agree on a commit may still disagree on that commit's bytes. A mismatch
    is one `bump-leg.py` clears, since it recomputes the digest (#478). The
    leg's path is spelled in every line (#712).

    A CHECKOUT THIS USER CANNOT SEARCH IS REFUSED BY NAME (#712, after
    RV827's S1), `pin-submodule-unreadable`, naming its `.git`: the digest
    cannot be recomputed, and the leg is not uninitialized, which is what
    Python 3.14's `exists()` would have said of it. So is a `.git` gitfile
    this user cannot open (#919): see `_gitfile_opens`.
    """
    submodule = root / path
    named = _shown(path)
    dotgit = submodule / ".git"
    try:
        initialized = _is_there(dotgit) and _gitfile_opens(dotgit)
    except OSError as exc:
        raise _unreadable_file(
            "pin-submodule-unreadable", _named(root, dotgit), exc,
            "each leg's checkout, to recompute its pinned tree digest from "
            "the leg's own objects") from exc
    if not initialized:
        raise Refusal(
            "pin-submodule-uninitialized",
            f"{named} is not an initialized submodule checkout, so the pinned "
            "digest cannot be recomputed. Presence is not identity and an "
            "unreadable surface must fail rather than degrade.",
        )
    # `_git_runs` OUTSIDE the `try`: the refusal it raises is a `Refusal`, and
    # inside, the `except Refusal` below would turn "no git to run" into
    # `pin-commit-unresolvable`, which says the commit is missing.
    with _git_runs(f"{named}: the pinned commit {commit[:12]} could not be "
                   "looked up in that submodule"):
        try:
            git_out(["rev-parse", "--verify", "--quiet",
                     f"{commit}^{{commit}}"], cwd=submodule)
        except Refusal as exc:
            raise Refusal(
                "pin-commit-unresolvable",
                f"{named}: the pinned commit {commit} is not in that "
                f"submodule's object store ({exc.detail})",
            ) from exc
    recorded = (pin.get("digests") or {}).get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("pin-digest-malformed",
                       f"{rel}: digests.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding(
            "pin-digest-definition",
            f"{rel}: digest_definition is {pin.get('digest_definition')!r}, "
            f"expected {TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.",
        )
    else:
        with _git_runs(f"{named}: the tree digest at {commit[:12]} could not "
                       "be recomputed"):
            actual = tree_digest(submodule, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "pin-digest-mismatch",
                f"{rel}: digests.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                f"  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  " + LOCKSTEP,
                leg=role,
            )
            report.curable.append(Curable(len(report.findings) - 1, role,
                                          path, commit, None))
        else:
            report.note(f"{named}: tree digest recomputes "
                        f"({recorded[:12]}…)")


def _check_workflow_refs_for_leg(refs, repository: str, path: str,
                                 gitlink: str, report: Report,
                                 role=None) -> None:
    """Fact 3: split from `_check_leg` for #132 — every workflow `@<sha>`
    reference naming this leg's repository must agree with the gitlink. A
    mismatch is one `bump-leg.py` clears, since it moves every one (#478).

    THE NOTE COUNTS THE REFERENCES THAT AGREE (#739). It counted every
    reference naming the repository, so one off its gitlink was its finding
    and, beside it, `1 workflow @<sha> reference(s) agree with the gitlink`.
    Only those at the gitlink are counted, `N of M` where some are not, and
    no note is printed where none is.
    """
    seen = agree = 0
    for wf_path, wf_repo, wf_sha in refs:
        if wf_repo != repository:
            continue
        seen += 1
        if wf_sha != gitlink:
            report.finding(
                "pin-workflow-ref-mismatch",
                f"{_shown(wf_path.name)}: `{wf_repo}@{wf_sha}` != the gitlink "
                f"{gitlink} recorded at {path!r}\n  " + LOCKSTEP,
                leg=role,
            )
            report.curable.append(Curable(len(report.findings) - 1, role,
                                          path, gitlink, wf_sha))
        else:
            agree += 1
    if agree:
        counted = str(agree) if agree == seen else f"{agree} of {seen}"
        report.note(f"{repository}: {counted} workflow @<sha> reference(s) "
                    f"agree with the gitlink")


def _check_leg(root: Path, leg: dict, report: Report, refs) -> None:
    role = leg.get("role")
    path = str(leg.get("path") or "")
    repository = str(leg.get("repository") or "")
    pin, rel, commit = _load_leg_pin(root, role, path, repository, report)
    gitlink = _check_gitlink_matches_pin(root, role, path, commit, rel, report)
    _check_pin_digest(root, path, commit, pin, rel, report, role)
    _check_workflow_refs_for_leg(refs, repository, path, gitlink, report,
                                 role)


def _check_shape_pin_header(root: Path, manifest: dict, report: Report
                            ) -> tuple[dict, str]:
    """Load `shape-pin.yaml` and check the fields that describe its own
    commit, before the files it lists are checked one by one.

    Split from `_check_shape_pin` for #132. Returns the pin and its path
    relative to `root`.

    Named relative to the root in every line, the two refusals included,
    which named it absolute, and refused by name where it cannot be reached
    or read (#712). The two commits it compares are spelled: neither is
    asked to be 40 hex before the finding that names both. Something that
    is not a file in its place is named, with a remedy of its own (#919).
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    rel = _named(root, pin_path)
    if not _is_file(root, pin_path):
        raise _no_file("shape-pin-missing", pin_path, rel, " does not exist")
    pin = _load(root, pin_path)
    if not isinstance(pin, dict):
        raise Refusal("shape-pin-unreadable", f"{rel}: not a mapping")
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{rel}: revision_kind is {pin.get('revision_kind')!r}")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        report.finding("shape-pin-commit",
                       f"{rel}: `commit:` {commit!r} is not 40 hex")
    declared = (manifest.get("shape") or {}).get("commit")
    if declared and str(declared).lower() != commit.lower():
        report.finding("shape-pin-manifest-disagree",
                       f"{rel} commit {_shown(commit)} != project.yaml "
                       f"shape.commit {_shown(str(declared))}")
    return pin, rel


def _check_shape_copy(root: Path, row, rel: str, report: Report) -> None:
    """One `files:` row of the shape pin.

    Split from `_check_shape_pin` for #132 so the loop over the pinned files
    is a single call per row: is it a mapping, is the file still there, and
    does its sha256 still match what the pin recorded. A row whose `path:`
    is absent, empty or no string is `shape-pin-row`, as `update-shape.py`
    refuses it `update-pin-row`: its `path:` was read as a path, so a row
    with none was `None is pinned but absent` (#681).

    SOMETHING THAT IS NOT A FILE IN THE COPY'S PLACE IS NAMED (#919): `<pin>:
    <path> is pinned but is a directory, not a file` (`_not_a_file`), with
    a line under it saying what to do, where it was `pinned but absent`. A
    copy that is not there keeps those words byte for byte: `shape-doctor.py`
    reads them to find a merged-away `shape/` copy, which only a path with
    nothing at it can be (`update-shape.py`'s `merged_into`).
    """
    if not isinstance(row, dict):
        report.finding("shape-pin-row", f"{rel}: a files row is not a mapping")
        return
    path = row.get("path")
    if not isinstance(path, str) or not path:
        report.finding("shape-pin-row", f"{rel}: a files row's `path:` is "
                                        f"{path!r}, not the path of a file")
        return
    target = root / path
    # A copy whose `stat` or read is refused is `shape-copy-unreadable`, a
    # refusal naming it as the row does (#712). `is_file()` raised a refused
    # `stat` out of the run up to Python 3.13, and called the copy "pinned
    # but absent" on 3.14; a copy at mode 000 ended in `file_sha256`'s
    # `PermissionError` on every Python. The row's path and digest are
    # spelled, as the pin spells them.
    named = _shown(path)
    if not _is_file(root, target, "shape-copy-unreadable", named):
        what = _not_a_file(target)
        report.finding("shape-copy-missing", f"{rel}: {named} is pinned but "
                       + ("absent" if what is None
                          else f"{what}\n  {COPY_NOT_A_FILE}"))
        return
    try:
        actual = file_sha256(target)
    except OSError as exc:
        raise _unreadable_file("shape-copy-unreadable", named, exc) from exc
    if actual != str(row.get("sha256", "")).lower():
        report.finding(
            "shape-copy-drift",
            f"{named}: sha256 {actual}\n"
            f"       {rel} records {_shown(str(row.get('sha256')))}\n"
            "  A shape file was edited in place. Either revert it, or "
            "carry the change upstream to openRepoShape and re-pin.",
        )


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The shape pin is a COPY pin, and it is checked as one.

    openRepoShape is not a submodule of a scaffolded project: the scaffold
    COPIES a small set of files out of it so the project is self-contained in
    an org that may never obtain the upstream. There is therefore no gitlink to
    compare — the identity of the copies is carried by the per-file `sha256`
    rows, exactly the half of `neutral-product-pin`'s shape that exists for
    artifacts a consumer holds rather than mounts.
    """
    pin, rel = _check_shape_pin_header(root, manifest, report)
    before = len(report.findings)
    files = pin.get("files") or []
    if not isinstance(files, list):
        # Asked, not assumed (#290): `files: 5` was iterated, and the run
        # ended in a TypeError with no finding naming the pin.
        report.finding("shape-pin-row",
                       f"{rel}: `files:` is {files!r}, not a list of "
                       "`path:`/`sha256:` rows, so nothing about the copied "
                       "shape files is actually asserted")
        return
    if not files:
        report.finding("shape-pin-no-files",
                       f"{rel}: no `files:` rows, so nothing about the copied "
                       "shape files is actually asserted")
    for row in files:
        _check_shape_copy(root, row, rel, report)
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their digests")


def _shown(typed: str) -> str:
    """A `--pin-source` value as a note names it: as typed, unless a
    character in it is not printable (`str.isprintable`), and then as
    Python's `repr` spells it, `'x\\x1b[31mRED'` (#610). It is the spelling
    the scaffold's `pin-source-unreadable` gives a `--pin-source`
    (`repo_shape.shown_path`), written here rather than imported: a root
    whose `scripts/repo_shape.py` is older than this file has no such name,
    and this gate would end in an `ImportError` before it checked a pin.
    Printed raw, an ESC in the value reached the terminal as the control it
    is."""
    return typed if typed.isprintable() else repr(typed)


class PinSources:
    """Every `--pin-source` value AS TYPED, read against the neutral-product
    pins `project.yaml` declares, and which of them a pin actually read.

    THE READING (#295). `PRODUCT=PATH` and a bare `PATH` are told apart by an
    `=`, and a path may hold one: a stand-in cloned under `a=b/` is
    `--pin-source a=b/openGlass`. Splitting every value at its first `=` made
    that a source keyed to a product `a` that nothing declares, which no pin
    ever looked up — the digest went to `gh api` and a `skip`, exit 0, with
    the skip line itself suggesting the `--pin-source` the person had just
    passed. So the text before the first `=` is a PRODUCT only when its
    `pin_product_key` is a declared pin's, the key the lookup below uses,
    and any other value is a bare PATH, whole. A declared name wins
    even when a directory is spelled like the whole value
    (`openGlass=x/openGlass` beside a directory `openGlass=x`): the reading is
    decided by the manifest and never by what happens to be on the disk, and
    `./openGlass=x/openGlass` is how to mean that directory.

    WHAT NO PIN READ (#295). A value no declared pin used — a mistyped key, a
    bare path every pin had a more specific answer for, an earlier value a
    later one replaced — is said once the pins are checked, by
    `_note_unused_pin_sources`. Saying nothing is how a mistyped key read as
    a pass that never looked.

    A VALUE THAT NAMES NO PATH IS REFUSED (#442), `pin-source-no-path`:
    `openGlass=` with nothing after its `=`, or an empty value. Either was
    `Path("")`, which is `.`, so the directory this ran in was asked for the
    pinned commit and the finding blamed `.`. `.` typed still means it. The
    value and the product it names are spelled, as `_shown` spells them.

    KEYED BY `pin_product_key`, the pin file's own fold (#712, after #638).
    `casefold()` took `openss=` for `openß`, two pin files, where the chain
    readers' `LinkSources` read them as two: the two copied tools read
    `[PRODUCT=]PATH` one way over ASCII alone. A pin's digest stopped a wrong
    source from passing; the source was simply looked up under the other
    spelling.
    """

    def __init__(self, values: list[str], declared) -> None:
        #: The declared pins, spelled as `project.yaml` spells them.
        self.declared = [p for p in declared if isinstance(p, str) and p]
        names = {pin_product_key(product): product
                 for product in self.declared}
        #: `{pin_product_key(product): (typed, path)}`, the last value given
        #: wins.
        self.keyed: dict[str, tuple[str, Path]] = {}
        #: `(typed, path)` of the last bare value, if any.
        self.bare: tuple[str, Path] | None = None
        #: Every distinct value in the order given, and the declared pin it
        #: was read as keyed to, or None for a bare PATH.
        self.reading: dict[str, str | None] = {}
        #: `{typed: the later value that took its place}`.
        self.replaced: dict[str, str] = {}
        #: The values a pin's digest was asked of, readable or not.
        self.used: set[str] = set()
        for typed in values:
            key, sep, path = typed.partition("=")
            product = names.get(pin_product_key(key)) if sep else None
            self.reading[typed] = product
            if product is not None:
                earlier = self.keyed.get(pin_product_key(product))
                self.keyed[pin_product_key(product)] = (typed, Path(path))
            else:
                earlier = self.bare
                self.bare = (typed, Path(typed))
            self.replaced.pop(typed, None)
            if earlier is not None and earlier[0] != typed:
                self.replaced[earlier[0]] = typed
        no_path = [f"`--pin-source {_shown(typed)}` names no path for "
                   f"{_shown(product)}"
                   if typed else "`--pin-source ''` names no path"
                   for typed, product in self.reading.items()
                   if not (typed.partition("=")[2] if product else typed)]
        if no_path:
            raise Refusal(
                "pin-source-no-path",
                "; ".join(no_path) + ". An empty path would be read as the "
                "directory this runs in.",
                "Remediation: give the checkout's path (`--pin-source "
                "<product>=<path>`), or `.` to mean this directory.")

    def read_as_path(self, typed: str | None) -> str:
        """The sentence saying a value holding `=` was read as a bare PATH,
        or `""` — what a person who meant `PRODUCT=PATH` and mistyped the
        product needs told, since nothing else in the run names it. Nothing
        when no pin is declared: the note has already said so. The key is
        spelled as `_shown` spells the value (#610), and so is each declared
        pin, which is the manifest's text (#712)."""
        if typed is None or self.reading.get(typed) is not None \
                or "=" not in typed or not self.declared:
            return ""
        key = typed.partition("=")[0]
        what = f"`{_shown(key)}` is not" if key else "nothing before its `=` is"
        declared = ", ".join(_shown(product) for product in self.declared)
        return (f"It was read as a PATH: {what} a declared neutral-product "
                f"pin (declared: {declared}).")


def resolve_neutral_pin_source(root: Path, product: str, repository: str,
                               sources: PinSources,
                               env_shared: bool = False,
                               ) -> tuple[Path | None, str | None, str | None]:
    """Where to read `product`'s tree OFFLINE, if anywhere at all.

    Tried in order, the most explicit ask first:

      1. `--pin-source <product>=<path>` (case-insensitive on the name as
         `pin_product_key` folds it, #712, and it must be a declared pin's
         for the value to be read this way, #295)
      2. `SHAPE_PIN_SOURCE_<PRODUCT>` in the environment
      3. a checkout sitting BESIDE this assembly root, named for the pinned
         repository (`opensoft/openGlass` -> `../openGlass`) — the ordinary
         shape of a workspace that clones a project and its neutral products
         side by side
      4. a bare `--pin-source <path>` with no `product=` prefix, which applies
         to whichever pin does not already have a more specific answer — the
         common case is exactly one declared neutral-product pin

    Rule 2 is skipped when `env_shared` is true, which is when another
    declared pin names the same variable (#275): a variable that cannot say
    which product it holds answers for neither, and `neutral-pin-source-
    collides` is noted for the pair. The pin still verifies through rule 1,
    3 or 4.

    Returns `(path, how, typed)`, `typed` being the `--pin-source` value as
    given when one of those answered, so the caller can mark it used (#295).
    `(None, None, None)` when nothing above answers; the caller's next step
    is `gh api`, and after that, a SKIP. `how` is printed, so the product
    and the sibling's path in it are spelled (#712).

    A CHECKOUT BESIDE THE ROOT THAT THIS USER CANNOT SEARCH IS THE SOURCE
    (#712, after RV827's S1): something is there, so it answers, and
    `_digest_from_source` names why it cannot, a finding. `exists()` raised
    its `PermissionError` out of the run up to Python 3.13, and from 3.14
    would have passed it over for `gh api`.
    """
    keyed = sources.keyed.get(pin_product_key(product))
    if keyed is not None:
        typed, path = keyed
        return path, f"--pin-source {_shown(product)}=...", typed
    env_name = pin_source_env_name(product)
    env_value = None if env_shared else os.environ.get(env_name)
    if env_value:
        return Path(env_value), f"${env_name}", None
    sibling = root.parent / repo_basename(repository)
    try:
        beside = _is_there(sibling / ".git")
    except OSError:
        beside = True
    if beside:
        return sibling, f"sibling checkout ({_shown(str(sibling))})", None
    if sources.bare is not None:
        typed, path = sources.bare
        return path, "--pin-source", typed
    return None, None, None


def _digest_from_source(source: Path, commit: str) -> str:
    """`tree_digest` over a local source, with every way that source can fail
    to answer raised as a `Refusal` (#295).

    `tree_digest` runs `git` IN the source, and a directory that is not there
    is not a git failure but a `FileNotFoundError` out of `subprocess.run`
    (`NotADirectoryError` for a file, `PermissionError` for a directory this
    user cannot enter), which nothing caught: `--pin-source
    openGlass=<missing>` died on a traceback, exit 1, where a directory that
    is not a checkout is the `neutral-pin-source-unreadable` FINDING. An
    explicit source that cannot answer is that finding however it fails.

    `stat()` INSIDE THE GUARD, and not `exists()`/`is_dir()`: before 3.14
    those two swallow only a missing path and raise every other `OSError`,
    so a source under a parent this user cannot enter, or a name longer than
    the filesystem takes, was still a traceback on 3.9 to 3.13 and, on 3.14,
    a finding saying "no such directory" about a directory that exists. The
    reason the finding gives is the system's own.
    """
    try:
        mode = source.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        raise Refusal("pin-source-missing", "no such directory") from None
    except OSError as exc:
        raise Refusal("pin-source-unreadable",
                      f"{exc.strerror or exc}") from exc
    if not stat.S_ISDIR(mode):
        raise Refusal("pin-source-not-a-directory",
                      "it is a file, not a directory")
    try:
        return tree_digest(source, commit)
    except OSError as exc:
        raise Refusal("pin-source-unreadable",
                      f"{exc.strerror or exc}") from exc


def _check_neutral_pin_entry_and_load(root: Path, product, report: Report
                                      ) -> tuple[dict, str] | None:
    """Validate one `neutral_product_pins:` entry and load its pin file.

    Split from `_check_neutral_product_pins` for #132. Returns `None` when
    the entry itself is malformed — already reported, and there is no pin
    file name to go read — so the caller moves on to the next entry exactly
    as the original loop's `continue` did.

    THE PIN'S PATH IS SPELLED (#712). The entry was `repr`'d and the path
    built from it was not, so `["\\x1b[31mRED"]` put an ESC on stderr inside
    `contracts/<ESC>[31mred-pin.yaml`, and in the remedy's `--pin`. The pin
    is named relative to the root in every line, and refused by name where
    it cannot be reached or read. Something that is not a file in its place
    is named, with a remedy of its own (#919): see `_no_file`.
    """
    if not isinstance(product, str) or not product:
        report.finding(
            "neutral-pin-entry-malformed",
            f"project.yaml neutral_product_pins entry {product!r} is not "
            "a non-empty product name",
        )
        return None
    pin_path = root / "contracts" / f"{product.lower()}-pin.yaml"
    rel = _named(root, pin_path)
    if not _is_file(root, pin_path):
        raise _no_file(
            "neutral-pin-missing", pin_path,
            f"project.yaml declares a pin on {product!r} but {rel}",
            " does not exist",
            "Remediation: `scaffold-project.py --pin "
            f"{_shown(product)}@<commit>` writes that file. A declaration in "
            "project.yaml with no pin file beside it is a claim with no "
            "referent — either restore the file or remove the "
            "declaration.",
        )
    pin = _load(root, pin_path)
    if not isinstance(pin, dict):
        raise Refusal("neutral-pin-unreadable", f"{rel}: not a mapping")
    return pin, rel


def _check_neutral_pin_commit_and_digest_fields(pin: dict, rel: str,
                                                report: Report
                                                ) -> tuple[str, str] | None:
    """The pin's own `revision_kind`/`commit`/digest fields, before any
    recompute of the referent is attempted.

    Split from `_check_neutral_product_pins` for #132. Returns `None` when
    the digest fields are themselves malformed — already reported, and
    recomputing anything to compare against them would be pointless — else
    `(commit, recorded_digest)`.
    """
    if pin.get("revision_kind") != "commit":
        report.finding(
            "neutral-pin-tag-only",
            f"{rel}: revision_kind is {pin.get('revision_kind')!r}. A tag "
            "can be moved and a commit cannot; a pin is a commit or it is "
            "nothing.",
        )
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "neutral-pin-tag-only",
            f"{rel}: `commit:` is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.",
        )
    commit = commit.lower()

    recorded = (pin.get("digests") or {}).get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("neutral-pin-digest-malformed",
                       f"{rel}: digests.tree_sha256 is {recorded!r}, not "
                       "64 hex")
        return None
    if pin.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding(
            "neutral-pin-digest-definition",
            f"{rel}: digest_definition is "
            f"{pin.get('digest_definition')!r}, expected "
            f"{TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.",
        )
        return None
    return commit, recorded


def _also_a_directory(typed: str | None, sources: PinSources) -> str:
    """The line for a value read as `PRODUCT=PATH` that ALSO names an
    existing directory whole (#295): the keyed reading won, and this is how
    to ask for the other one. `os.path.isdir`, which is False for every
    `OSError` on every Python, where `Path.is_dir` before 3.14 raised a name
    too long out of the finding it was adding a line to.

    THE VALUE IS NAMED AS `_shown` NAMES IT, in the sentence and in the
    command (#610): a value that is not printable is `repr`'d, as the "not
    used" note names it."""
    if typed is None or sources.reading.get(typed) is None \
            or not os.path.isdir(typed):
        return ""
    named = _shown(typed)
    return (f"`{named}` is also a directory; `--pin-source ./{named}` "
            "reads it as one.")


def _recompute_neutral_pin_digest(root: Path, product: str, repository: str,
                                  commit: str, rel: str, sources: PinSources,
                                  report: Report,
                                  shared: frozenset[str] = frozenset()
                                  ) -> tuple[str, str] | None:
    """Recompute the referent's tree digest: offline where a source can be
    found, else from `gh api`, else a named SKIP that never fails the run.

    Split from `_check_neutral_product_pins` for #132. Returns `(actual,
    how)`, or `None` when nothing could answer — a finding or a skip is
    already reported in that case, exactly as the original loop's
    `continue` left it. The product and the pin's `source_repository` are
    spelled wherever they are printed (#712).
    """
    env_shared = pin_product_key(product) in shared
    source, how, typed = resolve_neutral_pin_source(root, product, repository,
                                                    sources, env_shared)
    named = _shown(repository)
    if source is not None:
        if typed is not None:
            sources.used.add(typed)
        try:
            return _digest_from_source(source, commit), how
        except Refusal as exc:
            report.finding(
                "neutral-pin-source-unreadable",
                f"{rel}: {_shown(str(source))} ({how}) could not answer for "
                f"{named} @ {commit}: {exc.detail}"
                + "".join(f"\n  {line}" for line in (
                    sources.read_as_path(typed),
                    _also_a_directory(typed, sources),
                    f"Remediation: point it at a clone of {named} that "
                    "has that commit (`git fetch` in it first), or drop it "
                    "so the next source in the order answers.") if line),
            )
            return None
    try:
        return tree_digest_from_gh(repository, commit), "gh-api-tree-recursive"
    except Refusal as exc:
        # A variable another pin shares is not offered, and neither is the
        # bare `--pin-source`, which answers for every pin that has no more
        # specific answer: the keyed form is the one that says which pin it
        # is for (#275).
        offered = (f"A --pin-source {_shown(product)}=<path> or" if env_shared
                   else f"A --pin-source, {pin_source_env_name(product)}, or")
        report.skip(
            f"{_shown(product)}: pin commit {commit[:12]} digest NOT "
            f"rechecked — no local checkout ({exc.code}: "
            f"{exc.detail}). {offered} a checkout at "
            f"{_shown('../' + repo_basename(repository))} beside "
            "this assembly root would verify it offline.",
        )
        return None


def _check_one_neutral_product_pin(root: Path, product, report: Report,
                                   sources: PinSources,
                                   shared: frozenset[str] = frozenset()
                                   ) -> None:
    """One `neutral_product_pins:` entry, start to finish.

    Split from `_check_neutral_product_pins` for #132 so the loop in that
    function is a single call per entry instead of the whole re-check
    inline; each `return` below is one of the original loop's `continue`s.
    """
    loaded = _check_neutral_pin_entry_and_load(root, product, report)
    if loaded is None:
        return
    pin, rel = loaded
    repository = str(pin.get("source_repository") or "")
    fields = _check_neutral_pin_commit_and_digest_fields(pin, rel, report)
    if fields is None:
        return
    commit, recorded = fields
    recomputed = _recompute_neutral_pin_digest(root, product, repository,
                                               commit, rel, sources, report,
                                               shared)
    if recomputed is None:
        return
    actual, how = recomputed
    if actual.lower() != recorded.lower():
        report.finding(
            "neutral-pin-digest-mismatch",
            f"{rel}: digests.tree_sha256 {recorded}\n"
            f"       recomputed at {commit[:12]} {actual} ({how})\n"
            "  A neutral-product pin's digest no longer matches the "
            "bytes it names — the referent this project's name claims "
            "descent from has moved, or the pin was hand-edited.",
        )
    else:
        report.note(f"{_shown(product)}: pin commit {commit[:12]} digest "
                   f"recomputes ({how})")


def _report_pin_source_collisions(products, report: Report) -> None:
    """One `neutral-pin-source-collides` NOTE for each variable two or more
    declared products share (#275), naming every one of them and the
    variable. It is a note and never a finding: such a project did nothing
    the standard forbade when it was made (`scaffold-project.py` has refused
    it only since #275), every pin in it still verifies through the keyed
    `--pin-source <product>=<path>` or a checkout beside this assembly root,
    and a finding would make `update-shape.py apply` refuse every shape
    update (`update-validators-red`) until a person dropped a true
    declaration of descent. Which declaration stays is that person's
    decision, so the note says so and nothing here asks for one to go.
    `pin_source_env_collisions` is `repo_shape`'s, the one answer
    `scaffold-project.py` refuses on too: products are distinct by their pin
    files, so a product listed twice is not a collision here. The names are
    quoted with `repr`, as `neutral-pin-entry-malformed` quotes an entry: they
    are the manifest's own text and may hold a newline, and a note is one
    line."""
    for variable, group in pin_source_env_collisions(products).items():
        names = " and ".join(repr(product) for product in group)
        report.advise(
            "neutral-pin-source-collides: project.yaml neutral_product_pins "
            f"declares {names}, and one variable, {variable}, names the local "
            "checkout of each: it cannot say which it holds, so it is read "
            "for none of them. Each pin still verifies from the keyed "
            "`--pin-source <product>=<path>` or from a checkout beside this "
            "assembly root; a bare `--pin-source` answers for every pin that "
            "has no more specific source. Which declaration stays is the "
            "human's decision, and nothing here fails on it.")


def _check_neutral_product_pins(root: Path, manifest: dict, report: Report,
                                pin_source_values: list[str]) -> None:
    """Re-check every `neutral_product_pins:` entry `project.yaml` declares.

    `<Domainx><Product>` is a CLAIM of descent and a claim needs a REFERENT
    (Brett Heap, 2026-09-02): the referent is `contracts/<product lowercased>-
    pin.yaml`, and this recomputes its digest the same way
    `scaffold-project.py` computed it when the pin was first written — from a
    local checkout when one can be found, else from `gh api`. Neither
    available is a SKIP, never a finding and never a refusal: the absence of
    a way to answer is not evidence that the pin is wrong.

    TWO PRODUCTS THAT SHARE ONE VARIABLE ARE A NOTE (#275), and neither
    reads it. `SHAPE_PIN_SOURCE_<PRODUCT>` is the product's name upper-cased
    with every character outside `[A-Z0-9_]` turned into `_`, so `open-glass`,
    `open_glass` and `open.glass` are three pin files and one variable.
    Whichever checkout it named answered for all of them, and the pin it was
    not a checkout of was reported as `neutral-pin-source-unreadable`: drift
    in the project, said about a variable. Now no pin reads it, each pin
    verifies from its own source, and `neutral-pin-source-collides` says so
    and goes no further: it is not a finding, because a project that already
    declares such a pair could not otherwise take a shape update, and which
    declaration to drop is a human's to decide.

    The `--pin-source` values are READ here rather than in `main`, because
    whether `a=b/openGlass` is keyed to a product or a bare path depends on
    the pins this manifest declares (#295); each one no pin used is noted
    once every pin has been checked.

    A VALUE THAT IS NOT A LIST IS A FINDING AND DECLARES NOTHING (#443),
    asked before `PinSources` reads it, in `validate-manifest.py`'s words for
    the same field (`manifest-neutral-product-pins`). Iterated as it stood,
    `5`, `true` or `1.5` ended this validator in a `TypeError`, and a scalar
    `openXdox` (or a mapping) was read one character (or key) at a time, so
    the run refused `neutral-pin-missing` for a pin on `'o'`, a name nobody
    wrote. Absent or null declares no pin, as ever; `0`, `false` and `''`,
    which `or []` read as an empty list, are the finding too.
    """
    products = manifest.get("neutral_product_pins")
    not_a_list = products is not None and not isinstance(products, list)
    if not_a_list:
        report.finding(
            "manifest-neutral-product-pins",
            f"neutral_product_pins is {products!r}, expected a list of "
            "neutral product names")
    if not isinstance(products, list):
        products = []
    sources = PinSources(pin_source_values, products)
    _report_pin_source_collisions(products, report)
    shared = frozenset(pin_source_env_shared(products))
    for product in products:
        _check_one_neutral_product_pin(root, product, report, sources, shared)
    _note_unused_pin_sources(sources, report, not_a_list)


def _note_unused_pin_sources(sources: PinSources, report: Report,
                             not_a_list: bool = False) -> None:
    """A note for each `--pin-source` value no declared pin read (#295),
    naming it as typed and why: a later value replaced it, its pin was never
    recomputed, nothing is declared, or every pin had a more specific
    answer. A value holding `=` that was read as a PATH says so, because
    that is the mistyped key's only trace in the run.

    "As typed" is `_shown`'s (#610): a value that is not printable, and the
    later value that replaced it, are named as `repr` spells them, and so is
    the declared product a keyed value names (#712).

    A FIELD THAT IS NOT A LIST IS NAMED (#712): `not_a_list` says that
    `neutral_product_pins` was `manifest-neutral-product-pins`'s finding,
    so it declares nothing, and the note points at that finding, where it
    said only that nothing is declared and left the reader to find why.
    """
    for typed, product in sources.reading.items():
        if typed in sources.used:
            continue
        later = sources.replaced.get(typed)
        if later is not None:
            why = f"the later `--pin-source {_shown(later)}` replaced it"
        elif product is not None:
            why = (f"{_shown(product)}'s digest was not recomputed from any "
                   "source")
        elif not sources.declared and not_a_list:
            why = ("project.yaml's neutral_product_pins is not a list, so it "
                   "declares no neutral-product pin (see the "
                   "manifest-neutral-product-pins finding)")
        elif not sources.declared:
            why = "project.yaml declares no neutral-product pin"
        else:
            why = ("each declared pin had a more specific source (a keyed "
                   "--pin-source, SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout "
                   "beside this assembly root) or was not recomputed")
        report.unused(" ".join(filter(None, (
            f"--pin-source {_shown(typed)}: not used — {why}.",
            sources.read_as_path(typed)))))


def _load_legs_to_check(root: Path, report: Report
                        ) -> tuple[dict, list[dict]]:
    """The manifest and its non-assembly legs, or a Refusal naming why there
    is nothing here to check. Split from `main` for #132.

    `project.yaml` is named relative to the root, as every file this
    validator names is, where three refusals named its absolute path raw,
    and it is refused by name where it cannot be reached or read (#712).
    Something that is not a file in its place is `manifest-missing` naming
    what it is, with a remedy of its own (#919): see `_no_file`.

    A `legs:` THAT IS NOT A LIST IS A FINDING, NOT THAT REFUSAL (#714), in
    `validate-manifest.py`'s words for it (`manifest-legs`), and no leg is
    checked. Iterated as `manifest.get("legs") or []`, `5` or `true` ended
    this validator in a `TypeError`, and a scalar `openXdox` or a mapping
    was walked one character, or one key, at a time, found no leg, and was
    refused `manifest-no-legs` with the lockstep remedy, which says to run
    `git submodule update`: nothing to do with the cause. The shape pin and
    the neutral-product pins are still checked. A refusal one of them makes
    is printed alone, as every refusal here is, so the finding is not
    printed then. Absent, null or `[]` is still that refusal.

    AN ENTRY THAT IS NOT A MAPPING IS `validate-manifest.py`'S `manifest-leg`
    FINDING, in its words (#714), as the naming gate says it too, and the
    refusal is chosen only where no entry was one: `legs: [5]` was refused
    `manifest-no-legs` with that same remedy, where the other two gates
    found the entry.
    """
    manifest_path = root / "project.yaml"
    if not _is_file(root, manifest_path):
        raise _no_file(
            "manifest-missing", manifest_path, "project.yaml",
            " does not exist, so there is no declaration of which legs to "
            "check. A one-repository project has no legs and does not run "
            "this validator.")
    manifest = _load(root, manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("manifest-unreadable", "project.yaml: not a mapping")
    declared = manifest.get("legs")
    if declared is not None and not isinstance(declared, list):
        report.finding(
            "manifest-legs",
            f"legs is {declared!r}, expected a list of `role:`, "
            "`repository:` and `path:` mappings")
        return manifest, []
    not_mappings = [leg for leg in (declared or [])
                    if not isinstance(leg, dict)]
    for leg in not_mappings:
        report.finding("manifest-leg", f"a leg is not a mapping: {leg!r}")
    legs = [leg for leg in (declared or [])
            if isinstance(leg, dict) and leg.get("role") != "assembly"]
    if not legs and not not_mappings:
        raise Refusal("manifest-no-legs",
                      "project.yaml: no non-assembly legs declared")
    return manifest, legs


def _run_all_checks(root: Path, report: Report,
                    pin_source_values: list[str]) -> None:
    """Every check `main` runs inside its one `try`, in order. Split from
    `main` for #132 so that `try` wraps a single call.
    """
    manifest, legs = _load_legs_to_check(root, report)
    refs = _workflow_refs(root)
    for leg in legs:
        _check_leg(root, leg, report, refs)
    _check_shape_pin(root, manifest, report)
    _check_neutral_product_pins(root, manifest, report, pin_source_values)
    _end_curable_findings(root, report, _end_gitlink_mismatches(root, report))


def _emit_report(report: Report, quiet: bool) -> int:
    """Print the notes and findings and choose the exit code. Split from
    `main` for #132.

    A CHARACTER STDOUT CANNOT ENCODE IS PRINTED ESCAPED (#295). A note names
    a `--pin-source` as typed, and a `sibling checkout (<path>)` line names a
    path, so a stdout in cp1252 (what Windows gives one that is not the
    console) raised `UnicodeEncodeError` on `日本` and turned a passing run
    into a traceback. A `strict` or `surrogateescape` stdout, the two that
    raise, becomes `backslashreplace`, the handler stderr already has; any
    other handler, one somebody chose, is left alone. The tools run from a
    checkout of the standard use `escape_what_stdout_cannot_encode` (#214),
    which also writes a byte `surrogateescape` read in back as that byte; it
    lives in `shape_materialize.py`, which no project carries, and this file
    imports nothing but `repo_shape`, so here such a byte prints as `\\udcXX`,
    as it already does on stderr.

    THE COUNT ENDS AT THE LOCKSTEP RULE ONLY WHERE IT APPLIES (#539): where
    one of `LOCKSTEP_CODES` was found. Every other finding names its own
    exit, and a lone `shape-copy-drift`, an edited copy that `update-shape.py`
    or a revert puts right, was followed by a rule about moving a gitlink, a
    pin and the workflows together.
    """
    if getattr(sys.stdout, "errors", None) in ("strict", "surrogateescape"):
        try:
            sys.stdout.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError, OSError):
            pass
    if not quiet:
        for note in report.notes:
            print(note)
    for finding in report.findings:
        print(finding, file=sys.stderr)
    if report.findings:
        rule = any(code in LOCKSTEP_CODES for code, _ in report.cleared_by)
        print(f"\n{len(report.findings)} finding(s)."
              + (" " + LOCKSTEP if rule else ""), file=sys.stderr)
        return 1
    print("pins ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="assembly root (default: the enclosing repository)")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument(
        "--pin-source", action="append", default=[],
        metavar="[PRODUCT=]PATH",
        help="a local checkout to recompute a neutral-product pin's digest "
             "from, instead of `gh api` — e.g. --pin-source openGlass=../"
             "openGlass. The text before the first `=` is a PRODUCT only when "
             "it names a pin project.yaml declares, and then that reading "
             "wins even over a directory spelled like the whole value "
             "(./PATH reads that directory); any other value is a bare PATH, "
             "which applies to whichever declared pin has no more specific "
             "answer (the common case is exactly one). Repeatable; a value no "
             "pin used is noted, and one that cannot be read is a finding. "
             "SHAPE_PIN_SOURCE_<PRODUCT> (env) and a checkout sitting beside "
             "this assembly root are also tried, before `gh api` and before "
             "this flag's bare form.")
    args = parser.parse_args(argv)

    report = Report()
    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        _run_all_checks(root, report, args.pin_source)
    except Refusal as exc:
        # THE LOCKSTEP REMEDY IS THIS VALIDATOR'S (#370). `repo_shape` gives a
        # refusal built without a remedy none, because it cannot know whose
        # it is; here it is the assembly root's, and every refusal this
        # prints that names no remedy of its own -- its own, and those
        # `load_yaml`, `git_out` and `find_repo_root` raise for it -- gets
        # `REMEDIATION`, exactly as it always did. Only that name is
        # imported, which every `repo_shape.py` a root has ever been given
        # defines, and one that still defaults to it prints it the same way.
        print(exc if exc.remediation else f"{exc}\n{REMEDIATION}",
              file=sys.stderr)
        return 2

    return _emit_report(report, args.quiet)


if __name__ == "__main__":
    sys.exit(main())
