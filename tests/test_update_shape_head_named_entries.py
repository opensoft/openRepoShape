# SPDX-License-Identifier: Apache-2.0
"""`update-shape.py` names HEAD to git with a `--` after it, so a project that
tracks an entry git cannot tell from HEAD is read as any other (#1215).

`git diff-tree <tree-ish>` and `git show <rev>:<path>` read their argument as
a revision AND, where the root holds an entry of that very name, as a path,
and refuse: `fatal: ambiguous argument ..., both revision and filename`,
exit 128. The tool asks each of them through `_git_answer`, which reads a
refusal as "git would not answer" and goes on without the answer.
MEASURED ON MAIN AT 4552efa6a (2026-11-09), git 2.43.0, a root cut at A:

  * `apply --branch` ended with `committed on <branch>:` and git's own list
    of what the commit holds (`diff-tree ... HEAD`, #674). Over a root that
    tracks a file named `HEAD` git answered nothing and the line named the
    paths the run was asked to commit instead, `contracts/shape-pin.yaml,
    project.yaml`, where the commit held the pin alone: the line #674 fixed
    came back, silently.
  * `_committed_pin` (`show HEAD:contracts/shape-pin.yaml`) answered "" where
    the root tracks a file spelled `HEAD:contracts/shape-pin.yaml`, a
    directory named `HEAD:contracts`: the refusals for a re-run or a run over
    a tree HEAD does not commit then left out which commit HEAD's pin names.
  * `_accepted_in_the_pin` (`show refs/remotes/origin/<base>:...`) answered
    "no copy was kept" where the root tracks a file spelled like that
    argument, so the pull request's body named none of the copies
    `--accept-local` kept (#535).

THE SECOND AND THIRD FILE NAMES HOLD A COLON, which Windows cannot give a
file, and are skipped there. A control with no such entry runs beside each.
The fixtures are `tests/test_update_shape_partial_rollback.py`'s.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import git, run_script
from test_update_shape_partial_rollback import (  # noqa: F401
    BRANCH, PIN, UPDATE, apply_args, root, standard, update_shape,
)

#: The local edit `--accept-local` keeps: the pinned copy the standard also
#: changed at B, so the project's bytes are what the pin names after the run.
KEPT = "scripts/bootstrap.py"
NOT_ON_WINDOWS = pytest.mark.skipif(
    os.name == "nt", reason="Windows cannot give a file a colon in its name")


def tracked(root: Path, name: str | None) -> None:
    """`name` made a tracked file of the root and committed, or nothing."""
    if name is None:
        return
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("an entry named like a revision\n", encoding="utf-8")
    git("add", "--", name, cwd=root)
    git("commit", "-q", "-m", f"Track {name}", cwd=root)


def keep_a_local_edit(root: Path) -> None:
    """A local edit of a pinned copy, committed, for `--accept-local`."""
    local = root / KEPT
    local.write_bytes(local.read_bytes() + b"# A local edit, kept.\n")
    git("commit", "-q", "-m", "A local edit", "--", KEPT, cwd=root)


@pytest.mark.parametrize("name", [None, "HEAD"],
                         ids=["no-such-file", "a-file-named-head"])
def test_the_committed_line_names_what_git_lists_over_a_file_named_head(
        standard, root, name):
    """`--accept-local` AT THE COMMIT THE PIN NAMES rewrites the manifest
    with its own bytes, so the commit holds the pin alone, and the line says
    `contracts/shape-pin.yaml` and no more, with a file named `HEAD` in the
    root as without one. On main the `diff-tree` of `HEAD` was ambiguous, git
    answered nothing, and the line named `contracts/shape-pin.yaml,
    project.yaml`, the paths the run was asked to commit."""
    tracked(root, name)
    keep_a_local_edit(root)

    result = run_script(UPDATE, *apply_args(
        standard, root, "a", "--accept-local", KEPT, "--branch", BRANCH))

    assert result.returncode == 0, result.stdout + result.stderr
    said = [line.strip() for line in result.stdout.splitlines()
            if line.strip().startswith("committed on ")]
    assert said == [f"committed on {BRANCH}: {PIN}"], said
    assert git("show", "--name-only", "--format=", "HEAD", "--",
               cwd=root).stdout.split() == [PIN]


@pytest.mark.parametrize("name", [
    None, pytest.param(f"HEAD:{PIN}", marks=NOT_ON_WINDOWS)],
    ids=["no-such-file", "a-file-spelled-as-the-argument"])
def test_the_commit_head_pins_is_read_over_a_file_spelled_as_the_argument(
        standard, root, update_shape, name):
    """`_committed_pin` gives the `commit:` of the pin HEAD holds, as
    `show HEAD:contracts/shape-pin.yaml` prints it. A root that tracks a
    file spelled exactly `HEAD:contracts/shape-pin.yaml` (a directory named
    `HEAD:contracts`) gets the same answer as one without; on main git
    called the argument ambiguous and the answer was empty."""
    tracked(root, name)

    assert update_shape._committed_pin(root, PIN) == standard["a"].lower()


@pytest.mark.parametrize(
    "spelled", [
        None, pytest.param("refs/remotes/origin/{base}:" + PIN,
                           marks=NOT_ON_WINDOWS)],
    ids=["no-such-file", "a-file-spelled-as-the-argument"])
def test_the_copies_a_run_kept_are_read_over_a_file_spelled_as_the_argument(
        standard, root, update_shape, spelled):
    """`_accepted_in_the_pin` names the copies `--accept-local` kept, by
    reading the pin the tracking branch holds on `origin` (`show
    refs/remotes/origin/<base>:contracts/shape-pin.yaml`) against the pin the
    run wrote. A root that tracks a file spelled as that argument is read as
    one without: the one kept copy is named. On main git called the argument
    ambiguous, no pin was read and the answer was `[]`."""
    args = update_shape.build_parser().parse_args(
        apply_args(standard, root, "a", "--accept-local", KEPT, "--branch",
                   BRANCH))
    kind = update_shape.root_kind(root)
    base = update_shape.tracking_branch_of(
        update_shape.load_yaml(root / kind.manifest))
    keep_a_local_edit(root)
    git("fetch", "-q", "origin", base, cwd=root)
    ran = run_script(UPDATE, *apply_args(
        standard, root, "a", "--accept-local", KEPT, "--branch", BRANCH))
    assert ran.returncode == 0, ran.stdout + ran.stderr
    if spelled:
        tracked(root, spelled.format(base=base))
    _, _, _, _, upstream, _, target, kind = update_shape.prepare(args)

    kept = update_shape._accepted_in_the_pin(root, upstream, target, kind)

    assert kept == [KEPT], kept
