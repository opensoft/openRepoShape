# SPDX-License-Identifier: Apache-2.0
"""`make bootstrap` does not make a tracking branch a disk that folds case, or
Unicode forms, reads as a branch that is there, and a twin is folded in NFC
too (#962).

WHAT #948 (#896) LEFT. `_folded_twin` asked only about HEAD's own ref, and
`create_at_pin` checked no other spelling of the branch it made, so on a disk
that folds case (macOS, Windows) `checkout -b main <pin>` wrote the loose file
that `Main` and `MAIN` are read from, and a commit only a packed `Main` held
was then in no ref, with only HEAD's reflog keeping it (rv896's probes):

- a leg DETACHED AT THE PIN over a packed `Main`, and no `main`;
- a leg on an UNBORN `Main` beside a packed `MAIN`: #948 refuses the unborn
  `Main`, whose way out is to check out the pin, and the next run then hid
  `MAIN`'s commit;
- the same with NFC and NFD, which APFS reads as one file as it reads `Main`
  and `main`: a leg on the NFD spelling of `café`, `str.casefold()` alone
  calling it no twin, was moved under its own HEAD as #896's was.

THE RULE NOW. `_fold` is NFC, then `casefold()`, and `_folded_twin` asks it
of HEAD's ref. Before `checkout -b`, `create_at_pin` asks `git for-each-ref
refs/heads/`, which lists the packed ones too, for a twin that holds a commit
the new branch would leave in no ref, and leaves the leg, naming it. A twin
whose commit is the pin's ancestor, or is held by another branch, a tag or a
remote-tracking ref, loses nothing, so the way out is #948's: keep the commits
on a branch of another name, and run bootstrap again, which then makes `main`.

THE WORDS HOLD ON A DISK THAT KEEPS CASE TOO, where a real `Main` is a branch
of its own: every state here that makes a real name, packed or loose, runs the
way out there, and skips on a disk that folds case, where it cannot be made.
A test with a symlink skips as `test_bootstrap_casefold_twin.py`'s do.
"""

from __future__ import annotations

import os
import shlex
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
    printed_way_out, status, step_a, twin_on_disk,
)
from test_bootstrap_leg_moves import main_of, typed
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


def spelling_lines(state: str, spelling: str, branch: str = "main",
                   kind=CASE) -> str:
    """The three lines step (a) prints of a leg that has a spelling of the
    missing branch it would hide (`_say_spelling`), byte for byte."""
    how, reads, more = kind
    return (f"  [spec] spec: {state}, and the leg has the branch {spelling}, "
            f"which differs from {branch} {how}\n"
            f"          {reads} reads {spelling} and {branch} as one branch, "
            f"so {MAKE.format(b=branch)}; the leg is left as it is\n"
            f"          keep the commits {spelling} holds on a branch whose "
            f"name differs from {branch} by more than {more}: `git -C spec "
            f"branch <another name> {shlex.quote(spelling)}`, and run "
            "bootstrap again.\n")


def missing(pin: str) -> str:
    return f"branch main does not exist (the pin is {pin[:12]})"


def created(pin: str) -> str:
    return f"  [spec] spec: branch main created at {pin[:12]} — at the pin\n"


def kept_by(root: Path, stdout: str, name: str) -> None:
    """The way out, run as printed with `<another name>` made `name`."""
    line = next(row for row in stdout.splitlines()
                if row.startswith("          keep the commits "))
    command = line.split("`")[1].replace("<another name>", name)
    typed(root, command)


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
    read from on a disk that folds case, hiding the commit. Nothing is made;
    the lines name `Main`, and the way out, run as printed, keeps the commit
    on another branch, so the next run makes `main`, and `Main` keeps it
    too. Loose and packed give the same lines (a loose `Main` cannot stand
    beside a missing `main` on a disk that folds case: it IS `main` there)."""
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

    kept_by(root, first.stdout, "kept-from-Main")
    again = skip_validators(root)
    assert again.returncode == 0, again.stderr + again.stdout
    assert step_a(again.stdout) == created(pin), again.stdout
    assert head_ref(leg) == "refs/heads/main"
    assert rev(leg, "refs/heads/kept-from-Main") == mine
    assert rev(leg, "refs/heads/Main") == mine, "`Main` keeps its commit"


def test_an_unborn_twin_beside_a_packed_third_spelling_is_left_twice(
        root, tmp_path):
    """(c) HEAD on an unborn `Main` while a packed `MAIN` holds a commit, and
    no `main`. #948 refuses the unborn `Main`; its way out, checking out the
    pin, ran `checkout -b main` over `MAIN`, and hid `MAIN`'s commit. The
    second refusal names `MAIN`, and its way out, run as printed, lets the
    third run make `main`."""
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
    assert (f"  [spec] spec: {missing(pin)}, and the checkout is on Main, "
            "which differs from main only in case\n") in first.stdout
    assert main_of(leg) is None

    git("checkout", "-q", "--detach", pin, cwd=leg)
    second = skip_validators(root)
    assert second.returncode == 0, second.stderr + second.stdout
    assert step_a(second.stdout) == spelling_lines(missing(pin), "MAIN"), (
        second.stdout)
    assert main_of(leg) is None, "no `main` is made"
    assert rev(leg, "refs/heads/MAIN") == mine

    kept_by(root, second.stdout, "kept-from-MAIN")
    third = skip_validators(root)
    assert third.returncode == 0, third.stderr + third.stdout
    assert step_a(third.stdout) == created(pin), third.stdout
    assert rev(leg, "refs/heads/kept-from-MAIN") == mine
    assert rev(leg, "refs/heads/MAIN") == mine


def test_the_spelling_that_would_hide_something_is_the_one_named(
        root, tmp_path):
    """Two twins, `MAIN` (first in the list) with its commit kept on another
    branch, and `Main` with a commit nothing else holds: the refusal names
    `Main`, and goes on past `MAIN`."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", "MAIN", cwd=leg)
    commit_on(leg, "ONE.md")
    git("branch", "-q", "kept", cwd=leg)
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("checkout", "-q", "-b", "Main", cwd=leg)
    mine = commit_on(leg, "TWO.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == spelling_lines(missing(pin), "Main"), (
        result.stdout)
    assert main_of(leg) is None
    assert rev(leg, "refs/heads/Main") == mine


@pytest.mark.parametrize("held", ["ancestor of the pin", "another branch",
                                  "a remote-tracking ref", "no twin"])
def test_a_spelling_with_nothing_to_hide_is_no_reason_to_leave(
        root, tmp_path, held):
    """Nothing is hidden where a twin's commit is the pin's ancestor (the new
    `main` holds it), or another branch or a remote-tracking ref holds it,
    and a branch that is no twin is no one's business: `main` is made, as it
    was. These pass on the base by design."""
    needs_a_disk_that_keeps_case(tmp_path)
    leg = root / "spec"
    pin = rev(leg)
    name = "mains" if held == "no twin" else "Main"
    git("checkout", "-q", "-b", name, cwd=leg)
    mine = pin if held == "ancestor of the pin" else commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    if held == "ancestor of the pin":
        # the remote-tracking refs hold the pin too: only the pin does here
        for ref in git("for-each-ref", "--format=%(refname)",
                       "refs/remotes/", cwd=leg).stdout.split():
            git("update-ref", "-d", ref, cwd=leg)
    if held == "another branch":
        git("branch", "-q", "kept", mine, cwd=leg)
    if held == "a remote-tracking ref":
        git("update-ref", "refs/remotes/origin/Main", mine, cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    result = skip_validators(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert step_a(result.stdout) == created(pin), result.stdout
    assert head_ref(leg) == "refs/heads/main"
    assert rev(leg, f"refs/heads/{name}") == mine


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
def test_a_missing_branch_beside_its_nfd_spelling_is_left(root, tmp_path):
    """The missing `café` in NFC beside a packed branch `café` in NFD that
    holds a commit: on APFS, which reads the two as one file, `checkout -b`
    would hide it. The lines name the NFD branch and say it differs in case
    or Unicode form; skips on a disk that reads the two as one."""
    if not keeps_forms(tmp_path):
        pytest.skip("this disk reads NFC and NFD as one file")
    leg = root / "spec"
    pin = rev(leg)
    git("checkout", "-q", "-b", NFD, cwd=leg)
    mine = commit_on(leg, "MINE.md")
    git("checkout", "-q", "--detach", pin, cwd=leg)
    git("branch", "-q", "-D", "main", cwd=leg)
    git("pack-refs", "--all", cwd=leg)

    result = run_script(root / "scripts" / "bootstrap.py",
                        "--skip-validators", "--branch", NFC, cwd=root)
    assert result.returncode == 0, result.stderr + result.stdout
    state = f"branch {NFC} does not exist (the pin is {pin[:12]})"
    assert step_a(result.stdout) == spelling_lines(
        state, NFD, NFC, FORM), result.stdout
    assert os.path.exists(gitdir_of(leg) / "packed-refs")
    assert git("rev-parse", "--verify", "--quiet", f"refs/heads/{NFC}",
               cwd=leg, check=False).stdout.strip() == "", "none is made"
    assert rev(leg, f"refs/heads/{NFD}") == mine


@pytest.mark.parametrize("current, branch, twin", [
    pytest.param(f"refs/heads/{NFD}", NFC, True, id="NFD for NFC"),
    pytest.param(f"refs/heads/{NFC}", NFD, True, id="NFC for NFD"),
    pytest.param(f"refs/heads/{NFC}", NFC, False, id="NFC itself"),
    pytest.param(f"refs/heads/{NFD}", NFD, False, id="NFD itself"),
    pytest.param(f"refs/heads/{NFD.upper()}", NFC, True,
                 id="NFD in capitals for NFC"),
    pytest.param("refs/heads/" + NFD, "caf" + chr(0xE8), False,
                 id="another letter"),
])
def test_the_helper_folds_unicode_forms_too(
        bootstrap_module, current, branch, twin):
    """`_folded_twin` folds in NFC before `casefold()`: the NFC and the NFD
    spelling of a name are twins, in either order and in capitals, a name is
    no twin of itself, and another letter is no twin."""
    assert bootstrap_module._folded_twin(current, branch) is twin


def test_the_fold_raises_nothing_on_a_name_that_is_not_utf_8(
        bootstrap_module):
    """A name held as surrogate escapes (a branch that is not UTF-8, #704)
    passes through the NFC step as the text it is."""
    name = f"a{chr(0xDCFF)}b"
    assert bootstrap_module._fold(name) == name
    assert bootstrap_module._folded_twin(f"refs/heads/A{chr(0xDCFF)}b",
                                         name) is True
