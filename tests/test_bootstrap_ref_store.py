# SPDX-License-Identifier: Apache-2.0
"""A cherry-pick or a revert in progress on a REFTABLE leg is refused as one
on the files backend is (#764, C4).

THE PROBE, with git 2.47.1 built for it (this host's git, 2.43.0, has no
reftable): in a repository made by `git init --ref-format=reftable`, a
cherry-pick stopped on a conflict and a `git revert` stopped on one leave NO
`CHERRY_PICK_HEAD` or `REVERT_HEAD` file in `.git`. `git show-ref --exists`
finds each in the ref store, and `git status` says the operation is in
progress. A stopped merge leaves `MERGE_HEAD` a FILE there, as on the files
backend.

THE DEFECT, reproduced with that git on lane 5's #745 head (f4935e11): a
scaffold cloned with `GIT_DEFAULT_REF_FORMAT=reftable`, so the root and both
legs are reftable, bootstrapped once, then a cherry-pick (or a revert)
stopped on `other` in the spec leg. `_in_progress` asked for the marker
FILES only and found none, so bootstrap checked `main` out and printed `on
main at <pin>` and `the leg was on other`. The cherry-pick was ENDED, its
staged README carried onto `main`; the revert was ended too, its staged
removal gone. That is #704's line 2, which Brett Heap's R1 refuses, met
again on the other ref backend. A merge was refused, by its file.

THE RULE NOW. `CHERRY_PICK_HEAD` and `REVERT_HEAD` are asked of the leg's
ref store too, by the exact name (`git show-ref --exists`, git 2.43 and
later), so a branch or a tag of that name is no operation. The refusal says
where git holds the marker: `is in its ref store`, or `is in its git dir`
as before.

The reftable cases skip where git makes no reftable repository (before
2.45); CI's runner image has a git that does. The exact-name case runs on
every git.
"""

from __future__ import annotations

import shlex
import shutil
from pathlib import Path

import pytest

from conftest import PROJECT, cloned_just_pushed, git
from test_bootstrap_after_bump import MAIN, head_ref, rev, skip_validators
from test_bootstrap_leg_moves import (
    OPERATIONS, placed_once_cleared, snapshot,
)

#: Where git holds each operation's marker on a reftable leg (the probe).
HELD = {"cherry-pick": "ref store", "revert": "ref store", "merge": "git dir"}


def in_progress(operation: str, held: str) -> str:
    """The two lines step (a) prints for a spec leg with `operation` in
    progress, its marker held in `held`."""
    _, marker, doing, verb = OPERATIONS[operation]
    return (f"  [spec] spec: {doing} is in progress in the leg ({marker} is "
            f"in its {held}), so nothing moved\n"
            f"          finish it (`git -C spec {verb} --continue`) or abort "
            f"it (`git -C spec {verb} --abort`), then run bootstrap again.\n")


def held_in(leg: Path, marker: str) -> str | None:
    """Where the leg's git holds `marker`: `git dir` for a file there,
    `ref store` for a ref by that exact name and no file, else None."""
    gitdir = Path(git("rev-parse", "--absolute-git-dir", cwd=leg).stdout
                  .strip())
    if (gitdir / marker).exists():
        return "git dir"
    held = git("show-ref", "--exists", marker, cwd=leg, check=False)
    return "ref store" if held.returncode == 0 else None


@pytest.fixture(scope="module")
def reftable_clone(scaffolded, tmp_path_factory) -> Path:
    """The session's scaffold cloned recursively by a git that makes every
    new repository reftable (`GIT_DEFAULT_REF_FORMAT`, git 2.45), and
    bootstrapped once, so each leg is on `main` at its pin."""
    clone = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}.git",
        tmp_path_factory.mktemp("reftable") / PROJECT,
        env={"GIT_DEFAULT_REF_FORMAT": "reftable"})
    format_ = git("rev-parse", "--show-ref-format", cwd=clone / "spec",
                  check=False).stdout.strip()
    if format_ != "reftable":
        pytest.skip("this git makes no reftable repository (git 2.45 and "
                    "later do)")
    first = skip_validators(clone)
    assert first.returncode == 0, first.stderr + first.stdout
    assert head_ref(clone / "spec") == MAIN, first.stdout
    return clone


@pytest.fixture
def reftable_root(reftable_clone, tmp_path) -> Path:
    """A private copy of `reftable_clone`; the reftable is plain files, and
    a leg's `.git` file names `.git/modules/<leg>` relatively."""
    target = tmp_path / PROJECT
    shutil.copytree(reftable_clone, target, symlinks=True)
    return target


@pytest.mark.parametrize("operation", sorted(HELD))
def test_an_operation_in_progress_on_a_reftable_leg_is_refused(
        reftable_root, operation):
    """A cherry-pick, a revert and a merge in progress on `other`, started
    from the pin, in a reftable leg: each is refused before any move, the
    line saying where git holds its marker, and nothing moves. The `--abort`
    it prints, typed from the root, ends it, and the next run places the
    leg."""
    leg = reftable_root / "spec"
    pin = rev(leg)
    make, marker = OPERATIONS[operation][:2]
    make(leg, pin)
    assert held_in(leg, marker) == HELD[operation], f"{operation} is held"
    before = snapshot(leg)

    result = skip_validators(reftable_root)
    assert result.returncode == 0, result.stderr + result.stdout
    expected = in_progress(operation, HELD[operation])
    assert expected in result.stdout, result.stdout
    assert snapshot(leg) == before, "nothing moved"
    assert held_in(leg, marker) == HELD[operation], f"the {operation} goes on"

    abort = expected.splitlines()[1].split("`")[3]
    assert abort == f"git -C spec {OPERATIONS[operation][3]} --abort", abort
    git(*shlex.split(abort)[1:], cwd=reftable_root)
    placed_once_cleared(reftable_root, pin)


def test_a_branch_or_a_tag_named_as_a_marker_is_no_operation(project):
    """A recursive clone's leg, detached at the pin, with a branch called
    `CHERRY_PICK_HEAD` and a tag called `REVERT_HEAD` and no operation:
    `git rev-parse --verify` resolves both names, and `git show-ref
    --exists` neither, so the leg is placed as it is without them. Runs on
    every git, the files backend included."""
    leg = project / "spec"
    pin = rev(leg)
    assert head_ref(leg) is None, "a recursive clone leaves the leg detached"
    git("branch", "CHERRY_PICK_HEAD", pin, cwd=leg)
    git("tag", "REVERT_HEAD", pin, cwd=leg)
    assert git("rev-parse", "-q", "--verify", "CHERRY_PICK_HEAD",
               cwd=leg).stdout.strip() == pin, "the branch resolves"

    result = skip_validators(project)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"  [spec] spec: on main at {pin[:12]} (branch tip == pin)\n" in (
        result.stdout), result.stdout
    assert "is in progress" not in result.stdout, result.stdout
    assert head_ref(leg) == MAIN
