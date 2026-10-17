# SPDX-License-Identifier: Apache-2.0
"""Three of #574's remedies in `family.py add`'s refusal of another spelling
of `members/`, each typed as printed in the state it describes (#685).

1. A `members/` RENAMED WITH `git mv` (`git mv members Members`), staged or
   committed. git renames each member's checkout, its gitlink and its
   section of `.gitmodules` (`path = Members/IRRS`). The remedy was the move
   back of each member's own gitlink (#646), which puts the gitlink back at
   `members/IRRS` and leaves the section where it is: typed as printed, `git
   submodule update` said `No url found for submodule path 'members/IRRS'`,
   and the gate found `gitmodules-path-unnamed`. (Before #646 it was #574's
   `git mv -- Members/IRRS <new name>`.) It is `git mv -- Members members`
   now, which takes every checkout, gitlink and section back, where no
   `members/` is on the disk. On a disk that folds case `Members` IS
   `members/`, and `git mv` would rename it into itself, so the move back
   is printed there, as before.
2. A disk that FOLDS CASE, holding `members/`, that pulled a commit adding
   `Members/README`: the file is on disk as `members/README`, and the
   remedy takes `Members/README` out of the index (`git rm -r --cached`),
   not a `git mv`. Typed as printed, on that disk as the family tests
   emulate it, it touches no file, the file stays at `members/README`,
   untracked, and `add` and the gate pass. The remedy is not changed: this
   test is the line's evidence.
3. A `--sparse` the remedy prints says it needs git 2.34 or later, on every
   git, since older git has none and no other way that types clean.

States that need `git mv members Members` are made on a disk that does not
fold case alone; what a folding disk answers is asked in process
(`disk_as`), as #574's and #646's tests ask it.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git
from test_family import NAME, SPARE, family  # noqa: F401
from test_family_add_member_variant import (
    OTHER_ROW, OTHER_VARIANT, ROW, VARIANT, VARIANT_SHOWN, dry_run_in_process,
    in_the_index, moved_back, refused_in_process, registered,
    typed_as_printed, variant,
)
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant, unborn_holder,
)
from test_family_head_lost_gitmodules import (
    DISKS, assert_passes_in_every_mode,
)
from test_family_members_case_variants import (
    MOUNT, NEEDS_GIT_2_34, added, commit_first, disk_as, disk_folds,
    refused_untouched, remedy_of, type_remedy,
)

#: The refusal's first line for both members' gitlinks under `Members/`.
BOTH = in_the_index(VARIANT_SHOWN, f"`{OTHER_VARIANT}` (a submodule)")

#: The one command the rename back prints.
RENAME_BACK = "git mv -- Members members"


def renamed_back(commit: bool) -> str:
    """The part of the remedy that renames `Members` back with `git mv`."""
    return ("rename `Members` back to members/, since it holds the gitlinks "
            "of members whose rows place them under members/, as a `git mv` "
            "of members/ leaves them: `git mv` takes each checkout and its "
            "section of .gitmodules back with it (`git mv -- Members "
            "members`)" + (", and commit the rename" if commit else ""))


def renamed_with_git(root: Path, committed: bool = False) -> dict:
    """`git mv members Members`, and its commit where `committed`. Returns
    `{row: the commit HEAD records it at}`, as the holder began."""
    commits = {row: git("rev-parse", f"HEAD:{row}", cwd=root).stdout.strip()
               for row in (ROW, OTHER_ROW)}
    git("mv", "members", "Members", cwd=root)
    if committed:
        git("commit", "-qm", "git mv members Members", cwd=root)
    return commits


def folding_skip(tmp_path: Path) -> None:
    """`git mv members Members` renames `members/` into itself where the
    disk folds case, so these states are made on one that does not."""
    if disk_folds(tmp_path):
        pytest.skip("on a disk that folds case `git mv members Members` "
                    "renames members/ into itself")


# --- 1. a members/ renamed with git mv ---------------------------------------

def staged(root: Path) -> tuple:
    """The rename staged: renamed back, nothing is left to commit."""
    return (renamed_with_git(root), BOTH, remedy_of(renamed_back(False)),
            [RENAME_BACK])


def committed(root: Path) -> tuple:
    """The rename committed: renamed back, and that committed."""
    return (renamed_with_git(root, True), BOTH,
            remedy_of(renamed_back(True)), [RENAME_BACK, "git commit"])


def committed_with_a_file(root: Path) -> tuple:
    """The rename committed with a file of its own under `Members/`, written
    as BYTES: it goes back with the rest, to `members/README`."""
    commits = renamed_with_git(root)
    (root / "Members" / "README").write_bytes(b"our own notes\n")
    git("add", "--", "Members/README", cwd=root)
    git("commit", "-qm", "git mv members Members, and a README", cwd=root)
    return (commits, BOTH + ", `Members/README` (a file)",
            remedy_of(renamed_back(True)), [RENAME_BACK, "git commit"])


def after_a_pending_change(root: Path) -> tuple:
    """A pending change in HEAD (`MEMBERS/old` taken out of the index, not
    committed) beside the staged rename: committed first, which commits the
    rename too, so renaming it back has a commit to make after it."""
    plant(root, "100644", "MEMBERS/old")
    git("commit", "-qm", "Track MEMBERS/old", cwd=root)
    git("rm", "-q", "--cached", "--", "MEMBERS/old", cwd=root)
    return (renamed_with_git(root),
            BOTH + "; in HEAD and no longer in the index: `MEMBERS/old` (a "
            "file)",
            remedy_of(commit_first("MEMBERS/old"), renamed_back(True)),
            ["git commit", RENAME_BACK, "git commit"])


#: `{state: how it is made, returning ({row: commit}, the refusal's first
#: line, its remedy, what is typed)}`.
RENAMED = {
    "staged": staged,
    "committed": committed,
    "committed, with a file of its own": committed_with_a_file,
    "after a pending change in HEAD": after_a_pending_change,
}


@pytest.mark.parametrize("state", list(RENAMED))
def test_members_renamed_with_git_mv_is_renamed_back_as_printed(
        family, holder, offline, tmp_path, state):
    """LINE 1: `git mv members Members`, and `add` of another member. The
    dry run and the real run refuse it alike, with the holder exactly as it
    was, and say `git mv -- Members members`, with a commit where one is
    left to make. Typed as printed, both members are where their rows say,
    at the commits they recorded, with their sections and checkouts, the
    gate passes in every mode, and the same `add` goes through."""
    folding_skip(tmp_path)
    commits, first, said, typed = RENAMED[state](holder)
    refused = refused_untouched(offline, holder, family["remotes"],
                                "--dry-run")
    assert refused_untouched(offline, holder, family["remotes"]) == refused
    assert refused == (first, said)
    assert typed_as_printed(holder, said) == typed
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    assert_passes_in_every_mode(holder, 2)
    added(offline, holder, family["remotes"])
    assert_passes_in_every_mode(holder, 3)


def test_an_untracked_file_in_it_goes_back_with_it(family, holder, offline,
                                                    tmp_path):
    """An untracked file under the renamed `Members/` is the rename's to
    take, so it is not named on its own: an `mv` of it printed after `git
    mv` would find nothing there. Typed as printed, it is at
    `members/notes.txt`, untracked, and `add` and the gate pass."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder)
    (holder / "Members" / "notes.txt").write_bytes(b"our own notes\n")
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (BOTH, remedy_of(renamed_back(False)))
    assert typed_as_printed(holder, said[1]) == [RENAME_BACK]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    assert (holder / "members" / "notes.txt").read_bytes() == (
        b"our own notes\n")
    assert_passes_in_every_mode(holder, 2)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("status", "--porcelain", cwd=holder).stdout == (
        "?? members/notes.txt\n")
    assert_passes_in_every_mode(holder, 3)


def test_a_fresh_clone_of_it_is_renamed_back_as_printed(family, holder,
                                                         offline, tmp_path):
    """The committed rename pushed, and a fresh recursive clone of it, its
    checkouts under `Members/`: the same text, and typed as printed the
    clone's gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    remote = family["remotes"] / f"{NAME}.git"
    branch = "w685/renamed-with-git"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=holder)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch)
    said = refused_untouched(offline, clone, family["remotes"], "--dry-run")
    assert said == (BOTH, remedy_of(renamed_back(True)))
    assert typed_as_printed(clone, said[1]) == [RENAME_BACK, "git commit"]
    for row, commit in commits.items():
        registered(clone, family["root"], commit, row)
    assert_passes_in_every_mode(clone, 2)
    added(offline, clone, family["remotes"])


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
def test_only_a_disk_with_no_members_renames_it_back(
        family, holder, family_module, offline, monkeypatch, capsys,
        tmp_path, folding):
    """THE DISK DECIDES. Asked in process of the same layout, a disk that
    does not fold case holds no `members/` and renames `Members` back. One
    that folds case takes `Members` for `members/` itself, where `git mv --
    Members members` would rename it into itself (`members/Members`), so it
    gets #646's move back, as it did before."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder)
    disk_as(monkeypatch, holder, folding)
    rows = {ROW: ([VARIANT], commits[ROW]),
            OTHER_ROW: ([OTHER_VARIANT], commits[OTHER_ROW])}
    move, closing = moved_back(rows, commit=False)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        BOTH, remedy_of(move, *closing) if folding
        else remedy_of(renamed_back(False)))


def members_beside_it(root: Path) -> None:
    """A `members/` on disk beside `Members/`, holding a file: the rename
    would go into it, `members/Members`."""
    (root / "members").mkdir()
    (root / "members" / "notes").write_bytes(b"our own notes\n")


def moved_out_of_the_holder(root: Path) -> None:
    """`Members/` gone from disk, as if moved out of the holder: `git mv`
    of it says `bad source`."""
    os.rename(root / "Members", root.parent / "Members-elsewhere")


def head_alone_holds_one(root: Path) -> None:
    """The rename committed, then one member's gitlink taken out of the
    index and not committed: the rename back would leave it out."""
    git("commit", "-qm", "git mv members Members", cwd=root)
    git("rm", "-q", "--cached", "--", OTHER_VARIANT, cwd=root)


#: `{state: how it is laid out after `git mv members Members`, staged}`.
NOT_RENAMED_BACK = {
    "a members/ on disk beside it": members_beside_it,
    "an entry the index holds under members/": (
        lambda root: plant(root, "100644", "members/notes")),
    "another spelling in the index too": (
        lambda root: plant(root, "100644", "MEMBERS/notes")),
    "a case variant of the mount path under it": (
        lambda root: plant(root, "100644", f"Members/{SPARE}")),
    "an entry under it a sparse checkout keeps off disk": (
        lambda root: git("update-index", "--skip-worktree", "--",
                         OTHER_VARIANT, cwd=root)),
    "a member's gitlink HEAD alone holds": head_alone_holds_one,
    "nothing of it on disk": moved_out_of_the_holder,
}


@pytest.mark.parametrize("state", list(NOT_RENAMED_BACK))
def test_only_members_renamed_whole_is_renamed_back(holder, family_module,
                                                    tmp_path, state):
    """`git mv -- Members members` is printed only where it types clean and
    leaves nothing out: no `members/` on disk, nothing in the index under
    `members/` itself or under a second spelling, no case variant of the
    mount path in it, nothing kept off disk under it, no member's gitlink
    that HEAD alone holds there, and the directory on disk. Elsewhere each
    path keeps its own remedy (the move back of a member's own gitlink, or
    #574's), never `git mv back`."""
    folding_skip(tmp_path)
    renamed_with_git(holder)
    NOT_RENAMED_BACK[state](holder)
    rows = family_module._rows_paths(family_module.Family.open(holder).members)
    found = family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder), rows)
    assert "git mv back" not in [spelled.remedy for spelled in found]
    assert {spelled.remedy for spelled in found
            if spelled.kind == "a submodule"} == {"git update-index"}


def test_nothing_in_it_a_members_own_keeps_its_own_remedy(family_module,
                                                          tmp_path):
    """A `Members/` that holds no member's own gitlink is no `members/`
    renamed: a committed `Members/README` alone, on disk, keeps #574's
    committed `git mv`."""
    root = unborn_holder(tmp_path)
    (root / "Members").mkdir()
    (root / "Members" / "README").write_bytes(b"our own notes\n")
    git("add", "--", "family.yaml", "Members/README", cwd=root)
    git("commit", "-qm", "Notes", cwd=root)
    found = family_module._members_spellings(
        root, SPARE, family_module._members_on_disk(root), frozenset())
    assert [(spelled.target, spelled.remedy) for spelled in found] == [
        ("Members/README", "git mv")]


# --- 2. a folding disk that pulled Members/README ----------------------------

def pulled_members_readme(root: Path, ignorecase: str) -> None:
    """What a disk that folds case holds after pulling a commit that adds
    `Members/README` beside the members: the file in the holder's own
    `members/`, as `members/README`, written as BYTES, while the index and
    HEAD hold `Members/README`, the blob of those bytes. git there runs with
    `core.ignorecase=true`; asked both ways (`DISKS`, as #611's tests ask
    it)."""
    git("config", "--local", "core.ignorecase", ignorecase, cwd=root)
    (root / "members" / "README").write_bytes(b"a file\n")
    plant(root, "100644", "Members/README")
    git("commit", "-qm", "Members/README, as pulled", cwd=root)


@DISKS
def test_a_folding_disk_that_pulled_members_readme_takes_it_out(
        family, holder, family_module, offline, monkeypatch, capsys,
        ignorecase):
    """LINE 2, CLOSED BY THIS TEST: the remedy is `git rm -r --cached --
    Members/README` and a commit, where nothing is on disk in that spelling.
    Each disk, emulated in process (`disk_as`), gives the subprocess's text.
    Typed as printed, the file stays on disk, byte for byte, at
    `members/README`, untracked, the gate passes in every mode, `add` goes
    through, and the gate passes again; committing the file then, under
    `members/`, still gives `family ok`."""
    pulled_members_readme(holder, ignorecase)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said[1] == remedy_of(
        "take what has nothing on disk in that spelling out of the index, "
        "which touches no file (`git rm -r --cached -- Members/README`), "
        "and commit the removal")
    for folding in (False, True):
        with monkeypatch.context() as patched:
            disk_as(patched, holder, folding)
            assert dry_run_in_process(family_module, patched, offline,
                                      holder, family["remotes"],
                                      capsys) == said
    assert type_remedy(holder, said[1]) == [
        "git rm -r --cached -- Members/README", "git commit"]
    assert (holder / "members" / "README").read_bytes() == b"a file\n"
    assert git("status", "--porcelain", cwd=holder).stdout == (
        "?? members/README\n")
    assert_passes_in_every_mode(holder, 2)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("ls-tree", "HEAD", MOUNT, cwd=holder).stdout.startswith(
        "160000 commit ")
    assert_passes_in_every_mode(holder, 3)
    git("add", "--", "members/README", cwd=holder)
    git("commit", "-qm", "members/README", cwd=holder)
    assert_passes_in_every_mode(holder, 3)


# --- 3. --sparse needs git 2.34 or later -------------------------------------

def test_the_move_backs_sparse_says_the_git_it_needs(holder, family_module):
    """LINE 3, for the move back's `git rm --sparse` (#646's S1): asked on
    any git, the text says it needs git 2.34 or later, right after the
    command, and only there. (`git mv --sparse`, #574's, is asked in
    `test_an_entry_a_sparse_checkout_keeps_off_disk_takes_git_mv_sparse`.)"""
    commit = variant(holder)
    git("update-index", "--skip-worktree", "--", VARIANT, cwd=holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sparse=True)
    assert f"--ignore-unmatch -- {VARIANT}`, {NEEDS_GIT_2_34}, then " in move
    assert refused_in_process(family_module, holder)[1] == remedy_of(
        move, *closing)
