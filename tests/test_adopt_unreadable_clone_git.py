# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py`: a plan's `source.local_path` whose `.git` this user
cannot read is refused by name, never called a clone that is no longer
whole, and never cloned again (#1099).

ON 4ed7c7bf5 (2026-10-21), Python 3.12.3, git 2.43.0, a non-root user, a
stub `gh` that records and refuses every call, and local remotes, with the
plan's `source.local_path` a directory this user can enter and its `.git` at
mode 000:

- recorded as a clone `plan` made (`source.cloned: true`), `check` and
  `execute --yes` printed "NOTE the plan's `source.local_path`, ..., is a
  clone `plan` made that is no longer whole (git finds no repository
  there), so its `source.repository`, testorg/Thing, is cloned again from
  GitHub" and "cloning testorg/Thing", and asked `gh repo clone` once. A
  `.git` that is a file (`gitdir:`) at mode 000 did the same.
- recorded with `source.cloned: false`: `REFUSED git-failed`, "`git
  rev-parse --is-inside-git-dir` in ... exited 128: fatal: not a git
  repository", or, for a `.git` file, "fatal: error opening '.../.git':
  Permission denied".

Git says "not a git repository" of a `.git` it cannot read, as it says of a
clone emptied, so its exit cannot tell the two apart. Now each is
`source-unreadable`, naming that `.git` and the operating system's reason,
with the cure for a directory or for a file, before anything is cloned, and
`gh` is never asked. A `.git` this user can read is read as before, and a
directory this user cannot enter is still named by itself (#918).

A real mode runs in a child, skipped on Windows and as root (`needs_a_mode`),
as `tests/test_adopt_unenterable_source_and_locale.py` runs it. The same
refusal is asked in-process with the `stat` of `.git/HEAD` refused, which
runs everywhere.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
from pathlib import Path

import pytest

from conftest import (ADOPT, git, load_without_bytecode, make_source_repo,
                      run_script, spelled)
from test_adopt_temp_work_roots import (PROJECT, SMALL_TREE,
                                        planned_from_github, recorded)
from test_adopt_unsearchable_source import (CURE, DENIED, UNREADABLE, URL,
                                            needs_a_mode, planned_locally,
                                            recording_gh, run, said)

DIRECTORY, FILE = "directory", "file"
#: What `source-unreadable` cannot tell of the `.git`, by `source.cloned`.
UNTOLD = {False: "whether a repository is there",
          True: "whether `plan`'s clone is still whole, to be read, or no "
                "longer whole, to be cloned again,"}
#: The way out, by what the `.git` is.
CURES = {DIRECTORY: CURE,
         FILE: ("Make it readable by this user: `chmod u+r` on the file and "
                "`chmod u+rx` on every directory above it, or fix who owns "
                "them. Then run the same command again")}
#: The way past it that names the source otherwise.
INSTEAD = ("or pass the source again with --source, which is held to the "
           "plan's `commit:`.")
#: What 4ed7c7bf5 said of such a `.git`, by `source.cloned`.
FALSE_ANSWERS = ("Traceback", "that is no longer whole",
                 "git finds no repository there", "is cloned again from",
                 "cloning ", "git-failed", "not a git repository",
                 "error opening", "plan-source-gone", "source-unclonable")


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "adopt_unreadable_clone_git")


def a_clone(tmp_path: Path, kind: str) -> Path:
    """A clone of a small source, at `<tmp>/Thing`, whose `origin` is the
    GitHub url `plan` records as `source.repository`. Its `.git` is a
    directory, or, for `FILE`, a file naming the git directory
    `<tmp>/store.git`, as `git clone --separate-git-dir` leaves it."""
    origin = make_source_repo(tmp_path / "origin" / PROJECT, tree=SMALL_TREE,
                              edits=())
    clone = tmp_path / PROJECT
    apart = ["--separate-git-dir", str(tmp_path / "store.git")] \
        if kind == FILE else []
    git("clone", "-q", *apart, str(origin), str(clone), cwd=tmp_path)
    git("remote", "set-url", "origin", f"{URL}.git", cwd=clone)
    assert (clone / ".git").is_file() is (kind == FILE), "premise"
    return clone


@contextlib.contextmanager
def at_mode_000(path: Path):
    """`path` at mode 000 for the `with`, its mode given back in a `finally`.
    The mode is asserted to bite: a file system that ignores modes would pass
    every row here for the wrong reason."""
    before = stat.S_IMODE(path.stat().st_mode)
    path.chmod(0)
    try:
        assert not os.access(path, os.R_OK), path
        yield path
    finally:
        path.chmod(before)


def refused_head(monkeypatch, clone: str) -> None:
    """`os.stat` of `<clone>/.git/HEAD` refused, `Permission denied`, as the
    operating system refuses it where that `.git` cannot be searched; every
    other `stat` is the real one, and git itself reads the clone."""
    head = os.path.normcase(os.path.join(clone, ".git", "HEAD"))
    real = os.stat

    def refusing(path, *args, **kwargs):
        if not isinstance(path, int) and \
                os.path.normcase(os.fsdecode(path)) == head:
            raise PermissionError(errno.EACCES, "Permission denied",
                                  os.fsdecode(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "stat", refusing)


def the_refusal(local_path: str, cloned: bool) -> str:
    """The line `source-unreadable` names the recorded `.git` with."""
    return (f"{UNREADABLE}the `.git` in the plan's `source.local_path`, "
            f"{spelled(os.path.join(local_path, '.git'))}: {DENIED}, so "
            f"{UNTOLD[cloned]} cannot be told")


def assert_no_false_answer(text: str) -> None:
    """None of the words 4ed7c7bf5 said of such a `.git`."""
    for words in FALSE_ANSWERS:
        assert words not in text, (words, text)


@needs_a_mode
@pytest.mark.parametrize("kind", [DIRECTORY, FILE])
@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
@pytest.mark.parametrize("verb", ["check", "execute"])
def test_a_recorded_git_this_user_cannot_read_is_refused_by_name(
        tmp_path, verb, cloned, kind):
    """The plan's `source.local_path` holds a `.git` at mode 000: on
    4ed7c7bf5 a clone `plan` made was "no longer whole (git finds no
    repository there)" and cloned again, `gh` asked, and any other was
    `git-failed`. Now `source-unreadable`, naming the `.git`, in `check` and
    `execute` alike; nothing is cloned or made and `gh` is never asked."""
    clone = a_clone(tmp_path, kind)
    plan = planned_locally(tmp_path, clone, cloned)
    local_path = str(recorded(plan)["local_path"])
    env, log = recording_gh(tmp_path / "gh-bin")
    work = tmp_path / f"{verb}-work"

    with at_mode_000(clone / ".git"):
        proc = run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                          str(work), "--local-remote-dir",
                          str(tmp_path / "remotes"),
                          *(["--yes"] if verb == "execute" else []), env=env)

    assert proc.returncode == 2, said(proc)
    assert the_refusal(local_path, cloned) in proc.stderr
    assert CURES[kind] in proc.stderr
    assert INSTEAD in proc.stderr
    assert_no_false_answer(said(proc))
    assert log.read_bytes() == b""
    assert not (work / "source-readonly").exists()
    assert not (tmp_path / "remotes").exists()


@pytest.mark.parametrize("kind", [DIRECTORY, FILE])
@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
def test_a_recorded_git_this_user_can_read_is_read_as_before(
        tmp_path, cloned, kind):
    """The same plans with the `.git` as `git clone` left it: `plan ok`, as
    on 4ed7c7bf5, read in place and `gh` never asked."""
    clone = a_clone(tmp_path, kind)
    plan = planned_locally(tmp_path, clone, cloned)
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = run_script(ADOPT, "check", "--plan", str(plan), "--work-dir",
                      str(tmp_path / "check-work"), "--local-remote-dir",
                      str(tmp_path / "remotes"), env=env)

    assert proc.returncode == 0, said(proc)
    assert "plan ok" in proc.stdout
    assert "source-unreadable" not in said(proc)
    assert log.read_bytes() == b""


def test_a_recorded_clone_whose_git_is_refused_is_not_cloned_again(
        adopter, monkeypatch, capsys, tmp_path):
    """`plan --source testorg/Thing` records its clone, and the `stat` of its
    `.git/HEAD` is refused: `source-unreadable`, naming the `.git`, and no
    second clone is asked for. In-process, so it runs as root and on
    Windows too."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    assert len(planned.calls) == 1, planned.calls
    refused_head(monkeypatch, planned.clone)

    code, out, err = run(adopter, capsys, "check", "--plan",
                         str(planned.plan), "--work-dir",
                         str(tmp_path / "check-work"), "--local-remote-dir",
                         str(tmp_path / "remotes"))

    assert code == 2, out + err
    assert the_refusal(planned.clone, True) in err
    assert CURES[DIRECTORY] in err
    assert_no_false_answer(out + err)
    assert len(planned.calls) == 1, planned.calls


@pytest.mark.parametrize("held", ["nothing", "a-git-directory", "a-git-file",
                                  "a-git-directory-with-no-head", "a-file"])
def test_a_git_that_can_be_read_or_is_not_there_is_gits_question(
        adopter, tmp_path, held):
    """`_git_refused` answers only for a `.git` the operating system refuses:
    where there is none, where git can be let into it, where it holds no
    `HEAD`, as a clone emptied, and where the source is a file, it leaves the
    question to git, as before."""
    if held == "a-git-directory":
        path = a_clone(tmp_path, DIRECTORY)
    elif held == "a-git-file":
        path = a_clone(tmp_path, FILE)
    elif held == "a-file":
        path = tmp_path / PROJECT
        path.write_bytes(b"not a directory\n")
    else:
        path = tmp_path / PROJECT
        path.mkdir()
        if held == "a-git-directory-with-no-head":
            (path / ".git").mkdir()

    assert adopter._git_refused(path) is None
