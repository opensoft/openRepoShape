#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after `git clone --recurse-submodules`.

    git clone --recurse-submodules <assembly-root-url>
    cd <Project>
    make bootstrap          # or: python3 scripts/bootstrap.py (python on Windows)

WHAT IT DOES, in order:

  (a) MOVES EACH LEG OFF DETACHED HEAD WITHOUT MOVING THE PIN. A fresh
      recursive clone leaves every submodule detached at the pinned commit —
      the thing that makes people hate submodules, and the first thing an
      engineer meets on day one. Bootstrap creates the tracking branch AT the
      pinned commit, so the WORKING state is branch-shaped while the RECORDED
      state stays an exact pin. It never advances the pin. A tracking branch
      that already exists is FAST-FORWARDED to the pin when its tip is an
      ancestor of it, because that move loses nothing: it is the state
      `bump-leg.py` leaves, the leg detached at the new pin over a branch at
      the old one. A branch AHEAD of the pin with no commit of its own, its
      tip being its upstream's remote-tracking ref, is MOVED BACK to the pin
      from a leg detached there, because that loses nothing either: it is
      what git's own recursive clone leaves when the leg's remote has moved
      past the pin, and the remote-tracking ref still holds every commit.
      Any other branch holding a commit the pin does not contain is never
      moved; bootstrap prints both and leaves them alone. A leg DETACHED at a
      commit that is not the pin is never moved off it either, whether its
      branch is at the pin, behind it, ahead of it or not there at all, and
      whatever the branch or `origin` holds: a commit made there is on no
      branch, and a checkout would leave it only in the reflog, so bootstrap
      says where the leg is instead, and so is one whose HEAD is on a ref
      outside `refs/heads/`, where a commit lands on that ref (#704). A leg
      with a merge, a cherry-pick, a revert, a rebase or an `am` in progress
      is not moved at all: a checkout ends the first three, carrying what
      they staged onto the branch, and leaves the last two to go on over
      it, as it does a cherry-pick or a revert of several commits whose
      stop was committed by hand (its `sequencer/todo` is still there), so
      the line names the operation and the commands that finish or abort
      it (#704). A move git would make over an IGNORED file at a path
      the pin tracks is refused, in git's words, as one over an untracked
      file is. A branch no command can be given (a NUL,
      or a lone surrogate this system cannot encode) is never tried: the leg
      is left as it is and the line says why (#455); step (b)'s manifest
      validator names the key when the manifest holds it. Nor is a branch
      holding a character this system's encoding cannot write (#710): where
      git takes the name in UTF-8, its line says the name is good and to
      run bootstrap under a UTF-8 locale, and where git refuses it there
      too, the line gives git's words. Every name git prints back is read
      as bytes and decoded so that it reaches git again as the bytes it
      was (#710). Advancing a pin
      remains an explicit commit in this repository — see `README.md`, "The
      lockstep invariant". This is why `.gitmodules` carries no `branch=`:
      that would buy the same ergonomics by weakening the pin, and then "what
      commit is this project" would have two answers.

  (b) RUNS THE NEUTRAL VALIDATORS — naming, manifest, lockstep pins. These are
      the only ones a fork with no review lane and no wallet register has, and
      they are enough: a project with no overlays is fully conformant. It then
      prints ONE line if this machine can tell OFFLINE that the upstream shape
      has moved past the pinned commit — see `shape_upstream_notice`, which
      adds no network call and is silent when it cannot answer.

  (c) READS A WALLET REVIEW-AUTHORITY REGISTER IF ONE EXISTS, and prints the
      grants whose objects name this project. If none is found it prints
      exactly `authority is not wallet-carried in this org` and CONTINUES. The
      readout degrades; it never fails. An organisation that has not adopted
      wallet-carried authority is not misconfigured, and a bootstrap that
      failed there would have made the layout load-bearing again.

  (d) EXITS 0 unless a validator failed, and says which way. A validator
      that FOUND something, any exit but 2, ends the run `bootstrap FAILED:
      <name> (exit <code>)`, exit 1. A validator that REFUSED, its exit 2,
      could not check at all, and the run ends `bootstrap REFUSED: <name>
      (exit 2)`, exit 2 (#764). Where one validator found and another
      refused, both lines are said, the finding first, and the run exits 2,
      since a check that could not run outranks a finding. Step (a) and the
      upstream notice refuse `git-not-runnable`, exit 2, where git cannot be
      started, as the validators do (#694): the run stops there and says
      neither line, though a validator may have found or refused by then.
      A `project.yaml` this user cannot read is refused by name, exit 2,
      before step (a), and a validator it cannot read before step (b) runs
      any (#430): read as absent, the first was a project that elected
      nothing and the second a validator SKIPPED, each `bootstrap ok`. A
      leg's `.git`, an operation's marker in its git dir or a register that
      it cannot read is named in its own step, which goes on: the leg is
      left as it is, and nothing is claimed from the register.

SCHEMA-NEUTRAL BY CONTRACT. A one-repository project runs the same command:
step (a) is a no-op where there are no submodules, and steps (c) and (d) are
unchanged. A bootstrap that existed only for electing projects would make the
election worth something operationally, which is exactly what the ratified
doctrine forbids.
"""

from __future__ import annotations

import argparse
import codecs
import errno
import os
import re
import shlex
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    Refusal, escape_unencodable_stdout, find_repo_root, git_out, load_yaml,
    recorded_gitlink, spelled,
)

DEGRADE_LINE = "authority is not wallet-carried in this org"

#: The two OFFLINE ways this command can learn where the upstream shape is.
#: Both are opt-in and neither is consulted unless it is already there:
#: `SHAPE_UPSTREAM_PATH` points at a clone of openRepoShape on this machine,
#: and `.shape-upstream-tip` is a 40-hex commit a nightly job or a human wrote
#: into the root. NO NETWORK CALL IS ADDED HERE, deliberately — `make
#: bootstrap` runs in organisations that cannot reach the upstream at all, and
#: a bootstrap that paused to ask GitHub a question would have made the shape
#: a dependency again, which is the whole thing the copies exist to avoid.
SHAPE_UPSTREAM_ENV = "SHAPE_UPSTREAM_PATH"
SHAPE_UPSTREAM_CACHE = ".shape-upstream-tip"
COMMIT_40 = re.compile(r"^[0-9a-fA-F]{40}$")
#: Where a remote-tracking ref lives. Only an upstream there holds a branch's
#: commits on the remote's behalf; an upstream of `.` is another local branch.
REMOTE_TRACKING = "refs/remotes/"
#: What step (a) prints under git's own lines when git refuses a move.
NOTHING_ELSE = ("          nothing else is tried; the recorded pin is "
                "authoritative. Deal with what git said and run bootstrap "
                "again.")
#: What a leg's git dir holds while git has an operation in progress there,
#: each with what step (a) calls it and the command that ends it, asked in
#: this order (#704): the two rebases first, as git's own `status` asks
#: them, since a pick a rebase stops on is the rebase's to finish or abort.
IN_PROGRESS = (
    ("rebase-apply/applying", "an `am`", "am"),
    ("rebase-apply", "a rebase", "rebase"),
    ("rebase-merge", "a rebase", "rebase"),
    ("MERGE_HEAD", "a merge", "merge"),
    ("CHERRY_PICK_HEAD", "a cherry-pick", "cherry-pick"),
    ("REVERT_HEAD", "a revert", "revert"),
)
#: The two `IN_PROGRESS` markers git writes as REFS (#764). On a leg whose
#: refs are in a reftable (`git init --ref-format=reftable`, git 2.45 and
#: later) neither is a file in the git dir while its operation is in
#: progress: each is in the ref store, which step (a) asks as well
#: (`_in_ref_store`). `MERGE_HEAD` is a file on both backends, as the two
#: rebases' directories and `sequencer/todo` are (measured with git 2.47.1).
IN_REF_STORE = ("CHERRY_PICK_HEAD", "REVERT_HEAD")
#: What a cherry-pick or a revert of SEVERAL commits leaves while it is not
#: done, asked after `IN_PROGRESS`: its stop committed by hand takes the
#: head file away and leaves this, whose first word says which it is.
SEQUENCER_TODO = "sequencer/todo"
#: The remedy of the `git-not-runnable` refusal (#694).
GIT_NOT_RUNNABLE = (
    "Remediation: put git on PATH and run this again. Step (a) reads each "
    "leg's pin and moves the leg through git, and the validators read the "
    "pins through git, so without it nothing here can be placed or checked.")
#: What `_argument_fault` calls a character this system's encoding cannot
#: write (#710): the one fault of a name that is good, so `_say_not_tried`
#: gives it a line of its own.
UNWRITABLE = "a character this system's encoding cannot write"
REGISTER_RELPATH = Path("governance") / "review-authority" / "register.yaml"
VALIDATORS = (
    ("naming", ["scripts/validate-repository-naming.py", "--project",
                "project.yaml", "--quiet"]),
    ("manifest", ["scripts/validate-manifest.py"]),
    ("pins", ["scripts/validate-pins.py"]),
)
#: The exit code a validator ends a REFUSAL with: it could not check, which
#: is not a finding (#764). Every other non-zero code is a failure.
VALIDATOR_REFUSED = 2


def _run(root: Path, args: list[str]) -> int:
    # Flush first: this process's own stdout is block-buffered when it is a
    # pipe, and a child writing straight to the fd would otherwise appear
    # BEFORE the heading that introduces it. The child is told what that fd
    # is (`inherited_child_environment`, #836).
    sys.stdout.flush()
    proc = subprocess.run([sys.executable, *args], cwd=str(root),
                          env=inherited_child_environment(), check=False)
    sys.stdout.flush()
    return proc.returncode


#: The built-in handlers that never raise on a character an encoding cannot
#: hold (#836), so a validator is told the one this stdout has. `strict` and
#: `surrogateescape` raise on such a character, and are not among them.
#: `scripts/shape_materialize.py`'s own set, which a project does not carry.
HANDLERS_THAT_NEVER_RAISE = frozenset((
    "backslashreplace", "ignore", "namereplace", "replace",
    "xmlcharrefreplace"))


def inherited_child_environment() -> dict[str, str]:
    """The environment `_run` starts each validator in: this process's own,
    with `PYTHONIOENCODING` naming the encoding of the stdout the validator
    writes into (#836).

    WHAT WAS WRONG. A child takes its stdout's encoding and handler from its
    OWN environment, and not from the `escape_unencodable_stdout` this
    process ran in `main`. So on a stdout whose code page cannot hold the
    project's name — `PYTHONIOENCODING=cp1252`, or the cp1252 with
    `surrogateescape` Windows gives any stdout that is not the console —
    this file printed `bootstrap: \\u65e5\\u672c`, and `validate-manifest.py`
    then raised `UnicodeEncodeError` at `manifest ok: 日本`: `make
    bootstrap` ended `bootstrap FAILED: manifest (exit 1)` over a manifest
    with nothing wrong in it. It is the defect #254 fixed in `bump-leg.py`
    and `update-shape.py apply`, which run the same two validators.

    THE RULE IS #254's, `scripts/shape_materialize.py`'s
    `inherited_child_environment`: a child that writes into this stdout is
    told the stdout's own encoding, with its handler where that one never
    raises and `backslashreplace` where it does, which is what
    `escape_unencodable_stdout` leaves it with. So a validator's lines and
    this file's are written alike: escaped where the code page cannot hold a
    character, and as they are where it can. A stdout with no usable
    encoding leaves the environment as it is.

    A COPY, as the validators' own `_shown` is. A project does not carry
    `shape_materialize.py`, and a root re-copies its pinned files one row at
    a time, so this file may meet a `repo_shape.py` older than itself, and
    imports nothing new from it. `tests/test_validator_child_encoding.py`
    holds the copy to the library's answer.
    """
    env = dict(os.environ)
    try:
        encoding = codecs.lookup(sys.stdout.encoding).name
    except (AttributeError, LookupError, TypeError):
        return env
    errors = getattr(sys.stdout, "errors", None)
    if errors not in HANDLERS_THAT_NEVER_RAISE:
        errors = "backslashreplace"
    env["PYTHONIOENCODING"] = f"{encoding}:{errors}"
    return env


def _try_git(args: list[str], cwd: Path) -> str | None:
    """What `git <args>` printed in `cwd`, stripped, or `None` where git
    exited non-zero.

    STEP (a)'S ONE DECODE RULE (#710). What git prints is read as BYTES and
    decoded the way the name is encoded when git is handed it again. On
    POSIX that is `os.fsdecode`, as `_head_of` and `_in_progress` read
    theirs: the inverse of the `os.fsencode` that `subprocess` applies to
    each argument, so a name git prints reaches git again as the same bytes
    under any locale. On Windows `subprocess` encodes no argument: it hands
    the command line to `CreateProcessW` as UTF-16, and git for Windows
    reads it, and writes a ref name, in UTF-8. So the bytes are decoded as
    UTF-8 there, as `git_out` decoded them, and not by `os.fsdecode`, which
    `PYTHONLEGACYWINDOWSFSENCODING=1` makes `mbcs` with `replace`, losing
    every character the code page lacks (RV824's N3). Through `git_out`'s
    strict UTF-8, `_upstream_holding` ended `make bootstrap` in a
    `UnicodeDecodeError` traceback over an upstream named with a byte that
    is not UTF-8 (`refs/remotes/origin/a<ff>b`), and, under an `ascii`
    encoding (`LC_ALL=C PYTHONUTF8=0`), in a `UnicodeEncodeError` over one
    named in UTF-8, since the text it read could not be handed back to
    `rev-parse`.

    `git_out` itself keeps its strict decode, as #710's ruling took Option
    2: the readers of `origin`'s URL in `shape-doctor.py` and in the
    advisory it reads take its `UnicodeDecodeError` to mean the URL names
    nothing (#385).

    The BYTES are stripped, of the ASCII whitespace git ends a line with,
    and not the text: `str.strip` also takes away a U+00A0 or a U+3000 that
    ends a name, so `refs/remotes/origin/a<U+00A0>` was read as `.../a`, and
    a branch with no commit of its own past the pin was not moved back.
    """
    try:
        raw = git_out(args, cwd=cwd, binary=True).strip()
    except Refusal:
        return None
    # #710's ruling, Option 2: the decode is step (a)'s own, here, and
    # `repo_shape.git_out` keeps its strict UTF-8 for every other caller.
    return raw.decode("utf-8") if os.name == "nt" else os.fsdecode(raw)


@contextmanager
def _git_runs(unread: str) -> Iterator[None]:
    """`git-not-runnable`, exit 2, where git could not be STARTED in the
    block (#694), with `unread` saying what was being done.

    `git_out` and `_git_says` raise `OSError` then, and nothing here caught
    it: `make bootstrap` with no git on PATH ended in a `FileNotFoundError`
    traceback, exit 1, which is `bootstrap FAILED`'s code. The code and the
    words are the validators'. Which `OSError` is git's is read as
    `validate-pins.py` reads it, by NAME: one whose `filename` is `git`, or
    a nameless `FileNotFoundError` or `PermissionError`, which is what
    Windows raises for a program it cannot start. An error that names a
    directory, which `subprocess` raises for a `cwd` it cannot enter, is
    not git's, and goes on as it did.
    """
    try:
        yield
    except OSError as exc:
        if exc.filename != "git" and (exc.filename is not None or not (
                isinstance(exc, (FileNotFoundError, PermissionError)))):
            raise
        raise Refusal("git-not-runnable",
                      f"{unread}: git could not be run "
                      f"({exc.strerror or exc})", GIT_NOT_RUNNABLE) from exc


#: The `OSError`s that `Path.is_file()` and `exists()` answered False to on
#: Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name: no such file, a part of the path that is not a
#: directory, a bad descriptor, a symlink loop, and Windows' "not ready",
#: "invalid name" and "cannot resolve". Every other one was raised, and is
#: named here as a path this user cannot read (#430), as `validate-pins.py`
#: names it.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)
#: What a path the operating system refused for ANOTHER reason than
#: permission is told (#430): an I/O error, a name longer than the
#: filesystem takes, a file replaced while this ran. No `chmod` puts one
#: right. `validate-pins.py`'s `OTHER_REASON`, word for word.
OTHER_REASON = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. ")
#: The sentence that ends what puts such a path right, `validate-pins.py`'s.
RUN_AGAIN = "Then run the same command again."
#: Why a `project.yaml` this user cannot read is refused (#430).
MANIFEST_READ = (
    "this command reads project.yaml for the legs it places and the "
    "validators it runs, and one it cannot read is not one that is absent, "
    "which would place no leg and check nothing.")
#: Why a validator this user cannot read is refused (#430).
VALIDATOR_READ = (
    "step (b) runs each neutral validator it finds and skips only one that "
    "is not there, and one it cannot read is a check that cannot run, never "
    "a pass.")


def _is_a(path: Path, kind: Callable[[int], bool], *,
          link: bool = False) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, or anything),
    raising the `OSError` of a `stat` the operating system REFUSED (#430).
    With `link`, of the name itself and not of what a symlink there names,
    as `os.path.lexists` asks.

    `validate-pins.py`'s `_is_a`, as a copy: this file imports nothing new
    from `repo_shape.py`, which may be older than it (#370, #610). NOT
    `Path.is_file()` or `exists()`, whose answer depends on the Python, nor
    `os.path.lexists`, whose does not. Up to 3.13 the first two raised a
    refused `stat` out of the run, a traceback and exit 1, which is
    `bootstrap FAILED`'s code; from 3.14 they answer False to ANY `OSError`,
    and `lexists` always has. So a `project.yaml` this user cannot reach was
    a project that elected nothing, and a `scripts/` it cannot search held
    three validators SKIPPED as absent: `bootstrap ok` over a gate nobody
    ran. A leg in a mount it cannot search was NOT INITIALIZED, a register
    it cannot reach was none, and the marker of a cherry-pick in a git dir
    it cannot search was no operation in progress, so the leg was moved and
    the pick's `--continue` went on over the tracking branch. A name the
    operating system cannot take at all (a NUL in it) is nothing there, as
    `is_file()` answered it.
    """
    try:
        mode = (path.lstat() if link else path.stat()).st_mode
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    except ValueError:
        return False
    return kind(mode)


def _named(root: Path, path: Path) -> str:
    """`path` as this file names one it cannot read (#430): relative to
    `root`, POSIX on every platform, or whole where it is not under it (a
    leg's git dir in another worktree), and spelled (#391)."""
    try:
        return spelled(path.relative_to(root).as_posix())
    except ValueError:
        return spelled(str(path))


def _cannot_read(root: Path, path: Path, exc: OSError) -> str:
    """`<path relative to the root>: cannot be read (<the operating
    system's reason>)`, `validate-pins.py`'s line for a path whose `stat` or
    open the operating system refused (#430)."""
    return (f"{_named(root, path)}: cannot be read "
            f"({exc.strerror or type(exc).__name__})")


def _cure(exc: OSError) -> str:
    """What puts right a path this command cannot read (#430), in
    `validate-pins.py`'s words: the mode or the owner for a permission
    (`PermissionError`, which is `EACCES` and `EPERM`), and `OTHER_REASON`
    for any other cause, which is not told to `chmod`. It ends on
    `RUN_AGAIN`."""
    if isinstance(exc, PermissionError):
        return ("Make what this user may not open readable by this user: "
                "`chmod u+r` on a file, `chmod u+rx` on a directory (and on "
                "every directory above it inside the root), or fix who owns "
                "it. " + RUN_AGAIN)
    return OTHER_REASON + RUN_AGAIN


def _unreadable(code: str, root: Path, path: Path, exc: OSError,
                why: str) -> Refusal:
    """The refusal of a file the run cannot go on without, whose `stat` or
    open the operating system refused (#430): `_cannot_read`'s line, then
    `why` the file is read and `_cure`'s advice, as `validate-pins.py`'s
    `_unreadable_file` says it."""
    return Refusal(code, _cannot_read(root, path, exc),
                   f"Remediation: {why} {_cure(exc)}")


def _is_file(root: Path, path: Path, code: str, why: str) -> bool:
    """Whether `path` is a file, asked as `_is_a` asks it, or `code`'s
    refusal naming it (`_unreadable`) where its `stat` was refused
    (#430)."""
    try:
        return _is_a(path, stat.S_ISREG)
    except OSError as exc:
        raise _unreadable(code, root, path, exc, why) from exc


def _load_manifest(root: Path, path: Path):
    """`load_yaml` of `project.yaml`, with one this user cannot OPEN refused
    as one whose `stat` was refused is (`_unreadable`, #430), so a manifest
    at mode 000 and one behind a folder nobody may search say one line.

    Read off the refusal's cause, as `validate-pins.py`'s `_load` reads it:
    `load_yaml` has raised its refusal `from` the `OSError` since it was
    written, so a `repo_shape.py` older than this file is read the same way.
    Any other refusal keeps its words."""
    try:
        return load_yaml(path)
    except Refusal as exc:
        if isinstance(exc.__cause__, OSError):
            raise _unreadable("yaml-unreadable", root, path, exc.__cause__,
                              MANIFEST_READ) from exc.__cause__
        raise


class _Unreadable(Exception):
    """A name in a leg that step (a) must look at and whose `stat` the
    operating system refused (#430): `path`, and its `OSError`, `error`.

    NOT AN `OSError`, so `_git_runs` never takes it for git's, and NOT A
    `Refusal`, so it ends no run: the leg is said to be left as it is
    (`_say_unreadable`), and the next leg is placed, as it is after a leg
    git refused to move."""

    def __init__(self, path: Path, error: OSError):
        super().__init__(path, error)
        self.path = path
        self.error = error


def _found(path: Path, *, link: bool = False) -> bool:
    """Whether anything is at `path` in a leg (its `.git`, or the marker of
    an operation in its git dir), asked as `_is_a` asks it, or `_Unreadable`
    where the operating system refused the `stat` (#430)."""
    try:
        return _is_a(path, lambda _mode: True, link=link)
    except OSError as exc:
        raise _Unreadable(path, exc) from exc


def _say_unreadable(where: str, root: Path, unread: _Unreadable) -> None:
    """A leg step (a) cannot look into (#430): the name it could not reach,
    in `_cannot_read`'s words, that the leg is left as it is, and what puts
    it right. No move is made."""
    print(f"  {where}: {_cannot_read(root, unread.path, unread.error)}, so "
          "the leg is left as it is")
    print(f"          {_cure(unread.error)}")


def _initialized(root: Path, sub: Path, where: str, path: str) -> bool:
    """Whether the leg at `sub` is a checkout step (a) can place, its `.git`
    there, saying why not: NOT INITIALIZED, with the command that makes it
    one, or `_say_unreadable` where the `stat` of its `.git` is refused
    (#430). `Path.exists()` raised that refusal out of the run up to Python
    3.13, a traceback, and from 3.14 answered False, so an initialized leg
    in a mount this user cannot search was NOT INITIALIZED."""
    try:
        there = _found(sub / ".git")
    except _Unreadable as unread:
        _say_unreadable(where, root, unread)
        return False
    if not there:
        print(f"  {where}: NOT INITIALIZED. Run "
              f"`git submodule update --init {spelled(path)}` — the "
              f"validators below will refuse until you do.")
    return there


def _stays_for_an_operation(root: Path, sub: Path, where: str,
                            path: str) -> bool:
    """Whether the leg stays where it is for an operation in progress in it
    (`_say_in_progress`, #704), or for the marker of one that step (a)
    cannot reach (`_say_unreadable`, #430), said either way. Asked through
    `os.path.lexists`, a marker it could not reach was no marker, so a leg
    whose `sequencer/` this user cannot search was moved over a cherry-pick
    that was not done."""
    try:
        doing = _in_progress(sub)
    except _Unreadable as unread:
        _say_unreadable(where, root, unread)
        return True
    if doing is not None:
        _say_in_progress(where, path, *doing)
    return doing is not None


#: What `_argument_fault` calls a character that does not print, or white
#: space (#715): git takes the name, and no person can tell it from the name
#: without it, so `_say_not_tried` gives it a line of its own.
UNSEEN = "a character that does not print or is white space"


def _argument_fault(branch: str) -> str | None:
    """What stops `branch` being an argument to a command, or `None` (#455).

    WHAT WAS WRONG. A branch reaches git as argv (`rev-parse --verify --quiet
    refs/heads/<branch>`, `checkout -q -b <branch> <pin>`) through `_try_git`,
    which catches `Refusal` and nothing else, and `subprocess` cannot hand a
    command a NUL (`ValueError: embedded null byte`) or a lone surrogate the
    system cannot encode (`UnicodeEncodeError`). `tracking_branch: "a\\ud83db"`
    or a leg's `branch: "a\\x00b"` ended `make bootstrap` in a traceback from
    `subprocess.py` in step (a), one step before `validate-manifest.py`, the
    validator that names the key, was reached.

    ASKED BEFORE ANY COMMAND IS BUILT FROM THE VALUE, and not read off an
    exception `_try_git` would then have to swallow: a `UnicodeDecodeError`,
    which `git_out` raises over output that is not UTF-8, is a `ValueError`
    too, and catching that there would read a leg whose HEAD is on such a
    branch as detached.

    A CHARACTER THIS SYSTEM'S ENCODING CANNOT WRITE IS A FAULT TOO (#710,
    Brett Heap's ruling (a) on L4-124), named `UNWRITABLE`. Under
    `LC_ALL=C PYTHONUTF8=0` the encoding is `ascii`, and
    `tracking_branch: "feature/日本"`, which `validate-manifest.py` passes
    and git takes under a UTF-8 locale, ended step (a) in a
    `UnicodeEncodeError` traceback from `subprocess.py`. The leg is left as
    it is, and `_say_not_tried` says why. Its line can call the name good,
    so this fault is asked last, and a name that holds a surrogate at all
    is named for the surrogate instead, even one that is one byte of a name
    (RV824's S1): `validate-manifest.py` names every surrogate (#280), so
    `"日\\udcff"` is not a good name, and #455's line is the true one.
    Whether git takes the name is asked before a line calls it good
    (`_git_refuses_in_utf8`).

    A surrogate that is ONE BYTE of a name is not refused. POSIX spells a name
    that is not UTF-8 with U+DC80 to U+DCFF and `os.fsencode` writes each back
    as the single byte it stands for, so git is handed that byte, as it was
    before this check. Any other surrogate has no byte: `os.fsencode` raises,
    or (`surrogatepass`, Windows) writes the three bytes of a sequence that
    is not UTF-8 for ANY of them, so a lone surrogate is never handed to git
    there either, where a `CreateProcess` would pass it on mangled. The answer
    is `os.fsencode`'s own, so it is the system's and not a list kept here.

    NOR IS A CHARACTER THAT DOES NOT PRINT, OR WHITE SPACE (#715), `UNSEEN`,
    which `validate-manifest.py` refuses in a branch too (`siblings.py` asks
    `isprintable()` alone, so a space it takes).
    git takes `main` followed by U+00A0, and since #715 the reader reads that
    no-break space as YAML does, where it used to strip it: so this step made
    a second `main` beside the first in every leg and checked it out. Asked
    once the name holds neither a NUL nor a lone surrogate, and never of a
    surrogate, so the byte-carrying ones above still reach git. Asked
    BEFORE `UNWRITABLE`, for that fault's reason: a name holding such a
    character is not good under any encoding, so the line that calls a
    name good is never said of it (`"日本 x"` under `LC_ALL=C` is named
    for its space, which the root's own validator names too).
    """
    for char in branch:
        if char == "\x00":
            return "U+0000, a NUL"
        if "\ud800" <= char <= "\udfff" and _fsencoded_length(char) != 1:
            return f"U+{ord(char):04X}, a lone surrogate"
    for char in branch:
        if not "\ud800" <= char <= "\udfff" and (
                not char.isprintable() or char.isspace()):
            return f"U+{ord(char):04X}, {UNSEEN}"
    unwritable = next((char for char in branch
                       if _fsencoded_length(char) == 0), None)
    if unwritable is None:
        return None
    surrogate = next((char for char in branch
                      if "\ud800" <= char <= "\udfff"), None)
    if surrogate is not None:
        return f"U+{ord(surrogate):04X}, a lone surrogate"
    return f"U+{ord(unwritable):04X}, {UNWRITABLE}"


def _fsencoded_length(char: str) -> int:
    """How many bytes `os.fsencode` writes for `char`; 0 when it cannot."""
    try:
        return len(os.fsencode(char))
    except UnicodeEncodeError:
        return 0


def _say_not_tried(where: str, named: str, fault: str,
                   refused: list[str] | None = None) -> None:
    """A branch `_argument_fault` found: no command was run with it. The leg
    stays where it is, and the line says which of the three places the
    person's value can have come from holds it (#455).

    `UNSEEN` (#715) has its own words: git takes `main` followed by U+00A0,
    so "which no command can be given" would be wrong of it, and the name
    to give is the one without that character.

    A character this system's encoding cannot write (`UNWRITABLE`, #710) is
    a branch step (a) DID NOT TRY, not one it could not create: the branch
    can be there already, made by a run under UTF-8 (RV824's N2). Where git
    takes the name in UTF-8 (`refused` is `None`), the line is the one Brett
    Heap ruled on L4-124: the name is good, the encoding is named
    (`sys.getfilesystemencoding()`, the one `os.fsencode` writes with), and
    the two ways to run bootstrap under UTF-8 follow, a UTF-8 locale or
    Python's UTF-8 mode. Where git refuses it in UTF-8 too, `refused` is
    git's lines (`_git_refuses_in_utf8`): the name is not called good, git's
    words are said, and #455's way out follows, since the name itself has
    to change (RV824's S1)."""
    if fault.endswith(UNSEEN):
        print(f"  {where}: could not create branch {named}: it holds "
              f"{fault}, which no person can tell from the name without it; "
              "the leg is left as it is")
        print("          the branch is the leg's `branch:`, else `--branch`, "
              "else `tracking_branch`. Give that one a name with no such "
              "character and run bootstrap again.")
        return
    unwritable = fault.endswith(UNWRITABLE)
    tried = "did not try" if unwritable else "could not create"
    print(f"  {where}: {tried} branch {named}: it holds {fault}, which no "
          "command can be given as an argument; the leg is left as it is")
    if unwritable and refused is None:
        print("          the name is good, and this system's encoding, "
              f"{sys.getfilesystemencoding()}, cannot write it: run bootstrap "
              "again under `LC_ALL=C.UTF-8`, or with `PYTHONUTF8=1`.")
        return
    if unwritable:
        print("          and git refuses it as a branch name in UTF-8 too:")
        _say_lines(refused)
    print("          the branch is the leg's `branch:`, else `--branch`, else "
          "`tracking_branch`. Give that one a name git can create and run "
          "bootstrap again.")


def _git_refuses_in_utf8(root: Path, branch: str) -> list[str] | None:
    """What git says of `branch` as a branch name in the bytes a run under
    UTF-8 would hand it, or `None` when git takes it (#710, RV824's S1).

    A name `_argument_fault` faults as `UNWRITABLE` is not called good until
    git has been asked: `feature/日本..x`, `日本.lock` and `日本 x` are names
    this system's encoding cannot write AND names git refuses in any
    encoding, and the way out the line gave ended in `fatal: ... is not a
    valid branch name`. `git check-ref-format --branch` is git's own answer.
    It is asked of `branch.encode("utf-8", "surrogateescape")`, handed to
    `subprocess` through `os.fsdecode`, which POSIX's `os.fsencode` writes
    back as exactly those bytes under any locale. On Windows no character
    is `UNWRITABLE` (its `os.fsencode` writes UTF-8, or replaces), so this
    is never asked there.

    ASKED IN THE ROOT, not in the leg (RV824's R1-N1). `--branch` makes git
    set up the repository it runs in, so in a leg whose `.git` file names a
    git dir that is gone it exits 128 (`not a git repository`), and a good
    name read as one git refuses there, while the same name was good in the
    next leg. The root is the repository this command was found in, and
    the answer is about the name alone.
    """
    utf8 = os.fsdecode(branch.encode("utf-8", "surrogateescape"))
    return _git_says(["check-ref-format", "--branch", utf8], root)


def _short(sha: str | None) -> str:
    return sha[:12] if sha else "?"


def _git_says(args: list[str], cwd: Path) -> list[str] | None:
    """`None` when `git <args>` succeeds in `cwd`, else the lines git wrote
    to say why not (never an empty list, and never a blank line).

    `_try_git` answers only whether a command worked, which is all a read
    needs. A MOVE git refuses has a reason the person has to act on (an
    untracked file in the way, a branch another worktree has checked out),
    so bootstrap prints git's own words rather than a guess. The bytes are
    decoded here, with `replace`, so no locale's codec decides whether the
    reason can be read. The blank line git puts between two paragraphs is
    dropped: printed under the indent, it was a line of trailing spaces.
    """
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          check=False)
    if proc.returncode == 0:
        return None
    said = proc.stderr.decode("utf-8", "replace").splitlines()
    verb = args[2] if args[0] == "-c" else args[0]
    return [line.rstrip() for line in said if line.strip()] or [
        f"`git {verb}` exited {proc.returncode}"]


def _head_of(sub: Path) -> tuple[str | None, str | None]:
    """The commit the leg has checked out, and the ref HEAD is on (`None`
    when it is detached).

    The ref is read as BYTES and decoded as this system decodes a name it
    is given (`os.fsdecode`), so a branch whose name is not UTF-8 reads
    back as the `refs/heads/<branch>` built from the same name. `git_out`'s
    strict decoding raised `UnicodeDecodeError` over it: a second run with
    `--branch` such a name ended in a traceback in `place_at_pin`, and the
    check of where `checkout -b` left HEAD would end the first (#704)."""
    try:
        ref = git_out(["symbolic-ref", "--quiet", "HEAD"], cwd=sub,
                      binary=True)
    except Refusal:
        ref = None
    return (_try_git(["rev-parse", "--verify", "--quiet", "HEAD"], sub),
            None if ref is None else os.fsdecode(ref.rstrip(b"\r\n")))


def _is_ancestor(sub: Path, commit: str | None, of: str | None) -> bool:
    """Whether `commit` is an ancestor of `of`, as `git merge-base
    --is-ancestor` answers it. A commit this leg has not fetched is not
    known to be one, and is answered no."""
    return commit is not None and of is not None and _try_git(
        ["merge-base", "--is-ancestor", commit, of], sub) is not None


def _upstream_holding(sub: Path, branch: str, local: str) -> str | None:
    """The remote-tracking ref `branch` builds on, when the branch tip
    `local` IS that ref's commit: a branch with no commit of its own.

    `None` for every other branch: one with no upstream, one whose upstream
    is another local branch (`branch.<name>.remote` of `.`), one whose
    remote-tracking ref is not there (never fetched, or pruned) and one
    whose tip is not the upstream's. The two are compared by object id.
    `for-each-ref` names the upstream whether or not its ref exists, and
    takes the branch after `refs/heads/`, where git reads no option. Its
    name is read by `_try_git`'s rule, so on POSIX an upstream named with
    a byte that is not UTF-8, or in UTF-8 under an `ascii` encoding, is the
    same ref when `rev-parse` is handed it, and no longer a traceback
    (#710).
    """
    upstream = _try_git(["for-each-ref", "--format=%(upstream)",
                         f"refs/heads/{branch}"], sub)
    if not upstream or not upstream.startswith(REMOTE_TRACKING):
        return None
    held = _try_git(["rev-parse", "--verify", "--quiet", upstream], sub)
    return upstream if held == local else None


def _held_upstream_past_the_pin(sub: Path, branch: str, local: str,
                                pin: str | None) -> str | None:
    """`_upstream_holding`'s ref when `move_back_to_pin` loses nothing,
    else `None`: the branch is AHEAD of the pin, the pin an ancestor of its
    tip; it has no commit of its own; and HEAD is detached AT the pin, so
    no file changes. Every other branch past the pin keeps its refusal."""
    upstream = _upstream_holding(sub, branch, local)
    if (upstream is None or not _is_ancestor(sub, pin, local)
            or _head_of(sub) != (pin, None)):
        return None
    return upstream


def _check_out(sub: Path, branch: str,
               pin: str) -> tuple[bool, list[str] | None]:
    """`git checkout <branch>`, judged by WHERE HEAD IS AFTERWARDS, not by
    git's exit code. Returns whether HEAD is on the branch at the pin, and
    git's lines when it exited non-zero (never `None` when HEAD is not).

    The two disagree both ways. A checkout git refused (a stale
    `index.lock`, a local edit in the way) leaves HEAD where it was, and a
    later run used to print `on <branch>` over a leg still detached. A
    post-checkout hook's exit status is the checkout's own, so a hook that
    fails after HEAD has moved makes git exit non-zero over a checkout that
    happened, which is not a refusal.

    `--no-overwrite-ignore` (#704): git's default overwrites an IGNORED
    file at a path the branch tracks, silently, where it refuses an
    untracked one; with it, git refuses both, in the same words.
    """
    why = _git_says(["checkout", "-q", "--no-overwrite-ignore", branch], sub)
    if _head_of(sub) == (pin, f"refs/heads/{branch}"):
        return True, why
    return False, why or [
        "`git checkout` exited 0, and HEAD is not on the branch at the pin"]


def _move_and_check_out(sub: Path, branch: str,
                        pin: str) -> tuple[bool, bool, list[str] | None]:
    """From HEAD DETACHED AT THE PIN, or on ANOTHER BRANCH (#603, D1):
    `branch -f <branch> <pin>`, then `_check_out` of the branch.

    From the pin the branch is by then the commit already checked out, so
    no file in the leg changes, a local edit included. From another branch
    the checkout changes files, as `place_at_pin`'s does, and git refuses
    it where a local change to a file that differs, or an untracked or
    IGNORED file (#704), is in the way: the branch has moved by then, and
    HEAD has not. A leg with an operation in progress is never brought
    here: `checkout_tracking_branch` refuses it first (#704).

    Returns whether the branch moved, whether HEAD is on it at the pin, and
    git's lines (`None` when both steps exited 0). The checkout runs only
    once `branch -f` has worked. A branch that moved is left at the pin when
    the checkout is refused, never put back: putting it back is a second
    ref write a stale lock refuses as well, and the next run finds the
    branch at the pin, which is `place_at_pin`'s state, and says again
    whether it could check it out. Not `checkout -B`: git 2.43 resets a
    branch another worktree has checked out with it, leaving that
    worktree's files behind its own HEAD, where `branch -f` refuses.
    """
    why = _git_says(["branch", "-f", branch, pin], sub)
    if why is not None:
        return False, False, why
    placed, why = _check_out(sub, branch, pin)
    return True, placed, why


def _say_lines(why: list[str]) -> None:
    for line in why:
        print(f"          {spelled(line.strip())}")


def _say_refused(first: str, why: list[str]) -> None:
    """A move git refused: `first`, git's own lines under it, spelled
    (#391), then what to do."""
    print(first)
    _say_lines(why)
    print(NOTHING_ELSE)


def _say_after(why: list[str] | None, moved: bool = True) -> None:
    """What git said when it exited non-zero AFTER HEAD reached the branch
    (a failing post-checkout hook): the move happened and its line has been
    printed, so git's words follow it as they are, not as a refusal.

    `moved` is whether the checkout changed where HEAD is. HEAD already on
    the branch at the pin, there was nothing to check out, so `checked out,
    and then git said:` over a stale `.git/index.lock` was false (#533). What
    is true of that state whatever git exited over (a stale lock, a failing
    post-checkout hook, an unmerged index) is that there was nothing to check
    out, so that is what it says, and never `refused`: a hook failing is not
    a refusal. Git's lines follow either way: the same lock blocks the
    person's next commit.
    """
    if why:
        print("          checked out, and then git said:" if moved else
              "          nothing to check out, and then git said:")
        _say_lines(why)


def _place_of(current: str | None) -> str:
    """Where HEAD is, for a line that names it: `detached`, or `on <branch>`
    with the branch spelled (#391)."""
    if current is None:
        return "detached"
    return "on " + spelled(current.split("refs/heads/", 1)[-1])


def _say_left(head: str | None, current: str, named: str) -> None:
    """The line under `fast-forwarded` (#603), or under `on <branch>` or
    `created` (#704), when the leg started on ANOTHER branch, `current`,
    and is on the tracking branch `named` now.

    The person is told, since their next commit lands on `named`. P9
    (`place_at_pin`) used to say nothing of the branch it left, where T7
    (`fast_forward_to_pin`) said it for the same move (#704). `head` is
    `None` for a branch with no commit yet, which has no commit to keep, so
    it is said so. Its own function, so that `fast_forward_to_pin` stays
    within Sonar's cognitive-complexity limit (S3776).
    """
    kept = ("a branch with no commit yet" if head is None
            else "which keeps its commits")
    print(f"          the leg was {_place_of(current)}, {kept}; it is on "
          f"{named} now")


def _say_keep(options: str = "the pin or the branch") -> None:
    """What to do about a checkout step (a) will not move, in the words
    both refusals of it share. Nothing moves."""
    print("          not moving the checkout off it. Keep any commit made "
          f"there on a branch, check out {options} in the leg, and run "
          "bootstrap again.")


def _say_neither(label: str, state: str, head: str | None,
                 current: str | None) -> None:
    """The checkout is not one a move starts from: `state` says what the
    branch is to the pin, and the line names where the leg stands instead.
    Nothing moves. A commit made on a leg detached off the pin is on no
    branch, so checking the branch out would leave it only in the reflog,
    and one made on a HEAD on a ref outside `refs/heads/` lands on that ref
    (#704). A leg on another branch is not said here (#603): that branch
    holds its commits, so the leg is moved off it."""
    print(f"  {label}: {state}, and the checkout is at {_short(head)} "
          f"({_place_of(current)}), which is neither")
    _say_keep()


def _on_a_branch(current: str | None) -> bool:
    """Whether HEAD is on a branch, `refs/heads/<name>`, one with no commit
    yet included: the one checkout besides the pin a move starts from."""
    return current is not None and current.startswith("refs/heads/")


def _in_progress(sub: Path) -> tuple[tuple[str, str, str], str] | None:
    """The `IN_PROGRESS` row of the operation git has in progress in the
    leg, with where its marker is (`git dir` or `ref store`), or `None`
    (#704).

    Asked of the leg's own git dir, which `git rev-parse --git-dir` names
    (a submodule's is under the root's `.git/modules/`, a linked
    worktree's under the leg's `worktrees/`, and each operation's state is
    that worktree's own). Read as bytes and decoded as the system decodes a
    path, so no name of a directory can fail the read. A leg git names no
    git dir for has nothing to read here, and the move after this says what
    git says of it.

    A cherry-pick's or a revert's marker is asked of the leg's ref store
    too (`IN_REF_STORE`, #764). On a reftable leg it is there and in no
    file, so a leg stopped in either was moved, and the move ended it as
    #704 measured on the files backend: `CHERRY_PICK_HEAD` or `REVERT_HEAD`
    gone, and what it had staged carried onto the tracking branch.

    A marker whose `stat` the operating system refuses is `_Unreadable`
    (#430), never no marker: `os.path.lexists` answered False to it.
    """
    try:
        said = git_out(["rev-parse", "--git-dir"], cwd=sub, binary=True)
    except Refusal:
        return None
    gitdir = sub / os.fsdecode(said.rstrip(b"\r\n"))
    for row in IN_PROGRESS:
        if _found(gitdir / row[0], link=True):
            return row, "git dir"
        if row[0] in IN_REF_STORE and _in_ref_store(sub, row[0]):
            return row, "ref store"
    sequence = _sequence_in_progress(gitdir)
    return None if sequence is None else (sequence, "git dir")


def _in_ref_store(sub: Path, name: str) -> bool:
    """Whether the leg's ref store holds the ref called exactly `name`
    (#764).

    `git show-ref --exists` (git 2.43 and later) takes the name as it is,
    where `git rev-parse --verify CHERRY_PICK_HEAD` also resolves a branch
    or a tag of that name, which no operation leaves. A git before 2.43
    refuses the option and is answered no: such a git has no reftable
    either, so the file `_in_progress` asks first is the whole answer
    there."""
    return _try_git(["show-ref", "--exists", name], sub) is not None


def _sequence_in_progress(gitdir: Path) -> tuple[str, str, str] | None:
    """A cherry-pick or a revert of several commits that is not done, or
    `None` (rv704's S1 on #704).

    `git cherry-pick A B` stops on a conflict in A, the person resolves it
    and commits by hand: `CHERRY_PICK_HEAD` is gone, and `git status` still
    says `Cherry-pick currently in progress.` and to run `git cherry-pick
    --continue`, which picks B onto wherever HEAD is by then. A move onto
    the tracking branch put B there. `sequencer/todo` is what is left, and
    its first word is `revert` for a revert and `pick` for a cherry-pick;
    a file that cannot be read is taken as the cherry-pick, the commoner.
    A `sequencer/` this user cannot search is `_Unreadable` (#430): the
    leg is left as it is, and no `todo` is said to be missing."""
    todo = gitdir / SEQUENCER_TODO
    if not _found(todo, link=True):
        return None
    try:
        first = todo.read_bytes().split(None, 1)[:1]
    except OSError:
        first = []
    if first == [b"revert"]:
        return SEQUENCER_TODO, "a revert", "revert"
    return SEQUENCER_TODO, "a cherry-pick", "cherry-pick"


def _say_in_progress(label: str, path: str, row: tuple[str, str, str],
                     held: str) -> None:
    """A leg with an operation in progress (#704): what is in progress,
    where git holds its marker (`held`, #764), that nothing moved, and the
    two commands that end it, the leg's path shell-quoted, then spelled, as
    `move_back_to_pin` prints its command.

    No move is made from here. A checkout of the tracking branch, even from
    HEAD on it already or detached at the pin, ends a merge, a cherry-pick
    or a revert, taking away the head file `--continue` reads and carrying
    the staged result onto the branch, and it puts a rebase or an `am` on
    the branch, which goes on from there, as a cherry-pick or a revert of
    several commits does once its stop is committed by hand (its
    `sequencer/todo`); `merge --ff-only` refuses some of them and not
    others. It is the operation's own to finish or abort, so every such leg
    is refused alike, before any path of step (a) is chosen."""
    marker, doing, verb = row
    command = f"git -C {spelled(shlex.quote(path))} {verb}"
    print(f"  {label}: {doing} is in progress in the leg ({marker} is in its "
          f"{held}), so nothing moved")
    print(f"          finish it (`{command} --continue`) or abort it "
          f"(`{command} --abort`), then run bootstrap again.")


def place_at_pin(sub: Path, label: str, branch: str, pin: str) -> None:
    """Step (a) for a leg whose tracking branch IS the pin: check it out,
    and say `on <branch>` only when HEAD is on it afterwards.

    A checkout git refuses is said in git's words, and the leg stays where
    it is. It used to be ignored and the `on` line printed anyway, over a
    leg left detached (a stale `index.lock`) or on another branch (a local
    edit in the way): the next commit made there was on no branch, or on
    the wrong one, under a line saying otherwise.

    HEAD is read first (#533). Detached at a commit that is NOT the pin, the
    leg is left there, as `fast_forward_to_pin` leaves it. `bump-leg.py` to
    a branch's own tip, then a commit made on the detached leg, then
    bootstrap, checked the branch out and printed `on <branch> at <pin>`
    over a commit that was then on no branch, held by HEAD's reflog alone.
    Detached AT the pin, or already on the branch, the checkout is as it was.
    On ANOTHER branch it is as it was too: that branch holds its commits,
    and the line under `on <branch>` now says the leg left it, as T7's does
    (#704). A HEAD on a ref outside `refs/heads/` (`git symbolic-ref HEAD
    refs/remotes/origin/main`) is left where it is, as T7 leaves it: a
    commit made there lands on that ref, and this placed the leg while T7
    said `which is neither` of the same HEAD (#704).
    """
    named = spelled(branch)
    head, current = _head_of(sub)
    if not (_on_a_branch(current) or (current is None and head == pin)):
        _say_neither(label, f"branch {named} is at the pin {_short(pin)}",
                     head, current)
        return
    already = (head, current) == (pin, f"refs/heads/{branch}")
    placed, why = _check_out(sub, branch, pin)
    if not placed:
        _say_refused(f"  {label}: branch {named} is at the pin "
                     f"{_short(pin)}, and git refused to check it out:", why)
        return
    print(f"  {label}: on {named} at {_short(pin)} (branch tip == pin)")
    if current not in (None, f"refs/heads/{branch}"):
        _say_left(head, current, named)
    _say_after(why, moved=not already)


def fast_forward_to_pin(sub: Path, label: str, branch: str, local: str,
                        pin: str, remote: str | None) -> None:
    """Step (a) for a leg whose tracking branch is BEHIND the pin (#475).

    The branch tip `local` is an ancestor of `pin`, so moving the branch to
    the pin loses nothing. It is the state `bump-leg.py` leaves: the leg
    DETACHED at the new pin over the branch an earlier bootstrap placed at
    the old one. It used to stay detached, and the next commit made in the
    leg was on no branch. The branch is moved, and the leg put on it, from
    exactly three checkouts:

    - HEAD on the branch itself: `merge --ff-only`, which moves the working
      tree too, and moves nothing when a local change to a file the move
      changes, or an untracked file, is in the way, or an ignored one
      (`--no-overwrite-ignore`, #704). `merge.autostash` is
      off for it: with it on, git stashes the change, moves the branch,
      applies the stash back into conflicts and exits 0, and the leg was
      left unmerged under a line saying it had been fast-forwarded. `-c`,
      not `--no-autostash`, which a git before 2.27 refuses as an unknown
      option; such a git has no autostash and ignores the key.
    - HEAD detached AT THE PIN: `_move_and_check_out`.
    - HEAD on ANOTHER BRANCH, a `refs/heads/` ref that is not the tracking
      branch (#603, D1 of its checklist triage): `_move_and_check_out`. The
      other branch is not touched and keeps every commit made on it, so the
      move loses no commit and that work is no reason to leave the leg
      there. `place_at_pin` already checks the tracking branch out from
      this checkout when it is AT the pin; leaving the leg for a branch
      BEHIND the pin was a difference nobody could explain (#458). The
      checkout changes files from here, so git can refuse it over a local
      edit or an untracked or ignored file, and `_move_and_check_out` says
      what is left then. A HEAD on a branch with no commit yet takes this
      path too, as it does in `place_at_pin`. When the checkout is made,
      one line under the `fast-forwarded` one says the leg left that
      branch, and that it keeps its commits, since the next commit made in
      the leg is on the tracking branch now. NO COMMIT IS LOST, AND NOTHING
      ELSE A PERSON HAS (#704): git used to overwrite an IGNORED file at a
      path the pin tracks, here, in `place_at_pin`, in the missing-branch
      path and in the on-branch `merge --ff-only`, and a checkout ended a
      merge in progress on the other branch, its `MERGE_HEAD` removed and
      its staged result carried onto the tracking branch. Every move now
      refuses the first, and no leg with an operation in progress reaches
      here (`_say_in_progress`).

    A LEG DETACHED OFF THE PIN IS LEFT WHERE IT IS: a commit made on the
    detached leg after the bump is on no branch, and checking the branch
    out would leave it only in the reflog. That is said, with what to do,
    and nothing moves. So is a HEAD on a ref outside `refs/heads/`, which
    `place_at_pin` now leaves too (#704).

    `label` is the leg as `checkout_tracking_branch` prints it, already
    spelled; the branch names and git's own lines are spelled here (#391).
    """
    named = spelled(branch)
    head, current = _head_of(sub)
    other_branch = (_on_a_branch(current)
                    and current != f"refs/heads/{branch}")
    if current == f"refs/heads/{branch}":
        why = _git_says(["-c", "merge.autostash=false", "merge", "--ff-only",
                         "--no-overwrite-ignore", "-q", pin], sub)
        moved = placed = why is None
    elif other_branch or (current is None and head == pin):
        moved, placed, why = _move_and_check_out(sub, branch, pin)
    else:
        _say_neither(label, f"branch {named} tip {_short(local)} is behind "
                     f"the PIN {_short(pin)}", head, current)
        return
    if not placed:
        if moved:
            first = (f"  {label}: branch {named} moved {_short(local)} -> "
                     f"{_short(pin)}, the pin, and git refused to check it "
                     "out:")
        else:
            first = (f"  {label}: branch {named} tip {_short(local)} is "
                     f"behind the PIN {_short(pin)}, and git refused to move "
                     "it:")
        _say_refused(first, why or [])
        return
    note = ""
    if remote is not None and remote != pin:
        note = (f"; origin/{named} is {_short(remote)}, which the pin "
                "deliberately does NOT follow")
    print(f"  {label}: branch {named} fast-forwarded {_short(local)} -> "
          f"{_short(pin)}, the pin{note}")
    if other_branch:
        _say_left(head, current, named)
    _say_after(why)


def move_back_to_pin(sub: Path, label: str, path: str, branch: str,
                     local: str, pin: str, upstream: str) -> None:
    """Step (a) for a tracking branch AHEAD of the pin with no commit of
    its own (#475).

    `git clone --recurse-submodules` makes each leg's branch at its
    remote's tip and leaves HEAD detached at the pin. Where the leg's
    remote has moved past the pin, which is the ordinary state of an active
    project, the branch is ahead of the pin, and step (a) used to leave the
    leg detached, where the next commit made in it is on no branch: the
    harm `bump-leg.py` left, met on the first day instead.

    The caller has made sure that moving the branch back loses nothing: its
    tip `local` IS the commit of `upstream`, a remote-tracking ref, which
    still holds every commit the branch has past the pin; and HEAD is
    detached AT the pin, so `_move_and_check_out` changes no file. The one
    line printed says where those commits are and names the command that
    brings the branch forward, which is the person's to run: what this
    project records is the pin. The command's leg path and upstream are
    shell-quoted, then spelled, as `scripts/family.py` quotes the commands
    it prints.

    "Nothing is lost" holds at the last fetch. A commit the branch held
    that the remote has since DROPPED, by a force-push to the leg's shared
    branch, is left only in the reflog once the next fetch moves the
    remote-tracking ref; nothing in the leg can see that before it fetches.
    """
    named = spelled(branch)
    short = upstream[len(REMOTE_TRACKING):]
    held = spelled(short)
    moved, placed, why = _move_and_check_out(sub, branch, pin)
    if not placed:
        if moved:
            first = (f"  {label}: branch {named} moved back {_short(local)} "
                     f"-> {_short(pin)}, the pin ({held} still holds "
                     f"{_short(local)}), and git refused to check it out:")
        else:
            first = (f"  {label}: branch {named} tip {_short(local)} is "
                     f"ahead of the PIN {_short(pin)} with no commit {held} "
                     "lacks, and git refused to move it back:")
        _say_refused(first, why or [])
        return
    print(f"  {label}: branch {named} moved back {_short(local)} -> "
          f"{_short(pin)}, the pin; nothing is lost, {held} still holds "
          f"those commits, and `git -C {spelled(shlex.quote(path))} merge "
          f"--ff-only {spelled(shlex.quote(short))}` brings the branch "
          "forward")
    _say_after(why)


def _stays(sub: Path, branch: str, pin: str) -> str:
    """Where the checkout stays, for the `not moving an existing branch`
    line (#533): `on <branch> at its tip` when HEAD is on the branch that
    holds the commits the pin lacks, `at the pin` when it is detached there,
    and else `at <sha> (detached)` or `at <sha> (on <other branch>)`, as
    `_say_neither` names the place. The line said `at the pin` whatever the
    checkout was, which was false for a HEAD on the branch itself."""
    head, current = _head_of(sub)
    if current == f"refs/heads/{branch}":
        return f"on {spelled(branch)} at its tip"
    if current is None and head == pin:
        return "at the pin"
    return f"at {_short(head)} ({_place_of(current)})"


def create_at_pin(sub: Path, label: str, branch: str, pin: str,
                  remote: str | None) -> None:
    """Step (a) for a leg whose tracking branch IS NOT THERE: `checkout -b
    <branch> <pin>`, from HEAD detached at the pin or on a branch, a branch
    with no commit yet included.

    A checkout git refuses is said in git's own words under the line that
    says the branch could not be made (#704), with `--no-overwrite-ignore`,
    so an IGNORED file at a path the pin tracks is refused as an untracked
    one is, where git overwrote it silently. The line used to say `leaving
    detached` of a leg on another branch, too; it says where the leg stays.
    A HEAD on a ref outside `refs/heads/` is left where it is, as the
    branch-at-the-pin and the behind-branch paths leave it (#704).

    The checkout is judged by WHERE HEAD IS AFTERWARDS, as `_check_out`
    judges one (#533; rv704's S3): a post-checkout hook that fails after
    the branch is made makes git exit non-zero, and the line said `could
    not create` over a leg on the branch at the pin. It says `created`,
    and git's words follow it (`_say_after`). From another branch, the line
    under `created` says the leg left it, as P9's and T7's do (rv704's S2).
    """
    named = spelled(branch)
    head, current = _head_of(sub)
    if head is not None and current is None and head != pin:
        # `checkout -b <branch> <pin>` from a leg detached anywhere else
        # leaves the commit made there on no branch (#533), as placing a
        # branch that exists would. The branch is not there to check
        # out, so the way out names the pin alone. A HEAD git cannot
        # read (the leg's gitdir is gone) is no commit to keep: the
        # checkout below fails, and says it could not.
        print(f"  {label}: branch {named} does not exist, and the "
              f"checkout is at {_short(head)} (detached), which is not "
              f"the pin {_short(pin)}")
        _say_keep("the pin")
        return
    if current is not None and not _on_a_branch(current):
        print(f"  {label}: branch {named} does not exist, and the checkout "
              f"is at {_short(head)} ({_place_of(current)}), which is not a "
              "branch")
        _say_keep("the pin")
        return
    why = _git_says(["checkout", "-q", "--no-overwrite-ignore", "-b", branch,
                     pin], sub)
    if _head_of(sub) != (pin, f"refs/heads/{branch}"):
        stays = "detached" if current is None else f"it {_place_of(current)}"
        _say_refused(f"  {label}: could not create branch {branch!r} at "
                     f"the pin {_short(pin)}; leaving {stays}", why or [
                         "`git checkout -b` exited 0, and HEAD is not on the "
                         "branch at the pin"])
        return
    if remote is not None:
        _try_git(["branch", "-q", f"--set-upstream-to=origin/{branch}",
                  branch], sub)
    state = "at the pin"
    if remote is not None and remote != pin:
        state = (f"at the pin; origin/{named} is {_short(remote)}, which "
                 f"the pin deliberately does NOT follow")
    print(f"  {label}: branch {named} created at "
          f"{_short(pin)} — {state}")
    if current not in (None, f"refs/heads/{branch}"):
        _say_left(head, current, named)
    _say_after(why)


def checkout_tracking_branch(root: Path, leg: dict, branch: str) -> None:
    """Step (a) for one leg. Prints; never moves the pin; and never raises,
    but an `OSError` where git cannot be started (#694), which
    `_checkout_all_tracking_branches` turns into `git-not-runnable`.

    A leg with an operation in progress is refused before any path is
    chosen (`_say_in_progress`, #704), so no move below meets one. So is a
    leg whose `.git`, or an operation's marker in whose git dir, this user
    cannot reach (`_say_unreadable`, #430)."""
    path = str(leg.get("path") or "")
    sub = root / path
    # What is PRINTED of the leg is spelled (#391): `role`, `path` and `branch`
    # are the manifest's text, read before any validator has had its say.
    where = f"[{spelled(leg.get('role'))}] {spelled(path)}"
    named = spelled(branch)
    if not _initialized(root, sub, where, path):
        return
    fault = _argument_fault(branch)
    if fault is not None:
        _say_not_tried(where, named, fault,
                       _git_refuses_in_utf8(root, branch)
                       if fault.endswith(UNWRITABLE) else None)
        return
    pin = recorded_gitlink(root, path)
    local = _try_git(["rev-parse", "--verify", "--quiet",
                      f"refs/heads/{branch}"], sub)
    remote = _try_git(["rev-parse", "--verify", "--quiet",
                       f"refs/remotes/origin/{branch}"], sub)
    if _stays_for_an_operation(root, sub, where, path):
        return

    if local is None:
        if pin is None:
            print(f"  {where}: no gitlink recorded; leaving as is")
        else:
            create_at_pin(sub, where, branch, pin, remote)
        return

    if local == pin:
        place_at_pin(sub, where, branch, pin)
        return

    if _is_ancestor(sub, local, pin):
        fast_forward_to_pin(sub, where, branch, local, pin, remote)
        return

    upstream = _held_upstream_past_the_pin(sub, branch, local, pin)
    if upstream is not None:
        move_back_to_pin(sub, where, path, branch, local, pin, upstream)
        return

    print(f"  {where}: PIN {_short(pin)} != branch {named} tip "
          f"{_short(local)}")
    print("          not moving an existing branch. The checkout stays "
          f"{_stays(sub, branch, pin)}; the recorded pin is authoritative "
          "and advancing it is an explicit commit in this repository.")


def shape_upstream_notice(root: Path) -> None:
    """ONE LINE, and only when this machine can already answer offline.

    The pin says which openRepoShape the copied files came from; it cannot say
    whether that revision is still the current one. Where the answer happens to
    be on this machine — a clone at `SHAPE_UPSTREAM_PATH`, or a tip somebody
    cached at `.shape-upstream-tip` — saying so costs nothing and closes the
    gap that had two projects updated by hand. Where it is not, this is silent:
    an absent answer is not a finding, and it never fails the bootstrap. A
    clone named there that git cannot be STARTED to read is no absent
    answer but a machine with no git, refused `git-not-runnable` (#694).

    A READ THE SYSTEM REFUSES IS AN ABSENT ANSWER TOO (#764), and so is a
    `contracts/shape-pin.yaml` that is not a mapping, which `validate-pins.py`
    has refused by then: each ended `make bootstrap` in a traceback, exit 1.
    The two reads of the answer itself are `_clone_tip` and `_cached_tip`.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    try:
        pin = load_yaml(pin_path) if pin_path.is_file() else None
    except (OSError, Refusal):
        return
    pinned = str((pin if isinstance(pin, dict) else {}).get("commit")
                 or "").lower()
    if not COMMIT_40.match(pinned):
        return
    tip = _clone_tip(os.environ.get(SHAPE_UPSTREAM_ENV))
    if tip is None:
        tip = _cached_tip(root)
    if not tip or not COMMIT_40.match(tip):
        return
    if tip.lower() == pinned:
        return
    print(f"  shape: the upstream is at {tip[:12]} and this project is pinned "
          f"at {pinned[:12]}. Run openRepoShape's "
          f"`update-shape.py check --root .` to see what moved; nothing here "
          f"is wrong until you have.")


def _clone_tip(upstream: str | None) -> str | None:
    """`HEAD` of the clone `SHAPE_UPSTREAM_PATH` names, or `None` where no
    clone there can be read (#764).

    A directory this process may not enter is no clone it can read. Python
    3.12 and 3.13 raise `PermissionError` from `Path.is_dir` for a path
    under one, and `subprocess` raises it for a `cwd` it cannot enter,
    naming that directory, which `_git_runs` passes on as not git's. Each
    ended `make bootstrap` in a traceback, exit 1, where the notice is
    silent over every other absent answer, and the cache is still asked. A
    git that cannot be STARTED is still `git-not-runnable` (#694): that is
    the `Refusal` `_git_runs` raises, which `except OSError` does not catch.
    """
    if not upstream:
        return None
    try:
        if not Path(upstream).is_dir():
            return None
        with _git_runs(f"the clone {SHAPE_UPSTREAM_ENV} names, "
                       f"{spelled(upstream)}, could not be read"):
            return _try_git(["rev-parse", "HEAD"], Path(upstream))
    except OSError:
        return None


def _cached_tip(root: Path) -> str | None:
    """What `.shape-upstream-tip` holds, less a byte-order mark it starts
    with (#855), or `None` where it cannot be read: not there, a file this
    process may not read, or bytes that are not UTF-8, none of which is a
    commit (#764). The last two ended `make bootstrap` in a `PermissionError`
    or a `UnicodeDecodeError` traceback."""
    cache = root / SHAPE_UPSTREAM_CACHE
    try:
        # `utf-8-sig` takes off the byte-order mark a Windows editor may
        # start the file with (#855). `strip()` keeps U+FEFF, so a marked
        # tip read as no commit and the notice said nothing.
        return (cache.read_text(encoding="utf-8-sig").strip()
                if cache.is_file() else None)
    except (OSError, UnicodeDecodeError):
        return None


def _register_paths(root: Path, legs: list[dict]) -> list[Path]:
    candidates = [root / REGISTER_RELPATH]
    for leg in legs:
        path = str(leg.get("path") or "")
        if path and path != ".":
            candidates.append(root / path / REGISTER_RELPATH)
    return [c for c in candidates if _a_register(c)]


def _a_register(path: Path) -> bool:
    """Whether step (c) takes `path` for a register: a file, or a name whose
    `stat` the operating system refused (#430), which may be one and which
    `_load_register_rows` then names as unreadable. `Path.is_file()` raised
    that refusal out of step (c), which never fails, up to Python 3.13, a
    traceback, and from 3.14 answered False, so the run said `authority is
    not wallet-carried in this org` of a register it could not read."""
    try:
        return _is_a(path, stat.S_ISREG)
    except OSError:
        return True


def _row_objects(row: dict) -> list[str]:
    """Every object identifier a register row scopes authority to.

    Tolerant on purpose: the register's shape is a declared successor rather
    than a ratified schema, and the sibling topic proposes adding path-prefix
    objects below repository granularity. This reads what is there and claims
    nothing about what is not.
    """
    objects: list[str] = []
    for key in ("target_repo", "target_repository", "object"):
        value = row.get(key)
        if isinstance(value, str):
            objects.append(value)
    for container in (row, row.get("scope") if isinstance(row.get("scope"), dict) else {}):
        values = (container or {}).get("objects")
        if isinstance(values, list):
            objects.extend(str(v) for v in values if isinstance(v, (str, int)))
    return objects


def _matches(obj: str, repositories: set[str], prefixes: list[str]) -> bool:
    repo, _, path = obj.partition(":")
    if repo in repositories:
        return True
    if path:
        return any(path.startswith(prefix) for prefix in prefixes)
    return False


def _load_register_rows(register_path: Path,
                        root: Path) -> list[dict] | None:
    """One register file's rows, tolerant of which key holds them.

    Split from `read_authority` for #132. Returns `None` when the file
    itself could not be read — already printed in that case — so the
    caller's loop moves on to the next register file exactly as the
    original loop's `continue` did.

    One this user cannot reach or open is named relative to the root, in
    `_cannot_read`'s words, with what puts it right (#430). Read off the
    refusal's cause, as `_load_manifest` reads it; any other refusal is
    said in its own words, as it was.
    """
    try:
        data = load_yaml(register_path)
    except Refusal as exc:
        cause = exc.__cause__
        unread = isinstance(cause, OSError)
        detail = (_cannot_read(root, register_path, cause) if unread
                  else spelled(exc.detail))
        print(f"    unreadable, so nothing is claimed from it: {detail}")
        if unread:
            print(f"      {_cure(cause)}")
        return None
    rows = []
    if isinstance(data, dict):
        for key in ("rows", "grants", "entries"):
            value = data.get(key)
            if isinstance(value, list):
                rows.extend(r for r in value if isinstance(r, dict))
    return rows


def _row_report_line(row: dict, repositories: set[str],
                     prefixes: list[str]) -> str | None:
    """One register row, formatted for `read_authority`'s report — or
    `None` when it names none of this project's repositories or paths.

    Split from `read_authority` for #132.
    """
    objects = [o for o in _row_objects(row)
              if _matches(o, repositories, prefixes)]
    if not objects:
        return None
    # A register row is a file's text (#391): each value is spelled.
    holder = spelled(row.get("holder_ref") or row.get("holder") or "?")
    act = spelled(row.get("act") or row.get("acts") or "?")
    state = spelled(row.get("state") or "?")
    expires = spelled(row.get("expires_at") or "-")
    return (f"    {holder} · {act} · {', '.join(map(spelled, objects))} · "
           f"{state} · expires {expires}")


def _report_one_register(register_path: Path, root: Path,
                         repositories: set[str], prefixes: list[str]) -> None:
    """One register file, start to finish: read it, print each row that
    names this project, and the "no rows"/"no row names…" line when there
    is nothing to show.

    Split from `read_authority` for #132 so its loop over every register
    file found is a single call per file.
    """
    # POSIX, on every platform: this line names a file in the repository,
    # and git and the reader both spell it that way.
    print("  register: "
          f"{spelled(register_path.relative_to(root).as_posix())}")
    rows = _load_register_rows(register_path, root)
    if rows is None:
        return
    if not rows:
        print("    no rows")
        return
    hits = 0
    for row in rows:
        line = _row_report_line(row, repositories, prefixes)
        if line is None:
            continue
        hits += 1
        print(line)
    if not hits:
        print("    no row names this project's repositories or paths")


def read_authority(root: Path, legs: list[dict]) -> None:
    """Step (c). Prints the degrade line and returns when no register exists."""
    found = _register_paths(root, legs)
    if not found:
        print(DEGRADE_LINE)
        print("  (no `governance/review-authority/register.yaml` in the "
              "assembly root or in any leg. Wallet-carried authority is an "
              "OVERLAY; the shape confers nothing without it, and nothing "
              "with it.)")
        return
    repositories = {str(leg.get("repository")) for leg in legs
                    if leg.get("repository")}
    prefixes = [str(leg.get("path")) for leg in legs
                if leg.get("path") and leg.get("path") != "."]
    for register_path in found:
        _report_one_register(register_path, root, repositories, prefixes)
    print("  Grants are read here for REPORTING only. This command confers "
          "nothing and enforces nothing; a required check in the repository "
          "that owns the object is what confers.")


def _load_root_and_manifest(args) -> tuple[Path, dict | None]:
    """`--root`'s repository, and its `project.yaml` if it has one.

    Split from `main` for #132 so its `try` wraps one call — a `Refusal`
    from either step is `main`'s early exit 2, exactly as the original
    function's two separate `try`/`except Refusal` blocks around these same
    two steps both were.

    A `project.yaml` this user cannot reach or open is `yaml-unreadable`,
    naming it (#430), never a project with no manifest: read as absent, no
    leg was placed, no validator ran, and the run said `bootstrap ok`.
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    manifest_path = root / "project.yaml"
    manifest: dict | None = None
    if _is_file(root, manifest_path, "yaml-unreadable", MANIFEST_READ):
        loaded = _load_manifest(root, manifest_path)
        manifest = loaded if isinstance(loaded, dict) else None
    return root, manifest


def _legs_of(manifest: dict | None) -> tuple[list[dict], list[str]]:
    """`(the legs, what names no leg)`: each entry of `project.yaml`'s
    `legs:` that is a mapping, and for what is not, `validate-manifest.py`'s
    finding in its words (#714, #832).

    Iterated as `legs or []`, `legs: 5` ended `make bootstrap` in a
    `TypeError` before step (a) printed a line, and a scalar `openXdox` or a
    mapping was walked one character, or one key, at a time, so step (a)
    said "no submodule legs declared", as of a one-repository project. A
    `legs:` that is not a list names no leg; a list's entry that is not a
    mapping is no leg, and the mappings beside it are still placed, as
    `validate-pins.py` checks the rest past such an entry. Absent or null
    declares no leg and says nothing here: step (b)'s manifest validator
    says `legs is missing or empty`.
    """
    declared = (manifest or {}).get("legs")
    if declared is None:
        return [], []
    if not isinstance(declared, list):
        return [], [f"manifest-legs: legs is {declared!r}, expected a list of "
                    "`role:`, `repository:` and `path:` mappings; no leg is "
                    "placed, and the validators below refuse until `legs:` "
                    "is a list"]
    return ([leg for leg in declared if isinstance(leg, dict)],
            [f"manifest-leg: a leg is not a mapping: {leg!r}; it is not "
             "placed, and the validators below refuse until it is a mapping"
             for leg in declared if not isinstance(leg, dict)])


def _checkout_all_tracking_branches(root: Path, sub_legs: list[dict],
                                    manifest: dict | None,
                                    branch_arg: str | None,
                                    unread: list[str] = ()) -> None:
    """Step (a): place every submodule leg on its tracking branch.

    Split from `main` for #132. Git that cannot be started is
    `git-not-runnable`, naming the leg it met it at (#694): one fact about
    the machine, so no leg after it is tried. `unread` is what `_legs_of`
    found naming no leg, each said first, and a step with nothing else to
    place is not a one-repository project's no-op (#832).
    """
    for line in unread:
        print(f"  {line}")
    if not sub_legs:
        if not unread:
            print("  no submodule legs declared. A one-repository project "
                  "runs the same command and this step is a no-op.")
        return
    branch = branch_arg or (manifest or {}).get("tracking_branch") or "main"
    for leg in sub_legs:
        with _git_runs(f"the {spelled(leg.get('role'))} leg at "
                       f"{spelled(leg.get('path') or '')} could not be "
                       "placed on its tracking branch"):
            checkout_tracking_branch(root, leg,
                                     str(leg.get("branch") or branch))


def _run_neutral_validators(root: Path, manifest: dict | None,
                            skip: bool) -> list[tuple[str, int]]:
    """Step (b): run the neutral validators, then the upstream notice.

    Split from `main` for #132. Returns the label and the exit code of each
    validator that failed, in the order they ran: `_end_of_run` says which
    were findings and which refusals (#764).

    Each validator is looked for BEFORE ANY RUNS, and one whose `stat` the
    operating system refuses is `validator-unreadable`, naming it (#430):
    only one that is not there is SKIPPED. `Path.is_file()` raised that
    refusal out of the run up to Python 3.13, a traceback, and from 3.14
    answered False, so a `scripts/` this user cannot search SKIPPED all
    three and the run said `bootstrap ok`.
    """
    if skip:
        print("  skipped (--skip-validators)")
        return []
    if manifest is None:
        print("  no project.yaml: this project has not elected the schema, "
              "so there is no manifest and no pins to check. It is not less "
              "governed for that.")
        return []
    failed = []
    present = [(label, argv_, _is_file(root, root / argv_[0],
                                       "validator-unreadable",
                                       VALIDATOR_READ))
               for label, argv_ in VALIDATORS]
    for label, argv_, there in present:
        if not there:
            print(f"  {label}: {argv_[0]} is absent; SKIPPED")
            continue
        print(f"  --- {label} ---")
        code = _run(root, argv_)
        if code != 0:
            failed.append((label, code))
    shape_upstream_notice(root)
    return failed


def _end_of_run(failed: list[tuple[str, int]]) -> int:
    """The last line or two of the run, and its exit code (#764).

    A validator's exit 2 is its REFUSAL, that it could not check, and is said
    as one: `bootstrap REFUSED: <name> (exit 2)`, exit 2, the code every
    other refusal here ends with. Any other non-zero exit is a finding, as it
    was: `bootstrap FAILED: <name> (exit <code>)`, exit 1. Where both
    happened both lines are said, the findings first, and the run exits 2,
    since a check that could not run outranks a finding.
    """
    # Stdout first: piped, it is block-buffered and stderr is not, so a log of
    # both would show the lines below before step (c)'s, as `main`'s
    # `git-not-runnable` path takes care that it does not.
    sys.stdout.flush()
    found = [f"{label} (exit {code})" for label, code in failed
             if code != VALIDATOR_REFUSED]
    refused = [f"{label} (exit {code})" for label, code in failed
               if code == VALIDATOR_REFUSED]
    if found:
        print("bootstrap FAILED: " + ", ".join(found), file=sys.stderr)
    if refused:
        print("bootstrap REFUSED: " + ", ".join(refused), file=sys.stderr)
    if refused:
        return 2
    if found:
        return 1
    print("bootstrap ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--branch", default=None,
                        help="tracking branch to place the legs on "
                             "(default: project.yaml `tracking_branch`, else main)")
    parser.add_argument("--skip-validators", action="store_true")
    args = parser.parse_args(argv)

    try:
        root, manifest = _load_root_and_manifest(args)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    legs, unread = _legs_of(manifest)
    sub_legs = [leg for leg in legs if leg.get("role") != "assembly"]

    name = (manifest or {}).get("name") or root.name
    print(f"bootstrap: {spelled(name)} ({spelled(root)})")

    try:
        print("\n(a) legs on tracking branches, pins untouched")
        _checkout_all_tracking_branches(root, sub_legs, manifest, args.branch,
                                        unread)

        print("\n(b) neutral validators")
        failed = _run_neutral_validators(root, manifest, args.skip_validators)
    except Refusal as exc:
        # Only `git-not-runnable` (#694) and step (b)'s
        # `validator-unreadable` (#430) reach here: nothing else in the two
        # steps raises one. Stdout first, so a log of both streams reads in
        # the order the run went.
        sys.stdout.flush()
        print(str(exc), file=sys.stderr)
        return 2

    print("\n(c) review authority")
    read_authority(root, legs)

    print()
    return _end_of_run(failed)


if __name__ == "__main__":
    sys.exit(main())
