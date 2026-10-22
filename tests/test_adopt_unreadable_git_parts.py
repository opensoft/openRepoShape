# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py`: a part of a repository git reads that this user cannot
read is refused by name, in `--source` and in a plan's `source.local_path`
alike, never `git-failed`, never called a clone that is no longer whole, and
never cloned again (#1151, beside #1099's `.git`).

ON 961640c68 (2026-10-22), Python 3.12.3, git 2.43.0, a non-root user, a
stub `gh` that records and refuses every call, and local remotes:

- `plan --source` and `check --plan --source` of a repository whose `.git`
  is at mode 000: `REFUSED git-failed: git rev-parse --is-inside-git-dir ...
  fatal: not a git repository`, or, for a `.git` file, "fatal: error opening
  '.../.git': Permission denied", naming no `.git`.
- a plan's `source.local_path` recorded as a clone `plan` made
  (`source.cloned: true`) whose `.git/HEAD`, `.git/objects`, `.git/refs` or
  `.git/config`, whose `gitdir:` target, a linked worktree's git directory
  or the common `.git` above it, a submodule's `.git/modules/<m>`, or a
  directory above a `.git` link's target was at mode 000: "NOTE ... is a
  clone `plan` made that is no longer whole (git finds no repository
  there), so its `source.repository`, testorg/Thing, is cloned again from
  GitHub", `cloning testorg/Thing`, `gh repo clone` asked once.
- the same recorded with `source.cloned: false`: `git-failed`, "not a git
  repository" or "unable to access '.git/config'".

Now each is `source-unreadable`, naming the part the operating system
refused and its reason, with the cure for a directory or for a file, before
anything is cloned, and `gh` is never asked. A repository git reads is read
as before, and a part git does not find is git's own question.

A real mode runs in a child, skipped on Windows and as root (`needs_a_mode`),
as `tests/test_adopt_unreadable_clone_git.py` runs #1099's. The same
questions are asked in-process with `git` failing and an `open` or an
`access` refused, which runs everywhere.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import (ADOPT, git, load_without_bytecode, make_source_repo,
                      run_script, spelled)
from test_adopt_temp_work_roots import (PLANNED, PROJECT, SMALL_TREE,
                                        planned_from_github, recorded)
from test_adopt_unsearchable_source import (CURE, DENIED, UNREADABLE, URL,
                                            needs_a_mode, needs_a_symlink,
                                            planned_locally, recording_gh, run,
                                            said)

#: The way out where the part refused is a file.
FILE_CURE = ("Make it readable by this user: `chmod u+r` on the file and "
             "`chmod u+rx` on every directory above it, or fix who owns "
             "them. Then run the same command again")
#: The way out where the operating system gave another reason.
OTHER_CURE = "which no `chmod` puts right: put right what it names"
#: What `source-unreadable` cannot tell, by `source.cloned`.
UNTOLD = {False: "whether a repository is there",
          True: "whether `plan`'s clone is still whole, to be read, or no "
                "longer whole, to be cloned again,"}
#: The way past it that names the source otherwise.
INSTEAD = ("or pass the source again with --source, which is held to the "
           "plan's `commit:`.")
#: How a plan's source is named before its path.
RECORDED_AS = "the plan's `source.local_path`"
#: What 961640c68 said of such a part, by `source.cloned`.
FALSE_ANSWERS = ("Traceback", "that is no longer whole",
                 "git finds no repository there", "is cloned again from",
                 "cloning ", "git-failed", "not a git repository",
                 "error opening", "unable to access", "plan-source-gone",
                 "source-unclonable", "source-not-top-level",
                 "git reads it as part of")
GIT_DIRECTORY_OF = "the git directory of"
ABOVE_GIT_DIRECTORY = "a directory above the git directory of"


@pytest.fixture(scope="module")
def adopter():
    return load_without_bytecode(ADOPT, "adopt_unreadable_git_parts")


class Part(NamedTuple):
    """A part of a repository a row puts at mode 000: its `path`; `role`,
    how `source-unreadable` names it before the source; `at`, where it is,
    from the source in the source's own `.git` and whole elsewhere; and the
    cure, a directory's or a file's."""
    path: Path
    role: str
    at: str
    cure: str


def whole(path: Path) -> str:
    """`path` as the refusal names a part outside the source's `.git`."""
    return os.path.realpath(path)


def a_clone(root: Path, apart: bool = False) -> Path:
    """A clone of a small source at `<root>/Thing`, its `origin` the GitHub
    url `plan` records; its `.git` a file naming `<root>/store.git` where
    `apart`, as `git clone --separate-git-dir` leaves it."""
    origin = make_source_repo(root / "origin" / PROJECT, tree=SMALL_TREE,
                              edits=())
    clone = root / PROJECT
    extra = ["--separate-git-dir", str(root / "store.git")] if apart else []
    git("clone", "-q", *extra, str(origin), str(clone), cwd=root)
    git("remote", "set-url", "origin", f"{URL}.git", cwd=clone)
    return clone


def directory_layout(root: Path) -> tuple[Path, dict[str, Part]]:
    """A clone whose `.git` is a directory, and the parts git reads in it."""
    clone = a_clone(root)
    dot_git = clone / ".git"
    return clone, {
        ".git": Part(dot_git, "the `.git` in", ".git", CURE),
        "HEAD": Part(dot_git / "HEAD", "the `.git/HEAD` in", ".git/HEAD",
                     FILE_CURE),
        "objects": Part(dot_git / "objects", "the `.git/objects` in",
                        ".git/objects", CURE),
        "refs": Part(dot_git / "refs", "the `.git/refs` in", ".git/refs",
                     CURE),
        "config": Part(dot_git / "config", "the `.git/config` in",
                       ".git/config", FILE_CURE),
    }


def file_layout(root: Path) -> tuple[Path, dict[str, Part]]:
    """A clone whose `.git` is a file naming `<root>/store.git`."""
    clone = a_clone(root, apart=True)
    store = root / "store.git"
    return clone, {
        ".git": Part(clone / ".git", "the `.git` in", ".git", FILE_CURE),
        "gitdir": Part(store, GIT_DIRECTORY_OF, whole(store), CURE),
        "gitdir-HEAD": Part(store / "HEAD",
                            f"the `HEAD` in {GIT_DIRECTORY_OF}",
                            whole(store / "HEAD"), FILE_CURE),
    }


def worktree_layout(root: Path) -> tuple[Path, dict[str, Part]]:
    """A linked worktree `<root>/WT` of a clone: its `.git` is a file naming
    `<clone>/.git/worktrees/WT`, whose `commondir` names `<clone>/.git`."""
    main = a_clone(root)
    tree = root / "WT"
    git("worktree", "add", "-q", "-b", "wt", str(tree), cwd=main)
    common = main / ".git"
    gitdir = common / "worktrees" / "WT"
    return tree, {
        "gitdir": Part(gitdir, GIT_DIRECTORY_OF, whole(gitdir), CURE),
        "common": Part(common, ABOVE_GIT_DIRECTORY, whole(common), CURE),
        "commondir": Part(gitdir / "commondir",
                          f"the `commondir` in {GIT_DIRECTORY_OF}",
                          whole(gitdir / "commondir"), FILE_CURE),
        "common-objects": Part(common / "objects",
                               "the `objects` in the common git directory of",
                               whole(common / "objects"), CURE),
    }


def submodule_layout(root: Path) -> tuple[Path, dict[str, Part]]:
    """A submodule `<root>/Super/sub`: its `.git` is a file naming
    `../.git/modules/sub` in the superproject."""
    origin = make_source_repo(root / "origin" / PROJECT, tree=SMALL_TREE,
                              edits=())
    superproject = root / "Super"
    superproject.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=superproject)
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
        str(origin), "sub", cwd=superproject)
    git("commit", "-q", "-m", "Add sub", cwd=superproject)
    sub = superproject / "sub"
    git("remote", "set-url", "origin", f"{URL}.git", cwd=sub)
    modules = superproject / ".git" / "modules" / "sub"
    return sub, {"modules": Part(modules, GIT_DIRECTORY_OF, whole(modules),
                                 CURE)}


def symlink_layout(root: Path) -> tuple[Path, dict[str, Part]]:
    """A clone whose `.git` is a symlink to `<root>/far/locked/store.git`."""
    clone = a_clone(root)
    locked = root / "far" / "locked"
    locked.mkdir(parents=True)
    (clone / ".git").rename(locked / "store.git")
    (clone / ".git").symlink_to(locked / "store.git")
    return clone, {"above": Part(locked, ABOVE_GIT_DIRECTORY, whole(locked),
                                 CURE)}


LAYOUTS = {"directory": directory_layout, "file": file_layout,
           "worktree": worktree_layout, "submodule": submodule_layout,
           "symlink": symlink_layout}
PARTS = [pytest.param(layout, part, id=f"{layout}-{part}")
         for layout, parts in (
             ("directory", (".git", "HEAD", "objects", "refs", "config")),
             ("file", (".git", "gitdir", "gitdir-HEAD")),
             ("worktree", ("gitdir", "common", "commondir",
                           "common-objects")),
             ("submodule", ("modules",)),
             ("symlink", ("above",)))
         for part in parts]
READABLE = [pytest.param(layout, id=layout,
                         marks=[needs_a_symlink] if layout == "symlink"
                         else [])
            for layout in LAYOUTS]


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


def the_refusal(part: Part, named: str, source: str, untold: str,
                reason: str = DENIED) -> str:
    """The line `source-unreadable` names `part` of the source with: `named`
    as the refusal names the source, and `source` its path as given."""
    return (f"{UNREADABLE}{part.role} {named}, "
            f"{spelled(os.path.join(source, part.at))}: {reason}, so "
            f"{untold} cannot be told")


def assert_no_false_answer(text: str) -> None:
    """None of the words 961640c68 said of such a part."""
    for words in FALSE_ANSWERS:
        assert words not in text, (words, text)


def assert_refused(proc, line: str, cure: str) -> None:
    """Exit 2, `line` and `cure` said, and none of the false answers."""
    assert proc.returncode == 2, said(proc)
    assert line in proc.stderr, said(proc)
    assert cure in proc.stderr, said(proc)
    assert_no_false_answer(said(proc))


def checked(tmp_path: Path, plan: Path, env: dict, *extra: str,
            verb: str = "check"):
    """`<verb> --plan <plan>` in a child, with local remotes."""
    return run_script(ADOPT, verb, "--plan", str(plan), "--work-dir",
                      str(tmp_path / f"{verb}-work"), "--local-remote-dir",
                      str(tmp_path / "remotes"), *extra, env=env)


def assert_nothing_made(tmp_path: Path, log: Path, verb: str = "check"
                        ) -> None:
    """`gh` never asked, nothing cloned, no leg made."""
    assert log.read_bytes() == b""
    assert not (tmp_path / f"{verb}-work" / "source-readonly").exists()
    assert not (tmp_path / "remotes").exists()


# --- a `--source` (#1151's case 1) ------------------------------------------

@needs_a_mode
@pytest.mark.parametrize(("layout", "part"), PARTS)
def test_a_source_part_git_cannot_read_is_refused_by_name(tmp_path, layout,
                                                          part):
    """`plan --source` of a repository with one part git reads at mode 000:
    on 961640c68 `git-failed`, in git's words, naming no part. Now
    `source-unreadable`, naming it, and no plan is written."""
    source, parts = LAYOUTS[layout](tmp_path)
    plan = tmp_path / "adoption-plan.yaml"
    env, log = recording_gh(tmp_path / "gh-bin")

    with at_mode_000(parts[part].path):
        proc = run_script(ADOPT, "plan", "--source", str(source), *PLANNED,
                          "--out", str(plan), "--work-dir",
                          str(tmp_path / "work"), env=env)

    assert_refused(proc, the_refusal(parts[part], f"--source {str(source)!r}",
                                     str(source), UNTOLD[False]),
                   parts[part].cure)
    assert INSTEAD not in proc.stderr
    assert not plan.exists()
    assert log.read_bytes() == b""


@needs_a_mode
@pytest.mark.parametrize("layout", ["directory", "file"])
def test_check_given_a_source_whose_git_cannot_be_read_names_it(tmp_path,
                                                                layout):
    """`check --plan <plan> --source <it>`, the `.git` at mode 000: the same
    refusal as `plan --source`, before the plan's own source is asked."""
    source, parts = LAYOUTS[layout](tmp_path)
    plan = planned_locally(tmp_path, source)
    env, log = recording_gh(tmp_path / "gh-bin")

    with at_mode_000(parts[".git"].path):
        proc = checked(tmp_path, plan, env, "--source", str(source))

    assert_refused(proc, the_refusal(parts[".git"],
                                     f"--source {str(source)!r}", str(source),
                                     UNTOLD[False]), parts[".git"].cure)
    assert_nothing_made(tmp_path, log)


# --- a plan's `source.local_path` (#1151's cases 2 to 7) ---------------------

@needs_a_mode
@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
@pytest.mark.parametrize(("layout", "part"), PARTS)
def test_a_recorded_part_git_cannot_read_is_refused_by_name(
        tmp_path, layout, part, cloned):
    """The plan's `source.local_path` with one part git reads at mode 000: on
    961640c68 a clone `plan` made was "no longer whole (git finds no
    repository there)" and cloned again, `gh` asked, and any other was
    `git-failed`. Now `source-unreadable`, naming the part; nothing is
    cloned or made and `gh` is never asked."""
    source, parts = LAYOUTS[layout](tmp_path)
    plan = planned_locally(tmp_path, source, cloned)
    local_path = str(recorded(plan)["local_path"])
    env, log = recording_gh(tmp_path / "gh-bin")

    with at_mode_000(parts[part].path):
        proc = checked(tmp_path, plan, env)

    assert_refused(proc, the_refusal(parts[part], RECORDED_AS, local_path,
                                     UNTOLD[cloned]), parts[part].cure)
    assert INSTEAD in proc.stderr
    assert_nothing_made(tmp_path, log)


@needs_a_mode
@pytest.mark.parametrize(("layout", "part", "cloned"), [
    pytest.param("directory", "HEAD", True, id="directory-HEAD-cloned"),
    pytest.param("file", "gitdir", False, id="file-gitdir-given"),
])
def test_execute_refuses_the_same_part_before_anything_is_made(
        tmp_path, layout, part, cloned):
    """`execute --yes` asks the same questions as `check`, before any leg
    or clone is made."""
    source, parts = LAYOUTS[layout](tmp_path)
    plan = planned_locally(tmp_path, source, cloned)
    local_path = str(recorded(plan)["local_path"])
    env, log = recording_gh(tmp_path / "gh-bin")

    with at_mode_000(parts[part].path):
        proc = checked(tmp_path, plan, env, "--yes", verb="execute")

    assert_refused(proc, the_refusal(parts[part], RECORDED_AS, local_path,
                                     UNTOLD[cloned]), parts[part].cure)
    assert INSTEAD in proc.stderr
    assert_nothing_made(tmp_path, log, verb="execute")


@needs_a_mode
@pytest.mark.parametrize("verb", ["plan", "given", "cloned"])
def test_a_clone_inside_another_repository_is_named_not_read_as_part_of_it(
        tmp_path, verb):
    """The clone is inside another repository and its `.git/HEAD` is at mode
    000: git climbs past the `.git` it cannot read and reads the clone as a
    directory of the repository above. On 961640c68 that was
    `source-not-top-level`, or "no longer whole (git reads it as part of the
    repository at ...)" and cloned again. Now the `HEAD` is named."""
    outer = tmp_path / "outer"
    outer.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=outer)
    source, parts = directory_layout(outer)
    head = parts["HEAD"]
    env, log = recording_gh(tmp_path / "gh-bin")

    if verb == "plan":
        with at_mode_000(head.path):
            proc = run_script(ADOPT, "plan", "--source", str(source),
                              *PLANNED, "--out",
                              str(tmp_path / "out-plan.yaml"), "--work-dir",
                              str(tmp_path / "work"), env=env)
        line = the_refusal(head, f"--source {str(source)!r}", str(source),
                           UNTOLD[False])
    else:
        plan = planned_locally(tmp_path, source, verb == "cloned")
        with at_mode_000(head.path):
            proc = checked(tmp_path, plan, env)
        line = the_refusal(head, RECORDED_AS,
                           str(recorded(plan)["local_path"]),
                           UNTOLD[verb == "cloned"])

    assert_refused(proc, line, head.cure)
    assert_nothing_made(tmp_path, log)


@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
@pytest.mark.parametrize("layout", READABLE)
def test_a_repository_git_can_read_is_read_as_before(tmp_path, layout,
                                                     cloned):
    """Each layout as git left it: `plan ok`, as on 961640c68, read in place
    and `gh` never asked."""
    source, _ = LAYOUTS[layout](tmp_path)
    plan = planned_locally(tmp_path, source, cloned)
    env, log = recording_gh(tmp_path / "gh-bin")

    proc = checked(tmp_path, plan, env)

    assert proc.returncode == 0, said(proc)
    assert "plan ok" in proc.stdout
    assert "source-unreadable" not in said(proc)
    assert log.read_bytes() == b""


# --- in-process, as root and on Windows too -----------------------------------

def git_finds_none(adopter, monkeypatch, source: Path, failure: str) -> None:
    """`git_out` in `source` failing, as git fails in a repository with a part
    it cannot read: refused `git-failed`, or, for `failure` "oserror", a git
    that could not be started; every other `git_out` is the real one."""
    real = adopter.git_out
    where = os.path.normcase(os.path.realpath(source))

    def failing(args, cwd, *rest, **keywords):
        if os.path.normcase(os.path.realpath(cwd)) != where:
            return real(args, cwd, *rest, **keywords)
        if failure == "oserror":
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                                    "git")
        raise adopter.Refusal("git-failed", f"`git {' '.join(args)}` in "
                              f"{cwd} exited 128: a stand-in")

    monkeypatch.setattr(adopter, "git_out", failing)


def refused_open(monkeypatch, target: Path, code: int) -> None:
    """`os.open` of `target` refused with `code`; every other is the real
    one."""
    named = os.path.normcase(os.path.realpath(target))
    real = os.open

    def refusing(path, flags, *args, **kwargs):
        if os.path.normcase(os.fsdecode(path)) == named:
            raise OSError(code, os.strerror(code), os.fsdecode(path))
        return real(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", refusing)


@pytest.mark.parametrize(("code", "cure", "not_said"), [
    pytest.param(errno.EACCES, FILE_CURE, "on the directory", id="eacces"),
    pytest.param(errno.EIO, OTHER_CURE, "chmod u+r", id="eio"),
])
def test_a_source_whose_head_cannot_be_opened_is_refused_everywhere(
        adopter, monkeypatch, tmp_path, code, cure, not_said):
    """`--source` of a clone git reads no repository in, whose `.git/HEAD`
    the operating system will not open: `source-unreadable`, naming the
    `HEAD`, with a file's cure for a permission and none for another
    reason."""
    clone = a_clone(tmp_path)
    spec = str(clone)
    git_finds_none(adopter, monkeypatch, clone, "refusal")
    refused_open(monkeypatch, clone / ".git" / "HEAD", code)

    with pytest.raises(adopter.Refusal) as raised:
        adopter._source_spec(spec)

    refusal = raised.value
    assert refusal.code == "source-unreadable"
    assert refusal.detail == (
        f"the `.git/HEAD` in --source {spec!r}, "
        f"{spelled(os.path.join(spec, '.git/HEAD'))}: cannot be read "
        f"({os.strerror(code)}), so {UNTOLD[False]} cannot be told")
    assert cure in refusal.remediation
    assert not_said not in refusal.remediation


@pytest.mark.parametrize("failure", ["refusal", "oserror"])
def test_a_recorded_clone_whose_objects_cannot_be_searched_is_kept(
        adopter, monkeypatch, capsys, tmp_path, failure):
    """`plan --source testorg/Thing` records its clone; git then finds no
    repository there, and its `.git/objects` cannot be searched. As on
    961640c68 it would be "no longer whole" and cloned again; now it is
    `source-unreadable`, naming `objects`, and no second clone is asked
    for."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    assert len(planned.calls) == 1, planned.calls
    git_finds_none(adopter, monkeypatch, Path(planned.clone), failure)
    objects = os.path.normcase(os.path.realpath(
        os.path.join(planned.clone, ".git", "objects")))
    real = os.access

    def refusing(path, mode, *args, **kwargs):
        if os.path.normcase(os.path.realpath(path)) == objects:
            return False
        return real(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "access", refusing)
    code, out, err = run(adopter, capsys, "check", "--plan",
                         str(planned.plan), "--work-dir",
                         str(tmp_path / "check-work"), "--local-remote-dir",
                         str(tmp_path / "remotes"))

    assert code == 2, out + err
    part = Part(Path(), "the `.git/objects` in", ".git/objects", CURE)
    assert the_refusal(part, RECORDED_AS, planned.clone, UNTOLD[True]) in err
    assert CURE in err
    assert INSTEAD in err
    assert_no_false_answer(out + err)
    assert len(planned.calls) == 1, planned.calls


def test_where_a_stat_is_refused_is_the_directory_above_or_the_part(
        adopter, monkeypatch, tmp_path):
    """`_where_refused` names the directory this user cannot search, the one
    above the first part whose `stat` is refused for a permission; a part
    refused for another reason, by itself; and the path asked, where
    nothing is refused now."""
    root = Path(os.path.realpath(tmp_path))
    locked = root / "a" / "locked"
    locked.mkdir(parents=True)
    failing = root / "a" / "failing"
    real = Path.stat

    def refusing(self, *args, **kwargs):
        if locked in self.parents:
            raise PermissionError(errno.EACCES, "Permission denied",
                                  str(self))
        if self == failing:
            raise OSError(errno.EIO, os.strerror(errno.EIO), str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", refusing)
    asked = PermissionError(errno.EACCES, "Permission denied")

    at, exc = adopter._where_refused(locked / "b" / "HEAD", asked)
    assert (at, type(exc)) == (locked, PermissionError)
    at, exc = adopter._where_refused(failing / "HEAD", asked)
    assert (at, exc.errno) == (failing, errno.EIO)
    assert adopter._where_refused(locked, asked) == (locked, asked)


@needs_a_mode
def test_a_head_that_is_a_link_is_not_opened(adopter, tmp_path):
    """A `HEAD` that is a symlink is read as text by git, never opened:
    a link to `refs/heads/main` at mode 000 is not refused here."""
    clone = a_clone(tmp_path)
    dot_git = clone / ".git"
    commit = git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    ref = dot_git / "refs" / "heads" / "main"
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_text(commit + "\n", encoding="utf-8")
    link = dot_git / "HEAD.link"
    link.symlink_to("refs/heads/main")
    os.replace(link, dot_git / "HEAD")

    with at_mode_000(ref):
        assert adopter._refused_git_path(clone) is None


def held_at(tmp_path: Path, held: str) -> Path:
    """A source holding what `held` names."""
    if held in LAYOUTS:
        return LAYOUTS[held](tmp_path)[0]
    path = tmp_path / PROJECT
    if held == "a-file":
        path.write_bytes(b"not a directory\n")
        return path
    if held == "a-git-with-no-config":
        path = a_clone(tmp_path)
        os.replace(path / ".git" / "config", path / ".git" / "config.aside")
        return path
    path.mkdir()
    if held == "an-empty-git":
        (path / ".git").mkdir()
    elif held == "a-head-that-is-a-directory":
        (path / ".git" / "HEAD").mkdir(parents=True)
    elif held != "nothing":
        (path / ".git").write_bytes({
            "a-git-file-of-another-format": b"not a gitdir line\n",
            "an-empty-gitdir-line": b"gitdir: \n",
            "a-gitdir-naming-nothing": b"gitdir: elsewhere\n",
            "a-gitdir-with-a-nul": b"gitdir: else\0where\n",
        }[held])
    return path


@pytest.mark.parametrize("held", [
    "nothing", "a-file", "an-empty-git", "a-git-with-no-config",
    pytest.param("a-head-that-is-a-directory", marks=pytest.mark.skipif(
        sys.platform == "win32", reason="Windows refuses to open a "
        "directory, which git does not do either")),
    "a-git-file-of-another-format", "an-empty-gitdir-line",
    "a-gitdir-naming-nothing", "a-gitdir-with-a-nul", *READABLE,
])
def test_a_part_git_can_read_or_does_not_find_is_gits_question(
        adopter, tmp_path, held):
    """`_refused_git_path` answers only for a part the operating system
    refuses: where nothing is there, where a part git asks for is not
    there, where the `.git` is not one git reads, and in each layout git
    reads, it leaves the question to git, as before."""
    assert adopter._refused_git_path(held_at(tmp_path, held)) is None
