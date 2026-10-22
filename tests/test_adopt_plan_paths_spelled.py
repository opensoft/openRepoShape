# SPDX-License-Identifier: Apache-2.0
"""`plan` names the two paths the caller typed, `--out` and `--work-dir`, as
every other path in its report is named (#1115, and #1120's N4).

`plan written to {out}` printed the typed `--out` as it was. A path holding
U+202E (a bidi override), U+2066 (a bidi isolate), a line feed or a tab
reached the terminal unspelled: the two bidi controls reverse or isolate what
is printed after them, a line feed splits the line in two, and a tab pads it.
`cloning {repository} (read only) into {path}` did the same with `--work-dir`,
for an `org/repo` source, and `Source.clone` prints that line for `plan`,
`check` and `execute` alike. The `source` line, the table and the follow-ups
already name such a path with `_shown` (#199, #900): as it is when every
character in it is printable, and otherwise between two backticks, each
character as the plan's own `path:` writes it.

NO NETWORK AND NO GITHUB. `plan` is run as a child, as a person runs it. The
`--out` rows read a local source. The `--work-dir` rows name `testorg/Thing`,
which a `gh` stand-in first on PATH refuses to clone: the line is printed
before `gh` runs, so the refusal changes nothing it says. The stand-in is a
`#!` script, and no Windows file name holds a line feed or a tab, so the
module is POSIX only.

`_shown`'s rule is held from both ends (#1167, from #1154's review). A
printable path is named as it was typed, a non-ASCII one too (U+00E9), and a
relative `--out` as `Path` reads it, which drops a leading `./`. A printable
`--out` that ends in a space, or that begins and ends with a backtick, is
spelled all the same (#900). A `--work-dir` that is not UTF-8 is spelled, and
no raw byte reaches stdout. `check` and `execute` say the `cloning` line
`plan` says, and each is run here: `execute` keeps the clone it makes and
hands `Source.clone` no list of them, where `plan` and `check` do.

THE TEST SOURCE IS ASCII: every character that is not printable is written as
an escape.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, NOT_UTF_8_PROBE, make_source_repo, run_script,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_the_environment_cannot_carry)

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="the `gh` stand-in is a `#!` script, and a Windows file name "
           "holds no line feed or tab")

ORG = "testorg"
PROJECT = "Thing"
REPOSITORY = f"{ORG}/{PROJECT}"
SOURCE_READONLY = "source-readonly"
TREE = {"README.md": "# Thing\n", "src/main.py": "x = 1\n"}
#: `plan` refuses a clone of `gh` that fails, as this.
UNCLONABLE = "REFUSED source-unclonable: "

#: Each character a terminal does not show as itself, and how `_shown` writes
#: it: the escape `repo_shape.double_quoted` writes for it in the plan.
CHARACTERS = [
    pytest.param("\u202e", "\\u202e", id="bidi-override-U+202E"),
    pytest.param("\u2066", "\\u2066", id="bidi-isolate-U+2066"),
    pytest.param("\n", "\\n", id="line-feed"),
    pytest.param("\t", "\\t", id="tab"),
    pytest.param("\u202e\u2066\n\t", "\\u202e\\u2066\\n\\t", id="all-four"),
    pytest.param("\x1b", "\\x1b", id="escape"),
    pytest.param("\r", "\\r", id="carriage-return"),
]


def lines_starting(stdout: str, start: str) -> list[str]:
    """The lines of `stdout` that begin with `start`, as a terminal breaks
    them: at each line feed, so a name that holds one is two lines."""
    return [line for line in stdout.split("\n") if line.startswith(start)]


def plan_arguments(source: str, out: Path | str, *extra: str) -> list[str]:
    """`plan --source <source>` for the project `testorg/Thing`, writing
    `out`."""
    return ["plan", "--source", source, "--project", PROJECT, "--org", ORG,
            "--elected-by", "Test Human", "--elected-on", "2026-09-02",
            "--out", str(out), *extra]


def plan_of_a_local_source(tmp_path: Path, out: Path | str,
                           cwd: Path | None = None
                           ) -> subprocess.CompletedProcess:
    """`plan` over a repository on disk, which it reads in place, writing
    `out` as it is typed, run in `cwd` where that is given: a relative `out`
    is written there."""
    source = make_source_repo(tmp_path / PROJECT, tree=TREE, edits=())
    return run_script(ADOPT, *plan_arguments(str(source), out), cwd=cwd,
                      env={"PYTHONIOENCODING": "utf-8"})


def a_gh_that_refuses(base: Path) -> dict:
    """The environment that puts a `gh` first on PATH that refuses every
    call, and writes its arguments, one to a line, to `base/gh.log`: the
    clone `plan` asks for is never made."""
    binary = base / "bin"
    binary.mkdir()
    script = binary / "gh"
    script.write_bytes(b"#!/bin/sh\n"
                       b"printf '%s\\n' \"$@\" >> \"$GH_STUB_LOG\"\n"
                       b"echo 'stub gh: refusing' >&2\n"
                       b"exit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {"PATH": f"{binary}{os.pathsep}{os.environ.get('PATH', '')}",
            "GH_STUB_LOG": str(base / "gh.log"),
            "PYTHONIOENCODING": "utf-8"}


def plan_of_a_repository_on_github(tmp_path: Path,
                                   work: Path) -> subprocess.CompletedProcess:
    """`plan --source testorg/Thing --work-dir <work>`: the work directory is
    made, the `cloning` line is said, and the stand-in `gh` refuses."""
    stand_in = a_gh_that_refuses(tmp_path)
    return run_script(
        ADOPT, *plan_arguments(REPOSITORY, tmp_path / "plan.yaml",
                               "--work-dir", str(work)), env=stand_in)


def where_the_clone_goes(work: Path) -> str:
    """The path `Source.clone` clones into: the work directory as
    `os.path.realpath` reads it, then `source-readonly/<repo>`."""
    return f"{os.path.realpath(work)}/{SOURCE_READONLY}/{PROJECT}"


# --- `--out`: `plan written to` ----------------------------------------------

@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_plan_written_to_spells_an_out_path_a_terminal_would_not_show(
        tmp_path, typed, spelled):
    """On main the line was `plan written to <the path as typed>`: the bidi
    controls reached the terminal, and a line feed or a tab broke the line.
    Now it is the one line `_shown` writes, between backticks."""
    skip_where_the_environment_cannot_carry(typed)
    out = tmp_path / f"pl{typed}an.yaml"
    result = plan_of_a_local_source(tmp_path, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.is_file(), "the plan was not written where --out named"
    expected = f"plan written to `{os.fspath(tmp_path)}/pl{spelled}an.yaml`"
    assert lines_starting(result.stdout, "plan written to") == [expected], \
        result.stdout


@pytest.mark.parametrize("typed", ["\u202e", "\u2066"])
def test_the_out_path_reaches_no_bidi_control_unspelled(tmp_path, typed):
    """The same rows from the other side: whatever else the report prints,
    none of it holds the control, which would turn the line around."""
    skip_where_the_environment_cannot_carry(typed)
    result = plan_of_a_local_source(tmp_path, tmp_path / f"pl{typed}an.yaml")
    assert result.returncode == 0, result.stdout + result.stderr
    assert typed not in result.stdout, result.stdout


def test_a_plain_out_path_is_named_exactly_as_it_was(tmp_path):
    """The control, which passes on main as well: a path whose every
    character is printable is not respelled and not wrapped in backticks."""
    out = tmp_path / "adoption-plan.yaml"
    result = plan_of_a_local_source(tmp_path, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert lines_starting(result.stdout, "plan written to") == [
        f"plan written to {os.fspath(out)}"], result.stdout


def test_an_out_path_typed_with_a_dot_segment_is_named_as_it_always_was(
        tmp_path):
    """Also the control: `plan` names the path as `Path` reads it, so
    `<dir>/./adoption-plan.yaml` is named `<dir>/adoption-plan.yaml`. What
    `_shown` spells is that path, and not the text that was typed."""
    out = tmp_path / "adoption-plan.yaml"
    result = plan_of_a_local_source(
        tmp_path, f"{os.fspath(tmp_path)}{os.sep}.{os.sep}{out.name}")
    assert result.returncode == 0, result.stdout + result.stderr
    assert lines_starting(result.stdout, "plan written to") == [
        f"plan written to {os.fspath(out)}"], result.stdout


def test_a_printable_non_ascii_out_path_is_named_as_it_was_typed(tmp_path):
    """A character that is not ASCII is not one a terminal does not show:
    `pl<U+00E9>an.yaml` is printable, so `_shown` returns it as it is, with
    no backticks and no escape. A spelling of every non-ASCII path passes the
    rows above, and fails here."""
    typed = "\u00e9"
    skip_where_the_environment_cannot_carry(typed)
    out = tmp_path / f"pl{typed}an.yaml"
    result = plan_of_a_local_source(tmp_path, out)
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.is_file(), "the plan was not written where --out named"
    assert lines_starting(result.stdout, "plan written to") == [
        f"plan written to {os.fspath(out)}"], result.stdout


@pytest.mark.parametrize("typed", ["plan.yaml", "./plan.yaml"])
def test_a_relative_out_path_is_named_as_it_was_typed(tmp_path, typed):
    """`plan` names the path as `Path` reads it: `plan.yaml` is `plan.yaml`
    and `./plan.yaml` is too, and neither is made absolute. Run in `tmp_path`,
    so the plan is written there. The dot-segment row above types an absolute
    path, which an `os.path.abspath` would not change."""
    result = plan_of_a_local_source(tmp_path, typed, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / "plan.yaml").is_file(), \
        "the plan was not written where --out named"
    assert lines_starting(result.stdout, "plan written to") == [
        "plan written to plan.yaml"], result.stdout


@pytest.mark.parametrize("typed, spelled", [
    pytest.param("plan.yaml ", "`plan.yaml `", id="trailing-space"),
    pytest.param("`plan.yaml`", "`\\x60plan.yaml\\x60`",
                 id="begins-and-ends-with-a-backtick"),
])
def test_a_printable_out_path_that_reads_as_another_is_spelled(
        tmp_path, typed, spelled):
    """`_shown`'s rule from #900, which `isprintable()` alone is not: a path
    that ends in a space reads as the one without it, and one that begins and
    ends with a backtick reads as the spelling of the path between them. Both
    are printable, and both are spelled. Each is a relative path, run in
    `tmp_path`. A `--work-dir` cannot reach either case: the path the clone
    line prints ends in `source-readonly/<repo>` and begins with a slash."""
    result = plan_of_a_local_source(tmp_path, typed, cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (tmp_path / typed).is_file(), \
        "the plan was not written where --out named"
    assert lines_starting(result.stdout, "plan written to") == [
        f"plan written to {spelled}"], result.stdout


# --- `--work-dir`: `cloning <repository> (read only) into` -------------------

@pytest.mark.parametrize("typed, spelled", CHARACTERS)
def test_cloning_spells_a_work_dir_a_terminal_would_not_show(tmp_path, typed,
                                                             spelled):
    """On main the line was `cloning testorg/Thing (read only) into <the
    path as typed>`, for an `org/repo` source only: a local source is read in
    place and clones nothing. Now it is the one line `_shown` writes."""
    skip_where_the_environment_cannot_carry(typed)
    work = tmp_path / f"wd{typed}k"
    result = plan_of_a_repository_on_github(tmp_path, work)
    assert result.returncode == 2, result.stdout + result.stderr
    assert UNCLONABLE in result.stderr, result.stdout + result.stderr
    base = os.path.realpath(tmp_path)
    expected = (f"cloning {REPOSITORY} (read only) into "
                f"`{base}/wd{spelled}k/{SOURCE_READONLY}/{PROJECT}`")
    assert lines_starting(result.stdout, "cloning ") == [expected], \
        result.stdout


@pytest.mark.parametrize("typed", ["\u202e", "\u2066"])
def test_the_work_dir_reaches_no_bidi_control_unspelled(tmp_path, typed):
    """The same rows from the other side, as for `--out`."""
    skip_where_the_environment_cannot_carry(typed)
    result = plan_of_a_repository_on_github(tmp_path,
                                            tmp_path / f"wd{typed}k")
    assert result.returncode == 2, result.stdout + result.stderr
    assert typed not in result.stdout, result.stdout


def test_a_plain_work_dir_is_named_exactly_as_it_was(tmp_path):
    """The control, which passes on main as well, and which holds that the
    stand-in `gh` ran: it was asked to clone the one repository."""
    work = tmp_path / "work"
    result = plan_of_a_repository_on_github(tmp_path, work)
    assert result.returncode == 2, result.stdout + result.stderr
    assert lines_starting(result.stdout, "cloning ") == [
        f"cloning {REPOSITORY} (read only) into {where_the_clone_goes(work)}"
    ], result.stdout
    log = (tmp_path / "gh.log").read_text(encoding="utf-8").splitlines()
    assert log[:3] == ["repo", "clone", REPOSITORY], log


def test_a_printable_non_ascii_work_dir_is_named_as_it_was_typed(tmp_path):
    """The same control as for `--out`: `wd<U+00E9>k` is printable, so the
    line names it as it is, with no backticks and no escape."""
    typed = "\u00e9"
    skip_where_the_environment_cannot_carry(typed)
    work = tmp_path / f"wd{typed}k"
    result = plan_of_a_repository_on_github(tmp_path, work)
    assert result.returncode == 2, result.stdout + result.stderr
    assert UNCLONABLE in result.stderr, result.stdout + result.stderr
    assert lines_starting(result.stdout, "cloning ") == [
        f"cloning {REPOSITORY} (read only) into {where_the_clone_goes(work)}"
    ], result.stdout


def plan_of_a_repository_on_github_as_bytes(
        tmp_path: Path, work: Path) -> tuple[int, bytes, bytes]:
    """`(exit, stdout, stderr)` of `plan --source testorg/Thing --work-dir
    <work>` with the stand-in `gh` that refuses, and a `surrogateescape`
    stdout: the bytes the child wrote. `run_script` decodes them in the
    parent's own locale, which a raw byte that is not UTF-8 fails."""
    environment = {**os.environ, "LANES_LANE": "",
                   **a_gh_that_refuses(tmp_path),
                   "PYTHONIOENCODING": "utf-8:surrogateescape"}
    arguments = plan_arguments(REPOSITORY, tmp_path / "plan.yaml",
                               "--work-dir", str(work))
    proc = subprocess.run([sys.executable, str(ADOPT), *arguments],
                          capture_output=True, env=environment,
                          stdin=subprocess.DEVNULL, check=False)
    return proc.returncode, proc.stdout, proc.stderr


def test_a_work_dir_that_is_not_utf8_is_spelled_and_no_raw_byte_is_written(
        tmp_path):
    """`--work-dir` holding the byte 0xff, which is not UTF-8: Python reads
    it in as U+DCFF, which a `surrogateescape` stdout writes back as the raw
    byte. The line is the one `_shown` writes, `\\udcff` between backticks, and
    no raw byte reaches stdout. The `--out` row of `test_stdout_encoding.py`
    holds the same for `plan written to`."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    work = tmp_path / f"wd{NOT_UTF_8_PROBE}k"
    code, stdout, stderr = plan_of_a_repository_on_github_as_bytes(
        tmp_path, work)
    assert code == 2 and b"Traceback" not in stderr, stdout + stderr
    assert UNCLONABLE.encode() in stderr, stdout + stderr
    clone = f"{os.path.realpath(tmp_path)}/wd\\udcffk/{SOURCE_READONLY}"
    assert [line for line in stdout.split(b"\n")
            if line.startswith(b"cloning ")] == [
        f"cloning {REPOSITORY} (read only) into `{clone}/{PROJECT}`".encode()
    ], stdout
    assert b"\xff" not in stdout, stdout


# --- both at once ------------------------------------------------------------

def a_gh_that_clones(base: Path, origin: Path) -> dict:
    """The environment that puts a `gh` first on PATH that makes the one
    clone `plan` asks for: `gh repo clone <repository> <directory> --
    --quiet` is a `git clone` of `origin`, its own `origin` then set to the
    GitHub url, as `gh` leaves it. Any other call is refused."""
    binary = base / "bin"
    binary.mkdir()
    script = binary / "gh"
    script.write_bytes(
        b"#!/bin/sh\n"
        b"if [ \"$1 $2\" = \"repo clone\" ]; then\n"
        b"  git clone -q --no-local \"$STUB_ORIGIN\" \"$4\" || exit 1\n"
        b"  exec git -C \"$4\" remote set-url origin "
        b"\"https://github.com/$3.git\"\n"
        b"fi\n"
        b"echo 'stub gh: refusing' >&2\n"
        b"exit 1\n")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return {"PATH": f"{binary}{os.pathsep}{os.environ.get('PATH', '')}",
            "STUB_ORIGIN": str(origin), "PYTHONIOENCODING": "utf-8"}


def test_each_of_the_two_paths_is_spelled_in_one_run(tmp_path):
    """`--out` and `--work-dir` typed with the same control in one run that
    clones and writes its plan: both lines are said, and both are spelled, so
    a spelling given to one flag and not the other fails here whichever it
    is."""
    typed = "\u202e"
    skip_where_the_environment_cannot_carry(typed)
    origin = make_source_repo(tmp_path / "github" / PROJECT, tree=TREE,
                              edits=())
    out = tmp_path / f"pl{typed}an.yaml"
    work = tmp_path / f"wd{typed}k"
    result = run_script(
        ADOPT, *plan_arguments(REPOSITORY, out, "--work-dir", str(work)),
        env=a_gh_that_clones(tmp_path, origin))
    assert result.returncode == 0, result.stdout + result.stderr
    assert out.is_file(), result.stdout
    base = os.path.realpath(tmp_path)
    assert lines_starting(result.stdout, "cloning ") == [
        f"cloning {REPOSITORY} (read only) into "
        f"`{base}/wd\\u202ek/{SOURCE_READONLY}/{PROJECT}`"], result.stdout
    assert lines_starting(result.stdout, "plan written to") == [
        f"plan written to `{os.fspath(tmp_path)}/pl\\u202ean.yaml`"
    ], result.stdout
    assert typed not in result.stdout, result.stdout


# --- `check` and `execute` say the same line ---------------------------------

def a_command_on_github(tmp_path: Path, command: str,
                        work: Path) -> subprocess.CompletedProcess:
    """`check` or `execute` over the plan `plan` wrote from a local source,
    handed `--source testorg/Thing --work-dir <work>`: the work directory is
    made, the `cloning` line is said, and the stand-in `gh` refuses."""
    plan = tmp_path / "plan.yaml"
    planned = plan_of_a_local_source(tmp_path, plan)
    assert planned.returncode == 0, planned.stdout + planned.stderr
    return run_script(ADOPT, command, "--plan", str(plan), "--source",
                      REPOSITORY, "--work-dir", str(work),
                      env=a_gh_that_refuses(tmp_path))


@pytest.mark.parametrize("command", ["check", "execute"])
def test_check_and_execute_spell_the_work_dir_as_plan_does(tmp_path, command):
    """`Source.clone` prints the `cloning` line for `plan`, `check` and
    `execute` alike. `plan` and `check` hand it a list of the clones they
    made, and `execute` none, as it keeps its clone: a spelling that holds
    only where the caller keeps that list leaves `execute` printing the
    U+202E as it was typed, which the `execute` row catches and `check`'s
    does not."""
    typed, spelled = "\u202e", "\\u202e"
    skip_where_the_environment_cannot_carry(typed)
    result = a_command_on_github(tmp_path, command,
                                 tmp_path / f"wd{typed}k")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED source-unclonable" in result.stderr, \
        result.stdout + result.stderr
    base = os.path.realpath(tmp_path)
    assert lines_starting(result.stdout, "cloning ") == [
        f"cloning {REPOSITORY} (read only) into "
        f"`{base}/wd{spelled}k/{SOURCE_READONLY}/{PROJECT}`"], result.stdout
    assert typed not in result.stdout, result.stdout
