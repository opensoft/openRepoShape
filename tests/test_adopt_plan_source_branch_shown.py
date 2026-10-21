# SPDX-License-Identifier: Apache-2.0
"""`plan`'s `source` line names the source's branch as `_shown` names a path
(#1035).

The line read `source     <where> @ <commit> (<branch>), N files, M commits`,
and `<branch>` was printed as it is. A branch is a name its author chose, and
git lets one hold U+202E and the other bidirectional controls, the line
boundaries U+0085 and U+2028, and a zero-width space: lane 1's reviewer
planned a source on `ma<U+202E>in` with `--tracking-branch main` and found the
U+202E in the terminal's bytes, where it reorders what the line shows after
it. `plan` already spelled every other name it prints (`_shown`, #199, #900),
and `check` spells this branch where it names it (`plan-stale`,
`plan-tracking-branch-missing`), so the line now says `` `ma\\u202ein` ``.

AN ORDINARY BRANCH PRINTS AS IT DID: `_shown` returns a printable name as it
is, so `(main)` is still `(main)` and not `` (`main`) ``.

The end-to-end rows make the branch in a real local source and run `plan` as
a person does, reading the BYTES it prints. Git refuses an ASCII control
character in a ref name (`git branch` says `not a valid branch name`, and so
does `update-ref`), so no source can hold a carriage return, an ESC or a NUL
in its branch: those rows call the report in this process, with the branch
set on the `Source` it reads, as the tests of `check`'s sentences do.
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

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources, git,
                      make_source_repo, on_a_branch_that_is_not_utf_8)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

PLAN_FILE = "adoption-plan.yaml"
#: What every row's line starts with.
SOURCE = "source     "
#: `<where> @ <commit>, then the branch in parentheses, then the counts.
LINE_RE = re.compile(r"source {5}.+ @ (?P<commit>[0-9a-f]{12}) "
                     r"\((?P<branch>.*)\), (?P<files>\d+) files, "
                     r"(?P<commits>\d+) commits")

#: The characters git lets into a branch name that a terminal does not show
#: as they are, by the id their rows wear: `(raw, as _spelled writes it)`.
#: A bidirectional override and an isolate, the two line boundaries of
#: `str.splitlines` that git allows (U+0085, U+2028), and a zero-width space.
BRANCH_CHARACTERS = {
    "bidi-override": ("\u202e", "\\u202e"),
    "bidi-isolate": ("\u2066", "\\u2066"),
    "next-line": ("\x85", "\\x85"),
    "line-separator": ("\u2028", "\\u2028"),
    "zero-width-space": ("\u200b", "\\u200b"),
}
EACH_BRANCH_CHARACTER = pytest.mark.parametrize(
    ("char", "spelled"), list(BRANCH_CHARACTERS.values()),
    ids=list(BRANCH_CHARACTERS))

#: The ASCII controls no git ref name can hold, with the plan's spelling of
#: each (`repo_shape.double_quoted`).
CONTROL_CHARACTERS = {
    "nul": ("\x00", "\\x00"),
    "bell": ("\x07", "\\x07"),
    "backspace": ("\x08", "\\x08"),
    "carriage-return": ("\r", "\\r"),
    "line-feed": ("\n", "\\n"),
    "escape": ("\x1b", "\\x1b"),
    "delete": ("\x7f", "\\x7f"),
}
EACH_CONTROL = pytest.mark.parametrize(
    ("char", "spelled"), list(CONTROL_CHARACTERS.values()),
    ids=list(CONTROL_CHARACTERS))


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location(
        "adopt_plan_source_branch_shown", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def planned(source: Path, plan: Path, **asked: str
            ) -> subprocess.CompletedProcess:
    """`plan` as a person runs it, answered in BYTES: a name printed raw,
    `\\r`, would read as `\\n` through text mode. `--tracking-branch main`
    because the source is read at the branch it is on, and a branch outside
    `unsafe-value`'s alphabet is refused as the default tracking branch."""
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", **asked}, asked)
    return subprocess.run(
        [sys.executable, str(ADOPT), "plan", "--source", str(source),
         "--project", "Northwind", "--org", "testorg",
         "--elected-by", "Test Human", "--elected-on", "2026-09-02",
         "--tracking-branch", "main", "--out", str(plan)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)


def source_on(base: Path, branch: str) -> Path:
    """A source whose HEAD is on a new `branch`, beside `main`, which the
    plan tracks: both at the one commit, so the tracking branch is one the
    source has and `plan` has no NOTE to print about it."""
    source = make_source_repo(base / "Thing")
    git("switch", "-q", "-c", branch, cwd=source)
    return source


def the_source_line(text: str) -> str:
    """The one line of `text` that begins `source     `, split at line feeds
    only: a line boundary printed raw stays inside it."""
    [line] = [each for each in text.split("\n") if each.startswith(SOURCE)]
    return line


def counted(source: Path) -> tuple[str, str, str]:
    """`(commit, files, commits)` as the `source` line should say them."""
    commit = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    files = git("ls-tree", "-r", "--name-only", "HEAD", cwd=source)
    commits = git("rev-list", "--count", "HEAD", cwd=source)
    return (commit[:12], str(len(files.stdout.splitlines())),
            commits.stdout.strip())


def assert_branch_in_the_line(done: subprocess.CompletedProcess, source: Path,
                              branch: str) -> None:
    """`plan` exited 0 and its `source` line is one printable line that names
    the branch as `branch` and then the counts git gives."""
    assert done.returncode == 0, done.stderr + done.stdout
    assert b"Traceback" not in done.stderr
    line = the_source_line(done.stdout.decode("utf-8"))
    assert line.isprintable(), f"not one line of printable text: {line!r}"
    commit, files, commits = counted(source)
    found = LINE_RE.fullmatch(line)
    assert found, line
    assert found.groupdict() == {"commit": commit, "branch": branch,
                                 "files": files, "commits": commits}, line


# --- end to end: a branch git made ------------------------------------------

@EACH_BRANCH_CHARACTER
def test_plan_spells_a_branch_that_holds_an_unprintable_character(
        tmp_path, char, spelled):
    """The issue's repro, and the four characters beside U+202E that git
    lets into a branch name. The raw character is in none of the bytes
    `plan` printed, the line holds the branch spelled between backticks as
    `check` spells it, and the plan file still records the branch as it is
    (`default_branch:` is written escaped, and reads back whole)."""
    branch = f"ma{char}in"
    source = source_on(tmp_path, branch)
    plan = tmp_path / PLAN_FILE

    done = planned(source, plan)

    assert char.encode("utf-8") not in done.stdout, done.stdout
    assert_branch_in_the_line(done, source, f"`ma{spelled}in`")
    assert load_yaml(plan)["source"]["default_branch"] == branch


def test_plan_names_an_ordinary_branch_as_it_did(tmp_path):
    """A printable branch is `_shown` as it is: no backticks, no escape. A
    spelling for every branch would read `` (`trunk`) `` and change a line
    nobody asked to change."""
    source = source_on(tmp_path, "feat/x-1")

    done = planned(source, tmp_path / PLAN_FILE)

    assert_branch_in_the_line(done, source, "feat/x-1")


def test_plan_spells_a_branch_that_is_not_utf8_on_a_strict_stdout(tmp_path):
    """The byte 0xE9 in a branch, kept as the lone surrogate U+DCE9 (#425),
    is spelled as a name is: `\\udce9` between backticks, as `check` names
    it, and not the bare `caf\\udce9` a stdout that `backslashreplace`s a
    surrogate printed. Skipped where no name can hold the byte."""
    source = make_source_repo(tmp_path / "Thing")
    on_a_branch_that_is_not_utf_8(source)

    done = planned(source, tmp_path / PLAN_FILE,
                   PYTHONIOENCODING="utf-8:strict")

    assert_branch_in_the_line(done, source, "`caf\\udce9`")


# --- in this process: a branch no git can make ------------------------------

def report(adopter, capsys, base: Path, branch: str, cloned: bool = False
           ) -> str:
    """What `_print_plan_report` prints for a source of one commit read at
    `branch`: a real repository with `branch` set on its `Source`, since
    git refuses the name. Nothing else is in the report: no entry, no
    follow-up, no pin."""
    repo = make_source_repo(base / "Thing")
    commit = git("rev-parse", "HEAD", cwd=repo).stdout.strip()
    source = adopter.Source(repo, "testorg/Thing" if cloned else None, branch,
                            commit, cloned=cloned)
    args = Namespace(project="Northwind", id="northwind", org="testorg",
                     tracking_branch="main", allow_empty_leg=[],
                     spec_path="spec", code_path="code")
    adopter._print_plan_report(args, source, [], [], [], [], None)
    return capsys.readouterr().out


@EACH_CONTROL
def test_the_report_spells_a_control_character_in_the_branch(
        adopter, capsys, tmp_path, char, spelled):
    """A carriage return sends the cursor back over the line and hides what
    it said; a line feed splits it; an ESC begins a terminal's escape
    sequence. None of them is printed: the branch is `_spelled`."""
    out = report(adopter, capsys, tmp_path, f"ma{char}in")

    assert f"ma{char}in" not in out, repr(out)
    line = the_source_line(out)
    assert line.isprintable(), repr(line)
    assert f" (`ma{spelled}in`), " in line, line


@EACH_BRANCH_CHARACTER
def test_the_report_spells_the_branch_of_a_clone_too(
        adopter, capsys, tmp_path, char, spelled):
    """A repository `plan` cloned is named by its `owner/repo`, as before,
    and its branch is spelled in the same line."""
    out = report(adopter, capsys, tmp_path, f"ma{char}in", cloned=True)

    assert char not in out, repr(out)
    line = the_source_line(out)
    assert line.startswith(f"{SOURCE}testorg/Thing @ "), line
    assert f" (`ma{spelled}in`), " in line, line
