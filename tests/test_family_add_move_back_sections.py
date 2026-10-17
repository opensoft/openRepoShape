# SPDX-License-Identifier: Apache-2.0
"""`family.py add`'s move back of a member's gitlink held in the wrong case
(#646) and rename back of a `members/` renamed with `git mv` (#685), typed as
printed in each state git leaves them in (#761).

1. (e) `git mv members/IRRS Members/IRRS` moves the section's `path` too. The
   move back put the gitlink back and left the section naming the variant:
   `git submodule update` said `No url found for submodule path
   'members/IRRS'`. Each such section is pointed back now (`git config -f
   .gitmodules submodule.<name>.path <row path>`, `git add -- .gitmodules`),
   in the move's commit where HEAD's section moved too.
2. (g) A file at or under the row's path beside the variant's gitlink kept
   #574's remedy, which took the member's gitlink away. It is set aside
   first now, with `git mv` where it is on disk, then the gitlink moved back.
3. (h) A file or link at `members` itself: each `git update-index` failed
   `appears as both a file and as a directory`. It is set aside first too.
4. The plain `mv` of the variant's directory moved a live checkout out of
   the holder, its `.git` file left pointing nowhere. The `mv` is guarded as
   `validate-family.py` guards it (#681), the text says where the commits
   are and to delete the checkout by hand, before the update, and a checkout
   `add` finds on disk later is never given a plain `mv`.
5. rv685's three: a member whose gitlink's removal is staged beside a staged
   `git mv members Members` is moved back with its section, not passed by; a
   file under a third spelling keeps its own remedy beside the rename back;
   and an entry the sparse rules leave out, its `skip-worktree` bit cleared,
   is given `--sparse`.
6. Codex's two P2s on #828: what is in the way of the move back is the
   member's own to set aside whatever a sparse checkout says of it, with
   `--sparse` where it needs one, and the closing `mv` moves nothing, and
   exits 0, where nothing is at the variant.

States that need two directories differing only in case, or `git mv` into
one, are made on a disk that does not fold case alone; what a folding disk
answers is asked in process (`disk_as`).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git, rmtree
from test_family import NAME, SPARE, family  # noqa: F401
from test_family_add_member_variant import (
    HEAD_ONLY, MOVE_OUT, OTHER_ROW, OTHER_VARIANT, REMOVE, REMOVE_SPARSE, ROW,
    SUBMODULE, VARIANT, VARIANT_SHOWN, dry_run_in_process, guarded,
    in_the_index, moved_back, point_back, record, refused_in_process,
    registered, remedy, typed_as_printed, variant,
)
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant,
)
from test_family_add_spellings_remedies import (
    BOTH, folding_skip, renamed_back, renamed_with_git, two_steps,
)
from test_family_head_lost_gitmodules import assert_passes_in_every_mode
from test_family_members_case_variants import (
    DIR_VARIANT, NEEDS_GIT_2_34, NEEDS_GIT_2_38, added, disk_as, disk_folds,
    git_version, index_part, refused_untouched, remedy_of,
)
from test_family_refuse_up_front import needs_check_rules

#: Both sections pointed back.
SECTIONS = (ROW, OTHER_ROW)
#: The two gitlinks under `Members/` taken out in one line, with `-f` where
#: a staged one has its checkout on disk.
REMOVE_BOTH = (f"git rm -r --cached --ignore-unmatch -- {VARIANT} "
               f"{OTHER_VARIANT}")
REMOVE_BOTH_FORCED = REMOVE_BOTH.replace("--cached", "--cached -f")
REMOVE_FORCED = REMOVE.replace("--cached", "--cached -f")
POINTED = [point_back(), point_back(OTHER_ROW), "git add -- .gitmodules"]


def mount_moved(root: Path, committed: bool = True) -> str:
    """`git mv members/IRRS Members/IRRS`, which moves the checkout, the
    gitlink and the section's `path`, and its commit where `committed`.
    Returns the commit the gitlink records."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()
    (root / "Members").mkdir(exist_ok=True)
    git("mv", "members/IRRS", VARIANT, cwd=root)
    if committed:
        git("commit", "-qm", "git mv members/IRRS Members/IRRS", cwd=root)
    return commit


def work_there(root: Path, name: str = VARIANT) -> str:
    """A commit of its own made in the checkout at `name`, and a file not
    committed, written as BYTES. Returns the commit."""
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--allow-empty", "-m", "Work there", cwd=root / name)
    (root / name / "WIP.txt").write_bytes(b"not committed\n")
    return git("rev-parse", "HEAD", cwd=root / name).stdout.strip()


def deleted_by_hand(*names: str):
    """What the text says of each checkout at `names`, done by hand, before
    the update: `git -C <name> status` first names the file not committed
    there (the update would point the store at the row's path, and it then
    names none), then the checkout is deleted."""
    def by_hand(root: Path) -> None:
        for name in names:
            if not (root / name / ".git").is_file():
                continue
            status = git("-C", name, "status", "--porcelain", cwd=root)
            assert "?? WIP.txt" in status.stdout.splitlines(), status.stdout
            rmtree(root / name)
    return by_hand


def kept_in_the_store(root: Path, commit: str, row: str = ROW) -> None:
    """`commit` is in the member's store, `.git/modules/<row>`, the
    checkout it was made in deleted."""
    store = root / ".git" / "modules" / row
    kept = subprocess.run(["git", f"--git-dir={store}", "cat-file", "-e",
                           commit], capture_output=True, check=False)
    assert kept.returncode == 0, kept.stderr


def gate_then_add(offline, root: Path, remotes: Path) -> None:
    """The holder's gate in every mode, the same `add`, the gate again."""
    assert_passes_in_every_mode(root, 2)
    added(offline, root, remotes)
    assert_passes_in_every_mode(root, 3)


# --- 1. (e) a section git mv moved -------------------------------------------

@pytest.mark.parametrize("committed", [True, False],
                         ids=["committed", "staged"])
def test_a_mount_moved_with_git_mv_is_moved_back_with_its_section(
        family, holder, offline, tmp_path, committed):
    """(e) `git mv members/IRRS Members/IRRS`, the member's commit and a
    file not committed in its checkout there. Typed as printed: the gitlink
    and the section are back at `members/IRRS` (HEAD's `.gitmodules` byte
    for byte the holder's), the commit only where HEAD's section moved
    (none after a staged move, where `git commit` would fail), the removal
    with `-f` where the move is staged, which `git rm --cached` refused
    beside that checkout's work, the guarded `mv` keeps the checkout, `git
    -C Members/IRRS status` names the file not committed, the checkout is
    deleted by hand, and `git submodule update --init` checks the member
    out at its row's path with the commit still in its store. The gate
    passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commit = mount_moved(holder, committed)
    work = work_there(holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, commit=committed,
                               sections=(ROW,), forced=not committed)
    said = refused_untouched(offline, holder, family["remotes"], "--dry-run")
    assert said == (in_the_index(VARIANT_SHOWN), remedy_of(move, *closing))
    assert typed_as_printed(holder, said[1], deleted_by_hand(VARIANT)) == [
        REMOVE if committed else REMOVE_FORCED, record(commit), point_back(),
        "git add -- .gitmodules", *(["git commit"] if committed else []),
        MOVE_OUT, SUBMODULE]
    registered(holder, family["root"], commit)
    assert (holder / ROW / "project.yaml").is_file()
    kept_in_the_store(holder, work)
    gate_then_add(offline, holder, family["remotes"])


def test_a_fresh_clone_of_it_is_moved_back_with_its_section(
        family, holder, offline, tmp_path):
    """(e), committed and pushed, and a fresh recursive clone: its section
    gives `Members/IRRS`, so the member is checked out there. The same
    text; typed as printed, with that checkout deleted by hand, the clone's
    gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commit = mount_moved(holder)
    remote = family["remotes"] / f"{NAME}.git"
    branch = "w761/mount-moved"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=holder)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch)
    assert (clone / VARIANT / ".git").is_file(), "premise: checked out there"
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,))
    said = refused_untouched(offline, clone, family["remotes"], "--dry-run")
    assert said == (in_the_index(VARIANT_SHOWN), remedy_of(move, *closing))
    assert typed_as_printed(clone, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        REMOVE, record(commit), *POINTED[::2], "git commit", MOVE_OUT,
        SUBMODULE]
    registered(clone, family["root"], commit)
    gate_then_add(offline, clone, family["remotes"])


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
def test_every_disk_points_the_section_back(family, holder, family_module,
                                            offline, monkeypatch, capsys,
                                            tmp_path, folding):
    """(e) asked in process of a disk that folds case and of one that does
    not: one text, the section line on both."""
    folding_skip(tmp_path)
    commit = mount_moved(holder)
    disk_as(monkeypatch, holder, folding)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,))
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        in_the_index(VARIANT_SHOWN), remedy_of(move, *closing))


def test_a_sparse_gitmodules_is_named_first_where_a_section_is_pointed_back(
        family, holder, offline, tmp_path):
    """(e), and a `.gitmodules` a sparse checkout marks: `git config -f`
    would write a new file of the one line, which `git add` refuses, so
    `gitmodules-sparse` names it first, with the holder as it was."""
    folding_skip(tmp_path)
    mount_moved(holder)
    git("update-index", "--skip-worktree", "--", ".gitmodules", cwd=holder)
    first, _ = refused_untouched(offline, holder, family["remotes"])
    assert first.startswith("REFUSED gitmodules-sparse: "), first


# --- 2. (g) and 3. (h): what is in the way, set aside first ------------------

def set_aside(entries: list[str], kinds: dict, renamed=(), out=(),
              sparse=(), out_sparse: bool = False) -> str:
    """The part of the remedy that sets `entries` aside: `renamed` with `git
    mv`, `sparse` with `git mv --sparse`, `out` taken out of the index, with
    `--sparse` where `out_sparse` (Codex's P2 on #828)."""
    how = []
    if renamed:
        how.append("rename each that is on disk as the index holds it with "
                   "`git mv` (" + " and ".join(f"`git mv -- {name} <new name>`"
                                               for name in renamed) + ")")
    if sparse:
        how.append("rename each that the sparse checkout leaves out with `git "
                   f"mv --sparse`, {NEEDS_GIT_2_38} ("
                   + " and ".join(f"`git mv --sparse -- {name} <new name>`"
                                  for name in sparse) + ")")
    if out:
        how.append("take each that is not on disk so out of the index, which "
                   "touches no file (`git rm -r --cached"
                   f"{' --sparse' if out_sparse else ''} -- {' '.join(out)}`"
                   + (f", {NEEDS_GIT_2_34}" if out_sparse else "") + ")")
    named = ", ".join(f"`{name}` ({kinds.get(name, 'a file')})"
                      for name in entries)
    return ("set aside first what the index holds in the way of the move of "
            f"a member's gitlink below, {named}, since git's update-index "
            "replaces a file at the path it records without a word and fails "
            "beside one under it or at members itself, and taking the "
            "gitlink out instead un-registers the member: "
            + " and ".join(how))


def file_committed(root: Path, name: str) -> bytes:
    """`name` written as BYTES and committed. Returns the bytes."""
    data = b"our own notes\n"
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(data)
    git("add", "--", name, cwd=root)
    git("commit", "-qm", f"A file at {name}", cwd=root)
    return data


@pytest.mark.parametrize("entry", [ROW, f"{ROW}/notes"],
                         ids=["at the row's path", "under it"])
def test_a_file_at_or_under_the_rows_path_is_set_aside_first(
        family, holder, offline, tmp_path, entry):
    """(g) `git mv members/IRRS Members/IRRS`, then a file committed at the
    row's path or under it. #574's `git mv -- Members/IRRS <new name>` took
    the member away from its row. Typed as printed: the file renamed with
    `git mv`, then the move back and the section in the same commit, the
    checkout deleted by hand, the update; the file's bytes are at its new
    name in HEAD, the member is where its row says, the gate passes and the
    same `add` goes through."""
    folding_skip(tmp_path)
    commit = mount_moved(holder)
    data = file_committed(holder, entry)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,))
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN),
                    remedy_of(set_aside([entry], {}, renamed=[entry]), move,
                              *closing))
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        f"git mv -- {entry} renamed-1", REMOVE, record(commit), *POINTED[::2],
        "git commit", MOVE_OUT, SUBMODULE]
    assert git("show", "HEAD:renamed-1", cwd=holder).stdout.encode() == data
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_file_where_the_disk_holds_the_checkout_is_taken_out_first(
        family, holder, offline):
    """(g) #646's state, the member's checkout still at `members/IRRS`, and
    a file the index holds there, which `git mv` cannot take: it is taken
    out of the index, which touches no file, then the gitlink is moved
    back over the checkout."""
    commit = variant(holder)
    plant(holder, "100644", ROW)
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN),
                    remedy_of(set_aside([ROW], {}, out=[ROW]), move,
                              *closing))
    assert typed_as_printed(holder, said[1]) == [
        f"git rm -r --cached -- {ROW}", REMOVE, record(commit), "git commit",
        MOVE_OUT]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def members_file_deleted(root: Path) -> tuple:
    """A file `members` committed, then deleted from disk and not staged:
    taken out of the index."""
    file_committed(root, "members")
    (root / "members").unlink()
    return set_aside(["members"], {}, out=["members"]), \
        "git rm -r --cached -- members"


def members_a_link(root: Path) -> tuple:
    """A link `members -> Members` committed: renamed with `git mv`."""
    if os.name == "nt":
        pytest.skip("a symlink needs a privilege Windows runners do not grant")
    os.symlink("Members", root / "members", target_is_directory=True)
    git("add", "--", "members", cwd=root)
    git("commit", "-qm", "A link members -> Members", cwd=root)
    return (set_aside(["members"], {"members": "a symlink"},
                      renamed=["members"]), "git mv -- members renamed-1")


def members_file_marked(root: Path) -> tuple:
    """A file `members` committed, which a sparse checkout keeps off disk
    (`skip-worktree`): it was left where it was, so each `git update-index`
    still failed beside it. Renamed with `git mv --sparse`, which keeps what
    it holds, as the index's own rule names such an entry (Codex's P2 1 on
    #828)."""
    if git_version() < (2, 38):
        pytest.skip("`git mv --sparse` of one entry kept off disk needs git "
                    "2.38 or later")
    file_committed(root, "members")
    git("update-index", "--skip-worktree", "--", "members", cwd=root)
    (root / "members").unlink()
    return (set_aside(["members"], {}, sparse=["members"]),
            "git mv --sparse -- members renamed-1")


@pytest.mark.parametrize("make", [members_file_deleted, members_a_link,
                                  members_file_marked],
                         ids=["a file deleted from disk", "a link",
                              "a file a sparse checkout keeps off disk"])
def test_an_entry_at_members_itself_is_set_aside_first(family, holder,
                                                       offline, tmp_path,
                                                       make):
    """(h) `git mv members Members`, committed, and the index holds a file
    or a link at `members`, one a sparse checkout keeps off disk too: each
    `git update-index` failed `appears as both a file and as a directory`,
    exit 128. Typed as printed: the entry set aside, both gitlinks and
    sections moved back in one commit, both checkouts deleted by hand, the
    update; the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    aside, typed_first = make(holder)
    move, closing = moved_back({ROW: ([VARIANT], commits[ROW]),
                                OTHER_ROW: ([OTHER_VARIANT],
                                            commits[OTHER_ROW])},
                               sections=SECTIONS)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (BOTH, remedy_of(aside, move, *closing))
    assert typed_as_printed(holder, said[1], lambda root: [
        rmtree(root / name) for name in (VARIANT, OTHER_VARIANT)]) == [
        typed_first, REMOVE_BOTH, record(commits[ROW]),
        record(commits[OTHER_ROW], OTHER_ROW), *POINTED, "git commit",
        MOVE_OUT, guarded(OTHER_VARIANT, OTHER_ROW), SUBMODULE]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


# --- 4. a live checkout is never moved by a plain mv ------------------------

def test_a_checkout_left_at_the_variant_is_named_to_delete_by_hand(
        family, holder, offline, tmp_path):
    """(e) typed as printed with the hand step skipped: the update then
    points the member's store at its row's path, and `git -C Members/IRRS
    status` names nothing, though a file not committed is there (why the
    text puts the hand step first). The next `add` names the checkout to
    delete by hand, with no `mv`; deleted, the commit is still in the store,
    and the gate and `add` pass."""
    folding_skip(tmp_path)
    commit = mount_moved(holder)
    work = work_there(holder)
    said = refused_untouched(offline, holder, family["remotes"])
    typed_as_printed(holder, said[1])
    assert (holder / VARIANT / "WIP.txt").is_file()
    assert git("-C", VARIANT, "status", "--porcelain",
               cwd=holder).stdout == ""
    first, again = refused_untouched(offline, holder, family["remotes"])
    assert first == DIR_VARIANT + (f"on disk and untracked: `{VARIANT}` (a "
                                   "directory)")
    assert again == remedy_of(
        f"delete by hand each checkout on disk and untracked, `{VARIANT}`, "
        "once nothing only it holds is needed, rather than move it: its .git "
        "file names its store by a path relative to it, which a move would "
        "leave pointing nowhere, and its commits are kept in that store, so "
        "only what is not committed is in it alone")
    assert re.findall(r"`mv ", again) == []
    assert typed_as_printed(holder, again,
                            lambda root: rmtree(root / VARIANT)) == []
    registered(holder, family["root"], commit)
    kept_in_the_store(holder, work)
    gate_then_add(offline, holder, family["remotes"])


# --- 5. rv685's three --------------------------------------------------------

@pytest.mark.parametrize("committed", [False, True],
                         ids=["staged", "committed"])
def test_a_members_removal_staged_beside_the_rename_is_moved_back(
        family, holder, offline, tmp_path, committed):
    """rv685's candidate 1: `git mv members Members`, then `git rm --cached
    Members/IRSS`. Staged, HEAD records `members/IRSS` and the index holds
    it nowhere: nothing named it, the rename back left its section at
    `Members/IRSS`, `add` committed that, and the gate refused. Now it is
    named, put back at HEAD's commit beside IRRS's move, with both sections
    and no commit, which nothing would be left to make. Committed, HEAD
    holds `Members/IRSS`: the move back from HEAD, with both sections and
    the commit. Typed as printed, both members are where their rows say,
    the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, committed)
    git("rm", "-q", "--cached", "--", OTHER_VARIANT, cwd=holder)
    rows = {ROW: ([VARIANT], commits[ROW])}
    staged = {}
    if committed:
        rows[OTHER_ROW] = ([OTHER_VARIANT], commits[OTHER_ROW])
        where = "in HEAD and no longer in the index"
    else:
        staged = {OTHER_ROW: (OTHER_VARIANT, commits[OTHER_ROW])}
        where = "in .gitmodules, its gitlink's removal staged"
    move, closing = moved_back(rows, commit=committed, sections=SECTIONS,
                               staged=staged, forced=not committed)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN)
                    + f"; {where}: `{OTHER_VARIANT}` (a submodule)",
                    remedy_of(move, *closing))
    assert typed_as_printed(holder, said[1], lambda root: [
        rmtree(root / name) for name in (VARIANT, OTHER_VARIANT)]) == [
        REMOVE_BOTH if committed else REMOVE_BOTH_FORCED,
        record(commits[ROW]), record(commits[OTHER_ROW], OTHER_ROW),
        *POINTED, *(["git commit"] if committed else []), MOVE_OUT,
        guarded(OTHER_VARIANT, OTHER_ROW), SUBMODULE]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


def test_a_third_spelling_keeps_its_own_remedy_beside_the_rename_back(
        family, holder, offline, tmp_path):
    """rv685's NIT 5: `git mv members Members`, committed, and a file
    committed at `MEMBERS/notes`. The rename back was withheld for the move
    back, whose section gap (e) then left. Now the file keeps its own
    remedy, run first, and the rename back follows. Typed as printed, both
    members are where their rows say, the gate passes and the same `add`
    goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder, True)
    file_committed(holder, "MEMBERS/notes")
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + "in the index: `MEMBERS/notes` (a file), "
                    f"{VARIANT_SHOWN}, `{OTHER_VARIANT}` (a submodule)",
                    remedy_of(index_part(rename=["MEMBERS/notes"],
                                         commit="the rename"),
                              renamed_back(True)))
    assert typed_as_printed(holder, said[1]) == [
        "git mv -- MEMBERS/notes renamed-1", "git commit", *two_steps(),
        "git commit"]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
def test_every_disk_renames_back_beside_a_third_spelling(
        family, holder, family_module, offline, monkeypatch, capsys,
        tmp_path, folding):
    """The same, the third spelling in the index alone, as a disk that folds
    case holds it, where the three spellings are one directory and
    `MEMBERS` is not listed: taken out of the index, which touches no file,
    then the rename back, on both disks."""
    folding_skip(tmp_path)
    renamed_with_git(holder, True)
    plant(holder, "100644", "MEMBERS/notes")
    disk_as(monkeypatch, holder, folding)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        DIR_VARIANT + "in the index: `MEMBERS/notes` (a file), "
        f"{VARIANT_SHOWN}, `{OTHER_VARIANT}` (a submodule)",
        remedy_of(index_part(unstage=["MEMBERS/notes"]), renamed_back(True)))


def sparse_cone(root: Path) -> None:
    """A cone-mode sparse checkout keeping `members/` and every directory
    the gate reads, which leaves out `Members/`."""
    if git_version() < (2, 38):
        pytest.skip("`git mv --sparse` of one entry needs git 2.38 or later")
    git("sparse-checkout", "init", "--cone", cwd=root)
    git("sparse-checkout", "set", "members", "contracts", "scripts",
        ".github", cwd=root)


def bit_cleared(root: Path, name: str, on_disk: bool, directory: bool) -> None:
    """`name`'s `skip-worktree` bit cleared, and it put back on disk, a
    directory or a file written as BYTES, where `on_disk`."""
    if on_disk and directory:
        (root / name).mkdir(parents=True, exist_ok=True)
    elif on_disk:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_bytes(b"our own notes\n")
    git("update-index", "--no-skip-worktree", "--", name, cwd=root)
    assert git("ls-files", "-t", "--", name, cwd=root).stdout.startswith("H ")


def readme_on_disk(root: Path) -> tuple:
    """`Members/README` on disk: plain `git mv` refuses it."""
    file_committed(root, "Members/README")
    sparse_cone(root)
    bit_cleared(root, "Members/README", True, False)
    return (DIR_VARIANT + "in the index: `Members/README` (a file)",
            remedy_of(index_part(sparse=["Members/README"],
                                 commit="the rename")),
            ["git mv --sparse -- Members/README renamed-1", "git commit"])


def readme_off_disk(root: Path) -> tuple:
    """`Members/README` off disk: plain `git rm --cached` refuses it."""
    file_committed(root, "Members/README")
    sparse_cone(root)
    bit_cleared(root, "Members/README", False, False)
    return (DIR_VARIANT + "in the index: `Members/README` (a file)",
            remedy_of("take what has nothing on disk in that spelling out of "
                      "the index, which touches no file (`git rm -r --cached "
                      "--sparse -- Members/README`, which needs git 2.34 or "
                      "later), and commit the removal"),
            ["git rm -r --cached --sparse -- Members/README", "git commit"])


def own_gitlink_on_disk(root: Path) -> tuple:
    """#646's state, `Members/IRRS` an empty directory on disk: plain `git
    rm --cached --ignore-unmatch` passes it over, exit 0, and the move left
    two gitlinks."""
    commit = variant(root)
    sparse_cone(root)
    bit_cleared(root, VARIANT, True, True)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sparse=True)
    return (in_the_index(VARIANT_SHOWN), remedy_of(move, *closing),
            [REMOVE_SPARSE, record(commit), "git commit", MOVE_OUT])


SPARSE = {
    "a file on disk": readme_on_disk,
    "a file off disk": readme_off_disk,
    "a member's own gitlink on disk": own_gitlink_on_disk,
}


@needs_check_rules
@pytest.mark.parametrize("state", list(SPARSE))
def test_an_entry_the_sparse_rules_leave_out_takes_sparse_whatever_its_bit(
        family, holder, offline, state):
    """rv685's candidate 2: a cone-mode sparse checkout leaves `Members/`
    out, and an entry there has its `skip-worktree` bit cleared. Plain `git
    mv` (on disk) and `git rm --cached` (off disk) refuse it, exit 1, `exist
    outside of your sparse-checkout definition`, and the move back's removal
    passes it over. Each is given `--sparse` and the git it needs; typed as
    printed, the gate passes and the same `add` goes through."""
    first, said, typed = SPARSE[state](holder)
    assert refused_untouched(offline, holder, family["remotes"]) == (first,
                                                                     said)
    assert typed_as_printed(holder, said) == typed
    gate_then_add(offline, holder, family["remotes"])


@needs_check_rules
def test_a_gitlink_the_sparse_rules_leave_out_is_renamed_with_sparse(
        family, holder, offline):
    """rv685's candidate 2, on a gitlink, as the issue asks (`Members/X`, on
    disk as a directory, its bit cleared): plain `git mv` would take it, and
    `git mv --sparse` takes it too, so the one rule holds; typed as printed,
    the same `add` goes through."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=holder).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},Members/X",
        cwd=holder)
    git("commit", "-qm", "A gitlink Members/X", cwd=holder)
    sparse_cone(holder)
    bit_cleared(holder, "Members/X", True, True)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + "in the index: `Members/X` (a submodule)",
                    remedy_of(index_part(sparse=["Members/X"],
                                         commit="the rename")))
    assert typed_as_printed(holder, said[1]) == [
        "git mv --sparse -- Members/X renamed-1", "git commit"]
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr


@needs_check_rules
def test_the_rename_back_is_withheld_where_the_rules_leave_an_entry_out(
        holder, family_module, tmp_path):
    """The rename back's first `git mv` refuses a directory holding an entry
    the sparse rules leave out, its bit cleared (exit 1, measured), so the
    move back is printed, its removal with `--sparse`."""
    folding_skip(tmp_path)
    renamed_with_git(holder, True)
    sparse_cone(holder)
    for name in (VARIANT, OTHER_VARIANT):
        bit_cleared(holder, name, True, True)
    _, said = refused_in_process(family_module, holder)
    assert "git mv -- Members members.renaming" not in said
    assert f"`git rm -r --cached --sparse --ignore-unmatch -- {VARIANT} " \
           f"{OTHER_VARIANT}`, {NEEDS_GIT_2_34}, " in said


# --- what each rule turns on -------------------------------------------------

def test_a_section_head_moved_is_a_change_to_commit(holder, family_module,
                                                    tmp_path):
    """HEAD records the gitlink at its row's path and its section at
    `Members/IRRS`, as #646's move back left it typed after a committed
    `git mv` of the mount, and the index stages the gitlink at the variant
    again: the move alone leaves nothing to commit, but pointing the
    section back does, so the commit is printed."""
    folding_skip(tmp_path)
    commit = mount_moved(holder)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=holder)
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{ROW}",
        cwd=holder)
    git("commit", "-qm", "#646's move back, its section left", cwd=holder)
    git("rm", "-q", "--cached", "--", ROW, cwd=holder)
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{VARIANT}",
        cwd=holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,),
                               forced=True)
    assert refused_in_process(family_module, holder)[1] == remedy_of(
        move, *closing)


def test_what_is_set_aside_is_committed_with_the_move(family, holder,
                                                      offline, tmp_path):
    """(g) staged: `git mv members/IRRS Members/IRRS` and a new file at the
    row's path, neither committed. The move back alone would leave nothing
    to commit, but the file renamed aside would be left staged, so the
    commit is printed; typed as printed, HEAD holds the file at its new
    name, the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commit = mount_moved(holder, committed=False)
    (holder / ROW).write_bytes(b"our own notes\n")
    git("add", "--", ROW, cwd=holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,),
                               forced=True)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said[1] == remedy_of(set_aside([ROW], {}, renamed=[ROW]), move,
                                *closing)
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        f"git mv -- {ROW} renamed-1", REMOVE_FORCED, record(commit),
        *POINTED[::2], "git commit", MOVE_OUT, SUBMODULE]
    assert git("show", "HEAD:renamed-1", cwd=holder).stdout == (
        "our own notes\n")
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_what_a_sparse_checkout_keeps_off_disk_is_committed_with_the_move(
        family, holder, offline, tmp_path):
    """The same, the new file marked `skip-worktree` and kept off disk, as a
    sparse checkout keeps it: renamed aside with `git mv --sparse`, which
    leaves a change to commit though nothing is on disk, so the commit is
    printed (Codex's P2 1 on #828). Typed as printed, HEAD holds the file at
    its new name, the gate passes and the same `add` goes through."""
    if git_version() < (2, 38):
        pytest.skip("`git mv --sparse` of one entry kept off disk needs git "
                    "2.38 or later")
    folding_skip(tmp_path)
    commit = mount_moved(holder, committed=False)
    (holder / ROW).write_bytes(b"our own notes\n")
    git("add", "--", ROW, cwd=holder)
    git("update-index", "--skip-worktree", "--", ROW, cwd=holder)
    (holder / ROW).unlink()
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,),
                               forced=True)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said[1] == remedy_of(set_aside([ROW], {}, sparse=[ROW]), move,
                                *closing)
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        f"git mv --sparse -- {ROW} renamed-1", REMOVE_FORCED, record(commit),
        *POINTED[::2], "git commit", MOVE_OUT, SUBMODULE]
    assert git("show", "HEAD:renamed-1", cwd=holder).stdout == (
        "our own notes\n")
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_removal_where_head_records_the_gitlink_leaves_no_commit(
        family, holder, offline, tmp_path):
    """The same, the new file deleted from disk and not marked: taken out of
    the index. HEAD records the member's gitlink at that path, which the
    move puts back, so the removal leaves nothing to commit, and no commit
    is printed: one was, and `git commit` failed with nothing to commit
    (found in #828's fix round for Codex's P2s). Typed as printed, the
    member is where its row says, the gate passes and the same `add` goes
    through."""
    folding_skip(tmp_path)
    commit = mount_moved(holder, committed=False)
    (holder / ROW).write_bytes(b"our own notes\n")
    git("add", "--", ROW, cwd=holder)
    (holder / ROW).unlink()
    move, closing = moved_back({ROW: ([VARIANT], commit)}, commit=False,
                               sections=(ROW,), forced=True)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said[1] == remedy_of(set_aside([ROW], {}, out=[ROW]), move,
                                *closing)
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        f"git rm -r --cached -- {ROW}", REMOVE_FORCED, record(commit),
        *POINTED[::2], MOVE_OUT, SUBMODULE]
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_both_removals_staged_with_no_gitmodules_on_disk(family, holder,
                                                         offline, tmp_path):
    """A staged `git mv members Members`, both gitlinks then taken out of the
    index, and `.gitmodules` deleted from the work tree: nothing the index
    holds is a gitlink, yet both sections are pointed back, so the copy the
    index holds is put back first, where `git config -f` would otherwise
    write a new file of one line. Typed as printed, both members are where
    their rows say, the gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    commits = renamed_with_git(holder)
    git("rm", "-q", "--cached", "--", VARIANT, OTHER_VARIANT, cwd=holder)
    (holder / ".gitmodules").unlink()
    move, closing = moved_back({}, commit=False, sections=SECTIONS, staged={
        ROW: (VARIANT, commits[ROW]),
        OTHER_ROW: (OTHER_VARIANT, commits[OTHER_ROW])})
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (
        DIR_VARIANT + "in .gitmodules, its gitlink's removal staged: "
        f"{VARIANT_SHOWN}, `{OTHER_VARIANT}` (a submodule)",
        remedy_of("put back the copy of .gitmodules the index holds, which "
                  "the work tree lacks, since git edits each member's section "
                  "there (`git checkout -- .gitmodules`)", move, *closing))
    assert typed_as_printed(holder, said[1], lambda root: [
        rmtree(root / name) for name in (VARIANT, OTHER_VARIANT)]) == [
        "git checkout -- .gitmodules", REMOVE_BOTH, record(commits[ROW]),
        record(commits[OTHER_ROW], OTHER_ROW), *POINTED, MOVE_OUT,
        guarded(OTHER_VARIANT, OTHER_ROW), SUBMODULE]
    for row, commit in commits.items():
        registered(holder, family["root"], commit, row)
    gate_then_add(offline, holder, family["remotes"])


def test_a_checkout_under_an_index_entry_is_the_indexs_to_name(
        holder, family_module):
    """A checkout on disk at `Members/X` (a `.git` file) under which the
    index holds `Members/X/notes`: the index's remedy names that path, and
    the checkout is not named a second time from the disk."""
    (holder / "Members" / "X").mkdir(parents=True)
    (holder / "Members" / "X" / ".git").write_bytes(
        b"gitdir: ../../.git/modules/x\n")
    plant(holder, "100644", "Members/X/notes")
    found = family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder), frozenset())
    assert [(spelled.where, spelled.target) for spelled in found] == [
        ("in the index", "Members/X")]


# --- 6. Codex's two P2s on #828 ----------------------------------------------

#: A file committed under the row's path, in the way of the move back.
NOTES = f"{ROW}/notes"


def notes_marked(on_disk: bool):
    """`members/IRRS/notes` marked `skip-worktree`, as a sparse checkout
    marks it, and kept off disk unless `on_disk`."""
    def make(root: Path) -> None:
        if not on_disk and git_version() < (2, 38):
            pytest.skip("`git mv --sparse` of one entry kept off disk needs "
                        "git 2.38 or later")
        git("update-index", "--skip-worktree", "--", NOTES, cwd=root)
        if not on_disk:
            (root / NOTES).unlink()
    return make


def notes_left_out(on_disk: bool):
    """Non-cone sparse rules that leave out `members/IRRS/notes` alone, its
    `skip-worktree` bit cleared, on disk where `on_disk`."""
    def make(root: Path) -> None:
        git("sparse-checkout", "set", "--no-cone", "/*", f"!/{NOTES}",
            cwd=root)
        bit_cleared(root, NOTES, on_disk, False)
    return make


#: `{state: (how it is made, the set-aside part's arguments, the line typed
#: for it)}`.
SPARSE_ASIDE = {
    "marked, on disk": (notes_marked(True), {"renamed": [NOTES]},
                        f"git mv -- {NOTES} renamed-1"),
    "marked, off disk": (notes_marked(False), {"sparse": [NOTES]},
                         f"git mv --sparse -- {NOTES} renamed-1"),
    "left out by the rules, on disk": (
        notes_left_out(True), {"sparse": [NOTES]},
        f"git mv --sparse -- {NOTES} renamed-1"),
    "left out by the rules, off disk": (
        notes_left_out(False), {"out": [NOTES], "out_sparse": True},
        f"git rm -r --cached --sparse -- {NOTES}"),
}


@pytest.mark.parametrize("state", [
    pytest.param(state, marks=needs_check_rules) if "rules" in state
    else state for state in SPARSE_ASIDE])
def test_a_blocker_a_sparse_checkout_marks_or_leaves_out_is_set_aside_too(
        family, holder, offline, tmp_path, state):
    """Codex's P2 1 on #828: `git mv members/IRRS Members/IRRS`, committed,
    and a file committed under the row's path, which a sparse checkout
    marks or its rules leave out. Such a row was dropped from the rows to
    set aside before the member's own gitlink was asked for, so
    `Members/IRRS` kept #574's `git mv -- Members/IRRS <new name>`, which
    takes the member's gitlink and section away from its row. Now the
    gitlink is moved back, and the file is set aside as the index's own
    rule names it: plain `git mv` where it is marked and on disk, `git mv
    --sparse` where it is marked and off disk or left out and on disk, and
    `git rm -r --cached --sparse` where it is left out and off disk; plain
    `git mv` and `git rm --cached` refuse each of the last three (measured
    on git 2.43 and 2.47.1). Typed as printed, the file's bytes are at its
    new name where it is renamed, the member is where its row says, the
    gate passes and the same `add` goes through."""
    folding_skip(tmp_path)
    make, how, typed_first = SPARSE_ASIDE[state]
    commit = mount_moved(holder)
    data = file_committed(holder, NOTES)
    make(holder)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sections=(ROW,))
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN),
                    remedy_of(set_aside([NOTES], {}, **how), move, *closing))
    assert typed_as_printed(holder, said[1],
                            lambda root: rmtree(root / VARIANT)) == [
        typed_first, REMOVE, record(commit), *POINTED[::2], "git commit",
        MOVE_OUT, SUBMODULE]
    if typed_first.startswith("git mv"):
        assert git("show", "HEAD:renamed-1",
                   cwd=holder).stdout.encode() == data
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])


def test_a_link_pointing_nowhere_at_the_variant_is_still_moved_out(
        family, holder, offline, tmp_path):
    """Codex's P2 2 on #828: the closing `mv` failed, exit 1, where nothing
    is at the variant, so its guard now begins `[ ! -e <variant> ] && [ !
    -L <variant> ]`, and every typing of a state with nothing there types
    it, as printed, moving nothing. The second test keeps what the guard did
    before for a link there pointing nowhere, which `-e` takes for nothing:
    #646's state with the removal staged, so HEAD alone holds the variant,
    and a link `Members/IRRS -> nowhere`. (With the variant's gitlink still
    in the index, git 2.45.1 and later refuse the link itself: `git status`
    says `expected submodule path 'Members/IRRS' not to be a symbolic
    link`, measured on git 2.47.1.) Typed as printed, the link is moved out
    of the holder, the member is where its row says, the gate passes and
    the same `add` goes through."""
    if os.name == "nt":
        pytest.skip("a symlink needs a privilege Windows runners do not grant")
    if disk_folds(tmp_path):
        pytest.skip("a link at the variant beside the row's directory needs a "
                    "disk that does not fold case")
    commit = variant(holder)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=holder)
    (holder / "Members").mkdir()
    os.symlink("nowhere", holder / VARIANT)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + f"{HEAD_ONLY}: {VARIANT_SHOWN}",
                    remedy(commit))
    assert typed_as_printed(holder, said[1]) == [
        REMOVE, record(commit), "git commit", MOVE_OUT]
    assert not os.path.lexists(holder / VARIANT)
    assert os.readlink(holder.parent / "Members-IRRS") == "nowhere"
    registered(holder, family["root"], commit)
    gate_then_add(offline, holder, family["remotes"])
