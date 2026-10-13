# SPDX-License-Identifier: Apache-2.0
"""A plan's `question:`, its `source: commit:` and a submodule's name are
`_spelled` in a FINDING (#328).

#212 spelled every PATH a finding names, so that a line break, an ESC or a
byte that is not UTF-8 in a source name cannot escape the line it is printed
on. Three other texts reached a finding as typed, measured on c7c02fa:

  * a plan entry's `question:`, which people and AIs edit by hand, repeated
    after `The question was:` in `plan-unresolved`. A line feed in it ended
    the finding's line and began another, `grep '^FINDING'` read as `check`'s
    own; a carriage return and an ESC reached the terminal; and a byte that
    is not UTF-8 reached it as Python's own raw surrogate, which `print`
    writes to stderr as `\\udce9` and refuses on a stream strict about UTF-8;
  * the key git reports, `missing value for 'submodule.<name>.update'`, in
    `plan-gitmodules-unreadable`: the `<name>` is the source author's choice,
    and git prints it as it is. `_refused_value`'s messages spell the same
    key; this one did not. `execute` repeats it as its refusal, and the
    third too;
  * the first 12 characters of the plan's hand-edited `source: commit:`, in
    `plan-stale`, which `check` prints and `execute` refuses with (found by
    the review of this change, not by the issue).

All three now go through `_spelled`. A question and a commit print as they
did unless a character in them is not printable (`_shown`), and a key keeps
git's single quotes unless `_spelled` has anything to write differently, so
every finding that holds nothing unsafe is byte-identical to what it was.

NOTHING HERE WRITES A SPELLING `_spelled` MAY CHANGE. The characters pinned
by their spelling are the ones whose escape is the same before and after the
change that spells a byte `\\udcNN` and a character `\\xNN` (#329): a line
feed, a carriage return, ESC, a tab, U+0085 and U+2028. A byte that is not
UTF-8 is asked of `adopter._spelled` itself, whatever it writes.
"""

from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, GITLINK, GITMODULES, as_human,
                      blank_unnamed_pin_sources, git, link, make_source_repo,
                      planned, put_gitmodules, resolve, write_plan)

UTF8 = "utf-8"
UNRESOLVED = "plan-unresolved"
UNREADABLE = "plan-gitmodules-unreadable"
STALE = "plan-stale"
PROJECT = "Northwind"
#: Each character, by the id its tests wear: `(raw, as _spelled writes it)`.
CHARACTERS = {
    "line-feed": ("\n", "\\n"),
    "carriage-return": ("\r", "\\r"),
    "escape": ("\x1b", "\\x1b"),
    "tab": ("\t", "\\t"),
    "next-line": ("\x85", "\\x85"),
    "line-separator": ("\u2028", "\\u2028"),
}
EACH_CHARACTER = pytest.mark.parametrize(
    ("char", "spelled"), list(CHARACTERS.values()), ids=list(CHARACTERS))
#: The byte 0xE9, as `Source.tree` and `_git_path` keep a byte that is not
#: UTF-8: a lone surrogate.
BYTE = "\udce9"
#: The finding's own words up to the question, for an entry `README.md`.
ASKED = "FINDING plan-unresolved: `README.md` still has `leg: null`. The question was: "
#: The issue's own question: a line feed, a carriage return and an ESC, as a
#: plan's double-quoted scalar writes them, and the text they decode to.
ISSUE_QUESTION_YAML = ('"Which leg?\\nFINDING plan-ok: this line was not '
                       'written by check\\r\\u001b[2Kplan ok"')
ISSUE_QUESTION = ("Which leg?\nFINDING plan-ok: this line was not written by "
                  "check\r\x1b[2Kplan ok")
ISSUE_QUESTION_SPELLED = ("`Which leg?\\nFINDING plan-ok: this line was not "
                          "written by check\\r\\x1b[2Kplan ok`")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_question_and_submodule_spelling", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_filter_repo_probe(adopter, monkeypatch):
    """`cmd_execute` asks for `git filter-repo` first, and no test here gets
    as far as using it."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


def assert_one_readable_line(line: str, *raw: str) -> None:
    """`line` is one line a terminal shows as written: no line break, no ESC,
    no other character `str.isprintable` refuses, and so nothing that cannot
    be encoded as UTF-8 either; and none of `raw`."""
    for char in raw:
        assert char not in line, f"the raw character is printed: {line!r}"
    assert line.isprintable(), f"not one line of printable text: {line!r}"
    line.encode(UTF8)


def plan_of(adopter, entries: list[dict]):
    """An adoption plan holding `entries`, read as `Plan.load` reads one,
    built in memory: the finding is what is under test, not the reader."""
    return adopter.Plan(Path("adoption-plan.yaml"), {
        "kind": adopter.PLAN_KIND, "mode": "in-place",
        "legs": {"spec_path": "spec", "code_path": "code"},
        "paths": entries})


def asked(adopter, question) -> list[str]:
    """`_leg_findings` for one unanswered entry, `README.md`, whose
    `question:` is `question`; `None` is an entry with no `question:` at
    all."""
    entry = {"path": "README.md", "leg": None}
    if question is not None:
        entry["question"] = question
    return adopter._leg_findings(plan_of(adopter, [entry]), [])


# --- the question: what is spelled -----------------------------------------

@EACH_CHARACTER
def test_a_question_holding_the_character_is_spelled_on_one_line(adopter, char,
                                                                spelled):
    [finding] = asked(adopter, f"Which{char}leg?")
    assert finding == f"{ASKED}`Which{spelled}leg?`"
    assert_one_readable_line(finding, char)


def test_the_issues_own_question_forges_no_second_finding(adopter):
    """On c7c02fa this was two findings, the second not written by `check`:
    `FINDING plan-ok: this line was not written by check`, then a carriage
    return and an ESC, which sent the cursor back over the line and cleared
    it."""
    findings = asked(adopter, ISSUE_QUESTION)
    assert findings == [ASKED + ISSUE_QUESTION_SPELLED]
    assert_one_readable_line(findings[0], "\n", "\r", "\x1b")
    assert findings[0].count("FINDING") == 2, "the text is shown, as text"


def test_a_question_holding_a_byte_that_is_not_utf8_is_spelled_as_a_path_is(
        adopter):
    """`_spelled` decides how: the lone surrogate `Source.tree` keeps for the
    byte 0xE9 is `\\xe9` or `\\udce9` by which spelling it writes. Printed
    raw it raised `UnicodeEncodeError` on a stream strict about UTF-8, and
    on stderr, which is not, came out as Python's own `\\udce9`."""
    [finding] = asked(adopter, f"Which leg of caf{BYTE}?")
    assert finding == f"{ASKED}{adopter._spelled(f'Which leg of caf{BYTE}?')}"
    assert BYTE not in finding
    assert_one_readable_line(finding, BYTE)


def test_a_backtick_and_a_backslash_beside_a_line_feed_are_escaped(adopter):
    """The spelling reads one way only, and the backticks that wrap it still
    delimit it: a question that says `\\n` and one that holds a line feed are
    not the same text."""
    [finding] = asked(adopter, "A `tick`, a \\n and\n a line feed")
    assert finding == f"{ASKED}`A \\`tick\\`, a \\\\n and\\n a line feed`"


def test_every_unsafe_character_at_once_is_one_spelled_question(adopter):
    raw = "".join(char for char, _ in CHARACTERS.values())
    [finding] = asked(adopter, f"a{raw}b")
    assert finding == (ASKED + "`a"
                       + "".join(spelled for _, spelled in CHARACTERS.values())
                       + "b`")
    assert_one_readable_line(finding, *raw)


# --- the question: what is not --------------------------------------------

#: Questions that hold only printable characters, and the text they print as:
#: byte for byte what the finding said before. `plan` writes only these (the
#: last test below), and a hand edit that keeps its backticks, its backslashes
#: and its accents is one too.
UNCHANGED = {
    "plain": ("Which leg?", "Which leg?"),
    "empty": ("", ""),
    "backticks-and-backslashes": (
        "Is `src/a\\`b/` code? A \\ stays a \\.",
        "Is `src/a\\`b/` code? A \\ stays a \\."),
    "accents-and-dashes": ("Is café — `src/` — spec or code? ‘yes’",
                           "Is café — `src/` — spec or code? ‘yes’"),
    "single-and-double-quotes": ("It's \"spec\"?", "It's \"spec\"?"),
    "no-question-at-all": (None, "None"),
    "a-number": (7, "7"),
    "a-list": (["a", "b\x1bc"], "['a', 'b\\x1bc']"),
}


@pytest.mark.parametrize("question, printed", UNCHANGED.values(),
                         ids=list(UNCHANGED))
def test_a_printable_question_prints_exactly_as_it_did(adopter, question,
                                                       printed):
    assert asked(adopter, question) == [ASKED + printed]


def test_a_question_is_spelled_by_spelled_itself(adopter, monkeypatch):
    """So that a change to the way `_spelled` writes a character moves the
    question with it (#329): the same entry, spelled by a stand-in, is named
    by the stand-in. A question with nothing unsafe in it never asks."""
    monkeypatch.setattr(adopter, "_spelled", lambda text: "`<spelled>`")
    assert asked(adopter, "Which\nleg?") == [
        "FINDING plan-unresolved: `<spelled>` still has `leg: null`. The "
        "question was: `<spelled>`"]
    assert asked(adopter, "Which leg?") == [
        "FINDING plan-unresolved: `<spelled>` still has `leg: null`. The "
        "question was: Which leg?"]


def test_a_bad_leg_still_names_the_leg_as_it_did(adopter):
    """`plan-bad-leg` repeats the `leg:` through `repr`, which escapes what
    it should; nothing about it moves."""
    plan = plan_of(adopter, [{"path": "README.md", "leg": "Sp\x1bec"}])
    assert adopter._leg_findings(plan, []) == [
        "FINDING plan-bad-leg: `README.md` declares leg 'Sp\\x1bec'; it is "
        "one of ['spec', 'code', 'root', 'drop']"]


def test_every_question_the_shipped_policy_asks_is_printable(adopter):
    """The reason `plan`'s own questions print exactly as they did: a rule's
    `question:` is prose with no character `str.isprintable` refuses, and
    the paths `_asked_about` adds to one are `_spelled`."""
    policy = adopter.PathPolicy.load(adopter.PATH_POLICY)
    questions = [rule["question"] for rule, _ in policy.rules
                 if rule.get("question")]
    questions.append(policy.default["question"])
    assert len(questions) >= 5
    for question in questions:
        assert question.isprintable(), question


# --- the submodule's name: what is spelled ---------------------------------

def key_of(char: str) -> str:
    return f"submodule.b{char}x.update"


def listed(key: str) -> bytes:
    """`git config -z --list` for a file holding `key` and no value: `-z`
    prints a key with no value with no newline."""
    return key.encode(UTF8, "surrogateescape") + b"\x00"


#: A name cannot hold a line feed: git refuses a raw one in a section header
#: and reads the escape `\\n` as the letter `n`, and `-z` ends a key at one.
IN_A_NAME = {name: pair for name, pair in CHARACTERS.items()
             if name != "line-feed"}


@pytest.mark.parametrize(("char", "spelled"), list(IN_A_NAME.values()),
                         ids=list(IN_A_NAME))
def test_a_name_holding_the_character_is_spelled_in_missing_value(
        adopter, char, spelled):
    said = adopter._registrations(listed(key_of(char)))
    assert said == f"missing value for `submodule.b{spelled}x.update`"
    assert_one_readable_line(said, char)


def test_a_name_holding_a_byte_that_is_not_utf8_is_spelled(adopter):
    key = key_of(BYTE)
    said = adopter._registrations(listed(key))
    assert said == f"missing value for {adopter._spelled(key)}"
    assert_one_readable_line(said, BYTE)


@pytest.mark.parametrize("var", ["path", "url", "ignore", "update", "branch"])
def test_each_key_git_dies_on_is_spelled(adopter, var):
    said = adopter._registrations(listed(f"submodule.b\x1bx.{var}"))
    assert said == f"missing value for `submodule.b\\x1bx.{var}`"


def test_the_name_is_spelled_beside_a_record_that_has_a_value(adopter):
    """The first key git dies on is the one named, and the registration
    before it is read as it always was."""
    said = adopter._registrations(
        b"submodule.a.path\nvendor/a\x00submodule.a.url\n../a\x00"
        + listed(key_of("\x1b")))
    assert said == "missing value for `submodule.b\\x1bx.update`"


def test_a_name_git_ignores_is_still_not_a_finding(adopter):
    """Under a name git skips (`..` between separators, or empty) nothing
    dies, so there is nothing to spell, whatever the name holds."""
    registered = adopter._registrations(
        listed("submodule.../\x1b.update") + listed("submodule..update"))
    assert isinstance(registered, adopter.Registrations)


# --- the submodule's name: what is not -------------------------------------

#: Names `_spelled` leaves as they are: the finding keeps git's single
#: quotes and reads byte for byte as it did.
UNCHANGED_NAMES = ["b", "my dep", "a.b", "vendor/b-c_d", "café", "名前",
                   "it's", 'say "hi"']


@pytest.mark.parametrize("name", UNCHANGED_NAMES)
@pytest.mark.parametrize("var", ["path", "url", "ignore", "update", "branch"])
def test_a_printable_name_keeps_gits_quotes(adopter, name, var):
    assert adopter._registrations(listed(f"submodule.{name}.{var}")) == (
        f"missing value for 'submodule.{name}.{var}'")


@pytest.mark.parametrize("name, spelled", [
    ("b`x", "`submodule.b\\`x.update`"),
    ("b\\x", "`submodule.b\\\\x.update`"),
], ids=["a-backtick", "a-backslash"])
def test_a_backtick_or_a_backslash_in_the_name_is_spelled_as_a_path_is(
        adopter, name, spelled):
    """The one printable name whose finding changes, because `_spelled`
    writes a backslash and a backtick with a backslash, as `_refused_value`
    already does for the same key, so that the spelling reads one way only."""
    assert adopter._registrations(listed(f"submodule.{name}.update")) == (
        f"missing value for {spelled}")


def test_the_name_is_spelled_the_way_a_refused_value_spells_it(adopter):
    """One name, two findings, one spelling: `update = bogus` under the same
    name names the key through `_spelled` too."""
    name = "b\x1bx"
    missing = adopter._registrations(listed(f"submodule.{name}.update"))
    refused = adopter._registrations(
        f"submodule.{name}.update\nbogus\x00".encode())
    assert adopter._spelled(f"submodule.{name}.update") in missing
    assert adopter._spelled(f"submodule.{name}.update") in refused


def test_git_quoted_asks_spelled_and_writes_no_escape_of_its_own(
        adopter, monkeypatch):
    """So that a change to the way `_spelled` writes a character moves this
    finding with it (#329): the same name, spelled by a stand-in, is named by
    the stand-in."""
    monkeypatch.setattr(adopter, "_spelled", lambda text: "`<spelled>`")
    assert adopter._git_quoted("submodule.b.update") == "`<spelled>`"
    monkeypatch.setattr(adopter, "_spelled", lambda text: f"`{text}`")
    assert adopter._git_quoted("submodule.b.update") == (
        "'submodule.b.update'")


# --- end to end: `check` as a person runs it, and `execute` ---------------

def check_bytes(plan: Path, work: Path) -> subprocess.CompletedProcess:
    """`check --plan <plan>` as a person runs it, its output kept as BYTES:
    text mode turns a carriage return into a line break before a test can
    see it."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": UTF8}, {})
    return subprocess.run(
        [sys.executable, str(ADOPT), "check", "--plan", str(plan),
         "--work-dir", str(work)],
        capture_output=True, stdin=subprocess.DEVNULL, env=env, check=False)


def printed_lines(output: bytes) -> list[str]:
    """`output` as the lines a terminal shows, split ONLY where the tool
    ended a line. Python ends one with `os.linesep`, which is `\\r\\n` on
    Windows; any other carriage return, line feed or separator is the
    tool's to have spelled."""
    return output.replace(os.linesep.encode(), b"\n").decode(
        UTF8, "surrogateescape").split("\n")


def plan_asking(base: Path, question_yaml: str | None) -> Path:
    """A plan for `make_source_repo`'s tree in which every question is
    answered but the one for `examples/`, whose `question:` line is
    `question_yaml`, a scalar as the plan's own writer spells one; or, for
    None, in which nothing is answered."""
    source = make_source_repo(base / "Thing")
    plan = base / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    if question_yaml is None:
        return plan
    for path in (".claude/", "release.yaml"):
        resolve(plan, path, "root")
    text = plan.read_text(encoding=UTF8)
    edited, count = re.subn(
        r"(  - path: examples/\n(?:    .*\n)*?    question: ).*\n",
        lambda found: found[1] + question_yaml + "\n", text, count=1)
    assert count == 1, text
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(edited)
    return plan


def findings_printed(done: subprocess.CompletedProcess, code: str) -> list[str]:
    return [line for line in printed_lines(done.stderr)
            if line.startswith(f"FINDING {code}: ")]


def test_check_prints_the_issues_question_on_one_line(tmp_path):
    """THE ISSUE'S ROUTE 1, read as bytes: one finding for the entry, no
    second one forged out of its text, and nothing `check` prints, on either
    stream, holds a character `str.isprintable` refuses."""
    plan = plan_asking(tmp_path, ISSUE_QUESTION_YAML)
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    for line in printed_lines(done.stderr) + printed_lines(done.stdout):
        assert_one_readable_line(line, "\r", "\x1b")
    assert findings_printed(done, UNRESOLVED) == [
        "FINDING plan-unresolved: `examples/` still has `leg: null`. The "
        "question was: " + ISSUE_QUESTION_SPELLED]
    forged = [line for line in printed_lines(done.stderr)
              if line.startswith("FINDING plan-ok")]
    assert forged == [], "a finding `check` did not write"


def test_check_spells_a_question_holding_a_byte_that_is_not_utf8(adopter,
                                                                 tmp_path):
    question = f"Which leg of caf{BYTE}?"
    plan = plan_asking(tmp_path, '"Which leg of caf\\udce9?"')
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    [line] = findings_printed(done, UNRESOLVED)
    assert line == ("FINDING plan-unresolved: `examples/` still has `leg: "
                    f"null`. The question was: {adopter._spelled(question)}")
    assert_one_readable_line(line)
    for printed in printed_lines(done.stderr) + printed_lines(done.stdout):
        assert_one_readable_line(printed, BYTE)


def test_check_prints_every_question_plan_wrote_exactly_as_it_did(adopter,
                                                                  tmp_path):
    """The questions `plan` wrote for this tree, left unanswered, are read
    back by the tool's own reader, and each is printed whole after `The
    question was:`, byte for byte: nothing is spelled that is not unsafe."""
    plan = plan_asking(tmp_path, None)
    questions = {str(entry["path"]): entry["question"] for entry in
                 adopter.Plan.load(plan).entries
                 if entry.get("leg") is None}
    assert set(questions) >= {"examples/", ".claude/", "release.yaml"}
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    printed = findings_printed(done, UNRESOLVED)
    assert len(printed) == len(questions)
    for path, question in questions.items():
        line = (f"FINDING plan-unresolved: `{path}` still has `leg: null`. "
                f"The question was: {question}")
        assert line in printed, (line, printed)


def test_execute_refuses_an_unresolved_entry_without_the_question(
        adopter, tmp_path):
    """The issue says `execute` repeats the question. It does not:
    `_refuse_an_unrunnable_plan` refuses an entry whose `leg:` is null in
    its own words, the paths and not the question, before
    `_refuse_what_check_finds` could repeat `check`'s finding. The refusal
    holds no raw character, on main and here."""
    plan = plan_asking(tmp_path, ISSUE_QUESTION_YAML)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNRESOLVED
    for line in str(caught.value).split("\n"):
        assert_one_readable_line(line, "\r", "\x1b")
        assert "FINDING plan-ok" not in line
    assert not remotes.exists()


#: A source tree `plan` asks only about `.gitmodules` and `vendor/` for:
#: `specs/` and `src/` classify themselves and `README.md` stays in the root.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
ANSWERS = {GITMODULES: "code", "vendor/": "code"}


def source_naming(base: Path, name: bytes) -> Path:
    """A source whose tip holds a gitlink at `vendor/b` and a `.gitmodules`
    registering it under `name`, and an `update` with no value: the one
    key git's submodule reader dies on that says no value."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    put_gitmodules(source, b'[submodule "' + name + b'"]\n\tpath = '
                   + GITLINK.encode() + b"\n\turl = ../b\n\tupdate\n")
    link(source)
    as_human("commit", "-qm", "A submodule named oddly", cwd=source)
    return source


#: `(the name's bytes in the `.gitmodules`, the key as `check` reads it, how
#: the finding names the key)`; None where `_spelled` decides, as it does for
#: a byte that is not UTF-8.
NAMES = {
    "escape": (b"b\x1b[2Kx", "submodule.b\x1b[2Kx.update",
               "`submodule.b\\x1b[2Kx.update`"),
    "next-line": (b"b\xc2\x85x", "submodule.b\x85x.update",
                  "`submodule.b\\x85x.update`"),
    "line-separator": (b"b\xe2\x80\xa8x", "submodule.b\u2028x.update",
                       "`submodule.b\\u2028x.update`"),
    "a-byte-that-is-not-utf8": (b"b\xe9x", f"submodule.b{BYTE}x.update", None),
    "a-backtick": (b"b`x", "submodule.b`x.update",
                   "`submodule.b\\`x.update`"),
    "an-ordinary-name": (b"b", "submodule.b.update", "'submodule.b.update'"),
}


@pytest.mark.parametrize("name, key, quoted", NAMES.values(),
                         ids=list(NAMES))
def test_check_spells_the_name_in_the_one_line_of_the_finding(adopter,
                                                              tmp_path, name,
                                                              key, quoted):
    plan = planned(source_naming(tmp_path, name), tmp_path, ANSWERS)
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    for line in printed_lines(done.stderr) + printed_lines(done.stdout):
        assert_one_readable_line(line, "\r", "\x1b", "\x85", "\u2028", BYTE)
    [line] = findings_printed(done, UNREADABLE)
    quoted = quoted or adopter._spelled(key)
    assert (f"for its submodules (missing value for {quoted}), and the "
            "source holds a submodule, ") in line, line


@pytest.mark.parametrize("name, key", [NAMES["escape"][:2],
                                       NAMES["a-byte-that-is-not-utf8"][:2]],
                         ids=["escape", "a-byte-that-is-not-utf8"])
def test_execute_refuses_on_the_lines_check_prints(adopter, tmp_path, name,
                                                   key):
    """`execute` repeats this one in its refusal, as `check` prints it, and
    creates nothing."""
    plan = planned(source_naming(tmp_path, name), tmp_path, ANSWERS)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == UNREADABLE
    said = str(caught.value).split("\n")
    for line in said:
        assert_one_readable_line(line, "\r", "\x1b", BYTE)
    assert any(f"(missing value for {adopter._spelled(key)}), " in line
               for line in said), said
    assert not remotes.exists(), "not even the directory the legs go in"


# --- the plan's `source: commit:`: what is spelled -------------------------
#
# Found by the review of this change, on a96297e: `plan-stale` prints the
# first 12 characters of the plan's `commit:` as typed, in `check`'s finding
# and in `execute`'s refusal, which is the same class as the two above.

#: `(the scalar as the plan's writer spells one, the text it reads back as,
#: how the finding spells that text's first 12 characters)`; None where
#: `_spelled` decides, as it does for a byte that is not UTF-8. The slice is
#: taken before the spelling, so that twenty escapes print as twelve.
COMMITS = {
    "an-esc-and-a-line-feed": (
        '"a\\u001b[2K\\nFINDING ok"', "a\x1b[2K\nFINDING ok",
        "`a\\x1b[2K\\nFINDIN`"),
    "a-leading-line-feed": (
        '"\\nFINDING ok: x"', "\nFINDING ok: x", "`\\nFINDING ok:`"),
    "a-carriage-return": (
        '"abc\\rFINDING plan-ok: x"', "abc\rFINDING plan-ok: x",
        "`abc\\rFINDING `"),
    "next-line": ('"ab\\u0085cd"', "ab\x85cd", "`ab\\x85cd`"),
    "line-separator": ('"ab\\u2028cd"', "ab\u2028cd", "`ab\\u2028cd`"),
    "a-byte-that-is-not-utf8": ('"abc\\udce9def"', f"abc{BYTE}def", None),
    "twenty-escapes": ('"' + "\\u001b" * 20 + '"', "\x1b" * 20,
                       "`" + "\\x1b" * 12 + "`"),
}
EACH_COMMIT = pytest.mark.parametrize(
    ("commit_yaml", "commit", "spelled"), list(COMMITS.values()),
    ids=list(COMMITS))


def stale_plan(adopter, base: Path, commit_yaml: str) -> tuple[Path, str]:
    """A plan for a source `plan` has no question for, whose `source:
    commit:` is the scalar `commit_yaml`, and the tip git names for that
    source: so the plan is stale, and `check` and `execute` say so."""
    source = make_source_repo(base / "Thing", tree=SMALL_TREE, edits=())
    plan = planned(source, base, {})
    assert [entry for entry in adopter.Plan.load(plan).entries
            if entry.get("leg") is None] == [], "an unanswered entry"
    text = plan.read_text(encoding=UTF8)
    edited, count = re.subn(r"(?m)^(  commit: ).*$",
                            lambda found: found[1] + commit_yaml, text,
                            count=1)
    assert count == 1, text
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(edited)
    return plan, git("rev-parse", "HEAD", cwd=source).stdout.strip()


def spelled_commit(adopter, commit: str, spelled: str | None) -> str:
    """The first 12 characters of `commit`, as the finding spells them: by
    the table, or by `_spelled` itself where it decides."""
    return spelled if spelled is not None else adopter._spelled(commit[:12])


@EACH_COMMIT
def test_check_spells_the_plans_commit_in_the_one_line_of_plan_stale(
        adopter, tmp_path, commit_yaml, commit, spelled):
    plan, tip = stale_plan(adopter, tmp_path, commit_yaml)
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    said = printed_lines(done.stderr) + printed_lines(done.stdout)
    for line in said:
        assert_one_readable_line(line, "\r", "\x1b", "\x85", "\u2028", BYTE)
    [line] = findings_printed(done, STALE)
    assert line.startswith(
        "FINDING plan-stale: the plan was written against "
        f"{spelled_commit(adopter, commit, spelled)} but `main` is now "
        f"at {tip[:12]}. Re-run `plan`: "), line
    forged = [line for line in said if line.startswith("FIND")
              and not line.startswith("FINDING plan-")]
    assert forged == [], "a finding `check` did not write"


@EACH_COMMIT
def test_execute_refuses_plan_stale_on_the_line_check_prints(
        adopter, tmp_path, commit_yaml, commit, spelled):
    """`execute` repeats `plan-stale` in its refusal, and creates nothing."""
    plan, tip = stale_plan(adopter, tmp_path, commit_yaml)
    remotes = tmp_path / "remotes"
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=remotes,
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert caught.value.code == STALE
    said = str(caught.value).split("\n")
    for line in said:
        assert_one_readable_line(line, "\r", "\x1b", "\x85", "\u2028", BYTE)
    assert said[0] == (
        "REFUSED plan-stale: the plan was written against "
        f"{spelled_commit(adopter, commit, spelled)} and `main` is now "
        f"at {tip[:12]}"), said
    assert not remotes.exists(), "not even the directory the legs go in"


# --- the plan's `source: commit:`: what is not -----------------------------

#: A plan's `commit:` that holds only printable characters, and the first 12
#: of them: printed as they were, with no backticks.
UNCHANGED_COMMITS = {
    "a-hash": ("0123456789abcdef0123456789abcdef01234567", "0123456789ab"),
    "a-name": ("release-1.0.0-rc1", "release-1.0."),
}


@pytest.mark.parametrize("commit, printed", UNCHANGED_COMMITS.values(),
                         ids=list(UNCHANGED_COMMITS))
def test_a_printable_stale_commit_prints_exactly_as_it_did(adopter, tmp_path,
                                                           commit, printed):
    """The case that happens: a plan written against a commit the source has
    since moved on from. Its first 12 characters print as they were, in
    `check` and in `execute`."""
    plan, tip = stale_plan(adopter, tmp_path, f'"{commit}"')
    done = check_bytes(plan, tmp_path / "work")
    assert done.returncode == 1, done.stderr + done.stdout
    [line] = findings_printed(done, STALE)
    assert line.startswith(
        f"FINDING plan-stale: the plan was written against {printed} but "
        f"`main` is now at {tip[:12]}. Re-run `plan`: ")
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan), source=None, local_remote_dir=tmp_path / "remotes",
            allow_empty_leg=[], yes=True, work_dir=tmp_path / "work"))
    assert str(caught.value).split("\n")[0] == (
        f"REFUSED plan-stale: the plan was written against {printed} and "
        f"`main` is now at {tip[:12]}")
