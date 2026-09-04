# SPDX-License-Identifier: Apache-2.0
"""Adopting a repository that has a specification and NO code.

THE INKROUTER CASE, as a test. Brett Heap, 2026-09-04: *"We do not have any
code yet for either service and this is just 2 of what will be 8 services."*
A plan that assigns no path to the code leg cannot extract one — `git
filter-repo` over an empty path list rewrites every commit to nothing and
leaves an empty HISTORY, which is not an empty repository — so the leg is
SEEDED from `templates/code-root/` instead, and the split mounts and pins it
like any other.

NO REAL REPOSITORY IS EVER CREATED and no network is used: the legs are bare
repositories on disk and the source is a repository in a temporary directory.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

PROJECT = "Redwood"

#: A specification repository: requirements, decisions, the project-level
#: workflow tooling every repository of this estate carries — and nothing a
#: path rule would call code. Deliberately NOT empty of ambiguity: `examples/`
#: still has to be answered, because a spec-only adoption is not a shortcut
#: past the questions.
SPEC_ONLY_TREE = {
    "openspec/changes/add-routing/proposal.md": "## Why\n",
    "specs/001-render/spec.md": "# Render\n",
    "specs/001-render/tasks.md": "- [ ] one\n",
    "contracts/routing.yaml": "schema_version: 1\nkind: policy\n",
    "docs/architecture.md": "# Architecture\n",
    "README.md": "# IRRS\n",
    "LICENSE": "Apache-2.0\n",
    "AGENTS.md": "Follow the procedure.\n",
    "CLAUDE.md": "Follow the procedure.\n",
    ".claude/commands/ship.md": "ship it\n",
    "examples/golden-run/expected.yaml": "result: ok\n",
}
ANSWERS = (("examples/", "spec"), (".claude/", "root"))

#: The second and third commits, both on the specification side — there is no
#: implementation to touch, which is the whole point.
EDITS = (
    ("specs/001-render/spec.md", "# Render\n\nA second paragraph.\n",
     "Extend the specification"),
    ("openspec/changes/add-routing/proposal.md", "## Why\n\nBecause.\n",
     "Argue the change"),
)

pytestmark = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def spec_only_plan(tmp_path, *extra):
    source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE, edits=EDITS)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return source, plan, written


@pytest.fixture(scope="module")
def adopted(tmp_path_factory) -> dict:
    base = tmp_path_factory.mktemp("adopt-spec-only")
    source, plan, _ = spec_only_plan(base, "--allow-empty-leg", "code")
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(base / "remotes"),
                        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    return {"base": base, "source": source, "plan": plan,
            "remotes": base / "remotes", "work": base / "work",
            "check": checked, "stdout": result.stdout}


@pytest.fixture
def adopted_clone(adopted, tmp_path):
    target = tmp_path / PROJECT
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         "-b", "adopt/three-repo-shape", str(adopted["source"]), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return target


# --- the plan records it ----------------------------------------------------

def test_the_plan_records_the_leg_it_would_seed(tmp_path):
    _source, plan_path, written = spec_only_plan(tmp_path)
    plan = load_yaml(plan_path)
    assert plan["seeding"]["code"]["seeded_from_template"] is True
    assert plan["seeding"]["code"]["template"] == "templates/code-root"
    assert plan["seeding"]["spec"]["seeded_from_template"] is False
    assert "template" not in plan["seeding"]["spec"]
    assert plan["allow_empty_legs"] == []
    assert "SEEDED from templates/code-root/" in written.stdout


def test_the_plan_records_the_consent_when_it_is_given(tmp_path):
    _source, plan_path, written = spec_only_plan(
        tmp_path, "--allow-empty-leg", "code")
    assert load_yaml(plan_path)["allow_empty_legs"] == ["code"]
    assert "--allow-empty-leg code is declared" in written.stdout


def test_an_ordinary_repository_records_neither_leg_as_seeded(source_repo,
                                                              tmp_path):
    """The synthetic repository has both sides, so nothing changes for it."""
    out = tmp_path / "plan.yaml"
    assert write_plan(source_repo, out, project=PROJECT).returncode == 0
    plan = load_yaml(out)
    assert plan["seeding"] == {
        "spec": {"seeded_from_template": False},
        "code": {"seeded_from_template": False}}


# --- check WARNS, it does not refuse ---------------------------------------

def test_check_warns_about_the_seeded_leg_and_still_passes(tmp_path):
    _source, plan, _ = spec_only_plan(tmp_path)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "plan ok" in result.stdout
    assert "WARNING the code leg will be SEEDED" in result.stdout
    assert "SEED the code leg from templates/code-root/" in result.stdout
    assert "`execute` REFUSES until a human says so" in result.stdout


def test_check_says_the_record_is_stale_once_a_path_is_moved_into_the_leg(
        tmp_path):
    """The plan is EDITED between `plan` and `execute`; a human answering
    `examples/` with `code` un-empties the leg. The entries win and the note
    says so — refusing there would punish the human for answering."""
    source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE, edits=EDITS)
    plan = tmp_path / "plan.yaml"
    assert write_plan(source, plan, project=PROJECT).returncode == 0
    resolve(plan, "examples/", "code")
    resolve(plan, ".claude/", "root")
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "the entries now say extracted" in result.stdout
    assert "WARNING the code leg will be SEEDED" not in result.stdout


# --- execute needs the human's word ----------------------------------------

def test_execute_refuses_to_seed_a_leg_nobody_consented_to(tmp_path):
    _source, plan, _ = spec_only_plan(tmp_path)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "adopt-empty-leg-unconsented" in result.stderr
    assert "--allow-empty-leg code" in result.stderr
    assert not (tmp_path / "remotes").exists(), \
        "a refused execute creates nothing at all"


def test_the_consent_may_be_given_on_execute_itself(tmp_path):
    _source, plan, _ = spec_only_plan(tmp_path)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--allow-empty-leg", "code",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout


# --- the seeded leg ---------------------------------------------------------

def test_the_seeded_leg_is_one_commit_of_the_template(adopted, tmp_path):
    clone = tmp_path / "code-leg"
    subprocess.run(["git", "clone", "-q",
                    str(adopted["remotes"] / f"{PROJECT}-code.git"),
                    str(clone)], check=True)
    assert int(git("rev-list", "--count", "HEAD", cwd=clone).stdout) == 1
    assert (clone / "README.md").is_file()
    assert (clone / "src" / ".gitkeep").is_file()
    readme = (clone / "README.md").read_text()
    assert readme.startswith(f"# {PROJECT}-code")
    assert "{{" not in readme, "every placeholder must have been substituted"
    message = git("log", "-1", "--format=%B", cwd=clone).stdout
    assert "SEEDED" in message
    assert "templates/code-root/" in message
    assert "carries no history" in message


def test_the_spec_leg_still_carries_the_history(adopted, tmp_path):
    clone = tmp_path / "spec-leg"
    subprocess.run(["git", "clone", "-q",
                    str(adopted["remotes"] / f"{PROJECT}-spec.git"),
                    str(clone)], check=True)
    assert int(git("rev-list", "--count", "HEAD", cwd=clone).stdout) > 1
    assert (clone / "specs" / "001-render" / "spec.md").is_file()
    assert "Source Human" in git("log", "--format=%an", cwd=clone).stdout


def test_the_split_commit_says_the_leg_was_seeded(adopted):
    message = git("log", "-1", "--format=%B", "adopt/three-repo-shape",
                  cwd=adopted["source"]).stdout
    assert "MOVED TO THE CODE LEG" in message
    assert "this leg was SEEDED from" in message
    assert "templates/code-root/" in message


# --- the verification table -------------------------------------------------

def test_the_verification_names_the_seeded_leg_and_still_adds_up(adopted):
    out = adopted["stdout"]
    assert "adoption verified: every source path is in exactly one place" in out
    row = [line for line in out.splitlines()
           if line.strip().startswith("code ") and " of " in line][0]
    assert row.strip().startswith("code       0 of "), row
    assert row.endswith("source paths (seeded from template)"), row
    counted = sum(int(line.split()[1]) for line in out.splitlines()
                  if line.strip().startswith(("spec ", "code ", "root ",
                                              "drop "))
                  and " of " in line)
    total = int([line for line in out.splitlines()
                 if " of " in line and "source paths" in line][0].split()[3])
    assert counted == total, "the table must add up to the source's file count"


# --- the adopted root -------------------------------------------------------

def test_the_root_mounts_the_seeded_leg_and_passes_its_own_gate(adopted_clone):
    assert (adopted_clone / "spec" / "specs" / "001-render" / "spec.md").is_file()
    assert (adopted_clone / "code" / "README.md").is_file()
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py", [])):
        result = run_script(adopted_clone / "scripts" / validator, *args,
                            cwd=adopted_clone)
        assert result.returncode == 0, \
            f"{validator}: {result.stderr}{result.stdout}"


def test_the_seeded_leg_is_pinned_exactly_like_an_extracted_one(adopted,
                                                                adopted_clone):
    pin = load_yaml(adopted_clone / "contracts" / "code-pin.yaml")
    assert pin["revision_kind"] == "commit"
    tip = git("rev-parse", "main",
              cwd=adopted["remotes"] / f"{PROJECT}-code.git").stdout.strip()
    assert pin["commit"] == tip
    gitlink = git("rev-parse", "HEAD:code", cwd=adopted_clone).stdout.strip()
    assert gitlink == tip, "the gitlink and the pin move together or not"
