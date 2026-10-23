# SPDX-License-Identifier: Apache-2.0
"""A name that holds a character a terminal draws as nothing is spelled
(#1128).

`_shown` printed a name as it is wherever `str.isprintable` passed it, and
`_spelled_character` wrote such a character as it is. Unicode's
Default_Ignorable_Code_Point characters are drawn as nothing, and
`str.isprintable` passes 267 of them: 263 combining marks, among them
U+034F and the variation selectors, and four Hangul fillers, among them
U+3164. Git takes each in a branch or a path, so `plan` printed the branch
`ma<U+034F>in` as `main`; and `checked_value`'s `unsafe-value` refusal,
which spells the value with `repr`, printed U+3164 raw on stderr the same
way. RV1120 measured U+034F, U+3164 and U+FE0F reaching `plan`'s output raw
(#1120 issuecomment-6319321596, N1).

A default-ignorable character is spelled by its code point now, whatever
`str.isprintable` says of it: `` `ma\\u034fin` `` in a report, and
`'ma\\u034fin'` in the refusal. The table is Unicode's, written into
`repo_shape.py` (`DEFAULT_IGNORABLE_RANGES`), and is listed here again as
`DerivedCoreProperties.txt` lists it, line by line, so no row depends on the
Unicode data of the Python that runs it: CI runs 3.14 and the bench 3.12,
and their `unicodedata` differ.

THE CONTROLS. U+200B, U+2060 and U+180E are format characters, which
`str.isprintable` refuses, so they were spelled already; their rows pass on
main too, and say that the spelling of a character already spelled did not
move. So do the rows of a printable name: `feat/caf\\u00e9` and a name in
CJK print as they are.

`plan`'s `source` line prints the source's branch as it is on main; #1120,
which this change is stacked on, gives it `_shown`. The end-to-end rows read
the branch wherever `plan` names it: that line, the NOTE about a tracking
branch the source lacks, and the `unsafe-value` refusal of the default
tracking branch. On #1120 alone the `source` line printed `ma<U+034F>in` as
`(main)`, as RV1120 measured.

THE ROWS THAT PIN #1120 (#1128's items 2 and 3, from RV1120's review). A
printable branch outside ASCII, `feat/caf\\u00e9`, prints as it is; a branch
named `` `main` ``, backticks and all, is spelled; and the branch that is not
UTF-8 is spelled under a `utf-8:surrogateescape` stdout too, where main wrote
the byte 0xE9 itself to the terminal. #1120's code is right in each, and
each passes on #1120 alone: the rows keep it so. RV1120's mutants E
(`_spelled` for every branch outside ASCII) and N (`str.isprintable` alone,
with no backtick rule) passed every row #1120 has.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources,
                      make_source_repo, on_a_branch_that_is_not_utf_8)
from test_adopt_plan_source_branch_shown import (
    assert_branch_in_the_line, planned as planned_tracking_main, source_on)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402

PLAN_FILE = "adoption-plan.yaml"

#: The characters #1128 names, each with the escape it is spelled with.
#: The first three are default-ignorable characters `str.isprintable`
#: passes: a combining mark, a Hangul filler and a variation selector. The
#: last three are the controls: format characters `str.isprintable`
#: refuses, already spelled on main.
CHARACTERS = {
    "combining-grapheme-joiner": ("\u034f", "\\u034f"),
    "hangul-filler": ("\u3164", "\\u3164"),
    "variation-selector-16": ("\ufe0f", "\\ufe0f"),
    "zero-width-space": ("\u200b", "\\u200b"),
    "word-joiner": ("\u2060", "\\u2060"),
    "mongolian-vowel-separator": ("\u180e", "\\u180e"),
}
EACH_CHARACTER = pytest.mark.parametrize(
    ("char", "spelled"), list(CHARACTERS.values()), ids=list(CHARACTERS))

#: Default_Ignorable_Code_Point as Unicode 16.0.0's
#: `DerivedCoreProperties.txt` lists it, one line to an entry; 14.0.0 and
#: 17.0.0 list the same 27 lines, 4174 code points.
DERIVED_CORE_PROPERTIES = """
    00AD 034F 061C 115F..1160 17B4..17B5 180B..180D 180E 180F 200B..200F
    202A..202E 2060..2064 2065 2066..206F 3164 FE00..FE0F FEFF FFA0
    FFF0..FFF8 1BCA0..1BCA3 1D173..1D17A E0000 E0001 E0002..E001F
    E0020..E007F E0080..E00FF E0100..E01EF E01F0..E0FFF
""".split()


def listed(lines: list[str]) -> list[int]:
    """Every code point the lines name, in order."""
    points = []
    for line in lines:
        low, _, high = line.partition("..")
        points += range(int(low, 16), int(high or low, 16) + 1)
    return points


IGNORABLE = listed(DERIVED_CORE_PROPERTIES)

#: Names a terminal shows as they are, which print as they are: a printable
#: letter outside ASCII, and CJK. `feat/caf\u00e9` is #1128's.
PRINTABLE_NAMES = ["feat/caf\u00e9", "\u6a5f\u80fd/x", "main"]


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_shown_default_ignorables", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def escaped(code: int) -> str:
    """The code-point escape of `code`: the shortest of `\\xNN`, `\\uNNNN`
    and `\\UNNNNNNNN` that holds it, in lowercase hex, as the plan writes
    one and `repr` does."""
    for letter, digits in (("x", 2), ("u", 4), ("U", 8)):
        if code < 16 ** digits:
            return f"\\{letter}{code:0{digits}x}"
    raise AssertionError(code)


# --- the table ---------------------------------------------------------------

def test_the_table_is_unicodes():
    """`DEFAULT_IGNORABLE_RANGES` holds exactly the 4174 code points
    `DerivedCoreProperties.txt` lists, in ranges that neither overlap nor
    touch, so no line of the file was dropped when they were joined."""
    assert len(DERIVED_CORE_PROPERTIES) == 27
    assert len(IGNORABLE) == len(set(IGNORABLE)) == 4174
    ranges = repo_shape.DEFAULT_IGNORABLE_RANGES
    assert [low for low, _ in ranges] == sorted(low for low, _ in ranges)
    for (_, high), (low, _) in zip(ranges, ranges[1:]):
        assert high + 1 < low, (hex(high), hex(low))
    held = [code for low, high in ranges for code in range(low, high + 1)]
    assert held == IGNORABLE


def test_the_compiled_pattern_matches_the_table_and_nothing_else():
    """`DEFAULT_IGNORABLE`, the pattern every helper asks, matches exactly
    the code points of the table, over all 0x110000: not one more, not one
    fewer. The sweeps below take their expected value from the pattern, so a
    pattern that ran one past each range spelled the extra characters and
    passed every one of them (RV1171's N1, mutant M11); the table row above
    reads `DEFAULT_IGNORABLE_RANGES` and never the compiled pattern."""
    matched = [code for code in range(0x110000)
               if repo_shape.DEFAULT_IGNORABLE.match(chr(code))]
    assert matched == IGNORABLE


def test_every_default_ignorable_character_is_spelled(adopter):
    """Each of the 4174, between two letters, is spelled by `_shown` and by
    `_spelled_character` as its code-point escape, and never returned as it
    is. On main the 267 `str.isprintable` passes came back raw."""
    raw, misspelled = [], []
    for code in IGNORABLE:
        char = chr(code)
        shown = adopter._shown(f"ma{char}in")
        if char in shown or char in adopter._spelled_character(char):
            raw.append(f"U+{code:04X}")
        elif shown != f"`ma{escaped(code)}in`":
            misspelled.append(f"U+{code:04X}: {shown}")
    assert not raw, f"{len(raw)} returned as they are: {raw[:8]}"
    assert not misspelled, misspelled[:8]


def test_every_default_ignorable_character_is_escaped_in_a_refusal():
    """`checked_value` names the value it refuses as `repr` does, with each
    of the 4174 written as its code-point escape. On main `repr` wrote the
    267 `str.isprintable` passes as they are."""
    raw = []
    for code in IGNORABLE:
        with pytest.raises(repo_shape.Refusal) as refused:
            repo_shape.checked_value("--tracking-branch", f"ma{chr(code)}in")
        assert refused.value.code == "unsafe-value"
        if (chr(code) in refused.value.detail
                or f"'ma{escaped(code)}in'" not in refused.value.detail):
            raw.append(f"U+{code:04X}")
    assert not raw, f"{len(raw)} not escaped: {raw[:8]}"


def test_each_of_three_default_ignorables_in_one_value_is_escaped(adopter):
    """A value that holds three, `m` U+034F `a` U+3164 `in` U+FE0F (#1128's
    own characters), is refused by `checked_value` and shown by `_shown`
    with EACH written as its code-point escape, and none of the three as it
    is. Every other row holds one character to a value, so a `visible_repr`
    that escaped only the first match (`count=1`) passed all of them and
    printed the second and the third raw on stderr again (RV1171's S1,
    mutant M12)."""
    value = "m\u034fa\u3164in\ufe0f"
    raw = ("\u034f", "\u3164", "\ufe0f")
    with pytest.raises(repo_shape.Refusal) as refused:
        repo_shape.checked_value("--tracking-branch", value)
    assert refused.value.code == "unsafe-value"
    assert " is 'm\\u034fa\\u3164in\\ufe0f', " in refused.value.detail, (
        refused.value.detail)
    shown = adopter._shown(value)
    assert shown == "`m\\u034fa\\u3164in\\ufe0f`", shown
    for char in raw:
        assert char not in refused.value.detail, (hex(ord(char)),
                                                  refused.value.detail)
        assert char not in shown, (hex(ord(char)), shown)


# --- the helpers, by the issue's characters -----------------------------------

@EACH_CHARACTER
def test_shown_spells_the_character(adopter, char, spelled):
    """`ma<char>in` is `` `ma<escape>in` ``, where on main the first three
    printed as they are, and read as `main`."""
    assert adopter._shown(f"ma{char}in") == f"`ma{spelled}in`"


@EACH_CHARACTER
def test_the_spelling_reads_back_as_the_name(adopter, char, spelled):
    """The escape is one the plan's reader resolves: a spelled name copied
    between the plan's double quotes is that name, as `_spelled` promises
    (#329, #900)."""
    assert adopter._spelled_character(char) == spelled
    body = adopter._spelled(f"ma{char}in")[1:-1]
    assert repo_shape.parse_yaml(f'path: "{body}"\n') == {
        "path": f"ma{char}in"}


@pytest.mark.parametrize("name", PRINTABLE_NAMES)
def test_shown_prints_a_printable_name_as_it_is(adopter, name):
    """A control: a name a terminal shows as it is still prints as it is,
    with no backticks, outside ASCII too."""
    assert adopter._shown(name) == name


def test_shown_still_spells_a_name_in_backticks(adopter):
    """A control: `` `main` `` is spelled, as #900 made it, so that it does
    not read as the spelling of `main`."""
    assert adopter._shown("`main`") == "`\\x60main\\x60`"


# --- plan, end to end ----------------------------------------------------------

def planned(source: Path, plan: Path, *flags: str
            ) -> subprocess.CompletedProcess:
    """`plan` as a person runs it, answered in BYTES, so a character printed
    raw is found as its UTF-8 bytes."""
    env = blank_unnamed_pin_sources({**os.environ, "LANES_LANE": ""}, {})
    return subprocess.run(
        [sys.executable, str(ADOPT), "plan", "--source", str(source),
         "--project", "Northwind", "--org", "testorg",
         "--elected-by", "Test Human", "--elected-on", "2026-09-02",
         *flags, "--out", str(plan)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)


def lines_with(text: bytes, start: bytes) -> list[bytes]:
    """The lines of `text` that begin with `start`, split at line feeds
    only."""
    return [line for line in text.split(b"\n") if line.startswith(start)]


@EACH_CHARACTER
def test_plan_spells_the_branch_in_its_note(tmp_path, char, spelled):
    """A source whose only branch is `ma<char>in`, planned to track `main`,
    which it lacks: `plan` prints the NOTE `check` will turn into
    `plan-tracking-branch-missing`, and the NOTE names the source's
    branches and its default branch, spelled. On main the first three were
    in it raw."""
    branch = f"ma{char}in"
    source = make_source_repo(tmp_path / "Thing", branch=branch)

    done = planned(source, tmp_path / PLAN_FILE, "--tracking-branch", "main")

    assert done.returncode == 0, done.stderr + done.stdout
    [note] = lines_with(done.stdout, b"NOTE the tracking branch is ")
    assert char.encode("utf-8") not in note, note
    said = f"`ma{spelled}in`".encode("ascii")
    assert b"(its branches: " + said + b"; " in note, note
    assert b"the source's default branch is " + said + b")" in note, note


@EACH_CHARACTER
def test_plan_refuses_the_branch_with_it_escaped(tmp_path, char, spelled):
    """Planned with no `--tracking-branch`, the source's own branch is the
    tracking branch, and `checked_value` refuses it as `unsafe-value`
    before any plan is written, naming it with the character escaped. On
    main the first three were on stderr raw."""
    source = make_source_repo(tmp_path / "Thing", branch=f"ma{char}in")
    plan = tmp_path / PLAN_FILE

    done = planned(source, plan)

    assert done.returncode == 2, done.stderr + done.stdout
    assert b"Traceback" not in done.stderr
    assert not plan.exists()
    assert char.encode("utf-8") not in done.stderr, done.stderr
    [refused] = lines_with(done.stderr, b"REFUSED unsafe-value: ")
    assert f" is 'ma{spelled}in', ".encode("ascii") in refused, refused


@EACH_CHARACTER
def test_plan_spells_a_path_in_its_table(tmp_path, char, spelled):
    """`_shown` itself, end to end: a source on `main` whose root holds
    `ma<char>in.md`. The table names it spelled, and no byte of the
    character is anywhere in what `plan` printed. On main the first three
    were in the table raw."""
    source = make_source_repo(tmp_path / "Thing",
                              {"README.md": "# Thing\n",
                               f"ma{char}in.md": "notes\n"}, edits=())

    done = planned(source, tmp_path / PLAN_FILE, "--tracking-branch", "main")

    assert done.returncode == 0, done.stderr + done.stdout
    assert char.encode("utf-8") not in done.stdout, done.stdout
    said = f"`ma{spelled}in.md`".encode("ascii")
    assert [line for line in done.stdout.split(b"\n")
            if line.lstrip().startswith(said)], done.stdout


# --- plan's `source` line, which #1120 gives `_shown` ------------------------

@EACH_CHARACTER
def test_plan_spells_the_branch_in_its_source_line(tmp_path, char, spelled):
    """RV1120's repro: a source on `ma<char>in` beside `main`, which the plan
    tracks. The `source` line names the branch spelled, no byte of the
    character is anywhere in what `plan` printed, and the plan still records
    the branch as it is. On #1120 alone the first three were in the line
    raw, and `ma<U+034F>in` read `(main)`; on main all six were."""
    branch = f"ma{char}in"
    source = source_on(tmp_path, branch)
    plan = tmp_path / PLAN_FILE

    done = planned_tracking_main(source, plan)

    assert char.encode("utf-8") not in done.stdout, done.stdout
    assert_branch_in_the_line(done, source, f"`ma{spelled}in`")
    assert repo_shape.load_yaml(plan)["source"]["default_branch"] == branch


def test_plan_names_a_printable_branch_outside_ascii_as_it_is(tmp_path):
    """#1128's item 2, a control: `feat/caf\\u00e9` is printable, so the
    line names it as it is, with no backticks and no escape. A rule that
    spelled every branch outside ASCII (RV1120's mutant E) printed it
    between backticks. It passes on main and on #1120 alone: it pins
    #1120's `_shown`."""
    source = source_on(tmp_path, "feat/caf\u00e9")

    done = planned_tracking_main(source, tmp_path / PLAN_FILE)

    assert_branch_in_the_line(done, source, "feat/caf\u00e9")


def test_plan_spells_a_branch_named_in_backticks(tmp_path):
    """#1128's item 2: a branch named `` `main` ``, backticks and all, is
    spelled `` `\\x60main\\x60` ``, as #900 spells such a name. Printed as
    it is, the line said `` (`main`) ``, which reads as the spelling of
    `main`. `str.isprintable` alone (RV1120's mutant N) printed it so.
    Fails on main; passes on #1120 alone."""
    source = source_on(tmp_path, "`main`")

    done = planned_tracking_main(source, tmp_path / PLAN_FILE)

    assert b"(`main`)" not in done.stdout, done.stdout
    assert_branch_in_the_line(done, source, "`\\x60main\\x60`")


def test_plan_spells_a_branch_that_is_not_utf8_on_a_surrogateescape_stdout(
        tmp_path):
    """#1128's item 3: #1120's row for the byte 0xE9 in a branch runs under
    `utf-8:strict`, where main never wrote the byte. Under
    `utf-8:surrogateescape` the stream turns the lone surrogate U+DCE9 back
    into the byte, so main wrote 0xE9 itself to the terminal, in a line of
    UTF-8. The line names the branch `` `caf\\udce9` `` under this stdout
    too, and the byte is in none of what `plan` printed. Fails on main;
    passes on #1120 alone. Skipped where no name can hold the byte."""
    source = make_source_repo(tmp_path / "Thing")
    on_a_branch_that_is_not_utf_8(source)

    done = planned_tracking_main(source, tmp_path / PLAN_FILE,
                                 PYTHONIOENCODING="utf-8:surrogateescape")

    assert b"caf\xe9" not in done.stdout, done.stdout
    assert_branch_in_the_line(done, source, "`caf\\udce9`")
