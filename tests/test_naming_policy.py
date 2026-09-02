# SPDX-License-Identifier: Apache-2.0
"""The naming policy classifies what it claims to, and refuses what it does not."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy, Refusal  # noqa: E402

POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"
VALIDATOR = REPO / "scripts" / "validate-repository-naming.py"


@pytest.fixture(scope="module")
def policy() -> NamingPolicy:
    return NamingPolicy.load(POLICY_PATH)


def _family(policy: NamingPolicy, family_id: str) -> dict:
    return next(f for f in policy.families if f["id"] == family_id)


@pytest.mark.parametrize("family_id", ["neutral-product", "install",
                                       "domain-descendant", "project-leg"])
def test_family_examples_classify_to_their_own_family(policy, family_id):
    """Every example in the DATA classifies to the family that declares it."""
    family = _family(policy, family_id)
    for example in family["examples"]:
        found = policy.classify(example)
        assert found is not None, f"{example} classified as nothing"
        assert found[0] == family_id, f"{example} -> {found}, wanted {family_id}"


def test_project_leg_roles_are_distinguished(policy):
    """The three leg forms are told apart, which is what the scaffold relies on."""
    family = _family(policy, "project-leg")
    for role in family["roles"]:
        for example in role["examples"]:
            assert policy.classify(example) == ("project-leg", role["id"])


@pytest.mark.parametrize("family_id", ["neutral-product", "install",
                                       "domain-descendant", "project-leg"])
def test_counter_examples_do_not_match_their_family(policy, family_id):
    """A counter-example says 'not THIS family'.

    Several still land in the residual assembly-root class — `MedChart` is a
    perfectly good project name — and that is the honest reading rather than a
    gap. What must never happen is a counter-example satisfying the pattern it
    is filed against.
    """
    family = _family(policy, family_id)
    for name in family.get("counter_examples") or []:
        hits = [m for m in policy.matches(name) if m[0] == family_id]
        assert not hits, f"{name} unexpectedly matched {family_id}"


def test_unclassified_examples_match_no_family(policy):
    for name in policy.data["unclassified_examples"]:
        assert policy.classify(name) is None, f"{name} unexpectedly classified"


def test_overlaps_are_reported_not_hidden(policy):
    """`openxFactory` satisfies three forms; precedence picks one, --explain
    shows all three."""
    matches = policy.matches("openxFactory")
    assert [m[0] for m in matches] == ["neutral-product", "domain-descendant",
                                       "project-leg"]
    assert policy.classify("openxFactory") == ("neutral-product", None)


def test_cli_accepts_good_names():
    result = run_script(VALIDATOR, "openChart", "MedxChart", "Hermes-Install",
                        "Atlas", "Atlas-spec", "Atlas-code")
    assert result.returncode == 0, result.stderr
    assert "project-leg/spec" in result.stdout


def test_cli_exits_nonzero_on_an_unclassified_name():
    result = run_script(VALIDATOR, "Atlas_spec")
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr


def test_cli_strips_the_owner_prefix():
    result = run_script(VALIDATOR, "opensoft/openxFactory")
    assert result.returncode == 0
    assert "neutral-product" in result.stdout


def test_cli_explain_names_the_winner_and_the_overlap():
    result = run_script(VALIDATOR, "--explain", "openxFactory")
    assert result.returncode == 0
    assert "OVERLAP resolved by precedence" in result.stdout
    assert "openxFactory: neutral-product" in result.stdout


def test_cli_refuses_with_no_target():
    """A validator invoked with no scan target refuses rather than self-tests."""
    result = run_script(VALIDATOR, "--policy", str(POLICY_PATH))
    assert result.returncode == 2
    assert "naming-no-target" in result.stderr


def test_cli_refuses_a_file_that_is_not_a_naming_policy(tmp_path):
    bogus = tmp_path / "not-a-policy.yaml"
    bogus.write_text("schema_version: 1\nkind: something-else\n")
    result = run_script(VALIDATOR, "--policy", str(bogus), "Atlas")
    assert result.returncode == 2
    assert "policy-wrong-kind" in result.stderr


def test_cli_reads_a_project_manifest(project):
    result = run_script(VALIDATOR, "--project", str(project / "project.yaml"))
    assert result.returncode == 0, result.stderr
    assert "project-leg/assembly" in result.stdout


def test_cli_finds_a_role_that_disagrees_with_its_name(project):
    manifest = project / "project.yaml"
    manifest.write_text(manifest.read_text().replace(
        "  - role: spec\n    repository: testorg/Atlas-spec",
        "  - role: spec\n    repository: testorg/Atlas-code"))
    result = run_script(VALIDATOR, "--project", str(manifest))
    assert result.returncode == 1
    assert "declared role 'spec'" in result.stderr


def test_topic_is_derived_from_the_id(policy):
    assert policy.topic_for("atlas") == "xf-project-atlas"
    assert policy.topic_pattern.match("xf-project-atlas")


def test_the_policy_file_refuses_to_load_when_absent():
    with pytest.raises(Refusal):
        NamingPolicy.load(REPO / "contracts" / "no-such-policy.yaml")
