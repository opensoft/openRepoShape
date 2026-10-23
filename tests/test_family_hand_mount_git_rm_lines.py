# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/validate-family.py`: the `git rm`
line `member-gitlink-unnamed` prints for a member mounted by hand works
typed, and the gate after the commit passes (#936).

THE ISSUE'S THREE STATES, each measured on #889's head (29083a5f) before
this change, every printed line typed as printed:

1. A gitlink the index stages at a commit HEAD does not record there, with
   something on disk at it: `git mv members/IRRS members/IRRS2`, staged,
   clean or with a commit in the checkout it moved; a gitlink staged over
   an empty directory, a directory holding a file or a dangling link (x889c's
   NIT A on #889); a `git submodule add`
   not committed; a checkout moved to `HEAD~1` and `git add`-ed. The
   printed `git rm -- <path>` exited 1 in each (`the following file has
   changes staged in the index`, or, where what is on disk differs from
   what is staged too, `... has staged content different from both the
   file and the HEAD`), and the gate found the gitlink again. `-f` would
   take the checkout's changes with it. The line is `git rm --cached` now,
   with `-f` over anything but an empty directory, which touches no file,
   and the text says why, quoting both refusals, what it leaves on disk
   and what to do with it. Where the work tree's `.gitmodules` holds a
   change not staged, `git add -- .gitmodules` comes first, since git
   takes no gitlink out of the index until it is staged (RV1025's NIT 2 on
   #1025).
2. A hand mount with its own section, then a staged removal of a member,
   with the work tree's `.gitmodules` deleted: the `git rm` took the
   section out of no file, the removal's put-back brought it back, and the
   gate found `gitmodules-path-unnamed` after the commit. The file is put
   back first now, from where git reads it, and the `git rm` takes the
   section out of it.
3. A member cloned by hand into `members/IRQS`, its `.git` a directory,
   then `git add`, with no section giving the path: the printed `git rm --
   members/IRQS` died (`could not lookup name for submodule`, exit 128).
   The line is `git rm --cached` now, and the clone, which holds its
   commits there and nowhere else, is said to be moved out whole.

BEYOND THE ISSUE, its goal (every hand mount's `git rm` works typed): a
directory holding files and no `.git`, or a file, at a committed hand
mount's path, where the plain line exited 1 (`the following file has local
modifications`). It is `git rm --cached` too.

THE CONTROLS: a hand mount with nothing on disk, one with its checkout and
its section, and a clone a section names, which a plain `git rm` moves into
the holder's store first: each still prints the plain `git rm`, which works.

WHAT CANNOT BE READ (#430, met on main after #956): what is on disk at a
hand mount is asked as #956 asks it, so a `.git` whose `stat` is refused is
`member-unreadable` by name, never a traceback or a false "no checkout".
`tests/test_validate_family_unreadable.py` holds the rows for the path
itself and the folder above it.

Each row types every `git` line as printed, in the order printed, split as
a POSIX shell splits it and run with no shell (not `family.py add`, which
mounts a hand mount again only where the person wants it), deals by hand
with what the text says to delete or move out, commits, then asks the gate
in every mode, and a plain clone's `git submodule update --init
--recursive` must check out both members. The helpers are #879's
(`tests/test_family_holder_remedies_compose.py`) and those it imports.

#1036, RV1025'S SHOULD 1 ON #1025: state 1's `git submodule add`, not
committed, with the work tree's `.gitmodules` then deleted. The section
the add staged is in the index's file alone, which git reads in place of
the one gone (`git submodule status members/IRQS` maps it, git 2.43), but
`gitmodules-path-unnamed` read the work tree's alone and named nothing:
every line typed exited 0, the gate passed, and the commit of what was
staged recorded the section. It reads the file git reads now, the index's,
then HEAD's, and its lines put that file back first (`git config -f`
on no file exits 5 and makes none). Its rows are at the end of this file.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import rmtree
from test_bump_leg_unopenable import made_unopenable, needs_a_mode
from test_family import SPARE, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import hand_mounted, type_line
from test_family_head_lost_gitmodules import (  # noqa: F401
    commit_all, staged_and_committed,
)
from test_family_holder_remedies_compose import (
    MODES, OTHER_ROW, PUT_BACK_THEN, a_file_at, cloning, codes_of,
    committed_with_its_checkout, ends_well, files_at, found_alike,
    head_paths, holding_a_file, moved_back_and_added, moved_by_git_mv,
    moved_with_a_commit, staged_by_hand, typed_in_order, value_committed,
)
from test_family_member_path import raw
from test_family_unnamed_gitlink import (
    FORCED_NO_HEAD, THEN_STAGE, TOOLS, section_first, submodule_added,
)
from test_validate_family_typed_states import GONE, ROW, gone
from test_validate_family_unnamed_mounts import (
    SECTION_REMEDY, SECTION_SAID, SECTION_UNDER_GIT_RM, STAGE, VARIANT,
    commands, removal, with_section,
)

HAND = f"members/{SPARE}"

#: What a hand mount's text says of a `git rm --cached` it prints (#936),
#: by why a plain `git rm` is not printed. A holder's CI matches on text, so
#: each is pinned here and not rebuilt from the gate's own strings.
CACHED_SAID = ("take it out of the index alone with the second, which "
               "touches no file{forced}, since a plain git rm refuses it "
               "here: ")
FORCED = (" (-f takes out a staged gitlink whose checkout has moved on or "
          "holds a file git does not track, which git rm otherwise refuses, "
          "and with --cached touches no file)")
STAGED_WHY = ("the index stages it at a commit HEAD does not record there, "
              "with something on disk at it (the following file has changes "
              "staged in the index, or, where what is on disk differs too, "
              "has staged content different from both the file and the "
              "HEAD, exit 1)")
CLONE_WHY = ("its .git is a directory and no section of .gitmodules gives "
             "its path, so git rm cannot move that directory into this "
             "holder's store first (could not lookup name for submodule, "
             "exit 128)")
NO_CHECKOUT_WHY = ("what is on disk there is no checkout (the following file "
                   "has local modifications, exit 1)")
#: What it says of the commit, where HEAD records the gitlink, and not.
COMMIT_THAT = (", and commit that removal, since family.py add refuses a "
               "path under another spelling of members/ that HEAD holds and "
               "the index no longer does, then mount it with the third")
NOTHING_LEFT = ("; HEAD records nothing there, so nothing of it is left to "
                "commit, then mount it with the third")
#: What it says is left at `{path}`, untracked, and what to do with it.
ADD_REFUSES = ("before the add, which refuses anything at {path} "
               "(member-path-taken).")
CHECKOUT_LEFT = (
    " The checkout at {path} stays there, untracked: its .git file names "
    "the store that keeps its commits whatever becomes of the checkout, so "
    "only what is not committed is in the checkout alone, which `git -C "
    "{path} status` shows. Delete it by hand once nothing only it holds is "
    "needed, " + ADD_REFUSES)
EMPTY_LEFT = (" The empty directory at {path} stays there: delete it "
              + ADD_REFUSES)
CLONE_LEFT = (
    " The clone at {path}, whose .git is a directory, stays there, "
    "untracked: it holds its commits there and nowhere else, and `git -C "
    "{path} log --oneline HEAD --branches --not --remotes` lists the ones "
    "not pushed, so move it out of the holder whole, by hand, rather than "
    "delete it, " + ADD_REFUSES)
NO_CHECKOUT_LEFT = (
    " What is on disk at {path}, which is no checkout, stays there, "
    "untracked: move it out of the holder, or delete it by hand once "
    "nothing in it is needed, " + ADD_REFUSES)
#: What the plain line says, as before this change.
PLAIN_SAID = ("take it out with the second, which refuses while its "
              "checkout holds changes and takes its .gitmodules section out "
              "too, and commit that removal")


def mount_of(found: list[str], path: str) -> str:
    """The hand mount's finding for `path` among `found`."""
    head = f"FINDING member-gitlink-unnamed: {path} "
    mounts = [finding for finding in found if finding.startswith(head)]
    assert len(mounts) == 1, found
    return mounts[0]


def typed_around(root: Path, env: dict, found: list[str], dealt) -> None:
    """Every `git` line `found` prints, typed as printed, in the order
    printed, but each `git submodule update`, typed after `dealt()` has
    dealt by hand with what the text says to delete or move out first:
    the update points a moved checkout's store back at the row's path
    (#879's C4)."""
    later = []
    for finding in found:
        for line in commands(finding):
            if line.startswith("git submodule update"):
                later.append(line)
            elif line.startswith("git "):
                type_line(root, env, line)
    dealt()
    for line in later:
        type_line(root, env, line)


def committed_if_staged(root: Path, env: dict) -> None:
    """`.gitmodules` staged, as the section's lines say, then a commit of
    what is staged, where anything is: after a gitlink HEAD never recorded
    is taken out, nothing of it is left to commit."""
    raw(root, env, "add", "--", ".gitmodules")
    if raw(root, env, "diff", "--cached", "--quiet",
           check=False).returncode:
        commit_all(root, env, "Typed in order")


def deleted(where: Path) -> None:
    """What is at `where` deleted by hand, a directory or a file."""
    if where.is_dir() and not where.is_symlink():
        rmtree(where)
    else:
        where.unlink()


# --- 1. a gitlink staged at a commit HEAD does not record ------------------

def added_not_committed(root: Path, env: dict, family) -> str:
    """`git submodule add` at `members/IRQS`, not committed: its checkout and
    its section, staged. Returns the path."""
    submodule_added(root, env, family, HAND)
    return HAND


#: `(the state, the line's flag, whether HEAD records the gitlink, what is
#: left on disk)`. Typed, a plain `git rm` said `has changes staged in the
#: index` in the first four, and `has staged content different from both
#: the file and the HEAD` in the last three, whose disk differs from what
#: is staged (lane 1's NIT 1 on #889, round 3). A dangling link is
#: something on disk, as `os.path.lexists` reads it and git refuses it,
#: where `exists` reads nothing (x889c's NIT A on #889).
STAGED = {
    "git-mv": (moved_by_git_mv, " -f", False, CHECKOUT_LEFT),
    "an-empty-directory": (staged_by_hand(Path.mkdir), "", False,
                           EMPTY_LEFT),
    "submodule-add-not-committed": (added_not_committed, " -f", False,
                                    CHECKOUT_LEFT),
    "head-records-another-commit": (moved_back_and_added, " -f", True,
                                    CHECKOUT_LEFT),
    "git-mv-and-a-commit-in-it": (moved_with_a_commit, " -f", False,
                                  CHECKOUT_LEFT),
    "a-directory-holding-a-file": (staged_by_hand(holding_a_file), " -f",
                                   False, NO_CHECKOUT_LEFT),
    "a-dangling-link": (staged_by_hand(
        lambda where: where.symlink_to("nowhere")), " -f", False,
        NO_CHECKOUT_LEFT),
}


@pytest.mark.parametrize("make, flag, in_head, left", STAGED.values(),
                         ids=STAGED)
def test_issue_1_a_gitlink_staged_over_what_is_on_disk_comes_out_cached(
        family, holder, offline, tmp_path, make, flag, in_head, left):
    """The issue's state 1 (lane 1's SHOULD on #889): the index stages the
    gitlink at a commit HEAD does not record there, with something on disk
    at it. The printed `git rm -- <path>` exited 1, with either of git's
    two refusals. It is `git rm --cached` now, in every mode, `-f` over
    anything but an empty directory, and the text says why, quoting both
    refusals, what is left, and that nothing is left to commit where HEAD
    records nothing.
    A section that gives the path prints its own lines, which `--cached`
    leaves to it. Typed in order, what is left deleted by hand as the text
    says, then committed: nothing is left, the gate passes in every mode
    and a plain clone checks both members out."""
    env = cloning(offline, tmp_path, family)
    path = make(holder, env, family)

    found = found_alike(holder, *MODES)

    mount = mount_of(found, path)
    assert commands(mount)[1] == f"git rm --cached{flag} -- {path}"
    assert (CACHED_SAID.format(forced=FORCED if flag else "") + STAGED_WHY
            + (COMMIT_THAT if in_head else NOTHING_LEFT)) in mount, mount
    assert left.format(path=path) in mount, mount
    typed_around(holder, env, found, lambda: deleted(holder / path))
    committed_if_staged(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


#: What the text says where the work tree's `.gitmodules` holds a change the
#: index does not (`_stage_first`, #879's C3): `git add -- .gitmodules`
#: first, since git takes no gitlink out of the index, `--cached` and `-f` or
#: not, until it is staged (RV1025's NIT 2 on #1025).
STAGED_FIRST = (
    "stage .gitmodules with the second, which stages every other change in "
    "it too, since git rm refuses to take any gitlink out of the index, -f "
    "or not, while .gitmodules holds changes not staged (please stage your "
    "changes to .gitmodules or stash them to proceed, exit 128), as lines "
    "printed above may leave it or as it stands, take it out of the index "
    "alone with the third, which touches no file{forced}, since a plain git "
    "rm refuses it here: ")
NOTHING_LEFT_FOURTH = ("; HEAD records nothing there, so nothing of it is "
                       "left to commit, then mount it with the fourth")


def edited_after_git_mv(root: Path, env: dict, family) -> str:
    """`moved_by_git_mv`'s state, then a line appended to the work tree's
    `.gitmodules` by hand and not staged. Returns the moved path."""
    path = moved_by_git_mv(root, env, family)
    with (root / ".gitmodules").open("ab") as handle:
        handle.write(b"# a note made by hand\n")
    return path


def test_issue_1_a_gitmodules_change_not_staged_is_staged_before_cached(
        family, holder, offline, tmp_path):
    """State 1's `git mv members/IRRS members/IRRS2`, staged, then a line
    appended to the work tree's `.gitmodules` by hand and not staged
    (RV1025's NIT 2 on #1025). Git takes no gitlink out of the index,
    `--cached` and `-f` or not, while that file holds changes the index
    does not: `git rm --cached -f` typed first exits 128 (`please stage
    your changes to .gitmodules or stash them to proceed`). So the
    `--cached` line comes after `git add -- .gitmodules`, in every mode,
    and the text numbers both. Typed in order, the moved checkout deleted
    by hand as the text says, then committed: nothing is left, the gate
    passes in every mode and a plain clone checks both members out."""
    env = cloning(offline, tmp_path, family)
    path = edited_after_git_mv(holder, env, family)

    found = found_alike(holder, *MODES)

    mount = mount_of(found, path)
    assert commands(mount)[1:3] == ["git add -- .gitmodules",
                                    f"git rm --cached -f -- {path}"], mount
    assert (STAGED_FIRST.format(forced=FORCED) + STAGED_WHY
            + NOTHING_LEFT_FOURTH) in mount, mount
    assert CHECKOUT_LEFT.format(path=path) in mount, mount
    typed_around(holder, env, found, lambda: deleted(holder / path))
    committed_if_staged(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- 2. a hand mount's section, with the work tree's file gone ------------

#: The flags of the removal of MEMBER, by how it was staged.
REMOVED = {"cached": ["--cached"], "plain": []}


def gone_from(root: Path, env: dict, how: str) -> None:
    """The work tree's `.gitmodules` deleted, or its deletion staged too, as
    `how` (`GONE`) says: by `git rm --cached` and the file deleted, since
    after a plain `git rm` of a member the plain `git rm` of the file
    refuses its staged change."""
    if how != "deleted":
        raw(root, env, "rm", "-q", "--cached", "--", ".gitmodules")
    (root / ".gitmodules").unlink()


def removal_lines(kind: str, how: str, url: str) -> list[str]:
    """What the removal's finding prints after the hand mount's put-back:
    its gitlink, and after a plain `git rm` its checkout, with its section
    written back key by key where the file put back, the index's, lacks
    it, which HEAD's does not."""
    if kind == "cached":
        return [f"git reset -q -- {ROW}"]
    section = ([f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
                f"git config -f .gitmodules submodule.{ROW}.url {url}",
                "git add -- .gitmodules"] if how == "deleted" else [])
    return [f"git reset -q -- {ROW}", *section,
            f"git submodule update --init --recursive -- {ROW}"]


@pytest.mark.parametrize("how", GONE)
@pytest.mark.parametrize("kind", REMOVED)
def test_issue_2_a_hand_mount_s_section_comes_out_of_the_file_put_back(
        family, holder, offline, tmp_path, kind, how):
    """The issue's state 2: a hand mount with its checkout and its section,
    committed, then `git rm --cached members/IRRS` or a plain `git rm
    members/IRRS`, and the work tree's `.gitmodules` deleted or its
    deletion staged. The hand mount's `git rm` took its section out of no
    file, the removal's put-back brought it back, and the gate found
    `gitmodules-path-unnamed` after the commit. The hand mount puts the
    file back first now, from where git reads it, and the removal after it
    puts nothing back, writing MEMBER's section back key by key where the
    file put back lacks it. Typed in order and committed, nothing is left,
    HEAD's `.gitmodules` gives both members, the gate passes in every mode
    and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    path = committed_with_its_checkout(holder, env, family)
    url = raw(holder, env, "config", "-f", ".gitmodules",
              f"submodule.{ROW}.url").stdout.decode("utf-8").strip()
    raw(holder, env, "rm", "-q", *REMOVED[kind], "--", ROW)
    gone_from(holder, env, how)

    found = found_alike(holder, *MODES)

    whose, put_back = GONE[how]
    mount = mount_of(found, path)
    assert commands(mount)[1:3] == [put_back, f"git rm -- {path}"]
    assert (f"put .gitmodules, gone from the work tree, back from {whose} "
            "with the second, so that the git rm takes its section out of "
            "that file and every other section stays, take it out with the "
            "third, which refuses while its checkout holds changes") in mount
    assert commands(found[-1]) == removal_lines(kind, how, url)
    typed_in_order(holder, env, validate(holder, "--no-members"))
    staged_and_committed(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    ends_well(holder, env, family, tmp_path)


# --- 3. a clone of its own, added by hand, that no section names -----------

@pytest.mark.parametrize("committed", [True, False],
                         ids=["committed", "staged"])
def test_issue_3_a_clone_no_section_names_comes_out_cached_and_is_kept(
        family, holder, offline, tmp_path, committed):
    """The issue's state 3: IRQS cloned by hand into `members/IRQS`, with a
    commit only that clone holds, then `git add members/IRQS`, committed or
    not, and no section giving the path. The printed `git rm --
    members/IRQS` died (`could not lookup name for submodule`, exit 128).
    It is `git rm --cached` now, in every mode, `-f` where the index
    stages it and HEAD records nothing, and the text says to move the
    clone out whole, with the `git log` that lists its commit. Typed, the
    clone moved out of the holder as it says, and committed where HEAD
    recorded it: nothing is left, the moved clone keeps its commit, the
    gate passes in every mode and a plain clone checks both members out."""
    env = cloning(offline, tmp_path, family)
    raw(holder, env, "clone", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), HAND)
    clone = holder / HAND
    raw(clone, env, "-c", "user.name=t", "-c", "user.email=t@t", "commit",
        "-q", "--allow-empty", "-m", "Only this clone holds it")
    made = raw(clone, env, "rev-parse", "HEAD").stdout.decode("ascii").strip()
    raw(holder, env, "add", "--", HAND)
    if committed:
        commit_all(holder, env, "A clone mounted by hand")

    found = found_alike(holder, *MODES)

    mount = mount_of(found, HAND)
    flag = "" if committed else " -f"
    assert commands(mount)[1] == f"git rm --cached{flag} -- {HAND}"
    assert (CACHED_SAID.format(forced=FORCED if flag else "") + CLONE_WHY
            + (COMMIT_THAT if committed else NOTHING_LEFT)) in mount, mount
    assert CLONE_LEFT.format(path=HAND) in mount, mount
    listed = raw(clone, env, "log", "--oneline", "HEAD", "--branches",
                 "--not", "--remotes").stdout.decode().split()
    assert made.startswith(listed[0]), listed
    kept = tmp_path / "kept-out"
    typed_around(holder, env, found,
                 lambda: shutil.move(str(clone), str(kept)))
    committed_if_staged(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert raw(kept, env, "cat-file", "-e", made,
               check=False).returncode == 0
    ends_well(holder, env, family, tmp_path)


# --- beyond the issue: what is on disk is no checkout ----------------------

NO_CHECKOUTS = {"a-directory-holding-files": files_at, "a-file": a_file_at}


@pytest.mark.parametrize("make", NO_CHECKOUTS.values(), ids=NO_CHECKOUTS)
def test_beyond_what_is_no_checkout_comes_out_cached(
        family, holder, offline, tmp_path, make):
    """Beyond the issue, its goal: a hand mount committed with nothing on
    disk, then a directory holding a file and no `.git`, or a file, made at
    its path. The printed `git rm -- members/IRQS` exited 1 (`the following
    file has local modifications`). It is `git rm --cached` now, in every
    mode, and the text says what is left. Typed, what is left deleted by
    hand, and committed: nothing is left, the gate passes in every mode
    and a plain clone checks both members out."""
    env = cloning(offline, tmp_path, family)
    path = hand_mounted(holder, env, family)
    make(holder, path)

    found = found_alike(holder, *MODES)

    mount = mount_of(found, path)
    assert commands(mount)[1] == f"git rm --cached -- {path}"
    assert (CACHED_SAID.format(forced="") + NO_CHECKOUT_WHY
            + COMMIT_THAT) in mount, mount
    assert NO_CHECKOUT_LEFT.format(path=path) in mount, mount
    typed_around(holder, env, found, lambda: deleted(holder / path))
    committed_if_staged(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- the controls: the plain git rm, which works ---------------------------

def clone_a_section_names(root: Path, env: dict, family) -> str:
    """IRQS cloned by hand into `members/IRQS`, its `.git` a directory, then
    `git submodule add` of it, which writes its section, committed. Returns
    the path."""
    remote = str(family["remotes"] / f"{SPARE}.git")
    raw(root, env, "clone", "-q", "--", remote, HAND)
    raw(root, env, "submodule", "add", "-q", "--", remote, HAND)
    commit_all(root, env, "A clone a section names")
    return HAND


CONTROLS = {
    "nothing-on-disk": hand_mounted,
    "a-checkout-and-its-section": committed_with_its_checkout,
    "a-clone-a-section-names": clone_a_section_names,
}


@pytest.mark.parametrize("make", CONTROLS.values(), ids=CONTROLS)
def test_control_a_hand_mount_the_plain_git_rm_takes_keeps_it(
        family, holder, offline, tmp_path, make):
    """The controls: a hand mount with nothing on disk, one with its
    checkout and its section, and a clone whose path a section gives,
    which a plain `git rm` moves into the holder's store first. Each prints
    the plain `git rm`, as before this change. Typed in order and
    committed, nothing is left, the gate passes in every mode and a plain
    clone checks both members out."""
    env = cloning(offline, tmp_path, family)
    path = make(holder, env, family)

    found = found_alike(holder, *MODES)

    mount = mount_of(found, path)
    assert commands(mount)[1] == f"git rm -- {path}"
    assert PLAIN_SAID in mount, mount
    typed_in_order(holder, env, validate(holder, "--no-members"))
    commit_all(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- what cannot be read (#430) --------------------------------------------

#: A hand mount's checkout with its section, committed, whose plain `git rm`
#: turns on its `.git` (`_hand_cached`), and the same staged by `git
#: submodule add`, whose `--cached` line says what it leaves by its `.git`
#: (`_cached_left`).
UNSEARCHABLE = {
    "a-checkout-and-its-section": committed_with_its_checkout,
    "submodule-add-not-committed": added_not_committed,
}


@needs_a_mode
@pytest.mark.parametrize("make", UNSEARCHABLE.values(), ids=UNSEARCHABLE)
def test_a_hand_mount_s_git_this_user_cannot_reach_is_refused_by_name(
        family, holder, offline, tmp_path, make):
    """WHAT IS ON DISK IS ASKED AS #430 ASKS IT (#956): the checkout at mode
    444, which this user can list but not search, so the `stat` of its
    `.git` is refused. `os.path.lexists` read no `.git` there, a false "no
    checkout" and a `git rm --cached` the plain line did not need, and
    `Path.is_dir()` ended the run in a traceback on 3.12. Now each mode is
    refused by name, exit 2, with the `chmod` cure, and with the mode back
    the gate says what it said before."""
    env = cloning(offline, tmp_path, family)
    path = make(holder, env, family)
    before = found_alike(holder, *MODES)
    with made_unopenable(holder, path, mode=0o444):
        refused = [validate(holder, *extra) for extra in MODES]
    for result in refused:
        assert result.returncode == 2, result.stderr
        assert result.stderr.splitlines()[0] == (
            f"REFUSED member-unreadable: {path}/.git: cannot be read "
            "(Permission denied)"), result.stderr
        assert "Traceback" not in result.stderr
        assert "chmod u+rx" in result.stderr
    assert found_alike(holder, *MODES) == before


# --- #1036: a section the file git reads gives, the work tree's gone ---------

def put_back_said(how: str) -> str:
    """What `gitmodules-path-unnamed` says of the line it prints before a
    section's keys where the work tree's `.gitmodules` is gone, as `how`
    (`GONE`) says, ahead of what it says last (#1036)."""
    whose = GONE[how][0]
    return f"after the line that puts {PUT_BACK_THEN.format(whose=whose)}, "


def index_url(root: Path, env: dict, name: str) -> str:
    """The url the section `name` of the index's `.gitmodules` gives."""
    return raw(root, env, "config", "--blob", ":.gitmodules",
               f"submodule.{name}.url").stdout.decode("utf-8").strip()


def what_is_staged_committed(root: Path, env: dict) -> None:
    """`git commit` of what is staged, typed by the person after the
    printed lines, the issue's Verify, and nothing else: no `git add` the
    text does not print (RV1069's SHOULD 1 on #1069). Where nothing is
    staged it exits 1, `nothing to commit`, and HEAD is as it was."""
    raw(root, env, "commit", "-q", "-m", "What is staged", check=False)


def lines_of(*lines: str) -> str:
    """`lines` as a finding prints them, one to an indented line."""
    return "".join(f"\n    {line}" for line in lines)


def ghost_out(how: str, *, put_back: bool) -> str:
    """`gitmodules-path-unnamed` whole for a section named `ghost` giving
    `Members/IRRS`, a case variant of MEMBER's path, url
    `/nowhere/ghost.git`, with the work tree's `.gitmodules` gone as `how`
    (`GONE`) says: its keys' lines, after the line that puts the file back
    where `put_back`, then the line that stages the file, since HEAD's
    holds the section (#1077, RV1069's NIT 3 on #1069)."""
    line = GONE[how][1]
    return (SECTION_SAID.format(path="Members/IRRS", name="ghost",
                                url="url /nowhere/ghost.git")
            + VARIANT.format(row_path=ROW, project="IRRS")
            + " Take the section out by hand, in a POSIX shell, every key it "
            "holds, so a submodule later given its name inherits none of "
            "them, " + (put_back_said(how) if put_back else "")
            + "then stage and commit .gitmodules:"
            + lines_of(*([line] if put_back else []),
                       *removal("ghost", "path", "url"), STAGE))


def test_1036_a_section_the_index_alone_gives_comes_out_of_the_file_put_back(
        family, holder, offline, tmp_path):
    """#1036, RV1025's SHOULD 1 on #1025: `git submodule add` at
    `members/IRQS`, not committed, then the work tree's `.gitmodules`
    deleted, not staged (`MD .gitmodules`). The index's file, which git
    reads in its place, gives IRQS's section, and `gitmodules-path-unnamed`
    read the work tree's alone: the hand mount's `git rm --cached -f` exited
    0, the gate passed, and the commit of what was staged recorded the
    section. The section is a finding now, in every mode, whose lines put
    the index's file back first, take every key out, then stage the file,
    since HEAD's holds no section of that name (RV1069's SHOULD 1 on #1069:
    the text said "then commit .gitmodules", the index's file kept the
    section, and a `git commit` recorded it). Only the printed lines typed,
    in order, the checkout deleted as the text says, then `git commit` of
    what is staged, the issue's Verify: HEAD's `.gitmodules` gives the two
    members alone, nothing is left, the gate passes in every mode and a
    plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    path = added_not_committed(holder, env, family)
    url = index_url(holder, env, path)
    gone(holder, env, "deleted")

    found = found_alike(holder, *MODES)

    typed_around(holder, env, found, lambda: deleted(holder / path))
    what_is_staged_committed(holder, env)
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)
    assert codes_of(found) == ["member-gitlink-unnamed",
                               "gitmodules-path-unnamed"]
    assert (commands(mount_of(found, path))[1]
            == f"git rm --cached -f -- {path}")
    put_back = GONE["deleted"][1]
    assert found[1] == (
        SECTION_SAID.format(path=path, name=path, url=f"url {url}")
        + SECTION_REMEDY.replace("then stage and commit .gitmodules:",
                                 put_back_said("deleted") + THEN_STAGE + ":")
        + lines_of(put_back, *removal(path, "path", "url"), STAGE))


def test_1036_outside_members_the_gitlink_goes_first_then_the_put_back(
        family, holder, offline, tmp_path):
    """#1036 outside `members/`: `git submodule add` at tools/x, not
    committed, then the work tree's `.gitmodules` deleted. The index's file
    gives tools/x its section, so `gitlink-unnamed` rightly says nothing,
    and `gitmodules-path-unnamed` read the work tree's alone: the gate
    passed, and the next commit recorded a gitlink and a section no row can
    name. The section's finding takes the gitlink out of the index first,
    then puts the index's file back, takes every key out and stages the
    file. Only the printed lines typed, then `git commit` of what is staged,
    nothing is left to commit, the checkout stays untracked, the gate passes
    in every mode and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    submodule_added(holder, env, family, TOOLS)
    url = index_url(holder, env, TOOLS)
    gone(holder, env, "deleted")

    found = found_alike(holder, *MODES)

    put_back = GONE["deleted"][1]
    removed = f"\n    git rm --cached -f -- {TOOLS}"
    assert found == [section_first(
        TOOLS, TOOLS, url, FORCED_NO_HEAD,
        put_back_said("deleted") + THEN_STAGE, " -f").replace(
            removed, removed + lines_of(put_back))]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    what_is_staged_committed(holder, env)
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    assert raw(holder, env, "status", "--porcelain").stdout == b"?? tools/\n"
    ends_well(holder, env, family, tmp_path)


@pytest.mark.parametrize("how", GONE)
def test_1036_a_stray_section_comes_out_of_the_file_put_back(
        family, holder, offline, tmp_path, how):
    """#1036 in the case-variant branch: a section named `ghost` giving
    `Members/IRRS`, a second path to MEMBER's directory on macOS and
    Windows, committed, then the work tree's `.gitmodules` deleted or its
    deletion staged. Git reads the index's file, or HEAD's, both of which
    give it, and the gate passed. Its lines put that file back first now,
    then take every key out. Typed in order, staged and committed as it
    says, HEAD's `.gitmodules` gives the two members alone, the gate
    passes in every mode and a plain clone checks both out."""
    env = cloning(offline, tmp_path, family)
    with_section(holder, tmp_path, "ghost", "Members/IRRS",
                 "/nowhere/ghost.git")
    gone(holder, env, how)

    found = found_alike(holder, *MODES)

    assert found == [ghost_out(how, put_back=True)]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    staged_and_committed(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    ends_well(holder, env, family, tmp_path)


def test_1036_one_put_back_serves_two_sections(family, holder, offline,
                                               tmp_path):
    """#1036, two sections no row names, `ghost` giving `Members/IRRS` and
    `members/Old` giving its own name, committed, then the work tree's
    `.gitmodules` deleted. The first finding puts the index's file back
    before its keys, and records that; the second prints its keys alone,
    as with the file on disk: a second put-back, typed after the first
    finding's lines, brought back the section they had just taken out.
    Typed in order, staged and committed, HEAD's `.gitmodules` gives the
    two members alone, the gate passes in every mode and a plain clone
    checks both out."""
    env = cloning(offline, tmp_path, family)
    with_section(holder, tmp_path, "ghost", "Members/IRRS",
                 "/nowhere/ghost.git")
    with_section(holder, tmp_path, "members/Old", "members/Old",
                 "/nowhere/old.git")
    gone(holder, env, "deleted")

    found = found_alike(holder, *MODES)

    assert found == [
        ghost_out("deleted", put_back=True),
        SECTION_SAID.format(path="members/Old", name="members/Old",
                            url="url /nowhere/old.git")
        + SECTION_REMEDY + lines_of(*removal("members/Old", "path", "url"),
                                    STAGE)]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    staged_and_committed(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    ends_well(holder, env, family, tmp_path)


@pytest.mark.parametrize("how", GONE)
def test_1036_a_hand_mount_s_section_under_its_plain_git_rm_prints_nothing(
        family, holder, offline, tmp_path, how):
    """#1036 where the hand mount's plain `git rm` takes the section out: a
    member mounted by hand with its checkout and its section, committed,
    then the work tree's `.gitmodules` deleted or its deletion staged. The
    section, which the file git reads gives, is named now, as with the file
    on disk, and prints no command: the hand mount's text puts that file
    back first and its `git rm` takes the section out of it (#936). Typed in
    order and committed, nothing is left, HEAD's `.gitmodules` gives the two
    members alone, the gate passes in every mode and a plain clone checks
    both out."""
    env = cloning(offline, tmp_path, family)
    path = committed_with_its_checkout(holder, env, family)
    url = index_url(holder, env, path)
    gone(holder, env, how)

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["member-gitlink-unnamed",
                               "gitmodules-path-unnamed"]
    assert commands(mount_of(found, path))[1:3] == [GONE[how][1],
                                                    f"git rm -- {path}"]
    assert found[1] == (
        SECTION_SAID.format(path=path, name=path, url=f"url {url}")
        + SECTION_UNDER_GIT_RM.format(path=path))
    typed_in_order(holder, env, validate(holder, "--no-members"))
    commit_all(holder, env, "Typed in order")
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    ends_well(holder, env, family, tmp_path)


def test_1036_control_a_value_git_dies_on_keeps_what_it_read(
        family, holder, offline, tmp_path):
    """#1036's control: `update = None` committed in IRSS's section, a value
    git dies on, then IRQS's gitlink staged over a directory holding a file,
    its section staged in the index's `.gitmodules` alone, and the work
    tree's file deleted. Git reads the index's file, which gives the value,
    so `gitmodules-path-unnamed` reads nothing from it, as git reads
    nothing, and as with the file on disk. The value's lines put back the
    index's file now, the one git reads, not HEAD's, which dropped IRQS's
    section (#1077), and take the key out. Typed in order, what is on disk
    deleted as the text says, then staged and committed as the value's
    finding says, HEAD holds IRQS's section, as with the file on disk, and
    the next run names it in every mode. Its lines typed, then a plain `git
    commit`, nothing is left, the gate passes in every mode and a plain
    clone checks both out."""
    env = cloning(offline, tmp_path, family)
    value_committed(holder, env, OTHER_ROW)
    path = staged_by_hand(holding_a_file)(holder, env, family)
    data = (holder / ".gitmodules").read_bytes() + (
        f'[submodule "{path}"]\n\tpath = {path}\n'
        f"\turl = https://github.com/InkRouter/{SPARE}.git\n").encode()
    blob = raw(holder, env, "hash-object", "-w", "--stdin",
               stdin=data).stdout.decode("ascii").strip()
    raw(holder, env, "update-index", "--cacheinfo",
        f"100644,{blob},.gitmodules")
    gone(holder, env, "deleted")

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["gitmodules-value-refused",
                               "member-gitlink-unnamed"]
    assert commands(found[0])[0] == GONE["deleted"][1]
    typed_around(holder, env, found, lambda: deleted(holder / path))
    staged_and_committed(holder, env, "Typed in order")
    assert head_paths(holder, env) == {ROW, OTHER_ROW, path}
    assert found_alike(holder, *MODES) == [
        SECTION_SAID.format(
            path=path, name=path,
            url=f"url https://github.com/InkRouter/{SPARE}.git")
        + SECTION_REMEDY + lines_of(*removal(path, "path", "url"), STAGE)]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    what_is_staged_committed(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    ends_well(holder, env, family, tmp_path)
