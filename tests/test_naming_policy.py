# SPDX-License-Identifier: Apache-2.0
"""The naming policy classifies what it claims to, and refuses what it does not."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy, Refusal, accepts_role  # noqa: E402

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
    """Every example in the DATA classifies to the family that declares it.

    A family that `requires_referent` is given the referent its own data
    records for the example — which is the whole point of the 2026-09-02
    ruling: `MedxChart` is a descendant BECAUSE MedxChart pins `openChart`,
    not because of how it is spelled.
    """
    family = _family(policy, family_id)
    referents = family.get("example_referents") or {}
    for example in family["examples"]:
        pins = {referents[example]} if example in referents else None
        found = policy.classify(example, declared_pins=pins)
        assert found is not None, f"{example} classified as nothing"
        assert found[0] == family_id, f"{example} -> {found}, wanted {family_id}"


def test_every_descendant_example_declares_the_referent_it_needs(policy):
    """The data cannot claim a descendant it has no referent for."""
    family = _family(policy, "domain-descendant")
    assert family.get("requires_referent") is True
    referents = family["example_referents"]
    for example in family["examples"]:
        assert example in referents, f"{example} has no example_referent"
        assert referents[example] in policy.descendant_referents(example)


# --- the ruling: a descendant form is a CLAIM that needs a PIN --------------

def test_a_descendant_form_with_no_pin_is_an_assembly_root(policy):
    """The pilot case. `MedxScribe` in a `MedxSoft` org descends from nothing:
    no `openScribe` exists, none is pinned, and it is an ordinary project."""
    found = policy.classify("MedxScribe", declared_role="assembly")
    assert found == ("project-leg", "assembly")
    assert found.also_matches == ("domain-descendant",)
    assert "no referent pin declared" in found.reason
    assert policy.descendant_referent("MedxScribe") == "openScribe"


def test_a_descendant_form_with_no_pin_and_no_declared_role_is_still_a_leg(policy):
    """With nothing declared at all the residual project-leg form wins, and
    the claim is REPORTED rather than dropped."""
    found = policy.classify("MedxScribe")
    assert found == ("project-leg", "assembly")
    assert found.also_matches == ("domain-descendant",)


def test_the_pin_is_what_makes_a_descendant(policy):
    """`MedxChart` is a descendant BECAUSE MedxChart pins `openChart`."""
    found = policy.classify("MedxChart", declared_pins={"openChart"})
    assert found == ("domain-descendant", None)
    assert found.also_matches == ("project-leg/assembly",)
    assert "declared pin on openChart" in found.reason


def test_the_same_name_without_the_pin_is_not_a_descendant(policy):
    """Same characters, different facts, different answer — and the form the
    name still satisfies survives in `also_matches`."""
    found = policy.classify("MedxChart", declared_role="assembly")
    assert found == ("project-leg", "assembly")
    assert found.also_matches == ("domain-descendant",)


def test_an_unrelated_pin_does_not_make_a_descendant(policy):
    """The referent must be the MATCHING neutral product, not merely a pin."""
    found = policy.classify("MedxScribe", declared_pins={"openChart"})
    assert found == ("project-leg", "assembly")


def test_the_x_stem_spelling_of_a_referent_counts(policy):
    """`codexFactory` descends from `openxFactory`, which the neutral family
    admits; refusing that spelling would be a spelling rule in a semantic
    costume."""
    assert policy.classify("codexFactory",
                           declared_pins={"openxFactory"})[0] == "domain-descendant"


def test_a_qualified_pin_is_accepted(policy):
    """`opensoft/openChart` names the same referent as `openChart`."""
    assert policy.classify(
        "MedxChart", declared_pins={"opensoft/openChart"})[0] == "domain-descendant"


def test_a_neutral_product_is_unambiguous_by_construction(policy):
    """No pin and no declared role can move it: `open` in front says what it
    is, so offering it as an assembly root is still a neutral product."""
    for pins in (None, {"openScribe"}, {"openxScribe"}):
        found = policy.classify("openScribe", declared_role="assembly",
                                declared_pins=pins)
        assert found == ("neutral-product", None)


def test_an_install_is_unambiguous_by_construction(policy):
    for pins in (None, {"openFoo"}):
        found = policy.classify("Foo-Install", declared_role="assembly",
                                declared_pins=pins)
        assert found == ("install", None)


def test_a_spec_name_offered_as_the_assembly_root_is_still_a_spec(policy):
    """A declared role wins only where the NAME satisfies it. Declaring
    `assembly` over `<Project>-spec` does not make it one — which is what
    keeps the scaffold's remaining refusals real."""
    found = policy.classify("MedxScribe-spec", declared_role="assembly")
    assert found == ("project-leg", "spec")


def test_the_claim_without_referent_example_in_the_data_holds(policy):
    """The pilot case is kept IN THE CONTRACT, so the rule is testable from
    the data rather than from memory."""
    family = _family(policy, "domain-descendant")
    for name in family["claim_without_referent_examples"]:
        assert family["_re"].match(name), f"{name} should match the form"
        found = policy.classify(name)
        assert found[0] == "project-leg"
        assert "domain-descendant" in found.also_matches


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
    assert "openxFactory: neutral-product" in result.stdout
    assert "OVERLAP " in result.stdout
    assert "also_matches: domain-descendant, project-leg/assembly" in result.stdout


def test_cli_explain_says_why_a_claim_without_a_referent_is_not_one():
    result = run_script(VALIDATOR, "--explain", "--role", "assembly",
                        "MedxScribe")
    assert result.returncode == 0
    assert "MedxScribe: project-leg / assembly" in result.stdout
    assert "descendant form, no referent pin declared" in result.stdout
    assert "assembly root by declared role" in result.stdout
    assert "also_matches: domain-descendant" in result.stdout
    assert "a CLAIM: needs a declared pin on openScribe" in result.stdout


def test_cli_pins_turn_the_claim_into_a_classification():
    result = run_script(VALIDATOR, "--explain", "--pins", "openChart",
                        "MedxChart")
    assert result.returncode == 0
    assert "MedxChart: domain-descendant" in result.stdout
    assert "declared pin on openChart" in result.stdout


def test_cli_without_pins_reports_the_overlap_in_the_plain_listing():
    result = run_script(VALIDATOR, "MedxScribe")
    assert result.returncode == 0
    assert "project-leg/assembly" in result.stdout
    assert "also_matches domain-descendant" in result.stdout


def test_cli_role_does_not_rescue_a_neutral_product_form():
    """`--role assembly` is a declaration, not an override."""
    result = run_script(VALIDATOR, "--role", "assembly", "openScribe")
    assert result.returncode == 0
    assert "neutral-product" in result.stdout


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


def test_cli_reads_the_declared_pins_out_of_the_manifest(project):
    """A manifest that DECLARES the referent gets the descendant reading; the
    same manifest without the declaration does not."""
    manifest = project / "project.yaml"
    text = manifest.read_text().replace(
        "repository: testorg/Atlas\n    path: \".\"",
        "repository: testorg/MedxChart\n    path: \".\"")
    manifest.write_text(text)
    without = run_script(VALIDATOR, "--project", str(manifest))
    assert "MedxChart                        project-leg/assembly" in without.stdout

    manifest.write_text(text.replace("neutral_product_pins: []",
                                     "neutral_product_pins:\n  - openChart"))
    with_pin = run_script(VALIDATOR, "--project", str(manifest))
    assert "MedxChart                        domain-descendant" in with_pin.stdout


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


# --- the ruling: a DESCENDANT MAY CARRY LEGS -------------------------------

def test_a_declared_descendant_answers_as_the_assembly_root(policy):
    """THE MedxGlass CASE (2026-09-02). Descent and the three-repository shape
    are independent facts, so a name may hold both at once."""
    found = policy.classify("MedxGlass", "assembly", {"openGlass"})
    assert found == ("domain-descendant", "assembly")
    assert found.also_matches == ("project-leg/assembly",)
    assert "a descendant may carry legs" in found.reason
    assert accepts_role(found, "assembly")


def test_a_descendant_root_with_no_declared_role_is_unchanged(policy):
    """The role is the one the project DECLARES; asked without one, the answer
    is the same 2-tuple every existing caller already compares against."""
    found = policy.classify("MedxGlass", declared_pins={"openGlass"})
    assert found == ("domain-descendant", None)


def test_the_legs_of_a_descendant_root_are_ordinary_project_legs(policy):
    """`MedxGlass-spec` carries the lowercase suffix, so it does not even
    match the descendant pattern: it descends from nothing and says so."""
    for role in ("spec", "code"):
        found = policy.classify(f"MedxGlass-{role}", role, {"openGlass"})
        assert found == ("project-leg", role)
        assert found.also_matches == ()


def test_a_descendant_is_not_admitted_into_a_spec_or_code_role(policy):
    """`admits_declared_role:` is data and lists `assembly` alone. A bare
    CamelCase name offered as the code leg is still the assembly form."""
    found = policy.classify("MedxGlass", "code", {"openGlass"})
    assert found == ("domain-descendant", None)
    assert not accepts_role(found, "code")


def test_the_policy_data_declares_which_role_a_descendant_may_answer_in(policy):
    family = _family(policy, "domain-descendant")
    assert family["admits_declared_role"] == ["assembly"]
    assert "roles" not in family, (
        "the descendant family must declare no roles of its own: "
        "`MedxGlass` and `MedxGlass-spec` are not the same form")
