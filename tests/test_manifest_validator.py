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


# --- the `naming:` record: a descendant form is a claim that needs a pin ----

ASSEMBLY_NAMING = ("    naming:\n"
                   "      form: project-leg\n"
                   "      role: assembly\n"
                   "      also_matches: []\n")


def test_the_scaffolded_naming_block_is_accepted(project):
    """A scaffolded `Atlas` records the form it classified as and an EMPTY
    overlap, and its own validator agrees."""
    assert ASSEMBLY_NAMING in (project / "project.yaml").read_text()
    assert validate(project).returncode == 0


def test_a_naming_block_is_optional(project):
    """The field is a RECORD, not a requirement: a manifest written before it
    existed is not thereby wrong, which is why no schema_version moved."""
    edit(project, ASSEMBLY_NAMING, "")
    result = validate(project)
    assert result.returncode == 0, result.stderr


def test_a_naming_form_that_disagrees_with_the_name_is_a_finding(project):
    edit(project, "      form: project-leg\n      role: assembly",
         "      form: domain-descendant\n      role: assembly")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-form" in result.stderr


def test_an_also_matches_that_invents_an_overlap_is_a_finding(project):
    """`also_matches` records the forms that were NOT chosen. It is not a
    place to add one."""
    edit(project, "      also_matches: []", "      also_matches: [install]")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-also-matches" in result.stderr


def test_a_descendant_form_leg_records_the_overlap_or_is_a_finding(project):
    """Rename the root to a `<Domainx><Product>` name and the empty overlap
    the manifest still claims becomes false."""
    edit(project, "repository: testorg/Atlas\n    path: \".\"",
         "repository: testorg/MedxChart\n    path: \".\"")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-also-matches" in result.stderr
    assert "domain-descendant" in result.stderr


def test_a_descendant_form_leg_with_a_consistent_record_is_accepted(project):
    """The pilot case, in a manifest: an assembly root that also matches the
    descendant form, with no referent declared."""
    edit(project, "repository: testorg/Atlas\n    path: \".\"",
         "repository: testorg/MedxChart\n    path: \".\"")
    edit(project, "      also_matches: []",
         "      also_matches: [domain-descendant]\n"
         "      descendant_referent: openChart\n"
         "      referent_declared: false")
    result = validate(project)
    assert result.returncode == 0, result.stderr


def test_a_referent_declared_without_the_pin_file_is_a_finding(project):
    """`referent_declared: true` is a claim about this tree, so the tree is
    consulted: a declared pin that is not in `contracts/` is a claim wearing
    the costume of a referent."""
    edit(project, "repository: testorg/Atlas\n    path: \".\"",
         "repository: testorg/MedxChart\n    path: \".\"")
    edit(project, "neutral_product_pins: []",
         "neutral_product_pins:\n  - openChart")
    edit(project, "      form: project-leg\n      role: assembly\n"
                  "      also_matches: []",
         "      form: domain-descendant\n      role: ~\n"
         "      also_matches: [project-leg/assembly]\n"
         "      descendant_referent: openChart\n"
         "      referent_declared: true")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-referent-missing" in result.stderr
    # and the leg is no longer a project leg at all, which is also reported
    assert "naming-not-a-leg" in result.stderr


def test_the_pin_file_makes_the_referent_real(project):
    edit(project, "neutral_product_pins: []",
         "neutral_product_pins:\n  - openChart")
    edit(project, "repository: testorg/Atlas-code\n    path: code",
         "repository: testorg/MedxChart\n    path: code")
    edit(project, "      form: project-leg\n      role: code\n"
                  "      also_matches: []",
         "      form: domain-descendant\n      role: ~\n"
         "      also_matches: [project-leg/assembly]\n"
         "      descendant_referent: openChart\n"
         "      referent_declared: true")
    before = validate(project)
    assert "naming-referent-missing" in before.stderr
    (project / "contracts" / "openchart-pin.yaml").write_text(
        "schema_version: 1\nkind: neutral-product-pin\n")
    after = validate(project)
    assert "naming-referent-missing" not in after.stderr


def test_a_referent_declared_flag_that_declares_itself_is_a_finding(project):
    """A `naming:` record cannot vouch for its own descent. The declaration is
    `neutral_product_pins:`; `referent_declared:` only reports it."""
    edit(project, "repository: testorg/Atlas\n    path: \".\"",
         "repository: testorg/MedxChart\n    path: \".\"")
    edit(project, "      also_matches: []",
         "      also_matches: [domain-descendant]\n"
         "      descendant_referent: openChart\n"
         "      referent_declared: true")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-referent-declared" in result.stderr
    assert "a claim; the pin is the referent" in result.stderr


def test_the_x_stem_spelling_of_a_referent_is_accepted_in_a_manifest(project):
    """`codexFactory` descends from `openxFactory`, and the manifest records
    the CANONICAL `openFactory` spelling for the same referent set."""
    edit(project, "neutral_product_pins: []",
         "neutral_product_pins:\n  - openxFactory")
    edit(project, "repository: testorg/Atlas-code\n    path: code",
         "repository: testorg/codexFactory\n    path: code")
    edit(project, "      form: project-leg\n      role: code\n"
                  "      also_matches: []",
         "      form: domain-descendant\n      role: ~\n"
         "      also_matches: [project-leg/assembly]\n"
         "      descendant_referent: openFactory\n"
         "      referent_declared: true")
    result = validate(project)
    assert "naming-referent-declared" not in result.stderr
    assert "naming-form" not in result.stderr
    assert "naming-also-matches" not in result.stderr
    # only the pin FILE is missing, which is the check still doing its job
    assert "naming-referent-missing" in result.stderr
    assert "openxfactory-pin.yaml" in result.stderr


def test_a_referent_on_a_name_that_claims_nothing_is_a_finding(project):
    """`Atlas` is not in `<Domainx><Product>` form and descends from nothing."""
    edit(project, "      also_matches: []",
         "      also_matches: []\n      descendant_referent: openAtlas")
    result = validate(project)
    assert result.returncode == 1
    assert "naming-referent" in result.stderr


def test_neutral_product_pins_must_be_a_list(project):
    edit(project, "neutral_product_pins: []", "neutral_product_pins: openChart")
    result = validate(project)
    assert result.returncode == 1
    assert "manifest-neutral-product-pins" in result.stderr


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
