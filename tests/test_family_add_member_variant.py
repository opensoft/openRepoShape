# SPDX-License-Identifier: Apache-2.0
"""`family.py add`'s refusal of a member's own gitlink held in the wrong case
moves it back to its row's path, and never takes it away from the row (#646).

THE STATE: a member's ONLY gitlink is at `Members/IRRS`, while its row and
`.gitmodules` say `members/IRRS`, as a holder committed in #363's state
holds it. `add` of ANOTHER member is refused, as #574 rules
(`family-members-dir-variant`), and its remedy used to be #574's for any
path under another spelling of `members/`: `git rm -r --cached -- Members/IRRS`
where nothing is on disk in that spelling, `git mv -- Members/IRRS <new name>`
where something is, and `git commit` where only HEAD holds it. Each one,
typed as printed, took the member's gitlink away from its row, and the
holder's validator then said `member-gitlink-absent`.

THE REMEDY NOW is the index-only move `validate-family.py` gives the same
state (#611), which Brett Heap accepted on 2026-10-16 ("Accept; merge #639
after #637") in place of the "committed `git mv`" of his "Refuse on every
disk" ruling, since `git mv` to the row's path fails or misplaces the
gitlink: `git rm -r --cached --ignore-unmatch` of the variant, `git
update-index --add --cacheinfo 160000,<commit>,members/IRRS` at the commit
the variant records, and a commit. Then, as the validator says, `git
submodule update --init --recursive` where nothing is checked out at the
row's path, an `mv` out of the holder of what a case-sensitive disk leaves at
the variant, and nothing to do on macOS and Windows, where that directory is
the row's own.

EVERY PRINTED COMMAND IS TYPED AS PRINTED (`typed_as_printed`), in each
layout rv611b's review of #639 used, and the holder's gate then passes, the
member is still where its row says, and the same `add` goes through. The
text is the same on every disk: asked in process of an emulated folding disk
and of a Linux one (`disk_as`), it does not change. Layouts that need two
directories differing only in case are made on a disk that does not fold
case alone.
"""

from __future__ import annotations

import os
import re
import shlex
import tempfile
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git, rmtree
from test_family import NAME, ORG, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant, refusal,
)
from test_family_members_case_variants import (
    DIR_VARIANT, MOUNT, MOVE_BACK, added, commit_first, disk_as, disk_folds,
    index_part, refused_untouched, remedy_of, renamed_members,
)

#: The member whose gitlink is moved into the wrong case, its row's path,
#: the variant, and the other member.
MEMBER = "IRRS"
ROW = f"members/{MEMBER}"
VARIANT = f"Members/{MEMBER}"
OTHER_ROW = "members/IRSS"
OTHER_VARIANT = "Members/IRSS"

#: The three typed lines of the move, as the remedy prints them.
REMOVE = f"git rm -r --cached --ignore-unmatch -- {VARIANT}"
SUBMODULE = "git submodule update --init --recursive"
MOVE_OUT = f"mv -- {VARIANT} ../Members-{MEMBER}"


def record(commit: str, row: str = ROW) -> str:
    """The `git update-index` line that records `row`'s gitlink."""
    return f"git update-index --add --cacheinfo 160000,{commit},{row}"


def moved_back(rows: dict, commit: bool = True) -> tuple[str, list[str]]:
    """`(the part that moves each gitlink back, the closing parts)` of the
    remedy, for `rows`, `{row path: ([its variants], the commit named)}`."""
    variants = sorted(name for names, _ in rows.values() for name in names)
    pairs = " and ".join(f"`{name}` for the row {row}"
                         for row, (names, _) in sorted(rows.items())
                         for name in sorted(names))
    lines = " and ".join(f"`{record(at, row)}`"
                         for row, (_, at) in sorted(rows.items()))
    move = ("move each member's gitlink held only under another spelling of "
            f"its row's path, {pairs}, to that path, at the commit it "
            "records, in the index alone, which touches no file (`git rm -r "
            f"--cached --ignore-unmatch -- {' '.join(variants)}`, then "
            f"{lines})" + (", and commit that" if commit else ""))
    moved = " and ".join(f"`mv -- {name} ../{name.replace('/', '-')}`"
                         for name in variants)
    return move, [
        f"where nothing is checked out at {' or '.join(sorted(rows))}, as in "
        f"a fresh clone, `{SUBMODULE}` then checks the member out there",
        "on a case-sensitive disk, as Linux's usually is, a directory left "
        f"at {' or '.join(variants)} stays there, untracked, and add refuses "
        "it as family-members-dir-variant: move each one that is there out "
        f"of the holder, {moved}",
        "on macOS and Windows it is the row's own directory, so leave it"]


def remedy(commit: str) -> str:
    """The whole remedy for the member's gitlink alone, at `commit`."""
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return remedy_of(move, *closing)


def in_the_index(*shown: str) -> str:
    """The refusal's first line, naming what the index holds."""
    return DIR_VARIANT + "in the index: " + ", ".join(shown)


VARIANT_SHOWN = f"`{VARIANT}` (a submodule)"

#: Where the refusal finds the gitlink.
IN_INDEX = "in the index"
HEAD_ONLY = "in HEAD and no longer in the index"


def variant(root: Path, row: str = ROW, spelled: str = VARIANT,
            commit: str | None = None) -> str:
    """`row`'s gitlink moved, in the index alone, to `spelled`, at the
    commit it records (or `commit`), and committed: #363's state after the
    fact, its row and its `.gitmodules` section saying `row`. The checkout
    stays where it is. Returns the commit recorded."""
    commit = commit or git("rev-parse", f"HEAD:{row}", cwd=root).stdout.strip()
    git("rm", "-q", "--cached", "--", row, cwd=root)
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{spelled}",
        cwd=root)
    git("commit", "-qm", f"{row} at {spelled}", cwd=root)
    return commit


def on_disk_as_named(root: Path, name: str) -> bool:
    """Is `name` on disk in that very spelling, component by component?"""
    here = root
    for part in name.split("/"):
        if not here.is_dir() or part not in os.listdir(here):
            return False
        here = here / part
    return True


def typed_as_printed(root: Path, said: str) -> list[str]:
    """EVERY COMMAND `said` PRINTS, TYPED AS PRINTED, in its order, and the
    commit each part asks for, as `type_remedy` types #574's: `<new name>`
    filled in `renamed-N` for a `git mv` and `../moved-N` for a `mv`. Typed
    where its sentence says so, and only there: `git submodule update` where
    nothing is checked out at the row's path, and an `mv` with nothing to
    fill in where its source is on disk in that spelling and the disk does
    not fold case (on macOS and Windows the text says to leave it). A local
    member is cloned with `protocol.file.allow`, the suite's one concession
    to bare repositories as origins. Returns what was typed."""
    folds = disk_folds(root.parent)
    typed: list[str] = []
    count = {"git": 0, "mv": 0}
    for part in said.split(" on every disk. ", 1)[1].split("; "):
        for command in re.findall(r"`([^`]*)`", part):
            argv = shlex.split(command)
            if command == "git commit":
                git("commit", "-qm", "The pending change", cwd=root)
            elif command == SUBMODULE:
                rows = re.search(r"checked out at (.+?), as in", part)
                if all((root / row / ".git").exists()
                       for row in rows.group(1).split(" or ")):
                    continue
                git("-c", "protocol.file.allow=always", *argv[1:], cwd=root)
            elif "<new name>" in command:
                tool = argv[0]
                count[tool] += 1
                argv[-1] = (f"renamed-{count['git']}" if tool == "git"
                            else f"../moved-{count['mv']}")
                if tool == "git":
                    git(*argv[1:], cwd=root)
                else:
                    os.rename(root / argv[2], root / argv[3])
                command = shlex.join(argv)
            elif argv[0] == "mv":
                if folds or not on_disk_as_named(root, argv[2]):
                    continue
                os.rename(root / argv[2], root / argv[3])
            elif argv[0] == "git" and (" -- " in command
                                       or argv[1] == "update-index"):
                git(*argv[1:], cwd=root)
            else:
                continue
            typed.append(command)
        if re.search(r", and commit (the rename|the removal|both|that)$",
                     part):
            git("commit", "-qm", "The remedy", cwd=root)
            typed.append("git commit")
    return typed


def registered(root: Path, before: Path, commit: str, row: str = ROW) -> None:
    """The member is where its row says: HEAD and the index record its
    gitlink at `row`, at `commit`; nothing at or under another spelling of
    `members/` is left in either; and its row and its `.gitmodules` section
    are HEAD's bytes in `before`, the holder the test began with."""
    assert git("ls-tree", "HEAD", row, cwd=root).stdout == (
        f"160000 commit {commit}\t{row}\n")
    assert git("ls-files", "-s", row, cwd=root).stdout == (
        f"160000 {commit} 0\t{row}\n")
    for listed in (git("ls-tree", "-r", "--name-only", "HEAD", cwd=root),
                   git("ls-files", cwd=root)):
        assert [name for name in listed.stdout.splitlines()
                if name.split("/")[0].lower() == "members"
                and not name.startswith("members/")] == []
    for name in ("family.yaml", ".gitmodules"):
        assert git("show", f"HEAD:{name}", cwd=root).stdout == git(
            "show", f"HEAD:{name}", cwd=before).stdout


def gate_passes(root: Path) -> None:
    """The holder's own gate, `validate-family.py`, every member asked."""
    gate = validate(root)
    assert gate.returncode == 0, gate.stdout + gate.stderr


# --- each layout, typed as printed ------------------------------------------

def nothing_there(root: Path, remotes: Path, commit: str) -> None:
    """Nothing on disk in that spelling: the checkout stays at the row's
    path, where it was."""


def both_directories(root: Path, remotes: Path, commit: str) -> None:
    """The checkout at the row's path, and a second one at the variant."""
    cloned_just_pushed(remotes / f"{MEMBER}.git", root / VARIANT,
                       recurse=False)
    git("checkout", "-q", "--detach", commit, cwd=root / VARIANT)


def checkout_at_the_variant(root: Path, remotes: Path, commit: str) -> None:
    """The member's only checkout at `Members/IRRS`, a clone of its own,
    and none at the row's path, whose object store stays in
    `.git/modules`."""
    rmtree(root / ROW)
    both_directories(root, remotes, commit)


def removal_staged(root: Path, remotes: Path, commit: str) -> None:
    """Half repaired: the variant taken out of the index, staged and not
    committed, so HEAD alone holds it (#639's review, N1)."""
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)


#: `{layout: (how it is laid out after the move, whether it needs two
#: directories differing only in case, where the refusal finds the gitlink,
#: what is typed after the move and its commit)}`.
LAYOUTS = {
    "nothing on disk in that spelling": (nothing_there, False, IN_INDEX, []),
    "the only checkout at the variant": (checkout_at_the_variant, True,
                                         IN_INDEX, [SUBMODULE, MOVE_OUT]),
    "both directories": (both_directories, True, IN_INDEX, [MOVE_OUT]),
    "the removal staged, not committed": (removal_staged, False, HEAD_ONLY,
                                          []),
}


@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_each_layout_moves_the_gitlink_back_as_printed(family, holder,
                                                       offline, tmp_path,
                                                       layout):
    """THE ISSUE (#646): `add` of another member is refused, the dry run
    and the real run alike, with the holder exactly as it was, and the
    remedy moves the member's gitlink back to its row's path, where #574's
    `git rm --cached`, `git mv` or `git commit` took it away. Typed as
    printed, the member is where its row says, at the commit it recorded,
    the holder's gate passes, and the same `add` goes through."""
    lay_out, two_spellings, where, after = LAYOUTS[layout]
    if two_spellings and disk_folds(tmp_path):
        pytest.skip("two directories differing only in case need a disk "
                    "that does not fold case")
    commit = variant(holder)
    lay_out(holder, family["remotes"], commit)
    said = refused_untouched(offline, holder, family["remotes"], "--dry-run")
    assert refused_untouched(offline, holder, family["remotes"]) == said
    assert said == (DIR_VARIANT + f"{where}: {VARIANT_SHOWN}",
                    remedy(commit))
    assert typed_as_printed(holder, said[1]) == [
        REMOVE, record(commit), "git commit", *after]
    registered(holder, family["root"], commit)
    gate_passes(holder)
    added(offline, holder, family["remotes"])


def test_a_fresh_clone_moves_the_gitlink_back_as_printed(family, holder,
                                                          offline, tmp_path):
    """A FRESH RECURSIVE CLONE of a holder whose HEAD records the gitlink
    only at `Members/IRRS`: the clone leaves an empty `Members/IRRS` and
    nothing at the row's path. The same text; typed as printed, `git
    submodule update` checks the member out at its row's path, the empty
    directory leaves the holder on a case-sensitive disk (on macOS and
    Windows it is the row's own, and stays), and the clone's gate passes.
    The branch is pushed to the fixture's remote under a name no other test
    uses."""
    commit = variant(holder)
    remote = family["remotes"] / f"{NAME}.git"
    branch = "w646/fresh-clone"
    git("push", "-q", str(remote), f"HEAD:refs/heads/{branch}", cwd=holder)
    clone = cloned_just_pushed(remote, tmp_path / "clone" / NAME, branch)
    assert (clone / VARIANT).is_dir()
    assert not (clone / ROW / ".git").exists()
    said = refused_untouched(offline, clone, family["remotes"], "--dry-run")
    assert said == (in_the_index(VARIANT_SHOWN), remedy(commit))
    assert typed_as_printed(clone, said[1]) == [
        REMOVE, record(commit), "git commit", SUBMODULE,
        *([] if disk_folds(tmp_path) else [MOVE_OUT])]
    registered(clone, family["root"], commit)
    gate_passes(clone)
    added(offline, clone, family["remotes"])


# --- one answer on every disk -----------------------------------------------

def dry_run_in_process(module, monkeypatch, offline, root: Path,
                       remotes: Path, capsys) -> tuple[str, str]:
    """`add --dry-run` of the spare member IN THIS PROCESS, where `disk_as`
    reaches it; the refusal's two lines, and nothing on stdout."""
    monkeypatch.setattr(tempfile, "tempdir", str(offline.temp))
    monkeypatch.setenv("PATH", offline.env["PATH"])
    code = module.main(["add", "--family-root", str(root), "--member",
                        f"{ORG}/{SPARE}", "--local-remote-dir", str(remotes),
                        "--dry-run"])
    out, err = capsys.readouterr()
    assert code == 2, out + err
    assert out == ""
    return refusal(err)


@pytest.mark.parametrize("folding", [False, True], ids=["linux", "folding"])
@pytest.mark.parametrize("layout", list(LAYOUTS))
def test_every_disk_gives_the_same_answer(family, holder, family_module,
                                          offline, monkeypatch, capsys,
                                          tmp_path, layout, folding):
    """ON EVERY DISK ("Refuse on every disk"): each layout asked in process
    of a disk that folds case and of one that does not, emulated below the
    holder (`disk_as`), gives the one text the subprocess gives. The move
    reads the index and HEAD, never the disk, so the disk cannot change
    it."""
    lay_out, two_spellings, where, _ = LAYOUTS[layout]
    if two_spellings and disk_folds(tmp_path):
        pytest.skip("two directories differing only in case need a disk "
                    "that does not fold case")
    commit = variant(holder)
    lay_out(holder, family["remotes"], commit)
    disk_as(monkeypatch, holder, folding)
    assert dry_run_in_process(family_module, monkeypatch, offline, holder,
                              family["remotes"], capsys) == (
        DIR_VARIANT + f"{where}: {VARIANT_SHOWN}", remedy(commit))


# --- with the other remedies, each in its order -----------------------------

def two_rows(root: Path) -> dict:
    """Both members' gitlinks in the wrong case."""
    return {ROW: ([VARIANT], variant(root)),
            OTHER_ROW: ([OTHER_VARIANT], variant(root, OTHER_ROW,
                                                 OTHER_VARIANT))}


def staged_only(root: Path) -> str:
    """The move to the variant staged and not committed, so HEAD still
    records the gitlink at the row's path, at the same commit: the move
    back leaves nothing to commit. Returns the commit."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()
    git("rm", "-q", "--cached", "--", ROW, cwd=root)
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{VARIANT}",
        cwd=root)
    return commit


def beside_a_file(root: Path, remotes: Path) -> tuple:
    """`Members/README` staged beside the gitlink: #574's remedy for it,
    then the move back."""
    commit = variant(root)
    plant(root, "100644", "Members/README")
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return (in_the_index(VARIANT_SHOWN, "`Members/README` (a file)"),
            remedy_of(index_part(unstage=["Members/README"]), move,
                      *closing),
            ["git rm -r --cached -- Members/README", REMOVE, record(commit),
             "git commit"], commit)


def after_a_pending_change(root: Path, remotes: Path) -> tuple:
    """A pending change in HEAD (`MEMBERS/old` taken out of the index, not
    committed) beside a staged move to the variant: the pending change is
    committed first, so the move back has a commit to make after it."""
    plant(root, "100644", "MEMBERS/old")
    git("commit", "-qm", "Track MEMBERS/old", cwd=root)
    git("rm", "-q", "--cached", "--", "MEMBERS/old", cwd=root)
    commit = staged_only(root)
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return (in_the_index(VARIANT_SHOWN) + "; in HEAD and no longer in the "
            "index: `MEMBERS/old` (a file)",
            remedy_of(commit_first("MEMBERS/old"), move, *closing),
            ["git commit", REMOVE, record(commit), "git commit"], commit)


def nothing_to_commit(root: Path, remotes: Path) -> tuple:
    """The staged move alone: no commit is printed, since none is left to
    make, and a printed one would fail as typed."""
    commit = staged_only(root)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, commit=False)
    return (in_the_index(VARIANT_SHOWN), remedy_of(move, *closing),
            [REMOVE, record(commit)], commit)


def members_renamed_by_hand(root: Path, remotes: Path) -> tuple:
    """The holder's `members/` renamed `Members` by hand on Linux, the other
    member's checkout in it, and the member's gitlink at `Members/IRRS`
    with no checkout anywhere: the move back of the directory comes after
    the gitlink's, and the closing sentences after both, so `git submodule
    update` checks the member out in the `members/` moved back, and nothing
    is left at the variant to move out."""
    commit = variant(root)
    rmtree(root / ROW)
    renamed_members(root)
    move, closing = moved_back({ROW: ([VARIANT], commit)})
    return (in_the_index(VARIANT_SHOWN) + "; on disk and untracked: "
            "`Members` (a directory)",
            remedy_of(move, MOVE_BACK, *closing),
            [REMOVE, record(commit), "git commit", "mv -- Members members",
             SUBMODULE], commit)


def head_only_and_on_disk(root: Path, remotes: Path) -> tuple:
    """HEAD alone holds the gitlink at the variant, and the member's only
    checkout is there: the directory is the move's to name, never a second
    time as untracked."""
    commit = variant(root)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)
    checkout_at_the_variant(root, remotes, commit)
    return (DIR_VARIANT + f"{HEAD_ONLY}: {VARIANT_SHOWN}", remedy(commit),
            [REMOVE, record(commit), "git commit", SUBMODULE, MOVE_OUT],
            commit)


#: `{state: (how it is made, from the holder and the remotes, returning
#: (the refusal's two lines, what is typed, the member's commit), whether it
#: needs two directories differing only in case)}`.
WITH_OTHERS = {
    "beside a file under Members/": (beside_a_file, False),
    "after a pending change in HEAD": (after_a_pending_change, False),
    "with nothing left to commit": (nothing_to_commit, False),
    "members/ renamed by hand": (members_renamed_by_hand, True),
    "HEAD alone, the checkout at the variant": (head_only_and_on_disk, True),
}


@pytest.mark.parametrize("state", list(WITH_OTHERS))
def test_with_the_other_remedies_each_runs_in_its_order(family, holder,
                                                        offline, tmp_path,
                                                        state):
    """The move back among #574's remedies, each kept for its own path:
    the pending change committed first, what the index holds under
    `Members/` next, then the move back and its commit where one is left to
    make, then the disk, and the move back's closing sentences last. Typed
    as printed, in that order, the member is where its row says, the gate
    passes and the same `add` goes through."""
    make, two_spellings = WITH_OTHERS[state]
    if two_spellings and disk_folds(tmp_path):
        pytest.skip("two directories differing only in case need a disk "
                    "that does not fold case")
    first, said, typed, commit = make(holder, family["remotes"])
    assert refused_untouched(offline, holder, family["remotes"]) == (first,
                                                                     said)
    assert typed_as_printed(holder, said) == typed
    registered(holder, family["root"], commit)
    gate_passes(holder)
    added(offline, holder, family["remotes"])


def test_every_member_held_in_the_wrong_case_is_moved_back(family, holder,
                                                           offline):
    """TWO ROWS, both gitlinks in the wrong case: one removal naming both,
    one `git update-index` per row, one commit; typed as printed, both are
    where their rows say."""
    rows = two_rows(holder)
    move, closing = moved_back(rows)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN,
                                 f"`{OTHER_VARIANT}` (a submodule)"),
                    remedy_of(move, *closing))
    assert typed_as_printed(holder, said[1]) == [
        f"git rm -r --cached --ignore-unmatch -- {VARIANT} {OTHER_VARIANT}",
        record(rows[ROW][1]), record(rows[OTHER_ROW][1], OTHER_ROW),
        "git commit"]
    for row, (_, commit) in rows.items():
        registered(holder, family["root"], commit, row)
    gate_passes(holder)
    added(offline, holder, family["remotes"])


# --- which gitlink is the member's own, and at which commit -----------------

def refused_in_process(module, root: Path) -> tuple[str, str]:
    """`_checked_mount_path` of the spare member's path, asked as `add`
    asks it, with the holder's rows: the refusal's two lines."""
    rows = module._rows_paths(module.Family.open(root).members)
    with pytest.raises(module.Refusal) as caught:
        module._checked_mount_path(root, SPARE, MOUNT, rows)
    return tuple(str(caught.value).splitlines())


def first_commit(root: Path) -> str:
    """The member's commit before the one its row pins."""
    return git("rev-parse", "HEAD~1", cwd=root / ROW).stdout.strip()


def at_another_commit(root: Path) -> tuple[list[str], str]:
    """The gitlink at the variant records a commit the row does not pin:
    the move keeps the commit, a move and not a bump."""
    first = first_commit(root)
    variant(root, commit=first)
    return [VARIANT], first


def twice_in_the_index(root: Path) -> tuple[list[str], str]:
    """Two variants in the index at two commits: both are taken out, and
    the one the index lists first is recorded."""
    first = first_commit(root)
    variant(root)
    git("update-index", "--add", "--cacheinfo",
        f"160000,{first},MEMBERS/{MEMBER}", cwd=root)
    git("commit", "-qm", "A second variant", cwd=root)
    return [f"MEMBERS/{MEMBER}", VARIANT], first


def in_the_index_and_head(root: Path) -> tuple[list[str], str]:
    """One variant that HEAD alone holds, at one commit, and another the
    index holds, at the row's: the index's commit is recorded, since the
    next commit records the index."""
    pinned = git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()
    variant(root, spelled=f"MEMBERS/{MEMBER}", commit=first_commit(root))
    git("rm", "-q", "--cached", "--", f"MEMBERS/{MEMBER}", cwd=root)
    git("update-index", "--add", "--cacheinfo",
        f"160000,{pinned},{VARIANT}", cwd=root)
    return [VARIANT, f"MEMBERS/{MEMBER}"], pinned


def staged_at_another_commit(root: Path) -> tuple[list[str], str]:
    """The move to the variant staged at another commit, HEAD still
    recording the row's gitlink at its own: the index's commit is recorded,
    never HEAD's, and the move has a commit to make, since HEAD's gitlink
    at the row's path is another."""
    first = first_commit(root)
    git("rm", "-q", "--cached", "--", ROW, cwd=root)
    git("update-index", "--add", "--cacheinfo", f"160000,{first},{VARIANT}",
        cwd=root)
    return [VARIANT], first


COMMITS = {
    "the variant at a commit the row does not pin": at_another_commit,
    "two variants in the index": twice_in_the_index,
    "one in the index, one in HEAD alone": in_the_index_and_head,
    "staged at another commit, HEAD keeping the row's": (
        staged_at_another_commit),
}


@pytest.mark.parametrize("state", list(COMMITS))
def test_the_gitlink_is_recorded_at_the_commit_it_records(holder,
                                                          family_module,
                                                          state):
    """THE COMMIT NAMED is the one the variant records, never another: a
    move, not a bump. Where one row has two variants, both are taken out
    and the first found is recorded, the index's before HEAD's."""
    names, commit = COMMITS[state](holder)
    move, closing = moved_back({ROW: (names, commit)})
    assert refused_in_process(family_module, holder)[1] == remedy_of(
        move, *closing)


def head_file(root: Path) -> None:
    """A FILE at the variant that HEAD alone holds: a pending change."""
    plant(root, "100644", VARIANT)
    git("commit", "-qm", "A file at the variant", cwd=root)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)


#: `{state: (how it is made after the row's gitlink leaves the index, what
#: `_members_spellings` gives the variant: where, target, remedy)}`. The
#: index never holds the row's gitlink but in the first.
OWN = {
    "a second gitlink beside the row's": (
        lambda root: plant(root, "160000", VARIANT),
        (IN_INDEX, VARIANT, "git rm -r --cached")),
    "a file at the variant": (
        lambda root: plant(root, "100644", VARIANT),
        (IN_INDEX, VARIANT, "git rm -r --cached")),
    "a gitlink under the variant": (
        lambda root: plant(root, "160000", f"{VARIANT}/x"),
        (IN_INDEX, VARIANT, "git rm -r --cached")),
    "a file at the variant in HEAD alone": (
        head_file, (HEAD_ONLY, VARIANT, "git commit")),
    "the member's own gitlink": (
        lambda root: plant(root, "160000", VARIANT),
        (IN_INDEX, ROW, "git update-index")),
}


@pytest.mark.parametrize("state", list(OWN))
def test_only_the_members_own_gitlink_is_moved_back(holder, family_module,
                                                    state):
    """WHICH PATH IS THE MEMBER'S OWN: a gitlink at a case variant of a
    row's path, where the index holds none at that path. A second gitlink
    beside the row's, a file there, or a gitlink under it keeps #574's
    remedy, which takes nothing away from the row."""
    make, (where, target, remedy_said) = OWN[state]
    if state != "a second gitlink beside the row's":
        git("rm", "-q", "--cached", "--", ROW, cwd=holder)
    make(holder)
    rows = family_module._rows_paths(family_module.Family.open(holder).members)
    assert [(spelled.where, spelled.target, spelled.remedy)
            for spelled in family_module._members_spellings(
                holder, SPARE, family_module._members_on_disk(holder),
                rows)] == [(where, target, remedy_said)]


def test_the_rows_that_have_a_path_of_their_own(family_module):
    """`_rows_paths`: `members/<project>` for every row with that path, or
    no `path:` at all; none for a row whose `path:` is another, or whose
    project is no single directory name, which `member-path` refuses."""
    assert family_module._rows_paths([
        {"project": "IRRS"}, {"project": "IRSS", "path": OTHER_ROW},
        {"project": "Elsewhere", "path": "elsewhere/Elsewhere"},
        {"project": ".."}, {"project": 7}, {}]) == frozenset(
        {ROW, OTHER_ROW})
