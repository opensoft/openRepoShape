# SPDX-License-Identifier: Apache-2.0
"""A project's own `neutral_product_pins:` or a leg's `naming.referent_chain:`
that is not a list is a FINDING in every validator that reads it, in one
sentence, and never a traceback (#443).

FOUR ITERATIONS ASKED NOTHING OF WHAT THEY ITERATED, each `for x in (value or
[])`: the naming gate's `_pins_from_project` and `_chain_from_leg`,
`validate-manifest.py`'s `_declared_pins` and `validate-pins.py`'s
`PinSources`. So `5`, `true` or `1.5` ended each in `TypeError: 'int' object
is not iterable`, exit 1 -- `validate-manifest.py` one line before its own
`manifest-neutral-product-pins` finding for that value -- and `make validate`
stopped in the naming gate's traceback, its first command. A scalar
`openXdox` was read as the characters `X`, `d`, `e`, `n`, `o`, `p`, `x`: the
naming gate classified and exited 0, and `validate-pins.py` refused
`neutral-pin-missing` for a pin on `'o'`. A mapping in either field was read
as its keys. Since #557 the doctor answered the naming gate's crash `CANNOT
ANSWER`, exit 3, which outranked the manifest's own finding.

NOW each reader takes a value that is not a list as declaring nothing (a
string is still one link of a chain, as `validate-manifest.py`'s
`_recorded_chain` has always read it), and each validator that reads the
field says `validate-manifest.py`'s own sentence for it:

    FINDING manifest-neutral-product-pins: neutral_product_pins is <value>,
      expected a list of neutral product names
    FINDING naming-referent-chain: leg '<role>': referent_chain is <value>,
      expected a list of neutral-product names

THE HARNESS is `tests/test_manifest_validator.py`'s (`edit`, the scaffolded
assembly leg's `naming:` block, and conftest's `project`) for the gates, as a
project runs them from its root, and `tests/test_shape_doctor.py`'s session
standard for the doctor. Entries inside a list that are not names (`[5]`,
`[[a]]`) were not examined by #443 and nothing here pins them.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

import pytest

from conftest import REPO, load_without_bytecode, run_script
from test_manifest_validator import ASSEMBLY_NAMING, edit
#: The doctor's session standard and the project scaffolded from it, from the
#: module that owns them: a second way of building either would test a
#: different one.
from test_shape_doctor import (  # noqa: F401
    doctor, rows_of, scaffolded_here, standard,
)

#: The three gates `make validate` runs, in its order, as it runs them: the
#: project's own copies, from the assembly root.
GATES = {
    "naming": ("scripts/validate-repository-naming.py", "--project",
               "project.yaml"),
    "manifest": ("scripts/validate-manifest.py",),
    "pins": ("scripts/validate-pins.py",),
}

#: Every value the issue measured that is not a list, as `(id, the YAML
#: spelling, what the parser makes of it)`.
NOT_A_LIST = [
    ("number", "5", 5),
    ("true", "true", True),
    ("float", "1.5", 1.5),
    ("scalar-string", "openXdox", "openXdox"),
    ("mapping", "{a: b}", {"a": "b"}),
    ("zero", "0", 0),
    ("false", "false", False),
    ("empty-string", "''", ""),
]

#: The two strings are a chain's one link and its empty record, as
#: `_recorded_chain` reads them, so neither is a finding for a chain.
CHAIN_NOT_A_LIST = [row for row in NOT_A_LIST
                    if not isinstance(row[2], str)]


def pins_said(value) -> str:
    """`validate-manifest.py`'s sentence for the pins, whole."""
    return ("FINDING manifest-neutral-product-pins: neutral_product_pins is "
            f"{value!r}, expected a list of neutral product names\n")


def chain_said(value, role: str = "assembly") -> str:
    """`validate-manifest.py`'s sentence for a leg's chain, the assembly
    leg's unless `role` says another, as that gate names the leg."""
    return (f"FINDING naming-referent-chain: leg {role!r}: referent_chain "
            f"is {value!r}, expected a list of neutral-product names\n")


def spelled_as(key: str, spelled: str) -> str:
    """`key: <spelled>`, and `key:` alone, which is null, for `""`."""
    return f"{key}: {spelled}" if spelled else f"{key}:"


def set_pins(project, spelled: str | None) -> None:
    """`neutral_product_pins: <spelled>`, or no such key for None."""
    if spelled is None:
        edit(project, "\nneutral_product_pins: []\n", "\n")
    else:
        edit(project, "neutral_product_pins: []",
             spelled_as("neutral_product_pins", spelled))


#: The spec leg's `naming:` block, as the scaffold writes it: the leg a chain
#: is recorded on is named in the sentence by this `role:`.
SPEC_NAMING = ("    naming:\n"
               "      form: project-leg\n"
               "      role: spec\n"
               "      also_matches: []\n")


def set_chain(project, spelled: str, naming: str = ASSEMBLY_NAMING) -> None:
    """A leg's `naming:` block, the assembly leg's unless `naming` says
    another, recording `referent_chain:`."""
    edit(project, naming,
         naming + "      " + spelled_as("referent_chain", spelled) + "\n")


def gate(project, which: str) -> subprocess.CompletedProcess:
    script, *args = GATES[which]
    return run_script(project / script, *args, cwd=project)


def assert_said_once(result, said: str) -> None:
    """Exit 1, the sentence once, and no traceback."""
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "Traceback" not in out, out
    assert result.stderr.count(said) == 1, out


# --- the readers, on the pure functions: nothing is read as characters ------

@pytest.fixture(scope="module")
def readers():
    """The naming gate and the manifest gate as modules, loaded from this
    checkout. Each puts its own directory on `sys.path` as it loads; that is
    put back, so no later test imports from a template directory."""
    saved = list(sys.path)
    try:
        naming = load_without_bytecode(
            REPO / "scripts" / "validate-repository-naming.py",
            "naming_gate_443")
        manifest = load_without_bytecode(
            REPO / "templates" / "assembly-root" / "scripts"
            / "validate-manifest.py", "manifest_gate_443")
    finally:
        sys.path[:] = saved
    return naming, manifest


@pytest.mark.parametrize("value", [row[2] for row in NOT_A_LIST],
                         ids=[row[0] for row in NOT_A_LIST])
def test_pins_that_are_not_a_list_declare_nothing_and_are_said_alike(
        readers, value):
    """A scalar `openXdox` is no pin on `X`, `d`, `e`, `n`, `o`, `p`, `x`,
    a mapping no pin on its key, and `5` no `TypeError`: both readers
    declare nothing, and the naming gate's finding is the manifest gate's,
    word for word."""
    naming, manifest = readers
    data = {"neutral_product_pins": value}
    assert naming._pins_from_project(data) == set()
    assert manifest._declared_pins(data) == set()
    said = ["FINDING " + line for line in naming._pins_field_findings(data)]
    assert said == manifest._neutral_product_pins_type_finding(data)
    assert said == [pins_said(value).rstrip("\n")]


@pytest.mark.parametrize("value", [row[2] for row in CHAIN_NOT_A_LIST],
                         ids=[row[0] for row in CHAIN_NOT_A_LIST])
def test_a_chain_that_is_not_a_list_records_nothing_and_is_said_alike(
        readers, value):
    """The naming gate's `_chain_from_leg` is `_recorded_chain` rule for
    rule: `5` no `TypeError`, and `{a: b}` no chain of the link `a`."""
    naming, manifest = readers
    leg = {"role": "assembly", "naming": {"referent_chain": value}}
    assert naming._chain_from_leg(leg) == ()
    assert manifest._recorded_chain(leg["naming"]) == ()
    said = ["FINDING " + line for line in naming._chain_field_findings(leg)]
    assert said == manifest._naming_chain_field_finding("assembly",
                                                        leg["naming"])
    assert said == [chain_said(value).rstrip("\n")]


@pytest.mark.parametrize("value,pins,chain", [
    pytest.param(None, set(), (), id="null"),
    pytest.param([], set(), (), id="empty-list"),
    pytest.param(["openXdox"], {"openXdox"}, ("openXdox",), id="one-name"),
    pytest.param("openXdox", None, ("openXdox",), id="one-link-string"),
    pytest.param("", None, (), id="empty-string-chain"),
])
def test_what_is_a_list_or_absent_reads_as_it_always_did(readers, value,
                                                         pins, chain):
    """THE OTHER SIDE: null and an empty list declare nothing, a list of
    names declares them, and a chain recorded as one string is that one
    link, with no finding from either gate. (`pins` None: a string is not a
    pin list, and the rows above hold that.)"""
    naming, manifest = readers
    if pins is not None:
        data = {"neutral_product_pins": value}
        assert naming._pins_from_project(data) == pins
        assert manifest._declared_pins(data) == pins
        assert naming._pins_field_findings(data) == []
        assert manifest._neutral_product_pins_type_finding(data) == []
    leg = {"role": "assembly", "naming": {"referent_chain": value}}
    assert naming._chain_from_leg(leg) == chain
    assert manifest._recorded_chain(leg["naming"]) == chain
    assert naming._chain_field_findings(leg) == []
    assert manifest._naming_chain_field_finding("assembly",
                                                leg["naming"]) == []


# --- the gates, as `make validate` runs them --------------------------------

@pytest.mark.parametrize("which", ["naming", "manifest", "pins"])
@pytest.mark.parametrize("spelled,value", [row[1:] for row in NOT_A_LIST],
                         ids=[row[0] for row in NOT_A_LIST])
def test_each_gate_says_pins_that_are_not_a_list_in_one_sentence(
        project, which, spelled, value):
    """`neutral_product_pins: <not a list>` is `manifest-neutral-product-
    pins`, exit 1, from each of the three gates: no `TypeError`, no pin on
    `'o'` refused as `neutral-pin-missing`, and `0`, `false` and `''` no
    longer an empty list to two of them while the third found them."""
    set_pins(project, spelled)
    result = gate(project, which)
    assert_said_once(result, pins_said(value))
    assert "neutral-pin-missing" not in result.stderr, result.stderr


@pytest.mark.parametrize("which", ["naming", "manifest"])
@pytest.mark.parametrize("spelled,value",
                         [row[1:] for row in CHAIN_NOT_A_LIST],
                         ids=[row[0] for row in CHAIN_NOT_A_LIST])
def test_each_gate_that_reads_a_chain_says_one_that_is_not_a_list(
        project, which, spelled, value):
    """A leg's `naming.referent_chain: <not a list>` is
    `naming-referent-chain`, exit 1, from the naming gate as from the
    manifest gate, naming the leg by its role, as that gate does."""
    set_chain(project, spelled)
    assert_said_once(gate(project, which), chain_said(value))


@pytest.mark.parametrize("which", ["naming", "manifest"])
def test_a_chain_on_the_spec_leg_is_said_with_the_spec_leg_named(project,
                                                                 which):
    """The sentence names the leg the chain is recorded on, by its declared
    `role:`, in both gates: `5` on the SPEC leg says `leg 'spec'`, not the
    assembly leg every other case here records it on."""
    set_chain(project, "5", SPEC_NAMING)
    assert_said_once(gate(project, which), chain_said(5, "spec"))


def test_the_pins_sentence_is_said_before_the_chain_line_it_explains(project):
    """THE ORDER a person reads it in (#443): a scalar `openXdox` in the pins
    declares no pin, so a chain that begins at `openXdox` is said broken `(it
    begins at openXdox, which is not in this project's neutral_product_pins:
    ...)`. That line reads as false to someone who wrote
    `neutral_product_pins: openXdox`, unless the sentence before it says
    that the field is not a list. The pins sentence is said first, so it is."""
    edit(project, 'repository: testorg/Atlas\n    path: "."',
         'repository: testorg/codexDox\n    path: "."')
    set_pins(project, "openXdox")
    edit(project, ASSEMBLY_NAMING,
         ASSEMBLY_NAMING.replace("also_matches: []",
                                 "also_matches: [domain-descendant]")
         + "      referent_chain: [openXdox, openDox]\n")
    result = gate(project, "naming")
    said = pins_said("openXdox")
    assert_said_once(result, said)
    broken = "the declared chain openXdox → openDox is broken"
    assert broken in result.stderr, result.stderr
    assert result.stderr.index(said) < result.stderr.index(broken), \
        result.stderr


#: `(field, YAML spelling or None for no key, {gate: exit})`: what main
#: answered for each (#443's controls, measured at 8f453d0e), and still does.
#: `[openXdox]` declares a pin whose file the scaffold never wrote, so
#: `validate-pins.py` refuses it, as ever, by its name.
CONTROLS = [
    pytest.param("pins", None, {"naming": 0, "manifest": 0, "pins": 0},
                 id="pins-absent"),
    pytest.param("pins", "", {"naming": 0, "manifest": 0, "pins": 0},
                 id="pins-null"),
    pytest.param("pins", "[openXdox]", {"naming": 0, "manifest": 0, "pins": 2},
                 id="pins-one-name"),
    pytest.param("chain", "[]", {"naming": 0, "manifest": 0, "pins": 0},
                 id="chain-empty-list"),
    pytest.param("chain", "", {"naming": 0, "manifest": 0, "pins": 0},
                 id="chain-null"),
    pytest.param("chain", "openXdox", {"naming": 0, "manifest": 0, "pins": 0},
                 id="chain-one-link-string"),
    pytest.param("chain", "''", {"naming": 0, "manifest": 0, "pins": 0},
                 id="chain-empty-string"),
    pytest.param("chain", "[openXdox]",
                 {"naming": 0, "manifest": 0, "pins": 0}, id="chain-one-link"),
]


@pytest.mark.parametrize("field,spelled,exits", CONTROLS)
def test_what_is_a_list_or_absent_keeps_its_answer_in_every_gate(
        project, field, spelled, exits):
    """No gate says either sentence over a value that is a list, is absent
    or null, or is a chain's one-link string, and each exits as it did."""
    if field == "pins":
        set_pins(project, spelled)
    else:
        set_chain(project, spelled)
    results = {which: gate(project, which) for which in exits}
    for which, code in exits.items():
        result = results[which]
        out = result.stdout + result.stderr
        assert result.returncode == code, (which, out)
        assert "Traceback" not in out, (which, out)
        assert "manifest-neutral-product-pins" not in out, (which, out)
        assert "naming-referent-chain" not in out, (which, out)
    if exits["pins"] == 2:
        assert ("REFUSED neutral-pin-missing: project.yaml declares a pin on "
                "'openXdox' but contracts/openxdox-pin.yaml does not exist"
                in results["pins"].stderr), results["pins"].stderr


MAKE = shutil.which("make")


@pytest.mark.skipif(MAKE is None or sys.platform == "win32",
                    reason="`make validate` needs make and a POSIX shell for "
                           "its recipe")
@pytest.mark.parametrize("field", ["pins", "chain"])
def test_make_validate_stops_at_its_first_command_with_the_sentence(
        project, field):
    """`make validate` runs the naming gate first and stops at the first
    that fails. It stopped there in a `TypeError`; it still stops there,
    exit 2 (make's code for a failed recipe), on the sentence, and the
    manifest gate is never started."""
    if field == "pins":
        set_pins(project, "5")
        said = pins_said(5)
    else:
        set_chain(project, "5")
        said = chain_said(5)
    proc = subprocess.run([MAKE, "validate", f"PYTHON={sys.executable}"],
                          cwd=str(project), capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 2, out
    assert said in proc.stderr, out
    assert "Traceback" not in out, out
    assert "scripts/validate-repository-naming.py --project" in proc.stdout
    assert "scripts/validate-manifest.py" not in proc.stdout, out


# --- the doctor: a finding in each row that reads the field, not a crash -----

@pytest.fixture
def doctored(scaffolded_here, tmp_path):
    """A private copy of the project the doctor's standard scaffolded."""
    target = tmp_path / "Atlas"
    shutil.copytree(scaffolded_here["clone"], target, symlinks=True)
    return target


@pytest.mark.parametrize("field,spelled,value,reading", [
    pytest.param("pins", "5", 5, ("naming", "manifest", "pins"),
                 id="pins-number"),
    pytest.param("pins", "openXdox", "openXdox",
                 ("naming", "manifest", "pins"), id="pins-scalar-string"),
    pytest.param("chain", "5", 5, ("naming", "manifest"), id="chain-number"),
])
def test_the_doctor_quotes_the_sentence_in_every_row_that_reads_the_field(
        standard, doctored, field, spelled, value, reading):
    """`5` in either field was `CANNOT ANSWER`, exit 3: the standard's
    naming script crashed, and that outranked the manifest's own finding.
    Now each row whose gate reads the field is a FINDING quoting the
    sentence, none of them a crash, and the verdict is INVALID, exit 1. The
    string's `pins` row was the `neutral-pin-missing` refusal for `'o'`."""
    if field == "pins":
        set_pins(doctored, spelled)
        said = pins_said(value).rstrip("\n")
    else:
        set_chain(doctored, spelled)
        said = chain_said(value).rstrip("\n")
    result = doctor(standard, doctored, "--json")
    payload = json.loads(result.stdout)
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["exit"] == 1
    assert payload["verdict"] == f"INVALID ({', '.join(reading)})", payload
    rows = rows_of(result)
    for which in reading:
        row = rows[which]
        assert row["status"] == "FINDING", row
        assert not row["detail"].get("crashed"), row
        assert said in row["reason"], row
        assert "TypeError" not in row["reason"], row
        assert "crashed" not in row["reason"], row
    for which in {"naming", "manifest", "pins"} - set(reading):
        assert rows[which]["status"] == "ok", rows[which]
