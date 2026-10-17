# SPDX-License-Identifier: Apache-2.0
"""`plan` asks whether it can write `--out` before it does any work, and says
the plan is written the moment it is (#799: L1-89 and L1-79 of #457).

ON MAIN AT bf1f099b (2026-10-17), probed with a stub `gh` and git 2.43.0:
- L1-89. `plan` built the whole plan and ended at `write_lf(out, ...)`, exit
  1, with a traceback and no `REFUSED` line, for each of: `--out` in a
  folder that is not there (`FileNotFoundError`), `--out` that is a folder
  (`IsADirectoryError`) and `--out` in a folder this user cannot write in
  (`PermissionError`), the default `adoption-plan.yaml` in such a current
  directory included. Each had by then made a work directory and, for an
  `org/repo` source, cloned it.
- L1-79. `plan` writes the plan before `_print_plan_report` reads more of
  the source, so a read that failed there (`git cat-file --batch`, in
  `symlink_targets`) left the plan on disk, exited 2 and never printed
  `plan written to`, the one line that says the file exists.

Now `--out` is asked with the flags, before a work directory or a clone, and
refused as `adopt-out-unwritable`; a write that fails anyway (a race, a full
disk) is the same refusal, and `plan written to` is printed as soon as the
file is.

A folder the run itself makes is not asked for: `--work-dir` is made where it
is missing, and an `--out` at or below it is written there. `chmod` keeps
neither root nor a Windows user from writing, so the tests of a folder or a
file nobody can write skip where it does not.
"""

from __future__ import annotations

import errno
import importlib.util
import os
import shlex
import shutil
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, run_script
from test_adopt_empty_symlinks import NAMED, source_with_links
from test_adopt_plan_leg_path_help import HELP_ENV, option_help, option_lines
from test_adopt_root_symlinks import ticked, unwritable_work  # noqa: F401

CODE = "adopt-out-unwritable"
PLAN_FILE = "adoption-plan.yaml"
WORK_FLAG = "--work-dir"
#: The `--work-dir` the runs here are given: not `work`, which the fixture
#: of a folder nobody can write in is.
RUN_WORK = "run-work"
OUT_FLAG = "--out"
#: A source small enough that `plan` asks no question.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: `plan`'s arguments after `--source <it>`.
PLANNED = ["--project", "Thing", "--org", "testorg", "--elected-by",
           "Test Human", "--elected-on", "2026-09-02"]
#: An `org/repo` `--source`, cloned with `gh`, which the suite's own `gh`
#: refuses and logs.
ORG_REPO = "acme/Atlas"
MINE = "mine\n"
#: The line that says the plan is on disk.
WRITTEN = "plan written to"
#: What every refusal of `--out` says to do, after `no plan was written.`
FIX = ("Pass an --out that names a file in a folder this user can write in, "
       "making the folder first if it is not there.")
#: What the refusal of a write that began, and failed, adds.
CUT_SHORT = (" If the write began, what now lies at that path is cut short "
             "and is not a plan.")


def reason_text(code: int) -> str:
    """What the system says of errno `code`, as the refusal quotes it."""
    return os.strerror(code)


def refusal(out: str, why: str, fix: str = FIX) -> str:
    """The whole of stderr when `plan` refuses `--out out` for `why`."""
    return (f"REFUSED {CODE}: --out {ticked(out)} cannot be written: {why}\n"
            f"Remediation: no plan was written. {fix}\n")


def where(folder: Path) -> str:
    """A folder as the refusal names it: between backticks, as the system
    spells it."""
    return ticked(os.path.realpath(folder))


@pytest.fixture
def source(tmp_path) -> Path:
    return make_source_repo(tmp_path / "Thing", tree=SMALL_TREE, edits=())


def plan_of(given: str, *flags: str, cwd: Path | None = None, env=None):
    """`plan --source given`, with `flags` after `PLANNED`."""
    return run_script(ADOPT, "plan", "--source", given, *PLANNED, *flags,
                      cwd=cwd, env=env)


def refused_before_any_work(tmp_path: Path, gh_guard, source: Path,
                            out: str, expected: str, *,
                            cwd: Path | None = None) -> None:
    """`plan` of a local source, and of an `org/repo` one, refuses `out`
    with `expected` alone on stderr and nothing on stdout, exit 2, no
    traceback, and with a `--work-dir` that is not there before it.

    The work directory is the proof that nothing was started: `_work_root`
    makes a `--work-dir` where it is missing and nothing removes it. The
    `org/repo` source is the other: `Source.open` hands it to `gh repo
    clone`, and the suite's `gh` logs every call it is given (`gh_guard`).
    """
    work = tmp_path / RUN_WORK
    flags = ([OUT_FLAG, out] if out else []) + [WORK_FLAG, str(work)]
    for given in (str(source), ORG_REPO):
        result = plan_of(given, *flags, cwd=cwd)
        assert result.returncode == 2, result.stderr + result.stdout
        assert result.stderr == expected, given
        assert result.stdout == "", given
        assert not work.exists(), f"{given}: a work directory was made"
        assert gh_guard.take() == [], f"{given}: gh was called"


# ---------------------------------------------------------------------------
# L1-89: the three cases, and what falls out of the same question
# ---------------------------------------------------------------------------

def test_an_out_in_a_folder_that_is_not_there_is_refused_first(
        tmp_path, gh_guard, source):
    """`--out <dir>/nope/adoption-plan.yaml` ended in `FileNotFoundError`."""
    out = tmp_path / "nope" / PLAN_FILE
    refused_before_any_work(
        tmp_path, gh_guard, source, str(out),
        refusal(str(out), "the folder it goes in, "
                f"{where(out.parent)}, does not exist"))


def test_an_out_that_is_a_folder_is_refused_first(tmp_path, gh_guard, source):
    """`--out <an existing folder>` ended in `IsADirectoryError`."""
    out = tmp_path / "a-folder"
    out.mkdir()
    refused_before_any_work(
        tmp_path, gh_guard, source, str(out),
        refusal(str(out), "it is a folder, and the plan is one file"))


def test_an_out_in_a_folder_nobody_can_write_in_is_refused_first(
        tmp_path, gh_guard, source, unwritable_work):  # noqa: F811
    """`--out <a folder nobody can write in>/adoption-plan.yaml` ended in
    `PermissionError`."""
    out = unwritable_work / PLAN_FILE
    refused_before_any_work(
        tmp_path, gh_guard, source, str(out),
        refusal(str(out), "a file cannot be made in the folder it goes in, "
                f"{where(unwritable_work)}: making it failed "
                f"({reason_text(errno.EACCES)})"))
    assert not out.exists()


def test_the_default_out_in_a_current_directory_nobody_can_write_in_is_refused(
        tmp_path, gh_guard, source, unwritable_work):  # noqa: F811
    """No `--out` at all: the plan goes to `adoption-plan.yaml` in the
    current directory, which this user cannot write in."""
    refused_before_any_work(
        tmp_path, gh_guard, source, "",
        refusal(PLAN_FILE, "a file cannot be made in the folder it goes in, "
                f"{where(unwritable_work)}: making it failed "
                f"({reason_text(errno.EACCES)})"),
        cwd=unwritable_work)
    assert not (unwritable_work / PLAN_FILE).exists()


def test_an_out_under_a_file_is_refused_first(tmp_path, gh_guard, source):
    """The folder an `--out` goes in is a file, as `--out a-file/plan.yaml`
    has it: not a folder that is missing, and said so."""
    a_file = tmp_path / "a-file"
    a_file.write_text(MINE)
    out = a_file / PLAN_FILE
    refused_before_any_work(
        tmp_path, gh_guard, source, str(out),
        refusal(str(out), f"the folder it goes in, {where(a_file)}, is a "
                "file or lies under one"))
    assert a_file.read_text() == MINE


def test_a_plan_file_nobody_can_write_is_refused_first_and_kept(
        tmp_path, gh_guard, source):
    """An `--out` that is already a file, which it is rewritten in place:
    it must be one this user can write. It is not touched."""
    out = tmp_path / PLAN_FILE
    out.write_text(MINE)
    out.chmod(0o400)
    try:
        if os.access(out, os.W_OK):
            pytest.skip("chmod cannot keep this user from writing a file")
        refused_before_any_work(
            tmp_path, gh_guard, source, str(out),
            refusal(str(out), "the file already there cannot be written "
                    f"({reason_text(errno.EACCES)})"))
        assert out.read_text() == MINE
    finally:
        out.chmod(0o600)


def test_a_folder_that_asks_nothing_of_the_write_is_planned_into(
        tmp_path, source):
    """Control: the same `plan` into a folder that is there, a file in it
    already, and nothing refused: the question leaves no file of its own."""
    out = tmp_path / "there" / PLAN_FILE
    out.parent.mkdir()
    for _ in range(2):
        result = plan_of(str(source), OUT_FLAG, str(out))
        assert result.returncode == 0, result.stderr + result.stdout
    assert sorted(path.name for path in out.parent.iterdir()) == [PLAN_FILE]


# ---------------------------------------------------------------------------
# A folder this run makes is not asked for
# ---------------------------------------------------------------------------

def test_an_out_in_the_work_dir_the_run_makes_is_still_planned_into(
        tmp_path, source):
    """`--work-dir` is made where it is missing, so an `--out` in it, the
    plan kept beside its clones, is written there as it always was."""
    work = tmp_path / RUN_WORK
    out = work / PLAN_FILE
    result = plan_of(str(source), WORK_FLAG, str(work), OUT_FLAG, str(out))
    assert result.returncode == 0, result.stderr + result.stdout
    assert out.is_file()


def test_an_out_in_a_folder_the_work_dir_does_not_make_is_the_backstops(
        tmp_path, source):
    """Only the work directory and the clone are made, so `--out
    <work>/nope/plan.yaml` is not asked for up front, and the write that
    cannot be made is refused by the backstop, with no traceback."""
    work = tmp_path / RUN_WORK
    out = work / "nope" / PLAN_FILE
    result = plan_of(str(source), WORK_FLAG, str(work), OUT_FLAG, str(out))
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr == refusal(
        str(out), f"writing it failed ({reason_text(errno.ENOENT)})",
        FIX + CUT_SHORT)


# ---------------------------------------------------------------------------
# The backstop: a write that fails after the question was answered
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_plan_out", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_folder_that_goes_after_the_question_is_the_same_refusal(
        adopter, monkeypatch, capsys, tmp_path, source):
    """A race: the folder was there when `--out` was asked, and is gone
    when the plan is written. In this process, so that the write itself is
    the thing that fails."""
    out = tmp_path / "soon-gone" / PLAN_FILE
    out.parent.mkdir()

    def gone(path, _text):
        out.parent.rmdir()
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                str(path))

    monkeypatch.setattr(adopter, "write_lf", gone)
    capsys.readouterr()
    code = adopter.main(["plan", "--source", str(source), *PLANNED,
                         OUT_FLAG, str(out)])
    said = capsys.readouterr()
    assert code == 2, said.err + said.out
    assert said.err == refusal(
        str(out), f"writing it failed ({reason_text(errno.ENOENT)})",
        FIX + CUT_SHORT)
    assert WRITTEN not in said.out


@pytest.mark.skipif(not os.path.exists("/dev/full"),
                    reason="this machine has no /dev/full")
def test_a_full_disk_is_the_same_refusal_and_no_traceback(source):
    """`/dev/full` accepts the open and refuses every byte: no space left.
    It is a file that can be written, as far as the question can tell."""
    result = plan_of(str(source), OUT_FLAG, "/dev/full")
    assert result.returncode == 2, result.stderr + result.stdout
    assert "Traceback" not in result.stderr
    assert result.stderr == refusal(
        "/dev/full", f"writing it failed ({reason_text(errno.ENOSPC)})",
        FIX + CUT_SHORT)
    assert WRITTEN not in result.stdout


# ---------------------------------------------------------------------------
# L1-79: `plan written to` as soon as the plan is
# ---------------------------------------------------------------------------

def a_git_that_cannot_read_a_symlink_target(directory: Path) -> dict:
    """A `git` that fails `cat-file --batch`, the read `symlink_targets`
    makes after the plan is written, and runs every other command as git
    does: the environment that puts it first on PATH."""
    directory.mkdir()
    script = directory / "git"
    script.write_text(
        "#!/bin/sh\n"
        'for argument in "$@"; do\n'
        '  if [ "$argument" = "--batch" ]; then\n'
        '    echo "fatal: no object can be read" >&2\n'
        "    exit 128\n"
        "  fi\n"
        "done\n"
        f'exec {shlex.quote(shutil.which("git"))} "$@"\n')
    script.chmod(0o755)
    return {"PATH": str(directory) + os.pathsep + os.environ["PATH"]}


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a `git` that is a shell script runs on POSIX only")
def test_plan_written_to_is_printed_though_a_later_read_fails(tmp_path):
    """The plan is on disk, `symlink_targets` cannot read the link's target,
    and the run still exits 2 as it did: the one line that says the plan
    exists is now printed before that read, where it was printed after."""
    source = source_with_links(tmp_path, "docs/link", target=NAMED)
    out = tmp_path / PLAN_FILE
    env = a_git_that_cannot_read_a_symlink_target(tmp_path / "bin")
    result = plan_of(str(source), OUT_FLAG, str(out), env=env)
    assert result.returncode == 2, result.stderr + result.stdout
    assert out.is_file()
    assert f"\n{WRITTEN} {out}\n" in result.stdout, result.stdout
    assert result.stderr.startswith("REFUSED git-failed: `git cat-file "
                                    "--batch` in "), result.stderr


def test_a_run_that_reads_fine_says_it_once_before_the_report(tmp_path,
                                                              source):
    out = tmp_path / PLAN_FILE
    result = plan_of(str(source), OUT_FLAG, str(out))
    assert result.returncode == 0, result.stderr + result.stdout
    said = result.stdout
    assert said.count(WRITTEN) == 1, said
    assert said.index(f"{WRITTEN} {out}") < said.index("source     "), said
    assert said.index("source     ") < said.index("follow-ups ("), said


# ---------------------------------------------------------------------------
# What `--help` says
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def plan_help() -> str:
    result = run_script(ADOPT, "plan", "--help", env=HELP_ENV)
    assert result.returncode == 0, result.stderr + result.stdout
    return result.stdout


def test_the_help_says_where_the_plan_goes_and_what_is_refused(plan_help):
    said = option_help(plan_help, OUT_FLAG)
    for words in (PLAN_FILE, "current directory", "a folder that is there",
                  "this user can write in", f"`{CODE}`",
                  "before the source is read or cloned"):
        assert words in said, f"`plan --help` says no {words} of --out"


def test_the_code_sits_whole_on_one_line_of_the_help(plan_help):
    """`docs/cli.md` is grepped for the code a tool prints, and at 80
    columns `textwrap` breaks a hyphenated word at a line end."""
    lines = option_lines(plan_help, OUT_FLAG)
    assert any(f"`{CODE}`" in line for line in lines), "\n".join(lines)
