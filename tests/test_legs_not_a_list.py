# SPDX-License-Identifier: Apache-2.0
"""A project manifest's `legs:` that is not a list is a FINDING in every gate
that reads it, a chain link or a declared pin that is not a name is a FINDING,
the naming gate never waits on stdin under `--project`, and a name that is not
UTF-8 reaches `naming-unclassified` (#714).

`legs:` WAS ITERATED AS IT STOOD, `value or []`: the naming gate's
`_project_leg_chains` and `_targets_from_project`, and `validate-pins.py`'s
`_load_legs_to_check`. So `5` or `true` ended both in `TypeError: 'int' object
is not iterable`, exit 1, where `validate-manifest.py` said `legs is missing or
empty`, which `5` is not. A scalar `openXdox` was walked one character at a
time: no leg was a target, so the naming gate read names from stdin, and on a
pipe left open (a parent that holds it) it WAITED; `validate-pins.py`
refused `manifest-no-legs` with the lockstep remedy, `git submodule update`.
NOW the three gates say one sentence, exit 1:

    FINDING manifest-legs: legs is <value>, expected a list of `role:`,
      `repository:` and `path:` mappings

and under `--project` the naming gate reads no stdin at all, whatever `legs:`
holds, so absent, null, `[]` and `[5]` cannot wait either. A manifest that
names no leg (absent, null or `[]`) is `validate-manifest.py`'s `legs is
missing or empty` in the naming gate too, exit 1 (lane 4's ruling), and not
`REFUSED naming-no-target`, whose offers of `--project` and of names on stdin
were no way out under `--project`. Without `--project` that refusal stands.

AN ENTRY THAT IS NOT A NAME (#443 left `[5]` and `[[a]]` unexamined) was read
with `str()`: `[5]` was the pin or the link `'5'`, and a link holding ESC,
`referent_chain: "\\x1b[31mRED"`, exited 0 in the naming gate and in
`validate-manifest.py`. NOW `_not_a_name` is one rule in both files: text
(`validate-pins.py`'s `neutral-pin-entry-malformed` asks it), not blank, and
`str.isprintable`. A pin entry that is not a name declares nothing and the
others still do; a chain holding such a link records no chain, as one that is
not a list records none. Each is said, with why:

    FINDING manifest-neutral-product-pins: neutral_product_pins entry <entry>
      is not a neutral product name: <why>
    FINDING naming-referent-chain: leg '<role>': referent_chain link <link>
      is not a neutral-product name: <why>

A NAME THAT IS NOT UTF-8 (`Atl\\xffas`) ended `--explain` and the plain
listing in a `UnicodeEncodeError` on a strict stdout (`PYTHONIOENCODING=utf-8`,
which the doctor gives its children), and a read from stdin in a
`UnicodeDecodeError`. NOW stdout escapes what it cannot encode, as
`validate-pins.py`'s `_emit_report` does, and stdin reads the byte as argv
does, so the name is `Atl\\udcffas` wherever it is printed and reaches
`naming-unclassified`.

THE HARNESS is `tests/test_non_list_project_fields.py`'s (#443): the three
gates as a project runs them from its root, the field editors, and its
`readers` for the pure functions.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from conftest import REPO, run_script
from test_manifest_validator import edit
from test_non_list_project_fields import (  # noqa: F401
    GATES, NOT_A_LIST, SPEC_NAMING, assert_said_once, chain_said, gate,
    readers, set_chain, set_pins, spelled_as,
)

NAMING_SCRIPT = REPO / "scripts" / "validate-repository-naming.py"

#: The scaffold writes `legs:` as the manifest's last block.
LEGS_START = "\nlegs:\n"

#: How long a gate may take with stdin a pipe nobody writes or closes before
#: the test calls it a wait. A run here takes well under a second.
STDIN_WAIT = 30

NOT_TEXT = "it is not text"
BLANK = "it is blank"
NOT_PRINTABLE = "it holds a character that is not printable"
ESC = "\x1b[31mRED"
#: The issue's name that is not UTF-8, as argv reads the byte `\xff`.
NOT_UTF8 = "Atl\udcffas"


#: `validate-manifest.py`'s sentence for a `legs:` that names no leg.
LEGS_MISSING = "FINDING manifest-legs: legs is missing or empty\n"


def legs_said(value) -> str:
    """`validate-manifest.py`'s sentence for `legs:`, whole."""
    return (f"FINDING manifest-legs: legs is {value!r}, expected a list of "
            "`role:`, `repository:` and `path:` mappings\n")


def entry_said(field: str, entry, why: str, role: str = "assembly") -> str:
    """The sentence for a pin entry or a chain link that is not a name."""
    if field == "pins":
        return (f"FINDING manifest-neutral-product-pins: neutral_product_pins "
                f"entry {entry!r} is not a neutral product name: {why}\n")
    return (f"FINDING naming-referent-chain: leg {role!r}: referent_chain "
            f"link {entry!r} is not a neutral-product name: {why}\n")


def set_legs(project, spelled: str | None) -> None:
    """`legs: <spelled>` in place of the scaffold's three legs, or no
    `legs:` key for None."""
    manifest = project / "project.yaml"
    head, sep, rest = manifest.read_text().partition(LEGS_START)
    assert sep, "fixture drift: no `legs:` block in project.yaml"
    assert all(line.startswith("  ") or not line
               for line in rest.splitlines()), \
        "fixture drift: `legs:` is not the manifest's last block"
    manifest.write_text(head + "\n" + ("" if spelled is None else
                                       spelled_as("legs", spelled) + "\n"))


def naming_gate_beside_an_open_pipe(project) -> subprocess.CompletedProcess:
    """The naming gate as `make validate` runs it, with stdin a pipe that is
    open and never written: what a parent holding the pipe gives it. A gate
    that reads it waits until the pipe closes, so the test closes it only
    after `STDIN_WAIT` and calls that a failure."""
    script, *args = GATES["naming"]
    read_end, write_end = os.pipe()
    try:
        return subprocess.run([sys.executable, str(project / script), *args],
                              cwd=str(project), stdin=read_end,
                              capture_output=True, text=True,
                              timeout=STDIN_WAIT, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail(f"the naming gate waited {STDIN_WAIT}s on a stdin left "
                    "open under --project")
    finally:
        os.close(read_end)
        os.close(write_end)


# --- legs: that is not a list -----------------------------------------------

@pytest.mark.parametrize("which", ["naming", "manifest", "pins"])
@pytest.mark.parametrize("spelled,value", [row[1:] for row in NOT_A_LIST],
                         ids=[row[0] for row in NOT_A_LIST])
def test_each_gate_says_legs_that_are_not_a_list_in_one_sentence(
        project, which, spelled, value):
    """`legs: <not a list>` is `manifest-legs`, exit 1, from each of the
    three gates, in words true of the value: no `TypeError`, no
    `naming-no-target`, no `manifest-no-legs` and its `git submodule update`
    remedy, and no "missing or empty" for `5`."""
    set_legs(project, spelled)
    result = gate(project, which)
    assert_said_once(result, legs_said(value))
    for wrong in ("naming-no-target", "manifest-no-legs",
                  "git submodule update", "missing or empty"):
        assert wrong not in result.stderr, result.stderr


@pytest.mark.parametrize("spelled,said", [
    pytest.param("openXdox", legs_said("openXdox"), id="scalar-string"),
    pytest.param("5", legs_said(5), id="number"),
    pytest.param("{a: b}", legs_said({"a": "b"}), id="mapping"),
    pytest.param(None, LEGS_MISSING, id="absent"),
    pytest.param("", LEGS_MISSING, id="null"),
    pytest.param("[]", LEGS_MISSING, id="empty-list"),
    pytest.param("[5]", "FINDING project.yaml: a leg has no `repository:`",
                 id="a-leg-that-is-not-a-mapping"),
])
def test_the_naming_gate_never_waits_on_a_stdin_left_open(project, spelled,
                                                          said):
    """THE WAIT (L4-141). Under `--project` stdin is never read, so a pipe
    nobody writes or closes cannot hold the gate, whatever `legs:` is, and
    every manifest with no target is a finding, exit 1: `[5]` was
    `naming-no-target`, which dropped its finding, and absent, null and `[]`
    were that refusal, which offered `--project` and names on stdin to a run
    that had passed `--project`. They are `validate-manifest.py`'s `legs is
    missing or empty` now (lane 4's ruling)."""
    set_legs(project, spelled)
    result = naming_gate_beside_an_open_pipe(project)
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "Traceback" not in out, out
    assert result.stderr.count(said) == 1, out
    assert "naming-no-target" not in result.stderr, out


@pytest.mark.parametrize("which", ["naming", "manifest"])
@pytest.mark.parametrize("spelled", [
    pytest.param(None, id="absent"),
    pytest.param("", id="null"),
    pytest.param("[]", id="empty-list"),
])
def test_a_manifest_that_names_no_leg_is_said_alike(project, which, spelled):
    """`legs:` absent, null or `[]` is one sentence, exit 1, from the
    naming gate as from the manifest gate."""
    set_legs(project, spelled)
    assert_said_once(gate(project, which), LEGS_MISSING)


def test_without_project_no_name_is_still_refused_naming_no_target(tmp_path):
    """THE OTHER SIDE of the ruling: with no `--project`, no name and
    nothing on stdin, the run is refused `naming-no-target`, exit 2, in its
    own words, as it always was."""
    result = run_script(NAMING_SCRIPT, cwd=tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr == (
        "REFUSED naming-no-target: no names given. Pass names, "
        "`--project project.yaml`, or names on stdin.\n"), result.stderr


def test_names_on_stdin_are_read_without_project_and_never_with_it(project):
    """THE OTHER SIDE: a name piped in is classified as ever when no other
    source names one, and is not read under `--project`, where a manifest
    with no leg is `legs is missing or empty` and the name is not listed."""
    alone = run_script(NAMING_SCRIPT, cwd=project, input="openChart\n")
    assert alone.returncode == 0, alone.stdout + alone.stderr
    assert "openChart" in alone.stdout, alone.stdout
    set_legs(project, "[]")
    script, *args = GATES["naming"]
    piped = run_script(project / script, *args, cwd=project,
                       input="openChart\n")
    assert_said_once(piped, LEGS_MISSING)
    assert "naming-no-target" not in piped.stderr, piped.stderr
    assert "openChart" not in piped.stdout, piped.stdout


def test_validate_pins_still_checks_the_shape_and_neutral_pins(project):
    """A `legs:` that is not a list checks no leg, and `validate-pins.py`
    still checks the shape pin's copies and the neutral-product pins: a pins
    field that is not a list beside it is said too, once each."""
    set_legs(project, "5")
    set_pins(project, "5")
    result = gate(project, "pins")
    assert_said_once(result, legs_said(5))
    assert result.stderr.count(
        "FINDING manifest-neutral-product-pins: neutral_product_pins is 5, "
        "expected a list of neutral product names\n") == 1, result.stderr
    assert "copied shape file(s) match their digests" in result.stdout, \
        result.stdout


# --- an entry that is not a name ---------------------------------------------

#: `(entry, why)`: what `_not_a_name` says of each, in both files.
NOT_NAMES = [
    pytest.param(5, NOT_TEXT, id="number"),
    pytest.param(True, NOT_TEXT, id="true"),
    pytest.param(None, NOT_TEXT, id="null"),
    pytest.param(["a"], NOT_TEXT, id="list"),
    pytest.param({"a": "b"}, NOT_TEXT, id="mapping"),
    pytest.param("", BLANK, id="empty"),
    pytest.param("  ", BLANK, id="spaces"),
    pytest.param(ESC, NOT_PRINTABLE, id="esc"),
    pytest.param(NOT_UTF8, NOT_PRINTABLE, id="lone-surrogate"),
    pytest.param("open‮Xdox", NOT_PRINTABLE, id="bidi-control"),
    pytest.param("open\nXdox", NOT_PRINTABLE, id="newline"),
]


@pytest.mark.parametrize("entry,why", NOT_NAMES)
def test_an_entry_that_is_not_a_name_is_dropped_and_said_alike(readers,
                                                               entry, why):
    """Both readers drop a pin entry that is not a name and keep the rest,
    record no chain where a link is not a name, and say each in one
    sentence, word for word."""
    naming, manifest = readers
    assert naming._not_a_name(entry) == manifest._not_a_name(entry) == why
    data = {"neutral_product_pins": ["openXdox", entry]}
    assert naming._pins_from_project(data) == {"openXdox"}
    assert manifest._declared_pins(data) == {"openXdox"}
    said = ["FINDING " + line for line in naming._pins_field_findings(data)]
    assert said == manifest._neutral_product_pins_type_finding(data)
    assert said == [entry_said("pins", entry, why).rstrip("\n")]
    leg = {"role": "assembly",
           "naming": {"referent_chain": ["openXdox", entry, "openDox"]}}
    assert naming._chain_from_leg(leg) == ()
    assert manifest._recorded_chain(leg["naming"]) == ()
    said = ["FINDING " + line for line in naming._chain_field_findings(leg)]
    assert said == manifest._naming_chain_field_finding("assembly",
                                                        leg["naming"])
    assert said == [entry_said("chain", entry, why).rstrip("\n")]


@pytest.mark.parametrize("value,chain", [
    pytest.param(["openß", "öpenDox"], ("openß", "öpenDox"),
                 id="printable-letters-outside-ascii"),
    pytest.param("  ", (), id="blank-string-is-the-empty-record"),
    pytest.param(ESC, (), id="one-link-string-holding-esc"),
])
def test_a_name_is_printable_text_and_a_blank_string_records_nothing(
        readers, value, chain):
    """A letter outside ASCII is printable and part of a name; a blank
    string is the empty record a chain's `''` always was, no finding; and a
    one-link string holding ESC is that link, refused."""
    naming, manifest = readers
    leg = {"role": "assembly", "naming": {"referent_chain": value}}
    assert naming._chain_from_leg(leg) == chain
    assert manifest._recorded_chain(leg["naming"]) == chain
    found = naming._chain_field_findings(leg)
    assert ["FINDING " + line for line in found] == \
        manifest._naming_chain_field_finding("assembly", leg["naming"])
    assert bool(found) == (value == ESC), found


#: `(field, YAML spelling, the entry as read, why)`, the issue's own first.
ENTRIES_IN_A_GATE = [
    pytest.param("chain", '"\\x1b[31mRED"', ESC, NOT_PRINTABLE,
                 id="chain-one-link-string-esc"),
    pytest.param("chain", '["\\x1b[31mRED"]', ESC, NOT_PRINTABLE,
                 id="chain-esc"),
    pytest.param("chain", "[5]", 5, NOT_TEXT, id="chain-number"),
    pytest.param("chain", "[[a]]", ["a"], NOT_TEXT, id="chain-list"),
    pytest.param("chain", "[{a: b}]", {"a": "b"}, NOT_TEXT, id="chain-mapping"),
    pytest.param("chain", "[true]", True, NOT_TEXT, id="chain-true"),
    pytest.param("chain", "[openXdox, '']", "", BLANK, id="chain-empty-link"),
    pytest.param("pins", '["\\x1b[31mRED"]', ESC, NOT_PRINTABLE,
                 id="pins-esc"),
    pytest.param("pins", "[5]", 5, NOT_TEXT, id="pins-number"),
    pytest.param("pins", "[[a]]", ["a"], NOT_TEXT, id="pins-list"),
    pytest.param("pins", "[null]", None, NOT_TEXT, id="pins-null"),
    pytest.param("pins", "['']", "", BLANK, id="pins-empty"),
]


@pytest.mark.parametrize("which", ["naming", "manifest"])
@pytest.mark.parametrize("field,spelled,entry,why", ENTRIES_IN_A_GATE)
def test_each_gate_that_reads_the_field_says_an_entry_that_is_not_a_name(
        project, which, field, spelled, entry, why):
    """L4-142: a chain link or a declared pin that is not a name is a
    finding, exit 1, from the naming gate as from the manifest gate, where
    each exited 0; and an ESC in it never reaches the terminal raw."""
    if field == "pins":
        set_pins(project, spelled)
    else:
        set_chain(project, spelled)
    result = gate(project, which)
    assert_said_once(result, entry_said(field, entry, why))
    assert "\x1b" not in result.stdout + result.stderr


@pytest.mark.parametrize("which", ["naming", "manifest"])
@pytest.mark.parametrize("spelled", [
    pytest.param("[openß]", id="printable-letter-outside-ascii"),
    pytest.param("'  '", id="blank-string"),
])
def test_a_chain_of_names_or_a_blank_string_keeps_its_answer(project, which,
                                                             spelled):
    """THE OTHER SIDE, in the gates: neither is a finding, and each gate
    exits 0 as it did."""
    set_chain(project, spelled)
    result = gate(project, which)
    out = result.stdout + result.stderr
    assert result.returncode == 0, out
    assert "naming-referent-chain" not in out, out


@pytest.mark.parametrize("spelled,said", [
    pytest.param("5", chain_said(5, "code"), id="not-a-list"),
    pytest.param('"\\x1b[31mRED"', entry_said("chain", ESC, NOT_PRINTABLE,
                                              "code"), id="link-not-a-name"),
])
def test_the_chain_sentence_is_said_before_the_legs_other_finding(
        project, spelled, said):
    """L4-145, THE ORDER (#443's M6b): `_leg_target` says a leg's chain
    sentence before its other findings, as `validate-manifest.py` does. Here
    the spec leg is declared `code`, so the same leg has the declared-role
    finding too, and the chain sentence comes first."""
    edit(project, "  - role: spec\n    repository: testorg/Atlas-spec",
         "  - role: code\n    repository: testorg/Atlas-spec")
    set_chain(project, spelled, SPEC_NAMING)
    result = gate(project, "naming")
    assert_said_once(result, said)
    role = ("FINDING Atlas-spec: declared role 'code' but the name is the "
            "'spec' form of the project-leg family")
    assert role in result.stderr, result.stderr
    assert result.stderr.index(said) < result.stderr.index(role), \
        result.stderr


# --- a name that is not UTF-8 ------------------------------------------------

#: A strict UTF-8 stdout and stdin, as the doctor gives its children.
STRICT_UTF8 = {"PYTHONIOENCODING": "utf-8"}


def assert_not_utf8_is_unclassified(result) -> None:
    """Exit 1, no traceback, and the name spelled as `\\udcff` where it is
    printed: `naming-unclassified` on stderr."""
    out = result.stdout + result.stderr
    assert result.returncode == 1, out
    assert "Traceback" not in out, out
    assert "FINDING naming-unclassified: Atl\\udcffas\n" in result.stderr, out


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a name that is not UTF-8 reaches argv only as "
                           "bytes, which a Windows command line does not hold")
@pytest.mark.parametrize("flags", [
    pytest.param(("--explain",), id="explain"),
    pytest.param((), id="plain-listing"),
])
def test_a_name_that_is_not_utf8_prints_escaped_to_a_strict_stdout(
        tmp_path, flags):
    """L4-02: `--explain` and the plain listing ended in a
    `UnicodeEncodeError` on a strict stdout, where `--quiet` said
    `naming-unclassified`; now stdout writes the name escaped, as
    `validate-pins.py` writes what it cannot encode."""
    result = run_script(NAMING_SCRIPT, *flags, NOT_UTF8, cwd=tmp_path,
                        env=STRICT_UTF8)
    assert_not_utf8_is_unclassified(result)
    assert "Atl\\udcffas" in result.stdout, result.stdout


@pytest.mark.parametrize("flags", [
    pytest.param(("--quiet",), id="quiet"),
    pytest.param((), id="plain-listing"),
])
def test_a_name_on_stdin_that_is_not_utf8_reaches_naming_unclassified(
        tmp_path, flags):
    """L4-02: a strict stdin ended the run in a `UnicodeDecodeError`; now the
    byte is read as argv reads it, so the name is the one argv gives and
    reaches `naming-unclassified`."""
    names = tmp_path / "names"
    names.write_bytes(b"Atl\xffas\n")
    with names.open("rb") as stdin:
        result = run_script(NAMING_SCRIPT, *flags, cwd=tmp_path,
                            env=STRICT_UTF8, stdin=stdin)
    assert_not_utf8_is_unclassified(result)
