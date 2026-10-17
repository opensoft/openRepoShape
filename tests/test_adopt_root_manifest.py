# SPDX-License-Identifier: Apache-2.0
"""The source's own top-level `project.yaml`, kept in the root (#305).

`plan` asked about a source's own `project.yaml` under
`ambiguous-top-level-yaml`, whose question offers `root`. Answered `root`,
on main (b30595c, and c7c02fa):

- `check` said `plan ok`;
- `execute` wrote the shape's manifest beside it as `shape/project.yaml`,
  said "nothing was overwritten" and `adoption verified`;
- `shape-doctor.py` then called the root NOT A SHAPE ROOT, and its first
  `make bootstrap` failed naming, manifest and pins.

Now the file is asked a question of its own, `ambiguous-project-yaml`,
which does not offer `root`, and a plan that keeps it in the root anyway, as
a hand-edited one would, is `check`'s finding `plan-root-blocks-manifest`
and `execute`'s refusal before any leg exists. The rule is #313's
(`_root_shape_findings`), extended: the manifest is the one path the shape
writes whose copy beside the source's own stands in for nothing, so the root
holding it is refused outright, on a disk that keeps case and on one that
ignores it.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, make_source_repo, run_script

sys.path.insert(0, str(REPO / "scripts"))
from path_classify import PathPolicy  # noqa: E402

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
UTF8 = "utf-8"
REMOTES = "remotes"
WORK = "work"
ROLES = ("spec", "code")
SPLIT_BRANCH = "adopt/three-repo-shape"
POLICY = REPO / "contracts" / "path-classification.yaml"
CODE = "plan-root-blocks-manifest"
RULE = "ambiguous-project-yaml"
CASE_ASIDE = " once case is ignored, as a macOS or Windows disk does"
THEIRS = "name: theirs\n"
#: The issue's source: a spec, the code, a README the root keeps, and a
#: `project.yaml` of its own.
TREE = {"src/app.py": "print(1)\n", "docs/spec.md": "# Spec\n",
        "README.md": "# Thing\n", "project.yaml": THEIRS}


@pytest.fixture(scope="module")
def adopter():
    module_spec = importlib.util.spec_from_file_location(
        "adopt_root_manifest", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def no_filter_repo_probe(adopter, monkeypatch):
    """Every refusal here comes before `git filter-repo` would be used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


# --- the question `plan` asks ------------------------------------------------

def test_the_manifest_is_a_path_the_shape_writes_into_the_root(adopter):
    assert adopter.SHAPE_MANIFEST in adopter.assembly_root_paths()
    assert (REPO / "templates" / "assembly-root"
            / adopter.SHAPE_MANIFEST).is_file()


def test_project_yaml_is_asked_a_question_with_no_root_in_it(adopter):
    verdict = PathPolicy.load(POLICY).classify_file(adopter.SHAPE_MANIFEST)
    assert verdict.rule == RULE
    assert verdict.leg is None and verdict.review_required
    assert "(spec)" in verdict.question and "(code)" in verdict.question
    assert "(root)" not in verdict.question, "root is offered"
    assert "`root` is not an answer for this file" in verdict.question


def test_every_other_top_level_yaml_is_asked_as_before():
    """Only the manifest's name: `release.yaml` keeps the question that
    offers `root`, and a nested `project.yaml` is not the manifest."""
    policy = PathPolicy.load(POLICY)
    release = policy.classify_file("release.yaml")
    assert release.rule == "ambiguous-top-level-yaml"
    assert "(root)" in release.question
    assert policy.classify_file("config/project.yaml").rule != RULE


def plan_for(tmp_path: Path, tree: dict = TREE) -> tuple[Path, Path]:
    source = make_source_repo(tmp_path / "Thing", tree=tree, edits=())
    out = tmp_path / "plan.yaml"
    written = run_script(ADOPT, "plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--elected-by",
                         "Test Human", "--elected-on", "2026-09-02",
                         "--out", str(out))
    assert written.returncode == 0, written.stderr + written.stdout
    return source, out


def entry_of(plan: Path, path: str) -> str:
    text = plan.read_bytes().decode(UTF8)
    found = re.search(rf"(?m)^  - path: {re.escape(path)}\n(?:    .*\n)+",
                      text)
    assert found, f"no entry {path} in the plan"
    return found.group(0)


def test_plan_asks_the_question_with_no_root_in_it(tmp_path):
    _, plan = plan_for(tmp_path)
    entry = entry_of(plan, "project.yaml")
    assert "    leg: null\n" in entry
    assert f"    rule: {RULE}\n" in entry
    assert "    review_required: true\n" in entry
    assert "(root)" not in entry
    assert "`root` is not an answer for this file" in entry


# --- the rule, in memory ---------------------------------------------------

def row(path: str, mode: str = "100644") -> tuple:
    """A row of `Source.tree()`: `(path, mode, blob id, size)`."""
    return (path, mode, "0" * 40, 1)


def keeping(adopter, *entries: tuple):
    return adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place",
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": [{"path": path, "leg": leg} for path, leg in entries]})


def found(adopter, entries: list, rows: list) -> list[str]:
    return adopter._root_shape_findings(keeping(adopter, *entries), rows)


def test_a_kept_project_yaml_is_a_finding(adopter):
    said, = found(adopter, [("project.yaml", "root")], [row("project.yaml")])
    assert said == (
        f"FINDING {CODE}: the plan keeps the file `project.yaml` in the "
        "assembly root, where the shape writes its manifest. No copy stands "
        "in for the manifest: `shape-doctor.py`, the root's validators and "
        "`make bootstrap` read `project.yaml` at the root itself, and there "
        "they would find the source's file. `execute` would write the "
        "shape's manifest beside it as `shape/project.yaml` and fail its "
        "verification (`adopt-manifest-not-shape`), after both leg "
        "repositories were created and pushed: send `project.yaml` to a leg, "
        "`drop` it, or rename it in the source and re-run `plan`.")


@pytest.mark.parametrize("leg", ["spec", "code", "drop"])
def test_a_project_yaml_the_plan_sends_away_is_not_kept(adopter, leg):
    assert found(adopter, [("project.yaml", leg)], [row("project.yaml")]) \
        == []


@pytest.mark.parametrize("twin", ["Project.yaml", "PROJECT.YAML"])
def test_a_case_twin_is_the_manifest_once_case_is_ignored(adopter, twin):
    """On a macOS or Windows disk `place` finds the twin AT `project.yaml`
    and writes the manifest beside it; on Linux the two stand side by side
    and a clone on such a disk keeps one of them. Refused on every disk, the
    trade #172 and #313 make for theirs."""
    said, = found(adopter, [(twin, "root")], [row(twin)])
    assert said.startswith(
        f"FINDING {CODE}: the plan keeps the file `{twin}` in the assembly "
        f"root, at `project.yaml`{CASE_ASIDE}, where the shape writes its "
        "manifest. ")
    assert said.endswith(f"send `{twin}` to a leg, `drop` it, or rename it "
                         "in the source and re-run `plan`.")


def test_a_kept_symlink_there_is_a_finding_whatever_it_leads_to(adopter):
    """A link to the source's own file leaves that file where the manifest
    is read (NOT A SHAPE ROOT on c7c02fa). A link to nothing has the
    manifest written through it, which a clone that makes no symlinks holds
    as a file naming the target. The tree holds no target, so both are
    refused."""
    said, = found(adopter, [("project.yaml", "root")],
                  [row("project.yaml", "120000")])
    assert said.startswith(f"FINDING {CODE}: the plan keeps the symlink "
                           "`project.yaml` in the assembly root, ")
    assert "and where it leads nowhere, through it, which a clone that " \
           "makes no symlinks holds as a file naming its target; either " \
           "way it would fail its verification " \
           "(`adopt-manifest-not-shape`), after both" in said


def test_a_kept_directory_there_names_what_it_holds(adopter):
    said, = found(adopter, [("project.yaml/", "root")],
                  [row("project.yaml/a.md"), row("project.yaml/b.md")])
    assert said.startswith(
        f"FINDING {CODE}: the plan keeps the file `project.yaml/a.md` and 1 "
        "more in the assembly root under the entry `project.yaml/`, inside "
        "`project.yaml`, where the shape writes its manifest. ")
    assert "there they would find the source's directory." in said
    assert "send `project.yaml/` to a leg" in said


def test_a_submodule_there_is_the_submodule_rules_and_said_once(adopter):
    """`plan-submodule-root` (#166) refuses it; this rule says nothing."""
    assert found(adopter, [("project.yaml", "root")],
                 [row("project.yaml", "160000")]) == []


def test_the_copy_is_not_asked_about_where_the_manifest_is_refused(adopter):
    """The remediation takes `project.yaml` out of the root, so no copy is
    written and the source's own `shape/project.yaml` is in no way."""
    said = found(adopter, [("project.yaml", "root"), ("shape/", "root")],
                 [row("project.yaml"), row("shape/project.yaml")])
    assert [line.split(":")[0] for line in said] == [f"FINDING {CODE}"]


@pytest.mark.parametrize("held", ["README.md", "Makefile", "AGENTS.md"])
def test_every_other_path_the_shape_writes_keeps_its_copy(adopter, held):
    """Not over-refused: a kept `README.md` or `Makefile` is the common
    case, written beside and merged as the follow-up says, as before."""
    assert found(adopter, [(held, "root")], [row(held)]) == []


def test_it_comes_in_the_order_the_shape_writes(adopter):
    """`README.md`'s copy first, the manifest, then the `.github` file."""
    said = found(adopter, [("README.md", "root"), ("project.yaml", "root"),
                           (".github", "root"), ("shape/", "root")],
                 [row("README.md"), row("project.yaml"), row(".github"),
                  row("shape/README.md")])
    assert [line.split(":")[0] for line in said] == [
        "FINDING plan-root-blocks-shape-copy", f"FINDING {CODE}",
        "FINDING plan-root-blocks-shape"]


# --- `check` and `execute`, on real plans ------------------------------------

def answered(plan: Path, leg: str) -> Path:
    """The issue's edit: `project.yaml` answered `leg`, with a reason."""
    text = plan.read_bytes().decode(UTF8)
    text, count = re.subn(
        r"(?m)^(  - path: project\.yaml\n    leg: )\S+$",
        rf'\g<1>{leg}\n    resolution: "the person\'s answer"', text)
    assert count == 1
    plan.write_bytes(text.encode(UTF8))
    return plan


def check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


def findings_of(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def test_check_reports_what_it_passed(tmp_path):
    """#305's run, answered `root`: on main, `plan ok`."""
    _, plan = plan_for(tmp_path)
    result = check(answered(plan, "root"))
    assert result.returncode == 1, result.stdout + result.stderr
    finding, = findings_of(result)
    assert finding.startswith(f"FINDING {CODE}: the plan keeps the file "
                              "`project.yaml` in the assembly root, ")
    assert "plan ok" not in result.stdout
    assert "1 finding(s) in " in result.stderr


@pytest.mark.parametrize("leg", ["spec", "code", "drop"])
def test_the_answers_the_question_offers_check_ok(tmp_path, leg):
    _, plan = plan_for(tmp_path)
    result = check(answered(plan, leg))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout


def test_check_reports_a_case_twin_kept_in_the_root(tmp_path):
    tree = {**{k: v for k, v in TREE.items() if k != "project.yaml"},
            "Project.yaml": THEIRS}
    _, plan = plan_for(tmp_path, tree)
    text = plan.read_bytes().decode(UTF8)
    text, count = re.subn(r"(?m)^(  - path: Project\.yaml\n    leg: )\S+$",
                          r'\g<1>root\n    resolution: "kept"', text)
    assert count == 1
    plan.write_bytes(text.encode(UTF8))
    finding, = findings_of(check(plan))
    assert finding.startswith(
        f"FINDING {CODE}: the plan keeps the file `Project.yaml` in the "
        f"assembly root, at `project.yaml`{CASE_ASIDE}, ")


def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def test_execute_refuses_it_before_any_leg_exists(
        adopter, no_filter_repo_probe, tmp_path):
    source, plan = plan_for(tmp_path)
    printed, = findings_of(check(answered(plan, "root")))
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))
    assert caught.value.code == CODE
    assert printed in caught.value.detail
    assert ("keep in the root no path where the shape writes a file or its "
            "copy") in caught.value.remediation
    assert not (tmp_path / REMOTES).exists()
    for role in ROLES:
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


def executed(plan: Path, tmp_path: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(tmp_path / REMOTES),
                      "--work-dir", str(tmp_path / WORK))


@needs_filter_repo
def test_execute_refuses_it_end_to_end_and_the_remote_dir_stays_empty(
        tmp_path):
    """On main this run made and pushed both legs and the split, said
    `adoption verified`, and left a root the doctor calls NOT A SHAPE
    ROOT."""
    source, plan = plan_for(tmp_path)
    answered(plan, "root")
    (tmp_path / REMOTES).mkdir()
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {CODE}: 1 finding(s) in " in result.stderr
    assert "creating the leg repositories" not in result.stdout
    assert "beside  shape/project.yaml" not in result.stdout
    assert "adoption verified" not in result.stdout
    assert list((tmp_path / REMOTES).iterdir()) == [], "no leg was made"
    assert git("branch", "--list", SPLIT_BRANCH, cwd=source).stdout == ""


@needs_filter_repo
@pytest.mark.parametrize("leg", ["code", "drop"])
def test_an_answer_the_question_offers_adopts_with_the_shapes_manifest(
        tmp_path, leg):
    """The root's `project.yaml` is then the shape's manifest, with no copy
    beside it; sent to a leg, the source's own file is in that leg."""
    source, plan = plan_for(tmp_path)
    answered(plan, leg)
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    assert "beside  shape/project.yaml" not in result.stdout
    root = git("show", f"{SPLIT_BRANCH}:project.yaml", cwd=source).stdout
    assert root.startswith("schema_version: 1\nkind: project-manifest\n"), \
        root
    split = git("ls-tree", "-r", "--name-only", SPLIT_BRANCH,
                cwd=source).stdout.splitlines()
    assert "shape/project.yaml" not in split
    if leg == "code":
        code = tmp_path / REMOTES / f"{PROJECT}-code.git"
        assert git("show", "main:project.yaml", cwd=code).stdout == THEIRS
