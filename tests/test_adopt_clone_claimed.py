# SPDX-License-Identifier: Apache-2.0
"""The clone `plan` and `check` make in the work directory is claimed by this
run, and removed only as what this run made (#803: L1-65, L1-97, L1-98,
L1-99 and L1-102 of #457).

ON MAIN AT bf1f099b (2026-10-17), with a stand-in `gh`:
- L1-99 (b). `_leave_the_clones` asked the clone's real path, then
  `_remove_a_tree` removed it by that path: `W/source-readonly`, swapped for
  a symlink to `victim/` between the two, removed `victim/Thing`.
- L1-99 (a). A removal skipped because the path led elsewhere said nothing.
- L1-98. A run whose clone failed removed the clone another run on the same
  `--work-dir` had made there since, and that run's plan recorded it.
- L1-97. `check --source <org/repo>` removed its clone where it had made it
  at the plan's own `source.local_path`.
- L1-102. The clone's recorded path and its real path were compared with
  `!=`, which on Windows reads the disk's case on one side only.
- L1-65. A file at `W/source-readonly` ended `plan`, `check` and `execute`
  in a `FileExistsError` traceback.
- A `--work-dir`, or a `source-readonly/` in it, that another user owns or
  every user can write in was used as any other.

NO NETWORK AND NO GITHUB: `gh repo clone` is a `git clone` of a repository
on disk (`gh_clones`), or a stub `gh` that fails (the race). Every directory
a test swaps in or moves is under its own `tmp_path`.
"""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from conftest import ADOPT, WINDOWS_SKIP, spelled
from test_adopt_source_clone_record import (
    MINE, OCCUPIED, SOURCE_READONLY, WORK, WORK_FLAG, clone_dir, on_github,
    plan_args, run, symlinks_are_made,
)
from test_adopt_temp_work_roots import (  # noqa: F401
    CHECK, EXECUTE, LOCAL_REMOTE_DIR, ORG, PLAN, PLAN_FLAG, PLAN_VERB, PROJECT,
    REMOTES, REPOSITORY, SOURCE_FLAG, adopter, planned_from_github,
)

SHARED = "REFUSED adopt-work-dir-shared: "
UNWRITABLE = "REFUSED adopt-work-dir-unwritable: "
UNCLONABLE = "REFUSED source-unclonable: "
#: `execute`'s word, before its way out, that nothing exists yet.
NOTHING_PUSHED = "no leg repository was created and nothing was pushed. "
ANOTHER = ("Pass a --work-dir that does not hold it, or none: without one, "
           "each run makes a new one.")
OWN = ("Pass a --work-dir this user owns and no other user can write in, or "
       "none: without one, each run makes a new one.")
EVERY_USER = "can be written in by every user, without the sticky bit"
#: The NOTE for a clone the run made and did not remove, up to its path.
NOT_REMOVED = "NOTE the clone this run made, "
NOT_MADE_HERE = ("what that path leads to now is not the directory this run "
                 "made, so nothing is removed through it.")
PRECIOUS = "precious.txt"
SWAPS = ["symlink", "directory"]
posix_only = pytest.mark.skipif(
    not hasattr(os, "geteuid"),
    reason="Windows asks no owner and no mode of a directory")


def real(path: Path) -> Path:
    return Path(os.path.realpath(path))


def the_clone_of(work: Path) -> Path:
    """`clone_dir`, as the NOTE spells the path this run made."""
    return real(work) / SOURCE_READONLY / PROJECT


def victim_holding(base: Path) -> Path:
    """`base/victim`, holding `Thing/precious.txt`: a directory of the
    person's own, outside every work directory."""
    victim = base / "victim"
    (victim / PROJECT).mkdir(parents=True)
    (victim / PROJECT / PRECIOUS).write_text(MINE, encoding="utf-8")
    return victim


def swap(work: Path, aside: Path, victim: Path, how: str) -> None:
    """`work/source-readonly` moved to `aside`, and in its place a symlink to
    `victim`, or `victim` itself moved there."""
    os.rename(work / SOURCE_READONLY, aside)
    if how == "symlink":
        os.symlink(victim, work / SOURCE_READONLY, target_is_directory=True)
    else:
        os.rename(victim, work / SOURCE_READONLY)


def checked_with_source(planned, work: Path) -> list[str]:
    return [CHECK, PLAN_FLAG, str(planned.plan), SOURCE_FLAG, REPOSITORY,
            WORK_FLAG, str(work)]


def argv_for(command: str, planned, work: Path, base: Path) -> list[str]:
    """`command` given `--source REPOSITORY --work-dir work`."""
    if command == PLAN_VERB:
        return plan_args(REPOSITORY, base / "again.yaml", WORK_FLAG, str(work))
    argv = checked_with_source(planned, work)
    if command == EXECUTE:
        argv[0] = EXECUTE
        argv += [LOCAL_REMOTE_DIR, str(base / REMOTES)]
    return argv


# --- L1-99 (b): a swap at the removal removes nothing of anybody's -----------

@pytest.mark.parametrize("how", SWAPS)
def test_a_swap_as_the_removal_starts_removes_nothing_outside_the_clone(
        adopter, monkeypatch, capsys, tmp_path, how):
    """t111c's injection: `source-readonly` swapped at the start of
    `_remove_a_tree`, for a symlink to `victim/` or for `victim/` itself. On
    main `check` exited 0 and removed `victim/Thing` with the file in it.
    Now the removal finds no longer the directory this run made, says so,
    and removes nothing."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    if how == "symlink":
        symlinks_are_made(tmp_path)
    work, aside = tmp_path / WORK, tmp_path / "aside"
    victim = victim_holding(tmp_path)
    precious = (victim if how == "symlink" else work / SOURCE_READONLY) \
        / PROJECT / PRECIOUS
    made_at = the_clone_of(work)
    removal = adopter._remove_a_tree

    def swapped_first(*args, **keywords):
        swap(work, aside, victim, how)
        return removal(*args, **keywords)

    monkeypatch.setattr(adopter, "_remove_a_tree", swapped_first)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 0, err
    assert precious.read_text(encoding="utf-8") == MINE
    assert f"{NOT_REMOVED}{spelled(made_at)}, is not removed: " \
           f"{NOT_MADE_HERE}" in err.splitlines(), err
    assert (aside / PROJECT / ".git").is_dir()


def test_a_swap_after_the_checks_removes_only_the_runs_own_clone(
        adopter, monkeypatch, capsys, tmp_path):
    """The window between the last check and the removal: `source-readonly`
    swapped for a symlink to `victim/` as `shutil.rmtree` is called. The
    removal is relative to the directory this run made, held open, so it
    removes the run's own clone, moved aside, and nothing through the link.
    Where the removal is by path (Python 3.9 and 3.10, and Windows) this
    window stays open, and the test cannot close it."""
    if not getattr(adopter, "FD_REMOVAL", True):
        pytest.skip("this Python removes a clone by its path: the window "
                    "between the check and the removal stays open")
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    symlinks_are_made(tmp_path)
    work, aside = tmp_path / WORK, tmp_path / "aside"
    victim = victim_holding(tmp_path)
    removal = adopter.shutil.rmtree

    def swapped_first(path, *args, **keywords):
        if os.path.basename(path) == PROJECT and not aside.exists():
            swap(work, aside, victim, "symlink")
        return removal(path, *args, **keywords)

    monkeypatch.setattr(adopter.shutil, "rmtree", swapped_first)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 0, err
    assert (victim / PROJECT / PRECIOUS).read_text(encoding="utf-8") == MINE
    assert not os.path.lexists(aside / PROJECT)


# --- L1-99 (a): a removal skipped is named -----------------------------------

def test_a_source_readonly_swapped_for_a_symlink_is_named_and_kept(
        adopter, monkeypatch, capsys, tmp_path):
    """`W/source-readonly` swapped for a symlink to `bigdisk/` once the
    clone was read: the clone's path now leads elsewhere, so nothing is
    removed through it, and a NOTE says so. On main the skip was a bare
    `continue`, and stderr was empty."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    symlinks_are_made(tmp_path)
    work, aside = tmp_path / WORK, tmp_path / "aside"
    bigdisk = tmp_path / "bigdisk"
    bigdisk.mkdir()
    made_at = the_clone_of(work)
    leaving = adopter._leave_the_clones

    def swapped_first(args):
        swap(work, aside, bigdisk, "symlink")
        return leaving(args)

    monkeypatch.setattr(adopter, "_leave_the_clones", swapped_first)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 0, err
    assert (f"{NOT_REMOVED}{spelled(made_at)}, is not removed: that path now "
            f"leads to {spelled(real(bigdisk) / PROJECT)}, so nothing is "
            "removed through it.") in err.splitlines(), err
    assert (aside / PROJECT / ".git").is_dir()
    assert os.listdir(bigdisk) == []


# --- L1-98: a run claims its clone's directory --------------------------------

#: A `gh` that says it started, then waits, at most a minute, for the test
#: to let it go, and fails: the run whose clone fails late.
LATE_GH = (b"#!/bin/sh\n"
           b": > \"$W803_STARTED\"\n"
           b"i=0\n"
           b"while [ ! -e \"$W803_GO\" ] && [ $i -lt 600 ]; do\n"
           b"  sleep 0.1\n"
           b"  i=$((i + 1))\n"
           b"done\n"
           b"echo 'stub gh: could not clone' >&2\n"
           b"exit 1\n")


def wait_for(path: Path, child: subprocess.Popen) -> None:
    """Until `path` exists, a minute at most, while `child` runs."""
    for _ in range(600):
        if path.exists() or child.poll() is not None:
            break
        time.sleep(0.1)
    assert path.exists(), child.communicate()


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_a_run_never_takes_the_clone_another_run_on_its_work_dir_claimed(
        adopter, monkeypatch, capsys, tmp_path):
    """Run A, `check --source testorg/Thing --work-dir W`, is in `gh` when
    run B, `plan --source testorg/Thing --work-dir W`, starts; then A's
    clone fails. On main B cloned into the directory A was about to clone
    into and wrote its plan, and A then removed B's clone. Now A made that
    directory first, so B is refused it, and A removes only what it made."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    stub = tmp_path / "late-bin"
    stub.mkdir()
    (stub / "gh").write_bytes(LATE_GH)
    (stub / "gh").chmod(0o755)
    (tmp_path / "gh-config").mkdir()
    started, go = tmp_path / "started", tmp_path / "go"
    env = {**os.environ, "W803_STARTED": str(started), "W803_GO": str(go),
           "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
           "GH_TOKEN": "bogus-w803", "GH_CONFIG_DIR": str(tmp_path / "gh-config")}
    first = subprocess.Popen(  # noqa: S603 - this interpreter, this tool
        [sys.executable, str(ADOPT), *checked_with_source(planned, work)],
        cwd=str(tmp_path), env=env, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(started, first)
        second = tmp_path / "second.yaml"
        code, _, err = run(adopter, capsys,
                           *plan_args(REPOSITORY, second, WORK_FLAG, str(work)))
    finally:
        go.touch()
        _, first_err = first.communicate(timeout=120)
    assert code == 2, err
    assert err.startswith(
        f"{OCCUPIED}--work-dir {spelled(real(work))} already holds "
        f"`{SOURCE_READONLY}/{PROJECT}`, an empty directory, "), err
    assert not second.exists()
    assert len(planned.calls) == 1
    assert first.returncode == 2, first_err
    assert UNCLONABLE in first_err
    assert not os.path.lexists(work / SOURCE_READONLY)


def test_an_empty_directory_where_the_clone_goes_is_refused_and_kept(
        adopter, monkeypatch, capsys, tmp_path):
    """A directory already there is never taken for this run's own: on main
    `plan` cloned into an empty one and listed none of it."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    clone_dir(work).mkdir(parents=True)
    code, _, err = run(adopter, capsys, *plan_args(
        REPOSITORY, tmp_path / PLAN, WORK_FLAG, str(work)))
    assert code == 2, err
    assert err == (
        f"{OCCUPIED}--work-dir {spelled(real(work))} already holds "
        f"`{SOURCE_READONLY}/{PROJECT}`, an empty directory, where this run "
        f"clones {REPOSITORY}, and a run clones only into a directory it has "
        "just made, so that it never takes another run's for its own\n"
        f"Remediation: {ANOTHER}\n")
    assert calls == []
    assert clone_dir(work).is_dir()


def test_execute_whose_clone_fails_removes_what_it_made_and_no_more(
        adopter, monkeypatch, capsys, tmp_path):
    """`execute` keeps the clone it makes, so it lists none. Its claim on
    the clone's directory is made before `gh`, and a clone that fails leaves
    that directory empty: it removes what its own `mkdir` made, so that the
    same command run again is not refused at it. What the person keeps in
    the work directory stays."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir()
    (work / "mine.txt").write_text(MINE, encoding="utf-8")
    argv = [EXECUTE, PLAN_FLAG, str(planned.plan), SOURCE_FLAG,
            f"{ORG}/Elsewhere", WORK_FLAG, str(work), LOCAL_REMOTE_DIR,
            str(tmp_path / REMOTES)]
    for _ in range(2):
        code, _, err = run(adopter, capsys, *argv)
        assert code == 2, err
        assert err.startswith(UNCLONABLE), err
    assert sorted(os.listdir(work)) == ["mine.txt"]


# --- L1-97: the plan's own record is kept -------------------------------------

def test_a_source_clone_made_at_the_plans_own_record_is_kept(
        adopter, monkeypatch, capsys, tmp_path):
    """The plan records `W/source-readonly/Thing`, moved away since. `check
    --source testorg/Thing --work-dir W` clones there again, which is the
    plan's source again: kept, as the same `check` without `--source` keeps
    it. On main it was removed, and the next run cloned it once more."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work, plan = tmp_path / WORK, tmp_path / PLAN
    assert run(adopter, capsys, *plan_args(REPOSITORY, plan, WORK_FLAG,
                                           str(work)))[0] == 0
    os.rename(clone_dir(work), tmp_path / "moved")
    code, _, err = run(adopter, capsys, CHECK, PLAN_FLAG, str(plan),
                       SOURCE_FLAG, REPOSITORY, WORK_FLAG, str(work))
    assert code == 0, err
    assert (clone_dir(work) / ".git").is_dir()
    assert len(calls) == 2


# --- L1-102: the clone's path is compared as the platform compares names -----

def test_the_clones_path_is_compared_whatever_its_case(
        adopter, monkeypatch, capsys, tmp_path):
    """On Windows `os.path.realpath` gives the disk's case, here
    `Source-Readonly`, and the recorded path was spelled `source-readonly`:
    on main the two differed, and the clone was kept, silently. Emulated
    with `os.path` patched as `ntpath` answers, during the removal only."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    made_at = the_clone_of(work)
    leaving, realpath = adopter._leave_the_clones, os.path.realpath

    def as_windows_reads_it(args):
        with monkeypatch.context() as patched:
            patched.setattr(os.path, "normcase", str.lower)
            patched.setattr(os.path, "realpath", lambda path, *rest, **kw: (
                realpath(path, *rest, **kw).replace(
                    SOURCE_READONLY, "Source-Readonly")))
            return leaving(args)

    monkeypatch.setattr(adopter, "_leave_the_clones", as_windows_reads_it)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 0, err
    assert NOT_REMOVED not in err
    assert not os.path.lexists(made_at)


# --- L1-65 and the work directory's own `source-readonly` --------------------

@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_a_file_at_source_readonly_is_refused_by_name_before_gh(
        adopter, monkeypatch, capsys, tmp_path, command):
    """On main each command ended in `FileExistsError: [Errno 17] File
    exists: '<work-dir>/source-readonly'`, exit 1. Now it is refused by
    name, before any `gh` call, and the file stays."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir()
    (work / SOURCE_READONLY).write_text(MINE, encoding="utf-8")
    done = NOTHING_PUSHED if command == EXECUTE else ""
    code, _, err = run(adopter, capsys,
                       *argv_for(command, planned, work, tmp_path))
    assert code == 2, err
    assert err == (
        f"{OCCUPIED}--work-dir {spelled(real(work))} already holds "
        f"`{SOURCE_READONLY}`, a file, where this run clones {REPOSITORY} "
        f"into a directory of its own\nRemediation: {done}{ANOTHER}\n")
    assert len(planned.calls) == 1
    assert (work / SOURCE_READONLY).read_text(encoding="utf-8") == MINE


INJECTED = {
    "a-file-made-since": (
        "file", OCCUPIED, "already holds `source-readonly`, a file, where this "
        f"run clones {REPOSITORY} into a directory of its own", ANOTHER),
    "a-mkdir-refused": (
        "refused", UNWRITABLE, "cannot hold `source-readonly`, where this run "
        f"clones {REPOSITORY}: making it failed (Permission denied)",
        "Pass a --work-dir this user can write in, or none: without one, "
        "each run makes a new one."),
}


@pytest.mark.parametrize(("what", "refused", "detail", "remedy"),
                         list(INJECTED.values()), ids=list(INJECTED))
def test_a_source_readonly_that_cannot_be_made_is_refused_by_name(
        adopter, monkeypatch, capsys, tmp_path, what, refused, detail, remedy):
    """Asked before the NOTE, `source-readonly` was free; then its `mkdir`
    failed: a file made there since, or the system refusing it. Each is
    refused by name, before `gh`. On main each was a traceback."""
    calls = on_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    mkdir = os.mkdir

    def in_the_way(path, *args, **keywords):
        if os.path.basename(path) == SOURCE_READONLY:
            if what == "refused":
                raise PermissionError(errno.EACCES, "Permission denied", path)
            Path(path).write_text(MINE, encoding="utf-8")
        return mkdir(path, *args, **keywords)

    monkeypatch.setattr(os, "mkdir", in_the_way)
    code, _, err = run(adopter, capsys, *plan_args(
        REPOSITORY, tmp_path / PLAN, WORK_FLAG, str(work)))
    assert code == 2, err
    assert err == (f"{refused}--work-dir {spelled(real(work))} {detail}\n"
                   f"Remediation: {remedy}\n")
    assert calls == []


# --- decision 1: a directory another user can rename in ----------------------

@posix_only
@pytest.mark.parametrize("command", [PLAN_VERB, CHECK, EXECUTE])
def test_a_work_dir_every_user_can_write_in_is_refused_before_anything(
        adopter, monkeypatch, capsys, tmp_path, command):
    """`chmod 777`, no sticky bit: another user can rename anything in it,
    the clone included. Refused before anything is made there, the write
    probe included, and before `gh`. On main each command used it."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir()
    os.chmod(work, 0o777)
    done = NOTHING_PUSHED if command == EXECUTE else ""
    code, _, err = run(adopter, capsys,
                       *argv_for(command, planned, work, tmp_path))
    assert code == 2, err
    assert err == (
        f"{SHARED}--work-dir {spelled(real(work))} {EVERY_USER}, so another "
        "user could rename or replace what this run makes in it\n"
        f"Remediation: {done}{OWN}\n")
    assert os.listdir(work) == []
    assert len(planned.calls) == 1


@posix_only
def test_a_source_readonly_every_user_can_write_in_is_refused(
        adopter, monkeypatch, capsys, tmp_path):
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    (work / SOURCE_READONLY).mkdir(parents=True)
    os.chmod(work / SOURCE_READONLY, 0o777)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 2, err
    assert err == (
        f"{SHARED}--work-dir {spelled(real(work))} holds `{SOURCE_READONLY}`, "
        f"which {EVERY_USER}, so another user could rename or replace the "
        f"clone this run makes in it\nRemediation: {ANOTHER}\n")
    assert os.listdir(work / SOURCE_READONLY) == []
    assert len(planned.calls) == 1


@posix_only
def test_the_sticky_bit_keeps_each_entry_to_its_owner(
        adopter, monkeypatch, capsys, tmp_path):
    """The control: a work directory and a `source-readonly` every user can
    write in, each with the sticky bit, as `/tmp` is. Nobody but this user
    can rename what this run makes there, so both are used, and the clone
    removed."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    (work / SOURCE_READONLY).mkdir(parents=True)
    for path in (work, work / SOURCE_READONLY):
        os.chmod(path, 0o1777)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 0, err
    assert os.listdir(work / SOURCE_READONLY) == []
    assert len(planned.calls) == 2


def owned_by_another(adopter, monkeypatch, path: Path) -> int:
    """`path` owned by another user: given away where this test runs as
    root, and otherwise told so by `os.lstat` for that path alone. The
    other user's id."""
    other = os.geteuid() + 1 if os.geteuid() else 65534
    if os.geteuid() == 0:
        os.chown(path, other, -1)
        return other
    lstat, which = os.lstat, os.path.realpath(path)

    def as_another_owns_it(target, *args, **keywords):
        status = lstat(target, *args, **keywords)
        if keywords.get("dir_fd") is None and not args \
                and os.fspath(target) == which:
            fields = list(status[:10])
            fields[4] = other
            return os.stat_result(fields)
        return status

    monkeypatch.setattr(os, "lstat", as_another_owns_it)
    return other


@posix_only
def test_a_source_readonly_another_user_owns_is_refused(
        adopter, monkeypatch, capsys, tmp_path):
    """The other user who made `source-readonly/` first owns the clone's
    parent, and can swap the clone or the removal. Refused by name, before
    `gh`."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    (work / SOURCE_READONLY).mkdir(parents=True)
    owned_by_another(adopter, monkeypatch, work / SOURCE_READONLY)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 2, err
    assert err.startswith(
        f"{SHARED}--work-dir {spelled(real(work))} holds `{SOURCE_READONLY}`, "
        "which is owned by "), err
    assert err.endswith(
        ", not by this user, so another user could rename or replace the "
        f"clone this run makes in it\nRemediation: {ANOTHER}\n"), err
    assert len(planned.calls) == 1


@posix_only
def test_a_work_dir_another_user_owns_is_refused(
        adopter, monkeypatch, capsys, tmp_path):
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir()
    owned_by_another(adopter, monkeypatch, work)
    code, _, err = run(adopter, capsys, *checked_with_source(planned, work))
    assert code == 2, err
    assert err.startswith(
        f"{SHARED}--work-dir {spelled(real(work))} is owned by "), err
    assert err.endswith(
        ", not by this user, so another user could rename or replace what "
        f"this run makes in it\nRemediation: {OWN}\n"), err
    assert os.listdir(work) == []
    assert len(planned.calls) == 1


@posix_only
def test_a_mode_this_run_makes_lets_no_other_user_write(
        adopter, monkeypatch, capsys, tmp_path):
    """`source-readonly` and the clone's directory are made 0755 whatever
    the umask, so a run under `umask 0` makes none another user can rename
    in. Asked as `then` reads it, right after the clone."""
    seen: dict = {}
    calls = on_github(adopter, monkeypatch, tmp_path)
    work = tmp_path / WORK
    work.mkdir(mode=0o755)
    real_run = adopter.run

    def and_look(args, *rest, **keywords):
        done = real_run(args, *rest, **keywords)
        if args[0] == "gh":
            seen.update({path: stat.S_IMODE(os.lstat(path).st_mode) & 0o022
                         for path in (work / SOURCE_READONLY, Path(args[4]))})
        return done

    monkeypatch.setattr(adopter, "run", and_look)
    before = os.umask(0)
    try:
        code, _, err = run(adopter, capsys, *plan_args(
            REPOSITORY, tmp_path / PLAN, WORK_FLAG, str(work)))
    finally:
        os.umask(before)
    assert code == 0, err
    assert len(calls) == 1
    assert set(seen.values()) == {0}
