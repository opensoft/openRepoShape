# SPDX-License-Identifier: Apache-2.0
"""A symlink in the source whose target is empty (#303).

A source tree can hold a `120000` entry whose blob is the empty blob, and
`plan` and `check` never read a link's target, so `check` said `plan ok`. On
main (b30595c, and c7c02fa) what `execute` did next turned on how git checks
a symlink out where it ran:

- with symlinks on, Linux refuses a symlink to nothing, so `execute` created
  both leg repositories and then failed in its first clone of the source,
  exit 2 with nothing on stderr, whatever the plan answered for the link,
  `drop` included;
- with `core.symlinks=false`, it said `adoption verified` over a leg or a
  root that no clone with symlinks on can check out.

Now `check` reports each such link as `plan-empty-symlink`, whatever the plan
answers and whatever `core.symlinks` says, `execute` refuses it before any
leg exists, and `plan` notes it while it still writes the plan.

The links are made in the INDEX with `git update-index --cacheinfo`, as the
issue's reproduction makes them, so no symlink is ever made on a disk to
build a source, and every test but one runs on Windows too. `execute` is
refused before it clones anything, so nothing here checks a link out except
the end-to-end test of a link given a target, which is skipped where the
platform cannot make one.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, appended_to_command_scope, as_human, git,
                      make_source_repo, run_script, write_plan)

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: Git for Windows checks a tracked symlink out as a plain file unless
#: `core.symlinks` is on, and a runner may make one only in Developer Mode.
needs_disk_symlinks = pytest.mark.skipif(
    sys.platform == "win32",
    reason="a tracked symlink is a plain file in a Windows checkout")

PROJECT = "Northwind"
UTF8 = "utf-8"
REMOTES = "remotes"
WORK = "work"
ROLES = ("spec", "code")
SPLIT_BRANCH = "adopt/three-repo-shape"
SYMLINK = "120000"
CODE = "plan-empty-symlink"
#: The issue's small source: a spec, the code, and a README the root keeps.
TREE = {"src/app.py": "print(1)\n", "docs/spec.md": "# Spec\n",
        "README.md": "# Thing\n"}


def symlinks_off() -> dict:
    """`core.symlinks=false` for every git a run starts, as Git for Windows
    has it by default: appended, when it is called, to the git command scope
    the environment holds (#758)."""
    return appended_to_command_scope(os.environ, [("core.symlinks", "false")])


@pytest.fixture(scope="module")
def adopter():
    module_spec = importlib.util.spec_from_file_location(
        "adopt_empty_symlinks", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """Every refusal here comes before `git filter-repo` would be used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


# --- sources and plans -----------------------------------------------------

def blob(repo: Path, content: bytes) -> str:
    """`content` written as a blob of `repo`: bytes on stdin, as a hand edit
    leaves them on every platform."""
    made = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(repo), input=content, capture_output=True,
                          check=True)
    return made.stdout.decode().strip()


def put_link(repo: Path, path: str, target: bytes = b"") -> None:
    """A symlink at `path` whose target is `target`, in the index only."""
    git("update-index", "--add", "--cacheinfo",
        f"{SYMLINK},{blob(repo, target)},{path}", cwd=repo)


def source_with_links(tmp_path: Path, *links: str, tree=None) -> Path:
    """The issue's source with an empty symlink at each of `links`,
    committed, as `git update-index --cacheinfo` and `git commit` make it."""
    source = make_source_repo(tmp_path / "Thing", tree=tree or TREE,
                              edits=())
    for path in links:
        put_link(source, path)
    as_human("commit", "-qm", "Add the links", cwd=source)
    return source


def planned(source: Path, out: Path, answers: dict | None = None,
            env: dict | None = None) -> Path:
    """`plan` for `source`, each entry `answers` names given that `leg:`
    with a reason, whatever `plan` proposed for it."""
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--elected-by",
                         "Test Human", "--elected-on", "2026-09-02",
                         "--out", str(out), env=env)
    assert written.returncode == 0, written.stderr + written.stdout
    text = out.read_bytes().decode(UTF8)
    for path, leg in (answers or {}).items():
        text, count = re.subn(
            rf"(?m)^(  - path: \"?{re.escape(path)}\"?\n    leg: )\S+$",
            rf'\g<1>{leg}\n    resolution: "answered by the test"', text)
        assert count == 1, f"no entry {path} in the plan"
    out.write_bytes(text.encode(UTF8))
    return out


def check(plan: Path, env: dict | None = None):
    return run_script(ADOPT, "check", "--plan", str(plan), env=env)


def findings_of(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def no_leg_was_created(tmp_path: Path, source: Path) -> None:
    assert not (tmp_path / REMOTES).exists(), (
        "not even the directory the legs go in")
    for role in ROLES:
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()
    assert not (tmp_path / WORK / PROJECT).exists(), "no clone of the source"
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


def executed(plan: Path, tmp_path: Path, env: dict | None = None):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(tmp_path / REMOTES),
                      "--work-dir", str(tmp_path / WORK), env=env)


#: Where the link sits and what the plan answers for it: the issue's two
#: runs, `docs/empty-link` inside an entry the rules send to the spec leg,
#: and a top-level `empty-link`, which `plan` asks about, answered each way.
#: `drop` is among them: with symlinks on, the clone fails before the split
#: removes anything.
PLACES = [
    pytest.param("docs/empty-link", {}, id="in-docs-sent-to-spec"),
    *(pytest.param("empty-link", {"empty-link": leg},
                   id=f"top-level-answered-{leg}")
      for leg in ("root", "code", "spec", "drop")),
]


# --- the rule, in memory ---------------------------------------------------

def row(path: str, mode: str = "100644", size: int = 1) -> tuple:
    """A row of `Source.tree()`: `(path, mode, blob id, size)`."""
    return (path, mode, "0" * 40, size)


def test_only_a_symlink_of_size_zero_is_empty(adopter):
    """The size `ls-tree -l` gives a symlink is its target's length. An
    empty FILE is not a symlink, a symlink with a target is not empty, and a
    submodule, which `Source.tree()` gives size 0 for `ls-tree`'s `-`, is
    neither."""
    tree = [row("a", SYMLINK, 0), row("b", SYMLINK, 7), row("c", "100644", 0),
            row("d", "160000", 0), row("e/f", SYMLINK, 0)]
    assert adopter.empty_symlinks(tree) == ["a", "e/f"]


def test_the_finding_names_the_link_and_says_why_whatever_the_answer(
        adopter):
    found, remediation = adopter._empty_symlink_findings(
        [row("docs/empty-link", SYMLINK, 0)])
    finding, = found
    assert finding.startswith(
        f"FINDING {CODE}: `docs/empty-link` is a symlink whose target is "
        "empty at the source commit, and Linux cannot make a symlink to "
        "nothing. ")
    assert "after both leg repositories were created" in finding
    assert "whatever the plan answers for it" in finding
    assert "`core.symlinks` is false" in finding
    assert remediation == [adopter.EMPTY_SYMLINK_REMEDIATION]
    assert "`drop` included" in remediation[0]
    assert "commit, and re-run `plan`" in remediation[0]


def test_a_source_with_none_has_no_finding_and_no_remediation(adopter):
    assert adopter._empty_symlink_findings(
        [row("README.md"), row("link", SYMLINK, 9)]) == ([], [])


def test_past_twenty_the_rest_are_counted(adopter):
    tree = [row(f"l{n:02d}", SYMLINK, 0) for n in range(23)]
    found, _ = adopter._empty_symlink_findings(tree)
    assert len(found) == 21
    assert found[19].startswith(f"FINDING {CODE}: `l19` ")
    assert found[20] == (f"FINDING {CODE}: … and 3 more symlinks whose "
                         "target is empty")


def test_the_finding_spells_a_name_it_cannot_print(adopter):
    """A source name is bytes and may hold a line break: one line still."""
    finding, = adopter._empty_symlink_findings(
        [row("a\nb", SYMLINK, 0)])[0]
    assert "\n" not in finding
    assert "`a\\nb` is a symlink" in finding


# --- `plan` and `check` -----------------------------------------------------

def test_plan_notes_it_and_still_writes_the_plan(tmp_path):
    source = source_with_links(tmp_path, "docs/empty-link")
    out = tmp_path / "plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--out", str(out),
                         "--elected-by", "Test Human")
    assert written.returncode == 0, written.stderr + written.stdout
    assert out.is_file()
    assert ("\nNOTE `docs/empty-link` is a symlink whose target is empty at "
            "the source commit, and Linux cannot make a symlink to "
            "nothing. ") in written.stdout
    assert (f"`check` reports this as `{CODE}` and `execute` refuses it, "
            "whatever the plan answers") in written.stdout


def test_plan_notes_nothing_for_a_symlink_with_a_target(tmp_path):
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    put_link(source, "docs/link", b"spec.md")
    as_human("commit", "-qm", "Add a link", cwd=source)
    written = write_plan(source, tmp_path / "plan.yaml")
    assert written.returncode == 0, written.stderr + written.stdout
    assert CODE not in written.stdout


@pytest.mark.parametrize("link, answers", PLACES)
def test_check_reports_what_it_passed(tmp_path, link, answers):
    """#303's runs: on main, `plan ok` for each."""
    plan = planned(source_with_links(tmp_path, link),
                   tmp_path / "plan.yaml", answers)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {CODE}: `{link}` is a symlink ")
    assert "plan ok" not in result.stdout
    assert result.stderr.count("Remediation: a symlink's target is a fact "
                               "of the source") == 1


def test_check_reports_it_where_git_makes_no_symlinks_too(tmp_path):
    """The issue's second run, where every clone held the link as an empty
    file and the adoption verified: `check` reads the tree, not the disk,
    so `core.symlinks=false` changes nothing it says."""
    plan = planned(source_with_links(tmp_path, "docs/empty-link"),
                   tmp_path / "plan.yaml", env=symlinks_off())
    off, on = check(plan, env=symlinks_off()), check(plan)
    assert off.returncode == on.returncode == 1
    assert findings_of(off) == findings_of(on)
    assert len(findings_of(off)) == 1


def test_each_link_is_named(tmp_path):
    plan = planned(source_with_links(tmp_path, "docs/a", "docs/b"),
                   tmp_path / "plan.yaml")
    assert [line.split("`")[1] for line in findings_of(check(plan))] == [
        "docs/a", "docs/b"]


def test_it_comes_after_the_unsafe_paths_and_before_coverage(
        adopter, no_filter_repo_probe, tmp_path):
    """No answer fixes it, so it is listed before the findings about the
    answers, here an entry deleted from the plan (`plan-uncovered`), and
    after #196's entry paths (`plan-unsafe-path`, a file `-notes.md` the
    plan sends to the spec leg), which `execute`'s refusal still wears."""
    source = source_with_links(tmp_path, "docs/empty-link",
                               tree={**TREE, "-notes.md": "# Notes\n"})
    plan = planned(source, tmp_path / "plan.yaml", {"-notes.md": "spec"})
    text = plan.read_bytes().decode(UTF8)
    text, count = re.subn(r"(?m)^  - path: src/\n(?:    .*\n)+", "", text)
    assert count == 1
    plan.write_bytes(text.encode(UTF8))
    codes = [line.split(":")[0] for line in findings_of(check(plan))]
    assert codes == ["FINDING plan-unsafe-path", f"FINDING {CODE}",
                     "FINDING plan-uncovered"]
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == "plan-unsafe-path"
    assert adopter.EMPTY_SYMLINK_REMEDIATION in caught.value.remediation
    no_leg_was_created(tmp_path, source)


@pytest.mark.parametrize("how", ["removed", "given-a-target"])
def test_the_remediation_the_finding_names_makes_check_pass(tmp_path, how):
    """Fixed in the source and planned again, the plan checks ok."""
    source = source_with_links(tmp_path, "docs/empty-link")
    if how == "removed":
        git("update-index", "--force-remove", "docs/empty-link", cwd=source)
    else:
        put_link(source, "docs/empty-link", b"spec.md")
    as_human("commit", "-qm", f"The link, {how}", cwd=source)
    result = check(planned(source, tmp_path / "plan.yaml"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


# --- `execute` ---------------------------------------------------------------

@pytest.mark.parametrize("link, answers", PLACES)
def test_execute_refuses_it_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path, link, answers):
    source = source_with_links(tmp_path, link)
    plan = planned(source, tmp_path / "plan.yaml", answers)
    printed, = findings_of(check(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == CODE
    assert printed in caught.value.detail
    assert "no leg repository was created" in caught.value.remediation
    assert adopter.EMPTY_SYMLINK_REMEDIATION in caught.value.remediation
    no_leg_was_created(tmp_path, source)


@needs_filter_repo
@pytest.mark.parametrize("off", [
    pytest.param(False, id="symlinks-on"),
    pytest.param(True, id="symlinks-off"),
])
@pytest.mark.parametrize("link, answers", [
    pytest.param("docs/empty-link", {}, id="in-docs"),
    pytest.param("empty-link", {"empty-link": "drop"}, id="top-level-drop"),
])
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path, off, link, answers):
    """The issue's runs as commands: on main, both leg repositories and exit
    2 with nothing said (symlinks on), or `adoption verified` over a leg no
    clone with symlinks on can check out (symlinks off). Refused before a
    leg is made, so the EMPTY `--local-remote-dir` stays empty."""
    env = symlinks_off() if off else None
    source = source_with_links(tmp_path, link)
    plan = planned(source, tmp_path / "plan.yaml", answers, env=env)
    (tmp_path / REMOTES).mkdir()
    result = executed(plan, tmp_path, env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {CODE}: 1 finding(s) in " in result.stderr
    assert f"`{link}` is a symlink whose target is empty" in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert "adoption verified" not in result.stdout
    assert list((tmp_path / REMOTES).iterdir()) == [], "no leg was made"
    assert not (tmp_path / WORK / PROJECT).exists(), "the source not cloned"
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


@needs_filter_repo
def test_the_link_removed_in_the_source_adopts_end_to_end(tmp_path):
    source = source_with_links(tmp_path, "docs/empty-link")
    git("update-index", "--force-remove", "docs/empty-link", cwd=source)
    as_human("commit", "-qm", "Remove the link", cwd=source)
    plan = planned(source, tmp_path / "plan.yaml")
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout


@needs_filter_repo
@needs_disk_symlinks
def test_the_link_given_a_target_adopts_end_to_end(tmp_path):
    """The other remediation: `execute`'s clones now check the link out, so
    this needs a platform that makes symlinks, and the leg holds it."""
    source = source_with_links(tmp_path, "docs/empty-link")
    put_link(source, "docs/empty-link", b"spec.md")
    as_human("commit", "-qm", "Give the link a target", cwd=source)
    plan = planned(source, tmp_path / "plan.yaml")
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    spec = tmp_path / REMOTES / f"{PROJECT}-spec.git"
    assert git("ls-tree", "main", "--", "docs/empty-link",
               cwd=spec).stdout.startswith(f"{SYMLINK} blob ")

