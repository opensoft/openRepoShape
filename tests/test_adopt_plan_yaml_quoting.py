# SPDX-License-Identifier: Apache-2.0
"""A string the plan writer emits is read back by the plan's loader as that
same string (#181).

`y()` wrote `null`, `Null`, `true` and `False` bare, and `repo_shape`'s reader
takes those for a null and a boolean. So `plan --spec-path null` wrote
`spec_path: null`, which loads as "no value", and the leg was mounted at the
default `spec` while the plan's own follow-ups said `null/contracts`;
`--tracking-branch true` came back as a boolean, and a source file named
`null` came back as a plan entry with no path at all.

THE RULE IS ASKED OF THE LOADER, NOT OF A LIST. Every test here round-trips
through `repo_shape.parse_yaml` itself, in each place the writer puts a
string: after `key: ` (`emit`), as a `- ` item, and as `Entry.write`'s
`- path: `. None of them names the words the loader treats as keywords, which
is how a second list of them would drift; the one test that does names a
word the loader does NOT read today, to show the writer follows the reader
when the reader changes.

A LINE BREAK IS NOT IN THE GENERATED ALPHABET, because it is #199's and not
this change's. The reader takes a plan line by line (`str.splitlines`, which
also splits on `\\r`, `\\x0b`, `\\x0c`, `\\x1c`-`\\x1e`, `\\x85`, `\\u2028` and
`\\u2029`), so `y` quotes such a name with `repo_shape.double_quoted`, which
spells every character `str.isprintable` refuses from the escape table the
reader resolves, and the name is one line that reads back;
`tests/test_adopt_plan_escapes.py` proves that for every code point to
U+02FF and more. Before #199 a name whose ONLY line break was a final one
matched `_PLAIN_RE`, because `$` matches before it, and was written bare:
the plan read the entry back as the name WITHOUT its line break (`trail` for
`trail\\n`), and `check` reported the file uncovered (`plan-uncovered`) and
the entry empty (`plan-empty-entry`). `_PLAIN_RE` ends at `\\Z` now, and the
name is written `"trail\\n"`, on one line.

WHAT `execute` WRITES IS ASKED ABOUT TOO (lane 2's review of 76a6153). Once
the plan said `null` and meant it, `execute` put it into `project.yaml` and
the leg pins as it stands -- `path: null`, `id: true`, `tracking_branch:
true` -- and the run ended `adoption verified` before a bootstrap that failed,
or that put the legs on a branch other than the one they were pushed on. So
`plan`, `check` and `execute` refuse a value the project's own loader would
read back as something else, by the same question `y` asks
(`loader_reading`), put into each template line that carries the value; and
the end-to-end test clones and bootstraps what is still accepted.

SINCE #259 THE TEMPLATES QUOTE THOSE LINES (main's 47b1e06): the id, the
branch, the leg paths, the election date and the visibility are written
between double quotes, which read back as typed. Since #514 (main's
e6fbd748) `execute` quotes an item of the manifest's `neutral_product_pins:`
list the reader would misread, so a pin's product reads back too. Each value
the gate refused is planned, checked and written as given (`READ_BACK`), and
on the shipped templates the gate finds nothing. It is asked of a line
written bare once more where a test means its own answer (`bare_template`,
`bare_pins`, in this process): how it names a value, which values it asks
about at all, and what `plan`, `check` and `execute` do with its answer
(`REFUSED`).

THE PROJECT'S OWN VALIDATOR IS ASKED FIRST (#261, rv181f's G1). A value it
refuses as the loader reads it -- `visibility: secret`, and `visibility:
true`, a boolean main does not ask it about -- is refused in its words
alone. The misread finding is for what the validator accepts and `execute`
writes in every mode, which is what its remediation says.
"""

from __future__ import annotations

import argparse
import functools
import importlib.util
import itertools
import random
import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, cloned_just_pushed, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
from repo_shape import load_yaml, parse_yaml  # noqa: E402
from shape_materialize import neutral_pin_path  # noqa: E402

DOCTOR = REPO / "shape-doctor.py"

#: What the one `execute` test here needs and nothing else does.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: Spelled once each: the same word in a table, a loop and an assertion is one
#: fact written three times, and `python:S1192` counts it.
FALSE_WORD = "false"
FALSE_TITLE = "False"
OPEN_GLASS = "openGlass"
SPLIT_BRANCH = "adopt/three-repo-shape"
QUOTED_YES = '"yes"'
QUOTED_TRUE = '"True"'
PATHS = "paths"
PLAN_FILE = "plan.yaml"
UTF8 = "utf-8"
#: The project the plans below adopt, and the directory of its source.
PROJECT_NAME = "Northwind"
SOURCE_NAME = "Thing"
#: The reader's scalar function, which the tests that teach it a keyword
#: replace.
SCALAR_READER = "_scalar"

#: Answered the way `test_adopt_plan.py` answers them, so `check` can pass.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))


def text_of(plan: Path) -> str:
    return plan.read_text(encoding=UTF8)


def casings(word: str) -> list[str]:
    """Every spelling of `word` in upper and lower case: `null` is sixteen."""
    return sorted({"".join(letters) for letters in itertools.product(
        *[{c.lower(), c.upper()} for c in word])})


#: The brief's classes, each spelled the way a person or a path might.
NULLS = ["null", "Null", "NULL", "~", "", *casings("null")]
BOOLEANS = [*casings("true"), *casings(FALSE_WORD)]
#: YAML 1.1's other booleans. The loader reads NONE of them today, so they are
#: candidates and not a list of what is quoted: whichever way the loader
#: reads one, the writer has to give it back unchanged.
YAML_1_1_BOOLEANS = [spelling for word in ("yes", "no", "on", "off", "y", "n")
                     for spelling in casings(word)]
NUMBERS = ["0", "1", "-1", "+1", "007", "1_000", "3.14", "-0.5", ".5", "1.",
           "1e3", "1E-3", "0o17", "017", "0x1F", "0b101", ".inf", "-.inf",
           ".Inf", ".INF", ".nan", ".NaN", "inf", "nan", "NaN"]
DATES = ["2026-10-09", "2026-10-09T12:30:00Z", "2026-10-09 12:30", "12:30",
         "1:30:00"]
#: Every YAML indicator, leading a string and inside one.
INDICATORS = [f"{mark}{rest}" for mark in "-?:,[]{}#&*!|>'\"%@`~="
              for rest in ("", "x", " x")]
SYNTAX = ["a: b", "a:b", "key:", "a:", ": a", "a #b", "a#b", "a # b", " a",
          "a ", "  ", " ", "a  b", "\ta", "a\t", "a,b", "[a]", "{a: b}",
          "a [b]", "- a", "-", "--", "---", "...", "<<", "? a", "a: [b]"]
ESCAPES = ['a"b', "a'b", '"q"', "'q'", "a\\b", "a\\\\b", "\\n", "\\t", '\\"',
           "a\\", "\\", '"', '""', "''", "a\\\"b", "\\x41", "\\u00e9"]
NON_ASCII = ["é", "日本", "emoji \U0001F600", " x"]
#: What the plan is mostly made of. These were written bare before and are
#: written bare now.
ORDINARY = ["spec", "code", "legs/spec", PROJECT_NAME, "Northwind-spec",
            SPLIT_BRANCH, "main", OPEN_GLASS, "opensoft/openGlass", "xf-project-northwind", "README.md",
            ".gitignore", ".github/", "a:b", "a@b", "a+b", "nullable",
            "trueish", "nul", "Nonesuch", "falsey", "notnull"]

#: One of each, in order: `casings` and the lists above overlap.
CANDIDATES = list(dict.fromkeys([
    *NULLS, *BOOLEANS, *YAML_1_1_BOOLEANS, *NUMBERS, *DATES, *INDICATORS,
    *SYNTAX, *ESCAPES, *NON_ASCII, *ORDINARY]))

#: The loader's keywords as it reads them today. NOT used to decide anything
#: in the writer, and not used to decide what these tests expect either except
#: in `test_a_value_the_loader_reads_as_a_keyword_is_quoted`, whose point is
#: that these exact strings are the ones that were wrong.
READ_AS_A_KEYWORD = ["null", "Null", "NULL", "~", "", "true", "True", "TRUE",
                     FALSE_WORD, FALSE_TITLE, "FALSE"]

SHAPES_OF_A_STRING = ["a value (`emit`)", "a list item", "an entry's path"]


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module: `y` has no command line."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_plan_yaml_quoting", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def readings(adopter, value: str) -> list:
    """What the loader makes of `value`, written by the plan's own writers
    in each of the three places a string goes: `emit`, a follow-up's `- `
    item (written inline by `render_plan`, so spelled the same here), and
    `Entry.write`'s path. Order is `SHAPES_OF_A_STRING`."""
    emitted: list[str] = []
    adopter.emit(emitted, "key", value, 2)
    item = f"  - {adopter.y(value)}"
    entry: list[str] = []
    adopter.Entry(value, adopter.Verdict("spec", "r", "why", "high"), 1,
                  1).write(entry)
    return [
        parse_yaml("top:\n" + "\n".join(emitted) + "\n")["top"]["key"],
        parse_yaml("top:\n" + item + "\n")["top"][0],
        parse_yaml("paths:\n" + "\n".join(entry) + "\n")[PATHS][0]["path"],
    ]


def assert_reads_back(adopter, value: str) -> None:
    for shape, got in zip(SHAPES_OF_A_STRING, readings(adopter, value)):
        said = (f"{value!r} was written as {adopter.y(value)} and read back "
                f"as {got!r} ({type(got).__name__}) as {shape}")
        assert isinstance(got, str), said
        assert got == value, said


# --- the round trip, through the real loader -------------------------------

@pytest.mark.parametrize("value", CANDIDATES,
                         ids=[repr(c) for c in CANDIDATES])
def test_every_candidate_reads_back_as_the_same_string(adopter, value):
    assert_reads_back(adopter, value)


def test_a_value_the_loader_reads_as_a_keyword_is_quoted(adopter):
    """The strings that were wrong, said out loud: `plan --spec-path null`
    wrote `spec_path: null` and `--tracking-branch true` wrote `true`."""
    for value in READ_AS_A_KEYWORD:
        assert adopter.y(value) == f'"{value}"', value


def test_every_casing_of_a_keyword_reads_back_as_text(adopter):
    """`NuLl` is text to this loader and `NULL` is not; whichever it is, the
    writer has to give back what it was handed."""
    for word in ("null", "true", FALSE_WORD, "yes", "no", "on", "off", "y", "n",
                 "nan", "inf", "none"):
        for spelling in casings(word):
            assert_reads_back(adopter, spelling)


def test_a_keyword_with_something_on_either_side_reads_back_as_text(adopter):
    for word in ("null", "true", "FALSE", "~", "yes"):
        for prefix, suffix in itertools.product(
                ("", ".", "_", "-", "x", " ", ":"), ("", ".", "_", ":", " ",
                                                    "-", " #", "x")):
            assert_reads_back(adopter, f"{prefix}{word}{suffix}")


#: `(alphabet, longest string)`. Exhaustive, not sampled. The first is made of
#: the letters of `null` and `true` in both cases, to the length of the
#: keywords themselves, so every spelling of those two is among them; the
#: second is the characters the loader treats specially.
EXHAUSTIVE = [("nulNULtreTRE", 4), ("ab:# -.0'\"\\", 3)]


@pytest.mark.parametrize("alphabet, longest", EXHAUSTIVE)
def test_every_short_string_over_an_alphabet_reads_back(adopter, alphabet,
                                                        longest):
    for length in range(1, longest + 1):
        for chars in itertools.product(alphabet, repeat=length):
            assert_reads_back(adopter, "".join(chars))


def test_generated_strings_read_back(adopter):
    """A seeded sample of longer strings over the whole printable ASCII range
    and a few non-ASCII letters, so a case nobody thought of still has to come
    back. No line break: see the module docstring."""
    rng = random.Random(181)
    alphabet = [chr(code) for code in range(32, 127)] + ["\t", "é",
                                                         "日"]
    words = ["null", "true", FALSE_WORD, "yes", "~", "on"]
    for _ in range(4000):
        if rng.random() < 0.35:
            value = rng.choice(words) + "".join(
                rng.choice(alphabet) for _ in range(rng.randint(0, 3)))
        else:
            value = "".join(rng.choice(alphabet)
                            for _ in range(rng.randint(0, 14)))
        assert_reads_back(adopter, value)


def test_a_float_a_bool_an_int_and_none_are_still_typed_values(adopter):
    """What is NOT a string is not quoted: the plan's counts and flags are
    numbers and booleans on purpose, and `None` is how `leg: null` says an
    entry is unresolved."""
    assert adopter.y(None) == "null"
    assert adopter.y(True) == "true"
    assert adopter.y(False) == FALSE_WORD
    assert adopter.y(0) == "0"
    assert adopter.y(1234) == "1234"
    assert adopter.y(0.5) == "0.5000"


# --- what round-trips is written as it always was --------------------------

#: `(value, how `main` wrote it)`. Ordinary plans must not change, so these
#: are the spellings that existed before #181. `yes`, `on` and `y` are bare
#: because THIS loader reads them as text; the guard is for a writer that
#: quotes every word that looks like a keyword somewhere.
#: Bare before and bare now: the plan's ordinary values, and the words that
#: only look like keywords to a YAML 1.1 reader.
BARE_AS_ALWAYS = [*ORDINARY, "yes", "No", "on", "OFF", "y", "N", ".inf",
                  ".nan", "nUll", "tRUE"]
UNCHANGED = [(word, word) for word in BARE_AS_ALWAYS] + [
    # Never bare, with or without #181:
    ("", '""'), ("~", '"~"'), ("1abc", '"1abc"'), ("007", '"007"'),
    ("1.5", '"1.5"'), ("-1", '"-1"'), ("a b", '"a b"'), ("a:", '"a:"'),
    (" a", '" a"'), ("a ", '"a "'), ("#x", '"#x"'), ("a #b", '"a #b"'),
    ("2026-10-09", '"2026-10-09"'), ("a\\b", '"a\\\\b"'),
    ('a"b', '"a\\"b"'),
]


@pytest.mark.parametrize("value, written", UNCHANGED,
                         ids=[repr(v) for v, _ in UNCHANGED])
def test_a_value_the_loader_reads_as_text_is_written_as_it_always_was(
        adopter, value, written):
    assert adopter.y(value) == written


# --- the writer asks the loader ---------------------------------------------

def test_the_writer_follows_the_loader_when_the_loader_learns_a_keyword(
        adopter, monkeypatch):
    """No list in `adopt-project.py` knows `yes`: it is bare today because
    the loader reads it as text. Teach the REAL reader that `yes` and `on` are
    booleans and the writer quotes them without an edit; everything the reader
    still reads as text stays bare."""
    reads = repo_shape._scalar

    def learned(raw):
        return True if raw.strip() in ("yes", "on") else reads(raw)

    assert adopter.y("yes") == "yes"
    assert adopter.y("on") == "on"
    monkeypatch.setattr(repo_shape, SCALAR_READER, learned)
    assert adopter.y("yes") == QUOTED_YES
    assert adopter.y("on") == '"on"'
    assert adopter.y("spec") == "spec"
    assert adopter.y("off") == "off"


def test_a_word_the_loader_refuses_is_quoted_not_raised(adopter, monkeypatch):
    """A line the reader will not read is a value it does not read back: when
    the loader RAISES on a bare word, the writer quotes it instead of letting
    `plan` die with a `YamlError` that names a line of a plan nobody has seen.
    No plain string raises today (the reader refuses `&x`, which `_PLAIN_RE`
    never lets through), so the loader is taught to."""
    reads = repo_shape._scalar

    def refusing(raw):
        if raw.strip() == "yes":
            raise repo_shape.YamlError("a word this reader does not take")
        return reads(raw)

    monkeypatch.setattr(repo_shape, SCALAR_READER, refusing)
    assert adopter.y("yes") == QUOTED_YES
    assert adopter.y("spec") == "spec"


@pytest.mark.parametrize("place, wrong", [
    ("k: yes\n", {"k": True}), ("- yes\n", [True])],
    ids=["after a key", "as a list item"])
def test_a_value_is_asked_about_in_each_place_it_is_written(
        adopter, monkeypatch, place, wrong):
    """The two places read a string differently (`- a:` is a one-key mapping,
    `k: a:` is not), and today the second is the stricter, so removing the
    first changes no output. A loader that misreads the word in ONE of them
    still has to get it quoted, so each question is pinned here."""
    reads = adopter.parse_yaml
    monkeypatch.setattr(adopter, "parse_yaml",
                        lambda text: wrong if text == place else reads(text))
    assert adopter.y("yes") == QUOTED_YES
    assert adopter.y("spec") == "spec"


# --- what `execute` writes into the project, asked of the same loader -------

#: How `manifest_misreads` says the loader read a null, spelled once.
NO_VALUE = "no value at all"
TRUE_READ = "the boolean true"
SEVEN_READ = "the number 7"
#: An election date in the basic ISO form, which the loader reads as a number.
DATE_DIGITS = "20260902"
#: How `check` and `execute` begin the line about each one.
MISREAD_FINDING = "FINDING plan-manifest-misread: "
#: How `check` begins #255's line about a value no file can hold.
UNWRITABLE_FINDING = "FINDING plan-unwritable-value: "
#: How `check` begins #261's line about a value the project's own
#: validate-manifest.py refuses.
INVALID_FINDING = "FINDING plan-manifest-invalid: "
#: How the remediation after the project's own validator's findings begins.
VALIDATOR_REMEDIATION_START = (
    "Remediation: choose a value the project's own validate-manifest.py "
    "accepts")
#: `true` as text, as a plan edited by hand quotes it, and `007` and
#: `null` too.
TRUE_TEXT = '"true"'
QUOTED_007 = '"007"'
QUOTED_NULL = '"null"'
#: How `plan`'s and `check`'s codes for #181's rule end.
MISREAD_CODE = "manifest-misread"
#: The plan key of the assembly's name, which an id nobody set comes from.
ASSEMBLY_KEY = "legs.assembly"
#: The election date a plan below is written with.
ELECTION_DATE = "2026-09-02"
#: The plan keys the rows below name, and the flag `plan` takes each as.
SPEC_PATH_KEY = "legs.spec_path"
TRACKING_KEY = "tracking_branch"
PINS_KEY = "pins"
ELECTED_BY_KEY = "elected_by"
ELECTED_ON_KEY = "elected_on"
REFERENCE_KEY = "reference"
VISIBILITY_KEY = "visibility"
SPEC_FLAG = "--spec-path"
TRACKING_FLAG = "--tracking-branch"
PIN_FLAG = "--pin"
ELECTED_BY_FLAG = "--elected-by"
MANIFEST = "project.yaml"
#: How a sentence names a plan key, where that is not the key itself: one of
#: `pins:` is an item of a list, a mapping since #273, and what `execute`
#: writes into the manifest for it is its product.
NAMED = {PINS_KEY: "the product of a pin in pins"}
#: And how `plan` names a flag's value, where that is not the flag itself:
#: `--pin` is `product@<40 hex>`, and the product is what is written.
FLAG_NAMED = {PIN_FLAG: "the product of a --pin"}
#: What `plan` records of a pin besides its product (#273), as a plan edited
#: by hand would carry it: a commit and a digest `check` reads no network
#: for, and how the digest was read.
PIN_COMMIT = "1" * 40
PIN_DIGEST = "2" * 64
PIN_DIGEST_SOURCE = "gh-api-tree-recursive"
#: The owner `plan` qualifies an unqualified `--pin` with.
PIN_OWNER = "opensoft"
#: The flag that names the stand-in clone a `--pin`'s digest is read from.
PIN_SOURCE_FLAG = "--pin-source"
#: The organisation every plan here is written for.
TEST_ORG = "testorg"
#: How every finding `check` prints begins.
ANY_FINDING = "FINDING"
#: The other flags the tools here are given, spelled once.
PLAN_OPTION = "--plan"
WORK_DIR_FLAG = "--work-dir"
#: What `check` says of a plan it passes.
PLAN_OK = "plan ok"
#: The key a leg's pin records its mount path under.
SUBMODULE_PATH = "submodule_path"
#: The parameters of the tests that carry a value spelled by hand.
KEY_SPELLED = "key, spelled"
#: The first line of the pin `plan` records for `openGlass`.
GLASS_ITEM = "  - product: openGlass"
#: The `_template_values` placeholders the tests below fill.
TRACKING_PLACEHOLDER = "TRACKING_BRANCH"
ELECTED_BY_PLACEHOLDER = "ELECTED_BY"
ELECTED_ON_PLACEHOLDER = "ELECTED_ON"
REFERENCE_PLACEHOLDER = "REFERENCE"
PINS_PLACEHOLDER = "NEUTRAL_PRODUCT_PINS"
#: The leg path and the branch the accepted end-to-end run is given.
LEGS_NULL = "legs/null"
Q4_BRANCH = "2026-q4"
#: A Windows `DOMAIN\user` name. Pasted raw between double quotes, the loader
#: makes the `\t` a tab (`DOUBLE_QUOTED_ESCAPES`), which a sentence names as
#: one; between the manifest's own quotes `render` spells it `"CORP\\tom"`
#: since #284, which reads back as typed.
DOMAIN_USER = "CORP\\tom"
DOMAIN_USER_READ = "the text `CORP`, then a tab, then `om`"
#: The same name with double quotes of its own, as a plan edited by hand
#: carries it: `'"CORP\tom"'`.
QUOTED_DOMAIN_USER = f"'\"{DOMAIN_USER}\"'"

#: `(flag, value, plan key, what the project's loader reads)`: values the
#: project's loader misreads on a line written bare, the branch as
#: `tracking_branch:` was before #259 (`bare_template`) and a pin's product
#: as an item of the manifest's `neutral_product_pins:` list was before #514
#: (`bare_pins`). At 76a6153 `--tracking-branch true` and `--pin null` went
#: through `execute` to `adoption verified`, the legs pushed on one branch
#: and put on another by the first bootstrap, and the pin gone; before #514
#: `--pin 007@<commit>` did, over a root whose own `validate-pins.py` refused
#: `entry 7`. The project's own validator, which reads the shipped
#: templates, makes no finding about any of them, and each branch is one the
#: source has (`holding`), so each is #181's, at `plan` and in a plan. Since
#: #273 a `--pin` is `<product>@<40 hex>` and a plan's pin a whole one
#: (`flag_args`, `whole_pin`): the value is the pin's product. On the
#: templates shipped since #259, and since #514 for the pins, each reads back
#: as typed (`READ_BACK`), so these rows ask the rule's own answer, in this
#: process.
REFUSED = [
    (TRACKING_FLAG, "true", TRACKING_KEY, TRUE_READ),
    (TRACKING_FLAG, "null", TRACKING_KEY, NO_VALUE),
    (TRACKING_FLAG, "007", TRACKING_KEY, SEVEN_READ),
    (PIN_FLAG, "null", PINS_KEY, NO_VALUE),
    (PIN_FLAG, "True", PINS_KEY, TRUE_READ),
    (PIN_FLAG, "007", PINS_KEY, SEVEN_READ),
]
#: #181's, as `plan` is given it, and as a plan carries it.
PLANNED = [(flag, value, reading) for flag, value, _, reading in REFUSED]
CARRIED = [(key, value, reading) for _, value, key, reading in REFUSED]

#: How a `READ_BACK` row names the value `plan` takes from the source when
#: no `--tracking-branch` is given: its default branch (#479).
DEFAULT_BRANCH = "default-branch"
#: The flags of the leg paths, and of the project an id is derived from.
CODE_FLAG = "--code-path"
PROJECT_FLAG = "--project"
#: `(flag, value)`: values the project's loader read as something else
#: while the templates wrote them bare. `plan` refused the branches as a
#: misread, and the leg paths and the ids, given or derived from
#: `--project`, as the project's own validator's (`manifest-leg-path`,
#: `manifest-id`); at 76a6153 each went through `execute` to `adoption
#: verified` and a bootstrap that failed or put the legs on another branch.
#: Since #259 (main's 47b1e06) each line is between double quotes and reads
#: back as typed, so each is planned, checked and written as given, with no
#: finding of #181's or the validator's. A branch is asked of a source that
#: has it (#479), and one row takes it from the source's default branch.
#: The pins were `REFUSED`'s rows while the manifest's list wrote its items
#: bare; since #514 (main's e6fbd748) `execute` writes each as `- "null"`,
#: `- "True"` and `- "007"`, which read back as typed too.
READ_BACK = [
    *[(TRACKING_FLAG, value) for value in ("true", "null", "007")],
    *[(SPEC_FLAG, value) for value in ("null", "Null", "NULL", "~", "true",
                                       FALSE_TITLE, "2026", "1.5")],
    (CODE_FLAG, "null"),
    ("--id", "true"), ("--id", "null"),
    (PROJECT_FLAG, "True"), (PROJECT_FLAG, "Null"),
    (DEFAULT_BRANCH, "true"),
    *[(PIN_FLAG, value) for value in ("null", "True", "007")],
]
#: The placeholders #259 put between double quotes in the assembly root's
#: templated YAML files, which `bare_template` writes bare again.
QUOTED_BY_259 = ("PROJECT_ID", "ELECTED_ON", "VISIBILITY", "TRACKING_BRANCH",
                 "SPEC_PATH", "CODE_PATH")


def ids_of(rows, key: int, value: int) -> list[str]:
    return [f"{row[key]}={row[value]!r}" for row in rows]


def checked(plan: Path):
    return run_script(ADOPT, "check", PLAN_OPTION, str(plan))


#: The directory `executed` names for the local remotes, which a run that is
#: refused before any leg exists never creates.
REMOTES = "remotes"


def execute_argv(plan: Path, tmp_path: Path) -> list[str]:
    """`execute`'s arguments for a run under local remotes."""
    return ["execute", PLAN_OPTION, str(plan), "--yes",
            "--local-remote-dir", str(tmp_path / REMOTES),
            WORK_DIR_FLAG, str(tmp_path / "work")]


def executed(plan: Path, tmp_path: Path):
    return run_script(ADOPT, *execute_argv(plan, tmp_path))


def run_here(adopter, capsys, *argv: str) -> tuple[int, str, str]:
    """`adopt-project.py <argv>` run in this process, where `bare_template`
    and `bare_pins` reach it: `(exit, stdout, stderr)`."""
    code = adopter.main(list(argv))
    said = capsys.readouterr()
    return code, said.out, said.err


def branches_of(source: Path) -> str:
    """The source's branches: no split branch until `execute` commits one."""
    return git("branch", "--list", cwd=source).stdout


def planned(tmp_path: Path, *extra: str, tree: dict | None = None) -> Path:
    source = make_source_repo(tmp_path / SOURCE_NAME, tree=tree)
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    return plan


def plan_argv(source: Path, out: Path, tmp_path: Path, *extra: str) -> list:
    """`plan`'s arguments for a run in this process (`adopter.main`): as
    `conftest.write_plan` gives them, with a work directory of the test's
    own."""
    return ["plan", "--source", str(source), PROJECT_FLAG, PROJECT_NAME,
            "--org", TEST_ORG, ELECTED_BY_FLAG, "Test Human", "--elected-on",
            ELECTION_DATE, WORK_DIR_FLAG, str(tmp_path / "work"), "--out",
            str(out), *extra]


def answer(plan: Path, path: str, leg: str) -> None:
    """`resolve` for an entry whose path the writer had to QUOTE, which
    `conftest.resolve` cannot find because it looks for the bare spelling."""
    text = text_of(plan)
    needle = f'  - path: "{path}"\n    leg: null\n'
    assert needle in text, f"{path} is not a quoted, unresolved entry"
    plan.write_text(text.replace(
        needle, f'  - path: "{path}"\n    leg: {leg}\n'
                '    resolution: "answered by the test"\n', 1),
        encoding=UTF8)


def misread(what: str, value: str, reading: str) -> tuple[str, str]:
    """The two halves of the sentence `manifest_misreads` writes: who, and
    what the loader made of it, with the fix. The value is shown as it is
    typed, between backticks, never as `repr` spells it: `CORP\\tom` is not
    `'CORP\\\\tom'` (review181's N1). Every value here is printable, which
    is what lets this oracle be the backticks alone."""
    assert value.isprintable(), value
    return (f"{what} is `{value}`, which `execute` writes into ",
            f"reads it back as {reading} and not as that text: choose "
            "another value.")


@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> tuple[Path, str]:
    """One source and one answered plan of it, which `check` passes, for the
    tests below to copy and edit. No test below writes into this source:
    `plan` and `check` only read it, and a test that runs `execute` runs it
    on a copy of its own (`answered_copy`)."""
    base = tmp_path_factory.mktemp("misread")
    source = make_source_repo(base / SOURCE_NAME)
    plan = base / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    assert checked(plan).returncode == 0
    return source, text_of(plan)


#: The plan's line naming its source, which `answered_copy` points at a copy.
SOURCE_LINE = re.compile(r"^  local_path: .*$", re.MULTILINE)


@pytest.fixture
def answered_copy(adopter, answered, tmp_path) -> tuple[Path, str]:
    """`answered` for a test that runs `execute`: a copy of the source of its
    own, and the plan's text with `local_path:` naming that copy.

    `execute` commits its split branch into the source it is given. Were the
    source shared, a regression that let one `execute` through would leave
    that branch in the source of every test after it, and each later
    `execute` test would fail at its last assertion for a reason that is
    not its own: one test's run must never change another's input."""
    source, text = answered
    assert len(SOURCE_LINE.findall(text)) == 1, "one `local_path:` line"
    copy = tmp_path / SOURCE_NAME
    shutil.copytree(source, copy, symlinks=True)
    return copy, SOURCE_LINE.sub(
        lambda _match: f"  local_path: {adopter.y(str(copy))}", text, count=1)


@pytest.fixture
def glass(tmp_path) -> tuple[Path, str]:
    """A stand-in clone of a neutral product, `(path, commit)`, for `plan
    --pin <product>@<commit> --pin-source <path>` to read a digest from with
    no network (#273). The product's name is the `--pin`'s, not the clone's."""
    path = tmp_path / "pin-source" / OPEN_GLASS
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    (path / "glass.txt").write_bytes(b"openGlass\n")
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "one",
        cwd=path)
    return path, git("rev-parse", "HEAD", cwd=path).stdout.strip()


def holding(source: Path, key: str, branch) -> None:
    """Since #479 a tracking branch that is no branch of the source is
    `plan-tracking-branch-missing` alone, so a row about the tracking branch
    is asked of a source that has it as its own branch: `branch`, as the
    plan's loader reads it, spelled as `execute` takes it (`str`). One
    branch per copy of the source, because `true` and `True` are one file
    on a disk that ignores case."""
    if key in (TRACKING_KEY, TRACKING_FLAG):
        git("branch", str(branch), cwd=source)


def flag_args(source: Path, glass: tuple[Path, str], flag: str,
              value: str) -> tuple[str, ...]:
    """`plan`'s arguments for one row of a flag's: a `--pin` is
    `<product>@<40 hex>` read from the stand-in clone (#273), and a
    `--tracking-branch` names a branch the source has (#479)."""
    holding(source, flag, value)
    if flag != PIN_FLAG:
        return flag, value
    path, commit = glass
    return PIN_FLAG, f"{value}@{commit}", PIN_SOURCE_FLAG, str(path)


def whole_pin(spelled: str) -> str:
    """`pins:` holding one pin as `plan` records it since #273, its
    `product:` spelled as given: product, repository, commit, digest and
    how the digest was read. The repository is named after the product as
    the plan's loader reads it, as `plan` names it, so that `_read_pins`
    asks about the product alone."""
    read = parse_yaml(f"product: {spelled}\n")["product"]
    return ("pins:\n"
            f"  - product: {spelled}\n"
            "    repository: "
            f"{repo_shape.double_quoted(f'{PIN_OWNER}/{read}')}\n"
            f'    commit: "{PIN_COMMIT}"\n'
            f'    tree_sha256: "{PIN_DIGEST}"\n'
            f"    digest_source: {PIN_DIGEST_SOURCE}\n")


def carrying(plan: Path, text: str, key: str, spelled: str) -> None:
    """Write `text`, an answered plan, to `plan` with `key` set to `spelled`
    exactly as given: a plan edited by hand, or written by a `plan` older
    than this check. LF, as `plan` writes it. A pin is a whole one, whose
    product is `spelled` (`whole_pin`)."""
    if key == PINS_KEY:
        edited = text.replace("\npins: []\n", "\n" + whole_pin(spelled), 1)
    else:
        leaf = key.split(".")[-1]
        indent = "  " if key.startswith("legs.") else ""
        line = re.compile(rf"^{indent}{leaf}: .*$", re.MULTILINE)
        assert line.search(text), f"no `{key}` line in the plan"
        edited = line.sub(lambda _match: f"{indent}{leaf}: {spelled}", text,
                          count=1)
    assert edited != text, key
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(edited)


@pytest.mark.parametrize("flag, value, reading", PLANNED,
                         ids=ids_of(PLANNED, 0, 1))
def test_plan_refuses_a_value_the_projects_loader_would_misread(
        adopter, answered_copy, glass, bare_template, bare_pins, tmp_path,
        capsys, flag, value, reading):
    """Before the plan is written: the flag, the value, what the project's
    loader would read, and the fix. Asked where the line is bare
    (`bare_template`, `bare_pins`), in this process."""
    source, _ = answered_copy
    plan = tmp_path / PLAN_FILE
    code, _, stderr = run_here(adopter, capsys, *plan_argv(
        source, plan, tmp_path, *flag_args(source, glass, flag, value)))
    assert code == 2, stderr
    assert stderr.startswith("REFUSED adopt-manifest-misread: "), stderr
    who, what = misread(FLAG_NAMED.get(flag, flag), value, reading)
    assert who in stderr, stderr
    assert what in stderr, stderr
    assert "No plan was written." in stderr
    assert not plan.exists()


#: How a refusal or a finding in the validator's words goes on, once it has
#: named the value.
VALIDATOR_REFUSES = "which the project's own validate-manifest.py refuses: "


@pytest.fixture
def bare_template(adopter, tmp_path, monkeypatch) -> Path:
    """The templates #181's gate reads (`ASSEMBLY_TEMPLATE`), each line #259
    quoted written bare again, as it was before #259.

    The gate asks the line `execute` writes, and since #259 every line it
    asks about but the pins' list is quoted, where no value is misread (the
    pins' list since #514: `bare_pins`). What it says of a line written bare
    -- how it names a value, which values it asks about at all, and what
    `plan`, `check` and `execute` do with that answer -- is still the rule's
    own answer, and a test of that is asked here, of the gate directly or of
    `plan`, `check` or `execute` in this process (`run_here`). No run as a
    process of its own sees this copy, nor the leg-path rule
    (`leg_path_problem`, #266) unless a test points it here too, nor the
    validator, which reads the shipped templates. The copy is a templates
    directory's `assembly-root`, as the shape's own is."""
    copy = tmp_path / "bare-templates" / "assembly-root"
    shipped = ""
    for rel in adopter.TEMPLATED_YAML:
        text = (adopter.ASSEMBLY_TEMPLATE / rel).read_text(encoding=UTF8)
        shipped += text
        for placeholder in QUOTED_BY_259:
            text = text.replace(f'"{{{{{placeholder}}}}}"',
                                f"{{{{{placeholder}}}}}")
        target = copy / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding=UTF8)
    assert all(f'"{{{{{placeholder}}}}}"' in shipped
               for placeholder in QUOTED_BY_259), "#259's quotes moved"
    monkeypatch.setattr(adopter, "ASSEMBLY_TEMPLATE", copy)
    return copy


def pins_written_bare(pins) -> str:
    """The manifest's `neutral_product_pins:` list as `_template_table`
    wrote it before #514: each product bare, as it stands."""
    if not pins:
        return "[]"
    return "\n" + "\n".join(f"  - {product}" for product in sorted(pins))


@pytest.fixture
def bare_pins(adopter, monkeypatch) -> None:
    """The manifest's pins' list written bare again, as it was before #514
    (main's e6fbd748), whose `_neutral_product_pins` quotes an item the
    project's reader would misread and which `_template_table` takes the
    list from. The gate asks that table (`_pin_field`), so on the shipped
    code it finds no pin misread; what it says of a bare item -- how it
    names a pin's product, at `plan` and in a plan, and which pins it asks
    about at all -- is still the rule's own answer, asked here in this
    process. The validator is asked of the same table, so a manifest its
    reader refuses is the validator's here too."""
    assert adopter._neutral_product_pins(["007"]) == '\n  - "007"', (
        "#514's quotes moved")
    monkeypatch.setattr(adopter, "_neutral_product_pins", pins_written_bare)


def planned_as_given(tmp_path: Path, glass: tuple[Path, str], flag: str,
                     value: str) -> tuple[Path, Path]:
    """`(source, plan)` for a `READ_BACK` row: `plan` given the flag, or the
    project an id is derived from, or a source whose default branch is the
    value, then answered. A branch is one the source has (#479), and a pin's
    digest is read from the stand-in clone (`flag_args`)."""
    default = value if flag == DEFAULT_BRANCH else "main"
    source = make_source_repo(tmp_path / SOURCE_NAME, branch=default)
    extra = (() if flag in (DEFAULT_BRANCH, PROJECT_FLAG)
             else flag_args(source, glass, flag, value))
    plan = tmp_path / PLAN_FILE
    written = write_plan(
        source, plan, project=value if flag == PROJECT_FLAG else PROJECT_NAME,
        extra=extra)
    assert written.returncode == 0, written.stdout + written.stderr
    assert "REFUSED" not in written.stderr, written.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return source, plan


def as_given(flag: str, value: str) -> str:
    """What the row's value must read back as: an id `plan` derives from
    `--project` is the project lowercased, and everything else as typed."""
    return value.lower() if flag == PROJECT_FLAG else value


def where_it_lands(flag: str) -> tuple[tuple, tuple]:
    """`(in the plan, in project.yaml)`: where the row's value lands in
    each, as the steps into what its loader reads. A leg is the second or
    third of the manifest's `legs:`; the assembly is the first. A pin is
    the plan's one pin, by its product, and the manifest's one item of
    `neutral_product_pins:`."""
    if flag in (TRACKING_FLAG, DEFAULT_BRANCH):
        return (TRACKING_KEY,), (TRACKING_KEY,)
    if flag == PIN_FLAG:
        return (PINS_KEY, 0, "product"), ("neutral_product_pins", 0)
    if flag in (SPEC_FLAG, CODE_FLAG):
        role = flag[2:6]
        return (("legs", f"{role}_path"),
                ("legs", 1 if role == "spec" else 2, "path"))
    return ("id",), ("id",)


def read_at(loaded, steps: tuple):
    """What a loader read at `steps` into what it loaded."""
    for step in steps:
        loaded = loaded[step]
    return loaded


@pytest.mark.parametrize("flag, value", READ_BACK,
                         ids=ids_of(READ_BACK, 0, 1))
def test_a_value_the_template_quotes_is_planned_and_checked_as_given(
        glass, tmp_path, flag, value):
    """`plan` refused each of these, as #181's misread or in the project's
    own validator's words (`manifest-leg-path`, `manifest-id`), while the
    template wrote its line bare, and a pin's product while the manifest's
    list did. Since #259 the line is quoted, and since #514 the list's item
    where the reader would misread it, and each reads back as typed: `plan`
    writes the plan, which reads the value back as given, and `check`
    passes it with no finding at all."""
    _, plan = planned_as_given(tmp_path, glass, flag, value)
    in_plan, _ = where_it_lands(flag)
    assert read_at(load_yaml(plan), in_plan) == as_given(flag, value)
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert PLAN_OK in result.stdout, result.stdout
    assert ANY_FINDING not in result.stderr, result.stderr


@needs_filter_repo
@pytest.mark.parametrize("flag, value", READ_BACK,
                         ids=ids_of(READ_BACK, 0, 1))
def test_execute_writes_a_value_the_template_quotes_as_given(
        glass, tmp_path, flag, value):
    """`execute` refused each of these before any leg existed, as #181's
    misread or as the validator's. Since #259 it writes each between double
    quotes, and since #514 a pin's product as a quoted item of the
    manifest's list (`- "007"`); it ends `adoption verified`, and the
    split's `project.yaml` reads the value back as given; a leg path reads
    back from its pin's `submodule_path:` too, a pin's product from its own
    `contracts/<product>-pin.yaml` (`product: "007"`, since #516), and the
    legs are pushed on the branch."""
    source, plan = planned_as_given(tmp_path, glass, flag, value)
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout, result.stdout
    assert MISREAD_CODE not in result.stdout + result.stderr

    def shown(rel: str) -> dict:
        return parse_yaml(git("show", f"{SPLIT_BRANCH}:{rel}",
                              cwd=source).stdout)

    _, in_manifest = where_it_lands(flag)
    assert read_at(shown(MANIFEST), in_manifest) == as_given(flag, value)
    if flag == PIN_FLAG:
        manifest = git("show", f"{SPLIT_BRANCH}:{MANIFEST}", cwd=source)
        assert f'\n  - "{value}"\n' in manifest.stdout, manifest.stdout
        assert shown(neutral_pin_path(value))["product"] == value
    if flag in (SPEC_FLAG, CODE_FLAG):
        pin = shown(f"contracts/{flag[2:6]}-pin.yaml")
        assert pin[SUBMODULE_PATH] == value
    if flag in (TRACKING_FLAG, DEFAULT_BRANCH):
        for leg in ("spec", "code"):
            heads = git("for-each-ref", "--format=%(refname:short)",
                        "refs/heads",
                        cwd=tmp_path / REMOTES / f"{PROJECT_NAME}-{leg}.git")
            assert heads.stdout.split() == [value], leg


def test_the_misread_rule_names_an_id_plan_derived_by_where_it_came_from(
        adopter, bare_template, tmp_path):
    """Where #181 refuses an id `plan` derived, its sentence says where the
    value came from, so the person knows the flag that chooses another.
    Since #259 the template quotes `id:`, and `true` reads back there
    (`READ_BACK`), so `plan` is asked here of a bare line
    (`bare_template`), in this process: what is left is the rule's own
    answer. The validator, which reads the shipped template, accepts the
    id `true`, as it does on main."""
    args = argparse.Namespace(
        project="True", org=TEST_ORG, id=None, visibility="private",
        elected_by="Test Human", elected_on=ELECTION_DATE, reference=None,
        tracking_branch="main", spec_path="spec", code_path="code", pin=[],
        pin_owner=PIN_OWNER, pin_source=None, out=str(tmp_path / PLAN_FILE))
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    source = argparse.Namespace(repository=None)
    with pytest.raises(adopter.Refusal) as refused:
        adopter._checked_plan_inputs(args, source, naming)
    assert refused.value.code == "adopt-manifest-misread", refused.value
    who, what = misread("--id (not given, so --project lowercased)", "true",
                        TRUE_READ)
    assert refused.value.detail.startswith(who), refused.value.detail
    assert refused.value.detail.endswith(what), refused.value.detail


def test_plan_takes_an_elector_from_git_the_manifests_quotes_read_back(
        answered, tmp_path):
    """No `--elected-by`: `plan` asks `git config user.name`. A `CORP\\tom`
    there was refused while `render` pasted it raw between the manifest's
    quotes, where the loader made its `\\t` a tab. Since #284 `execute`
    writes it `"CORP\\\\tom"`, which reads back as typed, so `plan` writes
    the plan and `check` passes it."""
    source, _ = answered
    plan = tmp_path / PLAN_FILE
    result = run_script(
        ADOPT, "plan", "--source", str(source), PROJECT_FLAG, PROJECT_NAME,
        "--org", TEST_ORG, "--elected-on", ELECTION_DATE, "--out", str(plan),
        env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name",
             "GIT_CONFIG_VALUE_0": DOMAIN_USER})
    assert result.returncode == 0, result.stdout + result.stderr
    assert '\nelected_by: "CORP\\\\tom"\n' in text_of(plan)
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    passed = checked(plan)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert MISREAD_CODE not in passed.stderr


@pytest.mark.parametrize("key, value, reading", CARRIED,
                         ids=ids_of(CARRIED, 0, 1))
def test_check_reports_a_plan_carrying_one(
        adopter, answered_copy, bare_template, bare_pins, tmp_path, capsys,
        key, value, reading):
    """A plan carrying the value -- spelled by the plan writer, so the plan
    itself reads it back -- is a FINDING, with the remediation once after.
    It is #181's alone, one finding: the project's own validator, asked
    first, makes no finding about what the loader reads of it, and `execute`
    writes it in every mode. Asked where the line is bare (`bare_template`,
    `bare_pins`), in this process."""
    source, text = answered_copy
    holding(source, key, value)
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, adopter.y(value))
    code, stdout, stderr = run_here(adopter, capsys, "check", PLAN_OPTION,
                                    str(plan))
    assert code == 1, stdout + stderr
    who, what = misread(NAMED.get(key, key), value, reading)
    (line,) = judged_lines(stderr)
    assert line.startswith(f"{MISREAD_FINDING}{who}"), stderr
    assert what in stderr, stderr
    assert stderr.count("Remediation: ") == 1, stderr
    assert stderr.count(adopter.MANIFEST_MISREAD_REMEDIATION) == 1
    assert PLAN_OK not in stdout


def judged_lines(stderr: str) -> list[str]:
    """The lines of #181's rule and the validator's, in the order printed."""
    return [line for line in stderr.splitlines()
            if line.startswith((MISREAD_FINDING, INVALID_FINDING))]


#: How a plan sets no id, each beside how it spells the assembly the id is
#: then derived from. The first pair is what `main`'s
#: `plan --project True --id null` writes: `id: null`, and a bare `True`
#: its loader reads as a boolean. The rest are this branch's quoted `True`
#: with `~`, nothing, and no `id:` line at all.
NO_ID = [
    pytest.param("id: null\n", "True", id="main-plan-project-True-id-null"),
    pytest.param("id: ~\n", QUOTED_TRUE, id="tilde"),
    pytest.param("id:\n", QUOTED_TRUE, id="nothing"),
    pytest.param("", QUOTED_TRUE, id="no-id-line"),
]


def without_an_id(text: str, id_line: str) -> str:
    """The answered plan's text with its `id:` line put as `id_line`."""
    edited = re.sub(r"^id: .*\n", id_line, text, count=1, flags=re.MULTILINE)
    assert edited != text, "no `id:` line in the plan"
    return edited


@pytest.mark.parametrize("id_line, assembly", NO_ID)
def test_check_passes_an_id_it_derived_from_the_assembly_as_the_text_it_is(
        answered, tmp_path, id_line, assembly):
    """A plan that sets no id gets one from `execute`, which lowercases
    `legs.assembly`: `true`. While the template wrote `id:` bare the loader
    read that as a boolean, and the validator refused it as that (`id is
    True`). Since #259 the line is quoted, `true` reads back as the id it
    is, which the validator accepts, and `check` passes the plan with no
    finding."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, without_an_id(text, id_line), ASSEMBLY_KEY, assembly)
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert PLAN_OK in result.stdout, result.stdout
    assert ANY_FINDING not in result.stderr, result.stderr


@pytest.mark.parametrize("id_line, assembly", NO_ID)
def test_the_misread_rule_names_an_id_it_derived_from_the_assembly(
        adopter, answered, bare_template, tmp_path, id_line, assembly):
    """Where #181 reports an id `execute` derives from `legs.assembly`, its
    sentence says so, because the line to change is not the one with the
    value. It says "not set in the plan" and not "not in the plan": an `id:
    null` is in the plan and sets nothing (review181's N3), and `Plan.get`
    reads it exactly as a missing key. Since #259 the template quotes `id:`,
    where `true` reads back, so this is the rule's own answer for a bare
    line (`bare_template`), asked of it directly."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, without_an_id(text, id_line), ASSEMBLY_KEY, assembly)
    who, what = misread("id (not set in the plan, so legs.assembly "
                        "lowercased)", "true", TRUE_READ)
    said = adopter.manifest_misreads([adopter._id_field(
        adopter.Plan.load(plan))])
    assert len(said) == 1, said
    assert said[0].startswith(who), said
    assert said[0].endswith(what.rstrip(".")), said


#: `(plan key, as a hand-edited plan spells it, what the plan's loader reads
#: it as, the text `execute` writes for it)`. The plan's loader reads each
#: one as something that is not text, so the plan does not say what `str`
#: of it says: `007` is read as 7, and `TRUE` as true, and `execute` writes
#: `str` of what was read. While the template wrote these lines bare, the
#: project's loader read that text back as the same kind again, and #181
#: named the branch by what was READ, with its kind, and then the text
#: `execute` writes (review181's N2); the validator refused the id as `id is
#: 7`. Since #259 the line is quoted and `7` reads back as the text `7`, so
#: nothing names any of them, as on main: `execute` writes `7` for a plan
#: that says `007`. A date or a visibility read as not text is still
#: refused (`LATE_DATES`, `NOT_TEXT_INVALID`), and a pin's product is #273's
#: (`test_a_pin_whose_product_is_not_text_is_273s_finding_alone`). The
#: source has the branch as `execute` takes it, `str` of what was read
#: (#479).
READ_AS_NOT_TEXT = [
    (TRACKING_KEY, "007", SEVEN_READ, "7"),
    (TRACKING_KEY, "TRUE", TRUE_READ, "True"),
    (TRACKING_KEY, "1.50", "the number 1.5", "1.5"),
    ("id", "007", SEVEN_READ, "7"),
]


@pytest.mark.parametrize("key, spelled, read_as, written", READ_AS_NOT_TEXT,
                         ids=ids_of(READ_AS_NOT_TEXT, 0, 1))
def test_check_passes_a_plan_value_read_as_not_text_as_main_does(
        answered_copy, tmp_path, key, spelled, read_as, written):
    """`check` named each of these, the branch as #181's misread and the id
    in the validator's words, while the template wrote its line bare. Since
    #259 the line is quoted, the text `execute` writes reads back, and
    neither rule has a finding: `check` passes the plan, as main does, and
    `execute` writes `str` of what was read, `7` for `007` (a residual this
    change shares with main, in its description). `read_as` is the
    misread rule's answer for a bare line, asked in the test below."""
    source, text = answered_copy
    holding(source, key, written)
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert PLAN_OK in result.stdout, result.stdout
    assert ANY_FINDING not in result.stderr, result.stderr


@pytest.mark.parametrize("key, spelled, read_as, written", READ_AS_NOT_TEXT,
                         ids=ids_of(READ_AS_NOT_TEXT, 0, 1))
def test_the_misread_rule_names_a_plan_value_that_is_not_text_by_what_was_read(
        adopter, answered, bare_template, tmp_path, key, spelled, read_as,
        written):
    """The finding said `tracking_branch is '7'` for a plan that says `007`,
    and `'True'` for `TRUE`: `str` of what was read, which the plan never
    said. It says what the plan's loader read, and the text `execute`
    writes for it, which is `str` of that and is named as such; an id too,
    never `str` of what `Plan.project_id` makes of it. Since #259 the
    template quotes these lines, so this is the rule's answer for a bare one
    (`bare_template`), asked of `_misread_findings` directly."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    (said,) = adopter._misread_findings(adopter.Plan.load(plan))
    named = NAMED.get(key, key)
    assert said.startswith(f"{MISREAD_FINDING}{named} was read out of the "
                           f"plan as {read_as}, which `execute` writes "
                           "into "), said
    assert said.endswith(f"reads it back as {read_as} and not as the text "
                         f"`{written}`: choose another value."), said
    assert f"{named} is " not in said, "`str` of it was echoed"


#: `(plan key, as a plan edited by hand spells it)`: values the project's
#: loader misread where a template wrote them bare, which `execute` never
#: writes. It refuses the branch as `unsafe-value` (`_checked_plan_values`),
#: and `gh repo create` takes no `--true`, before anything is written. A
#: finding would say the value is written and the run ends `adoption
#: verified`: for these neither is true (rv181f's F2, F2b). Since #261 the
#: visibility is the project's own validator's finding instead
#: (`JUDGED_ONCE`).
#:
#: So is every other visibility outside the three choices, in gh mode,
#: `execute`'s default: `gh repo create` would be handed `--null`, `--` or
#: `--'private'` before any leg exists, and `check` is not told the mode.
#: The texts the loader read as no value, or as one of the three, while the
#: template wrote `visibility:` bare were ones the validator accepted as
#: read, and nothing named them (rv181f's G3). Since #259 the line is quoted,
#: each is the text it is, and the validator refuses it, in either mode,
#: before anything exists.
#:
#: So is a branch the loader misreads that git will not create, `~`, read
#: as no value where it is bare. No source has it, so it is #479's
#: `plan-tracking-branch-missing`, and `execute` refuses it before any leg
#: exists (rv181f's H1).
#:
#: On the templates shipped since #259 each of these lines is quoted and
#: reads back, and `check` names none of them misread whatever the rule
#: asks; `test_the_misread_rule_asks_nothing_of_a_value_execute_never_writes`
#: asks the rule of a bare line.
NEVER_WRITTEN = [
    pytest.param(TRACKING_KEY, QUOTED_DOMAIN_USER, id=TRACKING_KEY),
    pytest.param(TRACKING_KEY, '"~"', id="tracking_branch-tilde"),
    pytest.param(VISIBILITY_KEY, TRUE_TEXT, id=VISIBILITY_KEY),
    *[pytest.param(VISIBILITY_KEY, spelled, id=f"visibility-{name}")
      for spelled, name in [
          ('""', "empty"), ("''", "empty-single"), (QUOTED_NULL, "null"),
          ('"Null"', "Null"), ('"NULL"', "NULL"), ('"~"', "null-tilde"),
          ('"#"', "hash"), ('"#x"', "hash-x"), ('" "', "space"),
          ('"  "', "spaces"), ("|-", "block"), ("\"'private'\"", "private"),
          ("'\"public\"'", "public"), ("\"'internal'\"", "internal")]],
]


@pytest.mark.parametrize(KEY_SPELLED, NEVER_WRITTEN)
def test_check_says_nothing_misread_of_a_value_execute_never_writes(
        adopter, answered, tmp_path, key, spelled):
    """`check` asked the loader about every value, and named these as
    misread, with a remediation saying the run would still end `adoption
    verified`. It asks only about a value `execute` gets as far as writing
    in every mode."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


@pytest.mark.parametrize(KEY_SPELLED, NEVER_WRITTEN)
def test_the_misread_rule_asks_nothing_of_a_value_execute_never_writes(
        adopter, answered, bare_template, tmp_path, key, spelled):
    """Asked of a bare line (`bare_template`), the rule still names none of
    these: `_execute_gets_to_write` leaves out the branch `execute` refuses
    as `unsafe-value`, the one git will not create and every visibility
    outside the three choices, and the validator, asked first, judges each
    such visibility as well. Asked of `_misread_findings` directly."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    assert adopter._misread_findings(adopter.Plan.load(plan)) == []


#: A tracking branch the loader reads as no value, and git will not create.
BRANCH_GIT_REFUSES = "~"


def test_plan_refuses_a_branch_git_will_not_create_in_gits_words(
        answered, tmp_path):
    """`plan` refused `--tracking-branch ~` as misread, with a remediation
    saying `execute` writes it and the run would still end `adoption
    verified` (rv181f's H1). Git will not create `~`, so no source has it,
    and since #520 `plan` asks git about the flag: it refuses it as
    `adopt-bad-tracking-branch`, in git's words, and never as misread, and
    writes no plan (#420)."""
    source, _ = answered
    plan = tmp_path / PLAN_FILE
    result = write_plan(source, plan,
                        extra=(TRACKING_FLAG, BRANCH_GIT_REFUSES))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED adopt-bad-tracking-branch: " in result.stderr
    assert "adopt-manifest-misread" not in result.stderr, result.stderr
    assert not plan.exists()


def test_git_is_asked_only_about_a_branch_the_loader_misreads(
        adopter, bare_template, monkeypatch):
    """`branch_problem` starts git. It is asked about `~` and `true`, which
    the loader misreads on a bare line, and not about `develop`, which it
    reads back, so a plan whose values all read back starts no process. Git
    creates `true`, so that one is the misread rule's. Since #259 the
    template quotes the branch, where no branch is misread and git is asked
    nothing, so this is asked of a bare line (`bare_template`)."""
    asked = []
    real = adopter.branch_problem

    def recorded(what, value):
        asked.append(value)
        return real(what, value)

    monkeypatch.setattr(adopter, "branch_problem", recorded)
    assert adopter._execute_gets_to_write(TRACKING_KEY, "develop")
    assert not adopter._execute_gets_to_write(TRACKING_KEY,
                                              BRANCH_GIT_REFUSES)
    assert adopter._execute_gets_to_write(TRACKING_KEY, "true")
    assert asked == [BRANCH_GIT_REFUSES, "true"]


@needs_filter_repo
def test_execute_refuses_that_branch_as_unsafe_before_any_leg_exists(
        answered_copy, tmp_path):
    """What `execute` does with the branch `check` no longer calls misread:
    it refuses it as `unsafe-value`, before it creates a leg or touches the
    source, so no sentence of `check`'s says it gets further."""
    source, text = answered_copy
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, TRACKING_KEY, QUOTED_DOMAIN_USER)
    assert MISREAD_FINDING not in checked(plan).stderr
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED unsafe-value: {TRACKING_KEY} is "), result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


# --- the tracking branch is a branch of the source (main's #479) ------------

#: How #479's finding, and the note `plan` prints for the same branch, begin.
BRANCH_MISSING = "FINDING plan-tracking-branch-missing: `tracking_branch` is "
BRANCH_NOTED = "NOTE the tracking branch is `true`, which is no branch of "


def test_a_misread_branch_the_source_lacks_is_479s_finding_alone(
        adopter, answered, tmp_path):
    """`execute` refuses a tracking branch that is no branch of the source
    before any leg exists (#479), so it never writes it. At the merge of
    main cc8f2da `check` named `true` there twice, #479's finding and a
    misread one saying `execute` writes it and the run ends `adoption
    verified`, and `plan` refused it under that remediation. `plan` records
    it with #479's note, as main does, and `check` says #479's finding
    alone. Since #259 the shipped template quotes the branch, where `true`
    reads back, so this passes there with the misread rule asking nothing;
    `test_a_branch_execute_does_not_push_in_every_mode_is_never_misread`
    asks the rule where the line is bare."""
    source, _ = answered
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=(TRACKING_FLAG, "true"))
    assert written.returncode == 0, written.stdout + written.stderr
    assert BRANCH_NOTED in written.stdout, written.stdout
    assert MISREAD_CODE not in written.stdout + written.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert f"{BRANCH_MISSING}`true`, which is no branch of the source " in (
        result.stderr), result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


def with_origin(tmp_path: Path, branch: str | None) -> Path:
    """A source whose remote `origin` has been fetched, `origin` holding
    `branch` beside `main` where one is given, and the source no branch of
    its own but `main`. `origin` is under `testorg/Northwind`, the
    repository `plan` is given, because `plan` reads the source's
    repository from its `origin`'s last two directories and refuses a plan
    for another (#499)."""
    seed = make_source_repo(tmp_path / TEST_ORG / PROJECT_NAME)
    if branch:
        holding(seed, TRACKING_KEY, branch)
    source = make_source_repo(tmp_path / SOURCE_NAME)
    git("remote", "add", "origin", str(seed), cwd=source)
    git("fetch", "-q", "origin", cwd=source)
    return source


def test_a_misread_branch_origin_lacks_is_479s_finding_alone(
        adopter, tmp_path):
    """The source has `true` as its own branch, and its fetched `origin`,
    the repository the split's pull request goes to, does not. `check`
    reads `origin`'s branches and finds it `plan-tracking-branch-missing`,
    which `execute` refuses before any leg exists in either mode, so it is
    #479's finding alone, as at `plan`, though the source itself has it.
    On the shipped templates, which quote the branch since #259, this
    passes with the misread rule asking nothing; the rule is asked where
    the line is bare in
    `test_a_branch_execute_does_not_push_in_every_mode_is_never_misread`."""
    source = with_origin(tmp_path, None)
    holding(source, TRACKING_KEY, "true")
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=(TRACKING_FLAG, "true"))
    assert written.returncode == 0, written.stdout + written.stderr
    assert BRANCH_NOTED in written.stdout, written.stdout
    assert MISREAD_CODE not in written.stdout + written.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"{BRANCH_MISSING}`true`, which is no branch of the source's "
            "remote `origin` ") in result.stderr, result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


def origin_only(tmp_path: Path) -> tuple[Path, Path]:
    """`(source, plan)`: a source whose remote `origin` has the branch
    `true`, fetched, and which has no branch of its own by that name,
    planned and answered with `--tracking-branch true`. `plan` notes
    nothing: `origin` has it."""
    source = with_origin(tmp_path, "true")
    assert "true" not in branches_of(source).split()
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=(TRACKING_FLAG, "true"))
    assert written.returncode == 0, written.stdout + written.stderr
    assert "NOTE the tracking branch" not in written.stdout, written.stdout
    assert MISREAD_CODE not in written.stdout + written.stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return source, plan


def test_a_misread_branch_only_origin_has_is_named_by_neither(
        adopter, tmp_path):
    """In gh mode the split goes to `origin`, which has the branch, and
    `execute` would write it; under `--local-remote-dir` it is pushed back
    into the source, which does not, and `execute` refuses it before any
    leg exists. `check` is not told the mode, so a sentence saying
    `execute` writes it would be false in one of them: `check` passes the
    plan, as main does. On the shipped templates, which quote the branch
    since #259, it passes because `true` reads back there; where the line
    is bare, `_pushed_in_every_mode` is what keeps the rule silent
    (`test_a_branch_execute_does_not_push_in_every_mode_is_never_misread`)."""
    _, plan = origin_only(tmp_path)
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert PLAN_OK in result.stdout, result.stdout
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


@needs_filter_repo
def test_execute_refuses_a_branch_only_origin_has_under_a_local_remote(
        tmp_path):
    """What makes the misread sentence false there: main's `execute` asks
    the source itself, the remote under `--local-remote-dir`, and refuses
    the branch before any leg exists (#479)."""
    source, plan = origin_only(tmp_path)
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED plan-tracking-branch-missing: `tracking_branch` is `true`, "
    ), result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


def branch_source(tmp_path: Path, own: bool, origin: bool | None) -> Path:
    """A source for the branch `true`: one of its own where `own`; a
    fetched remote `origin` that has it where `origin` is True, lacks it
    where False, and no `origin` at all where None."""
    if origin is None:
        source = make_source_repo(tmp_path / SOURCE_NAME)
    else:
        source = with_origin(tmp_path, "true" if origin else None)
    if own:
        holding(source, TRACKING_KEY, "true")
    return source


#: `(the source has `true`, its fetched `origin` has it, or None for no
#: `origin`, how `check`'s one finding begins, or None where it passes the
#: plan)`: #479's three tracking branches `execute` does not push the legs
#: to in every mode, and refuses before any leg exists (69a743e, 94242a2).
BRANCH_CASES = [
    pytest.param(False, None,
                 f"{BRANCH_MISSING}`true`, which is no branch of the source ",
                 id="the-source-lacks-it"),
    pytest.param(True, False,
                 f"{BRANCH_MISSING}`true`, which is no branch of the "
                 "source's remote `origin` ", id="origin-lacks-it"),
    pytest.param(False, True, None, id="only-origin-has-it"),
]


@pytest.mark.parametrize("own, origin, finding", BRANCH_CASES)
def test_a_branch_execute_does_not_push_in_every_mode_is_never_misread(
        adopter, bare_template, tmp_path, capsys, own, origin, finding):
    """Where `tracking_branch:` is written bare, as before #259
    (`bare_template`), the loader misreads `true`, so the misread rule asks
    git and then the source whether `execute` pushes the legs to it in
    every mode (`_a_branch_execute_writes`, `_pushed_in_every_mode`). In
    each of these it does not, and refuses it before any leg exists. So
    `plan` records it, noting it where it is no branch of the source or of
    its `origin`, and refuses nothing; `check` finds it #479's
    `plan-tracking-branch-missing` alone, or passes the plan where only
    `origin` has it, as main does; and neither says it is misread. In this
    process."""
    source = branch_source(tmp_path, own, origin)
    plan = tmp_path / PLAN_FILE
    code, stdout, stderr = run_here(adopter, capsys, *plan_argv(
        source, plan, tmp_path, TRACKING_FLAG, "true"))
    assert code == 0, stdout + stderr
    assert (BRANCH_NOTED in stdout) == (finding is not None), stdout
    assert MISREAD_CODE not in stdout + stderr
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    code, stdout, stderr = run_here(adopter, capsys, "check", PLAN_OPTION,
                                    str(plan))
    assert MISREAD_FINDING not in stderr, stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in stderr
    if finding is None:
        assert code == 0, stdout + stderr
        assert PLAN_OK in stdout, stdout
    else:
        assert code == 1, stdout + stderr
        assert finding in stderr, stderr


@pytest.mark.parametrize("own, origin, pushed", [
    pytest.param(False, None, False, id="the-source-lacks-it"),
    pytest.param(True, False, False, id="origin-lacks-it"),
    pytest.param(False, True, False, id="only-origin-has-it"),
    pytest.param(True, True, True, id="both-have-it"),
])
def test_the_source_says_whether_execute_pushes_the_legs_to_a_branch(
        adopter, tmp_path, own, origin, pushed):
    """`_pushed_in_every_mode`: `execute` pushes the legs to a tracking
    branch in every mode only where #479's question finds it -- among the
    branches of the source's `origin` as the clone remembers them, or the
    source's own where it has no `origin` (gh mode) -- and the source
    itself has it (`--local-remote-dir`)."""
    opened = adopter.Source.open(str(branch_source(tmp_path, own, origin)),
                                 tmp_path / "work")
    assert adopter._pushed_in_every_mode(opened, "true") is pushed


def test_plan_asks_the_validator_before_the_misread_rule(
        adopter, answered, bare_template, tmp_path, monkeypatch, capsys):
    """rv181f's G1 at `plan`: the project's own validator is asked first,
    and a value it refuses is refused in its words alone. On a bare `id:`
    line, as before #259, `--id true` is read as a boolean: the validator
    refuses it (`manifest-id`), and the misread rule would name it too. So
    the validator is given the same bare copy (`bare_template`, with the
    template's own `scripts/` beside it, asked through
    `manifest_value_problems`), and `plan` refuses the id as
    `adopt-manifest-invalid`, says nothing of a misread, and writes no plan.
    On the shipped templates `true` reads back and is `READ_BACK`'s. In
    this process."""
    shutil.copytree(REPO / "templates" / "assembly-root" / "scripts",
                    bare_template / "scripts")
    materialize = sys.modules["shape_materialize"]
    monkeypatch.setattr(materialize, "manifest_value_problems",
                        functools.partial(materialize.manifest_value_problems,
                                          template_dir=bare_template))
    source, _ = answered
    plan = tmp_path / PLAN_FILE
    code, _, stderr = run_here(adopter, capsys, *plan_argv(
        source, plan, tmp_path, "--id", "true"))
    assert code == 2, stderr
    assert stderr.startswith("REFUSED adopt-manifest-invalid: "), stderr
    assert "manifest-id" in stderr, stderr
    assert MISREAD_CODE not in stderr, stderr
    assert not plan.exists()


def test_plan_names_a_tracking_branch_it_took_from_the_source(
        adopter, bare_template, tmp_path, capsys):
    """Since #479 `plan` records the source's default branch when no
    `--tracking-branch` is given. Where the line `execute` writes it into
    is bare, a source whose default branch is `true` is refused before the
    plan exists, naming where the value came from, as `checked_value` names
    it, and not as a flag nobody passed. Since #259 that line is quoted,
    and such a source is planned and adopted as given (`READ_BACK`), so
    `plan` is asked of a bare line (`bare_template`), in this process."""
    source = make_source_repo(tmp_path / SOURCE_NAME, branch="true")
    plan = tmp_path / PLAN_FILE
    code = adopter.main(plan_argv(source, plan, tmp_path))
    stderr = capsys.readouterr().err
    assert code == 2, stderr
    who, what = misread(
        "--tracking-branch (not given, so the source's default branch)",
        "true", TRUE_READ)
    assert stderr.startswith(f"REFUSED adopt-manifest-misread: {who}"), (
        stderr)
    assert what in stderr, stderr
    assert not plan.exists()


def test_the_source_is_asked_only_about_a_branch_the_loader_misreads(
        adopter, bare_template, monkeypatch):
    """`_pushed_in_every_mode` starts git. It is asked about `true`, which
    the loader misreads on a bare line (`bare_template`), and not about
    `develop`, which it reads back, as git's own question is asked
    (`_a_branch_git_creates`)."""
    asked = []

    def recorded(_source, branch):
        asked.append(branch)
        return False

    monkeypatch.setattr(adopter, "_pushed_in_every_mode", recorded)
    assert adopter._a_branch_execute_writes(None, TRACKING_KEY, "develop")
    assert not adopter._a_branch_execute_writes(None, TRACKING_KEY, "true")
    assert asked == ["true"]


# --- a pin is `product@<40 hex>`, recorded whole (main's #273) --------------

def test_a_pin_beside_a_273_finding_is_not_named_misread(
        adopter, answered, bare_pins, tmp_path, capsys):
    """`execute` refuses a plan whose `pins:` has a finding of #273's
    before any leg exists, so it writes none of its pins: a misread
    sentence about the whole pin beside it would say otherwise. One wrong
    `pins:` is #273's findings alone. Since #514 the pin `"null"` reads back
    from the manifest's list, so it is asked where the list is written
    bare (`bare_pins`), in this process."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, PINS_KEY, QUOTED_NULL)
    edited = text_of(plan).replace("\npins:\n", "\npins:\n  - openX\n", 1)
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(edited)
    code, stdout, stderr = run_here(adopter, capsys, "check", PLAN_OPTION,
                                    str(plan))
    assert code == 1, stdout + stderr
    assert "FINDING plan-pin-unrecorded: `pins:` entry 1, 'openX'" in (
        stderr), stderr
    assert MISREAD_FINDING not in stderr, stderr


def test_a_pin_whose_product_is_not_text_is_273s_finding_alone(
        answered, tmp_path):
    """`product: TRUE` is read as a boolean, which `_read_pins` finds
    `plan-pin-malformed`, and `execute` refuses before any leg exists. Before
    #273 a pin was a name, and #181 named this one by what was read."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, PINS_KEY, "TRUE")
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FINDING plan-pin-malformed: `pins:` entry 1 records " in (
        result.stderr), result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr


#: A date with a line break in it, as a plan edited by hand spells it.
UNWRITABLE_DATE = '"2026-09-02\\nx"'
#: `(plan key, as a plan edited by hand spells it)`: values no file
#: `execute` writes can hold, which #255 names as `plan-unwritable-value`:
#: a line break, in a value read back as one line, and a control character
#: such as a tab. Where the date and the pins were written bare, the
#: project's loader would read each as something else too; the visibility
#: is not one #181 judges (`NEVER_WRITTEN`). Beside a line break, the
#: project's own validator lists the manifest such a value makes, as main
#: has it (#255 before #261, `_entry_findings`); a pin holding a tab is
#: #255's finding alone.
UNWRITABLE = [
    pytest.param(ELECTED_ON_KEY, UNWRITABLE_DATE, id=ELECTED_ON_KEY),
    pytest.param(VISIBILITY_KEY, '"private\\nx"', id=VISIBILITY_KEY),
    pytest.param(PINS_KEY, '"a\\nb"', id="pins-line-break"),
    pytest.param(PINS_KEY, '"openGlass\\t"', id="pins-tab"),
]


@pytest.mark.parametrize(KEY_SPELLED, UNWRITABLE)
def test_check_names_a_value_no_file_can_hold_once_as_unwritable(
        adopter, answered, tmp_path, key, spelled):
    """At the merge of #255 the gate also called the date and the pin
    misread, under a remediation saying the run would still end `adoption
    verified`: one wrong value was two findings, and the second was false,
    because `execute` refuses the value before it writes anything. It is
    #255's finding, once, and never #181's."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert result.stderr.count(UNWRITABLE_FINDING) == 1, result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


@needs_filter_repo
def test_execute_refuses_a_date_no_file_can_hold_as_unwritable_not_misread(
        answered_copy, tmp_path):
    """`execute` refuses a plan under the code of `check`'s first finding,
    which for this date was the misread one: it is refused as what it is,
    before any leg exists."""
    source, text = answered_copy
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, ELECTED_ON_KEY, UNWRITABLE_DATE)
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED plan-unwritable-value: "), result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: `(plan key, as a plan edited by hand spells it)`: values #261's
#: validator (`plan-manifest-invalid`) refuses as the loader reads them. The
#: validator is asked first, and a value it refuses is its alone, text the
#: loader misreads included (rv181f's G1). `id: "007"`, `tracking_branch:
#: "007"` and `legs.spec_path: "null"` were a row each here, the first the
#: validator's and the others #181's; since #259 each reads back and is no
#: finding (main's `TEXT_THE_TEMPLATE_NOW_HOLDS`, and `READ_BACK`). So were
#: a pin `"null"`, #181's, and a pin `? x`, whose bare item made a manifest
#: the validator's reader refuses (rv181f's G2); since #514 each item reads
#: back. What is left of #181's is asked where a line is bare
#: (`test_check_reports_a_plan_carrying_one`), and so is G2
#: (`test_a_manifest_its_reader_refuses_is_the_validators_alone`).
JUDGED_ONCE = [
    pytest.param(ELECTED_BY_KEY, '" "', id="elector-blank"),
    pytest.param(VISIBILITY_KEY, "secret", id="visibility-secret"),
    pytest.param(VISIBILITY_KEY, TRUE_TEXT, id="visibility-text-true"),
    pytest.param(VISIBILITY_KEY, "true", id="visibility-boolean"),
    pytest.param(VISIBILITY_KEY, "[secret]", id="visibility-list"),
]


@pytest.mark.parametrize(KEY_SPELLED, JUDGED_ONCE)
def test_check_judges_each_value_once_by_the_rule_true_of_it(
        answered_copy, tmp_path, key, spelled):
    """At the merge of main dd8d0ea, `id: "007"` and `elected_on:
    "20260902"` were two findings each, #181's and the validator's, and a
    visibility that is not text was none. At 7ac2358 each was one, but
    #181's, whose remediation said `execute` writes the value and the run
    ends `adoption verified` where `execute` refuses it as the validator's
    (rv181f's G1), and `elected_on: "!"` was still two (G2). Each is one,
    in the validator's words."""
    source, text = answered_copy
    holding(source, key, parse_yaml(f"{key}: {spelled}\n")[key])
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    (line,) = judged_lines(result.stderr)
    assert line.startswith(INVALID_FINDING), result.stderr
    assert result.stderr.count("Remediation: ") == 1, result.stderr
    assert VALIDATOR_REMEDIATION_START in result.stderr, result.stderr


def test_a_manifest_its_reader_refuses_is_the_validators_alone(
        adopter, answered, bare_pins, tmp_path, capsys):
    """rv181f's G2. Where the project's own reader refuses the whole
    manifest a plan makes, no value of it can be said to pass the validator
    (`manifest_judged` is None), so #181 leaves every value to it, and
    `check` prints one finding of the two rules', the validator's, with its
    remediation once. A pin `? x` made such a manifest while the pins' list
    was written bare (`- ? x`, an explicit key). Since #514 `execute` quotes
    it, and no plan value was found to make such a manifest of the shipped
    templates (probed: each key the manifest is rendered from, with every
    candidate here), so it is asked with the list written bare again
    (`bare_pins`), in this process. The pin is #273's `plan-pin-malformed`
    as well, as it was."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, PINS_KEY, '"? x"')
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    values = adopter._manifest_values(adopter.Plan.load(plan), naming)
    assert adopter.manifest_judged(values, naming,
                                   ignore=adopter.LEG_PATH_CODES) is None
    code, _, stderr = run_here(adopter, capsys, "check", PLAN_OPTION,
                               str(plan))
    assert code == 1, stderr
    (line,) = judged_lines(stderr)
    assert line.startswith(f"{INVALID_FINDING}the manifest this run would "
                           "write is a file the project's own YAML reader "
                           "refuses: "), stderr
    assert stderr.count("Remediation: ") == 1, stderr
    assert VALIDATOR_REMEDIATION_START in stderr, stderr


#: A leg path the validator refuses as text, which its finding about the
#: leg (`manifest-leg-path`) names by no one value of the plan's.
OUTSIDE_THE_ROOT = '"../x"'
#: `(plan key, as a plan edited by hand spells it, whether the leg-path
#: codes `check` leaves to `_leg_findings` are left out, what
#: `manifest_judged` answers)`. The first and the last two were `id: "007"`
#: and `legs.spec_path: "null"` while the template wrote those lines bare;
#: since #259 each reads back, and the validator accepts it. A pin `? x`,
#: whose manifest its reader refused while the pins' list was written bare,
#: was a row here; since #514 it is asked with the list bare again
#: (`test_a_manifest_its_reader_refuses_is_the_validators_alone`).
JUDGED_BY_THE_VALIDATOR = [
    pytest.param(VISIBILITY_KEY, "secret", False, frozenset({"VISIBILITY"}),
                 id="its-finding-names-the-value"),
    pytest.param(TRACKING_KEY, QUOTED_007, False, frozenset(),
                 id="a-value-it-does-not-judge"),
    pytest.param(SPEC_PATH_KEY, OUTSIDE_THE_ROOT, False, None,
                 id="a-finding-about-no-one-value"),
    pytest.param(SPEC_PATH_KEY, OUTSIDE_THE_ROOT, True, frozenset(),
                 id="a-code-check-leaves-to-its-own-rule"),
]


@pytest.mark.parametrize("key, spelled, as_check, judged",
                         JUDGED_BY_THE_VALIDATOR)
def test_the_validator_says_which_values_it_judges(
        adopter, answered, tmp_path, key, spelled, as_check, judged):
    """`manifest_judged`: the placeholders whose value the validator makes
    a finding about, which #181 leaves to it; None where no value can be
    said to pass it -- its reader refuses the file, or it makes a finding
    about no one value -- and #181 then leaves every value to it (rv181f's
    G1, G2)."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    values = adopter._manifest_values(adopter.Plan.load(plan), naming)
    ignore = adopter.LEG_PATH_CODES if as_check else ()
    assert adopter.manifest_judged(values, naming, ignore=ignore) == judged


def test_no_value_passes_a_validator_that_is_not_asked(
        adopter, answered, bare_template, tmp_path):
    """Names the naming policy does not classify are `check`'s finding in
    their own words, and no manifest is rendered from them, so the
    validator is asked nothing: no value can be said to pass it, and #181
    names none until it can be asked. The branch `"007"` is one #181 names
    on a bare line (`bare_template`); since #259 the template quotes it."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, ASSEMBLY_KEY, "north_wind")
    carrying(plan, text_of(plan), TRACKING_KEY, QUOTED_007)
    loaded = adopter.Plan.load(plan)
    assert adopter._validator_judged(loaded) is None
    assert adopter._misread_findings(loaded) == []


#: How a plan edited by hand spells an `elected_on:` that `election_date`
#: refuses. #294's rule (`_plan_field_findings`) names it as
#: `election-date-malformed`, in the plan key's own words, and `execute`
#: refuses it before any leg exists. `_manifest_values` then renders no
#: manifest, so the validator is asked nothing and #181 names no value
#: (`_validator_judged`): the date is one finding. Before the merge of main
#: 965420b, the first three and the last two were the validator's, and the
#: fourth, a date in its own quotes, #181's.
LATE_DATES = [
    pytest.param(f'"{DATE_DIGITS}"', id="text-misread"),
    pytest.param(DATE_DIGITS, id="read-as-a-number"),
    pytest.param('"!"', id="the-reader-refuses"),
    pytest.param("'\"2026-09-02\"'", id="read-as-another-date"),
    pytest.param("[a]", id="list"),
    pytest.param("{a: b}", id="mapping"),
]


@pytest.mark.parametrize("spelled", LATE_DATES)
def test_check_leaves_a_date_election_date_refuses_to_that_rule(
        adopter, answered, tmp_path, spelled):
    """One finding, #294's, and no misread finding or remediation beside it:
    #181's would say `execute` writes the date and the run would still end
    `adoption verified`, where `execute` refuses it before any leg exists."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, ELECTED_ON_KEY, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert len(findings) == 1, result.stderr
    assert findings[0].startswith("FINDING election-date-malformed: "), (
        result.stderr)
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr
    assert adopter._misread_findings(adopter.Plan.load(plan)) == []

#: `(plan key, as a plan edited by hand spells it, how the validator's
#: sentence names it, the validator's code)`: read as not text, each is
#: named by what was read, as #181 names such a value, before the text
#: `execute` would write for it. The validator refuses what the loader
#: reads of each, so each is its finding alone (rv181f's G1). A date read
#: as not text is #294's (`LATE_DATES`). `id: 007` was a row here, the
#: validator's `id is 7`, while the template wrote `id:` bare; since #259
#: `execute` writes it `"7"`, which the validator accepts
#: (`READ_AS_NOT_TEXT`).
NOT_TEXT_INVALID = [
    pytest.param(VISIBILITY_KEY, "true", "visibility, read out of the plan "
                 "as the boolean true, is 'True',",
                 "manifest-visibility", id="visibility-boolean"),
    pytest.param(VISIBILITY_KEY, "[secret]", "visibility, read out of the "
                 "plan as a list, is \"['secret']\",",
                 "manifest-visibility", id="visibility-list"),
]


@pytest.mark.parametrize("key, spelled, named, code", NOT_TEXT_INVALID)
def test_the_validator_names_a_value_read_as_not_text_by_what_was_read(
        answered, tmp_path, key, spelled, named, code):
    """Its sentence quotes `str` of the value, the text `execute` would
    write: `visibility is 'True'` alone, for a plan that says `true`, would
    name text the plan never said (review181's N2)."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    (line,) = judged_lines(result.stderr)
    assert line.startswith(f"{INVALID_FINDING}{named} {VALIDATOR_REFUSES}"
                           f"{code}: "), result.stderr


@needs_filter_repo
def test_execute_refuses_a_visibility_it_never_writes_as_the_validators(
        answered_copy, tmp_path):
    """`visibility: "true"`: #181 leaves it to the validator, and `execute`
    refuses it under the validator's code before any leg exists."""
    source, text = answered_copy
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, VISIBILITY_KEY, TRUE_TEXT)
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED plan-manifest-invalid: "), result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: `(placeholder, value, the manifest line `execute` writes, what the loader
#: reads it back as)`: values the loader reads back as OTHER TEXT, each
#: through a placeholder written bare, as `elected_on:` was before #259
#: (`bare_template`); since #259 the template quotes it, where `render`
#: spells each value with `double_quoted`. The double quotes in the
#: first six are the VALUE's own, as a hand-edited plan's
#: `elected_on: '"CORP\tom"'` carries them: the loader takes them for YAML's
#: and resolves the escape between them. The manifest's OWN quotes no longer
#: do that, since #284 (`BETWEEN_THE_QUOTES`). `\\r` and a code point's
#: `\\xNN` are escapes the loader resolves since #199, which the gate follows
#: with no edit of its own: it asks the loader. Not a `tracking_branch`'s:
#: `execute` refuses a quote, a backslash or a space in one as
#: `unsafe-value` before it writes anything (`NEVER_WRITTEN`).
UNESCAPED = [
    (ELECTED_ON_PLACEHOLDER, f'"{DOMAIN_USER}"',
     f'elected_on: "{DOMAIN_USER}"', DOMAIN_USER_READ),
    (ELECTED_ON_PLACEHOLDER, '"docs\\new.md"', 'elected_on: "docs\\new.md"',
     "the text `docs`, then a line break, then `ew.md`"),
    (ELECTED_ON_PLACEHOLDER, '"a\\\\b"', 'elected_on: "a\\\\b"',
     "the text `a\\b`"),
    (ELECTED_ON_PLACEHOLDER, '"a\\"b"', 'elected_on: "a\\"b"',
     'the text `a"b`'),
    (ELECTED_ON_PLACEHOLDER, '"CORP\\ralph"', 'elected_on: "CORP\\ralph"',
     "the text `CORP`, then a carriage return, then `alph`"),
    (ELECTED_ON_PLACEHOLDER, '"docs\\x41.md"', 'elected_on: "docs\\x41.md"',
     "the text `docsA.md`"),
    (ELECTED_ON_PLACEHOLDER, "a #b", "elected_on: a #b", "the text `a`"),
]


@pytest.mark.parametrize("placeholder, value, line, reading", UNESCAPED,
                         ids=ids_of(UNESCAPED, 0, 1))
def test_text_the_loader_reads_as_other_text_is_shown_as_typed_and_read(
        adopter, bare_template, placeholder, value, line, reading):
    """`repr` showed `CORP\\tom` with its backslash doubled, and the tab the
    loader makes of it as `\\t`, so each looked like the other (review181's
    N1). The value is shown as it is typed, and a character a terminal shows
    as something else is named, so the difference is the one there is."""
    assert adopter.manifest_misreads(
        [adopter._field("x", placeholder, value)]) == [
        f"x is `{value}`, which `execute` writes into {MANIFEST} as "
        f"`{line}`, where the project's own YAML loader reads it back as "
        f"{reading} and not as that text: choose another value"]


#: Hand-edited pins whose product ends in whitespace, which the loader drops
#: from the manifest's `  - ` item. Before #273 a pin was a name, and #181
#: named such a pin in the line `execute` writes, whitespace and all
#: (rv181f's F1). Since #273 a pin's product is held to `PIN_ARG_RE`'s
#: alphabet, which has no whitespace (`_pin_row_problem`).
PIN_WITH_A_TRAIL = [
    pytest.param('"openGlass "', id="space"),
    pytest.param('"openGlass\\xa0"', id="no-break-space"),
]


@pytest.mark.parametrize("trailed", PIN_WITH_A_TRAIL)
def test_a_pin_ending_in_whitespace_is_273s_finding_alone(
        adopter, answered, bare_pins, tmp_path, capsys, trailed):
    """`check` finds the pin `plan-pin-malformed`, and `execute` refuses it
    before any leg exists, so it is never written: one finding, #273's, and
    no misread sentence saying `execute` writes it. Since #514 the manifest's
    list quotes such an item, so it is asked where the list is written bare
    (`bare_pins`), in this process."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, PINS_KEY, trailed)
    code, stdout, stderr = run_here(adopter, capsys, "check", PLAN_OPTION,
                                    str(plan))
    assert code == 1, stdout + stderr
    assert "FINDING plan-pin-malformed: `pins:` entry 1 " in stderr, stderr
    assert MISREAD_FINDING not in stderr, stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in stderr


#: Values the manifest's own double quotes misread while `render` pasted
#: them raw between them: an escape the loader resolved, a `"` that ended
#: the scalar early, a last `\\` that left it unclosed, and a carriage return
#: that split the line. Since #284 `render` spells each with `double_quoted`,
#: which the loader reads back as typed.
BETWEEN_THE_QUOTES = [DOMAIN_USER, "docs\\new.md", "CORP\\ralph",
                      "docs\\x41.md", "a\\\\b", 'a\\"b', 'Robert "Bob" Smith',
                      "trail\\", '"', "a\rb"]


@pytest.mark.parametrize("placeholder, key", [
    (ELECTED_BY_PLACEHOLDER, ELECTED_BY_KEY),
    (REFERENCE_PLACEHOLDER, REFERENCE_KEY)],
    ids=[ELECTED_BY_KEY, REFERENCE_KEY])
@pytest.mark.parametrize("value", BETWEEN_THE_QUOTES)
def test_a_value_between_the_manifests_quotes_is_asked_as_render_writes_it(
        adopter, placeholder, key, value):
    """`project.yaml` writes `elected_by:` and `reference:` between double
    quotes, where `render` spells the value with `double_quoted` since #284.
    The gate asked the line with the value pasted raw, so it refused
    `CORP\\tom` for a line `execute` no longer writes, and a name holding a
    `"`. It asks the line `render` writes, and passes each value."""
    assert adopter._written(placeholder, value) == [
        (MANIFEST, f"{key}: {repo_shape.double_quoted(value)}")]
    assert adopter.manifest_misreads(
        [adopter._field(key, placeholder, value)]) == []


#: Free text holding a placeholder's token, as #260's values may: each
#: field's own, bare after a letter and between double quotes, and one that
#: no table names.
HOLDING_A_TOKEN = ["x{{ELECTED_BY}}", '"{{ELECTED_BY}}"', "x{{REFERENCE}}",
                   '"{{REFERENCE}}"', "{{NOPE}}"]


@pytest.mark.parametrize("placeholder, key", [
    (ELECTED_BY_PLACEHOLDER, ELECTED_BY_KEY),
    (REFERENCE_PLACEHOLDER, REFERENCE_KEY)],
    ids=[ELECTED_BY_KEY, REFERENCE_KEY])
@pytest.mark.parametrize("text", HOLDING_A_TOKEN)
def test_a_value_holding_a_placeholder_is_asked_as_render_puts_it_in_once(
        adopter, placeholder, key, text):
    """Since #260 `render` puts each value in once and never searches it
    again. The gate built the line in two steps, the quoted placeholder and
    then the bare one over that output, so a value holding its own token
    was put in twice: `"x{{ELECTED_BY}}"` became `"xx{{ELECTED_BY}}"`, and
    the gate refused a value `execute` writes as typed. It asks `render`."""
    assert adopter._written(placeholder, text) == [
        (MANIFEST, f"{key}: {repo_shape.double_quoted(text)}")]
    assert adopter.manifest_misreads(
        [adopter._field(key, placeholder, text)]) == []


@needs_filter_repo
@pytest.mark.parametrize("key, value, reading", CARRIED,
                         ids=ids_of(CARRIED, 0, 1))
def test_execute_refuses_a_plan_carrying_one_before_any_leg_exists(
        adopter, answered_copy, bare_template, bare_pins, tmp_path, capsys,
        key, value, reading):
    """The refused half of the end-to-end run: `execute` says no through
    #168's one list of `check`'s findings, before it creates a leg or
    touches the source. Asked where the line is bare (`bare_template`,
    `bare_pins`), in this process."""
    source, text = answered_copy
    holding(source, key, value)
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, adopter.y(value))
    code, stdout, stderr = run_here(adopter, capsys,
                                    *execute_argv(plan, tmp_path))
    assert code == 2, stdout + stderr
    assert stderr.startswith("REFUSED plan-manifest-misread: "), stderr
    who, what = misread(NAMED.get(key, key), value, reading)
    assert f"{MISREAD_FINDING}{who}" in stderr
    assert what in stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION in stderr
    assert INVALID_FINDING not in stderr, stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: What the gate let through while the templates wrote these lines bare,
#: each spelled like a keyword somewhere: a leg path with `null` as a
#: segment, a branch the PLAN quotes for its leading digit, an id that is a
#: YAML 1.1 boolean this loader reads as text, and a person whose name is a
#: null, which `elected_by:` has always quoted. Since #259 `project.yaml`
#: quotes the id, the branch and the leg path too, and the run reads each
#: back as given all the same.
ACCEPTED = (SPEC_FLAG, LEGS_NULL, TRACKING_FLAG, Q4_BRANCH, "--id", "yes",
            ELECTED_BY_FLAG, "Null")


@needs_filter_repo
def test_what_is_still_accepted_adopts_clones_and_bootstraps(tmp_path):
    """The accepted half of the end-to-end run, to the step lane 2 found it
    stopped short of: the recursive clone and the first bootstrap, which put
    each leg on the branch `execute` pushed it on, with that branch as its
    upstream, and read back every value the plan was given."""
    source = make_source_repo(tmp_path / SOURCE_NAME)
    # Since #479 the tracking branch is a branch of the source: `execute`
    # pushes the split back into it under `--local-remote-dir`.
    holding(source, TRACKING_KEY, Q4_BRANCH)
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=ACCEPTED)
    assert written.returncode == 0, written.stderr + written.stdout
    for line in ("id: yes", f'tracking_branch: "{Q4_BRANCH}"',
                 'elected_by: "Null"', f"  spec_path: {LEGS_NULL}"):
        assert f"\n{line}\n" in text_of(plan), line
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "mount the legs at legs/null/ and code/" in result.stdout
    result = executed(plan, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout

    clone = cloned_just_pushed(source, tmp_path / "clone", SPLIT_BRANCH)
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, (bootstrapped.stderr
                                          + bootstrapped.stdout)
    assert "bootstrap ok" in bootstrapped.stdout
    manifest = load_yaml(clone / MANIFEST)
    assert (manifest["id"], manifest[TRACKING_KEY],
            manifest[ELECTED_BY_KEY]) == ("yes", Q4_BRANCH, "Null")
    assert [leg["path"] for leg in manifest["legs"]] == [".", LEGS_NULL,
                                                         "code"]
    assert load_yaml(clone / "contracts/spec-pin.yaml")[SUBMODULE_PATH] \
        == LEGS_NULL
    for mount in (LEGS_NULL, "code"):
        branches = [git("rev-parse", "--abbrev-ref", ref,
                        cwd=clone / mount).stdout.strip()
                    for ref in ("HEAD", "@{upstream}")]
        assert branches == [Q4_BRANCH, f"origin/{Q4_BRANCH}"], mount


# --- the gate asks the loader, where the template writes the value ----------

def loaded_plan(adopter, answered, tmp_path: Path):
    """The answered plan, as `check` loads it."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)
    return adopter.Plan.load(plan)


def pin_field(adopter, plan, product: str) -> tuple:
    """`_pin_field` for one pin of `plan`, as `check` asks about it."""
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    return adopter._pin_field(PINS_KEY, plan, product, naming)


def one_pin_table(adopter, plan, product: str) -> dict | None:
    """The table `execute` writes the manifest from (`_template_table`, as
    `_manifest_values` builds it) for `plan` with one pin, `product`."""
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    alone = adopter.Plan(plan.path, {**plan.data,
                                     PINS_KEY: [product]})
    return adopter._manifest_values(alone, naming)


def test_the_gate_follows_the_loader_when_the_loader_learns_a_keyword(
        adopter, answered, bare_template, tmp_path, monkeypatch):
    """ONE QUESTION, `loader_reading`, for the plan writer, the pins' list
    and the gate. Teach the real reader that `yes` is a boolean and all
    three change with no edit: `y` quotes it; `execute` writes a pin called
    `yes` as `- "yes"`, because #514 asks the same reader, and the gate
    passes that line; and a branch called `yes`, on a line written bare as
    before #259 (`bare_template`), is refused. On the shipped templates a
    branch is written between double quotes, which the reader reads back as
    the text whatever it has learnt (`READ_BACK`)."""
    reads = repo_shape._scalar
    plan = loaded_plan(adopter, answered, tmp_path)
    branch = adopter._field(TRACKING_KEY, TRACKING_PLACEHOLDER, "yes")
    assert branch[2] == [(MANIFEST, "tracking_branch: yes")]
    assert adopter.manifest_misreads(
        [branch, pin_field(adopter, plan, "yes")]) == []
    monkeypatch.setattr(repo_shape, SCALAR_READER,
                        lambda raw: True if raw.strip() == "yes"
                        else reads(raw))
    assert adopter.y("yes") == QUOTED_YES
    pin = pin_field(adopter, plan, "yes")
    assert pin[2] == [(f"{MANIFEST}'s neutral_product_pins", '- "yes"')]
    assert [problem.split(" is ")[0] for problem
            in adopter.manifest_misreads([branch, pin])] == [TRACKING_KEY]


def test_the_template_line_says_whether_a_value_is_quoted(
        adopter, answered, tmp_path):
    """No list in `adopt-project.py` says which placeholders the templates
    quote: the line is read. `Null` is a person's name between the quotes
    of `elected_by:`, and a branch between those of `tracking_branch:`
    since #259; as an item of the pins' list, which `execute` writes
    `- "Null"` since #514, it is a product too."""
    assert adopter._written(ELECTED_BY_PLACEHOLDER, "Null") == [
        (MANIFEST, 'elected_by: "Null"')]
    assert adopter._written(TRACKING_PLACEHOLDER, "Null") == [
        (MANIFEST, 'tracking_branch: "Null"')]
    assert adopter.manifest_misreads([
        adopter._field(ELECTED_BY_KEY, ELECTED_BY_PLACEHOLDER, "Null"),
        adopter._field(TRACKING_KEY, TRACKING_PLACEHOLDER, "Null")]) == []
    field = pin_field(adopter, loaded_plan(adopter, answered, tmp_path),
                      "Null")
    assert field[2] == [(f"{MANIFEST}'s neutral_product_pins", '- "Null"')]
    assert adopter.manifest_misreads([field]) == []


def test_the_gate_asks_the_table_execute_writes_the_pins_from(
        adopter, answered, tmp_path, monkeypatch):
    """`_pin_field` asks `_template_table`, the table `execute`'s
    `_template_values` writes the manifest from, and never a copy of how it
    spells an item. Since #514 (main's e6fbd748) that table quotes a product
    the project's reader would misread, and the gate asks the quoted line
    and passes `null`, with no edit of its own. Made to write the item bare
    again, as before #514 (`pins_written_bare`), the table's bare line is
    the one the gate asks, and refuses."""
    plan = loaded_plan(adopter, answered, tmp_path)
    field = pin_field(adopter, plan, "null")
    assert field[2] == [(f"{MANIFEST}'s neutral_product_pins", '- "null"')]
    assert adopter.manifest_misreads([field]) == []
    monkeypatch.setattr(adopter, "_neutral_product_pins", pins_written_bare)
    field = pin_field(adopter, plan, "null")
    assert field[2] == [(f"{MANIFEST}'s neutral_product_pins", "- null")]
    assert adopter.manifest_misreads([field])


#: Where each placeholder lands in the RENDERED files, as their loader reads
#: them: `(file, path into what it loads)`. The test's own oracle, written
#: from the templates, never from `adopt-project.py`.
LANDS = {
    TRACKING_PLACEHOLDER: [(MANIFEST, (TRACKING_KEY,))],
    ELECTED_BY_PLACEHOLDER: [(MANIFEST, (ELECTED_BY_KEY,))],
    REFERENCE_PLACEHOLDER: [(MANIFEST, (REFERENCE_KEY,))],
    "SPEC_PATH": [(MANIFEST, ("legs", 1, "path")),
                  ("contracts/spec-pin.yaml", (SUBMODULE_PATH,))],
    PINS_PLACEHOLDER: [(MANIFEST, ("neutral_product_pins", 0))],
}


def rendered_readings(placeholder: str, value: str) -> list:
    """What the project's loader reads where `value` lands, in the three
    templated YAML files rendered WHOLE by the materializer's own `render`,
    every other placeholder filled with plain text. For the pins, `value`
    is the list as `_template_table` makes it."""
    from shape_materialize import PLACEHOLDER_RE, render
    template = REPO / "templates" / "assembly-root"
    # A naming block is lines of its own, and an empty one is no lines.
    values = {PINS_PLACEHOLDER: "[]", "ASSEMBLY_NAMING": "",
              "SPEC_NAMING": "", "CODE_NAMING": "", placeholder: value}
    readings = []
    for name, path in LANDS[placeholder]:
        text = (template / name).read_text(encoding=UTF8)
        filled = {key.strip("{}"): "filler"
                  for key in PLACEHOLDER_RE.findall(text)}
        try:
            loaded = parse_yaml(render(text, {**filled, **values}, name))
            for step in path:
                loaded = loaded[step]
        except (repo_shape.YamlError, LookupError, TypeError) as exc:
            loaded = exc
        readings.append(loaded)
    return readings


@pytest.mark.parametrize("placeholder", sorted(LANDS))
def test_the_gate_agrees_with_the_rendered_files_on_every_candidate(
        adopter, answered, tmp_path, placeholder):
    """The gate asks one template line at a time. Rendered whole, as
    `execute` renders them, the files must agree on every candidate this
    module generates: a value the gate passes comes back out of each place
    it lands, and one it refuses does not. A pin is asked as `check` asks
    it, of the answered plan with that one pin, and rendered from the same
    table; the empty candidate is no pin (`Plan` keeps no empty product)."""
    plan = loaded_plan(adopter, answered, tmp_path)
    asked = 0
    for value in CANDIDATES:
        if placeholder == PINS_PLACEHOLDER:
            if not value:
                continue
            field = pin_field(adopter, plan, value)
            written = one_pin_table(adopter, plan, value)[PINS_PLACEHOLDER]
        else:
            field = adopter._field("x", placeholder, value)
            written = value
        refused = bool(adopter.manifest_misreads([field]))
        lands = rendered_readings(placeholder, written)
        assert refused == any(got != value for got in lands), (value, lands)
        asked += 1
    assert asked >= len(CANDIDATES) - 1


# --- a leg path the project's loader misreads is #266's (main's 191105a) ----

def test_a_leg_path_written_bare_is_266s_finding_alone(
        adopter, answered, bare_template, tmp_path, monkeypatch, capsys):
    """Where every template line that holds a leg path is bare, as before
    #259, the leg-path rule both tools ask (`leg_path_problem`, #266)
    refuses a leg path the project's loader misreads, and #181's gate asks
    its question of a leg path only where that rule has no answer
    (`_plan_fields`): one wrong value is one finding, #266's. Since #259
    those lines are quoted, and neither rule refuses `null` there
    (`READ_BACK`). Asked of a bare copy of the shape's templates, given to
    both rules, in this process."""
    materialize = sys.modules["shape_materialize"]
    monkeypatch.setattr(materialize, "LEG_PATH_TEMPLATES",
                        bare_template.parent)
    said = adopter.leg_path_problem(SPEC_PATH_KEY, "null")
    assert said.startswith(f"{SPEC_PATH_KEY} is 'null', which the project "
                           "would not read back as text: "), said
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, SPEC_PATH_KEY, QUOTED_NULL)
    assert adopter._misread_findings(adopter.Plan.load(plan)) == []
    assert adopter.main(["check", PLAN_OPTION, str(plan)]) == 1
    findings = [line for line in capsys.readouterr().err.splitlines()
                if line.startswith("FINDING ")]
    assert findings == [f"FINDING plan-bad-leg-path: {said}"], findings


# --- an explicit null leg path, the reviewer's question on 76a6153 ----------

@pytest.mark.parametrize("spelled", ["null", "~", ""],
                         ids=["null", "tilde", "nothing"])
def test_an_explicit_null_leg_path_is_a_finding_not_the_default(
        adopter, answered, tmp_path, spelled):
    """A plan `main` wrote for `--spec-path null` says `spec_path: null`,
    and `check` called it a mount at `spec` while that plan's own follow-ups
    said `null/contracts`. A key that is there with no value is a value
    nobody chose, as #169 rules an explicit empty one: a finding, with no
    `None/` in the line that names the mounts."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, SPEC_PATH_KEY, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert ("FINDING plan-bad-leg-path: legs.spec_path is not text: its value "
            "was read as no value at all, and a leg path is text: write the "
            "path you mean, or remove the key to mount the leg at its role's "
            "own name") in result.stderr
    assert "mount the legs at" not in result.stdout
    assert "None" not in result.stdout + result.stderr
    loaded = adopter.Plan.load(plan)
    with pytest.raises(adopter.Refusal) as refused:
        adopter._checked_plan_values(loaded)
    assert refused.value.code == "plan-bad-leg-path"


def test_the_plan_writer_quotes_a_pin_whatever_refuses_it_later(
        adopter, answered, glass, tmp_path, monkeypatch):
    """`pins: [` was the one list of strings the plan wrote without `y`, so
    `--pin null` was `pins: [null]`: a null `Plan.load` drops. Since #273
    `plan` writes each pin as a mapping through `y` (`_pin_lines`). The
    writer is asked with the gate taken away, so the answer is the writer's
    alone, whatever refuses the product later: it is a string like any
    other in the plan."""
    source, _ = answered
    path, commit = glass
    monkeypatch.setattr(adopter, "manifest_misreads", lambda _fields: [])
    for pin in ("null", "Null", "NULL", "true", FALSE_TITLE):
        plan = tmp_path / f"{pin}.yaml"
        assert adopter.main(plan_argv(
            source, plan, tmp_path, PIN_FLAG, f"{pin}@{commit}",
            PIN_SOURCE_FLAG, str(path))) == 0
        assert f'\n  - product: "{pin}"\n' in text_of(plan)
        assert load_yaml(plan)[PINS_KEY][0]["product"] == pin
        assert adopter.Plan.load(plan).pins == [pin]


@pytest.mark.parametrize("pins, written", [
    ((OPEN_GLASS,), (GLASS_ITEM, "    repository: opensoft/openGlass")),
    (("opensoft/openGlass",), (GLASS_ITEM,
                               "    repository: opensoft/openGlass")),
    ((OPEN_GLASS, "opensoft/openCode"),
     (GLASS_ITEM, "  - product: openCode",
      "    repository: opensoft/openCode")),
    ((), ("pins: []",)),
], ids=["one", "owned", "two", "none"])
def test_an_ordinary_pin_is_written_as_it_always_was(glass, tmp_path, pins,
                                                     written):
    """`openGlass` and `opensoft/openGlass` are the pins that exist; their
    product and repository stay bare, singly and together, and no pin is
    still `pins: []`."""
    path, commit = glass
    extra = tuple(part for pin in pins
                  for part in (PIN_FLAG, f"{pin}@{commit}"))
    if pins:
        extra += (PIN_SOURCE_FLAG, str(path))
    text = text_of(planned(tmp_path, *extra))
    for line in written:
        assert f"\n{line}\n" in text, line


def test_a_source_file_named_like_a_keyword_is_one_entry_with_that_path(
        tmp_path):
    """The writer's other caller: an entry's `path:`. A file called `null` or
    `True` was an entry with no path (or a boolean one), and `check` reported
    the file uncovered and the entry empty on a plan the tool had just
    written."""
    tree = {"null": "x\n", "True": "x\n", "README.md": "# Thing\n",
            "src/app/main.py": "VALUE = 1\n", "specs/001/spec.md": "# s\n"}
    plan = planned(tmp_path, tree=tree)
    paths = [e["path"] for e in load_yaml(plan)[PATHS]]
    assert "null" in paths, paths
    assert "True" in paths, paths
    assert all(isinstance(path, str) for path in paths), paths
    for path in ("null", "True"):
        answer(plan, path, "root")
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert ANY_FINDING not in result.stdout + result.stderr


def test_the_doctors_placement_plan_quotes_a_path_the_same_way(adopter):
    """`shape-doctor.py --placement-plan` writes its entries with this `y`, so
    a misplaced file called `null` was the same defect there. It reads back as
    the string too."""
    module_spec = importlib.util.spec_from_file_location(
        "shape_doctor_yaml_quoting", DOCTOR)
    doctor = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(doctor)
    entry = {"path": "null", "leg": "spec", "classified_as": "code",
             "confidence": "medium", "rule": "extension-majority",
             "reason": "x", "files": 1, "bytes": 2, "review_required": False}
    lines = doctor.placement_plan_entry(adopter, entry)
    loaded = parse_yaml("paths:\n" + "\n".join(lines) + "\n")
    assert loaded[PATHS][0]["path"] == "null"
