# SPDX-License-Identifier: Apache-2.0
"""`validate-pins.py` with no git to run refuses `git-not-runnable`, exit 2,
naming the check that could not run it (#412).

`git_out` raises `FileNotFoundError` when there is no git on PATH, and
`PermissionError` when the `git` found there will not run, and nothing in the
validator caught either: a scaffolded root ended in a traceback, which exits
1, a FINDING's code, though nothing was found. The module's own exit codes make
1 "drift a reviewer can act on" and 2 "the question could not be asked ...
never an implicit pass". The doctor's `pins` row on such a machine quoted that
traceback as "reports a finding (exit 1)".

Caught IN THE VALIDATOR, around the three calls that run git (the leg's
gitlink, the pinned commit's lookup and the tree digest), never in `git_out`
and never around a whole check. ONE code, `git-not-runnable`, the one
`validate-family.py` uses for the same fact. And a git that will not start is
told apart from every other `OSError`: the wrapper is around the git calls
alone, and inside one it counts an `OSError` whose `filename` is `git` (a
missing git, one that will not run, and one that cannot be executed, `ENOEXEC`:
a binary for another architecture or a script with no shebang), a
`FileNotFoundError` or a `PermissionError` that names no file (Windows'
`CreateProcess` failures carry none), and an `OSError` that names none whose
`winerror` is 193, a `git.exe` Windows cannot execute (#1001). `subprocess`
raises the same two classes when the directory it was to run git in cannot be
entered, and names that directory in `filename`; a program that will not start
names `git`.

THE ROOT'S OWN VALIDATOR, RUN IN THIS PROCESS, with git failing as a missing
program does, and no PATH changed for anything else, so each test means the
same on every OS. Two names reach git: the validator's own `git_out`, and the
one `recorded_gitlink` and `tree_digest` call inside `repo_shape`, so each test
says which of the three calls fails. The one test that does change PATH runs
the real `subprocess` and skips on Windows, and says why.

THE FAKE PICKS A CALL BY ITS SUBCOMMAND, never by `args[0]` (the review of
#412). `repo_shape`'s `recorded_gitlink` is about to run `git
--literal-pathspecs ls-files ...` (#367, #406), and a predicate that read the
first argument would stop matching it, so the "gitlink" cases would stop
failing where they should and eight tests would fail on that merge.
"""

from __future__ import annotations

import errno
import importlib.util
import sys
from pathlib import Path

import pytest

from conftest import WINDOWS_SKIP, git

OTHER_SHA = "0123456789abcdef0123456789abcdef01234567"

#: The remediation every `git-not-runnable` refusal ends with.
REMEDIATION = (
    "Remediation: put git on PATH and run `scripts/validate-pins.py` again. "
    "This assembly root's lockstep gate reads each leg's gitlink and "
    "recomputes its pinned tree digest through git, so without it nothing "
    "says whether the pins agree, and a gate that cannot answer is never a "
    "pass.")

#: How a missing program, a program that will not run, and a program this
#: machine cannot execute (`ENOEXEC`: another architecture's binary, a script
#: with no shebang) fail to start. `subprocess` names `git` in each.
NO_GIT = FileNotFoundError(2, "No such file or directory", "git")
NOT_EXECUTABLE = PermissionError(13, "Permission denied", "git")
CANNOT_EXECUTE = OSError(errno.ENOEXEC, "Exec format error", "git")
#: An error that names no file: Windows' `CreateProcess` failures carry no
#: filename, so a missing git there looks like this, and nothing says it was a
#: directory. Only these two classes count, named or not, and the one
#: `WIN_ERROR_193` is (see `NOT_GIT`).
NO_FILE_NAMED = FileNotFoundError(2, "No such file or directory")
NOT_EXECUTABLE_NO_FILE_NAMED = PermissionError(13, "Permission denied")
#: What CPython raises on Windows for a `git.exe` that Windows cannot execute
#: (`[WinError 193] %1 is not a valid Win32 application`): a plain `OSError`,
#: since `winerror` 193 maps to `errno` `ENOEXEC`, which has no subclass, and
#: no filename, since `CreateProcess` failures carry none. It counts by its
#: `winerror` (#1001). Read from CPython (`PC/errmap.h`,
#: `_winapi.CreateProcess`), not run on Windows, and built by hand on every
#: OS, since only Windows sets `winerror`.
WIN_ERROR_193 = OSError(errno.ENOEXEC, "%1 is not a valid Win32 application")
WIN_ERROR_193.winerror = 193

#: The run options. The validator has one mode of work and these three
#: spellings of asking it: plain, without the `ok` notes, and with a source
#: for a neutral product's digest.
RUNS = pytest.mark.parametrize(
    "extra", [(), ("--quiet",), ("--pin-source", "nowhere")],
    ids=["plain", "quiet", "pin-source"])

#: git's global options that take their value as the NEXT argument, which the
#: subcommand is not.
GLOBAL_OPTIONS_WITH_A_VALUE = ("-C", "-c", "--git-dir", "--work-tree",
                               "--namespace", "--config-env")


def subcommand(args: list[str]) -> str | None:
    """The git subcommand `args` runs, wherever it sits among git's global
    options: `git --literal-pathspecs ls-files -s -- spec` runs `ls-files`,
    and so does `git -C there --no-pager ls-files`. `args[0]` is the
    subcommand only until a caller adds a global option (#406 does)."""
    rest = iter(args)
    for arg in rest:
        if arg in GLOBAL_OPTIONS_WITH_A_VALUE:
            next(rest, None)
        elif not arg.startswith("-"):
            return arg
    return None


#: The three calls that run git, as the predicate on `git_out`'s argv that
#: makes one of them fail and no other. `recorded_gitlink` lists the index
#: (`ls-files`), the pinned commit's lookup is `rev-parse`, and the digest is
#: a recursive `ls-tree`. Each reads the SUBCOMMAND, never `args[0]`.
GITLINK = ("gitlink", lambda args: subcommand(args) == "ls-files")
COMMIT = ("commit", lambda args: subcommand(args) == "rev-parse")
DIGEST = ("digest",
          lambda args: subcommand(args) == "ls-tree" and "-r" in args)
EVERY_CALL = ("every", lambda args: True)
CALLS = pytest.mark.parametrize(
    "call", [GITLINK, COMMIT, DIGEST], ids=lambda call: call[0])


@pytest.fixture
def validator(project, monkeypatch):
    """The project's own `scripts/validate-pins.py`, loaded as a module, and
    its own `repo_shape.py` beside it. The module puts its `scripts/` on
    `sys.path`, and the `repo_shape` it imports is put back, or dropped,
    afterwards: a copy under a temporary directory must not outlive the
    test for the next one that imports the standard's."""
    monkeypatch.setattr(sys, "path", list(sys.path))
    saved = sys.modules.pop("repo_shape", None)
    try:
        spec = importlib.util.spec_from_file_location(
            "project_validate_pins_without_git",
            project / "scripts" / "validate-pins.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop("repo_shape", None)
        if saved is not None:
            sys.modules["repo_shape"] = saved


def failing(error: OSError, fails, real):
    """A `git_out` that raises `error`, as a program that will not start does,
    for each call `fails` says so of, and runs `real` for every other. It
    takes `**kwargs` because `git_out` has grown a keyword before and may
    again: the fake must not be what stops it."""
    def git_out(args, cwd, binary=False, **kwargs):
        if fails(args):
            raise error
        return real(args, cwd, binary=binary, **kwargs)
    return git_out


def git_fails(module, monkeypatch, error: OSError, call=EVERY_CALL) -> None:
    """Make `call` fail with `error` in the validator's own `git_out` and in
    the one `recorded_gitlink` and `tree_digest` call in `repo_shape`."""
    fake = failing(error, call[1], module.git_out)
    monkeypatch.setattr(module, "git_out", fake)
    monkeypatch.setattr(sys.modules[module.recorded_gitlink.__module__],
                        "git_out", fake)


def run(module, project, capsys, *extra) -> tuple[int, str, list[str]]:
    code = module.main(["--root", str(project), *extra])
    out, err = capsys.readouterr()
    assert "Traceback" not in out + err
    return code, out, err.splitlines()


def spec_commit(project) -> str:
    return git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()


#: What can come before the subcommand: nothing, #406's `--literal-pathspecs`
#: (the one a caller really adds), a flag, and options that take a value.
GLOBAL_OPTIONS = pytest.mark.parametrize(
    "before",
    [(), ("--literal-pathspecs",), ("--no-pager", "--literal-pathspecs"),
     ("-C", "elsewhere"), ("-c", "core.quotepath=off", "--literal-pathspecs")],
    ids=["none", "literal-pathspecs", "flags", "dash-C",
         "dash-c-then-literal-pathspecs"])


@GLOBAL_OPTIONS
def test_each_call_is_picked_by_its_subcommand_wherever_it_sits(before):
    """THE REVIEW OF #412 (MUST-1): `args[0] == "ls-files"` stopped matching
    the gitlink call the day `recorded_gitlink` began to run `git
    --literal-pathspecs ls-files ...`, and the "gitlink" cases then ran with
    nothing failing, so they failed for the wrong reason or passed for no
    reason. Each of the three predicates picks its own call, and no other,
    whatever global options come before the subcommand, and the second
    listing `recorded_gitlink` falls back to (`ls-tree HEAD`) is none of
    them: no case here fails it."""
    calls = {
        "gitlink": ["ls-files", "-s", "--", "spec"],
        "commit": ["rev-parse", "--verify", "--quiet",
                   f"{OTHER_SHA}^{{commit}}"],
        "digest": ["ls-tree", "-r", "-z", OTHER_SHA],
    }
    every = (GITLINK, COMMIT, DIGEST)
    for name, tail in calls.items():
        argv = [*before, *tail]
        assert [n for n, picks in every if picks(argv)] == [name], argv
    fallback = [*before, "ls-tree", "HEAD", "--", "spec"]
    assert [n for n, picks in every if picks(fallback)] == []


@RUNS
@pytest.mark.parametrize(
    "error", [NO_GIT, NOT_EXECUTABLE, CANNOT_EXECUTE, NO_FILE_NAMED,
              NOT_EXECUTABLE_NO_FILE_NAMED, WIN_ERROR_193],
    ids=["no-git", "git-not-executable", "git-cannot-execute",
         "no-file-named", "not-executable-no-file-named", "winerror-193"])
def test_no_git_at_all_is_one_refusal_in_every_run(
        validator, project, monkeypatch, capsys, extra, error):
    """A SCAFFOLDED ROOT AND NO GIT: the first check to run git is the first
    leg's gitlink, so that is the check named. Exit 2 and the one code, where
    main ended in a traceback and exit 1."""
    git_fails(validator, monkeypatch, error)
    code, out, err = run(validator, project, capsys, *extra)
    assert code == 2, err
    assert out == ""
    assert err == [
        "REFUSED git-not-runnable: the spec leg's gitlink recorded at "
        f"'spec' could not be read: git could not be run ({error.strerror})",
        REMEDIATION]


@CALLS
@pytest.mark.parametrize("error", [NO_GIT, NOT_EXECUTABLE, CANNOT_EXECUTE],
                         ids=["no-git", "git-not-executable",
                              "git-cannot-execute"])
def test_each_call_that_runs_git_names_the_check_it_is(
        validator, project, monkeypatch, capsys, call, error):
    """GIT FAILS IN ONE CALL AND RUNS IN THE REST, so every check before it
    passes and the one that met the missing git is the one named: the leg's
    gitlink, then the pinned commit's lookup in the submodule, then the tree
    digest at that commit."""
    commit = spec_commit(project)[:12]
    says = {
        "gitlink": "the spec leg's gitlink recorded at 'spec' could not be "
                   "read",
        "commit": f"spec: the pinned commit {commit} could not be looked up "
                  "in that submodule",
        "digest": f"spec: the tree digest at {commit} could not be "
                  "recomputed",
    }
    git_fails(validator, monkeypatch, error, call)
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert err == [
        f"REFUSED git-not-runnable: {says[call[0]]}: git could not be run "
        f"({error.strerror})", REMEDIATION]


def test_a_missing_git_is_not_read_as_no_gitlink(
        validator, project, monkeypatch, capsys):
    """`recorded_gitlink` answers `None`, which the validator refuses as
    `pin-gitlink-absent` ("declare it as a submodule"), when git RAN and
    listed nothing. Its `except Refusal` is for a git that ran and exited
    non-zero; a git that never started is no `Refusal`, passes straight
    through it, and must not be said to be an absent gitlink."""
    git_fails(validator, monkeypatch, NO_GIT, GITLINK)
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert "pin-gitlink-absent" not in "\n".join(err)
    assert err[0].startswith("REFUSED git-not-runnable: ")


def test_a_gitlink_the_root_does_not_record_is_still_pin_gitlink_absent(
        validator, project, capsys):
    """THE CONTROL: with git running, a root that records no gitlink for a
    leg it declares is still the refusal it always was, so the test above is
    about the missing git and not about a check that no longer asks."""
    git("rm", "--cached", "-q", "--", "spec", cwd=project)
    git("commit", "-q", "-m", "stop recording the spec leg", cwd=project)
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert err[0].startswith("REFUSED pin-gitlink-absent: "), err
    assert "git-not-runnable" not in "\n".join(err)


def test_a_missing_git_is_not_read_as_an_unresolvable_commit(
        validator, project, monkeypatch, capsys):
    """The lookup's own `except Refusal` says the commit is not in the
    submodule's object store, which tells the operator to fetch it. A git
    that never started says nothing about the object store."""
    git_fails(validator, monkeypatch, NO_GIT, COMMIT)
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert "pin-commit-unresolvable" not in "\n".join(err)
    assert err[0].startswith("REFUSED git-not-runnable: ")


def test_a_commit_git_cannot_find_is_still_pin_commit_unresolvable(
        validator, project, capsys):
    """THE CONTROL: the gitlink and the pin both name a commit the submodule
    does not hold, and git runs and says so, so the refusal is the
    unresolvable commit it always was."""
    old = spec_commit(project)
    git("update-index", "--cacheinfo", f"160000,{OTHER_SHA},spec", cwd=project)
    pin = project / "contracts" / "spec-pin.yaml"
    text = pin.read_text(encoding="utf-8")
    assert text.count(old) == 1, "fixture drift: the pin names its commit once"
    pin.write_bytes(text.replace(old, OTHER_SHA).encode("utf-8"))
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert err[0].startswith("REFUSED pin-commit-unresolvable: "), err
    assert "git-not-runnable" not in "\n".join(err)


@RUNS
def test_with_git_running_the_same_root_says_pins_ok(
        validator, project, monkeypatch, capsys, extra):
    """THE CONTROL OF THE WHOLE FILE: the same root, through the same
    harness, with a `git_out` that fails for no call at all. It is the fake
    that forwards, not the validator, that this exit 0 vouches for."""
    git_fails(validator, monkeypatch, NO_GIT, ("none", lambda args: False))
    code, out, err = run(validator, project, capsys, *extra)
    assert code == 0, out + "\n".join(err)
    assert err == []
    assert out.splitlines()[-1] == "pins ok"
    # `--quiet` is the one run that prints no `ok` note before it.
    assert ("  ok  " in out) is (extra != ("--quiet",))


#: What else can go wrong inside a call that runs git, and is not a git that
#: will not start: the directory git was to run in, which `subprocess` names
#: in `filename` where it names `git` for a program (here the leg's submodule,
#: the directory two of the three calls run in, as a submodule nobody may
#: enter), and errors that name no file and are none of the three that
#: Windows' `CreateProcess` raises for a git it cannot start (an `ENOEXEC`
#: with no name is the one a reader might expect to count, and does not: the
#: nameless errors that count are those two classes and `WIN_ERROR_193`, which
#: carries its `winerror`). Built in the test, which knows the paths.
NOT_GIT = {
    "unreadable-directory": lambda root: PermissionError(
        errno.EACCES, "Permission denied", str(root / "spec")),
    "missing-directory": lambda root: FileNotFoundError(
        errno.ENOENT, "No such file or directory", str(root / "spec")),
    "not-a-directory": lambda root: NotADirectoryError(
        errno.ENOTDIR, "Not a directory", str(root / "spec")),
    "io-error": lambda root: OSError(errno.EIO, "Input/output error"),
    "out-of-memory": lambda root: OSError(errno.ENOMEM,
                                          "Cannot allocate memory"),
    "exec-format-error-naming-no-file": lambda root: OSError(
        errno.ENOEXEC, "Exec format error"),
    "exec-format-error-naming-a-directory": lambda root: OSError(
        errno.ENOEXEC, "Exec format error", str(root / "spec")),
}


@CALLS
@pytest.mark.parametrize("make", NOT_GIT.values(), ids=NOT_GIT.keys())
def test_an_oserror_that_is_not_a_missing_git_leaves_the_wrapper_unchanged(
        validator, project, monkeypatch, capsys, call, make):
    """THE REVIEW OF #406: its wrapper caught every `OSError` and told an
    operator whose directory nobody could read to put git on PATH. Here the
    error leaves the wrapper as it entered, at each of the three calls: no
    refusal, no `git-not-runnable`, and so nothing that sends that operator
    after the wrong thing. What the validator does with it instead is what it
    always did, and is not this change's to decide."""
    error = make(project)
    git_fails(validator, monkeypatch, error, call)
    with pytest.raises(OSError) as caught:
        validator.main(["--root", str(project)])
    assert caught.value is error
    out, err = capsys.readouterr()
    assert "git-not-runnable" not in out + err


@WINDOWS_SKIP
def test_a_real_missing_git_is_the_error_the_wrapper_counts(
        validator, project, monkeypatch, tmp_path, capsys):
    """THE ONE TEST WITH NO FAKE. The rest hand the validator an error built
    the way `subprocess` builds it, which is this change's reading of
    `subprocess`, not a fact about it. Here PATH names an empty directory and
    the real `subprocess.run` is asked for `git`: whatever it raises is what
    the wrapper must count, and the run must end in the refusal. It changes
    PATH, in this process only and put back, and skips on Windows, where the
    program search is not PATH's alone and an emptied PATH is not git absent
    on every machine."""
    nowhere = tmp_path / "no-git"
    nowhere.mkdir()
    monkeypatch.setenv("PATH", str(nowhere))
    code, out, err = run(validator, project, capsys)
    assert code == 2, err
    assert err == [
        "REFUSED git-not-runnable: the spec leg's gitlink recorded at "
        "'spec' could not be read: git could not be run (No such file or "
        "directory)", REMEDIATION]
