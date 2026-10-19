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
`--local-remote-dir`, and once the plan's names and `org:` pass, it asks
`gh repo view` once of the spec leg's repository and once of the code leg's
(#798), and off Windows the session's guard answers each as a `gh` with no
login does (`tests/gh_guard.py`). Every run below is `plan` and `check`,
which read a local source, or `execute --local-remote-dir`, which refuses
before any leg or adopts.

The branch the source is read at is one of its own (#797). A clone made with
`git clone -b dev` has `origin/HEAD` naming `main` and no `main` of its own,
and `plan`, `check` and `execute` ended `git-failed` in `git rev-parse main`,
with no remedy, whatever `--tracking-branch` said. Now that clone is refused
by name, with both ways through, and `--tracking-branch dev` reads it at
`dev`. A default branch outside the alphabet a command line may carry, such
as `café`, is refused as before, and the refusal now says the way past it.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

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
