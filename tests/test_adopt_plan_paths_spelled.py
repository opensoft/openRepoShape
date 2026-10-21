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

THE TEST SOURCE IS ASCII: every character that is not printable is written as
an escape.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import (ADOPT, make_source_repo, run_script,
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


def plan_of_a_local_source(tmp_path: Path,
                           out: Path | str) -> subprocess.CompletedProcess:
    """`plan` over a repository on disk, which it reads in place, writing
    `out` as it is typed."""
    source = make_source_repo(tmp_path / PROJECT, tree=TREE, edits=())
    return run_script(ADOPT, *plan_arguments(str(source), out),
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
