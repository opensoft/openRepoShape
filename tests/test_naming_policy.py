# SPDX-License-Identifier: Apache-2.0
"""The naming policy classifies what it claims to, and refuses what it does not."""

from __future__ import annotations

import errno
import os
import string
import sys
from pathlib import Path

import pytest

from conftest import (
    REPO, SCAFFOLD, blank_unnamed_pin_sources, clear_ambient_pin_sources, git,
    run_script,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    PROJECT_ID_RE, SAFE_ARG_RE, UNAMBIGUOUS_FORMS, LinkPins, NamingPolicy,
    Refusal, accepts_role, link_manifest_lookup, link_pins_from_trees,
    parse_yaml,
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


#: What a `--project` or a `--family` can hold past `checked_value`
#: (`SAFE_ARG_RE`) that no id takes once lowercased (`PROJECT_ID_RE`): the
#: characters an id derived from the name is refused for.
NO_ID_CHARACTERS = (".", "_", "/", "@", "+", "~")


def test_those_are_the_characters_the_two_patterns_disagree_on():
    """`NO_ID_CHARACTERS` is every character the two patterns disagree on,
    so one either of them gains or loses is asked about below."""
    between = sorted(c for c in string.printable
                     if SAFE_ARG_RE.fullmatch(f"a{c}b")
                     and not PROJECT_ID_RE.match(f"a{c}b".lower()))
    assert between == sorted(NO_ID_CHARACTERS)


@pytest.mark.parametrize("character", NO_ID_CHARACTERS)
def test_no_root_or_family_name_holds_a_character_no_id_takes(policy,
                                                              character):
    """#658 and #659 tell a derived id refused for one of these characters
    to change `--project` or `--family` to one CamelCase token, never to
    pass an `--id`, and, in place, that the source cannot be adopted under
    that name. That holds while the policy classifies no such name as an
    assembly root or a family holder."""
    name = f"North{character}Wind"
    assert policy.classify(name, "assembly", set()) is None, name
    assert policy.classify(name, "family") is None, name


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
#
# EVERY TEST BELOW CALLS `link_pins_from_trees` DIRECTLY, IN THIS PROCESS —
# no `run_script`, no subprocess (Copilot, PR #128, on `blank_unnamed_pin_
# sources`'s own tests/conftest.py doc: "the direct link_pins_from_trees
# tests... still call resolve_link_source, which reads os.environ
# directly"). `blank_unnamed_pin_sources` only sanitises the environment a
# SPAWNED CHILD sees; it does nothing for `resolve_link_source`'s rule 2
# reading THIS process's own `os.environ`, which is exactly what these
# tests do. An exported `SHAPE_PIN_SOURCE_OPENXDOX` pointing at a real
# manifest — `~/projects/openXdox` on this workstation, again — would let
# rule 2 answer before rule 3 (the sibling `tmp_path` tree each test below
# actually builds) is ever tried, exactly the class of exposure #126
# closed for a spawned child but not for a direct call. `clear_ambient_
# pin_sources` (`tests/conftest.py`) clears every SHAPE_PIN_SOURCE_* name,
# not only `openXdox`: `link_pins_from_trees(("openXdox", "openDox"), ...)`
# below resolves BOTH names it is given, so naming only the first one
# would still leave `SHAPE_PIN_SOURCE_OPENDOX` free to answer for the
# second (Copilot's second pass on the same PR). Every test below clears
# them all first.

def _tree(path: Path, *pins: str) -> Path:
    """A stand-in for a link's checkout: a manifest and its declaration."""
    path.mkdir(parents=True, exist_ok=True)
    body = "".join(f"  - {pin}\n" for pin in pins) or " []\n"
    (path / "project.yaml").write_text(
        "schema_version: 1\nkind: project-manifest\n"
        "neutral_product_pins:" + ("\n" + body if pins else body),
        encoding="utf-8")
    return path


def test_a_link_is_read_from_a_checkout_beside_the_project(tmp_path, monkeypatch):
    """The ordinary workspace: the project and the products it pins, cloned
    side by side. Same lookup order `validate-pins.py` already uses."""
    clear_ambient_pin_sources(monkeypatch)
    _tree(tmp_path / "openXdox", "openDox")
    found = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox")
    assert found == {"openxdox": {"openDox"}}


def test_a_link_source_names_the_tree_explicitly(tmp_path, monkeypatch):
    clear_ambient_pin_sources(monkeypatch)
    _tree(tmp_path / "elsewhere", "openDox")
    found = link_pins_from_trees(
        ("openXdox",), root=None,
        keyed_sources={"openxdox": tmp_path / "elsewhere"})
    assert found == {"openxdox": {"openDox"}}


def test_a_tree_with_no_manifest_answers_nothing(tmp_path, monkeypatch):
    """Absent is UNVERIFIED, not empty: a directory that is not a project of
    this shape has not said that it declares no pins."""
    clear_ambient_pin_sources(monkeypatch)
    (tmp_path / "openXdox").mkdir()
    assert link_pins_from_trees(("openXdox",), root=tmp_path / "codexDox") == {}


def test_a_tree_that_declares_nothing_answers_the_empty_set(tmp_path, monkeypatch):
    """And an EMPTY declaration is an answer, which is why it breaks a chain
    running through it rather than leaving it unverified."""
    clear_ambient_pin_sources(monkeypatch)
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


def test_cli_reports_an_unread_link_as_a_warning_and_still_classifies(tmp_path):
    """Offline is the ordinary case, so it is a WARNING and exit 0.

    Run with `cwd` set to a directory under `tmp_path`, never the pytest
    process's own cwd: `resolve_link_source`'s rule 3
    (`scripts/repo_shape.py`) reads a checkout sitting BESIDE wherever the
    validator is run from, so a workstation that happens to have a real
    `openXdox` checkout beside whatever directory pytest was invoked from
    would satisfy that rule and the link would verify instead of staying
    unread — and the warning under test would never print. `tmp_path` is
    fresh and unique per test on every machine, so it has no such sibling
    to be found by accident.

    That leaves rule 2, which reads BEFORE rule 3: `SHAPE_PIN_SOURCE_OPENXDOX`
    in the environment. This test no longer overrides it itself (#114 fixed
    it locally that way; #120's own follow-up asked for the general form):
    `run_script` (`tests/conftest.py`) now blanks every `SHAPE_PIN_SOURCE_*`
    variable it would otherwise inherit from the calling process unless THIS
    call's own `env=` names it — the same mechanism PR #112 gave
    `LANES_LANE`, generalised for #114/#120 — so a developer shell or CI box
    that happens to export `SHAPE_PIN_SOURCE_OPENXDOX`, pointed at a tree
    that really does declare `openDox` (the same shape `~/projects/openXdox`
    has on Brett's workstation), never reaches the validator subprocess
    started below and cannot make the link verify by accident.
    `test_run_script_blanks_an_inherited_pin_source_unless_named` and
    `test_run_script_still_passes_a_pin_source_the_caller_names`, right
    below, prove that mechanism directly; this test only needs its own
    `cwd` isolation from rule 3.
    """
    workdir = tmp_path / "codexDox"
    workdir.mkdir()
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                        "--referent-chain", "openXdox,openDox", "codexDox",
                        cwd=workdir)
    assert result.returncode == 0, result.stderr
    assert "domain-descendant/assembly" in result.stdout
    assert "WARNING codexDox: declared-unverified" in result.stderr


def test_run_script_blanks_an_inherited_pin_source_unless_named(
        tmp_path, monkeypatch):
    """PROVES the general rule #120's follow-up asked for and
    `tests/conftest.py::run_script` now carries: an inherited
    `SHAPE_PIN_SOURCE_*` variable must not reach the child unless THIS
    CALL's own `env=` names it.

    Build a tree that WOULD verify the `openXdox` link (`_tree`, same
    helper every other test in this section uses), point the AMBIENT
    environment at it with `monkeypatch.setenv` — standing in for the
    developer shell or CI box PR #120's review comment described — and call
    the validator through `run_script` with no `env=` of its own. Without
    the blanking rule, rule 2 (`resolve_link_source`,
    `scripts/repo_shape.py`) would read that ambient variable before rule 3
    is ever reached, the link would verify, and the warning below would
    never print — exactly the finding Copilot made on PR #120 before
    `c30d9f4` fixed it for this one test only.
    """
    workdir = tmp_path / "codexDox"
    workdir.mkdir()
    _tree(tmp_path / "would-verify-if-not-blanked", "openDox")
    monkeypatch.setenv("SHAPE_PIN_SOURCE_OPENXDOX",
                       str(tmp_path / "would-verify-if-not-blanked"))
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                        "--referent-chain", "openXdox,openDox", "codexDox",
                        cwd=workdir)
    assert result.returncode == 0, result.stderr
    assert "domain-descendant/assembly" in result.stdout
    assert "WARNING codexDox: declared-unverified" in result.stderr


def test_run_script_still_passes_a_pin_source_the_caller_names(tmp_path):
    """The other half of the same rule: a caller that DOES name the
    variable in its own `env=` must still reach the child. The blanking
    rule stands in only for a caller that said nothing; it never overrides
    one that said something. Point `SHAPE_PIN_SOURCE_OPENXDOX` at a tree
    that verifies the link and expect a `[verified]` chain, mirroring
    `test_cli_classifies_a_chain_given_on_the_command_line` above but
    through rule 2 instead of `--link-source`.

    THE TREE SITS AT `elsewhere`, NOT AT THE SIBLING PATH `tmp_path /
    "openXdox"` rule 3 would also check: putting the verifying manifest
    there would let this test pass even if a broken blanking rule wiped the
    caller's own `env=` too, because rule 3 would find the very same tree
    by accident and the assertion would never notice. Naming it something
    else means only rule 2 — the env var this test actually names — can
    make the chain verify, which is what `test_a_link_source_names_the_tree_explicitly`
    above already does for the same reason, one rule earlier.
    """
    workdir = tmp_path / "codexDox"
    workdir.mkdir()
    _tree(tmp_path / "elsewhere", "openDox")
    result = run_script(VALIDATOR, "--role", "assembly", "--pins", "openXdox",
                        "--referent-chain", "openXdox,openDox",
                        "--explain", "codexDox", cwd=workdir,
                        env={"SHAPE_PIN_SOURCE_OPENXDOX":
                             str(tmp_path / "elsewhere")})
    assert result.returncode == 0, result.stderr
    assert "codexDox: domain-descendant / assembly" in result.stdout
    assert "CHAIN openXdox → openDox   [verified]" in result.stdout
    assert "WARNING" not in result.stdout


def test_blank_unnamed_pin_sources_folds_case_like_windows_does():
    """Copilot's finding on PR #128: Windows environment variable names are
    case-insensitive, so `blank_unnamed_pin_sources` (`tests/conftest.py`)
    must fold case for both "is this a pin-source name at all" and "did
    the caller ask for THIS one" — a real Windows child would treat
    `SHAPE_PIN_SOURCE_OPENXDOX` and any other-cased spelling of the same
    name as one variable, so a dict built with plain, case-sensitive
    Python comparisons cannot be allowed to disagree with it.

    Unit-level on the dict, not through `run_script` and a real
    subprocess like the two tests above: POSIX environment variables ARE
    case-sensitive, so a CLI-level test run on this suite's own ubuntu and
    macos legs could not observe a case-folding defect here at all — the
    child would simply never look up the differently-cased key, fix or no
    fix. Only a Windows child's OWN case-insensitive lookup makes the
    distinction this function has to get right observable, which a direct
    check of what the function returns proves without needing one."""
    # Not asked for, in ANY case: every spelling of the name is blanked,
    # exactly as an all-uppercase one already was before PR #128.
    assert blank_unnamed_pin_sources(
        {"SHAPE_PIN_SOURCE_OPENXDOX": "/real", "shape_pin_source_openink": "/real2"},
        {},
    ) == {"SHAPE_PIN_SOURCE_OPENXDOX": "", "shape_pin_source_openink": ""}
    # Asked for under the exact same spelling that is already in `env`
    # (the ordinary case, `env` already merged with `asked` the way
    # `run_script` merges them): kept, not blanked.
    assert blank_unnamed_pin_sources(
        {"SHAPE_PIN_SOURCE_OPENXDOX": "/named"},
        {"SHAPE_PIN_SOURCE_OPENXDOX": "/named"},
    ) == {"SHAPE_PIN_SOURCE_OPENXDOX": "/named"}
    # Asked for, but an INHERITED case-variant alias of that same name is
    # ALSO in `env` (as it would be after `{**os.environ, **asked}` merges
    # an ambient lower-case name with the caller's own upper-case one):
    # the alias is DROPPED, not merely left unblanked, so a real Windows
    # child — which would fold both to the one name it actually reads —
    # is never handed two disagreeing values for it.
    assert blank_unnamed_pin_sources(
        {"shape_pin_source_openxdox": "/ambient",
         "SHAPE_PIN_SOURCE_OPENXDOX": "/named"},
        {"SHAPE_PIN_SOURCE_OPENXDOX": "/named"},
    ) == {"SHAPE_PIN_SOURCE_OPENXDOX": "/named"}


def test_clear_ambient_pin_sources_folds_case_like_windows_does(monkeypatch):
    """Copilot's round-4 finding on PR #128: `clear_ambient_pin_sources`
    (`tests/conftest.py`) repeated `blank_unnamed_pin_sources`'s own
    round-1 case-sensitivity gap — its prefix check did not fold case
    before this fix, so an inherited `shape_pin_source_openxdox`
    (lower-case, as a real Windows child would still read
    case-insensitively) survived it.

    Hermetic, not through the four `link_pins_from_trees` tests above:
    those only fail when the MACHINE running them happens to carry a
    matching ambient variable, which this suite's own CI legs never do —
    so they cannot tell this fix from its absence either. Setting the
    ambient variable INSIDE the test with `monkeypatch.setenv`, the same
    way `test_run_script_blanks_an_inherited_pin_source_unless_named`
    above does for `blank_unnamed_pin_sources`, makes the fold provable
    regardless of what the machine running it actually exports."""
    monkeypatch.setenv("shape_pin_source_openxdox", "/ambient")
    clear_ambient_pin_sources(monkeypatch)
    assert "shape_pin_source_openxdox" not in os.environ


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


# --- what a --link-source value MEANS, and a source that cannot answer -----
#
# #338. `--link-source` is `[PRODUCT=]PATH`, and a path may hold an `=`.
# Splitting every value at its first `=` made `a=b/openXdox` a source keyed
# to a link `a` that no chain names: never asked, so the link stayed
# declared-unverified, exit 0, under a WARNING offering the `--link-source`
# the person had just passed. And the lookup asked `is_dir()`/`is_file()`,
# which before 3.14 raise every `OSError` but four, so a source that could
# not be entered, keyed, `SHAPE_PIN_SOURCE_<PRODUCT>` or beside the project,
# ended the naming gate in a traceback. Now the text before the first `=` is
# a link only when a chain here names it, as `validate-pins.py` reads
# `--pin-source` (#295); a source that cannot answer is a WARNING with the
# system's reason, never a traceback and never a finding; and a value no
# link used is a NOTE. Every run below is made from a directory of its own
# under `tmp_path`, so the only checkout beside it is one the test made.

CHAIN_ARGS = ("--role", "assembly", "--pins", "openXdox",
              "--referent-chain", "openXdox,openDox")

#: A mode denies nothing on Windows, where `chmod` has no search or read bit
#: to clear, and nothing to root. The same reason, and the same skip, as
#: `tests/test_neutral_pin_validator.py`'s `SEARCH_DENIED`; as a mark, it is
#: decided before the test body makes any path at all.
SEARCH_DENIED = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs a POSIX mode that denies access: Windows has no search or "
           "read bit for chmod to clear, and root is not stopped by one")

UNREADABLE = "WARNING link-source-unreadable: "


def naming_from(cwd: Path, *args, env=None):
    """The validator run from `cwd`, made here if it is not there yet."""
    cwd.mkdir(parents=True, exist_ok=True)
    return run_script(VALIDATOR, *args, cwd=cwd, env=env)


def test_a_bare_link_source_whose_path_holds_an_equals_sign_is_a_path(
        tmp_path):
    """THE DEFECT, its first half. The link tree is under a directory named
    `a=b`, passed BARE. The text before the `=` names no link of the chain,
    so the whole value is the path, and the link VERIFIES with nothing
    warned or noted. It used to be a source keyed to a link `<tmp>/a`, which
    no lookup asks for. `=` is a legal character in a path on all three
    platforms, so nothing here is skipped for spelling one."""
    tree = _tree(tmp_path / "a=b" / "openXdox", "openDox")
    result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--explain",
                         "--link-source", str(tree), "codexDox")
    assert result.returncode == 0, result.stderr
    assert "CHAIN openXdox → openDox   [verified]" in result.stdout
    assert "WARNING" not in result.stdout + result.stderr
    assert "NOTE" not in result.stderr


def test_a_link_named_before_the_equals_is_the_key_even_over_a_directory(
        tmp_path):
    """`openXdox=x/openXdox` where a directory `openXdox=x` holds the tree
    and `x/openXdox` does not exist. `openXdox` IS a link of the chain, so
    the keyed reading wins, decided by the chain and not by the disk, and
    the missing `x/openXdox` is named, with the other reading and how to ask
    for it. `./` asks for it, and the link verifies."""
    work = tmp_path / "work"
    _tree(work / "openXdox=x" / "openXdox", "openDox")
    keyed = naming_from(work, *CHAIN_ARGS, "--link-source",
                        "openXdox=x/openXdox", "codexDox")
    assert keyed.returncode == 0, keyed.stderr
    assert "Traceback" not in keyed.stderr
    assert "WARNING codexDox: declared-unverified" in keyed.stderr
    assert (f"{UNREADABLE}{Path('x', 'openXdox')} (--link-source "
            "openXdox=...) could not answer for openXdox: no such file or "
            "directory\n  `openXdox=x/openXdox` is also a directory; "
            "`--link-source ./openXdox=x/openXdox` reads it as one.\n"
            in keyed.stderr), keyed.stderr
    assert "NOTE" not in keyed.stderr, (
        "a source that was asked and could not answer is a WARNING, never "
        "also a NOTE")

    whole = naming_from(work, *CHAIN_ARGS, "--explain", "--link-source",
                        "./openXdox=x/openXdox", "codexDox")
    assert whole.returncode == 0, whole.stderr
    assert "CHAIN openXdox → openDox   [verified]" in whole.stdout
    assert "WARNING" not in whole.stdout + whole.stderr


def test_a_mistyped_link_name_alone_is_named_as_read(tmp_path):
    """THE ISSUE'S THIRD ROW: `openXdx=<tree>`, the only value. `openXdx`
    names no link, so the value is a PATH that is not there: the link stays
    declared-unverified, as it did, and the run now says which value was
    asked, that it could not answer, and how it was read."""
    tree = _tree(tmp_path / "trees" / "openXdox", "openDox")
    typo = f"openXdx={tree}"
    result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--link-source",
                         typo, "codexDox")
    assert result.returncode == 0, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert (f"{UNREADABLE}{Path(typo)} (--link-source) could not answer for "
            "openXdox: " in result.stderr), result.stderr
    assert ("\n  It was read as a PATH: `openXdx` is not a link of a "
            "referent chain here (links: openXdox, openDox).\n"
            in result.stderr), result.stderr
    # Those two and nothing else: the checkout beside the project that is
    # not there is the ordinary case, and is never said.
    assert result.stderr.count("WARNING ") == 2, result.stderr
    assert "NOTE" not in result.stderr


def test_a_link_source_no_link_used_is_a_note_and_changes_no_exit(tmp_path):
    """Each value no lookup asked is a NOTE on stderr, named as typed, with
    why, and the run still exits 0. The keyed value answers `openXdox`; the
    first bare one is replaced by a later bare one; and that later one is a
    MISTYPED key, read as a path because no chain names `openXdx`, beside a
    keyed source that had already answered — which used to say nothing at
    all."""
    tree = _tree(tmp_path / "trees" / "openXdox", "openDox")
    spare = tmp_path / "spare"
    spare.mkdir()
    work = tmp_path / "work"
    typo = f"openXdx={tree}"
    result = naming_from(work, *CHAIN_ARGS, "--link-source", str(spare),
                         "--link-source", f"openXdox={tree}",
                         "--link-source", typo, "codexDox")
    assert result.returncode == 0, result.stderr
    assert "WARNING" not in result.stderr
    assert (f"NOTE --link-source {spare}: not used — the later "
            f"`--link-source {typo}` replaced it.\n" in result.stderr)
    assert (f"NOTE --link-source {typo}: not used — each link whose own "
            "declaration is read had a more specific source (a keyed "
            "--link-source, SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout beside "
            "the project). It was read as a PATH: `openXdx` is not a link of "
            "a referent chain here (links: openXdox, openDox).\n"
            in result.stderr), result.stderr
    assert f"--link-source openXdox={tree}" not in result.stderr

    # The issue's own row: the mistyped key BEFORE a good bare source. The
    # good one is read; the typo is named, replaced, and read as a path.
    issue = naming_from(work, *CHAIN_ARGS, "--link-source", typo,
                        "--link-source", str(tree), "codexDox")
    assert issue.returncode == 0, issue.stderr
    assert "WARNING" not in issue.stderr
    assert (f"NOTE --link-source {typo}: not used — the later "
            f"`--link-source {tree}` replaced it. It was read as a PATH: "
            "`openXdx` is not a link" in issue.stderr), issue.stderr

    # A keyed value a later one for the same link replaced, in any case.
    replaced = naming_from(work, *CHAIN_ARGS, "--link-source",
                           f"openXdox={spare}", "--link-source",
                           f"OPENXDOX={tree}", "codexDox")
    assert replaced.returncode == 0, replaced.stderr
    assert "WARNING" not in replaced.stderr
    assert (f"NOTE --link-source openXdox={spare}: not used — the later "
            f"`--link-source OPENXDOX={tree}` replaced it.\n"
            in replaced.stderr), replaced.stderr

    # The same value given twice is one value: noted once, for its own
    # reason, and never as having replaced itself.
    twice = naming_from(work, *CHAIN_ARGS, "--link-source",
                        f"openXdox={tree}", "--link-source", str(spare),
                        "--link-source", str(spare), "codexDox")
    assert twice.returncode == 0, twice.stderr
    assert twice.stderr.count("NOTE ") == 1, twice.stderr
    assert "replaced it" not in twice.stderr

    # A value for the chain's END: its own declaration is never read, so a
    # source for it decided nothing, readable or not.
    end = naming_from(work, *CHAIN_ARGS, "--link-source", f"openXdox={tree}",
                      "--link-source", f"openDox={spare}", "codexDox")
    assert end.returncode == 0, end.stderr
    assert (f"NOTE --link-source openDox={spare}: not used — no name "
            "classified here reads openDox's own declaration.\n"
            in end.stderr), end.stderr

    # No name records a chain at all.
    none = naming_from(work, "--link-source", str(tree), "Atlas")
    assert none.returncode == 0, none.stderr
    assert (f"NOTE --link-source {tree}: not used — no name classified here "
            "records a referent chain.\n" in none.stderr), none.stderr

    # `--quiet`, the project's own `make bootstrap` and the doctor's
    # `naming` row: nothing is said, as no WARNING is.
    quiet = naming_from(work, *CHAIN_ARGS, "--quiet", "--link-source",
                        str(spare), "--link-source", typo, "codexDox")
    assert quiet.returncode == 0, quiet.stderr
    assert quiet.stderr == ""


@pytest.mark.parametrize("case", [
    pytest.param("keyed-parent-not-searchable", marks=SEARCH_DENIED),
    pytest.param("env-parent-not-searchable", marks=SEARCH_DENIED),
    pytest.param("sibling-not-searchable", marks=SEARCH_DENIED),
    "keyed-name-too-long",
])
def test_a_link_source_that_cannot_be_entered_or_named_is_a_warning(
        tmp_path, case):
    """THE DEFECT, its second half (#338). Each of these was a traceback on
    3.9 to 3.13, exit 1, and on 3.14 a declared-unverified WARNING offering
    the very source that had been given. Now each is the declared-unverified
    WARNING it is, and beside it the source, named with the system's own
    reason, on every Python; the exit is 0, because a link no source answers
    for is a warning in this validator, an explicit source included.

    The long name is RELATIVE, so the system has to refuse it by name. It
    runs everywhere: whatever Windows calls it, the line is asserted, and the
    reason is POSIX's `ENAMETOOLONG` only where that is the call."""
    work = tmp_path / "work"
    work.mkdir()
    locked, env, args = None, None, ()
    said = os.strerror(errno.EACCES)
    if case in ("keyed-parent-not-searchable", "env-parent-not-searchable"):
        source = _tree(tmp_path / "locked" / "openXdox", "openDox")
        locked = tmp_path / "locked"
        if case.startswith("keyed"):
            how, args = ("--link-source openXdox=...",
                         ("--link-source", f"openXdox={source}"))
        else:
            how = "$SHAPE_PIN_SOURCE_OPENXDOX"
            env = {"SHAPE_PIN_SOURCE_OPENXDOX": str(source)}
    elif case == "sibling-not-searchable":
        locked = _tree(tmp_path / "openXdox", "openDox")
        source = work.resolve().parent / "openXdox"
        how = f"sibling checkout ({source})"
        said = f"its project.yaml: {said}"
    else:
        source = Path("n" * 300)
        how, args = ("--link-source openXdox=...",
                     ("--link-source", f"openXdox={source}"))
        said = None if os.name == "nt" else os.strerror(errno.ENAMETOOLONG)
    if locked is not None:
        locked.chmod(0)
    try:
        result = run_script(VALIDATOR, *CHAIN_ARGS, *args, "codexDox",
                            cwd=work, env=env)
    finally:
        if locked is not None:
            locked.chmod(0o700)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "domain-descendant/assembly" in result.stdout
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert (f"{UNREADABLE}{source} ({how}) could not answer for openXdox: "
            in result.stderr), result.stderr
    if said is not None:
        assert f"could not answer for openXdox: {said}\n" in result.stderr
    assert "NOTE" not in result.stderr


@pytest.mark.parametrize("case", [
    pytest.param("not-readable", marks=SEARCH_DENIED),
    "not-utf-8",
    "not-a-mapping",
])
def test_a_link_manifest_that_cannot_be_read_is_named(tmp_path, case):
    """A source that HAS a `project.yaml` the link cannot be read from:
    named, with the reason, beside the declared-unverified WARNING it always
    was. It used to be that WARNING alone."""
    tree = tmp_path / "trees" / "openXdox"
    tree.mkdir(parents=True)
    manifest = tree / "project.yaml"
    if case == "not-utf-8":
        manifest.write_bytes(b"neutral_product_pins:\n  - open\xffDox\n")
        said = f"{manifest}: not UTF-8 at byte "
    elif case == "not-a-mapping":
        manifest.write_bytes(b"- openDox\n")
        said = f"{manifest}: not a mapping\n"
    else:
        manifest.write_bytes(b"neutral_product_pins:\n  - openDox\n")
        said = f"{manifest}: {os.strerror(errno.EACCES)}\n"
        manifest.chmod(0)
    try:
        result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--link-source",
                             f"openXdox={tree}", "codexDox")
    finally:
        manifest.chmod(0o600)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert (f"{UNREADABLE}{tree} (--link-source openXdox=...) could not "
            f"answer for openXdox: {said}" in result.stderr), result.stderr


@pytest.mark.parametrize("case", [
    "env-no-manifest",
    pytest.param("sibling-not-searchable", marks=SEARCH_DENIED),
])
def test_a_source_asked_only_for_the_chain_end_is_never_named(tmp_path,
                                                               case):
    """`openDox` ends the chain and its own declaration is never read, so a
    `SHAPE_PIN_SOURCE_OPENDOX` at a checkout with no manifest (a CI job may
    seed one for `validate-pins.py`'s digest), or an `../openDox` this user
    cannot enter, decides nothing and is not said. The second was a
    traceback before 3.14: the lookup asks for every link."""
    tree = _tree(tmp_path / "trees" / "openXdox", "openDox")
    work = tmp_path / "work"
    work.mkdir()
    env, locked = None, None
    if case == "env-no-manifest":
        plain = tmp_path / "plain"
        plain.mkdir()
        env = {"SHAPE_PIN_SOURCE_OPENDOX": str(plain)}
    else:
        locked = tmp_path / "openDox"
        locked.mkdir()
        locked.chmod(0)
    try:
        result = run_script(VALIDATOR, *CHAIN_ARGS, "--explain",
                            "--link-source", f"openXdox={tree}", "codexDox",
                            cwd=work, env=env)
    finally:
        if locked is not None:
            locked.chmod(0o700)
    assert result.returncode == 0, result.stderr
    assert "CHAIN openXdox → openDox   [verified]" in result.stdout
    assert "WARNING" not in result.stdout + result.stderr
    assert "NOTE" not in result.stderr


def _codexdox(project: Path) -> Path:
    """The scaffolded `Atlas` root's manifest, recast as `codexDox` pinning
    `openXdox` and RECORDING the chain `openXdox → openDox`, exactly as
    `test_cli_reads_the_chain_out_of_a_project_manifest` recasts it."""
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
    return manifest


def test_under_project_a_link_is_one_a_leg_records(project, tmp_path):
    """`--project` reads each leg's `naming.referent_chain:`, so its links
    are the names a value may be keyed to, with no `--referent-chain`: a
    bare tree under `a=b/` is a path, and verifies, where it used to be
    keyed to `<tmp>/a`; and `openXdox=<tree>` is keyed to the leg's link,
    and verifies, as it always did."""
    manifest = _codexdox(project)
    tree = _tree(tmp_path / "a=b" / "openXdox", "openDox")
    for value in (str(tree), f"openXdox={tree}"):
        result = run_script(VALIDATOR, "--project", str(manifest),
                            "--link-source", value, cwd=project)
        assert result.returncode == 0, result.stderr
        assert "codexDox                         domain-descendant" \
            in result.stdout
        assert result.stderr == "", value


@SEARCH_DENIED
def test_the_projects_own_gates_name_a_checkout_beside_it_they_cannot_enter(
        project):
    """`../openXdox` at mode 000 beside a project whose leg records the
    chain: the lookup every run of the project's gate makes. The naming step
    (`validate-repository-naming.py --project`, which `make validate`,
    `validate.yml` and `make bootstrap` run), its `--quiet` form (the naming
    step of `make bootstrap`, and the doctor's `naming` row) and
    `validate-manifest.py` (the same lookup, through `link_pins_from_trees`)
    each ended in a `PermissionError` traceback, exit 1, before 3.14. Each now
    exits 0 with the link declared-unverified, and the naming step names the
    checkout with the system's reason.

    WHAT THIS DOES NOT SAY is that those three TARGETS stop crashing on this
    row. They also run `validate-pins.py`, whose `resolve_neutral_pin_source`
    asks `(sibling / ".git").exists()` with no guard, so a sibling at mode 000
    still ends it in a `PermissionError` traceback before 3.14. That is a
    separate defect in a separate file, and not this change's."""
    manifest = _codexdox(project)
    sibling = _tree(project.parent / "openXdox", "openDox")
    sibling.chmod(0)
    try:
        gate = run_script(VALIDATOR, "--project", str(manifest), cwd=project)
        quiet = run_script(VALIDATOR, "--project", str(manifest), "--quiet",
                           cwd=project)
        own = run_script(project / "scripts" / "validate-manifest.py",
                         cwd=project)
    finally:
        sibling.chmod(0o700)
    assert gate.returncode == 0, gate.stderr
    assert "Traceback" not in gate.stderr, gate.stderr
    assert "WARNING codexDox: declared-unverified" in gate.stderr
    resolved = project.resolve().parent / "openXdox"
    assert (f"{UNREADABLE}{resolved} (sibling checkout ({resolved})) could "
            "not answer for openXdox: its project.yaml: "
            f"{os.strerror(errno.EACCES)}\n" in gate.stderr), gate.stderr
    assert quiet.returncode == 0, quiet.stderr
    assert quiet.stderr == ""
    assert "Traceback" not in own.stderr, own.stderr
    assert ("WARNING naming-referent-chain: leg 'assembly': "
            "declared-unverified" in own.stdout + own.stderr), (
        own.stdout + own.stderr)


@SEARCH_DENIED
def test_scaffold_reads_a_link_past_a_variable_it_cannot_enter(tmp_path):
    """`scaffold-project.py --referent-chain` reads each link through the
    same lookup, with `--pin-source` as the bare source. A
    `SHAPE_PIN_SOURCE_OPENXDOX` under a parent this user cannot enter was
    a `PermissionError` traceback at the plan, exit 1; it is now passed
    over, and `--pin-source` verifies the link. (A `--pin-source` that
    cannot be entered is #339, `pin_digest_from_source`, and not this.)"""
    source = tmp_path / "openXdox"
    source.mkdir()
    (source / "project.yaml").write_bytes(
        b"schema_version: 1\nkind: project-manifest\n"
        b"neutral_product_pins:\n  - openDox\n")
    git("init", "-q", "-b", "main", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-qm", "seed", cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    locked = tmp_path / "locked"
    _tree(locked / "openXdox", "openDox")
    locked.chmod(0)
    try:
        result = run_script(
            SCAFFOLD, "--org", "codexSoft", "--project", "codexDox",
            "--elected-by", "Test Human", "--elected-on", "2026-09-05",
            "--pin", f"openXdox@{commit}", "--pin-source", str(source),
            "--referent-chain", "openXdox,openDox", "--dry-run",
            "--local-remote-dir", str(tmp_path / "remotes"),
            env={"SHAPE_PIN_SOURCE_OPENXDOX": str(locked / "openXdox")})
    finally:
        locked.chmod(0o700)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert "declared-unverified" not in result.stderr + result.stdout
    assert "--dry-run: nothing was created." in result.stdout


@SEARCH_DENIED
def test_link_pins_from_trees_records_why_a_source_did_not_answer(
        tmp_path, monkeypatch):
    """The lookup itself, in this process: a checkout beside the project
    that cannot be entered is ABSENT from the answer, as one that is not
    there is, and never raises; `tried` says which sources were asked, in
    order, and why each did not answer."""
    clear_ambient_pin_sources(monkeypatch)
    locked = _tree(tmp_path / "openXdox", "openDox")
    elsewhere = tmp_path / "elsewhere"
    locked.chmod(0)
    tried: dict = {}
    try:
        found = link_pins_from_trees(
            ("openXdox", "openDox"), root=tmp_path / "codexDox",
            keyed_sources={"openxdox": elsewhere}, tried=tried)
    finally:
        locked.chmod(0o700)
    assert found == {}
    sibling = tmp_path.resolve() / "openXdox"
    assert tried["openXdox"] == [
        ("keyed", "--link-source openXdox=...", elsewhere,
         "no such file or directory"),
        ("sibling", f"sibling checkout ({sibling})", sibling,
         f"its project.yaml: {os.strerror(errno.EACCES)}"),
    ]
    assert [rule for rule, *_ in tried["openDox"]] == ["sibling"]


# --- fix round 1 on #338: pins that are not a list of names, the sources
# --- that were never exercised, and a chain nobody reads --------------------

#: The ways a link manifest's `neutral_product_pins:` is not a list of names.
#: Each is a tree that CANNOT ANSWER, never an answer: `5` ended the naming
#: gate in a `TypeError`, a scalar `openDox` was read as the characters `D`,
#: `e`, `n`, `o`, `p`, `x` (so the chain broke, and under `--project` that is
#: a FINDING), a mapping as its keys (so `openDox: yes` DECLARED `openDox`),
#: and a number among the names as its digits.
#:
#: The FALSY ones (fix round 2) are rows of their own, because each is a
#: change the first fix round made without a test: `0`, `false` and `''` were
#: read as an empty list, so a chain through the tree was BROKEN ("declares no
#: pin at all", and under `--project` a FINDING), and they are now a tree that
#: cannot answer. A `0`, `false` or `true` AMONG the names was dropped as a
#: blank, or read as the text `True`, so a chain through it VERIFIED, and it
#: is now unverified too. A blank entry (`null`, `''`) is still dropped, and
#: `test_a_link_manifest_with_an_absent_or_blank_pin_list_still_answers` holds
#: that side.
NOT_A_LIST_OF_NAMES = [
    pytest.param("neutral_product_pins: 5\n", "is not a list", id="number"),
    pytest.param("neutral_product_pins: openDox\n", "is not a list",
                 id="scalar-string"),
    pytest.param("neutral_product_pins:\n  openDox: yes\n", "is not a list",
                 id="mapping"),
    pytest.param("neutral_product_pins:\n  - openDox\n  - 5\n",
                 "holds an entry that is not text", id="list-with-a-number"),
    pytest.param("neutral_product_pins:\n  - openDox\n  - a: b\n",
                 "holds an entry that is not text", id="list-with-a-mapping"),
    pytest.param("neutral_product_pins: 0\n", "is not a list",
                 id="falsy-zero"),
    pytest.param("neutral_product_pins: false\n", "is not a list",
                 id="falsy-false"),
    pytest.param("neutral_product_pins: ''\n", "is not a list",
                 id="falsy-empty-string"),
    pytest.param("neutral_product_pins:\n  - openDox\n  - 0\n",
                 "holds an entry that is not text", id="list-with-a-zero"),
    pytest.param("neutral_product_pins:\n  - openDox\n  - false\n",
                 "holds an entry that is not text", id="list-with-false"),
    pytest.param("neutral_product_pins:\n  - openDox\n  - true\n",
                 "holds an entry that is not text", id="list-with-true"),
]


@pytest.mark.parametrize("body,said", NOT_A_LIST_OF_NAMES)
def test_a_link_manifest_whose_pins_are_not_a_list_of_names_is_named(
        tmp_path, body, said):
    """A manifest that cannot be read AS a declaration is declared-unverified
    with the reason named, as `not a mapping` is: never a traceback, and never
    a chain broken by a declaration nobody made."""
    tree = tmp_path / "trees" / "openXdox"
    tree.mkdir(parents=True)
    manifest = tree / "project.yaml"
    manifest.write_bytes(
        ("schema_version: 1\nkind: project-manifest\n" + body).encode())
    result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--link-source",
                         f"openXdox={tree}", "codexDox")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert "is broken" not in result.stderr, result.stderr
    assert (f"{UNREADABLE}{tree} (--link-source openXdox=...) could not "
            f"answer for openXdox: {manifest}: neutral_product_pins {said}\n"
            in result.stderr), result.stderr


def test_under_project_pins_that_are_not_a_list_are_a_warning_not_a_finding(
        tmp_path):
    """`--project` makes a chain that does not hold a FINDING, exit 1. A
    scalar `openDox` made one that way, from characters, with nothing wrong
    in the tree: now the tree cannot answer, and the exit is 0."""
    ws = tmp_path / "ws" / "codexDox"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_bytes((
        "neutral_product_pins:\n  - openXdox\nlegs:\n"
        "  - repository: testorg/codexDox\n    path: \".\"\n"
        "    role: assembly\n    naming:\n"
        "      referent_chain: [openXdox, openDox]\n").encode())
    sibling = tmp_path / "ws" / "openXdox"
    sibling.mkdir()
    manifest = sibling / "project.yaml"
    manifest.write_bytes(b"neutral_product_pins: openDox\n")
    result = run_script(VALIDATOR, "--project", "project.yaml", cwd=ws)
    assert result.returncode == 0, result.stderr
    assert "FINDING" not in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    resolved = sibling.resolve()
    assert (f"{UNREADABLE}{resolved} (sibling checkout ({resolved})) could "
            f"not answer for openXdox: {resolved / 'project.yaml'}: "
            "neutral_product_pins is not a list\n" in result.stderr), (
        result.stderr)


@pytest.mark.parametrize("body,said", NOT_A_LIST_OF_NAMES)
def test_link_pins_from_trees_passes_over_pins_that_are_not_a_list_of_names(
        tmp_path, monkeypatch, body, said):
    """The lookup itself, in this process, which the scaffold and the
    project's own `validate-manifest.py` call too: the link is ABSENT from the
    answer, as one that is not there is, and `tried` carries the reason."""
    clear_ambient_pin_sources(monkeypatch)
    tree = tmp_path / "openXdox"
    tree.mkdir()
    (tree / "project.yaml").write_bytes(("schema_version: 1\n"
                                         + body).encode())
    tried: dict = {}
    found = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox", tried=tried)
    assert found == {}
    sibling = tmp_path.resolve() / "openXdox"
    assert tried["openXdox"] == [
        ("sibling", f"sibling checkout ({sibling})", sibling,
         f"{sibling / 'project.yaml'}: neutral_product_pins {said}")]


@pytest.mark.parametrize("body,expected", [
    pytest.param("", set(), id="key-absent"),
    pytest.param("neutral_product_pins:\n", set(), id="null"),
    pytest.param("neutral_product_pins: []\n", set(), id="empty-list"),
    pytest.param("neutral_product_pins:\n  - \n  - openDox\n", {"openDox"},
                 id="blank-entry"),
    pytest.param("neutral_product_pins:\n  - ''\n  - openDox\n", {"openDox"},
                 id="empty-string-entry"),
    pytest.param("neutral_product_pins:\n  - testorg/openDox\n  - openYdox\n",
                 {"openDox", "openYdox"}, id="qualified-entry"),
])
def test_a_link_manifest_with_an_absent_or_blank_pin_list_still_answers(
        tmp_path, monkeypatch, body, expected):
    """THE OTHER SIDE of the guard: an absent or empty list declares nothing,
    and a blank entry in a list is dropped, as they always were. Only a value
    that is not a list of names stops the tree answering."""
    clear_ambient_pin_sources(monkeypatch)
    tree = tmp_path / "openXdox"
    tree.mkdir()
    (tree / "project.yaml").write_bytes(
        ("schema_version: 1\n" + body).encode())
    assert link_pins_from_trees(("openXdox", "openDox"),
                                root=tmp_path / "codexDox") == {
        "openxdox": expected}


@pytest.mark.parametrize("case", [
    "manifest-is-a-directory",
    pytest.param("source-is-a-device", marks=pytest.mark.skipif(
        not os.path.exists("/dev/null"), reason="needs /dev/null")),
])
def test_a_source_that_is_not_a_file_where_one_is_wanted_is_named(tmp_path,
                                                                  case):
    """Two sources `stat()` answers for and `load_yaml` must never be handed:
    a tree whose `project.yaml` is a directory, and a path that is neither a
    directory nor a file (a device here; a named pipe, which would hang the
    gate, is the next test)."""
    if case == "manifest-is-a-directory":
        source = tmp_path / "trees" / "openXdox"
        (source / "project.yaml").mkdir(parents=True)
        said = "its project.yaml is not a file"
    else:
        source = Path("/dev/null")
        said = "it is neither a directory nor a file"
    result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--link-source",
                         f"openXdox={source}", "codexDox")
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert (f"{UNREADABLE}{source} (--link-source openXdox=...) could not "
            f"answer for openXdox: {said}\n" in result.stderr), result.stderr


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs mkfifo")
def test_a_fifo_is_never_opened_as_a_manifest(tmp_path):
    """A named pipe as the source: `stat()` says it is neither a directory nor
    a file, and that is the whole answer. Opening one for reading blocks until
    somebody writes to it, so a lookup that took it for the manifest would
    hang the gate; this asks the lookup alone, and fails by an assertion."""
    fifo = tmp_path / "openXdox"
    os.mkfifo(fifo)
    assert link_manifest_lookup(fifo) == (
        None, "it is neither a directory nor a file")


@pytest.mark.parametrize("case", [
    "env-missing", "env-no-manifest", "env-not-a-mapping"])
def test_a_variable_that_cannot_answer_is_named_whatever_the_reason(
        tmp_path, case):
    """A `SHAPE_PIN_SOURCE_<LINK>` is something somebody SET, so every way it
    fails to answer for a link that holds a pin is said, not only a
    permission: a path that is not there, a directory with no `project.yaml`
    and a file that is no manifest. (A checkout BESIDE the project is
    different: that one being absent, or holding no manifest, is the ordinary
    case and is never said.)"""
    work = tmp_path / "work"
    work.mkdir()
    if case == "env-missing":
        source = tmp_path / "nowhere" / "openXdox"
        said = "no such file or directory"
    elif case == "env-no-manifest":
        source = tmp_path / "plain"
        source.mkdir()
        said = "it holds no project.yaml"
    else:
        source = tmp_path / "notes.yaml"
        source.write_bytes(b"- openDox\n")
        said = f"{source}: not a mapping"
    result = run_script(VALIDATOR, *CHAIN_ARGS, "codexDox", cwd=work,
                        env={"SHAPE_PIN_SOURCE_OPENXDOX": str(source)})
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "WARNING codexDox: declared-unverified" in result.stderr
    assert (f"{UNREADABLE}{source} ($SHAPE_PIN_SOURCE_OPENXDOX) could not "
            f"answer for openXdox: {said}\n" in result.stderr), result.stderr
    assert "NOTE" not in result.stderr


def test_a_value_given_again_after_another_is_the_one_in_force(tmp_path):
    """A, then B, then A for the chain's END, which nothing reads: B was
    replaced by the last A, and A was replaced by nothing, so A says only that
    no name reads openDox's declaration. A note that had kept `A replaced by
    B` would call the value in force a dead one."""
    tree = _tree(tmp_path / "trees" / "openXdox", "openDox")
    first, second = tmp_path / "first", tmp_path / "second"
    result = naming_from(
        tmp_path / "work", *CHAIN_ARGS, "--link-source", f"openXdox={tree}",
        "--link-source", f"openDox={first}", "--link-source",
        f"openDox={second}", "--link-source", f"openDox={first}", "codexDox")
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        f"NOTE --link-source openDox={first}: not used — no name classified "
        "here reads openDox's own declaration.\n"
        f"NOTE --link-source openDox={second}: not used — the later "
        f"`--link-source openDox={first}` replaced it.\n"), result.stderr


def test_a_value_holding_an_equals_sign_is_not_misread_when_no_chain_exists(
        tmp_path):
    """With no chain at all there is no link a key could have been meant for,
    so the value is not said to have been READ as a path for want of one: the
    note that no name records a chain is the whole of it."""
    result = naming_from(tmp_path / "work", "--link-source", "a=b/openXdox",
                         "Atlas")
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        "NOTE --link-source a=b/openXdox: not used — no name classified "
        "here records a referent chain.\n"), result.stderr


#: What a chain a classification does NOT read is. Each is run on its own, with
#: the same `--link-source` and the same variable, and none is asked.
UNREAD_CHAINS = [
    pytest.param(("--pins", "openXdox", "--referent-chain", "openXdox,openDox",
                  "Atlas"), id="a-name-with-no-referent-to-reach"),
    pytest.param(("--referent-chain", "openXdox,openDox", "codexDox"),
                 id="a-chain-that-does-not-begin-at-a-held-pin"),
    # `codexInk` would need `openInk`: `openXdox` is the x-stem spelling of
    # `openDox`, so a pin on it is a DIRECT pin on `codexDox`'s referent.
    pytest.param(("--pins", "openXdox", "--referent-chain",
                  "openXdox,openYdox", "codexInk"),
                 id="a-chain-that-ends-at-no-referent-of-the-name"),
]


@pytest.mark.parametrize("args", UNREAD_CHAINS)
def test_a_chain_no_classification_reads_is_neither_read_nor_reported(
        tmp_path, args):
    """`classify` consults a link's own declaration only for a name that
    claims a referent, with a chain whose shape holds. For any other chain a
    source was still asked, and so reported UNREADABLE (a path that is not
    there) or counted USED (a good tree), for a question nobody put. Now none
    is asked: the keyed value is a NOTE saying so, and the variable, a
    checkout that nothing needed, says nothing."""
    work = tmp_path / "work"
    work.mkdir()
    tree = _tree(tmp_path / "trees" / "openXdox", "openDox")
    missing = tmp_path / "nowhere" / "openXdox"
    env = {"SHAPE_PIN_SOURCE_OPENXDOX": str(missing)}
    for source in (missing, tree):
        result = run_script(VALIDATOR, "--role", "assembly", *args[:-1],
                            "--link-source", f"openXdox={source}", args[-1],
                            cwd=work, env=env)
        assert result.returncode == 0, result.stderr
        assert result.stderr == (
            f"NOTE --link-source openXdox={source}: not used — no name "
            "classified here reads openXdox's own declaration.\n"), (
            result.stderr)


def _spec_leg_chain_project(tmp_path: Path) -> Path:
    """A `codexDox` project whose chain is read, and whose spec leg records
    a SECOND chain, through `openYdox`, that its own name never reads."""
    ws = tmp_path / "ws" / "codexDox"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_bytes((
        "neutral_product_pins:\n  - openXdox\n  - openYdox\nlegs:\n"
        "  - repository: testorg/codexDox\n    path: \".\"\n"
        "    role: assembly\n    naming:\n"
        "      referent_chain: [openXdox, openDox]\n"
        "  - repository: testorg/codexDox-spec\n    path: spec\n"
        "    role: spec\n    naming:\n"
        "      referent_chain: [openYdox, openDox]\n").encode())
    _tree(tmp_path / "ws" / "openXdox", "openDox")
    return ws


def test_a_chain_recorded_on_a_spec_leg_is_not_read_for_the_leg(tmp_path):
    """THE REVIEW'S CASE. `codexDox-spec` is a project leg: it claims no
    referent, so the chain its manifest entry records is never consulted, and
    the `openYdox` it names is neither asked for nor reported. The keyed value
    for it is a NOTE, as it is for a link nobody reads; the one for the
    assembly leg's chain is used, and says nothing."""
    ws = _spec_leg_chain_project(tmp_path)
    missing = tmp_path / "nowhere" / "openYdox"
    result = run_script(VALIDATOR, "--project", "project.yaml",
                        "--link-source", f"openYdox={missing}", cwd=ws)
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        f"NOTE --link-source openYdox={missing}: not used — no name "
        "classified here reads openYdox's own declaration.\n"), result.stderr


@SEARCH_DENIED
def test_a_checkout_beside_the_project_that_no_chain_reads_is_never_asked(
        tmp_path):
    """The same case with no `--link-source` at all: `../openYdox` at mode 000
    is beside a project whose only reader of that chain is a spec leg. It used
    to be named UNREADABLE, for a link nothing needed."""
    ws = _spec_leg_chain_project(tmp_path)
    locked = _tree(tmp_path / "ws" / "openYdox", "openDox")
    locked.chmod(0)
    try:
        result = run_script(VALIDATOR, "--project", "project.yaml", cwd=ws)
    finally:
        locked.chmod(0o700)
    assert result.returncode == 0, result.stderr
    assert result.stderr == "", result.stderr


class _ReadSpy(dict):
    """A `link_pins` mapping that notes whether `resolve_referent` read it."""
    read = False

    def items(self):
        self.read = True
        return super().items()


def _chain_read_cases(policy) -> list:
    too_long = ("openXdox",
                *(f"open{'x' * n}dox" for n in range(
                    int(policy.chain_rule()["max_length"]))), "openDox")
    return [
        ("codexDox", {"openXdox"}, ("openXdox", "openDox"), True),
        ("codexDox", {"openXdox"}, ("openXdox", "openYdox", "openDox"), True),
        ("codexDox", {"testorg/openXdox"}, ("openXdox", "openDox"), True),
        # A QUALIFIED chain link: `resolve_referent` compares its basename, and
        # a gate that compared the text as typed would call the chain broken
        # at its first link and never read a tree (fix round 2).
        ("codexDox", {"openXdox"}, ("testorg/openXdox", "openDox"), True),
        ("codexDox", {"openXdox"}, (), False),
        ("codexDox", {"openXdox"}, ("", " "), False),
        ("Atlas", {"openXdox"}, ("openXdox", "openDox"), False),
        ("codexDox", set(), ("openXdox", "openDox"), False),
        ("codexDox", {"openXdox"}, ("openXdox", "openYdox"), False),
        ("codexDox", {"openXdox"}, ("openXdox", "openXdox", "openDox"), False),
        ("codexDox", {"openXdox"}, too_long, False),
    ]


def test_the_policy_says_a_chain_is_read_exactly_when_it_is_read(policy):
    """`reads_link_declarations` is what the validator asks before it reads a
    tree, and it must never drift from `resolve_referent`, which is what
    reads one: both are run over every way a chain is, and is not, consulted,
    with a mapping that notes whether `resolve_referent` took it."""
    for name, pins, chain, expected in _chain_read_cases(policy):
        spy = _ReadSpy({"openxdox": {"openDox"}})
        policy.resolve_referent(name, pins, chain, spy)
        assert spy.read is expected, (name, pins, chain)
        assert policy.reads_link_declarations(name, pins, chain) is expected, (
            name, pins, chain)


# --- fix round 2 on #338: what the unverified warning says of a tree that was
# --- reached ---------------------------------------------------------------
#
# A link whose own tree went unread is `declared-unverified`, and the warning
# said the tree "is not reachable here". That is true of a tree nothing found.
# It is untrue of one `--pin-source` DID reach and whose `neutral_product_
# pins:` could not be read, which is what the first fix round made of the
# scaffold's `chain-not-declared` refusal on a scalar: a REFUSAL became a
# warning that blamed the path. The scaffold now asks for the reason
# (`link_pins_from_trees(..., with_reasons=True)`) and says it. Every other
# reader's text is exactly what it was, and these tests hold both halves.

#: The warning a link whose tree nothing reached has always carried.
NOT_REACHED = (
    "declared-unverified: openXdox declaring a pin on openDox is a fact in "
    "openXdox's own tree, which is not reachable here (a sibling checkout, "
    "SHAPE_PIN_SOURCE_OPENXDOX, or --link-source openXdox=<path> would let "
    "it be read). The recorded chain still classifies.")


def _unverified_warnings(policy, link_pins) -> list[str]:
    return list(policy.resolve_referent("codexDox", {"openXdox"},
                                        ("openXdox", "openDox"),
                                        link_pins).warnings)


def test_the_unverified_warning_is_unchanged_where_no_tree_was_reached(
        policy, tmp_path, monkeypatch):
    """Nothing reached the tree, or whoever asked did not ask for a reason:
    the warning is the same bytes it was. That covers a plain mapping, a
    `LinkPins` with nothing in `unreadable`, a tree that is not there even
    when the reason was asked for, and a tree that WAS reached and could not
    be read when it was not (the naming validator, which says why on a line
    of its own, and `validate-manifest.py`)."""
    clear_ambient_pin_sources(monkeypatch)
    assert _unverified_warnings(policy, {}) == [NOT_REACHED]
    assert _unverified_warnings(policy, LinkPins()) == [NOT_REACHED]
    absent = link_pins_from_trees(("openXdox", "openDox"),
                                  root=tmp_path / "codexDox",
                                  with_reasons=True)
    assert absent == {} and absent.unreadable == {}
    assert _unverified_warnings(policy, absent) == [NOT_REACHED]
    tree = tmp_path / "openXdox"
    tree.mkdir()
    (tree / "project.yaml").write_bytes(
        b"schema_version: 1\nneutral_product_pins: openDox\n")
    plain = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox")
    assert type(plain) is dict
    assert _unverified_warnings(policy, plain) == [NOT_REACHED]


def test_the_unverified_warning_says_a_tree_was_reached_when_it_was(
        policy, tmp_path, monkeypatch):
    """The other half, in this process: asked to say why, the lookup keeps the
    reason for the link whose source answered, and the warning for it names
    the reason and no longer says the tree is not reachable. The mapping is
    still equal to a plain one, with the link absent from it."""
    clear_ambient_pin_sources(monkeypatch)
    tree = tmp_path / "openXdox"
    tree.mkdir()
    manifest = tree / "project.yaml"
    manifest.write_bytes(b"schema_version: 1\nneutral_product_pins: openDox\n")
    found = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox",
                                 with_reasons=True)
    why = f"{manifest}: neutral_product_pins is not a list"
    assert isinstance(found, dict) and found == {}
    assert found.unreadable == {"openxdox": why}
    assert _unverified_warnings(policy, found) == [
        "declared-unverified: openXdox declaring a pin on openDox is a fact "
        "in openXdox's own tree, which was reached but could not be read as a "
        f"declaration ({why}). The recorded chain still classifies."]


#: The other trees a `--pin-source` REACHES and cannot read as a declaration,
#: those whose manifest is not a pins list at all (reviewW2's NIT-R1). The
#: scaffold's reached branch is keyed on the fact that the source ANSWERED, not
#: on the reason, so a manifest that is not a mapping or does not parse says
#: "reached but could not be read" too, where on main (and at 4b21263) it said
#: "is not reachable here" of a file it had just opened. Narrowing the branch
#: to the not-a-list reasons (`why.endswith(("is not a list", "is not text"))`
#: before `unreadable[...] = why` in `link_pins_from_trees`) passed every
#: `NOT_A_LIST_OF_NAMES` row; these two kill it. The reasons are the
#: repository's own parser's, so they hold on every platform.
UNREADABLE_AS_A_DECLARATION = [
    pytest.param(b"- openInk\n", "not a mapping", id="not-a-mapping"),
    pytest.param(
        b"schema_version: 1\nkind: project-manifest\n"
        b"neutral_product_pins: [openInk\n",
        "not a flow collection: '[openInk'", id="does-not-parse"),
]


@pytest.mark.parametrize("body,said", UNREADABLE_AS_A_DECLARATION)
def test_the_lookup_remembers_why_a_manifest_it_reached_cannot_be_read(
        policy, tmp_path, monkeypatch, body, said):
    """The same two manifests in this process (NIT-R1): a manifest that is
    not a mapping, or does not parse, is a tree the source REACHED, so asked to
    say why, the lookup keeps the reason for the link, the mapping is still
    equal to a plain one with the link absent, and the warning names the
    reason instead of saying the tree is not reachable."""
    clear_ambient_pin_sources(monkeypatch)
    tree = tmp_path / "openXdox"
    tree.mkdir()
    manifest = tree / "project.yaml"
    manifest.write_bytes(body)
    found = link_pins_from_trees(("openXdox", "openDox"),
                                 root=tmp_path / "codexDox",
                                 with_reasons=True)
    why = f"{manifest}: {said}"
    assert isinstance(found, dict) and found == {}
    assert found.unreadable == {"openxdox": why}
    assert _unverified_warnings(policy, found) == [
        "declared-unverified: openXdox declaring a pin on openDox is a fact "
        "in openXdox's own tree, which was reached but could not be read as a "
        f"declaration ({why}). The recorded chain still classifies."]


def _scaffold_with_link_tree(tmp_path, manifest_body: bytes | None, *,
                             raw: bool = False):
    """`scaffold-project.py --dry-run` for `codexInk` with `--pin-source` a
    git clone of a stand-in `openXdox` whose `project.yaml` is
    `manifest_body` after a two-line header (none: the clone holds no
    `project.yaml`; `raw`: the manifest is `manifest_body` and nothing else,
    for one that must not begin with a mapping), and the chain
    `openXdox,openInk`. Returns the result and the manifest's path."""
    source = tmp_path / "trees" / "openXdox"
    source.mkdir(parents=True)
    if manifest_body is None:
        (source / "README").write_bytes(b"no manifest here\n")
    elif raw:
        (source / "project.yaml").write_bytes(manifest_body)
    else:
        (source / "project.yaml").write_bytes(
            b"schema_version: 1\nkind: project-manifest\n" + manifest_body)
    git("init", "-q", "-b", "main", cwd=source)
    git("add", "-A", cwd=source)
    git("commit", "-qm", "seed", cwd=source)
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    result = run_script(
        SCAFFOLD, "--org", "codexSoft", "--project", "codexInk",
        "--elected-by", "Test Human", "--elected-on", "2026-09-05",
        "--pin", f"openXdox@{commit}", "--pin-source", str(source),
        "--referent-chain", "openXdox,openInk", "--dry-run",
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"))
    return result, source / "project.yaml"


@pytest.mark.parametrize("body,said", NOT_A_LIST_OF_NAMES)
def test_scaffold_says_a_pin_source_it_reached_could_not_be_read(
        tmp_path, body, said):
    """REVIEWW2's ROW. `--pin-source` is a tree whose `neutral_product_pins:`
    is a scalar (or any value that is not a list of names). On main the
    scaffold REFUSED `chain-not-declared`, exit 2, with `openXdox declares I,
    e, k, n, o, p, not openInk` read from the characters; it is now a
    declared-unverified WARNING and the scaffold goes on, which is the rule
    for a tree that cannot answer. The warning says the tree was REACHED and
    could not be read, with the reason, because `--pin-source` did reach it:
    the clause "is not reachable here" blamed a path that was right."""
    result, manifest = _scaffold_with_link_tree(tmp_path, body.encode())
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED" not in result.stderr, result.stderr
    assert "not reachable here" not in result.stderr, result.stderr
    assert (
        "WARNING declared-unverified: openXdox declaring a pin on openInk is "
        "a fact in openXdox's own tree, which was reached but could not be "
        f"read as a declaration ({manifest}: neutral_product_pins {said}). "
        "The recorded chain still classifies.\n") in result.stderr, (
        result.stderr)
    assert "(1 link declared-unverified)" in result.stdout
    assert "--dry-run: nothing was created." in result.stdout


@pytest.mark.parametrize("body,said", UNREADABLE_AS_A_DECLARATION)
def test_scaffold_says_a_pin_source_whose_manifest_cannot_be_read_was_reached(
        tmp_path, body, said):
    """NIT-R1. `--pin-source` is a clone whose `project.yaml` is a list, or is
    a flow list that never closes. The tree was REACHED and its manifest could
    not be read, so the scaffold's declared-unverified warning says so, with
    the reason, as it does for a `neutral_product_pins:` that is not a list:
    "is not reachable here" blamed a path that was right, and a narrower
    reading of "reached" (the not-a-list reasons only) would leave that
    untruth for every manifest the lookup cannot parse."""
    result, manifest = _scaffold_with_link_tree(tmp_path, body, raw=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED" not in result.stderr, result.stderr
    assert "not reachable here" not in result.stderr, result.stderr
    assert (
        "WARNING declared-unverified: openXdox declaring a pin on openInk is "
        "a fact in openXdox's own tree, which was reached but could not be "
        f"read as a declaration ({manifest}: {said}). "
        "The recorded chain still classifies.\n") in result.stderr, (
        result.stderr)
    assert "(1 link declared-unverified)" in result.stdout
    assert "--dry-run: nothing was created." in result.stdout


def test_scaffold_offers_its_own_sources_for_a_pin_source_with_no_manifest(
        tmp_path):
    """A `--pin-source` clone that holds no `project.yaml` is the ordinary
    absence, as it always was: the tree is "not reachable here", never
    "reached". What would let it be read is the scaffold's own (#610). It
    offered "a sibling checkout, SHAPE_PIN_SOURCE_OPENXDOX, or --link-source
    openXdox=<path>", the naming validator's three, and the scaffold has no
    `--link-source` and reads no sibling checkout. It reads the variable,
    and, for the first link, its `--pin-source`."""
    result, _manifest = _scaffold_with_link_tree(tmp_path, None)
    assert result.returncode == 0, result.stderr + result.stdout
    assert ("WARNING declared-unverified: openXdox declaring a pin on openInk "
            "is a fact in openXdox's own tree, which is not reachable here "
            "(SHAPE_PIN_SOURCE_OPENXDOX, or a --pin-source clone of openXdox "
            "that holds its project.yaml, would let it be read). The recorded "
            "chain still classifies.\n") in result.stderr, result.stderr
    assert "was reached" not in result.stderr
    assert "--link-source" not in result.stderr
    assert "sibling checkout" not in result.stderr


def test_the_naming_validator_keeps_its_own_two_lines_for_a_tree_it_reached(
        tmp_path):
    """The validator names the reason on a line of its own, so its
    declared-unverified WARNING is unchanged by fix round 2: the same bytes
    as before, and the `link-source-unreadable` line beside it."""
    tree = tmp_path / "trees" / "openXdox"
    tree.mkdir(parents=True)
    manifest = tree / "project.yaml"
    manifest.write_bytes(b"schema_version: 1\nneutral_product_pins: openDox\n")
    result = naming_from(tmp_path / "work", *CHAIN_ARGS, "--link-source",
                         f"openXdox={tree}", "codexDox")
    assert result.returncode == 0, result.stderr
    assert result.stderr == (
        f"WARNING codexDox: {NOT_REACHED}\n"
        f"{UNREADABLE}{tree} (--link-source openXdox=...) could not answer "
        f"for openXdox: {manifest}: neutral_product_pins is not a list\n"), (
        result.stderr)


def test_the_projects_own_manifest_gate_keeps_its_warning_for_a_tree_it_reached(
        project):
    """`validate-manifest.py` reads the same link tree through the same
    lookup and prints no reason of its own, so it is the text it always was;
    this change reaches the scaffold alone."""
    _codexdox(project)
    sibling = project.parent / "openXdox"
    sibling.mkdir()
    (sibling / "project.yaml").write_bytes(
        b"schema_version: 1\nneutral_product_pins: openDox\n")
    own = run_script(project / "scripts" / "validate-manifest.py",
                     cwd=project)
    assert "Traceback" not in own.stderr, own.stderr
    assert "which is not reachable here (a sibling checkout, " in (
        own.stdout + own.stderr), own.stdout + own.stderr
    assert "was reached" not in own.stdout + own.stderr


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


# --- the ruling: a SIXTH FORM, the person's WORKSPACE repository -----------
#
# openRepoShape#81, and Brett Heap on 2026-09-09: "the new-workstation name is
# one per user right? so if we have brett and scott as engineers, then we need
# something like brett-wip and scott-wip right?" — with rulings 1 to 3 giving
# the placement (one per person, private, in that person's HOME organisation,
# a per-org `orgs:` override for an org whose work must stay inside it) and
# the issue's own two recommendations taken on 2026-09-10: nothing in this
# standard creates one, and `<user>` is the GitHub login lowercased.
#
# `<user>-wip` is UNAMBIGUOUS BY CONSTRUCTION, exactly as `<X>-Install` is, so
# it is not `declared_only:` and needs no `--role`. What every test below is
# really about is the property the README states and this file has enforced
# for two earlier forms: adding a form changes NO existing name's answer.

def test_a_wip_suffix_is_the_workspace_form(policy):
    """THE brett-wip CASE. One lowercase login token, the literal `-wip`, and
    no declaration of any kind — the characters are the whole rule."""
    for name in ("brett-wip", "scott-wip", "a1-wip", "my-user-wip"):
        found = policy.classify(name)
        assert found == ("workspace", None), f"{name} -> {found}"
        assert found.also_matches == (), (
            "no other form in this policy admits a `-wip` suffix, so a "
            "workspace name overlaps nothing and records nothing")
        assert "unambiguous by construction" in found.reason


def test_the_workspace_form_sits_last_and_is_not_declared_only(policy):
    """It is BELOW the family holder in precedence and, unlike it, needs no
    declaration: `family` is spelled like an assembly root and only
    `family.yaml` tells them apart, while nothing else spells `-wip` at all."""
    family = _family(policy, "workspace")
    assert family["precedence"] == 6
    assert family["precedence"] > _family(policy, "family")["precedence"]
    assert not policy.declared_only("workspace")
    assert "declared_only" not in family
    assert "roles" not in family, (
        "a workspace repository has no legs and answers in no role")
    assert "admits_declared_role" not in family, (
        "it is admitted into no role either: `brett-wip` is not an assembly "
        "root, which is what makes `nothing creates one` a check")
    assert not family.get("requires_referent")


def test_the_workspace_form_carries_no_declared_role(policy):
    """`--role` is for a form that needs a declaration. Declared over a
    workspace name, a role is IGNORED rather than carried — exactly what
    `<X>-Install` does, and for the same reason."""
    for role in ("assembly", "spec", "code", "family", "workspace"):
        found = policy.classify("brett-wip", role)
        assert found == ("workspace", None), f"--role {role} -> {found}"
        assert found.reason.startswith("the workspace form is unambiguous")


def test_nothing_in_this_standard_creates_a_workspace_repository(policy):
    """The enforced half of open decision 1. `accepts_role` is the ONE
    definition of "which forms may be an assembly leg", consulted by the
    scaffold, by `adopt-project.py` and by a project's own
    `validate-manifest.py` — and it refuses a workspace name in every role,
    so no tool here can be pointed at one. A person makes their own."""
    for role in ("assembly", "spec", "code"):
        assert not accepts_role(policy.classify("brett-wip", role), role)


def test_the_workspace_form_is_unambiguous_by_construction_in_the_code(policy):
    """The list of forms that need nothing declared lives beside the
    classifier that reads it, and `UNAMBIGUOUS_FORMS` says why it is not a key
    in the policy file: a new classifier reading an OLD copied policy would
    then classify every `open<Product>` as a project leg."""
    assert UNAMBIGUOUS_FORMS == ("neutral-product", "install", "workspace")
    for family_id in UNAMBIGUOUS_FORMS:
        assert _family(policy, family_id) is not None
        assert not policy.declared_only(family_id)
        assert not policy.requires_referent(family_id)


#: THE REGRESSION SET, as a table: `(name, --role, --pins) -> (family, role,
#: also_matches)`, or `None` for a name that matches no family at all. Every
#: row above `brett-wip` restates an answer asserted somewhere else in this
#: file, and the rows below it are the sixth form's own positives and
#: negatives. ONE table, because the property being asserted is one property:
#: adding a form to the policy changes no existing name's answer, and the
#: evidence for that is worth nothing if it is not the same list of names the
#: rest of the suite already relies on. A form added to the contract that
#: moves any row here has broken a live project's manifest, since
#: `validate-manifest.py` compares `also_matches` exactly.
KEEPS_ITS_ANSWER = (
    ("openxFactory", None, (),
     ("neutral-product", None, ("domain-descendant", "project-leg/assembly"))),
    ("openScribe", None, (),
     ("neutral-product", None, ("project-leg/assembly",))),
    ("openScribe", "assembly", (),
     ("neutral-product", "assembly", ("project-leg/assembly",))),
    ("openDox", None, (),
     ("neutral-product", None, ("project-leg/assembly",))),
    ("openDox", "assembly", (),
     ("neutral-product", "assembly", ("project-leg/assembly",))),
    ("openDox", "spec", (),
     ("neutral-product", None, ("project-leg/assembly",))),
    ("openDox-spec", "assembly", (), ("project-leg", "spec", ())),
    ("openXdox", "assembly", (),
     ("neutral-product", "assembly", ("project-leg/assembly",))),
    ("openXwallet", "assembly", (),
     ("neutral-product", "assembly", ("project-leg/assembly",))),
    ("openChart", "family", (),
     ("neutral-product", None, ("project-leg/assembly", "family"))),
    ("Foo-Install", "assembly", (), ("install", None, ())),
    ("xFactory-Hermes-Install", "assembly", (), ("install", None, ())),
    ("MedxChart", None, ("openChart",),
     ("domain-descendant", None, ("project-leg/assembly",))),
    ("MedxChart", "assembly", (),
     ("project-leg", "assembly", ("domain-descendant",))),
    ("MedxScribe", None, (),
     ("project-leg", "assembly", ("domain-descendant",))),
    ("MedxScribe", "assembly", (),
     ("project-leg", "assembly", ("domain-descendant",))),
    ("MedxScribe", None, ("openChart",),
     ("project-leg", "assembly", ("domain-descendant",))),
    ("MedxScribe-spec", "assembly", (), ("project-leg", "spec", ())),
    ("MedxGlass", "assembly", ("openGlass",),
     ("domain-descendant", "assembly", ("project-leg/assembly",))),
    ("MedxGlass", "code", ("openGlass",),
     ("domain-descendant", None, ("project-leg/assembly",))),
    ("MedxGlass-spec", "spec", ("openGlass",), ("project-leg", "spec", ())),
    ("codexFactory", None, ("openxFactory",),
     ("domain-descendant", None, ("project-leg/assembly",))),
    ("Atlas", None, (), ("project-leg", "assembly", ())),
    ("Atlas-spec", None, (), ("project-leg", "spec", ())),
    ("Atlas-code", None, (), ("project-leg", "code", ())),
    ("InkRouter", None, (), ("project-leg", "assembly", ())),
    ("InkRouter", "family", (), ("family", None, ("project-leg/assembly",))),
    ("InkRouter-spec", "family", (), ("project-leg", "spec", ())),
    ("Ink-Router", "family", (), None),
    ("Atlas_spec", None, (), None),
    ("Atlas-tests", None, (), None),
    ("hermes-install", None, (), None),
    ("Keycloak-Installer", None, (), None),
    ("xFactory-Installer", None, (), None),
    ("9Lives", None, (), None),
    ("Atlas spec", None, (), None),
    # The sixth form (2026-09-10). The positives are the only names in this
    # table whose answer this addition changed at all — each of them matched
    # NOTHING before it existed.
    ("brett-wip", None, (), ("workspace", None, ())),
    ("scott-wip", None, (), ("workspace", None, ())),
    ("a1-wip", None, (), ("workspace", None, ())),
    ("my-user-wip", None, (), ("workspace", None, ())),
    ("9lives-wip", None, (), ("workspace", None, ())),
    ("brett-wip", "assembly", (), ("workspace", None, ())),
    # And the negatives, each one a thing a reader might expect to classify.
    # `<user>` is the GitHub login LOWERCASED, so an uppercase letter
    # anywhere is not one; `-wip` is the literal suffix, so it is neither an
    # infix nor a name of its own; a login carries single hyphens and neither
    # doubles them nor leads with one; and `wip` alone is a perfectly good
    # project name, which is the honest reading rather than a gap.
    ("Brett-wip", None, (), None),
    ("brett-WIP", None, (), None),
    ("brett_wip", None, (), None),
    ("brett.wip", None, (), None),
    ("-wip", None, (), None),
    ("brett--wip", None, (), None),
    ("brett-wip-2", None, (), None),
    ("brett-wip2", None, (), None),
    ("wip", None, (), ("project-leg", "assembly", ())),
)


@pytest.mark.parametrize("name,role,pins,expected", KEEPS_ITS_ANSWER)
def test_every_classified_name_keeps_its_exact_answer(policy, name, role, pins,
                                                      expected):
    """The property the README states, as a table rather than as a claim."""
    found = policy.classify(name, role, set(pins))
    if expected is None:
        assert found is None, f"{name} unexpectedly classified as {found}"
        return
    assert found is not None, f"{name} classified as nothing"
    actual = (found.family, found.role, found.also_matches)
    assert actual == expected


def test_the_policy_file_parses_under_the_projects_own_loader():
    """The contract is read by the stdlib YAML SUBSET this standard ships —
    there is no PyYAML anywhere in it — so a form added to the file has to be
    spellable in that subset or no tool of this standard can read the file at
    all, in this repository or in any project carrying a copy."""
    data = parse_yaml(POLICY_PATH.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data["kind"] == "repository-naming-policy"
    assert [f["id"] for f in data["families"]] == [
        "neutral-product", "install", "domain-descendant", "project-leg",
        "family", "workspace"]


def test_the_six_forms_have_distinct_precedences_in_order(policy):
    """PRECEDENCE IS SEMANTIC, so two forms sharing one would leave the order
    of two answers to `sorted`'s stability rather than to the contract."""
    precedences = [f["precedence"] for f in policy.families]
    assert precedences == [1, 2, 3, 4, 5, 6]
    assert len(set(precedences)) == len(precedences)
    assert [f["id"] for f in policy.families] == [
        "neutral-product", "install", "domain-descendant", "project-leg",
        "family", "workspace"]


def test_a_form_no_branch_claims_is_reported_rather_than_raised(tmp_path):
    """A SEVENTH form, in a fork's own policy file, before anybody writes its
    branch in `classify()`. The file is DATA and its own header says data can
    be edited, so a form this classifier has no rule for is reported by
    PRECEDENCE with a reason that says so. Until 2026-09-10 that path raised
    `KeyError: 'domain-descendant'` — a data file crashing the tool that reads
    it rather than being read by it — which is what `brett-wip` would have hit
    had the workspace form been added to the contract alone."""
    policy_file = tmp_path / "seventh.yaml"
    policy_file.write_text(
        "schema_version: 1\n"
        "kind: repository-naming-policy\n"
        "families:\n"
        "  - id: sigil\n"
        "    precedence: 7\n"
        "    title: Sigil\n"
        '    pattern: "^~[a-z]+$"\n',
        encoding="utf-8")
    found = NamingPolicy.load(policy_file).classify("~ink")
    assert found == ("sigil", None)
    assert found.also_matches == ()
    assert "no rule of its own" in found.reason


def test_cli_classifies_a_workspace_name():
    result = run_script(VALIDATOR, "brett-wip", "scott-wip")
    assert result.returncode == 0, result.stderr
    assert "brett-wip                        workspace" in result.stdout
    assert "also_matches" not in result.stdout


def test_cli_strips_the_owner_prefix_from_a_workspace_name():
    """`opensoft/brett-wip` names the same form as `brett-wip`: the
    organisation login is not part of any family, and WHICH org holds the
    repository is the person's `orgs:` map to answer, not the name's."""
    result = run_script(VALIDATOR, "opensoft/brett-wip")
    assert result.returncode == 0, result.stderr
    assert "workspace" in result.stdout


def test_cli_explain_names_the_workspace_form_and_the_rule():
    result = run_script(VALIDATOR, "--explain", "brett-wip")
    assert result.returncode == 0, result.stderr
    assert "brett-wip: workspace" in result.stdout
    assert "MATCH workspace" in result.stdout
    assert "^[a-z0-9]+(?:-[a-z0-9]+)*-wip$" in result.stdout
    assert "UNAMBIGUOUS BY CONSTRUCTION" in result.stdout
    assert "it needs nothing declared" in result.stdout
    assert "OVERLAP" not in result.stdout, (
        "a workspace name satisfies exactly one form, so there is no overlap "
        "to report")


def test_cli_refuses_a_near_miss_workspace_name():
    """A doubled hyphen is not a login and `-wip` is a suffix, so neither name
    is a workspace — and neither is anything else, which is a FINDING."""
    result = run_script(VALIDATOR, "brett--wip", "brett-wip-2")
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr
    assert "brett--wip" in result.stderr
    assert "brett-wip-2" in result.stderr


def test_cli_does_not_take_workspace_as_a_declared_role():
    """`--role` names a DECLARATION, and only a form that needs one is a value
    there — `family`, and the three leg roles. `workspace` needs none, exactly
    as `install` and `neutral-product` need none, so the flag refuses it as
    the unknown choice it is rather than pretending there was something to
    declare."""
    result = run_script(VALIDATOR, "--role", "workspace", "brett-wip")
    assert result.returncode == 2
    assert "invalid choice: 'workspace'" in result.stderr


def test_cli_role_assembly_does_not_move_a_workspace_name():
    """The other half: a role that IS a choice, declared over a workspace
    name, leaves the answer exactly where the characters put it."""
    result = run_script(VALIDATOR, "--role", "assembly", "brett-wip")
    assert result.returncode == 0, result.stderr
    assert "workspace" in result.stdout
    assert "project-leg" not in result.stdout
