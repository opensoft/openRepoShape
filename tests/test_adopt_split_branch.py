# SPDX-License-Identifier: Apache-2.0
"""The split branch is a NEW branch where the split is pushed (#320).

`execute` pushes its one split commit to the plan's `adopt_branch:`
(`adopt/three-repo-shape`) in the repository the split goes to: the source
itself under `--local-remote-dir`, the assembly repository on GitHub
otherwise. An earlier run leaves that branch behind, verified or failed after
the push, and nothing looked for it. On main at 71b58a1 the same plan re-run
into fresh legs passed `check` as `plan ok`, made and pushed both legs, and
was refused at the push of the split as a non-fast-forward; a source branch
`adopt`, which git cannot hold beside `adopt/three-repo-shape`, failed the
run after both legs were made as well. Over a source whose tip `.gitmodules`
git's submodule reader cannot read, #226's history scan refused the re-run,
but named a commit of the old split branch that the extraction never
exports.

Now a branch at the split branch's name, or in git's way of it, is `check`'s
finding `plan-split-branch-taken`, and `execute` refuses it before any leg
exists, first among `check`'s findings.

All repositories here are local, GitHub included: a run without
`--local-remote-dir` is pointed at a bare repository on disk by git's own
`url.<base>.insteadOf`, and its `gh` is never reached. Only the tests marked
`needs_filter_repo` run `git filter-repo`; the rest call `cmd_execute` in
this process with its probe for the tool stubbed, because every refusal
under test comes before the tool would be used.
"""

from __future__ import annotations

import importlib.util
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, FILE_PROTOCOL, GITMODULES, as_human, findings, \
    git, make_source_repo, planned, put_gitmodules, refused_before_any_leg, \
    run_script

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

TAKEN = "plan-split-branch-taken"
UNREADABLE = "plan-gitmodules-unreadable"
SPLIT_BRANCH = "adopt/three-repo-shape"
PROJECT, ORG = "Northwind", "testorg"
REMOTES, WORK = "remotes", "work"
#: A source `plan` asks no question about: `specs/` and `src/` classify
#: themselves and `README.md` stays in the root.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: #195's tip `.gitmodules`: a key with no value, which git's submodule
#: reader dies on for any gitlink `git fast-export` meets.
BARE_PATH = '[submodule "b"]\n\tpath\n'


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_split_branch",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Proceeded(Exception):
    """`cmd_execute` got past every refusal to the step that makes legs."""


def small_source(base: Path, gitmodules: str | None = None) -> Path:
    """SMALL_TREE in one commit on `main`, and `gitmodules` as its
    `.gitmodules` in a second when one is given."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    if gitmodules is not None:
        put_gitmodules(source, gitmodules)
        as_human("commit", "-qm", "A .gitmodules", cwd=source)
    return source


def split_branch_by_hand(source: Path, branch: str = SPLIT_BRANCH) -> str:
    """`branch`, one commit off `main` that adds gitlinks `spec` and `code`:
    the tree an earlier run's split commit has, made as the issue made it.
    `main` is checked out again after it, and holds no gitlink."""
    head = git("rev-parse", "main", cwd=source).stdout.strip()
    as_human("checkout", "-q", "-b", branch, cwd=source)
    for path in ("spec", "code"):
        git("update-index", "--add", "--cacheinfo", f"160000,{head},{path}",
            cwd=source)
    as_human("commit", "-qm", "An earlier split, by hand", cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    as_human("checkout", "-q", "-f", "main", cwd=source)
    return commit


def plan_for(source: Path, base: Path, answers: dict | None = None) -> Path:
    return planned(source, base, answers or {})


def renamed(plan: Path, branch: str) -> Path:
    """`plan` with `adopt_branch:` set to `branch`, beside it."""
    other = plan.with_name("renamed-plan.yaml")
    other.write_bytes(plan.read_bytes().replace(
        f"adopt_branch: {SPLIT_BRANCH}\n".encode(),
        f"adopt_branch: {branch}\n".encode(), 1))
    assert other.read_bytes() != plan.read_bytes()
    return other


def execute_args(plan: Path, base: Path, local: bool = True) -> Namespace:
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=base / REMOTES if local else None,
                     allow_empty_leg=[], yes=True, work_dir=base / WORK)


def stop_at_the_legs(adopter, monkeypatch) -> None:
    """`_create_leg_remotes` raises `Proceeded`: what reaches it was refused
    by nothing before it."""
    def proceeded(*args, **kwargs):
        raise Proceeded()
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(adopter, "_create_leg_remotes", proceeded)


# --- what `check` finds, and `execute` refuses, in the source ---------------

def test_check_finds_an_earlier_split_branch_in_the_source(adopter,
                                                           tmp_path):
    """On main this was `plan ok`, and `execute` made both legs before the
    push of the split was refused as a non-fast-forward."""
    source = small_source(tmp_path)
    old = split_branch_by_hand(source)
    found = findings(plan_for(source, tmp_path))
    assert found == [(TAKEN, (
        f"the source {source} already holds the plan's split branch "
        f"`{SPLIT_BRANCH}`, at {old[:12]}. `execute --local-remote-dir` "
        f"pushes its split commit to `{SPLIT_BRANCH}` there, after both leg "
        "repositories were created and pushed, and as a new branch: a "
        "branch already there refuses that push unless the split "
        "fast-forwards it, and then the split lands on a branch this "
        f"adoption did not make. Delete `{SPLIT_BRANCH}` there, or set "
        "`adopt_branch:` in the plan to a branch git can create there."))]


def test_check_says_how_to_go_on_once_after_its_findings(adopter, tmp_path):
    source = small_source(tmp_path)
    split_branch_by_hand(source)
    result = run_script(ADOPT, "check", "--plan",
                        str(plan_for(source, tmp_path)))
    assert result.returncode == 1, result.stderr + result.stdout
    assert result.stderr.count(adopter.SPLIT_BRANCH_REMEDIATION) == 1


def test_execute_refuses_it_before_any_leg_exists(adopter, tmp_path,
                                                  monkeypatch):
    """`check`'s finding, raised by `_refuse_what_check_finds` before
    `_create_leg_remotes`: the directory the legs go in is never made, and
    the source's branch is where it was."""
    source = small_source(tmp_path)
    old = split_branch_by_hand(source)
    refusal = refused_before_any_leg(adopter, monkeypatch,
                                     plan_for(source, tmp_path), tmp_path)
    assert refusal.code == TAKEN
    assert refusal.remediation.endswith(
        "\n" + adopter.SPLIT_BRANCH_REMEDIATION)
    assert git("rev-parse", SPLIT_BRANCH, cwd=source).stdout.strip() == old


def test_a_branch_the_split_would_fast_forward_is_taken_too(adopter,
                                                            tmp_path,
                                                            monkeypatch):
    """At the plan's own commit, the split fast-forwards it, and on main it
    was pushed onto that branch and verified: a branch this adoption did
    not make. It is refused like any other."""
    source = small_source(tmp_path)
    git("branch", SPLIT_BRANCH, cwd=source)
    plan = plan_for(source, tmp_path)
    assert [code for code, _ in findings(plan)] == [TAKEN]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == TAKEN


#: Branch names git cannot hold beside the split branch: one whose name is
#: a directory of it, and one under it. On main each passed `check`, and
#: `execute` failed after both legs were made -- for `adopt`, silently, at
#: the `git filter-repo` that could not create `refs/heads/adopt` beside the
#: split branch `_extract_leg` checks out.
IN_THE_WAY = ["adopt", f"{SPLIT_BRANCH}/old"]
#: Names that only look like it, which git holds beside it.
BESIDE_IT = [f"{SPLIT_BRANCH}-old", "adopt/other", "adopt-three-repo-shape",
             "three-repo-shape"]


def in_the_extraction(source: Path, name: str, at: str) -> str:
    """`check`'s finding for a source branch `name` at `at` that git cannot
    hold beside the split branch: about the extraction, which both runs
    make."""
    return (f"the source {source} holds the branch `{name}`, at {at[:12]}. "
            "`execute`, with `--local-remote-dir` or without it, extracts a "
            "leg from a clone of the source with the plan's split branch "
            f"`{SPLIT_BRANCH}` checked out in it, after both leg repositories "
            f"were created, and `git filter-repo` cannot create `{name}` "
            f"beside `{SPLIT_BRANCH}` there: git holds no branch whose name "
            "is a directory of another's, or lies under it. Delete "
            f"`{name}` there, or set `adopt_branch:` in the plan to a branch "
            "git can create there.")


@pytest.mark.parametrize("name", IN_THE_WAY)
def test_a_branch_in_gits_way_of_the_split_branch_is_taken(adopter,
                                                           tmp_path,
                                                           monkeypatch,
                                                           name):
    """Said as the extraction's failure, for both runs: the review of #320
    measured a run without `--local-remote-dir` failing there too, after
    both GitHub leg repositories were made, while this finding said it was
    about `execute --local-remote-dir` alone."""
    source = small_source(tmp_path)
    git("branch", name, cwd=source)
    at = git("rev-parse", name, cwd=source).stdout.strip()
    plan = plan_for(source, tmp_path)
    assert findings(plan) == [(TAKEN, in_the_extraction(source, name, at))]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == TAKEN


@pytest.mark.parametrize("name", BESIDE_IT)
def test_a_branch_git_holds_beside_the_split_branch_is_not_taken(tmp_path,
                                                                 name):
    source = small_source(tmp_path)
    git("branch", name, cwd=source)
    assert findings(plan_for(source, tmp_path)) == []


def test_another_split_branch_in_the_plan_is_not_taken(tmp_path):
    """The finding's own second exit: the plan names a branch that is new
    there."""
    source = small_source(tmp_path)
    split_branch_by_hand(source)
    assert findings(renamed(plan_for(source, tmp_path), "adopt/again")) == []


def test_each_branch_in_the_way_is_named(tmp_path):
    """Two branches under the split branch's name, which one repository can
    hold together (it cannot hold either beside the split branch itself)."""
    source = small_source(tmp_path)
    for name in ("old", "older"):
        git("branch", f"{SPLIT_BRANCH}/{name}", cwd=source)
    found = findings(plan_for(source, tmp_path))
    assert [code for code, _ in found] == [TAKEN, TAKEN]
    assert f"holds the branch `{SPLIT_BRANCH}/old`" in found[0][1]
    assert f"holds the branch `{SPLIT_BRANCH}/older`" in found[1][1]


# --- #226's history scan, with this finding first --------------------------

def issue_source(base: Path) -> tuple[Path, str]:
    """The issue's second shape: a tip `.gitmodules` with a key with no
    value, no gitlink at the tip, and an earlier split branch whose one
    commit adds gitlinks. Returns the source and that commit."""
    source = small_source(base)
    old = split_branch_by_hand(source)
    put_gitmodules(source, BARE_PATH)
    as_human("commit", "-qm", "The tip .gitmodules", cwd=source)
    assert "160000" not in git("ls-tree", "-r", "main", cwd=source).stdout
    return source, old


def scan_names(commit: str) -> str:
    """How `plan-gitmodules-unreadable` names the old split commit."""
    return f"where commit {commit[:12]} adds `code`"


def test_the_branch_is_named_before_the_history_it_adds(adopter, tmp_path,
                                                        monkeypatch):
    """On main `check` and `execute` named only the history scan's finding,
    for a commit the extraction never exports while the plan names the
    branch that holds it. The branch is now the first finding, and the code
    of `execute`'s refusal."""
    source, old = issue_source(tmp_path)
    plan = plan_for(source, tmp_path, {GITMODULES: "code"})
    found = findings(plan)
    assert [code for code, _ in found] == [TAKEN, UNREADABLE], found
    assert f"at {old[:12]}" in found[0][1]
    assert scan_names(old) in found[1][1]
    refusal = refused_before_any_leg(adopter, monkeypatch, plan, tmp_path)
    assert refusal.code == TAKEN


def test_with_the_branch_deleted_nothing_names_its_history(tmp_path):
    source, _ = issue_source(tmp_path)
    plan = plan_for(source, tmp_path, {GITMODULES: "code"})
    git("branch", "-q", "-D", SPLIT_BRANCH, cwd=source)
    assert findings(plan) == []


def test_with_another_split_branch_the_history_finding_stands(tmp_path):
    """Not left out of the scan: under another name `git filter-repo`
    exports the old branch, which
    `test_the_extraction_exports_the_old_branch_only_under_another_name`
    measures."""
    source, old = issue_source(tmp_path)
    plan = renamed(plan_for(source, tmp_path, {GITMODULES: "code"}),
                   "adopt/again")
    found = findings(plan)
    assert [code for code, _ in found] == [UNREADABLE], found
    assert scan_names(old) in found[0][1]


@needs_filter_repo
@pytest.mark.parametrize("branch, exported", [
    (SPLIT_BRANCH, False), ("adopt/again", True)],
    ids=["the-same-name", "another-name"])
def test_the_extraction_exports_the_old_branch_only_under_another_name(
        adopter, tmp_path, branch, exported):
    """`_extract_leg` itself, over the issue's source: `git checkout -B`
    of the plan's branch in its clone shadows an old branch of that name,
    which `git filter-repo` then leaves out, and under another name it
    exports it and fails on the tip `.gitmodules`. So with this refusal
    first, the scan, which reads the old branch, reads what every run that
    gets past it exports."""
    source, _ = issue_source(tmp_path)
    read = adopter.Source.open(str(source), tmp_path / "read")
    leg = tmp_path / "leg.git"
    git("init", "-q", "--bare", "-b", "main", str(leg), cwd=tmp_path)
    extract = (lambda: adopter._extract_leg(
        "code", read, tmp_path / "clone", ["src/"], tmp_path / "paths.txt",
        branch, str(leg), "main", f"{ORG}/{PROJECT}-code"))
    if not exported:
        extract()
        assert git("rev-parse", "main", cwd=leg).stdout.strip()
        return
    with pytest.raises(adopter.CommandFailed) as caught:
        extract()
    assert caught.value.args_list[1] == "filter-repo", caught.value.args_list
    assert ".gitmodules" in caught.value.output, caught.value.output


@needs_filter_repo
@pytest.mark.parametrize("name", IN_THE_WAY)
def test_the_extraction_stops_at_a_source_branch_in_its_way(adopter,
                                                            tmp_path, name):
    """`_extract_leg` itself, over a source holding `name`: its clone has
    the split branch checked out, and `git filter-repo`, which makes each
    of the clone's remote-tracking branches a branch, cannot make `name`
    beside it, so nothing is pushed to the leg. That is before the split is
    pushed anywhere, so the finding is about both runs."""
    source = small_source(tmp_path)
    git("branch", name, cwd=source)
    read = adopter.Source.open(str(source), tmp_path / "read")
    leg = tmp_path / "leg.git"
    git("init", "-q", "--bare", "-b", "main", str(leg), cwd=tmp_path)
    with pytest.raises(adopter.CommandFailed) as caught:
        adopter._extract_leg(
            "code", read, tmp_path / "clone", ["src/"], tmp_path / "paths.txt",
            SPLIT_BRANCH, str(leg), "main", f"{ORG}/{PROJECT}-code")
    assert caught.value.args_list[1] == "filter-repo", caught.value.args_list
    assert git("for-each-ref", cwd=leg).stdout == ""


# --- the assembly repository on GitHub --------------------------------------

def github_repository(tmp_path: Path, branches=(SPLIT_BRANCH,)) -> Path:
    """A bare `testorg/Northwind` under `tmp_path/github`, holding `main`
    and `branches`, each at a commit of another repository's `main`."""
    bare = tmp_path / "github" / ORG / f"{PROJECT}.git"
    bare.mkdir(parents=True)
    seed = small_source(tmp_path / "seed")
    git("init", "-q", "--bare", "-b", "main", str(bare), cwd=tmp_path)
    for name in ("main", *branches):
        git(*FILE_PROTOCOL, "push", "-q", str(bare), f"main:refs/heads/{name}",
            cwd=seed)
    return bare


def github_at(root: Path, monkeypatch) -> None:
    """git pointed at `root` for `https://github.com/testorg/`, by its own
    `url.<base>.insteadOf`, in the environment every `git` this process
    starts inherits. The org is in it because git takes the LONGEST
    `insteadOf` that matches, and a workstation may already rewrite
    `https://github.com/` (to `git@github.com:`, say) in its own config."""
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0",
                       f"url.{(root / ORG).as_posix()}/.insteadOf")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", f"https://github.com/{ORG}/")


def a_github(tmp_path: Path, monkeypatch, branches=(SPLIT_BRANCH,)) -> Path:
    """`github_repository`, with git pointed at it (`github_at`)."""
    bare = github_repository(tmp_path, branches)
    github_at(tmp_path / "github", monkeypatch)
    return bare


def no_gh(adopter, monkeypatch) -> list:
    """`run`, with every `gh` command it is given recorded and refused as
    `Proceeded`: nothing here may reach GitHub."""
    asked: list = []
    real = adopter.run

    def run(args, cwd=None, capture=True):
        if args and args[0] == "gh":
            asked.append(args)
            raise Proceeded(args)
        return real(args, cwd, capture)

    monkeypatch.setattr(adopter, "run", run)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    return asked


def test_execute_asks_github_where_it_pushes_without_local_remotes(
        adopter, tmp_path, monkeypatch):
    """The source holds no such branch; the repository the split is pushed
    to does, and `execute` asks it, before `gh repo create`."""
    source = small_source(tmp_path)
    plan = plan_for(source, tmp_path)
    bare = a_github(tmp_path, monkeypatch)
    at = git("rev-parse", SPLIT_BRANCH, cwd=bare).stdout.strip()
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert caught.value.code == TAKEN
    assert (f"  FINDING {TAKEN}: `{ORG}/{PROJECT}` on GitHub already holds "
            f"the plan's split branch `{SPLIT_BRANCH}`, at {at[:12]}. "
            "`execute` without `--local-remote-dir` pushes its split commit "
            f"to `{SPLIT_BRANCH}` there") in caught.value.detail
    assert asked == []


def test_execute_goes_on_to_the_legs_when_github_has_no_such_branch(
        adopter, tmp_path, monkeypatch):
    source = small_source(tmp_path)
    plan = plan_for(source, tmp_path)
    a_github(tmp_path, monkeypatch, branches=("adopt/other",))
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(Proceeded):
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert asked[0][:3] == ["gh", "repo", "create"]


def test_execute_refuses_a_repository_it_cannot_list(adopter, tmp_path,
                                                     monkeypatch):
    """No `testorg/Northwind` where git is pointed: the push of the split
    would fail there after both legs were made, so nothing is made."""
    source = small_source(tmp_path)
    plan = plan_for(source, tmp_path)
    github_at(tmp_path / "nowhere", monkeypatch)
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert caught.value.code == adopter.SPLIT_TARGET_UNREADABLE
    assert caught.value.detail.startswith(
        f"could not list the branches of https://github.com/{ORG}/{PROJECT}"
        f".git, where `execute` pushes the split, to see whether "
        f"`{SPLIT_BRANCH}` is new there: `git ls-remote` exited ")
    assert "no leg repository was created" in caught.value.remediation
    assert asked == []


def test_a_branch_in_gits_way_on_github_is_refused_in_the_pushs_words(
        adopter, tmp_path, monkeypatch):
    """GitHub holds `adopt`, and the source does not: the push of the
    split would meet it there, so the finding is about the run that pushes
    there, in git's own words."""
    source = small_source(tmp_path)
    plan = plan_for(source, tmp_path)
    bare = a_github(tmp_path, monkeypatch, branches=("adopt",))
    at = git("rev-parse", "adopt", cwd=bare).stdout.strip()
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert caught.value.code == TAKEN
    assert (f"  FINDING {TAKEN}: `{ORG}/{PROJECT}` on GitHub holds the "
            f"branch `adopt`, at {at[:12]}. `execute` without "
            "`--local-remote-dir` pushes its split commit to "
            f"`{SPLIT_BRANCH}` there, after both leg repositories were "
            "created and pushed, and git cannot create "
            f"`{SPLIT_BRANCH}` beside `adopt`: `'refs/heads/adopt' exists; "
            f"cannot create 'refs/heads/{SPLIT_BRANCH}'`. Delete `adopt` "
            "there, or set `adopt_branch:` in the plan to a branch git can "
            "create there.") in caught.value.detail.splitlines()
    assert asked == []


@pytest.mark.parametrize("name", IN_THE_WAY)
def test_a_github_run_is_refused_for_a_source_branch_in_the_extractions_way(
        adopter, tmp_path, monkeypatch, name):
    """The review of #320: without `--local-remote-dir`, a local source
    holding `adopt` made both GitHub leg repositories, and the run exited 2
    at `git filter-repo`, saying nothing. GitHub holds no such branch here;
    the source does, and `execute` asks it as well, before `gh repo
    create`, and refuses with `check`'s finding, word for word."""
    source = small_source(tmp_path)
    git("branch", name, cwd=source)
    at = git("rev-parse", name, cwd=source).stdout.strip()
    plan = plan_for(source, tmp_path)
    a_github(tmp_path, monkeypatch, branches=())
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert caught.value.code == TAKEN
    lines = caught.value.detail.splitlines()
    assert lines[0].startswith("1 finding(s) in "), lines
    assert lines[1] == (f"  FINDING {TAKEN}: "
                        + in_the_extraction(source, name, at))
    assert asked == []


def test_a_github_run_is_not_refused_for_the_split_branch_in_the_source(
        adopter, tmp_path, monkeypatch):
    """The split branch's own name in the source stops only the run that
    pushes there. The extraction's `checkout -B` shadows it in its clone
    (`test_the_extraction_exports_the_old_branch_only_under_another_name`),
    and this run pushes to GitHub, which holds none."""
    source = small_source(tmp_path)
    split_branch_by_hand(source)
    plan = plan_for(source, tmp_path)
    a_github(tmp_path, monkeypatch, branches=())
    asked = no_gh(adopter, monkeypatch)
    with pytest.raises(Proceeded):
        adopter.cmd_execute(execute_args(plan, tmp_path, local=False))
    assert asked[0][:3] == ["gh", "repo", "create"]


def test_a_plan_that_seeds_both_legs_is_not_asked_about_the_extraction(
        adopter, tmp_path, monkeypatch):
    """Nothing is extracted, so a source branch `adopt` stops only the push
    of the split to the source: `check` says that of `execute
    --local-remote-dir`, in the push's words, and a run without it goes
    on."""
    source = small_source(tmp_path)
    git("branch", "adopt", cwd=source)
    at = git("rev-parse", "adopt", cwd=source).stdout.strip()
    plan = plan_for(source, tmp_path, {"specs/": "root", "src/": "root"})
    found = findings(plan)
    assert [code for code, _ in found] == [TAKEN], found
    assert found[0][1].startswith(
        f"the source {source} holds the branch `adopt`, at {at[:12]}. "
        "`execute --local-remote-dir` pushes its split commit to "
        f"`{SPLIT_BRANCH}` there, "), found
    a_github(tmp_path, monkeypatch, branches=())
    asked = no_gh(adopter, monkeypatch)
    args = execute_args(plan, tmp_path, local=False)
    args.allow_empty_leg = ["spec", "code"]
    with pytest.raises(Proceeded):
        adopter.cmd_execute(args)
    assert asked[0][:3] == ["gh", "repo", "create"]


def with_origin(source: Path, bare: Path) -> None:
    """`bare` as the source's `origin`, fetched: its branches are the
    source's remote-tracking branches, and its path ends in
    `testorg/Northwind.git`, which `plan` reads as the source's repository."""
    git("remote", "add", "origin", bare.as_posix(), cwd=source)
    git(*FILE_PROTOCOL, "fetch", "-q", "origin", cwd=source)


def test_check_reads_github_as_the_sources_origin_last_fetched_it(
        adopter, tmp_path, monkeypatch):
    """`check` reads no network, and does not know whether `execute` will
    be given `--local-remote-dir`: where the source's `origin` is the
    assembly repository, what it fetched from there is asked too, and the
    finding says which run it is about. A run that pushes to the source
    itself is not refused for it."""
    bare = github_repository(tmp_path)
    source = small_source(tmp_path)
    with_origin(source, bare)
    at = git("rev-parse", f"origin/{SPLIT_BRANCH}", cwd=source).stdout.strip()
    plan = plan_for(source, tmp_path)
    found = findings(plan)
    assert found == [(TAKEN, (
        f"`{ORG}/{PROJECT}` on GitHub, as the source's `origin` last fetched "
        f"it, already holds the plan's split branch `{SPLIT_BRANCH}`, at "
        f"{at[:12]}. `execute` without `--local-remote-dir` pushes its split "
        f"commit to `{SPLIT_BRANCH}` there, after both leg repositories were "
        "created and pushed, and as a new branch: a branch already there "
        "refuses that push unless the split fast-forwards it, and then the "
        "split lands on a branch this adoption did not make. Delete "
        f"`{SPLIT_BRANCH}` there, or set `adopt_branch:` in the plan to a "
        "branch git can create there."))]
    stop_at_the_legs(adopter, monkeypatch)
    with pytest.raises(Proceeded):
        adopter.cmd_execute(execute_args(plan, tmp_path))


def test_an_origin_that_is_not_the_assembly_repository_is_not_asked(
        tmp_path):
    source = small_source(tmp_path)
    with_origin(source, github_repository(tmp_path))
    plan = tmp_path / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         "Elsewhere", "--org", ORG, "--elected-by", "Test",
                         "--elected-on", "2026-09-02", "--out", str(plan))
    assert written.returncode == 0, written.stderr + written.stdout
    assert findings(plan) == []


def test_a_branch_gone_from_github_leaves_check_once_the_source_prunes(
        adopter, tmp_path):
    """What the remediation says of a branch named as the source's `origin`
    last fetched it: deleted there, it stays a finding until `git fetch
    --prune origin` in the source, which `execute`, asking GitHub itself,
    does not wait for."""
    bare = github_repository(tmp_path)
    source = small_source(tmp_path)
    with_origin(source, bare)
    plan = plan_for(source, tmp_path)
    assert [code for code, _ in findings(plan)] == [TAKEN]
    git("update-ref", "-d", f"refs/heads/{SPLIT_BRANCH}", cwd=bare)
    assert [code for code, _ in findings(plan)] == [TAKEN]
    git(*FILE_PROTOCOL, "fetch", "-q", "--prune", "origin", cwd=source)
    assert findings(plan) == []
    assert ("once `git fetch --prune origin` in the source finds it gone "
            "there") in adopter.SPLIT_BRANCH_REMEDIATION


# --- end to end -------------------------------------------------------------

@needs_filter_repo
def test_the_issue_re_run_is_refused_and_runs_once_the_branch_is_gone(
        tmp_path):
    """#320 as measured on main: a verified run, then the same plan re-run
    into fresh legs, which passed `check` and died at the push of the split
    after both legs were made. Now `check` names the branch and the first
    run's split commit, `execute` refuses before any leg exists, and once
    the branch is deleted the same command adopts."""
    source = small_source(tmp_path)
    plan = plan_for(source, tmp_path)
    flags = ("--plan", str(plan), "--yes")
    first = run_script(ADOPT, "execute", *flags, "--local-remote-dir",
                       str(tmp_path / "first-remotes"), "--work-dir",
                       str(tmp_path / "first-work"))
    assert first.returncode == 0, first.stderr + first.stdout
    split = git("rev-parse", SPLIT_BRANCH, cwd=source).stdout.strip()

    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert (f"FINDING {TAKEN}: the source {source} already holds the plan's "
            f"split branch `{SPLIT_BRANCH}`, at {split[:12]}.") \
        in checked.stderr
    remotes = tmp_path / REMOTES
    again = ("--local-remote-dir", str(remotes), "--work-dir",
             str(tmp_path / WORK))
    refused = run_script(ADOPT, "execute", *flags, *again)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {TAKEN}: 1 finding(s) in " in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists()
    assert git("rev-parse", SPLIT_BRANCH, cwd=source).stdout.strip() == split

    git("branch", "-q", "-D", SPLIT_BRANCH, cwd=source)
    assert run_script(ADOPT, "check", "--plan", str(plan)).returncode == 0
    adopted = run_script(ADOPT, "execute", *flags, *again)
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout
