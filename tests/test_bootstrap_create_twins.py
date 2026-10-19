# SPDX-License-Identifier: Apache-2.0
"""`make bootstrap` does not make a tracking branch a disk that folds case, or
Unicode forms, reads as a branch that is there, and a twin is folded in NFC
too (#962).

WHAT #948 (#896) LEFT. `_folded_twin` asked only about HEAD's own ref, and
`create_at_pin` checked no other spelling of the branch it made, so on a disk
that folds case (macOS, Windows) `checkout -b main <pin>` wrote the loose file
that `Main` and `MAIN` are read from. What such a disk then does to a packed
`Main` is reasoned from git's files backend (rv984), and not measured on one:
the packed entry stays, `for-each-ref` goes on listing it at its old sha while
`rev-parse Main` reads the new file `main`, and a later `branch -D Main`
unlinks that file. The commit is still in a ref; its name is shadowed, and the
state is fragile. Three states did it:

- a leg DETACHED AT THE PIN over a packed `Main`, and no `main`;
- a leg on an UNBORN `Main` beside a packed `MAIN`: #948 refuses the unborn
  `Main`, whose way out is to check out the pin, and the next run then made
  `main` over `MAIN`;
- the same with NFC and NFD, which APFS reads as one file as it reads `Main`
  and `main`: a leg on the NFD spelling of `café`, `str.casefold()` alone
  calling it no twin, was moved under its own HEAD as #896's was.

THE RULE NOW. `_fold` is NFC, then `casefold()`, and `_folded_twin` asks it
of HEAD's ref. Before `checkout -b`, `create_at_pin` asks `git for-each-ref
refs/heads/`, which lists the packed ones too, for ANY twin, and leaves the
leg, naming it: whether or not a tag, a remote-tracking ref, another branch
or the pin holds the twin's commits, since the ref made is one a folding disk
reads as a branch that is already there. The way out RENAMES the twin, `git -C
<leg> branch -m <twin> <twin>-kept`, for a twin elsewhere and for the twin
HEAD is on alike: git moves HEAD with the rename, and the next run makes `main`
(an earlier way out, to keep the commits on another branch and check out the
pin, left the twin where it was, so the refusal came back).

THE NAME OF THE RENAME (#1000). `_kept_name` prints `<twin>-kept`, then
`-kept-2` and on, and git refuses to make `Main-kept` over a branch stored
under it, `Main-kept/x` (exit 128, a loose ref or a packed one), so such a name
is skipped like one that is there; a branch that only starts with it
(`Main-kept-x`) is no bar. A twin whose name has a slash (`Team/main` for
`--branch team/main`) is named whole, not by its last part.

THE WORDS HOLD ON A DISK THAT KEEPS CASE TOO, where a real `Main` is a branch
of its own: every state here that makes a real name, packed or loose, runs the
way out there, and skips on a disk that folds case, where it cannot be made.
A test with a symlink skips as `test_bootstrap_casefold_twin.py`'s do.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import unicodedata
from pathlib import Path

import pytest

from conftest import git, run_script
from test_bootstrap_after_bump import (  # noqa: F401
    bootstrapped, head_ref, rev, root, skip_validators,
)
from test_bootstrap_branch_bytes import bootstrap_module  # noqa: F401
from test_bootstrap_casefold_twin import (
    behind, commit_on, gitdir_of, needs_a_disk_that_keeps_case,
    printed_rename, printed_way_out, status, step_a, twin_on_disk,
)
from test_bootstrap_leg_moves import main_of
from test_bootstrap_non_utf8_branch import NEEDS_A_UTF8_PROCESS, head_bytes
from test_bootstrap_pasteable_lines import pasted

NFC = "caf" + chr(0xE9)
NFD = unicodedata.normalize("NFD", NFC)
#: What a refusal says a twin differs from the branch in, what reads the two
#: as one, and what a name must differ in to be no twin (`_twin_words`).
CASE = ("only in case", "a disk that folds case (macOS, Windows)", "case")
FORM = ("only in case or Unicode form",
        "a disk that folds case or Unicode forms (macOS folds both, Windows "
        "folds case)", "case or Unicode form")
MAKE = ("making {b} could hide the commits a branch spelled like {b} holds "
        "behind the new ref")
MOVE = ("moving {b} could move the ref HEAD stands on and leave the index "
        "at the old commit")
ON = "the checkout is on"
HAS = "the leg has the branch"


def spelling_lines(state: str, spelling: str, branch: str = "main",
                   kind=CASE, where: str = HAS, kept: str = "") -> str:
    """The three lines step (a) prints of a leg that has a twin of the
    missing branch (`_say_spelling`), byte for byte, `where` saying how the
    leg has it and `kept` being the name the rename gives it."""
    how, reads, more = kind
    kept = kept or f"{spelling}-kept"
    return (f"  [spec] spec: {state}, and {where} {spelling}, "
            f"which differs from {branch} {how}\n"
            f"          {reads} reads {spelling} and {branch} as one branch, "
            f"so {MAKE.format(b=branch)}; the leg is left as it is\n"
            f"          rename {spelling} to a name that differs from "
            f"{branch} by more than {more}, its commits staying on it: "
            f"`git -C spec branch -m {shlex.quote(spelling)} "
            f"{shlex.quote(kept)}`, and run bootstrap again.\n")


def missing(pin: str, branch: str = "main") -> str:
    return f"branch {branch} does not exist (the pin is {pin[:12]})"


def created(pin: str, branch: str = "main") -> str:
    return (f"  [spec] spec: branch {branch} created at {pin[:12]} "
            "— at the pin\n")


def sha_of(leg: Path, ref: str) -> str:
    """What `ref` names in the leg, or the empty string where it is none."""
    return git("rev-parse", "--verify", "--quiet", ref, cwd=leg,
               check=False).stdout.strip()


def twin_with_a_commit(leg: Path, twin: str,
                       on_it: bool = False) -> tuple[str, str]:
    """A branch `twin` with a commit of its own, packed (`git pack-refs
    --all`), and the leg detached at the pin or, with `on_it`, left on the
    twin. `main` is not touched. Returns the pin and the commit."""
    pin = rev(leg)
    git("checkout", "-q", "-b", twin, cwd=leg)
    mine = commit_on(leg, "MINE.md")
    if not on_it:
        git("checkout", "-q", "--detach", pin, cwd=leg)
    git("pack-refs", "--all", cwd=leg)
    return pin, mine


def detached_without_main(leg: Path) -> str:
    """The leg detached at the pin, `main` gone. Returns the pin."""
    pin = rev(leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    return pin


def keeps_forms(directory: Path) -> bool:
    """Whether the disk tells the NFC from the NFD spelling of `café`."""
    (directory / NFC).write_bytes(b"")
    return not (directory / NFD).exists()


@pytest.mark.parametrize("packed", [True, False],
                         ids=["packed Main", "loose Main"])
def test_a_leg_detached_at_the_pin_over_a_real_spelling_is_left(
        root, tmp_path, packed):
    """(b) HEAD detached at the pin, `Main` holding a commit of its own, no
    `main`. `checkout -b main <pin>` exited 0 and wrote the file `Main` is
    read from on a disk that folds case. Nothing is made; the lines name
    `Main`, and the way out, run as printed through `/bin/sh`, renames it, so
    the next run makes `main`, and the commit stays on `Main-kept`. Loose
    and packed give the same lines (a loose `Main` cannot stand beside a
    missing `main` on a disk that folds case: it IS `main` there)."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "Main", cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    if packed:
        git("pack-refs", "--all", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(missing(pin), "Main"), (
        first.stdout)
    assert main_of(leg) is None, "no `main` is made"
    assert head_ref(leg) is None, "HEAD stays detached at the pin"
    assert rev(leg) == pin
    assert rev(leg, "refs/heads/Main") == mine
    assert status(leg) == ""

    pasted(root, printed_rename(first.stdout))
    assert rev(leg, "refs/heads/Main-kept") == mine
    assert sha_of(leg, "refs/heads/Main") == "", "`Main` is renamed"
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == created(pin), again.stdout
    assert head_ref(leg) == "refs/heads/main"
    assert rev(leg, "refs/heads/Main-kept") == mine


def test_a_leg_on_a_twin_takes_the_rename_and_head_goes_with_it(
        root, tmp_path):
    """#948's HEAD-twin line, for a branch that is not there, said to keep
    the commits on another branch and check out the pin. The rename gives the
    same ending to a leg ON the twin: git moves HEAD with the renamed
    branch, the next run finds no twin, makes `main`, and says the leg was on
    `Main-kept`, which keeps its commits."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "Main", cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(
        missing(pin), "Main", where=ON), first.stdout
    assert main_of(leg) is None, "no `main` is made"
    assert head_ref(leg) == "refs/heads/Main"
    assert rev(leg) == mine
    assert status(leg) == ""

    pasted(root, printed_rename(first.stdout))
    assert head_ref(leg) == "refs/heads/Main-kept", "HEAD goes with it"
    assert rev(leg) == mine
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == created(pin) + (
        "          the leg was on Main-kept, which keeps its commits; it is "
        "on main now\n"), again.stdout
    assert head_ref(leg) == "refs/heads/main"
    assert rev(leg) == pin
    assert rev(leg, "refs/heads/Main-kept") == mine


def test_an_unborn_twin_beside_a_packed_third_spelling_is_renamed_in_turn(
        root, tmp_path):
    """(c) HEAD on an unborn `Main` while a packed `MAIN` holds a commit, and
    no `main`. #948 refuses the unborn `Main`; its way out, checking out the
    pin, ran `checkout -b main` over `MAIN`. Now each twin is named in turn
    and renamed as printed: the unborn `Main` first (HEAD goes with it), then
    `MAIN`, and the third run makes `main`."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "MAIN", cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)
    git("symbolic-ref", "HEAD", "refs/heads/Main", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(
        missing(pin), "Main", where=ON), first.stdout
    assert main_of(leg) is None
    pasted(root, printed_rename(first.stdout))
    assert head_ref(leg) == "refs/heads/Main-kept", "HEAD goes with it"

    second = skip_validators(root)
    assert second.returncode == 0, second.stderr + second.stdout
    assert step_a(second.stdout) == spelling_lines(missing(pin), "MAIN"), (
        second.stdout)
    assert main_of(leg) is None, "no `main` is made"
    assert rev(leg, "refs/heads/MAIN") == mine
    pasted(root, printed_rename(second.stdout))

    third = skip_validators(root)
    assert third.returncode == 0, third.stderr + third.stdout
    assert step_a(third.stdout) == created(pin) + (
        "          the leg was on Main-kept, a branch with no commit yet; "
        "it is on main now\n"), third.stdout
    assert rev(leg, "refs/heads/MAIN-kept") == mine
    assert sha_of(leg, "refs/heads/MAIN") == ""


def test_two_twins_are_named_in_turn_and_the_second_name_is_taken_in_case(
        root, tmp_path):
    """Two twins, `MAIN` (first in the list) and `Main`, each with a commit:
    the refusal names `MAIN`, and once it is renamed, `Main`. The second
    rename is `Main-kept-2`, not `Main-kept`, which differs from the first
    rename, `MAIN-kept`, only in case: on a disk that folds case it would be
    the same file."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "MAIN", cwd=leg)
    one = commit_on(leg, "ONE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("checkout", "-q", "-b", "Main", cwd=leg)
    two = commit_on(leg, "TWO.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(missing(pin), "MAIN"), (
        first.stdout)
    pasted(root, printed_rename(first.stdout))

    second = skip_validators(root)
    assert second.returncode == 0, second.stderr + second.stdout
    assert step_a(second.stdout) == spelling_lines(
        missing(pin), "Main", kept="Main-kept-2"), second.stdout
    assert main_of(leg) is None
    pasted(root, printed_rename(second.stdout))

    third = skip_validators(root)
    assert third.returncode == 0, third.stderr + third.stdout
    assert step_a(third.stdout) == created(pin), third.stdout
    assert rev(leg, "refs/heads/MAIN-kept") == one
    assert rev(leg, "refs/heads/Main-kept-2") == two


@pytest.mark.parametrize("held", ["the pin alone", "another branch",
                                  "a tag", "a remote-tracking ref",
                                  "the stash"])
def test_a_twin_is_a_reason_to_leave_however_its_commit_is_held(
        root, tmp_path, held):
    """The ref bootstrap would make is one a disk that folds case reads as a
    branch that is already there, so a twin is a reason to leave whether or
    not something else holds its commit: the pin (`Main` at the pin itself),
    another branch, a tag, a remote-tracking ref or the stash (rv984 measured
    the four that hold a commit the pin lacks, which an earlier rule
    spared). The rename ends it, and the commit is where it was."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "Main", cwd=leg)
    mine = pin if held == "the pin alone" else commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    if held == "another branch":
        git("branch", "-q", "kept", mine, cwd=leg)
    if held == "a tag":
        git("tag", "kept-tag", mine, cwd=leg)
    if held == "a remote-tracking ref":
        git("update-ref", "refs/remotes/origin/Main", mine, cwd=leg)
    if held == "the stash":
        git("update-ref", "refs/stash", mine, cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(missing(pin), "Main"), (
        first.stdout)
    assert main_of(leg) is None, "no `main` is made"
    assert head_ref(leg) is None
    assert rev(leg, "refs/heads/Main") == mine

    pasted(root, printed_rename(first.stdout))
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == created(pin), again.stdout
    assert rev(leg, "refs/heads/Main-kept") == mine


def test_a_branch_that_is_no_twin_is_no_reason_to_leave(root, tmp_path):
    """`mains` holds a commit and is no spelling of `main`: it is no one's
    business, and `main` is made, as it was. This passes on the base by
    design."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "mains", cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == created(pin), result.stdout
    assert head_ref(leg) == "refs/heads/main"
    assert rev(leg, "refs/heads/mains") == mine


@NEEDS_A_UTF8_PROCESS
def test_a_leg_on_the_nfd_spelling_of_its_branch_is_left_and_the_way_out_works(
        root, bootstrapped, tmp_path):
    """T7 with the tracking branch `café` in NFC, behind the pin, and HEAD on
    its NFD spelling (a symlink, as APFS reads the two as one file). The
    byte-for-byte and the `casefold` compares called it no twin, `branch -f`
    moved `café` under HEAD, and `D NEW-CONTRACT.md;M README.md` followed.
    Now the leg is left, the lines say it differs in case or Unicode form,
    and the printed `switch`, run as printed, puts HEAD on the NFC name byte
    for byte, which the next run fast-forwards."""
    old, new = behind(root, bootstrapped["remotes"], tmp_path)
    leg = root / "spec"
    git("branch", "-q", "-m", "main", NFC, cwd=leg)
    twin_on_disk(leg, NFD, NFC)
    bootstrap = root / "scripts" / "bootstrap.py"

    first = run_script(bootstrap, "--skip-validators", "--branch", NFC,
                       cwd=root)
    assert first.returncode == 0, first.stderr + first.stdout
    how, reads, _ = FORM
    assert step_a(first.stdout) == (
        f"  [spec] spec: branch {NFC} tip {old[:12]} is behind the PIN "
        f"{new[:12]}, and the checkout is on {NFD}, which differs from {NFC} "
        f"{how}\n"
        f"          {reads} reads {NFD} and {NFC} as one branch, so "
        f"{MOVE.format(b=NFC)}; the leg is left as it is\n"
        f"          run `git -C spec switch {shlex.quote(NFC)}`, which moves "
        "no branch, and then run bootstrap again.\n"), first.stdout
    assert head_bytes(leg) == f"refs/heads/{NFD}\n".encode("utf-8")
    assert rev(leg, f"refs/heads/{NFC}") == old
    assert status(leg) == ""

    pasted(root, printed_way_out(first.stdout))
    assert head_bytes(leg) == f"refs/heads/{NFC}\n".encode("utf-8")

    again = run_script(bootstrap, "--skip-validators", "--branch", NFC,
                       cwd=root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert (f"  [spec] spec: branch {NFC} fast-forwarded {old[:12]} -> "
            f"{new[:12]}, the pin\n") in again.stdout
    assert rev(leg) == new
    assert status(leg) == ""


@NEEDS_A_UTF8_PROCESS
def test_a_missing_branch_beside_its_nfd_spelling_is_left_and_renamed(
        root, tmp_path):
    """The missing `café` in NFC beside a packed branch `café` in NFD that
    holds a commit: on APFS, which reads the two as one file, `checkout -b`
    would shadow it. The lines name the NFD branch and say it differs in case
    or Unicode form; the rename, run as printed, gives the next run a branch
    to make; skips on a disk that reads the two as one."""
    if not keeps_forms(tmp_path):
        pytest.skip("this disk reads NFC and NFD as one file")
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", NFD, cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)
    bootstrap = root / "scripts" / "bootstrap.py"

    result = run_script(bootstrap, "--skip-validators", "--branch", NFC,
                        cwd=root)
    assert result.returncode == 0, result.stderr + result.stdout
    state = f"branch {NFC} does not exist (the pin is {pin[:12]})"
    assert step_a(result.stdout) == spelling_lines(
        state, NFD, NFC, FORM), result.stdout
    assert os.path.exists(gitdir_of(leg) / "packed-refs")
    assert sha_of(leg, f"refs/heads/{NFC}") == "", "none is made"
    assert rev(leg, f"refs/heads/{NFD}") == mine

    pasted(root, printed_rename(result.stdout))
    assert rev(leg, f"refs/heads/{NFD}-kept") == mine
    again = run_script(bootstrap, "--skip-validators", "--branch", NFC,
                       cwd=root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == (
        f"  [spec] spec: branch {NFC} created at {pin[:12]} — at the pin\n"
    ), again.stdout


@pytest.mark.parametrize("names, spelling, expected", [
    pytest.param([], "Main", "Main-kept", id="nothing taken"),
    pytest.param(["main-kept"], "Main", "Main-kept-2",
                 id="the name taken in another case"),
    pytest.param(["Main-kept", "Main-kept-2"], "Main", "Main-kept-3",
                 id="two taken"),
    pytest.param(["mains"], "Main", "Main-kept", id="another name is no bar"),
])
def test_the_rename_is_to_a_name_no_branch_folds_to(
        bootstrap_module, root, tmp_path, names, spelling, expected):
    """`_kept_name`: the spelling and `-kept`, then `-kept-2` and on, the
    first that no branch of the leg folds to, so the printed line can be
    pasted as it is and names no branch that is there."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    for name in names:
        git("branch", "-q", name, cwd=leg)
    assert bootstrap_module._kept_name(leg, spelling) == expected


@NEEDS_A_UTF8_PROCESS
def test_the_rename_is_taken_in_unicode_form_too(
        bootstrap_module, root, tmp_path):
    """The NFD spelling of `café-kept` is taken: the NFC spelling of the
    rename is not free, though the two differ in bytes."""
    if not keeps_forms(tmp_path):
        pytest.skip("this disk reads NFC and NFD as one file")
    leg = root / "spec"
    git("branch", "-q", f"{NFD}-kept", cwd=leg)
    assert bootstrap_module._kept_name(leg, NFC) == f"{NFC}-kept-2"


@pytest.mark.parametrize("names, spelling, expected", [
    pytest.param(["Main-kept/x"], "Main", "Main-kept-2",
                 id="a branch stored under it"),
    pytest.param(["main-kept/x"], "Main", "Main-kept-2",
                 id="a branch stored under it, in another case"),
    pytest.param(["Main-kept/x/y"], "Main", "Main-kept-2",
                 id="a branch stored deeper under it"),
    pytest.param(["Main-kept/x", "Main-kept-2/y"], "Main", "Main-kept-3",
                 id="a branch under each of the first two"),
    pytest.param(["Main-kept-x"], "Main", "Main-kept",
                 id="a name that only starts with it is no bar"),
    pytest.param(["xMain-kept/y"], "Main", "Main-kept",
                 id="a branch under another name that holds it is no bar"),
    pytest.param(["team/main-kept/x"], "Team/main", "Team/main-kept-2",
                 id="a twin whose name has a slash"),
])
def test_the_rename_is_to_a_name_with_no_branch_stored_under_it(
        bootstrap_module, root, tmp_path, names, spelling, expected):
    """`_kept_name` (#1000): git will not make `Main-kept` over a branch
    stored under it, so the name is skipped, in another case too, at any
    depth. A name that only starts with it, or holds it in the middle, is no
    bar: these rows pass only for a check that asks for the slash, right
    after the name."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    for name in names:
        git("branch", "-q", name, cwd=leg)
    assert bootstrap_module._kept_name(leg, spelling) == expected


@NEEDS_A_UTF8_PROCESS
@pytest.mark.parametrize("held, spelling", [
    pytest.param(NFD, NFC, id="NFD under, NFC name"),
    pytest.param(NFC, NFD, id="NFC under, NFD name"),
])
def test_the_rename_is_barred_under_unicode_form_too(
        bootstrap_module, root, tmp_path, held, spelling):
    """A branch stored under `café-kept` in the other Unicode form bars the
    name, though the two differ in bytes: a disk that folds forms reads both
    as one directory. Either form may be the one held."""
    if not keeps_forms(tmp_path):
        pytest.skip("this disk reads NFC and NFD as one file")
    leg = root / "spec"
    git("branch", "-q", f"{held}-kept/x", cwd=leg)
    assert bootstrap_module._kept_name(leg, spelling) == f"{spelling}-kept-2"


@pytest.mark.parametrize("packed", [True, False],
                         ids=["x packed", "x loose"])
def test_a_branch_stored_under_the_name_makes_the_rename_another_name(
        root, tmp_path, packed):
    """#1000. The leg detached at the pin, `Main` packed with a commit, and a
    branch `Main-kept/x`: the printed `branch -m Main Main-kept` exited 128
    (git cannot make `Main-kept` over it), and the next run printed the same
    line. `Main-kept-2` is printed, the line run as printed through `/bin/sh`
    works, the commit is on `Main-kept-2`, `Main-kept/x` is where it was, and
    the next run makes `main`."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin, mine = twin_with_a_commit(leg, "Main")
    git("branch", "-q", "-D", "main", cwd=leg)
    git("branch", "-q", "Main-kept/x", pin, cwd=leg)
    if packed:
        git("pack-refs", "--all", cwd=leg)

    first = skip_validators(root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(
        missing(pin), "Main", kept="Main-kept-2"), first.stdout
    assert main_of(leg) is None, "no `main` is made"

    pasted(root, printed_rename(first.stdout))
    assert rev(leg, "refs/heads/Main-kept-2") == mine
    assert sha_of(leg, "refs/heads/Main") == "", "`Main` is renamed"
    assert rev(leg, "refs/heads/Main-kept/x") == pin, "the branch under stays"
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == created(pin), again.stdout
    assert head_ref(leg) == "refs/heads/main"


@pytest.mark.parametrize("on_it", [False, True],
                         ids=["detached", "on the twin"])
def test_a_twin_whose_name_has_a_slash_is_named_whole_and_renamed(
        root, tmp_path, on_it):
    """`--branch team/main` with a packed `Team/main` holding a commit: the
    refusal names the twin whole, `Team/main`, where a name cut at its last
    slash would be `main` (rv984b's mutant O3); the printed `branch -m
    Team/main Team/main-kept` works through `/bin/sh`, and the next run makes
    `team/main` with the commit on `Team/main-kept`. Detached at the pin over
    the twin, and ON it, where the rename moves HEAD."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin, mine = twin_with_a_commit(leg, "Team/main", on_it)
    bootstrap = root / "scripts" / "bootstrap.py"
    args = ("--skip-validators", "--branch", "team/main")

    first = run_script(bootstrap, *args, cwd=root)
    assert first.returncode == 0, first.stderr + first.stdout
    assert step_a(first.stdout) == spelling_lines(
        missing(pin, "team/main"), "Team/main", "team/main",
        where=ON if on_it else HAS), first.stdout
    assert sha_of(leg, "refs/heads/team/main") == "", "none is made"
    assert rev(leg, "refs/heads/Team/main") == mine

    pasted(root, printed_rename(first.stdout))
    assert rev(leg, "refs/heads/Team/main-kept") == mine
    assert sha_of(leg, "refs/heads/Team/main") == "", "`Team/main` is renamed"
    again = run_script(bootstrap, *args, cwd=root)
    assert again.returncode == 0, again.stderr + again.stdout
    left = ("          the leg was on Team/main-kept, which keeps its "
            "commits; it is on team/main now\n" if on_it else "")
    assert step_a(again.stdout) == created(pin, "team/main") + left, (
        again.stdout)
    assert head_ref(leg) == "refs/heads/team/main"
    assert rev(leg) == pin


@pytest.mark.skipif(os.name == "nt", reason="the words are `sh`'s")
@pytest.mark.parametrize("path, spelling", [
    pytest.param("spec", "Main", id="ordinary names"),
    pytest.param("my spec", "Main", id="path with a space"),
    pytest.param("spec", f"A{chr(0xDCFF)}b", id="spelling with the byte"),
    pytest.param(f"-sp{chr(0xDCFF)}ec", f"A{chr(0xDCFF)}b",
                 id="both, the path leading with a dash"),
])
def test_a_shell_reads_each_word_of_the_rename_as_the_bytes_of_its_name(
        bootstrap_module, capsys, tmp_path, path, spelling):
    """`_paste_word` for the path, the twin and the name it is renamed to:
    the words `/bin/sh` reads from the printed command are the bytes of the
    names, the name a byte that is not UTF-8 is spelled with included. `git`
    is a function here that prints its arguments, NUL-separated."""
    if not os.path.exists("/bin/sh"):
        pytest.skip("this system has no /bin/sh")
    branch = spelling.lower()
    bootstrap_module._say_spelling(
        tmp_path, "[spec] x", path, branch, spelling, "branch is not there")
    command = printed_rename(capsys.readouterr().out)
    read = subprocess.run(
        ["/bin/sh", "-c", 'git() { printf "%s\\0" "$@"; }\n' + command],
        capture_output=True, check=True).stdout.split(b"\0")[:-1]
    assert read == [b"-C", os.fsencode(path), b"branch", b"-m",
                    os.fsencode(spelling), os.fsencode(spelling) + b"-kept"]


@pytest.mark.parametrize("current, branch, twin", [
    pytest.param(f"refs/heads/{NFD}", NFC, True, id="NFD for NFC"),
    pytest.param(f"refs/heads/{NFC}", NFD, True, id="NFC for NFD"),
    pytest.param(f"refs/heads/{NFC}", NFC, False, id="NFC itself"),
    pytest.param(f"refs/heads/{NFD}", NFD, False, id="NFD itself"),
    pytest.param(f"refs/heads/{NFD.upper()}", NFC, True,
                 id="NFD in capitals for NFC"),
    pytest.param("refs/heads/" + NFD, "caf" + chr(0xE8), False,
                 id="another letter"),
    pytest.param("refs/heads/main" + chr(0xB2), "main2", False,
                 id="a superscript two is no two (NFKC would fold it)"),
    pytest.param("refs/heads/" + chr(0x2460), "1", False,
                 id="a circled one is no one (NFKC would fold it)"),
])
def test_the_helper_folds_unicode_forms_too(
        bootstrap_module, current, branch, twin):
    """`_folded_twin` folds in NFC before `casefold()`: the NFC and the NFD
    spelling of a name are twins, in either order and in capitals, a name is
    no twin of itself, and another letter is no twin. A compatibility form
    (`main` and U+00B2, `1` and U+2460) is none: APFS does not fold those,
    and NFKC would."""
    assert bootstrap_module._folded_twin(current, branch) is twin


def test_the_fold_raises_nothing_on_a_name_that_is_not_utf_8(
        bootstrap_module):
    """A name held as surrogate escapes (a branch that is not UTF-8, #704)
    passes through the NFC step as the text it is."""
    name = f"a{chr(0xDCFF)}b"
    assert bootstrap_module._fold(name) == name
    assert bootstrap_module._folded_twin(f"refs/heads/A{chr(0xDCFF)}b",
                                         name) is True
