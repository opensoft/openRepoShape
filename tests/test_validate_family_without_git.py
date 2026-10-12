# SPDX-License-Identifier: Apache-2.0
"""`validate-family.py` with no git to run refuses `git-not-runnable`, exit
2, in every mode, naming the check that could not run it (#368).

`git_out` raises `OSError` (`FileNotFoundError`) when there is no git to
start, and nothing in the validator caught it outside #317's one `.gitmodules`
reader: the default and `--pins` modes ended in a traceback, which exits 1,
a FINDING's code, though nothing was found. The docstring's own exit codes
make 1 "drift a reviewer can act on" and 2 "the question could not be
asked ... never an implicit pass".

Caught IN THE VALIDATOR, around every check that runs git (#317's
`.gitmodules` reader, #361's gitlink listing, and each member's gitlink and
tree), never in `git_out`, and never around a whole check: a
`project.yaml` nobody may read is an `OSError` too. ONE code for the
validator, whichever check met the missing git first; `gitmodules-unreadable`
keeps meaning a file git ran and could not read. And `recorded_gitlink`'s
`except Refusal` does not turn the missing git into "no gitlink": a
`FileNotFoundError` is no refusal and passes straight through it.

THE HOLDER'S OWN VALIDATOR, RUN IN THIS PROCESS, with git failing as a
missing program does, as `tests/test_family_add_refusals.py`'s no-git test
runs it: no PATH is changed for anything else, so each test means the same
on every OS. Two names reach git: the validator's own `git_out`, and the
one `recorded_gitlink` and `tree_digest` call inside `repo_shape`, so each
test says which of them fails, and where.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from test_family import family, holder  # noqa: F401

#: The remediation every `git-not-runnable` refusal ends with.
REMEDIATION = (
    "Remediation: put git on PATH and run this again. This check reads the "
    "holder the way git does, and nothing could clone it or fetch its "
    "members without git either.")

MODES = pytest.mark.parametrize(
    "extra", [(), ("--pins",), ("--no-members",)],
    ids=["members-checked", "pins", "no-members"])
MEMBER_MODES = pytest.mark.parametrize(
    "extra", [(), ("--pins",)], ids=["members-checked", "pins"])


def holder_validator(holder, monkeypatch):
    """The holder's `scripts/validate-family.py`, loaded as a module. It
    puts its own `scripts/` on `sys.path`, which is put back afterwards."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    spec = importlib.util.spec_from_file_location(
        "holder_validate_family_without_git",
        holder / "scripts" / "validate-family.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def failing(error: OSError, real=None, *, outside: Path | None = None):
    """A `git_out` that raises `error` as a program that will not start
    does. With `outside`, only where git runs anywhere but there (in a
    member, for instance), and `real` everywhere else."""
    def git_out(args, cwd, binary=False, env=None):
        if outside is not None and Path(cwd).resolve() == outside.resolve():
            return real(args, cwd, binary=binary, env=env)
        raise error
    return git_out


def without_git(module, monkeypatch, *, validator: bool, helpers: bool,
                error: OSError | None = None,
                outside: Path | None = None) -> None:
    """Make git fail for the validator's own calls (`validator`), for the
    ones `recorded_gitlink` and `tree_digest` make in `repo_shape`
    (`helpers`), or both."""
    error = error or FileNotFoundError(2, "No such file or directory", "git")
    real = module.git_out
    fake = failing(error, real, outside=outside)
    if validator:
        monkeypatch.setattr(module, "git_out", fake)
    if helpers:
        monkeypatch.setattr(sys.modules[module.recorded_gitlink.__module__],
                            "git_out", fake)


def run(module, holder, capsys, *extra) -> tuple[int, list[str]]:
    code = module.main(["--root", str(holder), *extra])
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err
    return code, err.splitlines()


@MODES
@pytest.mark.parametrize("error", [
    FileNotFoundError(2, "No such file or directory", "git"),
    PermissionError(13, "Permission denied", "git")],
    ids=["no-git", "git-not-executable"])
def test_no_git_at_all_is_one_refusal_in_every_mode(holder, monkeypatch,
                                                    capsys, extra, error):
    """THE HOLDER AS `add` LEFT IT: `.gitmodules` is read first, so that is
    the check named. Exit 2 and the one code in every mode, where #317 said
    `gitmodules-unreadable`, a code that now means a file git ran and could
    not read."""
    module = holder_validator(holder, monkeypatch)
    without_git(module, monkeypatch, validator=True, helpers=True,
                error=error)
    code, err = run(module, holder, capsys, *extra)
    assert code == 2, err
    assert err == [
        "REFUSED git-not-runnable: .gitmodules could not be read as git "
        f"reads it: git could not be run ({error.strerror})", REMEDIATION]


@MODES
def test_with_no_gitmodules_the_gitlink_listing_is_named(holder, monkeypatch,
                                                         capsys, extra):
    """THE ISSUE'S RESIDUE: a holder with member rows and its `.gitmodules`
    gone from the working tree, where main still ended in the traceback in
    the default and `--pins` modes. The first check to run git is now #361's
    listing of `members/`, which every mode runs, `--no-members` included:
    where it passed before, having run no git at all, it now refuses."""
    (holder / ".gitmodules").unlink()
    module = holder_validator(holder, monkeypatch)
    without_git(module, monkeypatch, validator=True, helpers=True)
    code, err = run(module, holder, capsys, *extra)
    assert code == 2, err
    assert err == [
        "REFUSED git-not-runnable: the gitlinks this repository records in "
        "members/ could not be listed: git could not be run (No such file "
        "or directory)", REMEDIATION]


@MEMBER_MODES
def test_a_members_gitlink_that_git_cannot_read_is_named_not_absent(
        holder, monkeypatch, capsys, extra):
    """GIT FAILS ONLY IN `recorded_gitlink`, so every check before the
    members' runs, and the first member's gitlink is the check named. Were
    the missing git read as "no gitlink here", this would say
    `member-gitlink-absent` and tell the operator to `add` a member that is
    mounted."""
    module = holder_validator(holder, monkeypatch)
    without_git(module, monkeypatch, validator=False, helpers=True)
    code, err = run(module, holder, capsys, *extra)
    assert code == 2, err
    assert err == [
        "REFUSED git-not-runnable: the gitlink recorded at members/IRRS "
        "could not be read: git could not be run (No such file or "
        "directory)", REMEDIATION]


def test_no_members_runs_no_member_check_that_needs_git(holder, monkeypatch,
                                                        capsys):
    """And `--no-members`, which reads no member, passes with the same git:
    the refusal is the check's, not the mode's."""
    module = holder_validator(holder, monkeypatch)
    without_git(module, monkeypatch, validator=False, helpers=True)
    code = module.main(["--root", str(holder), "--no-members"])
    out, err = capsys.readouterr()
    assert code == 0, out + err
    assert "family ok: InkRouter (inkrouter), 2 member(s)" in out


@MEMBER_MODES
def test_a_members_tree_that_git_cannot_read_is_named(holder, monkeypatch,
                                                      capsys, extra):
    """GIT RUNS IN THE HOLDER AND NOT IN A MEMBER, so the gitlink is read
    and the pinned commit and its digest, read inside the member, are the
    check named."""
    module = holder_validator(holder, monkeypatch)
    without_git(module, monkeypatch, validator=True, helpers=True,
                outside=holder)
    code, err = run(module, holder, capsys, *extra)
    assert code == 2, err
    assert err == [
        "REFUSED git-not-runnable: IRRS's pinned commit and its tree digest "
        "could not be read in members/IRRS: git could not be run (No such "
        "file or directory)", REMEDIATION]

