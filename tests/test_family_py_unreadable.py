# SPDX-License-Identifier: Apache-2.0
"""`scripts/family.py`: a path it must read and this user cannot is refused
by name, never taken for a path that is not there (#430, slice G).

WHAT WAS WRONG. `Path.is_file()`, `is_dir()` and `exists()` RAISED a refused
`stat` on Python 3.9 to 3.13 (`PermissionError`, a traceback, exit 1) and
answer False to ANY `OSError` from 3.14; `os.path.lexists` has answered False
to one on every version. So on 3.14 a holder this user could not search was
`family-root-missing`, "this is not a family root"; an unsearchable
`scripts/` was `siblings-script-missing`, whose remedy adds a file the holder
has; a member checkout this user could not enter was `member-uninitialized`;
`remove --dry-run` said "not on disk" of a mount in an unsearchable
`members/`; the NOTE `remove` prints about the object store `git rm` leaves
behind was dropped without a word; and `remove`'s rollback said the store it
could not read was "not there, and clone it there". On 3.12 each was a
traceback, some of them after the commit had landed or in the middle of a
rollback.

NOW every guard asks the operating system itself, as `bump-leg.py`'s `_is_a`
does (#383): `ENOENT`, `ENOTDIR`, `EBADF` and `ELOOP` are "not there", any
other `OSError` is a refusal, `<path>: cannot be read (<reason>)`, exit 2,
with `chmod` for a permission and no `chmod` for any other cause. BEFORE A
REMOVAL "not there" is `ENOENT` alone (`_gone`): `remove` deletes the mount,
and the rollbacks of `add`, `bump` and `remove` delete or make again what
they recorded, so a file where a folder was is refused, never removed past.

EACH SITE HAS ITS ROWS: the control, where nothing is there and the answer is
the one it always was; a refused `stat`, made in-process by
`test_bump_leg_unopenable.refused_stat`, which answers as 3.14 does on every
Python and platform and as root; and a real mode where one can be made, by
`made_unopenable` or a hook, skipped on Windows and as root
(`needs_a_mode`). `refused_stat` patches `Path.stat`; `refused` routes
`Path.lstat` through it as well, which 3.12 and 3.13 do of themselves and a
Python whose `lstat` calls `os.lstat` directly does not, so the `lstat`
questions (`_gone`, `_is_there`) meet the same refusal everywhere.
"""

from __future__ import annotations

import errno
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

from conftest import git, refusal_detail, rmtree, run_script
from test_family import FAMILY, MEMBERS, ORG, SPARE, family  # noqa: F401
from test_family import family_module
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bump_remove_rollback import (
    facts, in_process, remove, typed_by_hand,
)
from test_family_dry_run import isolated
from test_bump_leg_unopenable import (
    made_unopenable, needs_a_mode, refusal_of, refused_stat,
)

MEMBER = MEMBERS[0]
PATH = f"members/{MEMBER}"
STORE = f".git/modules/{PATH}"
SPARE_PATH = f"members/{SPARE}"
ZEROS = "0" * 40

#: How each refusal of a path this user may not read begins its remedy's
#: cure, and how one for any other cause does: the two never mix.
CHMOD = "`chmod u+rx` on a directory"
NO_CHMOD = "no `chmod` puts it right"
#: How a rollback step that met a path it could not read ends, after the
#: path and the reason: the cure for a permission (#955's round 1).
STEP_CURE = ("make it readable by this user (`chmod u+r` on a file, `chmod "
             "u+rx` on a directory and on every directory above it inside "
             "the holder)")


def refused(monkeypatch, *names: str) -> None:
    """`refused_stat`, with `Path.lstat` asked through the `Path.stat` it
    patches, as Python 3.9 to 3.13 ask it, so a name it refuses is refused
    to an `lstat` too on a Python whose `lstat` calls `os.lstat` itself."""
    refused_stat(monkeypatch, *names)
    monkeypatch.setattr(Path, "lstat",
                        lambda self: self.stat(follow_symlinks=False))


def remedy(stderr: str) -> str:
    """The `Remediation:` line a refusal prints."""
    lines = [line for line in stderr.splitlines()
             if line.startswith("Remediation:")]
    assert len(lines) == 1, stderr
    return lines[0]


def run(env: dict, *argv: str):
    return run_script(FAMILY, *argv, env=env)


def hook(root: Path, tmp_path: Path, name: str, body: str) -> None:
    """A `name` hook in `root` running `body`, set LOCALLY, so a
    `core.hooksPath` in the runner's own configuration cannot point git
    somewhere it is not."""
    hooks = tmp_path / "hooks"
    hooks.mkdir(exist_ok=True)
    (hooks / name).write_text("#!/bin/sh\n" + body, encoding="utf-8")
    (hooks / name).chmod(0o755)
    git("config", "--local", "core.hooksPath", hooks.as_posix(), cwd=root)


def aside(path: Path, tmp_path: Path) -> Path:
    """`path` moved out of the holder, and where it went."""
    moved = tmp_path / f"aside-{path.name}"
    shutil.move(str(path), str(moved))
    return moved


def file_where_members_was(holder: Path, tmp_path: Path) -> bytes:
    """`members/` moved out of the holder and a FILE written at its name, so
    every path under it fails `ENOTDIR`; returns the file's bytes."""
    aside(holder / "members", tmp_path)
    data = b"a file where the members folder was\n"
    (holder / "members").write_bytes(data)
    return data


# --- the family root: `Family.open` and `siblings` (:305, :9530) ------------

ROOT_ARGV = {
    "bump": lambda root: ["bump", "--dry-run", "--family-root", str(root),
                          "--member", MEMBER, "--to", ZEROS],
    "siblings": lambda root: ["siblings", "--dry-run", "--family-root",
                              str(root)],
}


def root_refusal(root: Path) -> list[str]:
    return ["REFUSED family-root-unreadable: "
            f"{root.resolve() / 'family.yaml'}: cannot be read "
            "(Permission denied)"]


@pytest.mark.parametrize("verb", sorted(ROOT_ARGV))
def test_a_folder_with_no_family_yaml_is_still_not_a_family_root(
        verb, offline, tmp_path):
    """The control: nothing at `family.yaml` is `family-root-missing`."""
    empty = tmp_path / "not-a-holder"
    empty.mkdir()

    result = run(isolated(offline, tmp_path), *ROOT_ARGV[verb](empty))

    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_detail(result.stderr, "family-root-missing") == [
        f"REFUSED family-root-missing: {empty.resolve() / 'family.yaml'} "
        "does not exist, so this is not a family root"]


@pytest.mark.parametrize("verb", sorted(ROOT_ARGV))
def test_a_family_yaml_whose_stat_is_refused_is_not_a_missing_one(
        verb, holder, offline, tmp_path, monkeypatch, capsys):
    """Python 3.14's answer, on every Python: the holder is named as one
    this user cannot read, with the permission's cure, never "not a family
    root", whose remedy runs `init` over a holder that exists."""
    refused(monkeypatch, "family.yaml")

    code = in_process(family_module(), monkeypatch,
                      isolated(offline, tmp_path), ROOT_ARGV[verb](holder))

    err = capsys.readouterr().err
    assert code == 2, err
    assert refusal_detail(err, "family-root-unreadable") == root_refusal(
        holder)
    assert CHMOD in remedy(err)
    assert "family-root-missing" not in err


@needs_a_mode
@pytest.mark.parametrize("verb", sorted(ROOT_ARGV))
def test_a_holder_this_user_cannot_search_is_named_not_a_traceback(
        verb, holder, offline, tmp_path):
    """A holder listable and not searchable (`r--`): a `PermissionError`
    traceback on 3.12, `family-root-missing` on 3.14, now the one refusal."""
    env = isolated(offline, tmp_path)
    with made_unopenable(holder, ".", mode=0o444):
        result = run(env, *ROOT_ARGV[verb](holder))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, "family-root-unreadable") == (
        root_refusal(holder))
    assert CHMOD in remedy(result.stderr)


# --- `siblings`: the holder's own script (:9538) ---------------------------

SIBLINGS = ["siblings", "--dry-run", "--family-root"]


def test_a_holder_with_no_siblings_script_is_still_told_to_add_it(
        holder, offline, tmp_path):
    """The control: no `scripts/siblings.py` is `siblings-script-missing`."""
    aside(holder / "scripts" / "siblings.py", tmp_path)

    result = run(isolated(offline, tmp_path), *SIBLINGS, str(holder))

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED siblings-script-missing: ")


def assert_script_unreadable(code: int, err: str) -> None:
    assert code == 2, err
    assert refusal_detail(err, "siblings-script-unreadable") == [
        "REFUSED siblings-script-unreadable: scripts/siblings.py: cannot be "
        "read (Permission denied)"]
    assert CHMOD in remedy(err)
    assert "nothing was cloned or fetched" in remedy(err)


def test_a_siblings_script_whose_stat_is_refused_is_not_a_missing_one(
        holder, offline, tmp_path, monkeypatch, capsys):
    """Not `siblings-script-missing`, whose remedy adds with
    `update-shape.py` a file the holder has, and nothing run or cloned."""
    refused(monkeypatch, "siblings.py")

    code = in_process(family_module(), monkeypatch,
                      isolated(offline, tmp_path), [*SIBLINGS, str(holder)])

    assert_script_unreadable(code, capsys.readouterr().err)
    offline.assert_left_nothing()


@needs_a_mode
def test_a_scripts_folder_this_user_cannot_search_is_named(holder, offline,
                                                           tmp_path):
    with made_unopenable(holder, "scripts"):
        result = run(isolated(offline, tmp_path), *SIBLINGS, str(holder))

    assert "Traceback" not in result.stderr
    assert_script_unreadable(result.returncode, result.stderr)


@pytest.mark.skipif(sys.platform == "win32",
                    reason="a link to itself is a POSIX symbolic link")
def test_a_siblings_script_that_is_a_link_loop_is_missing(holder, offline,
                                                          tmp_path):
    """THE OTHER HALF, `ELOOP`: a link to itself is no file to run, as
    every Python up to 3.13 answered, and stays `siblings-script-missing`,
    not a file this user cannot read (r955's M19 on #955)."""
    script = holder / "scripts" / "siblings.py"
    aside(script, tmp_path)
    os.symlink("siblings.py", script)

    result = run(isolated(offline, tmp_path), *SIBLINGS, str(holder))

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED siblings-script-missing: ")


# --- `bump`: the member's `.git` (:8704) -----------------------------------

def bump_argv(holder: Path, dry: bool) -> list[str]:
    to = git("rev-parse", "HEAD~1", cwd=holder / PATH).stdout.strip()
    return ["bump", "--family-root", str(holder), "--member", MEMBER,
            "--to", to, *(["--dry-run"] if dry else [])]


#: What `bump` says of a member whose `.git` it cannot read.
GIT_UNREADABLE = [f"REFUSED member-unreadable: {PATH}/.git: cannot be read "
                  "(Permission denied)"]


def test_a_member_with_no_git_is_still_uninitialized(holder, offline,
                                                     tmp_path):
    """The control: nothing at the member's `.git` is `member-uninitialized`,
    as it always was."""
    argv = bump_argv(holder, dry=True)
    aside(holder / PATH / ".git", tmp_path)

    result = run(isolated(offline, tmp_path), *argv)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED member-uninitialized: ")


@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_member_git_whose_stat_is_refused_is_not_uninitialized(
        dry, holder, offline, tmp_path, monkeypatch, capsys):
    """Not `member-uninitialized`, whose remedy runs `git submodule update
    --init` over a checkout that is there; refused before the fetch, and
    the holder as it was."""
    env = isolated(offline, tmp_path)
    argv = bump_argv(holder, dry)
    before = facts(holder, env)
    refused(monkeypatch, ".git")

    code = in_process(family_module(), monkeypatch, env, argv)

    err = capsys.readouterr().err
    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == GIT_UNREADABLE
    assert CHMOD in remedy(err)
    monkeypatch.undo()
    assert facts(holder, env) == before


@needs_a_mode
@pytest.mark.parametrize("where", [PATH, "members"])
def test_a_member_this_user_cannot_enter_is_named_by_bump(
        where, holder, offline, tmp_path):
    env = isolated(offline, tmp_path)
    argv = bump_argv(holder, dry=False)
    before = facts(holder, env)

    with made_unopenable(holder, where):
        result = run(env, *argv)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == (
        GIT_UNREADABLE)
    assert facts(holder, env) == before


def test_a_member_under_a_file_is_still_uninitialized(holder, offline,
                                                      tmp_path):
    """THE OTHER HALF, `ENOTDIR`: a file where the member's mount was has no
    `.git` under it, which `bump`, removing nothing, reads as absent, as
    every Python up to 3.13 did: `member-uninitialized`, never a member
    this user cannot read (r955's M18 on #955)."""
    argv = bump_argv(holder, dry=True)
    aside(holder / PATH, tmp_path)
    (holder / PATH).write_bytes(b"a file where the mount was\n")

    result = run(isolated(offline, tmp_path), *argv)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED member-uninitialized: ")


# --- `remove`: the mount it deletes (:9423, and the real run's record) -------

MOUNT_UNREADABLE = [f"REFUSED member-unreadable: {PATH}: cannot be read "
                    "(Permission denied)"]


def test_a_mount_that_is_not_there_is_still_not_on_disk(holder, offline,
                                                        tmp_path):
    """The control, `ENOENT`: the dry run says the directory is not on
    disk, as it always did."""
    aside(holder / PATH, tmp_path)

    result = remove(holder, isolated(offline, tmp_path), "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"directory    {PATH}  not on disk" in result.stdout.splitlines()


@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_mount_under_a_file_is_refused_not_removed_past(
        dry, holder, offline, tmp_path):
    """THE REMOVAL ROW, `ENOTDIR`: a file where `members/` was. The dry run
    said "not on disk", exit 0, and the real run ran `git submodule deinit
    -f` past a file it never looked at, met `git rm`'s exit 128 and was
    rolled back, exit 2. Now both refuse it before any git command that
    writes, by the system's reason and with no `chmod`, and change
    nothing."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    data = file_where_members_was(holder, tmp_path)

    result = remove(holder, env, *(["--dry-run"] if dry else []))

    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == [
        f"REFUSED member-unreadable: {PATH}: cannot be read (Not a "
        "directory)"]
    assert NO_CHMOD in remedy(result.stderr)
    assert "chmod u+r" not in remedy(result.stderr)
    assert (holder / "members").read_bytes() == data
    assert facts(holder, env) == before


@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_mount_whose_stat_is_refused_is_named_before_anything(
        dry, holder, offline, tmp_path, monkeypatch, capsys):
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    refused(monkeypatch, MEMBER)

    code = in_process(family_module(), monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER,
        *(["--dry-run"] if dry else [])])

    err = capsys.readouterr().err
    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == MOUNT_UNREADABLE
    monkeypatch.undo()
    assert facts(holder, env) == before


@needs_a_mode
@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_members_folder_this_user_cannot_search_is_named_by_remove(
        dry, holder, offline, tmp_path):
    """The dry run said "not on disk"; the real run raised a traceback on
    3.12 and, on 3.14, ran `git submodule deinit -f` before `git rm`
    failed. Now both refuse first."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)

    with made_unopenable(holder, "members"):
        result = remove(holder, env, *(["--dry-run"] if dry else []))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == (
        MOUNT_UNREADABLE)
    assert facts(holder, env) == before


# The next two are r955's rows on #955 (SHOULD-2), as r955 wrote them: the
# mount's `.git`, which `remove` asks after the mount itself. `50178305`'s
# dry run said "deleted with everything in it", exit 0.

@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_mount_git_whose_stat_is_refused_is_named_by_remove(
        dry, holder, offline, tmp_path, monkeypatch, capsys):
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    refused(monkeypatch, ".git")

    code = in_process(family_module(), monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER,
        *(["--dry-run"] if dry else [])])

    err = capsys.readouterr().err
    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == GIT_UNREADABLE
    monkeypatch.undo()
    assert facts(holder, env) == before


@needs_a_mode
@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_member_this_user_cannot_enter_is_named_by_remove(
        dry, holder, offline, tmp_path):
    env = isolated(offline, tmp_path)
    before = facts(holder, env)

    with made_unopenable(holder, PATH):
        result = remove(holder, env, *(["--dry-run"] if dry else []))

    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == (
        GIT_UNREADABLE)
    assert facts(holder, env) == before


#: What `remove` says of the object store git keeps for the member, when
#: this user cannot read it (r955's SHOULD-1 on #955).
STORE_REFUSED = [f"REFUSED member-unreadable: {STORE}: cannot be read "
                 "(Permission denied)"]


@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_store_whose_stat_is_refused_is_named_by_remove(
        dry, holder, offline, tmp_path, monkeypatch, capsys):
    """The store's `HEAD`, asked before anything is written: `remove`
    committed past it, and a rollback after its first write said no store
    held the checkout and it came back only from its remote."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    refused(monkeypatch, "HEAD")

    code = in_process(family_module(), monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER,
        *(["--dry-run"] if dry else [])])

    err = capsys.readouterr().err
    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == STORE_REFUSED
    assert CHMOD in remedy(err)
    monkeypatch.undo()
    assert facts(holder, env) == before


@needs_a_mode
@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("where", [".git/modules/members", STORE],
                         ids=["modules", "store"])
def test_a_store_this_user_cannot_read_is_refused_by_remove(
        where, dry, holder, offline, tmp_path):
    """r955's SHOULD-1 rows: `remove` ran `deinit -f` and `git rm` and
    committed, exit 0, over a store this user could not read."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)

    with made_unopenable(holder, where):
        result = remove(holder, env, *(["--dry-run"] if dry else []))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == (
        STORE_REFUSED)
    assert facts(holder, env) == before


def test_a_member_whose_store_is_gone_is_still_planned_for_removal(
        holder, offline, tmp_path):
    """The control, `ENOENT`: a member whose store is gone is removed as
    #365 removes it, and the dry run plans it so."""
    rmtree(holder / STORE)

    result = remove(holder, isolated(offline, tmp_path), "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"directory    {PATH}  deleted with everything in it" in (
        result.stdout)


# --- `remove`: the NOTE about the store left behind (:9333) ------------------

#: The NOTE a landed `remove` prints when the store cannot be read.
STORE_NOTE = (f"  NOTE {STORE}: cannot be read (Permission denied), so "
              "whether `git rm` left that member's object store behind is "
              "not known")


def test_a_store_left_behind_is_still_noted(holder, offline, tmp_path):
    """The control: the store `git rm` keeps is named for deletion."""
    result = remove(holder, isolated(offline, tmp_path))

    assert result.returncode == 0, result.stdout + result.stderr
    assert ("  NOTE that member's object store is left behind."
            in result.stdout)


def test_a_store_whose_stat_is_refused_is_noted_not_dropped(
        holder, offline, tmp_path, monkeypatch, capsys):
    """After the commit: the NOTE says the store could not be read, exit 0,
    where 3.14 dropped it without a word and 3.12 raised a traceback over a
    commit that had landed. Asked of the step itself, since a refused
    `stat` of the member's name refuses the mount, earlier, too."""
    for key, value in isolated(offline, tmp_path).items():
        monkeypatch.setenv(key, value)
    module = family_module()
    family_open = module.Family.open(holder)
    row = family_open.member(MEMBER)
    refused(monkeypatch, MEMBER)

    code = module._unmount_and_drop(family_open, row, PATH)

    out = capsys.readouterr().out
    assert code == 0, out
    assert STORE_NOTE in out
    assert "is left behind" not in out


@needs_a_mode
def test_a_store_this_user_cannot_read_after_the_commit_is_noted(
        holder, offline, tmp_path):
    """A `post-commit` hook takes the store's folder away from this user
    between the commit and the question."""
    modules = holder / ".git" / "modules" / "members"
    hook(holder, tmp_path, "post-commit",
         f"chmod 000 '{modules.as_posix()}'\n")
    try:
        result = remove(holder, isolated(offline, tmp_path))
    finally:
        modules.chmod(0o755)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert STORE_NOTE in result.stdout
    assert git("log", "-1", "--format=%s", cwd=holder).stdout.startswith(
        f"Remove {MEMBER} from the ")


# --- `remove`'s rollback: the store the checkout comes back from (:7179) --

def pinned(holder: Path) -> str:
    return git("rev-parse", f"HEAD:{PATH}", cwd=holder).stdout.strip()


def test_a_store_that_is_there_or_gone_is_answered_as_it_was(holder):
    """The control: a store that holds the pin answers None; one that is
    not there (`ENOENT`) is the clone the rollback will not make."""
    module = family_module()
    commit = pinned(holder)
    assert module._unrestorable(holder, PATH, commit) is None

    rmtree(holder / STORE)

    assert module._unrestorable(holder, PATH, commit) == (
        f"git would check it out of {STORE}, which is not there, and clone "
        "it there")


#: What the rollback says of a store it cannot read.
STORE_UNREAD = (f"git would check it out of {STORE}, which cannot be read "
                "(Permission denied): `chmod u+rx` on it, and on every "
                "directory above it inside the holder, lets git read it")


def test_a_store_whose_stat_is_refused_is_no_store_that_is_gone(
        holder, monkeypatch):
    """Not "not there, and clone it there": `member-unreadable`."""
    module = family_module()
    commit = pinned(holder)
    refused(monkeypatch, MEMBER)

    refusal = refusal_of(module, module._unrestorable, holder, PATH, commit)

    assert refusal.code == "member-unreadable"
    assert refusal.code == module.STORE_UNREADABLE
    assert refusal.detail == STORE_UNREAD


def stat_failing(monkeypatch, name: str, error: OSError) -> None:
    """`Path.stat` of `name` failing with `error`, a cause that is not a
    permission, which `refused_stat` does not make."""
    real = Path.stat

    def failing(self, *args, **kwargs):
        if self.name == name:
            raise error
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", failing)


#: An I/O error: a cause no `chmod` puts right.
EIO = OSError(errno.EIO, "Input/output error")


def test_a_store_that_fails_for_another_cause_is_told_no_chmod(
        holder, monkeypatch):
    """r955's NIT 6 on #955: the cure follows the cause. An I/O error is
    not told the mode (r955's M27)."""
    module = family_module()
    commit = pinned(holder)
    stat_failing(monkeypatch, MEMBER, EIO)

    refusal = refusal_of(module, module._unrestorable, holder, PATH, commit)

    assert refusal.detail == (
        f"git would check it out of {STORE}, which cannot be read "
        f"(Input/output error): {module.OTHER_CURE}")
    assert "chmod u+r" not in refusal.detail


def test_a_store_that_fails_for_another_cause_is_noted_no_chmod(
        holder, offline, tmp_path, monkeypatch, capsys):
    """The NOTE after `remove`'s commit, for an I/O error: #430's
    other-reason words, never "once this user can read the directory"."""
    for key, value in isolated(offline, tmp_path).items():
        monkeypatch.setenv(key, value)
    module = family_module()
    family_open = module.Family.open(holder)
    row = family_open.member(MEMBER)
    stat_failing(monkeypatch, MEMBER, EIO)

    code = module._unmount_and_drop(family_open, row, PATH)

    out = capsys.readouterr().out
    assert code == 0, out
    assert (f"  NOTE {STORE}: cannot be read (Input/output error), so whether"
            in out)
    assert module.OTHER_CURE in out
    assert "once this user can read" not in out


def assert_store_unread_said(sentence: str) -> None:
    """The rollback's sentence names the store as unreadable, types the
    update that brings the checkout back from it, and never sends the
    person to the member's remote."""
    assert STORE_UNREAD in sentence
    assert ("`git -c protocol.allow=never submodule update --init --no-fetch "
            f"-- {PATH}`") in sentence
    assert "comes back only from its remote" not in sentence
    assert "not there, and clone it there" not in sentence


def test_a_rollback_meeting_a_refused_store_types_the_restore(
        holder, offline, tmp_path, monkeypatch, capsys):
    """In-process: the commit fails and, by then, the store's `stat` is
    refused. The step is named, and its commands are typed."""
    module = family_module()
    fail = module.CommandFailed(["git", "commit"], holder, 1,
                                "pre-commit: refusing (injected)")

    def refused_then_failed(*args, **kwargs):
        refused(monkeypatch, MEMBER)
        raise fail

    monkeypatch.setattr(module, "_commit_one", refused_then_failed)

    code = in_process(module, monkeypatch, isolated(offline, tmp_path), [
        "remove", "--family-root", str(holder), "--member", MEMBER])

    err = capsys.readouterr().err
    assert code == 2, err
    assert "Traceback" not in err
    sentence = err.splitlines()[-1]
    assert_store_unread_said(sentence)
    # The mount's own `stat` is refused too, so it is not made again over
    # (r955's M30), and no `mkdir` is typed for it.
    assert "was made again, empty" not in sentence
    assert "`mkdir " not in sentence


@needs_a_mode
def test_a_rollback_meeting_an_unreadable_store_is_put_right_as_typed(
        holder, offline, tmp_path):
    """A `pre-commit` hook takes the store's folder away and refuses. The
    rollback names it, makes the mount again, empty, and types the update
    that brings the checkout back from the store with no network: 3.12
    raised a traceback in the middle of the rollback, and 3.14 said the
    store was not there and the checkout came back only from its remote.
    With the mode given back, the commands, typed as printed, put the
    member back on its branch at its commit."""
    env = isolated(offline, tmp_path)
    at = git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip()
    modules = holder / ".git" / "modules" / "members"
    hook(holder, tmp_path, "pre-commit",
         f"chmod 000 '{modules.as_posix()}'\nexit 1\n")
    try:
        result = remove(holder, env)
    finally:
        modules.chmod(0o755)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    sentence = result.stderr.splitlines()[-1]
    assert_store_unread_said(sentence)
    assert f", and {PATH} was made again, empty" in sentence
    git("config", "--local", "--unset", "core.hooksPath", cwd=holder)
    typed_by_hand(holder, sentence)
    assert_back_on_main(holder, at)


def assert_back_on_main(holder: Path, at: str) -> None:
    """The member checked out on `main` at `at`, the holder clean."""
    assert git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip() == at
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=holder / PATH).stdout.strip() == "main"
    assert git("status", "--porcelain", cwd=holder).stdout == ""


@needs_a_mode
def test_a_rollback_step_that_cannot_read_names_the_path_and_the_cure(
        holder, offline, tmp_path):
    """r955's SHOULD-3 on #955: a `pre-commit` hook takes `members/` away
    from this user and refuses. The step that brings the checkout back
    said only "Permission denied", and the commands typed after it failed
    until the mode was given back. Now it names the path and the cure; with
    the mode given back, the commands, typed as printed, put the member
    back."""
    env = isolated(offline, tmp_path)
    at = git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip()
    members = holder / "members"
    hook(holder, tmp_path, "pre-commit",
         f"chmod 000 '{members.as_posix()}'\nexit 1\n")
    try:
        result = remove(holder, env)
    finally:
        members.chmod(0o755)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    sentence = result.stderr.splitlines()[-1]
    assert (f" from the object store `git rm` keeps: {PATH}/.git: cannot be "
            f"read (Permission denied); {STEP_CURE}") in sentence
    git("config", "--local", "--unset", "core.hooksPath", cwd=holder)
    typed_by_hand(holder, sentence)
    assert_back_on_main(holder, at)


# --- `add`'s rollback: what it records and what it deletes (:6536-:6620) ----

def mount_rollback(holder: Path):
    """`MountRollback` of the spare member's mount, recorded now."""
    module = family_module()
    return module, module.MountRollback(holder, SPARE_PATH)


def test_a_mount_not_there_yet_is_recorded_as_made_by_the_run(holder):
    """The control, `ENOENT`: both trees the mount makes are recorded."""
    _, rollback = mount_rollback(holder)

    assert [shown for _, shown, _ in rollback.trees] == [
        SPARE_PATH, f".git/modules/{SPARE_PATH}"]
    assert rollback.files[".gitmodules"][0] == (
        holder / ".gitmodules").read_bytes()


@pytest.mark.parametrize("name, shown", [
    (SPARE, SPARE_PATH),
    (".gitmodules", ".gitmodules"),
], ids=["mount", "gitmodules"])
def test_a_record_whose_stat_is_refused_is_refused_before_the_mount(
        name, shown, holder, monkeypatch):
    """A tree recorded as absent is one `undo` deletes: a refused `stat` is
    refused, not recorded as made by this run; so is a file `undo` would
    delete as one there was none of."""
    module = family_module()
    refused(monkeypatch, name)

    refusal = refusal_of(module, module.MountRollback, holder, SPARE_PATH)

    assert refusal.code == "member-unreadable"
    assert refusal.detail == f"{shown}: cannot be read (Permission denied)"


@needs_a_mode
def test_a_record_under_a_folder_this_user_cannot_search_is_refused(holder):
    module = family_module()
    with made_unopenable(holder, "members"):
        refusal = refusal_of(module, module.MountRollback, holder, SPARE_PATH)

    assert refusal.detail == (f"{SPARE_PATH}: cannot be read (Permission "
                              "denied)")


def test_an_undo_with_nothing_made_changes_nothing(holder):
    """The control: nothing was made, nothing is deleted."""
    _, rollback = mount_rollback(holder)

    assert rollback.undo() == (" Nothing was added, and nothing in the holder "
                               "had changed.")


def test_an_undo_meeting_a_file_where_a_folder_was_says_so(holder, tmp_path):
    """THE REMOVAL ROW, `ENOTDIR`: `exists()` said "nothing there" of the
    mount under a file where `members/` was, and `undo` called the holder
    unchanged. Now the step is named as not done, and the file is kept."""
    _, rollback = mount_rollback(holder)
    data = file_where_members_was(holder, tmp_path)

    said = rollback.undo()

    assert (f"; NOT {SPARE_PATH} removed: {SPARE_PATH}: cannot be read (Not "
            f"a directory); {NO_CHMOD}") in said
    assert (holder / "members").read_bytes() == data


def test_an_undo_meeting_a_refused_stat_deletes_nothing(holder, monkeypatch):
    """A mount the run made, whose `stat` is refused by the time `undo`
    asks: named as not removed, and left in place, where 3.14 called the
    holder unchanged."""
    _, rollback = mount_rollback(holder)
    (holder / SPARE_PATH).mkdir()
    refused(monkeypatch, SPARE)

    said = rollback.undo()

    assert (f"; NOT {SPARE_PATH} removed: {SPARE_PATH}: cannot be read "
            f"(Permission denied); {STEP_CURE}") in said
    monkeypatch.undo()
    assert (holder / SPARE_PATH).is_dir()


@needs_a_mode
def test_an_undo_under_a_folder_this_user_cannot_search_says_so(holder):
    _, rollback = mount_rollback(holder)
    (holder / SPARE_PATH).mkdir()

    with made_unopenable(holder, "members"):
        said = rollback.undo()

    assert (f"; NOT {SPARE_PATH} removed: {SPARE_PATH}: cannot be read "
            f"(Permission denied); {STEP_CURE}") in said
    assert (holder / SPARE_PATH).is_dir()


# --- `bump`'s and `remove`'s rollback: what it records (:7198-:7446) ---------

def pin_rollback(holder: Path):
    module = family_module()
    return module, module.PinRollback(holder, PATH, "remove",
                                      (".gitmodules", "family.yaml"),
                                      unmount=True)


def test_a_checked_out_member_is_recorded_as_one(holder):
    """The control: a checkout, its directory and its commit."""
    _, rollback = pin_rollback(holder)

    assert rollback.checkout is True
    assert rollback.existed is True
    assert rollback.at == git("rev-parse", "HEAD",
                              cwd=holder / PATH).stdout.strip()


@pytest.mark.parametrize("name, shown", [
    (".git", f"{PATH}/.git"),
    (MEMBER, PATH),
], ids=["git", "mount"])
def test_a_pin_record_whose_stat_is_refused_is_refused(name, shown, holder,
                                                       monkeypatch):
    """Not "no checkout", which a failed `remove` made again, empty, and
    called as it was."""
    module = family_module()
    refused(monkeypatch, name)

    refusal = refusal_of(module, module.PinRollback, holder, PATH, "remove",
                         (".gitmodules", "family.yaml"))

    assert refusal.code == "member-unreadable"
    assert refusal.detail == f"{shown}: cannot be read (Permission denied)"


@needs_a_mode
def test_a_pin_record_of_a_member_this_user_cannot_enter_is_refused(holder):
    module = family_module()
    with made_unopenable(holder, PATH):
        refusal = refusal_of(module, module.PinRollback, holder, PATH,
                             "remove", (".gitmodules", "family.yaml"))

    assert refusal.detail == (f"{PATH}/.git: cannot be read (Permission "
                              "denied)")


def test_a_kept_store_is_named_there_gone_or_unreadable(holder, tmp_path,
                                                        monkeypatch):
    """`_store_kept`, the store the checkout's own `.git` named where git
    looks in another: still there, named; gone, unsaid; its `stat` refused,
    named as unreadable, never left out as gone."""
    _, rollback = pin_rollback(holder)
    kept = tmp_path / "kept-store"
    kept.mkdir()
    rollback.store = kept
    assert rollback._store_kept() == (
        f"; the object store its checkout had, {kept.as_posix()}, is still "
        "there")
    rollback.store = tmp_path / "no-store"
    assert rollback._store_kept() == ""

    rollback.store = kept
    refused(monkeypatch, kept.name)

    assert rollback._store_kept() == (
        f"; the object store its checkout had, {kept.as_posix()}: cannot be "
        "read (Permission denied)")
    assert rollback.store_said is True


# --- `add`: the mount path and the cached store (:6031, :6171) --------------

def add_argv(holder: Path, family: dict, *extra: str) -> list[str]:
    return ["add", "--family-root", str(holder), "--member",
            f"{ORG}/{SPARE}", "--local-remote-dir", str(family["remotes"]),
            *extra]


def test_a_free_mount_path_is_still_free(family, holder, offline, tmp_path):
    """The control: nothing at the path, so `add --dry-run` plans the
    mount."""
    result = run(isolated(offline, tmp_path),
                 *add_argv(holder, family, "--dry-run"))

    assert result.returncode == 0, result.stdout + result.stderr


def test_a_cached_store_is_still_refused_as_one(family, holder, offline,
                                                tmp_path):
    """The control: a store a removed member left behind is
    `member-git-dir-cached`."""
    (holder / ".git" / "modules" / SPARE_PATH).mkdir(parents=True)

    result = run(isolated(offline, tmp_path), *add_argv(holder, family))

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED member-git-dir-cached: ")


def add_in_process(module, family, holder, offline, tmp_path, monkeypatch,
                   capsys) -> tuple[int, str]:
    code = in_process(module, monkeypatch, isolated(offline, tmp_path),
                      add_argv(holder, family))
    return code, capsys.readouterr().err


def test_a_mount_path_whose_stat_is_refused_is_not_free(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """`os.path.lexists` called it free, and the mount died in git's clone
    after the member was read; on 3.12 the rollback's record raised first."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    refused(monkeypatch, SPARE)

    code, err = add_in_process(family_module(), family, holder, offline,
                               tmp_path, monkeypatch, capsys)

    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == [
        f"REFUSED member-unreadable: {SPARE_PATH}: cannot be read "
        "(Permission denied)"]
    monkeypatch.undo()
    assert facts(holder, env) == before
    offline.assert_left_nothing()


def test_a_cached_store_whose_stat_is_refused_is_named(
        family, holder, offline, tmp_path, monkeypatch, capsys):
    """Asked past the mount path's own question, which a refused `stat` of
    the member's name answers first."""
    module = family_module()
    monkeypatch.setattr(module, "_checked_mount_path",
                        lambda *args, **kwargs: None)
    refused(monkeypatch, SPARE)

    code, err = add_in_process(module, family, holder, offline, tmp_path,
                               monkeypatch, capsys)

    assert code == 2, err
    assert refusal_detail(err, "member-unreadable") == [
        f"REFUSED member-unreadable: .git/modules/{SPARE_PATH}: cannot be "
        "read (Permission denied)"]


@needs_a_mode
@pytest.mark.parametrize("where, shown", [
    ("members", SPARE_PATH),
    (".git/modules/members", f".git/modules/{SPARE_PATH}"),
], ids=["mount", "store"])
def test_add_names_a_folder_this_user_cannot_search(
        where, shown, family, holder, offline, tmp_path):
    """3.12 raised a traceback; 3.14 mounted, and git's clone died."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)

    with made_unopenable(holder, where):
        result = run(env, *add_argv(holder, family))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == [
        f"REFUSED member-unreadable: {shown}: cannot be read (Permission "
        "denied)"]
    assert facts(holder, env) == before


@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_add_refuses_a_file_where_the_stores_folder_belongs(
        dry, family, holder, offline, tmp_path):
    """r955's NIT 4 on #955: with a FILE at `.git/modules/members` the dry
    run planned a mount, exit 0, that the real run's record refused. Both
    refuse it now, before the member is read, with no `chmod`."""
    env = isolated(offline, tmp_path)
    modules = holder / ".git" / "modules" / "members"
    aside(modules, tmp_path)
    modules.write_bytes(b"a file where the stores' folder was\n")
    before = facts(holder, env)

    result = run(env, *add_argv(holder, family,
                                *(["--dry-run"] if dry else [])))

    assert result.returncode == 2, result.stdout + result.stderr
    assert refusal_detail(result.stderr, "member-unreadable") == [
        f"REFUSED member-unreadable: .git/modules/{SPARE_PATH}: cannot be "
        "read (Not a directory)"]
    assert NO_CHMOD in remedy(result.stderr)
    assert facts(holder, env) == before
    offline.assert_left_nothing()


# --- the member's own `project.yaml` (:778) --------------------------------

def test_a_member_with_no_manifest_is_still_not_a_project(tmp_path):
    """The control: nothing at `project.yaml` is `member-not-a-project`."""
    module = family_module()

    refusal = refusal_of(module, module._read_member_project, tmp_path,
                         SPARE, f"{ORG}/{SPARE}")

    assert refusal.code == "member-not-a-project"


@pytest.mark.parametrize("shown", [None, f"{ORG}/{SPARE} @ abc:project.yaml"],
                         ids=["mount", "objects"])
def test_a_manifest_whose_stat_is_refused_is_unreadable_not_absent(
        shown, tmp_path, monkeypatch):
    """Not `member-not-a-project`, which sends the person to scaffold a
    project that is one: the manifest is named, as `shown` names it."""
    module = family_module()
    refused(monkeypatch, "project.yaml")

    refusal = refusal_of(module, module._read_member_project, tmp_path,
                         SPARE, f"{ORG}/{SPARE}", shown)

    assert refusal.code == "member-manifest-unreadable"
    named = shown or str(tmp_path / "project.yaml")
    assert refusal.detail == f"{named}: cannot be read (Permission denied)"


@needs_a_mode
def test_a_manifest_linked_into_a_folder_this_user_cannot_search(tmp_path):
    """A `project.yaml` that is a link into a folder this user may not
    search."""
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "project.yaml").write_text("id: irqs\n", encoding="utf-8")
    member = tmp_path / "member"
    member.mkdir()
    os.symlink(locked / "project.yaml", member / "project.yaml")
    module = family_module()
    mode = stat.S_IMODE(locked.stat().st_mode)
    locked.chmod(0)
    try:
        refusal = refusal_of(module, module._read_member_project, member,
                             SPARE, f"{ORG}/{SPARE}")
    finally:
        locked.chmod(mode)

    assert refusal.code == "member-manifest-unreadable"
