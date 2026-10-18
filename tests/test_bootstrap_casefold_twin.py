# SPDX-License-Identifier: Apache-2.0
"""`make bootstrap` leaves a leg whose HEAD is on a TWIN of the tracking
branch, one that differs from it only in case, and moves nothing (#896).

THE DEFECT, from lane 3's triage of #458 (R603, "reasoned only"). The
assembly root's pinned `scripts/bootstrap.py` compared HEAD's ref with
`refs/heads/<branch>` byte for byte. A disk that folds case (macOS APFS,
Windows NTFS, by default), with loose refs, reads `refs/heads/Main` and
`refs/heads/main` as ONE file, so `git switch Main` in a leg whose tracking
branch is `main` puts HEAD on the file `branch -f main <pin>` moves. Once the
pin moved past that commit, step (a) called the leg "on another branch":

1. `branch -f main <pin>` was let through, since git's guard against moving
   a checked-out branch compares the two names byte for byte, and it moved
   the file HEAD stands on;
2. `checkout main` then found HEAD at the pin and changed no file;
3. bootstrap printed `branch main fast-forwarded` and `the leg was on Main,
   which keeps its commits; it is on main now`;
4. the index and the work tree still held the old commit, so the next
   commit in the leg reverted the pin's changes.

THE EMULATION. CI is Linux only, so a disk that folds case is emulated on
one that keeps it: a symlink `.git/refs/heads/Main -> main`, which git's files
backend reads through, and HEAD on `refs/heads/Main`. The issue's own probe
made the state the same way (`git status --short` said `M  f.txt` after).

THE RULE NOW. Where HEAD's ref and `refs/heads/<branch>` are equal under
`str.casefold()` and differ in bytes, bootstrap leaves the leg on each of the
three paths that would have moved or made the branch: T7 (the branch is
behind the pin), P9 (it is at the pin) and the missing-branch path. No ref
moves and none is made. The lines say where the leg is, why it is left, and
the way out: `git -C <leg> switch <branch>` for T7 and P9, which on a disk
that folds case re-spells HEAD and moves no file, and for the missing branch,
where that command has no branch to go to, keeping the commits on a branch of
another name and checking out the pin.

THE WORDS HOLD ON A DISK THAT KEEPS CASE TOO, where `Main` and `main` are two
branches: they say that a disk that folds case reads them as one, never that
they are. `test_on_a_disk_that_keeps_case_the_words_are_true_too` runs the
way out there, with a real `Main` that has commits of its own.

A test with a symlink skips on Windows, where a tracked or ref symlink is a
plain file or needs Developer Mode, and wherever `os.symlink` raises: a disk
that folds case refuses the link, `Main` already being `main`. A test that
makes a real `Main` skips on such a disk too.
"""

from __future__ import annotations

import itertools
import os
import re
import sys
from pathlib import Path

import pytest

from conftest import git
from test_bootstrap_after_bump import (  # noqa: F401
    EDITED, MAIN, bootstrapped, bumped, fast_forwarded, head_ref,
    left_branch, rev, root, skip_validators,
)
from test_bootstrap_branch_bytes import bootstrap_module  # noqa: F401
from test_bootstrap_leg_moves import main_of, typed

TWIN = "Main"
TWIN_REF = f"refs/heads/{TWIN}"
#: A branch of the spec remote per `behind` call, each its own so that no
#: test sees another's commit (as `bumped` asks).
ADVANCES = itertools.count()
#: The second line of the three twin lines, by what the step would have done.
RISKS = {
    "move": "moving main could move the ref HEAD stands on and leave the "
            "index at the old commit",
    "place": "the leg is already on main there, and bootstrap would say it "
             "left a branch that keeps its commits",
    "make": "making main could hide the commits a branch spelled like main "
            "holds behind the new ref",
}
#: The way out of a leg with a branch to go to (T7, P9).
SWITCH = ("          run `git -C spec switch main`, which moves no branch, "
          "and then run bootstrap again.\n")
#: The way out of a leg with no `main` (#896's missing-branch path).
KEEP = ("          not moving the checkout off it. Keep any commit made "
        "there on a branch whose name differs from main by more than case, "
        "check out the pin in the leg, and run bootstrap again.\n")
HEADING = "\n(a) legs on tracking branches, pins untouched\n"


def twin_lines(state: str, act: str, way: str, twin: str = TWIN) -> str:
    """The three lines step (a) prints of a leg on a twin, byte for byte as
    main prints them, `state` being what the branch is to the pin."""
    return (f"  [spec] spec: {state}, and the checkout is on {twin}, which "
            "differs from main only in case\n"
            f"          a disk that folds case (macOS, Windows) reads {twin} "
            f"and main as one branch, so {RISKS[act]}; the leg is left as it "
            f"is\n{way}")


def step_a(stdout: str) -> str:
    """Step (a)'s lines of the spec leg, the manifest's first: from the
    heading to the second leg's line, which none of these tests touches."""
    return stdout.split(HEADING, 1)[1].split("  [code] code:", 1)[0]


def gitdir_of(leg: Path) -> Path:
    return Path(git("rev-parse", "--absolute-git-dir",
                    cwd=leg).stdout.strip())


def twin_on_disk(leg: Path, twin: str = TWIN) -> None:
    """HEAD on `refs/heads/<twin>`, which reads the file `main` is: what
    `git switch Main` does on a disk that folds case, emulated by a symlink
    `<twin> -> main` that git's files backend reads through. Skips on
    Windows, where a symlink needs Developer Mode and git does not read
    through one by default, and wherever the platform cannot make one: a
    disk that folds case refuses the link, `Main` being `main`. `main` is
    loose, as the link needs."""
    if sys.platform == "win32":
        pytest.skip("a ref symlink is not read through on Windows")
    link = gitdir_of(leg) / "refs" / "heads" / twin
    try:
        os.symlink("main", link)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot make the symlink that emulates "
                    f"a disk that folds case: {exc}")
    git("symbolic-ref", "HEAD", f"refs/heads/{twin}", cwd=leg)


def keeps_case(directory: Path) -> bool:
    """Whether the disk tells `case-probe` from `CASE-PROBE`."""
    (directory / "case-probe").write_bytes(b"")
    return not (directory / "CASE-PROBE").exists()


def needs_a_disk_that_keeps_case(tmp_path: Path) -> None:
    """Skip where `Main` and `main` are one file, so no real second branch
    can be made."""
    if not keeps_case(tmp_path):
        pytest.skip("this disk folds case: `Main` is `main` here, and a "
                    "real second branch cannot be made")


def behind(root: Path, remotes: Path, tmp_path: Path) -> tuple[str, str]:
    """T7's state, from the bootstrapped clone: the pin moved past `main`
    (`bump-leg.py`, the commit also editing a tracked file), then `main`
    checked out, so HEAD is on it, behind the pin. Returns `main`'s old
    commit and the pin."""
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, remotes, tmp_path, f"twin-{next(ADVANCES)}", EDITED)
    git("checkout", "-q", "main", cwd=leg)
    return old, new


def commit_on(leg: Path, name: str) -> str:
    """A commit of its own on the branch HEAD is on. Returns it."""
    (leg / name).write_bytes(b"work\n")
    git("add", "--", name, cwd=leg)
    git("commit", "-q", "-m", f"work: {name}", cwd=leg)
    return rev(leg)


def printed_way_out(stdout: str) -> str:
    """The command the `run ...` line gives, between its backticks."""
    line = next(row for row in stdout.splitlines()
                if row.startswith("          run `"))
    return line.split("`")[1]


def status(leg: Path) -> str:
    return git("status", "--short", cwd=leg).stdout


def test_t7_leaves_a_leg_on_a_twin_and_moves_no_ref(
        root, bootstrapped, tmp_path):
    """THE ISSUE'S PROBE. `main` loose and behind the pin, HEAD on the
    symlink twin `Main`. `main` moved to the pin under HEAD, and `M
    README.md` followed, under `fast-forwarded` and `it is on main now`."""
    old, new = behind(root, bootstrapped["remotes"], tmp_path)
    leg = root / "spec"
    twin_on_disk(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == twin_lines(
        f"branch main tip {old[:12]} is behind the PIN {new[:12]}", "move",
        SWITCH), result.stdout
    assert main_of(leg) == old, "`main` is not moved"
    assert head_ref(leg) == TWIN_REF, "HEAD stays where it was"
    assert rev(leg) == old
    assert status(leg) == "", "the index is the commit HEAD is at"
    assert rev(root, "HEAD:spec") == new, "and the pin is not moved"


def test_the_way_out_of_t7_puts_the_leg_on_main_and_the_next_run_moves_it(
        root, bootstrapped, tmp_path):
    """The printed `git -C spec switch main`, run as printed, re-spells
    HEAD and moves no file; the next bootstrap takes the on-branch
    `merge --ff-only` path, which moves the files with the branch."""
    old, new = behind(root, bootstrapped["remotes"], tmp_path)
    leg = root / "spec"
    twin_on_disk(leg)
    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout

    typed(root, printed_way_out(first.stdout))
    assert head_ref(leg) == MAIN, "HEAD is re-spelled"
    assert main_of(leg) == old, "and no branch moved"

    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == fast_forwarded(old, new), again.stdout
    assert head_ref(leg) == MAIN
    assert rev(leg) == new == main_of(leg), "at the pin"
    assert status(leg) == ""


def test_p9_leaves_a_leg_on_a_twin_of_the_branch_at_the_pin(root):
    """`main` AT the pin, HEAD on the twin. Bootstrap checked `main` out and
    said `on main at <pin>` and that the leg was on `Main`, which keeps its
    commits: a branch that, on such a disk, is `main`."""
    leg = root / "spec"
    pin = rev(leg)
    twin_on_disk(leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == twin_lines(
        f"branch main is at the pin {pin[:12]}", "place", SWITCH), (
        result.stdout)
    assert main_of(leg) == pin
    assert head_ref(leg) == TWIN_REF, "HEAD stays where it was"
    assert status(leg) == ""

    typed(root, printed_way_out(result.stdout))
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == (
        f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n")
    assert head_ref(leg) == MAIN


def without_main(leg: Path) -> str:
    """The pin's commit, the leg detached there with `main` deleted: the
    state a missing-branch step (a) starts from."""
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    return pin


def test_the_missing_branch_path_leaves_an_unborn_twin_and_makes_nothing(
        root):
    """`Main` unborn (no commit, the dangling symlink `Main -> main` a disk
    that folds case reads as one), `main` not there. `checkout -b main` made
    the file `Main` reads, and said the leg had been on a branch with no
    commit yet."""
    leg = root / "spec"
    pin = without_main(leg)
    twin_on_disk(leg)
    assert main_of(leg) is None

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == twin_lines(
        f"branch main does not exist (the pin is {pin[:12]})", "make",
        KEEP), result.stdout
    assert main_of(leg) is None, "no `main` is made"
    assert not (gitdir_of(leg) / "refs" / "heads" / "main").exists()
    assert head_ref(leg) == TWIN_REF, "HEAD stays where it was"
    assert pin == rev(root, "HEAD:spec")


def test_the_missing_branch_path_leaves_a_packed_twin_with_commits(
        root, tmp_path):
    """The state that loses something on a disk that folds case: `Main`
    holds a commit of its own, packed (`git pack-refs --all`, which is
    what a `gc` leaves), and `main` is not there. A new loose `main` is the
    file `Main` reads, which hides what `Main` holds. Left, with the way
    out run as printed: the commit kept on a branch of another name, the
    pin checked out, bootstrap again, which makes `main` at the pin."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", TWIN, cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == twin_lines(
        f"branch main does not exist (the pin is {pin[:12]})", "make",
        KEEP), result.stdout
    assert main_of(leg) is None, "no `main` is made"
    assert head_ref(leg) == TWIN_REF
    assert rev(leg) == mine, "HEAD stays on `Main`'s commit"
    assert status(leg) == ""

    git("branch", "-q", "kept-from-Main", cwd=leg)
    shown = re.search(r"\(the pin is ([0-9a-f]{12})\)", result.stdout)
    assert shown is not None, "the line prints the pin"
    git("checkout", "-q", "--detach", shown.group(1), cwd=leg)
    assert rev(leg) == pin, "the printed sha is the pin"
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == (
        f"  [spec] spec: branch main created at {pin[:12]} — at the pin\n"), (
        again.stdout)
    assert head_ref(leg) == MAIN
    assert rev(leg, "refs/heads/kept-from-Main") == mine
    assert rev(leg, TWIN_REF) == mine, "`Main` keeps its commit here"


def test_on_a_disk_that_keeps_case_the_words_are_true_too(
        root, bootstrapped, tmp_path):
    """No symlink: a REAL loose `Main` with a commit of its own, HEAD on
    it, `main` behind the pin. The leg is left with the same lines. The way
    out, run as printed, puts the leg on the real `main`, which bootstrap
    then fast-forwards, and `Main` keeps its commit: the words said only
    that a disk that folds case reads the two as one branch."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    old = rev(leg)
    new = bumped(root, bootstrapped["remotes"], tmp_path,
                 f"twin-{next(ADVANCES)}", EDITED)
    git("checkout", "-q", "-b", TWIN, "main", cwd=leg)
    mine = commit_on(leg, "MINE.md")

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == twin_lines(
        f"branch main tip {old[:12]} is behind the PIN {new[:12]}", "move",
        SWITCH), first.stdout
    assert main_of(leg) == old
    assert rev(leg, TWIN_REF) == mine
    assert head_ref(leg) == TWIN_REF
    assert status(leg) == ""

    typed(root, printed_way_out(first.stdout))
    assert head_ref(leg) == MAIN, "on the real `main`"
    assert rev(leg) == old
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == fast_forwarded(old, new), again.stdout
    assert head_ref(leg) == MAIN
    assert rev(leg) == new == main_of(leg)
    assert rev(leg, TWIN_REF) == mine, "`Main` keeps its commit"
    assert status(leg) == ""


@pytest.mark.parametrize("other", [None, "feature", "mains"],
                         ids=["main itself", "feature", "mains"])
def test_every_other_checkout_is_moved_as_it_was(
        root, bootstrapped, tmp_path, other):
    """T7 from HEAD on `main` itself, on a branch that does not fold to
    `main` (`feature`) and on one that nearly does (`mains`): the leg is
    moved, and the line that it left a branch is said for the two others
    only, byte for byte as before."""
    old, new = behind(root, bootstrapped["remotes"], tmp_path)
    leg = root / "spec"
    if other is not None:
        git("checkout", "-q", "-b", other, "main", cwd=leg)
    expected = fast_forwarded(old, new)
    if other is not None:
        expected += left_branch(other)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == expected, result.stdout
    assert head_ref(leg) == MAIN
    assert rev(leg) == new == main_of(leg)
    assert status(leg) == ""


SIGMA = chr(0x3C3)
FINAL_SIGMA = chr(0x3C2)
SURROGATE = chr(0xDCFF)


@pytest.mark.parametrize("current, branch, twin", [
    pytest.param("refs/heads/Main", "main", True, id="Main"),
    pytest.param("refs/heads/MAIN", "main", True, id="MAIN"),
    pytest.param("refs/heads/main", "Main", True, id="branch is the twin"),
    pytest.param("refs/heads/main", "main", False, id="the branch itself"),
    pytest.param("refs/heads/Main", "Main", False, id="Main itself"),
    pytest.param(None, "main", False, id="detached"),
    pytest.param("refs/remotes/origin/main", "main", False, id="not a head"),
    pytest.param("refs/heads/feature", "main", False, id="another branch"),
    pytest.param("refs/heads/mains", "main", False, id="a longer name"),
    pytest.param("refs/Heads/main", "main", False, id="not refs/heads/"),
    pytest.param("refs/notes/Main", "main", False, id="a notes ref"),
    pytest.param("refs/tags/xMain", "main", False, id="a tag, 11 characters"),
    pytest.param(f"refs/heads/{SIGMA}", FINAL_SIGMA, True,
                 id="casefold folds a final sigma, lower() does not"),
    pytest.param(f"refs/heads/a{SURROGATE}b", f"a{SURROGATE}b", False,
                 id="a name that is not UTF-8, itself"),
    pytest.param(f"refs/heads/A{SURROGATE}b", f"a{SURROGATE}b", True,
                 id="a name that is not UTF-8, a twin"),
])
def test_the_helper_asks_the_names_after_refs_heads(
        bootstrap_module, current, branch, twin):
    """`_folded_twin`: equal under `casefold()` and not in bytes, for a
    branch under `refs/heads/` only. It raises on no name (#704)."""
    assert bootstrap_module._folded_twin(current, branch) is twin


def test_the_way_out_is_quoted_for_a_shell_as_the_move_back_line_is(
        bootstrap_module, capsys):
    """The command is the leg's path and the branch, `shlex.quote`d and then
    spelled, as `move_back_to_pin` prints its own."""
    bootstrap_module._say_twin("[spec] my leg", "my leg", "a$b",
                               "refs/heads/A$b", "branch a$b is at the pin",
                               "place")
    lines = capsys.readouterr().out.splitlines()
    assert lines[-1] == ("          run `git -C 'my leg' switch 'a$b'`, which "
                         "moves no branch, and then run bootstrap again.")


def test_the_lines_spell_a_name_that_is_not_utf_8(bootstrap_module, capsys):
    """A twin named with a byte that is not UTF-8 holds a surrogate escape
    here (#704): printed raw it would raise `UnicodeEncodeError`, so each
    name in the lines is spelled (#391), the leg's path too."""
    twin = f"A{SURROGATE}b"
    branch = f"a{SURROGATE}b"
    leg = f"a{chr(0x1B)}b"
    spelled = bootstrap_module.spelled
    bootstrap_module._say_twin(
        f"[spec] {spelled(leg)}", leg, branch, f"refs/heads/{twin}",
        f"branch {spelled(branch)} does not exist", "make")
    out = capsys.readouterr().out
    assert out.isascii(), "every name is written as an escape"
    assert chr(0x1B) not in out
    assert ("the checkout is on A\\udcffb, which differs from a\\udcffb "
            "only in case") in out
    assert "differs from a\\udcffb by more than case" in out
