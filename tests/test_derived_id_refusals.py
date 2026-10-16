# SPDX-License-Identifier: Apache-2.0
"""`scaffold-bad-id` and `family-bad-id` name an id by where it came from,
and send a derived one to the flag it came from (#659).

WHAT WAS WRONG (#459's L2-56, and its label half in comment 6198174555).
`scaffold-project.py` fills `--id` in as `--project` lowercased when none is
passed, and `family.py init` as `--family` lowercased. Both then refused that
id as `--id 'north_wind' must match ^[a-z0-9][a-z0-9-]*$`, a flag nobody had
passed, with "Remediation: pass an explicit lowercase --id." And that remedy
led straight to a second refusal: the naming policy reads `--project`
(`--family`) itself, every form it holds takes only ASCII letters, digits
and hyphens, so `--id north-wind` met `naming-unclassified: 'North_Wind'
matches no family in the naming policy`.

THE CURE, in the words `adopt-project.py plan` uses for `adopt-bad-id`
(#658): a derived id's flag is named by where its value came from, `--id
(not given, so --project lowercased)`, the label each tool's manifest
refusals already give it, and its remedy is to change the flag it came from,
which also names what the run makes. A `--id` the person passed keeps
today's sentence and remedy, value as typed, even when it equals the derived
one: what is read is whether the flag was passed, not what its value is. An
empty `--id ''` derives the id as no `--id` does (`args.id or ...`), and is
named as empty, because it was passed.

Every run is a `--dry-run` into `--local-remote-dir`, which never calls `gh`.
"""

from __future__ import annotations

import sys

import pytest

from conftest import ORG, REPO, SCAFFOLD, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PROJECT_ID_RE, SAFE_ARG_RE  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
PATTERN = PROJECT_ID_RE.pattern

#: Per tool: the command, the flag naming whoever creates it, the flag the
#: id is derived from and what else that flag names, and the finding's code.
TOOLS = {
    "scaffold": {"command": (SCAFFOLD,), "who": "--elected-by",
                 "flag": "--project", "code": "scaffold-bad-id",
                 "names": "the assembly root and both legs"},
    "family": {"command": (FAMILY, "init"), "who": "--created-by",
               "flag": "--family", "code": "family-bad-id",
               "names": "the holder"},
}
PASSED_REMEDY = "Remediation: pass an explicit lowercase --id."


def derived(tool: str, unset: str) -> str:
    """How `tool` names a derived id's flag: `--id` given no value
    (`unset`), so the flag the id is derived from, lowercased."""
    return f"--id ({unset}, so {TOOLS[tool]['flag']} lowercased)"


def derived_remedy(tool: str) -> str:
    """The remedy `tool` gives for an id derived from its flag."""
    flag = TOOLS[tool]["flag"]
    return (f"Remediation: change {flag}. The id is {flag} lowercased, and "
            f"an explicit --id would not change {flag}, which also names "
            f"{TOOLS[tool]['names']}.")


#: Every character a name may hold on a command line (`SAFE_ARG_RE`, which
#: `checked_value` asks of `--project` and `--family` before the id is
#: derived from it) that leaves the name, lowercased, no id
#: (`PROJECT_ID_RE`): the characters a DERIVED id is refused for.
REFUSED_IN_AN_ID = tuple(
    c for c in map(chr, range(0x21, 0x7F))
    if SAFE_ARG_RE.fullmatch(f"North{c}Wind")
    and not PROJECT_ID_RE.match(f"North{c}Wind".lower()))


def run_tool(tmp_path, tool: str, name: str, *extra: str):
    """One dry run of `tool` for `name`, into a local remote that never
    exists: every row here is refused before anything is made."""
    remotes = tmp_path / "remotes"
    result = run_script(*TOOLS[tool]["command"], "--org", ORG,
                        TOOLS[tool]["flag"], name,
                        TOOLS[tool]["who"], "Test Human", "--dry-run",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"), *extra)
    assert result.returncode == 2, result.stdout + result.stderr
    assert not remotes.exists()
    return result.stderr


def refusal(tool: str, what: str, remedy: str) -> str:
    return f"REFUSED {TOOLS[tool]['code']}: {what}\n{remedy}\n"


@pytest.mark.parametrize("tool", TOOLS)
def test_a_derived_id_is_named_by_where_it_came_from_and_sent_to_that_flag(
        tmp_path, tool):
    stderr = run_tool(tmp_path, tool, "North_Wind")
    assert refusal(
        tool,
        f"{derived(tool, 'not given')} is 'north_wind', which must match "
        f"{PATTERN}",
        derived_remedy(tool)) in stderr
    assert "--id 'north_wind'" not in stderr
    assert PASSED_REMEDY not in stderr


@pytest.mark.parametrize("tool", TOOLS)
def test_an_empty_id_is_named_as_empty_and_not_as_not_given(tmp_path, tool):
    """`--id ''` was passed, so "not given" would be false of it; the id is
    still the derived one, and the remedy is still the flag's."""
    stderr = run_tool(tmp_path, tool, "North_Wind", "--id=")
    assert refusal(
        tool,
        f"{derived(tool, 'empty')} is 'north_wind', which must match "
        f"{PATTERN}",
        derived_remedy(tool)) in stderr
    assert "not given" not in stderr


@pytest.mark.parametrize("tool", TOOLS)
def test_a_passed_id_equal_to_the_derived_one_is_still_named_as_passed(
        tmp_path, tool):
    """Passed means typed, not "differs from the name lowercased"."""
    stderr = run_tool(tmp_path, tool, "North_Wind", "--id", "north_wind")
    assert refusal(tool, f"--id 'north_wind' must match {PATTERN}",
                   PASSED_REMEDY) in stderr
    assert "derived" not in stderr


@pytest.mark.parametrize("tool", TOOLS)
def test_a_passed_bad_id_keeps_its_sentence_and_its_remedy(tmp_path, tool):
    stderr = run_tool(tmp_path, tool, "NorthWind", "--id", "Foo_Bar")
    assert refusal(tool, f"--id 'Foo_Bar' must match {PATTERN}",
                   PASSED_REMEDY) in stderr
    assert "derived" not in stderr


def test_the_characters_a_derived_id_is_refused_for():
    """The rows below are every one of them; an empty list would pass
    vacuously, and a new one is a name the remedy has to be true of."""
    assert REFUSED_IN_AN_ID == ("+", ".", "/", "@", "_", "~")


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("char", REFUSED_IN_AN_ID)
def test_a_name_whose_derived_id_is_refused_is_refused_by_the_naming_policy(
        tmp_path, tool, char):
    """Why a derived id's remedy is its flag's and not `--id`'s: the naming
    policy reads the name itself and refuses every one whose lowercase is no
    id, so a `--id` that is an id only meets that refusal. Run with one, so
    this is the run the old remedy led to."""
    name = f"North{char}Wind"
    stderr = run_tool(tmp_path, tool, name, "--id", "north-wind")
    assert (f"REFUSED naming-unclassified: {name!r} matches no family in the "
            "naming policy") in stderr
    assert TOOLS[tool]["code"] not in stderr
