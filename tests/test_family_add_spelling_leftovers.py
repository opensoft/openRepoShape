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
   member out nowhere. Only the section named after the row's path is
   pointed back, and only where no section gives that path: one beside the
   member's own section, as `git rm --cached` of a submodule a hand added at
   `Members/IRRS` leaves it, is taken out with the gate's own `--unset-all`
   lines (rv865's MUST 1: pointed back, it sent a recursive clone to ITS
   url, exit 128). A gitlink at such a path beside the member's own, a
   second path to its directory, is taken out of the index alone, as the
   gate's own line does, and never renamed: `git mv` carried its section
   along, and the take-out then left a gitlink no section names, at which a
   plain clone's `git submodule update --init --recursive` stopped, exit
   128 (rv865b's MUST 1). Its removal takes `-f` where the move back's
   would, and its checkout is named to delete by hand in the same round,
   before any update, with the `git -C` status that shows its work
   (rv865b's round-2 MUST 1 and SHOULD 1).
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
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import (
    cloned_just_pushed, git, rmtree, submodule_update_through_git,
)
from test_family import NAME, ORG, SPARE, family, validate  # noqa: F401
import test_family_add_member_variant as member_variant
from test_family_add_member_variant import (
    MOVE_OUT, OTHER_ROW, OTHER_VARIANT, REMOVE, ROW, SUBMODULE, VARIANT,
    VARIANT_SHOWN, dry_run_in_process, guarded, in_the_index, moved_back,
    point_back, record, registered, remedy, typed_as_printed, variant,
)
from test_family_add_move_back_sections import (
    POINTED, REMOVE_BOTH, REMOVE_FORCED, SECTIONS, bit_cleared,
    deleted_by_hand, file_committed, gate_then_add, mount_moved, set_aside,
    sparse_cone, work_there,
)
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant,
)
from test_family_add_spellings_remedies import (
    BOTH, BOTH_AND_A_FILE, STAGE_FIRST, folding_skip, no_symlink_on_windows,
    renamed_back, renamed_with_git, two_steps,
)
from test_family_members_case_variants import (
    DIR_VARIANT, NEEDS_GIT_2_34, commit_first, disk_as, disk_folds,
    index_part, refused_untouched, remedy_of,
)
from test_family_members_case_variants import move as untracked_moved
from test_family_refuse_up_front import needs_check_rules

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


#: Where a section beside the member's own section is found.
BESIDE_SECTION = "in .gitmodules, beside the section giving its row's path"


def unset(name: str) -> list[str]:
    """The gate's `--unset-all` line for each key of the section `name`,
    its `path` and its `url`, in that order, the key quoted for a POSIX
    shell as printed."""
    return ["git config -f .gitmodules --unset-all "
            + shlex.quote(f"submodule.{name}.{key}")
            for key in ("path", "url")]


def taken_out(*names: str, commit: bool = True) -> str:
    """The part that takes out each section `names`, every key it holds,
    beside the member's own (rv865's MUST 1)."""
    lines = " and ".join(f"`{line}`" for name in names
                         for line in unset(name))
    return ("take out each section of .gitmodules that gives another "
            "spelling of a row's path beside the section that gives that path "
            "itself, every key it holds, as the gate's own lines do, so a "
            "submodule later given its name inherits none of them: add would "
            "commit that .gitmodules beside the new member, a disk that folds "
            "case takes the two paths for one, and git rm --cached of a "
            f"gitlink at that path leaves it ({lines}, then `git add -- "
            ".gitmodules`)" + (", and commit that" if commit else ""))


#: What `-f` on a `git rm --cached` of a gitlink does, as the move back says
#: it (#761).
FORCED = ("whose -f takes out a staged gitlink whose checkout has moved on "
          "or holds a file git does not track, which git rm otherwise "
          "refuses, and with --cached touches no file")


def second_out(*names: str, commit: str = "", sparse: bool = False,
               forced: bool = False) -> str:
    """The index's part that takes each second gitlink `names`, beside the
    member's own, out of the index alone, as the gate's own line does
    (rv865b's MUST 1), with `--sparse` where a sparse checkout needs it,
    `-f` where the index stages it at a commit HEAD does not record there
    beside its checkout (rv865b's round-2 MUST 1), and `, and commit
    <commit>` where given."""
    flag = (" --sparse" if sparse else "") + (" -f" if forced else "")
    return ("take each gitlink at another spelling of a row's path beside "
            "the member's own gitlink at that path, a second path to its "
            "directory, out of the index alone, which touches no file, as "
            "the gate's own line does, since git mv would carry the section "
            "of .gitmodules that gives its path along under the same name, "
            "and with that section taken out, a gitlink no section names "
            "would stop a plain clone's git submodule update --init "
            f"--recursive (`git rm -r --cached{flag} -- {' '.join(names)}`"
            + (f", {NEEDS_GIT_2_34}" if sparse else "")
            + (f", {FORCED}" if forced else "") + ")"
            + (f", and commit {commit}" if commit else ""))


def second_checkout(*names: str) -> str:
    """The part that names each checkout `git rm --cached` of a second path
    leaves at `names`, to be deleted by hand in the same round, before any
    update (rv865b's round-2 SHOULD 1)."""
    named = " and ".join(f"`{name}`" for name in names)
    status = " or ".join(f"`git -C {name} status`" for name in names)
    return ("delete by hand each checkout that git rm --cached of a second "
            f"path leaves on disk, {named}, once nothing only it holds is "
            "needed, rather than move it, and before any update below: its "
            ".git file names its store by a path relative to it, which a move "
            "would leave pointing nowhere, its commits are kept in that "
            "store, so only what is not committed is in it alone "
            f"({status} shows it), and the update points a store it may share "
            "with the row at the row's path, after which that status shows "
            "the row's checkout instead")


def deleted(name: str):
    """What the text says of the checkout at `name`, done by hand: it is a
    checkout, its `.git` a file, and it is deleted."""
    def by_hand(root: Path) -> None:
        assert (root / name / ".git").is_file(), name
        rmtree(root / name)
    return by_hand


def cloned_with_the_member(root: Path, remotes: Path, tmp_path: Path,
                           branch: str, commit: str) -> None:
    """HEAD pushed to `branch` of the family's own remote, under a name no
    other test uses, and a fresh recursive clone of it, which must exit 0,
    with `members/IRRS` checked out from IRRS's own remote at `commit`."""
    remote = remotes / f"{NAME}.git"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=root)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch)
    url = git("-C", ROW, "config", "remote.origin.url", cwd=clone)
    assert Path(url.stdout.strip()).name == "IRRS.git", url.stdout
    assert git("-C", ROW, "rev-parse", "HEAD",
               cwd=clone).stdout.strip() == commit


def gitlinks(root: Path) -> list[str]:
    """Every gitlink the index of `root` holds, by path."""
    return [line.partition("\t")[2] for line in git(
        "ls-files", "-s", cwd=root).stdout.splitlines()
        if line.startswith("160000 ")]


def every_clone_checks_every_member_out(root: Path, remotes: Path,
                                        tmp_path: Path, branch: str,
                                        commit: str) -> None:
    """`cloned_with_the_member`, and a plain clone of the same branch, as
    the holder's own CI makes it (`validate.yml`: `submodules: false`, then
    `git submodule update --init --recursive`), whose update must exit 0
    with every member HEAD records checked out; `git submodule status`
    exits 0 in the holder and in both clones (rv865b's MUST 1: a gitlink no
    section names stopped the update and the status, exit 128, while the
    gate passed)."""
    cloned_with_the_member(root, remotes, tmp_path, branch, commit)
    plain = cloned_just_pushed(remotes / f"{NAME}.git",
                               tmp_path / "plain" / NAME, branch,
                               recurse=False)
    submodule_update_through_git(plain, remotes, "-q", "--init",
                                 "--recursive")
    members = gitlinks(plain)
    assert members == gitlinks(root)
    assert {ROW, OTHER_ROW} <= set(members), members
    assert [path for path in members if not path.startswith("members/")
            or not (plain / path / ".git").exists()] == [], members
    for where in (root, tmp_path / "clone" / NAME, plain):
        git("submodule", "status", cwd=where)


def typed_through(family, holder, offline, tmp_path, made: tuple,
                  branch: str) -> None:
    """`made`, `(IRRS's commit, the refusal's first line, the remedy's
    parts, what is typed, what is done by hand or None)`, refused and typed
    as printed in one round, what the text says to do by hand done where it
    says; then the member is where its row says, every clone checks every
    member out, the gate passes in every mode and the same `add` goes
    through."""
    commit, lead, parts, typed, by_hand = made
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (lead, remedy_of(*parts))
    assert typed_as_printed(holder, said[1], by_hand) == typed
    registered(holder, family["root"], commit)
    every_clone_checks_every_member_out(holder, family["remotes"], tmp_path,
                                        branch, commit)
    gate_then_add(offline, holder, family["remotes"])


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


def staged_beside_a_pending_change(root: Path) -> tuple:
    """`Members/README` committed, then `git rm --cached` and deleted: a
    pending change the remedy commits first, which takes the staged section
    into HEAD."""
    file_committed(root, "Members/README")
    git("rm", "-q", "--cached", "--", "Members/README", cwd=root)
    (root / "Members" / "README").unlink()
    return ("in HEAD and no longer in the index: `Members/README` (a file); ",
            [commit_first("Members/README")], ["git commit"])


def staged_beside_a_rename(root: Path) -> tuple:
    """`Members/README` committed and on disk: the rename's commit takes
    the staged section into HEAD."""
    file_committed(root, "Members/README")
    return ("in the index: `Members/README` (a file); ",
            [index_part(rename=["Members/README"], commit="the rename")],
            ["git mv -- Members/README renamed-1", "git commit"])


def staged_beside_a_removal(root: Path) -> tuple:
    """`Members/README` in the index and HEAD, nothing on disk: the
    removal's commit takes the staged section into HEAD (rv865b's X2)."""
    plant(root, "100644", "Members/README")
    git("commit", "-qm", "A file at Members/README", cwd=root)
    return ("in the index: `Members/README` (a file); ",
            [index_part(unstage=["Members/README"], commit="the removal")],
            ["git rm -r --cached -- Members/README", "git commit"])


#: `{state: how the commit before the point-back is made, returning (the
#: places it adds, the parts before the point-back, what is typed)}`.
COMMITTED_BEFORE = {"a pending change": staged_beside_a_pending_change,
                    "a rename": staged_beside_a_rename,
                    "a removal": staged_beside_a_removal}


@pytest.mark.parametrize("state", list(COMMITTED_BEFORE))
def test_a_staged_section_astray_is_committed_after_an_earlier_commit(
        family, holder, offline, state):
    """Line 1, the section's edit staged, beside a remedy that commits
    first: a pending change (rv865's R26) or the index's rename. That
    commit takes the staged section into HEAD, so the point-back is a
    change to commit after it. Printed without its commit, the point-back
    was left staged, HEAD's section gave `Members/IRRS`, and the gate found
    `member-gitmodules-absent`. Typed as printed, HEAD's `.gitmodules` is
    the holder's again, the gate passes and the same `add` goes through."""
    if disk_folds(holder):
        pytest.skip("`Members/README` beside `members/` needs a disk that "
                    "does not fold case")
    places, parts, typed = COMMITTED_BEFORE[state](holder)
    commit = section_astray(holder, VARIANT, "staged")
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + places
                    + f"{IN_SECTION}: `{VARIANT}` (a section)",
                    remedy_of(*parts, pointed_back(True), update(ROW)))
    assert typed_as_printed(holder, said[1]) == [
        *typed, point_back(), "git add -- .gitmodules", "git commit"]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_an_unreadable_gitmodules_is_refused_after_the_spelling(
        family, holder, offline):
    """`.gitmodules` that git cannot read (`bad config line`), committed,
    beside a committed `Members/README` (rv865's R13). The sections astray
    are not asked of a file git cannot read: the spelling refusal comes
    first, and `gitmodules-unreadable` after it, as `_sections_restored`
    already orders them. Measured: `git mv` of the file types clean there,
    and `git status` does not (exit 128), so the snapshot asks none."""
    if disk_folds(holder):
        pytest.skip("`Members/README` beside `members/` needs a disk that "
                    "does not fold case")
    data = (holder / ".gitmodules").read_bytes()
    (holder / ".gitmodules").write_bytes(data + b"[submodule\n")
    git("add", "--", ".gitmodules", cwd=holder)
    git("commit", "-qm", "A .gitmodules git cannot read", cwd=holder)
    file_committed(holder, "Members/README")
    said = refused_untouched(offline, holder, family["remotes"],
                             status=False)
    assert said == (DIR_VARIANT + "in the index: `Members/README` (a file)",
                    remedy_of(index_part(rename=["Members/README"],
                                         commit="the rename")))
    assert typed_as_printed(holder, said[1]) == [
        "git mv -- Members/README renamed-1", "git commit"]
    again = offline.add(holder, SPARE, remotes=family["remotes"])
    assert again.returncode == 2, again.stdout + again.stderr
    assert again.stderr.startswith("REFUSED gitmodules-unreadable: "), (
        again.stderr)


def added_by_hand(root: Path, remotes: Path, path: str,
                  commit: bool = True) -> str:
    """`git submodule add` of IRSS's remote at `path`, committed where
    `commit`, its checkout kept: a section named `path`, giving `path`, with
    IRSS's url, beside the member IRRS's own. Returns the commit IRRS's
    gitlink records."""
    if disk_folds(root):
        pytest.skip(f"`{path}` beside `members/IRRS` needs a disk that does "
                    "not fold case")
    git("-c", "protocol.file.allow=always", "submodule", "add", "-q", "--",
        str(remotes / "IRSS.git"), path, cwd=root)
    if commit:
        git("commit", "-qm", f"IRSS added by hand at {path}", cwd=root)
    return git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()


def at_the_variant(root: Path, remotes: Path) -> tuple:
    """(a) `git submodule add <IRSS> Members/IRRS`, committed, its checkout
    kept: a second path to the member's directory, taken out of the index
    alone, as the gate's own line does, which leaves its section to be
    taken out, and its checkout to delete by hand in the same round. #574's
    `git mv` renamed it and moved its section with it, and the take-out
    after it left `renamed-1` a gitlink no section names (rv865b's MUST
    1)."""
    commit = added_by_hand(root, remotes, VARIANT)
    return (commit, DIR_VARIANT + f"in the index: `{VARIANT}` (a submodule); "
            f"{BESIDE_SECTION}: `{VARIANT}` (a section)",
            [second_out(VARIANT, commit="the removal"), taken_out(VARIANT),
             second_checkout(VARIANT)],
            [f"git rm -r --cached -- {VARIANT}", "git commit",
             *unset(VARIANT), "git add -- .gitmodules", "git commit"],
            deleted(VARIANT))


def under_members_itself(root: Path, remotes: Path) -> tuple:
    """(b) the same at `members/irrs`, as `git submodule add` makes it:
    line 3's second gitlink, with its section."""
    commit = added_by_hand(root, remotes, ROW_SPELLED)
    return (commit, ROW_VARIANT + f"in the index: `{ROW_SPELLED}` (a "
            f"submodule); {BESIDE_SECTION}: `{ROW_SPELLED}` (a section)",
            [second_out(ROW_SPELLED, commit="the removal"),
             taken_out(ROW_SPELLED), second_checkout(ROW_SPELLED)],
            [f"git rm -r --cached -- {ROW_SPELLED}", "git commit",
             *unset(ROW_SPELLED), "git add -- .gitmodules", "git commit"],
            deleted(ROW_SPELLED))


def checkout_deleted(root: Path, remotes: Path) -> tuple:
    """(c) (a) with its checkout deleted: its gitlink is taken out of the
    index, which leaves its section."""
    commit = added_by_hand(root, remotes, VARIANT)
    rmtree(root / "Members")
    return (commit, DIR_VARIANT + f"in the index: `{VARIANT}` (a submodule); "
            f"{BESIDE_SECTION}: `{VARIANT}` (a section)",
            [index_part(unstage=[VARIANT], commit="the removal"),
             taken_out(VARIANT)],
            [f"git rm -r --cached -- {VARIANT}", "git commit",
             *unset(VARIANT), "git add -- .gitmodules", "git commit"], None)


def section_left_alone(root: Path, remotes: Path) -> tuple:
    """(d) what `git rm --cached` of (a) leaves: a section `Members/IRRS`
    with IRSS's url, alone, committed."""
    for key, value in (("path", VARIANT), ("url", str(remotes / "IRSS.git"))):
        git("config", "-f", ".gitmodules", f"submodule.{VARIANT}.{key}",
            value, cwd=root)
    git("add", "--", ".gitmodules", cwd=root)
    git("commit", "-qm", "A section left at Members/IRRS", cwd=root)
    return (git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip(),
            DIR_VARIANT + f"{BESIDE_SECTION}: `{VARIANT}` (a section)",
            [taken_out(VARIANT)],
            [*unset(VARIANT), "git add -- .gitmodules", "git commit"], None)


def stale_section(root: Path, remotes: Path, name: str, path: str,
                  commit: bool) -> None:
    """A section `name` giving `path` with IRSS's url, staged, and
    committed where `commit`."""
    for key, value in (("path", path), ("url", str(remotes / "IRSS.git"))):
        git("config", "-f", ".gitmodules", f"submodule.{name}.{key}", value,
            cwd=root)
    git("add", "--", ".gitmodules", cwd=root)
    if commit:
        git("commit", "-qm", f"A section {name} at {path}", cwd=root)


#: The refusal's first sentence where a path is under another spelling of
#: `members/` and another is a case variant of a row's path under
#: `members/` itself.
BOTH_LEADS = (DIR_VARIANT[:-3] + ", and a case variant of the path of a "
              "`members:` row under members/, the same path as that row's on "
              "a case-insensitive disk — ")


def pointed_and_taken_out(root: Path, remotes: Path,
                          committed: bool = True) -> tuple:
    """Line 1's own section, named `members/IRRS`, giving `Members/IRRS`,
    committed, and a second one, `stale`, giving `members/irrs` with IRSS's
    url, committed where `committed`: no section gives the row's path, so
    the member's own is pointed back, and the other is then beside it and
    taken out, with a commit either way, the point-back's own commit having
    taken a staged `stale` into HEAD (rv865b's NIT 3: printed without one,
    HEAD kept `stale`, and the gate passed)."""
    commit = section_astray(root, VARIANT, "committed")
    stale_section(root, remotes, "stale", ROW_SPELLED, committed)
    return (commit, BOTH_LEADS + f"{IN_SECTION}: `{VARIANT}` (a section); "
            f"{BESIDE_SECTION}: `{ROW_SPELLED}` (a section)",
            [pointed_back(True), taken_out("stale"), update(ROW)],
            [point_back(), "git add -- .gitmodules", "git commit",
             *unset("stale"), "git add -- .gitmodules", "git commit"], None)


def staged_taken_out(root: Path, remotes: Path) -> tuple:
    """A section `stale` staged and never committed: its take-out after the
    point-back's commit is committed too (rv865b's NIT 3)."""
    return pointed_and_taken_out(root, remotes, committed=False)


#: A section name that a POSIX shell takes for three words unless quoted.
SPACED = "a stale one"


def spaced_and_staged(root: Path, remotes: Path) -> tuple:
    """A section named `a stale one`, giving `members/irrs`, staged and
    never committed, beside the member's own section: taken out with each
    key quoted as printed (rv865b's X6), and nothing to commit, HEAD never
    having held it (rv865b's X1)."""
    stale_section(root, remotes, SPACED, ROW_SPELLED, False)
    return (git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip(),
            ROW_VARIANT + f"{BESIDE_SECTION}: `{ROW_SPELLED}` (a section)",
            [taken_out(SPACED, commit=False)],
            [*unset(SPACED), "git add -- .gitmodules"], None)


#: `{state: how it is made, returning (IRRS's commit, the refusal's first
#: line, the remedy's parts, what is typed, what is done by hand or None)}`,
#: rv865's four states and the two remedies together.
BESIDE = {"a submodule added at Members/IRRS": at_the_variant,
          "the same at members/irrs": under_members_itself,
          "its checkout deleted": checkout_deleted,
          "its section left alone": section_left_alone,
          "pointed back, and another taken out": pointed_and_taken_out,
          "pointed back, and a staged one taken out": staged_taken_out,
          "a staged one whose name needs quoting": spaced_and_staged}


@pytest.mark.parametrize("state", list(BESIDE))
def test_a_section_beside_the_members_own_is_taken_out(
        family, holder, offline, tmp_path, state):
    """rv865's MUST 1: a section giving another spelling of `members/IRRS`
    beside the member's own section, which gives `members/IRRS` itself, was
    pointed back at `members/IRRS`, with its own url, IRSS's. Typed as
    printed, `.gitmodules` gave `members/IRRS` twice, the gate refused
    `gitmodules-path-twice` in every mode, `add` went through, and a
    recursive clone fetched the member from IRSS's remote and failed (`did
    not contain <commit>`, exit 128, measured at #865's `4268f804` on git
    2.43 and 2.47.1). Now such a section is taken out, every key it holds,
    with the gate's own `--unset-all` lines, after the index's own remedy
    for a gitlink at its path; only the member's own, named after its row's
    path, is pointed back, where no section gives that path. A gitlink at
    its path is taken out of the index first, and its checkout named to
    delete by hand (rv865b's MUST 1, and its round-2 SHOULD 1). Typed as
    printed, in one round, a recursive clone of the
    pushed branch checks the member out from IRRS's remote, a plain clone's
    update checks every member out, `git submodule status` exits 0, the gate
    passes in every mode and the same `add` goes through."""
    typed_through(family, holder, offline, tmp_path,
                  BESIDE[state](holder, family["remotes"]),
                  f"w865f/beside-{list(BESIDE).index(state)}")


def test_the_section_named_after_the_row_beside_its_path_is_taken_out(
        family, holder, offline, tmp_path):
    """Line 1's own section, named `members/IRRS`, giving `Members/IRRS`,
    beside a section `other` that gives `members/IRRS` itself, with the
    member's url, committed. A section gives the row's path, so the gate
    calls the other one a second one (`STRAY`) and prints its `--unset-all`
    lines, whatever its name: it is taken out, not pointed back, which
    would give the path twice. Typed as printed, a recursive clone of the
    pushed branch checks the member out from IRRS's remote, the gate passes
    in every mode and the same `add` goes through."""
    commit = section_astray(holder, VARIANT, "committed")
    url = git("config", "-f", ".gitmodules", f"submodule.{ROW}.url",
              cwd=holder).stdout.strip()
    for key, value in (("path", ROW), ("url", url)):
        git("config", "-f", ".gitmodules", f"submodule.other.{key}", value,
            cwd=holder)
    git("add", "--", ".gitmodules", cwd=holder)
    git("commit", "-qm", "Another section giving members/IRRS", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + f"{BESIDE_SECTION}: `{VARIANT}` (a "
                    "section)", remedy_of(taken_out(ROW)))
    assert typed_as_printed(holder, said[1]) == [
        *unset(ROW), "git add -- .gitmodules", "git commit"]
    cloned_with_the_member(holder, family["remotes"], tmp_path,
                           "w865f/named-after-the-row", commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_variant_section_no_rule_names_is_left_to_the_gate(
        family, holder, family_module):
    """No section gives `members/IRRS` and none is named after it: the
    member's own section is gone, and a section `stale` gives `Members/IRRS`
    with the member's url. It may be the member's only registration, so
    `add` neither points it back nor takes it out, and leaves it to the
    gate, which names it and prints no command for it (`WRONG_CASE`), as
    taking it out could un-register the member. At `4268f804` it was
    pointed back, whatever submodule it belonged to."""
    url = git("config", "-f", ".gitmodules", f"submodule.{ROW}.url",
              cwd=holder).stdout.strip()
    git("config", "-f", ".gitmodules", "--remove-section",
        f"submodule.{ROW}", cwd=holder)
    for key, value in (("path", VARIANT), ("url", url)):
        git("config", "-f", ".gitmodules", f"submodule.stale.{key}", value,
            cwd=holder)
    git("add", "--", ".gitmodules", cwd=holder)
    git("commit", "-qm", "The member's section renamed stale, astray",
        cwd=holder)
    rows = family_module._rows_paths(family_module.Family.open(holder).members)
    assert family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder), rows) == []
    gate = validate(holder, "--no-members")
    assert gate.returncode == 1, gate.stdout + gate.stderr
    assert "taking this section out could un-register it" in (
        gate.stdout + gate.stderr)


def recorded_again(root: Path) -> str:
    """`git mv members/IRRS Members/IRRS`, committed, which moves the
    checkout, the gitlink and the section's path, then the member's gitlink
    recorded at its row's path again by hand, at the same commit, and
    committed. Returns that commit."""
    if disk_folds(root):
        pytest.skip("`Members/IRRS` beside `members/IRRS` needs a disk that "
                    "does not fold case")
    commit = mount_moved(root, True)
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{ROW}",
        cwd=root)
    git("commit", "-qm", f"{ROW} recorded again by hand", cwd=root)
    return commit


#: The refusal's first line where a second gitlink and the member's own
#: section astray are both at `Members/IRRS`.
SECOND_AND_ASTRAY = (DIR_VARIANT + f"in the index: `{VARIANT}` (a "
                     f"submodule); {IN_SECTION}: `{VARIANT}` (a section)")


def second_committed(root: Path, remotes: Path) -> tuple:
    """K2 committed: `recorded_again`. The second gitlink is taken out of
    the index, which leaves the section, and the section is pointed back in
    the same round; both are committed, the checkout `git mv` left at
    `Members/IRRS` is deleted by hand, and the update checks the member out
    at its row's path. At `f7072d08` its `git mv` took the section to
    `renamed-1`, and the gate refused `member-gitmodules-absent`; with the
    gitlink clause dropped alone, the update printed after the point-back
    stopped, `No url found for submodule path 'renamed-1'` (rv865b)."""
    commit = recorded_again(root)
    return (commit, SECOND_AND_ASTRAY,
            [second_out(VARIANT, commit="the removal"), pointed_back(True),
             second_checkout(VARIANT), update(ROW)],
            [f"git rm -r --cached -- {VARIANT}", "git commit", point_back(),
             "git add -- .gitmodules", "git commit", SUBMODULE],
            deleted(VARIANT))


def second_reset(root: Path, remotes: Path) -> tuple:
    """K2 reset: `git mv members/IRRS Members/IRRS`, staged, then `git
    reset -- members/IRRS`, which puts the member's gitlink back at its
    row's path in the index: nothing HEAD holds changes, so nothing is
    committed, and the removal takes `-f`, HEAD recording nothing at
    `Members/IRRS` beside its checkout."""
    if disk_folds(root):
        pytest.skip("`Members/IRRS` beside `members/IRRS` needs a disk that "
                    "does not fold case")
    commit = mount_moved(root, False)
    git("reset", "-q", "--", ROW, cwd=root)
    return (commit, SECOND_AND_ASTRAY,
            [second_out(VARIANT, forced=True), pointed_back(False),
             second_checkout(VARIANT), update(ROW)],
            [f"git rm -r --cached -f -- {VARIANT}", point_back(),
             "git add -- .gitmodules", SUBMODULE], deleted(VARIANT))


def second_checkout_deleted(root: Path, remotes: Path) -> tuple:
    """K2 with its checkout deleted: nothing is on disk at `Members/IRRS`,
    so its gitlink is taken out of the index as before, and nothing is left
    to delete (one round; two at `f7072d08`)."""
    commit = recorded_again(root)
    rmtree(root / "Members")
    return (commit, SECOND_AND_ASTRAY,
            [index_part(unstage=[VARIANT], commit="the removal"),
             pointed_back(True), update(ROW)],
            [f"git rm -r --cached -- {VARIANT}", "git commit", point_back(),
             "git add -- .gitmodules", "git commit", SUBMODULE], None)


def second_foreign(root: Path, remotes: Path) -> tuple:
    """K2 foreign: the member's own section astray at `Members/IRRS`,
    committed, then `git submodule add <IRSS> Members/IRRS`, committed: the
    gitlink is taken out of the index, the member's section pointed back,
    IRSS's section, then beside it, taken out, and its checkout deleted by
    hand. At `f7072d08` the gate refused `gitmodules-path-unnamed` for
    `renamed-1` after `add`; with the clause dropped alone, `renamed-1` was
    left with no section."""
    commit = section_astray(root, VARIANT, "committed")
    added_by_hand(root, remotes, VARIANT)
    return (commit, SECOND_AND_ASTRAY + f"; {BESIDE_SECTION}: `{VARIANT}` (a "
            "section)",
            [second_out(VARIANT, commit="the removal"), pointed_back(True),
             taken_out(VARIANT), second_checkout(VARIANT), update(ROW)],
            [f"git rm -r --cached -- {VARIANT}", "git commit", point_back(),
             "git add -- .gitmodules", "git commit", *unset(VARIANT),
             "git add -- .gitmodules", "git commit"], deleted(VARIANT))


#: `{state: how it is made, returning (IRRS's commit, the refusal's first
#: line, the remedy's parts, what is typed, what is done by hand or None)}`:
#: rv865b's four K2 states.
SECOND = {"committed": second_committed, "reset": second_reset,
          "checkout deleted": second_checkout_deleted,
          "foreign": second_foreign}


@pytest.mark.parametrize("state", list(SECOND))
def test_a_second_gitlink_beside_the_members_own_is_taken_out_of_the_index(
        family, holder, offline, tmp_path, state):
    """rv865b's ruling on K2, with its MUST 1: a gitlink at `Members/IRRS`
    beside the member's own at `members/IRRS`, the member's own section
    giving `Members/IRRS`. The section was never pointed back while a
    gitlink was at its path, and that gitlink was renamed with `git mv`,
    which took the section along. Now the gitlink is taken out of the index
    alone, `git rm -r --cached`, the gate's own line for a second path,
    which leaves the section where the point-back finds it in the same
    round. Typed as printed, in one round, the checkout left on disk
    deleted by hand before the update, the member is where its row says, a
    recursive and a plain clone check every member out, `git submodule
    status` exits 0, the gate passes in every mode and the same `add` goes
    through."""
    typed_through(family, holder, offline, tmp_path,
                  SECOND[state](holder, family["remotes"]),
                  f"w865f/second-{list(SECOND).index(state)}")


def left_out_by_the_rules(root: Path):
    """A cone-mode sparse checkout that leaves `Members/` out, the gitlink's
    bit cleared and its checkout on disk. Returns what is done by hand: the
    checkout deleted."""
    sparse_cone(root)
    bit_cleared(root, VARIANT, True, True)
    return deleted(VARIANT)


def marked_by_hand(root: Path):
    """No sparse checkout, the gitlink's `skip-worktree` bit set by hand and
    its checkout deleted: nothing is left to do by hand."""
    rmtree(root / "Members")
    git("update-index", "--skip-worktree", "--", VARIANT, cwd=root)
    return None


#: `{how: how the sparse state is made, returning what is done by hand}`.
SPARSE_SECOND = {"left out by the rules": left_out_by_the_rules,
                 "marked by hand": marked_by_hand}


@needs_check_rules
@pytest.mark.parametrize("how", list(SPARSE_SECOND))
def test_a_second_gitlink_a_sparse_checkout_holds_takes_sparse(
        family, holder, offline, tmp_path, how):
    """(a), where the sparse rules leave the gitlink out, or its bit is set:
    plain `git rm --cached` refuses it either way (`outside of your
    sparse-checkout definition`, exit 1, measured on git 2.43 and 2.47.1
    for a bit set with no sparse checkout), so its removal takes
    `--sparse`, and says the git it needs. Typed as printed, as (a)."""
    commit = added_by_hand(holder, family["remotes"], VARIANT)
    by_hand = SPARSE_SECOND[how](holder)
    typed_through(family, holder, offline, tmp_path, (
        commit, DIR_VARIANT + f"in the index: `{VARIANT}` (a submodule); "
        f"{BESIDE_SECTION}: `{VARIANT}` (a section)",
        [second_out(VARIANT, commit="the removal", sparse=True),
         taken_out(VARIANT), *([second_checkout(VARIANT)] if by_hand else [])],
        [f"git rm -r --cached --sparse -- {VARIANT}", "git commit",
         *unset(VARIANT), "git add -- .gitmodules", "git commit"], by_hand),
        f"w865f/second-sparse-{list(SPARSE_SECOND).index(how)}")


#: The refusal's first line for a gitlink and its section at `Members/IRRS`.
AT_THE_VARIANT = (DIR_VARIANT + f"in the index: `{VARIANT}` (a submodule); "
                  f"{BESIDE_SECTION}: `{VARIANT}` (a section)")


def kept_in_its_store(root: Path, commit: str, name: str) -> None:
    """`commit` is in the store `.git/modules/<name>`, the checkout it was
    made in deleted. The work tree is given, since the store's own
    `core.worktree` may name that deleted checkout."""
    store = root / ".git" / "modules" / name
    kept = subprocess.run(["git", f"--git-dir={store}", f"--work-tree={root}",
                           "cat-file", "-e", commit], capture_output=True,
                          check=False)
    assert kept.returncode == 0, kept.stderr


def committed_there(root: Path, name: str) -> str:
    """A commit of its own made in the checkout at `name`, and nothing
    else. Returns the commit."""
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "Work there", cwd=root / name)
    return git("rev-parse", "HEAD", cwd=root / name).stdout.strip()


def staged_untracked(root: Path, remotes: Path) -> tuple:
    """(a) staged: `git submodule add <IRSS> Members/IRRS`, not committed,
    and an untracked file in its checkout. Plain `git rm --cached` refused
    it (`staged content different from both the file and the HEAD`, exit 1,
    rv865b's round-2 MUST 1), so the removal takes `-f`; nothing HEAD holds
    changes, so nothing is committed."""
    commit = added_by_hand(root, remotes, VARIANT, commit=False)
    (root / VARIANT / "WIP.txt").write_bytes(b"not committed\n")
    return ((commit, AT_THE_VARIANT,
             [second_out(VARIANT, forced=True),
              taken_out(VARIANT, commit=False), second_checkout(VARIANT)],
             [f"git rm -r --cached -f -- {VARIANT}", *unset(VARIANT),
              "git add -- .gitmodules"], deleted_by_hand(VARIANT)), None)


def staged_committed_there(root: Path, remotes: Path) -> tuple:
    """(a) staged, with a commit of its own made in its checkout, which has
    moved on from the commit the index stages: `-f` too, and that commit is
    kept in the checkout's store, `.git/modules/Members/IRRS`."""
    commit = added_by_hand(root, remotes, VARIANT, commit=False)
    work = committed_there(root, VARIANT)
    return ((commit, AT_THE_VARIANT,
             [second_out(VARIANT, forced=True),
              taken_out(VARIANT, commit=False), second_checkout(VARIANT)],
             [f"git rm -r --cached -f -- {VARIANT}", *unset(VARIANT),
              "git add -- .gitmodules"], deleted(VARIANT)), (work, VARIANT))


def staged_and_left_out(root: Path, remotes: Path) -> tuple:
    """(a) staged, an untracked file in its checkout, and a cone-mode sparse
    checkout that leaves `Members/` out, the gitlink's bit cleared: the
    removal takes `--sparse` and `-f` together, as the move back's does."""
    commit = added_by_hand(root, remotes, VARIANT, commit=False)
    sparse_cone(root)
    bit_cleared(root, VARIANT, True, True)
    (root / VARIANT / "WIP.txt").write_bytes(b"not committed\n")
    return ((commit, AT_THE_VARIANT,
             [second_out(VARIANT, sparse=True, forced=True),
              taken_out(VARIANT, commit=False), second_checkout(VARIANT)],
             [f"git rm -r --cached --sparse -f -- {VARIANT}",
              *unset(VARIANT), "git add -- .gitmodules"],
             deleted_by_hand(VARIANT)), None)


def reset_with_work(root: Path, remotes: Path) -> tuple:
    """K2 reset with work in the checkout at `Members/IRRS`, a commit of
    its own and an untracked file: refused without `-f` (rv865b's round-2
    MUST 1), and its untracked file shown by `git -C Members/IRRS status`
    when the text says to delete it, before the update points the store it
    shares with the member at `members/IRRS`."""
    made = second_reset(root, remotes)
    work = work_there(root, VARIANT)
    return ((*made[:4], deleted_by_hand(VARIANT)), (work, ROW))


def committed_with_work(root: Path, remotes: Path) -> tuple:
    """K2 committed with work in the checkout at `Members/IRRS` (rv865b's
    round-2 SHOULD 1): the update printed in the same round pointed the
    member's store, which that checkout shares, at `members/IRRS`, so `git
    -C Members/IRRS status` printed nothing while `WIP.txt` was there, and
    the next run said to delete it. Now it is named before the update, and
    its status names the file when the text says to delete it."""
    made = second_committed(root, remotes)
    work = work_there(root, VARIANT)
    return ((*made[:4], deleted_by_hand(VARIANT)), (work, ROW))


#: `{state: how it is made, returning (what `typed_through` takes, the
#: commit made in the checkout and the row or path whose store keeps it, or
#: None)}`: work in the checkout of a second path.
WORK = {"(a) staged, an untracked file": staged_untracked,
        "(a) staged, a commit of its own": staged_committed_there,
        "(a) staged and left out by the rules": staged_and_left_out,
        "K2 reset, work in the checkout": reset_with_work,
        "K2 committed, work in the checkout": committed_with_work}


@pytest.mark.parametrize("state", [
    pytest.param(state, marks=needs_check_rules) if "left out" in state
    else state for state in WORK])
def test_a_second_paths_checkout_with_work_is_forced_and_named_first(
        family, holder, offline, tmp_path, state):
    """rv865b's round-2 MUST 1 and SHOULD 1: work in the checkout of a
    second path. Where the index stages the gitlink at a commit HEAD does
    not record there, its removal takes `-f`, said as the move back says
    it, and `--sparse` with it where the rules leave it out; and its
    checkout is named to delete by hand in the same round, before any
    update, with the `git -C` status that shows its untracked file (the
    hand step asserts it does), its commits kept in its store. Typed as
    printed, in one round, the member is where its row says, a recursive
    and a plain clone check every member out, `git submodule status` exits
    0, the gate passes in every mode and the same `add` goes through."""
    made, kept = WORK[state](holder, family["remotes"])
    typed_through(family, holder, offline, tmp_path, made,
                  f"w865f/work-{list(WORK).index(state)}")
    if kept is not None:
        kept_in_its_store(holder, *kept)


@needs_check_rules
def test_a_staged_second_gitlink_with_nothing_on_disk_takes_no_f(
        family, holder, offline, tmp_path):
    """(a) staged, its checkout deleted and its bit set by hand: `-f` is
    asked only where a checkout is on disk (`_forced`, as the move back
    asks it), so the removal is `--sparse` alone; nothing HEAD holds
    changes, so nothing is committed, and nothing is left to delete."""
    commit = added_by_hand(holder, family["remotes"], VARIANT, commit=False)
    rmtree(holder / "Members")
    git("update-index", "--skip-worktree", "--", VARIANT, cwd=holder)
    typed_through(family, holder, offline, tmp_path, (
        commit, AT_THE_VARIANT,
        [second_out(VARIANT, sparse=True), taken_out(VARIANT, commit=False)],
        [f"git rm -r --cached --sparse -- {VARIANT}", *unset(VARIANT),
         "git add -- .gitmodules"], None), "w865f/second-staged-off-disk")


def test_a_clone_of_its_own_at_a_second_path_is_moved_whole_next(
        family, holder, offline, tmp_path):
    """A gitlink at `Members/IRRS`, committed with no section, whose
    directory is a clone of its own, its `.git` a directory holding its
    commits and nothing else: it is no checkout to delete by hand, so the
    second path's removal names none, and the next run moves the clone out
    of the holder whole, as #828 moves one. Typed as printed, the member is
    where its row says, every clone checks every member out, the gate
    passes in every mode and the same `add` goes through."""
    if disk_folds(holder):
        pytest.skip("`Members/IRRS` beside `members/IRRS` needs a disk that "
                    "does not fold case")
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    clone = cloned_just_pushed(family["remotes"] / "IRSS.git",
                               holder / VARIANT, recurse=False)
    head = git("rev-parse", "HEAD", cwd=clone).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{head},{VARIANT}",
        cwd=holder)
    git("commit", "-qm", "A clone of its own at Members/IRRS", cwd=holder)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + f"in the index: `{VARIANT}` (a submodule)",
                    remedy_of(second_out(VARIANT, commit="the removal")))
    assert typed_as_printed(holder, said[1]) == [
        f"git rm -r --cached -- {VARIANT}", "git commit"]
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + f"on disk and untracked: `{VARIANT}` (a "
                    "directory)", remedy_of(untracked_moved(VARIANT)))
    assert typed_as_printed(holder, said[1]) == [f"mv -- {VARIANT} ../moved-1"]
    assert (holder.parent / "moved-1" / ".git").is_dir()
    registered(holder, family["root"], commit)
    every_clone_checks_every_member_out(holder, family["remotes"], tmp_path,
                                        "w865f/second-clone", commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_link_in_members_at_a_rows_variant_is_named(family, holder,
                                                      offline):
    """rv865b's NIT 1: a link `members/irrs -> IRRS`, to the member's own
    checkout. `samefile` follows a link, so at `f7072d08` it was let
    through on Linux, and `add` went through beside it; `4268f804` named it.
    A link is never the row's own path: it is named on disk, and moved out
    of the holder, the link alone; typed as printed, the member is where
    its row says, the gate passes and the same `add` goes through."""
    no_symlink_on_windows()
    if disk_folds(holder):
        pytest.skip("a link `members/irrs` beside `members/IRRS` needs a "
                    "disk that does not fold case")
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    os.symlink("IRRS", holder / ROW_SPELLED, target_is_directory=True)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (ROW_VARIANT + f"on disk and untracked: `{ROW_SPELLED}` "
                    "(a symlink)", remedy_of(untracked_moved(ROW_SPELLED)))
    assert typed_as_printed(holder, said[1]) == [
        f"mv -- {ROW_SPELLED} ../moved-1"]
    assert os.readlink(holder.parent / "moved-1") == "IRRS"
    registered(holder, family["root"], commit)
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


def clone_of_its_own(root: Path, remotes: Path, path: str) -> None:
    """A clone of IRSS of its own at `path`, its `.git` a directory, read
    through git, with its legs checked out in it: each a directory holding
    a `.git` FILE, a checkout whose store is in the clone's own."""
    cloned_just_pushed(remotes / "IRSS.git", root / path)
    assert (root / path / ".git").is_dir()
    assert (root / path / "spec" / ".git").is_file()


def the_clone_moved(root: Path, remotes: Path, tmp_path: Path) -> None:
    """`Members/X` itself a clone of its own (rv865's R7): the walk does not
    enter a directory moved that is a repository, whose legs are its own."""
    clone_of_its_own(root, remotes, "Members/X")


def a_clone_and_a_link_inside(root: Path, remotes: Path,
                              tmp_path: Path) -> None:
    """`Members/X` a plain directory holding a clone of its own at
    `Members/X/Y` (rv865's R8 and R10: neither it nor its legs are named,
    the `mv` takes it whole) and a link `Members/X/L` to a directory outside
    the holder that holds what looks like a checkout, `C/.git` a file
    (rv865's R9: the walk does not follow a link)."""
    no_symlink_on_windows()
    clone_of_its_own(root, remotes, "Members/X/Y")
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / "C").mkdir(parents=True)
    (elsewhere / "C" / ".git").write_bytes(b"gitdir: nowhere\n")
    os.symlink(str(elsewhere), root / "Members" / "X" / "L",
               target_is_directory=True)


#: `{state: how `Members/X` is made}`.
CLONES = {"the clone moved": the_clone_moved,
          "a clone and a link inside": a_clone_and_a_link_inside}


@pytest.mark.parametrize("state", list(CLONES))
def test_a_clone_of_its_own_in_a_directory_moved_is_moved_whole(
        family, holder, offline, tmp_path, state):
    """Line 2's other side: a clone of its own keeps its commits in its own
    `.git` directory, so the `mv` of `Members/X` takes it whole, and only
    that `mv` is named: not the clone, not its legs, whether `Members/X` is
    the clone or holds one, and nothing behind a link inside it. Typed as
    printed, the clone is out of the holder with its `.git` directory, the
    gate passes and the same `add` goes through."""
    if disk_folds(holder):
        pytest.skip("`Members/X` beside `members/` needs a disk that does "
                    "not fold case")
    CLONES[state](holder, family["remotes"], tmp_path)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + "on disk and untracked: `Members/X` (a "
                    "directory)", remedy_of(untracked_moved("Members/X")))
    assert typed_as_printed(holder, said[1]) == ["mv -- Members/X ../moved-1"]
    assert (tmp_path / "moved-1" / (
        ".git" if state == "the clone moved" else "Y/.git")).is_dir()
    gate_then_add(offline, holder, family["remotes"])


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
    that does not (`disk_as`): one text on both, since each is in the index,
    HEAD or `.gitmodules`, and the disk holds the member's checkout at its
    row's path alone, which is no other spelling on either."""
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


@pytest.mark.parametrize("folding", [True, False], ids=["folding", "linux"])
def test_the_members_own_checkout_listed_in_another_case_is_its_own(
        family, holder, family_module, offline, monkeypatch, capsys,
        folding):
    """rv865's SHOULD 1: `git mv members/IRRS members/irrs`, committed,
    which moves the member's checkout, gitlink and section: line 3's own
    gitlink state, with its checkout. Its move back typed as printed
    records the gitlink and the section at `members/IRRS` again, and on a
    disk that folds case its closing guard `[ members/irrs -ef members/IRRS
    ]` is true, so nothing moves: the member's one checkout is listed as
    `members/irrs`, the spelling it was made in. The next `add` refused it
    as on disk and untracked, every time it ran. Now a disk that takes it
    for the row's own path (`samefile`) lets it through; on one that does
    not, `members/IRRS` holds nothing and `members/irrs` is still named.
    Asked in process (`disk_as`), with `--dry-run`."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    git("mv", ROW, ROW_SPELLED, cwd=holder)
    git("commit", "-qm", f"git mv {ROW} {ROW_SPELLED}", cwd=holder)
    move, closing = moved_back({ROW: ([ROW_SPELLED], commit)},
                               sections=(ROW,))
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (ROW_VARIANT + f"in the index: `{ROW_SPELLED}` (a "
                    "submodule)", remedy_of(move, *closing))
    # The move back's git lines, as printed; on a disk that folds case the
    # guarded `mv` moves nothing, and the update finds the member there.
    for line in (f"git rm -r --cached --ignore-unmatch -- {ROW_SPELLED}",
                 record(commit), point_back(), "git add -- .gitmodules"):
        git(*line.split()[1:], cwd=holder)
    git("commit", "-qm", "The move back", cwd=holder)
    disk_as(monkeypatch, holder, folding)
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    code = family_module.main([
        "add", "--family-root", str(holder), "--member", f"{ORG}/{SPARE}",
        "--local-remote-dir", str(family["remotes"]), "--dry-run"])
    out, err = capsys.readouterr()
    if folding:
        assert code == 0, out + err
        assert "REFUSED" not in err
    else:
        assert code == 2, out + err
        assert err.startswith(ROW_VARIANT + "on disk and untracked: "
                              f"`{ROW_SPELLED}` (a directory)"), err


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


def unmerged_at(root: Path, name: str, stages: tuple[bytes, ...],
                numbers: tuple[int, ...] = (1, 2, 3)) -> None:
    """`name` unmerged, a file at stages `numbers` (1, 2 and 3) holding
    `stages`, and at no stage 0, with nothing in progress, as a conflicted
    `git stash pop` leaves it, written by `update-index --index-info` as
    BYTES."""
    git("rm", "-q", "--cached", "--ignore-unmatch", "--", name, cwd=root)
    written = subprocess.run(
        ["git", "update-index", "--index-info"], cwd=str(root),
        input="".join(f"100644 {blob(root, data)} {stage}\t{name}\n"
                      for stage, data in zip(numbers, stages)
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


@pytest.mark.parametrize("shell", ["dash", "bash"])
def test_a_link_at_a_variant_the_index_holds_is_refused_first(
        family, holder, offline, monkeypatch, shell):
    """The coordinator's added state for #840 (w761's candidate 8 on #828):
    #646's state, the member's gitlink at `Members/IRRS` in the index, and
    a link there on disk to the member's checkout. git 2.45.1 and later
    refuse `git status` itself (`expected submodule path 'Members/IRRS' not
    to be a symbolic link`, measured on 2.47.1). ALREADY ANSWERED at #828's
    head, measured on git 2.43 and 2.47.1: `add` reads no `git status`
    there and gives its spelling refusal first, no `fatal:` and no
    traceback. Typed as printed, in dash and in bash, the move back's guard
    moves the link out of the holder, the link alone, in #839's form, `[ !
    -L Members/IRRS ]` first (rv865b's NIT 4: `[ Members/IRRS -ef
    members/IRRS ]` followed it to the row's own directory and kept it, and
    a third round named it on disk); the member is where its row says, the
    gate passes and the same `add` goes through, two rounds on every git."""
    no_symlink_on_windows()
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} on this system")
    monkeypatch.setattr(member_variant, "SHELL", shell)
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
    assert not os.path.lexists(holder / VARIANT)
    assert os.readlink(holder.parent / "Members-IRRS") == os.path.join(
        "..", ROW)
    assert (holder / ROW / ".git").is_file()
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


# --- 7. an unmerged file in the way of the move back -------------------------

#: A file under the row's path.
NOTES = f"{ROW}/notes"
#: The three sides of an unmerged file, and what a conflict leaves on disk.
SIDES = (b"base\n", b"ours\n", b"theirs\n")
MARKED = b"<<<<<<< ours\nours\n=======\ntheirs\n>>>>>>> theirs\n"


def unmerged_file(root: Path, name: str, on_disk: bool,
                  numbers: tuple[int, ...] = (1, 2, 3)) -> None:
    """`name` unmerged at the stages `numbers`, its conflict on disk where
    `on_disk`."""
    unmerged_at(root, name, tuple(SIDES[number - 1] for number in numbers),
                numbers)
    if on_disk:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(MARKED)


#: `{state: (the entry, whether it is on disk, whether `git mv
#: members/IRRS Members/IRRS` is committed, the stages it is held at)}`.
#: Stages 1 and 3 alone are a file this side deleted and the other changed,
#: with no stage 2 (rv865's R42); on disk with the move staged, neither the
#: removal nor the move leaves anything to commit (rv865's R23).
UNMERGED_IN_THE_WAY = {
    "under the row's path, on disk": (NOTES, True, True, (1, 2, 3)),
    "at the row's path, on disk": (ROW, True, True, (1, 2, 3)),
    "under the row's path, off disk": (NOTES, False, True, (1, 2, 3)),
    "off disk, the move staged": (NOTES, False, False, (1, 2, 3)),
    "on disk, the move staged": (NOTES, True, False, (1, 2, 3)),
    "deleted on this side, off disk": (NOTES, False, True, (1, 3)),
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
    entry, on_disk, committed, numbers = UNMERGED_IN_THE_WAY[state]
    commit = mount_moved(holder, committed)
    unmerged_file(holder, entry, on_disk, numbers)
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
