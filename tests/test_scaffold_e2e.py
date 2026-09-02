# SPDX-License-Identifier: Apache-2.0
"""End to end: scaffold into local bare remotes, clone recursively, bootstrap.

NO REAL REPOSITORY IS EVER CREATED. `--local-remote-dir` makes three bare
repositories on disk and uses them as origins; `gh` is never invoked.
"""

from __future__ import annotations

import os
import subprocess
import sys

from conftest import (FILE_PROTOCOL, ORG, PROJECT, REPO, SCAFFOLD, git,
                      run_script)

DEGRADE_LINE = "authority is not wallet-carried in this org"


# --- the scaffold ----------------------------------------------------------

def test_dry_run_creates_nothing(tmp_path):
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Northwind",
                        "--elected-by", "Test Human", "--dry-run",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr
    assert "--dry-run: nothing was created." in result.stdout
    assert "xf-project-northwind" in result.stdout
    assert not remotes.exists()


def test_a_bad_project_name_refuses_before_creating_anything(tmp_path):
    """A naming mistake costs a message, not three repositories and a rename."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Atlas-tests",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "naming-unclassified" in result.stderr
    assert not remotes.exists()


def test_a_bad_project_id_refuses_before_creating_anything(tmp_path):
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "North_Wind",
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-bad-id" in result.stderr
    assert not remotes.exists()


def test_the_scaffold_refuses_with_no_elector(tmp_path):
    """Electing the shape is a human's act and the manifest records whose.

    `git config user.name` is the only fallback, so the global and system
    config are suppressed to make the no-elector path reachable at all.
    """
    remotes = tmp_path / "remotes"
    env = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Northwind",
                        "--elected-by", "", "--dry-run",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"), env=env)
    assert result.returncode == 2, result.stdout
    assert "scaffold-no-elector" in result.stderr
    assert not remotes.exists()


def test_the_scaffold_creates_three_bare_remotes(scaffolded):
    for name in (PROJECT, f"{PROJECT}-spec", f"{PROJECT}-code"):
        assert (scaffolded["remotes"] / f"{name}.git").is_dir()
    assert "NEXT STEPS" in scaffolded["stdout"]
    assert "make bootstrap" in scaffolded["stdout"]


def test_rescaffolding_over_an_existing_remote_refuses(scaffolded, tmp_path):
    """There is no --force: re-running over a live project is not a scaffold."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(scaffolded["remotes"]),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "There is no --force" in result.stderr


def test_the_topic_is_set_on_the_manifest(project):
    assert "topic: xf-project-atlas" in (project / "project.yaml").read_text()


def test_the_legs_are_submodules_at_the_declared_paths(project):
    status = git("submodule", "status", cwd=project).stdout
    assert " code" in status and " spec" in status
    modules = (project / ".gitmodules").read_text()
    assert 'path = spec' in modules and 'path = code' in modules
    assert "branch =" not in modules, (
        "`.gitmodules` must carry no `branch=`: that would buy the ergonomics "
        "by weakening the pin, and then 'what commit is this project' has two "
        "answers")


# --- the clone and the bootstrap -------------------------------------------

def test_a_recursive_clone_leaves_the_legs_detached(scaffolded, tmp_path):
    """The submodule tax bootstrap exists to pay, demonstrated."""
    target = tmp_path / "fresh"
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(scaffolded["remotes"] / f"{PROJECT}.git"), str(target)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    head = git("rev-parse", "--abbrev-ref", "HEAD", cwd=target / "spec").stdout
    assert head.strip() == "HEAD", "expected a detached HEAD before bootstrap"


def test_bootstrap_succeeds_and_puts_the_legs_on_tracking_branches(project):
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "bootstrap ok" in result.stdout
    for leg in ("spec", "code"):
        branch = git("rev-parse", "--abbrev-ref", "HEAD",
                     cwd=project / leg).stdout.strip()
        assert branch == "main", f"{leg} is on {branch!r}, expected 'main'"


def test_bootstrap_does_not_move_the_pin(project):
    before = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    run_script(project / "scripts" / "bootstrap.py", cwd=project)
    after = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    assert before == after
    tip = git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip()
    assert tip == before, "the tracking branch must be created AT the pin"


def test_bootstrap_prints_the_degrade_line_when_no_register_exists(project):
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert DEGRADE_LINE in result.stdout
    assert result.returncode == 0


def test_bootstrap_reports_a_pin_that_disagrees_with_a_branch_tip(project):
    """It prints both and moves neither."""
    run_script(project / "scripts" / "bootstrap.py", cwd=project)
    git("commit", "-q", "--allow-empty", "-m", "local work",
        cwd=project / "spec")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert "!= branch main tip" in result.stdout
    assert "not moving an existing branch" in result.stdout


def test_bootstrap_fails_when_a_validator_fails(project):
    (project / "scripts" / "repo_shape.py").write_text(
        (project / "scripts" / "repo_shape.py").read_text() + "\n# edited\n")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 1
    assert "bootstrap FAILED" in result.stderr


def test_bootstrap_reads_a_wallet_register_when_one_exists(project):
    register = project / "governance" / "review-authority" / "register.yaml"
    register.parent.mkdir(parents=True, exist_ok=True)
    register.write_text(
        "register_version: 1\n"
        "rows:\n"
        "  - row_id: row-test-0001\n"
        "    holder_ref: agent:merge-readiness-council\n"
        "    target_repo: testorg/Atlas-code\n"
        "    act: review\n"
        "    state: active\n"
        "    expires_at: \"2026-11-23T12:00:00Z\"\n"
        "  - row_id: row-test-0002\n"
        "    holder_ref: agent:somebody-else\n"
        "    target_repo: otherorg/Unrelated\n"
        "    act: review\n"
        "    state: active\n")
    result = run_script(project / "scripts" / "bootstrap.py", cwd=project)
    assert result.returncode == 0, result.stderr
    assert DEGRADE_LINE not in result.stdout
    assert "agent:merge-readiness-council" in result.stdout
    assert "testorg/Atlas-code" in result.stdout
    assert "agent:somebody-else" not in result.stdout
    assert "confers nothing and enforces nothing" in result.stdout


def test_bootstrap_is_schema_neutral(project, tmp_path):
    """A one-repository project runs the same command: the submodule step is a
    no-op and the authority readout is unchanged."""
    plain = tmp_path / "plain"
    plain.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(plain)], check=True)
    (plain / "scripts").mkdir()
    for name in ("bootstrap.py", "repo_shape.py"):
        (plain / "scripts" / name).write_text(
            (project / "scripts" / name).read_text())
    result = run_script(plain / "scripts" / "bootstrap.py", cwd=plain)
    assert result.returncode == 0, result.stderr
    assert "no submodule legs declared" in result.stdout
    assert "has not elected the schema" in result.stdout
    assert DEGRADE_LINE in result.stdout


def test_make_targets_exist(project):
    makefile = (project / "Makefile").read_text()
    for target in ("bootstrap:", "validate:", "pins:"):
        assert target in makefile


def test_the_ci_workflow_checks_out_submodules(project):
    workflow = (project / ".github" / "workflows" / "validate.yml").read_text()
    assert "submodules: true" in workflow
    assert "on:\n  pull_request:" in workflow
    for validator in ("validate-repository-naming.py", "validate-manifest.py",
                      "validate-pins.py"):
        assert validator in workflow


def test_the_shape_pin_records_the_openreposhape_commit(project):
    sys.path.insert(0, str(REPO / "scripts"))
    from repo_shape import load_yaml
    pin = load_yaml(project / "contracts" / "shape-pin.yaml")
    assert pin["revision_kind"] == "commit"
    assert pin["materialization"] == "copied"
    assert pin["source_repository"] == "opensoft/openRepoShape"
    assert len(pin["files"]) >= 9
    manifest = load_yaml(project / "project.yaml")
    assert manifest["shape"]["commit"] == pin["commit"]
