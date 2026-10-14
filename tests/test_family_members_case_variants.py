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
alone, and the holder is left exactly as it was.

EVERY TEST RUNS ON ALL THREE SYSTEMS, as #318's do. An index or HEAD variant
is planted with `update-index --cacheinfo`, with nothing on disk, and
`core.ignorecase` is set both ways explicitly. A disk variant is made in a
holder with no member yet (`unborn_holder`), so the holder has no `members/`
on disk beside it: no test makes two directories whose names differ only in
case, which macOS and Windows hold as one. On those two disks the one
`Members/IRQS` also answers for `members/IRQS`, and the refusal asserted is
the same there.
"""

from __future__ import annotations

import os
import re
import shlex
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
    "REFUSED family-members-dir-variant: the family root holds a spelling of "
    "members/ other than members/ itself, which macOS and Windows hold as "
    "one directory with it — ")
MOUNT_VARIANT = (
    f"REFUSED member-path-taken: the family root holds a case variant of "
    f"{MOUNT}, the same path on a case-insensitive disk, though no "
    "`members:` row names it — ")

#: The part of the remedy for a path the index holds, named by its spelling
#: of `members`.
RENAME = ("rename what the index holds with `git mv`, so that nothing is left "
          "at or under `{0}` (`git mv -- {0} <new name>`), and commit the "
          "rename")

#: The part for a path HEAD holds and the index no longer does.
COMMIT_FIRST = (
    "commit the pending change first (`git commit`), since the add's own "
    f"commit names .gitmodules, {MOUNT} and family.yaml alone: HEAD would "
    "keep `{}` beside the member, or, with `core.ignorecase` set, record the "
    "member's gitlink in that spelling")

#: The part for a path on disk and untracked.
MOVE = ("move what is on disk and untracked out of the way "
        "(`mv -- {} <new name>`)")


def remedy_of(*parts: str) -> str:
    """The remedy line: its parts, one for each place, in the order they are
    to be run, between what every remedy begins and ends with."""
    said = "; ".join(parts)
    return ("Remediation: every member is mounted under members/, and a "
            "holder keeps that directory in one spelling on every disk. "
            + said[0].upper() + said[1:] + "; then re-run.")


def refused_untouched(offline, root, remotes, *extra):
    """`add` of the spare member, refused before anything about the member
    is printed or read, with the holder exactly as it was: the snapshot, the
    index byte for byte, no `gh` call and no throwaway clone left. Returns
    the refusal's two lines."""
    before, index = snapshot(root), index_bytes(root)
    result = offline.add(root, SPARE, *extra, remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert index_bytes(root) == index
    assert snapshot(root) == before
    offline.assert_left_nothing()
    return refusal(result.stderr)


def commands(remedy: str) -> list[list[str]]:
    """Each command the remedy prints, split as a POSIX shell splits it,
    with its `<new name>` filled in."""
    return [shlex.split(command.replace("<new name>", "renamed"))
            for command in re.findall(r"`((?:git )?mv -- [^`]*)`", remedy)]


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


# --- the index (#362) ---------------------------------------------------------

@pytest.mark.parametrize("ignorecase", ["true", "false"])
@pytest.mark.parametrize("name", ["Members/README", "MEMBERS/notes/a",
                                  "Members"])
def test_a_spelling_of_members_in_the_index_is_refused_on_every_disk(
        family, holder, offline, name, ignorecase):
    """THE ISSUE'S STATE (#362): the index holds a path under `Members/`, or
    `Members` itself, and nothing is on disk. With `core.ignorecase` set git
    stages the gitlink as `Members/IRQS` and the commit matches nothing;
    without it the add commits and leaves `Members/` beside the member, for
    the next clone on macOS or Windows to meet. Refused both ways, before
    the member is read, and `--dry-run` refuses it alike."""
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    plant(holder, "100644", name)
    first = name.split("/")[0]
    said = (DIR_VARIANT + f"in the index: `{name}` (a file)",
            remedy_of(RENAME.format(first)))
    assert refused_untouched(offline, holder, family["remotes"],
                             "--dry-run") == said
    assert refused_untouched(offline, holder, family["remotes"]) == said


@pytest.mark.parametrize("made", ["Members/README", "Members"])
def test_a_spelling_of_members_tracked_on_disk_takes_the_printed_git_mv(
        family, offline, tmp_path, made):
    """THE STATE ON A REAL DISK: `Members/README`, or a file `Members`,
    committed, its file on disk, in a holder with no `members/` yet, so it is
    the only spelling on every disk. The index names it, once: it is not
    untracked on disk as well. The printed `git mv`, run with a name filled
    in and committed, lets the same `add` through, and the member is pinned
    under `members/` alone."""
    root = unborn_holder(tmp_path)
    (root / made).parent.mkdir(exist_ok=True)
    (root / made).write_bytes(b"our own notes\n")
    git("add", "--", "family.yaml", made, cwd=root)
    git("commit", "-qm", f"Notes at {made}", cwd=root)
    said, remedy = refused_untouched(offline, root, family["remotes"])
    assert said == DIR_VARIANT + f"in the index: `{made}` (a file)"
    assert remedy == remedy_of(RENAME.format("Members"))
    (argv,) = commands(remedy)
    assert argv == ["git", "mv", "--", "Members", "renamed"]
    git(*argv[1:], cwd=root)
    git("commit", "-qm", "Rename Members", cwd=root)
    again = offline.add(root, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    mounted_alone(root)
    renamed = "renamed" + made[len("Members"):]
    assert git("show", f"HEAD:{renamed}", cwd=root).stdout == (
        "our own notes\n")


def test_every_place_is_named_and_the_pending_change_is_committed_first(
        family, holder, offline):
    """TWO PLACES AT ONCE: the index holds `Members/README`, and HEAD holds
    `MEMBERS/old`, which the index no longer does. Both are named, each
    where it was found, and the remedy commits the pending change before it
    renames, since that commit is what takes `MEMBERS/old` out of HEAD."""
    plant(holder, "100644", "MEMBERS/old")
    git("commit", "-qm", "Track MEMBERS/old", cwd=holder)
    git("rm", "-q", "--cached", "--", "MEMBERS/old", cwd=holder)
    plant(holder, "100644", "Members/README")
    assert refused_untouched(offline, holder, family["remotes"]) == (
        DIR_VARIANT + "in the index: `Members/README` (a file); in HEAD and "
        "no longer in the index: `MEMBERS/old` (a file)",
        remedy_of(COMMIT_FIRST.format("MEMBERS"), RENAME.format("Members")))


def test_more_than_five_paths_in_one_place_are_counted(family, holder,
                                                       offline):
    """Five names in each place at most, then a count, as the unwind's
    sentence names an index that moved: a `Members/` of a holder's own may
    hold any number of files, and its one `git mv` renames them all."""
    for n in range(1, 8):
        plant(holder, "100644", f"Members/{n}")
    shown = ", ".join(f"`Members/{n}` (a file)" for n in range(1, 6))
    assert refused_untouched(offline, holder, family["remotes"]) == (
        DIR_VARIANT + f"in the index: {shown} and 2 more",
        remedy_of(RENAME.format("Members")))


# --- HEAD, and no longer the index (#363) ------------------------------------

#: What HEAD holds and the index no longer does, as `(mode, name, the code's
#: first sentence, its spelling of `members` or of the mount path, kind)`.
HEAD_ONLY = {
    "a file under Members/": ("100644", "Members/README.md", DIR_VARIANT,
                              "Members", "a file"),
    "a variant of the mount path": ("160000", f"members/{SPARE.lower()}",
                                    MOUNT_VARIANT, f"members/{SPARE.lower()}",
                                    "a submodule"),
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
    mode, name, first, spelled, kind = HEAD_ONLY[state]
    git("config", "--local", "core.ignorecase", ignorecase, cwd=holder)
    plant(holder, mode, name)
    git("commit", "-qm", f"Track {name}", cwd=holder)
    git("rm", "-q", "--cached", "--", name, cwd=holder)
    assert refused_untouched(offline, holder, family["remotes"]) == (
        first + f"in HEAD and no longer in the index: `{name}` ({kind})",
        remedy_of(COMMIT_FIRST.format(spelled)))
    git("commit", "-qm", f"Untrack {name}", cwd=holder)
    again = offline.add(holder, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    mounted_alone(holder)


# --- the disk (#364) ----------------------------------------------------------

#: What is on disk and untracked, in a holder with nothing else under any
#: spelling of `members`, as `(the file made, the code's first sentence, the
#: path named and its kind, the path the remedy moves)`.
ON_DISK = {
    "a variant of the mount path under Members/": (
        f"Members/{SPARE}/notes.txt", MOUNT_VARIANT,
        f"`Members/{SPARE}` (a directory)", "Members"),
    "a variant of the mount path under members/": (
        f"members/{SPARE.lower()}/notes.txt", MOUNT_VARIANT,
        f"`members/{SPARE.lower()}` (a directory)",
        f"members/{SPARE.lower()}"),
    "a file under Members/": ("Members/README.md", DIR_VARIANT,
                              "`Members` (a directory)", "Members"),
    "a file named Members": ("Members", DIR_VARIANT, "`Members` (a file)",
                             "Members"),
}


@pytest.mark.parametrize("state", list(ON_DISK))
def test_an_untracked_spelling_on_disk_is_refused_alike_on_every_disk(
        family, offline, tmp_path, state):
    """THE ISSUE'S STATE (#364): an untracked `Members/IRQS` was refused by
    `lexists` on macOS and Windows and mounted beside on Linux. The disk is
    listed now, one level at a time, so each OS sees the directory in the
    spelling it keeps and says the same thing. On macOS and Windows the one
    `Members/IRQS` is `members/IRQS` as well, and the refusal is this one
    there too, not `already exists`. The printed `mv`, done, lets the same
    `add` through. The holder has no commit yet, so HEAD is unborn."""
    made, first, named, moved = ON_DISK[state]
    root = unborn_holder(tmp_path)
    (root / made).parent.mkdir(parents=True, exist_ok=True)
    (root / made).write_bytes(b"our own notes\n")
    assert refused_untouched(offline, root, family["remotes"]) == (
        first + f"on disk and untracked: {named}",
        remedy_of(MOVE.format(moved)))
    assert (root / made).read_bytes() == b"our own notes\n"
    os.rename(root / moved, root / "renamed")
    again = offline.add(root, SPARE, remotes=family["remotes"])
    assert again.returncode == 0, again.stdout + again.stderr
    untracked = "renamed/" if (root / "renamed").is_dir() else "renamed"
    assert git("status", "--porcelain", cwd=root).stdout == (
        f"?? {untracked}\n")
    assert git("ls-tree", "-r", "--name-only", "HEAD",
               cwd=root).stdout.split() == [".gitmodules", "family.yaml",
                                            MOUNT]


def folding_lexists(path) -> bool:
    """`os.path.lexists` as a disk that folds case answers it, macOS's and
    Windows' by default: each component found in its parent's listing in
    any case."""
    path = Path(path)
    here = Path(path.anchor)
    for part in path.parts[1:]:
        try:
            names = os.listdir(here)
        except OSError:
            return False
        found = [name for name in names if name.lower() == part.lower()]
        if not found:
            return False
        here = here / found[0]
    return True


def test_a_disk_that_folds_case_gives_the_same_refusal(family_module,
                                                       monkeypatch, tmp_path):
    """THE SAME ANSWER ON macOS AND WINDOWS, ASKED ON ANY DISK (#364). There
    `lexists` finds `members/IRQS` inside an untracked `Members/IRQS`, and
    `add` used to refuse it as `already exists` while Linux mounted the
    member beside it. With `lexists` answering as such a disk does, the
    refusal is still the one the listing makes on every disk."""
    root = unborn_holder(tmp_path)
    (root / "Members" / SPARE).mkdir(parents=True)
    (root / "Members" / SPARE / "notes.txt").write_bytes(b"our own notes\n")
    assert folding_lexists(root / MOUNT)
    monkeypatch.setattr(os.path, "lexists", folding_lexists)
    with pytest.raises(family_module.Refusal) as caught:
        family_module._checked_mount_path(root, SPARE, MOUNT)
    assert str(caught.value).splitlines() == [
        MOUNT_VARIANT + f"on disk and untracked: `Members/{SPARE}` (a "
        "directory)", remedy_of(MOVE.format("Members"))]


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


def test_a_members_directory_a_case_insensitive_disk_spelled_is_tracked(
        holder, family_module):
    """WHAT A CHECKOUT ON macOS OR WINDOWS MAKES of a holder that held
    `Members/README` beside its members: one directory, created as
    `Members` because that entry sorts first, holding the members' own
    checkouts. Once `Members/README` is renamed and committed, that directory
    holds only what the index tracks under `members/`, and is no untracked
    variant: moving it would move the members. Renamed here, a directory
    renamed in place, so no second spelling is ever made."""
    os.rename(holder / "members", holder / "Members")
    on_disk = family_module._members_on_disk(holder)
    assert list(on_disk) == ["Members"]
    assert family_module._members_spellings(holder, SPARE, on_disk) == []


# --- the control ---------------------------------------------------------------

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

