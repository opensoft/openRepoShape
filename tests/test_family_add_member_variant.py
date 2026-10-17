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
the variant records, and a commit. Then, as the validator says, an `mv`
out of the holder of what a case-sensitive disk leaves at the variant,
guarded by two tests a POSIX shell runs so that it moves nothing where that
directory is the row's own (macOS and Windows) or a checkout, which is
deleted, or for a clone of its own moved, by hand; and last `git submodule
update --init --recursive` where nothing is checked out at the row's path
(#761).

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
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import cloned_just_pushed, git, rmtree
from test_family import NAME, ORG, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, offline, plant, refusal,
)
from test_family_members_case_variants import (
    DIR_VARIANT, MOUNT, MOVE_BACK, NEEDS_GIT_2_34, added, commit_first,
    disk_as, disk_folds, git_version, index_part, refused_untouched,
    remedy_of, renamed_members,
)

#: The member whose gitlink is moved into the wrong case, its row's path,
#: the variant, and the other member.
MEMBER = "IRRS"
ROW = f"members/{MEMBER}"
VARIANT = f"Members/{MEMBER}"
OTHER_ROW = "members/IRSS"
OTHER_VARIANT = "Members/IRSS"

#: The typed lines of the move, as the remedy prints them: the removal,
#: with `--sparse` where a sparse checkout keeps the variant off disk.
REMOVE = f"git rm -r --cached --ignore-unmatch -- {VARIANT}"
REMOVE_SPARSE = f"git rm -r --cached --sparse --ignore-unmatch -- {VARIANT}"
SUBMODULE = "git submodule update --init --recursive"


def guarded(name: str = VARIANT, row: str = ROW) -> str:
    """The closing `mv` of a directory left at `name`, the variant of
    `row`'s path, guarded by the two tests a POSIX shell runs (#761, as
    `validate-family.py` guards it, #681): it moves nothing where the two
    names are one directory, nor where it holds a `.git` entry."""
    return (f"[ {name} -ef {row} ] || [ -e {name}/.git ] || "
            f"mv -- {name} ../{name.replace('/', '-')}")


MOVE_OUT = guarded()


def record(commit: str, row: str = ROW) -> str:
    """The `git update-index` line that records `row`'s gitlink."""
    return f"git update-index --add --cacheinfo 160000,{commit},{row}"


def point_back(row: str = ROW, name: str | None = None) -> str:
    """The line that points the section `name` (named after `row`, as `git
    submodule add` names one) back at `row` (#761)."""
    return f"git config -f .gitmodules submodule.{name or row}.path {row}"


def moved_back(rows: dict, commit: bool = True, sparse: bool = False,
               sections: tuple = (), staged: dict | None = None,
               forced: bool = False) -> tuple[str, list[str]]:
    """`(the part that moves each gitlink back, the closing parts)` of the
    remedy, for `rows`, `{row path: ([its variants], the commit named)}`;
    `sparse` where a sparse checkout keeps a variant off disk; `sections`,
    the rows whose section is pointed back (#761); `staged`, `{row path:
    (the path its section gives, HEAD's commit)}` for a member whose
    removal is staged (#761); `forced` where the removal takes `-f`
    (#761)."""
    staged = staged or {}
    every = {**{row: (names, at) for row, (names, at) in rows.items()},
             **{row: ([given], at) for row, (given, at) in staged.items()}}
    variants = sorted(name for names, _ in every.values() for name in names)
    row_of = {name: row for row, (names, _) in every.items()
              for name in names}
    pairs = " and ".join(f"`{name}` for the row {row}"
                         for row, (names, _) in sorted(rows.items())
                         for name in sorted(names))
    put = " and ".join(f"{row}, whose section gives `{given}`"
                       for row, (given, _) in sorted(staged.items()))
    lines = " and ".join(f"`{record(at, row)}`"
                         for row, (_, at) in sorted(every.items()))
    said = []
    if pairs:
        said.append("move each member's gitlink held only under another "
                    f"spelling of its row's path, {pairs}, to that path, at "
                    "the commit it records")
    if put:
        said.append("put back at its row's path each member's gitlink whose "
                    "removal is staged though a section of .gitmodules gives "
                    f"it another spelling, {put}, at the commit HEAD records")
    pointed = " and ".join(f"`{point_back(row)}`" for row in sorted(sections))
    move = (", and ".join(said) + ", in the index alone, which touches no "
            "file"
            + (", and point each section of .gitmodules that gives one of "
               "them another spelling of its row's path, as a `git mv` of "
               "its mount leaves it, at that path" if sections else "")
            + f" (`git rm -r --cached{' --sparse' if sparse else ''}"
            f"{' -f' if forced else ''} --ignore-unmatch -- "
            f"{' '.join(variants)}`, "
            + (f"{NEEDS_GIT_2_34}, " if sparse else "")
            + ("whose -f takes out a staged gitlink whose checkout has moved "
               "on or holds a file git does not track, which git rm "
               "otherwise refuses, and with --cached touches no file, "
               if forced else "") + f"then {lines}"
            + (f", then {pointed} and `git add -- .gitmodules`"
               if sections else "") + ")"
            + (", and commit that" if commit else ""))
    moved = " and ".join(f"`{guarded(name, row_of[name])}`"
                         for name in variants)
    status = " or ".join(f"`git -C {name} status`" for name in variants)
    unpushed = " or ".join(f"`git -C {name} log --oneline HEAD --branches "
                           "--not --remotes`" for name in variants)
    return move, [
        f"a directory left at {' or '.join(variants)} is the row's own where "
        "the disk folds case, as macOS's and Windows' usually do and a Linux "
        "mount can (WSL's /mnt/c)",
        "where the disk holds the two apart it stays there, untracked, and "
        "add refuses it as family-members-dir-variant: move each one that is "
        f"there out of the holder, in a POSIX shell, {moved}, which moves "
        "nothing where the two names are one directory or where it holds a "
        ".git entry, a checkout",
        "a checkout there that git submodule add or git mv made holds a .git "
        "file naming its store by a path relative to it, which a move would "
        "leave pointing nowhere: its commits are kept under this holder's "
        ".git/modules/, in the directory its .git file names, whatever "
        "becomes of the checkout, and only what is not committed is in the "
        f"checkout alone ({status} shows it, except where a plain mv brought "
        "the checkout to that path: git cannot open it there, so check its "
        "files by hand), so delete such a checkout by hand once nothing only "
        "it holds is needed, before the update below, which points a store "
        "the row shares at the row's path",
        "a checkout whose .git is a directory, a clone of its own, holds its "
        f"commits there and nowhere else, and {unpushed} lists the ones not "
        "pushed: move it out of the holder whole, by hand, rather than "
        "delete it",
        f"then, where nothing is checked out at {' or '.join(sorted(every))}, "
        f"as in a fresh clone, `{SUBMODULE}` checks the member out there"]


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


def typed_in_sh(root: Path, command: str) -> None:
    """`command` typed into a POSIX shell in `root`, as printed: exit 0."""
    typed = subprocess.run(["sh", "-c", command], cwd=str(root),
                           capture_output=True, check=False)
    assert typed.returncode == 0, (command, typed.stderr)


def typed_as_printed(root: Path, said: str, by_hand=None) -> list[str]:
    """EVERY COMMAND `said` PRINTS, TYPED AS PRINTED, in its order, and the
    commit each part asks for, as `type_remedy` types #574's: `<new name>`
    filled in `renamed-N` for a `git mv` and `../moved-N` for a `mv`. Typed
    where its sentence says so, and only there: `git submodule update` where
    nothing is checked out at the row's path, and a guarded `mv` (#761)
    where its source is there, into a POSIX shell, which keeps a checkout and
    the row's own directory in place. `by_hand`, where given, is what a
    person does by hand where the text says to (#761), run after the last
    such part. A local member is cloned with `protocol.file.allow`, the
    suite's one concession to bare repositories as origins. Returns what was
    typed."""
    typed: list[str] = []
    count = {"git": 0, "mv": 0}
    parts = said.split(" on every disk. ", 1)[1].split("; ")
    last_by_hand = max((index for index, part in enumerate(parts)
                        if "by hand" in part),
                       default=None)
    for index, part in enumerate(parts):
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
                argv = shlex.split(command.replace(
                    "<new name>", f"renamed-{count['git']}" if tool == "git"
                    else f"../moved-{count['mv']}"))
                if tool == "git":
                    git(*argv[1:], cwd=root)
                else:
                    os.rename(root / argv[2], root / argv[3])
                command = shlex.join(argv)
            elif argv[0] in ("mv", "["):
                source = argv[1] if argv[0] == "[" else argv[2]
                if not os.path.lexists(root / source):
                    continue
                typed_in_sh(root, command)
            elif argv[0] == "git" and (" -- " in command or argv[1] in (
                    "update-index", "config")):
                git(*argv[1:], cwd=root)
            else:
                continue
            typed.append(command)
        if re.search(r", and commit (the rename|the removal|both|that)$",
                     part):
            git("commit", "-qm", "The remedy", cwd=root)
            typed.append("git commit")
        if index == last_by_hand and by_hand is not None:
            by_hand(root)
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


def clone_moved_out_by_hand(root: Path) -> None:
    """What the text says of a clone of its own at the variant, done by
    hand: the guarded `mv` moved nothing, since it holds a `.git` entry, and
    the clone, whose `.git` is a directory, is moved out of the holder whole
    (#761, as `validate-family.py` says it, #681)."""
    assert (root / VARIANT / ".git").is_dir(), "premise: a clone of its own"
    os.rename(root / VARIANT, root.parent / f"{MEMBER}-clone")


#: `{layout: (how it is laid out after the move, whether it needs two
#: directories differing only in case, where the refusal finds the gitlink,
#: what is typed after the move and its commit, what is done by hand)}`.
LAYOUTS = {
    "nothing on disk in that spelling": (nothing_there, False, IN_INDEX, [],
                                         None),
    "the only checkout at the variant": (checkout_at_the_variant, True,
                                         IN_INDEX, [MOVE_OUT, SUBMODULE],
                                         clone_moved_out_by_hand),
    "both directories": (both_directories, True, IN_INDEX, [MOVE_OUT],
                         clone_moved_out_by_hand),
    "the removal staged, not committed": (removal_staged, False, HEAD_ONLY,
                                          [], None),
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
    the holder's gate passes, and the same `add` goes through. A clone of
    its own at the variant is kept by the guarded `mv` and moved out by
    hand, as the text says, before the update (#761)."""
    lay_out, two_spellings, where, after, by_hand = LAYOUTS[layout]
    if two_spellings and disk_folds(tmp_path):
        pytest.skip("two directories differing only in case need a disk "
                    "that does not fold case")
    commit = variant(holder)
    lay_out(holder, family["remotes"], commit)
    said = refused_untouched(offline, holder, family["remotes"], "--dry-run")
    assert refused_untouched(offline, holder, family["remotes"]) == said
    assert said == (DIR_VARIANT + f"{where}: {VARIANT_SHOWN}",
                    remedy(commit))
    assert typed_as_printed(holder, said[1], by_hand) == [
        REMOVE, record(commit), "git commit", *after]
    registered(holder, family["root"], commit)
    gate_passes(holder)
    added(offline, holder, family["remotes"])


def test_a_fresh_clone_moves_the_gitlink_back_as_printed(family, holder,
                                                          offline, tmp_path):
    """A FRESH RECURSIVE CLONE of a holder whose HEAD records the gitlink
    only at `Members/IRRS`: the clone leaves an empty `Members/IRRS` and
    nothing at the row's path. The same text; typed as printed, the empty
    directory leaves the holder on a case-sensitive disk by the guarded
    `mv` (on macOS and Windows it is the row's own, and the shell's `-ef`
    keeps it), `git submodule update` checks the member out at its row's
    path, and the clone's gate passes. The branch is pushed to the
    fixture's remote under a name no other test uses."""
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
        REMOVE, record(commit), "git commit", MOVE_OUT, SUBMODULE]
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
    lay_out, two_spellings, where, _, _ = LAYOUTS[layout]
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
    checkout is there, a clone of its own: the directory is the move's to
    name, never a second time as untracked, and it is moved out by hand
    before the update (#761)."""
    commit = variant(root)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)
    checkout_at_the_variant(root, remotes, commit)
    return (DIR_VARIANT + f"{HEAD_ONLY}: {VARIANT_SHOWN}", remedy(commit),
            [REMOVE, record(commit), "git commit", MOVE_OUT, SUBMODULE],
            commit)


def head_holding_both(root: Path, remotes: Path) -> tuple:
    """HEAD records the gitlink at the row's path AND at the variant, at one
    commit, and the index has the row's removal staged beside the variant:
    HEAD's gitlink at the row's path is the move's commit already, but HEAD
    still holds the variant, so the commit is printed. Without it `D
    Members/IRRS` stays staged, and the next `add` refuses it as a pending
    change (#646's review, S2)."""
    commit = git("rev-parse", f"HEAD:{ROW}", cwd=root).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{VARIANT}",
        cwd=root)
    git("commit", "-qm", "Both spellings", cwd=root)
    git("rm", "-q", "--cached", "--", ROW, cwd=root)
    return (in_the_index(VARIANT_SHOWN), remedy(commit),
            [REMOVE, record(commit), "git commit"], commit)


def kept_off_disk(root: Path, remotes: Path) -> tuple:
    """The variant kept off disk by a sparse checkout (`skip-worktree`), as
    #574's sparse case keeps its entry: `git rm --cached --ignore-unmatch`
    alone passes it over, exit 0, and the move then left two gitlinks in
    the index, so the removal says `--sparse` (#646's review, S1). Skipped
    on the git versions #574's sparse case is skipped on."""
    if git_version() < (2, 34):
        pytest.skip("git's `--sparse` options are asked of git 2.34 or later")
    commit = variant(root)
    git("update-index", "--skip-worktree", "--", VARIANT, cwd=root)
    move, closing = moved_back({ROW: ([VARIANT], commit)}, sparse=True)
    return (in_the_index(VARIANT_SHOWN), remedy_of(move, *closing),
            [REMOVE_SPARSE, record(commit), "git commit"], commit)


def file_blob(root: Path) -> str:
    """A blob for a file at the variant, written as BYTES."""
    return subprocess.run(
        ["git", "hash-object", "-w", "--stdin"], cwd=str(root),
        input=b"a file\n", capture_output=True,
        check=True).stdout.decode("ascii").strip()


def unmerged_at(root: Path, stages: dict[int, str],
                files: tuple[int, ...] = ()) -> None:
    """The variant at each of `stages`, `{stage: object}`, and at no stage
    0, written as bytes by `update-index --index-info`: a file, whose blob
    it names, at each stage in `files`, and a gitlink, at the commit it
    names, at the others."""
    written = subprocess.run(
        ["git", "update-index", "--index-info"], cwd=str(root),
        input="".join(f"{'100644' if stage in files else '160000'} {at} "
                      f"{stage}\t{VARIANT}\n"
                      for stage, at in stages.items()).encode("ascii"),
        capture_output=True, check=False)
    assert written.returncode == 0, written.stderr


def unmerged(root: Path, remotes: Path) -> tuple:
    """The variant UNMERGED, at stages 1, 2 and 3 and at no stage 0, with no
    merge or stash in progress, as a conflicted `git stash pop` leaves it:
    moved back at stage 2's commit, the holder's own side and what HEAD
    records there, never at stage 1's, the merge base, which git lists
    first (#646's review, N2). The removal takes out every stage."""
    commit = variant(root)
    first = first_commit(root)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)
    unmerged_at(root, {1: first, 2: commit, 3: first})
    return (in_the_index(VARIANT_SHOWN), remedy(commit),
            [REMOVE, record(commit), "git commit"], commit)


#: `{state: (how it is made, from the holder and the remotes, returning
#: (the refusal's two lines, what is typed, the member's commit), whether it
#: needs two directories differing only in case, what is done by hand)}`.
WITH_OTHERS = {
    "beside a file under Members/": (beside_a_file, False, None),
    "after a pending change in HEAD": (after_a_pending_change, False, None),
    "with nothing left to commit": (nothing_to_commit, False, None),
    "members/ renamed by hand": (members_renamed_by_hand, True, None),
    "HEAD alone, the checkout at the variant": (head_only_and_on_disk, True,
                                                clone_moved_out_by_hand),
    "HEAD holding both, the row's removal staged": (head_holding_both,
                                                    False, None),
    "kept off disk by a sparse checkout": (kept_off_disk, False, None),
    "unmerged, with nothing in progress": (unmerged, False, None),
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
    make, two_spellings, by_hand = WITH_OTHERS[state]
    if two_spellings and disk_folds(tmp_path):
        pytest.skip("two directories differing only in case need a disk "
                    "that does not fold case")
    first, said, typed, commit = make(holder, family["remotes"])
    assert refused_untouched(offline, holder, family["remotes"]) == (first,
                                                                     said)
    assert typed_as_printed(holder, said, by_hand) == typed
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


def test_a_commit_the_row_does_not_pin_is_moved_not_bumped(family, holder,
                                                            offline):
    """THE VARIANT AT A COMMIT THE ROW DOES NOT PIN, its checkout at that
    commit, as the holder records it, typed as printed: the member is at its
    row's path at the commit it recorded, and nothing else changed, a move
    and not a bump. The gate then names the drift the holder really has,
    `member-gitlink-mismatch`, exit 1, whose own remedy is `bump`; and `add`
    of another member still goes through (#646's review, S3)."""
    _, commit = at_another_commit(holder)
    git("checkout", "-q", "--detach", commit, cwd=holder / ROW)
    said = refused_untouched(offline, holder, family["remotes"])
    assert said == (in_the_index(VARIANT_SHOWN), remedy(commit))
    assert typed_as_printed(holder, said[1]) == [REMOVE, record(commit),
                                                 "git commit"]
    registered(holder, family["root"], commit)
    gate = validate(holder)
    assert gate.returncode == 1, gate.stdout + gate.stderr
    assert re.findall(r"^FINDING ([a-z-]+):", gate.stderr, re.M) == [
        "member-gitlink-mismatch"]
    assert f"{ROW}: gitlink {commit} != family.yaml pin " in gate.stderr
    added(offline, holder, family["remotes"])


def head_file(root: Path) -> None:
    """A FILE at the variant that HEAD alone holds: a pending change."""
    plant(root, "100644", VARIANT)
    git("commit", "-qm", "A file at the variant", cwd=root)
    git("rm", "-q", "--cached", "--", VARIANT, cwd=root)


def beside_a_file_at(path: str):
    """The variant's gitlink with a FILE at `path`, the row's path or under
    it, in the index: the move would replace the one, and stop on the other
    (`appears as both a file and as a directory`) once the variant was out
    (#646's review, N3), so the file is set aside first, here out of the
    index, since the disk holds the member's checkout there (#761)."""
    def make(root: Path) -> None:
        plant(root, "100644", path)
        plant(root, "160000", VARIANT)
    return make


def unmerged_theirs(root: Path) -> None:
    """The variant unmerged with no gitlink at stage 2, the holder's own
    side: no member's own (#646's review, N2)."""
    unmerged_at(root, {1: "1" * 40, 3: "1" * 40})


def unmerged_file_ours(root: Path) -> None:
    """The variant unmerged with a gitlink at stage 1, a FILE at stage 2 and
    a gitlink at stage 3: git lists stage 1 first, and a gitlink there is
    not the holder's own side, which is a file, so no member's own (#646's
    review, NIT-3; a rule that read the first record listed would move the
    file's blob back as a gitlink)."""
    unmerged_at(root, {1: "1" * 40, 2: file_blob(root), 3: "1" * 40},
                files=(2,))


#: `{state: (how it is made after the row's gitlink leaves the index, what
#: `_members_spellings` gives each path: where, target, remedy)}`. The
#: index never holds the row's gitlink but in the first.
OWN = {
    "a second gitlink beside the row's": (
        lambda root: plant(root, "160000", VARIANT),
        [(IN_INDEX, VARIANT, "git rm -r --cached")]),
    "a file at the variant": (
        lambda root: plant(root, "100644", VARIANT),
        [(IN_INDEX, VARIANT, "git rm -r --cached")]),
    "a gitlink under the variant": (
        lambda root: plant(root, "160000", f"{VARIANT}/x"),
        [(IN_INDEX, VARIANT, "git rm -r --cached")]),
    "a file at the variant in HEAD alone": (
        head_file, [(HEAD_ONLY, VARIANT, "git commit")]),
    "a file at the row's path": (
        beside_a_file_at(ROW), [(IN_INDEX, ROW, "git update-index"),
                                (IN_INDEX, ROW, "git rm -r --cached aside")]),
    "a file under the row's path": (
        beside_a_file_at(f"{ROW}/x"),
        [(IN_INDEX, ROW, "git update-index"),
         (IN_INDEX, f"{ROW}/x", "git rm -r --cached aside")]),
    "unmerged, with no gitlink at stage 2": (
        unmerged_theirs, [(IN_INDEX, VARIANT, "git rm -r --cached")]),
    "unmerged, with a file at stage 2 and gitlinks at 1 and 3": (
        unmerged_file_ours, [(IN_INDEX, VARIANT, "git rm -r --cached")]),
    "the member's own gitlink": (
        lambda root: plant(root, "160000", VARIANT),
        [(IN_INDEX, ROW, "git update-index")]),
}


@pytest.mark.parametrize("state", list(OWN))
def test_only_the_members_own_gitlink_is_moved_back(holder, family_module,
                                                    state):
    """WHICH PATH IS THE MEMBER'S OWN: a gitlink at a case variant of a
    row's path, where the index holds nothing at or under that path but
    files (#761), which are set aside first. A second gitlink beside the
    row's, a file at the variant, a gitlink under it, or an unmerged variant
    with no gitlink at stage 2 (none, or a file there, whatever stages 1
    and 3 hold) keeps #574's remedy."""
    make, said = OWN[state]
    if state != "a second gitlink beside the row's":
        git("rm", "-q", "--cached", "--", ROW, cwd=holder)
    make(holder)
    rows = family_module._rows_paths(family_module.Family.open(holder).members)
    assert [(spelled.where, spelled.target, spelled.remedy)
            for spelled in family_module._members_spellings(
                holder, SPARE, family_module._members_on_disk(holder),
                rows)] == said


def test_the_rows_that_have_a_path_of_their_own(family_module):
    """`_rows_paths`: `members/<project>` for every row with that path, or
    no `path:` at all; none for a row whose `path:` is another, or whose
    project is no single directory name, which `member-path` refuses."""
    assert family_module._rows_paths([
        {"project": "IRRS"}, {"project": "IRSS", "path": OTHER_ROW},
        {"project": "Elsewhere", "path": "elsewhere/Elsewhere"},
        {"project": ".."}, {"project": 7}, {}]) == frozenset(
        {ROW, OTHER_ROW})
