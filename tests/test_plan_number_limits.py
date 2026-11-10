# SPDX-License-Identifier: Apache-2.0
"""A plain number the plan's reader cannot make is refused by its line, and a
float it does make is said in digits a plan can hold (#1212, which follows
#1114 and #1198), at the small end of a decimal as at the large (#1260).

RV1198 found both on #1198, and both are older than it.

- `scripts/repo_shape.py`'s `_scalar` read a plain integer with `int()`,
  which raises `ValueError` past `sys.get_int_max_str_digits()` (4300 digits
  by default), and nothing turned that into a refusal: `check` and `execute`
  ended in a traceback, for a `commit:` and for any other key. It read a
  plain decimal with `float()`, which makes `inf` of one too large to be
  finite.
- `adopt-project.py`'s `_read_as` spelled a float with `repr`: "the number
  inf", "the number 1e+300", "the number 1e-05". The plan's reader reads
  each of those as text, so the words named a value no plan can hold.

Now `_scalar` refuses both numbers as `yaml-unparsable`, with a remedy, so
`load_yaml` names the line; and `_read_as` says a float in the digits of its
`repr`, written out with no exponent, which the reader reads back as it.

#1260 is the other end of a decimal. `float()` makes `0.0` of a plain decimal
that holds a nonzero digit and is too small for a 64-bit float (`0.` and four
hundred `0`s and a `1`), a number the file does not hold, where it makes
`inf` of one too large. `_scalar` refuses it as it refuses that one: the same
`yaml-unparsable` by its line, with the same remedy, in words that say it
would be zero. `0.0`, `-0.0`, a decimal of only zeros and a subnormal such as
5e-324 are numbers still.

The reader's rows run in this process. The plan's rows edit a plan `plan`
wrote and run `check` and `execute --yes` on it, with a stub `gh` first on
PATH and `--local-remote-dir`: neither asks `gh` anything or makes the
directory the legs go in. The rows that end in a finding skip where `git
filter-repo` is not installed, because `execute` asks for it before it
refuses; a plan the reader refuses is refused before that.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, make_source_repo, planned
from test_adopt_pin_row_values import (
    ENTRY_NAMED, FROM, PLAN_FILE, a_pin, both_on, needs_filter_repo,
    one_finding, pinned,
)
from test_adopt_pins import ANSWERS

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, YamlError, load_yaml, parse_yaml  # noqa: E402

UTF8 = "utf-8"

#: Python's default for `sys.get_int_max_str_digits()`, which every row
#: here sets, so a host that changed it reads these rows as CI does.
DEFAULT_DIGITS = 4300

#: The remedy `_scalar`'s refusal of a number carries, whole.
REMEDY = (
    "Remediation: unquoted, YAML reads this value as a number, and this "
    "reader cannot make one of it, so it refuses it rather than guess. Write "
    "it in double quotes if it is text, or as a number of fewer digits, and "
    "run the command again.")

LONG = "1" * (DEFAULT_DIGITS + 1)
LONGEST = "1" * DEFAULT_DIGITS
INFINITE = "1" * 400 + ".5"

#: W1212's decimal that is too small: `0.`, four hundred `0`s and a `1`.
#: `float()` makes `0.0` of it, a number nothing in the file holds.
TINY = "0." + "0" * 400 + "1"

#: The decimals a digit either side of half the smallest float, 5e-324, which
#: `float()` rounds to the nearer of 0.0 and 5e-324: the one under half is
#: `0.0`, so it is refused, and the one over half is 5e-324, a number.
BELOW_HALF = "0." + "0" * 323 + "24703282292062327"
ABOVE_HALF = "0." + "0" * 323 + "24703282292062328"

#: Arabic-Indic zero and one: the pattern `_scalar` reads a decimal by takes
#: the digits of every script, and `float()` reads each as its value. Escapes,
#: so that this file stays ASCII.
ZERO_OF_ANOTHER_SCRIPT = "\u0660"
ONE_OF_ANOTHER_SCRIPT = "\u0661"


def too_long(digits: int) -> str:
    return (f"a plain integer of {digits} digits is too long for this Python "
            "to read as a number")


def too_large(digits: int) -> str:
    return (f"a plain decimal of {digits} digits is too large to read as a "
            "number: a 64-bit float cannot hold it, so it would be infinite")


def too_small(digits: int) -> str:
    return (f"a plain decimal of {digits} digits is too small to read as a "
            "number: a 64-bit float cannot hold it, so it would be zero")


needs_the_setting = pytest.mark.skipif(
    not hasattr(sys, "set_int_max_str_digits"),
    reason="this Python has no limit on an integer's digits")


@pytest.fixture
def default_digits(monkeypatch):
    """Python's default limit, here and in every tool a row runs, restored
    after the row."""
    monkeypatch.setenv("PYTHONINTMAXSTRDIGITS", str(DEFAULT_DIGITS))
    if not hasattr(sys, "set_int_max_str_digits"):
        yield
        return
    held = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(DEFAULT_DIGITS)
    try:
        yield
    finally:
        sys.set_int_max_str_digits(held)


def refusal_of(tmp_path: Path, text: str) -> Refusal:
    """What `load_yaml` refuses a file holding `text` with."""
    path = tmp_path / "file.yaml"
    path.write_bytes(text.encode(UTF8))
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    return caught.value


# --- the reader: a number it cannot make is refused by its line -------------

#: `(the file, the line the number is on, what the refusal says)`, by test
#: id: the integer one digit past the limit wherever a plain value is read,
#: and a decimal too large to be finite.
UNMADE = {
    "integer-block-value": (f"a: 1\nk: {LONG}\n", 2, too_long(4301)),
    "integer-negative": (f"a: 1\nk: -{LONG}\n", 2, too_long(4301)),
    "integer-zeros": (f"a: 1\nk: {'0' * 4301}\n", 2, too_long(4301)),
    "integer-sequence-item": (f"a: 1\nk:\n  - {LONG}\n", 3, too_long(4301)),
    "integer-flow-sequence": (f"a: 1\nk: [1, {LONG}]\n", 2, too_long(4301)),
    "integer-flow-mapping": (f"a: 1\nk: {{x: {LONG}}}\n", 2, too_long(4301)),
    "integer-nested": (f"a:\n  b:\n    k: {LONG}\n", 3, too_long(4301)),
    "decimal-block-value": (f"a: 1\nk: {INFINITE}\n", 2, too_large(401)),
    "decimal-negative": (f"a: 1\nk: -{INFINITE}\n", 2, too_large(401)),
    "decimal-flow-sequence": (f"a: 1\nk: [1.5, {INFINITE}]\n", 2,
                              too_large(401)),
    "decimal-past-the-largest": (f"k: 1{'0' * 309}.0\n", 1, too_large(311)),
}


@pytest.mark.parametrize("case", sorted(UNMADE))
def test_a_number_the_reader_cannot_make_is_refused_by_its_line(
        tmp_path, default_digits, case):
    """`yaml-unparsable`, naming the file and the line, with the remedy, and
    no `ValueError`: the integer one digit past this Python's limit, and a
    decimal `float()` makes infinite, in every place a plain value is read.
    """
    text, line, said = UNMADE[case]
    refusal = refusal_of(tmp_path, text)
    assert refusal.code == "yaml-unparsable"
    assert refusal.detail == (
        f"{tmp_path / 'file.yaml'}: line {line}: {said}"), refusal.detail
    assert refusal.remediation == REMEDY
    assert isinstance(refusal.__cause__, YamlError)


#: `(the file, what the reader makes of `k:`)`, by test id: the controls.
#: The longest integer this Python reads, the largest decimal that is
#: finite, and the long integer written as text, are each read as before.
#: `None` is the longest integer, which the row makes itself: `int(LONGEST)`
#: here would raise at import on a host whose limit is below 4300, and the
#: file would not collect.
MADE = {
    "integer-at-the-limit": (f"k: {LONGEST}\n", None),
    "integer-quoted": (f'k: "{LONG}"\n', LONG),
    "decimal-at-the-largest": (f"k: 1{'0' * 308}.0\n", 1e308),
    "decimal-quoted": (f'k: "{INFINITE}"\n', INFINITE),
}


@pytest.mark.parametrize("case", sorted(MADE))
def test_a_number_the_reader_can_make_reads_as_it_did(default_digits, case):
    text, value = MADE[case]
    if value is None:
        value = int(LONGEST)
    assert parse_yaml(text) == {"k": value}


@needs_the_setting
def test_the_refusal_follows_this_pythons_setting(tmp_path, default_digits):
    """At any `sys.set_int_max_str_digits` setting (#1212's "at any
    `int_max_str_digits` setting"): one digit past it is refused in the
    same words, and a setting above 4300 reads 4301 digits as a number."""
    sys.set_int_max_str_digits(640)
    assert parse_yaml(f"k: {'7' * 640}\n") == {"k": int("7" * 640)}
    refusal = refusal_of(tmp_path, f"k: {'7' * 641}\n")
    assert refusal.detail.endswith(f": line 1: {too_long(641)}"), (
        refusal.detail)
    sys.set_int_max_str_digits(5000)
    assert parse_yaml(f"k: {LONG}\n") == {"k": int(LONG)}


# --- the small end: a decimal a float can only make zero of (#1260) ----------

#: `(the file, the line the number is on, how many digits it holds)`, by test
#: id: W1212's decimal and the same with a minus sign, in each shape a plain
#: value is read in, and the two edges: the decimal a digit under half the
#: smallest float, and one in the digits of another script. Every one has a
#: nonzero digit and a float of zero.
TOO_SMALL = {
    "block-value": (f"a: 1\nk: {TINY}\n", 2, 402),
    "block-value-negative": (f"a: 1\nk: -{TINY}\n", 2, 402),
    "sequence-item": (f"a: 1\nk:\n  - {TINY}\n", 3, 402),
    "sequence-item-negative": (f"a: 1\nk:\n  - -{TINY}\n", 3, 402),
    "flow-sequence": (f"a: 1\nk: [1.5, {TINY}]\n", 2, 402),
    "flow-sequence-negative": (f"a: 1\nk: [1.5, -{TINY}]\n", 2, 402),
    "flow-mapping": (f"a: 1\nk: {{x: {TINY}}}\n", 2, 402),
    "flow-mapping-negative": (f"a: 1\nk: {{x: -{TINY}}}\n", 2, 402),
    "nested": (f"a:\n  b:\n    k: {TINY}\n", 3, 402),
    "nested-negative": (f"a:\n  b:\n    k: -{TINY}\n", 3, 402),
    "below-half-the-smallest": (f"k: {BELOW_HALF}\n", 1, 341),
    "another-script": (
        f"k: 0.{ZERO_OF_ANOTHER_SCRIPT * 400}{ONE_OF_ANOTHER_SCRIPT}\n", 1,
        402),
}


@pytest.mark.parametrize("case", sorted(TOO_SMALL))
def test_a_decimal_a_float_can_only_make_zero_of_is_refused_by_its_line(
        tmp_path, case):
    """`yaml-unparsable`, naming the file and the line, with the remedy and
    words that say it would be zero, as the large end's say it would be
    infinite: in every place a plain value is read, with a minus sign or
    none, and where the digits are another script's."""
    text, line, digits = TOO_SMALL[case]
    refusal = refusal_of(tmp_path, text)
    assert refusal.code == "yaml-unparsable"
    assert refusal.detail == (
        f"{tmp_path / 'file.yaml'}: line {line}: {too_small(digits)}"), (
        refusal.detail)
    assert refusal.remediation == REMEDY
    assert isinstance(refusal.__cause__, YamlError)


#: `(the decimal, what the reader makes of it)`, by test id: the controls.
#: A decimal of only zeros, in either script and either sign, is a number
#: with no nonzero digit; 5e-324 is a nonzero float, spelled in its 326
#: characters, and so is the decimal a digit over half of it.
STILL_NUMBERS = {
    "zero": ("0.0", 0.0),
    "negative-zero": ("-0.0", -0.0),
    "zeros": ("0.000", 0.0),
    "many-zeros": ("0." + "0" * 400, 0.0),
    "many-zeros-negative": ("-0." + "0" * 400, -0.0),
    "zeros-of-another-script": (
        f"{ZERO_OF_ANOTHER_SCRIPT}.{ZERO_OF_ANOTHER_SCRIPT * 400}", 0.0),
    "the-smallest": ("0." + "0" * 323 + "5", 5e-324),
    "the-smallest-negative": ("-0." + "0" * 323 + "5", -5e-324),
    "above-half-the-smallest": (ABOVE_HALF, 5e-324),
}


@pytest.mark.parametrize("case", sorted(STILL_NUMBERS))
def test_a_decimal_a_float_can_hold_is_still_read_as_a_number(case):
    """`repr` of the whole, so that a `-0.0` read as `0.0` is not the same."""
    spelled, value = STILL_NUMBERS[case]
    assert repr(parse_yaml(f"k: {spelled}\n")) == repr({"k": value})


# --- `_read_as`: a float in digits the reader reads back as it --------------


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, to ask `_read_as` itself."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_number_limits", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


#: `(a float the reader makes, how `_read_as` says it)`, by test id. The
#: first five have an exponent in `repr`; the rest are the controls, said
#: as `repr` says them.
FLOATS = {
    "large": (1e300, "1" + "0" * 300 + ".0"),
    "the-largest": (1.7976931348623157e308,
                    "17976931348623157" + "0" * 292 + ".0"),
    "past-sixteen-digits": (1.2345678901234568e16, "12345678901234568.0"),
    "small": (1e-05, "0.00001"),
    "the-smallest": (5e-324, "0." + "0" * 323 + "5"),
    "plain": (7.5, "7.5"),
    "whole": (7.0, "7.0"),
    "negative-zero": (-0.0, "-0.0"),
    "a-tenth": (0.1, "0.1"),
    "negative": (-3.25, "-3.25"),
}


@pytest.mark.parametrize("case", sorted(FLOATS))
def test_a_float_is_said_in_digits_the_reader_reads_back(adopter, case):
    """With no exponent and no `inf`, and in a form the plan's reader reads
    back as that very float."""
    value, digits = FLOATS[case]
    said = adopter._read_as(value)
    assert said == f"the number {digits}", said
    assert "e" not in digits
    assert "inf" not in digits
    read = parse_yaml(f"k: {digits}\n")["k"]
    assert isinstance(read, float), read
    assert repr(read) == repr(value), read


def test_an_integer_and_a_boolean_are_said_as_before(adopter, default_digits):
    assert adopter._read_as(7) == "the number 7"
    assert adopter._read_as(-3) == "the number -3"
    assert adopter._read_as(int(LONGEST)) == f"the number {LONGEST}"
    assert adopter._read_as(True) == "the boolean true"


# --- the plan, through `check` and `execute` -------------------------------


@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> str:
    """The text of the plan `plan` writes for the synthetic source, every
    question answered: each row edits a copy of it."""
    base = tmp_path_factory.mktemp("answered")
    source = make_source_repo(base / "Thing")
    return planned(source, base, dict(ANSWERS)).read_text(encoding=UTF8)


def line_of(text: str, held: str) -> int:
    """The number of the one line of `text` that is `held`."""
    lines = text.splitlines()
    assert lines.count(held) == 1, held[:40]
    return lines.index(held) + 1


def refused_unparsable(text: str, base: Path, line: int, said: str) -> None:
    """`check` and `execute --yes` each refuse the plan `text` as
    `yaml-unparsable` at `line`, in two lines and no more: the refusal, then
    the remedy. No traceback, no finding, and `gh` asked nothing."""
    checked, executed, asked = both_on(text, base)
    plan = base / PLAN_FILE
    for run in (checked, executed):
        assert run.returncode == 2, run.stdout + run.stderr
        assert run.stderr == (
            f"REFUSED yaml-unparsable: {plan}: line {line}: {said}\n"
            f"{REMEDY}\n"), run.stderr[:2000]
        assert run.stdout == "", run.stdout
    assert asked == "", asked


def test_a_commit_of_4301_digits_is_refused_by_its_line(
        answered, tmp_path, default_digits):
    """#1212's `int-4301-digits-commit`: a traceback in `check` and in
    `execute`, and now the reader's refusal of the `commit:` line."""
    text = pinned(answered, a_pin(commit=LONG))
    refused_unparsable(text, tmp_path, line_of(text, f"    commit: {LONG}"),
                       too_long(4301))


def test_a_key_outside_pins_of_4301_digits_is_refused_by_its_line(
        answered, tmp_path, default_digits):
    """#1212's `int-4301-digits-outside-pins`: the reader's fault, not the
    pin rows', so a key no pin holds is refused the same way."""
    text = answered + f"probe_extra: {LONG}\n"
    refused_unparsable(text, tmp_path, len(text.splitlines()),
                       too_long(4301))


def test_a_commit_too_large_to_be_finite_is_refused_by_its_line(
        answered, tmp_path, default_digits):
    """#1212's `float-overflow-commit`: four hundred `1`s and `.5` were "the
    number inf", and are now the reader's refusal of the line."""
    text = pinned(answered, a_pin(commit=INFINITE))
    refused_unparsable(text, tmp_path,
                       line_of(text, f"    commit: {INFINITE}"),
                       too_large(401))


# --- the small end, through `check` and `execute` (#1260) -------------------


@pytest.mark.parametrize("sign", ["", "-"], ids=["positive", "negative"])
def test_a_commit_too_small_to_be_nonzero_is_refused_by_its_line(
        answered, tmp_path, sign):
    """`check` and `execute` read W1212's decimal in a `commit:` as "the
    number 0.0" and said it was not text; they now refuse it, by its line, as
    they refuse one too large to be finite."""
    raw = sign + TINY
    text = pinned(answered, a_pin(commit=raw))
    refused_unparsable(text, tmp_path, line_of(text, f"    commit: {raw}"),
                       too_small(402))


def test_a_key_outside_pins_too_small_to_be_nonzero_is_refused_by_its_line(
        tmp_path):
    """A key no pin holds was read as `0.0`, and the plan was a good one:
    `check` printed no finding, and `execute` made the legs. It is the
    reader's fault, not the pin rows', so it is refused the same way.

    The row makes a source of its own, not the module's: where the reader
    read it as `0.0`, `execute` ran the plan and left its split branch in the
    source, and every row after this one would find `adopt-branch-exists`."""
    own = tmp_path / "own"
    own.mkdir()
    planned_text = planned(make_source_repo(own / "Thing"), own,
                           dict(ANSWERS)).read_text(encoding=UTF8)
    text = planned_text + f"probe_extra: {TINY}\n"
    refused_unparsable(text, tmp_path, len(text.splitlines()), too_small(402))


def test_a_follow_up_too_small_to_be_nonzero_is_refused_by_its_line(
        answered, tmp_path):
    """A `follow_ups:` item was read as `0.0` and `check` found it is a
    number, not text; the reader refuses it first."""
    assert answered.count("\nfollow_ups:\n") == 1
    text = answered.replace("\nfollow_ups:\n",
                            "\nfollow_ups:\n  - " + TINY + "\n", 1)
    refused_unparsable(text, tmp_path, line_of(text, f"  - {TINY}"),
                       too_small(402))


#: `(the commit as the plan spells it, how the finding says it)`, by test
#: id: decimals a float can hold, which are numbers still, and so are said.
HELD = {
    "zeros": ("0." + "0" * 400, "0.0"),
    "the-smallest": ("0." + "0" * 323 + "5", "0." + "0" * 323 + "5"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(HELD))
def test_a_commit_a_float_can_hold_is_still_a_finding(answered, tmp_path,
                                                       case):
    """The controls: a decimal of only zeros and the smallest float are
    numbers, and the `commit:` is said as #1198 says one that is not text."""
    raw, digits = HELD[case]
    found = one_finding(answered, tmp_path, (a_pin(commit=raw),),
                        "plan-pin-malformed")
    assert found.startswith(
        f"FINDING plan-pin-malformed: {ENTRY_NAMED} records `commit:` as the "
        f"number {digits}, which is not text. {FROM}, and nothing else: "), (
        found[:400])


@needs_filter_repo
def test_a_commit_of_4300_digits_is_still_a_finding(answered, tmp_path,
                                                     default_digits):
    """The control: 4300 digits is a number, and the `commit:` is said as
    #1198 says a number that is not text."""
    found = one_finding(answered, tmp_path, (a_pin(commit=LONGEST),),
                        "plan-pin-malformed")
    assert found.startswith(
        f"FINDING plan-pin-malformed: {ENTRY_NAMED} records `commit:` as the "
        f"number {LONGEST}, which is not text. {FROM}, and nothing else: "), (
        found[:300])


#: `(the commit as the plan spells it, how the finding says it)`, by test
#: id: floats whose `repr` has an exponent.
SAID = {
    "large": ("9" * 300 + ".5", "1" + "0" * 300 + ".0"),
    "small": ("0.00001", "0.00001"),
    "past-sixteen-digits": ("12345678901234567.5", "12345678901234568.0"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(SAID))
def test_a_float_commit_is_said_without_an_exponent(answered, tmp_path,
                                                    case):
    """#1212's `9` * 300 + `.5`, which read "the number 1e+300", and two
    more whose `repr` has an exponent: each is said in digits."""
    raw, digits = SAID[case]
    found = one_finding(answered, tmp_path, (a_pin(commit=raw),),
                        "plan-pin-malformed")
    assert found.startswith(
        f"FINDING plan-pin-malformed: {ENTRY_NAMED} records `commit:` as the "
        f"number {digits}, which is not text. {FROM}, and nothing else: "), (
        found[:400])
    assert "e+" not in found, found[:400]
    assert "e-0" not in found, found[:400]


@needs_filter_repo
def test_a_float_follow_up_is_said_without_an_exponent(answered, tmp_path):
    """`_read_as`'s other callers say a float the same way: a `follow_ups:`
    item that is a number, which no pin row reads."""
    assert answered.count("\nfollow_ups:\n") == 1
    text = answered.replace("\nfollow_ups:\n",
                            "\nfollow_ups:\n  - " + "9" * 300 + ".5\n", 1)
    checked, executed, asked = both_on(text, tmp_path)
    found = [line for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    assert found == [
        "FINDING plan-bad-follow-ups: item 1 of `follow_ups:` is the number "
        f"1{'0' * 300}.0, not text: `execute` writes each item into the "
        "split commit's message as one line of text"], checked.stderr[:2000]
    assert checked.returncode == 1, checked.stderr[:2000]
    assert executed.returncode == 2, executed.stderr[:2000]
    assert f"  {found[0]}" in executed.stderr.splitlines(), (
        executed.stderr[:2000])
    assert asked == "", asked
