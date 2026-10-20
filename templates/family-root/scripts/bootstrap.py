#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The one command an engineer runs after cloning a FAMILY holder.

    git clone --recurse-submodules <family-url>
    cd <Family>
    make bootstrap          # or: python3 scripts/bootstrap.py (python on Windows)

WHAT IT DOES, in order:

  (a) FETCHES EVERY MEMBER, RECURSIVELY, WITH A CREDENTIAL IF ONE IS THERE.
      A member is an assembly root that itself mounts two legs, so `--init
      --recursive` has to reach three repositories deep — and in most
      organisations all of them are PRIVATE. This resolves the same
      credentials the `validate` workflow does, in the same order: a GitHub
      App installation token (`SHAPE_LEGS_APP_TOKEN`, minted by whatever
      called this) first, then a `SHAPE_LEGS_TOKEN` PAT, then nothing at all.
      Whichever it finds is used ONLY through a `git -c
      url.<...>.insteadOf=<...>` rewrite for the duration of the one command,
      covering both the HTTPS and SSH spellings a submodule URL may carry,
      and of the two fetches made again where that command dies (below). It
      is never written into `.git/config`, never persisted, never printed,
      and never traced: each of those commands runs with every `GIT_TRACE*`
      variable taken out of its environment and trace2 turned off
      (`untraced`, #996), since a trace writes a command's arguments.

      With no credential this is a plain `git submodule update --init
      --recursive`, exactly as it was for a family whose members are public.
      A fetch that fails is REPORTED and does not stop the run: the members
      that did arrive are still worth bootstrapping, and a family that
      refused to do anything because one member is unreachable would be worse
      than one that says which. The advice to set a credential is given only
      where git asked for one: not where its init died at a gitlink it has
      no url for, nor where it read nothing from `.gitmodules`, both below,
      since it fetched nothing then (#839).

      Where every row's member is checked out and git's init in this
      holder died all the same, at a gitlink this holder records with no
      url or at a `.gitmodules` a merge left unmerged, git updated none of
      them, so the run fails, saying where git stopped and what cures it,
      as below, with no advice (#879). It said `family bootstrap ok`
      there, beside git's exit 128, as a run with every member checked
      out passes (#648), and gave the advice where git stopped at a
      gitlink.

      So it fails where git's update died (exit 128) past this holder's
      own records, in the two places that are told from a missing
      credential there, each asked as git asks it, in git's order, and
      never of git's words (`stopped_below`, #892):
      - at a gitlink in a member's own index that git has no url for,
        read in the member checked out at the commit this holder records
        as this holder's own index is read (`init_stop`): git's `No url
        found` there said `ok`;
      - at a member whose store still lacks the commit this holder
        records for it where git's fetch there reached the member's
        remote, by the fetch's exit code: git's own trace of the run
        says it (`fetched_in`), or, with `SHAPE_LEGS_TOKEN` or
        `SHAPE_LEGS_APP_TOKEN` set, whose rewrite a trace would write,
        so that git's update is never traced, the two fetches git's
        update makes there, made again in this process, untraced, say it
        (`refetched`, #996): its `not our ref` said `ok` too, and with a
        token set it still did, with the advice to set the token that
        was set (lane 5's SHOULD 4 on #954). A fetch git could not make,
        as for want of a credential, leaves the store as short, so the
        store alone tells nothing.
      A leg in a member is asked as a member is, and a gitlink git's
      update passes without a look, its `update` `none` or the gitlink
      inactive, is passed (lane 5's SHOULD 1 on #954). Where neither
      tells, an exit 128 is read as before, the advice and `ok` where no
      row is left not checked out but for want of a credential, and the
      run names only where git's init in this holder stopped.

      Where git's update ends on a signal, read from its exit code alone,
      `128 + N` where a git it ran died of signal N and `-N` where it was
      itself killed, the run fails naming the signal and the code, with
      no advice (`ended_on`, #998): no credential crashes git or kills
      it. It said `ok` there, with the advice, beside the 139 of git
      2.43.0 crashing on a member's own `.gitmodules`.

      "every member and leg fetched" is said only where git exited 0 AND
      every row's member is checked out (#648). A member left NOT CHECKED
      OUT where no credential would check it out is said here instead, with
      why, and fails the run (c): this holder records no gitlink at the
      row's path (a gitlink recorded only in another case, #363); no
      section of `.gitmodules` gives that path (a holder whose HEAD lost the
      file, #611); git has no url for that path, in the section it reads
      for it or in its config (a section that lost its url, or a second
      one for the path after the member's); git exited 0 and checked
      nothing out there; or git stopped at another gitlink it has no url
      for (a stray case variant, a member mounted by hand), since git's
      init dies at the first such gitlink it asks about, before it checks
      out any member. Which section and which url git reads is its own
      parser's answer, not `git config`'s (`gitmodules_sections`), from
      the work tree's file or, where the work tree has none, the index's,
      then HEAD's, and while a merge leaves `.gitmodules` unmerged in the
      index git reads none at all: every such member is said to be that,
      and the cure is the file resolved and added. Where the file gives a
      submodule a value git dies on as it reads it (`refused_value`, #768),
      every such member is said to be that, naming each key and its value,
      and the cure is the key given a value git takes or its line taken
      out; where every member was checked out the run fails all the same,
      since git updated none of them. A work tree file git cannot parse at
      all, a conflict marker or an open quote left in it, is said and
      failed on the same way, and its cure is the file mended by hand; in
      the index's or HEAD's file git reads the sections before such a line
      and goes on, and so does this (#856). Git exits 0 over the second
      where a recursive clone ran first, and 128 (`No url found for
      submodule path`) in a plain clone; a missing
      credential exits non-zero too, so what the holder records is the
      test, never git's words. The line says what cures each (`cures`):
      `validate-family.py` names the commit for the first two; for the
      fourth it prints the `git submodule update --init --checkout` that
      checks the member out whatever the clone chose. For the third and
      the last, `validate-family.py --no-members` names a path two
      sections give, or a gitlink in members/ that no row names; `git rm
      --cached` takes out one outside members/, as every mode of the
      validator says (#878); and where it is a row's own, with one section,
      the line says to write its section back. Where git read the index's
      or HEAD's file only up to a line it cannot parse, or up to a key it
      takes no value for (a bare `url` line, which `git config --list`
      takes), a section or url it did not read may be past that line, so
      for those three the line says to put that file back, mend the line
      or give the key a value or take it out, and commit it, and writes
      no section back (#856).

  (b) RUNS EACH MEMBER'S OWN `make bootstrap`. Each member is a whole project
      and knows how to bootstrap itself — it puts its legs on their
      tracking branches at their pins where that loses no commit, and says
      why where it does not; its own validators; its own
      review-authority readout. This command does not reimplement any of
      that; it walks the members `family.yaml` names and calls theirs.
      `--members-make validate` runs `make validate` instead, which is what
      the family Makefile's `validate` target uses. A member whose command
      fails is named with that command's exit code, read from make's
      `Error <code>` line, since make exits 2 for any command that fails,
      so a member's finding (1) and its refusal (2) are told apart, and
      from a failure of make's own, which prints no such line (#839). Where
      the member's make runs another, the code is the innermost command's,
      as far as make's lines tell it (`MakeErrors` says where they do not);
      make's stderr reaches the terminal through this run, and `run_make`
      says what that changes for a member (#884). Under the holder's `make
      -jN`, each member's make runs its jobs one at a time and says
      nothing of it: the jobserver of the make above this run, and the
      `-j` that comes with it, are taken out of the `MAKEFLAGS` it
      inherits (`member_make_env`, #888).

  (c) EXITS 0 unless a member's own command failed, or (a) left a member not
      checked out that no credential would check out, or found a line or a
      value in `.gitmodules` that git cannot read (#768), or found that,
      with every member checked out, git's init in this holder died at a
      gitlink this holder records with no url or at an unmerged
      `.gitmodules` (#879), or found where git's update died past this
      holder's own records, in a member's own index or at a member's
      commit no fetch brought (#892), or found that git's update ended
      on a signal (#998); an exit 128 none of those shows is no failure
      here, as (a) says. Any
      other member that is not checked out is REPORTED and skipped, not a
      failure: it is the state a missing credential leaves, and it is
      already reported in (a).
      Where (a) cannot start git, the run STOPS there, exit 2, refused
      `git-not-runnable` as `validate-family.py` refuses it (#694): each
      member's own bootstrap runs git too, so (b) would only say it again.
      And where (a) or (b) cannot ask whether a row's member is checked
      out, or whether it has a `Makefile`, because the operating system
      refused the `stat` of its `.git` or its `Makefile` (a `members/` this
      user cannot search), the run STOPS there, exit 2, refused
      `member-unreadable`, naming the path and the cure (#430). On Python
      3.14 that member read as NOT CHECKED OUT, or as having no Makefile,
      and was skipped, and the run said `family bootstrap ok`; before it,
      the run ended in a `PermissionError` traceback. A `family.yaml` whose
      `stat` is refused is `family-manifest-unreadable`, never
      `family-manifest-missing`.

THE FAMILY CONFERS NOTHING and neither does this command. It fetches, it
delegates, and it says what it could not reach.
"""

from __future__ import annotations

import argparse
import errno
import json
import os
import re
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_shape import (  # noqa: E402
    PYTHON, Refusal, escape_unencodable_stdout, find_repo_root, git_out,
    load_yaml, recorded_gitlink, spelled,
)

MANIFEST = "family.yaml"
GITMODULES = ".gitmodules"
DEFAULT_MEMBERS_DIR = "members"
#: A submodule's entry in the index, as `ls-files -s` spells its mode.
GITLINK_MODE = b"160000"

#: Why (a) left a row's member NOT CHECKED OUT where no credential would
#: check it out (#648), in the order `unfetchable` asks. `STOPPED` is
#: filled with the gitlink git's init died at (`init_stop`), and `REFUSED`
#: with each entry of `.gitmodules` git refused (`reason`). `UNREADABLE` is
#: a work tree file git cannot parse at all (#768).
UNMERGED = f"git reads no {GITMODULES} while a merge leaves it unmerged"
REFUSED = f"git cannot read {GITMODULES}: {{}}"
UNREADABLE = f"git cannot parse {GITMODULES}"
NO_GITLINK = "no gitlink is recorded at that path"
NO_SECTION = f"no section of {GITMODULES} gives that path"
NO_URL = "git has no url for that path"
EXITED_0 = "git exited 0 and checked nothing out there"
STOPPED = "git stopped at {}, a gitlink it has no url for"
#: What (a)'s line says where git updated no member, by whether `members:`
#: names any row: under "0 member(s)" it said no member was updated (lane
#: 1's NIT 5 on #889).
NONE_UPDATED = {True: "NO MEMBER UPDATED", False: "NOTHING UPDATED"}
#: What (a)'s line says where git's update died past this holder's own
#: records (`stopped_below`, #892): git updated what came before the stop
#: in its order, so it is no `NONE_UPDATED`.
UPDATE_STOPPED = "UPDATE STOPPED"
#: The exit code of git's update where it died (`die`), which `Failed to
#: recurse into submodule path` passes up from a member unchanged. A clone
#: that fails ends git's update 1, before it checks out or enters any
#: member, and a checkout that refuses is passed with `git checkout`'s own
#: 1, so no other code is asked past this holder's records
#: (`stopped_below`, #892). A code past it that a signal gives is read
#: apart (`ended_on`, #998).
GIT_DIED = 128
#: What (a)'s line says where git's update ended on a signal (`ended_on`,
#: #998): a git it ran crashed, or it was killed, and no credential does
#: either.
UPDATE_KILLED = "UPDATE KILLED"
#: The trace2 target git's update is run with where no credential is in
#: use, a directory, so each git it starts writes its events to a file of
#: its own there (`fetched_in`, #892).
TRACE_ENV = "GIT_TRACE2_EVENT"
#: How the name of each variable that asks git for a trace begins
#: (`GIT_TRACE`, `GIT_TRACE2_EVENT`, `GIT_TRACE_CURL` and the rest): each is
#: taken out of the environment of a git given the token (`untraced`, #996).
TRACE_PREFIX = "GIT_TRACE"
#: trace2's three targets, each set to `0` for a git given the token: git
#: reads a target the system or the global config names (`trace2.
#: eventTarget`) where its variable is absent or empty, and `0` turns it
#: off (`untraced`, #996).
TRACE2_OFF = ("GIT_TRACE2", "GIT_TRACE2_EVENT", "GIT_TRACE2_PERF")
#: What `git submodule` sets to `0` for every git it starts, so a url from
#: a `.gitmodules` is given no transport git gives only a person's own
#: (`user`); the fetches made again are given it too (`refetched`, #996).
FROM_USER_ENV = "GIT_PROTOCOL_FROM_USER"
#: The whys a `.gitmodules` git read only up to a line it cannot parse, or
#: up to a key with no value it stops at, may be the cause of, since what
#: it did not read is past that line (`Gitmodules.cut`, #856).
CUT_WHYS = frozenset({NO_SECTION, NO_URL, STOPPED})
#: HEAD's `.gitmodules`, as `git config --blob` is given it.
HEAD_GITMODULES = f"HEAD:{GITMODULES}"

#: What git 2.43 dies on in a `.gitmodules` it reads (#768), as
#: `parse_config` in its submodule-config.c reads a submodule's key: these
#: keys with no value (a `branch` with none crashes it, `BRANCH_READ_SINCE`),
#: and an `update` other than these four. A `shallow` must be a boolean and
#: a `fetchrecursesubmodules` a boolean or `on-demand` (`git_bool`). The
#: gate's `_values_refused`, `_git_takes_bool` and `GIT_TAKES` say the same,
#: and `tests/test_family_gitmodules_values.py` holds the two scripts to one
#: answer: a change made here is made there too (#856).
NO_VALUE_REFUSED = frozenset({"path", "url", "update", "ignore", "branch"})
#: The first git that reads a `branch` with no value as it reads a `url`
#: with none, `missing value` and `bad config line`, which dies in the work
#: tree's file and ends the reading of the index's or HEAD's, a blob: 2.43.1,
#: and 2.44.0 on its main line, by their submodule-config.c, and 2.47.1 as
#: measured. A git before it crashes reading any `.gitmodules` that gives
#: one, a blob too: 2.43.0 as measured (exit 139), and 2.42.4 and 2.39.5 by
#: their source, which has the same `xstrdup` of no value
#: (`crashes_on_branch`).
BRANCH_READ_SINCE = (2, 43, 1)
#: `git version 2.43.0`, `git version 2.45.1.windows.1`, `git version
#: 2.39.3 (Apple Git-146)`: three numbers, since the third decides here.
GIT_VERSION_RE = re.compile(r"git version (\d+)\.(\d+)\.(\d+)")
UPDATE_VALUES = ("none", "checkout", "rebase", "merge")
#: What git takes for a key whose value it refused, as (a)'s cure says it.
TAKES = {"update": "one of `none`, `checkout`, `rebase` or `merge`",
         "shallow": "a boolean, `true` or `false`",
         "fetchrecursesubmodules": "a boolean or `on-demand`",
         "ignore": "one of `untracked`, `dirty`, `all` or `none`",
         "path": "a path", "url": "a url", "branch": "a branch name"}

#: The two environment variables a leg/member credential may arrive in, in the
#: order the `validate` workflow resolves them. An App-minted installation
#: token is short-lived and per-owner; the PAT is the standing fallback.
CREDENTIAL_ENV = ("SHAPE_LEGS_APP_TOKEN", "SHAPE_LEGS_TOKEN")

#: Both spellings a submodule URL may carry, rewritten to an authenticated
#: HTTPS one for the duration of a single command.
REWRITE_TARGETS = ("https://github.com/", "git@github.com:")

#: The `OSError`s that `Path.is_file()` and `Path.exists()` answered False to
#: on Python 3.9 to 3.13 (pathlib's `_ignore_error`), because each means there
#: is nothing at the name to open: no such file, a part of the path that is
#: not a directory, a bad descriptor, a symlink loop, and Windows' "not
#: ready", "invalid name" and "cannot resolve". Every other one was raised.
_ABSENT_ERRNOS = (errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP)
_ABSENT_WINERRORS = (21, 123, 1921)

#: What a path the operating system refused for ANOTHER reason than
#: permission is told: an I/O error, a name longer than the filesystem
#: takes, a file replaced while this ran. No `chmod` puts one right.
#: `validate-pins.py`'s words for the same refusal (#712, #430).
OTHER_REASON = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. ")


def _is_a(path: Path, kind: Callable[[int], bool]) -> bool:
    """Whether `path` is there and of `kind` (`stat.S_ISREG`, `_anything`),
    raising the `OSError` of a `stat` the operating system REFUSED (#430).

    NOT `Path.is_file()` OR `Path.exists()`, whose answer depends on the
    Python. Up to 3.13 they raised a refused `stat` (`PermissionError`), and
    `make bootstrap` ended in that traceback; from 3.14 they answer False to
    ANY `OSError`. On 3.14 a member mounted under a `members/` this user
    cannot search was NOT CHECKED OUT, skipped, beside the advice to set a
    credential, and one whose `Makefile` could not be reached had none, and
    the run said `family bootstrap ok` over members nothing ran in. Asked
    here, every Python answers as 3.9 to 3.13 did, and a refused `stat` is a
    refusal that names the path (`unreadable`). A name the system cannot
    take at all (a NUL in a row's `path:`) is no file, as `exists()`
    answered it. This file's own copy, as each pinned copy keeps one (#370,
    #610): `bump-leg.py` has the same.
    """
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        if (exc.errno in _ABSENT_ERRNOS
                or getattr(exc, "winerror", None) in _ABSENT_WINERRORS):
            return False
        raise
    except ValueError:
        return False
    return kind(mode)


def _anything(mode: int) -> bool:
    """Any kind of file at all: what `Path.exists()` asks of a `.git`,
    which is a file in a mounted member and a folder in a clone (#430)."""
    return stat.S_IFMT(mode) != 0


def unreadable(code: str, named: str, exc: OSError, what: str) -> Refusal:
    """`code`'s refusal of a path this command must ask about and the
    operating system will not let it: its `stat` refused (`_is_a`), as in a
    folder this user cannot search (#430). The line is `validate-pins.py`'s
    `_cannot_read`, `<named>: cannot be read (<the system's reason>)`, with
    `named` relative to the holder and spelled; `what` says what was not
    done, and why the question matters. THE ADVICE FOLLOWS THE CAUSE, in
    `validate-pins.py`'s `_unreadable_file`'s words, word for word, since
    every path this command asks about is inside the holder: a permission
    (`PermissionError`, which is `EACCES` and `EPERM`) is put right by the
    mode or the owner, and any other cause is `OTHER_REASON`, which is not
    told to `chmod`."""
    advice = (
        "Make what this user may not open readable by this user: `chmod u+r` "
        "on a file, `chmod u+rx` on a directory (and on every directory above "
        "it inside the root), or fix who owns it. "
        if isinstance(exc, PermissionError) else OTHER_REASON)
    return Refusal(
        code,
        f"{named}: cannot be read ({exc.strerror or type(exc).__name__})",
        f"Remediation: {what} A path this command cannot read is a question "
        f"it cannot answer, never a pass. {advice}Then run the same command "
        "again.")


def checked_out(root: Path, row: dict) -> bool:
    """Whether the row's member is checked out: its mount holds a `.git`,
    asked as `_is_a` asks it, or the `member-unreadable` refusal naming that
    `.git` where its `stat` was refused (#430). (a) asks it of every row
    (`unfetchable`) and (b) before it runs anything in the member
    (`run_member_target`); on Python 3.14 the answer was "not checked out",
    and the member was skipped."""
    git_dir = member_path(root, row) / ".git"
    try:
        return _is_a(git_dir, _anything)
    except OSError as exc:
        raise unreadable(
            "member-unreadable", spelled(f"{row_path(row)}/.git"), exc,
            "Each row's mount is asked whether git checked its member out "
            "before anything is run in it, and this one could not be asked, "
            "so the run stopped there: no member's command was run after "
            "it.") from exc


def credential() -> tuple[str, str]:
    """`(source, token)`; `("none", "")` when the environment carries none."""
    for name in CREDENTIAL_ENV:
        value = (os.environ.get(name) or "").strip()
        if value:
            return name, value
    return "none", ""


def fetch_members(root: Path, rows: list[dict]) -> list[str]:
    """(a) `git submodule update --init --recursive`, authenticated or not.

    Where every member is checked out and git died on a value in
    `.gitmodules`, or on a work tree file it cannot parse, or its init
    died at a `.gitmodules` a merge left unmerged, so it updated none of
    them, the one failure line it returns is for `.gitmodules` (#768,
    #879); where its init in this holder died at a gitlink this holder
    records with no url, it is for that gitlink (`updated_none`, #879).
    Its line says no member was updated, or, where `rows` names none,
    nothing was (lane 1's NIT 5 on #889). Where none of that is so and
    git's update ended on a signal (`ended_on`, #998), the one failure
    line is for git's update, and its line names the signal and the code;
    where it died past this holder's own records, in a member's own
    index or at a member's commit no fetch brought (`stopped_below`,
    #892), the one failure line is for the gitlink git stopped at, and
    its line says the update stopped there. Whether a fetch there reached
    its remote is git's own trace's answer, or, where a token is in use
    and git's update was not traced, that of the two fetches made again
    with the token's rewrite (`fetch_reached`, #996).

    Returns a failure line for each of `rows` whose member it leaves not
    checked out where no credential would check it out (`unfetchable`), for
    the run to end FAILED on (#648); every member and leg is said to be
    fetched only where there is none and git exited 0. The advice to set a
    credential is printed only where git asked for one
    (`credential_advice`, #839). Raises the `git-not-runnable` refusal
    where git cannot be started (#694), and `member-unreadable` where a
    row's mount cannot be asked about, after git's own words (`unfetched`,
    #430)."""
    source, token = credential()
    rewrite: list[str] = []
    if token:
        for target in REWRITE_TARGETS:
            rewrite += ["-c", f"url.https://x-access-token:{token}@github.com/"
                              f".insteadOf={target}"]
    args = ["git", *rewrite, "submodule", "update", "--init", "--recursive"]
    print(f"  credential source: {source}")
    sys.stdout.flush()
    proc, fetched = run_update(args, root, traced=not token)
    left, stopper, modules = unfetched(root, rows, proc, source, token)
    whole = updated_none(stopper, modules)
    signum = ended_on(proc.returncode)
    below = (None if left or whole or proc.returncode != GIT_DIED
             else stopped_below(root, fetch_reached(fetched, rewrite)))
    if proc.returncode != 0:
        fetch_incomplete(proc, source, token,
                         credential_advice(bool(left), stopper, modules,
                                           below, signum))
    if left:
        print("  NOT CHECKED OUT, and not for want of a credential: "
              + ", ".join(f"{spelled(path)} ({reason(why, stopper, modules)})"
                          for _, path, why in left)
              + ". " + cures(left, stopper, rows, modules), file=sys.stderr)
        return [f"{spelled(row.get('project') or '?')} (not checked out)"
                for row, _, _ in left]
    if whole is not None:
        print(f"  {NONE_UPDATED[bool(rows)]}, and not for want of a "
              "credential: " + reason(whole, stopper, modules) + ". "
              + cures(left, stopper, rows, modules, (whole,)),
              file=sys.stderr)
        return [f"{spelled(stopper)} (git stopped at it)" if whole == STOPPED
                else f"{GITMODULES} (git cannot read it)"]
    if signum is not None:
        print(f"  {UPDATE_KILLED}, and not for want of a credential: "
              + killed_said(signum, proc.returncode), file=sys.stderr)
        return [f"git's update (ended on signal {signum})"]
    if below is not None:
        print(f"  {UPDATE_STOPPED}, and not for want of a credential: "
              + below_said(below), file=sys.stderr)
        return [f"{spelled(below.path)} (git stopped at it)"]
    if proc.returncode == 0:
        print("  every member and leg fetched")
    return []


def run_update(args: list[str], root: Path, traced: bool
               ) -> tuple[subprocess.CompletedProcess, frozenset[str] | None]:
    """(a)'s `git submodule update`, run as `args` say in `root`, and the
    work trees in which a fetch it made reached its remote (`fetched_in`,
    #892), or None where the run was not traced.

    TRACED ONLY WHERE `traced` SAYS, which `fetch_members` says where
    neither `SHAPE_LEGS_TOKEN` nor `SHAPE_LEGS_APP_TOKEN` is set
    (`CREDENTIAL_ENV`): trace2 writes each command's arguments, and the
    rewrite that carries that token is one, as is the url a remote helper
    is given with it, which git 2.43 writes unredacted (2.47.1 redacts the
    url, not the argument). Where `traced` says no, git's update runs in
    `untraced()`'s environment, so no trace the person asked for writes
    that token either: with `GIT_TRACE2_EVENT` set in this run's own
    environment, git wrote the rewrite into that file, the token in it
    (#996). A credential the person's own git config gives,
    a url rewrite in a config file or in `GIT_CONFIG_COUNT`, is read by the
    gits the update starts and can reach the trace files too (lane 5's
    NIT 1 on #954). The trace is a directory of the run's own, made with
    `tempfile.mkdtemp`, readable by its owner alone, and removed whatever
    the run does, so only a run killed before it ends leaves it behind;
    one that cannot be made leaves the run untraced. Raises the
    `git-not-runnable` refusal where git cannot be started (#694)."""
    trace = None
    if traced:
        try:
            trace = Path(tempfile.mkdtemp(prefix="bootstrap-trace-"))
        except OSError:
            trace = None
    env = (untraced() if not traced else None if trace is None
           else {**os.environ, TRACE_ENV: str(trace)})
    try:
        proc = started(args, root, env)
        return proc, None if trace is None else fetched_in(trace)
    finally:
        if trace is not None:
            shutil.rmtree(trace, ignore_errors=True)


def started(args: list[str], root: Path, env: dict[str, str] | None
            ) -> subprocess.CompletedProcess:
    """`args` run in `root` under `env` (None for this process's own), or
    the `git-not-runnable` refusal where git cannot be started (#694)."""
    try:
        return subprocess.run(args, cwd=str(root), capture_output=True,
                              text=True, encoding="utf-8", errors="replace",
                              check=False, env=env)
    except OSError as exc:
        refusal = git_not_started(exc)
        if refusal is None:
            raise
        raise refusal from exc


def fetched_in(trace: Path) -> frozenset[str]:
    """Each work tree (`same_place`) in which a `git fetch` git's update
    made exited 0, so reached the remote it fetched from, read from the
    trace2 events in `trace`, a file for each git the update started
    (#892).

    TOLD BY THE EXIT CODE, NEVER GIT'S WORDS, as `gitmodules_listed`
    tells a listing (#856): git's event format is JSON, a line an event,
    and a process's `cmd_name` event names its command, its `exit` event
    gives its code, and its `def_repo` event for repository 1 gives the
    work tree it runs in (a `git submodule` process opens each member as
    another repository, 2 and up, which are not its own). Measured, git
    2.43.0: where a member's commit is on no branch of its remote, git's
    `fetch` there exits 0 and its fetch of the commit 128 (`not our ref`);
    where git cannot reach the remote, as for want of a credential, both
    exit 128. A line that is no event is skipped, and a git with no trace2
    (before 2.22) writes nothing, so nothing is said to be fetched."""
    runs: dict[str, dict] = {}
    for event in trace_events(trace):
        run = runs.setdefault(str(event.get("sid")), {})
        kind = event.get("event")
        if kind == "cmd_name":
            run["name"] = event.get("name")
        elif kind == "def_repo" and event.get("repo") == 1:
            run["worktree"] = event.get("worktree")
        elif kind == "exit":
            run["code"] = event.get("code")
    return frozenset(same_place(run["worktree"]) for run in runs.values()
                     if run.get("name") == "fetch" and run.get("code") == 0
                     and isinstance(run.get("worktree"), str))


def trace_events(trace: Path) -> list[dict]:
    """Every trace2 event in the files in `trace`, in the order of their
    names, then of their lines; a file that cannot be read, or a line that
    is no event, is skipped."""
    try:
        names = sorted(os.listdir(trace))
    except OSError:
        return []
    events: list[dict] = []
    for name in names:
        try:
            text = (trace / name).read_text(encoding="utf-8",
                                            errors="replace")
        except OSError:
            continue
        events += filter(None, map(trace_event, text.splitlines()))
    return events


def trace_event(line: str) -> dict | None:
    """One trace2 event, or None where `line` is not one."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def same_place(path: str | Path) -> str:
    """`path` as one spelling for one directory: its real path, in the
    case the disk compares names in where it folds case."""
    return os.path.normcase(os.path.realpath(path))


#: How the walk asks, of a checkout whose store lacks the commit recorded
#: for it and that commit, whether a fetch there reached its remote and
#: did not bring it (B4, `entered`): `fetch_reached` makes one.
Reached = Callable[[Path, str], bool]


def fetch_reached(fetched: frozenset[str] | None, rewrite: list[str]
                  ) -> Reached:
    """How the walk asks whether a fetch git's update made in a checkout
    reached its remote (`entered`). Where `rewrite`, the token's `-c`, is
    given, git's update was not traced, and the two fetches it makes there
    are made again (`refetched`, #996); else the trace answers, by whether
    `fetched` holds that checkout's work tree (`fetched_in`, #892), and
    no fetch reached any remote where the run was not traced (`fetched`
    None)."""
    if rewrite:
        return lambda checkout, commit: refetched(checkout, commit, rewrite)
    return lambda checkout, commit: (fetched is not None
                                     and same_place(checkout) in fetched)


def refetched(checkout: Path, commit: str, rewrite: list[str]) -> bool:
    """Whether a fetch in `checkout` reaches its remote and leaves its
    store without `commit` (#996): the two fetches git's update makes
    there (`run_update_procedure` in git 2.43's submodule--helper.c),
    made again in this process, since a run with a token in use is not
    traced (`run_update`). `git fetch origin`, then, where the store still
    lacks `commit`, `git fetch origin <commit>`, each with `rewrite`, the
    token's `-c`, in its argv, as git's update was given it, and in
    `untraced()`'s environment, so neither writes the token anywhere; what
    they print is neither read nor shown. Each runs with
    `GIT_PROTOCOL_FROM_USER=0`, as `git submodule` runs every git it
    starts, so a url a member's config took from a `.gitmodules` is given
    only the transports git's update gives it: a plain fetch took the
    `file` transport, which git's update refused (`protocol.file.allow`
    is `user`), and brought a commit git's update could not (measured,
    git 2.43.0).

    TOLD BY THE EXIT CODE AND THE STORE, never git's words: B4 where the
    first exits 0, so reached the remote, and the store still lacks
    `commit` after the second. A first that fails, as where the token
    does not reach that remote, is the credential's, as git's own was;
    and where either brings the commit, git's update did not die for want
    of it as far as this tells, so nothing is said. Asked only of a
    checkout the walk reaches whose store lacks its commit after git's
    update exited 128 with a token in use, where the walk ends, so it
    costs two fetches at most."""
    env = {**untraced(), FROM_USER_ENV: "0"}
    first = subprocess.run(["git", *rewrite, "fetch", "origin"],
                           cwd=str(checkout), capture_output=True,
                           check=False, env=env)
    if first.returncode != 0 or commit_held(checkout, commit):
        return False
    subprocess.run(["git", *rewrite, "fetch", "origin", commit],
                   cwd=str(checkout), capture_output=True, check=False,
                   env=env)
    return not commit_held(checkout, commit)


def untraced() -> dict[str, str]:
    """This run's environment for a git given the token in its argv
    (#996): every variable whose name begins `GIT_TRACE` (`TRACE_PREFIX`)
    taken out, which on Windows `os.environ` spells in upper case
    whatever case it was set in, and trace2's targets set to `0`
    (`TRACE2_OFF`), which turns off one the system or the global config
    names too. A trace writes a command's arguments, the token's rewrite
    among them, and the url a remote helper is given, the token in it, to
    a file or a socket."""
    env = {name: value for name, value in os.environ.items()
           if not name.startswith(TRACE_PREFIX)}
    env.update(dict.fromkeys(TRACE2_OFF, "0"))
    return env


def unfetched(root: Path, rows: list[dict],
              proc: subprocess.CompletedProcess, source: str, token: str
              ) -> tuple[list[tuple[dict, str, str]], str | None,
                         Gitmodules]:
    """`unfetchable`, asked after git's update `proc` (#430). Where it
    refuses a mount it cannot ask about (`member-unreadable`) and git did
    not exit 0, git's own words for the update are printed first
    (`fetch_incomplete`), with no advice: what git said of that mount is
    the same fact, the refusal after it names the cure, and no credential
    is it. It refused before they were printed, and they were lost."""
    try:
        return unfetchable(root, rows, proc.returncode == 0)
    except Refusal:
        if proc.returncode != 0:
            fetch_incomplete(proc, source, token, "")
        raise


def fetch_incomplete(proc: subprocess.CompletedProcess, source: str,
                     token: str, advice: str) -> None:
    """(a)'s report of a `git submodule update` that exited non-zero: git's
    own words, then `advice`, where there is any (`credential_advice`)."""
    # The token can appear in git's own error text (it is in the URL it
    # tried), so the output is scrubbed before it is printed.
    message = (proc.stderr + proc.stdout).strip()
    if token:
        message = message.replace(token, "<redacted>")
    print(f"  FETCH INCOMPLETE (git exit {proc.returncode}) using "
          f"credential source '{source}':\n{message}", file=sys.stderr)
    if advice:
        print(advice, file=sys.stderr)


def credential_advice(denied: bool, stopper: str | None,
                      modules: Gitmodules, below: Below | None = None,
                      signum: int | None = None) -> str:
    """(a)'s advice to set a credential, or nothing where git asked for none
    (#839): where its init died at a gitlink it has no url for (`stopper`),
    or it read nothing from `.gitmodules`, a merge leaving it unmerged, a
    value git dies on or a file it cannot parse, it fetched nothing. Every
    row (a) then leaves not checked out is said to be no credential's, and
    the advice beside that was its denial (w768's candidate 1 on #819).
    Nor where git's update died past this holder's own records at what no
    credential cures (`below`, `stopped_below`, #892): a gitlink a member
    gives no url, or a member's commit a fetch that reached its remote did
    not bring. Nor where it ended on a signal (`signum`, `ended_on`,
    #998): a crash or a kill is no want of a credential, and a fetch git
    could not make ends git's update there with 128, so an update that
    ends `128 + N` met none. Anywhere else a fetch git made failed, a
    member's, or a leg's in a member checked out, and the advice stands;
    where a row is said to be no credential's beside it (`denied`), it is
    for the members that line does not name."""
    if (stopper is not None or below is not None or signum is not None
            or modules.unmerged or modules.refused or modules.unreadable):
        return ""
    which = ("the members the next line does not name" if denied
             else "the members")
    return (f"  If {which} are PRIVATE, set SHAPE_LEGS_TOKEN (a fine-grained "
            "PAT with contents:read on them) or export an App-minted "
            "SHAPE_LEGS_APP_TOKEN, then re-run. What did arrive is "
            "bootstrapped below.")


def ended_on(returncode: int) -> int | None:
    """The signal git's update ended on, or None (#998). TOLD BY THE EXIT
    CODE ALONE, never git's words, as `stopped_below` tells a 128:
    - `128 + N`, where a git it ran died of signal N, as `run_command`
      gives a child's signal, and git's update goes on past that gitlink
      and ends with that code (measured, git 2.43.0: `submodule--helper
      died of signal 11` on a member's own `.gitmodules` giving a `branch`
      no value, exit 139);
    - `-N`, where git itself was killed by signal N, as Python gives it.
    Not 128, git's `die`, which `stopped_below` asks about, nor a code from
    `128 + signal.NSIG` on, which numbers no signal this system has, as
    255, which git exits with where a command of its returns -1: those are
    read as before, the advice and `ok` where nothing else is told."""
    if returncode < 0:
        return -returncode
    if GIT_DIED < returncode < GIT_DIED + signal.NSIG:
        return returncode - GIT_DIED
    return None


def killed_said(signum: int, returncode: int) -> str:
    """(a)'s line, after its lead, where git's update ended on `signum`
    with `returncode` (`ended_on`, #998): the signal by its number and,
    where this system names it, its name, then the code; a code past 128
    is a git it ran that died of it, whose own words git printed above,
    and a negative one is git itself killed."""
    try:
        name = f"{signal.Signals(signum).name}, "
    except ValueError:
        name = ""
    said = (f"git's update ended on signal {signum} ({name}exit "
            f"{returncode}), ")
    if returncode < 0:
        return said + "which killed it."
    return (said + "which a git it ran died of. Git's own words above say "
            "which git and where.")


def git_not_started(exc: OSError) -> Refusal | None:
    """The `git-not-runnable` refusal for an `OSError` that says git could
    not be STARTED (#694), else `None`, and the error goes on as it did.

    Nothing caught one: `make bootstrap` with no git on PATH ended (a) in a
    `FileNotFoundError` traceback, exit 1, the code of `family bootstrap
    FAILED`, though nothing had failed. Git's is told by its NAME, as
    `validate-pins.py` tells it: a `filename` of `git`, or none at all on a
    `FileNotFoundError` or a `PermissionError`, as Windows raises them, or
    on an `OSError` whose `winerror` is 193, Windows' `[WinError 193]` for a
    `git.exe` it cannot execute (#1001); one naming a directory is not
    git's. The code, and the remedy's first sentence, are
    `validate-family.py`'s."""
    nameless = (exc.filename is None
                and (isinstance(exc, (FileNotFoundError, PermissionError))
                     or getattr(exc, "winerror", None) == 193))
    if exc.filename != "git" and not nameless:
        return None
    return Refusal(
        "git-not-runnable",
        f"the members could not be fetched: git could not be run "
        f"({exc.strerror or exc})",
        "Remediation: put git on PATH and run this again. Step (a) fetches "
        "every member through git, and each member's own bootstrap places "
        "its legs through git too, so without it nothing here can be "
        "fetched or bootstrapped.")


def cures(left: list[tuple[dict, str, str]], stopper: str | None,
          rows: list[dict], modules: Gitmodules,
          whole: tuple[str, ...] = ()) -> str:
    """What (a)'s line says cures the rows `left` names, one sentence for
    each kind of cause among them (#648), or, where it names none, what
    cures `whole`, why git updated no member (`updated_none`, #879), one
    reason or none:

    - A `.gitmodules` a merge left unmerged in the index, which git reads
      nothing from (`Gitmodules.unmerged`): the file resolved and added.
    - A `.gitmodules` that gives a value git dies on (`Gitmodules.refused`,
      #768): each key given a value git takes (`TAKES`), or its line taken
      out, and the file committed, with `validate-family.py --no-members`,
      whose `gitmodules-value-refused` prints the commands.
    - A work tree `.gitmodules` git cannot parse (`Gitmodules.unreadable`):
      the file mended by hand and committed.
    - A gitlink or a section the holder lacks at the row's path:
      `validate-family.py`, which names it and the commit that cures it,
      `member-gitlink-absent` (with the move, for a gitlink recorded only
      in another case, #363) or `member-gitmodules-absent`.
    - A path git has no url for (`has_url`), a row's own or the gitlink git
      stopped at. Where more than one section gives it, as a merge that
      kept both sides leaves them, `validate-family.py --no-members`, whose
      `gitmodules-path-twice` says which to keep and to take the others
      out: a section written back would be one more. Otherwise a row's own
      is its section written back. A gitlink in `members/` no row names is
      `--no-members` too, whose `member-gitlink-unnamed` names it and the
      commit that cures it: members checked, the validator refuses
      `member-uninitialized` for the first row where every row's gitlink
      is there, as with a stray or a hand mount, and `member-gitlink-absent`
      where a row's is only in another case, which the first sentence
      names. A gitlink outside `members/` is taken out of the index, as
      every mode of the validator says (#878): no row names it, and with
      no url no clone can check it out.
    - A row git exited 0 over: the update that checks it out whatever the
      clone chose. `--init` with the path registers a member a subset
      clone left out, and `--checkout` overrides an `update = none`.
    - The index's or HEAD's `.gitmodules`, a blob, which git read only up
      to a line it cannot parse, or up to a key with no value it stops at
      (`Gitmodules.cut`, #856), for a row with no section or no url there,
      or the gitlink git stopped at (`CUT_WHYS`): that file put back,
      mended and committed, which `gitmodules_cures` says. A section or
      url git did not read may be past the line, so no other cure is said
      for those: a section written back where the work tree holds no file
      would be the only one in it, and `validate-family.py` reads HEAD's
      file alone, not the index's."""
    whys = {why for _, _, why in left} | set(whole)
    said = gitmodules_cures(whys, modules)
    if modules.cut:
        left = [entry for entry in left if entry[2] not in CUT_WHYS]
        whys -= CUT_WHYS
    if whys & {NO_GITLINK, NO_SECTION}:
        said.append(f"`{PYTHON} scripts/validate-family.py` names the cause "
                    "and the commit that cures it.")
    unread = [path for _, path, why in left if why == NO_URL]
    if STOPPED in whys and stopper not in {path for _, path, _ in left}:
        unread.append(stopper)
    named = {row_path(row) for row in rows}
    twice = [path for path in unread if modules.given[path] > 1]
    own = [path for path in unread if path in named and path not in twice]
    if twice:
        said.append(f"`{PYTHON} scripts/validate-family.py --no-members` "
                    f"names each path more than one section of {GITMODULES} "
                    "gives, and how to take the others out.")
    if own:
        said.append(f"Write {'the' if len(own) == 1 else 'each'} section of "
                    f"{GITMODULES} for {', '.join(map(spelled, own))} back "
                    "as `family.py add` writes one, with its path and url, "
                    f"and commit {GITMODULES}.")
    for path in unread:
        if path in named or path in twice:
            continue
        if path.split("/", 1)[0].casefold() == DEFAULT_MEMBERS_DIR:
            said.append(f"`{PYTHON} scripts/validate-family.py --no-members` "
                        f"names each gitlink in {DEFAULT_MEMBERS_DIR}/ that "
                        "no row names, and the commit that cures it.")
        else:
            removal = shlex.join(["git", "rm", "--cached", "--", path])
            said.append(f"No row names {spelled(path)} and no clone can check "
                        f"it out: `{spelled(removal)}` takes its gitlink "
                        "out, then commit that.")
    exited = [path for _, path, why in left if why == EXITED_0]
    if exited:
        update = shlex.join(["git", "submodule", "update", "--init",
                             "--checkout", "--recursive", "--", *exited])
        said.append(f"`{spelled(update)}` checks "
                    f"{'it' if len(exited) == 1 else 'them'} out.")
    return " ".join(said)


def gitmodules_cures(whys: set[str], modules: Gitmodules) -> list[str]:
    """`cures`' sentences for a `.gitmodules` git reads nothing from, each
    in the order `cures` says them (#648, #768): a merge left unmerged,
    for a row `whys` names so; each value git dies on; a work tree file
    git cannot parse. And for a blob git read only up to such a line, or
    up to a key with no value it stops at, where a row `whys` names is
    one of `CUT_WHYS` (#856): the command that puts that file back in the
    work tree, `git checkout` from the index where git read the index's,
    which keeps what was staged, and from HEAD where it read HEAD's, then
    the file mended, or the key given a value git takes (`TAKES`) or its
    line taken out, and committed. The index's is put back with
    `--ignore-skip-worktree-bits`: in a sparse checkout that leaves
    `.gitmodules` out, its entry is skip-worktree, and `git checkout --
    .gitmodules` matches no file there (RV877's NIT-3, measured, git
    2.43.0); with the flag it puts the file back there and in any other
    work tree. HEAD's is put back only where the index holds no entry,
    so no skip-worktree bit, and `git checkout HEAD` puts it back in a
    sparse checkout too. `git config -f .gitmodules --list`
    takes a key with no value, so it is pointed at for the line alone."""
    said = []
    if UNMERGED in whys:
        said.append(f"Resolve the merge in {GITMODULES} and `git add "
                    f"{GITMODULES}`, then run this again.")
    if modules.refused:
        given = "; ".join(
            f"give `{spelled(key)}` a value git takes, "
            f"{TAKES[key.rpartition('.')[2]]}, or take that line out"
            for key in dict.fromkeys(key for key, _ in modules.refused))
        said.append(f"{given[:1].upper()}{given[1:]}, and commit "
                    f"{GITMODULES}. `{PYTHON} "
                    "scripts/validate-family.py --no-members` prints the "
                    "commands.")
    if modules.unreadable:
        said.append(f"Mend {GITMODULES} by hand (`git config -f "
                    f"{GITMODULES} --list` says where it breaks), and "
                    "commit it.")
    if modules.cut and whys & CUT_WHYS:
        head = modules.cut == HEAD_GITMODULES
        put_back = shlex.join([
            "git", "checkout",
            *(["HEAD"] if head else ["--ignore-skip-worktree-bits"]),
            "--", GITMODULES])
        whose = f"{'HEAD' if head else 'the index'}'s {GITMODULES}"
        key = modules.cut_key
        mend = (f"`{spelled(key)}`, a key with no value: give it a value "
                f"git takes, {TAKES[key.rpartition('.')[2]]}, or take that "
                "line out" if key else
                "a line it cannot parse: mend it by hand (`git config -f "
                f"{GITMODULES} --list` says where it breaks)")
        said.append(f"`{put_back}` puts back {whose}, which git read only "
                    f"up to {mend}, and commit it.")
    return said


def reason(why: str, stopper: str | None, modules: Gitmodules) -> str:
    """`why` as (a)'s line says it: `STOPPED` names the gitlink git stopped
    at, and `REFUSED` each entry of `.gitmodules` git refused, as "`<key>`
    is `<value>`", or "has no value" (#768)."""
    if why == STOPPED:
        return STOPPED.format(spelled(stopper))
    if why == REFUSED:
        return REFUSED.format(" and ".join(
            f"`{spelled(key)}` " + ("has no value" if value is None
                                     else f"is `{spelled(value)}`")
            for key, value in modules.refused))
    return why


class Gitmodules(NamedTuple):
    """`.gitmodules` as (a) asks it (#648), read by `gitmodules_sections`.

    `given` counts the sections that give each path, every section kept, as
    `validate-family.py` reads them for the findings (a)'s line names:
    `member-gitmodules-absent` and `gitmodules-path-twice`. `read` is
    `{path: name}`, the section git reads for each path, and `urls` is
    `{name: url}`, the url git takes from each, as git's own parser has
    them. `unmerged` says a merge left the file unmerged in the index, and
    `refused` holds each `(submodule.<name>.<key>, value)` git dies on as
    it reads the file, None for a key with no value (#768): git reads
    nothing from it then, and the three are empty. `unreadable` says the
    work tree's file is one `git config --list` cannot parse, which git
    dies reading: the three are empty then too. `cut` is the blob git read
    only up to such a line, as `gitmodules_source` names it,
    `HEAD:.gitmodules` or the index's object id, where it read an entry
    before it, or the blob is the index's (`gitmodules_listed`, #856):
    the three hold what it read,
    and `cures` writes no section back. Empty where git read the whole
    file, or nothing. `cut_key` is the `submodule.<name>.<key>` with no
    value that cut it, where that is what git stopped at
    (`ends_blob_reading`), a line `git config --list` takes, and empty
    where a line it cannot parse did. `updates` is `{name: update}`, the
    `update` git takes from each section, where any gives one, for the walk
    past this holder's records (`updated_there`, #892)."""

    given: Counter
    read: dict[str, str]
    urls: dict[str, str]
    unmerged: bool = False
    refused: tuple[tuple[str, str | None], ...] = ()
    unreadable: bool = False
    cut: str = ""
    cut_key: str = ""
    updates: dict[str, str] | None = None


def gitmodules_sections(root: Path) -> Gitmodules:
    """`.gitmodules` as `git submodule update` reads it: the work tree's
    file, which a fresh clone takes from HEAD, or, where the work tree has
    none, as a deletion not yet committed or a sparse checkout leaves it,
    the index's, then HEAD's (`gitmodules_source`, #768), each of the
    last two, a blob, up to a line git cannot parse, as git reads it,
    and `cut` where it read an entry before that line, or the blob is
    the index's (`gitmodules_listed`, #856), or up to a key with no value
    git stops at, `cut` and `cut_key` (`gitmodules_entries`). Nothing
    where none holds one, or git cannot read it: git has no url for any
    submodule then either.
    Nothing, and `unreadable`, where that is the
    work tree's file and `git config --list` cannot parse it: git dies
    reading it (`bad config line`), before it checks out any member.
    Nothing, and `unmerged`, where the index holds the file only at a
    merge's conflict stages (`git ls-files -s`): git reads no
    `.gitmodules` at all then, whatever the work tree holds
    (`repo_read_gitmodules`), and its init dies at the first gitlink.
    Nothing, and `refused`, where git dies on an entry as it reads the
    file (`refused_value`, #768), before it checks out any member.

    `read` and `urls` keep git's own rules (submodule-config.c), which
    drop what `git config --list` keeps (`gitmodules_entries`,
    `read_sections`)."""
    nothing = Gitmodules(Counter(), {}, {})
    source = gitmodules_source(root)
    if source is None:
        return nothing._replace(unmerged=True)
    listed = gitmodules_listed(root, source)
    if listed is None:
        return nothing._replace(unreadable=os.path.isfile(root / GITMODULES))
    printed, cut = listed
    entries, ended = gitmodules_entries(root, printed, source[0] == "--blob")
    refused = tuple(dict.fromkeys(
        (f"submodule.{name}.{key}", value)
        for name, key, value, ignored in entries
        if not ignored and refused_value(root, key, value)))
    if refused:
        return nothing._replace(refused=refused)
    return read_sections(entries)._replace(
        cut=source[1] if cut or ended else "", cut_key=ended)


def gitmodules_source(root: Path) -> list[str] | None:
    """What `git config` is given to read the `.gitmodules` git reads
    (`config_from_gitmodules`, #768): `--file` for the work tree's, where
    there is one, else `--blob` for the index's at stage 0, else HEAD's.
    None where the index holds it only at a merge's conflict stages."""
    try:
        stages = git_out(["ls-files", "-s", "-z", "--", GITMODULES],
                         cwd=root, binary=True)
    except Refusal:
        stages = b""
    source = ["--blob", HEAD_GITMODULES]
    for record in stages.split(b"\0"):
        meta, _, name = record.partition(b"\t")
        fields = meta.split()
        if name != GITMODULES.encode() or len(fields) != 3:
            continue
        if fields[2] != b"0":
            return None
        source = ["--blob", fields[1].decode("ascii")]
    if os.path.lexists(root / GITMODULES):
        return ["--file", GITMODULES]
    return source


def gitmodules_listed(root: Path, source: list[str]
                      ) -> tuple[bytes, bool] | None:
    """What `git config -z --no-includes --list` prints of the
    `.gitmodules` that `source` names (`gitmodules_source`), and whether
    git stopped short of the file's end at a line it cannot parse, or
    None where git cannot read it (#856).

    A BLOB IS READ UP TO A LINE GIT CANNOT PARSE. `git config --blob`
    prints the entries before that line, then `bad config line`, and
    exits 128. Git's submodule reader, which reads the index's or HEAD's
    file where the work tree has none, takes those same entries, says
    the same line as an error, not a die, and goes on (measured, git
    2.43.0): so what was printed is what git read, and a bad line before
    the first section leaves nothing, as git reads nothing. A work tree
    file with such a line is None: git dies reading it. Git is run as
    `git_out` runs it.

    TOLD BY THE EXIT CODE, NEVER GIT'S WORDS, which a git built with its
    translations prints in the person's language: a blob's listing that
    exits 128 is read for what it printed, whatever it says on stderr.
    The other 128 met is a blob git cannot find (`HEAD:.gitmodules`
    where HEAD holds none, #611), which prints nothing, and empty
    stdout reads as the same `Gitmodules` that None gives for a blob:
    no entry, and nothing `unreadable`, since a blob is read only where
    the work tree holds no file. So HEAD's, printing nothing, is no
    `cut`: it may be no file at all. The index's is, printing nothing or
    not: `git ls-files -s` gave its object id, so the blob is there, and
    a 128 can only be a line git cannot parse, the first included
    (RV877's SHOULD-2).

    NO `[include]` IS FOLLOWED (`--no-includes`), as git's submodule
    reader follows none. `git config --blob` follows one by default: a
    relative one stopped its listing there (`relative config includes
    must come from files`), where git reads on, and an absolute one's file
    was listed with the blob's own entries, where git reads the blob's
    alone. A work tree file's includes are not followed by default
    either."""
    proc = subprocess.run(["git", "config", "-z", "--no-includes", *source,
                           "--list"],
                          cwd=str(root), capture_output=True, check=False)
    if proc.returncode == 0:
        return proc.stdout, False
    if source[0] == "--blob" and proc.returncode == 128:
        return proc.stdout, bool(proc.stdout) or source[1] != HEAD_GITMODULES
    return None


def gitmodules_entries(root: Path, listed: bytes, blob: bool
                       ) -> tuple[list[tuple[str, str, str | None, bool]],
                                  str]:
    """`(name, key, value, ignored)` for each `submodule.<name>.<key>` that
    `git config -z --list` printed in `listed`, in file order, as git's
    submodule reader meets them: None for a key with no value, and
    `ignored` for a section git ignores whole, whose name is empty or has
    a `..` component, split on `/` and on a backslash (git warns `ignoring
    suspicious submodule name`), a value git would die on included. In the
    index's or HEAD's file, a `blob`, git reads nothing after a key it
    refuses with no value (`ends_blob_reading`), and that key, as
    `submodule.<name>.<key>`, is returned beside them; else nothing."""
    entries: list[tuple[str, str, str | None, bool]] = []
    for record in listed.split(b"\0"):
        key, valued, value = record.decode("utf-8",
                                           "surrogateescape").partition("\n")
        section, _, variable = key.rpartition(".")
        if not section.startswith("submodule."):
            continue
        name = section[len("submodule."):]
        ignored = not name or ".." in name.replace("\\", "/").split("/")
        if blob and not ignored and not valued and ends_blob_reading(
                root, variable):
            return entries, f"submodule.{name}.{variable}"
        entries.append((name, variable, value if valued else None, ignored))
    return entries, ""


def ends_blob_reading(root: Path, key: str) -> bool:
    """Whether a `key` with no value ends git's reading of the index's or
    HEAD's `.gitmodules`, a blob, where `bad config line` is an error and
    no die (#768): each key git refuses with no value, but a `branch` only
    where git does not crash on it (`crashes_on_branch`); before 2.43.1
    git crashes on it there too, and `refused_value` names it. Measured on
    git 2.43.0 (#856): a bare `url`, `path`, `update` or `ignore` in a
    blob is `missing value` and `bad config line`, and git reads no
    further; a bare `branch` crashes it (exit 139); a bare `shallow`,
    `fetchRecurseSubmodules` or `active` is read as true, and git reads
    on."""
    return key in NO_VALUE_REFUSED and (key != "branch"
                                        or not crashes_on_branch(root))


def read_sections(entries: list[tuple[str, str, str | None, bool]]
                  ) -> Gitmodules:
    """`Gitmodules` of `entries` (`gitmodules_entries`) where git refuses
    none. `given` counts every section that gives a path, an ignored one
    too. `read` and `urls` keep git's rules: a section git ignores gives
    neither; a `path` or `url` that begins with `-` is dropped, and the
    value before it stands (`may be interpreted as a command-line
    option`); where two sections give one path, the later in the file
    decides, as a later value in one section replaces an earlier, and a
    section that gives a path again lets go of the one it gave, even where
    a later section gave that one too: git then reads no section there.
    `updates` keeps each section's last `update`, as git keeps it (#892)."""
    sections: dict[str, dict[str, str]] = {}
    read: dict[str, str] = {}
    held: dict[str, str] = {}
    urls: dict[str, str] = {}
    updates: dict[str, str] = {}
    for name, key, value, ignored in entries:
        sections.setdefault(name, {})[key] = "" if value is None else value
        if ignored or value is None or value.startswith("-"):
            continue
        if key == "path":
            if name in held:
                read.pop(held[name], None)
            held[name] = value
            read[value] = name
        elif key == "url":
            urls[name] = value
        elif key == "update":
            updates[name] = value
    return Gitmodules(Counter(keys["path"] for keys in sections.values()
                              if "path" in keys), read, urls, updates=updates)


def refused_value(root: Path, key: str, value: str | None) -> bool:
    """Whether git 2.43 dies reading a `.gitmodules` that gives a submodule
    `value` for `key`, None for no value (#768), as `parse_config` in its
    submodule-config.c reads the key: a `path`, `url`, `update` or
    `ignore` with no value (`bad config line`), and a `branch` with none
    (it crashes, and git 2.43.1 and later refuse it as they refuse a `url`
    with none); an `update` other than `none`, `checkout`, `rebase` or
    `merge`, in that case, a `!command` included (`invalid value`); a
    `shallow` that is no boolean (`bad boolean config value`); and a
    `fetchrecursesubmodules` that is neither a boolean nor `on-demand`. An
    `ignore` it does not know is a warning, and any other key takes any
    value."""
    if value is None:
        return key in NO_VALUE_REFUSED
    if key == "update":
        return value not in UPDATE_VALUES
    if key == "shallow" or (key == "fetchrecursesubmodules"
                            and value != "on-demand"):
        return git_bool(root, value) is None
    return False


def crashes_on_branch(root: Path, version: str | None = None) -> bool:
    """Whether this git crashes reading a `.gitmodules` that gives a
    submodule a `branch` with no value (#768): every git before 2.43.1
    does, in the index's or HEAD's file too, where a later git reads that
    line as the end of the file (`BRANCH_READ_SINCE`). `version` is what
    `git version` printed, for a test to give; None asks this git. A git
    whose version cannot be read is taken for one that crashes: the run
    then fails naming the key, a cure true on every git, rather than pass
    a member git never asked for as the missing credential's."""
    if version is None:
        try:
            version = git_out(["version"], cwd=root)
        except Refusal:
            return True
    found = GIT_VERSION_RE.match(version)
    return (found is None
            or tuple(map(int, found.groups())) < BRANCH_READ_SINCE)


def git_bool(root: Path, value: str | None) -> bool | None:
    """`value` read as a boolean by git itself, which reads one so for
    every key (`git config --type=bool`, its `git_parse_maybe_bool`):
    `true`, `yes`, `on` in any case, a number other than 0, or no value at
    all are true, and `false`, `no`, `off`, 0 and an empty value false.
    None where git takes it for no boolean, and dies. It is asked as the
    `--default` of a key looked up in an empty file, so no `probe.value`
    in any of the person's own config scopes is read in its place."""
    if value is None:
        return True
    try:
        answer = git_out(["config", "--file", os.devnull, "--type=bool",
                          f"--default={value}", "--get", "probe.value"],
                         cwd=root)
    except Refusal:
        return None
    return answer == "true"


def submodule_config(root: Path) -> dict[str, list[str | None]]:
    """Every `submodule.` key this repository's git config sets, in every
    scope git reads, with each value it gives, None for no value, as git's
    init asks them: `submodule.active` and its patterns, a section's own
    `submodule.<name>.active` (#768), and `submodule.<name>.url` as an
    earlier init writes it. Empty where git lists none."""
    try:
        config = git_out(["config", "-z", "--get-regexp", r"^submodule\."],
                         cwd=root, binary=True)
    except Refusal:
        return {}
    found: dict[str, list[str | None]] = {}
    for record in filter(None, config.split(b"\0")):
        key, valued, value = record.decode("utf-8",
                                           "surrogateescape").partition("\n")
        found.setdefault(key, []).append(value if valued else None)
    return found


def has_url(modules: Gitmodules, config: dict[str, list[str | None]],
            path: str) -> bool:
    """Whether git's init finds a url for the gitlink at `path`: in the
    section git reads for that path (`Gitmodules.read`), or in the git
    config under that section's name, as an earlier init writes it. Where
    git reads no section there it has none, whatever the config holds."""
    name = modules.read.get(path)
    return name is not None and (name in modules.urls
                                 or f"submodule.{name}.url" in config)


def init_stop(root: Path, modules: Gitmodules,
              config: dict[str, list[str | None]]) -> str | None:
    """The gitlink `git submodule update --init` dies at, or None: the first
    in the index, in index order, that its init step asks about and has no
    url for (`No url found for submodule path`, exit 128), before it
    checks out any member (#648).

    ASKED AS GIT 2.43 ASKS IT, of the index, `modules` and `config`, this
    repository's git config. Every gitlink the index records is asked, but
    where the config sets `submodule.active`, as a recursive clone sets it
    (`.`), only those git counts active (`active`), and never one no
    section git reads gives a path. A gitlink git has no url for
    (`has_url`) stops it. So a stray case variant or a member mounted by
    hand stops a plain clone's update, and leaves a recursive clone's to
    the credential. Read nothing, it answers None. Asked of a member's
    checkout, with the member's own `.gitmodules` and config, it is where
    git's init in that member stops (`stopped_below`, #892)."""
    for path, _ in init_asks(root, modules, config):
        if not has_url(modules, config, path):
            return path
    return None


def init_asks(root: Path, modules: Gitmodules,
              config: dict[str, list[str | None]]) -> list[tuple[str, str]]:
    """`(path, commit)` of each gitlink git's init asks about, in index
    order (`init_stop`): every gitlink the index records, but where the
    config sets `submodule.active` only those git counts active
    (`active`). Empty where the index cannot be read."""
    try:
        index = git_out(["ls-files", "-s", "-z"], cwd=root, binary=True)
    except Refusal:
        return []
    asked = []
    for record in index.split(b"\0"):
        meta, _, entry = record.partition(b"\t")
        fields = meta.split()
        if fields[:1] != [GITLINK_MODE]:
            continue
        path = entry.decode("utf-8", "surrogateescape")
        if ("submodule.active" not in config
                or active(root, modules, config, path)):
            asked.append((path, fields[1].decode("ascii", "replace")))
    return asked


def active(root: Path, modules: Gitmodules,
           config: dict[str, list[str | None]], path: str) -> bool:
    """Whether git's init counts the gitlink at `path` active where the
    config sets `submodule.active` (`is_tree_submodule_active` in git
    2.43's submodule.c): never where no section git reads gives that path;
    else as the section's own `submodule.<name>.active` says, its last
    value read as a boolean (`git_bool`), where the config sets one that
    is (#768); else where one of `submodule.active`'s patterns names it
    (`pattern_names`)."""
    name = modules.read.get(path)
    if name is None:
        return False
    own = config.get(f"submodule.{name}.active")
    flag = git_bool(root, own[-1]) if own else None
    if flag is not None:
        return flag
    return any(pattern_names(pattern, path)
               for pattern in config["submodule.active"])


def pattern_names(pattern: str | None, path: str) -> bool:
    """Whether a `submodule.active` pattern names `path` (#768). A plain
    path, as `git clone --recurse-submodules=<path>` writes one, names
    itself and every path under it, as git's pathspec does, and `.` names
    every path. A pattern with pathspec magic (a leading `:`), a glob
    character or a backslash, or with an empty, `.` or `..` component past
    a leading `./`, is read as naming every path, as every pattern was
    before: this does not match those as git does."""
    if (pattern is None or pattern.startswith(":")
            or any(char in pattern for char in "*?[\\")):
        return True
    while pattern.startswith("./"):
        pattern = pattern[2:]
    pattern = pattern.rstrip("/")
    if pattern in ("", ".") or any(part in ("", ".", "..")
                                   for part in pattern.split("/")):
        return True
    return path == pattern or path.startswith(pattern + "/")


def unfetchable(root: Path, rows: list[dict], exited_0: bool
                ) -> tuple[list[tuple[dict, str, str]], str | None,
                           Gitmodules]:
    """`(row, path, why)` for each row whose member (a) left NOT CHECKED OUT
    where no credential would check it out (#648), in row order; the
    gitlink git's init died at (`init_stop`), or None; and `.gitmodules`
    as it was read, for `cures`.

    Asked of this holder's own records, never of git's words: any row at
    all while a merge leaves `.gitmodules` unmerged in the index, since git
    then reads no section and asks for no credential, or while the file
    gives a value git dies on (`Gitmodules.refused`, #768), or is a work
    tree file git cannot parse (`Gitmodules.unreadable`); a row at
    whose path the holder records no gitlink (`recorded_gitlink`,
    as `validate-family.py`'s `member-gitlink-absent` reads one), or whose
    gitlink no section of `.gitmodules` gives a path (as its
    `member-gitmodules-absent` reads HEAD's file, which is the work tree's
    in a clone); one git has no url for (`has_url`), where no credential
    helps either, whatever git exited; where git exited 0, any row at all,
    since git then lacked nothing a credential gives; and where git's init
    died at a gitlink it has no url for, any row at all, since git then
    checked out no member and asked for no credential. Any other row not
    checked out is the missing credential's, and stays the skip it always
    was. A path two rows give is said once. Where every row's member is
    checked out and git did not exit 0, `.gitmodules` is read all the
    same, and git's init asked where it stopped, for `fetch_members` to
    ask why git updated none (`updated_none`): this returned before
    `init_stop` there, so a run whose update git's init stopped said
    `family bootstrap ok` (#879). A row whose mount cannot be asked is
    refused, `member-unreadable` (`checked_out`, #430)."""
    left: dict[str, dict] = {}
    for row in rows:
        if not checked_out(root, row):
            left.setdefault(row_path(row), row)
    if not left and exited_0:
        return [], None, Gitmodules(Counter(), {}, {})
    modules = gitmodules_sections(root)
    config = submodule_config(root)
    stopper = None if exited_0 else init_stop(root, modules, config)
    found: list[tuple[dict, str, str]] = []
    for path, row in left.items():
        why = row_reason(root, path, modules, config, exited_0, stopper)
        if why is not None:
            found.append((row, path, why))
    return found, stopper, modules


def row_reason(root: Path, path: str, modules: Gitmodules,
               config: dict[str, list[str | None]], exited_0: bool,
               stopper: str | None) -> str | None:
    """Why `unfetchable` says the member at `path`, not checked out, is
    none a credential would check out (#648, #768), in the order it asks,
    or None where it is the missing credential's."""
    unread = file_reason(modules)
    if unread is not None:
        return unread
    if recorded_gitlink(root, path) is None:
        return NO_GITLINK
    if not modules.given[path]:
        return NO_SECTION
    if not has_url(modules, config, path):
        return NO_URL
    if exited_0:
        return EXITED_0
    return None if stopper is None else STOPPED


def file_reason(modules: Gitmodules) -> str | None:
    """Why git read nothing from `.gitmodules` (#648, #768), as (a)'s line
    says it, or None where it read the file: a merge left it unmerged, it
    gives a value git dies on, or it is a work tree file git cannot
    parse."""
    if modules.unmerged:
        return UNMERGED
    if modules.refused:
        return REFUSED
    return UNREADABLE if modules.unreadable else None


def updated_none(stopper: str | None, modules: Gitmodules) -> str | None:
    """Why git updated no member, where every row's member is checked out
    and git did not exit 0, or None: what `file_reason` says, or `STOPPED`
    where git's init in this holder died at a gitlink this holder records
    with no url (`stopper`, `init_stop`), before it updated any (#879).
    None where it asked for a credential, as a leg's fetch does.
    `fetch_members` asks it only where `unfetchable` left no row, whose
    line says why of each, so it asks nothing of the rows (lane 1's NIT 4
    on #889: a check of them here decided nothing)."""
    return file_reason(modules) or (None if stopper is None else STOPPED)


class Below(NamedTuple):
    """Where git's update died past this holder's own records (#892), as
    `stopped_below` finds it. `path` is the gitlink git stopped at, from
    this holder; `owners` the checkouts from this holder's member down to
    the one whose own index records `path`, none where this holder's
    does; `commit` the commit recorded at `path`, where git's fetch there
    reached the remote and did not bring it (B4), and empty where `path`
    is a gitlink its owner's index records with no url (B5)."""

    path: str
    owners: tuple[str, ...]
    commit: str = ""


#: What a checkout answers where git's update stopped at it and why is
#: not told (`walked`): nothing past it is asked, and nothing is said.
UNTOLD = Below("", ())


def stopped_below(root: Path, reached: Reached) -> Below | None:
    """Where git's update, which died (`GIT_DIED`) where `unfetchable`
    left no row and nothing in this holder's own records stopped it, died
    past them (#892), or None where that is not told.

    ASKED AS GIT 2.43 WALKS IT, never of git's words. Git updates the
    gitlinks its init asks about in index order, each in turn, and in
    each one checked out at the commit recorded for it, runs the same
    update, whose init asks every gitlink of that checkout's own index
    first; it dies at the first gitlink it has no url for, or at the
    first commit a fetch did not bring, and that ends every update above
    it (`Failed to recurse`, exit 128). So each gitlink is asked in that
    order (`walked`):
    - one git's update passes without a look (`updated_there`), its
      update strategy `none` or the gitlink inactive, is passed, and
      nothing in it asked: git prints `Skipping submodule` and goes on
      (lane 5's SHOULD 1 on #954);
    - one not checked out is passed, as git passes a clone that failed;
    - one whose `.git` the operating system will not `stat`, or that git
      cannot be run in, is untold (`checkout_stop`, lane 5's SHOULD 2);
    - one whose store lacks its recorded commit (`commit_held`) is the
      stop where a fetch git made there reached the remote (`reached`,
      `fetch_reached`: git's own trace, `fetched_in`, or, with a token in
      use, the two fetches made again, `refetched`, #996), and untold
      where none did, as for want of a credential, or where the run was
      not traced and no token was in use. Git asks whether a ref reaches
      the commit (`is_tip_reachable`) before it fetches, but it dies there
      only where its fetch of the commit fails, and a fetch of a commit
      the store holds is answered from the store (measured, git 2.43.0:
      exit 0), so a commit held and reached by no ref is never the stop;
    - one at another commit than the one recorded, which git did not check
      out there, is untold, nothing in it asked: its `git checkout` there
      refused to overwrite a change, exit 1, which git's update passes, or
      died, exit 128, as on an `index.lock` left in its store, which ends
      git's update there, or a rebase or a merge `update` asks for failed,
      and which it was is not told, so no stop past it is said where git
      may never have come to it (measured, git 2.43.0: where it was
      passed, an `index.lock` in IRRS named B5's stray in IRSS);
    - and one checked out at it is asked as this holder is, its own
      `.gitmodules` and config read as `gitmodules_sections` and
      `submodule_config` read this holder's, and `init_stop` asked of its
      index, then each of its gitlinks. Where git reads that `.gitmodules`
      other than whole, a merge leaving it unmerged, a value git dies on,
      a line it cannot parse, it is untold: git stops there other than at
      a gitlink with no url."""
    found = walked(root, reached, ())
    return found if found is not None and found.path else None


def walked(root: Path, reached: Reached,
           owners: tuple[str, ...]) -> Below | None:
    """`stopped_below` asked of the checkout `root`, which `owners` lead
    to from this holder (none for this holder, whose own records
    `unfetchable` asked): the stop, `UNTOLD`, or None where nothing there
    stops git's update."""
    modules = gitmodules_sections(root)
    config = submodule_config(root)
    if owners:
        if file_reason(modules) is not None or modules.cut:
            return UNTOLD
        stop = init_stop(root, modules, config)
        if stop is not None:
            return Below(f"{owners[-1]}/{stop}", owners)
    prefix = f"{owners[-1]}/" if owners else ""
    for path, commit in init_asks(root, modules, config):
        if not updated_there(root, modules, config, path):
            continue
        found = checkout_stop(root / path, prefix + path, commit, owners,
                              reached)
        if found is not None:
            return found
    return None


def updated_there(root: Path, modules: Gitmodules,
                  config: dict[str, list[str | None]], path: str) -> bool:
    """Whether git's update, its init done, goes on to the gitlink at
    `path`, as `prepare_to_clone_next_submodule` in git 2.43's
    submodule--helper.c asks before it clones, fetches or enters it
    (`walked`, lane 5's SHOULD 1 on #954). Not where no section git reads
    gives that path. Not where its update strategy is `none`: the last
    `submodule.<name>.update` this repository's config gives, else the
    section's own `update` (`Gitmodules.updates`), which git's init copies
    into the config where it holds none. And not where git counts it
    inactive (`is_submodule_active`): where the config sets
    `submodule.active`, `init_asks` asked `active` already; else its own
    `submodule.<name>.active`, where a config scope above the one git's
    init writes `true` in keeps it false (`git_bool`)."""
    name = modules.read.get(path)
    if name is None:
        return False
    values = config.get(f"submodule.{name}.update")
    update = (values[-1] if values and values[-1] is not None
              else (modules.updates or {}).get(name))
    if update == "none":
        return False
    own = config.get(f"submodule.{name}.active")
    return not own or git_bool(root, own[-1]) is not False


def checkout_stop(checkout: Path, where: str, commit: str,
                  owners: tuple[str, ...],
                  reached: Reached) -> Below | None:
    """`walked`'s answer for the gitlink at `where`, recorded at `commit`
    by the last of `owners` (this holder where there is none), whose
    checkout is `checkout`: None where its `.git` is not there, asked as
    `checked_out` asks a member's (`_is_a`, #430); `UNTOLD` where the
    operating system refused that `stat`, or refused a git run in it or
    below it (lane 5's SHOULD 2 on #954: `Path.exists` raised that
    refusal, a traceback, before Python 3.14, and from 3.14 reads it as no
    checkout); else `entered`'s answer."""
    try:
        if not _is_a(checkout / ".git", _anything):
            return None
        return entered(checkout, where, commit, owners, reached)
    except OSError:
        return UNTOLD


def entered(checkout: Path, where: str, commit: str,
            owners: tuple[str, ...],
            reached: Reached) -> Below | None:
    """`checkout_stop`'s answer for a checkout whose `.git` is there: B4
    where its store lacks `commit` and a fetch in it reached the remote
    and did not bring it (`reached`), `UNTOLD` where none did or where it
    is at another commit, and else what `walked` finds in it."""
    if not commit_held(checkout, commit):
        if reached(checkout, commit):
            return Below(where, owners, commit)
        return UNTOLD
    if head_commit(checkout) != commit:
        return UNTOLD
    return walked(checkout, reached, (*owners, where))


def commit_held(checkout: Path, commit: str) -> bool:
    """Whether the store `checkout` reads holds `commit`: `git cat-file -e
    <commit>^{commit}` exits 0. Not whether a ref reaches it, as git's
    update asks before it fetches (`is_tip_reachable`): git's fetch of a
    commit its store holds is answered from the store, so its update does
    not die for want of one (measured, git 2.43.0), and a held commit no
    ref reaches, whose checkout died, was named B4 (#954's round 1)."""
    proc = subprocess.run(["git", "cat-file", "-e", f"{commit}^{{commit}}"],
                          cwd=str(checkout), capture_output=True,
                          check=False)
    return proc.returncode == 0


def head_commit(checkout: Path) -> str | None:
    """The commit `checkout`'s HEAD is at, or None where it is at none."""
    try:
        return git_out(["rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
                       cwd=checkout)
    except Refusal:
        return None


def below_said(below: Below) -> str:
    """(a)'s line, after its lead, for where git's update died past this
    holder's records (`stopped_below`, #892): where git stopped and why,
    then what cures it, which is the repository's that records the
    gitlink, the last of `below.owners` or this holder.

    - A gitlink a member's own index records with no url (B5): no clone of
      that member can check it out. `git -C <owner> rm --cached` takes it
      out of that index, or a section gives it its url; committed and
      pushed there where its HEAD records it, the gitlink that records the
      member moves to that commit: this holder's with its pin (`family.py
      bump`), and a leg's in its member, up to this holder.
    - A commit no fetch brought (B4): pushed to that remote from a clone
      that holds it, or the gitlink moved to one the remote holds, which
      `validate-family.py` names, with the `bump` that moves the pin too,
      where this holder records it, and up to this holder where a member
      does."""
    owner = below.owners[-1] if below.owners else "this holder"
    path, commit = spelled(below.path), below.commit
    if commit:
        tail = (f": `{PYTHON} scripts/validate-family.py` names the `bump` "
                "that moves it with its pin." if not below.owners else
                ", and so on up to this holder.")
        return (f"git stopped at {path}, whose fetch reached its remote and "
                f"did not bring {commit}, the commit {spelled(owner)} "
                f"records there. Push {commit} to that remote from a clone "
                f"that holds it, or move the gitlink {spelled(owner)} "
                f"records there to a commit that remote holds{tail}")
    above = below.owners[-2] if len(below.owners) > 1 else "this holder"
    removal = shlex.join(["git", "-C", owner, "rm", "--cached", "--",
                          below.path[len(owner) + 1:]])
    tail = (", with its pin (`family.py bump`)." if len(below.owners) == 1
            else ", and so on up to this holder.")
    return (f"git stopped at {path}, a gitlink {spelled(owner)}'s own index "
            f"records with no url. No clone of {spelled(owner)} can check it "
            f"out: `{spelled(removal)}` takes it out of that index, or a "
            f"section of its {GITMODULES} can give it its path and url; "
            f"where its HEAD records it, commit that in {spelled(owner)} and "
            f"push it, then move the gitlink {spelled(above)} records for "
            f"{spelled(owner)} to that commit{tail}")


def members_of(root: Path) -> tuple[str, list[dict]]:
    """`(name:, the member rows)` out of `family.yaml`, or a refusal.

    A `family.yaml` whose `stat` the operating system refused is
    `family-manifest-unreadable`, naming it and the cure (#430), never
    `family-manifest-missing`, which Python 3.14 said of it, whose remedy
    sends a person to the wrong kind of root."""
    manifest_path = root / MANIFEST
    try:
        present = _is_a(manifest_path, stat.S_ISREG)
    except OSError as exc:
        raise unreadable(
            "family-manifest-unreadable", MANIFEST, exc,
            f"{MANIFEST} declares this holder's members, and which they are "
            "cannot be told without it.") from exc
    if not present:
        raise Refusal(
            "family-manifest-missing",
            f"{manifest_path} does not exist, so there is no declaration of "
            "which members to bootstrap",
            "Remediation: this command bootstraps a FAMILY holder. A project "
            "runs its own `scripts/bootstrap.py` instead.")
    manifest = load_yaml(manifest_path)
    if not isinstance(manifest, dict):
        raise Refusal("family-manifest-unreadable",
                      f"{manifest_path}: not a mapping")
    name = str(manifest.get("name") or root.name)
    # A `members:` THAT IS NOT A LIST, OR HOLDS AN ENTRY THAT IS NOT A
    # MAPPING, IS REFUSED BY NAME (#864), in `validate-family.py`'s words:
    # read as `members or []`, `5` ended `make bootstrap` and `make siblings`
    # in a `TypeError`, `openXdox` or `[5]` was "0 member(s)" and "family
    # bootstrap ok", and the rows beside a `5` were fetched with the `5`
    # unsaid. Absent or null is a family with no members.
    rows = manifest.get("members")
    if rows is None:
        rows = []
    if not isinstance(rows, list):
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: `members:` is {rows!r}, expected a "
                      "list")
    unread = [f"a member is not a mapping: {row!r}" for row in rows
              if not isinstance(row, dict)]
    if unread:
        raise Refusal("family-members-unreadable",
                      f"{manifest_path}: {'; '.join(unread)}")
    return name, rows


def row_path(row: dict) -> str:
    """The path a row mounts its member at, as the holder spells it."""
    return str(row.get("path")
               or f"{DEFAULT_MEMBERS_DIR}/{row.get('project')}")


def member_path(root: Path, row: dict) -> Path:
    return root / row_path(row)


def run_member_target(root: Path, row: dict, target: str) -> str | None:
    """(b) One member's own `make <target>`. Returns a failure line, or None:
    one naming the exit code of the member's command where make names it,
    else make's own (`run_make`, #839)."""
    # A member row is the family manifest's text (#391): what is PRINTED of it,
    # and of `--members-make`, is spelled. The path is built from the raw row.
    project = spelled(row.get("project") or "?")
    path = member_path(root, row)
    named = spelled(target)
    if not checked_out(root, row):
        print(f"  [{project}] {spelled(path.name)}: NOT CHECKED OUT; skipped. "
              "See the fetch above.")
        return None
    try:
        has_makefile = _is_a(path / "Makefile", stat.S_ISREG)
    except OSError as exc:
        # One it cannot reach is no "no Makefile" (#430), which Python 3.14
        # said of it, and `family bootstrap ok` after.
        raise unreadable(
            "member-unreadable", spelled(f"{row_path(row)}/Makefile"), exc,
            f"`make {named}` was not run in {project}, nor in any member "
            "after it.") from exc
    if not has_makefile:
        print(f"  [{project}] no Makefile; skipped. A member without one is "
              "not misconfigured — it simply has nothing for this command to "
              "call.")
        return None
    make = os.environ.get("MAKE") or shutil.which("make")
    if not make:
        print(f"  [{project}] `make` is not on PATH; skipped.")
        return None
    print(f"  --- {project}: make {named} ---")
    sys.stdout.flush()
    returncode, own = run_make(make, target, path)
    sys.stdout.flush()
    if returncode == 0:
        return None
    if own is not None:
        return f"{project} (make {named}: the member's command exited {own})"
    return (f"{project} (make {named} exited {returncode} and printed no "
            "`Error <code>` line for a command of the member's: make's own "
            "message above says what failed)")


#: What GNU make prints on stderr as a target fails, after its own name
#: and, in a make run by make, its depth (`make[1]:`): `*** [Makefile:44:
#: bootstrap] Error 1` where a command exits non-zero (`*** [bootstrap]
#: Error 1` before make 4.0), with the command's own exit code, which
#: make's does not carry, since make exits 2 for any command that fails
#: (#839); `*** No rule to make target ...`, or `*** [Makefile:44:
#: bootstrap] Killed`, where make fails on its own or a signal ends what it
#: ran, with none; and `[Makefile:44: bootstrap] Error 1 (ignored)`, or
#: `Killed (ignored)` where a signal ended it, with no `***`, where a `-`
#: before a command lets it fail, whatever ended it (#884, #890).
MAKE_FAILED_RE = re.compile(
    rb"(?:\[(\d+)\])?: (?:\*\*\* (?:\[[^\n]*\] Error (\d+)\s*$)?"
    rb"|\[[^\n]*\] [^\n]* \((ignored)\)\s*$)")
#: The bytes `MakeErrors` keeps of a line of make's stderr not yet ended:
#: an `Error <code>` line ends there, so the end of a line is enough.
LINE_KEPT = 4096


class MakeErrors:
    """What `run_make` reads of make's stderr, one line at a time as it
    passes (#884): `code`, that of the last `Error <code>` line make printed
    for a command of the member's (`MAKE_FAILED_RE`, its last match on a
    line, since a member's own text can come before make's on one), or
    None.

    Read as it passes, an `Error` line is never lost to what follows it,
    as one was to more than 4096 bytes after it (`make -k`) where only the
    last 4096 were kept. An `Error 2` at a shallower depth than the last
    `***` line before it, whatever lines come between, is taken for a
    make's parent saying it failed, since make exits 2 for any failure,
    and is passed over: where the member's make runs another (`$(MAKE)
    inner`), the code is the innermost command's, and where the inner make
    failed on its own there is none, as for make's own failure. Where a
    `-` let a command fail (`Error 1 (ignored)`, or `Killed (ignored)`,
    whatever ended it), the make that says so goes on, and would print a
    `***` line of its own if it failed after, so no `Error 2` is passed
    over again until a `***` line comes: a parent's own `Error 2` after a
    make a `-` let fail is named, however far below it the `-` was.

    WHERE THE CODE IS NOT THE INNERMOST COMMAND'S, since make's lines do
    not tell it:
    - a recipe that runs a make and lets its failure pass in the shell
      (`|| true`, or `;`), or with a `-` in a make run with `-s`, which
      prints no `(ignored)` line, then exits 2 itself with no `(ignored)`
      line between: its `Error 2` is read as that make's report, and the
      inner command's code is named;
    - under `-k`, a make a `-` lets fail after a command that failed (`a:
      $(MAKE) innerA`, whose command exits 1, then `b: -$(MAKE) innerB`,
      whose command exits 3): the last `Error` line is the command's in
      the make the `-` let fail, and its code, 3, is named;
    - an inner make run with `env -u MAKELEVEL`, which prints its parent's
      depth: the parent's `Error 2` is named;
    - under `-j`, a job of the parent's that fails while the inner make is
      still running: its line comes between, and the parent's `Error 2` is
      named;
    - a member's own line shaped like a deeper make's (`x[3]: *** y`)
      before it exits 2 itself: its `Error 2` is passed over."""

    def __init__(self) -> None:
        self.code: int | None = None
        self.depth = -1
        self.unended = b""

    def read(self, chunk: bytes) -> None:
        """`chunk` of make's stderr: each line it ends, read
        (`said`)."""
        *ended, unended = (self.unended + chunk).split(b"\n")
        for line in ended:
            self.said(line)
        self.unended = unended[-LINE_KEPT:]

    def said(self, line: bytes) -> None:
        """One line of make's stderr, read for its last `MAKE_FAILED_RE`."""
        found = MAKE_FAILED_RE.findall(line)
        if not found:
            return
        depth_said, code, ignored = found[-1]
        depth = int(depth_said or 0)
        if ignored:
            self.depth = -1
            return
        reports_a_make = code == b"2" and depth < self.depth
        self.depth = depth
        if code and not reports_a_make:
            self.code = int(code)


def run_members(root: Path, rows: list[dict], target: str,
                skip: bool) -> list[str]:
    """(b) Each member's own `make <target>`, in row order: the failure lines
    (`run_member_target`), or none where `skip` (`--skip-members`) or no row
    is declared. Raises `member-unreadable` at the first member whose mount
    or `Makefile` cannot be asked about (#430), and no member after it is
    run: `main` refuses the run there, exit 2."""
    print(f"\n(b) each member's own `make {spelled(target)}`")
    if skip:
        print("  skipped (--skip-members)")
        return []
    if not rows:
        print("  no members declared. A family with none is empty, not wrong: "
              "`family.py add` is what puts one here.")
        return []
    failed = []
    for row in rows:
        failure = run_member_target(root, row, target)
        if failure:
            failed.append(failure)
    return failed


def run_make(make: str, target: str, cwd: Path) -> tuple[int, int | None]:
    """(b) `make <target>` in a member, as `(make's exit code, the exit code
    of the member's command it names)`, the second None where make names
    none (`MakeErrors`, #839, #884).

    MAKE'S OWN CODE TELLS NOTHING APART. GNU make exits 2 for any command
    that fails, measured (GNU Make 4.3) for a command exiting 1, 2, 3 or
    126, and 2 for a failure of its own (`No rule to make target`), so the
    line said `make bootstrap exited 2` for the member's own `bootstrap
    FAILED` (1, a finding), for a refusal (2) and for make's own failure
    alike (w764b, for lane 4). The command's code is the one make names
    in its `Error <code>` line, so make's stderr is passed on to this
    run's own as it comes, and read a line at a time as it passes: the
    last such line names it, or, where the member's make runs another,
    the innermost command's line (`MakeErrors`). A make that prints none,
    one of its own failures, or a make speaking another language, leaves
    make's code alone. So does a command killed by a signal where what
    make started is what was killed: a command make runs with no shell,
    on a line with nothing a shell must read; the shell a `kill -KILL $$`
    kills; or a command bash runs in its own place, a line's last, a line
    of one command included. Make then prints the signal's name, `Killed`
    or `Terminated`, and no code. Where the shell outlives the command, as
    dash, `/bin/sh` on Debian and Ubuntu, does for every command, and bash
    for one that is not a line's last, the shell prints the signal's name
    itself and exits 128 and the signal's number, 137 for SIGKILL and 143
    for SIGTERM, which make names as the member's command's code; where
    the line goes on after it, the shell exits as the rest of the line
    does (#884). The member's command is never run around make:
    another target than `bootstrap` (`--members-make validate`) has no
    script of its own to call, as `make siblings` calls a member's
    `scripts/bootstrap.py`.

    WHAT PASSING STDERR ON CHANGES (#884), measured against a make that
    writes to this run's stderr, a terminal, itself:
    - The member's commands write stderr to a pipe, not a terminal, so a
      test of `isatty(2)` reads false: git shows no progress meter, and a
      command that colours or prompts by that test does neither. Stdin
      and stdout stay this run's own.
    - The member's stdout and stderr lines can come out of order: its
      stderr passes through this run, a little after the stdout written
      beside it.
    - A process a command leaves running with stderr open holds the run
      until it closes it or exits, since the pipe ends only then, and what
      it writes until then is passed on. Reading only until make exits
      would end the run at once, but that process's next write to stderr
      would meet a closed pipe and end it (SIGPIPE), unsaid. A recipe that
      starts one gives it a stderr of its own (`2>log`).
    - The bytes pass on as written, never decoded. On Windows a member's
      Python writes a pipe in the ANSI code page, and this run's stderr, a
      console, reads them as UTF-8, so non-ASCII text comes out garbled
      (read, not run).
    Giving make the terminal back would lose its `Error <code>` line,
    which nothing else make writes carries (`--debug=j` says only
    "Reaping losing child"), and the line would say `exited 2` for every
    failure again."""
    proc = subprocess.Popen([make, target], cwd=str(cwd),
                            stderr=subprocess.PIPE, env=member_make_env())
    errors = MakeErrors()
    for chunk in iter(lambda: proc.stderr.read1(65536), b""):
        passed_on(chunk)
        errors.read(chunk)
    proc.stderr.close()
    return proc.wait(), errors.code


def passed_on(chunk: bytes) -> None:
    """`chunk` of what a member's make wrote to its stderr, written to this
    run's as it came (#839): as its bytes, after what this run wrote there
    before, or as text where stderr has no byte buffer."""
    stream = sys.stderr
    if stream is None:
        return
    stream.flush()
    sink = getattr(stream, "buffer", None)
    if sink is None:
        stream.write(chunk.decode("utf-8", "replace"))
        stream.flush()
        return
    sink.write(chunk)
    sink.flush()


#: A word of `MAKEFLAGS` that names the jobserver of the make above this
#: run (#888): `--jobserver-auth=3,4`, a pipe's two descriptors (GNU make
#: 4.2 on), `--jobserver-auth=fifo:<path>`, a named pipe (4.4 on, where
#: there is `mkfifo`), and `--jobserver-fds=3,4` (before 4.2, as macOS's
#: make 3.81 writes it). `re.DOTALL` here and below, since a path may hold
#: any character.
JOBSERVER_WORD = re.compile(r"--jobserver-(?:auth|fds)=.*", re.DOTALL)
#: The words `member_make_env` takes out where one names a jobserver: that
#: word, and the jobs that come with it, `-j2`, or the bare `-j` a make
#: before 4.2 writes beside `--jobserver-fds`.
JOBS_WORD = re.compile(r"-j[0-9]*|--jobserver-(?:auth|fds)=.*", re.DOTALL)
#: A word of `MAKEFLAGS` as make splits it: only at a space or a tab, and
#: a backslash keeps the character after it in the word, a space or a tab
#: included (`ARGS=a\ -j2` is one word). Any other character, a newline
#: or a no-break space among them, is part of its word, as make reads it.
MAKEFLAGS_WORD = re.compile(r"(?:\\.|[^ \t])+", re.DOTALL)


def member_make_env() -> dict[str, str]:
    """This run's environment for a member's make: `MAKEFLAGS` without the
    jobserver of the make above this run, where it names one, and without
    the `-j` that comes with it (`JOBS_WORD`, #888). Every other word is
    kept, `-k`, `-s` and a variable given on the holder's command line
    among them, each word as make splits it: only at a space or a tab,
    a backslash keeping either in a value (`MAKEFLAGS_WORD`). A
    `MAKEFLAGS` that names no jobserver is left as it is: `make -j` with
    no number, which starts none, or a person's own `MAKEFLAGS=-j8` with
    no make above this run.

    WHY. Under the holder's `make -j2 bootstrap`, `validate`, `park` or
    `resume`, a member's make found `-j2 --jobserver-auth=3,4` in the
    `MAKEFLAGS` it inherits, and not the two descriptors: the holder's
    rule runs this script with no `+`, so make closes them for it, and
    `Popen` closes every descriptor past stderr. It printed `make[1]:
    warning: jobserver unavailable: using -j1.  Add '+' to parent make
    rule.`, of a rule the person does not own, and ran its jobs one at a
    time (GNU Make 4.3, measured). It runs them one at a time now, and
    says nothing.

    WHY NOT HAND THE JOBSERVER ON, as a `+` on the holder's rules and the
    descriptors passed to the member's make would, which then ran its
    jobs together (measured):
    - a `+` runs its line under `make -n` too: `make -n bootstrap`
      fetched every member and leg (measured);
    - a descriptor `MAKEFLAGS` names is a number, and no proof that it is
      the jobserver's: with a file open there, a member's make read a
      byte of it for a token and wrote a `+` into another (measured);
    - the member's make is `$MAKE` or `make` on PATH, not the make that
      ran the holder, which exports no `MAKE` (measured), and a make may
      not read another's jobserver: GNU make 4.3 stops at 4.4's `fifo:`
      (`invalid --jobserver-auth string`, measured).
    Taken out, no make is asked to read a jobserver at all."""
    env = dict(os.environ)
    words = MAKEFLAGS_WORD.findall(env.get("MAKEFLAGS", ""))
    if any(JOBSERVER_WORD.fullmatch(word) for word in words):
        env["MAKEFLAGS"] = " ".join(
            word for word in words if not JOBS_WORD.fullmatch(word))
    return env


def main(argv: list[str] | None = None) -> int:
    escape_unencodable_stdout()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument("--no-fetch", action="store_true",
                        help="skip step (a); the members are already there "
                             "(what `make validate` passes)")
    parser.add_argument("--members-make", default="bootstrap", metavar="TARGET",
                        help="the make target to run in each member "
                             "(default: bootstrap)")
    parser.add_argument("--skip-members", action="store_true",
                        help="fetch only; run nothing in the members")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
        name, rows = members_of(root)
    except Refusal as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"bootstrap: {spelled(name)} ({spelled(root)}) — "
          f"{len(rows)} member(s)")

    print("\n(a) members and their legs")
    failed: list[str] = []
    try:
        if args.no_fetch:
            print("  skipped (--no-fetch)")
        else:
            failed += fetch_members(root, rows)
        failed += run_members(root, rows, args.members_make,
                              args.skip_members)
    except Refusal as exc:
        # `git-not-runnable` from (a) (#694), or `member-unreadable` from
        # (a) or (b) (#430). Stdout first, so a log of both streams reads
        # in the order the run went.
        sys.stdout.flush()
        print(str(exc), file=sys.stderr)
        return 2

    print()
    if failed:
        print("family bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("family bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
