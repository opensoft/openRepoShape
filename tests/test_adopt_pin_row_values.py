# SPDX-License-Identifier: Apache-2.0
"""A `pins:` mapping's value that is not text is said as `_read_as` says what
the plan's reader read, in `check` and in `execute` (#1114, which follows
#1020).

`_pin_row_problem` held each of a pin's five fields (`product`, `repository`,
`commit`, `tree_sha256`, `digest_source`) to text and, for one that is not,
spelled the value as Python does: `commit: 7` read "records `commit: 7`, which
is not text", and `true` read `True`. Every other refusal of a plan's value
says what the reader read in words (`_read_as`): "the number 7", "the boolean
true", "a list of 2 item(s)", "a mapping of 1 key(s)". The field's finding
says it that way now: "records `commit:` as the number 7, which is not text".

WHAT DID NOT CHANGE. A text value is still spelled as Python spells it,
quoted, in the finding about its form (`commit: '7'`, which is not 40 hex),
and the code is `plan-pin-malformed`, as it was. A null or a blank is not a
value a pin has, so it is "records no `commit:`" under the code that finding
has always had (`plan-pin-unrecorded` for the commit and the digest): no
value of it is spelled at all, and the null rows below pin that.

Each row edits one `pins:` entry of a plan `plan` wrote, then runs `check` and
`execute --yes` on it, both with the same `--local-remote-dir` and a stub `gh`
first on PATH that records what it is asked: no run asks it, no run makes the
directory the legs go in, and `execute` refuses with `check`'s own finding.
`execute` asks for `git filter-repo` before it refuses, so the rows skip where
it is not installed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, planned, run_script
from test_adopt_pins import ANSWERS, gh_calls, stub_gh

UTF8 = "utf-8"
PLAN_FILE = "adoption-plan.yaml"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A commit and a digest of the form `plan` records. `gh-api-tree-recursive`
#: says the forge read the digest, so `check` recomputes nothing and reads no
#: network for the pin.
COMMIT = "0123456789abcdef" * 2 + "01234567"
DIGEST = "0123456789abcdef" * 4

#: The five fields `_pin_row_problem` holds to text, in the order `plan`
#: writes them (`PIN_FIELDS`), and a whole pin's value for each, as the YAML
#: of the plan spells it.
FIELDS = ("product", "repository", "commit", "tree_sha256", "digest_source")
WHOLE = {
    "product": "openGlass",
    "repository": "opensoft/openGlass",
    "commit": f'"{COMMIT}"',
    "tree_sha256": f'"{DIGEST}"',
    "digest_source": "gh-api-tree-recursive",
}

#: The first thing every finding about a non-text value says of the entry: its
#: number, and its product where the product is text.
ENTRY_NAMED = "`pins:` entry 1 ('openGlass')"
ENTRY_UNNAMED = "`pins:` entry 1"

#: How a finding ends where the field is none of `digest_source:`, and where
#: it is: the pin file `execute` writes says how the digest was read too.
FROM = ("`execute` writes the pin file from the commit and the digest "
        "`plan` records")
FROM_AND_HOW = FROM + ", and how it was read"


@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> str:
    """The text of the plan `plan` writes for the synthetic source, every
    question answered: each row edits a copy of it. `check` and `execute`
    only read the source, so the rows share it."""
    base = tmp_path_factory.mktemp("answered")
    source = make_source_repo(base / "Thing")
    return planned(source, base, dict(ANSWERS)).read_text(encoding=UTF8)


def a_pin(**raw: str) -> str:
    """One `pins:` mapping as `plan` writes it, with each field in `raw`
    spelled as given: YAML as it stands in the plan, so `commit="7"` is the
    number 7 and `commit='"7"'` is the text."""
    fields = {**WHOLE, **raw}
    assert sorted(raw) == sorted(set(raw) & set(FIELDS)), raw
    return "".join(
        ("  - " if number == 0 else "    ") + f"{key}: {fields[key]}\n"
        for number, key in enumerate(FIELDS))


def pinned(text: str, *entries: str) -> str:
    """`text` with its `pins: []` replaced by a list of `entries`."""
    assert text.count("\npins: []\n") == 1
    return text.replace("\npins: []\n", "\npins:\n" + "".join(entries), 1)


def both_on(text: str, base: Path):
    """`check` and then `execute --yes` on the plan `text`, written at
    `base`, each given the same `--local-remote-dir` and a stub `gh` first on
    PATH: `(check's run, execute's run, the stub's log)`. Neither makes the
    directory the legs go in, and neither asks `gh` anything."""
    plan = base / PLAN_FILE
    plan.write_bytes(text.encode(UTF8))
    env = stub_gh(base)
    remotes = base / "remotes"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--local-remote-dir", str(remotes), env=env)
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(base / "work"), env=env)
    assert not remotes.exists(), executed.stdout + executed.stderr
    return checked, executed, gh_calls(env)


def findings_of(result) -> list[str]:
    """Each `FINDING` line `check` printed."""
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def refused_with(executed, plan: Path, found: list[str]) -> str:
    """The code `execute` refused the plan at `plan` under, where it said
    every one of `found`, `check`'s findings, as `check` prints them."""
    lines = executed.stderr.splitlines()
    head = next(line for line in lines if line.startswith("REFUSED "))
    assert head.endswith(f": {len(found)} finding(s) in {plan}, as `check` "
                         "prints them:"), executed.stderr
    assert lines[lines.index(head) + 1:][:len(found)] == [
        f"  {finding}" for finding in found], executed.stderr
    return head.split()[1].rstrip(":")


def one_finding(answered: str, tmp_path: Path, entries: tuple, code: str):
    """The one finding `check` makes of a plan holding `entries`, which
    `execute` refuses with, as `check` prints it, under `code`, before any
    leg exists; `gh` is asked nothing, and no run raised. Returns the
    finding."""
    checked, executed, asked = both_on(pinned(answered, *entries), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(f"FINDING {code}: "), found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert refused_with(executed, tmp_path / PLAN_FILE, found) == code
    assert asked == "", asked
    for run in (checked, executed):
        assert "Traceback" not in run.stderr + run.stdout, run.stderr
    return found[0]


# --- every field, with every kind of value that is not text -----------------

#: `(the value as the plan spells it, what `_read_as` says of it, what Python
#: spells it as)`, by test id: a number, a boolean, a list and a mapping.
KINDS = {
    "number": ("7", "the number 7", "7"),
    "boolean": ("true", "the boolean true", "True"),
    "list": ("[a, b]", "a list of 2 item(s)", "['a', 'b']"),
    "mapping": ("{k: v}", "a mapping of 1 key(s)", "{'k': 'v'}"),
}

ROWS = [pytest.param(field, kind, id=f"{field}-{kind}")
        for field in FIELDS for kind in KINDS]


def written_from(field: str) -> str:
    """What a finding about `field` says `execute` writes the pin file
    from."""
    return (FROM_AND_HOW if field == "digest_source" else FROM) + ", and "


@needs_filter_repo
@pytest.mark.parametrize("field, kind", ROWS)
def test_a_pin_field_that_is_not_text_is_said_as_its_reader_read_it(
        answered, tmp_path, field, kind):
    """Each of the five fields, a number, a boolean, a list or a mapping:
    `check` finds the entry as `plan-pin-malformed` in `_read_as`'s words
    (`records `commit:` as the number 7, which is not text`), and not as
    Python spells the value (`commit: 7`, `True`); `execute` refuses it in
    the same words, and the code is the one it was."""
    raw, read, python = KINDS[kind]
    found = one_finding(answered, tmp_path, (a_pin(**{field: raw}),),
                        "plan-pin-malformed")
    entry = ENTRY_UNNAMED if field == "product" else ENTRY_NAMED
    assert found.startswith(
        f"FINDING plan-pin-malformed: {entry} records `{field}:` as {read}, "
        f"which is not text. {written_from(field)}nothing else: "
        "re-run `plan` with `--pin "), found
    assert f"`{field}: {python}`" not in found, found
    for spelled in ("True", "False", "None", "'a'", "'k'"):
        assert spelled not in found, found


# --- the whole sentence, once ----------------------------------------------


@needs_filter_repo
def test_the_whole_finding_for_a_number_commit(answered, tmp_path):
    """The issue's own `commit: 7`, word for word, in `check` and in
    `execute`'s refusal of it."""
    found = one_finding(answered, tmp_path, (a_pin(commit="7"),),
                        "plan-pin-malformed")
    assert found == (
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') records "
        "`commit:` as the number 7, which is not text. `execute` writes the "
        "pin file from the commit and the digest `plan` records, and nothing "
        "else: re-run `plan` with `--pin opensoft/openGlass@<40 hex commit>`,"
        " which reads the digest there (from `--pin-source <clone>` with no "
        "network, or `gh api`) and records both, as `scaffold-project.py "
        "--pin` takes it."), found


@needs_filter_repo
def test_the_whole_finding_for_a_boolean_digest_source(answered, tmp_path):
    """A boolean `digest_source:`, which the finding says the pin file is
    written from the commit, the digest and how it was read."""
    found = one_finding(answered, tmp_path, (a_pin(digest_source="true"),),
                        "plan-pin-malformed")
    assert found == (
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') records "
        "`digest_source:` as the boolean true, which is not text. `execute` "
        "writes the pin file from the commit and the digest `plan` records, "
        "and how it was read, and nothing else: re-run `plan` with `--pin "
        "opensoft/openGlass@<40 hex commit>`, which reads the digest there "
        "(from `--pin-source <clone>` with no network, or `gh api`) and "
        "records both, as `scaffold-project.py --pin` takes it."), found


# --- the other forms `_read_as` has, and the values a test would miss -------

#: `(the commit as the plan spells it, what `_read_as` says of it, what
#: Python spells it as)`, by test id. A zero, a `false` and an empty list or
#: mapping are not blank: none of them is `None` or `""`, so each is said as
#: what it is, and not as "no `commit:`".
EDGES = {
    "zero": ("0", "the number 0", "0"),
    "false": ("false", "the boolean false", "False"),
    "float": ("7.5", "the number 7.5", "7.5"),
    "negative": ("-3", "the number -3", "-3"),
    "padded": ("007", "the number 7", "7"),
    "empty-list": ("[]", "a list of 0 item(s)", "[]"),
    "empty-mapping": ("{}", "a mapping of 0 key(s)", "{}"),
    "list-of-one": ("[a]", "a list of 1 item(s)", "['a']"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(EDGES))
def test_a_commit_that_is_an_edge_of_not_text_is_said_as_read(
        answered, tmp_path, case):
    """`_read_as`'s other forms, and the values that look like nothing: each
    is a `commit:` that is not text, and not a missing one."""
    raw, read, python = EDGES[case]
    found = one_finding(answered, tmp_path, (a_pin(commit=raw),),
                        "plan-pin-malformed")
    assert found.startswith(
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') records "
        f"`commit:` as {read}, which is not text. {FROM}, and nothing else: "
        "re-run `plan` with `--pin "), found
    assert f"`commit: {python}`" not in found, found


@needs_filter_repo
def test_two_fields_that_are_not_text_are_each_said_as_read(answered,
                                                             tmp_path):
    """The finding names each field that is not text, in the order `plan`
    writes them, and says they are not text, as it did of more than one."""
    found = one_finding(answered, tmp_path,
                        (a_pin(commit="7", tree_sha256="true"),),
                        "plan-pin-malformed")
    assert found.startswith(
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') records "
        "`commit:` as the number 7, `tree_sha256:` as the boolean true, "
        f"which are not text. {FROM}, and nothing else: re-run `plan` with "
        "`--pin "), found
    assert "which is not text" not in found, found


@needs_filter_repo
def test_a_text_beside_a_value_that_is_not_text_is_named_once_it_is_mended(
        answered, tmp_path):
    """A `commit:` that is a number and a `digest_source:` that is bad text:
    the finding is about the number alone, as it was, and says nothing of
    the text until the number is mended."""
    found = one_finding(
        answered, tmp_path,
        (a_pin(commit="7", digest_source="read by hand"),),
        "plan-pin-malformed")
    assert found.startswith(
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') records "
        "`commit:` as the number 7, which is not text. "), found
    assert "digest_source" not in found, found
    assert "read by hand" not in found, found


@needs_filter_repo
def test_a_pin_that_is_not_text_beside_a_whole_pin_is_entry_two(answered,
                                                                 tmp_path):
    """Said as the entry it is: the number of the entry, and the product of
    the whole pin beside it is not borrowed."""
    other = a_pin(product="openLens", repository="opensoft/openLens")
    found = one_finding(answered, tmp_path,
                        (other, a_pin(commit="7")), "plan-pin-malformed")
    assert found.startswith(
        "FINDING plan-pin-malformed: `pins:` entry 2 ('openGlass') records "
        "`commit:` as the number 7, which is not text. "), found


# --- a null or a blank is not a value a pin has: no value is spelled --------

#: `(the field's value as the plan spells it, the code its finding has,
#: what it says)`, by test id: what every field says of a null, which is
#: what it said before, and says now.
NULLS = {
    "product-null": ("product", "~", "plan-pin-malformed",
                     ENTRY_UNNAMED + " records no `product:`."),
    "repository-null": ("repository", "null", "plan-pin-malformed",
                        ENTRY_NAMED + " records no `repository:`."),
    "commit-null": ("commit", "~", "plan-pin-unrecorded",
                    ENTRY_NAMED + " records no `commit:`."),
    "tree-sha256-null": ("tree_sha256", "null", "plan-pin-unrecorded",
                         ENTRY_NAMED + " records no `tree_sha256:`."),
    "digest-source-null": ("digest_source", "~", "plan-pin-malformed",
                           ENTRY_NAMED + " records no `digest_source:`."),
    "commit-blank": ("commit", '""', "plan-pin-unrecorded",
                     ENTRY_NAMED + " records no `commit:`."),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(NULLS))
def test_a_null_or_a_blank_pin_field_is_no_value_and_spells_none(
        answered, tmp_path, case):
    """A null is the one value `_read_as` says "null" of that never reaches
    `_pin_row_problem`'s sentence for a value that is not text: it is
    "records no `commit:`", under the code that finding has always had. This
    row says that is unchanged, and that no spelling of it is added."""
    field, raw, code, said = NULLS[case]
    found = one_finding(answered, tmp_path, (a_pin(**{field: raw}),), code)
    assert found.startswith(f"FINDING {code}: {said} "), found
    assert "not text" not in found, found
    assert "null" not in found.split(". ", 1)[0], found
    assert "None" not in found, found


# --- a text value is spelled as it was, byte for byte -----------------------

#: `(the field's value as the plan spells it, how the finding names the
#: entry, what it says of it)`, by test id. Each is a text, quoted as Python
#: quotes it, in the finding about its form: `commit: '7'` is the text "7",
#: where `commit: 7` is the number.
TEXTS = {
    "commit-quoted-seven": (
        {"commit": '"7"'}, ENTRY_NAMED,
        "records `commit: '7'`, which is not 40 hex: a tag, a branch or an "
        "abbreviated oid can be moved, and a commit cannot"),
    "commit-quoted-true": (
        {"commit": '"true"'}, ENTRY_NAMED,
        "records `commit: 'true'`, which is not 40 hex: a tag, a branch or "
        "an abbreviated oid can be moved, and a commit cannot"),
    "product-another": (
        {"product": "openLens"}, "`pins:` entry 1 ('openLens')",
        "records `product: 'openLens'` and `repository: "
        "'opensoft/openGlass'`, and `plan` records the repository as "
        "`<owner>/<openProduct>`, its name the product's"),
    "repository-no-owner": (
        {"repository": "openGlass"}, ENTRY_NAMED,
        "records `product: 'openGlass'` and `repository: 'openGlass'`, and "
        "`plan` records the repository as `<owner>/<openProduct>`, its name "
        "the product's"),
    "digest-short": (
        {"tree_sha256": '"abc"'}, ENTRY_NAMED,
        "records `tree_sha256: 'abc'`, which is not 64 hex"),
    "digest-source-by-hand": (
        {"digest_source": "read by hand"}, ENTRY_NAMED,
        "records `digest_source: 'read by hand'`, and `plan` records "
        "`gh-api-tree-recursive`, or `local-clone (<the clone's path>)` on "
        "one printable line, and nothing else"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(TEXTS))
def test_a_text_pin_value_is_spelled_as_it_was(answered, tmp_path, case):
    """The controls: a value that is text keeps Python's quotes in the
    finding about its form, byte for byte, under `plan-pin-malformed`, and
    is never said as a value of another kind."""
    raw, entry, said = TEXTS[case]
    found = one_finding(answered, tmp_path, (a_pin(**raw),),
                        "plan-pin-malformed")
    assert found.startswith(
        f"FINDING plan-pin-malformed: {entry} {said}. "), found
    assert "the number" not in found and "the boolean" not in found, found
    assert "which is not text" not in found, found
