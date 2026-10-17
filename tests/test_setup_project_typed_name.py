# SPDX-License-Identifier: Apache-2.0
"""The project name typed at `setup-project.py`'s prompt (#729).

A name that arrives as `--project` or as the positional is checked at parse
time, before step (1) prints, by `checked_value`. A name typed at the
`project name` prompt reached step (3) unchecked: `..` left `--into`, an
absolute name replaced it, `--help` made the naming validator print its help
and exit 0 at step (4) (the run itself ended at step (5), with the scaffold's
usage and exit 2), and the refusals that did come named an `--id` nobody passed
or dumped the usage text. These tests type each of those at a real terminal and
hold the run to the `--project` refusal, worded for what the person did: the
value is a `project name`.

Two things pin WHERE the check sits, not only that it is made. Nothing of step
(3) may print (`[ok] project`, `[ok] legs`), and a FILE stands where the folder
above `--into` goes, so a check made after step (3) has asked the disk would
say "is a file" and not `project name is`.

POSIX only, as every test that gives a run a terminal is (`PTY_SKIP`).
"""

from __future__ import annotations

import sys

import pytest

from conftest import PTY_SKIP, REPO, run_in_a_terminal
from test_setup_project_py import (SETUP_PROJECT, SETUP_SH, piped, run_entry,
                                   terminal_env)

PROMPT = "project name (ONE CamelCase token, e.g. Atlas): "

#: Step (4)'s heading, which no refused name may reach.
NAMING_POLICY = "(4) naming policy"

#: A file where the folder above `--into` goes, so any step that asks the
#: disk about the clone path refuses with "is a file".
FILE_ABOVE_INTO = b"a file where the folder above --into goes\n"

#: What a terminal in canonical mode takes as "the next character is text":
#: ^V, which is how a control character is typed into a line.
LNEXT = chr(0x16)
BELL = chr(7)

#: Names the check refuses, by case. `absolute` is a path under `tmp_path`,
#: so it is built by `typed_value`.
REFUSED = {
    "up-and-out": "../x",
    "slash": "a/b",
    "dot-dot": "..",
    "dot": ".",
    "dash": "-x",
    "help": "--help",
    "control": "a" + BELL + "b",
    "long": "x" * 256,
    "blank": "   ",
    "absolute": None,
}

#: Names step (4)'s policy rules on, as it did before: `NAME_RE` is
#: permissive on purpose.
LEFT_TO_STEP_FOUR = ("Bad_Name", "a b")


def typed_value(tmp_path, case):
    value = REFUSED[case]
    return str(tmp_path / "elsewhere" / "Name") if value is None else value


def at_the_prompt(tmp_path, typed, entry="py", seeded=False):
    """Setup, with no project, asked at a terminal and answered `typed`
    (`"EOF"` is Ctrl-D). `entry` is the file run directly, that file with
    its stdin a pipe (the terminal is then the controlling one), or
    `setup.sh`. `seeded` puts `FILE_ABOVE_INTO` where a later step would
    refuse it. Returns the exit status and the screen."""
    if seeded:
        (tmp_path / "parent").write_bytes(FILE_ABOVE_INTO)
    flags = ["--org", "demoorg", "--local-remote-dir",
             str(tmp_path / "remotes"), "--into",
             str(tmp_path / "parent" / "into")]
    argv = {"py": [sys.executable, str(SETUP_PROJECT), *flags],
            "sh": ["bash", str(SETUP_SH), *flags],
            "piped": piped("", *flags)}[entry]
    if typed != "EOF":
        typed = typed.replace(BELL, LNEXT + BELL) + "\n"
    status, screen, answered = run_in_a_terminal(
        argv, cwd=REPO, env=terminal_env(), answers=[typed], prompt=PROMPT,
        timeout=60)
    assert answered == 1, f"it never asked for a project name:\n{screen}"
    assert "(3) project" in screen, screen
    return status, screen


def the_refusal(text):
    return text[text.index("REFUSED: "):].strip()


def assert_nothing_was_made(tmp_path):
    """Only the seeded file is on the disk, and it is as it was."""
    assert sorted(p.name for p in tmp_path.iterdir()) == ["parent"]
    assert (tmp_path / "parent").read_bytes() == FILE_ABOVE_INTO


def assert_refused_at_the_prompt(tmp_path, value, entry="py"):
    status, screen = at_the_prompt(tmp_path, value, entry, seeded=True)
    assert status == 2, f"status {status}:\n{screen}"
    assert f"project name is {ascii(value)}, which is not a value" in screen
    assert "is a file" not in screen, screen
    assert "[ok] project" not in screen, screen
    assert "[ok] legs" not in screen, screen
    assert NAMING_POLICY not in screen, screen
    assert "usage: setup-project.py" not in screen, screen
    assert "--id" not in screen, screen
    assert_nothing_was_made(tmp_path)
    return screen


@PTY_SKIP
@pytest.mark.parametrize("case", REFUSED)
def test_a_typed_project_name_is_refused_as_the_flag_refuses_it(tmp_path,
                                                                case):
    value = typed_value(tmp_path, case)
    screen = assert_refused_at_the_prompt(tmp_path, value)
    flagged = run_entry("--project", value, "--org", "demoorg",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--into", str(tmp_path / "parent" / "into"))
    assert flagged.returncode == 2, flagged.stderr
    assert the_refusal(screen) == the_refusal(flagged.stderr).replace(
        "REFUSED: --project is", "REFUSED: project name is", 1)


@PTY_SKIP
@pytest.mark.parametrize("entry", ["piped", "sh"])
def test_a_typed_project_name_is_refused_on_every_way_in(tmp_path, entry):
    """The same check on the one-liner's shape (stdin a pipe, the answer
    read from the terminal) and through `setup.sh`, the shim."""
    assert_refused_at_the_prompt(tmp_path, "../x", entry)


@PTY_SKIP
@pytest.mark.parametrize("entry", ["py", "piped", "sh"])
@pytest.mark.parametrize("typed", ["", "EOF"])
def test_an_empty_answer_is_refused_as_no_name_not_as_no_terminal(
        tmp_path, typed, entry):
    status, screen = at_the_prompt(tmp_path, typed, entry, seeded=True)
    assert status == 2, f"status {status}:\n{screen}"
    assert the_refusal(screen) == (
        "REFUSED: no project name was typed; nothing was created.")
    assert "is a file" not in screen, screen
    assert "no terminal" not in screen, screen
    assert "usage: setup-project.py" not in screen, screen
    assert NAMING_POLICY not in screen, screen
    assert_nothing_was_made(tmp_path)


@PTY_SKIP
@pytest.mark.parametrize("value", LEFT_TO_STEP_FOUR)
def test_a_name_the_policy_decides_is_left_to_step_four(tmp_path, value):
    status, screen = at_the_prompt(tmp_path, value)
    assert NAMING_POLICY in screen, screen
    assert "project name is" not in screen, screen
    assert status == 1, f"status {status}:\n{screen}"
