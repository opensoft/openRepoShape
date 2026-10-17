# SPDX-License-Identifier: Apache-2.0
"""`family.py add`'s case-spelling remedies in the seven states #840 names,
each typed as printed in the state it describes, then the holder's gate in
every mode and the same `add`.

1. A section of `.gitmodules` that names a case variant of a row's path,
   with the gitlink at the row's path, a hand edit or #646's old move back:
   `add` went through and committed that `.gitmodules` beside the new
   member, and the gate refused it in every mode. It is named now
   (`family-members-dir-variant`, under the gate's own line `git config -f
   .gitmodules submodule.<name>.path <row path>`), with the commit where
   HEAD's section moved, and the update for a fresh clone, which checks the
   member out nowhere.
2. #574's `git mv` of a directory moved an untracked checkout inside it,
   whose `.git` file then named its store from the wrong place (`git -C`
   said `not a git repository`, measured). Each such checkout is named to
   be deleted by hand before the move, as #828's `CHECKOUT` names one; so
   is one inside a directory an `mv` moves.
3. A case variant of a row's path under `members/` itself (`members/irrs`
   beside the row `members/IRRS`) was named by nothing, and `add` went
   through, in the index, in HEAD or on disk. It is named now, and the
   member's own gitlink there is moved back as #646 moves one.
4. An unmerged `.gitmodules` the work tree lacks too: the rename back's
   commit failed (`Committing is not possible because you have unmerged
   files`). `gitmodules-missing` names it first, as for `remove`.
5. A deletion of `.gitmodules` the holder staged, HEAD holding the file:
   the printed commit took it, and every member's section, out of HEAD.
   HEAD's copy is put back first (`git checkout HEAD -- .gitmodules`), and
   with a copy in the work tree git does not track, `gitmodules-unstaged`
   asks which to keep, first.
6. `Members` a link to a directory outside the holder: the move back's `git
   rm --cached` went through it and failed (`not a git repository`, exit
   128, measured at #828's head). The link is moved out of the way first.
7. An unmerged file at or under a row's path, or at `members` (rv828's
   SHOULD 3): the member's gitlink kept #574's `git mv`, which took it away
   from its row, and `git mv` of an unmerged `members` failed (`conflicted`).
   It is taken out of the index, every stage, and moved out of the way.

States that need two names differing only in case on disk are made on a
disk that does not fold case alone; what a folding disk answers is asked in
process (`disk_as`). No test here needs a git newer than 2.34; measured on
git 2.43 and 2.47.1 (CI runs 2.55).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from conftest import (
    cloned_just_pushed, git, rmtree, submodule_update_through_git,
)
from test_family import NAME, SPARE, family  # noqa: F401
from test_family_add_member_variant import (
    MOVE_OUT, OTHER_ROW, OTHER_VARIANT, REMOVE, ROW, SUBMODULE, VARIANT,
    VARIANT_SHOWN, dry_run_in_process, guarded, in_the_index, moved_back,
    point_back, record, registered, remedy, typed_as_printed, variant,
)
from test_family_add_move_back_sections import (
    POINTED, REMOVE_BOTH, REMOVE_FORCED, SECTIONS, deleted_by_hand,
    file_committed, gate_then_add, mount_moved, set_aside,
)
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant,
)
from test_family_add_spellings_remedies import (
    BOTH, BOTH_AND_A_FILE, STAGE_FIRST, folding_skip, no_symlink_on_windows,
    renamed_back, renamed_with_git, two_steps,
)
from test_family_members_case_variants import (
    DIR_VARIANT, commit_first, disk_as, disk_folds, index_part,
    refused_untouched, remedy_of,
)
from test_family_members_case_variants import move as untracked_moved

#: The refusal's first sentence where every path is a case variant of a
#: row's path under `members/` itself (#840).
ROW_VARIANT = (
    "REFUSED family-members-dir-variant: the family root holds a case "
    "variant of the path of a `members:` row under members/, the same path "
    "as that row's on a case-insensitive disk — ")
#: Where a section astray beside its row's gitlink is found.
IN_SECTION = "in .gitmodules, its gitlink at its row's path"
#: A case variant of the row `members/IRRS` under `members/` itself.
ROW_SPELLED = "members/irrs"


def pointed_back(commit: bool, row: str = ROW) -> str:
    """The part that points the section of `row` back at it (#840)."""
    return ("point each section of .gitmodules that gives a member another "
            "spelling of its row's path back at that path, where the index "
            "records the member's gitlink there already, since add would "
            "commit that .gitmodules beside the new member and a recursive "
            f"clone finds no section for the member's path (`{point_back(row)}"
            "`, then `git add -- .gitmodules`)"
            + (", and commit that" if commit else ""))


def update(*rows: str) -> str:
    """The update that checks each member out at its row's path, last."""
    return (f"then, where nothing is checked out at {' or '.join(rows)}, as "
            f"in a fresh clone, `{SUBMODULE}` checks the member out there")


def section_astray(root: Path, path: str, state: str) -> str:
    """The section of the row `members/IRRS` hand-edited to give `path`,
    staged and committed as `state` says, its gitlink left at the row's
    path. Returns the commit the gitlink records."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()
    git("config", "-f", ".gitmodules", f"submodule.{ROW}.path", path,
        cwd=root)
    if state != "not staged":
        git("add", "--", ".gitmodules", cwd=root)
    if state == "committed":
        git("commit", "-qm", "The section hand-edited", cwd=root)
    return commit


def head_gitmodules_as_before(root: Path, before: Path) -> None:
    """HEAD's `.gitmodules` is the holder's as the test began, byte for
    byte."""
    assert git("show", "HEAD:.gitmodules", cwd=root).stdout == git(
        "show", "HEAD:.gitmodules", cwd=before).stdout


# --- 1. a section astray beside its row's gitlink ----------------------------

#: `{state: (the path the section gives, how it is left, whether HEAD's
#: section moved so that a commit is printed, the refusal's first sentence,
#: what is printed first)}`.
ASTRAY = {
    "committed": (VARIANT, "committed", True, DIR_VARIANT, []),
    "staged": (VARIANT, "staged", False, DIR_VARIANT, []),
    "not staged": (VARIANT, "not staged", False, DIR_VARIANT, [STAGE_FIRST]),
    "under members/ itself": (ROW_SPELLED, "committed", True, ROW_VARIANT,
                              []),
}


@pytest.mark.parametrize("state", list(ASTRAY))
def test_a_section_astray_beside_its_rows_gitlink_is_pointed_back(
        family, holder, offline, state):
    """Line 1: the gitlink at `members/IRRS` and its section giving
    `Members/IRRS` (or `members/irrs`). `add` went through and committed
    that `.gitmodules` beside the new member; the gate refused it in every
    mode (`gitmodules-path-unnamed`, and `member-gitmodules-absent` once
    committed). Now `add` refuses it, the holder as it was, with the gate's
    own line and `git add -- .gitmodules`, the commit only where HEAD's
    section moved (none where it is staged, where `git commit` would fail),
    and a change nobody has staged staged first. Typed as printed, HEAD's
    `.gitmodules` is the holder's again, the gate passes and the same `add`
    goes through."""
    path, left, committed, lead, first = ASTRAY[state]
    commit = section_astray(holder, path, left)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (lead + f"{IN_SECTION}: `{path}` (a section)",
                    remedy_of(*first, pointed_back(committed), update(ROW)))
    assert typed_as_printed(holder, said[1]) == [
        *(["git add -- .gitmodules"] if first else []), point_back(),
        "git add -- .gitmodules", *(["git commit"] if committed else [])]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_fresh_clone_of_a_section_astray_checks_the_member_out(
        family, holder, offline, tmp_path):
    """Line 1, committed and pushed, and a fresh clone: no section gives
    `members/IRRS`, so nothing checks the member out there. The same text;
    typed as printed, the section is pointed back and committed, the update
    checks the member out at its row's path, the clone's gate passes and
    the same `add` goes through. The branch is pushed under a name no other
    test uses."""
    commit = section_astray(holder, VARIANT, "committed")
    remote = family["remotes"] / f"{NAME}.git"
    branch = "w840/section-astray"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=holder)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch,
                               recurse=False)
    submodule_update_through_git(clone, family["remotes"], "-q", "--init",
                                 "--recursive", "--", OTHER_ROW)
    assert not (clone / ROW / ".git").exists(), "premise: not checked out"
    said = refused_untouched(offline, clone, family["remotes"])
    assert said == (DIR_VARIANT + f"{IN_SECTION}: `{VARIANT}` (a section)",
                    remedy_of(pointed_back(True), update(ROW)))
    assert typed_as_printed(clone, said[1]) == [
        point_back(), "git add -- .gitmodules", "git commit", SUBMODULE]
    assert (clone / ROW / "project.yaml").is_file()
    registered(clone, family["root"], commit)
    gate_then_add(offline, clone, family["remotes"])


def test_a_section_astray_beside_a_move_back_is_checked_out_by_its_update(
        family, holder, offline):
    """Line 1 beside #646's move back of the other member: IRSS's gitlink
    at `Members/IRSS`, and IRRS's section giving `Members/IRRS` beside its
    gitlink at its row's path. The section is pointed back and committed,
    the move back follows with its own commit, and the one update closing
    both names both rows. Typed as printed, both members are where their
    rows say, the gate passes and the same `add` goes through."""
    other = variant(holder, OTHER_ROW, OTHER_VARIANT)
    commit = section_astray(holder, VARIANT, "committed")
    move, closing = moved_back({OTHER_ROW: ([OTHER_VARIANT], other)})
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(f"`{OTHER_VARIANT}` (a submodule)")
                    + f"; {IN_SECTION}: `{VARIANT}` (a section)",
                    remedy_of(pointed_back(True), move, *closing[:-1],
                              update(ROW, OTHER_ROW)))
    assert typed_as_printed(holder, said[1]) == [
        point_back(), "git add -- .gitmodules", "git commit",
        f"git rm -r --cached --ignore-unmatch -- {OTHER_VARIANT}",
        record(other, OTHER_ROW), "git commit",
        guarded(OTHER_VARIANT, OTHER_ROW)]
    registered(holder, family["root"], commit)
    registered(holder, family["root"], other, OTHER_ROW)
    gate_then_add(offline, holder, family["remotes"])


# --- 2. a checkout inside a directory moved ----------------------------------

def checkout_inside(root: Path, remotes: Path, tracked_file: bool) -> str:
    """`Members/X`, holding a file committed there where `tracked_file`,
    and a checkout of another member at `Members/X/Y` that `git submodule
    add` made, its own legs checked out in it, then taken out of the index
    with its section: git tracks it no more, its `.git` file names its
    store by a path relative to it, and a file not committed is written in
    it, as BYTES. Returns the checkout's path."""
    if disk_folds(root):
        pytest.skip("`Members/X` beside `members/` needs a disk that does "
                    "not fold case")
    (root / "Members" / "X").mkdir(parents=True)
    if tracked_file:
        (root / "Members" / "X" / "notes").write_bytes(b"our own notes\n")
        git("add", "--", "Members/X/notes", cwd=root)
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(remotes / "IRSS.git"), "Members/X/Y", cwd=root)
    # Its legs are checkouts inside it, which are its own, not named again.
    submodule_update_through_git(root / "Members" / "X" / "Y", remotes, "-q",
                                 "--init")
    assert (root / "Members" / "X" / "Y" / "spec" / ".git").is_file()
    git("rm", "-q", "--cached", "--", "Members/X/Y", cwd=root)
    git("config", "-f", ".gitmodules", "--remove-section",
        "submodule.Members/X/Y", cwd=root)
    git("add", "--", ".gitmodules", cwd=root)
    if tracked_file:
        git("commit", "-qm", "A file in Members/X", cwd=root)
    (root / "Members" / "X" / "Y" / "WIP.txt").write_bytes(b"not committed\n")
    assert (root / "Members" / "X" / "Y" / ".git").is_file()
    return "Members/X/Y"


def checkout_first(*names: str) -> str:
    """The part that names each checkout to delete by hand first."""
    named = " and ".join(f"`{name}`" for name in names)
    status = " or ".join(f"`git -C {name} status`" for name in names)
    return ("first delete by hand each checkout git does not track inside a "
            f"directory moved below, {named}, once nothing only it holds is "
            "needed: git mv and mv of a directory move everything in it, "
            "and would leave the checkout's .git file, which names its store "
            "by a path relative to it, pointing nowhere, while its commits are "
            "kept in that store, so only what is not committed is in it alone "
            f"({status} shows it)")


#: `{state: (whether a file in `Members/X` is committed, the refusal's
#: places, the part that moves `Members/X`, what is typed)}`.
INSIDE = {
    "under a git mv": (
        True, "in the index: `Members/X/notes` (a file); on disk and "
        "untracked: `Members/X/Y` (a directory)",
        index_part(rename=["Members/X"], commit="the rename"),
        ["git mv -- Members/X renamed-1", "git commit"]),
    "under an mv": (
        False, "on disk and untracked: `Members/X` (a directory), "
        "`Members/X/Y` (a directory)", untracked_moved("Members/X"),
        ["mv -- Members/X ../moved-1"]),
}


@pytest.mark.parametrize("state", list(INSIDE))
def test_a_checkout_inside_a_directory_moved_is_named_first(family, holder,
                                                            offline, state):
    """Line 2: #574's `git mv -- Members/X <new name>` moved the untracked
    checkout at `Members/X/Y` with it, and `git -C <new name>/Y status`
    then said `not a git repository` (measured at #828's head); an `mv` of
    an untracked `Members/X` does the same. The checkout is named first now,
    to be deleted by hand once nothing only it holds is needed. Typed as
    printed, with the checkout's file not committed read by `git -C
    Members/X/Y status` and the checkout deleted by hand before the move,
    its commits are still in the holder's store, the gate passes and the
    same `add` goes through."""
    tracked_file, places, moving, typed = INSIDE[state]
    checkout = checkout_inside(holder, family["remotes"], tracked_file)
    store = holder / ".git" / "modules" / checkout
    kept = git(f"--git-dir={store}", "rev-parse", "HEAD",
               cwd=holder).stdout.strip()
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + places,
                    remedy_of(checkout_first(checkout), moving))
    assert typed_as_printed(holder, said[1],
                            deleted_by_hand(checkout)) == typed
    assert not os.path.lexists(holder / checkout)
    # The store's `core.worktree` names the checkout deleted by hand.
    assert git(f"--git-dir={store}", f"--work-tree={store}", "cat-file",
               "-t", kept, cwd=holder).stdout == "commit\n"
    gate_then_add(offline, holder, family["remotes"])


def test_a_checkout_git_tracks_inside_a_directory_moved_is_not_named(
        holder, family_module, family):
    """Line 2's control: the checkout at `Members/X/Y` still a gitlink in
    the index, which `git mv` of `Members/X` moves with its `.git` file
    mended (measured: `git -C <new name>/Y status` exits 0), so only the
    directory's own `git mv` is named."""
    checkout_inside(holder, family["remotes"], True)
    git("add", "--", "Members/X/Y", cwd=holder)
    found = family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder), frozenset())
    assert [(spelled.where, spelled.target, spelled.remedy)
            for spelled in found] == [("in the index", "Members/X", "git mv"),
                                      ("in the index", "Members/X", "git mv")]


# --- 3. a case variant of a row's path under members/ itself -----------------

def spelled_in_the_index(root: Path) -> tuple:
    """A file `members/irrs` in the index and HEAD, not on disk."""
    plant(root, "100644", ROW_SPELLED)
    git("commit", "-qm", "A file at members/irrs", cwd=root)
    return (f"in the index: `{ROW_SPELLED}` (a file)",
            [index_part(unstage=[ROW_SPELLED], commit="the removal")],
            [f"git rm -r --cached -- {ROW_SPELLED}", "git commit"])


def spelled_on_disk(root: Path) -> tuple:
    """A file `members/irrs` committed and on disk."""
    if disk_folds(root):
        pytest.skip("a file `members/irrs` beside `members/IRRS` needs a "
                    "disk that does not fold case")
    file_committed(root, ROW_SPELLED)
    return (f"in the index: `{ROW_SPELLED}` (a file)",
            [index_part(rename=[ROW_SPELLED], commit="the rename")],
            [f"git mv -- {ROW_SPELLED} renamed-1", "git commit"])


def spelled_gitlink(root: Path) -> tuple:
    """The member's own gitlink moved, in the index alone, to
    `members/irrs`, and committed: #646's state under `members/` itself."""
    commit = variant(root, ROW, ROW_SPELLED)
    move, closing = moved_back({ROW: ([ROW_SPELLED], commit)})
    return (f"in the index: `{ROW_SPELLED}` (a submodule)", [move, *closing],
            [f"git rm -r --cached --ignore-unmatch -- {ROW_SPELLED}",
             record(commit), "git commit", guarded(ROW_SPELLED, ROW)])


def spelled_untracked(root: Path) -> tuple:
    """An untracked directory `members/irrs` beside `members/IRRS`."""
    if disk_folds(root):
        pytest.skip("`members/irrs` beside `members/IRRS` needs a disk that "
                    "does not fold case")
    (root / ROW_SPELLED).mkdir()
    (root / ROW_SPELLED / "notes").write_bytes(b"our own notes\n")
    return (f"on disk and untracked: `{ROW_SPELLED}` (a directory)",
            [untracked_moved(ROW_SPELLED)],
            [f"mv -- {ROW_SPELLED} ../moved-1"])


def spelled_in_head_alone(root: Path) -> tuple:
    """A file `members/irrs` committed, its removal staged."""
    plant(root, "100644", ROW_SPELLED)
    git("commit", "-qm", "A file at members/irrs", cwd=root)
    git("rm", "-q", "--cached", "--", ROW_SPELLED, cwd=root)
    return (f"in HEAD and no longer in the index: `{ROW_SPELLED}` (a file)",
            [commit_first(ROW_SPELLED)], ["git commit"])


def spelled_second_gitlink(root: Path) -> tuple:
    """A second gitlink at `members/irrs`, the row's own at its path."""
    plant(root, "160000", ROW_SPELLED)
    git("commit", "-qm", "A gitlink at members/irrs", cwd=root)
    return (f"in the index: `{ROW_SPELLED}` (a submodule)",
            [index_part(unstage=[ROW_SPELLED], commit="the removal")],
            [f"git rm -r --cached -- {ROW_SPELLED}", "git commit"])


def spelled_section_removal_staged(root: Path) -> tuple:
    """The section of `members/IRRS` giving `members/irrs`, committed, then
    the gitlink's removal staged: #828's `IN_GITMODULES` under `members/`
    itself, put back at HEAD's commit with its section."""
    commit = section_astray(root, ROW_SPELLED, "committed")
    git("rm", "-q", "--cached", "--", ROW, cwd=root)
    move, closing = moved_back({}, sections=(ROW,),
                               staged={ROW: (ROW_SPELLED, commit)})
    return ("in .gitmodules, its gitlink's removal staged: "
            f"`{ROW_SPELLED}` (a submodule)", [move, *closing],
            [f"git rm -r --cached --ignore-unmatch -- {ROW_SPELLED}",
             record(commit), point_back(), "git add -- .gitmodules",
             "git commit", guarded(ROW_SPELLED, ROW)])


#: `{state: how it is made, returning (the places, the remedy's parts, what
#: is typed)}`.
SPELLED_HERE = {
    "a file in the index": spelled_in_the_index,
    "a file on disk": spelled_on_disk,
    "the member's own gitlink": spelled_gitlink,
    "a directory on disk": spelled_untracked,
    "a file in HEAD alone": spelled_in_head_alone,
    "a second gitlink": spelled_second_gitlink,
    "a section, its gitlink's removal staged": spelled_section_removal_staged,
}


@pytest.mark.parametrize("state", list(SPELLED_HERE))
def test_a_case_variant_of_a_rows_path_under_members_is_named(
        family, holder, offline, state):
    """Line 3: `members/irrs` beside the row `members/IRRS`, one path on
    macOS and Windows. Nothing named it and `add` went through: in the
    index, on disk, in HEAD alone, and for the member's own gitlink there,
    which the gate refuses (`member-gitlink-unnamed`). Now each is named
    as `family-members-dir-variant`, with #574's remedy, or #646's move
    back for the member's own gitlink. Typed as printed, nothing is at
    `members/irrs` in the index or HEAD, the member is where its row says,
    the gate passes and the same `add` goes through."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    places, parts, typed = SPELLED_HERE[state](holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (ROW_VARIANT + places, remedy_of(*parts))
    assert typed_as_printed(holder, said[1]) == typed
    for listed in (git("ls-tree", "-r", "--name-only", "HEAD", cwd=holder),
                   git("ls-files", cwd=holder)):
        assert ROW_SPELLED not in listed.stdout.splitlines()
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
@pytest.mark.parametrize("state", ["a section astray",
                                   "a gitlink under members/ itself"])
def test_every_disk_gives_the_same_answer(family, holder, family_module,
                                          offline, monkeypatch, capsys,
                                          state, folding):
    """Lines 1 and 3 asked in process of a disk that folds case and of one
    that does not (`disk_as`): one text on both, since each reads the
    index, HEAD and `.gitmodules`, never the disk."""
    if state == "a section astray":
        section_astray(holder, VARIANT, "committed")
        expected = (DIR_VARIANT + f"{IN_SECTION}: `{VARIANT}` (a section)",
                    remedy_of(pointed_back(True), update(ROW)))
    else:
        commit = variant(holder, ROW, ROW_SPELLED)
        move, closing = moved_back({ROW: ([ROW_SPELLED], commit)})
        expected = (ROW_VARIANT + f"in the index: `{ROW_SPELLED}` (a "
                    "submodule)", remedy_of(move, *closing))
    disk_as(monkeypatch, holder, folding)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == expected


# --- 4. an unmerged .gitmodules the work tree lacks --------------------------

def blob(root: Path, data: bytes) -> str:
    """A blob of `data`, written as BYTES."""
    return subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(root), input=data, capture_output=True,
                          check=True).stdout.decode("ascii").strip()


def head_bytes(root: Path, path: str) -> bytes:
    """HEAD's copy of `path`, as BYTES."""
    return subprocess.run(["git", "show", f"HEAD:{path}"], cwd=str(root),
                          capture_output=True, check=True).stdout


def unmerged_at(root: Path, name: str, stages: tuple[bytes, ...]) -> None:
    """`name` unmerged, a file at stages 1, 2 and 3 holding `stages`, and at
    no stage 0, with nothing in progress, as a conflicted `git stash pop`
    leaves it, written by `update-index --index-info` as BYTES."""
    git("rm", "-q", "--cached", "--ignore-unmatch", "--", name, cwd=root)
    written = subprocess.run(
        ["git", "update-index", "--index-info"], cwd=str(root),
        input="".join(f"100644 {blob(root, data)} {stage}\t{name}\n"
                      for stage, data in enumerate(stages, 1)
                      ).encode("utf-8"),
        capture_output=True, check=False)
    assert written.returncode == 0, written.stderr


def test_an_unmerged_gitmodules_the_work_tree_lacks_is_named_first(
        family, holder, offline, tmp_path):
    """Line 4: `git mv members Members`, committed, then `.gitmodules`
    unmerged (the base, this side's HEAD copy and another) and deleted from
    the work tree. `add` printed the rename back, whose commit failed
    (`Committing is not possible because you have unmerged files`, measured
    at #828's head). Now `gitmodules-missing` comes first, with the restore
    git takes there, as `remove` prints it. Typed as printed, the conflict
    written back and resolved by hand to HEAD's copy, then staged, the next
    refusal is the rename back; typed, both members are where their rows
    say, the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    ours = head_bytes(holder, ".gitmodules")
    unmerged_at(holder, ".gitmodules",
                (ours + b"# base\n", ours, ours + b"# theirs\n"))
    (holder / ".gitmodules").unlink()
    assert refused_untouched(offline, holder, family["remotes"]) == (
        "REFUSED gitmodules-missing: .gitmodules is not in the work tree, "
        "though the index holds one unmerged and HEAD holds one. The remedy "
        "for what `add` found under another spelling of members/ edits each "
        "member's section in the work tree's .gitmodules, and its commit "
        "fails while an entry is unmerged (`Committing is not possible "
        "because you have unmerged files`). No git command that writes was "
        "run and nothing was written.",
        "Remediation: write the conflicted file back, `git checkout --merge "
        "-- .gitmodules`, resolve it and stage the result, `git add "
        ".gitmodules`, and run the same command again.")
    git("checkout", "--merge", "--", ".gitmodules", cwd=holder)
    assert b"<<<<<<< " in (holder / ".gitmodules").read_bytes()
    (holder / ".gitmodules").write_bytes(ours)
    git("add", ".gitmodules", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (BOTH, remedy_of(renamed_back(True)))
    assert typed_as_printed(holder, said[1]) == [*two_steps(), "git commit"]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


# --- 5. a deletion of .gitmodules already staged -----------------------------

#: The part that puts back HEAD's copy of a `.gitmodules` whose deletion is
#: staged and that the work tree lacks.
DELETED_FIRST = (
    "put back HEAD's copy of .gitmodules, in the index and the work tree, "
    "since its deletion is staged and the work tree lacks it: git edits each "
    "member's section there, and any commit would take the deletion, and "
    "every member's section with it, out of HEAD (`git checkout HEAD -- "
    ".gitmodules`)")
RESTORED = "git checkout HEAD -- .gitmodules"


def beside_the_rename_back(root: Path) -> tuple:
    """`git mv members Members`, committed."""
    if disk_folds(root):
        pytest.skip("on a disk that folds case `git mv members Members` "
                    "renames members/ into itself")
    commits = renamed_with_git(root, True)
    return (BOTH, [renamed_back(True)], [*two_steps(), "git commit"],
            commits)


def beside_the_move_back(root: Path) -> tuple:
    """#646's state: IRRS's gitlink at `Members/IRRS`, committed."""
    commit = variant(root)
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return (in_the_index(VARIANT_SHOWN), [move, *closing],
            [REMOVE, record(commit), "git commit", MOVE_OUT], {ROW: commit})


def beside_a_file(root: Path) -> tuple:
    """A file `Members/README` committed, no gitlink in another spelling:
    the rename's own commit took the deletion as well."""
    if disk_folds(root):
        pytest.skip("`Members/README` beside `members/` needs a disk that "
                    "does not fold case")
    file_committed(root, "Members/README")
    return (DIR_VARIANT + "in the index: `Members/README` (a file)",
            [index_part(rename=["Members/README"], commit="the rename")],
            ["git mv -- Members/README renamed-1", "git commit"], {})


#: `{state: how it is made, returning (the refusal's first line, the
#: remedy's other parts, what is typed after the restore, {row: its
#: commit})}`.
DELETED = {"beside the rename back": beside_the_rename_back,
           "beside the move back": beside_the_move_back,
           "beside a file": beside_a_file}


@pytest.mark.parametrize("state", list(DELETED))
def test_a_deletion_of_gitmodules_staged_is_put_back_first(family, holder,
                                                           offline, state):
    """Line 5: `git rm .gitmodules`, HEAD holding the file, beside a
    spelling remedy. Typed as printed, its commit took `.gitmodules`, and
    every member's section, out of HEAD (the gate then found
    `member-gitmodules-absent` for each member, measured at #828's head).
    Now HEAD's copy is put back first. Typed as printed, HEAD's
    `.gitmodules` is the holder's again, each member is where its row says,
    the gate passes and the same `add` goes through."""
    first, parts, typed, commits = DELETED[state](holder)
    git("rm", "-q", "--", ".gitmodules", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (first, remedy_of(DELETED_FIRST, *parts))
    assert typed_as_printed(holder, said[1]) == [RESTORED, *typed]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    head_gitmodules_as_before(holder, family["root"])
    gate_then_add(offline, holder, family["remotes"])


def test_a_deletion_staged_beside_a_copy_git_does_not_track_comes_first(
        family, holder, offline):
    """Line 5, `git rm --cached .gitmodules`: the work tree keeps a copy
    git does not track. The move back's commit took the deletion, and the
    copy was left untracked (measured at #828's head). Which copy to keep is
    the person's, so `gitmodules-unstaged` asks it first; its first choice
    typed as printed, the move back follows, and typed, the member is where
    its row says, the gate passes and the same `add` goes through."""
    commit = variant(holder)
    git("rm", "-q", "--cached", "--", ".gitmodules", cwd=holder)
    assert refused_untouched(offline, holder, family["remotes"]) == (
        "REFUSED gitmodules-unstaged: the work tree has a .gitmodules and the "
        "index does not: its deletion is staged. `add` edits the work tree's "
        "copy and commits .gitmodules with its own change in it, so the work "
        "tree's copy must be the one the index holds: a change nobody has "
        "staged is not this command's to commit. No git command that writes "
        "was run and nothing was written.",
        "Remediation: which copy to keep is a person's to say. To keep the "
        "work tree's, stage it, `git add .gitmodules`; to put back HEAD's, in "
        "the index and the work tree, `git checkout HEAD -- .gitmodules`. "
        "Then run the same command again.")
    git("add", ".gitmodules", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN), remedy(commit))
    assert typed_as_printed(holder, said[1]) == [
        REMOVE, record(commit), "git commit", MOVE_OUT]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


# --- 6. Members a link to a directory outside the holder ---------------------

def link_out(*links: str) -> str:
    """The part that moves each link out of the way first (#840)."""
    moved = " and ".join(f"`mv -- {link} <new name>`" for link in links)
    return ("move each symbolic link that the index holds entries under out "
            f"of the way first ({moved}), which moves the link and not what it "
            "names: every member is mounted under members/, which must be a "
            "plain directory of the holder's own, and git goes through the "
            "link, where `git rm --cached` of a gitlink under it fails (`not a "
            "git repository`), since a checkout where it points names its "
            "store by a path relative to it")


@pytest.mark.parametrize("with_file", [False, True],
                         ids=["its gitlinks", "and a file under it"])
def test_members_a_link_outside_the_holder_is_moved_out_first(
        family, holder, offline, tmp_path, with_file):
    """Line 6: `git mv members Members`, committed, then `Members` moved
    outside the holder and a link left in its place. The move back's `git
    rm -r --cached` went through the link and failed (`fatal: not a git
    repository: Members/IRRS/../../.git/modules/members/IRRS`, exit 128,
    measured at #828's head, whose set-aside part does not reach it). Now
    the link is named first and moved out of the way, and a file under it
    is taken out of the index, nothing of it being on disk in the holder,
    where a `git mv` of it would fail once the link is gone (`bad source`).
    Typed as printed, both gitlinks and sections are back, the update
    checks both members out at their rows' paths, the gate passes and the
    same `add` goes through."""
    no_symlink_on_windows()
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    if with_file:
        file_committed(holder, "Members/README")
    os.rename(holder / "Members", holder.parent / "Members-real")
    os.symlink(os.path.join("..", "Members-real"), holder / "Members",
               target_is_directory=True)
    move, closing = moved_back({ROW: ([VARIANT], commits[ROW]),
                                OTHER_ROW: ([OTHER_VARIANT],
                                            commits[OTHER_ROW])},
                               sections=SECTIONS)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == ((BOTH_AND_A_FILE if with_file else BOTH)
                    + "; on disk and untracked: `Members` (a symlink)",
                    remedy_of(link_out("Members"), *(
                        [index_part(unstage=["Members/README"],
                                    commit="the removal")] if with_file
                        else []), move, *closing))
    assert typed_as_printed(holder, said[1]) == [
        "mv -- Members ../moved-1",
        *(["git rm -r --cached -- Members/README", "git commit"]
          if with_file else []), REMOVE_BOTH, record(commits[ROW]),
        record(commits[OTHER_ROW], OTHER_ROW), *POINTED, "git commit",
        MOVE_OUT, guarded(OTHER_VARIANT, OTHER_ROW), SUBMODULE]
    assert os.path.islink(holder.parent / "moved-1")
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


def test_a_link_at_a_variant_the_index_holds_is_refused_first(
        family, holder, offline):
    """The coordinator's added state for #840 (w761's candidate 8 on #828):
    #646's state, the member's gitlink at `Members/IRRS` in the index, and
    a link there on disk to the member's checkout. git 2.45.1 and later
    refuse `git status` itself (`expected submodule path 'Members/IRRS' not
    to be a symbolic link`, measured on 2.47.1). ALREADY ANSWERED at #828's
    head, measured on git 2.43 and 2.47.1: `add` reads no `git status`
    there and gives its spelling refusal first, no `fatal:` and no
    traceback. Typed as printed, the move back's guard keeps the link (`[
    Members/IRRS -ef members/IRRS ]` follows it to the row's own directory),
    and the next `add` names it on disk, with its `mv`; typed, the member
    is where its row says, the gate passes and the same `add` goes
    through, on every git."""
    no_symlink_on_windows()
    if disk_folds(holder):
        pytest.skip("a link at `Members/IRRS` beside `members/IRRS` needs a "
                    "disk that does not fold case")
    commit = variant(holder)
    (holder / "Members").mkdir()
    os.symlink(os.path.join("..", ROW), holder / VARIANT,
               target_is_directory=True)
    said = refused_untouched(offline, holder, family["remotes"], status=False)
    assert said == (in_the_index(VARIANT_SHOWN), remedy(commit))
    assert typed_as_printed(holder, said[1]) == [
        REMOVE, record(commit), "git commit", MOVE_OUT]
    assert os.path.islink(holder / VARIANT)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + f"on disk and untracked: `{VARIANT}` (a "
                    "symlink)", remedy_of(untracked_moved(VARIANT)))
    assert typed_as_printed(holder, said[1]) == [f"mv -- {VARIANT} ../moved-1"]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


# --- 7. an unmerged file in the way of the move back -------------------------

#: A file under the row's path.
NOTES = f"{ROW}/notes"
#: The three sides of an unmerged file, and what a conflict leaves on disk.
SIDES = (b"base\n", b"ours\n", b"theirs\n")
MARKED = b"<<<<<<< ours\nours\n=======\ntheirs\n>>>>>>> theirs\n"


def unmerged_file(root: Path, name: str, on_disk: bool) -> None:
    """`name` unmerged, its conflict on disk where `on_disk`."""
    unmerged_at(root, name, SIDES)
    if on_disk:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(MARKED)


#: `{state: (the entry, whether it is on disk, whether `git mv
#: members/IRRS Members/IRRS` is committed)}`.
UNMERGED_IN_THE_WAY = {
    "under the row's path, on disk": (NOTES, True, True),
    "at the row's path, on disk": (ROW, True, True),
    "under the row's path, off disk": (NOTES, False, True),
    "off disk, the move staged": (NOTES, False, False),
}


@pytest.mark.parametrize("state", list(UNMERGED_IN_THE_WAY))
def test_an_unmerged_file_in_the_way_is_set_aside_as_git_allows(
        family, holder, offline, tmp_path, state):
    """Line 7 (rv828's SHOULD 3): `git mv members/IRRS Members/IRRS`,
    committed, then a file unmerged at or under the row's path. The
    member's gitlink at the variant kept #574's `git mv -- Members/IRRS
    <new name>`, which took it away from its row, and the commit after it
    failed (measured at #828's head). Now it is the member's own: the file
    is taken out of the index, every stage, with `git rm -r --cached`,
    which git allows where `git mv` refuses a conflicted entry, and moved
    out of the way where it is on disk, then the gitlink and its section
    are moved back. A removal of what HEAD does not hold leaves nothing to
    commit, so where the move is staged no commit is printed, which `git
    commit` would refuse. Typed as printed, the checkout at the variant
    deleted by hand, the member is checked out where its row says, the gate
    passes and the same `add` goes through."""
    folding_skip(tmp_path)
    entry, on_disk, committed = UNMERGED_IN_THE_WAY[state]
    commit = mount_moved(holder, committed)
    unmerged_file(holder, entry, on_disk)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, commit=committed,
                               sections=(ROW,), forced=not committed)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN), remedy_of(
        set_aside([entry], {}, unmerged=[entry],
                  moved=[entry] if on_disk else []), move, *closing))
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        f"git rm -r --cached -- {entry}",
        *([f"mv -- {entry} ../moved-1"] if on_disk else []),
        REMOVE if committed else REMOVE_FORCED, record(commit),
        *POINTED[::2], *(["git commit"] if committed else []), MOVE_OUT,
        SUBMODULE]
    if on_disk:
        assert (holder.parent / "moved-1").read_bytes() == MARKED
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_an_unmerged_members_file_off_disk_is_set_aside_as_git_allows(
        family, holder, offline, tmp_path):
    """Line 7, at `members` itself: `git mv members Members`, committed,
    and a file unmerged at `members`, off disk. Each `git update-index` ran,
    and the commit failed (measured at #828's head). Now it is taken out of
    the index, every stage, first. Typed as printed, both members are where
    their rows say, the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    unmerged_file(holder, "members", False)
    move, closing = moved_back({ROW: ([VARIANT], commits[ROW]),
                                OTHER_ROW: ([OTHER_VARIANT],
                                            commits[OTHER_ROW])},
                               sections=SECTIONS)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (BOTH, remedy_of(
        set_aside(["members"], {}, unmerged=["members"]), move, *closing))
    assert typed_as_printed(holder, said[1], lambda root: [
        rmtree(root / name) for name in (VARIANT, OTHER_VARIANT)]) == [
        "git rm -r --cached -- members", REMOVE_BOTH, record(commits[ROW]),
        record(commits[OTHER_ROW], OTHER_ROW), *POINTED, "git commit",
        MOVE_OUT, guarded(OTHER_VARIANT, OTHER_ROW), SUBMODULE]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


@pytest.mark.parametrize("in_head", [False, True],
                         ids=["HEAD holds none", "HEAD holds the file"])
def test_an_unmerged_members_file_on_disk_is_taken_out_then_moved(
        family, holder, offline, tmp_path, in_head):
    """Line 7, at `members` itself and on disk: `member-path-unaddable`
    names the file first, and its `git mv -- members <new name>` failed
    (`fatal: conflicted, source=members`, exit 128, measured at #828's
    head). Now it says to take the file out of the index, every stage, then
    move it with `mv`, and, where HEAD holds the file, to commit that
    removal on its own first. Typed as printed, the next refusal is the
    rename back; typed, both members are where their rows say, the gate
    passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    if in_head:
        file_committed(holder, "members")
    unmerged_file(holder, "members", True)
    assert refused_untouched(offline, holder, family["remotes"]) == (
        "REFUSED member-path-unaddable: git will not add the mount path "
        "members/IRQS: `members` is a tracked file in the family root, not a "
        "directory, so nothing can be mounted under it, and `git submodule "
        "add` would fail at its mount (`Not a directory`) after the member "
        "was read. No git command that writes was run and nothing was "
        "written.",
        "Remediation: every member is mounted under members/, which must be a "
        "plain directory of the holder's own. Take it out of the index, every "
        "stage, which touches no file, since `git mv` refuses a conflicted "
        "entry (`git rm --cached -- members`), then move it aside, `mv -- "
        "members <new name>`"
        + (", and commit the removal on its own first, since the add's own "
           "commit names .gitmodules, members/IRQS and family.yaml alone"
           if in_head else "")
        + ", and run the same command again.")
    git("rm", "-q", "--cached", "--", "members", cwd=holder)
    os.rename(holder / "members", holder.parent / "moved-1")
    if in_head:
        git("commit", "-qm", "The removal, on its own", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (BOTH, remedy_of(renamed_back(True)))
    assert typed_as_printed(holder, said[1]) == [*two_steps(), "git commit"]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])
