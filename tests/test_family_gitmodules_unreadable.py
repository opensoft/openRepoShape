# SPDX-License-Identifier: Apache-2.0
"""A family holder's `.gitmodules` that this user may not read is refused
by name, never read as absent: `scripts/family.py`'s `_gitmodules_names`
and `_sections_giving`, and the family root's `scripts/siblings.py`
`submodule_urls` (#1110, slice B; the rule is #430's).

WHAT WAS WRONG. Each asked `Path.is_file()` of the holder's `.gitmodules`.
Python 3.9 to 3.13 raise a refused `stat` (`PermissionError`), and 3.14
answers False to any `OSError`. With `.gitmodules` a link into a folder at
mode 000, measured on `038dafba9` on Python 3.12.3 and on a 3.14-like shim:

- `make siblings` and `family.py siblings`, and `make park` (`--make`): a
  traceback on 3.12. On 3.14 no url was read, so the dry run planned each
  member from `https://github.com/<repository>.git`, a remote the holder is
  not pinned against, exit 0; the real run tried to clone from there; and
  `--make` took each working clone, cloned from the url the holder pins,
  for a different repository and skipped it.
- `remove`'s rollback, after a `pre-commit` hook made the file such a link
  and refused: a traceback on 3.12, the member's directory left gone. On
  3.14 no section gave git the member's path, so its checkout "comes back
  only from its remote", and no command brought it back from the object
  store it still had.
- With the `stat` refused in process, `remove --dry-run` said no section is
  removed, exit 0, and the real run was refused only by its rollback's
  record, as `member-unreadable`.

A person's own `remove` over such a link is refused before either reader
is asked: git lists a link where the index holds a file as modified, so
`gitmodules-unstaged` comes first, on base and here alike. A row below
holds that order.

NOW both files ask the file as their own `_is_a` asks it, and ask a file
whose `stat` is answered whether this user may open it (`os.access`), as
git would find out. Nothing at the name is no file, as it always was; any
other answer is `gitmodules-unreadable`, `.gitmodules: cannot be read
(<reason>)`, exit 2, before anything is written, cloned, fetched or run,
with `chmod` for a permission and none for any other cause. `remove`'s
rollback takes it as it takes a store it cannot read: the mount made again,
empty, and the update typed after the cure, never "only from its remote".

EACH SITE HAS ITS ROWS: the control (nothing there, or a link this user can
read); a refused `stat`, an I/O error or a refused `os.access` in process,
on every Python and platform and as root (`refused`, `refused_stat`,
`stat_failing`, `access_refused`); and a real link into a folder at mode
000, run as a person runs the tool, skipped on Windows and as root
(`needs_a_mode`).
"""

from __future__ import annotations

import contextlib
import errno
import os
import shutil
import stat
from pathlib import Path

import pytest

from conftest import git, refusal_detail, run_script
from test_bump_leg_unopenable import needs_a_mode, refusal_of, refused_stat
from test_family import (  # noqa: F401
    FAMILY, MEMBERS, NAME, SPARE, estate, family, family_module, siblings,
)
from test_family_add_refusals import (  # noqa: F401
    add_in_process, holder, offline,
)
from test_family_bump_remove_rollback import (
    facts, in_process, remove, typed_by_hand,
)
from test_family_dry_run import isolated
from test_family_py_unreadable import (
    EIO, STEP_CURE, assert_back_on_main, hook, refused, remedy, stat_failing,
)
from test_family_siblings_bootstrap_unreadable import (  # noqa: F401
    placed, placed_folder,
)
from test_family_siblings_placement import placement  # noqa: F401

MEMBER = MEMBERS[0]
PATH = f"members/{MEMBER}"
GITMODULES = ".gitmodules"
CODE = "gitmodules-unreadable"
DENIED = f"{GITMODULES}: cannot be read (Permission denied)"
#: What `os.access` refusing a read is named with, as the tools raise it.
NO_READ = f"{GITMODULES}: cannot be read ({os.strerror(errno.EACCES)})"
#: A permission's cure. The directories above are not said to be inside the
#: holder: a link can lead out of it.
CHMOD = "`chmod u+rx` on a directory (and on every directory above it)"
OTHER_CAUSE = "Where the operating system gave another reason"
#: The update `remove`'s rollback types for the member's checkout, under
#: the backstop that reaches no remote.
UPDATE = ("`git -c protocol.allow=never submodule update --init --no-fetch "
          f"-- {PATH}`")
ONLY_REMOTE = "comes back only from its remote"
#: The cure the rollback's sentence gives a `.gitmodules` it cannot read
#: when it asks for the checkout's store, which prints no remediation of its
#: own (r1164's NIT-1); not "inside the holder", as a link can lead out.
READ_CURE = ("`chmod u+r` on it, and `chmod u+rx` on every directory above "
             "it, lets git read it")
READERS = pytest.mark.parametrize("reader", ["_gitmodules_names",
                                             "_sections_giving"])
#: What each reader answers where the holder has no `.gitmodules`.
NOTHING = {"_gitmodules_names": (None, []), "_sections_giving": []}


def linked_into_locked(root: Path, tmp_path: Path) -> Path:
    """`root`'s `.gitmodules` moved into `<tmp>/locked/` and a link to it
    left in its place, so that once `locked` is at mode 000 its `stat` is
    refused while the holder and its `.git` can still be read; returns
    `locked`. Skipped where no link can be made."""
    locked = tmp_path / "locked"
    locked.mkdir()
    (root / GITMODULES).rename(locked / GITMODULES)
    try:
        (root / GITMODULES).symlink_to(locked / GITMODULES)
    except OSError as exc:
        pytest.skip(f"no symlink here: {exc}")
    return locked


@contextlib.contextmanager
def at_000(path: Path):
    """`path` at mode 000 while the block runs, its own mode after."""
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(0)
    try:
        yield
    finally:
        path.chmod(mode)


def access_refused(monkeypatch, name: str) -> None:
    """`os.access` answering that this user may not read `name`, as it
    answers for a file at mode 000 whose `stat` still succeeds: in process,
    so on every platform and as root."""
    real = os.access

    def access(path, mode, *args, **kwargs):
        if Path(path).name == name and mode & os.R_OK:
            return False
        return real(path, mode, *args, **kwargs)

    monkeypatch.setattr(os, "access", access)


def read_refused(module, reader: str, root: Path):
    """The refusal `reader` raises for `root`'s `.gitmodules`."""
    return refusal_of(module, getattr(module, reader), root, PATH)


# --- family.py: the two readers (`_gitmodules_names`, `_sections_giving`) --

@READERS
def test_a_holder_with_no_gitmodules_still_gives_no_section(reader, holder,
                                                            tmp_path):
    """The control, `ENOENT`: no file, or a link to nothing, gives the path
    to no section, as it always did."""
    module = family_module()
    (holder / GITMODULES).rename(tmp_path / "aside")

    assert getattr(module, reader)(holder, PATH) == NOTHING[reader]

    try:
        (holder / GITMODULES).symlink_to(tmp_path / "nowhere")
    except OSError:
        return
    assert getattr(module, reader)(holder, PATH) == NOTHING[reader]


def a_directory_at_gitmodules(root: Path, tmp_path: Path) -> None:
    """`root`'s `.gitmodules` moved aside and a directory made at its name."""
    (root / GITMODULES).rename(tmp_path / "aside")
    (root / GITMODULES).mkdir()


@READERS
def test_a_gitmodules_that_is_a_directory_still_gives_no_section(
        reader, holder, tmp_path, monkeypatch):
    """The control: a directory at the name is no file, as `is_file()`
    always answered, so it gives the path to no section and its read is
    never asked, even where this user may not read it (r1164's SHOULD-1:
    nothing held the regular-file test, `S_ISREG`)."""
    module = family_module()
    a_directory_at_gitmodules(holder, tmp_path)

    assert getattr(module, reader)(holder, PATH) == NOTHING[reader]

    access_refused(monkeypatch, GITMODULES)
    assert getattr(module, reader)(holder, PATH) == NOTHING[reader]


def test_a_gitmodules_linked_into_a_readable_folder_is_read(holder,
                                                            tmp_path):
    """The control: a link this user can follow is read through, as git
    reads it."""
    module = family_module()
    linked_into_locked(holder, tmp_path)

    assert module._gitmodules_names(holder, PATH) == (PATH, [])
    assert [name for name, _, _ in module._sections_giving(holder, PATH)] \
        == [PATH]


@READERS
def test_a_gitmodules_whose_stat_is_refused_is_refused_not_absent(
        reader, holder, monkeypatch):
    """Not "no section": `gitmodules-unreadable`, named, with the cure."""
    module = family_module()
    refused(monkeypatch, GITMODULES)

    refusal = read_refused(module, reader, holder)

    assert refusal.code == CODE == module.GITMODULES_UNREAD_CODE
    assert refusal.detail == DENIED
    assert CHMOD in refusal.remediation
    assert "inside the holder" not in refusal.remediation
    assert "never taken for one that is not there" in refusal.remediation


@READERS
def test_a_gitmodules_that_fails_for_another_cause_is_told_no_chmod(
        reader, holder, monkeypatch):
    """An I/O error: refused by its own reason, and no `chmod`."""
    module = family_module()
    stat_failing(monkeypatch, GITMODULES, EIO)

    refusal = read_refused(module, reader, holder)

    assert refusal.code == CODE
    assert refusal.detail == (f"{GITMODULES}: cannot be read (Input/output "
                              "error)")
    assert "chmod u+r" not in refusal.remediation
    assert module.OTHER_CURE in refusal.remediation


@READERS
def test_a_gitmodules_this_user_may_not_open_is_refused(reader, holder,
                                                        monkeypatch):
    """Its `stat` answered, its read refused (`os.access`): git could not
    read it either, so it is refused, not handed to git."""
    module = family_module()
    access_refused(monkeypatch, GITMODULES)

    refusal = read_refused(module, reader, holder)

    assert refusal.code == CODE
    assert refusal.detail == NO_READ
    assert CHMOD in refusal.remediation


@needs_a_mode
@READERS
@pytest.mark.parametrize("how", ["link-into-000", "file-at-000"])
def test_a_gitmodules_this_user_cannot_reach_is_refused(reader, how, holder,
                                                        tmp_path):
    """The case as a person meets it: a link into a folder at mode 000,
    which 3.12 raised as a `PermissionError` and 3.14 read as no file; and
    a file at mode 000, which git could not read."""
    module = family_module()
    target = (linked_into_locked(holder, tmp_path) if how == "link-into-000"
              else holder / GITMODULES)

    with at_000(target):
        refusal = read_refused(module, reader, holder)

    assert refusal.code == CODE
    assert refusal.detail == DENIED


# --- family.py: `remove`, the readers' caller --------------------------------

@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_remove_refuses_a_gitmodules_it_cannot_read_before_anything(
        dry, holder, offline, tmp_path, monkeypatch, capsys):
    """The `stat` of a `.gitmodules` git still reads as the index's refused
    in process. The dry run said no section is removed, exit 0, and the
    real run was refused by its rollback's record as `member-unreadable`.
    Both now refuse it as `gitmodules-unreadable` before any git command
    that writes, and leave the holder as it was."""
    env = isolated(offline, tmp_path)
    before = facts(holder, env)
    refused(monkeypatch, GITMODULES)

    code = in_process(family_module(), monkeypatch, env, [
        "remove", "--family-root", str(holder), "--member", MEMBER,
        *(["--dry-run"] if dry else [])])

    said = capsys.readouterr()
    assert code == 2, said.out + said.err
    assert refusal_detail(said.err, CODE) == [f"REFUSED {CODE}: {DENIED}"]
    assert CHMOD in remedy(said.err)
    assert "none is removed" not in said.out
    monkeypatch.undo()
    assert facts(holder, env) == before


@needs_a_mode
@pytest.mark.parametrize("dry", [True, False], ids=["dry-run", "real"])
def test_a_persons_remove_over_a_linked_gitmodules_is_refused_first(
        dry, holder, offline, tmp_path):
    """Run as a person runs it, over a `.gitmodules` that is a link into a
    folder at mode 000: git lists the link as modified, so `remove` refuses
    it as `gitmodules-unstaged` before either reader, with no traceback
    and nothing written, as it did before #1110."""
    env = isolated(offline, tmp_path)
    locked = linked_into_locked(holder, tmp_path)
    before = facts(holder, env)

    with at_000(locked):
        result = remove(holder, env, *(["--dry-run"] if dry else []))

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert result.stderr.startswith("REFUSED gitmodules-unstaged: ")
    assert facts(holder, env) == before


#: A modification time well before any index a test writes (2001-09-09), so
#: git's stat cache for a file set to it is never racily clean.
LONG_AGO = 1_000_000_000


def stat_cache(holder: Path, stale: bool) -> None:
    """git's stat cache for `.gitmodules` made current or stale ON PURPOSE.
    Its mtime is set long ago and the index refreshed, with
    `core.trustctime` off, so the `chmod` that follows, which moves only
    the ctime, leaves the cache current and `git ls-files -m` does not read
    the file. Where `stale`, the mtime moves once more: git must read the
    file to compare it, cannot, and lists it as modified."""
    path = holder / GITMODULES
    git("config", "--local", "core.trustctime", "false", cwd=holder)
    os.utime(path, (LONG_AGO, LONG_AGO))
    git("update-index", "-q", "--refresh", cwd=holder)
    if stale:
        os.utime(path, (LONG_AGO + 60, LONG_AGO + 60))


@needs_a_mode
@pytest.mark.parametrize("stale", [True, False],
                         ids=["git-lists-it", "git-does-not-list-it"])
def test_a_persons_remove_names_a_gitmodules_at_000_one_way(
        stale, holder, offline, tmp_path):
    """A `.gitmodules` that is a file at mode 000, run as a person runs
    `remove`, dry run and real, with git's stat cache stale or current.
    Where git listed it as modified, `_stages_as` asked `git hash-object`,
    and the refusal was `a git or gh command failed`; where git did not,
    it was `gitmodules-unreadable` (r1164's SHOULD-2). Now both are
    `gitmodules-unreadable`, with the cure, and nothing is written."""
    env = isolated(offline, tmp_path)
    stat_cache(holder, stale)
    before = facts(holder, env)

    with at_000(holder / GITMODULES):
        listed = git("ls-files", "-m", "-z", cwd=holder).stdout.split("\0")
        results = [remove(holder, env, "--dry-run"), remove(holder, env)]

    assert (GITMODULES in listed) is stale
    for result in results:
        assert result.returncode == 2, result.stdout + result.stderr
        assert "Traceback" not in result.stderr
        assert refusal_detail(result.stderr, CODE) == [
            f"REFUSED {CODE}: {DENIED}"]
        assert CHMOD in remedy(result.stderr)
    assert facts(holder, env) == before


def test_add_names_a_gitmodules_it_may_not_open_for_its_own_reading(
        family, holder, offline, monkeypatch, capsys):
    """`add` asks `_stages_as` too, of a `.gitmodules` the index marks
    assume-unchanged, which git does not compare. One this user may not
    open (`os.access`, in process) is `gitmodules-unreadable` there, before
    `git hash-object`, and its remedy says what `add` reads it for, not
    what `remove` does."""
    git("update-index", "--assume-unchanged", "--", GITMODULES, cwd=holder)
    access_refused(monkeypatch, GITMODULES)

    code = add_in_process(family_module(), monkeypatch, offline, holder,
                          SPARE, family["remotes"])

    said = capsys.readouterr()
    assert code == 2, said.out + said.err
    assert refusal_detail(said.err, CODE) == [f"REFUSED {CODE}: {NO_READ}"]
    assert remedy(said.err).startswith(
        f"Remediation: `add` reads the work tree's {GITMODULES} before it "
        "writes anything")
    assert "`remove`" not in remedy(said.err)
    assert CHMOD in remedy(said.err)


def failing_commit(module, holder: Path, monkeypatch, then) -> None:
    """`remove`'s one commit made to fail, as a `pre-commit` hook that
    refuses it fails it, after `then()`: every write before it is done."""
    fail = module.CommandFailed(["git", "commit"], holder, 1,
                                "pre-commit: refusing (injected)")

    def commit(*args, **kwargs):
        then()
        raise fail

    monkeypatch.setattr(module, "_commit_one", commit)


def test_a_rollback_meeting_a_refused_gitmodules_types_the_restore(
        holder, offline, tmp_path, monkeypatch, capsys):
    """By the time the commit fails, the `stat` of `.gitmodules` is refused.
    Its step is named with the cure, and the checkout's update is typed:
    3.14 read no section and said the checkout came back only from its
    remote."""
    module = family_module()
    failing_commit(module, holder, monkeypatch,
                   lambda: refused(monkeypatch, GITMODULES))

    code = in_process(module, monkeypatch, isolated(offline, tmp_path), [
        "remove", "--family-root", str(holder), "--member", MEMBER])

    err = capsys.readouterr().err
    assert code == 2, err
    assert "Traceback" not in err
    sentence = err.splitlines()[-1]
    assert (f"NOT {GITMODULES} restored byte for byte: {GITMODULES}: "
            f"Permission denied; {STEP_CURE}") in sentence
    assert UPDATE in sentence
    assert ONLY_REMOTE not in sentence


def test_a_rollback_that_cannot_open_gitmodules_makes_the_mount_again(
        holder, offline, tmp_path, monkeypatch, capsys):
    """`.gitmodules` is put back, then cannot be opened when the checkout
    is asked for (`os.access`): the step is named with its cure, the mount
    is made again, empty, as for a store this user cannot read, and the
    update is typed; typed as printed, with the read given back, the
    commands put the member back on its branch."""
    module = family_module()
    at = git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip()
    failing_commit(module, holder, monkeypatch,
                   lambda: access_refused(monkeypatch, GITMODULES))

    code = in_process(module, monkeypatch, isolated(offline, tmp_path), [
        "remove", "--family-root", str(holder), "--member", MEMBER])

    err = capsys.readouterr().err
    assert code == 2, err
    sentence = err.splitlines()[-1]
    assert (f"from the object store `git rm` keeps: {NO_READ}: "
            f"{READ_CURE}, and {PATH} was made again, empty") in sentence
    assert UPDATE in sentence
    assert ONLY_REMOTE not in sentence
    assert "`mkdir " not in sentence
    monkeypatch.undo()
    typed_by_hand(holder, sentence)
    assert_back_on_main(holder, at)


#: The checkout from the index `remove`'s rollback types for a `.gitmodules`
#: it could not read, before the update: the copy left on disk is the one
#: `git rm` wrote, without the member's section (r1164's MUST-1).
FROM_INDEX = f"`git checkout -- {GITMODULES}`"


def cured_and_typed(holder: Path, sentence: str, at: str) -> None:
    """With the mode given back (the cure), the hook gone, each command the
    rollback's sentence lists typed as printed puts the member back on
    `main` at `at` and leaves the holder clean."""
    git("config", "--local", "--unset", "core.hooksPath", cwd=holder)
    typed_by_hand(holder, sentence)
    assert_back_on_main(holder, at)


def rollback_said(result) -> str:
    """The sentence a `remove` whose commit a hook refused ends with, its
    `.gitmodules` step named with the cure and the checkout's update typed
    after the index's copy, never "only from its remote"."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    sentence = result.stderr.splitlines()[-1]
    assert (f"NOT {GITMODULES} restored byte for byte: {GITMODULES}: "
            f"Permission denied; {STEP_CURE}") in sentence
    assert UPDATE in sentence
    assert sentence.index(FROM_INDEX) < sentence.index(UPDATE)
    assert ONLY_REMOTE not in sentence
    return sentence


@needs_a_mode
def test_a_rollback_meeting_a_gitmodules_linked_into_a_locked_folder(
        holder, offline, tmp_path):
    """A `pre-commit` hook makes `.gitmodules` a link into a folder at mode
    000 and refuses. 3.12 ended the rollback in a traceback with the
    member's directory gone; 3.14 said the checkout came back only from its
    remote. Now the step is named with the cure, the update is typed, and
    the object store is where it was; and with the mode given back the
    commands, typed as printed, put the member back on its branch. Without
    the index's copy first they did not: the linked file is the one `git
    rm` wrote, so the update said `No url found` (r1164's MUST-1)."""
    env = isolated(offline, tmp_path)
    at = git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip()
    locked = tmp_path / "locked"
    moved = f"{locked.as_posix()}/{GITMODULES}"
    hook(holder, tmp_path, "pre-commit",
         f"mkdir '{locked.as_posix()}'\n"
         f"mv {GITMODULES} '{moved}'\n"
         f"ln -s '{moved}' {GITMODULES}\n"
         f"chmod 000 '{locked.as_posix()}'\nexit 1\n")
    try:
        result = remove(holder, env)
    finally:
        if locked.is_dir():
            locked.chmod(0o755)

    sentence = rollback_said(result)
    assert (holder / ".git" / "modules" / PATH / "HEAD").is_file()
    assert f"path = {PATH}" not in Path(moved).read_text(encoding="utf-8")
    cured_and_typed(holder, sentence, at)
    assert not (holder / GITMODULES).is_symlink()


@needs_a_mode
def test_a_rollback_meeting_a_gitmodules_at_000_types_the_index_copy(
        holder, offline, tmp_path):
    """A `pre-commit` hook that only takes the mode off `.gitmodules` and
    refuses. On 3.12 this said the checkout came back only from its remote
    and typed `mkdir`, since git could not read the file either; at
    `4352ac2fd` it typed the update over the copy `git rm` wrote, which
    said `No url found`. Now the index's copy comes first, and the
    commands, typed as printed once the mode is given back, put the member
    back on its branch."""
    env = isolated(offline, tmp_path)
    at = git("rev-parse", "HEAD", cwd=holder / PATH).stdout.strip()
    hook(holder, tmp_path, "pre-commit", f"chmod 000 {GITMODULES}\nexit 1\n")
    try:
        result = remove(holder, env)
    finally:
        (holder / GITMODULES).chmod(0o644)

    sentence = rollback_said(result)
    cured_and_typed(holder, sentence, at)


# --- siblings.py: `submodule_urls` ---------------------------------------------

def test_a_holder_with_no_gitmodules_still_has_no_urls(placement, holder,
                                                       tmp_path):
    """The control, `ENOENT`: no urls, so each member's row is its url."""
    (holder / GITMODULES).rename(tmp_path / "aside")

    assert placement.submodule_urls(holder) == {}


def test_a_gitmodules_that_is_a_directory_still_has_no_urls(
        placement, holder, tmp_path, monkeypatch):
    """The control: a directory at the name is no file, as `is_file()`
    always answered, so there are no urls and its read is never asked,
    even where this user may not read it (r1164's SHOULD-1)."""
    a_directory_at_gitmodules(holder, tmp_path)

    assert placement.submodule_urls(holder) == {}

    access_refused(monkeypatch, GITMODULES)
    assert placement.submodule_urls(holder) == {}


def test_a_gitmodules_linked_into_a_readable_folder_gives_its_urls(
        placement, holder, tmp_path):
    """The control: a link this user can follow gives the urls it gave."""
    urls = placement.submodule_urls(holder)
    assert set(urls) == {f"members/{member}" for member in MEMBERS}

    linked_into_locked(holder, tmp_path)

    assert placement.submodule_urls(holder) == urls


@pytest.mark.parametrize("cause", ["permission", "io-error", "no-read"])
def test_a_gitmodules_that_cannot_be_read_gives_a_refusal_not_no_urls(
        cause, placement, holder, monkeypatch):
    """In process: a refused `stat`, an I/O error and a refused read each
    refuse the run by name, with the cure for the cause; none is `{}`,
    which cloned every member from its row's github url."""
    if cause == "permission":
        refused_stat(monkeypatch, GITMODULES)
    elif cause == "io-error":
        stat_failing(monkeypatch, GITMODULES, EIO)
    else:
        access_refused(monkeypatch, GITMODULES)

    refusal = refusal_of(placement, placement.submodule_urls, holder)

    assert refusal.code == CODE
    assert refusal.detail == {"permission": DENIED, "no-read": NO_READ,
                              "io-error": f"{GITMODULES}: cannot be read "
                                          "(Input/output error)"}[cause]
    assert "nothing was cloned, fetched or run" in refusal.remediation
    if cause == "io-error":
        assert "chmod u+r" not in refusal.remediation
        assert OTHER_CAUSE in refusal.remediation
    else:
        assert CHMOD in refusal.remediation


@needs_a_mode
def test_a_gitmodules_linked_into_a_locked_folder_gives_a_refusal(
        placement, holder, tmp_path):
    locked = linked_into_locked(holder, tmp_path)

    with at_000(locked):
        refusal = refusal_of(placement, placement.submodule_urls, holder)

    assert refusal.code == CODE
    assert refusal.detail == DENIED


def make_or_skip(verb: str) -> None:
    if verb == "make" and shutil.which("make") is None:
        pytest.skip("no make on PATH: `--make` refuses before it reads")


@pytest.mark.parametrize("verb", ["place", "make"])
def test_siblings_refuses_a_gitmodules_whose_stat_is_refused(
        verb, placement, estate, monkeypatch, capsys):
    """`make siblings` and `make park`'s `--make`, in process: the run is
    refused before any member is planned, cloned or run in, exit 2."""
    make_or_skip(verb)
    refused_stat(monkeypatch, GITMODULES)

    code = placement.main(["--root", str(estate["holder"]), "--dry-run",
                           *(["--make", "help"] if verb == "make" else [])])

    said = capsys.readouterr()
    assert code == 2, said.out + said.err
    assert refusal_detail(said.err, CODE) == [f"REFUSED {CODE}: {DENIED}"]
    assert "would clone" not in said.out
    assert "(a) " not in said.out


@needs_a_mode
@pytest.mark.parametrize("how", ["dry-run", "real", "family.py"])
def test_make_siblings_refuses_a_gitmodules_linked_into_a_locked_folder(
        how, estate, offline, tmp_path):
    """As a person runs it: 3.12 ended in a traceback, and 3.14 planned,
    and cloned, each member from `https://github.com/<repository>.git`.
    Now nothing is planned or cloned, exit 2, by either entry point. Run
    where git may use the file protocol alone, so even a member the run
    got wrong could reach no network."""
    holder = estate["holder"]
    locked = linked_into_locked(holder, tmp_path)
    env = {"GIT_ALLOW_PROTOCOL": "file"}

    with at_000(locked):
        if how == "family.py":
            result = run_script(FAMILY, "siblings", "--dry-run",
                                "--family-root", str(holder),
                                env={**offline.env, **env})
        else:
            result = siblings(holder, *(["--dry-run"] if how == "dry-run"
                                        else []), env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, CODE) == [
        f"REFUSED {CODE}: {DENIED}"]
    assert CHMOD in remedy(result.stderr)
    assert "github.com" not in result.stdout
    assert sorted(os.listdir(estate["folder"])) == [NAME]


@needs_a_mode
def test_make_park_runs_in_no_member_past_a_locked_gitmodules(placed,
                                                              tmp_path):
    """`--make`, over clones placed from the url the holder pins: 3.14 read
    no url, took each clone for a different repository and skipped it, and
    3.12 ended in a traceback. Now the verb runs in no member, exit 2."""
    make_or_skip("make")
    locked = linked_into_locked(placed, tmp_path)

    with at_000(locked):
        result = siblings(placed, "--make", "help", "--dry-run")

    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr
    assert refusal_detail(result.stderr, CODE) == [
        f"REFUSED {CODE}: {DENIED}"]
    assert "(a) make help" not in result.stdout


def test_make_siblings_reads_a_gitmodules_linked_into_a_readable_folder(
        estate, tmp_path, family):
    """The control, as a person runs it: each member planned from the url
    `.gitmodules` gives, through the link, exit 0."""
    holder = estate["holder"]
    linked_into_locked(holder, tmp_path)

    result = siblings(holder, "--dry-run")

    assert result.returncode == 0, result.stdout + result.stderr
    for member in MEMBERS:
        assert (f"[{member}] would clone "
                f"{family['remotes'] / (member + '.git')} (.gitmodules)"
                in result.stdout)
