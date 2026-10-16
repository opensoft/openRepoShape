# SPDX-License-Identifier: Apache-2.0
"""A `.github/workflows/` DIRECTORY that this user cannot list or search is
REFUSED BY NAME, not a traceback (#434).

`tests/test_validate_pins_unreadable_workflow.py` (#359) covers a workflow
FILE the operating system will not open: `workflow-unreadable`, exit 2. The
same function, `_workflow_refs` in `scripts/validate-pins.py`, asked about the
DIRECTORY with three calls that had no handler: `workflows.is_dir()`,
`workflows.iterdir()` and `path.is_file()` on each child. `main()` catches
`Refusal` alone, so a directory this user could not list, or could list and
not search, or could not reach because `.github/` could not be searched, ended
the run in a `PermissionError` traceback, exit 1, which is the code this
validator uses for a FINDING. Now each is a `workflow-unreadable` refusal,
exit 2, naming the path and the operating system's own reason, whose remedy
is to restore read and search access and run the same command again.

THE ISSUE'S TABLE, one row per mode, run as the validator a real scaffold
wrote over a committed tree:

| mode                                   | what refuses                      |
|----------------------------------------|-----------------------------------|
| `.github/workflows/` 000               | `iterdir`: the directory          |
| `.github/workflows/` r-- (no search)   | `stat` of each `.yml`: each file  |
| `.github/` r-- (`workflows/` unreached)| `stat` of the directory           |
| `.github/workflows/` 755 (control)     | nothing: `pins ok`                |

THE MODE TESTS SKIP ON WINDOWS AND AS ROOT (a mode-000 directory is listed by
root, and Windows modes do not refuse a listing); the rest run everywhere. The
in-process tests at the end stand in for Python 3.14's answer to a refused
`stat`, and for a listing that fails for a reason that is no permission, so a
tool that leans on `is_dir` or `is_file` raising fails on every Python, root
included. Up to 3.13 those two raised a refused `stat`; from 3.14 they answer
False to ANY `OSError`, which would read an unsearchable `.github/` as "no
workflows" and every file of a listable-but-unsearchable directory as "not a
file": `pins ok` over workflows nobody read.

Every mode is put back in a `finally`, so the temporary directory can be
removed. NOTHING HERE REACHES A NETWORK: the scaffold uses
`--local-remote-dir` and no case asks for a neutral-product pin.
"""

from __future__ import annotations

import contextlib
import errno
import json
import os
import stat
from pathlib import Path

import pytest

from conftest import git, rmtree, run_script
from test_validate_pins_unreadable_workflow import (
    CANNOT_RUN_AS_ROOT, DOCTOR, WORKFLOWS, commit_bytes, leg_workflow,
    refusal_lines, validate,
)
# `refused_stat` is the stand-in `tests/test_bump_leg_unopenable.py` (#383)
# makes for Python 3.14's answer to a refused `stat`: the same four patches,
# and a second copy of it is what SonarCloud's duplication gate counted.
from test_bump_leg_unopenable import refused_stat
# A fixture is used by being named in this module's namespace, which is what
# this import is for: the project's own `validate-pins.py`, loaded as a module.
from test_validate_pins_without_git import validator  # noqa: F401

#: The directory as the refusal names it: relative to the root, POSIX, no
#: trailing slash, the spelling a reader pastes into `ls -ld`.
DIRECTORY = WORKFLOWS

#: What the refusal says about every directory, in full: what this validator
#: reads and why it never skips, then the cause's own advice, then the retry.
REASON_ADVICE = (
    "Remediation: this validator reads every `.yml` and `.yaml` file under "
    ".github/workflows/, whether or not it names a leg, and neither skips one "
    "nor reads one lossily: a workflow it skipped could hide a `@<sha>` "
    "reference that is out of lockstep, which is what it exists to find, and "
    "a directory it cannot list is one whose workflows it cannot read. ")
PERMISSION_ADVICE = (
    "Restore read and search access to .github/workflows/ and to every "
    "directory above it inside the root (`chmod u+rx` on each, or fix who "
    "owns them). Then run the same command again.")
OTHER_ADVICE = (
    "Where the operating system gave another reason, put a directory this "
    "user can list back in its place, and make sure nothing is changing it "
    "while this runs. Then run the same command again.")

#: The refusal for a file in a directory this user can list and not search.
FILE_ADVICE = (
    "A `cannot be read` file is not an encoding failure: this user cannot "
    "open it, so restore read access to it, and search access to every "
    "directory above it inside the root (a file in a directory this user can "
    "list but not search cannot be opened). ")


@contextlib.contextmanager
def mode_of(root: Path, relative: str, mode: int):
    """Set `relative`'s mode, run, and put it back in a `finally`, so the
    temporary directory can be removed whatever the run did."""
    path = root / relative
    saved = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode)
    try:
        yield
    finally:
        path.chmod(saved)


def tree_bytes(root: Path) -> dict[str, bytes]:
    """Every file under the root outside `.git` and the bytecode Python writes
    beside any script that imports a module (`scripts/__pycache__/`), by
    relative POSIX path: what a run that writes nothing leaves as it found
    it."""
    return {rel.as_posix(): path.read_bytes()
            for path in sorted(root.rglob("*"))
            if path.is_file()
            for rel in [path.relative_to(root)]
            if rel.parts[0] != ".git" and "__pycache__" not in rel.parts}


def assert_refused_the_directory(result, root, advice: str) -> None:
    """ONE `workflow-unreadable` refusal, exit 2, whose first line names the
    directory as unlistable with the system's reason and whose remedy is the
    fixed text; no traceback, no Python error name, no absolute path."""
    assert "Traceback" not in result.stderr, result.stderr
    assert "PermissionError" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.count("REFUSED ") == 1, result.stderr
    assert result.stderr == (
        f"REFUSED workflow-unreadable: {DIRECTORY}: cannot be listed "
        f"(Permission denied)\n{REASON_ADVICE}{advice}\n"), result.stderr
    assert "pins ok" not in result.stdout, result.stdout
    assert str(root) not in result.stderr, \
        "the directory is named relative to the root, never by absolute path"


@pytest.fixture
def with_leg_workflow(project) -> Path:
    """The project with `legs.yml` committed, naming the spec leg at its
    pinned commit: the file the lockstep rule exists for, so a directory that
    cannot be read could be hiding a stale reference."""
    commit_bytes(project, f"{WORKFLOWS}/legs.yml", leg_workflow(project),
                 "legs")
    return project


# --- the issue's table: one row per mode -------------------------------------

@CANNOT_RUN_AS_ROOT
def test_a_workflows_directory_that_cannot_be_listed_is_refused_by_name(
        with_leg_workflow):
    """ROW 1, mode 000: the directory is reached (its parent is searchable)
    and `iterdir` is what the operating system refuses. The refusal names the
    directory as a file this user cannot open is named, `<path>: cannot be
    listed (<reason>)` where the file's is `cannot be read (<reason>)`, with
    the system's own reason; the remedy is access, never a re-save, and ends
    in the retry. Nothing is written."""
    root = with_leg_workflow
    before = tree_bytes(root)
    with mode_of(root, ".github/workflows", 0):
        result = validate(root)
    assert_refused_the_directory(result, root, PERMISSION_ADVICE)
    assert tree_bytes(root) == before, "a validator reads and writes nothing"
    assert git("status", "--porcelain", cwd=root).stdout == ""


@CANNOT_RUN_AS_ROOT
def test_a_workflows_directory_that_can_be_listed_but_not_searched_names_each(
        with_leg_workflow):
    """ROW 2, mode r--: the listing works and the `stat` of each child is
    what is refused. A file taken for "not a file" and skipped would be a
    `pins ok` over a workflow nobody read, so each `.yml` is named as a file
    this user cannot read, with the system's reason, and the remedy names the
    directory's search access too: the files' own modes are fine."""
    root = with_leg_workflow
    with mode_of(root, ".github/workflows", stat.S_IRUSR):
        result = validate(root)
    assert "Traceback" not in result.stderr, result.stderr
    assert "PermissionError" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.count("REFUSED ") == 1, result.stderr
    assert result.stderr.startswith("REFUSED workflow-unreadable: "), \
        result.stderr
    assert refusal_lines(result) == [
        f"{WORKFLOWS}/legs.yml: cannot be read (Permission denied)",
        f"{WORKFLOWS}/validate.yml: cannot be read (Permission denied)",
    ], result.stderr
    assert "2 workflow file(s)" in result.stderr, result.stderr
    assert FILE_ADVICE in result.stderr, result.stderr
    assert "re-save" not in result.stderr, result.stderr
    assert "Then run the same command again." in result.stderr, result.stderr
    assert "pins ok" not in result.stdout, result.stdout
    assert str(root) not in result.stderr, result.stderr


@CANNOT_RUN_AS_ROOT
def test_a_github_directory_that_cannot_be_searched_refuses_the_workflows_one(
        with_leg_workflow):
    """ROW 3, `.github/` r--: `workflows/` itself cannot be statted, so the
    directory is not reached at all. It is the same refusal as row 1, naming
    `.github/workflows` and not `.github`: that is the path this validator
    needed, and the remedy reaches the one above it."""
    root = with_leg_workflow
    before = tree_bytes(root)
    with mode_of(root, ".github", stat.S_IRUSR):
        result = validate(root)
    assert_refused_the_directory(result, root, PERMISSION_ADVICE)
    assert tree_bytes(root) == before, "a validator reads and writes nothing"


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("relative, mode", [
    pytest.param(".github/workflows", 0, id="workflows-000"),
    pytest.param(".github/workflows", stat.S_IRUSR, id="workflows-r--"),
    pytest.param(".github", stat.S_IRUSR, id="github-r--"),
])
def test_the_remedy_is_the_whole_of_it(with_leg_workflow, relative, mode):
    """THE REFUSAL'S OWN ADVICE, FOLLOWED: with the mode back, the same
    command runs and says `pins ok` (the control row: 755 reads as it did
    before this change)."""
    root = with_leg_workflow
    with mode_of(root, relative, mode):
        refused = validate(root)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    again = validate(root)
    assert again.returncode == 0, again.stdout + again.stderr
    assert "pins ok" in again.stdout, again.stdout
    assert "Traceback" not in again.stderr, again.stderr


@CANNOT_RUN_AS_ROOT
def test_the_doctors_pins_row_names_the_directory(with_leg_workflow):
    """`shape-doctor.py` quotes the first `REFUSED` line of the project's own
    validator in its `pins` row, so the directory's name reaches a reader who
    never runs the validator. Before, the row quoted the last line of a
    traceback, if the validator ran at all."""
    root = with_leg_workflow
    with mode_of(root, ".github/workflows", 0):
        result = run_script(DOCTOR, "--root", str(root), "--json")
    assert "Traceback" not in result.stderr, result.stderr
    row = {r["id"]: r for r in json.loads(result.stdout)["rows"]}["pins"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["exit"] == 2, row
    assert "refuses (exit 2)" in row["reason"], row["reason"]
    assert (f"REFUSED workflow-unreadable: {DIRECTORY}: cannot be listed "
            "(Permission denied)") in row["reason"], row["reason"]
    assert "PermissionError" not in row["reason"], row["reason"]


# --- controls: what must not change ------------------------------------------

def remove(path: Path) -> None:
    """Take `path` away, whatever it is."""
    if path.is_dir():
        rmtree(path)
    else:
        path.unlink()


def assert_not_a_refusal_of_the_directory(result) -> None:
    """The run ends where it always did for a root with no workflow to read:
    the shape pin records `.github/workflows/validate.yml`, so a root without
    it is a `shape-copy-missing` FINDING (exit 1), not a refusal and not a
    traceback. What is under test is that the directory is not READ as one
    this user cannot list."""
    assert "Traceback" not in result.stderr, result.stderr
    assert "workflow-unreadable" not in result.stderr, result.stderr
    assert result.returncode == 1, result.stdout + result.stderr
    assert ("FINDING shape-copy-missing: contracts/shape-pin.yaml: "
            ".github/workflows/validate.yml is pinned but absent"
            ) in result.stderr, result.stderr


@pytest.mark.parametrize("gone", [
    pytest.param(f"{WORKFLOWS}/validate.yml", id="no-workflow-files"),
    pytest.param(WORKFLOWS, id="no-workflows-directory"),
    pytest.param(".github", id="no-github-directory"),
])
def test_a_workflows_directory_that_is_not_there_is_still_no_workflows(
        validator, project, gone):
    """NOTHING AT THE NAME IS NOT A REFUSAL: a root with no workflow files, no
    `.github/workflows/` or no `.github/` has no `@<sha>` references to read
    (`ENOENT`), as it always had none, and the run reaches the shape pin's
    own finding that the copy it records is gone."""
    remove(project / gone)
    assert validator._workflow_refs(project) == []
    assert_not_a_refusal_of_the_directory(validate(project))


@pytest.mark.parametrize("replaced", [WORKFLOWS, ".github"])
def test_a_workflows_path_that_is_a_file_is_still_no_workflows(
        validator, project, replaced):
    """A FILE WHERE A DIRECTORY SHOULD BE, at `.github/workflows` or at
    `.github` (`ENOTDIR` from the `stat` below it): there is nothing to list,
    as before, and it is not read as a directory this user cannot list."""
    remove(project / replaced)
    (project / replaced).write_text("not a directory\n")
    assert validator._workflow_refs(project) == []
    assert_not_a_refusal_of_the_directory(validate(project))


# --- the same answers on every Python, root and Windows included -------------

def refusal_of(validator, root):
    """The `Refusal` that `validator._workflow_refs(root)` raises, failing the
    test if it returns or raises anything else. The class is the one the
    project's own copy of `repo_shape` defines, which is the one its
    `main()` catches, and not a bare `Exception`, which would pass for any
    error at all (SonarCloud S5958)."""
    with pytest.raises(validator.Refusal) as refused:
        validator._workflow_refs(root)
    return refused.value


def test_a_directory_whose_stat_is_refused_is_refused_not_no_workflows(
        validator, with_leg_workflow, monkeypatch):
    """ON PYTHON 3.14 `is_dir()` ANSWERS FALSE to a refused `stat`: an
    unsearchable `.github/` read as "no workflows" and the run said `pins ok`.
    The `stat` is asked of the operating system, so the answer is the same on
    every Python: the directory refusal, with the system's reason."""
    refused_stat(monkeypatch, "workflows")
    refusal = refusal_of(validator, with_leg_workflow)
    assert refusal.code == "workflow-unreadable"
    assert refusal.detail == (f"{DIRECTORY}: cannot be listed "
                              "(Permission denied)")
    assert refusal.remediation == REASON_ADVICE + PERMISSION_ADVICE


def test_a_workflow_whose_stat_is_refused_is_named_not_skipped(
        validator, with_leg_workflow, monkeypatch):
    """A WORKFLOWS DIRECTORY LISTABLE BUT NOT SEARCHABLE, on every Python: the
    listing names `legs.yml` and its `stat` is refused. 3.14's `is_file()`
    would call it "not a file" and skip it, which is a stale reference the
    gate never saw. It is named as a file this user cannot read."""
    refused_stat(monkeypatch, "legs.yml")
    refusal = refusal_of(validator, with_leg_workflow)
    assert refusal.code == "workflow-unreadable"
    assert refusal.detail == (
        f"{WORKFLOWS}/legs.yml: cannot be read (Permission denied)")
    assert FILE_ADVICE in refusal.remediation, refusal.remediation


def test_every_file_whose_stat_is_refused_is_named_in_the_one_refusal(
        validator, with_leg_workflow, monkeypatch):
    """The refusal reads every file before it raises, as #359's does: two
    files whose `stat` is refused are one refusal naming both, and a file
    that can be statted and read is not named."""
    commit_bytes(with_leg_workflow, f"{WORKFLOWS}/other.yaml",
                 b"on: [push]\n", "other")
    commit_bytes(with_leg_workflow, f"{WORKFLOWS}/ok.yml",
                 b"on: [push]\n", "ok")
    refused_stat(monkeypatch, "legs.yml", "other.yaml")
    refusal = refusal_of(validator, with_leg_workflow)
    assert refusal.detail.splitlines() == [
        f"{WORKFLOWS}/legs.yml: cannot be read (Permission denied)",
        f"{WORKFLOWS}/other.yaml: cannot be read (Permission denied)",
    ]
    assert "2 workflow file(s)" in refusal.remediation
    assert "ok.yml" not in refusal.detail


@pytest.mark.parametrize("failure", [
    OSError(errno.EIO, "Input/output error"),
    OSError(errno.EMFILE, "Too many open files"),
], ids=["io-error", "too-many-open-files"])
def test_a_listing_that_fails_for_another_reason_is_refused_by_name(
        validator, with_leg_workflow, monkeypatch, failure):
    """THE `OSError` FAMILY, NOT `PermissionError` ALONE: a listing that fails
    for a reason that is no permission is the same refusal with the system's
    own reason on the line, and a remedy that does not tell the operator to
    `chmod` what is not a permission."""
    real = Path.iterdir

    def iterdir(self):
        if self.name == "workflows":
            raise type(failure)(failure.errno, failure.strerror, str(self))
        return real(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    refusal = refusal_of(validator, with_leg_workflow)
    assert refusal.code == "workflow-unreadable"
    assert refusal.detail == (
        f"{DIRECTORY}: cannot be listed ({failure.strerror})")
    assert refusal.remediation == REASON_ADVICE + OTHER_ADVICE
    assert "chmod" not in refusal.remediation


class WindowsNotReady(OSError):
    """An `OSError` as Windows raises one for a drive that is not ready (21),
    a name it takes as invalid (123) or a path it cannot resolve (1921): the
    `errno` means nothing here, the class attribute stands for `winerror`."""

    def __init__(self, winerror: int, *args):
        super().__init__(errno.EINVAL, "nothing there", *args)
        self.winerror = winerror


@pytest.mark.parametrize("code", [
    errno.ENOENT, errno.ENOTDIR, errno.ELOOP, errno.EBADF, 21, 123, 1921,
], ids=["no-such-file", "not-a-directory", "symlink-loop", "bad-descriptor",
        "winerror-not-ready", "winerror-invalid-name",
        "winerror-cannot-resolve"])
def test_nothing_at_the_name_is_answered_as_it_always_was(
        validator, project, monkeypatch, code):
    """THE OTHER HALF OF THE ANSWER: a `stat` that finds nothing to open
    (`ENOENT`, a part of the path that is a file, a symlink loop, a bad
    descriptor, and the three `winerror`s Windows gives for a name that
    cannot be resolved) is "no workflows", as `is_dir()` answered it on
    Python 3.9 to 3.13, and not a directory that cannot be listed."""
    real = Path.stat

    def gone(self, *args, **kwargs):
        if self.name == "workflows":
            if code in (21, 123, 1921):
                raise WindowsNotReady(code, str(self))
            raise OSError(code, "nothing there", str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", gone)
    assert validator._workflow_refs(project) == []


@pytest.mark.parametrize("code", [errno.EACCES, errno.EPERM, errno.EIO,
                                  errno.ENAMETOOLONG],
                         ids=lambda code: errno.errorcode[code])
def test_any_other_refused_stat_is_refused_by_name(
        validator, project, monkeypatch, code):
    """EVERY OTHER `OSError` IS A REFUSAL, not "no workflows": permission
    (`EACCES`, `EPERM`), an I/O error, a name longer than the filesystem
    takes. Python 3.9 to 3.13 raised each of them out of `is_dir()`, and 3.14
    would have answered False to every one."""
    real = Path.stat

    def refused(self, *args, **kwargs):
        if self.name == "workflows":
            raise OSError(code, os.strerror(code), str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refused)
    refusal = refusal_of(validator, project)
    assert refusal.code == "workflow-unreadable"
    assert refusal.detail == (
        f"{DIRECTORY}: cannot be listed ({os.strerror(code)})")
    assert ("chmod" in refusal.remediation) == (
        code in (errno.EACCES, errno.EPERM)), refusal.remediation
