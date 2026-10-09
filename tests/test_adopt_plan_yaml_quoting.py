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

A LINE BREAK IS NOT IN THE GENERATED ALPHABET, on purpose. The reader takes a
plan line by line (`str.splitlines`, which also splits on `\\r`, `\\x0b`,
`\\x0c`, `\\x1c`-`\\x1e`, `\\x85`, `\\u2028` and `\\u2029`), a double-quoted scalar
cannot span lines, and the loader resolves an escape for `\\n` and `\\t` only.
A value carrying one is therefore not a question of quoting, #181 does not
make one read back, and putting it in a generator would assert a rule this
change does not make. (The one visible difference: a name whose ONLY line
break is a final one matched `_PLAIN_RE`, because `$` matches before it, and
was written bare; it is quoted now. Both spellings split the entry over two
lines and `check` refuses either plan as `yaml-unparsable`.)
"""

from __future__ import annotations

import importlib.util
import itertools
import random
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, resolve, run_script,
                      write_plan)

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
OPEN_GLASS = "openGlass"
SPLIT_BRANCH = "adopt/three-repo-shape"
QUOTED_YES = '"yes"'
PATHS = "paths"

#: Answered the way `test_adopt_plan.py` answers them, so `check` can pass.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))


def text_of(plan: Path) -> str:
    return plan.read_text(encoding="utf-8")


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
ORDINARY = ["spec", "code", "legs/spec", "Northwind", "Northwind-spec",
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
                     FALSE_WORD, "False", "FALSE"]

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
    monkeypatch.setattr(repo_shape, "_scalar", learned)
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

    monkeypatch.setattr(repo_shape, "_scalar", refusing)
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


# --- end to end, through `plan` and `check` --------------------------------

def checked(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


def planned(tmp_path: Path, *extra: str, tree: dict | None = None) -> Path:
    source = make_source_repo(tmp_path / "Thing", tree=tree)
    plan = tmp_path / "plan.yaml"
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
        encoding="utf-8")


def test_a_spec_path_of_null_is_the_string_null_and_check_mounts_it_there(
        adopter, tmp_path):
    """The repro of #181. On `main` the plan said `spec_path: null`, which
    loaded as no value, so `execute` mounted the leg at `spec` while `check`
    said so in the one sentence that names the mount.

    WHAT #169'S CANONICAL CHECK THEN DECIDES: `null` is one plain segment,
    neither a name Git keeps (`.git`) nor a Windows device (`nul` is one,
    `null` is not), so it is a path a leg can be mounted at and `check`
    accepts it -- as a directory literally called `null`, which is what was
    typed. Refusing it would be refusing a legal name for being spelled like a
    YAML keyword, and rewriting it to `spec` is the silent change #169 refuses.
    """
    plan = planned(tmp_path, "--spec-path", "null")
    assert 'spec_path: "null"' in text_of(plan)
    loaded = load_yaml(plan)
    assert loaded["legs"]["spec_path"] == "null"
    assert isinstance(loaded["legs"]["spec_path"], str)
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    spec_path, code_path, _, _ = adopter._checked_plan_values(
        adopter.Plan.load(plan))
    assert (spec_path, code_path) == ("null", "code"), (
        "what `execute` mounts the legs at")
    result = checked(plan)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "plan ok" in result.stdout
    assert "mount the legs at null/ and code/" in result.stdout
    assert "at spec/" not in result.stdout


def test_a_tracking_branch_of_true_is_the_string_true(adopter, tmp_path):
    """`--tracking-branch true` was written `tracking_branch: true`, read back
    as a boolean, and reached `execute` as `True`."""
    plan = planned(tmp_path, "--tracking-branch", "true")
    assert 'tracking_branch: "true"' in text_of(plan)
    loaded = load_yaml(plan)
    assert loaded["tracking_branch"] == "true"
    assert isinstance(loaded["tracking_branch"], str)
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    assert adopter._checked_plan_values(adopter.Plan.load(plan))[3] == "true"
    assert checked(plan).returncode == 0


@needs_filter_repo
def test_execute_mounts_the_leg_at_null_and_tracks_the_branch_true(tmp_path):
    """The whole chain, to the split branch. On `main` `execute` read
    `spec_path: null` as no value and registered the mount at `spec`, and
    read `tracking_branch: true` as a boolean; now the gitlink is at `null`
    -- the directory the person typed, and the one `check` said it would use
    -- and the branch the legs track is the one called `true`."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    written = write_plan(source, plan, extra=("--spec-path", "null",
                                              "--tracking-branch", "true"))
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    gitlinks = [line.split()[-1] for line in git(
        "ls-tree", SPLIT_BRANCH, cwd=source).stdout.splitlines()
        if line.startswith("160000")]
    assert sorted(gitlinks) == ["code", "null"], (
        "no gitlink at `spec`: the leg is mounted where `check` said")
    for leg_repository in sorted(remotes.glob("*.git")):
        assert git("branch", "--list", cwd=leg_repository).stdout.split() == [
            "*", "true"], leg_repository.name


@pytest.mark.parametrize("pin", ["null", "Null", "NULL", "true", "False"])
def test_a_pin_named_like_a_keyword_is_that_pin(adopter, tmp_path, pin):
    """`pins: [` is the one list of strings the plan writes without `y`, and
    `--pin null` was written `pins: [null]`: a null the plan's reader drops,
    so the pin the person asked for vanished (and `--pin true` came back as
    the pin `True`)."""
    plan = planned(tmp_path, "--pin", pin)
    assert f'\npins: ["{pin}"]\n' in text_of(plan)
    assert load_yaml(plan)["pins"] == [pin]
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
    extra = tuple(part for pin in pins for part in ("--pin", pin))
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
