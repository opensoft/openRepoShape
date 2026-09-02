# SPDX-License-Identifier: Apache-2.0
"""THE LOCKSTEP VALIDATOR — one test per way the three facts come apart.

The three facts are the GITLINK, the PIN FILE's `commit:`, and every workflow
`@<sha>` reference naming the leg. Each drift case below is one of them moving
alone, which is precisely the failure that went a day unnoticed in the xFactory
aggregation because the check runs on pull requests only.
"""

from __future__ import annotations

from conftest import git, run_script

OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"
OTHER_DIGEST = "0" * 64


def validate(project):
    return run_script(project / "scripts" / "validate-pins.py", cwd=project)


def edit_pin(project, name: str, old: str, new: str) -> None:
    pin = project / "contracts" / name
    text = pin.read_text()
    assert old in text, f"fixture drift: {old!r} not in {name}"
    pin.write_text(text.replace(old, new, 1))


def test_a_scaffolded_project_is_in_lockstep(project):
    result = validate(project)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "pins ok" in result.stdout


# --- drift case 1: the gitlink moves and the pin file does not ---------------

def test_gitlink_ahead_of_the_pin_is_a_finding(project):
    """Exactly the aggregation's August defect: `git submodule update`, commit,
    and leave `contracts/<leg>-pin.yaml` behind."""
    git("commit", "-q", "--allow-empty", "-m", "advance the spec leg",
        cwd=project / "spec")
    git("add", "--", "spec", cwd=project)
    git("commit", "-q", "-m", "bump the spec gitlink alone", cwd=project)
    result = validate(project)
    assert result.returncode == 1
    assert "pin-gitlink-mismatch" in result.stderr
    assert "THE LOCKSTEP RULE" in result.stderr


def test_a_commit_that_is_not_40_hex_refuses(project):
    edit_pin(project, "spec-pin.yaml", "commit: \"", "commit: \"x")
    result = validate(project)
    assert result.returncode == 2  # not 40 hex: a refusal, not a finding
    assert "pin-tag-only" in result.stderr


# --- drift case 2: the digest no longer describes the pinned bytes ----------

def test_a_digest_that_does_not_recompute_is_a_finding(project):
    pin = (project / "contracts" / "spec-pin.yaml").read_text()
    recorded = pin.split("tree_sha256: \"")[1].split("\"")[0]
    edit_pin(project, "spec-pin.yaml", recorded, OTHER_DIGEST)
    result = validate(project)
    assert result.returncode == 1
    assert "pin-digest-mismatch" in result.stderr


def test_an_unstated_digest_definition_is_a_finding(project):
    edit_pin(project, "spec-pin.yaml", "digest_definition: sorted-ls-tree-r-v1",
             "digest_definition: whatever-git-does")
    result = validate(project)
    assert result.returncode == 1
    assert "pin-digest-definition" in result.stderr


# --- drift case 3: a workflow reference names a different sha ---------------

def test_a_workflow_ref_that_disagrees_with_the_gitlink_is_a_finding(project):
    workflow = project / ".github" / "workflows" / "lane.yml"
    workflow.write_text(
        "name: lane\non:\n  pull_request:\njobs:\n  lane:\n"
        "    uses: testorg/Atlas-code/.github/workflows/reusable.yml@"
        + OTHER_SHA + "\n")
    result = validate(project)
    assert result.returncode == 1
    assert "pin-workflow-ref-mismatch" in result.stderr
    assert "THE LOCKSTEP RULE" in result.stderr


def test_a_workflow_ref_that_agrees_with_the_gitlink_passes(project):
    gitlink = git("rev-parse", "HEAD:code", cwd=project).stdout.strip()
    workflow = project / ".github" / "workflows" / "lane.yml"
    workflow.write_text(
        "name: lane\non:\n  pull_request:\njobs:\n  lane:\n"
        f"    uses: testorg/Atlas-code/.github/workflows/reusable.yml@{gitlink}\n")
    result = validate(project)
    assert result.returncode == 0, result.stderr
    assert "workflow @<sha> reference(s) agree" in result.stdout


def test_a_ref_to_something_that_is_not_a_leg_is_ignored(project):
    """`actions/checkout@<sha>` is not a leg and is none of this validator's
    business."""
    workflow = project / ".github" / "workflows" / "lane.yml"
    workflow.write_text(
        f"name: lane\non:\n  pull_request:\njobs:\n  lane:\n"
        f"    steps:\n      - uses: actions/checkout@{OTHER_SHA}\n")
    assert validate(project).returncode == 0


# --- the shape pin: a copied file edited in place ---------------------------

def test_editing_a_copied_shape_file_is_drift(project):
    target = project / "scripts" / "repo_shape.py"
    target.write_text(target.read_text() + "\n# local edit\n")
    result = validate(project)
    assert result.returncode == 1
    assert "shape-copy-drift" in result.stderr
    assert "carry the change upstream" in result.stderr


def test_a_deleted_shape_copy_is_reported(project):
    (project / "Makefile").unlink()
    result = validate(project)
    assert result.returncode == 1
    assert "shape-copy-missing" in result.stderr


# --- refusals: the question cannot be asked --------------------------------

def test_an_uninitialized_submodule_refuses_rather_than_passing(project):
    (project / "spec" / ".git").unlink()
    result = validate(project)
    assert result.returncode == 2
    assert "pin-submodule-uninitialized" in result.stderr
    assert "git submodule update --init" in result.stderr


def test_a_pin_that_is_not_a_commit_refuses(project):
    edit_pin(project, "spec-pin.yaml", "revision_kind: commit",
             "revision_kind: tag")
    result = validate(project)
    assert result.returncode == 1
    assert "pin-tag-only" in result.stderr
    assert "A tag can be moved" in result.stderr


def test_a_commit_absent_from_the_object_store_refuses(project):
    edit_pin(project, "spec-pin.yaml",
             (project / "contracts" / "spec-pin.yaml").read_text()
             .split("commit: \"")[1].split("\"")[0], OTHER_SHA)
    result = validate(project)
    assert result.returncode in (1, 2)
    assert ("pin-commit-unresolvable" in result.stderr
            or "pin-gitlink-mismatch" in result.stderr)


def test_a_missing_pin_file_refuses(project):
    (project / "contracts" / "code-pin.yaml").unlink()
    result = validate(project)
    assert result.returncode == 2
    assert "pin-missing" in result.stderr


def test_a_missing_shape_pin_refuses(project):
    (project / "contracts" / "shape-pin.yaml").unlink()
    result = validate(project)
    assert result.returncode == 2
    assert "shape-pin-missing" in result.stderr


def test_a_pin_path_that_disagrees_with_the_manifest_is_a_finding(project):
    edit_pin(project, "spec-pin.yaml", "submodule_path: spec",
             "submodule_path: specification")
    result = validate(project)
    assert result.returncode == 1
    assert "pin-path-mismatch" in result.stderr
