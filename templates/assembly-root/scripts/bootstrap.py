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
      validator names the key when the manifest holds it. Advancing a pin
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

  (d) EXITS 0 unless a validator failed, and 2 where step (a) or the
      upstream notice cannot start git, refused `git-not-runnable` as the
      validators refuse it (#694).

SCHEMA-NEUTRAL BY CONTRACT. A one-repository project runs the same command:
step (a) is a no-op where there are no submodules, and steps (c) and (d) are
unchanged. A bootstrap that existed only for electing projects would make the
election worth something operationally, which is exactly what the ratified
doctrine forbids.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
from collections.abc import Iterator
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
#: What a cherry-pick or a revert of SEVERAL commits leaves while it is not
#: done, asked after `IN_PROGRESS`: its stop committed by hand takes the
#: head file away and leaves this, whose first word says which it is.
SEQUENCER_TODO = "sequencer/todo"
#: The remedy of the `git-not-runnable` refusal (#694).
GIT_NOT_RUNNABLE = (
    "Remediation: put git on PATH and run this again. Step (a) reads each "
    "leg's pin and moves the leg through git, and the validators read the "
    "pins through git, so without it nothing here can be placed or checked.")
REGISTER_RELPATH = Path("governance") / "review-authority" / "register.yaml"
VALIDATORS = (
    ("naming", ["scripts/validate-repository-naming.py", "--project",
                "project.yaml", "--quiet"]),
    ("manifest", ["scripts/validate-manifest.py"]),
    ("pins", ["scripts/validate-pins.py"]),
)


def _run(root: Path, args: list[str]) -> int:
    # Flush first: this process's own stdout is block-buffered when it is a
    # pipe, and a child writing straight to the fd would otherwise appear
    # BEFORE the heading that introduces it.
    sys.stdout.flush()
    proc = subprocess.run([sys.executable, *args], cwd=str(root), check=False)
    sys.stdout.flush()
    return proc.returncode


def _try_git(args: list[str], cwd: Path) -> str | None:
    try:
        return git_out(args, cwd=cwd)
    except Refusal:
        return None


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
    branch as detached. Only a NUL and a lone surrogate are looked for; a
    character the system's encoding merely lacks is not this fix's.

    A surrogate that is ONE BYTE of a name is not refused. POSIX spells a name
    that is not UTF-8 with U+DC80 to U+DCFF and `os.fsencode` writes each back
    as the single byte it stands for, so git is handed that byte, as it was
    before this check. Any other surrogate has no byte: `os.fsencode` raises,
    or (`surrogatepass`, Windows) writes the three bytes of a sequence that
    is not UTF-8 for ANY of them, so a lone surrogate is never handed to git
    there either, where a `CreateProcess` would pass it on mangled. The answer
    is `os.fsencode`'s own, so it is the system's and not a list kept here.
    """
    for char in branch:
        if char == "\x00":
            return "U+0000, a NUL"
        if "\ud800" <= char <= "\udfff" and _fsencoded_length(char) != 1:
            return f"U+{ord(char):04X}, a lone surrogate"
    return None


def _fsencoded_length(char: str) -> int:
    """How many bytes `os.fsencode` writes for `char`; 0 when it cannot."""
    try:
        return len(os.fsencode(char))
    except UnicodeEncodeError:
        return 0


def _say_not_tried(where: str, named: str, fault: str) -> None:
    """A branch `_argument_fault` found: no command was run with it. The leg
    stays where it is, and the line says which of the three places the
    person's value can have come from holds it (#455)."""
    print(f"  {where}: could not create branch {named}: it holds {fault}, "
          "which no command can be given as an argument; the leg is left as "
          "it is")
    print("          the branch is the leg's `branch:`, else `--branch`, else "
          "`tracking_branch`. Give that one a name git can create and run "
          "bootstrap again.")


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
    takes the branch after `refs/heads/`, where git reads no option.
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


def _in_progress(sub: Path) -> tuple[str, str, str] | None:
    """The `IN_PROGRESS` row of the operation git has in progress in the
    leg, or `None` (#704).

    Asked of the leg's own git dir, which `git rev-parse --git-dir` names
    (a submodule's is under the root's `.git/modules/`, a linked
    worktree's under the leg's `worktrees/`, and each operation's state is
    that worktree's own). Read as bytes and decoded as the system decodes a
    path, so no name of a directory can fail the read. A leg git names no
    git dir for has nothing to read here, and the move after this says what
    git says of it.
    """
    try:
        said = git_out(["rev-parse", "--git-dir"], cwd=sub, binary=True)
    except Refusal:
        return None
    gitdir = sub / os.fsdecode(said.rstrip(b"\r\n"))
    for row in IN_PROGRESS:
        if os.path.lexists(gitdir / row[0]):
            return row
    return _sequence_in_progress(gitdir)


def _sequence_in_progress(gitdir: Path) -> tuple[str, str, str] | None:
    """A cherry-pick or a revert of several commits that is not done, or
    `None` (rv704's S1 on #704).

    `git cherry-pick A B` stops on a conflict in A, the person resolves it
    and commits by hand: `CHERRY_PICK_HEAD` is gone, and `git status` still
    says `Cherry-pick currently in progress.` and to run `git cherry-pick
    --continue`, which picks B onto wherever HEAD is by then. A move onto
    the tracking branch put B there. `sequencer/todo` is what is left, and
    its first word is `revert` for a revert and `pick` for a cherry-pick;
    a file that cannot be read is taken as the cherry-pick, the commoner."""
    todo = gitdir / SEQUENCER_TODO
    if not os.path.lexists(todo):
        return None
    try:
        first = todo.read_bytes().split(None, 1)[:1]
    except OSError:
        first = []
    if first == [b"revert"]:
        return SEQUENCER_TODO, "a revert", "revert"
    return SEQUENCER_TODO, "a cherry-pick", "cherry-pick"


def _say_in_progress(label: str, path: str,
                     row: tuple[str, str, str]) -> None:
    """A leg with an operation in progress (#704): what is in progress,
    that nothing moved, and the two commands that end it, the leg's path
    shell-quoted, then spelled, as `move_back_to_pin` prints its command.

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
          "git dir), so nothing moved")
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
    chosen (`_say_in_progress`, #704), so no move below meets one."""
    path = str(leg.get("path") or "")
    sub = root / path
    # What is PRINTED of the leg is spelled (#391): `role`, `path` and `branch`
    # are the manifest's text, read before any validator has had its say.
    where = f"[{spelled(leg.get('role'))}] {spelled(path)}"
    named = spelled(branch)
    if not (sub / ".git").exists():
        print(f"  {where}: NOT INITIALIZED. Run "
              f"`git submodule update --init {spelled(path)}` — the "
              f"validators below will refuse until you do.")
        return
    fault = _argument_fault(branch)
    if fault is not None:
        _say_not_tried(where, named, fault)
        return
    pin = recorded_gitlink(root, path)
    local = _try_git(["rev-parse", "--verify", "--quiet",
                      f"refs/heads/{branch}"], sub)
    remote = _try_git(["rev-parse", "--verify", "--quiet",
                       f"refs/remotes/origin/{branch}"], sub)
    doing = _in_progress(sub)
    if doing is not None:
        _say_in_progress(where, path, doing)
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
    """
    pin_path = root / "contracts" / "shape-pin.yaml"
    if not pin_path.is_file():
        return
    try:
        pin = load_yaml(pin_path)
    except Refusal:
        return
    pinned = str((pin or {}).get("commit") or "").lower()
    if not COMMIT_40.match(pinned):
        return
    tip = None
    upstream = os.environ.get(SHAPE_UPSTREAM_ENV)
    if upstream and Path(upstream).is_dir():
        with _git_runs(f"the clone {SHAPE_UPSTREAM_ENV} names, "
                       f"{spelled(upstream)}, could not be read"):
            tip = _try_git(["rev-parse", "HEAD"], Path(upstream))
    if tip is None:
        cache = root / SHAPE_UPSTREAM_CACHE
        if cache.is_file():
            tip = cache.read_text(encoding="utf-8").strip()
    if not tip or not COMMIT_40.match(tip):
        return
    if tip.lower() == pinned:
        return
    print(f"  shape: the upstream is at {tip[:12]} and this project is pinned "
          f"at {pinned[:12]}. Run openRepoShape's "
          f"`update-shape.py check --root .` to see what moved; nothing here "
          f"is wrong until you have.")


def _register_paths(root: Path, legs: list[dict]) -> list[Path]:
    candidates = [root / REGISTER_RELPATH]
    for leg in legs:
        path = str(leg.get("path") or "")
        if path and path != ".":
            candidates.append(root / path / REGISTER_RELPATH)
    return [c for c in candidates if c.is_file()]


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


def _load_register_rows(register_path: Path) -> list[dict] | None:
    """One register file's rows, tolerant of which key holds them.

    Split from `read_authority` for #132. Returns `None` when the file
    itself could not be read — already printed in that case — so the
    caller's loop moves on to the next register file exactly as the
    original loop's `continue` did.
    """
    try:
        data = load_yaml(register_path)
    except Refusal as exc:
        print("    unreadable, so nothing is claimed from it: "
              f"{spelled(exc.detail)}")
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
    rows = _load_register_rows(register_path)
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
    """
    root = find_repo_root(args.root or Path(__file__).resolve().parents[1])
    manifest_path = root / "project.yaml"
    manifest: dict | None = None
    if manifest_path.is_file():
        loaded = load_yaml(manifest_path)
        manifest = loaded if isinstance(loaded, dict) else None
    return root, manifest


def _checkout_all_tracking_branches(root: Path, sub_legs: list[dict],
                                    manifest: dict | None,
                                    branch_arg: str | None) -> None:
    """Step (a): place every submodule leg on its tracking branch.

    Split from `main` for #132. Git that cannot be started is
    `git-not-runnable`, naming the leg it met it at (#694): one fact about
    the machine, so no leg after it is tried.
    """
    if not sub_legs:
        print("  no submodule legs declared. A one-repository project runs "
              "the same command and this step is a no-op.")
        return
    branch = branch_arg or (manifest or {}).get("tracking_branch") or "main"
    for leg in sub_legs:
        with _git_runs(f"the {spelled(leg.get('role'))} leg at "
                       f"{spelled(leg.get('path') or '')} could not be "
                       "placed on its tracking branch"):
            checkout_tracking_branch(root, leg,
                                     str(leg.get("branch") or branch))


def _run_neutral_validators(root: Path, manifest: dict | None,
                            skip: bool) -> list[str]:
    """Step (b): run the neutral validators, then the upstream notice.

    Split from `main` for #132. Returns the labels of any validator that
    failed, exactly as `main`'s local `failed` list used to accumulate them.
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
    for label, argv_ in VALIDATORS:
        if not (root / argv_[0]).is_file():
            print(f"  {label}: {argv_[0]} is absent; SKIPPED")
            continue
        print(f"  --- {label} ---")
        code = _run(root, argv_)
        if code != 0:
            failed.append(f"{label} (exit {code})")
    shape_upstream_notice(root)
    return failed


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

    legs = [leg for leg in ((manifest or {}).get("legs") or [])
            if isinstance(leg, dict)]
    sub_legs = [leg for leg in legs if leg.get("role") != "assembly"]

    name = (manifest or {}).get("name") or root.name
    print(f"bootstrap: {spelled(name)} ({spelled(root)})")

    try:
        print("\n(a) legs on tracking branches, pins untouched")
        _checkout_all_tracking_branches(root, sub_legs, manifest, args.branch)

        print("\n(b) neutral validators")
        failed = _run_neutral_validators(root, manifest, args.skip_validators)
    except Refusal as exc:
        # Only `git-not-runnable` reaches here (#694): nothing else in the
        # two steps raises one. Stdout first, so a log of both streams
        # reads in the order the run went.
        sys.stdout.flush()
        print(str(exc), file=sys.stderr)
        return 2

    print("\n(c) review authority")
    read_authority(root, legs)

    print()
    if failed:
        print("bootstrap FAILED: " + ", ".join(failed), file=sys.stderr)
        return 1
    print("bootstrap ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
