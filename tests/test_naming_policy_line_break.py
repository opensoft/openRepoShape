# SPDX-License-Identifier: Apache-2.0
"""A repository name that ends in a line feed is the name of no family
(#1202, the follow-up of #1139 and #1166).

THE DEFECT, measured on main 5926cccab (Python 3.12.3). The patterns of
`contracts/repository-naming.yaml` are every one `^...$`, and `NamingPolicy`
read a name against them with `.match` at four sites: `descendant_referents`
(the family's pattern, then its `split_pattern`), and `matches` (a role's
pattern, then a family's). In Python `$` also matches just before a trailing
line feed, so a name that ends in one was classified as the name without it:

- `matches("Atlas\\n")` was `[("project-leg", "assembly")]`, as for `Atlas`;
  so for `Atlas-spec`, `Atlas-code`, `openFoo`, `Thing-Install`, `user-wip`,
  `InkxRouter` and `MedxScribe`, and `descendant_referents` of the last two
  gave `openRouter`/`openxRouter` and `openScribe`/`openxScribe`;
- `validate-repository-naming.py --project project.yaml` over a manifest whose
  leg `repository:` is `"testorg/Atlas\\n"` (and the `-spec` and `-code`
  legs) exited 0, and so did the same name as an argument. The root template
  runs it at `Makefile:48` and `validate.yml:310`.

THE RULE NOW. The four sites ask `fullmatch`, so a name is read against the
whole of every pattern, and `contracts/repository-naming.yaml`'s header says
so for a fork's pattern: one with no `$` read as a prefix under `.match`, and
reads as the whole name now. Every shipped pattern begins with `^` and ends
with `$`, so no name without a line feed changes its answer
(`tests/test_naming_policy.py` passes as it was). `topic_pattern` has no
reader outside `tests/test_naming_policy.py`, so a row cannot fail on main
for it; a note beside it says a reader must use `fullmatch`.

THE ROWS. The names are read from the data, so a family or a role added to
the contract is covered without a line here. The two sites of
`descendant_referents` stand in series, and the shipped `split_pattern` takes
the language of the family's `pattern`, so either alone makes the other
redundant on the shipped data: a fork's policy, whose one pattern has no `$`,
is what asks each of them by itself.

No network and no GitHub: the policy is read in process and the project is
the offline one of `conftest.py`.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO, run_script
from test_value_pattern_line_break import findings, rewritten

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import NamingPolicy, parse_yaml  # noqa: E402

POLICY_PATH = REPO / "contracts" / "repository-naming.yaml"
VALIDATOR = REPO / "scripts" / "validate-repository-naming.py"
#: A line feed, as the YAML reader reads a double-quoted `\n`.
LF = chr(10)


def policy_of_the_data() -> NamingPolicy:
    return NamingPolicy.load(POLICY_PATH)


def examples_of_the_data() -> tuple[dict, dict]:
    """`({(family id, name): the role to declare}, {(family id, role id,
    name): the same})`: every example the data gives a family and every one
    it gives a role, so a family or a role added to the contract gets its rows
    without a line here. A `declared_only` family is reported only where it is
    asked for by its own id."""
    families, roles = {}, {}
    for family in policy_of_the_data().families:
        declared = family["id"] if family.get("declared_only") else None
        for name in family.get("examples") or []:
            families[(family["id"], name)] = declared
        for role in family.get("roles") or []:
            for name in role.get("examples") or []:
                roles[(family["id"], role["id"], name)] = declared
    return families, roles


FAMILIES, ROLES = examples_of_the_data()
FAMILY_ROWS = [pytest.param(family_id, name, declared,
                            id=f"{family_id}-{name}")
               for (family_id, name), declared in FAMILIES.items()]
ROLE_ROWS = [pytest.param(family_id, role_id, name, declared,
                          id=f"{family_id}-{role_id}-{name}")
             for (family_id, role_id, name), declared in ROLES.items()]
#: Every name of the data once, with the role it is asked under.
EVERY_NAME = [pytest.param(name, declared, id=f"{family_id}-{name}")
              for (family_id, name), declared in {
                  **FAMILIES, **{(f, n): d for (f, _r, n), d in ROLES.items()}
              }.items()]


@pytest.fixture(scope="module")
def policy() -> NamingPolicy:
    return policy_of_the_data()


# --- the four sites, over the shipped data -----------------------------------

@pytest.mark.parametrize("family_id, name, declared", FAMILY_ROWS)
def test_a_name_of_a_family_is_still_matched_without_the_line_feed(
        policy, family_id, name, declared):
    """The baseline of every row below: what main answered, and still does."""
    matched = [family for family, _role in policy.matches(name, declared)]
    assert family_id in matched


@pytest.mark.parametrize("family_id, role_id, name, declared", ROLE_ROWS)
def test_a_name_of_a_role_is_still_matched_without_the_line_feed(
        policy, family_id, role_id, name, declared):
    assert (family_id, role_id) in policy.matches(name, declared)


@pytest.mark.parametrize("name, declared", EVERY_NAME)
def test_a_name_that_ends_in_a_line_feed_matches_no_family(
        policy, name, declared):
    """THE ISSUE'S ROW, for `matches` (a role's pattern, then a family's), for
    `classify`, which reads `matches`, and for `descendant_referents`: on main
    each was the answer for the name without the line feed."""
    assert policy.matches(name + LF, declared) == []
    assert policy.classify(name + LF, declared) is None
    assert policy.descendant_referents(name + LF) == ()


#: The names that claim a descent: the data's examples, and the one it gives of
#: a claim with no referent.
DESCENDANTS = [pytest.param(name, id=name) for name in (
    policy_of_the_data().family("domain-descendant")["examples"]
    + policy_of_the_data().family(
        "domain-descendant")["claim_without_referent_examples"])]


@pytest.mark.parametrize("name", DESCENDANTS)
def test_a_descendant_name_still_has_its_referents(policy, name):
    """The baseline of the row below."""
    assert policy.descendant_referents(name) != ()


@pytest.mark.parametrize("name", DESCENDANTS)
def test_a_descendant_name_that_ends_in_a_line_feed_has_no_referent(
        policy, name):
    """On main `InkxRouter\\n` gave `openRouter` and `openxRouter`, as
    `InkxRouter` does."""
    assert policy.descendant_referents(name + LF) == ()
    assert policy.descendant_referent(name + LF) is None


# --- a fork's pattern with no `$` --------------------------------------------

def fork_policy(family_id: str, key: str, pattern: str,
                role_id: str | None = None) -> NamingPolicy:
    """The shipped policy with ONE pattern of a fork's own: the family's
    `pattern`, a role's, or the referent's `split_pattern`."""
    data = parse_yaml(POLICY_PATH.read_text(encoding="utf-8"))
    family = next(f for f in data["families"] if f["id"] == family_id)
    if key == "split_pattern":
        family["referent"]["split_pattern"] = pattern
    elif role_id is not None:
        next(r for r in family["roles"] if r["id"] == role_id)[key] = pattern
    else:
        family[key] = pattern
    return NamingPolicy(data)


#: The two sites of `descendant_referents` stand in series, and the shipped
#: `split_pattern` takes the family pattern's language, so each is asked by
#: itself only where the fork's two differ: the pattern of one has no `$`.
#: `MedxS` is a whole name of either pattern; `MedxScribe` is a name of the
#: shipped other one, and a prefix-match of the fork's.
@pytest.mark.parametrize("key, pattern", [
    pytest.param("pattern", "^[A-Za-z][A-Za-z0-9]*x[A-Z]",
                 id="family-pattern"),
    pytest.param("split_pattern", "^(?P<stem>[A-Za-z]+)x(?P<product>[A-Z])",
                 id="split-pattern"),
])
def test_a_forks_descendant_pattern_with_no_dollar_is_read_as_the_whole_name(
        key, pattern):
    """`.match` read the pattern as a prefix of the name; the header of the
    contract says a pattern is read against the whole of it."""
    fork = fork_policy("domain-descendant", key, pattern)
    assert fork.descendant_referents("MedxS") == ("openS", "openxS")
    assert fork.descendant_referents("MedxScribe") == ()


#: The same for the two sites of `matches`. `Atlas` is a whole name of the
#: fork's pattern, as of the shipped one; `Atlas_x` is a prefix-match of it only.
@pytest.mark.parametrize("role_id", [
    pytest.param("assembly", id="role-pattern"),
    pytest.param(None, id="family-pattern"),
])
def test_a_forks_leg_pattern_with_no_dollar_is_read_as_the_whole_name(role_id):
    fork = fork_policy("project-leg", "pattern", "^[A-Za-z][A-Za-z0-9]*",
                       role_id)
    assert fork.matches("Atlas") == [("project-leg", "assembly")]
    assert fork.matches("Atlas_x") == []


# --- the gate ------------------------------------------------------------------

@pytest.mark.parametrize("repository", [
    pytest.param("testorg/Atlas", id="assembly"),
    pytest.param("testorg/Atlas-spec", id="spec"),
    pytest.param("testorg/Atlas-code", id="code"),
])
def test_the_naming_gate_refuses_a_leg_repository_that_ends_in_a_line_feed(
        project, repository):
    """On main `validate-repository-naming.py --project` exited 0 over each
    of the three legs, with the name and its family on two lines. The finding
    names it as `repo_shape.spelled` does, `Atlas\\n` (#1267): printed raw it
    read as the finding for `Atlas`, with a blank line after it."""
    name = repository.split("/")[1]
    rewritten(project / "project.yaml", f"    repository: {repository}\n",
              f'    repository: "{repository}\\n"\n')
    result = run_script(VALIDATOR, "--project", str(project / "project.yaml"))
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [
        f"FINDING naming-unclassified: {name}\\n"]


def test_the_naming_gate_takes_a_leg_repository_double_quoted(project):
    """The baseline of the row above: the quotes are not what is refused."""
    rewritten(project / "project.yaml", "    repository: testorg/Atlas\n",
              '    repository: "testorg/Atlas"\n')
    result = run_script(VALIDATOR, "--project", str(project / "project.yaml"))
    assert result.returncode == 0, result.stdout + result.stderr


ARGV_NAMES = ["Atlas", "Atlas-spec", "Atlas-code"]


@pytest.mark.parametrize("name", ARGV_NAMES)
def test_the_naming_gate_takes_an_argv_name(name):
    """The baseline of the row below."""
    result = run_script(VALIDATOR, name)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("name", ARGV_NAMES)
def test_the_naming_gate_refuses_an_argv_name_that_ends_in_a_line_feed(name):
    """A name from the command line is not stripped (a name from stdin is):
    on main each was classified, its name and family on two lines. The
    finding names it spelled, `Atlas\\n` (#1267)."""
    result = run_script(VALIDATOR, name + LF)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [
        f"FINDING naming-unclassified: {name}\\n"]
