# SPDX-License-Identifier: Apache-2.0
"""The plan's two branch names are asked what `execute` asks of them (#420,
#520, and L2-1 on #457).

`execute` hands two plan values to git as branch names: `adopt_branch:`, the
split branch, and `tracking_branch:`, the branch both legs are pushed to. It
holds each to `checked_value`'s alphabet first (`_checked_plan_values`), and
git refuses names inside that alphabet. Measured on main at bfed143, under
`--local-remote-dir`:

- an `adopt_branch:` edited to a name git will not create (`a..b`, `~`,
  `x.lock`, `a/`) checked `plan ok`, and `execute` made both leg
  repositories and died at the extraction's `git checkout -B`; the same plan,
  corrected, was then refused `leg-remote-exists`;
- such a `tracking_branch:` was found since #479, but as
  `plan-tracking-branch-missing`, a branch the source does not have, and
  `plan --tracking-branch a..b` wrote the plan with a NOTE saying so;
- either name outside the alphabet that git accepts (`a=b`) checked `plan
  ok`, and `execute` refused it as `unsafe-value`.

Now `plan` refuses such a `--tracking-branch` as `adopt-bad-tracking-branch`
and writes nothing, and `check` finds, and `execute` refuses before any leg
exists, each of the two names: held to the alphabet first, as `execute`'s own
`unsafe-value` in its own words, and otherwise asked of git with #283's
`refuse_bad_branch`, as `plan-bad-adopt-branch` or `plan-bad-tracking-branch`.
One finding per value: a name outside the alphabet is not asked of git, a
split branch that is either is not looked for where the split is pushed, and
a tracking branch that is either is not also said to be missing from the
source.

Every run here is `plan` or `check`, which read a local source, or `execute`
in this process, refused before any leg; the one end-to-end test needs `git
filter-repo`. Each plan is edited as bytes, so it stays LF on every platform,
and a name git refuses is only ever a plan value, never a branch on disk.
"""

from __future__ import annotations

import importlib.util
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, findings, git, make_source_repo,
                      refused_before_any_leg, run_script, write_plan)

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A source small enough that `plan` asks no question.
TREE = {"README.md": "# Northwind\n", "src/app.py": "print(1)\n",
        "docs/spec.md": "# Spec\n"}
SPLIT_KEY, TRACKING_KEY = "adopt_branch", "tracking_branch"
SPLIT_BRANCH = "adopt/three-repo-shape"
#: Where `plan` writes the plan, and where the leg repositories go.
PLAN_FILE, REMOTES = "adoption-plan.yaml", "remotes"
UNSAFE = "unsafe-value"
BAD_SPLIT, BAD_TRACKING = "plan-bad-adopt-branch", "plan-bad-tracking-branch"
#: Each key, with the code `check` finds a name git refuses under.
KEYS = pytest.mark.parametrize(
    "key, code", [(SPLIT_KEY, BAD_SPLIT), (TRACKING_KEY, BAD_TRACKING)],
    ids=["adopt-branch", "tracking-branch"])
#: Inside `checked_value`'s alphabet and refused by git: #420's table.
DOT_DOT = "a..b"
GIT_REFUSES = [DOT_DOT, "~", "x.lock", "a/", "a//b", ".a"]
#: A name git creates, inside the alphabet, which the source holds: one of
#: #283's own examples.
GIT_CREATES = "lane-3/shape+fix@eagle"
#: Outside the alphabet: `a=b` git accepts, and the source holds (L2-1);
#: `a:b` git refuses too.
EQUALS = "a=b"
OUTSIDE_THE_ALPHABET = [EQUALS, "a:b"]
#: Git's verdict on a name, after the key and the name.
NOT_A_BRANCH = ("which is not a branch name git will create: `git "
                "check-ref-format --branch` refuses it")
#: `execute`'s own words for a value outside the alphabet.
NOT_ON_A_COMMAND_LINE = ("which is not a value this tool will put on a `git` "
                         "or `gh` command line")
#: What `check` says once after a finding about either name.
NAME_REMEDIATION = "Remediation: set each branch name a finding names"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_branch_names", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def world(tmp_path_factory) -> tuple[Path, Path]:
    """One source, holding every name here git creates as a branch, and
    `a`, which is in git's way of a split branch `a/`, and one plan of it.
    `plan` and `check` only read the source, and a test that edits the plan
    edits a copy (`with_branch`)."""
    root = tmp_path_factory.mktemp("branch-names")
    source = make_source_repo(root / "Northwind", tree=TREE, edits=())
    for name in (GIT_CREATES, EQUALS, "a"):
        git("branch", name, cwd=source)
    plan = root / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    return source, plan


def edited(plan: Path, key: str, name: str | None) -> Path:
    """`plan` with its `key:` line set to `name`, double-quoted, as a person
    edits it (`~` alone is YAML's null), or deleted when `name` is None,
    which leaves `execute`'s default. Bytes in and out: LF, as `plan` wrote
    it."""
    lines = plan.read_bytes().split(b"\n")
    (at,) = [index for index, line in enumerate(lines)
             if line.startswith(f"{key}: ".encode())]
    if name is None:
        del lines[at]
    else:
        lines[at] = f'{key}: "{name}"'.encode()
    plan.write_bytes(b"\n".join(lines))
    return plan


def with_branch(world, base: Path, key: str, name: str | None) -> Path:
    """A private copy of the world's plan, `edited`."""
    copy = base / PLAN_FILE
    copy.write_bytes(world[1].read_bytes())
    return edited(copy, key, name)


def execute_args(plan: Path, base: Path) -> Namespace:
    """`execute --yes --local-remote-dir <base>/remotes` of `plan`."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=base / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=base / "work")


# --- `plan` ------------------------------------------------------------------

@pytest.mark.parametrize("name", GIT_REFUSES)
def test_plan_refuses_a_tracking_branch_git_will_not_create(world, tmp_path,
                                                            name):
    """#420's first row. On main `plan` wrote it and said in a NOTE only that
    the source has no such branch, which `check` then found, and the plan
    was written again. It is refused now, in git's words, and nothing is
    written."""
    plan = tmp_path / PLAN_FILE

    result = write_plan(world[0], plan, extra=("--tracking-branch", name))

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"REFUSED adopt-bad-tracking-branch: --tracking-branch is "
            f"{name!r}, {NOT_A_BRANCH}") in result.stderr, result.stderr
    assert not plan.exists()


# --- `check` -----------------------------------------------------------------

@KEYS
@pytest.mark.parametrize("name", [DOT_DOT, "x.lock", "~", "a/"])
def test_check_finds_a_name_git_will_not_create_once(world, tmp_path, key,
                                                     code, name):
    """#420's second and third rows: a hand-edited name git refuses is ONE
    finding, in git's words, under the key's own code. The tracking branch
    is not also said to be missing from the source, and the split branch is
    not looked for where the split is pushed: the name is what is wrong."""
    ((found, detail),) = findings(with_branch(world, tmp_path, key, name))
    assert found == code
    assert detail.startswith(f"{key} is {name!r}, {NOT_A_BRANCH} ("), detail


@pytest.mark.parametrize("key", [SPLIT_KEY, TRACKING_KEY])
def test_check_holds_both_names_to_the_alphabet_execute_holds_them_to(
        world, tmp_path, key):
    """L2-1: `a=b`, which git accepts and the source holds, checked `plan
    ok`, and `execute` refused it as `unsafe-value`; `a:b`, which git
    refuses too, is one finding and not two. Each is `execute`'s own
    refusal, as a finding, in its words. A name git creates inside the
    alphabet checks ok, and so does a plan without the key, which `execute`
    reads as its default."""
    for name in OUTSIDE_THE_ALPHABET:
        assert findings(with_branch(world, tmp_path, key, name)) == [
            (UNSAFE, f"{key} is {name!r}, {NOT_ON_A_COMMAND_LINE}")]
    assert findings(with_branch(world, tmp_path, key, GIT_CREATES)) == []
    assert findings(with_branch(world, tmp_path, key, None)) == []


def test_both_names_are_found_in_one_run_and_the_way_on_said_once(
        world, tmp_path):
    """Two names wrong, two findings, the split branch's first, as
    `execute` asks them; and what to do about them, once."""
    plan = edited(with_branch(world, tmp_path, SPLIT_KEY, DOT_DOT),
                  TRACKING_KEY, EQUALS)

    result = run_script(ADOPT, "check", "--plan", str(plan))

    assert result.returncode == 1, result.stdout + result.stderr
    found = [line.split(":", 1)[0] for line in result.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert found == [f"FINDING {BAD_SPLIT}", f"FINDING {UNSAFE}"], found
    assert result.stderr.count(NAME_REMEDIATION) == 1, result.stderr
    assert "\n2 finding(s) in " in result.stderr


# --- `execute` ---------------------------------------------------------------

@KEYS
def test_execute_refuses_a_name_git_will_not_create_before_any_leg(
        adopter, world, tmp_path, monkeypatch, key, code):
    """`check`'s finding, refused by `_refuse_what_check_finds` before any
    leg exists, word for word: on main a split branch was refused only by
    the extraction's `git checkout -B`, after both legs were made."""
    plan = with_branch(world, tmp_path, key, DOT_DOT)
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == code


@pytest.mark.parametrize("key", [SPLIT_KEY, TRACKING_KEY])
def test_execute_refuses_a_name_outside_the_alphabet_as_check_finds_it(
        adopter, world, tmp_path, monkeypatch, key):
    """`_checked_plan_values` refuses it first, as it always did, and its
    refusal is now `check`'s finding: one code, one sentence."""
    plan = with_branch(world, tmp_path, key, EQUALS)
    ((code, detail),) = findings(plan)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    args = execute_args(plan, tmp_path)

    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)

    assert (caught.value.code, caught.value.detail) == (code, detail)
    assert not (tmp_path / REMOTES).exists()


@needs_filter_repo
def test_a_split_branch_git_will_not_create_makes_no_leg_and_the_fix_adopts(
        tmp_path):
    """#420's third and fifth rows, end to end. On main `execute` made both
    leg repositories, died at the extraction's `git checkout -B`, and the
    corrected plan, run into the same `--local-remote-dir`, was refused
    `leg-remote-exists`. Now nothing is made, and the corrected plan adopts
    there."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=())
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    remotes = tmp_path / REMOTES
    flags = ("--plan", str(plan), "--yes", "--local-remote-dir", str(remotes),
             "--work-dir", str(tmp_path / "work"))

    edited(plan, SPLIT_KEY, DOT_DOT)
    refused = run_script(ADOPT, "execute", *flags)

    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {BAD_SPLIT}: 1 finding(s) in " in refused.stderr
    assert not remotes.exists()
    assert git("for-each-ref", "--format=%(refname:short)", "refs/heads/",
               cwd=source).stdout.split() == ["main"]
    edited(plan, SPLIT_KEY, SPLIT_BRANCH)
    adopted = run_script(ADOPT, "execute", *flags)
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout
