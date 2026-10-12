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
"""

from __future__ import annotations

import importlib.util
import itertools
import random
import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
from repo_shape import load_yaml, parse_yaml  # noqa: E402

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
        assert isinstance(got, str) and got == value, (
            f"{value!r} was written as {adopter.y(value)} and read back "
            f"as {got!r} ({type(got).__name__}) as {shape}")


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
    assert adopter.y(True) == "true" and adopter.y(False) == FALSE_WORD
    assert adopter.y(0) == "0" and adopter.y(1234) == "1234"
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

    assert adopter.y("yes") == "yes" and adopter.y("on") == "on"
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
#: `pins:` is an item of a list, and what it was read as is the item's.
NAMED = {PINS_KEY: "a pin in pins"}
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

#: `(flag, value, plan key, what the project's loader reads)`. At 76a6153
#: each of the first fifteen went through `execute` to `adoption verified`
#: and then to a bootstrap that failed, or that put the legs on another branch
#: than the one they were pushed on (lane 2's review, and this fix's own repro
#: of it); `2026`, `1.5` and `~` did so on `main` too (#187's review). `007`
#: is a branch bootstrap would read as `7`. No value `project.yaml` writes
#: between its quotes is here: `render` spells those with `double_quoted`
#: since #284, and `BETWEEN_THE_QUOTES` below holds the ones that misread
#: before it.
REFUSED = [
    (SPEC_FLAG, "null", SPEC_PATH_KEY, NO_VALUE),
    (SPEC_FLAG, "Null", SPEC_PATH_KEY, NO_VALUE),
    (SPEC_FLAG, "NULL", SPEC_PATH_KEY, NO_VALUE),
    (SPEC_FLAG, "~", SPEC_PATH_KEY, NO_VALUE),
    (SPEC_FLAG, "true", SPEC_PATH_KEY, TRUE_READ),
    (SPEC_FLAG, FALSE_TITLE, SPEC_PATH_KEY, "the boolean false"),
    (SPEC_FLAG, "2026", SPEC_PATH_KEY, "the number 2026"),
    (SPEC_FLAG, "1.5", SPEC_PATH_KEY, "the number 1.5"),
    ("--code-path", "null", "legs.code_path", NO_VALUE),
    (TRACKING_FLAG, "true", TRACKING_KEY, TRUE_READ),
    (TRACKING_FLAG, "null", TRACKING_KEY, NO_VALUE),
    ("--id", "true", "id", TRUE_READ),
    ("--id", "null", "id", NO_VALUE),
    (PIN_FLAG, "null", PINS_KEY, NO_VALUE),
    (PIN_FLAG, "True", PINS_KEY, TRUE_READ),
    (TRACKING_FLAG, "007", TRACKING_KEY, SEVEN_READ),
]
#: `(plan key, value, what the loader reads)` that only an edited plan can
#: carry here: `plan` reads `--elected-on 20260902` as a date only on Python
#: 3.11 and later. No visibility is here: `plan` takes one from a fixed
#: choice, and `execute` hands any other to `gh repo create` before it
#: writes anything (`NEVER_WRITTEN`).
EDITED_ONLY = [
    (ELECTED_ON_KEY, DATE_DIGITS, f"the number {DATE_DIGITS}"),
]
#: REFUSED as `plan` is given it, and as a plan carries it.
PLANNED = [(flag, value, reading) for flag, value, _, reading in REFUSED]
CARRIED = [(key, value, reading) for _, value, key, reading in REFUSED] \
    + EDITED_ONLY


def ids_of(rows, key: int, value: int) -> list[str]:
    return [f"{row[key]}={row[value]!r}" for row in rows]


def checked(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


#: The directory `executed` names for the local remotes, which a run that is
#: refused before any leg exists never creates.
REMOTES = "remotes"


def executed(plan: Path, tmp_path: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(tmp_path / REMOTES),
                      "--work-dir", str(tmp_path / "work"))


def branches_of(source: Path) -> str:
    """The source's branches: no split branch until `execute` commits one."""
    return git("branch", "--list", cwd=source).stdout


def planned(tmp_path: Path, *extra: str, tree: dict | None = None) -> Path:
    source = make_source_repo(tmp_path / SOURCE_NAME, tree=tree)
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan, extra=extra)
    assert written.returncode == 0, written.stderr + written.stdout
    return plan


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
    tests below to copy and edit. Nothing below writes into the source: a
    refused `check` or `execute` never reaches it, and `plan` only reads it."""
    base = tmp_path_factory.mktemp("misread")
    source = make_source_repo(base / SOURCE_NAME)
    plan = base / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    assert checked(plan).returncode == 0
    return source, text_of(plan)


def carrying(plan: Path, text: str, key: str, spelled: str) -> None:
    """Write `text`, an answered plan, to `plan` with `key` set to `spelled`
    exactly as given: a plan edited by hand, or written by a `plan` older
    than this check. LF, as `plan` writes it."""
    if key == PINS_KEY:
        edited = text.replace("\npins: []\n", f"\npins: [{spelled}]\n", 1)
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
        answered, tmp_path, flag, value, reading):
    """Before the plan is written: the flag, the value, what the project's
    loader would read, and the fix."""
    source, _ = answered
    plan = tmp_path / PLAN_FILE
    result = write_plan(source, plan, extra=(flag, value))
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED adopt-manifest-misread: ")
    who, what = misread(flag, value, reading)
    assert who in result.stderr and what in result.stderr, result.stderr
    assert "No plan was written." in result.stderr
    assert not plan.exists()


@pytest.mark.parametrize("project, value, reading", [
    ("True", "true", TRUE_READ), ("Null", "null", NO_VALUE)],
    ids=["True", "Null"])
def test_plan_names_an_id_it_derived_from_the_project(
        answered, tmp_path, project, value, reading):
    """`--project True` passes no `--id`, and `plan` lowercases the project
    into one: the refusal says where the value came from, so the person
    knows the flag that chooses another."""
    source, _ = answered
    result = write_plan(source, tmp_path / PLAN_FILE, project=project)
    assert result.returncode == 2, result.stdout + result.stderr
    who, what = misread("--id (not given, so --project lowercased)", value,
                        reading)
    assert who in result.stderr and what in result.stderr, result.stderr


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
        ADOPT, "plan", "--source", str(source), "--project", PROJECT_NAME,
        "--org", "testorg", "--elected-on", "2026-09-02", "--out", str(plan),
        env={"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "user.name",
             "GIT_CONFIG_VALUE_0": DOMAIN_USER})
    assert result.returncode == 0, result.stdout + result.stderr
    assert '\nelected_by: "CORP\\\\tom"\n' in text_of(plan)
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    passed = checked(plan)
    assert passed.returncode == 0, passed.stdout + passed.stderr
    assert "manifest-misread" not in passed.stderr


@pytest.mark.parametrize("key, value, reading", CARRIED,
                         ids=ids_of(CARRIED, 0, 1))
def test_check_reports_a_plan_carrying_one(adopter, answered, tmp_path, key,
                                           value, reading):
    """A plan carrying the value -- spelled by the plan writer, so the plan
    itself reads it back -- is a FINDING, with the remediation once after."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, adopter.y(value))
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    who, what = misread(NAMED.get(key, key), value, reading)
    assert f"{MISREAD_FINDING}{who}" in result.stderr
    assert what in result.stderr, result.stderr
    assert result.stderr.count(adopter.MANIFEST_MISREAD_REMEDIATION) == 1
    assert "plan ok" not in result.stdout


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


@pytest.mark.parametrize("id_line, assembly", NO_ID)
def test_check_names_an_id_it_derived_from_the_assembly(
        answered, tmp_path, id_line, assembly):
    """A plan that sets no id gets one from `execute`, which lowercases
    `legs.assembly`: the finding says so, because the line to change is not
    the one with the value. It says "not set in the plan" and not "not in
    the plan": an `id: null` is in the plan and sets nothing (review181's
    N3), and `Plan.get` reads it exactly as a missing key."""
    _, text = answered
    without_id = re.sub(r"^id: .*\n", id_line, text, count=1,
                        flags=re.MULTILINE)
    assert without_id != text, "no `id:` line in the plan"
    plan = tmp_path / PLAN_FILE
    carrying(plan, without_id, "legs.assembly", assembly)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    who, what = misread("id (not set in the plan, so legs.assembly "
                        "lowercased)", "true", TRUE_READ)
    assert f"{MISREAD_FINDING}{who}" in result.stderr
    assert what in result.stderr, result.stderr


#: `(plan key, as a hand-edited plan spells it, what the plan's loader reads
#: it as, the text `execute` writes for it)`. The loader reads each one as
#: something that is not text, so the plan does not say what `str` of it
#: says: `007` is read as 7, and `TRUE` as true. The sentence names what was
#: READ, with its kind, and then the text `execute` writes (review181's N2).
#: The project's loader reads that text back as the same kind again. The
#: list and the mapping are an `elected_on`'s, which `execute` writes as it
#: stands: as a `tracking_branch` it refuses either as `unsafe-value`, and
#: as a `visibility` `gh` takes neither, before anything is written
#: (`NEVER_WRITTEN`).
READ_AS_NOT_TEXT = [
    (TRACKING_KEY, "007", SEVEN_READ, "7"),
    (TRACKING_KEY, "TRUE", TRUE_READ, "True"),
    (TRACKING_KEY, "1.50", "the number 1.5", "1.5"),
    (ELECTED_ON_KEY, "[a]", "a list", "['a']"),
    (ELECTED_ON_KEY, "{a: b}", "a mapping", "{'a': 'b'}"),
    ("id", "007", SEVEN_READ, "7"),
    (PINS_KEY, "TRUE", TRUE_READ, "True"),
    (ELECTED_ON_KEY, DATE_DIGITS, f"the number {DATE_DIGITS}", DATE_DIGITS),
]


@pytest.mark.parametrize("key, spelled, read_as, written", READ_AS_NOT_TEXT,
                         ids=ids_of(READ_AS_NOT_TEXT, 0, 1))
def test_check_names_a_plan_value_that_is_not_text_by_what_was_read(
        answered, tmp_path, key, spelled, read_as, written):
    """The finding said `tracking_branch is '7'` for a plan that says `007`,
    and `'True'` for `TRUE`: `str` of what was read, which the plan never
    said. It says what the plan's loader read, and the text `execute`
    writes for it, which is `str` of that and is named as such."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    named = NAMED.get(key, key)
    assert (f"{MISREAD_FINDING}{named} was read out of the plan as {read_as}, "
            "which `execute` writes into ") in result.stderr, result.stderr
    assert (f"reads it back as {read_as} and not as the text `{written}`: "
            "choose another value.") in result.stderr, result.stderr
    assert f"{named} is " not in result.stderr, "`str` of it was echoed"


#: `(plan key, as a plan edited by hand spells it)`: values the project's
#: loader would misread, which `execute` never writes. It refuses the branch
#: as `unsafe-value` (`_checked_plan_values`), and `gh repo create` takes no
#: `--true`, before anything is written. A finding would say the value is
#: written and the run ends `adoption verified`: for these neither is true
#: (rv181f's F2, F2b).
NEVER_WRITTEN = [
    pytest.param(TRACKING_KEY, QUOTED_DOMAIN_USER, id=TRACKING_KEY),
    pytest.param(VISIBILITY_KEY, '"true"', id=VISIBILITY_KEY),
]


@pytest.mark.parametrize("key, spelled", NEVER_WRITTEN)
def test_check_says_nothing_misread_of_a_value_execute_never_writes(
        adopter, answered, tmp_path, key, spelled):
    """`check` asked the loader about every value, and named these two as
    misread, with a remediation saying the run would still end `adoption
    verified`. It asks only about a value `execute` gets as far as
    writing."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, spelled)
    result = checked(plan)
    assert result.returncode in (0, 1), result.stdout + result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION not in result.stderr


@needs_filter_repo
def test_execute_refuses_that_branch_as_unsafe_before_any_leg_exists(
        answered, tmp_path):
    """What `execute` does with the branch `check` no longer calls misread:
    it refuses it as `unsafe-value`, before it creates a leg or touches the
    source, so no sentence of `check`'s says it gets further."""
    source, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, TRACKING_KEY, QUOTED_DOMAIN_USER)
    assert MISREAD_FINDING not in checked(plan).stderr
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED unsafe-value: {TRACKING_KEY} is "), result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: A date with a line break in it, as a plan edited by hand spells it.
UNWRITABLE_DATE = '"2026-09-02\\nx"'
#: `(plan key, as a plan edited by hand spells it)`: values no file
#: `execute` writes can hold, which #255 names as `plan-unwritable-value`:
#: a line break, in a value read back as one line, and a control character
#: such as a tab. The date and the pins are written bare, where the
#: project's loader would read each as something else too; the visibility
#: is one `gh` takes no flag for (`NEVER_WRITTEN`).
UNWRITABLE = [
    pytest.param(ELECTED_ON_KEY, UNWRITABLE_DATE, id=ELECTED_ON_KEY),
    pytest.param(VISIBILITY_KEY, '"private\\nx"', id=VISIBILITY_KEY),
    pytest.param(PINS_KEY, '"a\\nb"', id="pins-line-break"),
    pytest.param(PINS_KEY, '"openGlass\\t"', id="pins-tab"),
]


@pytest.mark.parametrize("key, spelled", UNWRITABLE)
def test_check_names_a_value_no_file_can_hold_once_as_unwritable(
        adopter, answered, tmp_path, key, spelled):
    """At the merge of #255 the gate also called the date and the pin
    misread, under a remediation saying the run would still end `adoption
    verified`: one wrong value was two findings, and the second was false,
    because `execute` refuses the value before it writes anything. It is
    #255's finding alone."""
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
        answered, tmp_path):
    """`execute` refuses a plan under the code of `check`'s first finding,
    which for this date was the misread one: it is refused as what it is,
    before any leg exists."""
    source, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, ELECTED_ON_KEY, UNWRITABLE_DATE)
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED plan-unwritable-value: "), result.stderr
    assert MISREAD_FINDING not in result.stderr, result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: `(placeholder, value, the manifest line `execute` writes, what the loader
#: reads it back as)`: values the loader reads back as OTHER TEXT, each
#: through a placeholder the template writes bare. The double quotes in the
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
        adopter, placeholder, value, line, reading):
    """`repr` showed `CORP\\tom` with its backslash doubled, and the tab the
    loader makes of it as `\\t`, so each looked like the other (review181's
    N1). The value is shown as it is typed, and a character a terminal shows
    as something else is named, so the difference is the one there is."""
    assert adopter.manifest_misreads(
        [adopter._field("x", placeholder, value)]) == [
        f"x is `{value}`, which `execute` writes into {MANIFEST} as "
        f"`{line}`, where the project's own YAML loader reads it back as "
        f"{reading} and not as that text: choose another value"]


#: `(a hand-edited plan's pin, the item `execute` writes for it, as a
#: sentence shows that line)`. `execute` writes a pin into its `  - ` item as
#: it stands, so the whitespace after it stays in the line, where the loader
#: drops it. A space shows between the backticks; a no-break space makes the
#: line one a terminal would not show as it is, so Python spells it. Not a
#: tab since #255: no file `execute` writes holds a control character, and a
#: pin holding one is #255's finding alone (`UNWRITABLE`).
PIN_WITH_A_TRAIL = [
    pytest.param('"openGlass "', "`- openGlass `", id="space"),
    pytest.param('"openGlass\\xa0"', "'- openGlass\\xa0'",
                 id="no-break-space"),
]


@pytest.mark.parametrize("spelled, shown", PIN_WITH_A_TRAIL)
def test_a_pin_is_shown_in_the_line_execute_writes_whitespace_and_all(
        answered, tmp_path, spelled, shown):
    """The finding said `execute` writes `- openGlass` for a pin
    `"openGlass "`: the line was stripped after the pin was put in it, so
    the space `execute` keeps was gone from the line the sentence named
    (rv181f's F1). The loader drops that space, which is why the pin is
    refused, and the line named is the one `execute` writes."""
    _, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, PINS_KEY, spelled)
    result = checked(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"{MANIFEST}'s neutral_product_pins as {shown}, where the "
            "project's own YAML loader reads it back as the text `openGlass` "
            "and not as that text") in result.stderr, result.stderr


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
        adopter, answered, tmp_path, key, value, reading):
    """The refused half of the end-to-end run: `execute` says no through
    #168's one list of `check`'s findings, before it creates a leg or
    touches the source."""
    source, text = answered
    plan = tmp_path / PLAN_FILE
    carrying(plan, text, key, adopter.y(value))
    result = executed(plan, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED plan-manifest-misread: ")
    who, what = misread(NAMED.get(key, key), value, reading)
    assert f"{MISREAD_FINDING}{who}" in result.stderr
    assert what in result.stderr
    assert adopter.MANIFEST_MISREAD_REMEDIATION in result.stderr
    assert not (tmp_path / REMOTES).exists()
    assert SPLIT_BRANCH not in branches_of(source)


#: What the gate still lets through, each spelled like a keyword somewhere:
#: a leg path with `null` as a segment, a branch the PLAN quotes for its
#: leading digit and `project.yaml` writes bare, an id that is a YAML 1.1
#: boolean this loader reads as text, and a person whose name is a null
#: anywhere `project.yaml` does not quote it (`elected_by:` it does).
ACCEPTED = (SPEC_FLAG, LEGS_NULL, TRACKING_FLAG, Q4_BRANCH, "--id", "yes",
            ELECTED_BY_FLAG, "Null")


@needs_filter_repo
def test_what_is_still_accepted_adopts_clones_and_bootstraps(tmp_path):
    """The accepted half of the end-to-end run, to the step lane 2 found it
    stopped short of: the recursive clone and the first bootstrap, which put
    each leg on the branch `execute` pushed it on, with that branch as its
    upstream, and read back every value the plan was given."""
    source = make_source_repo(tmp_path / SOURCE_NAME)
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

    clone = tmp_path / "clone"
    cloned = git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b",
                 SPLIT_BRANCH, str(source), str(clone), cwd=tmp_path,
                 check=False)
    assert cloned.returncode == 0, cloned.stderr
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, (bootstrapped.stderr
                                          + bootstrapped.stdout)
    assert "bootstrap ok" in bootstrapped.stdout
    manifest = load_yaml(clone / MANIFEST)
    assert (manifest["id"], manifest[TRACKING_KEY],
            manifest[ELECTED_BY_KEY]) == ("yes", Q4_BRANCH, "Null")
    assert [leg["path"] for leg in manifest["legs"]] == [".", LEGS_NULL,
                                                         "code"]
    assert load_yaml(clone / "contracts/spec-pin.yaml")["submodule_path"] \
        == LEGS_NULL
    for mount in (LEGS_NULL, "code"):
        branches = [git("rev-parse", "--abbrev-ref", ref,
                        cwd=clone / mount).stdout.strip()
                    for ref in ("HEAD", "@{upstream}")]
        assert branches == [Q4_BRANCH, f"origin/{Q4_BRANCH}"], mount


# --- the gate asks the loader, where the template writes the value ----------

def test_the_gate_follows_the_loader_when_the_loader_learns_a_keyword(
        adopter, monkeypatch):
    """ONE QUESTION, `loader_reading`, for the plan writer and the gate. Teach
    the real reader that `yes` is a boolean and both change with no edit:
    `y` quotes it, and a branch or an id called `yes` is refused."""
    reads = repo_shape._scalar
    fields = [adopter._field(TRACKING_KEY, TRACKING_PLACEHOLDER, "yes"),
              adopter._field("id", "PROJECT_ID", "yes")]
    assert adopter.manifest_misreads(fields) == []
    monkeypatch.setattr(repo_shape, SCALAR_READER,
                        lambda raw: True if raw.strip() == "yes"
                        else reads(raw))
    assert adopter.y("yes") == QUOTED_YES
    assert [problem.split(" is ")[0] for problem
            in adopter.manifest_misreads(fields)] == [TRACKING_KEY, "id"]


def test_the_template_line_says_whether_a_value_is_quoted(adopter):
    """No list in `adopt-project.py` says which placeholders the templates
    quote: the line is read. `Null` is a person's name between the quotes of
    `elected_by:`, and no branch at all after `tracking_branch:`."""
    assert adopter._written(ELECTED_BY_PLACEHOLDER, "Null") == [
        (MANIFEST, 'elected_by: "Null"')]
    assert adopter.manifest_misreads(
        [adopter._field(ELECTED_BY_KEY, ELECTED_BY_PLACEHOLDER, "Null")]) == []
    assert adopter.manifest_misreads(
        [adopter._field(TRACKING_KEY, TRACKING_PLACEHOLDER, "Null")]) != []


#: Where each placeholder lands in the RENDERED files, as their loader reads
#: them: `(file, path into what it loads)`. The test's own oracle, written
#: from the templates, never from `adopt-project.py`.
LANDS = {
    TRACKING_PLACEHOLDER: [(MANIFEST, (TRACKING_KEY,))],
    ELECTED_BY_PLACEHOLDER: [(MANIFEST, (ELECTED_BY_KEY,))],
    REFERENCE_PLACEHOLDER: [(MANIFEST, (REFERENCE_KEY,))],
    "SPEC_PATH": [(MANIFEST, ("legs", 1, "path")),
                  ("contracts/spec-pin.yaml", ("submodule_path",))],
    PINS_PLACEHOLDER: [(MANIFEST, ("neutral_product_pins", 0))],
}


def rendered_readings(adopter, placeholder: str, value: str) -> list:
    """What the project's loader reads where `value` lands, in the three
    templated YAML files rendered WHOLE by the materializer's own `render`,
    every other placeholder filled with plain text."""
    from shape_materialize import PLACEHOLDER_RE, render
    template = REPO / "templates" / "assembly-root"
    # A naming block is lines of its own, and an empty one is no lines.
    values = {PINS_PLACEHOLDER: "[]", "ASSEMBLY_NAMING": "",
              "SPEC_NAMING": "", "CODE_NAMING": ""}
    if placeholder == PINS_PLACEHOLDER:
        values[placeholder] = "\n" + adopter._pin_item(value)
    else:
        values[placeholder] = value
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
        adopter, placeholder):
    """The gate asks one template line at a time. Rendered whole, as
    `execute` renders them, the files must agree on every candidate this
    module generates: a value the gate passes comes back out of each place
    it lands, and one it refuses does not."""
    for value in CANDIDATES:
        if placeholder == PINS_PLACEHOLDER:
            field = adopter._pin_field(PINS_KEY, value)
        else:
            field = adopter._field("x", placeholder, value)
        refused = bool(adopter.manifest_misreads([field]))
        lands = rendered_readings(adopter, placeholder, value)
        assert refused == any(got != value for got in lands), (value, lands)


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
        adopter, answered, tmp_path, monkeypatch):
    """`pins: [` was the one list of strings the plan wrote without `y`, so
    `--pin null` was `pins: [null]`: a null `Plan.load` drops. `plan` now
    refuses such a pin before writing, so the writer is asked with the
    gate taken away: the pin is a string like any other in the plan."""
    source, _ = answered
    monkeypatch.setattr(adopter, "manifest_misreads", lambda _fields: [])
    for pin in ("null", "Null", "NULL", "true", FALSE_TITLE):
        plan = tmp_path / f"{pin}.yaml"
        assert adopter.main([
            "plan", "--source", str(source), "--project", PROJECT_NAME,
            "--org", "testorg", ELECTED_BY_FLAG, "Test Human",
            "--elected-on", "2026-09-02", PIN_FLAG, pin,
            "--work-dir", str(tmp_path / "work"), "--out", str(plan)]) == 0
        assert f'\npins: ["{pin}"]\n' in text_of(plan)
        assert load_yaml(plan)[PINS_KEY] == [pin]
        assert adopter.Plan.load(plan).pins == [pin]


@pytest.mark.parametrize("pins, written", [
    ((OPEN_GLASS,), "pins: [openGlass]"),
    (("opensoft/openGlass",), "pins: [opensoft/openGlass]"),
    ((OPEN_GLASS, "opensoft/openCode"), "pins: [openGlass, opensoft/openCode]"),
    ((), "pins: []"),
], ids=["one", "owned", "two", "none"])
def test_an_ordinary_pin_is_written_as_it_always_was(tmp_path, pins, written):
    """`openGlass` and `opensoft/openGlass` are the pins that exist; they stay
    bare, singly and together, and no pin is still `pins: []`."""
    extra = tuple(part for pin in pins for part in (PIN_FLAG, pin))
    text = text_of(planned(tmp_path, *extra))
    assert f"\n{written}\n" in text


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
    assert "null" in paths and "True" in paths, paths
    assert all(isinstance(path, str) for path in paths), paths
    for path in ("null", "True"):
        answer(plan, path, "root")
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FINDING" not in result.stdout + result.stderr


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
