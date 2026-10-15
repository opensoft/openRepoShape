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
a GitHub run has. Nothing here runs `gh`: every run below is `plan` and
`check`, which read a local source, or `execute --local-remote-dir`, which
refuses before any leg.
"""

from __future__ import annotations

import shutil
import sys

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      run_script, write_plan)

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
