# SPDX-License-Identifier: Apache-2.0
"""The tracking branch follows the source's default branch (#479).

`tracking_branch` is the branch both legs are pushed to, the branch the
assembly root's `project.yaml` says the project tracks, and the base `execute`
opens the split's pull request against. `plan` defaulted it to `main` whatever
the source used, so a `master` or `trunk` source was adopted all the way, both
legs created and pushed and the split pushed and verified, and then its pull
request was refused (`Base ref must be a branch`), with the same refused
command printed as the way out.

`plan` now records the branch it reads the source at unless `--tracking-branch`
names another, and `check` finds, and `execute` refuses before any leg exists,
a tracking branch that is no branch of the source
(`plan-tracking-branch-missing`). The branches are the source's remote
`origin`'s when it has fetched any, since that is the repository the pull
request goes to, and its own otherwise.

The GitHub-mode runs, a `master` and a `trunk` source whose pull request opens
against that branch, a base the source lacks refused before any `gh` runs, and
one the clone remembers after GitHub renamed it, which `execute` asks the
remote about, are in `tests/test_adopt_github_exits.py`, beside the other exits
a GitHub run has. The only `gh` run here is `check`'s: given no
`--local-remote-dir`, and once nothing before it ends `check` and the plan's
names and `org:` pass, it asks `gh repo view` once of the spec leg's repository
and once of the code leg's (#798), and off Windows the session's guard answers
each as a `gh` with no login does (`tests/gh_guard.py`). Every run below is
`plan` and `check`, which read a local source, or `execute --local-remote-dir`,
which refuses before any leg or adopts.

The branch the source is read at is one of its own (#797). A clone made with
`git clone -b dev` has `origin/HEAD` naming `main` and no `main` of its own,
and `plan`, `check` and `execute` ended `git-failed` in `git rev-parse main`,
with no remedy, whatever `--tracking-branch` said. Now that clone is refused
by name, with both ways through, and `--tracking-branch dev` reads it at
`dev`. A default branch outside the alphabet a command line may carry, such
as `café`, is refused as before, and the refusal now says the way past it.

A branch git could not list is no branch the source lacks (#1219). A
directory of the source's refs this user cannot list was read as holding
none, and a ref git could not reach as not there, so a clone whose
`.git/refs/heads` was at mode 000 was refused as having no branch of its
own, "(its branches: none)". Each is `source-unreadable` now, naming the
directory, with the `chmod` cure; the rows are at the end of this file.

So is one that may hold the split branch an earlier run left (#1257):
with the source's `.git/refs/heads/adopt` at mode 000, `check` said
`plan ok` over the `adopt/three-repo-shape` it finds as
`adopt-branch-exists` once it can list that directory, and `execute
--local-remote-dir` made and pushed both legs before its split push met
that branch. Their rows follow #1219's.
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import stat
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, load_without_bytecode,
                      make_source_repo, run_script, spelled, write_plan)
from test_adopt_unsearchable_source import (CURE, DENIED, UNREADABLE,
                                            needs_a_mode, recording_gh, said)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: A source small enough that `plan` asks no question.
TREE = {"README.md": "# Northwind\n", "src/app.py": "print(1)\n",
        "docs/spec.md": "# Spec\n"}
MISSING = "plan-tracking-branch-missing"
REMEDIATION = "Remediation: set `tracking_branch:` in the plan"
#: The plan's last follow-up, whole, for the `Northwind` that `planned` adopts.
#: It names the pull request's base by the plan's key, never its value
#: (#493's review, F3). It is a review: `execute` opens that pull request
#: itself against GitHub, so it is never "open the split as a pull request",
#: and the legs it creates and pushes first are extracted, never "seeded"
#: (#523, N1). `plan` writes it, `check` prints it, and the split commit and
#: the pull request's body list it.
PULL_REQUEST_FOLLOW_UP = (
    "review the root's diff together with Northwind-spec and Northwind-code, "
    "the two new repositories `execute` creates and pushes before the split; "
    "against GitHub it opens the split's pull request itself, whose base is "
    "the plan's `tracking_branch`, the branch the assembly root and both legs "
    "track")
#: What it said until #523, which no follow-up says now.
OPEN_THE_SPLIT = "open the split as a pull request"


def planned(tmp_path, source, *flags: str):
    """`plan` of `source` into `tmp_path`: the run, and the plan it wrote."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    plan = tmp_path / "adoption-plan.yaml"
    result = write_plan(source, plan, extra=flags)
    assert result.returncode == 0, result.stderr + result.stdout
    return result, plan


def tracking_branch_of(plan) -> str:
    return load_yaml(plan)["tracking_branch"]


def check(plan):
    return run_script(ADOPT, "check", "--plan", str(plan))


def retracked(plan, old: str, new: str) -> None:
    """The plan's `tracking_branch:` edited by hand, LF as `plan` wrote it."""
    text = plan.read_text(encoding="utf-8")
    line = f"\ntracking_branch: {old}\n"
    assert line in text, text
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace(line, f"\ntracking_branch: {new}\n", 1))


def test_plan_records_the_branch_it_reads_the_source_at(tmp_path):
    """No flag: the source's own branch, `master`, which `plan` also records
    as `source.default_branch`, and the last follow-up names the plan's
    `tracking_branch` as the pull request's base. An explicit
    `--tracking-branch` still wins."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="master")
    git("branch", "develop", cwd=source)

    result, plan = planned(tmp_path / "default", source)
    written = load_yaml(plan)
    assert written["source"]["default_branch"] == "master"
    assert written["tracking_branch"] == "master", written
    assert written["follow_ups"][-1] == PULL_REQUEST_FOLLOW_UP, \
        written["follow_ups"]
    assert not [item for item in written["follow_ups"]
                if OPEN_THE_SPLIT in item or "seeded" in item], \
        written["follow_ups"]
    assert MISSING not in result.stdout + result.stderr

    result, plan = planned(tmp_path / "explicit", source,
                           "--tracking-branch", "develop")
    assert tracking_branch_of(plan) == "develop"
    assert MISSING not in result.stdout + result.stderr
    assert check(plan).returncode == 0


def test_the_follow_up_names_no_branch_a_hand_edit_can_leave_behind(tmp_path):
    """The follow-ups are written once, by `plan`, and `execute` copies them
    into the split commit, which is also the pull request's body. The last
    one named the branch, so a plan made with `--tracking-branch develop`
    and then edited to `master`, as `plan-tracking-branch-missing`'s
    remediation asks, checked ok saying `develop`, and its pull request
    opened against `master` with a body saying `develop` (#493's review,
    F3). It names the plan's key now, which no edit leaves behind."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="master")
    git("branch", "develop", cwd=source)
    _, plan = planned(tmp_path, source, "--tracking-branch", "develop")
    retracked(plan, "develop", "master")

    result = check(plan)

    assert result.returncode == 0, result.stdout + result.stderr
    (said,) = [line for line in result.stdout.splitlines()
               if "the plan's `tracking_branch`" in line]
    assert said == f"  follow-up: {PULL_REQUEST_FOLLOW_UP}", said
    assert "develop" not in said and "master" not in said, said
    assert OPEN_THE_SPLIT not in result.stdout, result.stdout


def test_check_finds_a_tracking_branch_the_source_does_not_have(tmp_path):
    """A plan whose `tracking_branch:` was edited to a branch the source does
    not have is a finding of `check`, naming the value, the branches the
    source has and its default branch; the remediation is printed once. It
    used to check ok, and the run it led to pushed both legs and the split
    before GitHub refused the pull request."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="master")
    git("branch", "develop", cwd=source)
    _, plan = planned(tmp_path, source)
    retracked(plan, "master", "main")

    result = check(plan)

    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"FINDING {MISSING}: `tracking_branch` is `main`, which is no "
            "branch of the source (its branches: `develop`, `master`; the "
            "source's default branch is `master`). `execute` pushes both legs "
            "to it,") in result.stderr, result.stderr
    assert "`Base ref must be a branch`" in result.stderr
    assert result.stderr.count(REMEDIATION) == 1, result.stderr
    assert "\n1 finding(s) in " in result.stderr


@pytest.mark.skipif(shutil.which("git-filter-repo") is None,
                    reason="git filter-repo is not installed: "
                           "`pip install git-filter-repo`")
def test_execute_refuses_it_before_any_leg_exists(tmp_path):
    """`execute` refuses every finding of `check`'s before it creates a leg
    repository (#168), and this one with them: under `--local-remote-dir`
    the run used to make both legs at `main` and exit 0, over a project
    tracking a branch its root does not have."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="master")
    _, plan = planned(tmp_path, source)
    retracked(plan, "master", "main")

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {MISSING}: 1 finding(s) in " in result.stderr
    assert "no leg repository was created" in result.stderr
    assert REMEDIATION in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_the_branches_asked_are_origins_once_the_source_has_fetched_any(
        tmp_path):
    """A clone knows the repository its pull request goes to by `origin`'s
    branches. One only `origin` has, `develop`, checks ok; one only the clone
    has, `wip`, never pushed, is what GitHub would refuse as a base, so
    `plan` notes it and `check` finds it, naming `origin`."""
    seed = make_source_repo(tmp_path / "seed", tree=TREE, edits=())
    git("branch", "develop", cwd=seed)
    # Under `testorg/`, as #499 needed while `plan` read a path `origin`'s
    # last two directories as the source's repository; since #521 a path
    # names none, and is compared with nothing.
    remote = tmp_path / "testorg" / "Northwind.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(remote),
        cwd=tmp_path)
    source = tmp_path / "Northwind"
    git(*FILE_PROTOCOL, "clone", "-q", str(remote), str(source), cwd=tmp_path)
    git("branch", "wip", cwd=source)

    _, plan = planned(tmp_path / "develop", source,
                      "--tracking-branch", "develop")
    checked = check(plan)
    assert checked.returncode == 0, checked.stdout + checked.stderr

    result, plan = planned(tmp_path / "wip", source, "--tracking-branch", "wip")
    found = ("is `wip`, which is no branch of the source's remote `origin` "
             "(its branches: `develop`, `main`; the source's default branch "
             "is `main`)")
    assert f"NOTE the tracking branch {found}" in result.stdout, result.stdout
    assert f"`check` reports this as `{MISSING}`" in result.stdout
    checked = check(plan)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert f"FINDING {MISSING}: `tracking_branch` {found}" in checked.stderr


def test_a_default_branch_no_command_line_can_carry_is_named_as_the_default(
        tmp_path):
    """The source's own branch is put on a `git` command line like any
    tracking branch, so one outside that alphabet is refused before a plan
    is written; and since nobody passed it, the refusal says where it came
    from, as `--elected-by` is named when `git config user.name` filled it
    in. It used to plan `main`, a branch this source does not have."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="feat#1")
    plan = tmp_path / "adoption-plan.yaml"

    result = write_plan(source, plan)

    assert result.returncode == 2, result.stdout + result.stderr
    assert ("unsafe-value: --tracking-branch (not given, so the source's "
            "default branch) is 'feat#1'") in result.stderr, result.stderr
    assert not plan.exists()


@pytest.mark.parametrize("value", [pytest.param("", id="empty"),
                                   pytest.param("feat#1", id="feat-hash-1")])
def test_a_branch_the_person_passed_is_named_as_passed_when_refused(
        tmp_path, value):
    """#601's rider (RV567): a `--tracking-branch` the person PASSED is
    refused as the flag they typed, with `<given>` as the value, and never as
    "not given, so the source's default branch", which is only for the value
    `plan` filled in. An empty one is a value too: it is refused, where a
    test of the argument's truth would take it for none and plan the
    source's own branch without a word."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"

    result = write_plan(source, plan, extra=("--tracking-branch", value))

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"REFUSED unsafe-value: --tracking-branch is {value!r}, which is "
            "not a value this tool will put on a `git` or `gh` command "
            "line") in result.stderr, result.stderr
    assert "not given" not in result.stderr, result.stderr
    assert not plan.exists()


def test_a_passed_branch_equal_to_the_sources_own_is_still_named_as_passed(
        tmp_path):
    """Passed is what the person did, not whether the value differs from the
    source's default: `--tracking-branch feat#1` over a source ON `feat#1` is
    a flag typed, so it is refused as one."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="feat#1")
    plan = tmp_path / "adoption-plan.yaml"

    result = write_plan(source, plan, extra=("--tracking-branch", "feat#1"))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "unsafe-value: --tracking-branch is 'feat#1', which" in \
        result.stderr, result.stderr
    assert "not given" not in result.stderr, result.stderr
    assert not plan.exists()


# --- the source's own branch, by its full name (#797) -----------------------

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")
#: How a source whose `origin/HEAD` names a branch it has no branch of its
#: own for is refused, by `plan`, `check` and `execute` alike (L1-71's second
#: case on #457).
NOT_LOCAL = "REFUSED source-default-branch-not-local: "
#: What it says of the branch `origin/HEAD` names, `main`.
NAMES_MAIN = ("the source's `origin/HEAD` names `main`, the default branch "
              "its remote `origin` had when it was last asked, and the "
              "source has no branch `main` of its own (its branches: `dev`)")
#: The two ways through it, as its remediation names them, and what the
#: second promises of `check` and `execute`.
MAKE_IT_LOCAL = "`git branch main origin/main`, run in the source"
OR_TRACK_ANOTHER = ("run `plan` with `--tracking-branch` naming a branch "
                    "the source has, and the source is read at that branch")
WHILE_IT_HAS_NONE = ("`check` and `execute` then read it at that branch "
                     "while the source has no branch `main` of its own.")
#: The way through for an `origin/HEAD` its remote no longer has.
ASK_AGAIN = "`git remote set-head origin --auto`"
#: What `check` says once it reads the source where `plan` did.
PLAN_OK = "\nplan ok\n"
#: The flag that names the branch to track, and the plan `write_plan` writes.
TRACKING = "--tracking-branch"
PLAN_NAME = "adoption-plan.yaml"


def cloned_with(tmp_path, branch: str) -> Path:
    """`git clone -b <branch>` of a repository whose default branch is
    `main` and which has a `dev` a commit ahead of it: `origin/HEAD` names
    `origin/main`, and `branch` is the clone's one branch."""
    seed = make_source_repo(tmp_path / "seed", tree=TREE, edits=())
    git("switch", "-q", "-c", "dev", cwd=seed)
    git("commit", "-q", "--allow-empty", "-m", "Ahead on dev", cwd=seed)
    git("switch", "-q", "main", cwd=seed)
    remote = tmp_path / "testorg" / "Northwind.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(remote),
        cwd=tmp_path)
    source = tmp_path / "Northwind"
    git(*FILE_PROTOCOL, "clone", "-q", "-b", branch, str(remote), str(source),
        cwd=tmp_path)
    return source


def tip(source, branch: str) -> str:
    """The commit the source's own `branch` names."""
    return git("rev-parse", f"refs/heads/{branch}", cwd=source).stdout.strip()


def test_a_clone_of_another_branch_is_refused_by_name_with_both_ways_through(
        tmp_path):
    """L1-71's second case: on main, `plan` of a `git clone -b dev` source
    was refused `git-failed` in `git rev-parse main`, in git's words, with
    no remedy. It is refused by name now, before any plan is written, with
    both ways through; and the first, `main` made the source's own, plans
    the source at it."""
    source = cloned_with(tmp_path, "dev")
    plan = tmp_path / PLAN_NAME

    result = write_plan(source, plan)

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"{NOT_LOCAL}{NAMES_MAIN}" in result.stderr, result.stderr
    assert MAKE_IT_LOCAL in result.stderr, result.stderr
    assert OR_TRACK_ANOTHER in result.stderr, result.stderr
    assert WHILE_IT_HAS_NONE in result.stderr, result.stderr
    assert "git-failed" not in result.stderr, result.stderr
    assert not plan.exists()
    git("branch", "main", "origin/main", cwd=source)
    _, plan = planned(tmp_path / "made", source)
    assert load_yaml(plan)["source"]["commit"] == tip(source, "main")


def test_a_clone_of_another_branch_is_read_at_the_tracking_branch_given(
        tmp_path):
    """The other way through, `--tracking-branch dev`, was refused as the
    first run was: `Source.open` asked for `main` before anything else. Now
    the source is read at `dev`, which the plan records with ITS commit,
    and `check` reads it where `plan` did."""
    source = cloned_with(tmp_path, "dev")

    result, plan = planned(tmp_path, source, TRACKING, "dev")

    written = load_yaml(plan)
    assert written["source"]["default_branch"] == "dev", written["source"]
    assert written["source"]["commit"] == tip(source, "dev")
    assert written["tracking_branch"] == "dev"
    assert MISSING not in result.stdout + result.stderr
    checked = check(plan)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert PLAN_OK in checked.stdout


def test_check_of_a_plan_whose_branch_was_deleted_is_refused_by_name(
        tmp_path):
    """The issue's `check` row: a plan of a clone on `main`, whose `main`
    is then deleted with `dev` checked out. On main `check` said
    `git-failed`, `git rev-parse main`; now it refuses as `plan` does,
    naming `main` once."""
    source = cloned_with(tmp_path, "main")
    _, plan = planned(tmp_path, source)
    git("switch", "-q", "dev", cwd=source)
    git("branch", "-q", "-D", "main", cwd=source)

    result = check(plan)

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"{NOT_LOCAL}{NAMES_MAIN}. A clone made with `git clone -b "
            "<branch>` has none, nor does one whose own was deleted") in \
        result.stderr, result.stderr
    assert MAKE_IT_LOCAL in result.stderr, result.stderr


def test_an_origin_head_its_remote_renamed_names_the_way_to_ask_again(
        tmp_path):
    """r797's third finding: a clone made while its repository's default
    branch was `master`, which GitHub then renamed `main`. The clone's own
    branch is renamed to match and pruned, but `origin/HEAD` still names
    `master`, which `origin` no longer has. `git branch master
    origin/master` cannot run there, so the refusal asks `origin` for its
    default branch again instead, and that plans the source at `main`."""
    seed = make_source_repo(tmp_path / "seed", tree=TREE, edits=(),
                            branch="master")
    remote = tmp_path / "testorg" / "Northwind.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(remote),
        cwd=tmp_path)
    source = tmp_path / "Northwind"
    git(*FILE_PROTOCOL, "clone", "-q", str(remote), str(source), cwd=tmp_path)
    git("branch", "-m", "master", "main", cwd=remote)
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=remote)
    git("branch", "-m", "master", "main", cwd=source)
    git(*FILE_PROTOCOL, "fetch", "-q", "--prune", "origin", cwd=source)
    git("branch", "-q", "-u", "origin/main", "main", cwd=source)
    # As a clone made before the rename keeps it, whatever this git's fetch
    # does with a remote HEAD.
    git("symbolic-ref", "refs/remotes/origin/HEAD",
        "refs/remotes/origin/master", cwd=source)

    result = write_plan(source, tmp_path / PLAN_NAME)

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"{NOT_LOCAL}the source's `origin/HEAD` names `master`, the "
            "default branch its remote `origin` had when it was last asked, "
            "and the source has no branch `master` of its own (its "
            "branches: `main`)") in result.stderr, result.stderr
    assert ("Remediation: its remote `origin` has no branch `master` "
            f"either, as the source last fetched it: ask `origin` for its "
            f"default branch again, {ASK_AGAIN}, run in the source.") in \
        result.stderr, result.stderr
    assert "origin/master`" not in result.stderr, result.stderr
    git(*FILE_PROTOCOL, "remote", "set-head", "origin", "--auto", cwd=source)
    _, plan = planned(tmp_path / "asked", source)
    assert load_yaml(plan)["source"]["default_branch"] == "main"


@pytest.mark.parametrize("head", ["detached", "unborn"])
def test_a_default_branch_with_no_commit_is_read_at_the_tracking_branch(
        tmp_path, head):
    """`--tracking-branch` needs no default branch to resolve. With no
    `origin/HEAD`, a detached HEAD has `main` guessed, which this source
    does not have, and an orphan HEAD is on a branch with no commit yet:
    each was refused `git-failed` in `git rev-parse` of it, whatever
    `--tracking-branch` named. Now the source is read at the branch given,
    and `check` reads it there again."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="trunk")
    if head == "detached":
        git("checkout", "-q", "--detach", cwd=source)
    else:
        git("switch", "-q", "--orphan", "new", cwd=source)

    _, plan = planned(tmp_path / "plan", source, TRACKING, "trunk")

    written = load_yaml(plan)
    assert written["source"]["default_branch"] == "trunk", written["source"]
    assert written["source"]["commit"] == tip(source, "trunk")
    checked = check(plan)
    assert checked.returncode == 0, checked.stdout + checked.stderr


@needs_filter_repo
def test_a_clone_of_another_branch_is_adopted_at_the_tracking_branch(
        tmp_path):
    """`execute` of that plan reads the source where `plan` did, and the
    split is made on `dev`'s commit, which is not `main`'s."""
    source = cloned_with(tmp_path, "dev")
    _, plan = planned(tmp_path, source, TRACKING, "dev")

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    split = git("rev-parse", "refs/heads/adopt/three-repo-shape^",
                cwd=source).stdout.strip()
    assert split == tip(source, "dev")


def test_a_default_branch_outside_the_alphabet_names_the_way_past_it(
        tmp_path):
    """L1-71's first case: a source whose only branch is `café` was refused
    `unsafe-value` with the alphabet alone as its remedy, though a way past
    it works. The refusal says it now: a branch whose name is in the
    alphabet, at the same commit, given as `--tracking-branch`. Followed,
    `plan` reads the source at `café` and `check` finds nothing."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=(),
                              branch="café")
    plan = tmp_path / PLAN_NAME

    result = write_plan(source, plan)

    assert result.returncode == 2, result.stdout + result.stderr
    said = " ".join(result.stderr.split())
    assert ("So make a branch whose name matches at the same commit, in the "
            "source with that branch checked out (`git branch main`, and `git "
            "push origin main` where the source has a remote `origin`), and "
            "pass it: `--tracking-branch main`.") in said, said
    assert not plan.exists()
    git("branch", "main", cwd=source)
    _, plan = planned(tmp_path / "past", source, TRACKING, "main")
    written = load_yaml(plan)
    assert written["source"]["default_branch"] == "café", written["source"]
    assert written["tracking_branch"] == "main"
    checked = check(plan)
    assert checked.returncode == 0, checked.stdout + checked.stderr


# --- a directory of the source's refs git cannot list (#1219) ---------------
#
# `git for-each-ref` passes over a directory of refs it cannot list, without
# a word and exit 0; `git symbolic-ref -q` exits 128, "No such ref", of a
# ref it cannot reach, where it exits 1 of one that is not there. ON
# 50ce8ab1 (2026-10-23), git 2.43.0, Python 3.12.3, uid 1000, a stub `gh`
# and local remotes:
#
# - `.git/refs/heads` at mode 000 or `--x`, or `.git/refs` at `--x`: `plan
#   --source`, and `check` and `execute` of a plan recording `cloned: true`,
#   were `source-default-branch-not-local`, "the source's `origin/HEAD`
#   names `main` ... (its branches: none)"; so was a clone on `release/v1`
#   with `refs/heads/release` at 000 or `--x`.
# - `refs/heads/feature` at `--x`, HEAD on `feature/x` beside `main`: "its
#   HEAD is on `feature/x`, which has no commit yet"; at 000, HEAD was read
#   as detached and `plan` written at `main`, and `check` found `plan-stale`.
# - `refs/remotes/origin` at 000, `origin/HEAD` naming `main` and only a
#   `dev` of the source's own: `plan` written at `dev`, its `origin/HEAD`
#   passed over; at `--x`, the remote's branches fetched loose, refused
#   saying `origin` has no `main` "either", and to ask it again.
#
# Now each is `source-unreadable`, naming the directory, with the `chmod`
# cure, before anything is cloned or made, and `gh` is never asked. A real
# mode runs in a child, skipped on Windows and as root (`needs_a_mode`); the
# same questions are asked in-process too, which runs everywhere.

#: The modes a directory of refs is put at: no listing and no search, a
#: search alone, a listing alone.
REF_MODES = [pytest.param(0o000, id="000"), pytest.param(0o100, id="x-only"),
             pytest.param(0o400, id="r-only")]
#: What `source-unreadable` cannot tell, by the refs git could not list.
BRANCHES_UNTOLD = "the source's branches"
ORIGIN_UNTOLD = "the branches of the source's remote `origin`"
#: What 50ce8ab1 said of a clone whose `.git/refs/heads` it could not list.
NO_BRANCHES = "(its branches: none)"
#: The GitHub url the source's `origin` names, which `plan` records.
NORTHWIND_URL = "https://github.com/testorg/Northwind.git"
#: `plan`'s flags after `--source <it>`, as `write_plan` passes them.
PLAN_FLAGS = ("--project", "Northwind", "--org", "testorg", "--elected-by",
              "Test Human", "--elected-on", "2026-09-02")


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "adopt_tracking_branch")


@contextlib.contextmanager
def refs_at(directory: Path, mode: int):
    """`directory` at `mode` for the `with`, its mode given back in a
    `finally`. The mode is asserted to bite: this user can no longer both
    list and search it, which a file system that ignores modes would let
    pass for the wrong reason."""
    before = stat.S_IMODE(directory.stat().st_mode)
    directory.chmod(mode)
    try:
        assert not os.access(directory, os.R_OK | os.X_OK), directory
        yield directory
    finally:
        directory.chmod(before)


def refs_refused(source: Path, part: str, untold: str,
                 reason: str = DENIED) -> str:
    """The detail `source-unreadable` names `part` of the refs in the
    source's `.git` with, and the directory whole."""
    whole = os.path.join(os.path.realpath(source), ".git", *part.split("/"))
    return (f"the source's `{part}`, {spelled(whole)}: {reason}, so "
            f"{untold} cannot be told")


def a_clone(root: Path, default: str = "main") -> Path:
    """`git clone` of a repository whose default branch is `default`, with a
    `dev` beside it: `origin/HEAD` names `default`, the clone's one branch,
    and its `origin` is the GitHub url `plan` records."""
    seed = make_source_repo(root / "seed", tree=TREE, edits=(),
                            branch=default)
    git("branch", "dev", cwd=seed)
    remote = root / "testorg" / "Northwind.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(remote),
        cwd=root)
    source = root / "Northwind"
    git(*FILE_PROTOCOL, "clone", "-q", str(remote), str(source), cwd=root)
    git("remote", "set-url", "origin", NORTHWIND_URL, cwd=source)
    return source


def a_fetched_source(root: Path, own: str) -> Path:
    """A source as `git init`, `git remote add` and `git fetch` leave one:
    its remote's branches, `main` and `dev`, loose in `refs/remotes/origin`
    (a clone packs them), `origin/HEAD` naming `main`, and one branch of its
    own, `own`, made from its remote's."""
    seed = make_source_repo(root / "seed", tree=TREE, edits=())
    git("branch", "dev", cwd=seed)
    remote = root / "testorg" / "Northwind.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", str(seed), str(remote),
        cwd=root)
    source = root / "Northwind"
    source.mkdir()
    git("init", "-q", "-b", own, ".", cwd=source)
    git("remote", "add", "origin", str(remote), cwd=source)
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", cwd=source)
    git("remote", "set-head", "origin", "main", cwd=source)
    git("checkout", "-q", "-B", own, f"origin/{own}", cwd=source)
    git("remote", "set-url", "origin", NORTHWIND_URL, cwd=source)
    assert not (source / ".git" / "packed-refs").exists()
    return source


def a_repository_on(root: Path, branch: str) -> Path:
    """A repository with no remote: `main`, and HEAD on `branch`, a commit
    ahead of it."""
    source = make_source_repo(root / "Northwind", tree=TREE, edits=())
    git("switch", "-q", "-c", branch, cwd=source)
    git("commit", "-q", "--allow-empty", "-m", "Ahead", cwd=source)
    return source


def planned_as_cloned(root: Path, source: Path, *flags: str) -> Path:
    """`plan --source <source>` while git reads it whole, and the plan it
    wrote, recorded as a clone `plan` made (`source.cloned: true`), as `plan
    --source <org/repo>` records its clone."""
    plan = root / PLAN_NAME
    result = write_plan(source, plan, extra=(
        "--work-dir", str(root / "plan-work"), *flags))
    assert result.returncode == 0, result.stdout + result.stderr
    assert MISSING not in result.stdout + result.stderr
    text = plan.read_bytes()
    assert text.count(b"\n  cloned: false\n") == 1, text
    plan.write_bytes(text.replace(b"\n  cloned: false\n",
                                  b"\n  cloned: true\n"))
    return plan


def asked_of(root: Path, verb: str, source: Path, plan: Path | None,
             env: dict, *flags: str) -> subprocess.CompletedProcess:
    """`plan --source <source> <flags>`, or `<verb> --plan <plan>` with a
    work directory and local remotes of its own."""
    if verb == "plan":
        return run_script(ADOPT, "plan", "--source", str(source),
                          *PLAN_FLAGS, *flags, "--out",
                          str(root / "again.yaml"), "--work-dir",
                          str(root / "again-work"), env=env)
    return run_script(ADOPT, verb, "--plan", str(plan),
                      *(["--yes"] if verb == "execute" else []),
                      "--work-dir", str(root / f"{verb}-work"),
                      "--local-remote-dir", str(root / "remotes"), env=env)


def assert_refs_refused(proc, detail: str, root: Path, log: Path, *,
                        written: bool = False) -> None:
    """Exit 2, `source-unreadable` with `detail` and the cure, none of the
    answers 50ce8ab1 gave, `gh` never asked and nothing made; and no plan
    written again unless `written`, `plan` having written it before the
    report's last reads."""
    text = said(proc)
    assert proc.returncode == 2, text
    assert f"{UNREADABLE}{detail}" in proc.stderr, text
    assert CURE in proc.stderr, text
    for words in (NOT_LOCAL, NO_BRANCHES, ASK_AGAIN, MISSING, "plan-stale",
                  "Traceback"):
        assert words not in text, (words, text)
    assert log.read_bytes() == b""
    assert (root / "again.yaml").exists() is written
    assert not (root / "remotes").exists()


@needs_a_mode
@pytest.mark.parametrize("mode", REF_MODES)
@pytest.mark.parametrize("verb", ["plan", "check", "execute"])
def test_a_clone_whose_branches_git_cannot_list_is_refused_by_name(
        tmp_path, verb, mode):
    """RV1186's case: a clone `plan` made, its `.git/refs/heads` at mode 000,
    `--x` or `r--`. On 50ce8ab1 `plan`, `check` and `execute` alike were
    `source-default-branch-not-local`, "(its branches: none)", with a `git
    branch` to run as the way out. Now `source-unreadable`, naming the
    directory, exit 2."""
    source = a_clone(tmp_path)
    plan = planned_as_cloned(tmp_path, source)
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / "refs" / "heads", mode):
        proc = asked_of(tmp_path, verb, source, plan, env)

    assert_refs_refused(proc, refs_refused(source, "refs/heads",
                                           BRANCHES_UNTOLD), tmp_path, log)


@needs_a_mode
def test_a_clone_whose_refs_git_can_search_and_not_list_is_named(tmp_path):
    """`.git/refs` at `--x`: git takes the repository for one, since it
    asks `refs` with a search, and lists nothing in it, so on 50ce8ab1 the
    clone had no branch of its own. Now `refs` is named."""
    source = a_clone(tmp_path)
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / "refs", 0o100):
        proc = asked_of(tmp_path, "plan", source, None, env)

    assert_refs_refused(proc, refs_refused(source, "refs", BRANCHES_UNTOLD),
                        tmp_path, log)


@needs_a_mode
@pytest.mark.parametrize("mode", REF_MODES)
@pytest.mark.parametrize("verb", ["plan", "check"])
@pytest.mark.parametrize(("layout", "part"), [
    pytest.param("origin-names-it", "refs/heads/release",
                 id="origin-names-it"),
    pytest.param("head-is-on-it", "refs/heads/feature", id="head-is-on-it"),
])
def test_a_nested_directory_of_branches_git_cannot_list_is_named(
        tmp_path, layout, part, verb, mode):
    """A branch named `release/v1` is kept in `refs/heads/release`, which git
    lists apart. A clone on it, `origin/HEAD` naming it, and a repository
    with no remote, its HEAD on `feature/x` beside `main`, with that
    directory at mode 000, `--x` or `r--`: on 50ce8ab1 refused as having no
    such branch, or, HEAD on it at 000, read at `main`. Now that directory
    is named."""
    source = (a_clone(tmp_path, "release/v1") if layout == "origin-names-it"
              else a_repository_on(tmp_path, "feature/x"))
    plan = planned_as_cloned(tmp_path, source)
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / Path(*part.split("/")), mode):
        proc = asked_of(tmp_path, verb, source, plan, env)

    assert_refs_refused(proc, refs_refused(source, part, BRANCHES_UNTOLD),
                        tmp_path, log)


@needs_a_mode
@pytest.mark.parametrize("mode", REF_MODES)
def test_a_remote_whose_branches_git_cannot_list_is_named(tmp_path, mode):
    """A source whose `origin/HEAD` names `main`, which only its remote has:
    read whole, it is `source-default-branch-not-local`, with `git branch
    main origin/main` as the way through. Its `refs/remotes/origin` at mode
    000: on 50ce8ab1 git said "No such ref" of the `origin/HEAD`, which was
    passed over, and the plan written at `dev`; at `--x`, `origin` had no
    `main` "either", and was to be asked again. Now the directory is
    named."""
    source = a_fetched_source(tmp_path, "dev")
    env, log = recording_gh(tmp_path / "gh-bin")
    whole = asked_of(tmp_path, "plan", source, None, env)
    assert (f"{NOT_LOCAL}the source's `origin/HEAD` names `main`") in \
        whole.stderr, said(whole)
    assert MAKE_IT_LOCAL in whole.stderr, said(whole)

    with refs_at(source / ".git" / "refs" / "remotes" / "origin", mode):
        proc = asked_of(tmp_path, "plan", source, None, env)

    assert_refs_refused(proc, refs_refused(source, "refs/remotes/origin",
                                           ORIGIN_UNTOLD), tmp_path, log)


@needs_a_mode
@pytest.mark.parametrize("verb", ["check", "execute"])
def test_an_origin_head_git_cannot_reach_is_not_passed_over(tmp_path, verb):
    """The same source planned with `--tracking-branch dev`, recorded as a
    clone `plan` made, and its `refs/remotes/origin` then at mode 000: on
    50ce8ab1 `check` read it at HEAD's branch, `plan ok`, what its
    `origin/HEAD` names untold. Now `check` and `execute` are refused."""
    source = a_fetched_source(tmp_path, "dev")
    plan = planned_as_cloned(tmp_path, source, TRACKING, "dev")
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / "refs" / "remotes" / "origin", 0o000):
        proc = asked_of(tmp_path, verb, source, plan, env)

    assert_refs_refused(proc, refs_refused(source, "refs/remotes/origin",
                                           ORIGIN_UNTOLD), tmp_path, log)


@needs_a_mode
@pytest.mark.parametrize("verb", ["plan", "check"])
def test_a_tracking_branch_git_cannot_list_is_not_called_missing(tmp_path,
                                                                 verb):
    """A source on a `main` of its own, tracking `dev`, which only its
    remote has, fetched loose; its `refs/remotes/origin` at `--x`, so
    `origin/HEAD` is read and `origin`'s branches are not listed. On
    50ce8ab1 `plan` noted, and `check` found, `plan-tracking-branch-missing`:
    `dev` "is no branch of the source (its branches: `main`; ...)", read
    from its own branches. Now `source-unreadable`; `plan` has written the
    plan by then, as before any of the report's last reads."""
    source = a_fetched_source(tmp_path, "main")
    plan = planned_as_cloned(tmp_path, source, TRACKING, "dev")
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / "refs" / "remotes" / "origin", 0o100):
        proc = asked_of(tmp_path, verb, source, plan, env, TRACKING, "dev")

    assert_refs_refused(proc, refs_refused(source, "refs/remotes/origin",
                                           ORIGIN_UNTOLD), tmp_path, log,
                        written=verb == "plan")


def test_a_source_with_no_branch_of_its_own_is_still_said_to_have_none(
        tmp_path):
    """A source whose HEAD is detached and whose one branch was deleted has
    no branch: git lists each directory and finds none. It is
    `source-default-branch-not-local`, "(its branches: none)", as on
    50ce8ab1, and never `source-unreadable`."""
    source = make_source_repo(tmp_path / "Northwind", tree=TREE, edits=())
    git("checkout", "-q", "--detach", cwd=source)
    git("branch", "-q", "-D", "main", cwd=source)

    result = write_plan(source, tmp_path / PLAN_NAME)

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"{NOT_LOCAL}the source names no branch of its own to read: it "
            "has no `origin/HEAD` naming a branch of its remote `origin`, "
            "its HEAD is detached, and it has no branch `main`, which this "
            f"tool reads then {NO_BRANCHES}.") in result.stderr, result.stderr
    assert "source-unreadable" not in result.stderr, result.stderr


# --- the same questions, in-process (as root and on Windows too) ------------

def unlisted_here(adopter, monkeypatch, directory: Path,
                  code: int = errno.EACCES) -> None:
    """In this process, as git and the system answer where `directory`
    cannot be listed: `git for-each-ref` printing nothing, and `os.scandir`
    of `directory` refused with `code`; every other call is the real one."""
    locked = os.path.normcase(os.path.realpath(directory))
    real_scandir = os.scandir
    real_git_out = adopter.git_out

    def refusing(path="."):
        if not isinstance(path, int) and os.path.normcase(
                os.path.realpath(path)) == locked:
            raise OSError(code, os.strerror(code), os.fspath(path))
        return real_scandir(path)

    def listing_nothing(args, cwd, *rest, **kwargs):
        if args[:1] == ["for-each-ref"]:
            return b""
        return real_git_out(args, cwd, *rest, **kwargs)

    monkeypatch.setattr(os, "scandir", refusing)
    monkeypatch.setattr(adopter, "git_out", listing_nothing)


@pytest.mark.parametrize(("code", "cure", "not_said"), [
    pytest.param(errno.EACCES, CURE, "which no `chmod`", id="eacces"),
    pytest.param(errno.EIO, "which no `chmod` puts right", "chmod u+rx",
                 id="eio"),
])
def test_a_directory_the_system_will_not_list_is_named_everywhere(
        adopter, monkeypatch, tmp_path, code, cure, not_said):
    """`Source.open` of a clone on `release/v1` whose `refs/heads/release`
    the system will not list: `source-unreadable`, naming it, with the cure
    for a permission and none for another reason."""
    source = a_clone(tmp_path, "release/v1")
    unlisted_here(adopter, monkeypatch,
                  source / ".git" / "refs" / "heads" / "release", code)

    with pytest.raises(adopter.Refusal) as raised:
        adopter.Source.open(str(source), tmp_path / "work")

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == refs_refused(
        source, "refs/heads/release", BRANCHES_UNTOLD,
        f"cannot be read ({os.strerror(code)})")
    assert cure in refusal.remediation
    assert not_said not in refusal.remediation


def test_a_head_git_cannot_reach_is_asked_about_everywhere(
        adopter, monkeypatch, tmp_path):
    """`git symbolic-ref -q HEAD` exiting 128, "No such ref", as git does
    where it cannot reach the branch HEAD names, and `refs/heads/feature`
    refused to `os.scandir`: a repository on `feature/x` is
    `source-unreadable`, naming it. On 50ce8ab1 HEAD was read as detached
    and the source read at `main`."""
    source = a_repository_on(tmp_path, "feature/x")
    unlisted_here(adopter, monkeypatch,
                  source / ".git" / "refs" / "heads" / "feature")
    real_run = subprocess.run

    def unreached(args, *rest, **kwargs):
        if list(args) == ["git", "symbolic-ref", "-q", "HEAD"]:
            return subprocess.CompletedProcess(
                args, 128, b"", b"fatal: No such ref: HEAD\n")
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(subprocess, "run", unreached)

    with pytest.raises(adopter.Refusal) as raised:
        adopter.Source.open(str(source), tmp_path / "work")

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == refs_refused(source, "refs/heads/feature",
                                               BRANCHES_UNTOLD)


def test_the_branch_a_clone_checks_out_is_not_guessed_past_an_unlisted_one(
        adopter, monkeypatch, tmp_path):
    """`_cloned_branch` reads HEAD's branch, `feature/x`, and on 50ce8ab1
    took a list without it for a HEAD on no branch, so `check` guessed what
    `git clone` would write. Now that list is asked about first."""
    source = a_repository_on(tmp_path, "feature/x")
    opened = adopter.Source(Path(os.path.realpath(source)), None,
                            "feature/x", "")
    assert adopter._cloned_branch(opened) == "feature/x"
    unlisted_here(adopter, monkeypatch,
                  source / ".git" / "refs" / "heads" / "feature")

    with pytest.raises(adopter.Refusal) as raised:
        adopter._cloned_branch(opened)

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == refs_refused(source, "refs/heads/feature",
                                               BRANCHES_UNTOLD)


def test_a_source_git_reads_whole_is_asked_nothing_more(adopter, monkeypatch,
                                                        tmp_path):
    """A source git reads whole costs nothing new: a clone, a clone on a
    branch in a directory of its own, a repository with no remote on
    `feature/x`, and one whose HEAD is detached are each read at the branch
    they were read at before, and their tracking branch found, and
    `_refuse_unlisted_refs`, which runs `git rev-parse` and lists
    directories, is never asked."""
    asked = []
    monkeypatch.setattr(adopter, "_refuse_unlisted_refs",
                        lambda *args: asked.append(args))
    detached = make_source_repo(tmp_path / "detached" / "Northwind",
                                tree=TREE, edits=())
    git("checkout", "-q", "--detach", cwd=detached)
    sources = {"clone": a_clone(tmp_path / "clone"),
               "nested": a_clone(tmp_path / "nested", "release/v1"),
               "no-remote": a_repository_on(tmp_path / "local", "feature/x"),
               "detached": detached}
    read = {}
    for name, source in sources.items():
        opened = adopter.Source.open(str(source), tmp_path / "work")
        read[name] = opened.branch
        assert adopter._tracking_branch_problem(opened, "it",
                                                opened.branch) is None
        assert adopter._cloned_branch(opened) == (
            None if name == "detached" else opened.branch)

    assert read == {"clone": "main", "nested": "release/v1",
                    "no-remote": "feature/x", "detached": "main"}
    assert asked == []


# --- a directory git cannot list where the split branch may be (#1257) ------
#
# `check` asks for the plan's split branch, `adopt/three-repo-shape`, among
# the source's own branches (`_branches_at`) and, where the source's
# `origin` is the assembly repository, among its remote's as it last
# fetched them (`_branches_in`); `execute --local-remote-dir` asks the
# source's own before any leg exists. Each was `git for-each-ref` alone. ON
# b7a00b31 (#1252 merged into main at dffc4226, 2026-11-08), git 2.43.0,
# Python 3.12.3, uid 1000, a stub `gh` and local remotes, with an earlier
# run's split branch at a commit outside `main`:
#
# - in `.git/refs/heads/adopt` at mode 000 or `--x`: `check` said `plan ok`;
#   at `r--`, `adopt-git-unasked`, the split's clone meeting a null OID; and
#   `execute --local-remote-dir`, at 000, made and pushed both legs and then
#   failed at the split push.
# - in `.git/refs/remotes/origin/adopt` at any of those modes: `check` said
#   `plan ok`.
#
# Readable, each is `adopt-branch-exists`. Now each is `source-unreadable`,
# naming the directory, with the `chmod` cure, before any leg exists; and
# a source git reads whole runs the same git calls as before, because the
# directories are read from the disk (`_refuse_unlisted_refs_if_seen`).

#: The plan's split branch, and `check`'s finding for one an earlier run left.
SPLIT_BRANCH = "adopt/three-repo-shape"
BRANCH_EXISTS = "adopt-branch-exists"
#: Where an earlier run's split branch is kept, by the refs `check` reads it
#: in, and what `source-unreadable` cannot tell where git cannot list it.
SPLIT_PLACES = {"own": ("refs/heads/adopt", BRANCHES_UNTOLD),
                "fetched": ("refs/remotes/origin/adopt", ORIGIN_UNTOLD)}


def with_a_split_branch_left(source: Path, place: str) -> None:
    """An earlier run's split branch, a commit outside `main`, loose in the
    source: one of its own (`own`), or its `origin`'s as it last fetched it
    (`fetched`)."""
    git("switch", "-q", "-c", "earlier-run", cwd=source)
    git("commit", "-q", "--allow-empty", "-m", "An earlier split", cwd=source)
    tip = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    git("switch", "-q", "main", cwd=source)
    git("branch", "-q", "-D", "earlier-run", cwd=source)
    refs = "refs/heads/" if place == "own" else "refs/remotes/origin/"
    git("update-ref", refs + SPLIT_BRANCH, tip, cwd=source)
    assert (source / ".git" / Path(*SPLIT_PLACES[place][0].split("/"))
            ).is_dir()


@pytest.mark.parametrize("place", SPLIT_PLACES)
def test_a_split_branch_git_lists_is_still_found(tmp_path, place):
    """Read whole, an earlier run's split branch is `adopt-branch-exists`,
    as before, and never `source-unreadable`."""
    source = a_clone(tmp_path)
    with_a_split_branch_left(source, place)
    plan = planned_as_cloned(tmp_path, source)
    env, _ = recording_gh(tmp_path / "gh-bin")

    proc = asked_of(tmp_path, "check", source, plan, env)

    assert proc.returncode == 1, said(proc)
    assert proc.stderr.count(f"FINDING {BRANCH_EXISTS}: ") == 1, said(proc)
    assert "source-unreadable" not in said(proc)


@needs_a_mode
@pytest.mark.parametrize("mode", REF_MODES)
@pytest.mark.parametrize("place", SPLIT_PLACES)
def test_a_split_branch_git_cannot_list_is_refused_by_check(tmp_path, place,
                                                            mode):
    """RV1252's case, and the same for the split branch `origin` last
    fetched: its directory at mode 000, `--x` or `r--`. On b7a00b31 `check`
    said `plan ok` (at `r--` in `refs/heads/adopt`, `adopt-git-unasked`).
    Now `source-unreadable`, naming the directory, exit 2."""
    source = a_clone(tmp_path)
    with_a_split_branch_left(source, place)
    plan = planned_as_cloned(tmp_path, source)
    env, log = recording_gh(tmp_path / "gh-bin")
    part, untold = SPLIT_PLACES[place]

    with refs_at(source / ".git" / Path(*part.split("/")), mode):
        proc = asked_of(tmp_path, "check", source, plan, env)

    assert_refs_refused(proc, refs_refused(source, part, untold), tmp_path,
                        log)
    assert "plan ok" not in said(proc)


@needs_a_mode
@pytest.mark.parametrize("mode", REF_MODES[:2])
def test_a_split_branch_git_cannot_list_is_refused_before_any_leg(tmp_path,
                                                                  mode):
    """`execute --local-remote-dir` pushes the split into the source, and
    asks it first for the branch an earlier run left there
    (`_refuse_a_split_branch_left_behind`). On b7a00b31, with its
    `.git/refs/heads/adopt` at mode 000, it made and pushed both legs and
    then failed at the split push. Now it is refused before any leg exists.
    At `r--` git lists the branch and cannot read it, and the split's clone
    meets a null OID first, `adopt-git-unasked`, before any leg, as on
    b7a00b31: `check`'s own questions come before this one in `execute`."""
    source = a_clone(tmp_path)
    with_a_split_branch_left(source, "own")
    plan = planned_as_cloned(tmp_path, source)
    env, log = recording_gh(tmp_path / "gh-bin")

    with refs_at(source / ".git" / "refs" / "heads" / "adopt", mode):
        proc = asked_of(tmp_path, "execute", source, plan, env)

    assert_refs_refused(proc, refs_refused(source, "refs/heads/adopt",
                                           BRANCHES_UNTOLD), tmp_path, log)


# --- the same questions, in-process (as root and on Windows too) ------------

def split_directory_unlisted_here(adopter, monkeypatch, source: Path,
                                  part: str) -> Path:
    """The source's directory `part` made, empty, as git lists it, and
    refused to `os.scandir` in this process, as a mode refuses it
    (`unlisted_here`, with git left to list what it can)."""
    directory = source / ".git" / Path(*part.split("/"))
    directory.mkdir()
    git_listing = adopter.git_out
    unlisted_here(adopter, monkeypatch, directory)
    monkeypatch.setattr(adopter, "git_out", git_listing)
    return directory


def check_args(root: Path, plan: Path) -> Namespace:
    return Namespace(plan=str(plan), source=None, work_dir=root / "read",
                     local_remote_dir=root / "remotes")


def execute_args(root: Path, plan: Path) -> Namespace:
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=root / "remotes", allow_empty_leg=[],
                     yes=True, work_dir=root / "execute-work")


def stopped_at_the_legs(adopter, monkeypatch) -> None:
    """`execute` with its probe for `git filter-repo` stubbed, and stopped
    where it would make the legs: what reaches there was refused by
    nothing."""
    def proceeded(*args, **kwargs):
        raise AssertionError("execute went on to make the legs")
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(adopter, "_create_leg_remotes", proceeded)


@pytest.mark.parametrize("place", SPLIT_PLACES)
def test_check_names_a_split_branch_directory_the_system_will_not_list(
        adopter, monkeypatch, tmp_path, place):
    """`check`, in this process, of a clone whose split-branch directory the
    system will not list: `source-unreadable`, naming it. On b7a00b31 this
    was `plan ok`."""
    source = a_clone(tmp_path)
    plan = planned_as_cloned(tmp_path, source)
    part, untold = SPLIT_PLACES[place]
    split_directory_unlisted_here(adopter, monkeypatch, source, part)

    with pytest.raises(adopter.Refusal) as raised:
        adopter.cmd_check(check_args(tmp_path, plan))

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == refs_refused(source, part, untold)
    assert CURE in raised.value.remediation


def test_execute_names_a_split_branch_directory_the_system_will_not_list(
        adopter, monkeypatch, tmp_path):
    """`execute --local-remote-dir`, in this process: refused naming the
    source's `refs/heads/adopt` before any leg exists. On b7a00b31 it went
    on to make the legs."""
    source = a_clone(tmp_path)
    plan = planned_as_cloned(tmp_path, source)
    split_directory_unlisted_here(adopter, monkeypatch, source,
                                  "refs/heads/adopt")
    stopped_at_the_legs(adopter, monkeypatch)

    with pytest.raises(adopter.Refusal) as raised:
        adopter.cmd_execute(execute_args(tmp_path, plan))

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == refs_refused(source, "refs/heads/adopt",
                                               BRANCHES_UNTOLD)
    assert not (tmp_path / "remotes").exists()


def test_a_source_git_reads_whole_asks_no_git_more_for_its_split_branch(
        adopter, monkeypatch, tmp_path, capsys):
    """A source git reads whole runs the same git calls as before (#1257).
    With no split branch, `check` and `execute` read its directories from
    the disk, `refs/heads/` and `refs/remotes/origin/` for `check` and
    `refs/heads/` for each of `execute`'s two questions, and never run
    `_refuse_unlisted_refs`, whose `git rev-parse` would be one call more
    each time. With an earlier run's split branch in both places, which git
    lists, nothing more is asked at all."""
    refused, walked = [], []
    real_refuse = adopter._refuse_unlisted_refs
    real_walk = adopter._unlisted_ref_directory

    def refusing(*args):
        refused.append(args)
        return real_refuse(*args)

    def walking(common, prefix):
        walked.append(prefix)
        return real_walk(common, prefix)

    clean = a_clone(tmp_path / "clean")
    clean_plan = planned_as_cloned(tmp_path / "clean", clean)
    left = a_clone(tmp_path / "left")
    for place in SPLIT_PLACES:
        with_a_split_branch_left(left, place)
    left_plan = planned_as_cloned(tmp_path / "left", left)
    monkeypatch.setattr(adopter, "_refuse_unlisted_refs", refusing)
    monkeypatch.setattr(adopter, "_unlisted_ref_directory", walking)

    assert adopter.cmd_check(check_args(tmp_path / "clean", clean_plan)) == 0
    assert walked == ["refs/heads/", "refs/remotes/origin/"]
    del walked[:]
    stopped_at_the_legs(adopter, monkeypatch)
    with pytest.raises(AssertionError, match="went on to make the legs"):
        adopter.cmd_execute(execute_args(tmp_path / "clean", clean_plan))
    assert walked == ["refs/heads/", "refs/heads/"]
    del walked[:]
    assert adopter.cmd_check(check_args(tmp_path / "left", left_plan)) == 1
    assert capsys.readouterr().err.count(f"FINDING {BRANCH_EXISTS}: ") == 2
    assert walked == []
    assert refused == []


@pytest.mark.parametrize("layout", ["clone", "worktree", "separate",
                                    "git-dir"])
def test_the_disk_names_the_common_git_directory_git_names(adopter, tmp_path,
                                                           layout):
    """`_common_dir_on_disk` finds the source's refs where git finds them: a
    clone's `.git`; a linked worktree's `.git` file, then its git
    directory's `commondir`; the `.git` file `git init --separate-git-dir`
    leaves; and a git directory read as the source itself."""
    source = a_clone(tmp_path)
    path = {"clone": source, "worktree": tmp_path / "worktree",
            "separate": tmp_path / "separate",
            "git-dir": source / ".git"}[layout]
    if layout == "worktree":
        git("worktree", "add", "-q", "-b", "elsewhere", str(path),
            cwd=source)
    elif layout == "separate":
        git("init", "-q", "--separate-git-dir", str(tmp_path / "kept.git"),
            str(path), cwd=tmp_path)
    named = git("rev-parse", "--path-format=absolute", "--git-common-dir",
                cwd=path).stdout.rstrip("\n")

    found = adopter._common_dir_on_disk(path)

    assert found is not None
    assert os.path.realpath(found) == os.path.realpath(named)


def test_the_disk_is_not_read_where_git_would_not_read_it(adopter,
                                                          monkeypatch,
                                                          tmp_path):
    """Where git is told another git directory, or a `.git` file names
    none, `_common_dir_on_disk` says nothing, and git is asked."""
    source = a_clone(tmp_path)
    for name in ("GIT_DIR", "GIT_COMMON_DIR"):
        with monkeypatch.context() as told:
            told.setenv(name, str(source / ".git"))
            assert adopter._common_dir_on_disk(source) is None
    odd = tmp_path / "odd"
    odd.mkdir()
    (odd / ".git").write_bytes(b"not a gitfile\n")
    assert adopter._common_dir_on_disk(odd) is None


def test_a_linked_worktree_is_asked_in_its_common_git_directory(
        adopter, monkeypatch, tmp_path):
    """A linked worktree keeps its branches in its common git directory, the
    clone's `.git`: there a `refs/heads/adopt` the system will not list is
    named, as `git rev-parse --git-common-dir` names it."""
    source = a_clone(tmp_path)
    worktree = tmp_path / "worktree"
    git("worktree", "add", "-q", "-b", "elsewhere", str(worktree),
        cwd=source)
    split_directory_unlisted_here(adopter, monkeypatch, source,
                                  "refs/heads/adopt")

    with pytest.raises(adopter.Refusal) as raised:
        adopter._branches_at(str(worktree), worktree, SPLIT_BRANCH)

    assert raised.value.code == "source-unreadable"
    assert raised.value.detail == refs_refused(source, "refs/heads/adopt",
                                               BRANCHES_UNTOLD)
