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
   `git mv -- Members/IRRS <new name>`.) It is now `git mv -- Members
   members.renaming`, then `git mv -- members.renaming members`, which takes
   every checkout, gitlink and section back, on every disk: on macOS and
   Windows `Members` IS `members/`, where a one-step `git mv -- Members
   members` renames it into itself. An entry under it that the disk lacks,
   which `git mv` refuses (`bad source`), is put back first.
2. A disk that FOLDS CASE, holding `members/`, that pulled a commit adding
   `Members/README`: the file is on disk as `members/README`, and the
   remedy takes `Members/README` out of the index (`git rm -r --cached`),
   not a `git mv`. Typed as printed, on that disk as the family tests
   emulate it, it touches no file, the file stays at `members/README`,
   untracked, and `add` and the gate pass. The remedy is not changed: this
   test is the line's evidence.
3. A `--sparse` the remedy prints says the git it needs, on every git:
   2.38 for `git mv --sparse` of one entry, 2.34 for `git rm --sparse`.

States that need `git mv members Members` are made on a disk that does not
fold case alone, where that command works; what a folding disk answers is
asked in process (`disk_as`), as #574's and #646's tests ask it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git, rmtree
from test_family import NAME, SPARE, family  # noqa: F401
from test_family_add_member_variant import (
    OTHER_ROW, OTHER_VARIANT, REMOVE, ROW, VARIANT, VARIANT_SHOWN,
    dry_run_in_process, in_the_index, moved_back, record, refused_in_process,
    registered, typed_as_printed, variant,
)
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, index_bytes, offline, plant, refusal,
    unborn_holder,
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
#: The same, and a file of the holder's own under `Members/`.
BOTH_AND_A_FILE = BOTH + ", `Members/README` (a file)"

#: The free name the rename back goes through, and its two steps.
FREE = "members.renaming"


def two_steps(free: str = FREE) -> list[str]:
    """The two `git mv` lines of the rename back, through `free`."""
    return [f"git mv -- Members {free}", f"git mv -- {free} members"]


#: What puts back a gitlink the disk lacks.
SUBMODULE_BACK = "git submodule update --init --recursive --"


def renamed_back(commit: bool, free: str = FREE, gone: tuple = (),
                 files: tuple = ()) -> str:
    """The part of the remedy that renames `Members` back, through `free`,
    putting back first each gitlink in `gone` and each file in `files`."""
    back = [f"`{command} {' '.join(names)}`" for command, names in (
        (SUBMODULE_BACK, gone), ("git checkout --", files)) if names]
    first, second = two_steps(free)
    return ((f"put back what the index holds under `Members` and the disk "
             f"does not, {' and '.join(back)}, then " if back else "")
            + "rename `Members` back to members/, since it holds the "
            "gitlinks of members whose rows place them under members/, in "
            "two steps through a name nothing holds, as macOS and Windows "
            "take `Members` for members/ itself: `git mv` takes each "
            "checkout, and each section of .gitmodules that names it, with "
            f"it (`{first}`, then `{second}`)"
            + (", and commit the rename" if commit else ""))


#: The part of the remedy for a change to `.gitmodules` nobody staged.
STAGE_FIRST = ("stage the change to .gitmodules that nobody has staged, or "
               "set it aside, since `git mv` and `git rm` of a gitlink refuse "
               "to run beside one (`git add -- .gitmodules`)")
#: The part of the remedy for a `.gitmodules` the work tree lacks.
RESTORE_FIRST = ("put back the copy of .gitmodules the index holds, which the "
                 "work tree lacks, since git edits each member's section "
                 "there (`git checkout -- .gitmodules`)")


def gitmodules_changed(root: Path) -> None:
    """A change to `.gitmodules` nobody staged, a comment written as
    BYTES."""
    with (root / ".gitmodules").open("ab") as out:
        out.write(b"# our own note\n")


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


def typed_with_local_remotes(monkeypatch, root: Path, said: str) -> list:
    """`typed_as_printed`, with `protocol.file.allow=always` for the typing
    alone: a `git submodule update --recursive` the remedy prints may clone
    a member's legs, whose urls are the fixture's local paths."""
    with monkeypatch.context() as patched:
        count = int(os.environ.get("GIT_CONFIG_COUNT", "0"))
        patched.setenv("GIT_CONFIG_COUNT", str(count + 1))
        patched.setenv(f"GIT_CONFIG_KEY_{count}", "protocol.file.allow")
        patched.setenv(f"GIT_CONFIG_VALUE_{count}", "always")
        return typed_as_printed(root, said)


# --- 1. a members/ renamed with git mv ---------------------------------------

def staged(root: Path) -> tuple:
    """The rename staged: renamed back, nothing is left to commit."""
    return (renamed_with_git(root), BOTH, remedy_of(renamed_back(False)),
            two_steps())


def committed(root: Path) -> tuple:
    """The rename committed: renamed back, and that committed."""
    return (renamed_with_git(root, True), BOTH,
            remedy_of(renamed_back(True)), [*two_steps(), "git commit"])


def staged_ignoring_case(root: Path) -> tuple:
    """The rename staged with `core.ignorecase=true`, as git on macOS and
    Windows runs: the same text, typed the same."""
    git("config", "--local", "core.ignorecase", "true", cwd=root)
    return staged(root)


def committed_with_a_file(root: Path) -> tuple:
    """The rename committed with a file of its own under `Members/`, written
    as BYTES: it goes back with the rest, to `members/README`."""
    commits = renamed_with_git(root)
    (root / "Members" / "README").write_bytes(b"our own notes\n")
    git("add", "--", "Members/README", cwd=root)
    git("commit", "-qm", "git mv members Members, and a README", cwd=root)
    return (commits, BOTH_AND_A_FILE, remedy_of(renamed_back(True)),
            [*two_steps(), "git commit"])


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
            ["git commit", *two_steps(), "git commit"])


def with_the_free_name_taken(root: Path) -> tuple:
    """A file the holder tracks at `members.renaming`: the rename back goes
    through `members.renaming-2`."""
    (root / FREE).write_bytes(b"our own notes\n")
    git("add", "--", FREE, cwd=root)
    git("commit", "-qm", f"A file at {FREE}", cwd=root)
    return (renamed_with_git(root), BOTH,
            remedy_of(renamed_back(False, f"{FREE}-2")),
            two_steps(f"{FREE}-2"))


def one_checkout_gone(root: Path) -> tuple:
    """The rename committed, then one member's checkout deleted: `git mv`
    says `bad source` for it, so it is put back first, from the section that
    names `Members/IRSS` (#685's review, MUST-2)."""
    commits = renamed_with_git(root, True)
    rmtree(root / OTHER_VARIANT)
    return (commits, BOTH,
            remedy_of(renamed_back(True, gone=(OTHER_VARIANT,))),
            [f"{SUBMODULE_BACK} {OTHER_VARIANT}", *two_steps(), "git commit"])


def an_empty_members(root: Path) -> tuple:
    """The rename staged, then both checkouts moved out of the holder,
    leaving `Members/` empty: both are put back first."""
    commits = renamed_with_git(root)
    for name in (VARIANT, OTHER_VARIANT):
        os.rename(root / name, root.parent / name.replace("/", "-"))
    return (commits, BOTH,
            remedy_of(renamed_back(False, gone=(VARIANT, OTHER_VARIANT))),
            [f"{SUBMODULE_BACK} {VARIANT} {OTHER_VARIANT}", *two_steps()])


def nothing_of_it_on_disk(root: Path) -> tuple:
    """The rename staged, then `Members/` itself moved out of the holder:
    both checkouts are put back first, which makes `Members/` again."""
    commits = renamed_with_git(root)
    os.rename(root / "Members", root.parent / "Members-elsewhere")
    return (commits, BOTH,
            remedy_of(renamed_back(False, gone=(VARIANT, OTHER_VARIANT))),
            [f"{SUBMODULE_BACK} {VARIANT} {OTHER_VARIANT}", *two_steps()])


def a_committed_file_deleted(root: Path) -> tuple:
    """The rename committed with a file of its own under `Members/`, then
    that file deleted from disk and not staged: it is checked out again
    first."""
    commits, first, _, _ = committed_with_a_file(root)
    (root / "Members" / "README").unlink()
    return (commits, first,
            remedy_of(renamed_back(True, files=("Members/README",))),
            ["git checkout -- Members/README", *two_steps(), "git commit"])


def gitmodules_unstaged(root: Path) -> tuple:
    """The rename staged, then a change to `.gitmodules` nobody staged, a
    comment written as BYTES: `git mv` of a gitlink refuses to run beside it,
    so it is staged first (#685's review, SHOULD-1)."""
    commits = renamed_with_git(root)
    gitmodules_changed(root)
    return (commits, BOTH, remedy_of(STAGE_FIRST, renamed_back(False)),
            ["git add -- .gitmodules", *two_steps()])


def gitmodules_deleted(root: Path) -> tuple:
    """The rename committed, then `.gitmodules` deleted from the work tree
    and not staged: it is put back first, never staged, since `git add` of
    it would stage the deletion and the commit would then take every
    member's section out of HEAD (#685's review, MUST-A)."""
    commits = renamed_with_git(root, True)
    (root / ".gitmodules").unlink()
    return (commits, BOTH, remedy_of(RESTORE_FIRST, renamed_back(True)),
            ["git checkout -- .gitmodules", *two_steps(), "git commit"])


#: `{state: how it is made, returning ({row: commit}, the refusal's first
#: line, its remedy, what is typed)}`.
RENAMED = {
    "staged": staged,
    "committed": committed,
    "staged, with core.ignorecase=true": staged_ignoring_case,
    "committed, with a file of its own": committed_with_a_file,
    "after a pending change in HEAD": after_a_pending_change,
    "with the free name taken": with_the_free_name_taken,
    "one checkout gone": one_checkout_gone,
    "an empty Members/": an_empty_members,
    "nothing of it on disk": nothing_of_it_on_disk,
    "a committed file deleted from disk": a_committed_file_deleted,
    "a change to .gitmodules nobody staged": gitmodules_unstaged,
    "a .gitmodules deleted from disk": gitmodules_deleted,
}


@pytest.mark.parametrize("state", list(RENAMED))
def test_members_renamed_with_git_mv_is_renamed_back_as_printed(
        family, holder, offline, monkeypatch, tmp_path, state):
    """LINE 1: `git mv members Members`, and `add` of another member. The
    dry run and the real run refuse it alike, with the holder exactly as it
    was, and say to rename `Members` back in two steps through a free name,
    after putting back what the disk lacks under it and staging a change to
    `.gitmodules` nobody staged, with a commit where one is left to make.
    Typed as printed, both members are where their rows say, at the commits
    they recorded, with their sections and checkouts, the gate passes in
    every mode, the same `add` goes through, and the gate passes again."""
    folding_skip(tmp_path)
    commits, first, said, typed = RENAMED[state](holder)
    refused = refused_untouched(offline, holder, family["remotes"],
                                "--dry-run")
    assert refused_untouched(offline, holder, family["remotes"]) == refused
    assert refused == (first, said)
    assert typed_with_local_remotes(monkeypatch, holder, said) == typed
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
    assert typed_as_printed(holder, said[1]) == two_steps()
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
    clone's gate passes, the same `add` goes through, and the gate passes
    again."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    remote = family["remotes"] / f"{NAME}.git"
    branch = "w685/renamed-with-git"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=holder)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch)
    said = refused_untouched(offline, clone, family["remotes"], "--dry-run")
    assert said == (BOTH, remedy_of(renamed_back(True)))
    assert typed_as_printed(clone, said[1]) == [*two_steps(), "git commit"]
    for row, commit in commits.items():
        registered(clone, family["root"], commit, row)
    assert_passes_in_every_mode(clone, 2)
    added(offline, clone, family["remotes"])
    assert_passes_in_every_mode(clone, 3)


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
def test_every_disk_gets_the_same_rename_back(
        family, holder, family_module, offline, monkeypatch, capsys,
        tmp_path, folding):
    """ONE TEXT ON EVERY DISK. Asked in process of the same layout, a disk
    that does not fold case holds no `members/`, and one that folds case
    takes `Members` for `members/` itself: both get the two steps, since
    neither step's destination is on either disk when it runs."""
    folding_skip(tmp_path)
    renamed_with_git(holder)
    disk_as(monkeypatch, holder, folding)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        BOTH, remedy_of(renamed_back(False)))


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
def test_a_folding_disk_that_received_it_renames_it_back(
        family, holder, family_module, offline, monkeypatch, capsys,
        tmp_path, folding):
    """THE RENAME RECEIVED: the index holds `Members/IRRS` and
    `Members/IRSS`, and the directory on disk is spelled `members`, as a
    pull leaves it on a disk that folds case. There `Members` is that very
    directory, and the two steps are printed. On Linux `Members` is not on
    disk at all, a second spelling `git mv` cannot find, and #646's move
    back is printed, as before."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder)
    os.rename(holder / "Members", holder / "members")
    disk_as(monkeypatch, holder, folding)
    move, closing = moved_back({ROW: ([VARIANT], commits[ROW]),
                                OTHER_ROW: ([OTHER_VARIANT],
                                            commits[OTHER_ROW])},
                               commit=False)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        BOTH, remedy_of(renamed_back(False)) if folding
        else remedy_of(move, *closing))


def members_beside_it(root: Path) -> None:
    """A `members/` on disk beside `Members/`, holding a file: the second
    step would go into it, `members/members.renaming`."""
    (root / "members").mkdir()
    (root / "members" / "notes").write_bytes(b"our own notes\n")


def head_alone_holds_one(root: Path) -> None:
    """The rename committed, then one member's gitlink taken out of the
    index and not committed: the rename back would leave it out."""
    git("commit", "-qm", "git mv members Members", cwd=root)
    git("rm", "-q", "--cached", "--", OTHER_VARIANT, cwd=root)


def unmerged_under_it(root: Path) -> None:
    """One member's gitlink under `Members/` unmerged, at stages 1, 2 and 3
    and at no stage 0, with nothing in progress: `git mv` says `source
    directory is empty` (#685's review, SHOULD-1)."""
    commit = git("rev-parse", f":{OTHER_VARIANT}", cwd=root).stdout.strip()
    git("rm", "-q", "--cached", "--", OTHER_VARIANT, cwd=root)
    written = subprocess.run(
        ["git", "update-index", "--index-info"], cwd=str(root),
        input="".join(f"160000 {commit} {stage}\t{OTHER_VARIANT}\n"
                      for stage in (1, 2, 3)).encode("ascii"),
        capture_output=True, check=False)
    assert written.returncode == 0, written.stderr


def gone_where_no_section_names_it(root: Path) -> None:
    """One member's checkout deleted, and its section of `.gitmodules`
    giving `members/IRSS`, staged: no `git submodule update` can put
    `Members/IRSS` back, so nothing is renamed back (#685's review, MUST-2,
    its fallback)."""
    data = (root / ".gitmodules").read_bytes()
    assert data.count(b"path = Members/IRSS") == 1, data
    (root / ".gitmodules").write_bytes(
        data.replace(b"path = Members/IRSS", b"path = members/IRSS"))
    git("add", "--", ".gitmodules", cwd=root)
    rmtree(root / OTHER_VARIANT)


def a_file_where_a_checkout_was(root: Path) -> None:
    """One member's checkout deleted, and a file, written as BYTES, where
    it was: the disk holds the path, and not as the index holds it."""
    rmtree(root / OTHER_VARIANT)
    (root / OTHER_VARIANT).write_bytes(b"our own notes\n")


def a_directory_where_a_file_is(root: Path) -> None:
    """A file `Members/README` in the index, and a directory there on disk:
    the disk holds the path, and not as the index holds it."""
    plant(root, "100644", "Members/README")
    (root / "Members" / "README").mkdir()
    (root / "Members" / "README" / "inner").write_bytes(b"our own notes\n")


def no_symlink_on_windows() -> None:
    """A symlink needs a privilege Windows runners do not grant."""
    if os.name == "nt":
        pytest.skip("a symlink needs a privilege Windows runners do not grant")


def members_a_link_to_it(root: Path) -> None:
    """A link `members -> Members`: no disk's `members/` itself, and the
    second step would say `destination already exists` and leave the holder
    half renamed (#685's review, MUST-B)."""
    no_symlink_on_windows()
    os.symlink("Members", root / "members", target_is_directory=True)


def it_a_link_outside(root: Path) -> None:
    """`Members` a link to a directory outside the holder, holding the
    checkouts: `git mv` of it says `not under version control` (#685's
    review, SHOULD-A)."""
    no_symlink_on_windows()
    os.rename(root / "Members", root.parent / "Members-real")
    os.symlink(os.path.join("..", "Members-real"), root / "Members",
               target_is_directory=True)


#: `{state: how it is laid out after `git mv members Members`, staged}`.
NOT_RENAMED_BACK = {
    "a members/ on disk beside it": members_beside_it,
    "an entry the index holds under members/": (
        lambda root: plant(root, "100644", "members/notes")),
    "a file at members in the index": (
        lambda root: plant(root, "100644", "members")),
    "another spelling in the index too": (
        lambda root: plant(root, "100644", "MEMBERS/notes")),
    "a case variant of the mount path under it": (
        lambda root: plant(root, "100644", f"Members/{SPARE}")),
    "an entry under it a sparse checkout keeps off disk": (
        lambda root: git("update-index", "--skip-worktree", "--",
                         OTHER_VARIANT, cwd=root)),
    "a member's gitlink HEAD alone holds": head_alone_holds_one,
    "an entry under it unmerged": unmerged_under_it,
    "a checkout gone that no section names there": (
        gone_where_no_section_names_it),
    "a file where a checkout was": a_file_where_a_checkout_was,
    "a directory where a file is": a_directory_where_a_file_is,
    "a link members to Members": members_a_link_to_it,
    "Members a link to a directory outside": it_a_link_outside,
}


@pytest.mark.parametrize("state", list(NOT_RENAMED_BACK))
def test_only_members_renamed_whole_is_renamed_back(holder, family_module,
                                                    tmp_path, state):
    """The rename back is printed only where it types clean and leaves
    nothing out: no `members/` on disk but that spelling's own directory,
    nothing in the index at or under `members` itself or under a second
    spelling, no case variant of the mount path in it, nothing under it
    kept off disk or unmerged, no member's gitlink that HEAD alone holds
    there, and every entry under it on disk as the index holds it or able
    to be put back. Elsewhere each path keeps its own remedy (the move back
    of a member's own gitlink, or #574's), never `git mv back`."""
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


def beside_the_move_back(root: Path) -> str:
    """#646's state, IRRS's gitlink moved to `Members/IRRS` in the index
    alone, and a change to `.gitmodules` nobody staged: staged first, as
    `git rm` of a gitlink refuses beside it too. Returns the remedy."""
    commit = variant(root)
    gitmodules_changed(root)
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return remedy_of(STAGE_FIRST, move, *closing)


def beside_a_file_alone(root: Path) -> str:
    """A file `Members/README` in the index, and a change to `.gitmodules`
    nobody staged: `git rm --cached` takes the file out whatever
    `.gitmodules` holds, so nothing is said of it."""
    plant(root, "100644", "Members/README")
    gitmodules_changed(root)
    return remedy_of(
        "take what has nothing on disk in that spelling out of the index, "
        "which touches no file (`git rm -r --cached -- Members/README`)")


def gitmodules_kept_off_disk(root: Path) -> str:
    """#646's state, and a `.gitmodules` a sparse checkout keeps off disk:
    `git checkout --` of it matches nothing, and it is `gitmodules-sparse`'s
    to name, so nothing is said of it here."""
    commit = variant(root)
    git("update-index", "--skip-worktree", "--", ".gitmodules", cwd=root)
    (root / ".gitmodules").unlink()
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return remedy_of(move, *closing)


#: `{state: how it is made, returning the remedy}`.
GITMODULES_STATES = {
    "a change beside a gitlink": beside_the_move_back,
    "a change beside a file alone": beside_a_file_alone,
    "a copy a sparse checkout keeps off disk": gitmodules_kept_off_disk,
}


@pytest.mark.parametrize("state", list(GITMODULES_STATES))
def test_what_gitmodules_needs_first_is_said_beside_a_gitlink(
        holder, family_module, state):
    """What the work tree's `.gitmodules` needs before `git mv` or `git rm`
    of a gitlink is said first wherever the index holds a gitlink the
    refusal names, and only what git can type: nothing beside a file alone,
    nor for a copy a sparse checkout keeps off disk."""
    said = GITMODULES_STATES[state](holder)
    assert refused_in_process(family_module, holder)[1] == said


def test_no_gitmodules_in_the_index_adds_nothing_first(family_module,
                                                       tmp_path):
    """A holder whose index holds no `.gitmodules` at all, and a gitlink
    under `Members/`: nothing is said of the file."""
    root = unborn_holder(tmp_path)
    plant(root, "160000", "Members/X")
    with pytest.raises(family_module.Refusal) as caught:
        family_module._checked_mount_path(root, SPARE, MOUNT, frozenset())
    assert str(caught.value).splitlines()[1] == remedy_of(
        "take what has nothing on disk in that spelling out of the index, "
        "which touches no file (`git rm -r --cached -- Members/X`)")


def test_a_missing_gitmodules_is_put_back_before_the_move_back(
        family, holder, offline):
    """#646's state, and `.gitmodules` deleted from the work tree and not
    staged: put back first, never staged. Typed as printed, HEAD keeps
    every section, IRRS is where its row says, the gate passes in every
    mode, and the same `add` goes through with every member registered
    (#685's review, MUST-A)."""
    commit = variant(holder)
    (holder / ".gitmodules").unlink()
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN),
                    remedy_of(RESTORE_FIRST, move, *closing))
    assert typed_as_printed(holder, said[1]) == [
        "git checkout -- .gitmodules", REMOVE, record(commit), "git commit"]
    registered(holder, family["root"], commit)
    assert_passes_in_every_mode(holder, 2)
    added(offline, holder, family["remotes"])
    assert_passes_in_every_mode(holder, 3)


def unmerged_gitmodules(root: Path) -> bytes:
    """`.gitmodules` unmerged at stages 1, 2 and 3, the other side adding a
    comment, and its work-tree copy holding conflict markers, with nothing
    in progress, as a conflicted `git stash pop` leaves it; all written as
    BYTES. Returns this side's copy, the resolution the test takes."""
    ours = (root / ".gitmodules").read_bytes()
    base = git("rev-parse", ":.gitmodules", cwd=root).stdout.strip()
    theirs = subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=str(root),
        input=ours + b"# theirs\n", capture_output=True,
        check=True).stdout.decode("ascii").strip()
    written = subprocess.run(
        ["git", "update-index", "--index-info"], cwd=str(root),
        input=(f"0 {'0' * 40}\t.gitmodules\n100644 {base} 1\t.gitmodules\n"
               f"100644 {base} 2\t.gitmodules\n"
               f"100644 {theirs} 3\t.gitmodules\n").encode("ascii"),
        capture_output=True, check=False)
    assert written.returncode == 0, written.stderr
    (root / ".gitmodules").write_bytes(
        ours + b"<<<<<<< Updated upstream\n=======\n# theirs\n"
        b">>>>>>> Stashed changes\n")
    return ours


def test_an_unmerged_gitmodules_is_named_first(family, holder, offline,
                                              monkeypatch, tmp_path):
    """The rename committed, and `.gitmodules` unmerged, its work-tree copy
    holding conflict markers: `gitmodules-unstaged` names it first, with its
    own restore, since `git add` of it stages the markers and `git mv` then
    says `bad config line` (#685's review, MUST-A). The index is left as it
    was. With the conflict resolved to this side and staged as printed, the
    rename back is printed and types through: every member is where its
    row says, the gate passes in every mode, and the same `add` goes
    through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    ours = unmerged_gitmodules(holder)
    index = index_bytes(holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 2, result.stdout + result.stderr
    first, said = refusal(result.stderr)
    assert first.startswith("REFUSED gitmodules-unstaged: .gitmodules is "
                            "unmerged in the index.")
    assert said == ("Remediation: resolve the conflict in it and stage the "
                    "result, `git add .gitmodules`, then run the same "
                    "command again.")
    assert index_bytes(holder) == index
    (holder / ".gitmodules").write_bytes(ours)
    git("add", ".gitmodules", cwd=holder)
    refused = refused_untouched(offline, holder, family["remotes"])
    assert refused == (BOTH, remedy_of(renamed_back(True)))
    assert typed_with_local_remotes(monkeypatch, holder, refused[1]) == [
        *two_steps(), "git commit"]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    assert_passes_in_every_mode(holder, 2)
    added(offline, holder, family["remotes"])
    assert_passes_in_every_mode(holder, 3)


#: `{state: (what holds a name like the free one, the name chosen)}`.
FREE_NAMES = {
    "nothing": ((), (), FREE),
    "a file on disk": ((FREE,), (), f"{FREE}-2"),
    "an entry in the index, in another case": ((), ("MEMBERS.RENAMING/x",),
                                               f"{FREE}-2"),
    "both, and the second on disk": ((f"{FREE}-2",), (FREE,), f"{FREE}-3"),
}


@pytest.mark.parametrize("state", list(FREE_NAMES))
def test_the_free_name_is_one_nothing_holds(family_module, tmp_path, state):
    """`_free_name`: `members.renaming`, or the first numbered variant that
    neither the disk nor the index holds, the index asked in any case."""
    on_disk_names, in_index, chosen = FREE_NAMES[state]
    for name in on_disk_names:
        (tmp_path / name).write_bytes(b"x\n")
    assert family_module._free_name(
        tmp_path, {name: [] for name in in_index}) == chosen


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


# --- 3. --sparse says the git it needs ---------------------------------------

def test_the_move_backs_sparse_says_the_git_it_needs(holder, family_module):
    """LINE 3, for the move back's `git rm --sparse` (#646's S1): asked on
    any git, the text says it needs git 2.34 or later, right after the
    command, and only there. (`git mv --sparse`, #574's, which needs 2.38
    for the one entry it names, is asked in
    `test_an_entry_a_sparse_checkout_keeps_off_disk_takes_git_mv_sparse`.)"""
    commit = variant(holder)
    git("update-index", "--skip-worktree", "--", VARIANT, cwd=holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sparse=True)
    assert f"--ignore-unmatch -- {VARIANT}`, {NEEDS_GIT_2_34}, then " in move
    assert refused_in_process(family_module, holder)[1] == remedy_of(
        move, *closing)
