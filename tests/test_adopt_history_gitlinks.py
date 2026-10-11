# SPDX-License-Identifier: Apache-2.0
"""A submodule the HISTORY holds and the tip does not still fails the
extraction (#195).

`git filter-repo` runs `git fast-export --all` in a clone of the source, and
git's submodule reader reads the clone's CHECKED-OUT `.gitmodules` for every
gitlink a commit of any branch or tag adds, changes or removes. #166 asked
the tip tree alone, so a source whose history once held a submodule, whose
tip holds none, and whose tip `.gitmodules` has a key with no value
(`[submodule "b"]` and a bare `path`) passed `check` as `plan ok`, and
`execute` died in `git fast-export` after both leg repositories were made:
a corrected re-run then met `leg-remote-exists`.

All repositories here are local, and only the one end-to-end test at the
bottom needs `git filter-repo`. The rest read the history with
`_exported_gitlink`, run `check`, and call `cmd_execute` in this process
with its probe for the tool stubbed, because the refusal under test comes
before the tool would be used.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import stat
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, resolve, run_script, \
    write_plan

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
GITMODULES = ".gitmodules"
UNREADABLE = "plan-gitmodules-unreadable"
REMOTES = "remotes"
#: The submodule the history holds, registered under the name `b`.
GITLINK = "vendor/b"
REGISTRATION = '[submodule "b"]\n\tpath = vendor/b\n\turl = ../b\n'
#: The issue's tip `.gitmodules`: a key with no value.
BARE_PATH = '[submodule "b"]\n\tpath\n'
#: A line no git reader can parse.
BAD_LINE = '[submodule "b"\n\tpath = vendor/b\n'
#: A source whose plan asks one question, `.gitmodules`': `specs/` and `src/`
#: classify themselves and `README.md` stays in the root.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: How `_exported_gitlink` names a commit's change to the gitlink.
NAMED = r"commit [0-9a-f]{12} (adds|removes) `vendor/b`"


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_history_gitlinks",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def as_human(*args: str, cwd: Path):
    """`git <args>` with an identity, for the commits and merges below."""
    return git("-c", "user.name=Source Human",
               "-c", "user.email=source@invalid.example", *args, cwd=cwd)


def put_gitmodules(source: Path, text: str) -> None:
    """`text` as the source's `.gitmodules`, staged: BYTES, so it is LF on
    every platform, as a hand edit would leave it."""
    (source / GITMODULES).write_bytes(text.encode())
    git("add", "--", GITMODULES, cwd=source)


def link(source: Path) -> None:
    """A gitlink at GITLINK, staged straight into the index, as `git add` of
    an embedded clone records one; no checkout of it is needed. It names
    `main`'s commit, which an orphan branch's first commit has no HEAD to
    give."""
    head = git("rev-parse", "main", cwd=source).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},{GITLINK}",
        cwd=source)


def unlink(source: Path) -> None:
    git("rm", "-q", "--cached", "--", GITLINK, cwd=source)


def add_then_remove(source: Path) -> None:
    """Two commits on the branch checked out: the submodule and its
    registration, then the submodule gone."""
    put_gitmodules(source, REGISTRATION)
    link(source)
    as_human("commit", "-qm", "Add vendor/b", cwd=source)
    unlink(source)
    as_human("commit", "-qm", "Remove vendor/b", cwd=source)


def on_a_side_branch_merged(source: Path) -> None:
    as_human("checkout", "-q", "-b", "side", cwd=source)
    add_then_remove(source)
    as_human("checkout", "-q", "main", cwd=source)
    as_human("merge", "-q", "--no-ff", "-m", "Merge side", "side", cwd=source)
    as_human("branch", "-q", "-D", "side", cwd=source)


def on_a_branch_never_merged(source: Path) -> None:
    as_human("checkout", "-q", "-b", "other", cwd=source)
    link(source)
    as_human("commit", "-qm", "Add vendor/b on other", cwd=source)
    as_human("checkout", "-q", "main", cwd=source)


def on_a_commit_only_a_tag_reaches(source: Path) -> None:
    as_human("checkout", "-q", "--detach", cwd=source)
    link(source)
    as_human("commit", "-qm", "Add vendor/b, tagged", cwd=source)
    as_human("tag", "only-a-tag", cwd=source)
    as_human("checkout", "-q", "main", cwd=source)


def in_a_root_commit_of_its_own(source: Path) -> None:
    """The ONE commit of an unrelated branch adds it: only a root diff,
    which `log.showRoot=false` leaves out, shows it."""
    as_human("checkout", "-q", "--orphan", "pages", cwd=source)
    git("rm", "-r", "-q", "--cached", "--", ".", cwd=source)
    link(source)
    as_human("commit", "-qm", "pages root with vendor/b", cwd=source)
    as_human("checkout", "-q", "-f", "main", cwd=source)


def by_merges_alone(source: Path) -> None:
    """One merge adds it and another removes it, so no commit with one
    parent touches it: only a merge's own diff, which a plain `git log`
    does not show, finds it."""
    for branch, change in (("s1", link), ("s2", unlink)):
        as_human("checkout", "-q", "-b", branch, cwd=source)
        (source / f"{branch}.txt").write_bytes(b"x\n")
        git("add", "--", f"{branch}.txt", cwd=source)
        as_human("commit", "-qm", branch, cwd=source)
        as_human("checkout", "-q", "main", cwd=source)
        as_human("merge", "-q", "--no-ff", "--no-commit", branch, cwd=source)
        change(source)
        as_human("commit", "-qm", f"merge {branch}", cwd=source)
        as_human("branch", "-q", "-D", branch, cwd=source)


def hidden_by_a_replacement(source: Path) -> None:
    """The commit that adds it, replaced by its parent: `git log` honours
    the replacement and a clone, which copies no `refs/replace/`, does
    not."""
    add_then_remove(source)
    added = git("rev-parse", "HEAD~1", cwd=source).stdout.strip()
    git("replace", added, f"{added}~1", cwd=source)


#: Where the history holds the submodule, and what the commit `git log`
#: meets first does to it; the tip holds none in every one.
HISTORIES = {
    "on-the-branch-adopted": (add_then_remove, "removes"),
    "on-a-side-branch-merged": (on_a_side_branch_merged, "removes"),
    "on-a-branch-never-merged": (on_a_branch_never_merged, "adds"),
    "on-a-commit-only-a-tag-reaches": (on_a_commit_only_a_tag_reaches,
                                       "adds"),
    "in-a-root-commit-of-its-own": (in_a_root_commit_of_its_own, "adds"),
    "by-merges-alone": (by_merges_alone, "removes"),
    "hidden-by-a-replacement": (hidden_by_a_replacement, "removes"),
}


def history_source(base: Path, history=add_then_remove,
                   tip: str | None = BARE_PATH) -> Path:
    """A source whose `history` holds GITLINK and whose tip holds no
    submodule, with `tip` as its `.gitmodules` (none when None), committed
    last on `main` and checked out."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    if history is not None:
        history(source)
    if tip is None:
        git("rm", "-q", "--ignore-unmatch", "--", GITMODULES, cwd=source)
    else:
        put_gitmodules(source, tip)
    as_human("commit", "-q", "--allow-empty", "-m", "The tip .gitmodules",
             cwd=source)
    tip_tree = git("ls-tree", "-r", "HEAD", cwd=source).stdout
    assert "160000" not in tip_tree, tip_tree
    return source


def opened(adopter, source: Path, tmp_path: Path):
    return adopter.Source.open(str(source), tmp_path / "read")


# --- where the history holds a gitlink -------------------------------------

@pytest.mark.parametrize("history, verb", HISTORIES.values(),
                         ids=list(HISTORIES))
def test_the_history_is_read_where_the_extraction_reads_it(
        adopter, tmp_path, history, verb):
    """Each of these failed `execute`'s extraction on main (measured with
    git 2.43 and `git filter-repo` 2.47.0). The source's own configuration
    hides a gitlink from a plain `git log` twice over, and its checked-out
    `.gitmodules` is the file git's submodule reader dies on, which a `git
    log` that ran that reader would die on too."""
    source = history_source(tmp_path, history)
    git("config", "diff.ignoreSubmodules", "all", cwd=source)
    git("config", "log.showRoot", "false", cwd=source)
    assert (source / GITMODULES).read_bytes() == BARE_PATH.encode()
    found = adopter._exported_gitlink(opened(adopter, source, tmp_path))
    assert re.fullmatch(NAMED.replace("(adds|removes)", verb), found), found


def test_a_history_with_no_gitlink_is_read_to_its_root(adopter, tmp_path):
    source = history_source(tmp_path, None)
    assert adopter._exported_gitlink(opened(adopter, source, tmp_path)) \
        is None


def test_a_history_git_cannot_read_is_refused_not_taken_to_hold_none(
        adopter, tmp_path):
    """A tree of the first commit, gone from the object store: the scan
    cannot finish, and a history it could not read has not been shown to
    hold no gitlink."""
    source = history_source(tmp_path, None)
    tree = git("rev-parse", "HEAD~1^{tree}", cwd=source).stdout.strip()
    loose = source / ".git" / "objects" / tree[:2] / tree[2:]
    os.chmod(loose, stat.S_IWRITE)   # git writes objects read-only
    loose.unlink()
    with pytest.raises(adopter.Refusal) as caught:
        adopter._exported_gitlink(opened(adopter, source, tmp_path))
    assert caught.value.code == "git-failed"
    assert tree in caught.value.detail


# --- what `check` finds -----------------------------------------------------

def planned(source: Path, base: Path, answers: dict) -> Path:
    """`plan` for `source`, its `.gitmodules` question answered and any
    other entry's `leg:` set as `answers` says."""
    plan = base / "plan" / "adoption-plan.yaml"
    plan.parent.mkdir()
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    text = plan.read_bytes().decode()
    for path, leg in answers.items():
        entry = re.search(rf"  - path: {re.escape(path)}\n    leg: (\S+)\n",
                          text)
        assert entry, f"no entry {path} in the plan"
        if entry[1] == "null":
            resolve(plan, path, leg)
            text = plan.read_bytes().decode()
        else:
            text = text.replace(entry[0],
                                f"  - path: {path}\n    leg: {leg}\n", 1)
    plan.write_bytes(text.encode())
    return plan


def findings(plan: Path) -> list[tuple[str, str]]:
    result = run_script(ADOPT, "check", "--plan", str(plan))
    found = [tuple(line.split(" ", 1)[1].split(": ", 1))
             for line in result.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert result.returncode == (1 if found else 0), result.stderr
    return found


def in_the_history(adopter, verb: str = "removes") -> re.Pattern:
    """The end of the finding for a gitlink only the history holds."""
    return re.compile(re.escape(adopter.FAILS_IN_THE_HISTORY).replace(
        re.escape("{}"), NAMED.replace("(adds|removes)", verb)) + "$")


#: Where the plan sends `.gitmodules`; the two legs are extracted either way.
EITHER_WAY = pytest.mark.parametrize("modules_leg", ["code", "drop"])


@EITHER_WAY
@pytest.mark.parametrize("tip, said", [
    (BARE_PATH, "missing value for 'submodule.b.path'"),
    ('[submodule "b"]\n\tpath = vendor/b\n\turl\n',
     "missing value for 'submodule.b.url'"),
    # git's submodule reader dies on these three with no value as well;
    # `branch` crashes git 2.43 outright, with nothing said.
    (REGISTRATION + "\tignore\n", "missing value for 'submodule.b.ignore'"),
    (REGISTRATION + "\tupdate\n", "missing value for 'submodule.b.update'"),
    (REGISTRATION + "\tbranch\n", "missing value for 'submodule.b.branch'"),
    (BAD_LINE, "fatal: bad config line 2 in .gitmodules"),
], ids=["path", "url", "ignore", "update", "branch", "bad-line"])
def test_check_finds_a_gitmodules_the_extraction_cannot_read(
        adopter, tmp_path, modules_leg, tip, said):
    """On main each of these passed `check`, but for a bad line kept in a
    leg, which it said fails in the CLONE: the extraction fails first."""
    plan = planned(history_source(tmp_path, tip=tip), tmp_path,
                   {GITMODULES: modules_leg})
    found = findings(plan)
    assert [code for code, _ in found] == [UNREADABLE], found
    detail = found[0][1]
    assert detail.startswith("git cannot read the source's .gitmodules for "
                             f"its submodules ({said}), "), detail
    assert in_the_history(adopter).search(detail), detail


def test_check_names_a_commit_no_branch_of_the_adoption_holds(adopter,
                                                              tmp_path):
    """The submodule is on a branch never merged: the person reading the
    finding finds no such commit on `main`, so it is named."""
    plan = planned(history_source(tmp_path, on_a_branch_never_merged),
                   tmp_path, {GITMODULES: "code"})
    found = findings(plan)
    assert [code for code, _ in found] == [UNREADABLE], found
    assert in_the_history(adopter, "adds").search(found[0][1]), found


@pytest.mark.parametrize("tip", [
    # read as true, and git's submodule reader goes on
    REGISTRATION + "\tfetchRecurseSubmodules\n",
    REGISTRATION + "\tshallow\n",
    # a well-formed file registering a submodule the tree no longer holds
    REGISTRATION,
    # no `.gitmodules` at the tip at all: nothing for the reader to read
    None,
], ids=["fetchRecurseSubmodules", "shallow", "stale-registration",
        "no-gitmodules"])
def test_check_passes_a_gitmodules_the_extraction_reads(tmp_path, tip):
    """Each of these adopts on main with the history's submodule, and
    `check` still passes it."""
    answers = {GITMODULES: "code"} if tip is not None else {}
    plan = planned(history_source(tmp_path, tip=tip), tmp_path, answers)
    assert findings(plan) == []


def test_a_plan_that_extracts_no_leg_is_not_refused(tmp_path):
    """Every path rooted or dropped: `git filter-repo` never runs, so
    nothing reads the file, and on main this adopts and verifies."""
    plan = planned(history_source(tmp_path), tmp_path,
                   {GITMODULES: "drop", "src/": "root", "specs/": "root"})
    assert findings(plan) == []


def test_a_key_with_no_value_and_no_gitlink_anywhere_still_passes(tmp_path):
    """#166's S3, unchanged: with no gitlink in the tree or its history,
    nothing reads the file with git's submodule reader."""
    plan = planned(history_source(tmp_path, None), tmp_path,
                   {GITMODULES: "code"})
    assert findings(plan) == []


# --- what `execute` refuses -------------------------------------------------

@EITHER_WAY
def test_execute_refuses_it_before_any_leg_exists(adopter, tmp_path,
                                                  monkeypatch, modules_leg):
    """The refusal is `check`'s finding, raised by `_refuse_what_check_finds`
    before `_create_leg_remotes`: the directory the legs go in is never
    made."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    plan = planned(history_source(tmp_path), tmp_path,
                   {GITMODULES: modules_leg})
    found = findings(plan)
    remotes = tmp_path / REMOTES
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    refusal = caught.value
    assert refusal.code == UNREADABLE
    assert refusal.detail.splitlines()[1:] == [
        f"  FINDING {code}: {detail}" for code, detail in found]
    assert "no leg repository was created" in refusal.remediation
    assert refusal.remediation.endswith("\n" + adopter.SUBMODULE_REMEDIATION)
    assert not remotes.exists()


# --- end to end -------------------------------------------------------------

@needs_filter_repo
def test_the_issue_shape_is_refused_and_the_repaired_source_then_adopts(
        tmp_path):
    """#195 as the issue measured it: `check` 0 and `execute` 2 after both
    leg remotes existed, so that the corrected re-run met
    `leg-remote-exists`. Now `check` finds it, `execute` refuses it with no
    leg made, and once the source's `.gitmodules` is repaired the same
    `--local-remote-dir` takes the adoption."""
    source = history_source(tmp_path)
    plan = planned(source, tmp_path, {GITMODULES: "code"})
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert (f"FINDING {UNREADABLE}: git cannot read the source's .gitmodules "
            "for its submodules (missing value for 'submodule.b.path'), and "
            "the source's tip holds no submodule but the history `git "
            "filter-repo` rewrites does") in checked.stderr
    remotes, work = tmp_path / REMOTES, tmp_path / "work"
    flags = ("--yes", "--local-remote-dir", str(remotes))
    refused = run_script(ADOPT, "execute", "--plan", str(plan), *flags,
                         "--work-dir", str(work))
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {UNREADABLE}: 1 finding(s) in " in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists() or not any(remotes.iterdir()), \
        "a refused plan left a leg repository behind"

    put_gitmodules(source, REGISTRATION)
    as_human("commit", "-qm", "Repair .gitmodules", cwd=source)
    repaired = tmp_path / "repaired"
    repaired.mkdir()
    plan = planned(source, repaired, {GITMODULES: "code"})
    assert run_script(ADOPT, "check", "--plan", str(plan)).returncode == 0
    adopted = run_script(ADOPT, "execute", "--plan", str(plan), *flags,
                         "--work-dir", str(repaired / "work"))
    assert adopted.returncode == 0, adopted.stderr + adopted.stdout
    assert "adoption verified" in adopted.stdout
    for role in ("spec", "code"):
        assert (remotes / f"{PROJECT}-{role}.git").is_dir()
