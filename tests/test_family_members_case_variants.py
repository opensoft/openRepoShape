# SPDX-License-Identifier: Apache-2.0
"""`family.py add` refuses a case variant of `members/` on every disk, before
the member is read (#362, #363, #364).

BRETT HEAP'S RULING OF 2026-10-14, "Refuse on every disk": "Refuse before
reading the member, naming the entries and a committed `git mv` as the
remedy, with one rule for index, HEAD and disk. Linux, macOS and Windows give
the same answer, matching #318's any-case rule for the mount path. Cost: a
Linux holder with its own `Members/` folder must rename it first."

THREE PLACES, ONE RULE. Before it, a path under `Members/` (any spelling of
`members` but `members` itself) was let through by design (#318), and:

- in the INDEX, with `core.ignorecase` set, git staged the new gitlink as
  `Members/<P>`, the add's commit matched nothing, and the remedy its closing
  sentence printed failed the same way every time (#362);
- in HEAD and no longer in the index, a `git rm -r Members` not committed
  yet, `add` committed the gitlink as `Members/<P>` with exit 0 while
  `.gitmodules` and `family.yaml` said `members/<P>`, and every fresh clone
  left the member empty (#363);
- on DISK, untracked, `_checked_mount_path`'s exact `lexists` refused
  `Members/<P>` on macOS and Windows and mounted the member beside it on
  Linux (#364).

Each is refused now, naming every path in its own spelling and where it was
found, `member-path-taken` where it is a case variant of the mount path and
`family-members-dir-variant` where it is under a spelling of `members/`
alone, and the holder is left exactly as it was. EVERY PRINTED REMEDY IS
TYPED AS PRINTED here (`type_remedy`), and the same `add` then goes through.

ONE ENTRY AT A TIME, NEVER THE OTHER SPELLING'S DIRECTORY (#574's review,
B1). On macOS and Windows a `Members/` and `members/` are ONE directory, and
it holds the members' own checkouts: a `git mv` of `Members` would take
them all. So the remedy renames, removes or moves the entries under it, and
the text is the same on all three systems. Where that one directory is
spelled `Members` on such a disk, `members/` itself is it
(`_members_dir_on_disk`, asked with `isdir` and `samefile`), so what it holds
is no variant; on Linux a `Members/` is always another directory (Codex's P2
on #574).

EVERY TEST RUNS ON ALL THREE SYSTEMS. An index or HEAD variant is planted
with `update-index --cacheinfo`, with nothing on disk. A disk state is made
in a holder with no `members/` yet (`unborn_holder`), or by renaming the
holder's `members/` in place, so no test makes two directories whose names
differ only in case. What the disk answers is either the same everywhere,
asserted for the disk the test runs on (`disk_folds`), or asked in process
of a disk that folds case and of one that does not (`disk_as`), each
emulated below the holder alone, so both answers are asserted on every OS.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import git
from test_family import SPARE, family  # noqa: F401
from test_family_add_refusals import (  # noqa: F401
    family_module, holder, index_bytes, offline, plant, refusal, snapshot,
    unborn_holder,
)

#: `add`'s mount path for the spare member.
MOUNT = f"members/{SPARE}"

#: The first sentence of each refusal, before ` — ` and the places it names.
DIR_VARIANT = (
    "REFUSED family-members-dir-variant: the family root holds a path at or "
    "under another spelling of members/, which a case-insensitive disk takes "
    "for members/ itself — ")
MOUNT_VARIANT = (
    f"REFUSED member-path-taken: the family root holds a case variant of "
    f"{MOUNT}, the same path on a case-insensitive disk, though no "
    "`members:` row names it — ")

#: The mount path itself on disk, as it was always refused.
TAKEN = (f"REFUSED member-path-taken: {MOUNT} already exists in the family "
         "root but no `members:` row names it",
         "Remediation: this is a half-finished add or a hand-made directory. "
         "Remove it (`git rm -r` if it is tracked), then re-run.")

#: What a printed `--sparse` says it needs (#685): `git mv --sparse` of the
#: one entry a sparse checkout keeps off disk says `bad source` before git
#: 2.38, and `git rm --sparse` came with git 2.34.
NEEDS_GIT_2_38 = "which needs git 2.38 or later"
NEEDS_GIT_2_34 = "which needs git 2.34 or later"

#: The part of the remedy for a `members/` a hand renamed `Members/`.
MOVE_BACK = ("move `Members` back to members/, since it holds checkouts of "
             "members git tracks under members/ (`mv -- Members members`)")


def each(command: str, targets) -> str:
    """One printed `<command> -- <target> <new name>` for each target."""
    return " and ".join(f"`{command} -- {target} <new name>`"
                        for target in targets)


def index_part(*, rename=(), sparse=(), unstage=(), commit="") -> str:
    """The part of the remedy for what the index holds."""
    said = []
    if rename:
        said.append("rename what the index holds with `git mv`, entry by "
                    f"entry ({each('git mv', rename)})")
    if sparse:
        said.append("rename what the sparse checkout leaves out with "
                    f"`git mv --sparse`, {NEEDS_GIT_2_38}, entry by entry "
                    f"({each('git mv --sparse', sparse)})")
    if unstage:
        said.append("take what has nothing on disk in that spelling out of "
                    "the index, which touches no file (`git rm -r --cached -- "
                    + " ".join(unstage) + "`)")
    return ", ".join(said) + (f", and commit {commit}" if commit else "")


def commit_first(*targets: str) -> str:
    """The part for what HEAD holds and the index no longer does."""
    named = ", ".join(f"`{target}`" for target in targets)
    return ("commit the pending change first (`git commit`), since the add's "
            f"own commit names .gitmodules, {MOUNT} and family.yaml alone: "
            f"HEAD would keep {named} beside the member, or, with "
            "`core.ignorecase` set, record the member's gitlink in that "
            "spelling")


def move(*targets: str) -> str:
    """The part for what is on disk and untracked."""
    return ("move what is on disk and untracked out of the way "
            f"({each('mv', targets)})")


def remedy_of(*parts: str) -> str:
    """The remedy line: its parts, in the order they are to be run, between
    what every remedy begins and ends with."""
    said = "; ".join(parts)
    return ("Remediation: every member is mounted under members/, and a "
            "holder keeps that directory in one spelling on every disk. "
            + said[0].upper() + said[1:] + "; then re-run.")


def refused_untouched(offline, root, remotes, *extra, status=True):
    """`add` of the spare member, refused before anything about the member
    is printed or read, with the holder exactly as it was: the snapshot, the
    index byte for byte, no `gh` call and no throwaway clone left. Returns
    the refusal's two lines.

    `status=False` is passed to `snapshot`, which then asks no `git status`,
    for a holder where git 2.45.1 and later refuse it: a gitlink the index
    holds that is a symbolic link on disk (`expected submodule path
    'Members/IRRS' not to be a symbolic link`). The rest of the snapshot is
    kept."""
    before, index = snapshot(root, status=status), index_bytes(root)
    result = offline.add(root, SPARE, *extra, remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert index_bytes(root) == index
    assert snapshot(root, status=status) == before
    offline.assert_left_nothing()
    return refusal(result.stderr)


def type_remedy(root: Path, remedy: str) -> list[str]:
    """EVERY COMMAND THE REMEDY PRINTS, TYPED AS PRINTED, in its order, and
    the commit each part asks for: the printed `git commit`, and one where a
    part ends "and commit ...". Only `<new name>` is filled in: `renamed-N`
    for a `git mv`, which is committed and stays, and `../moved-N` for a
    `mv`, so what is untracked leaves the holder. Returns what was typed."""
    typed: list[str] = []
    count = {"git": 0, "mv": 0}
    for part in remedy.split(" on every disk. ", 1)[1].split("; "):
        for command in re.findall(r"`([^`]*)`", part):
            if command == "git commit":
                git("commit", "-qm", "The pending change", cwd=root)
            elif " -- " in command:
                if "<new name>" in command:
                    tool = command.partition(" ")[0]
                    count[tool] += 1
                    command = command.replace(
                        "<new name>", f"renamed-{count['git']}"
                        if tool == "git" else f"../moved-{count['mv']}")
                argv = shlex.split(command)
                if argv[0] == "git":
                    git(*argv[1:], cwd=root)
                else:
                    os.rename(root / argv[2], root / argv[3])
            else:
                continue
            typed.append(command)
        if re.search(r", and commit (the rename|the removal|both)$", part):
            git("commit", "-qm", "The remedy", cwd=root)
            typed.append("git commit")
    return typed


def mounted_alone(root) -> None:
    """After the add: HEAD holds the spare member's gitlink at its mount
    path and nothing at or under any other spelling of `members/` but the
    members it held before, and the working tree is clean."""
    held = [line for line in git("ls-tree", "-r", "--name-only", "HEAD",
                                 cwd=root).stdout.splitlines()
            if line.split("/", 1)[0].lower() == "members"]
    assert [name for name in held if not name.startswith("members/")] == []
    assert MOUNT in held
    assert git("ls-tree", "HEAD", MOUNT, cwd=root).stdout.startswith(
        "160000 commit ")
    assert git("status", "--porcelain", cwd=root).stdout == ""


def added(offline, root, remotes) -> None:
    """The same `add` again, through, and the member mounted alone."""
    again = offline.add(root, SPARE, remotes=remotes)
    assert again.returncode == 0, again.stdout + again.stderr
    mounted_alone(root)
    offline.assert_left_nothing()


def disk_folds(directory: Path) -> bool:
    """Does the disk `directory` is on fold case, as macOS's and Windows'
    do by default? Asked with one directory, so none is ever made twice."""
    probe = directory / "Case-Probe"
    probe.mkdir()
    try:
        return os.path.isdir(directory / "case-probe")
    finally:
        probe.rmdir()


def commit_bytes(root: Path, made: str) -> None:
    """`made` written as BYTES, and committed with `family.yaml`."""
    (root / made).parent.mkdir(parents=True, exist_ok=True)
    (root / made).write_bytes(b"our own notes\n")
    git("add", "--", "family.yaml", made, cwd=root)
    git("commit", "-qm", f"Notes at {made}", cwd=root)


# --- the index (#362) --------------------------------------------------------

@pytest.mark.parametrize("ignorecase", ["true", "false"])
@pytest.mark.parametrize("name, target", [
    ("Members/README", "Members/README"),
    ("MEMBERS/notes/a", "MEMBERS/notes"),
    ("Members", "Members"),
    # `irrs` is what `members/IRRS` holds on a disk that folds case: the
    # remedy names the entry itself, never that directory.
    ("Members/irrs/a", "Members/irrs/a"),
])
def test_an_index_entry_with_nothing_on_disk_is_taken_out_of_the_index(
        family, holder, offline, name, target, ignorecase):
    """THE ISSUE'S STATE (#362): the index holds a path under `Members/`, or
    `Members` itself, and nothing is on disk in that spelling. With
    `core.ignorecase` set git stages the gitlink as `Members/IRQS` and the
    commit matches nothing; without it the add commits and leaves `Members/`
    beside the member. Refused both ways, before the member is read, and
    `--dry-run` refuses it alike. `git mv` of an entry with nothing on disk
    fails (`bad source`), so it is taken out of the index, touching no file,
    as #318 takes out a variant of the mount path; staged and never
    committed, it leaves nothing to commit. Typed as printed, it lets the
    same `add` through."""
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    plant(holder, "100644", name)
    said = (DIR_VARIANT + f"in the index: `{name}` (a file)",
            remedy_of(index_part(unstage=[target])))
    assert refused_untouched(offline, holder, family["remotes"],
                             "--dry-run") == said
    assert refused_untouched(offline, holder, family["remotes"]) == said
    assert type_remedy(holder, said[1]) == [
        f"git rm -r --cached -- {target}"]
    added(offline, holder, family["remotes"])


#: What a holder with no `members/` yet commits, its file on disk, as
#: `(the code's first sentence, what the index names, the path renamed,
#: where the file is after the rename)`.
TRACKED = {
    "Members/README": (DIR_VARIANT, "Members/README", "renamed-1"),
    "Members": (DIR_VARIANT, "Members", "renamed-1"),
    "Members/docs/notes": (DIR_VARIANT, "Members/docs", "renamed-1/notes"),
    # #318's state with its file on disk: one round, not three.
    f"Members/{SPARE}/README": (MOUNT_VARIANT, f"Members/{SPARE}",
                                "renamed-1/README"),
}


@pytest.mark.parametrize("made", list(TRACKED))
def test_a_tracked_path_on_disk_takes_one_committed_git_mv(family, offline,
                                                           tmp_path, made):
    """THE STATE ON A REAL DISK: a path under `Members/`, or a file
    `Members`, committed with its file on disk. Brett Heap's ruling names
    "a committed `git mv`" as the remedy, and this is it: the entry directly
    under the other spelling is renamed, never that spelling's directory,
    and the rename committed. One round does it, #318's tracked
    `Members/IRQS/...` included, which used to take `git rm --cached`, a
    commit, then a `mv` (#574's review, S3). On macOS and Windows `Members`
    is `members/` itself here, and the text is the same. The `git mv` leaves
    an empty `Members/` on Linux, which holds nothing and is not named."""
    first, target, renamed = TRACKED[made]
    root = unborn_holder(tmp_path)
    commit_bytes(root, made)
    said, remedy = refused_untouched(offline, root, family["remotes"])
    assert said == first + f"in the index: `{made}` (a file)"
    assert remedy == remedy_of(index_part(rename=[target],
                                          commit="the rename"))
    assert type_remedy(root, remedy) == [f"git mv -- {target} renamed-1",
                                         "git commit"]
    added(offline, root, family["remotes"])
    assert git("show", f"HEAD:{renamed}", cwd=root).stdout == (
        "our own notes\n")


def test_a_tracked_file_deleted_from_disk_is_taken_out_and_committed(
        family, offline, tmp_path):
    """` D Members/README`, what an `rm -rf Members` of a committed file
    leaves (#574's review, S2): `git mv` says `bad source`, so the entry is
    taken out of the index and, since HEAD holds it, that removal is
    committed. The empty `Members/` an `rm` of the file leaves on Linux
    holds nothing, and is not named."""
    root = unborn_holder(tmp_path)
    commit_bytes(root, "Members/README")
    (root / "Members" / "README").unlink()
    said, remedy = refused_untouched(offline, root, family["remotes"])
    assert said == DIR_VARIANT + "in the index: `Members/README` (a file)"
    assert remedy == remedy_of(index_part(unstage=["Members/README"],
                                          commit="the removal"))
    assert type_remedy(root, remedy) == [
        "git rm -r --cached -- Members/README", "git commit"]
    added(offline, root, family["remotes"])


def git_version() -> tuple[int, int]:
    """This host's git, as `(major, minor)`."""
    found = re.match(r"git version (\d+)\.(\d+)",
                     git("--version", cwd=Path.cwd()).stdout)
    return int(found.group(1)), int(found.group(2))


def test_an_entry_a_sparse_checkout_keeps_off_disk_takes_git_mv_sparse(
        family, holder, offline):
    """A SPARSE CHECKOUT (#574's review, S2): an entry the checkout keeps
    off disk (`skip-worktree`) is refused by `git mv` as `not under version
    control` and by `git rm --cached` as outside the sparse-checkout
    definition. `git mv --sparse` renames it, keeping what it holds, and the
    rename is committed. The text says that needs git 2.38 or later, on
    every git (#685); it is typed only there."""
    plant(holder, "100644", "Members/README")
    git("update-index", "--skip-worktree", "--", "Members/README", cwd=holder)
    said, remedy = refused_untouched(offline, holder, family["remotes"])
    assert said == DIR_VARIANT + "in the index: `Members/README` (a file)"
    assert remedy == remedy_of(index_part(sparse=["Members/README"],
                                          commit="the rename"))
    if git_version() < (2, 38):
        pytest.skip("`git mv --sparse` of one entry kept off disk says `bad "
                    "source` before git 2.38")
    assert type_remedy(holder, remedy) == [
        "git mv --sparse -- Members/README renamed-1", "git commit"]
    added(offline, holder, family["remotes"])


def test_every_place_is_named_and_the_pending_change_is_committed_first(
        family, holder, offline):
    """TWO PLACES AT ONCE: the index holds `Members/README`, staged, and
    HEAD holds `MEMBERS/old`, which the index no longer does. Both are
    named, each where it was found, and the pending change is committed
    first, since that commit is what takes `MEMBERS/old` out of HEAD. It
    commits `Members/README` too, so its removal from the index is a change
    to commit after it."""
    plant(holder, "100644", "MEMBERS/old")
    git("commit", "-qm", "Track MEMBERS/old", cwd=holder)
    git("rm", "-q", "--cached", "--", "MEMBERS/old", cwd=holder)
    plant(holder, "100644", "Members/README")
    said, remedy = refused_untouched(offline, holder, family["remotes"])
    assert said == (DIR_VARIANT + "in the index: `Members/README` (a file); "
                    "in HEAD and no longer in the index: `MEMBERS/old` (a "
                    "file)")
    assert remedy == remedy_of(
        commit_first("MEMBERS/old"),
        index_part(unstage=["Members/README"], commit="the removal"))
    assert type_remedy(holder, remedy) == [
        "git commit", "git rm -r --cached -- Members/README", "git commit"]
    added(offline, holder, family["remotes"])


def test_more_than_five_paths_in_one_place_are_counted(family, holder,
                                                       offline):
    """Five names in each place at most, then a count, as the unwind's
    sentence names an index that moved; the remedy still names every
    entry it acts on."""
    for n in range(1, 8):
        plant(holder, "100644", f"Members/{n}")
    shown = ", ".join(f"`Members/{n}` (a file)" for n in range(1, 6))
    assert refused_untouched(offline, holder, family["remotes"]) == (
        DIR_VARIANT + f"in the index: {shown} and 2 more",
        remedy_of(index_part(unstage=[f"Members/{n}" for n in range(1, 8)])))


# --- HEAD, and no longer the index (#363) ------------------------------------

#: What HEAD holds and the index no longer does, as `(mode, name, the code's
#: first sentence, kind)`.
HEAD_ONLY = {
    "a file under Members/": ("100644", "Members/README.md", DIR_VARIANT,
                              "a file"),
    "a variant of the mount path": ("160000", f"members/{SPARE.lower()}",
                                    MOUNT_VARIANT, "a submodule"),
}


@pytest.mark.parametrize("ignorecase", ["true", "false"])
@pytest.mark.parametrize("state", list(HEAD_ONLY))
def test_what_head_holds_and_the_index_no_longer_does_is_committed_first(
        family, holder, offline, state, ignorecase):
    """THE ISSUE'S STATE (#363): HEAD holds a path under `Members/`, and a
    removal of it is staged and not committed. `add` used to commit the
    gitlink as `Members/IRQS` with exit 0, `.gitmodules` and `family.yaml`
    saying `members/IRQS`, and a fresh clone of the pushed holder left the
    member empty. A case variant of the mount path itself in HEAD is the
    same fault under `member-path-taken`. Refused on every disk, before the
    member is read; committing the removal, as the remedy says, lets the
    same `add` through with the member under `members/` alone."""
    mode, name, first, kind = HEAD_ONLY[state]
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    plant(holder, mode, name)
    git("commit", "-qm", f"Track {name}", cwd=holder)
    git("rm", "-q", "--cached", "--", name, cwd=holder)
    said, remedy = refused_untouched(offline, holder, family["remotes"])
    assert said == first + f"in HEAD and no longer in the index: `{name}` " \
                           f"({kind})"
    assert remedy == remedy_of(commit_first(name))
    assert type_remedy(holder, remedy) == ["git commit"]
    added(offline, holder, family["remotes"])


def test_a_name_head_holds_that_is_not_utf8_is_shown_replaced(
        holder, family_module):
    """A name in HEAD that is not UTF-8 is shown as the index's names are,
    with U+FFFD, never as a lone surrogate a stream may not encode. Planted
    through `update-index --index-info`, BYTES on its stdin, committed by
    `write-tree` and `commit-tree`, which never look for it on disk, and
    taken out of the index the same way, so no argument needs those
    bytes."""
    oid = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                         cwd=str(holder), input=b"a file\n",
                         capture_output=True, check=True).stdout.strip()

    def index_info(line: bytes) -> None:
        subprocess.run(["git", "-c", "core.protectNTFS=false", "update-index",
                        "--index-info"], cwd=str(holder), input=line,
                       capture_output=True, check=True)

    index_info(b"100644 " + oid + b"\tMembers/\xff\n")
    tree = git("write-tree", cwd=holder).stdout.strip()
    commit = git("commit-tree", tree, "-p", "HEAD", "-m",
                 "A name that is not UTF-8", cwd=holder).stdout.strip()
    git("update-ref", "HEAD", commit, cwd=holder)
    index_info(b"0 " + b"0" * 40 + b"\tMembers/\xff\n")
    assert family_module._members_spellings(
        holder, SPARE, family_module._members_on_disk(holder)) == [
        ("Members/\N{REPLACEMENT CHARACTER}", "a file",
         "in HEAD and no longer in the index",
         "Members/\N{REPLACEMENT CHARACTER}", False, "git commit", True, "",
         False, "", False, (), False)]


# --- the disk (#364) ---------------------------------------------------------

#: What is on disk and untracked in a holder with no `members/` yet, the
#: same on every disk, as `(the file made, the refusal, its remedy)`.
ON_DISK = {
    "a variant of the mount path under members/": (
        f"members/{SPARE.lower()}/notes.txt",
        MOUNT_VARIANT + "on disk and untracked: "
        f"`members/{SPARE.lower()}` (a directory)",
        move(f"members/{SPARE.lower()}")),
    "a file named Members": (
        "Members", DIR_VARIANT + "on disk and untracked: `Members` (a file)",
        move("Members")),
}


@pytest.mark.parametrize("state", list(ON_DISK))
def test_an_untracked_path_on_disk_is_moved_out_of_the_way(family, offline,
                                                           tmp_path, state):
    """THE ISSUE'S STATE (#364), where every disk holds the same thing: a
    case variant of the mount path under `members/` itself, and a file
    named `Members`, which no disk takes for a directory. The disk is listed,
    one level at a time, so each OS sees the name in the spelling it keeps
    and says the same thing. The printed `mv`, typed, lets the same `add`
    through. The holder has no commit yet, so HEAD is unborn."""
    made, said, part = ON_DISK[state]
    root = unborn_holder(tmp_path)
    (root / made).parent.mkdir(parents=True, exist_ok=True)
    (root / made).write_bytes(b"our own notes\n")
    assert refused_untouched(offline, root, family["remotes"]) == (
        said, remedy_of(part))
    assert (root / made).read_bytes() == b"our own notes\n"
    assert type_remedy(root, remedy_of(part)) == ["mv -- {} ../moved-1".format(
        made.partition("/notes.txt")[0])]
    added(offline, root, family["remotes"])


#: An untracked directory spelled `Members` in a holder with no `members/`
#: yet: `members/` itself on a disk that folds case, another directory on
#: Linux. `(the file made, Linux's refusal and remedy, the folding disk's)`;
#: None where the folding disk lets the add through.
OTHER_SPELLING = {
    "a variant of the mount path under Members/": (
        f"Members/{SPARE}/notes.txt",
        (MOUNT_VARIANT + f"on disk and untracked: `Members/{SPARE}` (a "
         "directory)", remedy_of(move(f"Members/{SPARE}"))),
        TAKEN),
    "a file under Members/": (
        "Members/README.md",
        (DIR_VARIANT + "on disk and untracked: `Members/README.md` (a file)",
         remedy_of(move("Members/README.md"))),
        None),
}


@pytest.mark.parametrize("state", list(OTHER_SPELLING))
def test_an_untracked_members_directory_is_moved_entry_by_entry_on_linux(
        family, offline, tmp_path, state):
    """THE ISSUE'S STATE (#364) under `Members/`, which the disk decides. On
    Linux a `Members/` is never `members/`: each entry in it is named and
    moved, never the directory, and the empty directory left is not named.
    On macOS and Windows that `Members` IS `members/`: a `Members/IRQS` is
    the mount path itself, `already exists` as it always was, and a
    `Members/README.md` is a file in `members/`, as harmless as it is under
    that spelling on Linux. Each answer, done as it says, lets the same
    `add` through."""
    made, linux, folding = OTHER_SPELLING[state]
    root = unborn_holder(tmp_path)
    (root / made).parent.mkdir(parents=True)
    (root / made).write_bytes(b"our own notes\n")
    folds = disk_folds(root)
    said = folding if folds else linux
    if said is not None:
        assert refused_untouched(offline, root, family["remotes"]) == said
    if said is TAKEN:
        shutil.rmtree(root / "Members" / SPARE)
    elif said is not None:
        assert len(type_remedy(root, said[1])) == 1
    result = offline.add(root, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert git("ls-tree", "-r", "--name-only", "HEAD",
               cwd=root).stdout.split() == [".gitmodules", "family.yaml",
                                            MOUNT]
    assert os.path.exists(root / made) is (folds and said is None)


@pytest.mark.skipif(os.name == "nt", reason="a symlink needs a privilege "
                                            "Windows runners do not grant")
def test_a_spelling_that_is_a_link_is_named_and_not_entered(family, offline,
                                                            tmp_path):
    """A `Members` that is a LINK to a directory holding `IRQS` is named
    as the link it is and moved, link and all, and what it points at is
    not entered: no disk takes a link for `members/` itself."""
    elsewhere = tmp_path / "elsewhere"
    (elsewhere / SPARE).mkdir(parents=True)
    root = unborn_holder(tmp_path)
    os.symlink(elsewhere, root / "Members", target_is_directory=True)
    said, remedy = refused_untouched(offline, root, family["remotes"])
    assert said == DIR_VARIANT + "on disk and untracked: `Members` (a symlink)"
    assert remedy == remedy_of(move("Members"))
    assert type_remedy(root, remedy) == ["mv -- Members ../moved-1"]
    added(offline, root, family["remotes"])
    assert (elsewhere / SPARE).is_dir()


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="a directory nobody may list needs POSIX "
                           "permissions, which root does not obey")
def test_another_spelling_nobody_may_list_is_named_and_moved_whole(
        family, offline, tmp_path):
    """A `Members/` this user may not list cannot be named entry by entry,
    and is not empty for all anyone can tell: on Linux it is named, and
    moved, whole. (On a disk that folds case that `Members` is `members/`
    itself, which nothing names.)"""
    if disk_folds(tmp_path):
        pytest.skip("on a disk that folds case this Members is members/")
    root = unborn_holder(tmp_path)
    (root / "Members").mkdir()
    (root / "Members" / "notes.txt").write_bytes(b"our own notes\n")
    (root / "Members").chmod(0o300)
    try:
        said, remedy = refused_untouched(offline, root, family["remotes"])
        assert type_remedy(root, remedy) == ["mv -- Members ../moved-1"]
    finally:
        for left in (root / "Members", tmp_path / "moved-1"):
            if left.is_dir():
                left.chmod(0o755)
    assert said == DIR_VARIANT + "on disk and untracked: `Members` (a " \
                                 "directory)"
    assert remedy == remedy_of(move("Members"))
    added(offline, root, family["remotes"])


@pytest.mark.skipif(os.name == "nt" or os.geteuid() == 0,
                    reason="a directory nobody may list needs POSIX "
                           "permissions, which root does not obey")
def test_a_members_directory_nobody_may_list_still_hides_nothing(
        family_module, tmp_path):
    """`lexists` IS STILL ASKED, LAST. A `members/` this user may enter and
    not list hides `members/IRQS` from every listing, and the path itself
    still answers: refused `already exists`, as it always was."""
    root = unborn_holder(tmp_path)
    (root / MOUNT).mkdir(parents=True)
    (root / "members").chmod(0o300)
    try:
        with pytest.raises(family_module.Refusal) as caught:
            family_module._checked_mount_path(root, SPARE, MOUNT)
    finally:
        (root / "members").chmod(0o755)
    assert (caught.value.code, caught.value.detail) == (
        "member-path-taken", f"{MOUNT} already exists in the family root but "
        "no `members:` row names it")


# --- one directory or two: what each disk answers ----------------------------

def disk_as(monkeypatch, root: Path, folding: bool) -> None:
    """`os.path.isdir`, `os.path.samefile` and `os.path.lexists` answer,
    BELOW `root` ONLY, as a disk that folds case answers them (macOS's and
    Windows' by default) or as one that does not (Linux's), whatever disk
    the test runs on: each component is found in its parent's listing,
    exactly, or, folding, in any case. Listings stay exact; both kinds of
    disk list a name in the spelling they keep."""
    real_isdir, real_samefile, real_lexists = (
        os.path.isdir, os.path.samefile, os.path.lexists)

    def resolved(path) -> Path | None:
        path = Path(path)
        try:
            parts = path.relative_to(root).parts
        except ValueError:
            return path
        here = root
        for part in parts:
            try:
                names = os.listdir(here)
            except OSError:
                return path
            same = [name for name in names if name == part
                    or (folding and name.lower() == part.lower())]
            if not same:
                return None
            here = here / same[0]
        return here

    def samefile(first, second) -> bool:
        one, other = resolved(first), resolved(second)
        if one is None or other is None:
            raise FileNotFoundError(first if one is None else second)
        return real_samefile(one, other)

    monkeypatch.setattr(os.path, "isdir",
                        lambda path: resolved(path) is not None
                        and real_isdir(resolved(path)))
    monkeypatch.setattr(os.path, "samefile", samefile)
    monkeypatch.setattr(os.path, "lexists",
                        lambda path: resolved(path) is not None
                        and real_lexists(resolved(path)))


def renamed_members(root: Path) -> None:
    """The holder's `members/` renamed `Members/` in place, the members'
    checkouts in it: what a case-insensitive checkout of a holder that held
    `Members/README` beside them makes, and, on Linux, Codex's state, a
    `members/` a hand renamed with nothing staged."""
    os.rename(root / "members", root / "Members")


def with_file(made: str, staged: bool = False):
    """A layout: `members/` renamed, and `made` written there, as BYTES,
    planted in the index too where `staged`."""
    def lay_out(root: Path) -> None:
        renamed_members(root)
        (root / made).parent.mkdir(parents=True, exist_ok=True)
        (root / made).write_bytes(b"our own notes\n")
        if staged:
            plant(root, "100644", made)
    return lay_out


def human_members(root: Path) -> None:
    """`members/` gone from disk, and a human's own `Members/` holding a
    `README.md` and a directory named like the member IRRS, with no
    checkout in it."""
    shutil.rmtree(root / "members")
    (root / "Members" / "IRRS").mkdir(parents=True)
    (root / "Members" / "IRRS" / "notes").write_bytes(b"our own notes\n")
    (root / "Members" / "README.md").write_bytes(b"our own notes\n")


def gitlink_named_members(root: Path) -> None:
    """`members/` renamed, and a gitlink `Members` in the index: on a disk
    that folds case, the directory that holds the members. (No Linux
    checkout makes it: a gitlink there would be its own directory.)"""
    renamed_members(root)
    plant(root, "160000", "Members")


def file_named_members_in_the_index(root: Path) -> None:
    """A file `Members` in the index, nothing of it on disk, beside the
    holder's `members/`, which a disk that folds case resolves it to."""
    plant(root, "100644", "Members")


def variant_in_members(root: Path) -> None:
    """An untracked `members/irqs`, under `members/` itself."""
    (root / "members" / SPARE.lower()).mkdir()
    (root / "members" / SPARE.lower() / "x").write_bytes(b"x\n")


def linked_members(root: Path) -> None:
    """`members/` gone, and a LINK `Members` to a directory outside the
    holder: a disk that folds case resolves `members` through it, and it is
    still never `members/` itself, but a link, named and moved."""
    if os.name == "nt":
        pytest.skip("a symlink needs a privilege Windows runners do not grant")
    shutil.rmtree(root / "members")
    (root.parent / "elsewhere").mkdir()
    os.symlink(root.parent / "elsewhere", root / "Members",
               target_is_directory=True)


def every_index_remedy(root: Path) -> None:
    """`members/` renamed, and three entries under `Members/` committed: a
    gitlink `X` with its directory on disk, renamed; a file `README` where
    the disk holds a directory, taken out of the index, which HEAD holds, so
    the removal is committed too; and `docs/a`, which a sparse checkout
    keeps off disk, renamed with `--sparse` by the entry itself."""
    renamed_members(root)
    (root / "Members" / "README").mkdir()
    (root / "Members" / "README" / "inner").write_bytes(b"x\n")
    (root / "Members" / "X").mkdir()
    plant(root, "100644", "Members/README")
    plant(root, "160000", "Members/X")
    plant(root, "100644", "Members/docs/a")
    git("update-index", "--skip-worktree", "--", "Members/docs/a", cwd=root)
    git("commit", "-qm", "Entries under Members/", cwd=root)


def gitlink_over_a_human_members(root: Path) -> None:
    """`members/` gone, a human's `Members/notes.txt`, and a gitlink
    `Members` in the index: what is under that entry is the index's to
    name, never a second time on disk."""
    shutil.rmtree(root / "members")
    (root / "Members").mkdir()
    (root / "Members" / "notes.txt").write_bytes(b"our own notes\n")
    plant(root, "160000", "Members")


IN_MEMBERS_README = DIR_VARIANT + "in the index: `Members/README` (a file)"
IN_MEMBERS_IRQS = (MOUNT_VARIANT + f"in the index: `Members/{SPARE}/README` "
                   "(a file)")
UNDER_MEMBERS_IRQS = f"on disk and untracked: `Members/{SPARE.lower()}` (a " \
                     "directory)"
MOVED_BACK_TOO = "; on disk and untracked: `Members` (a directory)"
LINKED = (DIR_VARIANT + "on disk and untracked: `Members` (a symlink)",
          remedy_of(move("Members")))
EVERY_INDEX = (DIR_VARIANT + "in the index: `Members/README` (a file), "
               "`Members/X` (a submodule), `Members/docs/a` (a file)")
EVERY_INDEX_REMEDY = index_part(
    rename=["Members/X"], sparse=["Members/docs/a"],
    unstage=["Members/README"], commit="both")
IRQS_FILE = MOUNT_VARIANT + f"in the index: `Members/{SPARE}` (a file)"
IRQS_FILE_REMEDY = index_part(rename=[f"Members/{SPARE}"], commit="the rename")
GITLINK_MEMBERS = DIR_VARIANT + "in the index: `Members` (a submodule)"

#: `{layout: (how it is made, Linux's answer, the folding disk's answer)}`,
#: each answer the refusal's two lines, None where the check passes, and
#: `...` for a layout that disk never holds.
LAYOUTS = {
    "members/ renamed Members (Codex's P2)": (
        renamed_members,
        (DIR_VARIANT + "on disk and untracked: `Members` (a directory)",
         remedy_of(MOVE_BACK)),
        None),
    "and Members/README in the index (#362, B1)": (
        with_file("Members/README", staged=True),
        (IN_MEMBERS_README + "; on disk and untracked: `Members` (a "
         "directory)",
         remedy_of(index_part(rename=["Members/README"], commit="the rename"),
                   MOVE_BACK)),
        (IN_MEMBERS_README,
         remedy_of(index_part(rename=["Members/README"],
                              commit="the rename")))),
    "and an untracked Members/IRQS": (
        with_file(f"Members/{SPARE}/leftover"),
        (MOUNT_VARIANT + f"on disk and untracked: `Members/{SPARE}` (a "
         "directory), `Members` (a directory)",
         remedy_of(move(f"Members/{SPARE}"), MOVE_BACK)),
        TAKEN),
    "and Members/IRQS/README in the index (#318)": (
        with_file(f"Members/{SPARE}/README", staged=True),
        (IN_MEMBERS_IRQS + "; on disk and untracked: `Members` (a directory)",
         remedy_of(index_part(rename=[f"Members/{SPARE}"],
                              commit="the rename"), MOVE_BACK)),
        (IN_MEMBERS_IRQS,
         remedy_of(index_part(rename=[f"Members/{SPARE}"],
                              commit="the rename")))),
    "and an untracked Members/irqs": (
        with_file(f"Members/{SPARE.lower()}/x"),
        (MOUNT_VARIANT + UNDER_MEMBERS_IRQS + ", `Members` (a directory)",
         remedy_of(move(f"Members/{SPARE.lower()}"), MOVE_BACK)),
        (MOUNT_VARIANT + UNDER_MEMBERS_IRQS,
         remedy_of(move(f"Members/{SPARE.lower()}")))),
    "and a gitlink named Members in the index": (
        gitlink_named_members, ...,
        (DIR_VARIANT + "in the index: `Members` (a submodule)",
         remedy_of(index_part(unstage=["Members"])))),
    "a human's own Members/, no members/": (
        human_members,
        (DIR_VARIANT + "on disk and untracked: `Members/IRRS` (a directory), "
         "`Members/README.md` (a file)",
         remedy_of(move("Members/IRRS", "Members/README.md"))),
        None),
    "a file Members in the index, beside members/": (
        file_named_members_in_the_index,
        (DIR_VARIANT + "in the index: `Members` (a file)",
         remedy_of(index_part(unstage=["Members"]))),
        (DIR_VARIANT + "in the index: `Members` (a file)",
         remedy_of(index_part(unstage=["Members"])))),
    "an untracked members/irqs": (
        variant_in_members,
        (MOUNT_VARIANT + f"on disk and untracked: `members/{SPARE.lower()}` "
         "(a directory)", remedy_of(move(f"members/{SPARE.lower()}"))),
        (MOUNT_VARIANT + f"on disk and untracked: `members/{SPARE.lower()}` "
         "(a directory)", remedy_of(move(f"members/{SPARE.lower()}")))),
    "a link Members, no members/": (linked_members, LINKED, LINKED),
    "and every remedy the index takes": (
        every_index_remedy,
        (EVERY_INDEX + MOVED_BACK_TOO,
         remedy_of(EVERY_INDEX_REMEDY, MOVE_BACK)),
        (EVERY_INDEX, remedy_of(EVERY_INDEX_REMEDY))),
    "and a file Members/IRQS in the index and on disk": (
        with_file(f"Members/{SPARE}", staged=True),
        (IRQS_FILE + MOVED_BACK_TOO, remedy_of(IRQS_FILE_REMEDY, MOVE_BACK)),
        (IRQS_FILE, remedy_of(IRQS_FILE_REMEDY))),
    "a gitlink Members over a human's Members/": (
        gitlink_over_a_human_members,
        (GITLINK_MEMBERS, remedy_of(index_part(rename=["Members"],
                                               commit="the rename"))),
        (GITLINK_MEMBERS, remedy_of(index_part(unstage=["Members"])))),
}


@pytest.mark.parametrize("layout, folding", [
    pytest.param(layout, folding,
                 id=f"{layout}-{'folding' if folding else 'linux'}")
    for layout, answers in LAYOUTS.items()
    for folding in (False, True) if answers[1 + folding] is not ...])
def test_each_disk_answers_for_the_directory_it_holds(
        holder, family_module, monkeypatch, layout, folding):
    """ONE LAYOUT ON DISK, TWO DISKS, asked in process (#574's review, B1,
    and Codex's P2). Where the holder keeps its members in one directory
    spelled `Members` and no `members` is listed, a disk that folds case
    answers `members` with that directory (`isdir`, then `samefile`): it is
    `members/` itself, so an exact `IRQS` in it is `already exists`, a
    variant is named under that spelling, and only the index's own entries
    under `Members/` are renamed, one by one, never the directory. On Linux
    no `members` is there at all: the same `Members` is a `members/` a hand
    renamed, moved back, and what is under it is named. A `Members` in the
    index that IS that directory is never renamed, and an index entry is
    never taken to be on disk because the disk folds its name onto
    something else."""
    lay_out, linux, on_folding = LAYOUTS[layout]
    said = on_folding if folding else linux
    lay_out(holder)
    disk_as(monkeypatch, holder, folding)
    if said is None:
        assert family_module._checked_mount_path(holder, SPARE, MOUNT) is None
        return
    with pytest.raises(family_module.Refusal) as caught:
        family_module._checked_mount_path(holder, SPARE, MOUNT)
    assert tuple(str(caught.value).splitlines()) == said


#: `_disk_spellings` over a listing handed in, as `(the listing, the
#: spelling that is members/ on that disk, the gitlinks the index holds,
#: what is named and how)`. Every entry listed holds a `.git`.
MOVED_BACK = {
    "once, though two spellings hold checkouts": (
        {"MEMBERS": ["IRRS"], "Members": ["IRSS"]}, None,
        {"members/IRRS", "members/IRSS"},
        [("MEMBERS", "mv back"), ("Members/IRSS", "mv")]),
    "never where members/ is on disk": (
        {"Members": ["IRRS"], "members": []}, "members", {"members/IRRS"},
        [("Members/IRRS", "mv")]),
    "never for a .git no gitlink names": (
        {"Members": ["notes"]}, None, {"members/IRRS"},
        [("Members/notes", "mv")]),
}


@pytest.mark.parametrize("case", list(MOVED_BACK))
def test_only_a_spelling_that_is_members_renamed_is_moved_back(
        family_module, monkeypatch, tmp_path, case):
    """THE MOVE BACK (Codex's P2) is for ONE spelling, where no `members/`
    is on disk, holding a checkout whose gitlink the index holds under
    `members/`. Two spellings side by side exist only on a disk that does
    not fold case, and no test makes them, so the listing is handed in and
    nothing is read from a disk."""
    listing, canon, gitlinks, named = MOVED_BACK[case]
    monkeypatch.setattr(os.path, "lexists",
                        lambda path: Path(path).name == ".git")
    monkeypatch.setattr(family_module, "_disk_kind",
                        lambda path: "a directory")
    found = family_module._disk_spellings(
        tmp_path, {name: ("a directory", entries)
                   for name, entries in listing.items()},
        SPARE, canon, gitlinks)
    assert [(path, remedy) for path, _, remedy in found] == named


def test_the_printed_git_mv_leaves_the_members_where_they_are(
        holder, family_module, monkeypatch):
    """THE BLOCKER (#574's review, B1), typed: on a disk that folds case,
    `Members/README` beside the members in one directory `Members`. The
    remedy renames `Members/README` alone; typed as printed, the members'
    checkouts are still in that directory, and the check passes."""
    with_file("Members/README", staged=True)(holder)
    checkouts = sorted(os.listdir(holder / "Members"))
    disk_as(monkeypatch, holder, True)
    with pytest.raises(family_module.Refusal) as caught:
        family_module._checked_mount_path(holder, SPARE, MOUNT)
    assert type_remedy(holder, str(caught.value).splitlines()[1]) == [
        "git mv -- Members/README renamed-1", "git commit"]
    assert sorted(os.listdir(holder / "Members")) == [
        name for name in checkouts if name != "README"]
    assert (holder / "Members" / "IRRS" / ".git").exists()
    assert family_module._checked_mount_path(holder, SPARE, MOUNT) is None


def test_a_members_directory_renamed_by_hand_is_moved_back(family, holder,
                                                           offline, tmp_path):
    """CODEX'S P2 ON #574, ON THE DISK THE TEST RUNS ON. The holder's
    `members/` renamed `Members` with nothing staged. On Linux that left
    `members/` nowhere on disk, and the add mounted the member in a new
    `members/` beside `Members/`, splitting the holder: refused now, and
    the printed `mv` puts the directory back. On macOS and Windows the
    rename changes a spelling and nothing else, the directory is still
    `members/`, and the add goes through as it always did."""
    renamed_members(holder)
    if not disk_folds(tmp_path):
        said, remedy = refused_untouched(offline, holder, family["remotes"])
        assert said == DIR_VARIANT + "on disk and untracked: `Members` (a " \
                                     "directory)"
        assert remedy == remedy_of(MOVE_BACK)
        assert type_remedy(holder, remedy) == ["mv -- Members members"]
    added(offline, holder, family["remotes"])


# --- the control -------------------------------------------------------------

@pytest.mark.parametrize("ignorecase", ["true", "false"])
def test_a_holder_with_one_spelling_of_members_adds_a_member(
        family, holder, offline, ignorecase):
    """THE CONTROL: the holder `init` and `add` made, `members/` in one
    spelling everywhere, adds a member whatever `core.ignorecase` says."""
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    result = offline.add(holder, SPARE, remotes=family["remotes"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr == ""
    mounted_alone(holder)
    offline.assert_left_nothing()
