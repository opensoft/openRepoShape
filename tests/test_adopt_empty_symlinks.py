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

A link whose target BEGINS WITH A NUL BYTE is the same link to Linux (#388):
`\\0spec.md` is 8 bytes, not the empty blob, but a symlink's target ends at
its first NUL, so it is empty there, and on main `check` said `plan ok` and
`execute` failed as above. Now `plan` and `check` read the target of every
link whose blob is not empty, in one `git cat-file --batch`, and report such
a link the same way; each test of the rule runs with both targets.

The links are made in the INDEX with `git update-index --cacheinfo`, as the
issue's reproduction makes them, so no symlink is ever made on a disk to
build a source, and every test but one runs on Windows too. `execute` is
refused before it clones anything, so nothing here checks a link out except
the end-to-end test of a link given a target, which is skipped where the
platform cannot make one.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, as_human, git, make_source_repo, run_script, \
    write_plan

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
#: `core.symlinks=false` for every git a run starts, as Git for Windows has it
#: by default.
SYMLINKS_OFF = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.symlinks",
                "GIT_CONFIG_VALUE_0": "false"}
#: The issue's target (#388): 8 bytes, the first of them NUL, so Linux reads
#: it as the empty target.
NUL_LED = b"\0spec.md"
#: A target that names something: the control.
NAMED = b"spec.md"
#: Each target `plan-empty-symlink` reports, and how its finding begins.
TARGETS = [pytest.param(b"", "is empty", id="empty"),
           pytest.param(NUL_LED, "begins with a NUL byte", id="nul-led")]
#: Each test of the rule, run with both targets.
with_each_target = pytest.mark.parametrize("target, words", TARGETS)
#: How every finding and NOTE names the link at `link` whose target is
#: `words`.
SAID = "`{link}` is a symlink whose target {words} at the source commit"


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


def source_with_links(tmp_path: Path, *links: str, tree=None,
                      target: bytes = b"") -> Path:
    """The issue's source with a symlink to `target`, empty by default, at
    each of `links`, committed, as `git update-index --cacheinfo` and `git
    commit` make it."""
    source = make_source_repo(tmp_path / "Thing", tree=tree or TREE,
                              edits=())
    for path in links:
        put_link(source, path, target)
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
#: removes anything. And `.github` kept in the root, where the shape writes
#: `.github/workflows/validate.yml` through it: the walk of #183 meets it, and
#: it is still this one finding, not `plan-root-symlink` beside it.
PLACES = [
    pytest.param("docs/empty-link", {}, id="in-docs-sent-to-spec"),
    *(pytest.param("empty-link", {"empty-link": leg},
                   id=f"top-level-answered-{leg}")
      for leg in ("root", "code", "spec", "drop")),
    pytest.param(".github", {".github": "root"},
                 id="above-a-shape-path-kept-in-the-root"),
]


# --- the rule, in memory ---------------------------------------------------

def row(path: str, mode: str = "100644", size: int = 1,
        oid: str = "0" * 40) -> tuple:
    """A row of `Source.tree()`: `(path, mode, blob id, size)`."""
    return (path, mode, oid, size)


#: Blob ids for rows whose targets the in-memory tests hand in, as
#: `symlink_targets` reads them: by blob id.
NUL_OID, NAMED_OID, UNREAD_OID = "1" * 40, "2" * 40, "3" * 40


def test_only_a_symlink_of_size_zero_is_empty(adopter):
    """The size `ls-tree -l` gives a symlink is its target's length. An
    empty FILE is not a symlink, a symlink with a target is not empty, and a
    submodule, which `Source.tree()` gives size 0 for `ls-tree`'s `-`, is
    neither."""
    tree = [row("a", SYMLINK, 0), row("b", SYMLINK, 7), row("c", "100644", 0),
            row("d", "160000", 0), row("e/f", SYMLINK, 0)]
    assert adopter.empty_symlinks(tree, {}) == ["a", "e/f"]


def test_a_symlink_whose_target_begins_with_nul_is_empty_too(adopter):
    """#388: `\\0spec.md` is 8 bytes, but a symlink's target ends at its
    first NUL, so Linux reads it as the empty target. Only a SYMLINK's
    target counts: a file whose blob begins with NUL is a file. A link whose
    target names something is not empty, and neither is one whose target was
    not read: it is judged by its size alone, as before."""
    tree = [row("a", SYMLINK, 8, NUL_OID), row("b", SYMLINK, 7, NAMED_OID),
            row("c", size=8, oid=NUL_OID), row("d", SYMLINK, 7, UNREAD_OID),
            row("e", SYMLINK, 0)]
    targets = {NUL_OID: NUL_LED, NAMED_OID: NAMED}
    assert adopter.empty_symlinks(tree, targets) == ["a", "e"]


def test_the_finding_says_where_a_nul_led_target_ends(adopter):
    """The same finding, and the same remediation, in words true of this
    blob, which is not empty: it is a plain file, not an empty one, where
    `core.symlinks` is false."""
    found, remediation = adopter._empty_symlink_findings(
        [row("docs/odd-link", SYMLINK, 8, NUL_OID)], {NUL_OID: NUL_LED})
    finding, = found
    assert finding.startswith(
        f"FINDING {CODE}: `docs/odd-link` is a symlink whose target begins "
        "with a NUL byte at the source commit; a symlink's target ends at "
        "its first NUL, so this one is empty too, and Linux cannot make a "
        "symlink to nothing. ")
    assert "the clone holds it as a plain file, " in finding
    assert remediation == [adopter.EMPTY_SYMLINK_REMEDIATION]


def test_the_targets_are_read_in_one_pass_and_only_where_there_is_one(
        adopter, tmp_path, monkeypatch):
    """ONE `git cat-file --batch` reads the target of every symlink whose
    blob `Source.tree()` gives a size, each blob once however many links
    share it, byte for byte, a line break included. A link of size 0 (here
    `docs/empty`) is the empty target already, and a file is no link:
    neither is read."""
    source = source_with_links(tmp_path, "docs/empty")
    links = {"docs/named": NAMED, "docs/nul-led": NUL_LED,
             "docs/line-break": b"line\nbreak", "docs/named-too": NAMED}
    for path, target in links.items():
        put_link(source, path, target)
    as_human("commit", "-qm", "Add the links with a target", cwd=source)
    opened = adopter.Source.open(str(source), tmp_path / WORK)
    tree = opened.tree()
    started = []
    real_run = subprocess.run

    def counted(args, *rest, **kwargs):
        started.append(list(args))
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr(adopter.subprocess, "run", counted)
    targets = adopter.symlink_targets(opened, tree)
    assert targets == {oid: links[path] for path, _, oid, _ in tree
                       if path in links}
    assert len(targets) == 3, "the two links to `spec.md` share one blob"
    assert started == [["git", "cat-file", "--batch"]]


def test_a_source_whose_links_are_all_empty_reads_no_target(
        adopter, tmp_path, monkeypatch):
    """Every link of size 0 is the empty target already, so no process is
    started to read one."""
    source = source_with_links(tmp_path, "docs/empty", "docs/empty-too")
    opened = adopter.Source.open(str(source), tmp_path / WORK)
    tree = opened.tree()
    monkeypatch.setattr(adopter.subprocess, "run", None)
    assert adopter.symlink_targets(opened, tree) == {}


def test_the_finding_names_the_link_and_says_why_whatever_the_answer(
        adopter):
    found, remediation = adopter._empty_symlink_findings(
        [row("docs/empty-link", SYMLINK, 0)], {})
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
        [row("README.md"), row("link", SYMLINK, 7, NAMED_OID)],
        {NAMED_OID: NAMED}) == ([], [])


def test_past_twenty_the_rest_are_counted(adopter):
    tree = [row(f"l{n:02d}", SYMLINK, 0) for n in range(22)]
    tree.append(row("l22", SYMLINK, 8, NUL_OID))
    found, _ = adopter._empty_symlink_findings(tree, {NUL_OID: NUL_LED})
    assert len(found) == 21
    assert found[19].startswith(f"FINDING {CODE}: `l19` ")
    assert found[20] == (f"FINDING {CODE}: … and 3 more symlinks whose "
                         "target is empty or begins with a NUL byte")


def test_the_finding_spells_a_name_it_cannot_print(adopter):
    """A source name is bytes and may hold a line break: one line still."""
    finding, = adopter._empty_symlink_findings(
        [row("a\nb", SYMLINK, 0)], {})[0]
    assert "\n" not in finding
    assert "`a\\nb` is a symlink" in finding


# --- `plan` and `check` -----------------------------------------------------

@with_each_target
def test_plan_notes_it_and_still_writes_the_plan(tmp_path, target, words):
    source = source_with_links(tmp_path, "docs/empty-link", target=target)
    out = tmp_path / "plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--out", str(out),
                         "--elected-by", "Test Human")
    assert written.returncode == 0, written.stderr + written.stdout
    assert out.is_file()
    said = SAID.format(link="docs/empty-link", words=words)
    assert f"\nNOTE {said}" in written.stdout
    assert "Linux cannot make a symlink to nothing. " in written.stdout
    assert (f"`check` reports this as `{CODE}` and `execute` refuses it, "
            "whatever the plan answers") in written.stdout


def test_plan_notes_nothing_for_a_symlink_with_a_target(tmp_path):
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    put_link(source, "docs/link", b"spec.md")
    as_human("commit", "-qm", "Add a link", cwd=source)
    written = write_plan(source, tmp_path / "plan.yaml")
    assert written.returncode == 0, written.stderr + written.stdout
    assert CODE not in written.stdout


@with_each_target
@pytest.mark.parametrize("link, answers", PLACES)
def test_check_reports_what_it_passed(tmp_path, link, answers, target,
                                      words):
    """#303's runs and #388's, one finding each. Before this, each NUL-led
    link here checked `plan ok` but `.github`, which the walk of #183
    reported as `plan-root-symlink`, a link to a path the source does not
    hold, with a fix (send it to a leg, or `drop` it) that is none here."""
    plan = planned(source_with_links(tmp_path, link, target=target),
                   tmp_path / "plan.yaml", answers)
    result = check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(
        f"FINDING {CODE}: {SAID.format(link=link, words=words)}")
    assert "plan ok" not in result.stdout
    assert result.stderr.count("Remediation: a symlink's target is a fact "
                               "of the source") == 1


@with_each_target
def test_check_reports_it_where_git_makes_no_symlinks_too(tmp_path, target,
                                                          words):
    """The issue's second run, where every clone held the link as a plain
    file and the adoption verified: `check` reads the tree, not the disk,
    so `core.symlinks=false` changes nothing it says."""
    plan = planned(source_with_links(tmp_path, "docs/empty-link",
                                     target=target),
                   tmp_path / "plan.yaml", env=SYMLINKS_OFF)
    off, on = check(plan, env=SYMLINKS_OFF), check(plan)
    assert off.returncode == on.returncode == 1
    assert findings_of(off) == findings_of(on)
    finding, = findings_of(off)
    assert SAID.format(link="docs/empty-link", words=words) in finding


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

@with_each_target
@pytest.mark.parametrize("link, answers", PLACES)
def test_execute_refuses_it_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path, link, answers, target,
        words):
    source = source_with_links(tmp_path, link, target=target)
    plan = planned(source, tmp_path / "plan.yaml", answers)
    printed, = findings_of(check(plan))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == CODE
    assert printed in caught.value.detail
    assert SAID.format(link=link, words=words) in printed
    assert "no leg repository was created" in caught.value.remediation
    assert adopter.EMPTY_SYMLINK_REMEDIATION in caught.value.remediation
    no_leg_was_created(tmp_path, source)


@needs_filter_repo
@with_each_target
@pytest.mark.parametrize("env", [
    pytest.param(None, id="symlinks-on"),
    pytest.param(SYMLINKS_OFF, id="symlinks-off"),
])
@pytest.mark.parametrize("link, answers", [
    pytest.param("docs/empty-link", {}, id="in-docs"),
    pytest.param("empty-link", {"empty-link": "drop"}, id="top-level-drop"),
])
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path, env, link, answers, target, words):
    """The issue's runs as commands: on main, both leg repositories and exit
    2 (symlinks on; with nothing said, until #171's fix said what failed), or
    `adoption verified` over a leg no clone with symlinks on can check out
    (symlinks off). Refused before a leg is made, so the EMPTY
    `--local-remote-dir` stays empty."""
    source = source_with_links(tmp_path, link, target=target)
    plan = planned(source, tmp_path / "plan.yaml", answers, env=env)
    (tmp_path / REMOTES).mkdir()
    result = executed(plan, tmp_path, env=env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {CODE}: 1 finding(s) in " in result.stderr
    assert SAID.format(link=link, words=words) in result.stderr
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
@pytest.mark.parametrize("env", [
    pytest.param(None, id="symlinks-on", marks=needs_disk_symlinks),
    pytest.param(SYMLINKS_OFF, id="symlinks-off"),
])
def test_the_link_given_a_target_adopts_end_to_end(tmp_path, env):
    """The other remediation, and #388's control: a target that names
    something (`spec.md`, 7 bytes), read now, is no finding. With symlinks
    on, `execute`'s clones check the link out, so this needs a platform
    that makes symlinks; with them off, the clones hold it as a file. Either
    way the leg holds the link."""
    source = source_with_links(tmp_path, "docs/empty-link")
    put_link(source, "docs/empty-link", NAMED)
    as_human("commit", "-qm", "Give the link a target", cwd=source)
    plan = planned(source, tmp_path / "plan.yaml", env=env)
    result = executed(plan, tmp_path, env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    spec = tmp_path / REMOTES / f"{PROJECT}-spec.git"
    assert git("ls-tree", "main", "--", "docs/empty-link",
               cwd=spec).stdout.startswith(f"{SYMLINK} blob ")

