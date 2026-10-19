#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate this FAMILY's `family.yaml`, its member pins and its shape copies.

A family is a HOLDER: a repository that pins other projects' assembly roots as
submodules under `members/` and carries the utilities to fetch and bootstrap
them together (Brett Heap, 2026-09-04). It has no spec leg and no code leg,
and this validator is the whole of its gate.

IT CONFERS NOTHING, and neither does membership. No row in `family.yaml`
grants review authority, clearance eligibility, gate standing or lifecycle
state over anything it names; a project in no family is reviewed identically.
A consumer deriving a permission from membership is defective.

WHAT IS CHECKED

  - the envelope: `schema_version`, `kind: family-manifest`, `id`, `name`,
    `org`, `created_by` / `created_on`, `visibility`, `members_dir`
  - the family NAME against `contracts/repository-naming.yaml`, in the
    `family` form. That form is DECLARED-ONLY: `InkRouter` is spelled exactly
    like an assembly root and `family.yaml` is what tells them apart, so the
    declaration is this file's existence and the classifier is asked in those
    terms.
  - `shape`: a commit-and-digest pin of the openRepoShape revision this root
    was cut from, `revision_kind: commit`, never a tag
  - across the rows, that no two name ONE `project:`, in any case:
    `members/IRRS` and `members/irrs` are one directory on macOS and Windows,
    whatever `id:` each row records (#331). This one reads `family.yaml`
    alone, so `--no-members` asks it too.
  - that every entry of `members:` is a mapping, the `member-row` finding
    (#864). It reads `family.yaml` alone, so `--no-members` asks it too.
  - EVERY MEMBER, three ways:
      1. the GITLINK this repository records at `members/<Project>` equals
         `members[].pin.commit` — the same lockstep rule an assembly root
         applies to its legs, for the same reason: two facts that can drift
         apart will;
      2. the tree digest recomputed from the member's own object store equals
         `pin.tree_sha256`, so a gitlink and a pin that agree on a commit
         whose bytes are not the pinned bytes is still drift;
      3. the mounted tree carries a `project.yaml` whose `id` is the `id` this
         row records — a repository at the right commit is not by itself the
         project the row claims.
    A row whose `path:` is not `members/<Project>` is the `member-path`
    finding and none of the three is asked of it: nothing read through a
    path the row may not have is a fact about the member (#367). A row
    whose gitlink is recorded only at a case variant of its path is refused
    naming that variant, the index move that puts it back, and what to do
    with a directory the variant leaves on disk (#611); with `--sparse`
    where a sparse checkout keeps a variant off disk, an entry the index
    holds at or under the row's path moved aside first, and the lines that
    make `.gitmodules` give the row's path where no section of HEAD's does,
    as after a `git mv` (#762). The first is asked of every row before the
    other two are asked of any (#648), so a later row's gitlink refusal is
    never hidden behind an earlier row's `member-uninitialized`, as a plain
    clone whose `git submodule update` died at that gitlink left it. Where
    git's init would stop at a gitlink it has no url for, that refusal
    names it and bootstrap's cure for it before its update, and a pinned
    commit the member's store lacks names the fetch that brings it, or the
    `bump` for one no remote holds (#762).
    And, across the rows, that no two record ONE `id`: that is one project
    pinned twice, however each row spelled its repository (#206). This one
    reads `family.yaml` alone, so `--no-members` asks it too.
  - that no two sections of `.gitmodules` give ONE path (#300): a recursive
    clone fetches that path from only one of them, so the other is a url
    the next edit can make the one. It reads that file alone, so
    `--no-members` asks it too.
  - that no section of `.gitmodules` gives a value git dies on as it reads
    the file, before `git submodule update` checks out any member, the
    `gitmodules-value-refused` finding (#768): a `path`, `url`, `update`,
    `ignore` or `branch` with no value, an `update` other than `none`,
    `checkout`, `rebase` or `merge`, a `shallow` that is no boolean, or a
    `fetchRecurseSubmodules` that is neither a boolean nor `on-demand`. It
    reads the work tree's file and HEAD's, so `--no-members` asks it too,
    and where it is found no member that is not checked out is refused as
    uninitialized: git checked none out.
  - the REVERSE of every member check (#361): that each gitlink this
    repository records in `members/` (the index at stage 0, else HEAD), and
    each path a `.gitmodules` section gives, is a path some row names. A
    member mounted by hand, a row deleted by hand, a section `family.py
    remove` left behind: every check above starts from a row, so none of
    them ever asked. Neither needs a member checked out, so `--no-members`
    asks them too. A path a row names in another case is still one of these,
    and what it says to do depends on which of the two is the member's own:
    it names no command that would un-register the member, and for a member
    recorded only in the wrong case, where its row's path is its canonical
    `members/<Project>` and its pin a 40-hex commit, it names the index move
    that records it at that path, as the row's own refusal does members
    checked (#648). A gitlink whose removal is staged and not committed,
    which HEAD still records, says to commit it, and prints no `git rm`,
    which would fail (#681). One no section of HEAD's `.gitmodules` gives
    a url is said to be checked out nowhere by a recursive clone, and to
    stop a plain clone's `git submodule update --init` (#762).
  - that every gitlink OUTSIDE `members/`, which no row can name, is at a
    path a section of `.gitmodules` gives, the `gitlink-unnamed` finding
    (#878): a plain clone's `git submodule update --init` stops at one no
    section gives (`No url found for submodule path`, exit 128) before it
    checks out any member, as the holder's CI runs it, so it is taken out
    of the index. One a section gives is that section's
    `gitmodules-path-unnamed`, which takes the gitlink out of the index
    first, then the section: taken out alone, the section left the
    gitlink, and this gate passed it. Each `git rm --cached` comes after
    `git add -- .gitmodules` where lines printed before it may leave that
    file with changes not staged, or it holds some, since git takes no
    gitlink out of the index then. Neither needs a member checked out,
    so `--no-members` asks them too.
  - that a section of HEAD's `.gitmodules` gives the path of every row's
    gitlink, the `member-gitmodules-absent` finding (#611, #407's decision
    3). A recursive clone reads HEAD's file, so a gitlink no section of it
    gives is left empty there, by CI and by `make bootstrap`, though the
    holder it was committed in keeps its checkout. It needs no member
    checked out, so `--no-members` asks it too, and a member it names that
    is not checked out is not then refused as uninitialized. A
    `.gitmodules` staged and not committed counts for nothing until it is
    committed, since HEAD's file is the one a clone reads: a `family.py
    add` staged and not committed is this finding for its own member; a
    section taken out and staged, not committed, is no finding; and a file
    put back and staged, not committed, in a holder whose HEAD lost it is
    still this finding for every member. A section that gives the path and
    no url is `member-gitmodules-url-absent`, read the same way (#762).
  - that no row's own gitlink has its removal staged and not committed,
    the `member-gitlink-removal-staged` finding (#762): HEAD still records
    it, and the next commit un-registers the member under its row. It
    needs no member checked out, so `--no-members` asks it too.
  - the COPIED shape files, each against its `sha256` row in
    `contracts/shape-pin.yaml`. Editing a copy in place is drift and the exit
    is to carry it upstream, never to update the digest.

EVERY REMEDY IS TYPED AS PRINTED, IN THE ORDER PRINTED (#879). Where the
work tree's `.gitmodules` is gone from disk, the first remedy that writes
it puts it back first, from where git reads it, but for a
`gitmodules-value-refused` finding, which puts back HEAD's, whose value
its lines take out (#768), and no later one puts it back over what the
lines between wrote: a staged removal's finding after one that writes
the file, or says to commit it, writes its section back key by key and
stages the file, on disk or not. A `git rm` of a gitlink comes after
`git add -- .gitmodules` where lines printed before it leave that file
with changes not staged; and a checkout `git mv` moved off a row's path,
whose `.git` file names that member's store, is named, with its `git -C`
status, before the update that points the store at the row's path.

A PATH THIS USER CANNOT READ IS NEVER ABSENT (#430). Every guard asks the
operating system for the path's `stat` (`_is_a`), the same answer on every
Python, and one it refuses is refused by name, `<path>: cannot be read
(<reason>)`, with a cure for the cause, exit 2: a member's checkout or what
is on disk at any gitlink `member-unreadable`, the shape pin
`shape-pin-unreadable`, a shape copy `shape-copy-unreadable` and
`family.yaml` `family-manifest-unreadable`. A member's `project.yaml` is
the finding `member-manifest-unreadable`, exit 1, as one that cannot be
opened already was. Python 3.14's `is_file()` and `exists()` read each as
not there.

EXIT CODES
    0  the manifest is valid, every member is in lockstep, every copy matches
    1  a FINDING: drift a reviewer can act on
    2  a REFUSAL: the question could not be asked — no manifest, an
       uninitialized member (but for one no section of HEAD's `.gitmodules`
       gives, or gives a url, or whose removal is staged, and any while
       `.gitmodules` gives a value git dies on: those are
       `member-gitmodules-absent`, `member-gitmodules-url-absent`,
       `member-gitlink-removal-staged` and `gitmodules-value-refused`,
       exit 1), an unreadable pin, a path this user cannot read (#430), no
       git to run. An unanswerable question is never an implicit pass.
"""

from __future__ import annotations

import argparse
import errno
import os
import re
import shlex
import stat
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    COMMIT_RE, PROJECT_ID_RE, PYTHON, SHA256_RE, TREE_DIGEST_DEFINITION,
    VISIBILITY_CHOICES, NamingPolicy, Refusal, file_sha256, find_repo_root,
    git_out, load_yaml, recorded_gitlink, repo_basename, spelled,
    tree_digest,
)

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
QUALIFIED_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
MANIFEST = "family.yaml"
GITMODULES = ".gitmodules"
DEFAULT_MEMBERS_DIR = "members"
#: A submodule's entry in a tree or the index, as `ls-files -s` and
#: `ls-tree` spell its mode.
GITLINK_MODE = b"160000"


def _lockstep(root: Path, project: str | None = None,
              member_id: str | None = None) -> str:
    """THE LOCKSTEP RULE, with the `bump` that keeps it, for this holder.

    THE `bump` IT NAMED COULD NOT RUN (#610). The rule said `scripts/
    family.py bump --member <Project> --to <commit>`, with no `--family-root`,
    which `bump` requires, and no branch, though since #487 a real `bump`
    refuses the holder's tracking branch, where a person stands after
    `init`. So it names this holder by its path, as `member-gitlink-absent`'s
    `add` does, and the `git -C <holder> switch -c family/bump-<member>` that
    makes a branch first, as #539's `_switch_line` gives `add` and `remove`.

    `project` is the member a finding is about, its `--member`; the branch
    word is its row's `id:`, or the project where the row records none, as
    `family.py bump` suggests its own (which adds the commit's first twelve,
    unknown here: the `--to` is the person's to choose). The closing count
    names no member, since more than one may be out of step, and says
    `PROJECT_PLACEHOLDER` in both places, as `_switch_line` does.
    """
    member = (PROJECT_PLACEHOLDER if project is None
              else shlex.quote(project))
    word = None if project is None else (member_id or project)
    return (
        "THE LOCKSTEP RULE: a member's gitlink and its `members[].pin.commit` "
        f"in `{MANIFEST}` are ONE invariant. From a checkout of openRepoShape, "
        f"`{PYTHON} scripts/family.py bump --family-root "
        f"{shlex.quote(str(root))} --member {member} --to <commit>` moves both "
        "in one commit, on a branch other than the holder's tracking branch, "
        f"which it refuses (`{_switch_line(root, 'bump', word)}` makes one); "
        f"moving one alone is what this refuses. {BRANCH_LEFT}")


#: The findings THE LOCKSTEP RULE is about (#539): a member's gitlink and its
#: pin out of step, and the pin's digest of the commit they name. The closing
#: count ends at the rule only where one of them was found.
LOCKSTEP_CODES = frozenset({"member-gitlink-mismatch",
                            "member-digest-mismatch"})

#: A branch-name word as `family.py` suggests one (#487, its
#: `BRANCH_WORD_RE`): dot-separated words of lowercase letters, digits, `_`
#: and `-`, and no trailing `.lock`. Anything else is said as `member`.
BRANCH_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_-]*(?:\.[a-z0-9_-]+)*")

#: What a remedy says where it cannot name the member's project, a gitlink
#: whose path gives none: ONE placeholder for the one value, in the branch
#: and in `--member` alike (#539).
PROJECT_PLACEHOLDER = "<Project>"

#: What a remedy that names `_switch_line` says at the end of its prose
#: (#607): where an earlier act left that branch, `switch -c` fails `fatal: a
#: branch named '<branch>' already exists` (exit 128). Another name comes
#: first: it starts the branch where the holder stands now, which works in
#: every state. The same command with `switch` for `switch -c` goes back to
#: the old branch, which is right only where it holds work not merged yet;
#: it keeps its commits, and nothing here names `switch -C`, which resets it.
#: In words, not a second command: this report is read in CI too, where the
#: checkout has none of the person's branches to ask about. `family.py`'s
#: `BRANCH_LEFT`, word for word.
BRANCH_LEFT = ("If `git switch -c` says that branch already exists, an "
               "earlier act left it: give the branch another name, which "
               "starts it where the holder stands, or, only if that branch "
               "holds work not merged yet, the same command with `switch` "
               "in place of `switch -c` goes back to it and keeps every "
               "commit on it.")


def _switch_line(root: Path, verb: str, name: str | None) -> str:
    """`git -C <holder> switch -c family/<verb>-<member>`: the branch
    `family.py add`, `bump` and `remove` refuse to commit without, since a
    holder's tracking branch is refused (`family-on-tracking-branch`, #487),
    spelled as `family.py` suggests it and the holder's docs show it (#539).
    `name` is the member's row `id:` for `remove` and its project for
    `add`, lowercased; None says `PROJECT_PLACEHOLDER`, the one the
    `--member` beside it says. POSIX-quoted, as every other line this file
    prints is. Every remedy that names it ends its prose with `BRANCH_LEFT`
    (#607); openRepoShape's own tests read this file's source and fail one
    that does not."""
    if name is None:
        return (f"git -C {shlex.quote(str(root))} switch -c "
                f"family/{verb}-{PROJECT_PLACEHOLDER}")
    word = name.lower()
    if not BRANCH_WORD_RE.fullmatch(word) or word.endswith(".lock"):
        word = "member"
    return shlex.join(["git", "-C", str(root), "switch", "-c",
                       f"family/{verb}-{word}"])


class Report:
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.notes: list[str] = []
        #: Each finding's code, in step with `findings` (#539).
        self.codes: list[str] = []
        #: Where the work tree's `.gitmodules` is gone from disk, git's name
        #: for the file an earlier finding's line put back there,
        #: `:.gitmodules` or `HEAD:.gitmodules`, so that no later finding
        #: puts it back over what the lines between wrote (#879); empty
        #: until one has.
        self.put_back = ""
        #: Whether a finding printed before says to write the work tree's
        #: `.gitmodules`, or to commit it as it stands, so that no later
        #: finding puts HEAD's file back over that (`_section_back`, lane
        #: 1's MUST 1 and SHOULD 1 on #889).
        self.wrote = False

    def finding(self, code: str, detail: str) -> None:
        self.findings.append(f"FINDING {code}: {detail}")
        self.codes.append(code)

    def note(self, text: str) -> None:
        self.notes.append(f"  ok  {text}")


@contextmanager
def _git_runs(unread: str) -> Iterator[None]:
    """The `git-not-runnable` refusal, exit 2, for a check that reads this
    holder through git and could not start it (#368).

    `git_out` raises `OSError` when there is no git to run, and nothing here
    caught it: the run ended in a `FileNotFoundError` traceback, which exits
    1, a FINDING's code, though nothing was found. So every check that runs
    git, in every mode, runs it inside this, and `unread` says which check
    it was and what it could not read. ONE code for the whole validator,
    whichever check met the missing git first: it is one fact about the
    machine, and `gitmodules-unreadable` keeps meaning a file git ran and
    could not read.

    Around the git calls ALONE, and never around a whole check: a
    `project.yaml` nobody may read is an `OSError` too, and it is not this.
    """
    try:
        yield
    except OSError as exc:
        raise Refusal(
            "git-not-runnable",
            f"{unread}: git could not be run ({exc.strerror or exc})",
            "Remediation: put git on PATH and run this again. This check "
            "reads the holder the way git does, and nothing could clone it "
            "or fetch its members without git either.") from exc


# ---------------------------------------------------------------------------
# A path this user cannot read (#430)
# ---------------------------------------------------------------------------
#
# `Path.is_file()`, `is_dir()` and `exists()` answer differently by Python:
# up to 3.13 they raised a refused `stat` (`PermissionError`) and answered
# False only where nothing was there; from 3.14 they call `os.path.isfile`
# and the like, which answer False to ANY `OSError`. So a member checkout
# this user cannot search ended this run in a traceback on 3.12, and on
# 3.14 was refused `member-uninitialized`, whose `git submodule update`
# then failed on the checkout that was there; a shape copy in a folder
# this user cannot search was `pinned but absent`, the shape pin and
# `family.yaml` `does not exist`, and a staged removal's lines ended on an
# update of a checkout that was there. Every guard here asks the operating
# system itself now, as `bump-leg.py` and `validate-pins.py` do, and a
# `stat` it refuses is refused by name.
#
# THE `os.path.lexists` OF `.gitmodules` STAY, deliberately: it is a name
# at the holder's root, whose `lstat` needs no access the read of
# `family.yaml` before it did not already have, and git reads that file
# by the same `lstat`.

#: The `OSError`s that `Path.is_file()` and `Path.is_dir()` answered False to
#: on Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name to open: no such file, a part of the path that is
#: not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". Every other one was raised.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)


def _is_a(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `stat.S_ISDIR`,
    `_any_kind`), raising the `OSError` of a `stat` the operating system
    REFUSED (#430).

    NOT `Path.is_file()`, `is_dir()` OR `exists()`, whose answer depends on
    the Python. Up to 3.13 they raised a refused `stat` (`PermissionError`)
    and answered False only when nothing was there; from 3.14 they call
    `os.path.isfile` and the like, which answer False to ANY `OSError`. On
    3.14 a member checkout under a `members/` this user cannot search was
    "not an initialized submodule checkout" (`member-uninitialized`, whose
    update then failed `could not open ... for writing`), and a shape copy
    in a folder it can list but not search was "pinned but absent". Asked
    here, every Python answers as 3.9 to 3.13 did, and a refused `stat` is
    a refusal that names the path. `bump-leg.py`'s, word for word.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    except ValueError:
        # a name the operating system cannot take at all (a NUL in it)
        return False
    return kind(mode)


def _any_kind(_mode: int) -> bool:
    """`_is_a`'s kind for anything at all, what `exists()` asked."""
    return True


def _gone(path: Path) -> bool:
    """Whether NOTHING is at `path` (`ENOENT`), asked BEFORE A LINE THAT PUTS
    SOMETHING THERE OR NAMES WHAT TO DELETE (#430): the staged removal's
    `git submodule update` that checks a member out at its path
    (`_put_back_lines`), and the checkouts it names to delete by hand once
    none is at that path (`_moved_checkouts`).

    STRICTER THAN `_is_a`: a part of the path that is not a directory
    (`ENOTDIR`, a file where `members/<P>` should be), a symlink loop and
    every other `OSError` is raised, since each says something IS on the
    way, which that update fails on and which no checkout moved away. As
    `family.py` asks before its clean-ups (#430's slice G). A name the
    operating system cannot take at all holds nothing, as `exists()`
    answered it."""
    try:
        path.stat()
    except FileNotFoundError:
        return True
    except ValueError:
        return True
    return False


#: What a path the operating system refused for ANOTHER reason than
#: permission is told: an I/O error, a name longer than the filesystem
#: takes, a part of the path that is a file. No `chmod` puts one right.
#: `validate-pins.py`'s and `bump-leg.py`'s words for the same refusal
#: (#383, #712).
OTHER_REASON = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. ")

#: The sentence every refusal of a path this validator cannot read ends on.
RUN_AGAIN = "Then run the same command again."

#: What this validator reads, as `_unreadable`'s remedy says it.
PATHS_READ = (f"{MANIFEST}, the shape pin, every copy it lists, each "
              "member's checkout and its project.yaml, and what is on disk "
              "at each gitlink this holder records")

#: A checkout, or what is on disk at a gitlink, whose `stat` the operating
#: system refused (#430): a member's `.git`, a case variant or a stray the
#: holder records, the checkout `git mv` moved. The one new code: no code
#: here meant "a checkout cannot be read", and `member-uninitialized`, what
#: Python 3.14 made of it, sent the person after a checkout that is there.
MEMBER_UNREADABLE = "member-unreadable"


def _advice(exc: OSError) -> str:
    """What to do about `exc`, by its cause, in `validate-pins.py`'s words
    (#712): a permission (`PermissionError`, which is `EACCES` and `EPERM`)
    is put right by the mode or the owner, and any other cause is
    `OTHER_REASON`, which is not told to `chmod`."""
    return ("Make what this user may not open readable by this user: `chmod "
            "u+r` on a file, `chmod u+rx` on a directory (and on every "
            "directory above it inside the root), or fix who owns it. "
            if isinstance(exc, PermissionError) else OTHER_REASON)


def _cannot_read(named: str, exc: OSError) -> str:
    """`<named>: cannot be read (<the operating system's reason>)`, the line
    for a path whose `stat` or open the operating system refused, in
    `validate-pins.py`'s words (#359, #712). `named` is relative to the
    holder, and spelled (`spelled`)."""
    return (f"{spelled(named)}: cannot be read "
            f"({exc.strerror or type(exc).__name__})")


def _unreadable(code: str, named: str, exc: OSError) -> Refusal:
    """`code`'s refusal, exit 2, for the path `named` whose `stat` or open
    the operating system refused (#430): `_cannot_read`'s line and a remedy
    that follows the cause (`_advice`), as `validate-pins.py`'s
    `_unreadable_file` says it. A path this validator must read and cannot
    is a question it cannot answer, never "absent"."""
    return Refusal(
        code, _cannot_read(named, exc),
        f"Remediation: this validator reads {PATHS_READ}, and one it cannot "
        "read is a question it cannot answer, never a pass. "
        + _advice(exc) + RUN_AGAIN)


def _asked(path: Path, kind: Callable[[int], bool], code: str,
           named: str) -> bool:
    """`_is_a(path, kind)`, or `code`'s refusal naming `path` as `named`
    (`_unreadable`) where its `stat` was refused (#430)."""
    try:
        return _is_a(path, kind)
    except OSError as exc:
        raise _unreadable(code, named, exc) from exc


def _checked_out(checkout: Path, path: str) -> bool:
    """Whether a `.git` entry is in `checkout`, the gitlink path `path`
    (what `exists()` asked of it), or `member-unreadable` naming
    `<path>/.git` where its `stat` was refused (#430)."""
    return _asked(checkout / ".git", _any_kind, MEMBER_UNREADABLE,
                  f"{path}/.git")


def _checkout_gone(root: Path, path: str) -> bool:
    """`_gone` of the `.git` at the gitlink path `path`, or
    `member-unreadable` naming it where its `stat` was refused for any
    reason but `ENOENT` (#430)."""
    try:
        return _gone(root / path / ".git")
    except OSError as exc:
        raise _unreadable(MEMBER_UNREADABLE, f"{path}/.git", exc) from exc


def _anything_at(where: Path, named: str) -> bool:
    """Whether anything is at `where`, a symbolic link that leads nowhere
    included, as `os.path.lexists` answered it, or `member-unreadable`
    naming it as `named` where its `stat` was refused (#430).

    `os.path.lexists` answered False to ANY `OSError`, on every Python, so
    a gitlink path in a folder this user cannot search was "nothing on
    disk" (#430). A symbolic link there is on disk, asked by its own
    `lstat` first (`os.path.islink`), as `lexists` asks it: where it leads
    is not asked, so a link that leads nowhere, or into a folder this user
    cannot search, is something on disk and no refusal (r956's trial on
    #956). Anything else is asked by its `stat`, through `_asked`; where
    the `lstat` was refused, so is that `stat`, and the path is refused by
    name."""
    return (os.path.islink(where)
            or _asked(where, _any_kind, MEMBER_UNREADABLE, named))


def _check_schema_kind_and_id(manifest: dict, report: Report) -> None:
    """`schema_version`, `kind` and `id` — three fixed-shape fields that carry
    no lookup and no branch of their own, split from `_check_envelope` for
    #137 so the fields that DO (the name, the dates, the shape block) are not
    buried beside them."""
    if manifest.get("schema_version") != 1:
        report.finding("family-schema-version",
                       f"schema_version is {manifest.get('schema_version')!r}, "
                       "expected 1")
    if manifest.get("kind") != "family-manifest":
        report.finding("family-kind",
                       f"kind is {manifest.get('kind')!r}, expected "
                       "'family-manifest'")
    family_id = manifest.get("id")
    if not isinstance(family_id, str) or not PROJECT_ID_RE.match(family_id):
        report.finding("family-id",
                       f"id is {family_id!r}; it must match "
                       f"{PROJECT_ID_RE.pattern}")


def _check_family_name(manifest: dict, policy: NamingPolicy,
                       report: Report) -> None:
    """The one field in the envelope that is also a naming-policy question:
    is `name` even a string, and if so, does it classify as a family?

    Split from `_check_envelope` for #137: the DECLARED-ONLY classification
    below is its own decision, distinct from the fixed-shape checks beside it.
    """
    name = manifest.get("name")
    if not isinstance(name, str) or not name.strip():
        report.finding("family-name", f"name is {name!r}")
        return
    # THE DECLARED-ONLY FORM, ASKED FOR BY NAME. This manifest IS the
    # declaration, so the classifier is given `family` rather than being
    # left to read a bare CamelCase token as the assembly root it also
    # looks like.
    found = policy.classify(repo_basename(name.strip()), "family")
    if found is None:
        report.finding("naming-unclassified",
                       f"{name!r} matches no family in the naming policy. "
                       "A family holder is one CamelCase token with no "
                       "hyphen, underscore, dot or space.")
    elif found.family != "family":
        report.finding(
            "naming-not-a-family",
            f"{name!r} classifies as {found.family!r}"
            + (f"/{found.role}" if found.role else "")
            + f", not as a family holder ({found.reason})")
    else:
        report.note(f"{name}: {found.family} (declared by {MANIFEST})")


def _check_org_visibility_and_dates(manifest: dict, report: Report) -> None:
    """`org`, `created_by`, `created_on`, `visibility` and `members_dir` —
    five independent fields, none of them read by any other check, split from
    `_check_envelope` for #137."""
    if not isinstance(manifest.get("org"), str) or not manifest.get("org"):
        report.finding("family-org", f"org is {manifest.get('org')!r}")
    if not isinstance(manifest.get("created_by"), str) or \
            not manifest["created_by"].strip():
        report.finding("family-created-by",
                       "created_by is empty. Creating a family is a human's "
                       "act and the manifest records whose.")
    created_on = manifest.get("created_on")
    if not isinstance(created_on, str) or not DATE_RE.match(created_on):
        report.finding("family-created-on",
                       f"created_on is {created_on!r}, expected an ISO date "
                       "YYYY-MM-DD")
    visibility = manifest.get("visibility")
    if visibility is not None and visibility not in VISIBILITY_CHOICES:
        report.finding("family-visibility",
                       f"visibility is {visibility!r}, expected one of "
                       f"{sorted(VISIBILITY_CHOICES)} or no field at all")
    members_dir = manifest.get("members_dir", DEFAULT_MEMBERS_DIR)
    if members_dir != DEFAULT_MEMBERS_DIR:
        report.finding("family-members-dir",
                       f"members_dir is {members_dir!r}; this shape mounts "
                       f"members under {DEFAULT_MEMBERS_DIR!r}, and one name "
                       "is what keeps a reader and a validator looking in the "
                       "same place")


def _check_shape_block(manifest: dict, report: Report) -> None:
    """`shape:` — the commit-and-digest pin of the openRepoShape revision
    this root was cut from. Split from `_check_envelope` for #137: an absent
    block ends the check early exactly as it always did, since nothing below
    it can be asked about a `shape` that is not there."""
    shape = manifest.get("shape")
    if not isinstance(shape, dict):
        report.finding("family-shape",
                       "shape is missing; a family root records the "
                       "openRepoShape revision it was cut from")
        return
    if shape.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"shape.revision_kind is {shape.get('revision_kind')!r}. "
                       "A tag can be moved and a commit cannot.")
    if not COMMIT_RE.match(str(shape.get("commit") or "")):
        report.finding("family-shape-commit",
                       f"shape.commit is {shape.get('commit')!r}, not 40 hex")
    digests = shape.get("digests")
    if not isinstance(digests, dict) or \
            not SHA256_RE.match(str(digests.get("tree_sha256") or "")):
        report.finding("family-shape-digest",
                       f"shape.digests.tree_sha256 is not 64 hex: {digests!r}")
    if shape.get("digest_definition") != TREE_DIGEST_DEFINITION:
        report.finding("family-shape-digest-definition",
                       f"shape.digest_definition is "
                       f"{shape.get('digest_definition')!r}, expected "
                       f"{TREE_DIGEST_DEFINITION!r}")


def _check_envelope(manifest: dict, policy: NamingPolicy,
                    report: Report) -> None:
    """`schema_version`, `kind: family-manifest`, `id`, `name`, `org`,
    `created_by` / `created_on`, `visibility`, `members_dir` and `shape` — in
    that order, unchanged; each is now its own decision (#137)."""
    _check_schema_kind_and_id(manifest, report)
    _check_family_name(manifest, policy, report)
    _check_org_visibility_and_dates(manifest, report)
    _check_shape_block(manifest, report)


def _member_project_name(row: dict, seen: dict, report: Report) -> str | None:
    """The row's own `project:`, or None when nothing else about this member
    should run — it has none, or its name was already seen once in
    `members:`. Split from `_check_member` for #137: the two ways this
    member's checks stop before they start, in one place.

    A name seen once already stops this row's checks and says nothing: the
    finding for it is `_check_member_names_unique`'s (#331), made before any
    row is checked so `--no-members` makes it too, and made once, not here as
    well."""
    project = row.get("project")
    if not isinstance(project, str) or not project:
        report.finding("member-project", f"a member row has no `project:`: "
                                         f"{row!r}")
        return None
    if project in seen:
        return None
    seen[project] = True
    return project


def _check_member_repository_and_path(row: dict, project: str,
                                      report: Report) -> str | None:
    """`repository:` and `path:` against what they must equal for `project`.

    Split from `_check_member` for #137. Returns `path`, defaulted the same
    way the row itself defaults it, since the gitlink and digest checks that
    follow need the same value. Returns None where that is not the one path
    the row may have, the `member-path` finding: nothing may be read through
    it (#367).
    """
    repository = row.get("repository")
    if not isinstance(repository, str) or not QUALIFIED_RE.match(repository):
        report.finding("member-repository",
                       f"{project}: repository is {repository!r}, expected "
                       "`<org>/<Name>`")
    elif repo_basename(repository) != project:
        report.finding("member-repository-name",
                       f"{project}: repository is {repository!r}, whose name "
                       f"is {repo_basename(repository)!r}. A member's row and "
                       "the repository it pins are the same project or the "
                       "row is describing something else.")

    path = str(row.get("path") or f"{DEFAULT_MEMBERS_DIR}/{project}")
    expected = f"{DEFAULT_MEMBERS_DIR}/{project}"
    if path != expected:
        report.finding("member-path",
                       f"{project}: path is {path!r}, expected {expected!r}, "
                       f"the one path a row for {project} may have. Its "
                       "gitlink, digest and project id are not checked "
                       "through any other.")
        return None
    return path


def _pin_commit(pin: dict, project: str, report: Report) -> str:
    """The pin's `revision_kind` and `commit`, checked; returns the LOWERED
    commit. Split from `_check_member` for #137. Raises `Refusal` for a
    commit nothing after this point can be checked against — an abbreviated
    oid, a branch or a tag is a moving reference."""
    if pin.get("revision_kind") != "commit":
        report.finding("pin-tag-only",
                       f"{project}: pin.revision_kind is "
                       f"{pin.get('revision_kind')!r}. A tag can be moved and "
                       "a commit cannot; a pin is a commit or it is nothing.")
    commit = str(pin.get("commit") or "")
    if not COMMIT_RE.match(commit):
        raise Refusal(
            "member-pin-commit",
            f"{project}: pin.commit is {commit!r}, which is not 40 hex. An "
            "abbreviated oid, a branch or a tag is a moving reference.")
    return commit.lower()


def _check_member_gitlink(root: Path, path: str, commit: str, project: str,
                          repository, gitlinks: dict[str, str],
                          report: Report, rule: str,
                          removed: frozenset[str] = frozenset()) -> None:
    """The submodule gitlink this repository records at `path`, against the
    pin — THE LOCKSTEP RULE. Split from `_check_member` for #137. Raises
    `Refusal` when there is no gitlink at all: a row naming a member this
    repository does not record as a submodule (`_gitlink_put_back` says
    what to do). Where `gitlinks` (`_member_gitlinks`) holds one at a case
    variant of `path`, the refusal names that instead (#611). A gitlink
    whose removal is staged (`removed`) is HEAD's, which the next commit
    drops: `member-gitlink-removal-staged` names it, and nothing is said of
    it here (#762)."""
    gitlink = recorded_gitlink(root, path)
    if gitlink is None:
        variants = sorted(other for other in gitlinks if other != path
                          and other.casefold() == path.casefold())
        if variants:
            raise _gitlink_in_another_case(root, path, commit, project,
                                           variants, gitlinks, repository)
        raise Refusal(
            "member-gitlink-absent",
            f"no gitlink (mode 160000) recorded at {path!r}. {project} is "
            f"named in {MANIFEST} but this repository does not record it as a "
            "submodule.",
            _gitlink_put_back(root, path, commit, repository))
    if path in removed:
        return
    if gitlink != commit:
        report.finding(
            "member-gitlink-mismatch",
            f"{path}: gitlink {gitlink} != {MANIFEST} pin {commit}\n  "
            + rule)
    else:
        report.note(f"{path}: gitlink == pin {commit[:12]}")


def _gitlink_put_back(root: Path, path: str, commit: str,
                      repository) -> str:
    """What `member-gitlink-absent` says where no case variant of `path`
    holds the gitlink either: a row whose gitlink was taken out by hand, as
    `git rm` takes it out, with its `.gitmodules` section (#681).

    IN WORDS, AS NO TOOL TAKES THIS STATE. It named `family.py add`, which
    refuses the row that is there (`member-already-present`), and `family.py
    remove` dies at its `git submodule deinit` (`pathspec ... did not
    match`), which finds no gitlink, having removed nothing. So a member
    that is to stay has its gitlink put back in the index alone, at the
    commit the row pins, as `_wrong_case_move` records one, and, where no
    section of HEAD's `.gitmodules` gives its path, its section written back
    as `member-gitmodules-absent` writes one (`_section_lines`); and a
    member that is to go has its row taken out by hand. Either is
    committed, and a member put back is checked out as
    `member-uninitialized` says. Where the work tree's `.gitmodules` is
    gone from disk, the section's lines come after the one that puts the
    file back from where git reads it (`_file_put_back`): `git config -f`
    made a file of that one section, which staged and committed dropped
    every other (#879).
    """
    head = _head_gitmodules(root)
    sections = head[1] if head is not None else {}
    given = {keys["path"] for keys in sections.values() if "path" in keys}
    lines = ("" if path in given
             else _section_lines(path, repository, sections))
    put_back, whose = _file_put_back(root, None) if lines else ("", "")
    written = (", and its .gitmodules section back by hand, in a POSIX "
               "shell, as family.py add writes one, with the lines after it"
               + (f", the first of which puts {GITMODULES}, gone from the "
                  f"work tree, back from {whose}, so that every other "
                  "section stays" if put_back else "")
               + ", then stage .gitmodules" if lines else "")
    if put_back:
        lines = f"\n    {put_back}{lines}"
    return (
        "Remediation: family.py add refuses the row, which is there "
        "(member-already-present), and family.py remove cannot take the "
        "member out, since its git submodule deinit finds no gitlink. If "
        "the member is to stay, put its gitlink back at the commit the row "
        "pins, in the index alone, which touches no file, with the first "
        f"line below{written}. Commit that, and `git submodule update "
        "--init --recursive`, or `make bootstrap`, then checks the member "
        f"out at {path}. If it is to go, take its row out of {MANIFEST} by "
        "hand and commit that.\n"
        "    git update-index --add --cacheinfo "
        f"{shlex.quote(f'160000,{commit},{path}')}{lines}")


def _gitlink_in_another_case(root: Path, path: str, commit: str,
                             project: str, variants: list[str],
                             gitlinks: dict[str, str],
                             repository) -> Refusal:
    """`member-gitlink-absent` for a row whose gitlink this repository
    records only at a case variant of its path (#611, #363's item 3), as a
    holder committed in #363's state does: `Members/<P>`, under a row and a
    `.gitmodules` section that say `members/<P>`. A fresh clone checks out
    nothing at the row's path, and the plain refusal's `family.py add`
    cannot help: the row is there already.

    EACH VARIANT IS NAMED, AND THE GITLINK IS MOVED IN THE INDEX ALONE, as
    #574's remedies act on an index entry under another spelling of
    `members/` (Brett Heap, 2026-10-14, "Refuse on every disk"): `git rm -r
    --cached` takes each variant out and touches no file, and `git
    update-index --cacheinfo` records the gitlink at the row's path, at the
    commit the row pins, reading no disk either. So the two lines work on
    every disk, wherever the checkout stands, and the commit after them
    records the member once, at its own path. `member-gitlink-unnamed`
    prints the same move for the same gitlink under `--no-members` (#648),
    and no command that takes it out ALONE, which would un-register the
    member; these take it out and record it together. `--ignore-unmatch`,
    since a variant whose removal is staged and not yet committed is still
    named here, from HEAD, and the plain `git rm` of it failed (`pathspec
    ... did not match`). What else the move meets, `_move_context` reads
    (#762): a variant a sparse checkout keeps off disk, an entry the index
    holds at or under the row's path, and a `.gitmodules` that does not
    give the row's path.

    WHAT IS LEFT ON DISK. Where the disk holds a variant apart from the
    row's path, a directory there (the empty one a fresh clone leaves, a
    plain one, or a checkout) stays behind, untracked, and `family.py add`
    refuses it as `family-members-dir-variant` (#574), so the text says to
    move it out of the holder, by an `mv` with nothing to fill in, which a
    shell test skips where the disk folds the two names into one
    directory, the row's own, and where the directory is a checkout
    (#681), and where nothing is there, and never skips for a symbolic
    link (#839). A checkout is deleted by hand once nothing only it holds is
    needed. Where nothing is checked out at the row's path, as in a fresh
    clone, `git submodule update --init --recursive` then checks the member
    out there, LAST (#762): a checkout `git mv` moved to the variant names
    the member's own store, and that update points the store at the row's
    path, after which `git -C <variant> status`, which the text gives for
    what only the checkout holds, reads the row's path instead.
    """
    found = ", ".join(f"{variant} (at {gitlinks[variant]})"
                      for variant in variants)
    return Refusal(
        "member-gitlink-absent",
        f"no gitlink (mode 160000) recorded at {path!r}. {project} is named "
        f"in {MANIFEST}, and this repository records its gitlink only at a "
        "case variant of that path, which macOS and Windows hold as one "
        f"directory with it: {found}. A recursive clone checks out nothing "
        f"at {path}.",
        "Remediation: the member is recorded in the wrong case. "
        + _wrong_case_move(path, commit, variants,
                           _move_context(root, path, variants, repository,
                                         gitlinks, None)))


#: What the `-f` sentence says is on disk at a gitlink's path (`_held_as`):
#: a checkout, as #839 said, or what is there, which is none (rv882's NIT 2
#: on #882).
CHECKOUT = "a checkout"
NO_CHECKOUT = "what is on disk there, which is no checkout"


class MoveContext(NamedTuple):
    """What the wrong-case move meets beside the variants it takes out
    (#762), as `_move_context` reads it: `sparse`, the variants a sparse
    checkout keeps off disk; `in_the_way`, every entry the index holds at
    or under the row's path; and `section`, the lines that make
    `.gitmodules` give the row's path, with what they do, or empty where a
    section of HEAD's already gives it. `forced`, the variants whose `git
    rm --cached` takes `-f` (`_forced`, #839), and `forced_over`, what is
    on disk at them, as the `-f` sentence says it (`_forced_over`, rv882's
    NIT 2 on #882, and lane 1's NIT 3 on #889). `stage`, whether `git add
    -- .gitmodules` comes first (`_stage_first`, #879)."""

    sparse: tuple[str, ...] = ()
    in_the_way: tuple[str, ...] = ()
    section: str = ""
    section_said: str = ""
    forced: tuple[str, ...] = ()
    stage: bool = False
    forced_over: str = CHECKOUT


def _move_context(root: Path, path: str, variants: list[str],
                  repository, gitlinks: dict[str, str],
                  report: Report | None) -> MoveContext:
    """What the index and HEAD's `.gitmodules` hold around the move of a
    member recorded only at `variants` to its row's `path` (#762), and
    which variants the move's `git rm --cached` takes out only with `-f`
    (`_forced`, by `gitlinks`, `_member_gitlinks`, #839). `report` holds
    the findings printed before the move, or is None for members mode's
    refusal, which is printed alone (#879).

    `--sparse` (the issue's (f)): a variant a sparse checkout keeps off
    disk (`git ls-files -t`'s `S`, as `family.py`'s `_skip_worktree` reads
    it) is passed over by `git rm -r --cached --ignore-unmatch`, which
    exits 0 and removes nothing, so `git update-index --add` then left two
    gitlinks in the index. Measured on git 2.43, in a cone and a non-cone
    checkout alike; `git rm --sparse` came with git 2.34 (`family.py`'s
    `SPARSE_RM_GIT`).

    AN ENTRY IN THE WAY ((g)): `git update-index --add --cacheinfo`
    replaced a file at the row's path without a word, and failed on a file
    under it (`'members/<P>' appears as both a file and as a directory`,
    exit 128) after the line before it had taken the variant out, which
    left the member un-registered. Every entry at or under the path, as
    git compares paths, but those a merge left unmerged: at the path the
    move's second line replaces them, stages 1 to 3, as it replaces one at
    stage 0; under it, it leaves them beside the gitlink, and the commit
    after it refuses them (`Committing is not possible because you have
    unmerged files`, exit 128), so neither is lost without a word (git 2.43
    and 2.47.1, rv820's NIT 5). The whole index, with no pathspec, as
    `_member_gitlinks` lists it.

    THE SECTION ((e)): `git mv members/<P> Members/<P>` rewrites its
    section's `path` to the variant, under the name it had, so the move
    put the gitlink back and `member-gitmodules-absent` followed. Where no
    section of HEAD's `.gitmodules`, which a clone reads, gives the row's
    path, the section that gives a variant's is given the row's path, the
    first variant's where two have one; and where none gives a variant's
    either, the section is written as `family.py add` writes one
    (`_section_lines`). Then `git add` stages the file.

    WHERE THE WORK TREE'S `.gitmodules` IS GONE FROM DISK, the section's
    lines come after the one that puts it back from where git reads it,
    unless a finding printed before the move did (`_file_put_back`): `git
    config -f` made a file of that one key, which the move's `git add`
    staged, so the commit dropped every other section, and the put-back of
    a `member-gitmodules-url-absent` after it restored that staged file
    (#879's C1, rv876's P5b and P5e).

    `git add -- .gitmodules` COMES FIRST where a value finding's lines,
    printed before it, may leave that file with changes not staged, or it
    holds some as it stands (`_stage_first`): git takes no gitlink out of
    the index then, and the move's `git rm` exited 128 (#879's C3).
    """
    sparse, in_the_way = _index_around(root, path, variants)
    section, said = _move_section(root, path, variants, repository, report)
    edited = report is not None and "gitmodules-value-refused" in report.codes
    forced = _forced_variants(root, variants, gitlinks)
    return MoveContext(sparse, in_the_way, section, said, forced,
                       _stage_first(root, edited), _forced_over(root, forced))


def _forced_over(root: Path, forced: tuple[str, ...]) -> str:
    """What the `-f` sentence says is on disk at the variants `forced`
    (`_held_as`): `CHECKOUT` or `NO_CHECKOUT` where every one holds the
    same, and each by its path where they differ, since one said for all
    called a checkout no checkout (lane 1's NIT 3 on #889)."""
    held = {variant: _held_as(root, variant) for variant in forced}
    if len(set(held.values())) < 2:
        return next(iter(held.values()), CHECKOUT)
    return ", and over ".join(
        f"a checkout at {variant}" if what == CHECKOUT
        else f"what is on disk at {variant}, which is no checkout"
        for variant, what in held.items())


def _index_around(root: Path, path: str, variants: list[str]
                  ) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`(the variants a sparse checkout keeps off disk, every entry the
    index holds at or under path but those a merge left unmerged)`, from
    `git ls-files -t`, for `_move_context` (#762's (f) and (g))."""
    with _git_runs(f"the index entries at and around {path} could not be "
                   "listed"):
        listed = git_out(["ls-files", "-t", "-z"], cwd=root, binary=True)
    sparse: set[str] = set()
    in_the_way: dict[str, None] = {}
    for record in listed.split(b"\0"):
        tag, name = record[:1], record[2:].decode("utf-8", "surrogateescape")
        if tag == b"S" and name in variants:
            sparse.add(name)
        if tag != b"M" and (name == path or name.startswith(path + "/")):
            in_the_way[name] = None
    return tuple(sorted(sparse)), tuple(in_the_way)


def _move_section(root: Path, path: str, variants: list[str], repository,
                  report: Report | None) -> tuple[str, str]:
    """`(the lines that make .gitmodules give path, what they do)` for the
    wrong-case move (`_move_context`, #762's (e)), or two empty strings
    where a section of HEAD's gives it already: the section of a variant's
    path given the row's, or one written as `family.py add` writes it,
    after the line that puts the file back where it is gone from the work
    tree and no finding before put it back (`_file_put_back`, #879's C1),
    then `git add`. Where `report` holds the findings printed before it,
    the write is recorded there (`Report.wrote`), so no finding after it
    puts HEAD's file back over it (lane 1's MUST 1 on #889, its P5)."""
    head = _head_gitmodules(root)
    sections = head[1] if head is not None else {}
    given = {keys["path"]: name for name, keys in sections.items()
             if "path" in keys}
    if path in given:
        return "", ""
    named = next((given[variant] for variant in variants
                  if variant in given), None)
    if named is not None:
        section = (f"\n    git config -f {GITMODULES} "
                   f"{shlex.quote(f'submodule.{named}.path')} "
                   f"{shlex.quote(path)}")
        said = (f"give {path} back to the section of HEAD's {GITMODULES} "
                "that gives the variant's path, as git mv leaves it")
    else:
        section = _section_lines(path, repository, sections)
        said = (f"write its section as family.py add writes one, since no "
                f"section of HEAD's {GITMODULES} gives {path} or the "
                "variant's path")
    put_back, whose = _file_put_back(root, report)
    if put_back:
        section = f"\n    {put_back}{section}"
        said = (f"put {GITMODULES}, gone from the work tree, back from "
                f"{whose}, so that every other section stays, then {said}")
    if report is not None:
        report.wrote = True
    return f"{section}\n    git add -- {GITMODULES}", said


def _forced_variants(root: Path, variants: list[str],
                     gitlinks: dict[str, str]) -> tuple[str, ...]:
    """Each of `variants` whose `git rm --cached` takes `-f` (`_forced`),
    in their order (#839)."""
    return tuple(variant for variant in variants
                 if _forced(root, variant, gitlinks[variant]) is not None)


def _forced(root: Path, path: str, commit: str) -> str | None:
    """None where `git rm --cached` takes the gitlink at `path`, which
    `_member_gitlinks` reads at `commit`, out of the index as it is, else
    what HEAD records at `path`, its commit or `""` for nothing, where that
    takes `-f` (#839): the index stages the gitlink at a commit HEAD does
    not record there, and something is on disk at it (`_on_disk`). Git
    refuses it then wherever a checkout there has moved on or holds a file
    it does not track (`the following file has staged content different
    from both the file and the HEAD`, exit 1), measured on git 2.43 after
    `git mv members/<P> Members/<P>`, staged, and a commit or an untracked
    file in the checkout it moved (w761's candidate 2 on #828), and `-f`,
    with `--cached`, touches no file. It refuses it too over a directory
    that holds files and no `.git`, a file or a symbolic link, and takes it
    over an empty directory or nothing (git 2.43, rv882's NIT 2 on #882).
    A gitlink HEAD alone records, at a staged removal or a conflict, is
    read at HEAD's commit and takes none.

    GIT IS ASKED FIRST, AND THE DISK ONLY WHERE THE ANSWER TURNS ON IT
    (#430, r956's SHOULD 1 on #956): where HEAD records the gitlink at the
    index's own commit, no `-f` is printed whatever is on disk, so a path
    in a folder this user cannot search is not asked there, and the
    finding is said as it always was, not refused `member-unreadable`."""
    head = _head_records(root, path)
    if head == commit or not _on_disk(root, path):
        return None
    return head


def _head_records(root: Path, path: str) -> str:
    """The commit HEAD records at `path`, lower case, or `""` for nothing
    (`_forced`, `_staged_over`)."""
    with _git_runs(f"the gitlink HEAD records at {path} could not be read"):
        try:
            return git_out(["rev-parse", "--verify", "--quiet",
                            f"HEAD:{path}"], cwd=root).lower()
        except Refusal:
            return ""


def _staged_over(root: Path, path: str, commit: str) -> bool:
    """Whether a plain `git rm -- <path>` refuses the gitlink at `path`,
    which `_member_gitlinks` reads at `commit`, as staged (`STAGED_AT`):
    the index stages it at a commit HEAD does not record there, and
    anything is on disk at it, an empty directory too, which `git rm
    --cached` takes with no `-f` (`_forced`). Measured on git 2.43: with
    nothing on disk it took one staged and not committed; it refused one,
    exit 1, saying `the following file has changes staged in the index`
    where what is on disk matches what is staged, an empty directory, the
    clean checkout `git mv members/<P> members/<P>2` moved, or a checkout
    moved to `HEAD~1` and `git add`-ed, where HEAD records another commit,
    and `... has staged content different from both the file and the HEAD`
    where it differs too, a commit or an untracked file in the checkout
    `git mv` moved, a directory holding a file, or a file (lane 1's SHOULD
    on #889, round 2, and its NITs 1 and 2, round 3)."""
    # Git first (r956's SHOULD 1 on #956): where HEAD records the gitlink
    # at the index's own commit, nothing is said of the disk, so it is not
    # asked. Where the answer turns on it, a path whose `stat` is refused,
    # in a folder this user cannot search, is `member-unreadable`
    # (`_anything_at`, #430): `os.path.lexists` read it as nothing there,
    # and the refusal went unsaid.
    return (_head_records(root, path) != commit
            and _anything_at(root / path, path))


def _on_disk(root: Path, path: str) -> bool:
    """Whether anything but an empty directory is on disk at `path`, where
    a staged gitlink's `git rm --cached` takes `-f` (`_forced`): git 2.43
    refused it, with no `-f`, over a checkout, a directory holding a file
    and no `.git` (rv882's NIT 2 on #882), a file and a symbolic link, and
    took it over an empty directory and over nothing. A directory this user
    cannot list is taken to hold something: `-f`, with `--cached`, touches
    no file. A path whose `stat` is refused, in a folder this user cannot
    search, is `member-unreadable` (`_anything_at`, #430): asked with
    `os.path.lexists`, it was nothing on disk, and the `-f` git needs there
    was not printed."""
    where = root / path
    if not _anything_at(where, path):
        return False
    # After that `stat`, `lstat` needs no more access: a link is on disk.
    if os.path.islink(where) or not _asked(where, stat.S_ISDIR,
                                            MEMBER_UNREADABLE, path):
        return True
    try:
        with os.scandir(where) as entries:
            return any(True for _ in entries)
    except OSError:
        return True


def _held_as(root: Path, path: str) -> str:
    """What the `-f` sentence says is on disk at `path` (`_forced_said`):
    `CHECKOUT` where a `.git` entry is there, else `NO_CHECKOUT`, and
    `member-unreadable` where its `stat` was refused (`_anything_at`,
    #430): a checkout this user cannot search was said to be no checkout.
    Asked only where the `-f` is printed."""
    return (CHECKOUT if _anything_at(root / path / ".git", f"{path}/.git")
            else NO_CHECKOUT)


def _held_if_forced(root: Path, path: str, head: str | None) -> str:
    """`_held_as` where `_forced` answered `head` for the gitlink at `path`
    and the `-f` sentence says it, else `CHECKOUT`, which `_forced_said`
    does not read: a `.git` this user cannot search is refused only where
    what is said of it is printed (#430)."""
    return CHECKOUT if head is None else _held_as(root, path)


def _wrong_case_move(path: str, commit: str, variants: list[str],
                     context: MoveContext = MoveContext()) -> str:
    """The index move for a member recorded only at `variants`, case
    variants of its row's `path`, to `path` at the pinned `commit`, with
    what it leaves on disk: what `_gitlink_in_another_case` says, and
    `member-gitlink-unnamed` under `--no-members` (#648), in one text.
    What else it meets is `context` (`_move_context`, #762).

    EACH `mv` IS GUARDED BY TESTS A POSIX SHELL RUNS (#681, rv611c's N-1
    and N-2; `_guarded_move`), not by a system's name: this text is read in
    CI too, on another disk than the one it is typed on. `[ <variant> -ef
    <path> ]` is true where the disk takes the two names for one directory,
    the row's own, as a Linux mount that folds case does too (WSL's
    `/mnt/c`), where the `mv` moved the member's own checkout out. `[ -e
    <variant>/.git ]` is true for a checkout, and a submodule's `.git` is a
    file naming this holder's `.git/modules/` by a relative path, which a
    move leaves pointing nowhere (`fatal: not a git repository`). `[ ! -e
    <variant> ]` is true where nothing is there, where the bare `mv` failed
    (#839). A symbolic link there is asked first, `[ ! -L <variant> ]`, and
    always moved, since the other tests read through it (#839). So the
    `mv` runs only for a link, or a directory apart from the row's with no
    `.git` entry, the empty one a fresh clone leaves or a plain one, and
    the text says where a submodule checkout's commits are kept, in the
    store its `.git` file names (not always `.git/modules/<variant>`: a
    checkout a plain `mv` brought there names the old one, and git cannot
    open it), what deleting it would lose, and to delete it by hand once
    nothing only it holds is needed. A clone's own `.git` DIRECTORY holds
    its commits and nothing else does, so the text names the `git log` that
    lists the ones not pushed and says to move it out whole, not delete it
    (rv681's S2 and N1, Direction B: the `-e` guard Brett Heap's word took
    is kept).

    THE `git rm` TAKES `-f` where the index stages a variant at a commit
    HEAD does not record there and anything but an empty directory is on
    disk at it (`MoveContext.forced`, `_forced`, `_on_disk`, #839, rv882's
    NIT 2 on #882): git refuses it there wherever a checkout there has
    moved on or holds a file it does not track, and over a directory that
    holds files and no `.git`, a file or a symbolic link. The text says
    what `-f` does (`FORCED_SAID`) and what is on disk there, each
    variant's where they differ (`MoveContext.forced_over`, lane 1's NIT 3
    on #889). It comes after `git add -- .gitmodules` where
    `MoveContext.stage` (`_stage_first`, #879's C3).
    """
    taken_out = " ".join(shlex.quote(variant) for variant in variants)
    moved = " and ".join(_guarded_move(variant, path) for variant in variants)
    status = _statuses(variants)
    unpushed = _unpushed(variants)
    flag = (" --sparse" if context.sparse else "") + (
        " -f" if context.forced else "")
    lead = (STAGE_SAID if context.stage else "") + "move"
    lead = (f"Then {lead}" if context.in_the_way
            else f"{lead[0].upper()}{lead[1:]}")
    return (
        _entries_aside(path, context.in_the_way)
        + f"{lead} its gitlink to the row's path, at the commit the row "
        "pins, in the index alone, which touches no file, with the "
        + ("next two lines" if context.stage
           else "first two lines below" if context.section
           else "two lines below")
        + _first_line_flags(context)
        + (f"; the lines after them {context.section_said}, and stage "
           f"{GITMODULES}. Commit that." if context.section
           else ", and commit that.")
        + " A directory left at "
        f"{' or '.join(variants)} is the row's own where the disk folds "
        "case, as macOS's and Windows' usually do and a Linux mount can "
        "(WSL's /mnt/c). Where the disk holds the two apart it stays there, "
        "untracked, and family.py add refuses it as "
        "family-members-dir-variant: move each one that is there out of the "
        f"holder, in a POSIX shell (Git Bash on Windows), {moved}, which "
        "moves nothing where nothing is there, where the two names are one "
        "directory or where it holds a .git entry, a checkout, and moves a "
        "symbolic link there wherever it points, the link and never what it "
        "points at. A checkout git submodule add made holds a .git file "
        "naming its store by a path relative to it, which a move would "
        "leave pointing nowhere. Its commits are kept under this holder's "
        ".git/modules/, in the directory its .git file names, whatever "
        "becomes of the checkout, and only what is not committed is in the "
        f"checkout alone ({status} shows it, except where a plain mv brought "
        "the checkout to that path: git cannot open it there, so check its "
        "files by hand). Delete such a checkout by hand once nothing only it "
        "holds is needed. A checkout whose .git is a directory, a clone of "
        "its own, holds its commits there and nowhere else, and "
        f"{unpushed} lists the ones not pushed: move it out of the holder "
        "whole, by hand, rather than delete it. Then, where nothing is "
        f"checked out at {path}, as in a fresh clone, `git submodule update "
        "--init --recursive` checks the member out there. Run it last: a "
        "checkout git mv moved to a variant names the member's own store, "
        f"which that update points at {path}, so {status} reads {path} "
        "after it. The "
        + ("lines" if context.section or context.stage else "two lines")
        + ":\n" + (f"    {STAGE_LINE}\n" if context.stage else "")
        + f"    git rm -r --cached{flag} --ignore-unmatch -- {taken_out}\n"
        "    git update-index --add --cacheinfo "
        f"{shlex.quote(f'160000,{commit},{path}')}{context.section}")


#: What `-f` on a `git rm --cached` of a gitlink does, said where one is
#: printed with it (`_forced`, #839), as `family.py`'s move back says it
#: (#761).
FORCED_SAID = ("-f takes out a staged gitlink whose checkout has moved on or "
               "holds a file git does not track, which git rm otherwise "
               "refuses, and with --cached touches no file")


def _guarded_move(variant: str, path: str) -> str:
    """The backticked `mv` that moves a directory left at `variant`, a case
    variant of the row's `path`, out of the holder, each test a POSIX shell
    runs, dash and bash alike (#681, #839).

    `[ ! -L <variant> ]` FIRST, so a symbolic link there is always moved,
    the link and never what it points at: `-ef` and `-e` read through a
    link, so the guard kept one that points at the row's own directory, or
    at a clone elsewhere, and `family.py add` then refused it as
    `family-members-dir-variant`, a link on disk and untracked (w840's
    candidate 1). Then `[ ! -e <variant> ]`, true where nothing is there,
    a fresh clone's, where the bare `mv` failed `cannot stat`, exit 1, and
    stopped what was typed after it (Codex's P2 2 on #828, met again here);
    a link pointing nowhere, which `-e` takes for nothing, is a link, and
    moved. `[ <variant> -ef <path> ]`, true where the disk takes the two
    names for one directory, the row's own; `-L` asks the last component
    alone, so a `Members` that is itself a link to `members`, which
    `tests/test_validate_family_remedies_typed.py` emulates a folding disk
    with, still moves nothing. `[ -e <variant>/.git ]`, true for a
    checkout."""
    quoted = shlex.quote(variant)
    return (f"`[ ! -L {quoted} ] && {{ [ ! -e {quoted} ] || "
            f"[ {quoted} -ef {shlex.quote(path)} ] || "
            f"[ -e {shlex.quote(variant + '/.git')} ]; }} || "
            f"mv -- {quoted} "
            f"{shlex.quote('../' + variant.replace('/', '-'))}`")


def _first_line_flags(context: MoveContext) -> str:
    """What the wrong-case move says of the flags its first line, the `git
    rm`, carries, or nothing: `--sparse` (#762) and `-f` (#839)."""
    said = []
    if context.sparse:
        said.append("--sparse, which needs git 2.34 or later: a sparse "
                    f"checkout keeps {' and '.join(context.sparse)} off "
                    "disk, and without it git rm passes over what that keeps "
                    "off disk, exit 0, and removes nothing")
    if context.forced:
        said.append(f"-f, since the index stages "
                    f"{' and '.join(context.forced)} at a commit HEAD does "
                    f"not record there, over {context.forced_over}: "
                    f"{FORCED_SAID}")
    return f" (the first with {', and with '.join(said)})" if said else ""


def _entries_aside(path: str, entries: tuple[str, ...]) -> str:
    """What the wrong-case move says first where the index holds `entries`
    at or under the row's `path` (#762's (g)), or nothing: they go aside
    with a committed `git mv`, as `family.py`'s `_members_is_a_file` moves
    a file at `members`, since the move's second line replaced one at the
    path without a word and failed on one under it. `<new name>` is the
    person's to choose, as there."""
    if not entries:
        return ""
    if entries == (path,):
        held = (f"The index holds an entry at {path} that is no gitlink, "
                "which the move's second line replaces without a word")
    else:
        held = ("The index holds "
                + ", ".join(entries[:5])
                + (f" and {len(entries) - 5} more" if len(entries) > 5
                   else "")
                + f" under {path}, at which the move's second line stops "
                "(appears as both a file and as a directory) after the first "
                "has taken the variant out")
    return (
        f"{held}. Move it aside first, `git mv -- {shlex.quote(path)} <new "
        f"name>`, a new name outside {DEFAULT_MEMBERS_DIR}/, and commit that "
        "move on its own. ")


def _check_member_tree(member: Path, pin: dict, path: str, commit: str,
                       project: str, report: Report, rule: str,
                       stop: str = "") -> None:
    """Is `member`'s own object store readable at `commit`, and does its
    digest match the pin? Split from `_check_member` for #137 — the two
    questions were already one comment block ("the digest and the identity")
    in the source. Raises `Refusal` when the tree cannot even be read: an
    uninitialized submodule, or a commit its checkout does not have. Presence
    is not identity and an unreadable surface must fail rather than degrade.

    `member-uninitialized` names `git submodule update --init --recursive`,
    which dies where git's init stops at a gitlink it has no url for, before
    it checks out any member (rv648's S1, H1 and U1): `stop` is then what
    says so and cures it (`_init_stop_said`, #762).

    `member-commit-unresolvable` names the fetch of the pinned commit, which
    a remote that holds it serves and one that does not answers `not our
    ref`, and THE LOCKSTEP RULE's `bump` for a pin no remote holds (#762,
    rv681's P2: on the remote, the fetch put it in the store and the gate
    passed; on none, the fetch and `git submodule update` both exit 128).

    A CHECKOUT THIS USER CANNOT SEARCH is `member-unreadable`, naming its
    `.git` (`_checked_out`, #430): it ended the run in a traceback up to
    Python 3.13, and on 3.14 was `member-uninitialized`, whose update then
    failed (`could not open '<path>/.git' for writing`) on the checkout
    that is there.
    """
    if not _checked_out(member, path):
        raise Refusal(
            "member-uninitialized",
            f"{path} is not an initialized submodule checkout, so neither the "
            "pinned digest nor the project it claims can be read. Presence is "
            "not identity and an unreadable surface must fail rather than "
            "degrade.",
            f"Remediation: {stop}`git submodule update --init --recursive`, "
            "or `make bootstrap`, which resolves a credential for private "
            "members first.")
    try:
        git_out(["rev-parse", "--verify", "--quiet", f"{commit}^{{commit}}"],
                cwd=member)
    except Refusal as exc:
        fetch = shlex.join(["git", "-C", path, "fetch", "origin", commit])
        raise Refusal(
            "member-commit-unresolvable",
            f"{path}: the pinned commit {commit} is not in that member's "
            f"object store ({exc.detail})",
            f"Remediation: where a remote of the member holds it, `{fetch}` "
            "fetches it into that store, and this then reads it. Where none "
            "does, that fetch fails `not our ref`, exit 128, as `git "
            "submodule update` does, and the pin names a commit no clone can "
            "fetch: move the gitlink and the pin to one a remote holds. "
            + rule) from exc

    recorded = pin.get("tree_sha256")
    if not isinstance(recorded, str) or not SHA256_RE.match(recorded):
        report.finding("member-digest-malformed",
                       f"{project}: pin.tree_sha256 is {recorded!r}, not 64 hex")
    elif pin.get("digest_definition", TREE_DIGEST_DEFINITION) != \
            TREE_DIGEST_DEFINITION:
        report.finding(
            "member-digest-definition",
            f"{project}: pin.digest_definition is "
            f"{pin.get('digest_definition')!r}, expected "
            f"{TREE_DIGEST_DEFINITION!r}. A digest whose definition is "
            "unstated is a number, not an identity.")
    else:
        actual = tree_digest(member, commit)
        if actual.lower() != recorded.lower():
            report.finding(
                "member-digest-mismatch",
                f"{project}: pin.tree_sha256 {recorded}\n"
                f"       recomputed at {commit[:12]} {actual}\n"
                "  The gitlink and the pin may agree on a commit whose bytes "
                f"are not the bytes the pin was written against.\n  {rule}")
        else:
            report.note(f"{path}: tree digest recomputes ({recorded[:12]}…)")


class Gitlinked(NamedTuple):
    """A member `_check_member` asked up to its gitlink, with what
    `_check_member_checkout` reads its checkout by, and THE LOCKSTEP RULE
    its digest finding ends at, which names this member (#610)."""

    row: dict
    project: str
    path: str
    pin: dict
    commit: str
    rule: str


def _check_member(root: Path, row: dict, seen: dict, report: Report,
                  gitlinks: dict[str, str],
                  removed: frozenset[str] = frozenset()) -> Gitlinked | None:
    """One member up to its checkout: the row itself and the gitlink. The
    member, for `_check_member_checkout` to ask its digest and identity of,
    or None where nothing more is asked of it.

    NOTHING IS READ THROUGH A PATH THE ROW MAY NOT HAVE (#367). A hand-edited
    `path:` is `member-path`, and this member's checks stop once its pin is
    read: the pin is a fact of the row, and everything after it is read at
    the path. They used to go on. At `members/*` the gitlink listing took the
    path for a glob and answered with a neighbour's commit, gathered as this
    member's `member-gitlink-mismatch`, and the tree check then refused
    `member-uninitialized`, whose remedy cannot help, and whose refusal
    dropped both findings unprinted.

    The git each check runs is run inside `_git_runs`, which names the check
    when there is no git to run (#368); the identity check reads a file and
    runs none.
    """
    project = _member_project_name(row, seen, report)
    if project is None:
        return None

    path = _check_member_repository_and_path(row, project, report)

    pin = row.get("pin")
    if not isinstance(pin, dict):
        report.finding("member-pin", f"{project}: `pin:` is {pin!r}, expected "
                                     "a mapping")
        return None
    commit = _pin_commit(pin, project, report)
    if path is None:
        return None

    # ---- the gitlink -------------------------------------------------------
    # THE LOCKSTEP RULE each finding below ends at names this member (#610).
    rule = _lockstep(root, project, str(row.get("id") or project))
    with _git_runs(f"the gitlink recorded at {path} could not be read"):
        _check_member_gitlink(root, path, commit, project,
                              row.get("repository"), gitlinks, report, rule,
                              removed)
    return Gitlinked(row, project, path, pin, commit, rule)


def _check_member_checkout(root: Path, asked: Gitlinked, report: Report,
                           unregistered: set[str], stop: str = "") -> None:
    """One member's digest and identity, read in its checkout, asked once
    every row's gitlink has been (`_check_members`, #648).

    A MEMBER NO SECTION OF HEAD'S `.gitmodules` GIVES (`unregistered`, the
    `member-gitmodules-absent` finding, #611) that is not checked out is
    asked nothing here. Refused `member-uninitialized`, it named `git
    submodule update --init`, which exits 0 there and checks nothing out,
    and the refusal dropped the finding that says why: the state a fresh
    clone of a holder whose HEAD lost `.gitmodules` is in, and CI's. The
    finding is made all the same, so the run still fails. So is one whose
    section gives no url, and one whose removal is staged (#762), each the
    finding of its own. `stop` is what `member-uninitialized` says first
    where git's init would stop at a gitlink it has no url for
    (`_init_stop_said`). A checkout this user cannot search is
    `member-unreadable` (`_checked_out`, #430): on Python 3.14 it was
    one not checked out, and its digest and identity were not asked.
    """
    member = root / asked.path
    if asked.path in unregistered and not _checked_out(member, asked.path):
        return
    with _git_runs(f"{asked.project}'s pinned commit and its tree digest "
                   f"could not be read in {asked.path}"):
        _check_member_tree(member, asked.pin, asked.path, asked.commit,
                           asked.project, report, asked.rule, stop)
    _check_member_identity(member, asked.row, asked.project, asked.path,
                           report)


def _check_member_identity(member: Path, row: dict, project: str, path: str,
                           report: Report) -> None:
    """The mounted tree is the PROJECT this row claims, not just a commit.

    A member is an assembly root, so it carries `project.yaml`, and that file
    is the SOURCE of what that project is. The row here is a pin of it. Where
    the two disagree the row is wrong, because a family cannot rename a
    project by describing it differently.

    A `project.yaml` WHOSE `stat` IS REFUSED is `member-manifest-unreadable`,
    the finding one that cannot be opened already is, naming it and the
    cure (#430): on Python 3.14 it was `member-not-a-project`, "a family
    pins assembly roots, never legs", of a project that is one. ONE CODE,
    ONE TEXT: one that cannot be OPENED says the same, `<path>: cannot be
    read (<reason>)` and the cure for that cause (r956's SHOULD 2 on #956),
    where it named the file twice, relative and then absolute
    (`load_yaml`'s `yaml-unreadable` line), and gave no cure. `path` is the
    row's path as `_check_member_repository_and_path` resolved it, so a
    row that gives none is named at `members/<P>`, not `None` (r956's NIT 1).
    """
    manifest_path = member / "project.yaml"
    named = f"{path}/project.yaml"
    try:
        is_file = _is_a(manifest_path, stat.S_ISREG)
    except OSError as exc:
        report.finding("member-manifest-unreadable",
                       f"{_cannot_read(named, exc)}. {_advice(exc)}"
                       + RUN_AGAIN)
        return
    if not is_file:
        report.finding(
            "member-not-a-project",
            f"{path}: no project.yaml in the mounted tree. A member "
            "is a project's ASSEMBLY ROOT — the repository an engineer clones "
            "— and a family pins assembly roots, never legs.")
        return
    try:
        manifest = load_yaml(manifest_path)
    except Refusal as exc:
        cause = exc.__cause__
        said = (f"{_cannot_read(named, cause)}. {_advice(cause)}{RUN_AGAIN}"
                if isinstance(cause, OSError) else f"{named}: {exc.detail}")
        report.finding("member-manifest-unreadable", said)
        return
    if not isinstance(manifest, dict):
        report.finding("member-manifest-unreadable",
                       f"{named}: not a mapping")
        return
    recorded_id = row.get("id")
    actual_id = manifest.get("id")
    if recorded_id is None:
        report.finding(
            "member-id-absent",
            f"{project}: the row records no `id:`, so nothing checks that the "
            "tree mounted here is the project this row claims")
    elif str(recorded_id) != str(actual_id):
        report.finding(
            "member-id-mismatch",
            f"{path}: project.yaml declares id {actual_id!r} but "
            f"{MANIFEST} records {recorded_id!r} for {project}. The project's "
            "own manifest is the source; this row is a pin of it.")
    else:
        report.note(f"{path}: project.yaml id {actual_id}")


def _load_shape_pin(root: Path) -> tuple[dict, str]:
    """`contracts/shape-pin.yaml`, read and validated as a mapping.

    Split from `_check_shape_pin` for #137. Raises `Refusal` for a pin this
    validator cannot read at all — absent, or not a mapping — the same two
    ways every other REFUSAL in this file is unreadable. A pin whose `stat`
    is refused, in a `contracts/` this user cannot search, is
    `shape-pin-unreadable` by name (`_asked`, #430): on Python 3.14 it was
    `shape-pin-missing`, a present file said not to exist.
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not _asked(pin_path, stat.S_ISREG, "shape-pin-unreadable",
                  "contracts/shape-pin.yaml"):
        raise Refusal("shape-pin-missing", f"{pin_path} does not exist")
    pin = load_yaml(pin_path)
    # POSIX, on every platform: a finding names a path in THIS repository,
    # and `str()` of a relative Path on Windows spells it with backslashes —
    # a path the reader cannot paste back into git.
    rel = pin_path.relative_to(root).as_posix()
    if not isinstance(pin, dict):
        raise Refusal("shape-pin-unreadable", f"{pin_path}: not a mapping")
    return pin, rel


def _check_shape_pin_envelope(pin: dict, rel: str, manifest: dict,
                              report: Report) -> str:
    """`revision_kind`, `commit` and its agreement with `family.yaml`.

    Split from `_check_shape_pin` for #137. Returns the (un-lowered) `commit`
    string exactly as the parent used to hold it in its own local variable —
    nothing downstream reads it, but the shape matches every other `_pin_*`
    helper in this file.
    """
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
                       f"{rel} commit {commit} != {MANIFEST} shape.commit "
                       f"{declared}")
    return commit


def _check_one_shape_file(root: Path, rel: str, row, report: Report) -> None:
    """One `files:` row: present, and its digest matches its `sha256`.

    Split from `_check_shape_pin` for #137 — the per-row body of its loop.
    A row that is no mapping, or whose `path:` is absent, empty or no
    string, is `shape-pin-row`, as `update-shape.py` refuses it
    `update-pin-row`: its `path:` was read as a path, so a row with none
    was `None is pinned but absent` (#681).

    A copy whose `stat` or read is refused is `shape-copy-unreadable`, a
    refusal naming it as the row does (#430), `validate-pins.py`'s code for
    the same copy (#712): `is_file()` raised a refused `stat` out of the
    run up to Python 3.13, and called the copy "pinned but absent" on 3.14;
    a copy at mode 000 ended in `file_sha256`'s `PermissionError` on every
    Python.
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
    if not _asked(target, stat.S_ISREG, "shape-copy-unreadable", path):
        report.finding("shape-copy-missing",
                       f"{rel}: {row.get('path')} is pinned but absent")
        return
    try:
        actual = file_sha256(target)
    except OSError as exc:
        raise _unreadable("shape-copy-unreadable", path, exc) from exc
    if actual != str(row.get("sha256", "")).lower():
        report.finding(
            "shape-copy-drift",
            f"{row.get('path')}: sha256 {actual}\n"
            f"       {rel} records {row.get('sha256')}\n"
            "  A shape file was edited in place. Either revert it, or "
            "carry the change upstream to openRepoShape and re-pin with "
            "`update-shape.py`.")


def _check_shape_pin_files(root: Path, pin: dict, rel: str,
                           report: Report) -> None:
    """Every `files:` row, and the summary note when none of them drifted.

    Split from `_check_shape_pin` for #137.
    """
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
        _check_one_shape_file(root, rel, row, report)
    if len(report.findings) == before:
        report.note(f"{rel}: {len(files)} copied shape file(s) match their "
                    "digests")


def _check_shape_pin(root: Path, manifest: dict, report: Report) -> None:
    """The COPIED shape files, each against its digest. Same rule everywhere.

    A family root holds copies of openRepoShape rather than mounting it, so
    there is no gitlink to compare and the identity of the copies is carried
    by the per-file `sha256` rows.
    """
    pin, rel = _load_shape_pin(root)
    _check_shape_pin_envelope(pin, rel, manifest, report)
    _check_shape_pin_files(root, pin, rel, report)


def _check_member_names_unique(members: list, report: Report) -> None:
    """No two rows of `members:` name ONE project, in any case — the
    `member-duplicate` finding (#331).

    It reads `members:` alone, so it runs under `--no-members` too, the run a
    private family's CI falls back to when its members cannot be checked out,
    and it runs before any row is checked, as `member-duplicate-id` does
    (#206). `_member_project_name` used to make this finding, and only the
    members-checked loop reaches that, so `--no-members` passed a
    `family.yaml` that named one row twice. It is made HERE and once, in
    every mode: `_member_project_name` still skips a row it has already seen,
    and says nothing.

    Two spellings that differ only in case are one row: `members/IRRS` and
    `members/irrs` are ONE directory on a case-insensitive disk (macOS,
    Windows), where a holder can mount only one of them, whatever `id:` each
    row records. The rows' ids are no help here and `member-duplicate-id`'s
    question is a different one: it asks whether one PROJECT is mounted
    twice, this asks whether one DIRECTORY is named twice.

    THE FOLD IS `str.casefold()`, as the standard's other same-path-in-any-case
    checks use it (`shape_materialize.py`, `adopt-project.py`). `family.py add`
    only writes ASCII names (`checked_value`: `[A-Za-z0-9._/@+~-]`), and a
    members-checked run refuses any other as `member-repository`
    (`QUALIFIED_RE`) or `member-repository-name`. Under `--no-members` neither
    runs, so a hand edit can put ANY string in `project:`, and a disk folds
    more than ASCII case: the long s (U+017F) folds to `s`, and a final sigma
    (U+03C2) to a small sigma (U+03C3), so `IRRS` and `irrs` spelt with the
    long s, or a name in capital sigmas and the same name in small ones, are
    one directory there, and `lower()` keeps each pair apart. On every name
    `family.py` can write the two folds agree, and `Family.member` in
    `family.py` compares with `lower()` (#206), so the tool that writes the
    rows and this gate cannot disagree about a row the tool wrote.
    `casefold()` is no one disk's own fold either: NTFS's table does not fold
    the German sharp s (U+00DF) to `ss`, so for such a pair this may name a
    collision that disk does not make, and APFS also ignores normalization,
    which no fold here handles. It errs on the side of a gate that says one
    row has to go.

    A row whose spelling an earlier row already has, to the byte, keeps the
    finding it always had. A row that differs only in case, as a
    case-insensitive disk folds it, names BOTH rows as written. Either way
    each later row is one finding, against the first row that holds its name.
    A row with no `project:` is `member-project`'s, and a row that is no
    mapping is `member-row`'s: both are skipped here, as
    `_check_member_ids_unique` skips them.
    """
    spelled: set[str] = set()
    first_folded: dict[str, str] = {}
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project:
            continue
        if project in spelled:
            report.finding("member-duplicate",
                           f"{project} appears more than once in `members:`")
            continue
        spelled.add(project)
        first = first_folded.setdefault(project.casefold(), project)
        if first != project:
            report.finding(
                "member-duplicate",
                f"{first} and {project} are two rows of `members:` whose "
                f"`project:` differs only in case, so `members/{first}` and "
                f"`members/{project}` are one directory on a case-insensitive "
                "disk (macOS, Windows), and a holder there can keep only one "
                "of them. Whether the rows pin one project or two, one of "
                "them has to go: keep the row whose `repository:` is the "
                "member's and drop the other.")


def _check_member_ids_unique(root: Path, members: list,
                             report: Report) -> None:
    """No two rows record ONE `id:` — that is one project pinned twice (#206).

    `id` is the member's own `project.yaml` id, so two rows recording the same
    one mount the same project twice, however each row spelled its repository:
    GitHub resolves `InkRouter/IRRS` and `inkrouter/irrs` to one repository,
    and a `family.py add` that compared the spelling used to write both rows
    and pass this gate. A row with no `id:` is `member-id-absent`'s finding
    and a row with no `project:` is `member-project`'s, not this one's.

    A row whose `project:` an earlier row already spells EXACTLY is
    `member-duplicate`'s finding and is skipped here: one finding for one
    fault, and the `remove` this one prints would take out both of those
    rows, because `family.py remove` drops every row spelled that way.

    It reads `family.yaml` alone, so it runs under `--no-members` too — the
    run a private family's CI falls back to when its members cannot be
    checked out. The remediation is runnable as printed: openRepoShape's
    `scripts/family.py` from a checkout of the standard, this holder's own
    path, and the later row's own spelling, which `remove` matches exactly;
    and before it the `git switch -c` that `remove` needs on a holder that
    stands on its tracking branch, which it refuses (#487, #539).
    """
    ids: dict[str, str] = {}
    projects: set[str] = set()
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project or project in projects:
            continue
        projects.add(project)
        if not row.get("id"):
            continue
        member_id = str(row["id"])
        if member_id not in ids:
            ids[member_id] = project
            continue
        first = ids[member_id]
        report.finding(
            "member-duplicate-id",
            f"{project} and {first} both record id {member_id!r}: one "
            "project is pinned twice. A family pins each project once. From "
            "a checkout of openRepoShape, and on a branch other than the "
            "holder's tracking branch, which `remove` refuses "
            f"(`{_switch_line(root, 'remove', member_id)}` makes one), "
            f"`{PYTHON} scripts/family.py remove "
            f"--family-root {shlex.quote(str(root))} --member "
            f"{shlex.quote(project)}` takes the later row, {project}, out; "
            f"name {first} there instead to keep {project}. {BRANCH_LEFT}")


def _gitmodules_sections(root: Path) -> dict[str, dict[str, str]]:
    """Every `submodule` section of `.gitmodules`, `{name: {key: value}}`,
    each key in the order git lists it: the file read ONCE for the two
    questions asked of it, two sections for one path (#300) and a path no
    row names (#361).

    READ AS GIT READS IT, with `git config -z --file .gitmodules --list` as
    `family.py` reads it, and no parser of this file's own: the working-tree
    file, which in CI is HEAD's. A holder with no members has no
    `.gitmodules`, and that is no finding; one git cannot read is a refusal,
    because nothing could be cloned from it either. EVERY KEY a section
    holds is kept, not its path and url alone, because the remedy for a
    section no row names takes each of them out (`family.py`'s
    `_submodule_paths` says why: a key left behind is inherited).

    No git to run is `git-not-runnable` (#368). It used to be
    `gitmodules-unreadable`, which now means only a file git ran and could
    not read: the missing git is one fact about the machine, and every check
    here that meets it says so under one code.
    """
    return _sections_listed(_gitmodules_listed(root))


def _gitmodules_listed(root: Path) -> bytes:
    """What `git config -z --file .gitmodules --list` prints of the work
    tree's file, or nothing where there is none, read as
    `_gitmodules_sections` says: what it and `_check_gitmodules_values`
    read (#768)."""
    if not os.path.lexists(root / GITMODULES):
        return b""
    with _git_runs(f"{GITMODULES} could not be read as git reads it"):
        try:
            return git_out(["config", "-z", "--file", GITMODULES, "--list"],
                           cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitmodules-unreadable",
                f"{GITMODULES} could not be read as git reads it: "
                f"{exc.detail}",
                "Remediation: git cannot read it either, so none of this "
                "holder's submodules can be cloned from it as it stands. Mend "
                f"the file by hand (`git config -f {GITMODULES} --list` says "
                "where it breaks), then run this again.") from exc


def _sections_listed(listed: bytes) -> dict[str, dict[str, str]]:
    """`{name: {key: value}}` of every `submodule` section in what `git
    config -z --list` printed, each key in the order git lists it: one
    reading for the work tree's `.gitmodules` and HEAD's (#611)."""
    sections: dict[str, dict[str, str]] = {}
    for record in listed.split(b"\0"):
        key, _, value = record.decode("utf-8",
                                      "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if section.startswith("submodule."):
            sections.setdefault(section[len("submodule."):],
                                {})[variable] = value
    return sections


def _head_gitmodules(root: Path
                     ) -> tuple[bool, dict[str, dict[str, str]]] | None:
    """`(whether HEAD holds a .gitmodules, its sections)`, read as
    `_gitmodules_sections` reads the work tree's, or None for a HEAD git
    cannot list, a holder before its first commit, which a clone cannot
    take either (#611).

    HEAD'S, NOT THE WORK TREE'S: a recursive clone of this holder, and CI's
    checkout, read the file HEAD holds. A work tree's copy nobody has
    committed is no fact about what a clone gets, and neither is one a
    sparse checkout leaves out of the work tree or a deletion nobody has
    committed. HEAD's ROOT TREE is listed and the entry picked by name, with
    no pathspec, as `_member_gitlinks` lists HEAD. One git cannot read is
    `gitmodules-unreadable`, as the work tree's is.
    """
    head = _head_listed(root)
    return None if head is None else (head[0], _sections_listed(head[1]))


def _head_listed(root: Path) -> tuple[bool, bytes] | None:
    """`(whether HEAD holds a .gitmodules, what `git config -z --blob
    <its blob> --list` prints of it)`, read as `_head_gitmodules` says:
    what it and `_check_gitmodules_values` read (#768)."""
    with _git_runs(f"HEAD's {GITMODULES} could not be read as git reads it"):
        try:
            tree = git_out(["ls-tree", "-z", "HEAD"], cwd=root, binary=True)
        except Refusal:
            return None
        blob = next((meta.split()[2].decode("ascii")
                     for meta, _, name in (record.partition(b"\t")
                                           for record in tree.split(b"\0"))
                     if name == GITMODULES.encode()
                     and meta.split()[1:2] == [b"blob"]), None)
        if blob is None:
            return False, b""
        try:
            return True, git_out(["config", "-z", "--blob", blob, "--list"],
                                 cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitmodules-unreadable",
                f"HEAD's {GITMODULES} could not be read as git reads it: "
                f"{exc.detail}",
                "Remediation: git cannot read it either, so none of this "
                "holder's submodules can be cloned from it. Mend the file by "
                f"hand (`git config -f {GITMODULES} --list` says where it "
                "breaks), commit it, then run this again.") from exc


#: Where `gitmodules-value-refused` says a value is, by whether the work
#: tree's file and HEAD's give it (#768).
GIVEN_WHERE = {(True, True): "here and in HEAD, which a clone reads",
               (True, False): "in the work tree, not in HEAD",
               (False, True): "in HEAD, which a clone reads, not in the "
                              "work tree"}

#: What git takes for a `submodule.<name>.<key>` whose value it dies on as
#: it reads `.gitmodules` (#768), as `gitmodules-value-refused` says it.
#: This, `_values_refused` and `_git_takes_bool` say what bootstrap's
#: `TAKES`, `refused_value` and `git_bool` say, and
#: `tests/test_family_gitmodules_values.py` holds the two scripts to one
#: answer: a change made here is made there too (#856).
GIT_TAKES = {"update": "one of `none`, `checkout`, `rebase` or `merge`",
             "shallow": "a boolean, `true` or `false`",
             "fetchrecursesubmodules": "a boolean or `on-demand`",
             "ignore": "one of `untracked`, `dirty`, `all` or `none`",
             "path": "a path", "url": "a url", "branch": "a branch name"}


def _check_gitmodules_values(root: Path, members: list,
                             report: Report) -> tuple[bool, bool]:
    """No section of `.gitmodules` gives a value git dies on as it reads
    the file, the `gitmodules-value-refused` finding (#768). Returns
    whether the work tree's file gives one, and whether the work tree's
    or HEAD's does.

    Git dies reading such a file, before `git submodule update` checks
    out any member, so `make bootstrap` checks none out either. In
    a plain clone the members modes refused `member-uninitialized` for the
    first row, naming that same update, and `--no-members` said `family
    ok`. The rules are `parse_config`'s in git's submodule-config.c
    (`_values_refused`). The work tree's file is read, which git reads
    here, and HEAD's, which a clone reads, as `member-gitmodules-absent`
    reads it: no member needs to be checked out, so every mode asks it.
    One finding for each key, naming each value git dies on there.

    The remedy is by key, one command to a line, on the work tree's file,
    as `gitmodules-path-unnamed` takes a key out: `--unset-all` takes out
    every line of it, since git reads a section without one, and
    `.gitmodules` is then committed where HEAD's gives it too. A member's
    own section gets its `path` or `url` written back, as it last gave
    one, or else as `family.py add` writes it, named after its path, with
    `https://github.com/` and the row's `repository:` (`_written_back`).
    Where HEAD's file alone gives the value, the work tree's is what to
    commit, and where the work tree has no `.gitmodules`, the first such
    finding puts HEAD's back first, whose value its lines take out, and
    not the index's, which git reads there: a fix staged in the index's
    file is lost (#768, lane 1's NIT 1 on #889). Every one of these is
    recorded as a write (`Report.wrote`): a staged removal's finding after
    it then puts no file back over the fix (lane 1's SHOULD 1)."""
    present = os.path.lexists(root / GITMODULES)
    here = _submodule_entries(_gitmodules_listed(root))
    head = _head_listed(root)
    there = _submodule_entries(head[1]) if head else []
    in_work = _values_refused(root, here)
    in_head = _values_refused(root, there)
    rows = {f"{DEFAULT_MEMBERS_DIR}/{row['project']}": row.get("repository")
            for row in members if isinstance(row, dict)
            and isinstance(row.get("project"), str) and row["project"]}
    put_back = present
    for name, key in dict.fromkeys([*in_work, *in_head]):
        report.wrote = True
        said = _value_said(name, key, in_work, in_head)
        if present and (name, key) not in in_work:
            report.finding("gitmodules-value-refused",
                           f"{said} Stage and commit the work tree's "
                           f"{GITMODULES}, which does not give it.")
            continue
        back = _written_back(name, key, here if present else there, rows)
        report.finding("gitmodules-value-refused", _value_taken_out(
            said, f"submodule.{name}.{key}", back, put_back=put_back,
            committed=(name, key) in in_head))
        if not put_back:
            report.put_back = f"HEAD:{GITMODULES}"
        put_back = True
    return bool(in_work), bool(in_work or in_head)


def _value_said(name: str, key: str,
                in_work: dict[tuple[str, str], list[str | None]],
                in_head: dict[tuple[str, str], list[str | None]]) -> str:
    """`gitmodules-value-refused` up to its remedy, for the key `key` of
    the section `name` (#768): each value the work tree's file and HEAD's
    give it, where, and what git takes. Where HEAD's alone gives one, the
    file git reads here may not, so it says git dies on it in a clone,
    which reads HEAD's."""
    full = f"submodule.{name}.{key}"
    values = dict.fromkeys([*in_work.get((name, key), []),
                            *in_head.get((name, key), [])])
    where = (name, key) in in_work, (name, key) in in_head
    dies = ("so in a clone neither `git submodule update` nor make "
            "bootstrap checks out any member" if where == (False, True)
            else "before `git submodule update` checks out any member, so "
            "neither that nor make bootstrap checks one out")
    return (f"{GITMODULES} gives `{spelled(full)}` " + " and ".join(
        "no value" if value is None else f"the value `{spelled(value)}`"
        for value in values) + f" {GIVEN_WHERE[where]}, and git dies "
        f"reading a file that does, {dies}. Git takes {GIT_TAKES[key]} for "
        "that key.")


def _value_taken_out(said: str, full: str, back: str | None, *,
                     put_back: bool, committed: bool) -> str:
    """`gitmodules-value-refused` whole, `said` (`_value_said`) and its
    commands, one to a line, on the work tree's file (#768): HEAD's put
    back first where the work tree has none and no finding before put it
    back (`put_back` False), the key `full` taken out, and `back` written
    in, where it is given, then the commit where HEAD's gives the value
    (`committed`)."""
    key = full.rpartition(".")[2]
    lines = [] if put_back else [f"git checkout HEAD -- {GITMODULES}"]
    lines.append(f"git config -f {GITMODULES} --unset-all "
                 f"{shlex.quote(full)}")
    if back is not None:
        lines.append(f"git config -f {GITMODULES} {shlex.quote(full)} "
                     f"{back}")
    return (f"{said} "
            + ("" if put_back else f"The work tree holds no {GITMODULES}, "
               "so the first line below puts HEAD's back. ")
            + "Take the key out"
            + (f" and write its {key} back" if back is not None else "")
            + " by hand, in a POSIX shell"
            + (f", then stage and commit {GITMODULES}" if committed else "")
            + ":" + "".join(f"\n    {line}" for line in lines))


def _submodule_entries(listed: bytes) -> list[tuple[str, str, str | None]]:
    """`(name, key, value)` for each `submodule.<name>.<key>` in what `git
    config -z --list` printed, in file order, None for a key with no value
    (#768). A section git ignores whole, whose name is empty or has a `..`
    component, split on `/` and on a backslash, gives none."""
    entries: list[tuple[str, str, str | None]] = []
    for record in listed.split(b"\0"):
        key, valued, value = record.decode("utf-8",
                                           "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        name = section[len("submodule."):]
        if (section.startswith("submodule.") and name
                and ".." not in name.replace("\\", "/").split("/")):
            entries.append((name, variable, value if valued else None))
    return entries


def _values_refused(root: Path, entries: list[tuple[str, str, str | None]]
                    ) -> dict[tuple[str, str], list[str | None]]:
    """`{(name, key): [each value]}` of `entries` (`_submodule_entries`)
    that git dies on as it reads `.gitmodules` (#768), as `parse_config`
    in its submodule-config.c reads a key: a `path`, `url`, `update` or
    `ignore` with no value (`bad config line`), a `branch` with none (git
    before 2.43.1 crashes on it, and a later one refuses it as it refuses
    a `url` with none), an `update` other than `none`, `checkout`,
    `rebase` or `merge`, in that case, a `!command` included (`invalid
    value`), a `shallow` that is no boolean, and a `fetchrecursesubmodules`
    that is neither a boolean nor `on-demand`, as git itself reads a
    boolean (`git config --type=bool`). An `ignore` git does not know is
    a warning, and any other key takes any value."""
    refused: dict[tuple[str, str], list[str | None]] = {}
    for name, key, value in entries:
        if value is None:
            dies = key in {"path", "url", "update", "ignore", "branch"}
        elif key == "update":
            dies = value not in {"none", "checkout", "rebase", "merge"}
        else:
            dies = (key == "shallow" or (key == "fetchrecursesubmodules"
                                         and value != "on-demand")
                    ) and not _git_takes_bool(root, value)
        if dies:
            refused.setdefault((name, key), []).append(value)
    return refused


def _git_takes_bool(root: Path, value: str) -> bool:
    """Whether git reads `value` as a boolean, asked of git itself (`git
    config --type=bool`), which reads `shallow` and
    `fetchRecurseSubmodules` so (#768). It is asked as the `--default` of
    a key looked up in an empty file, so no `probe.value` in any of the
    person's own config scopes is read in its place."""
    with _git_runs(f"a value in {GITMODULES} could not be read as git "
                   "reads a boolean"):
        try:
            git_out(["config", "--file", os.devnull, "--type=bool",
                     f"--default={value}", "--get", "probe.value"],
                    cwd=root)
        except Refusal:
            return False
    return True


def _written_back(name: str, key: str,
                  entries: list[tuple[str, str, str | None]],
                  rows: dict[str, object]) -> str | None:
    """What `gitmodules-value-refused` writes back for the `path` or `url`
    of the section `name` once its key is out (#768), POSIX-quoted, or None
    for any other key, and for a section whose path no row's
    `members/<project>` is: the value the section last gave it that git
    takes, or else, as `family.py add` writes a section named after its
    path, that path, or `https://github.com/` and the row's `repository:`,
    `<url>` where that is not `<org>/<Name>`. The section's path is the one
    it last gave, or its name where it gave none."""
    if key not in {"path", "url"}:
        return None
    gave = {wanted: [value for section, variable, value in entries
                     if section == name and variable == wanted and value
                     and not value.startswith("-")]
            for wanted in ("path", "url")}
    path = gave["path"][-1] if gave["path"] else name
    if path not in rows:
        return None
    if gave[key]:
        return shlex.quote(gave[key][-1])
    if key == "path":
        return shlex.quote(path)
    repository = rows[path]
    return (shlex.quote(f"https://github.com/{repository}.git")
            if isinstance(repository, str) and QUALIFIED_RE.match(repository)
            else "<url>")


#: Where git's submodule commands read `.gitmodules` from when the work
#: tree's is gone from disk, in git's order (`config_from_gitmodules`):
#: `(the name git resolves, the line that puts the work tree's back from
#: it, whose it is)`.
GITMODULES_SOURCES = (
    (f":{GITMODULES}", f"git checkout -- {GITMODULES}", "the index's"),
    (f"HEAD:{GITMODULES}", f"git checkout HEAD -- {GITMODULES}",
     "HEAD's, as the index holds none"),
)


def _gitmodules_put_back(root: Path) -> tuple[str, str, str]:
    """Where the work tree's `.gitmodules` is gone from disk, the one git's
    submodule commands read in its place, as `(the name git resolves, the
    line that puts the work tree's back from it, whose it is)`; three empty
    strings where the work tree holds one, or nothing does (#762, rv820's
    SHOULD 2).

    GIT'S ORDER (`GITMODULES_SOURCES`): `:.gitmodules`, the index's at stage
    0, then `HEAD:.gitmodules`, each resolved here as git resolves it, with
    `git rev-parse --verify --quiet`. A file deleted and not staged, or
    whose deletion is staged, leaves git every section it read before; a
    cure that wrote one with `git config -f` made a file of that section
    alone, which staged and committed dropped every other, so the line puts
    the file back first.
    """
    if os.path.lexists(root / GITMODULES):
        return "", "", ""
    with _git_runs(f"where git reads {GITMODULES} from could not be read"):
        for spec, line, whose in GITMODULES_SOURCES:
            try:
                git_out(["rev-parse", "--verify", "--quiet", spec], cwd=root)
            except Refusal:
                continue
            return spec, line, whose
    return "", "", ""


def _file_put_back(root: Path, report: Report | None) -> tuple[str, str]:
    """`(the line that puts the work tree's .gitmodules back, whose file it
    puts back)` for a remedy whose lines write that file with `git config
    -f` where it is gone from disk (`_gitmodules_put_back`), or two empty
    strings: where the work tree holds one, and where a finding printed
    before it put it back (`Report.put_back`), so ONE PUT-BACK SERVES EVERY
    FINDING and none puts it back over what the lines between wrote
    (#879). `report` holds the findings printed before it, and records the
    put-back; None for a refusal, printed alone, which always says it."""
    if report is not None and report.put_back:
        return "", ""
    spec, line, whose = _gitmodules_put_back(root)
    if report is not None:
        report.put_back = spec
    return line, whose


def _check_gitmodules_paths(sections: dict[str, dict[str, str]],
                            report: Report) -> None:
    """No two sections of `.gitmodules` give ONE path (#300).

    `family.py add` committed a second section for a mount path that a
    section under another name already gave — a half-removed member, a hand
    edit, a merge that kept both sides — and this gate passed the result. A
    recursive clone fetches the path from only one of them, the last in the
    file, so the other is a url the next edit to the file can make the one
    fetched. `add` refuses to write one now; this finds a holder that
    already has one. `sections` is `_gitmodules_sections`'s reading. A
    section whose path no row names is `_check_gitmodules_named`'s question
    (#361). Its by-hand edit is recorded as a write (`Report.wrote`), so a
    staged removal's finding after it puts no file back over the edit
    (lane 1's SHOULD 1 on #889).
    """
    paths: dict[str, list[str]] = {}
    for name, keys in sections.items():
        if "path" in keys:
            paths.setdefault(keys["path"], []).append(name)
    for path, names in paths.items():
        if len(names) < 2:
            continue
        listing = ", ".join(
            f"`{name}` (" + (f"url {sections[name]['url']}"
                             if "url" in sections[name] else "no url") + ")"
            for name in names)
        report.finding(
            "gitmodules-path-twice",
            f"{GITMODULES} gives the path {path} to {len(names)} "
            f"submodules, {listing}. A recursive clone fetches that path "
            "from only one of them, the last in the file, so the order of "
            "the sections decides which repository lands there. Keep the one "
            "whose url is the member's (`family.py add` names it after its "
            f"path, `{path}`) and take each other out by hand, `git config "
            f"-f {GITMODULES} --unset-all submodule.<name>.<key>` for every "
            "key that section holds, so a submodule later given its name "
            f"inherits none of them, then commit {GITMODULES}.")
        report.wrote = True


def _in_members(path: str) -> bool:
    """Whether `path` is in `members/`, the directory spelt in any case
    (#361): `Members/Zed` is in `members/` on macOS and Windows."""
    return path.split("/", 1)[0].casefold() == DEFAULT_MEMBERS_DIR


def _member_gitlinks(root: Path) -> dict[str, str]:
    """`{path: commit}` for every gitlink this repository records: what
    `_check_gitlinks_named` asks of each in `members/`, the directory spelt
    in any case (#361, `_in_members`), and `_check_gitlinks_elsewhere` and
    `_check_gitmodules_named` of each outside it (#878). It listed
    `members/` alone, so no mode asked about a gitlink elsewhere, and
    `gitmodules-path-unnamed`'s remedy for a section that gave one took
    out the section and left the gitlink, at which a plain clone's `git
    submodule update --init` stops.

    IN THE ORDER `recorded_gitlink` READS ONE: the index at stage 0 first,
    HEAD second. A path the index holds at stage 0 as a gitlink is answered
    from there, any other gitlink HEAD records from HEAD, so this lists
    exactly the paths at which that function finds a gitlink, and each with
    the commit it would answer.

    THE WHOLE INDEX AND THE WHOLE TREE, WITH NO PATHSPEC, as `family.py`'s
    `_index_entries` lists the index (#302): a pathspec matches `members/`
    only in the case it is spelt, and `Members/Zed` is in `members/` on
    macOS and Windows. `-z`, so a name git would quote comes back as itself.

    A HEAD git cannot list is read as recording nothing, as
    `recorded_gitlink` reads it: a holder before its first commit has none.
    An index git cannot list is `gitlinks-unreadable`: this is the one check
    of `members/` that `--no-members` runs, and a directory nobody could
    list is never an implicit pass.
    """
    with _git_runs(f"the gitlinks this repository records in "
                   f"{DEFAULT_MEMBERS_DIR}/ could not be listed"):
        try:
            head = git_out(["ls-tree", "-r", "-z", "HEAD"], cwd=root,
                           binary=True)
        except Refusal:
            head = b""
        try:
            index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
        except Refusal as exc:
            raise Refusal(
                "gitlinks-unreadable",
                f"the index could not be listed, so the gitlinks it records "
                f"in {DEFAULT_MEMBERS_DIR}/ could not be read: {exc.detail}",
                "Remediation: git status in this repository says what is "
                "wrong with its index. Mend that, then run this "
                "again.") from exc
    found: dict[str, str] = {}
    for listing, oid_at, stage_at in ((head, 2, None), (index, 1, 2)):
        for record in listing.split(b"\0"):
            meta, _, name = record.partition(b"\t")
            fields = meta.split()
            if len(fields) != 3 or fields[0] != GITLINK_MODE:
                continue
            if stage_at is not None and fields[stage_at] != b"0":
                continue
            path = name.decode("utf-8", "surrogateescape")
            found[path] = fields[oid_at].decode("ascii").lower()
    return found


def _staged_removals(root: Path, gitlinks: dict[str, str]) -> frozenset[str]:
    """The paths of `gitlinks` (`_member_gitlinks`) whose removal is staged
    and not committed (#681): HEAD records the gitlink, and the index holds
    no entry at that path, at any stage. A `git rm` of one fails (`pathspec
    ... did not match any files`), so a finding about one says to commit
    the removal and prints none: it named the same `git rm` until the
    commit. A row's own is `member-gitlink-removal-staged` (#762). A path
    the index holds unmerged is a conflict, not a removal,
    and is not one of these. The whole index, `-z`, as `_member_gitlinks`
    lists it."""
    with _git_runs(f"the gitlinks this repository records in "
                   f"{DEFAULT_MEMBERS_DIR}/ could not be listed"):
        listed = git_out(["ls-files", "-z"], cwd=root, binary=True)
    indexed = {name.decode("utf-8", "surrogateescape")
               for name in listed.split(b"\0")}
    return frozenset(set(gitlinks) - indexed)


class RowPath(NamedTuple):
    """What a row names by the path it gives: `who` names the row in a
    finding, `canonical` is the one path its project may have,
    `members/<project>`, or None for a row with no `project:`, `pin` is
    the commit its `pin:` names, lowered, or None where that is no 40-hex
    commit (#648), and `repository` its `repository:`, for the section the
    wrong-case move writes (#762)."""

    who: str
    canonical: str | None
    pin: str | None = None
    repository: object = None


def _row_paths(members: list) -> dict[str, RowPath]:
    """`{path: RowPath}` for every row that gives a path: its `path:`, or
    `members/<project>` where it has none, defaulted as
    `_check_member_repository_and_path` defaults it. `who` names the row in
    a finding: `the row for <project>`, or, for a row with no `project:`
    (`member-project`'s), `a row with no project:`.

    A row NAMES the path it gives, AS WRITTEN (#361), and nothing else: a
    hand-edited `path:` names that string, so the member's own mount is then
    a gitlink no row names, beside the row's `member-path` finding. The
    row's canonical path rides along, because what to say about a path that
    folds to the row's depends on which of the two is the canonical one.
    """
    named: dict[str, RowPath] = {}
    for row in members:
        if not isinstance(row, dict):
            continue
        project = row.get("project")
        if not isinstance(project, str) or not project:
            project = None
        canonical = (f"{DEFAULT_MEMBERS_DIR}/{project}"
                     if project is not None else None)
        if row.get("path"):
            path = str(row["path"])
        elif canonical is not None:
            path = canonical
        else:
            continue
        pin = row.get("pin")
        commit = str(pin.get("commit") or "") if isinstance(pin, dict) else ""
        named.setdefault(path, RowPath(
            f"the row for {project}" if project else "a row with no project:",
            canonical, commit.lower() if COMMIT_RE.match(commit) else None,
            row.get("repository")))
    return named


def _case_variant(path: str,
                  named: dict[str, RowPath]) -> tuple[str, RowPath] | None:
    """`(row path, row)` of a row naming `path` in another case, or None.

    `str.casefold()`, as `member-duplicate` folds (#331): on macOS and
    Windows `Members/Atlas` IS `members/Atlas`, so a finding about the one
    says which row the other belongs to.
    """
    folded = path.casefold()
    for row_path, row in named.items():
        if row_path.casefold() == folded:
            return row_path, row
    return None


#: The three things a path that folds to a row's path can be, and so what a
#: finding about it may tell an operator to run: `STRAY`, a second path to
#: the member's own directory, which a command can take out; `ROW_EDITED`,
#: the member's own path, whose row was hand-edited into a case variant of
#: it; and `WRONG_CASE`, the only record of the member there is, in the
#: wrong case.
STRAY, ROW_EDITED, WRONG_CASE = "stray", "row-edited", "wrong-case"

#: What a gitlink or a section nobody can account for says to do when the
#: fault may be in the row, in `git log -p -- family.yaml`'s words.
RESTORE_ROW = ("If its row was deleted or its path: edited by hand, put the "
               "row back as git last had it (git log -p -- family.yaml shows "
               "the change).")


def _variant_case(path: str, row_path: str, row: RowPath,
                  holds: set[str]) -> str:
    """Which of `STRAY`, `ROW_EDITED` and `WRONG_CASE` the path `path`, which
    folds to the path `row_path` that `row` names, is (#361).

    `holds` is every exact path that holds what is being asked about: the
    gitlinks, or the paths the sections give. A command that takes `path` out
    leaves the member standing in ONE state only, `STRAY`: the row's path is
    its canonical `members/<project>` AND that exact path holds a gitlink (a
    section) too, so `path` is a second one. In the other two it takes the
    member's own record out, and every mode that does not check members would
    then say `family ok`:

    - `ROW_EDITED`: `path` IS the row's canonical path and the row spells it
      another way, a mount at `members/Nova` and a row written `Members/Nova`.
      The row is the hand edit, and the cure is in `family.yaml`.
    - `WRONG_CASE`, any other: the row's path is canonical with nothing at it,
      so `path` is the only record there is, in the wrong case; or the row's
      path is no canonical one either and `path` is a third spelling, which
      this does not decide while the row is wrong.
    """
    if row_path == row.canonical and row_path in holds:
        return STRAY
    if path == row.canonical:
        return ROW_EDITED
    return WRONG_CASE


def _variant_said(row_path: str, row: RowPath) -> str:
    """The sentence that says a path is a case variant of a row's."""
    return (f" It is a case variant of {row_path}, which {row.who} names, and "
            "macOS and Windows hold the two as one directory.")


def _variant_advice(kind: str, path: str, row_path: str, row: RowPath,
                    what: str) -> str:
    """What a `ROW_EDITED` or `WRONG_CASE` path says, in place of a command.

    `what` is `gitlink` or `section`. No command is printed in either: the
    `git rm --cached` or the `--unset-all` lines that suit a `STRAY` would
    take the member's own record out, and a family whose members a runner
    could not check out would then pass. A `ROW_EDITED` says the row is what
    is wrong, and where to put its path back; a `WRONG_CASE` says the member
    is recorded in the wrong case, and sends the operator to `git log -p --
    family.yaml`, as an unnamed path that no row folds to does (`RESTORE_ROW`).
    A `WRONG_CASE` gitlink whose row's path is its canonical one and whose
    pin is a commit never comes here: `_check_gitlinks_named` prints the
    index move for it, which records the member as it takes the gitlink out
    (#648).
    """
    if kind == ROW_EDITED:
        return (f" It is {path}, the one path {row.who} may have, and the row "
                f"names it as {row_path} instead, which macOS and Windows "
                "hold as one directory with it. The row's path: is the hand "
                f"edit and this {what} is the member's own: put {path} back "
                "in the row's path: (git log -p -- family.yaml shows the "
                f"change). No command is printed, since this {what} is not "
                "what is wrong.")
    return (_variant_said(row_path, row)
            + " The member is recorded in the wrong case, so no command is "
              f"printed: taking this {what} out could un-register it. "
            + RESTORE_ROW)


def _check_gitlinks_named(root: Path, gitlinks: dict[str, str],
                          named: dict[str, RowPath], removed: frozenset[str],
                          report: Report) -> None:
    """Every gitlink in `members/` is at a path some row names EXACTLY — the
    `member-gitlink-unnamed` finding (#361).

    Every member check starts from a row, so a gitlink no row names was
    never asked about: a member mounted by hand with `git submodule add`, or
    a row deleted by hand. Where a section of HEAD's `.gitmodules` gives its
    path a url, a recursive clone of the holder fetches it all the same, and
    so does `bootstrap.py`'s `git submodule update`, while nothing pins,
    digests or identifies it. Where none does, as for a stray case variant
    or a gitlink recorded by hand, a recursive clone checks out nothing at
    it, and in a plain clone `git submodule update --init` stops there
    (`No url found for submodule path`, exit 128) before it checks out any
    member: the text said a recursive clone fetched it (#762, w648b's S1,
    S2, H1 and X1).

    EXACTLY, as git compares paths. A gitlink a row names in another case is
    still a finding, and says which of three it is (`_variant_case`). A
    second path to the member's own directory is taken out of the index
    alone with `git rm --cached`, which touches no file, and committed. The
    member's own gitlink, which the ROW misspells, prints no command, since
    taking it out could un-register the member. The only record of a member
    there is, in the wrong case, prints the index move members mode's
    `member-gitlink-absent` prints (`_wrong_case_move`, #648), which records
    the member at its row's path as it takes the variants out, so
    `--no-members`, the run CI falls back to when the members cannot be
    checked out, names the cure too; where the row's path is not its
    canonical one, or its pin no commit, it prints no command either. Any
    other is taken out with a plain `git rm`,
    which refuses while its checkout holds changes, then mounted with
    `family.py add`: `add` cannot adopt an existing mount, and after `git rm
    --cached` alone it refuses the checkout left in the way
    (`member-path-taken`). The removal is committed between the two (#611):
    `add` refuses a path under another spelling of `members/` that HEAD
    holds and the index no longer does (#574), which an uncommitted `git rm
    -- Members/<P>` leaves. `add` then names the object store `git rm` leaves
    in `.git/modules`, if it is still there. `--member` is quoted as the
    paths are, its project alone: `<org>` is the operator's to fill in.
    A BRANCH FIRST (#539): `add` refuses the holder's tracking branch
    (#487), so the first of the three lines is the `git switch -c` that
    makes the branch `add` suggests.

    A REMOVAL STAGED AND NOT COMMITTED (`removed`, `_staged_removals`) is
    still a gitlink HEAD records, so it is still named, and its `git rm`
    typed again failed: it says to commit the removal instead and prints
    no `git rm` (#681). A hand mount's keeps the branch and the `add`.

    EACH `git rm` COMES AFTER `git add -- .gitmodules` where a value
    finding's lines, printed before it, may leave that file with changes
    not staged, or it holds some as it stands (`_stage_first`): git takes
    no gitlink out of the index then, `--cached` and `-f` or not, and the
    stray's, the hand mount's and the move's `git rm` each exited 128
    (#879's C3). The move puts back a `.gitmodules` gone from the work
    tree before it writes one, unless a finding before it did
    (`_move_context`, #879's C1).

    A gitlink outside `members/` is no member's mount, and no row can name
    it: `_check_gitlinks_elsewhere` and `_check_gitmodules_named` ask
    about it (#878).

    The gitlinks in `members/` no row names are listed once, before the
    loop, and each one's remedy is `_variant_remedy`'s or
    `_mounted_by_hand`'s, so this stays within S3776's limit (rv882's
    SHOULD 3 on #882).

    A hand mount's plain `git rm` takes its section out of the work tree's
    `.gitmodules`, as the move's lines write one (`_move_section`): each is
    recorded as a write (`Report.wrote`), so a staged removal's finding
    after it puts no file back over it (lane 1's SHOULD 1 on #889).
    """
    unnamed = [path for path in sorted(gitlinks)
               if path not in named and _in_members(path)]
    if not unnamed:
        return
    head = _head_gitmodules(root)
    fetched = ({keys["path"] for keys in head[1].values()
                if "path" in keys and "url" in keys}
               if head is not None else set())
    stage = head is not None and _stage_first(
        root, "gitmodules-value-refused" in report.codes)
    for path in unnamed:
        said = _gitlink_unnamed_said(path, gitlinks[path], path in fetched)
        variant = _case_variant(path, named)
        if variant is not None:
            report.finding(
                "member-gitlink-unnamed",
                said + _variant_remedy(root, path, variant, gitlinks,
                                       path in removed, stage, report))
            continue
        report.finding(
            "member-gitlink-unnamed",
            f"{said} " + _mounted_by_hand(
                root, path, _hand_project(path), path in removed, stage,
                _staged_over(root, path, gitlinks[path])))
        report.wrote = report.wrote or path not in removed


def _gitlink_unnamed_said(path: str, commit: str, fetched: bool) -> str:
    """What `member-gitlink-unnamed` says first of the gitlink at `path`,
    at `commit`, by whether a section of HEAD's `.gitmodules` gives it a
    url (`fetched`): a recursive clone fetches it, or no clone checks it
    out and a plain clone's update stops there (#762)."""
    return (f"{path} is a gitlink at {commit} that no row of members: "
            + ("names, so a recursive clone of this holder fetches it and "
               "nothing here pins, digests or identifies it." if fetched else
               f"names and no section of HEAD's {GITMODULES} gives a url, so "
               "a recursive clone of this holder checks out nothing at it, "
               "in a plain clone git submodule update --init stops there (No "
               "url found for submodule path, exit 128) before it checks out "
               "any member, and nothing here pins, digests or identifies "
               "it."))


def _hand_project(path: str) -> str | None:
    """The project a hand mount at `members/<P>` would be mounted as, `<P>`,
    or None for a path deeper or shallower than that."""
    parts = path.split("/")
    return parts[1] if len(parts) == 2 and parts[1] else None


def _variant_remedy(root: Path, path: str, variant: tuple[str, RowPath],
                    gitlinks: dict[str, str], staged: bool, stage: bool,
                    report: Report) -> str:
    """What `member-gitlink-unnamed` says, after what the gitlink at `path`
    is, of one a row names in another case (`variant`, `_case_variant`):
    the wrong-case move where it is the only record of the member
    (`_wrong_case_move`), the second path's `git rm --cached` where it is
    a STRAY (`_second_path_out`, after `git add -- .gitmodules` where
    `stage`, and the commit alone where its removal is `staged`), and
    `_variant_advice`'s words for the others, with no command."""
    row_path, row = variant
    kind = _variant_case(path, row_path, row, set(gitlinks))
    if kind == WRONG_CASE and row_path == row.canonical and row.pin:
        variants = sorted(other for other in gitlinks
                          if other != row_path
                          and other.casefold() == row_path.casefold())
        return (f"{_variant_said(row_path, row)} The member is recorded in "
                "the wrong case. "
                + _wrong_case_move(row_path, row.pin, variants,
                                   _move_context(root, row_path, variants,
                                                 row.repository, gitlinks,
                                                 report)))
    if kind != STRAY:
        return _variant_advice(kind, path, row_path, row, "gitlink")
    return (f"{_variant_said(row_path, row)} "
            + _second_path_out(root, path, gitlinks[path], staged, stage))


#: What a gitlink whose removal is staged and not committed says in place of
#: the `git rm` that would take it out, which fails there (#681).
STAGED_REMOVAL = ("HEAD records it and the index holds nothing at that "
                  "path, so its removal is staged and not committed, and no "
                  "git rm is printed, since one fails there (pathspec ... "
                  "did not match any files).")


def _second_path_out(root: Path, path: str, commit: str,
                     staged: bool, stage_first: bool = False) -> str:
    """What a `STRAY` gitlink at `path`, a second path to a member's own
    directory, which `_member_gitlinks` reads at `commit`, says to do: take
    it out of the index alone, with `-f` where git refuses it without
    (`_forced`, #839), or, where that is staged already (#681), commit it.

    A `git mv members/<P> Members/<P>`, staged, is this state: the index
    holds the variant, and HEAD the row's own gitlink, whose removal is
    staged (`member-gitlink-removal-staged`). A commit or an untracked file
    in the checkout `git mv` moved, and the plain `git rm --cached` refused
    (w761's candidate 2 on #828, measured on the gate's state).

    `gitlink-unnamed` says the same of a gitlink outside `members/` that no
    section gives (#878). Both come after `git add -- .gitmodules` where
    `stage_first` (`_stage_first`): after a value finding's lines the
    stray's plain `git rm --cached` exited 128 (#879's C3)."""
    if staged:
        return f"{STAGED_REMOVAL} Commit that removal."
    head = _forced(root, path, commit)
    return ((f"{STAGE_SAID[0].upper()}{STAGE_SAID[1:]}take" if stage_first
             else "Take")
            + " it out of the index alone, which touches no file"
            + _forced_said(head, "the second line" if stage_first
                           else "the line", _held_if_forced(root, path, head))
            + ":\n    " + (f"{STAGE_LINE}\n    " if stage_first else "")
            + _cached_removal(path, head))


#: The line the `git rm --cached` of a gitlink outside `members/` comes
#: after where `.gitmodules` may hold changes not staged (`_stage_first`,
#: #878), and what the text says of it, before what it says of the `git rm`.
STAGE_LINE = f"git add -- {GITMODULES}"
STAGE_WHY = ("since git rm refuses to take any gitlink out of the index, -f "
             f"or not, while {GITMODULES} holds changes not staged (please "
             f"stage your changes to {GITMODULES} or stash them to proceed, "
             "exit 128), as lines printed above may leave it or as it stands")
#: Said of `git add -- .gitmodules` beside why: it stages every other
#: change in the file too, which the commit after it then holds (rv882's
#: NIT 3 on #882).
STAGE_TOO = "which stages every other change in it too"
STAGE_SAID = (f"stage {GITMODULES} with the first line, {STAGE_TOO}, "
              f"{STAGE_WHY}, then ")


def _stage_first(root: Path, edited: bool) -> bool:
    """Whether the `git rm --cached` that `gitlink-unnamed` and
    `gitmodules-path-unnamed` print for a gitlink outside `members/` comes
    after `git add -- .gitmodules` (`STAGE_LINE`, #878).

    GIT TAKES NO GITLINK OUT OF THE INDEX, `--cached` and `-f` or not,
    while the work tree's `.gitmodules` holds changes the index does not
    (`please stage your changes to .gitmodules or stash them to proceed`,
    exit 128, `is_staging_gitmodules_ok` in git's rm.c), measured on git
    2.43 after a `gitmodules-value-refused` finding's `--unset-all` lines
    (the order #879's C3 names for a stray's `git rm --cached`), after an
    earlier unnamed section's lines, and over a hand edit not staged. So it
    does where `edited`, where lines printed before it may write the file,
    and where the file on disk differs from the index's as it stands: its
    bytes hashed as `git add` would store them (`git hash-object`) against
    the blob the index holds, as git compares them, and never by stat,
    which a file written in the same second as the index may fool. The
    commit the text names next commits what it stages, which the lines
    before it say to commit. Not where the work tree holds no
    `.gitmodules` and no line before it writes one, where `git add` would
    stage its deletion, nor where the index holds none at stage 0: git
    asks nothing of the file then."""
    if edited:
        return True
    if not os.path.lexists(root / GITMODULES):
        return False
    with _git_runs(f"whether {GITMODULES} holds changes not staged could not "
                   "be read"):
        try:
            staged = git_out(["rev-parse", "--verify", "--quiet",
                              f":{GITMODULES}"], cwd=root)
        except Refusal:
            return False
        return git_out(["hash-object", "--", GITMODULES], cwd=root) != staged


def _forced_said(head: str | None, line: str,
                 held: str = CHECKOUT) -> str:
    """What the text says after "take it out of the index alone, which
    touches no file" of the `git rm --cached` it prints as `line`, where
    `_forced` answered `head` (#839): that the removal is committed, and
    where the line takes `-f`, why, over what is on disk there (`held`,
    `_held_as`), and what `-f` does (`FORCED_SAID`), and that nothing is
    left to commit where HEAD records nothing."""
    if head is None:
        return ", and commit that"
    return ((", and commit that. The index stages it at a commit HEAD does "
             "not record there" if head else
             ": HEAD records nothing there, so nothing of it is left to "
             "commit. The index stages it")
            + f" over {held}, so {line} takes -f: {FORCED_SAID}")


def _cached_removal(path: str, head: str | None) -> str:
    """`git rm --cached -- <path>`, with `-f` where `_forced` answered
    `head` (#839)."""
    return ("git rm --cached" + ("" if head is None else " -f")
            + f" -- {shlex.quote(path)}")


def _check_gitlinks_elsewhere(root: Path, gitlinks: dict[str, str],
                              named: dict[str, RowPath],
                              removed: frozenset[str],
                              report: Report) -> None:
    """Every gitlink OUTSIDE `members/` that no row names is at a path a
    section of `.gitmodules` gives, the `gitlink-unnamed` finding (#878).

    NO ROW CAN NAME ONE, since a member's path is `members/<Project>`
    (`member-path`), and NO CLONE CAN CHECK OUT ONE NO SECTION GIVES: a
    plain clone's `git submodule update --init` stops there (`No url found
    for submodule path`, exit 128) before it checks out any member, which
    is how the holder's CI checks its members out before it runs the
    member half of this gate, a recursive clone checks out nothing at it,
    and `git submodule status` exits 128 (`no submodule mapping found`).
    No mode asked about one: `_member_gitlinks` listed `members/` alone, so
    `gitmodules-path-unnamed`'s `--unset-all` lines, typed as printed,
    left this state and the gate passed it. Bootstrap's `init_stop` names
    it, with its cure (`cures`), and so does this, in its words: `git rm
    --cached`, which touches no file, with `-f` where git refuses it
    without (`_forced`, #839), and the commit, or, where its removal is
    staged already (`removed`), the commit alone (`_second_path_out`).

    THE WORK TREE'S `.gitmodules`, read whole, as `_check_gitmodules_named`
    reads it where it gives no value git dies on: a gitlink a section
    there gives is that section's finding, which takes the gitlink out
    first, so each such gitlink is one finding, never two. Where the file
    gives a value git dies on, `gitmodules-path-unnamed` reads none of
    its sections, and a gitlink one of them gives is said once that is
    mended.

    `git add -- .gitmodules` COMES FIRST where a `gitmodules-value-refused`
    finding, printed before this one, may leave the file with changes not
    staged, or it holds some as it stands (`_stage_first`): git takes no
    gitlink out of the index then, and the `git rm` exited 128.

    WHERE THE WORK TREE'S `.gitmodules` IS GONE FROM DISK, the paths are
    read from the file git reads in its place (`_given_as_git_reads`):
    read from the work tree, none was given, and this said "no section of
    .gitmodules gives" of a gitlink the index's and HEAD's gave, whose
    plain clone checked it out (rv882's SHOULD 2 on #882)."""
    unnamed = [path for path in sorted(gitlinks)
               if path not in named and not _in_members(path)]
    if not unnamed:
        return
    given = _given_as_git_reads(root)
    stage_first = _stage_first(root,
                               "gitmodules-value-refused" in report.codes)
    for path in unnamed:
        if path in given:
            continue
        report.finding(
            "gitlink-unnamed",
            f"{path} is a gitlink at {gitlinks[path]}, outside "
            f"{DEFAULT_MEMBERS_DIR}/, that no section of {GITMODULES} gives, "
            "so in a plain clone of this holder git submodule update --init "
            "stops there (No url found for submodule path, exit 128) before "
            "it checks out any member, and a recursive clone checks out "
            f"nothing at it. No row names {path} and no clone can check it "
            "out. "
            + _second_path_out(root, path, gitlinks[path], path in removed,
                               stage_first))


def _given_as_git_reads(root: Path) -> set[str]:
    """Every path a section of `.gitmodules` gives, as git's submodule
    commands read the file: the work tree's where it is on disk, else the
    one git reads in its place (`_gitmodules_put_back`, the index's, then
    HEAD's), else none (rv882's SHOULD 2 on #882)."""
    if os.path.lexists(root / GITMODULES):
        return {keys["path"] for keys in _gitmodules_sections(root).values()
                if "path" in keys}
    spec = _gitmodules_put_back(root)[0]
    return _blob_paths(root, spec) if spec else set()


#: What a hand mount's text says its `git rm` meets where the index stages
#: the gitlink at a commit HEAD does not record there (`_mounted_by_hand`,
#: lane 1's SHOULD on #889, round 2): git's two refusals, each exit 1, the
#: second where what is on disk differs from what is staged too, as git
#: 2.43 gave them (`_staged_over`; lane 1's NIT 1 on #889, round 3).
STAGED_AT = (", and while the index stages it at a commit HEAD does not "
             "record there, as it does here (the following file has changes "
             "staged in the index, or, where what is on disk differs too, "
             "has staged content different from both the file and the HEAD, "
             "exit 1),")


def _mounted_by_hand(root: Path, path: str, project: str | None,
                     staged: bool, stage_first: bool = False,
                     staged_at: bool = False) -> str:
    """What a gitlink no row names, in no case, says to do after what it is:
    put its row back, or take a hand mount out, commit that, and mount it
    with `family.py add`, on a branch (`_check_gitlinks_named`). Where its
    removal is staged already (#681), the same with no `git rm`, and the
    checkout `git rm --cached` leaves at the path, which `family.py add`
    refuses (`member-path-taken`), deleted by hand first (rv681's S1).
    Its `git rm` comes after `git add -- .gitmodules` where `stage_first`
    (`_stage_first`): after a value finding's lines it exited 128 (#879's
    C3). Where that `git rm` refuses the gitlink as staged (`staged_at`,
    as `_staged_over` reads it), as after `git mv members/<P>
    members/<P>2`, staged, the text says so (`STAGED_AT`), where it said
    only that the line refuses while the checkout holds changes (lane 1's
    SHOULD on #889, round 2). No line here takes such a gitlink out:
    `-f` would take the checkout's changes with it."""
    member = (PROJECT_PLACEHOLDER if project is None
              else shlex.quote(project))
    add = (f"    {PYTHON} scripts/family.py add --family-root "
           f"{shlex.quote(str(root))} --member <org>/{member}")
    if staged:
        return (
            f"{STAGED_REMOVAL} Commit that removal before family.py add, "
            "which refuses a path under another spelling of members/ that "
            "HEAD holds and the index no longer does, and on a branch, since "
            "family.py add refuses the holder's tracking branch: where the "
            "holder stands on it, the first command below makes one, taking "
            "the staged removal with it. Where git rm --cached took it out, "
            f"its checkout is still at {path}, and family.py add refuses that "
            "directory (member-path-taken): delete it by hand, once nothing "
            "only it holds is needed, before the add. If it was mounted by "
            "hand, then mount it with the second, from a checkout of "
            "openRepoShape: family.py add writes its row and its gitlink in "
            "one commit, and names the object store git rm leaves under "
            f".git/modules if one is still there. {BRANCH_LEFT}\n"
            f"    {_switch_line(root, 'add', project)}\n{add}")
    staging, rm_at, add_at = ((f"stage {GITMODULES} with the second, "
                               f"{STAGE_TOO}, {STAGE_WHY}, ", "third",
                               "fourth")
                              if stage_first else ("", "second", "third"))
    return (
        f"{RESTORE_ROW} If it was mounted by hand, make a branch "
        "with the first command below, since family.py add refuses the "
        f"holder's tracking branch, {staging}take it out with the "
        f"{rm_at}, which refuses while its checkout holds changes"
        + (STAGED_AT if staged_at else "")
        + f" and takes its {GITMODULES} section out too, and commit that "
        "removal, since "
        "family.py add refuses a path under another spelling of members/ "
        "that HEAD holds and the index no longer does, then mount it "
        f"with the {add_at}, from a checkout of openRepoShape: family.py "
        "add writes its row and its gitlink in one commit, and names the "
        "object store git rm leaves under .git/modules if one is still "
        f"there. {BRANCH_LEFT}\n"
        f"    {_switch_line(root, 'add', project)}\n"
        + (f"    {STAGE_LINE}\n" if stage_first else "")
        + f"    git rm -- {shlex.quote(path)}\n{add}")


def _check_gitmodules_named(root: Path, sections: dict[str, dict[str, str]],
                            gitlinks: dict[str, str],
                            named: dict[str, RowPath], removed: frozenset[str],
                            report: Report) -> None:
    """Every path a `.gitmodules` section gives is a path some row names
    EXACTLY — the `gitmodules-path-unnamed` finding (#361).

    A section with no row is inert to a clone, which follows gitlinks, but
    it is what the next `family.py add` of its name or its path meets: under
    its own name git rewrites it in place and the member inherits every key
    it held, and under another name `add` refuses `member-path-registered`.
    It is what `family.py remove` leaves of two sections for one path
    (#360), and a section for `Members/Atlas` is one `add` commits beside
    the member's own, since git compares the two exactly: that one is still
    a finding, and says which of three it is (`_variant_case`). Only the
    section that is a second one beside the member's own is taken out. A
    section with no path gives none and is not one of these.

    The remedy is #300's, by key, every key the section holds, one command
    to a line: `--remove-section` cannot address a section whose name holds
    `]`, and a key left behind is inherited.

    A section at the path of a gitlink whose finding says to `git rm` it
    prints no command: that `git rm` takes the section out too, and a
    `--unset-all` run after it exits 5, the key being gone. A gitlink whose
    removal is staged (`removed`, #681) prints no `git rm`, so its section,
    which `git rm --cached` leaves, keeps its own commands. Where two
    sections give the path (`gitmodules-path-twice`) it takes out only the
    one git reads for it, the last in the file, so each of those keeps its
    own commands.

    A SECTION AT THE PATH OF A GITLINK OUTSIDE `members/` (#878), which no
    row can name, and which the index holds, prints the `git rm --cached`
    that takes the gitlink out first, and the commit, then its own lines
    (`_gitlink_out_first`): its lines alone took out the section and left
    the gitlink, which no section then gave, and the gate passed it while
    a plain clone's `git submodule update --init` stopped there. Once for
    each path, by the first section that gives it: the `git rm` typed
    again fails. A gitlink whose removal is staged prints none, as above.
    After a finding whose lines write `.gitmodules`, a value's or an
    earlier section's (`edited`), the `git rm` comes after `git add --
    .gitmodules`, which it needs (`_stage_first`). Each finding that
    prints lines is recorded as a write (`Report.wrote`), so a staged
    removal's finding after it puts no file back over them (lane 1's
    SHOULD 1 on #889).

    What a section in another case says is `_variant_advice`'s, and the
    rest of each remedy is `_section_out`'s, after `_gitlink_out_first`'s
    `git rm` where it prints one, so this stays within S3776's limit
    (rv882's SHOULD 3 on #882).
    """
    holds = {keys["path"] for keys in sections.values() if "path" in keys}
    given = Counter(keys["path"] for keys in sections.values()
                    if "path" in keys)
    taken: set[str] = set()
    edited = "gitmodules-value-refused" in report.codes
    for name, keys in sections.items():
        path = keys.get("path")
        if path is None or path in named:
            continue
        said = _section_unnamed_said(name, keys)
        variant = _case_variant(path, named)
        if variant is not None:
            kind = _variant_case(path, variant[0], variant[1], holds)
            if kind != STRAY:
                report.finding("gitmodules-path-unnamed",
                               said + _variant_advice(kind, path, *variant,
                                                      "section"))
                continue
            said += _variant_said(*variant) + _section_out(
                name, keys, "Take", f"then commit {GITMODULES}")
        elif (path in gitlinks and path not in removed and given[path] == 1
              and _in_members(path)):
            report.finding(
                "gitmodules-path-unnamed",
                f"{said}{SECTION_ROW_BACK} Otherwise the git rm printed above "
                f"for the gitlink at {path} takes this section out too, so no "
                "command is printed here.")
            continue
        else:
            said += SECTION_ROW_BACK + _gitlink_out_first(
                root, name, keys, gitlinks, removed, taken, edited)
        report.finding("gitmodules-path-unnamed", said)
        edited = report.wrote = True


#: What `gitmodules-path-unnamed` says of a section no row names, in no
#: case, before what it says to do.
SECTION_ROW_BACK = (" If its row was deleted or its path: edited by hand, put "
                    "the row back as git last had it.")


def _section_unnamed_said(name: str, keys: dict[str, str]) -> str:
    """What `gitmodules-path-unnamed` says first of the section `name`,
    which gives `keys["path"]` and no row names (#361)."""
    url = f"url {keys['url']}" if "url" in keys else "no url"
    return (f'{GITMODULES} gives the path {keys["path"]} to the submodule '
            f'named "{name}" ({url}), and no row of members: names that '
            "path, so nothing pins what it registers, and the next "
            "family.py add of its name or its path meets it.")


def _section_out(name: str, keys: dict[str, str], lead: str, then: str,
                 line: str = "") -> str:
    """The end of `gitmodules-path-unnamed`'s text, which takes the section
    `name` out by key (#300), every key it holds (`keys`), after `lead`,
    ending `then`, with `line`, a `git rm` printed first, before those
    lines."""
    removal = "".join(
        f"\n    git config -f {GITMODULES} --unset-all "
        f"{shlex.quote(f'submodule.{name}.{key}')}" for key in keys)
    return (f" {lead} the section out by hand, in a POSIX shell, every key "
            "it holds, so a submodule later given its name inherits none of "
            f"them, {then}:{line}{removal}")


def _gitlink_out_first(root: Path, name: str, keys: dict[str, str],
                       gitlinks: dict[str, str], removed: frozenset[str],
                       taken: set[str], edited: bool) -> str:
    """The rest of `gitmodules-path-unnamed`'s text for the section `name`,
    no row naming its path in any case, after what it says of the row:
    where that path (`keys["path"]`) is a gitlink outside `members/`
    (#878), the `git rm --cached` that takes the gitlink out first, then
    the section's own lines (`_section_out`), and elsewhere those lines
    alone, after "Otherwise".

    THE GITLINK GOES FIRST, out of the index alone, with `git rm --cached`,
    which touches no file and leaves the section, and the commit, as
    `member-gitlink-unnamed` takes out a second path to a member; `-f`
    where git refuses it without, with what `-f` does (`_forced`,
    `FORCED_SAID`, #839). Taken out alone, the section left a gitlink no
    section gives (`gitlink-unnamed`), at which a plain clone's `git
    submodule update --init` stops (`No url found for submodule path`,
    exit 128) before it checks out any member, and `git submodule status`
    exits 128 (`no submodule mapping found`). It ends as the section's
    finding does, `then commit .gitmodules`, but where HEAD's `.gitmodules`
    holds no section of its name, as after a `git submodule add` not
    committed: staged, the file is HEAD's again, and nothing of it is
    left to commit.

    `git add -- .gitmodules` COMES FIRST where `edited`, where lines
    printed before it may leave the file with changes not staged (a
    `gitmodules-value-refused` finding's, an earlier unnamed section's),
    or where it holds some as it stands (`_stage_first`): git takes no
    gitlink out of the index then, and the `git rm` exited 128.

    No `git rm` for a path in `members/`, whose gitlink has a finding of
    its own (`member-gitlink-unnamed`), for one that is no gitlink, and one
    whose removal is staged (`removed`), where a `git rm` fails (`pathspec
    ... did not match`), and for one an earlier section's finding took out
    (`taken`): the `git rm` typed again fails there too. A path it prints
    one for is added to `taken`."""
    path = keys["path"]
    if (path not in gitlinks or path in removed or _in_members(path)
            or path in taken):
        return _section_out(name, keys, "Otherwise take",
                            f"then commit {GITMODULES}")
    taken.add(path)
    head = _forced(root, path, gitlinks[path])
    in_head = _head_gitmodules(root)
    then = (f"then commit {GITMODULES}"
            if in_head is not None and name in in_head[1] else
            f"then stage {GITMODULES}: HEAD's holds no section of that name, "
            "so nothing of it is left to commit")
    stage = _stage_first(root, edited)
    nth = "the second line" if stage else "the first line"
    return (" Otherwise take its gitlink out first, since a gitlink no "
            "section gives stops a plain clone's git submodule update --init "
            "(No url found for submodule path, exit 128) before it checks out "
            "any member: " + (STAGE_SAID if stage else "")
            + f"take it out of the index alone, which touches no file, with "
            f"{nth}"
            + _forced_said(head, nth, _held_if_forced(root, path, head)) + "."
            + _section_out(name, keys, "Then, with the lines after it, take",
                           then, (f"\n    {STAGE_LINE}" if stage else "")
                           + f"\n    {_cached_removal(path, head)}"))


def _section_lines(path: str, repository,
                   sections: dict[str, dict[str, str]]) -> str:
    """The lines that write the `.gitmodules` section of the gitlink at
    `path` as `family.py add` writes it, each on an indented line of its
    own: named after its path, with the url it gives a member,
    `https://github.com/` and the row's `repository:`, or `<url>` where that
    is not `<org>/<Name>`. A section of that name in `sections` (HEAD's)
    that has a url keeps it: only its path is written. What
    `member-gitmodules-absent` prints, and `member-gitlink-absent` (#681).
    """
    keys = {"path": shlex.quote(path)}
    if "url" not in sections.get(path, {}):
        keys["url"] = (
            shlex.quote(f"https://github.com/{repository}.git")
            if isinstance(repository, str)
            and QUALIFIED_RE.match(repository) else "<url>")
    return "".join(
        f"\n    git config -f {GITMODULES} "
        f"{shlex.quote(f'submodule.{path}.{key}')} {value}"
        for key, value in keys.items())


def _check_gitlinks_registered(root: Path, members: list,
                               gitlinks: dict[str, str],
                               report: Report,
                               refused: bool = False) -> set[str]:
    """Every row's gitlink is at a path a section of HEAD's `.gitmodules`
    gives — the `member-gitmodules-absent` finding (#611, #407's decision
    3). Returns the paths it was made for, of which `_check_member` asks no
    checkout that is not there.

    A recursive clone checks a gitlink out only where a section gives its
    path, so a gitlink with none is left empty in every clone, by CI and by
    `make bootstrap` there, whose `git submodule update` exits 0 and checks
    nothing out. The holder the commit was made in keeps its checkout, and
    its git config the registration, so every other check here passed it:
    `family.py remove` committed a `.gitmodules` the work tree had lost
    (#407) and the gate said `family ok`.

    HEAD's file (`_head_gitmodules`), and the rows that `_check_member`
    reads at their path: one whose `path:` is not `members/<project>` is
    `member-path`'s, and one with no gitlink there is
    `member-gitlink-absent`'s (`gitlinks`, read as `recorded_gitlink` reads
    one). A holder with no members holds no gitlink and is asked nothing.
    THREE SOURCES: the gitlinks from the index first, the rows from the
    work tree's `family.yaml`, and the sections from HEAD alone, as #407's
    decision 3 has it, so a `.gitmodules` staged and not committed counts
    for nothing until it is committed (the module docstring gives the three
    cases).

    The remedy writes the section as `family.py add` writes it
    (`_section_lines`).

    A SECTION WITH NO URL is `member-gitmodules-url-absent`, made here for
    the same rows from the same file, and returned with them (#762, rv648's
    U1): one section gives the path and no url, so in a plain clone `git
    submodule update --init` dies there (`No url found for submodule
    path`, exit 128) before it checks out any member, and no mode named it.
    A path more than one section gives is `gitmodules-path-twice`'s.

    WHERE THE WORK TREE'S FILE IS GONE FROM DISK, the first of these
    findings puts it back first (`_gitmodules_put_back`), and no other
    does, nor any where `.gitmodules` gives a value git dies on
    (`refused`), whose `gitmodules-value-refused` puts HEAD's back first
    (#768): `git config -f` makes a file of the lines it is given, so
    `member-gitmodules-absent`'s lines, staged and committed, dropped every
    other section (rv820's review, comment 6237354577 on #839), and a
    second `member-gitmodules-url-absent`'s put the file back over the url
    the first had written (#839). Nor where the wrong-case move printed
    before them put it back (`Report.put_back`, #879's C1), whose write the
    url-absent finding's put-back undid; the one these print is recorded
    there, for `member-gitlink-removal-staged` after them (#879's C2), and
    so is each write, on disk or not (`Report.wrote`): that finding's
    `git checkout HEAD -- .gitmodules` took a section these wrote out
    again (lane 1's SHOULD 1 on #889).
    """
    head = _head_gitmodules(root)
    if head is None:
        return set()
    held, sections = head
    given = Counter(keys["path"] for keys in sections.values()
                    if "path" in keys)
    spec, line, whose = (("", "", "") if refused or report.put_back
                         else _gitmodules_put_back(root))
    back = (line, whose)
    unregistered: set[str] = set()
    for row, _, path in _rows_at_their_paths(members):
        if path not in gitlinks:
            continue
        if path in given:
            if given[path] == 1 and _url_absent(root, path, gitlinks[path],
                                                row, sections, report, back):
                unregistered.add(path)
                report.put_back = report.put_back or spec
                report.wrote = True
                back = ("", "")
            continue
        unregistered.add(path)
        report.finding("member-gitmodules-absent", _absent_said(
            path, gitlinks[path], held,
            _section_lines(path, row.get("repository"), sections), back))
        report.put_back = report.put_back or spec
        report.wrote = True
        back = ("", "")
    return unregistered


def _absent_said(path: str, commit: str, held: bool, lines: str,
                 back: tuple[str, str]) -> str:
    """`member-gitmodules-absent`'s text for the gitlink at `path`, at
    `commit`, where `held` says whether HEAD holds a `.gitmodules`, with
    `lines` (`_section_lines`) under it, after the line that puts the work
    tree's file back where `back` gives one (`_back_first`, #839)."""
    return (
        f"{path} is a gitlink at {commit} that a row of members: names, and "
        + (f"no section of HEAD's {GITMODULES} gives that path" if held
           else f"HEAD holds no {GITMODULES}")
        + ", so a recursive clone of this holder checks out nothing there, "
        "and neither does make bootstrap in that clone, whatever checkout "
        "this holder has of it. Write its section back by hand, in a POSIX "
        "shell, as family.py add writes one, then stage and commit "
        f"{GITMODULES}{_back_first(back)}{lines}")


def _back_first(back: tuple[str, str]) -> str:
    """The end of the sentence before a finding's `git config -f` lines,
    with the line that puts the work tree's `.gitmodules` back first where
    `back` is `(that line, whose file it puts back)`, or a colon where it is
    empty (#762, #839)."""
    put_back, whose = back
    if not put_back:
        return ":"
    return (f", which is gone from the work tree: the first line puts back "
            f"{whose}, so that every other section stays:\n    {put_back}")


def _url_absent(root: Path, path: str, commit: str, row: dict,
                sections: dict[str, dict[str, str]], report: Report,
                back: tuple[str, str]) -> bool:
    """`member-gitmodules-url-absent` where the one section of HEAD's
    `.gitmodules` (`sections`) that gives `path` gives no url (#762); True
    where it was made. The url written is the one `family.py add` writes,
    `https://github.com/` and the row's `repository:`, or `<url>` where
    that is not `<org>/<Name>`, as `_section_lines` writes it. Where the
    work tree's file is gone from disk, `back` is the line before it that
    puts that back (`_gitmodules_put_back`), since `git config -f` would
    make a file of that one key, and staged it dropped every other
    section, and empty where an earlier finding put it back (#839)."""
    name = next(name for name, keys in sections.items()
                if keys.get("path") == path)
    if "url" in sections[name]:
        return False
    repository = row.get("repository")
    url = (shlex.quote(f"https://github.com/{repository}.git")
           if isinstance(repository, str) and QUALIFIED_RE.match(repository)
           else "<url>")
    report.finding(
        "member-gitmodules-url-absent",
        f"{path} is a gitlink at {commit} that a row of members: names, and "
        f"the section of HEAD's {GITMODULES} that gives that path, "
        f'"{name}", gives no url, so in a plain clone of this holder git '
        "submodule update --init stops there (No url found for submodule "
        "path, exit 128) before it checks out any member, as make "
        "bootstrap's does, and a recursive clone checks out nothing there. "
        "Write its url back by hand, in a POSIX shell, as family.py add "
        f"writes one, then stage and commit {GITMODULES}{_back_first(back)}"
        f"\n    git config -f {GITMODULES} "
        f"{shlex.quote(f'submodule.{name}.url')} {url}")
    return True


def _check_removals_staged(root: Path, members: list,
                           gitlinks: dict[str, str], removed: frozenset[str],
                           worktree: dict[str, dict[str, str]],
                           report: Report) -> set[str]:
    """A row's own gitlink whose removal is staged and not committed — the
    `member-gitlink-removal-staged` finding (#762, w681's candidate 2).
    Returns the paths it was made for, of which `_check_member` asks no
    checkout that is not there.

    HEAD records the gitlink and the index holds nothing at its path
    (`removed`, `_staged_removals`), so `recorded_gitlink` answers from
    HEAD and the gate said `family ok`, members checked or not, while the
    next commit un-registers the member under its row, and the gate then
    refuses `member-gitlink-absent`: CI was the first to see it. It reads
    the index first because the index is what the next commit records, and
    that holds here too; a finding, not a refusal, since every question
    the row asks can still be asked of HEAD. A clean checkout, CI's, never
    holds one.

    BOTH WAYS OUT ARE TYPED (rv762's probes, git 2.43): to stay, `git reset
    -q -- <path>` puts the gitlink back as HEAD records it; where a plain
    `git rm` also took its section out of the work tree's `.gitmodules`
    (`worktree`), the lines `_section_back` gives put that back, and
    where it took the checkout, `git submodule update --init --recursive --
    <path>` checks it out again, since that update dies `No url found`
    while the section is gone. To go, the same, then `family.py remove`,
    which takes the row, the gitlink and the section out in one commit and
    refuses a work tree's `.gitmodules` that is not the index's
    (`gitmodules-unstaged`) and a staged removal alike, on a branch, as the
    duplicate-id remedy names it. HEAD's `.gitmodules` is read once: the
    rows whose removal is staged and whose path it gives, `wanted`, for
    the first put-back of a file gone from disk (lane 1's MUST 1 on #889),
    and every key it gives a value git dies on, `refused`
    (`_values_refused`), which a section written back key by key leaves
    out. The checkouts it names are `_moved_checkouts`'s.
    """
    if not removed:
        return set()
    head = _head_listed(root)
    listed = head[1] if head is not None else b""
    sections = _sections_listed(listed)
    given = {keys["path"] for keys in sections.values() if "path" in keys}
    rows = [(row, project, path)
            for row, project, path in _rows_at_their_paths(members)
            if path in removed]
    wanted = {path for _, _, path in rows if path in given}
    refused = set(_values_refused(root, _submodule_entries(listed)))
    for row, project, path in rows:
        lines = _put_back_lines(root, path, _section_back(
            root, path, sections, worktree, report, (wanted, refused)))
        report.finding("member-gitlink-removal-staged", _removal_staged_said(
            root, row, project, path, gitlinks[path], lines,
            _moved_checkouts(root, path, gitlinks, sections)))
    return {path for _, _, path in rows}


def _rows_at_their_paths(members: list) -> Iterator[tuple[dict, str, str]]:
    """`(row, project, path)` for each row of `members:` whose project is a
    name and whose `path:` is its own, `members/<project>`, or none, once
    for each path: the rows `_check_gitlinks_registered` and
    `_check_removals_staged` ask, which `_check_member` reads at that path.
    A row whose `path:` is another is `member-path`'s (#611, #762)."""
    seen: set[str] = set()
    for row in members:
        project = row.get("project") if isinstance(row, dict) else None
        if not isinstance(project, str) or not project:
            continue
        path = f"{DEFAULT_MEMBERS_DIR}/{project}"
        if str(row.get("path") or path) == path and path not in seen:
            seen.add(path)
            yield row, project, path


def _moved_checkouts(root: Path, path: str, gitlinks: dict[str, str],
                     sections: dict[str, dict[str, str]]
                     ) -> tuple[list[str], list[str]]:
    """`(moved, clones)`, what `member-gitlink-removal-staged` names
    (`_moved_said`) of the row's gitlink at `path`, where no checkout is
    there, else two empty lists.

    `moved`: each other gitlink the index holds whose `.git` FILE names
    the member's own store (`_store`, `_names_store`), the checkout `git
    mv` moved, whose store the update the finding prints last points back
    at `path` (#879's C4).
    Any path, not a case variant alone: after `git mv members/<P>
    renamed-1`, typed as printed, `renamed-1` was left untracked, named
    by no finding, with a file only it held unseen (lane 1's SHOULD 3 on
    #889).

    `clones`: each case variant of `path` the index holds a gitlink at
    whose `.git` is a DIRECTORY, a clone of its own, which holds its
    commits there and nowhere else. It was said to be the checkout `git
    mv` moved, to delete by hand, which lost a commit only it held (lane
    1's SHOULD 2 on #889).

    NONE IS AT `path` ONLY WHERE NOTHING IS (`_checkout_gone`, ENOENT
    alone), and a `.git` this user cannot search, at `path` or at another
    gitlink, is `member-unreadable` (#430): on Python 3.14 a checkout
    under a folder it cannot search was none, or named nothing, so the
    checkout `git mv` moved went unnamed again."""
    if not _checkout_gone(root, path):
        return [], []
    store = _store(root, path, sections)
    others = [other for other in sorted(gitlinks) if other != path]
    moved = [other for other in others
             if _names_store(root, other, store)]
    clones = [other for other in others
              if other.casefold() == path.casefold()
              and _asked(root / other / ".git", stat.S_ISDIR,
                         MEMBER_UNREADABLE, f"{other}/.git")]
    return moved, clones


def _store(root: Path, path: str,
           sections: dict[str, dict[str, str]]) -> str:
    """Where this holder keeps the store of the submodule at `path`, as git
    does, `modules/<name>` in its git directory, resolved and with its case
    normalised for `_names_store`, or nothing where git cannot name that
    directory: `<name>` the section of HEAD's `.gitmodules` (`sections`)
    that gives the path, the last, as git reads it, else the path, as `git
    submodule add` names one (lane 1's SHOULD 3 on #889)."""
    names = [name for name, keys in sections.items()
             if keys.get("path") == path]
    with _git_runs("this holder's git directory could not be read"):
        try:
            common = git_out(["rev-parse", "--git-common-dir"], cwd=root,
                             binary=True)
        except Refusal:
            return ""
    common_dir = root / common.decode("utf-8", "surrogateescape").strip()
    return os.path.normcase(os.path.realpath(
        common_dir / "modules" / (names[-1] if names else path)))


def _names_store(root: Path, path: str, store: str) -> bool:
    """Whether the `.git` at the gitlink path `path` is a FILE that names
    `store` (`_store`), read as git reads one: `gitdir: <path>`, trailing
    blanks stripped, the path relative to the file's directory unless it is
    absolute. One whose `stat` or read is refused is `member-unreadable`
    (#430): it was a `.git` that named no store, so the checkout `git mv`
    moved there went unnamed."""
    gitfile = root / path / ".git"
    named = f"{path}/.git"
    if not store or not _asked(gitfile, stat.S_ISREG, MEMBER_UNREADABLE,
                               named):
        return False
    try:
        text = gitfile.read_bytes().decode("utf-8", "surrogateescape")
    except OSError as exc:
        raise _unreadable(MEMBER_UNREADABLE, named, exc) from exc
    text = text.rstrip()
    if not text.startswith("gitdir: "):
        return False
    named = os.path.join(gitfile.parent, text[len("gitdir: "):])
    return os.path.normcase(os.path.realpath(named)) == store


#: What `member-gitlink-removal-staged` says its `git checkout HEAD --
#: .gitmodules` puts back (#762).
SECTION_TAKEN = (f"the {GITMODULES} section git rm took out, putting that "
                 "file back as HEAD has it and dropping any other change to "
                 "it")


def _section_back(root: Path, path: str,
                  sections: dict[str, dict[str, str]],
                  worktree: dict[str, dict[str, str]],
                  report: Report,
                  asked: tuple[set[str], set[tuple[str, str]]]
                  ) -> list[tuple[list[str], str]]:
    """The lines `member-gitlink-removal-staged` prints for `.gitmodules`,
    with what they put back, where HEAD's (`sections`) gives `path` (#762):
    none where the work tree's (`worktree`) gives it, nor where the file a
    finding before put back in place of one gone from disk does
    (`Report.put_back`), and else `git checkout HEAD -- .gitmodules`, which
    puts back the section a plain `git rm` took out.

    NOTHING IS PUT BACK OVER WHAT A FINDING PRINTED BEFORE WROTE, or where
    it put the file back (`Report.wrote`, `Report.put_back`): the section
    HEAD's gives is written in key by key, as HEAD has it, but for a key
    it gives a value git dies on (`asked`'s second, which
    `gitmodules-value-refused` takes out), and the file staged
    (`_keys_back`). Where the work tree's file is gone, only a put-back
    makes a file to write into: the first finding that writes one puts it
    back and records that (#879's C1), so `Report.put_back` alone is asked
    there. A hand mount's `git rm`, counted as a write, writes nothing
    into a file that is gone, and the key-by-key lines then made a file of
    one section, which the commit recorded (lane 1's MUST 2 on #889). The
    `git checkout HEAD` took
    out again a section a finding before had written, where the work
    tree's file was gone (#879's C2, rv876's P5d) and where it was on disk
    (lane 1's SHOULD 1 on #889); and written in alone, the section stayed
    out of the index's file, which the commit records, so the commit
    dropped it (lane 1's MUST 1, its P5).

    WHERE THE WORK TREE'S FILE IS GONE FROM DISK and no finding before put
    it back, this one does, and records that: from where git reads it
    (`_gitmodules_put_back`) where that file gives every path `asked`'s
    first holds, each row whose removal is staged and whose path HEAD's
    gives, so that
    a deletion of `.gitmodules` staged beside the removal is undone too,
    with nothing left to commit, and else from HEAD (`SECTION_TAKEN`). Put
    back from the index's, which a plain `git rm` of a second row had
    taken that row's section out of, the second row's finding wrote it in
    key by key and the commit dropped it (lane 1's MUST 1, its P4)."""
    given = {keys["path"] for keys in sections.values() if "path" in keys}
    if path not in given:
        return []
    on_disk = os.path.lexists(root / GITMODULES)
    if on_disk and any(keys.get("path") == path for keys in worktree.values()):
        return []
    if report.put_back and path in _blob_paths(root, report.put_back):
        return []
    wanted, refused = asked
    if report.put_back or (on_disk and report.wrote):
        report.wrote = True
        return _keys_back(path, sections, on_disk, refused)
    if on_disk:
        return [([f"git checkout HEAD -- {GITMODULES}"], SECTION_TAKEN)]
    spec, line, whose = _gitmodules_put_back(root)
    if wanted <= _blob_paths(root, spec):
        report.put_back = spec
        return [([line], f"the {GITMODULES} gone from the work tree, from "
                 f"{whose}")]
    report.put_back = f"HEAD:{GITMODULES}"
    return [([f"git checkout HEAD -- {GITMODULES}"], SECTION_TAKEN)]


def _keys_back(path: str, sections: dict[str, dict[str, str]],
               on_disk: bool, refused: set[tuple[str, str]]
               ) -> list[tuple[list[str], str]]:
    """`_section_back`'s lines after a finding that wrote the work tree's
    `.gitmodules` or put it back: the section of HEAD's (`sections`) that
    gives `path`, the last, as git reads it, written in key by key as HEAD
    has it, into the work tree's file as the lines above leave it
    (`on_disk`) or the file a line above put back, but for a key HEAD's
    gives a value git dies on (`refused`), which written back would be
    `gitmodules-value-refused` again; then `git add -- .gitmodules`
    (`STAGE_LINE`): the commit records the index's file, and a section
    written into the work tree's alone stayed out of it (lane 1's MUST 1
    on #889)."""
    name = [name for name, keys in sections.items()
            if keys.get("path") == path][-1]
    into = ("in the work tree's file, as the lines above leave it" if on_disk
            else "in the file a line above put back")
    return [([f"git config -f {GITMODULES} "
              f"{shlex.quote(f'submodule.{name}.{key}')} "
              f"{shlex.quote(value)}"
              for key, value in sections[name].items()
              if (name, key) not in refused],
             f"the {GITMODULES} section git rm took out, key by key as HEAD "
             f"has it, {into}"),
            ([STAGE_LINE], f"that section in the index, staging {GITMODULES} "
             f"whole, {STAGE_TOO}")]


def _blob_paths(root: Path, spec: str) -> set[str]:
    """Every path a section of the `.gitmodules` git names `spec` gives
    (`:.gitmodules`, the index's, or `HEAD:.gitmodules`), read as
    `_gitmodules_sections` reads the work tree's; none where git cannot
    read it (#879)."""
    with _git_runs(f"{spec} could not be read as git reads it"):
        try:
            listed = git_out(["config", "-z", "--blob", spec, "--list"],
                             cwd=root, binary=True)
        except Refusal:
            return set()
    return {keys["path"] for keys in _sections_listed(listed).values()
            if "path" in keys}


def _put_back_lines(root: Path, path: str,
                    section: list[tuple[list[str], str]]
                    ) -> list[tuple[list[str], str]]:
    """The lines `member-gitlink-removal-staged` prints that keep the member
    at `path`, each group with what it puts back (#762): its gitlink;
    `section`, the lines for `.gitmodules` (`_section_back`, #879); and
    its checkout, where none is there: where NOTHING is there
    (`_checkout_gone`, ENOENT alone), and a `.git` this user cannot search
    is `member-unreadable` (#430). On Python 3.14 that checkout was none,
    and the update printed for it failed (`could not open '<path>/.git'
    for writing`) on the checkout that is there."""
    lines = [([f"git reset -q -- {shlex.quote(path)}"], "its gitlink"),
             *section]
    if _checkout_gone(root, path):
        lines.append((["git submodule update --init --recursive -- "
                       f"{shlex.quote(path)}"], "its checkout"))
    return lines


#: What `member-gitlink-removal-staged` says after its lines where they
#: stage `.gitmodules` (`_keys_back`), in place of "and nothing is left to
#: commit": the file holds what the findings above write (lane 1's MUST 1
#: on #889).
STAGED_BACK = (f": commit {GITMODULES} then, with what the lines above "
               "write in it, and nothing else is left to commit.")


def _removal_staged_said(root: Path, row: dict, project: str, path: str,
                         commit: str, lines: list[tuple[list[str], str]],
                         found: tuple[list[str], list[str]]) -> str:
    """`member-gitlink-removal-staged`'s text for the row naming `project`,
    whose gitlink at `path` is at `commit` in HEAD, with `lines`
    (`_put_back_lines`) below it (#762), and what it says of the checkouts
    `_moved_checkouts` `found` (`_moved_said`, #879's C4). Where the lines
    stage `.gitmodules`, it says to commit that (`STAGED_BACK`)."""
    member_id = str(row.get("id") or project)
    remove = (f"{PYTHON} scripts/family.py remove --family-root "
              f"{shlex.quote(str(root))} --member {shlex.quote(project)}")
    commands = "\n    ".join(line for group, _ in lines for line in group)
    staged = any(group == [STAGE_LINE] for group, _ in lines)
    return (
        f"{path} is a gitlink at {commit} that a row of members: names and "
        "HEAD records, and the index holds nothing at that path: its removal "
        "is staged and not committed, so the next commit un-registers the "
        "member under its row, and this gate then refuses "
        "member-gitlink-absent. If the member is to stay, "
        + _put_back_said(lines)
        + (STAGED_BACK if staged else ", and nothing is left to commit.")
        + _moved_said(path, *found)
        + " If it is to go, put it back the "
        "same way, then take it out with family.py remove, from a checkout "
        "of openRepoShape, which takes its row, its gitlink and its section "
        "out in one commit, on a branch other than the holder's tracking "
        "branch, which it refuses "
        f"(`{_switch_line(root, 'remove', member_id)}` makes one): "
        f"`{remove}`. {BRANCH_LEFT}\n    {commands}")


def _moved_said(path: str, moved: list[str], clones: list[str]) -> str:
    """What `member-gitlink-removal-staged` says, before its last line, the
    update, of each checkout of the member `git mv` moved off `path`
    (`moved`) and each clone of its own at a case variant of it
    (`clones`), or nothing (`_moved_checkouts`).

    THE CHECKOUT `git mv` MOVED (#879's C4): after the lines were typed as
    printed it stayed there, untracked and named nowhere, so `family.py
    add` refused one at a case variant (`family-members-dir-variant`), and
    after the update `git -C <variant> status` read `path`, so a file only
    it held went unseen. Said as `family.py add`'s closing sentences say
    it (#828, #865), and of one outside `members/` too (lane 1's SHOULD 3
    on #889).

    A CLONE OF ITS OWN, whose `.git` is a directory, holds its commits
    there and nowhere else: said as the wrong-case move says it
    (`_wrong_case_move`), to move it out whole, not to delete it (lane 1's
    SHOULD 2 on #889)."""
    said = ""
    if moved:
        refused = (", and family.py add refuses it as "
                   "family-members-dir-variant"
                   if any(other.casefold() == path.casefold()
                          for other in moved) else "")
        status = _statuses(moved)
        said += (
            f" The checkout git mv moved to {' or '.join(moved)} stays "
            f"there, untracked{refused}: its .git file names the member's "
            "store under this holder's .git/modules/ by a path relative to "
            "it, and its commits are kept there whatever becomes of the "
            "checkout, so only what is not committed is in the checkout "
            f"alone, which {status} shows. Delete it by hand once nothing "
            "only it holds is needed, before the last line: that update "
            f"points the store at {path}, after which {status} reads {path} "
            "instead.")
    if clones:
        said += (
            f" The clone at {' or '.join(clones)}, whose .git is a "
            "directory, stays there, untracked, and family.py add refuses it "
            "as family-members-dir-variant: it holds its commits there and "
            f"nowhere else, and {_unpushed(clones)} lists the ones not "
            "pushed, so move it out of the holder whole, by hand, rather "
            "than delete it.")
    return said


def _statuses(paths: list[str]) -> str:
    """`git -C <path> status`, backticked, for each of `paths`, joined by
    `or`: what shows what only a checkout holds (#681, #879)."""
    return " or ".join(f"`git -C {shlex.quote(path)} status`"
                       for path in paths)


def _unpushed(paths: list[str]) -> str:
    """`git -C <path> log --oneline HEAD --branches --not --remotes`,
    backticked, for each of `paths`, joined by `or`: what lists the
    commits a clone of its own holds that no remote does (rv681's S2,
    #879)."""
    return " or ".join(f"`git -C {shlex.quote(path)} log --oneline HEAD "
                       "--branches --not --remotes`" for path in paths)


#: How `_put_back_said` counts the lines below a finding.
ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth",
            "seventh", "eighth", "ninth", "tenth")


def _put_back_said(groups: list[tuple[list[str], str]]) -> str:
    """What the lines `member-gitlink-removal-staged` prints put back, in
    their order, the gitlink first (#762): each group of lines
    (`_put_back_lines`) with what it puts back, `the second` for one line
    and `the second to the fourth` for more (#879)."""
    if len(groups) == 1 and len(groups[0][0]) == 1:
        return f"the line below puts {groups[0][1]} back as HEAD records it"
    said, at = [], 0
    for group, what in groups:
        span = f"the {_ordinal(at)}"
        if len(group) > 1:
            span += f" to the {_ordinal(at + len(group) - 1)}"
        said.append(f"{span} {what}")
        at += len(group)
    return ("the lines below put the member back as HEAD has it: "
            + ", ".join(said))


def _ordinal(at: int) -> str:
    """`first` for the line at 0, and so on (`ORDINALS`); `<n>th` past the
    tenth (#879)."""
    return ORDINALS[at] if at < len(ORDINALS) else f"{at + 1}th"


def _init_stop_said(root: Path, sections: dict[str, dict[str, str]],
                    named: dict[str, RowPath]) -> str:
    """What `member-uninitialized` says before its update where `git
    submodule update --init` would stop at a gitlink it has no url for, or
    nothing where it would not (#762, rv648's S1, H1 and U1, and H2).

    GIT'S INIT DIES AT THE FIRST SUCH GITLINK, in index order, before it
    checks out any member (`No url found for submodule path`, exit 128), so
    the update the refusal named died the same way, at a stray case
    variant, a member mounted by hand, a section with no url, or a gitlink
    outside `members/`. Asked as the family bootstrap's `init_stop` asks it
    (#648), more simply (`_init_stopper`): of the index, the `.gitmodules`
    git's init reads and this holder's git config. Every gitlink, but where
    the config sets `submodule.active`, as a recursive clone does, only
    those a section gives a path; one whose section, the last that gives
    its path, has no url, and the config none (`submodule.<name>.url`, as
    an earlier init writes it), stops it. What bootstrap also keeps of
    git's own parser (a name or a value git ignores, a `.gitmodules` a
    merge left unmerged) is not read here; where nothing is found the plain
    remedy stands.

    THE `.gitmodules` GIT READS is the work tree's (`sections`) where it is
    on disk, and where it is gone from disk the index's, else HEAD's
    (`_gitmodules_put_back`, rv820's SHOULD 2): read from the work tree
    alone, a plain clone whose file was deleted and not staged was said to
    stop at its first row, where git's update read the index's and checked
    both members out. Where git reads the index's or HEAD's, the line that
    puts the work tree's back comes first, so that the cure keeps every
    other section, and `--no-members`, which reads the work tree's, names
    what the cure says it names.

    THE CURE IS BOOTSTRAP'S FOR THE SAME GITLINK (`cures`), word for word
    but for the path, printed as this file prints one (`_init_stop_cure`).
    """
    spec, put_back, whose = _gitmodules_put_back(root)
    with _git_runs("the gitlinks git submodule update asks could not be "
                   "listed"):
        try:
            if spec:
                sections = _sections_listed(git_out(
                    ["config", "-z", "--blob", spec, "--list"], cwd=root,
                    binary=True))
            stopper = _init_stopper(root, sections)
        except Refusal:
            return ""
    if stopper is None:
        return ""
    restore = (f"{GITMODULES} is gone from the work tree, so git reads "
               f"{whose}: `{put_back}` puts it back first, so that what "
               "follows keeps every other section. " if put_back else "")
    return (f"`git submodule update --init` stops at {stopper}, a gitlink it "
            "has no url for (No url found for submodule path, exit 128), "
            f"before it checks out any member. {restore}"
            f"{_init_stop_cure(stopper, sections, named)} Then ")


def _init_stopper(root: Path,
                  sections: dict[str, dict[str, str]]) -> str | None:
    """The gitlink `git submodule update --init` stops at, the first in
    index order, or None, as `_init_stop_said` asks it: of the index,
    `sections` (the `.gitmodules` git's init reads) and this holder's git
    config. A config git lists nothing of (`--get-regexp` exits 1) holds
    none; an index git cannot list raises `Refusal`."""
    index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    try:
        listed = git_out(["config", "-z", "--get-regexp", r"^submodule\."],
                         cwd=root, binary=True)
    except Refusal:
        listed = b""
    config = {record.decode("utf-8", "surrogateescape").partition("\n")[0]
              for record in listed.split(b"\0")}
    read = {keys["path"]: name for name, keys in sections.items()
            if "path" in keys}
    for record in index.split(b"\0"):
        meta, _, entry = record.partition(b"\t")
        if meta.split()[:1] != [GITLINK_MODE]:
            continue
        path = entry.decode("utf-8", "surrogateescape")
        name = read.get(path)
        if name is None and "submodule.active" in config:
            continue
        if name is None or ("url" not in sections[name]
                            and f"submodule.{name}.url" not in config):
            return path
    return None


def _init_stop_cure(stopper: str, sections: dict[str, dict[str, str]],
                    named: dict[str, RowPath]) -> str:
    """Bootstrap's cure (`cures`) for `stopper`, the gitlink git's init
    stops at, as `_init_stop_said` prints it: `--no-members` for a path two
    of `sections` give or a gitlink in `members/` no row names, the section
    written back for a row's own path (`named`), and `git rm --cached` for
    a gitlink outside `members/`, as `gitlink-unnamed` and
    `gitmodules-path-unnamed` name it in every mode (#878)."""
    given = Counter(keys["path"] for keys in sections.values()
                    if "path" in keys)
    if given[stopper] > 1:
        return (f"`{PYTHON} scripts/validate-family.py --no-members` names "
                f"each path more than one section of {GITMODULES} gives, and "
                "how to take the others out.")
    if stopper in named:
        return (f"Write the section of {GITMODULES} for {stopper} back as "
                "`family.py add` writes one, with its path and url, and "
                f"commit {GITMODULES}.")
    if _in_members(stopper):
        return (f"`{PYTHON} scripts/validate-family.py --no-members` names "
                f"each gitlink in {DEFAULT_MEMBERS_DIR}/ that no row names, "
                "and the commit that cures it.")
    removal = shlex.join(["git", "rm", "--cached", "--", stopper])
    return (f"No row names {stopper} and no clone can check it out: "
            f"`{removal}` takes its gitlink out, then commit that.")


def _check_members(root: Path, members: list, no_members: bool,
                  report: Report) -> None:
    """Every row in `members:`, or the `--no-members` skip line.

    Split from `main` for #137. Every check that needs no member checked
    out comes first, so `--no-members` asks them too: the ones that read a
    file alone, `family.yaml`'s names (#331) and ids (#206) and the paths
    `.gitmodules` gives twice (#300), then the gitlinks and sections no row
    names, which read the index and HEAD as well (#361), the gitlinks no
    section of HEAD's `.gitmodules` gives (#611) or gives a url, and a
    row's own whose removal is staged (#762).

    AND EVERY ENTRY OF `members:` THAT IS NOT A MAPPING, `member-row`
    (#864), after the names and ids: it reads `family.yaml` alone, so
    `--no-members` asks it too, and the loop below skips the entry.

    THEN EVERY ROW'S GITLINK, AND ONLY THEN ANY ROW'S CHECKOUT (#648). Each
    row used to be asked whole before the next was asked at all, so in a
    plain clone of a holder whose later row's gitlink is recorded only in
    another case, where `git submodule update --init --recursive` dies at
    that gitlink (`No url found for submodule path`, exit 128) before it
    checks out any member, an earlier row was refused
    `member-uninitialized`, naming that same update, and the later row's
    `member-gitlink-absent`, which names the move that cures both, was
    never reached. Where git's init would stop at a gitlink it has no url
    for, `member-uninitialized` says so before its update, with the cure
    (`_init_stop_said`, #762).

    A VALUE GIT DIES ON IN `.gitmodules` (#768) is asked first of the
    checks that read that file, and where the work tree's file gives one,
    `gitmodules-path-twice` and `gitmodules-path-unnamed` read nothing from
    it, as git reads nothing: no command they would print for a section
    then meets one of its own lines. Where
    either file gives one, git checks out no member, so a member that is
    not checked out is asked nothing, as one `member-gitmodules-absent`
    names: the finding fails the run, where `member-uninitialized` named
    the update that dies, and `_init_stop_said`, which would name a stop
    git never reaches there, is not asked.
    """
    _check_member_names_unique(members, report)
    _check_member_ids_unique(root, members, report)
    # A ROW THAT IS NOT A MAPPING reads `family.yaml` alone too, so it is
    # found here, in both modes (#864): found only in the loop below, past
    # the `--no-members` return, it was counted as a member there, and the
    # rows beside a `5` were `family ok`, exit 0.
    for row in members:
        if not isinstance(row, dict):
            report.finding("member-row",
                           f"a member is not a mapping: {row!r}")
    sections = _gitmodules_sections(root)
    as_read = sections
    refused_here, refused = _check_gitmodules_values(root, members, report)
    if refused_here:
        sections = {}
    _check_gitmodules_paths(sections, report)
    named = _row_paths(members)
    gitlinks = _member_gitlinks(root)
    removed = _staged_removals(root, gitlinks)
    _check_gitlinks_named(root, gitlinks, named, removed, report)
    _check_gitlinks_elsewhere(root, gitlinks, named, removed, report)
    _check_gitmodules_named(root, sections, gitlinks, named, removed, report)
    unregistered = _check_gitlinks_registered(root, members, gitlinks,
                                              report, refused)
    unregistered |= _check_removals_staged(root, members, gitlinks, removed,
                                           as_read, report)
    if no_members:
        print(f"  --  {len(members)} member(s) SKIPPED (--no-members): "
              "their gitlinks, digests and project ids are not checked "
              "here")
        return
    seen: dict[str, bool] = {}
    gitlinked: list[Gitlinked] = []
    for row in members:
        if not isinstance(row, dict):
            continue
        asked = _check_member(root, row, seen, report, gitlinks, removed)
        if asked is not None:
            gitlinked.append(asked)
    stop = (_init_stop_said(root, sections, named)
            if not refused and any(
                asked.path not in unregistered
                and not _checked_out(root / asked.path, asked.path)
                for asked in gitlinked) else "")
    for asked in gitlinked:
        _check_member_checkout(root, asked, report,
                               set(gitlinks) if refused else unregistered,
                               stop)
    if not members:
        report.note("no members yet: a family with none is empty, not "
                    "wrong")


def _run_checks(args: argparse.Namespace,
                report: Report) -> tuple[Path, dict, list]:
    """Everything `main` used to run inside its own single `try`.

    Split from `main` for #137: lifting this whole body out from under
    `main`'s `try` removes a level of nesting from every branch inside it,
    which is where most of `main`'s cognitive complexity was. Raises
    `Refusal` exactly as `main` always caught it; returns `(root, manifest,
    members)`, which `main` still needs afterward for the final summary
    line, whose THE LOCKSTEP RULE names the holder (#610).
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    manifest_path = root / MANIFEST
    # A `family.yaml` whose `stat` is refused (a link into a folder this
    # user cannot search) is refused by name (#430): on Python 3.14 it was
    # `family-manifest-missing`, whose remedy makes a family that is here.
    if not _asked(manifest_path, stat.S_ISREG, "family-manifest-unreadable",
                  MANIFEST):
        raise Refusal(
            "family-manifest-missing",
            f"{manifest_path} does not exist. A family holder declares "
            f"itself in `{MANIFEST}`; a repository without one is not a "
            "family and does not run this validator.",
            f"Remediation: `{PYTHON} scripts/family.py init --org <org> "
            "--family <Name>` creates one. An ordinary project runs "
            "`validate-manifest.py` instead.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{manifest_path}: not a mapping")
    policy_path = args.policy or (root / "contracts" /
                                  "repository-naming.yaml")
    policy = NamingPolicy.load(policy_path)
    if not args.pins:
        _check_envelope(manifest, policy, report)

    members = manifest.get("members")
    if members is None:
        members = []
    if not isinstance(members, list):
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: `members:` is {members!r}, "
                      "expected a list")
    _check_members(root, members, args.no_members, report)
    if not args.pins:
        _check_shape_pin(root, manifest, report)
    return root, manifest, members


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None,
                        help="the family root (default: the enclosing "
                             "repository)")
    parser.add_argument("--policy", type=Path, default=None)
    parser.add_argument("--pins", action="store_true",
                        help="the member lockstep check alone: gitlink, "
                             "digest and identity, with no envelope and no "
                             "shape-copy check (what `make pins` runs)")
    parser.add_argument("--no-members", action="store_true",
                        help="the envelope and the shape copies alone, "
                             "skipping every member. The complement of "
                             "--pins, and what CI runs when the members could "
                             "not be checked out: the checks that do not need "
                             "them still run, and the ones that do are "
                             "skipped out loud rather than passing on an "
                             "unreadable surface.")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.pins and args.no_members:
        print("REFUSED family-nothing-to-check: --pins and --no-members are "
              "complements; together they ask for nothing.\n"
              "Remediation: pass one, or neither.", file=sys.stderr)
        return 2

    report = Report()
    try:
        root, manifest, members = _run_checks(args, report)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.quiet:
        for note in report.notes:
            print(note)
    for finding in report.findings:
        print(finding, file=sys.stderr)
    if report.findings:
        # THE LOCKSTEP RULE ONLY WHERE IT APPLIES (#539): a lone
        # `shape-copy-drift` or `member-duplicate-id` is no gitlink moved
        # alone.
        rule = any(code in LOCKSTEP_CODES for code in report.codes)
        print(f"\n{len(report.findings)} finding(s) in {MANIFEST}."
              + (f" {_lockstep(root)}" if rule else ""), file=sys.stderr)
        return 1
    print(f"family ok: {manifest.get('name')} ({manifest.get('id')}), "
          f"{len(members)} member(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
