# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: a path this user cannot SEARCH or read is refused by
name, and never read as absent (#430, slice A).

`tests/test_bump_leg_unopenable.py` (#383) covers the pin, the workflow files
and their directory. Three more guards asked `Path.is_file()` or
`Path.exists()`, which up to Python 3.13 raised a refused `stat`
(`PermissionError`) and from 3.14 answer False to it:

  * `run_validator`, of the project's own `scripts/validate-pins.py` and
    `scripts/validate-manifest.py`. With `scripts/` at mode 444 or 000, 3.14
    printed `<script> is absent; SKIPPED` for both and COMMITTED the bump,
    exit 0, with neither check run; 3.12 ended `bump-leg-rewrite-failed`,
    rolled back, after the leg had moved. A validator at mode 000 in a
    searchable `scripts/` was `bump-leg-validators-red` after the rewrite. A
    dry run said none of it, exit 0. Now each one that is there and cannot
    be read is `bump-leg-validator-unreadable`, named, exit 2, before
    anything is written, under `--dry-run` as well; one that is not there at
    all is still SKIPPED (the control below).
  * `_initialized_submodule`, of `<leg>/.git`. A leg at mode 000 was a
    traceback on 3.12 and `bump-leg-uninitialized` on 3.14, whose remedy
    initializes a checkout that is there. Now `bump-leg-submodule-unreadable`.
  * `Project.open`, of `<root>/project.yaml`. A root this user cannot search
    was a traceback on 3.12 and `bump-leg-root-not-a-project` ("does not
    exist") on 3.14. Now `bump-leg-manifest-unreadable`.

THE MODE TESTS run the tool as a subprocess on a real mode, through
`test_bump_leg_unopenable`'s `made_unopenable` (git told to assume the files
unchanged, so it is the read that fails and not `bump-leg-root-dirty`; the
mode put back in a `finally`), and the root's through `unsearchable_root`,
which asks git nothing while the root cannot be searched. They skip on
Windows and as root. On a Python before 3.14 they show the 3.12 half: the
refusal under its own id, no traceback, nothing moved.

THE 3.14 HALF, ON EVERY PYTHON. `refused_stat` (the same file) makes
`Path.stat` refuse the names it is given and `is_file`, `is_dir` and
`exists` answer as 3.14's do, in-process, so the tests that use it run
everywhere, root included, and fail a tool that leans on `is_file` raising.
The real run is `main()` itself, so "HEAD unchanged" is asked of a bump that
on 3.14 committed.

EVERY REFUSED RUN OF THE TOOL COMPARES THE WHOLE TREE (`snapshot`, taken
before the mode is changed), and every refused run on a real mode is run again
with the mode back, to show that the remedy the refusal gives is the whole of
it. The refusals asked in-process are not run again: their `stat` was never
really refused.

A CAUSE THAT IS NOT A PERMISSION (`stat_fails`, an I/O error) is asked on
every platform and as root too, for each of the three refusals: its own
reason on the line, no `chmod`, and, for a validator, a remedy that does not
take the file away, since a validator taken away is SKIPPED.
"""

from __future__ import annotations

import contextlib
import errno
import stat
from pathlib import Path

import pytest

from conftest import PROJECT, cloned_just_pushed, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    bump, bump_leg_module, committed, validate,
)
from test_bump_leg_rollback import assert_nothing_changed, snapshot
from test_bump_leg_unopenable import (
    made_unopenable, needs_a_mode, refusal_of, refused_again_fine,
    refused_stat, refused_while_unopenable,
)
from test_bump_leg_unreadable import MODES, prepared

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-unsearchable-advance"

VALIDATORS = ("scripts/validate-pins.py", "scripts/validate-manifest.py")

#: The names `refused_stat` refuses for the two validators.
VALIDATOR_NAMES = tuple(Path(script).name for script in VALIDATORS)

#: A directory this user can list and cannot search, and one it can do
#: neither with.
SEARCH_MODES = pytest.mark.parametrize(
    "mode", [stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH, 0],
    ids=["listable-not-searchable", "mode-000"])


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-unsearchable")
        / f"{PROJECT}-spec")
    (work / "UNSEARCHABLE-CONTRACT.md").write_text("# a contract gained\n")
    git("add", "--", "UNSEARCHABLE-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the unsearchable-path tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def bump_in_process(module, project: Path, scaffolded: dict, to: str,
                    *extra: str) -> int:
    """`main()` itself, so a `refused_stat` set by the test reaches it."""
    return module.main(["--root", str(project), "--leg", "spec", "--to", to,
                        "--local-remote-dir", str(scaffolded["remotes"]),
                        *extra])


def assert_names_both_validators(stderr: str) -> None:
    assert "2 of the project's own validator(s) cannot be opened" in stderr
    for script in VALIDATORS:
        assert f"{script}: cannot be read: Permission denied" in stderr, (
            stderr)


#: The operating system's two refusals of a `stat`: a permission, and a cause
#: that is not one. Never raised themselves: `stat_fails` makes a new one per
#: path, naming it.
IO_ERROR = OSError(errno.EIO, "Input/output error")
DENIED = PermissionError(errno.EACCES, "Permission denied")


def stat_fails(monkeypatch, failures: dict) -> None:
    """`Path.stat` raising, for each file NAME in `failures`, an error like
    the one it maps to, naming the path. Nothing else is changed (unlike
    `refused_stat`, which also makes `is_file` answer as 3.14's does), so it
    runs on every platform and as root, and asks the tool what it does with a
    `stat` that failed for a cause that is not a permission."""
    real = Path.stat

    def failing(self, *args, **kwargs):
        failure = failures.get(self.name)
        if failure is not None:
            raise type(failure)(failure.errno, failure.strerror, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing)


# --- the project's own validators, on a real mode --------------------------

@needs_a_mode
@MODES
@SEARCH_MODES
def test_a_scripts_directory_that_cannot_be_searched_refuses_both_validators(
        project, scaffolded, advanced, extra, mode):
    """THE ISSUE'S ROW: `scripts/` at 444 (its names list, no `stat` of one
    is let through) or 000. On 3.14 the real run SKIPPED both validators and
    committed, exit 0; on 3.12 it was `bump-leg-rewrite-failed` after the leg
    had moved; the dry run passed it, exit 0, on both. Now both runs refuse
    it by name, exit 2, with HEAD and every byte where they were, and the
    remedy names `chmod u+rx`."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-validator-unreadable",
        "scripts", extra=extra, mode=mode)

    assert_names_both_validators(stderr)
    assert "absent" not in stderr
    assert "SKIPPED" not in stderr
    assert "chmod u+rx" in stderr
    assert "every directory above it" in stderr
    assert "A `stat` of a file is refused" in stderr
    assert "`scripts/` or a directory above it" in stderr
    assert "never one to skip" in stderr
    assert "Then run the same command again" in stderr
    assert "bump-leg-rewrite-failed" not in stderr
    assert "rolled back" not in stderr, "refused before the leg moved"
    refused_again_fine(project, scaffolded, advanced, extra,
                       "contracts/spec-pin.yaml")


@needs_a_mode
@MODES
def test_a_validator_this_user_cannot_open_is_refused_by_name(
        project, scaffolded, advanced, extra):
    """`scripts/validate-pins.py` itself at mode 000, in a `scripts/` that can
    be searched: its `stat` answers, its open does not. It reached the child,
    which could not open it, and the real run was `bump-leg-validators-red`
    after the rewrite, the dry run exit 0. Now it is named before anything is
    written, and the validator that can be read is not."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-validator-unreadable",
        "scripts/validate-pins.py", extra=extra)

    assert "1 of the project's own validator(s) cannot be opened" in stderr
    assert ("scripts/validate-pins.py: cannot be read: Permission denied"
            in stderr)
    assert "scripts/validate-manifest.py: cannot be read" not in stderr
    assert "chmod u+r" in stderr
    assert "A `stat` of a file is refused" not in stderr, "the open failed"
    assert "bump-leg-validators-red" not in stderr
    assert "rolled back" not in stderr, "refused before the leg moved"
    refused_again_fine(project, scaffolded, advanced, extra,
                       "contracts/spec-pin.yaml")


@contextlib.contextmanager
def moved_aside(project: Path, aside: Path, *relatives: str):
    """Each of `relatives` moved out of the root, with git told to assume it
    unchanged so the root still reads clean, and both put back."""
    aside.mkdir()
    moved: list[str] = []
    try:
        for relative in relatives:
            git("update-index", "--assume-unchanged", "--", relative,
                cwd=project)
            moved.append(relative)
            (project / relative).rename(aside / Path(relative).name)
        yield
    finally:
        for relative in moved:
            parked = aside / Path(relative).name
            if parked.exists():
                parked.rename(project / relative)
            git("update-index", "--no-assume-unchanged", "--", relative,
                cwd=project)


@MODES
def test_a_validator_that_is_not_there_is_still_skipped(
        project, scaffolded, advanced, extra, tmp_path):
    """THE CONTROL: a validator that is NOT THERE (`ENOENT`) is no validator
    this user cannot read. It is SKIPPED by the real run, as it always was,
    and the bump commits; the dry run passes it. Neither is refused
    `bump-leg-validator-unreadable`."""
    prepared(project)

    with moved_aside(project, tmp_path / "aside", *VALIDATORS):
        assert git("status", "--porcelain", cwd=project).stdout == "", (
            "git must read the tree as clean")
        result = bump(project, scaffolded, advanced, *extra)

    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "bump-leg-validator-unreadable" not in output
    assert "Traceback" not in output
    if not extra:
        for script in VALIDATORS:
            assert f"{script} is absent; SKIPPED" in result.stdout, output
        assert "committed" in result.stdout
        assert "contracts/spec-pin.yaml" in committed(project)
        assert git("status", "--porcelain", cwd=project).stdout == ""


# --- the project's own validators, as Python 3.14 answers (everywhere) -----

@MODES
def test_validators_whose_stat_is_refused_are_refused_not_skipped(
        bump_leg_module, project, scaffolded, advanced, monkeypatch, capsys,
        extra):
    """THE 3.14 CASE, ON EVERY PYTHON: `scripts/` this user cannot search,
    as `refused_stat` stands in for it. `is_file()` answered "no file", the
    real run printed `<script> is absent; SKIPPED` twice and COMMITTED, exit
    0. Now the real run and the dry run are refused by name, exit 2, and the
    root's HEAD has not moved."""
    prepared(project)
    before = snapshot(project)
    refused_stat(monkeypatch, *VALIDATOR_NAMES)

    code = bump_in_process(bump_leg_module, project, scaffolded, advanced,
                           *extra)

    out, err = capsys.readouterr()
    monkeypatch.undo()
    assert code == 2, out + err
    assert "REFUSED bump-leg-validator-unreadable" in err, out + err
    assert_names_both_validators(err)
    assert "SKIPPED" not in out + err
    assert "committed" not in out
    assert "chmod u+rx" in err
    assert "`scripts/` or a directory above it" in err
    assert bump_leg_module.ROLLED_BACK not in err, "refused before the write"
    assert_nothing_changed(project, before)


def test_a_validator_refused_only_at_run_time_is_rolled_back_not_skipped(
        bump_leg_module, project, scaffolded, advanced, monkeypatch, capsys):
    """`run_validator`'s own guard, on every Python: where the `stat` is
    refused after `_validators_readable` let the run through (a mode changed
    while it ran, stood in for by switching the check off), the validator is
    not SKIPPED. The refused `stat` is raised, rolled back and reported as
    `bump-leg-rewrite-failed`, as Python 3.12 always did, and the root's HEAD
    has not moved."""
    prepared(project)
    before = snapshot(project)
    monkeypatch.setattr(bump_leg_module, "_validators_readable",
                        lambda root: None, raising=False)
    refused_stat(monkeypatch, *VALIDATOR_NAMES)

    code = bump_in_process(bump_leg_module, project, scaffolded, advanced)

    out, err = capsys.readouterr()
    monkeypatch.undo()
    assert code == 2, out + err
    assert "REFUSED bump-leg-rewrite-failed" in err, out + err
    assert "Permission denied" in err
    assert "SKIPPED" not in out + err
    assert "committed" not in out
    assert bump_leg_module.ROLLED_BACK in err
    assert_nothing_changed(project, before)


@pytest.mark.parametrize("script", VALIDATORS)
def test_a_validator_failing_for_another_reason_is_restored_not_taken_away(
        bump_leg_module, project, monkeypatch, script):
    """AN I/O ERROR IS NO PERMISSION, on every platform and as root, for each
    validator: the same refusal and the system's own reason on the line, and a
    remedy that does not tell the operator to `chmod` and does not offer to
    "take away one nobody wants", which would make the validator SKIPPED. It
    names the file to restore from the project's history, and no directory
    that is not at fault."""
    stat_fails(monkeypatch, {Path(script).name: IO_ERROR})
    other = next(name for name in VALIDATORS if name != script)

    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._validators_readable, project)

    assert refusal.code == "bump-leg-validator-unreadable"
    assert refusal.detail.startswith(
        "1 of the project's own validator(s) cannot be opened:")
    assert f"{script}: cannot be read: Input/output error" in refusal.detail
    assert other not in refusal.detail
    assert "chmod" not in refusal.remediation
    assert "Where the operating system gave another reason, restore" in (
        refusal.remediation)
    assert f"restore `{script}` from the project's history" in (
        refusal.remediation)
    assert f"(`git checkout -- {script}`)" in refusal.remediation
    assert "`scripts/` while this runs" in refusal.remediation
    assert "take away" not in refusal.remediation
    assert "put a regular file" not in refusal.remediation
    assert "A `stat` of a file is refused" not in refusal.remediation


def test_validators_refused_for_both_kinds_of_cause_get_each_ones_advice(
        bump_leg_module, project, monkeypatch):
    """ONE I/O ERROR AND ONE REFUSED PERMISSION: each cause's sentence once,
    the permission's first, and only the file whose cause is not a permission
    is restored."""
    stat_fails(monkeypatch, {"validate-pins.py": IO_ERROR,
                             "validate-manifest.py": DENIED})

    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._validators_readable, project)

    assert refusal.code == "bump-leg-validator-unreadable"
    assert refusal.detail.startswith(
        "2 of the project's own validator(s) cannot be opened:")
    assert ("scripts/validate-pins.py: cannot be read: Input/output error"
            in refusal.detail)
    assert ("scripts/validate-manifest.py: cannot be read: Permission denied"
            in refusal.detail)
    assert "chmod u+rx" in refusal.remediation
    assert "A `stat` of a file is refused" in refusal.remediation
    assert "(`git checkout -- scripts/validate-pins.py`)" in (
        refusal.remediation)
    assert "restore `scripts/validate-pins.py` from" in refusal.remediation
    assert "take away" not in refusal.remediation
    assert refusal.remediation.index("chmod u+rx") < (
        refusal.remediation.index("restore `scripts/validate-pins.py`"))


def test_a_validator_whose_open_is_refused_does_not_blame_a_directory(
        bump_leg_module, project, monkeypatch):
    """A `stat` that answers and an open that is refused (the file at mode
    000, as the test above it on a real mode): the file is at fault and no
    directory is, so the sentence about a directory on the way to it is not
    said. Asked in-process, so it runs as root too."""
    real = Path.open

    def opening(self, *args, **kwargs):
        if self.name == "validate-pins.py":
            raise type(DENIED)(DENIED.errno, DENIED.strerror, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opening)

    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._validators_readable, project)

    assert refusal.code == "bump-leg-validator-unreadable"
    assert refusal.detail.startswith(
        "1 of the project's own validator(s) cannot be opened:")
    assert ("scripts/validate-pins.py: cannot be read: Permission denied"
            in refusal.detail)
    assert "chmod u+r" in refusal.remediation
    assert "A `stat` of a file is refused" not in refusal.remediation


def test_a_run_with_nothing_to_do_asks_no_validator(
        bump_leg_module, project, scaffolded, monkeypatch, capsys):
    """THE ORDER, pinned: a run whose `--to` every fact already names writes
    nothing and runs no validator, so `nothing to do` (exit 1) is still its
    answer. The validators are asked after it, and before the dry-run
    return."""
    prepared(project)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    refused_stat(monkeypatch, *VALIDATOR_NAMES)

    code = bump_in_process(bump_leg_module, project, scaffolded, pinned)

    out, err = capsys.readouterr()
    assert code == 1, out + err
    assert "nothing to do" in out
    assert "bump-leg-validator-unreadable" not in err


# --- the leg's checkout ------------------------------------------------------

@needs_a_mode
@MODES
@SEARCH_MODES
def test_a_leg_checkout_that_cannot_be_searched_is_never_uninitialized(
        project, scaffolded, advanced, extra, mode):
    """THE ISSUE'S ROW: `spec/` at 000 (or 444), a checkout this user cannot
    enter. A traceback on 3.12 and `bump-leg-uninitialized` on 3.14, whose
    remedy is a `git submodule update --init` of a checkout that is there.
    Now `bump-leg-submodule-unreadable`, naming `spec/.git`, in both runs."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-submodule-unreadable",
        "spec", extra=extra, mode=mode)

    assert "spec/.git: cannot be read: Permission denied" in stderr
    assert "bump-leg-uninitialized" not in stderr
    assert "is not an initialized submodule checkout" not in stderr
    assert "chmod u+rx" in stderr
    refused_again_fine(project, scaffolded, advanced, extra,
                       "contracts/spec-pin.yaml")


def test_a_leg_checkout_whose_stat_is_refused_is_not_called_uninitialized(
        bump_leg_module, project, monkeypatch):
    """The 3.14 case, on every Python: the `stat` of `spec/.git` refused."""
    refused_stat(monkeypatch, ".git")

    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._initialized_submodule,
                         project, "spec")

    assert refusal.code == "bump-leg-submodule-unreadable"
    assert refusal.detail == "spec/.git: cannot be read: Permission denied"
    assert "chmod u+rx" in refusal.remediation
    assert "--init" in refusal.remediation
    assert "would not" in refusal.remediation


def test_a_leg_checkout_failing_for_another_reason_is_refused_sans_chmod(
        bump_leg_module, project, monkeypatch):
    """AN I/O ERROR ON `spec/.git`, on every platform and as root: the same
    refusal and the system's own reason, never `bump-leg-uninitialized`, and a
    remedy that does not tell the operator to `chmod` what is not a
    permission."""
    stat_fails(monkeypatch, {".git": IO_ERROR})

    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._initialized_submodule,
                         project, "spec")

    assert refusal.code == "bump-leg-submodule-unreadable"
    assert refusal.detail == "spec/.git: cannot be read: Input/output error"
    assert "chmod" not in refusal.remediation
    assert "Where the operating system gave another reason" in (
        refusal.remediation)


@pytest.mark.parametrize("leg", ["nowhere", "contracts/spec-pin.yaml"],
                         ids=["no-such-directory", "a-file-on-the-path"])
def test_a_leg_that_is_not_there_is_still_uninitialized(
        bump_leg_module, project, leg):
    """THE CONTROL: nothing at the name (`ENOENT`), or a file where the
    checkout goes (`ENOTDIR`), is the uninitialized leg it always was."""
    refusal = refusal_of(bump_leg_module,
                         bump_leg_module._initialized_submodule,
                         project, leg)

    assert refusal.code == "bump-leg-uninitialized"
    assert refusal.detail.startswith(
        f"{leg} is not an initialized submodule checkout")


# --- the root ----------------------------------------------------------------

@contextlib.contextmanager
def unsearchable_root(project: Path, mode: int):
    """`--root` itself at `mode`, put back in a `finally`. No git is asked
    anything while it is on: a root this user cannot enter is no cwd."""
    was = stat.S_IMODE(project.stat().st_mode)
    try:
        project.chmod(mode)
        yield
    finally:
        project.chmod(was)


@needs_a_mode
@MODES
@SEARCH_MODES
def test_a_root_that_cannot_be_searched_is_refused_by_name(
        project, scaffolded, advanced, extra, mode):
    """`--root` this user cannot search: a traceback on 3.12, and on 3.14
    `bump-leg-root-not-a-project`, "project.yaml does not exist", whose
    remedy sends the operator to another directory. Now
    `bump-leg-manifest-unreadable`, naming the manifest by its whole path,
    since relative to a root that cannot be searched it says no root."""
    prepared(project)
    before = snapshot(project)

    with unsearchable_root(project, mode):
        result = bump(project, scaffolded, advanced, *extra)

    output = result.stderr + result.stdout
    assert result.returncode == 2, output
    assert "REFUSED bump-leg-manifest-unreadable" in result.stderr, output
    manifest = project.resolve() / "project.yaml"
    assert f"{manifest}: cannot be read: Permission denied" in result.stderr
    assert "bump-leg-root-not-a-project" not in output
    assert "does not exist" not in output
    assert "Traceback" not in output
    assert "PermissionError" not in output
    assert "the root itself or a directory above it" in result.stderr
    assert "inside the root" not in result.stderr
    assert "chmod u+rx" in result.stderr
    assert_nothing_changed(project, before)
    refused_again_fine(project, scaffolded, advanced, extra,
                       "contracts/spec-pin.yaml")


def test_a_manifest_whose_stat_is_refused_is_not_called_absent(
        bump_leg_module, project, monkeypatch):
    """The 3.14 case, on every Python: the `stat` of `project.yaml` refused."""
    refused_stat(monkeypatch, "project.yaml")

    refusal = refusal_of(bump_leg_module, bump_leg_module.Project.open,
                         project)

    assert refusal.code == "bump-leg-manifest-unreadable"
    assert refusal.detail == (f"{project.resolve() / 'project.yaml'}: "
                              "cannot be read: Permission denied")
    assert "chmod u+rx" in refusal.remediation
    assert "(and on every directory above it), or" in refusal.remediation
    assert "inside the root" not in refusal.remediation


def test_a_manifest_failing_for_another_reason_is_refused_sans_chmod(
        bump_leg_module, project, monkeypatch):
    """AN I/O ERROR ON `project.yaml`, on every platform and as root: the same
    refusal and the system's own reason, no `chmod`, and no word of a
    directory above the root, which is no directory at fault here."""
    stat_fails(monkeypatch, {"project.yaml": IO_ERROR})

    refusal = refusal_of(bump_leg_module, bump_leg_module.Project.open,
                         project)

    assert refusal.code == "bump-leg-manifest-unreadable"
    assert refusal.detail == (f"{project.resolve() / 'project.yaml'}: "
                              "cannot be read: Input/output error")
    assert "chmod" not in refusal.remediation
    assert "Where the operating system gave another reason" in (
        refusal.remediation)
    assert "a directory above it" not in refusal.remediation


def test_a_root_with_no_manifest_is_still_not_a_project(
        bump_leg_module, tmp_path):
    """THE CONTROL: a directory with no `project.yaml` is not a project."""
    (tmp_path / "empty").mkdir()

    refusal = refusal_of(bump_leg_module, bump_leg_module.Project.open,
                         tmp_path / "empty")

    assert refusal.code == "bump-leg-root-not-a-project"
