# SPDX-License-Identifier: Apache-2.0
"""The naming policy classifies what it claims to, and refuses what it does not."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    NamingPolicy, Refusal, accepts_role, link_pins_from_trees,
)
from shape_materialize import naming_block  # noqa: E402

POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"
VALIDATOR = REPO / "scripts" / "validate-repository-naming.py"

#: Every family the policy declares. Read from the DATA rather than listed
#: here, so a family added to the contract cannot be added without the two
#: parametrized properties below being asserted about it.
FAMILY_IDS = [f["id"] for f in
              NamingPolicy.load(POLICY_PATH).families]


@pytest.fixture(scope="module")
def policy() -> NamingPolicy:
    return NamingPolicy.load(POLICY_PATH)


def _family(policy: NamingPolicy, family_id: str) -> dict:
    return next(f for f in policy.families if f["id"] == family_id)


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_family_examples_classify_to_their_own_family(policy, family_id):
    """Every example in the DATA classifies to the family that declares it.

    A family that `requires_referent` is given the referent its own data
    records for the example — which is the whole point of the 2026-09-02
    ruling: `MedxChart` is a descendant BECAUSE MedxChart pins `openChart`,
    not because of how it is spelled. A `declared_only` family is given the
    declaration, for the same reason: `InkRouter` is a family BECAUSE it
    carries `family.yaml`, not because of how it is spelled.
    """
    family = _family(policy, family_id)
    referents = family.get("example_referents") or {}
    chains = (family.get("referent") or {}).get("example_chains") or {}
    declared = family_id if family.get("declared_only") else None
    for example in family["examples"]:
        # An example declares EITHER the referent it pins directly or the
        # chain it reaches one through (2026-09-05). Both are read from the
        # data, so an example added to the contract without either fails here.
        chain = tuple(chains.get(example) or ())
        if example in referents:
            pins = {referents[example]}
        elif chain:
            pins = {chain[0]}
        else:
            pins = None
        found = policy.classify(example, declared_role=declared,
                                declared_pins=pins,
                                referent_chain=chain)
        assert found is not None, f"{example} classified as nothing"
        assert found[0] == family_id, f"{example} -> {found}, wanted {family_id}"


def test_every_descendant_example_declares_the_referent_it_needs(policy):
    """The data cannot claim a descendant it has no referent for.

    Since 2026-09-05 there are two ways to declare one — a direct pin or a
    recorded chain that ENDS at a referent — and an example must carry
    exactly one of them in the data.
    """
    family = _family(policy, "domain-descendant")
    assert family.get("requires_referent") is True
    referents = family["example_referents"]
    chains = family["referent"]["example_chains"]
    for example in family["examples"]:
        assert example in referents or example in chains, (
            f"{example} declares neither an example_referent nor a chain")
        if example in referents:
            assert referents[example] in policy.descendant_referents(example)
        if example in chains:
            assert chains[example][-1] in policy.descendant_referents(example), (
                f"{example}'s chain must END at a referent it could have")


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
    """No pin can move the FORM: `open` in front says what it is, so a name
    offered as the assembly root is still classified as a neutral product.

    Since 2026-09-05 that root ALSO carries the `assembly` role it declares
    (below), which is an addition to the answer and not a change to it — the
    family is `neutral-product` in every one of these readings, and the
    project-leg form it also satisfies stays in `also_matches`.
    """
    for pins in (None, {"openScribe"}, {"openxScribe"}):
        found = policy.classify("openScribe", declared_role="assembly",
                                declared_pins=pins)
        assert found.family == "neutral-product"
        assert found.also_matches == ("project-leg/assembly",)
        assert policy.classify("openScribe", declared_pins=pins) \
            == ("neutral-product", None)


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


@pytest.mark.parametrize("family_id", FAMILY_IDS)
def test_counter_examples_do_not_match_their_family(policy, family_id):
    """A counter-example says 'not THIS family'.

    Several still land in the residual assembly-root class — `MedChart` is a
    perfectly good project name — and that is the honest reading rather than a
    gap. What must never happen is a counter-example satisfying the pattern it
    is filed against.
    """
    family = _family(policy, family_id)
    declared = family_id if family.get("declared_only") else None
    for name in family.get("counter_examples") or []:
        hits = [m for m in policy.matches(name, declared) if m[0] == family_id]
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


def test_cli_role_does_not_override_a_neutral_product_form():
    """`--role assembly` is a declaration, not an override. It ADDS the role
    the form admits (2026-09-05); it never turns the form into a leg."""
    result = run_script(VALIDATOR, "--role", "assembly", "openScribe")
    assert result.returncode == 0
    assert "neutral-product/assembly" in result.stdout
    assert "project-leg/assembly" in result.stdout, (
        "the leg form it also satisfies belongs in also_matches, not lost")


def test_cli_role_spec_does_not_move_a_neutral_product_at_all():
    """The admission is `assembly` alone, so a role the name cannot spell
    leaves the answer exactly where it was before the ruling."""
    result = run_script(VALIDATOR, "--role", "spec", "openScribe")
    assert result.returncode == 0
    # The leg form it also satisfies still gets RECORDED, even though `spec`
    # is not a role this family admits — the refusal is of the role, not of
    # the overlap.
    assert "also_matches project-leg/assembly" in result.stdout
    assert "neutral-product/assembly" not in result.stdout


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


# --- the ruling: a FAMILY is a holder, and the form is declared-only -------

def test_a_family_name_is_the_holder_form_when_it_is_declared(policy):
    """THE INKROUTER CASE (2026-09-04). `InkRouter` holds IRRS and IRSS; it is
    spelled exactly like an assembly root, and `family.yaml` is what tells
    them apart — so the form answers only when it is asked for."""
    found = policy.classify("InkRouter", declared_role="family")
    assert found == ("family", None)
    assert found.also_matches == ("project-leg/assembly",)
    assert "DECLARED" in found.reason


def test_the_same_name_undeclared_is_an_ordinary_assembly_root(policy):
    found = policy.classify("InkRouter")
    assert found == ("project-leg", "assembly")
    assert found.also_matches == (), (
        "a declared-only form must not widen `also_matches`: "
        "`validate-manifest.py` compares that list exactly, and every "
        "manifest already in the wild records it")


def test_the_family_form_is_declared_only_in_the_data(policy):
    family = _family(policy, "family")
    assert family["declared_only"] is True
    assert family["precedence"] > _family(policy, "project-leg")["precedence"], (
        "the holder form sits BELOW the leg forms: a bare CamelCase token is "
        "an assembly root unless something says otherwise")
    assert policy.declared_only("family")
    assert not policy.declared_only("project-leg")


def test_a_hyphenated_name_is_not_a_family_even_when_declared(policy):
    assert policy.classify("Ink-Router", declared_role="family") is None
    found = policy.classify("InkRouter-spec", declared_role="family")
    assert found == ("project-leg", "spec")


def test_a_neutral_product_declared_as_a_family_is_still_a_neutral_product(policy):
    """Unambiguous by construction still wins: `open` in front says what it
    is, and a declaration cannot make it a holder."""
    assert policy.classify("openChart", declared_role="family") \
        == ("neutral-product", None)


def test_cli_role_family_names_the_holder_form():
    result = run_script(VALIDATOR, "--explain", "--role", "family", "InkRouter")
    assert result.returncode == 0, result.stderr
    assert "InkRouter: family" in result.stdout
    assert "DECLARED-ONLY" in result.stdout
    assert "family.yaml" in result.stdout


def test_cli_without_the_role_reports_the_assembly_form():
    result = run_script(VALIDATOR, "InkRouter")
    assert result.returncode == 0
    assert "project-leg/assembly" in result.stdout
    assert "also_matches" not in result.stdout


# --- the ruling: the referent may be reached through a CHAIN of pins --------
#
# Brett Heap, 2026-09-05: "elect the shape for both, follow the pin chain, no
# family yet" (opensoft/openxFactory#656). `codexDox` pins `openXdox` and
# `openXdox` pins `openDox`, so the referent is REACHED rather than pinned.
# Every test below states its facts as a manifest would: the pins the project
# declares, the chain it records, and what the links' own trees say — and
# nothing here reads a network, because nothing may.

def link(**declarations) -> dict:
    """`{link name: the pins ITS manifest declares}` — the readable links."""
    return {name: set(pins) for name, pins in declarations.items()}


def test_a_direct_pin_still_answers_alone(policy):
    """2026-09-02 is untouched: a name that classified as a descendant on the
    direct pin classifies the same way, and says so the same way."""
    found = policy.classify("MedxChart", declared_pins={"openChart"})
    assert found == ("domain-descendant", None)
    assert found.referent.status == "direct"
    assert found.referent.chain == ()
    assert "declared pin on openChart" in found.reason


def test_a_two_link_chain_reaches_the_referent(policy):
    """THE codexDox CASE, with `openXdox`'s own tree readable: every link is
    VERIFIED against the declaration that link's manifest carries."""
    found = policy.classify("codexDox", "assembly", {"openXdox"},
                            ["openXdox", "openDox"],
                            link(openXdox={"openDox"}))
    assert found == ("domain-descendant", "assembly")
    assert found.referent.status == "verified"
    assert found.referent.referent == "openDox"
    assert found.referent.chain == ("openXdox", "openDox")
    assert found.referent.warnings == ()
    assert "openXdox → openDox" in found.reason
    assert accepts_role(found, "assembly")


def test_an_unreadable_link_is_declared_unverified_and_still_classifies(policy):
    """The offline half of the ruling. `openXdox` is not checked out here, so
    its declaration cannot be READ — and the chain codexDox RECORDS is still
    the fact this classifier was given, so the answer does not change."""
    found = policy.classify("codexDox", "assembly", {"openXdox"},
                            ["openXdox", "openDox"])
    assert found == ("domain-descendant", "assembly")
    assert found.referent.status == "declared-unverified"
    assert found.referent.unverified == ("openXdox",)
    assert len(found.referent.warnings) == 1
    assert "declared-unverified" in found.referent.warnings[0]
    assert "SHAPE_PIN_SOURCE_OPENXDOX" in found.referent.warnings[0], (
        "a warning that does not name what would ANSWER it is a warning the "
        "reader can do nothing with")


def test_a_link_that_declares_something_else_breaks_the_chain(policy):
    """A link whose tree IS readable and says otherwise is the one case that
    fails: the record claims a declaration the other tree does not carry."""
    found = policy.classify("MedxScribe", "assembly", {"openInk"},
                            ["openInk", "openScribe"],
                            link(openInk={"openQuill"}))
    assert found == ("project-leg", "assembly")
    assert found.also_matches == ("domain-descendant",)
    assert found.referent.status == "broken"
    assert "openInk declares openQuill, not openScribe" in found.reason, (
        "the message must NAME the link that broke; 'the chain is invalid' "
        "sends the reader to read four manifests")


def test_a_chain_that_does_not_begin_at_a_declared_pin_is_broken(policy):
    """The first entry is the pin this project actually holds, so a chain
    that starts anywhere else is a claim about somebody else's tree."""
    found = policy.classify("MedxScribe", "assembly", {"openInk"},
                            ["openQuill", "openScribe"])
    assert found == ("project-leg", "assembly")
    assert found.referent.status == "broken"
    assert "begins at openQuill" in found.reason
    assert "neutral_product_pins" in found.reason


def test_a_chain_that_does_not_end_at_the_referent_is_broken(policy):
    found = policy.classify("MedxScribe", "assembly", {"openInk"},
                            ["openInk", "openLedger"])
    assert found == ("project-leg", "assembly")
    assert found.referent.status == "broken"
    assert "ends at openLedger" in found.reason
    assert "openScribe" in found.reason


def test_a_chain_that_repeats_a_link_is_a_cycle(policy):
    found = policy.classify("MedxScribe", "assembly", {"openInk"},
                            ["openInk", "openInk", "openScribe"])
    assert found[0] == "project-leg"
    assert "cycle" in found.reason


def test_a_chain_longer_than_the_policy_admits_is_broken(policy):
    """The bound is DATA (`referent.chain.max_length`), like every other rule
    here, so a fork can widen it without editing a validator."""
    limit = policy.chain_rule()["max_length"]
    chain = ["openInk"] + [f"openLink{n}" for n in range(limit)] + ["openScribe"]
    found = policy.classify("MedxScribe", "assembly", {"openInk"}, chain)
    assert found[0] == "project-leg"
    assert f"at most {limit}" in found.reason


def test_a_broken_chain_never_takes_away_the_direct_pin(policy):
    """"A direct pin stays sufficient; the chain is an ADDITION." A record to
    repair is a WARNING beside an answer, not the loss of the answer."""
    found = policy.classify("MedxChart", "assembly", {"openChart"},
                            ["openChart", "openLedger"])
    assert found == ("domain-descendant", "assembly")
    assert found.referent.status == "direct"
    assert any("is broken" in warning for warning in found.referent.warnings)


def test_the_second_worked_case_is_ledgerxwallet(policy):
    """`LedgerxWallet -> openXwallet -> openWallet`, the same shape the split
    product has — and `openWallet` need not exist anywhere for this to be the
    right answer, which is what "the check stays offline" means."""
    found = policy.classify("LedgerxWallet", "assembly", {"openXwallet"},
                            ["openXwallet", "openWallet"],
                            link(openXwallet={"openWallet"}))
    assert found == ("domain-descendant", "assembly")
    assert found.referent.status == "verified"
    assert found.referent.referent == "openWallet"


def test_a_name_that_is_not_a_claim_at_all_ignores_a_chain(policy):
    """`Atlas` claims descent from nothing, so there is nothing to reach."""
    found = policy.classify("Atlas", "assembly", {"openInk"},
                            ["openInk", "openAtlas"])
    assert found == ("project-leg", "assembly")
    assert found.referent.status == "none"


def test_the_chain_rule_is_data(policy):
    """Every knob the classifier reads is declared in the contract file, so a
    fork reads the rule rather than the implementation."""
    rule = policy.chain_rule()
    assert rule["record_field"] == "naming.referent_chain"
    assert rule["link_declared_by"] == "neutral_product_pins"
    assert rule["unverified_status"] == "declared-unverified"
    assert isinstance(rule["max_length"], int)


def test_every_example_chain_in_the_data_holds(policy):
    """The worked cases are testable FROM THE CONTRACT, not from memory."""
    chains = _family(policy, "domain-descendant")["referent"]["example_chains"]
    for name, chain in chains.items():
        found = policy.classify(name, "assembly", {chain[0]}, chain,
                                {holder: {held} for holder, held
                                 in zip(chain, chain[1:])})
        assert found[0] == "domain-descendant", f"{name} -> {found}"
        assert found.referent.status == "verified"


# --- reading a link's own declaration, from whatever tree is on the disk ----

def _tree(path: Path, *pins: str) -> Path:
    """A stand-in for a link's checkout: a manifest and its declaration."""
    path.mkdir(parents=True, exist_ok=True)
    body = "".join(f"  - {pin}\n" for pin in pins) or " []\n"
    (path / "project.yaml").write_text(
        "schema_version: 1\nkind: project-manifest\n"
        "neutral_product_pins:" + ("\n" + body if pins else body),
        encoding="utf-8")
    return path


def test_a_link_is_read_from_a_checkout_beside_the_project(tmp_path):
    """The ordinary workspace: the project and the products it pins, cloned
    side by side. Same lookup order `validate-pins.py` already uses."""
    _tree(tmp_path / "openXdox", "openDox")
    found = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox")
    assert found == {"openxdox": {"openDox"}}


def test_a_link_source_names_the_tree_explicitly(tmp_path):
    _tree(tmp_path / "elsewhere", "openDox")
    found = link_pins_from_trees(
        ("openXdox",), root=None,
        keyed_sources={"openxdox": tmp_path / "elsewhere"})
    assert found == {"openxdox": {"openDox"}}


def test_a_tree_with_no_manifest_answers_nothing(tmp_path):
    """Absent is UNVERIFIED, not empty: a directory that is not a project of
    this shape has not said that it declares no pins."""
    (tmp_path / "openXdox").mkdir()
    assert link_pins_from_trees(("openXdox",), root=tmp_path / "codexDox") == {}


def test_a_tree_that_declares_nothing_answers_the_empty_set(tmp_path):
    """And an EMPTY declaration is an answer, which is why it breaks a chain
    running through it rather than leaving it unverified."""
    _tree(tmp_path / "openXdox")
    assert link_pins_from_trees(("openXdox",),
                                root=tmp_path / "codexDox") == {"openxdox": set()}


# --- the CLI ---------------------------------------------------------------

def test_cli_explain_names_the_chain_as_well_as_the_direct_pin():
    """THE DEFECT THE RULING NAMES. `--explain codexDox` said only *needs a
    declared pin on openDox or openxDox* — neither of which this family holds,
    nor intends to — so the message sent the reader to declare a pin the
    ruling forbids. It now names BOTH ways a referent may be reached."""
    result = run_script(VALIDATOR, "--explain", "codexDox")
    assert result.returncode == 0, result.stderr
    assert "a CLAIM: needs a declared pin on openDox or openxDox" in result.stdout
    assert ("or a declared chain (`naming.referent_chain`) of pins ending in "
            "one of them") in result.stdout


def test_cli_classifies_a_chain_given_on_the_command_line(tmp_path):
    """The one-off form of the manifest question, with the link's tree named
    so the link is VERIFIED rather than merely declared."""
    _tree(tmp_path / "openXdox", "openDox")
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                        "--referent-chain", "openXdox,openDox",
                        "--link-source", f"openXdox={tmp_path / 'openXdox'}",
                        "--explain", "codexDox")
    assert result.returncode == 0, result.stderr
    assert "codexDox: domain-descendant / assembly" in result.stdout
    assert "CHAIN openXdox → openDox   [verified]" in result.stdout
    assert "WARNING" not in result.stdout


def test_cli_reports_an_unread_link_as_a_warning_and_still_classifies():
    """Offline is the ordinary case, so it is a WARNING and exit 0."""
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                        "--referent-chain", "openXdox,openDox", "codexDox")
    assert result.returncode == 0, result.stderr
    assert "domain-descendant/assembly" in result.stdout
    assert "WARNING codexDox: declared-unverified" in result.stderr


def test_cli_reports_a_broken_link_as_a_finding_naming_it(tmp_path):
    _tree(tmp_path / "openInk", "openQuill")
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openInk",
                        "--referent-chain", "openInk,openScribe",
                        "--link-source", f"openInk={tmp_path / 'openInk'}",
                        "--explain", "MedxScribe")
    assert result.returncode == 0, "a name given on the command line is not a "\
        "manifest; the reading is reported, and the manifest gate is where a "\
        "recorded chain becomes a finding"
    assert "MedxScribe: project-leg / assembly" in result.stdout
    assert "openInk declares openQuill, not openScribe" in result.stdout


def test_cli_reads_the_chain_out_of_a_project_manifest(project, tmp_path):
    """What a scaffolded project's own gate runs: the chain is READ from
    `naming.referent_chain:`, and the link beside the root verifies it."""
    manifest = project / "project.yaml"
    text = manifest.read_text().replace(
        "repository: testorg/Atlas\n    path: \".\"",
        "repository: testorg/codexDox\n    path: \".\"")
    text = text.replace("neutral_product_pins: []",
                        "neutral_product_pins:\n  - openXdox")
    text = text.replace(
        "      form: project-leg\n      role: assembly\n"
        "      also_matches: []",
        "      form: domain-descendant\n      role: assembly\n"
        "      also_matches: [project-leg/assembly]\n"
        "      descendant_referent: openDox\n"
        "      referent_declared: true\n"
        "      referent_chain: [openXdox, openDox]")
    manifest.write_text(text)
    _tree(project.parent / "openXdox", "openDox")
    result = run_script(VALIDATOR, "--project", str(manifest))
    assert result.returncode == 0, result.stderr
    assert "codexDox                         domain-descendant" in result.stdout
    assert "WARNING" not in result.stderr


def test_cli_finds_a_recorded_chain_that_does_not_hold(project, tmp_path):
    """A RECORDED chain that the link's own tree contradicts is drift in the
    record, and the finding names the link."""
    manifest = project / "project.yaml"
    text = manifest.read_text().replace(
        "repository: testorg/Atlas\n    path: \".\"",
        "repository: testorg/codexDox\n    path: \".\"")
    text = text.replace("neutral_product_pins: []",
                        "neutral_product_pins:\n  - openInk")
    text = text.replace("      also_matches: []",
                        "      also_matches: [domain-descendant]\n"
                        "      referent_chain: [openInk, openDox]")
    manifest.write_text(text)
    _tree(project.parent / "openInk", "openQuill")
    result = run_script(VALIDATOR, "--project", str(manifest))
    assert result.returncode == 1
    assert "openInk declares openQuill, not openDox" in result.stderr


# --- the ruling: a NEUTRAL PRODUCT MAY ELECT THE SHAPE ---------------------
#
# Brett Heap, 2026-09-05, on opensoft/openxFactory#656, verbatim: "elect the
# shape for both, follow the pin chain, no family yet". The chain is the half
# tested above; this is the other half. `both` is `openDox` and `openXdox`,
# each becoming an assembly root that carries `-spec` and `-code`.

def test_a_neutral_product_answers_as_its_own_assembly_root(policy):
    """THE openDox CASE. Being a neutral product and being a three-repository
    project are INDEPENDENT facts, so a name may hold both at once — the same
    reasoning that let a declared descendant carry legs on 2026-09-02."""
    found = policy.classify("openDox", "assembly")
    assert found == ("neutral-product", "assembly")
    assert found.also_matches == ("project-leg/assembly",)
    assert "may elect the shape" in found.reason
    assert "Brett Heap, 2026-09-05" in found.reason
    assert accepts_role(found, "assembly")


def test_the_form_still_wins_so_the_overlap_is_recorded_not_resolved(policy):
    """What is CONSUMED is `(neutral-product, None)`, which is why the leg form
    survives in `also_matches`. An overlap computed and then discarded is the
    defect this change fixes, not the fix."""
    found = policy.classify("openDox", "assembly")
    assert found.family == "neutral-product", (
        "the declaration adds a role; it does not override the form")
    assert "project-leg/assembly" in found.also_matches
    assert "neutral-product" not in found.also_matches, (
        "the family a name was classified INTO must not be listed among the "
        "forms it was not")


def test_a_neutral_product_with_no_declared_role_is_unchanged(policy):
    """Nothing about a name that declares nothing moved on 2026-09-05: the
    2-tuple every existing caller compares against is the one it always was."""
    found = policy.classify("openDox")
    assert found == ("neutral-product", None)
    assert found.also_matches == ("project-leg/assembly",)
    assert not accepts_role(found, "assembly")


def test_a_neutral_product_is_not_admitted_into_a_spec_or_code_role(policy):
    """`admits_declared_role:` is data and lists `assembly` alone, for the same
    reason it does in the descendant family: `openDox-spec` carries the
    lowercase suffix and is an ordinary project leg."""
    for role in ("spec", "code"):
        found = policy.classify("openDox", role)
        assert found == ("neutral-product", None)
        assert not accepts_role(found, role)


def test_the_legs_of_a_neutral_product_root_are_ordinary_project_legs(policy):
    for role in ("spec", "code"):
        found = policy.classify(f"openDox-{role}", role)
        assert found == ("project-leg", role)
        assert found.also_matches == ()


def test_a_neutral_product_leg_offered_as_the_root_is_still_refused(policy):
    """The refusal that must survive: a declared role wins only where the NAME
    satisfies it, and `openDox-spec` satisfies the spec form alone."""
    found = policy.classify("openDox-spec", "assembly")
    assert found == ("project-leg", "spec")
    assert not accepts_role(found, "assembly")


@pytest.mark.parametrize("name", ["Widget-Install", "xFactory-Hermes-Install"])
def test_an_install_is_admitted_into_no_role_at_all(policy, name):
    """`<X>-Install` carries a hyphen, so it satisfies no `project-leg` form to
    be admitted into. The data says so too, by declaring no admission."""
    found = policy.classify(name, "assembly")
    assert found == ("install", None)
    assert not accepts_role(found, "assembly")
    assert "admits_declared_role" not in _family(policy, "install")


def test_the_policy_data_declares_which_role_a_neutral_product_may_answer_in(policy):
    family = _family(policy, "neutral-product")
    assert family["admits_declared_role"] == ["assembly"]
    assert "roles" not in family, (
        "the neutral-product family must declare no roles of its own: "
        "`openDox` and `openDox-spec` are not the same form")


def test_the_second_elected_product_is_openxdox(policy):
    """The other half of "both". `openXdox` is a neutral product in its own
    right and a root in its own right."""
    found = policy.classify("openXdox", "assembly")
    assert found == ("neutral-product", "assembly")
    assert found.also_matches == ("project-leg/assembly",)
    assert accepts_role(found, "assembly")


def test_a_neutral_product_that_also_claims_descent_records_both_overlaps(policy):
    """`openXwallet` is the worked second case, and `openxFactory` is the one
    neutral product that ALSO matches the descendant form: electing the shape
    must not swallow either overlap."""
    wallet = policy.classify("openXwallet", "assembly")
    assert wallet == ("neutral-product", "assembly")
    assert wallet.also_matches == ("project-leg/assembly",)
    factory = policy.classify("openxFactory", "assembly")
    assert factory == ("neutral-product", "assembly")
    assert factory.also_matches == ("domain-descendant",
                                    "project-leg/assembly")


def test_the_naming_block_records_the_spelling_overlap_by_form_not_family(
        policy):
    """`naming_block()` records `descendant_referent:` and
    `referent_declared:` by the NAME'S form, not by the family that won —
    `openxFactory` elects the shape and classifies as `neutral-product`, and
    still shows the descent claim its spelling also makes, undeclared until a
    pin on `openFactory` is added."""
    block = naming_block(policy, "openxFactory", "assembly", set())
    assert "form: neutral-product" in block
    assert "role: assembly" in block
    assert "also_matches: [domain-descendant, project-leg/assembly]" in block
    assert "descendant_referent: openFactory" in block
    assert "referent_declared: false" in block

    pinned = naming_block(policy, "openxFactory", "assembly", {"openFactory"})
    assert "form: neutral-product" in pinned, (
        "a pin on the referent does not turn the elected form into a "
        "descendant: electing the shape and reaching a referent are "
        "different facts")
    assert "referent_declared: true" in pinned


def test_a_declared_descendant_root_is_untouched_by_the_new_rule(policy):
    """The 2026-09-02 answer is unchanged, pin chain and all: this ruling ADDS
    a form that may be a root and takes nothing away from the ones that were."""
    found = policy.classify("MedxGlass", "assembly", {"openGlass"})
    assert found == ("domain-descendant", "assembly")
    assert found.also_matches == ("project-leg/assembly",)
    assert found.referent.status == "direct"
    assert accepts_role(found, "assembly")


def test_cli_explain_names_the_admission():
    """A reader who sees `neutral-product / assembly` and no explanation has to
    read the classifier to learn that the form won and the role was added."""
    result = run_script(VALIDATOR, "--explain", "--role", "assembly", "openDox")
    assert result.returncode == 0, result.stderr
    assert "openDox: neutral-product / assembly" in result.stdout
    assert "ADMITS a declared role of assembly" in result.stdout
    assert "may elect the shape (Brett Heap, 2026-09-05)" in result.stdout
    assert "also_matches: project-leg/assembly" in result.stdout


def test_cli_explain_without_a_role_is_the_answer_it_always_was():
    result = run_script(VALIDATOR, "--explain", "openDox")
    assert result.returncode == 0, result.stderr
    header = next(line for line in result.stdout.splitlines()
                 if line.strip().startswith("openDox:"))
    # Asserted on the HEADER line, not the whole transcript: `/ assembly`
    # legitimately appears further down, in the `admits_declared_role:`
    # explanation prose, so a blanket `not in result.stdout` would break the
    # day that prose is reworded rather than the day the classification does.
    assert header.strip() == "openDox: neutral-product"
    assert not header.strip().endswith("/ assembly")
    assert "ADMITTED" not in result.stdout
