# SPDX-License-Identifier: Apache-2.0
"""Both roots' `bootstrap.py` with no git to run refuse `git-not-runnable`,
exit 2, as the validators beside them do (#694).

THE DEFECT, measured on lane 5's #682 head (8b39cd19) with `PATH` set to an
empty directory and the interpreter named by its path: the family root's
`make bootstrap` printed `(a) members and their legs`, `credential source:
none`, then a `FileNotFoundError: [Errno 2] No such file or directory: 'git'`
traceback, exit 1, which is the code of `family bootstrap FAILED`, though
nothing had failed. The assembly root's ended the same way in step (a), at
the first leg's `recorded_gitlink`, with `--skip-validators` too; and in a
clone whose legs are not initialized, where step (a) runs no git, its
offline upstream notice did, after `validate-pins.py` had refused
`git-not-runnable` itself.

THE RULE NOW. Each refuses `git-not-runnable`, the validators' code, with
their first remedy sentence (`put git on PATH and run this again`), exit 2,
and no traceback. The run STOPS there: every later step runs git too, so
going on would only say it again. Which `OSError` is git's is read by NAME,
as `validate-pins.py` reads it: `filename` `git`, or none on a
`FileNotFoundError` or a `PermissionError`, which is how Windows raises
them, or on an `OSError` whose `winerror` is 193, Windows' `[WinError 193]`
for a `git.exe` it cannot execute (#1001); an error naming a directory goes
on as it did.

The end-to-end runs are a person's: a scaffold's recursive clone, a plain
clone, and a family holder, each run with no git on `PATH`. The rule's other
errors are asked of each root's own function, in this process.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

from conftest import (PROJECT, REPO, clone_just_pushed, load_without_bytecode,
                      run_script)
from test_family import family, holder  # noqa: F401
from test_validate_pins_without_git import WIN_ERROR_193

#: What `subprocess` says when there is no git to start, here.
NO_GIT = ("The system cannot find the file specified" if os.name == "nt"
          else os.strerror(errno.ENOENT))
#: The assembly root's remedy, after the validators' first sentence.
ASSEMBLY_REMEDY = (
    "Remediation: put git on PATH and run this again. Step (a) reads each "
    "leg's pin and moves the leg through git, and the validators read the "
    "pins through git, so without it nothing here can be placed or checked.")
#: The family root's.
FAMILY_REMEDY = (
    "Remediation: put git on PATH and run this again. Step (a) fetches every "
    "member through git, and each member's own bootstrap places its legs "
    "through git too, so without it nothing here can be fetched or "
    "bootstrapped.")

#: What stands where a `git.exe` Windows cannot execute would. Python imports
#: `sitecustomize` at start-up from `PYTHONPATH`, so the script, and anything
#: it starts, load this first, as `tests/test_update_shape_landing.py`'s
#: `GH_ON_PATH` stands in for `gh`. Starting a program named `git` raises
#: what CPython raises on Windows there, `WIN_ERROR_193`; nothing else
#: changes.
GIT_NOT_WIN32 = """\
import errno
import os
import subprocess


class _Popen(subprocess.Popen):
    def __init__(self, args, *rest, **kwargs):
        if (isinstance(args, (list, tuple)) and args
                and os.path.basename(str(args[0])).lower()
                in ("git", "git.exe")):
            error = OSError(errno.ENOEXEC,
                            "%1 is not a valid Win32 application")
            error.winerror = 193
            raise error
        super().__init__(args, *rest, **kwargs)


subprocess.Popen = _Popen
"""


def without_git(root: Path, tmp_path: Path, *extra: str,
                env: dict | None = None):
    """`scripts/bootstrap.py` in `root` with `PATH` an empty directory: no
    git, and no `gh` either. The interpreter is `sys.executable`, named by
    its path."""
    empty = tmp_path / "no-git"
    empty.mkdir(exist_ok=True)
    return run_script(root / "scripts" / "bootstrap.py", *extra, cwd=root,
                      env={**(env or {}), "PATH": str(empty)})


def refused(result, *lines: str) -> None:
    """Exit 2, no traceback, and stderr ending on `lines`."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    said = result.stderr.splitlines()
    assert said[-len(lines):] == list(lines), result.stderr


@pytest.mark.parametrize("extra", [(), ("--skip-validators",)],
                         ids=["bootstrap", "skip-validators"])
def test_an_assembly_root_with_no_git_refuses_in_step_a(project, tmp_path,
                                                        extra):
    """THE ISSUE'S ASSEMBLY-ROOT CASE, run: a recursive clone. The first leg
    is where git is first needed, and the refusal names it; no leg after it
    is tried and no step after (a) runs."""
    result = without_git(project, tmp_path, *extra)
    refused(result,
            "REFUSED git-not-runnable: the spec leg at spec could not be "
            f"placed on its tracking branch: git could not be run ({NO_GIT})",
            ASSEMBLY_REMEDY)
    assert result.stdout.endswith(
        "\n(a) legs on tracking branches, pins untouched\n"), result.stdout


@pytest.mark.parametrize("shim, said", [
    (None, NO_GIT), (GIT_NOT_WIN32, WIN_ERROR_193.strerror)],
    ids=["no-git", "winerror-193"])
def test_the_offline_upstream_notice_with_no_git_refuses_too(scaffolded,
                                                             tmp_path, shim,
                                                             said):
    """A PLAIN clone: both legs NOT INITIALIZED, so step (a) runs no git, and
    `SHAPE_UPSTREAM_PATH` names a directory, so the notice after the
    validators runs one. `validate-pins.py` refuses `git-not-runnable`
    itself; the notice then ended the run in a traceback. It refuses, and
    the review-authority step is not reached. So it does where every start
    of git raises Windows' `[WinError 193]` (`GIT_NOT_WIN32`; #1001,
    RV1028's NIT 1), which the notice's `except OSError` used to swallow
    and say nothing of."""
    clone = tmp_path / PROJECT
    made = clone_just_pushed(scaffolded["remotes"] / f"{PROJECT}.git", clone,
                             recurse=False)
    assert made.returncode == 0, made.stderr
    upstream = tmp_path / "upstream"
    upstream.mkdir()
    env = {"SHAPE_UPSTREAM_PATH": str(upstream)}
    if shim is not None:
        sitecustomize = tmp_path / "git-not-win32"
        sitecustomize.mkdir()
        (sitecustomize / "sitecustomize.py").write_text(shim, encoding="utf-8")
        env["PYTHONPATH"] = str(sitecustomize)

    result = without_git(clone, tmp_path, env=env)
    refused(result,
            "REFUSED git-not-runnable: the clone SHAPE_UPSTREAM_PATH names, "
            f"{upstream}, could not be read: git could not be run ({said})",
            ASSEMBLY_REMEDY)
    assert "  [spec] spec: NOT INITIALIZED." in result.stdout, result.stdout
    assert "(c) review authority" not in result.stdout


@pytest.mark.parametrize("extra", [(), ("--skip-members",)],
                         ids=["bootstrap", "skip-members"])
def test_a_family_holder_with_no_git_refuses_at_its_fetch(holder, tmp_path,
                                                          extra):
    """THE ISSUE'S FAMILY-ROOT CASE, run. Step (a)'s `git submodule update`
    is where git is first needed; the run stops there, since each member's
    own bootstrap would only refuse the same way (#694's question for
    #648)."""
    result = without_git(holder, tmp_path, *extra)
    refused(result,
            "REFUSED git-not-runnable: the members could not be fetched: git "
            f"could not be run ({NO_GIT})", FAMILY_REMEDY)
    assert result.stdout.endswith(
        "\n(a) members and their legs\n  credential source: none\n"), (
        result.stdout)


# --- which `OSError` is git's: each root's own function ---------------------

@pytest.fixture(scope="module", params=["assembly-root", "family-root"])
def root_module(request):
    """Each root's `bootstrap.py`, loaded by path under a name of its own."""
    return load_without_bytecode(
        REPO / "templates" / request.param / "scripts" / "bootstrap.py",
        f"bootstrap_without_git_{request.param.replace('-', '_')}")


def made_of(module, error: OSError):
    """What `module` makes of `error` raised where it starts git: the
    `Refusal` it raises instead, or the error itself, raised on."""
    if hasattr(module, "_git_runs"):
        try:
            with module._git_runs("unread"):
                raise error
        except Exception as raised:  # noqa: BLE001 - what is asked
            return raised
    return module.git_not_started(error) or error


@pytest.mark.parametrize("error", [
    FileNotFoundError(errno.ENOENT, "No such file or directory", "git"),
    PermissionError(errno.EACCES, "Permission denied", "git"),
    OSError(errno.ENOEXEC, "Exec format error", "git"),
    FileNotFoundError(2, "The system cannot find the file specified"),
    WIN_ERROR_193,
], ids=["no git", "git not executable", "git no program", "windows",
        "windows winerror 193"])
def test_each_way_git_cannot_start_is_git_not_runnable(root_module, error):
    made = made_of(root_module, error)
    assert made.code == "git-not-runnable", made
    assert made.detail.endswith(
        f": git could not be run ({error.strerror})"), made.detail
    assert made.remediation.startswith(
        "Remediation: put git on PATH and run this again. "), made


@pytest.mark.parametrize("error", [
    FileNotFoundError(errno.ENOENT, "No such file or directory", "/nowhere"),
    PermissionError(errno.EACCES, "Permission denied", "/a/leg"),
    OSError(errno.EIO, "Input/output error"),
], ids=["a directory not there", "a directory not entered", "nameless"])
def test_an_error_that_is_not_gits_goes_on_as_it_did(root_module, error):
    assert made_of(root_module, error) is error
