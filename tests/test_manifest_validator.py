# SPDX-License-Identifier: Apache-2.0
"""`project.yaml` is the source of the group, so it is checked like one."""

from __future__ import annotations

import pytest

from conftest import run_script


def validate(project):
    return run_script(project / "scripts" / "validate-manifest.py", cwd=project)


def edit(project, old: str, new: str) -> None:
    manifest = project / "project.yaml"
    text = manifest.read_text()
    assert old in text, f"fixture drift: {old!r} not in project.yaml"
    manifest.write_text(text.replace(old, new, 1))


def test_a_scaffolded_manifest_is_valid(project):
    result = validate(project)
    assert result.returncode == 0, result.stderr
    assert "manifest ok" in result.stdout


def test_wrong_kind_is_a_finding(project):
    edit(project, "kind: project-manifest", "kind: project-register")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-kind" in result.stderr


def test_a_topic_that_is_not_derived_from_the_id_is_a_finding(project):
    edit(project, "topic: xf-project-atlas", "topic: xf-project-something-else")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-topic" in result.stderr


def test_a_missing_role_is_a_finding(project):
    edit(project,
         '  - role: code\n    repository: testorg/Atlas-code\n    path: code\n',
         "")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-roles" in result.stderr


def test_a_duplicated_role_is_a_finding(project):
    edit(project, "  - role: code\n    repository: testorg/Atlas-code",
         "  - role: spec\n    repository: testorg/Atlas-code")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-roles" in result.stderr


def test_a_leg_name_outside_the_naming_policy_is_a_finding(project):
    edit(project, "repository: testorg/Atlas-code",
         "repository: testorg/Atlas-tests")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr


def test_a_leg_whose_name_is_not_a_leg_at_all_is_a_finding(project):
    edit(project, "repository: testorg/Atlas-code",
         "repository: testorg/openChart")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-not-a-leg" in result.stderr


def test_the_assembly_leg_must_be_at_dot(project):
    edit(project, '  - role: assembly\n    repository: testorg/Atlas\n    path: "."',
         '  - role: assembly\n    repository: testorg/Atlas\n    path: assembly')
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-assembly-path" in result.stderr


def test_legs_split_across_organisations_is_a_finding(project):
    edit(project, "repository: testorg/Atlas-spec",
         "repository: otherorg/Atlas-spec")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-legs-split" in result.stderr


def test_a_shape_pinned_by_tag_is_refused_in_the_manifest_too(project):
    edit(project, "  revision_kind: commit", "  revision_kind: tag")
    result = validate(project)
    assert result.returncode == 1
    assert "pin-tag-only" in result.stderr


def test_an_election_with_no_elector_is_a_finding(project):
    edit(project, 'elected_by: "Test Human"', 'elected_by: ""')
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-elected-by" in result.stderr


def test_a_bad_id_is_a_finding(project):
    edit(project, "id: atlas", "id: Atlas")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-id" in result.stderr


def test_an_absent_manifest_refuses_rather_than_passing(project):
    (project / "project.yaml").unlink()
    result = validate(project)
    assert result.returncode == 2
    assert "manifest-missing" in result.stderr


def test_an_unparsable_manifest_refuses(project):
    (project / "project.yaml").write_text("legs:\n\t- role: spec\n")
    result = validate(project)
    assert result.returncode == 2
    assert "yaml-unparsable" in result.stderr
