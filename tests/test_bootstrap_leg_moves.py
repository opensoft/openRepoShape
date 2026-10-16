# SPDX-License-Identifier: Apache-2.0
"""`make bootstrap` moves a leg only where nothing the person has is lost, and
reads every HEAD one way (#704).

THE ISSUE'S LINES, each measured on lane 5's #682 head (8b39cd19, git 2.43.0)
before this change, in a scaffold's recursive clone bootstrapped once:

- LINE 1. Every move that changes files overwrote an IGNORED file at a path
  the pin tracks, silently: the checkout of the branch AT the pin from another
  branch (P9, `place_at_pin`), the checkout of the branch moved from BEHIND the
  pin (T7, `fast_forward_to_pin`), the `merge --ff-only` of a branch behind the
  pin with HEAD on it, and the `checkout -b` of a branch that is not there. A
  `README.md` the leg's `info/exclude` lists, holding the person's notes, was
  the pin's `README.md` after each, under `on main at <pin>`. Each now carries
  `--no-overwrite-ignore`, so git refuses it as it refuses an untracked file,
  in its own words, and the leg stays where it is.
- LINE 2. A merge, a cherry-pick or a revert in progress on the branch HEAD
  left was ENDED by each of those moves: its head file (`MERGE_HEAD`,
  `CHERRY_PICK_HEAD`, `REVERT_HEAD`) removed and what it had staged carried
  onto `main`. A merge was ended from HEAD detached at the pin, from HEAD
  already on `main` at the pin (a checkout that moves nothing) and by the move
  back of a branch past the pin, too; a rebase or an `am` stopped there was
  put on `main`, to go on over it. Brett Heap's R1 (2026-10-16T13:07:34Z): a
  leg in the way of a move REFUSES. A leg whose git dir holds any of the
  five markers is refused before any path is chosen, naming the operation,
  saying nothing moved, and giving the commands that finish or abort it.
- LINE 5. A HEAD that is a symbolic ref outside `refs/heads/` (`git
  symbolic-ref HEAD refs/remotes/origin/main`) was placed by P9 and the
  missing-branch path and left by T7 (`which is neither`). The issue's
  recommended answer: every path leaves it, since a commit made there lands
  on that ref.

Lines 3 and 4 are elsewhere: P9's line naming the branch it left is in
`tests/test_bootstrap_after_bump.py` (its other-branch tests, now reading
the line), and line 4 is the narrowed sentence in `AGENTS-shape.md` (R2).

Every state is made the way a person makes it, with git's own commands in the
leg, and every way out is run as printed, from the root.
"""

from __future__ import annotations

import itertools
import shlex
from pathlib import Path

import pytest

from conftest import git
from test_bootstrap_after_bump import (  # noqa: F401
    ADDED, EDITED, MAIN, NOTHING_ELSE, bootstrapped, bumped, head_ref,
    moved_and_refused, rev, root, skip_validators,
)

#: The pin's tracked file the branch `other` deletes, so that checking the
#: tracking branch out from `other` writes it.
IN_THE_WAY = "README.md"
#: What the person keeps in the ignored file.
MINE = b"MY LOCAL NOTES\n"
#: The three paths of the issue, by the state of `main` beside the pin.
PATHS = pytest.mark.parametrize("path", ["at", "behind", "missing"],
                                ids=["P9 at the pin", "T7 behind the pin",
                                     "missing branch"])
#: A branch name per `bumped` call: each pushes to the module's spec remote.
#: Not `tmp_path.name`, which a passed test's removal hands to the next one.
ADVANCES = itertools.count()


def keep(options: str) -> str:
    """The line under a checkout step (a) will not move off."""
    return ("          not moving the checkout off it. Keep any commit made "
            f"there on a branch, check out {options} in the leg, and run "
            "bootstrap again.\n")


def tracking(root: Path, remotes: Path, tmp_path: Path, path: str,
             touch: str | None = None) -> tuple[str, str]:
    """`main` as `path` names it, with the leg left DETACHED at the pin:
    AT the pin (P9: the bootstrapped clone's own state), BEHIND it (T7: a
    bump, `bumped`, with `touch` as it takes it) or NOT THERE (the missing-
    branch path). Returns the pin and the commit a branch made beside
    `main` starts from: `main`'s own, or the pin where there is none."""
    leg = root / "spec"
    if path == "behind":
        start = rev(leg, MAIN)
        pin = bumped(root, remotes, tmp_path, f"moves-{next(ADVANCES)}",
                     touch)
        return pin, start
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    if path == "missing":
        git("branch", "-q", "-D", "main", cwd=leg)
    return pin, pin


def main_of(leg: Path) -> str | None:
    """`main`'s commit, or None where the leg has no `main`."""
    return git("rev-parse", "--verify", "--quiet", MAIN, cwd=leg,
               check=False).stdout.strip() or None


def ignore(leg: Path, name: str) -> None:
    """`name` listed in the leg's own `info/exclude`, a person's ignore
    that no commit carries, and the person's bytes written there."""
    exclude = leg / git("rev-parse", "--git-path", "info/exclude",
                        cwd=leg).stdout.strip()
    listed = exclude.read_bytes() if exclude.is_file() else b""
    exclude.parent.mkdir(exist_ok=True)
    exclude.write_bytes(listed + name.encode("utf-8") + b"\n")
    (leg / name).write_bytes(MINE)


def snapshot(leg: Path) -> tuple:
    """Where the leg is: HEAD's ref and commit, `main`, and the status."""
    return (head_ref(leg), rev(leg), main_of(leg),
            git("status", "--porcelain", cwd=leg).stdout)


def placed_once_cleared(root: Path, pin: str) -> None:
    """The way out works: a run after it puts the leg on `main` AT the
    pin."""
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert head_ref(root / "spec") == MAIN, again.stdout
    assert rev(root / "spec") == pin, again.stdout


# --- line 1: an ignored file in the way is refused on every path ------------

def refused_first_line(path: str, pin: str, start: str) -> str:
    """What step (a) prints first over a move git refused, by path."""
    if path == "at":
        return (f"  [spec] spec: branch main is at the pin {pin[:12]}, and "
                "git refused to check it out:\n")
    if path == "behind":
        return moved_and_refused(start, pin)
    return (f"  [spec] spec: could not create branch 'main' at the pin "
            f"{pin[:12]}; leaving it on other\n")


@PATHS
def test_an_ignored_file_a_move_off_another_branch_writes_is_refused(
        root, bootstrapped, tmp_path, path):
    """HEAD on `other`, a branch that deleted `README.md`, which the pin
    tracks, and the person's own `README.md` ignored there. The checkout
    of `main` wrote the pin's over it (P9, the issue's own measure; T7; the
    missing branch's `checkout -b`). Git now refuses it in its own words,
    the file is the person's still, and HEAD stays on `other`. T7's
    `branch -f` has moved `main` to the pin by then, as over an untracked
    file, and says so; the next run meets P9's state."""
    pin, start = tracking(root, bootstrapped["remotes"], tmp_path, path)
    leg = root / "spec"
    git("checkout", "-q", "-b", "other", start, cwd=leg)
    git("rm", "-q", "--", IN_THE_WAY, cwd=leg)
    git("commit", "-q", "-m", "other keeps no README", cwd=leg)
    ignore(leg, IN_THE_WAY)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert refused_first_line(path, pin, start) in result.stdout, (
        result.stdout)
    assert f"          {IN_THE_WAY}\n" in result.stdout, "git names the file"
    assert NOTHING_ELSE in result.stdout
    assert (leg / IN_THE_WAY).read_bytes() == MINE, "the file is the person's"
    assert head_ref(leg) == "refs/heads/other", "HEAD stays on `other`"
    assert main_of(leg) == {"at": pin, "behind": pin, "missing": None}[path]

    (leg / IN_THE_WAY).unlink()
    placed_once_cleared(root, pin)


def test_an_ignored_file_the_fast_forward_writes_is_refused(
        root, bootstrapped, tmp_path):
    """T7 with HEAD ON `main` behind the pin: `merge --ff-only` wrote the
    pin's `NEW-CONTRACT.md` over the person's ignored one and said
    `fast-forwarded`. It now refuses, and `main` stays where it was."""
    pin, start = tracking(root, bootstrapped["remotes"], tmp_path, "behind")
    leg = root / "spec"
    git("checkout", "-q", "main", cwd=leg)
    ignore(leg, ADDED)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"  [spec] spec: branch main tip {start[:12]} is behind the PIN "
            f"{pin[:12]}, and git refused to move it:\n") in result.stdout, (
        result.stdout)
    assert f"          {ADDED}\n" in result.stdout, "git names the file"
    assert NOTHING_ELSE in result.stdout
    assert (leg / ADDED).read_bytes() == MINE
    assert head_ref(leg) == MAIN
    assert rev(leg) == start, "`main` is not moved"

    (leg / ADDED).unlink()
    placed_once_cleared(root, pin)


# --- line 2: an operation in progress is refused before any move ------------

def theirs(leg: Path, start: str) -> None:
    """A branch `theirs` from `start`, one commit adding `b.txt`; HEAD is
    left on it."""
    git("checkout", "-q", "-b", "theirs", start, cwd=leg)
    (leg / "b.txt").write_bytes(b"b\n")
    git("add", "--", "b.txt", cwd=leg)
    git("commit", "-q", "-m", "theirs", cwd=leg)


def merge_theirs(leg: Path) -> None:
    """`theirs` merged where HEAD is, `--no-commit --no-ff`: `MERGE_HEAD`,
    and `b.txt` staged."""
    git("merge", "-q", "--no-commit", "--no-ff", "theirs", cwd=leg)


def merging(leg: Path, start: str) -> None:
    """`other` from `start`, merging `theirs`."""
    theirs(leg, start)
    git("checkout", "-q", "-b", "other", start, cwd=leg)
    merge_theirs(leg)


def cherry_picking(leg: Path, start: str) -> None:
    """`other` from `start`, picking `theirs`'s second commit, which changes
    the README its first one wrote: a conflict, resolved and staged, so
    `CHERRY_PICK_HEAD` is there and nothing is unmerged."""
    git("checkout", "-q", "-b", "theirs", start, cwd=leg)
    for text in (b"first\n", b"second\n"):
        (leg / EDITED).write_bytes(text)
        git("commit", "-q", "-am", text.decode().strip(), cwd=leg)
    pick = rev(leg)
    git("checkout", "-q", "-b", "other", start, cwd=leg)
    assert git("cherry-pick", pick, cwd=leg, check=False).returncode != 0
    (leg / EDITED).write_bytes(b"resolved\n")
    git("add", "--", EDITED, cwd=leg)


def reverting(leg: Path, start: str) -> None:
    """`other` from `start` with a commit adding `y.txt`, reverted with
    `--no-commit`: `REVERT_HEAD`, and the deletion staged."""
    git("checkout", "-q", "-b", "other", start, cwd=leg)
    (leg / "y.txt").write_bytes(b"y\n")
    git("add", "--", "y.txt", cwd=leg)
    git("commit", "-q", "-m", "y", cwd=leg)
    git("revert", "--no-commit", "HEAD", cwd=leg)


#: Each operation: what makes it, the marker, what the line calls it, and
#: the git command that ends it.
OPERATIONS = {
    "merge": (merging, "MERGE_HEAD", "a merge", "merge"),
    "cherry-pick": (cherry_picking, "CHERRY_PICK_HEAD", "a cherry-pick",
                    "cherry-pick"),
    "revert": (reverting, "REVERT_HEAD", "a revert", "revert"),
    "rebase": (None, "rebase-merge", "a rebase", "rebase"),
    "rebase --apply": (None, "rebase-apply", "a rebase", "rebase"),
    "am": (None, "rebase-apply/applying", "an `am`", "am"),
}


def in_progress(operation: str) -> str:
    """The two lines step (a) prints for a leg with `operation` in progress
    (#704), byte for byte."""
    _, marker, doing, verb = OPERATIONS[operation]
    return (f"  [spec] spec: {doing} is in progress in the leg ({marker} is "
            "in its git dir), so nothing moved\n"
            f"          finish it (`git -C spec {verb} --continue`) or abort "
            f"it (`git -C spec {verb} --abort`), then run bootstrap again.\n")


def refused_until_aborted(root: Path, operation: str, pin: str) -> None:
    """Bootstrap refuses the leg as `in_progress` says and nothing moves:
    HEAD, `main`, the index and the operation's marker are as they were.
    Then the `--abort` the line names, run as printed from the root, and a
    run after it places the leg at the pin."""
    leg = root / "spec"
    marker = OPERATIONS[operation][1]
    gitdir = leg / git("rev-parse", "--git-dir", cwd=leg).stdout.strip()
    before = snapshot(leg)
    assert (gitdir / marker).exists(), f"{operation} is in progress"

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert in_progress(operation) in result.stdout, result.stdout
    assert snapshot(leg) == before, "nothing moved"
    assert (gitdir / marker).exists(), f"the {operation} goes on"

    # The `--abort` of the second line, which is in the output as it is in
    # `in_progress`: the fourth span of backticks there.
    abort = in_progress(operation).splitlines()[1].split("`")[3]
    assert abort.endswith(" --abort"), abort
    git(*shlex.split(abort)[1:], cwd=root)
    placed_once_cleared(root, pin)


@PATHS
@pytest.mark.parametrize("operation", ["merge", "cherry-pick", "revert"])
def test_an_operation_in_progress_on_the_branch_a_move_leaves_is_refused(
        root, bootstrapped, tmp_path, path, operation):
    """HEAD on `other` with a merge, a cherry-pick or a revert in progress
    there, on each of the three paths that check `main` out from another
    branch. Each move ENDED it: the head file gone, the staged result on
    `main`, and `on main` or `fast-forwarded` or `created` said over it."""
    pin, start = tracking(root, bootstrapped["remotes"], tmp_path, path)
    OPERATIONS[operation][0](root / "spec", start)
    refused_until_aborted(root, operation, pin)


def detached_at_the_pin(root: Path, remotes: Path, tmp_path: Path) -> str:
    """HEAD detached AT the pin, `main` there too (P9 from the pin)."""
    return tracking(root, remotes, tmp_path, "at")[0]


def on_main_at_the_pin(root: Path, remotes: Path, tmp_path: Path) -> str:
    """HEAD ON `main` AT the pin: the leg already placed, where a checkout
    of `main` moves nothing and still ends the merge."""
    pin = rev(root / "spec")
    assert head_ref(root / "spec") == MAIN
    return pin


def past_the_pin(root: Path, remotes: Path, tmp_path: Path) -> str:
    """`main` at `origin/main` one commit PAST the pin, HEAD detached at the
    pin: `move_back_to_pin`'s state, a fresh clone of a leg that moved on."""
    leg = root / "spec"
    pin = rev(leg)
    ahead = git("commit-tree", rev(leg, f"{pin}^{{tree}}"), "-p", pin, "-m",
                "the remote moved on", cwd=leg).stdout.strip()
    git("update-ref", "refs/remotes/origin/main", ahead, cwd=leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-f", "main", ahead, cwd=leg)
    return pin


@pytest.mark.parametrize("state", [detached_at_the_pin, on_main_at_the_pin,
                                   past_the_pin],
                         ids=["detached at the pin", "on main at the pin",
                              "main past the pin"])
def test_a_merge_in_progress_where_no_branch_is_left_is_not_ended_either(
        root, bootstrapped, tmp_path, state):
    """A merge started where HEAD already is: detached at the pin, on `main`
    at the pin, and detached at the pin under a `main` the move back takes
    to the pin. The checkout ended it from all three, though none leaves a
    branch: git's checkout drops `MERGE_HEAD` whenever it runs."""
    pin = state(root, bootstrapped["remotes"], tmp_path)
    leg = root / "spec"
    where = head_ref(leg)
    theirs(leg, pin)
    git("checkout", "-q", *(["main"] if where == MAIN else ["--detach", pin]),
        cwd=leg)
    merge_theirs(leg)
    refused_until_aborted(root, "merge", pin)


def rebased(leg: Path, pin: str, start: str, *backend: str) -> None:
    """`mine` from `start`, changing the README the pin changes too, rebased
    onto the pin: it stops on the conflict with HEAD detached AT the pin,
    resolved and staged."""
    git("checkout", "-q", "-b", "mine", start, cwd=leg)
    (leg / EDITED).write_bytes(b"mine\n")
    git("commit", "-q", "-am", "mine", cwd=leg)
    assert git("rebase", "-q", *backend, pin, cwd=leg,
               check=False).returncode != 0
    assert head_ref(leg) is None and rev(leg) == pin
    (leg / EDITED).write_bytes(b"resolved\n")
    git("add", "--", EDITED, cwd=leg)


def applied(leg: Path, pin: str, start: str, tmp_path: Path) -> None:
    """`other` at the pin, applying with `am -3` a patch made beside it that
    changes the README the pin changes: it stops on the conflict, resolved
    and staged, with HEAD on `other`."""
    git("checkout", "-q", "-b", "theirs", start, cwd=leg)
    (leg / EDITED).write_bytes(b"theirs\n")
    git("commit", "-q", "-am", "theirs", cwd=leg)
    patch = tmp_path / "theirs.patch"
    patch.write_bytes(git("format-patch", "-1", "--stdout", "HEAD",
                          cwd=leg).stdout.encode("utf-8"))
    git("checkout", "-q", "-b", "other", pin, cwd=leg)
    assert git("am", "-q", "-3", str(patch), cwd=leg,
               check=False).returncode != 0
    (leg / EDITED).write_bytes(b"resolved\n")
    git("add", "--", EDITED, cwd=leg)


@pytest.mark.parametrize("operation", ["rebase", "rebase --apply", "am"])
def test_a_rebase_or_an_am_stopped_in_the_leg_is_not_moved_onto_main(
        root, bootstrapped, tmp_path, operation):
    """A rebase stopped with HEAD detached AT the pin (either backend), and
    an `am` stopped on another branch, each over a conflict resolved and
    staged. The checkout of `main` was made and the operation was left in
    progress over it, its `--continue` then committing onto `main`. The pin
    changes the README (`touch`), and `main` is moved to it, as a pull in
    the leg would: the branch-at-the-pin state."""
    pin, start = tracking(root, bootstrapped["remotes"], tmp_path, "behind",
                          touch=EDITED)
    leg = root / "spec"
    git("branch", "-q", "-f", "main", pin, cwd=leg)
    if operation == "am":
        applied(leg, pin, start, tmp_path)
    else:
        rebased(leg, pin, start, *(["--apply"] if "apply" in operation
                                   else []))
    refused_until_aborted(root, operation, pin)


# --- line 5: a HEAD on a ref outside refs/heads/ is left by every path ------

@PATHS
def test_a_head_on_a_remote_tracking_ref_is_left_where_it_is(
        root, bootstrapped, tmp_path, path):
    """`git symbolic-ref HEAD refs/remotes/origin/main`, at `main`'s commit
    or the pin's where there is no `main`. P9 placed the leg (`on main`) and
    the missing-branch path made `main` there, while T7 said `which is
    neither` of the same HEAD. Every path leaves it now, as T7 did."""
    pin, start = tracking(root, bootstrapped["remotes"], tmp_path, path)
    leg = root / "spec"
    git("update-ref", "refs/remotes/origin/main", start, cwd=leg)
    git("symbolic-ref", "HEAD", "refs/remotes/origin/main", cwd=leg)
    before = snapshot(leg)
    place = f"at {start[:12]} (on refs/remotes/origin/main)"
    expected = {
        "at": (f"  [spec] spec: branch main is at the pin {pin[:12]}, and the "
               f"checkout is {place}, which is neither\n"
               + keep("the pin or the branch")),
        "behind": (f"  [spec] spec: branch main tip {start[:12]} is behind "
                   f"the PIN {pin[:12]}, and the checkout is {place}, which "
                   "is neither\n" + keep("the pin or the branch")),
        "missing": (f"  [spec] spec: branch main does not exist, and the "
                    f"checkout is {place}, which is not a branch\n"
                    + keep("the pin")),
    }[path]

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert expected in result.stdout, result.stdout
    assert snapshot(leg) == before, "nothing moved"
