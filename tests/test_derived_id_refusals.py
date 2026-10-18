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
today's sentence, value as typed, even when it equals the derived one: what
is read is whether the flag was passed, not what its value is.

AND #911 (#459's U156, U158, U159 and U162). A passed `--id` was told "pass
an explicit lowercase --id" whatever its fault, `foo_bar` included, which is
both; it is told what an id may hold now (`PROJECT_ID_RE` in words). A
passed one was refused before the name, so `--project North_Wind --id
north_wind` was sent to retype the id and then met `naming-unclassified`;
the name speaks first now. An empty `--id ''` derived the id as no `--id`
does (`args.id or ...`); it is a passed value now, refused by name. And
`init`'s derived remedy led `--family open_glass` to `openGlass`, which
`naming-not-a-family` refuses; the rule it names says so now.

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

#: The rule each tool's `naming-unclassified` holds a name to, in its own
#: words: the scaffold's is the token rule; `init`'s adds the two forms no
#: holder can be declared as (#911), in `naming-not-a-family`'s words.
NAME_RULE = "one CamelCase token with no hyphen, underscore, dot or space"
NOT_A_HOLDER = "and not an `open<Product>` or `<X>-Install` name"

#: Per tool: the command, the flag naming whoever creates it, the flag the
#: id is derived from and what else that flag names, the finding's code, and
#: the naming rule its derived remedy names.
TOOLS = {
    "scaffold": {"command": (SCAFFOLD,), "who": "--elected-by",
                 "flag": "--project", "code": "scaffold-bad-id",
                 "names": "the assembly root and both legs",
                 "rule": NAME_RULE},
    "family": {"command": (FAMILY, "init"), "who": "--created-by",
               "flag": "--family", "code": "family-bad-id",
               "names": "the holder and, unless --work-dir is given, its "
                        "family folder",
               "rule": f"{NAME_RULE}, {NOT_A_HOLDER}"},
}
#: What a passed `--id` is told (#911): `PROJECT_ID_RE` in words, the same
#: sentence from both tools.
PASSED_REMEDY = ("Remediation: pass an --id of lowercase letters, digits and "
                 "hyphens, starting with a letter or digit.")
#: The remedy both tools gave a passed `--id` before #911.
OLD_PASSED_REMEDY = "Remediation: pass an explicit lowercase --id."


def derived(tool: str, unset: str) -> str:
    """How `tool` names a derived id's flag: `--id` given no value
    (`unset`), so the flag the id is derived from, lowercased."""
    return f"--id ({unset}, so {TOOLS[tool]['flag']} lowercased)"


def derived_remedy(tool: str) -> str:
    """The remedy `tool` gives for an id derived from its flag: change the
    flag, to a name the naming policy takes."""
    flag = TOOLS[tool]["flag"]
    return (f"Remediation: change {flag} to {TOOLS[tool]['rule']}. The id is "
            f"{flag} lowercased, and an explicit --id would not change "
            f"{flag}, which also names {TOOLS[tool]['names']}.")


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


def assert_named_as_passed(tool: str, stderr: str, value: str) -> None:
    """A passed `--id` gets none of a derived id's words, neither its label
    ("not given") nor its remedy ("change --project"), and keeps its
    sentence, value as typed, with the remedy that says what an id may hold
    (#911). The derived words are asked first, so a run that gives a passed
    id either of them fails on that word."""
    assert "not given" not in stderr
    assert f"change {TOOLS[tool]['flag']}" not in stderr
    assert OLD_PASSED_REMEDY not in stderr
    assert refusal(tool, f"--id {value!r} must match {PATTERN}",
                   PASSED_REMEDY) in stderr


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
def test_an_empty_id_is_a_passed_id_refused_by_name(tmp_path, tool):
    """#911 (U156): `--id ''` was read by its truth, so it planned the
    derived id and exited 0, and a script's `--id "$ID"` with `ID` unset
    went through without a word. It is a passed value now, held to the
    id's rule and refused by name, before `checked_value` would call it
    `unsafe-value`."""
    stderr = run_tool(tmp_path, tool, "NorthWind", "--id=")
    assert_named_as_passed(tool, stderr, "")
    assert "empty, so" not in stderr
    assert "unsafe-value" not in stderr


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("value",
                         ["Foo_Bar", "foo_bar", "-north", "north wind"])
def test_a_passed_bad_id_is_told_what_an_id_may_hold(tmp_path, tool, value):
    """#911 (U158): `foo_bar` is explicit and lowercase already, and was
    told to be both; its fault is the underscore. Each row is refused as
    the id it is not, a leading hyphen and a space included, which
    `checked_value` refused as `unsafe-value` before the id's own rule was
    asked."""
    stderr = run_tool(tmp_path, tool, "NorthWind", f"--id={value}")
    assert_named_as_passed(tool, stderr, value)
    assert "unsafe-value" not in stderr


@pytest.mark.parametrize("tool", TOOLS)
def test_an_id_the_id_rule_lets_through_still_meets_the_alphabet(
        tmp_path, tool):
    """`PROJECT_ID_RE.match` takes a trailing line break (`$` matches before
    one), so the id is still held to `checked_value`'s alphabet after its
    own rule, and refused as before."""
    stderr = run_tool(tmp_path, tool, "NorthWind", "--id=north" + chr(10))
    assert "REFUSED unsafe-value: --id is 'north" in stderr
    assert TOOLS[tool]["code"] not in stderr


def test_the_passed_remedy_is_the_id_rule_in_words():
    """The words say what `PROJECT_ID_RE` holds: lowercase letters, digits
    and hyphens, the first a letter or a digit."""
    assert PATTERN == "^[a-z0-9][a-z0-9-]*$"
    for good in ("a", "0", "north-wind", "9-lives", "a--b"):
        assert PROJECT_ID_RE.match(good), good
    for bad in ("", "-a", "A", "a_b", "a.b", "a b"):
        assert not PROJECT_ID_RE.match(bad), bad


def test_the_characters_a_derived_id_is_refused_for():
    """The rows below are every one of them; an empty list would pass
    vacuously, and a new one is a name the remedy has to be true of."""
    assert REFUSED_IN_AN_ID == ("+", ".", "/", "@", "_", "~")


@pytest.mark.parametrize("tool", TOOLS)
@pytest.mark.parametrize("passed", ["north-wind", "north_wind", ""])
@pytest.mark.parametrize("char", REFUSED_IN_AN_ID)
def test_a_name_whose_derived_id_is_refused_is_refused_by_the_naming_policy(
        tmp_path, tool, char, passed):
    """Why a derived id's remedy is its flag's and not `--id`'s: the naming
    policy reads the name itself and refuses every one whose lowercase is no
    id, so a `--id` that is an id only meets that refusal. Run with one, so
    this is the run the old remedy led to. And the refusal states the rule
    the derived remedy names, in the same words.

    A REFUSED NAME SPEAKS FIRST, WHATEVER THE ID (#911, U159): with a
    passed id that is no id either (`north_wind`, `''`) the id was refused
    first, and its remedy's retype met this refusal; now this one comes
    first and the id's does not appear."""
    name = f"North{char}Wind"
    stderr = run_tool(tmp_path, tool, name, f"--id={passed}")
    assert (f"REFUSED naming-unclassified: {name!r} matches no family in the "
            "naming policy") in stderr
    assert TOOLS[tool]["rule"] in stderr
    assert TOOLS[tool]["code"] not in stderr
    assert PASSED_REMEDY not in stderr


def test_a_form_no_assembly_root_has_speaks_before_a_passed_id(tmp_path):
    """The scaffold's half (#911): a `--project` whose form the policy
    decides by its characters alone and which is no assembly root,
    `Foo-Install`, is refused as `naming-role-mismatch` before a passed id
    that is no id, as it is after a good one; no `--id` mends it."""
    for passed in ("foo_bar", "foo-bar"):
        stderr = run_tool(tmp_path / passed, "scaffold", "Foo-Install",
                          f"--id={passed}")
        assert ("REFUSED naming-role-mismatch: 'Foo-Install' classifies as "
                "install") in stderr
        assert "scaffold-bad-id" not in stderr


@pytest.mark.parametrize("name", ["openGlass", "MedxGlass"])
def test_a_name_the_scaffold_takes_leaves_the_passed_id_refused(tmp_path,
                                                                name):
    """THE CONTROL: a neutral product may be an assembly root, and a
    descendant form's role turns on what the project declares, which is
    read later; neither is refused early, so the passed id is."""
    stderr = run_tool(tmp_path, "scaffold", name, "--id=foo_bar")
    assert_named_as_passed("scaffold", stderr, "foo_bar")
    assert "naming-" not in stderr


def test_a_name_no_holder_can_have_speaks_before_a_passed_id(tmp_path):
    """`init` holds `--family` to the holder's form whole, so a name that
    classifies as another form, `openGlass`, is refused as
    `naming-not-a-family` before a passed id that is no id (#911)."""
    stderr = run_tool(tmp_path, "family", "openGlass", "--id=foo_bar")
    assert ("REFUSED naming-not-a-family: 'openGlass' classifies as "
            "neutral-product") in stderr
    assert "family-bad-id" not in stderr


def test_init_s_derived_remedy_rules_out_what_naming_not_a_family_refuses(
        tmp_path):
    """#911 (U162): `--family open_glass` was told to change `--family` to
    one CamelCase token, and `openGlass`, which is one, was then refused as
    `naming-not-a-family`. The remedy names the two forms no holder can be
    declared as, in that refusal's own words, and the retype it ruled out
    is still refused there."""
    stderr = run_tool(tmp_path, "family", "open_glass")
    assert refusal(
        "family",
        f"{derived('family', 'not given')} is 'open_glass', which must match "
        f"{PATTERN}",
        derived_remedy("family")) in stderr
    assert NOT_A_HOLDER in derived_remedy("family")
    retyped = run_tool(tmp_path / "retyped", "family", "openGlass")
    assert "REFUSED naming-not-a-family: 'openGlass' " in retyped
    assert "An `open<Product>` or `<X>-Install` name" in retyped
