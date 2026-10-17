# SPDX-License-Identifier: Apache-2.0
"""The holder gate's findings and refusals for a member recorded in the
wrong case, a gitlink git stops at, and a commit its checkout lacks, each
typed as printed in the state it names (#762).

THE ISSUE'S LINES, each reproduced on #747's head (58d6c50f) before this
change:

- (e) After `mkdir Members && git mv members/IRRS Members/IRRS`, committed,
  the move back put the gitlink at `members/IRRS` and left the section's
  `path` at `Members/IRRS`, as `git mv` rewrote it: a second round
  (`member-gitmodules-absent`), then a third (`member-uninitialized`). The
  move now gives the section the row's path back and stages it, and the
  update that checks the member out comes last: before it, `git -C
  Members/IRRS status` reads the checkout `git mv` moved there; after it,
  which points the member's own store at `members/IRRS`, it does not.
- (f) A variant a sparse checkout keeps off disk: `git rm -r --cached
  --ignore-unmatch` exited 0 and removed nothing, in a cone and a non-cone
  checkout, and the index ended with two gitlinks. The line says
  `--sparse` there, which needs git 2.34 or later.
- (g) A file at the row's path was replaced by the move's second line
  without a word, and one under it stopped that line (`appears as both a
  file and as a directory`, exit 128) after the first had taken the variant
  out, which committed left the member un-registered. The entry goes aside
  first with a committed `git mv`.
- A row's own `git rm --cached members/IRRS`, staged: `family ok` in every
  mode, and `member-gitlink-absent` only after the commit. A plain `git rm`
  was `member-uninitialized`, whose update dies `No url found`. It is
  `member-gitlink-removal-staged` now, with the lines that put it back and
  the `family.py remove` that takes it out.
- `member-commit-unresolvable` printed no remedy. It names the fetch of the
  pinned commit, which a remote that holds it serves, on a branch or not,
  and THE LOCKSTEP RULE's `bump` for a pin no remote holds, where the fetch
  and `git submodule update` exit 128 `not our ref`.
- In a plain clone of a holder with a stray case variant (S1), a hand mount
  with no section (H1), a section with no url (U1) or a gitlink outside
  `members/` (H2), members checked and `--pins` refused
  `member-uninitialized` with the update that dies at that gitlink. It
  names the gitlink and bootstrap's own cure now, and U1 is
  `member-gitmodules-url-absent` in every mode, where `--no-members` said
  `family ok`.
- `member-gitlink-unnamed` said a recursive clone fetches a gitlink no
  section gives a url; a recursive clone checks out nothing there.

THE SAME FAMILY AND OFFLINE RULES as `test_family_head_lost_gitmodules.py`
(#611), whose helpers are imported. The folding disk is emulated as there,
`core.ignorecase=true` for every git the test types; a state that needs a
second directory at a case variant is skipped where the disk cannot hold
one (`case_sensitive_disk`).
"""

from __future__ import annotations

import itertools
import re
import shlex
from pathlib import Path

import pytest

from conftest import (
    IDENTITY_CONFIG, REPO, clone_just_pushed, git, rmtree, run_script,
)
from repo_shape import PYTHON, tree_digest
from test_family import (  # noqa: F401
    MEMBERS, NAME, ORG, SPARE, family, validate,
)
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import (
    DUPLICATE, OUTSIDE_CURE, SECTION_CURE, TWICE_CURE, UNNAMED_CURE,
    UNNAMED_STOPS, cloned, fetching, type_line, without_url,
)
from test_family_dry_run import isolated
from test_family_head_lost_gitmodules import (  # noqa: F401
    DISKS, GUARDED_MOVE, assert_passes_in_every_mode, case_sensitive_disk,
    commit_all, committed_gitmodules, github_to, on_disk, pinned,
    recorded_at, typed_in_sh, variant_refused, without_section,
)
from test_family_member_path import raw
from test_family_tracking_branch import on_main  # noqa: F401
from test_validate_family_branch_step import (
    BRANCH_LEFT, RULE, rule_commands, switch_argv,
)
from test_validate_family_unnamed_mounts import (
    GITLINK_SAID, GITLINK_SAID_FETCHED, VARIANT, codes, commands, findings,
    spare_commits, stage_gitlink, stage_unmerged_gitlink,
)

MEMBER, OTHER = MEMBERS
ROW = f"members/{MEMBER}"
VARIANT_PATH = f"Members/{MEMBER}"

#: What members mode's variant refusal says before the move it prints.
WRONG_CASE_LEAD = "Remediation: the member is recorded in the wrong case. "


def refused_lines(root: Path, *extra: str) -> list[str]:
    """The gate in `root`, members checked unless `extra` says otherwise,
    which must refuse: its stderr lines."""
    result = validate(root, *extra)
    assert result.returncode == 2, result.stderr + result.stdout
    return result.stderr.splitlines()


def unnamed_as_moved(variant: str, at: str, refused: list[str], *,
                     said: str = GITLINK_SAID) -> str:
    """`member-gitlink-unnamed` WHOLE for MEMBER's gitlink at `variant`,
    under `--no-members`: what every unnamed gitlink says, the row it is a
    variant of, and members mode's refusal `refused` after its lead, word
    for word, with its lines."""
    assert refused[1].startswith(WRONG_CASE_LEAD), refused[1]
    return "\n".join([
        said.format(path=variant, commit=at)
        + VARIANT.format(row_path=ROW, project=MEMBER)
        + " The member is recorded in the wrong case. "
        + refused[1][len(WRONG_CASE_LEAD):], *refused[2:]])


def type_all(root: Path, env: dict, lines: list[str]) -> None:
    """Every printed command line, typed as printed."""
    for line in lines:
        type_line(root, env, line.strip())


def refused_and_unnamed(root: Path, commit: str,
                        expected: list[str]) -> list[str]:
    """The members-checked refusal in `root`, which must be `expected`,
    and `--no-members`, whose one finding must be the same move as
    `member-gitlink-unnamed` (`unnamed_as_moved`) for MEMBER's gitlink at
    `commit`: the refusal's lines."""
    lines = refused_lines(root)
    assert lines == expected
    fallback = validate(root, "--no-members")
    assert findings(fallback) == [unnamed_as_moved(VARIANT_PATH, commit,
                                                   expected)]
    return lines


# --- (e): a `git mv` to a variant, moved back with its section ---------------

#: What the move says its `.gitmodules` lines do, for a section `git mv`
#: rewrote and for none at all.
SECTION_GIVEN_BACK = (f"give {ROW} back to the section of HEAD's .gitmodules "
                      "that gives the variant's path, as git mv leaves it")
SECTION_WRITTEN = (f"write its section as family.py add writes one, since no "
                   f"section of HEAD's .gitmodules gives {ROW} or the "
                   "variant's path")


def git_moved(root: Path, env: dict) -> str:
    """MEMBER's mount moved to `Members/IRRS` with `git mv`, its parent made
    first, as git needs, and committed: the gitlink, the checkout and the
    section's `path` all move. Returns the commit the gitlink names."""
    commit = pinned(root, MEMBER)
    (root / "Members").mkdir()
    raw(root, env, "mv", "--", ROW, VARIANT_PATH)
    commit_all(root, env, f"git mv {ROW} {VARIANT_PATH}")
    assert f"\tpath = {VARIANT_PATH}\n".encode() in raw(
        root, env, "show", "HEAD:.gitmodules").stdout, "premise: git mv"
    return commit


@DISKS
def test_a_git_mv_to_a_variant_is_moved_back_with_its_section(
        family, holder, offline, tmp_path, case_sensitive_disk, ignorecase):
    """THE ISSUE'S (e). The refusal, and the same move under `--no-members`,
    print the section's path given back and staged, beside the two lines.
    Typed as printed and committed, the guarded `mv` moves nothing (the
    directory left is the member's checkout), the checkout is deleted by
    hand as the text says, and the update then checks the member out at
    its row's path: `git submodule update --init` exits 0, HEAD's section
    gives `members/IRRS`, and the gate passes in every mode."""
    env = on_disk(fetching(isolated(offline, tmp_path)), ignorecase)
    commit = git_moved(holder, env)
    section = (f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
               "git add -- .gitmodules")
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit}, section=section,
                               section_said=SECTION_GIVEN_BACK)

    lines = refused_lines(holder)

    assert lines == expected
    fallback = validate(holder, "--no-members")
    assert fallback.returncode == 1, fallback.stdout + fallback.stderr
    assert findings(fallback)[0] == unnamed_as_moved(
        VARIANT_PATH, commit, expected, said=GITLINK_SAID_FETCHED)
    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    (move,) = GUARDED_MOVE.findall(lines[1])
    assert typed_in_sh(holder, move).returncode == 0
    assert (holder / VARIANT_PATH / ".git").is_file(), "premise: a checkout"
    rmtree(holder / VARIANT_PATH)
    updated = raw(holder, env, "submodule", "update", "--init", "--recursive",
                  check=False)
    assert updated.returncode == 0, updated.stderr
    assert (holder / ROW / "project.yaml").is_file()
    assert f"\tpath = {ROW}\n".encode() in raw(
        holder, env, "show", "HEAD:.gitmodules").stdout
    assert_passes_in_every_mode(holder, 2)


def test_the_update_comes_last_where_git_mv_moved_the_checkout(
        family, holder, offline, tmp_path, case_sensitive_disk):
    """WHY THE UPDATE IS LAST. Work nobody committed in the checkout `git mv`
    moved to `Members/IRRS`: after the lines and their commit, `git -C
    Members/IRRS status`, which the text gives for what only that checkout
    holds, lists it. An update run first points the member's store, which
    that checkout names, at `members/IRRS`, and the same status then reads
    `members/IRRS` and lists nothing: deleted then, the work was lost."""
    env = fetching(isolated(offline, tmp_path))
    git_moved(holder, env)
    (holder / VARIANT_PATH / "WORK.md").write_bytes(b"not committed\n")
    lines = refused_lines(holder)
    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    (status,) = set(re.findall(r"`(git -C \S+ status)`", lines[1]))

    before = raw(holder, env, *shlex.split(status)[1:], "--porcelain").stdout
    raw(holder, env, "submodule", "update", "--init", "--recursive")
    after = raw(holder, env, *shlex.split(status)[1:], "--porcelain").stdout

    assert before == b"?? WORK.md\n"
    assert after == b""


def test_a_variant_no_section_gives_is_moved_with_its_section_written(
        family, holder, offline, tmp_path):
    """No section of HEAD's `.gitmodules` gives the row's path or the
    variant's (#363's state, MEMBER's section taken out by hand): the move
    writes the section as `family.py add` writes one, so its commit leaves
    no `member-gitmodules-absent` behind, and the gate passes in every
    mode."""
    env = fetching(isolated(offline, tmp_path))
    without_section(holder, env, MEMBER)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    section = (f"git config -f .gitmodules submodule.{ROW}.path {ROW}",
               f"git config -f .gitmodules submodule.{ROW}.url "
               f"https://github.com/{ORG}/{MEMBER}.git",
               "git add -- .gitmodules")

    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit}, section=section,
                               section_said=SECTION_WRITTEN)

    lines = refused_and_unnamed(holder, commit, expected)

    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    assert_passes_in_every_mode(holder, 2)


# --- (f): a variant a sparse checkout keeps off disk -------------------------

#: The two sparse checkouts that keep `Members/` off disk: a cone that holds
#: every directory the holder's gate reads, and non-cone patterns.
SPARSE = {
    "cone": ("--cone", "members", "scripts", "contracts", ".github"),
    "no-cone": ("--no-cone", "/*", "!/Members/"),
}


@pytest.mark.parametrize("rules", SPARSE.values(), ids=SPARSE)
def test_a_variant_a_sparse_checkout_keeps_off_disk_is_moved_with_sparse(
        holder, offline, tmp_path, rules):
    """THE ISSUE'S (f). `Members/IRRS` is skip-worktree, so the plain line
    removes nothing, exit 0 (the premise, typed), and the next leaves two
    gitlinks. The refusal, and `--no-members`, print `--sparse` and say
    which git it needs; typed as printed and committed, the index records
    the member once, at its row's path, and the gate passes in every
    mode."""
    env = isolated(offline, tmp_path)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    raw(holder, env, "sparse-checkout", "set", *rules)
    assert raw(holder, env, "ls-files", "-t", "--", VARIANT_PATH).stdout == (
        f"S {VARIANT_PATH}\n".encode()), "premise: kept off disk"
    plain = raw(holder, env, "rm", "-r", "-q", "--cached", "--ignore-unmatch",
                "--", VARIANT_PATH, check=False)
    assert plain.returncode == 0, plain.stderr
    assert raw(holder, env, "ls-files", "--", VARIANT_PATH).stdout, (
        "premise: the plain line removes nothing")
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit},
                               sparse=(VARIANT_PATH,))

    lines = refused_and_unnamed(holder, commit, expected)

    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    listed = raw(holder, env, "ls-files", "-s").stdout.decode()
    assert [line.split("\t")[1] for line in listed.splitlines()
            if line.startswith("160000 ")] == [ROW, f"members/{OTHER}"]
    assert_passes_in_every_mode(holder, 2)


def test_a_sparse_checkout_keeping_another_directory_off_disk_is_no_sparse(
        holder, offline, tmp_path):
    """rv820's SHOULD 3: a non-cone sparse checkout keeps `notes/`, which the
    gate never reads, off disk, and the variant on it. The refusal, and
    `--no-members`, print no `--sparse` and name nothing kept off disk;
    typed as printed and committed, the index records the member once, at
    its row's path, and the gate passes in every mode."""
    env = isolated(offline, tmp_path)
    (holder / "notes").mkdir()
    (holder / "notes" / "kept.md").write_bytes(b"kept off disk\n")
    raw(holder, env, "add", "--", "notes/kept.md")
    commit_all(holder, env, "A directory the gate never reads")
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    raw(holder, env, "sparse-checkout", "set", "--no-cone", "/*", "!/notes/")
    assert raw(holder, env, "ls-files", "-t", "--", "notes/kept.md",
               VARIANT_PATH).stdout == (
        f"H {VARIANT_PATH}\nS notes/kept.md\n".encode()), "premise"
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit})

    lines = refused_and_unnamed(holder, commit, expected)

    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    listed = raw(holder, env, "ls-files", "-s").stdout.decode()
    assert [line.split("\t")[1] for line in listed.splitlines()
            if line.startswith("160000 ")] == [ROW, f"members/{OTHER}"]
    assert_passes_in_every_mode(holder, 2)


# --- (g): an entry the index holds at or under the row's path ----------------

#: A file at the row's path, one under it, and seven under it, of which the
#: text names five: `(the entries, what the text names under the path)`.
IN_THE_WAY = {
    "at": ((ROW,), None),
    "under": ((f"{ROW}/notes",), f"{ROW}/notes"),
    "seven": (tuple(f"{ROW}/note{n}" for n in range(7)),
              f"{ROW}/note0, {ROW}/note1, {ROW}/note2, {ROW}/note3, "
              f"{ROW}/note4 and 2 more"),
}


@pytest.mark.parametrize("entries, named", IN_THE_WAY.values(),
                         ids=IN_THE_WAY)
def test_an_entry_in_the_way_is_moved_aside_first_as_printed(
        family, holder, offline, tmp_path, entries, named):
    """THE ISSUE'S (g). The checkout taken away and a file committed at
    `members/IRRS`, or under it, beside the variant's gitlink. The refusal,
    and `--no-members`, name the entry, or the first five of seven and how
    many more (rv820's NIT 6), and the committed `git mv` that moves it
    aside first. Typed as printed, `<new name>` filled in, then the two
    lines and their commit, the update checks the member out, the files
    are kept at their new name, and the gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    rmtree(holder / ROW)
    for entry in entries:
        (holder / entry).parent.mkdir(parents=True, exist_ok=True)
        (holder / entry).write_bytes(b"a file\n")
        raw(holder, env, "add", "--", entry)
    commit_all(holder, env, "A file in the way")
    aside = (f"The index holds an entry at {ROW} that is no gitlink, which "
             "the move's second line replaces without a word"
             if named is None else
             f"The index holds {named} under {ROW}, at which the move's "
             "second line stops (appears as both a file and as a directory) "
             "after the first has taken the variant out") + (
        f". Move it aside first, `git mv -- {ROW} <new name>`, a new name "
        "outside members/, and commit that move on its own. ")
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit}, aside=aside)

    lines = refused_and_unnamed(holder, commit, expected)

    (moved,) = re.findall(r"`(git mv -- [^`]*)`", lines[1])
    type_line(holder, env, moved.replace("<new name>", f"{MEMBER}-aside"))
    commit_all(holder, env, "Move the file aside, as printed")
    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    raw(holder, env, "submodule", "update", "--init", "--recursive")
    kept = raw(holder, env, "ls-tree", "-r", "--name-only", "HEAD", "--",
               f"{MEMBER}-aside").stdout.decode().splitlines()
    assert kept == [entry.replace(ROW, f"{MEMBER}-aside")
                    for entry in entries]
    assert_passes_in_every_mode(holder, 2)


def test_an_entry_beside_the_rows_path_is_not_in_the_way(
        holder, offline, tmp_path):
    """rv820's SHOULD 3: a file committed at `members/IRRS-notes`, beside the
    variant's gitlink, is not at or under `members/IRRS` as git compares
    paths, so the refusal, and `--no-members`, move nothing aside. Typed as
    printed and committed, the file stays where it is, and the gate passes
    in every mode."""
    env = isolated(offline, tmp_path)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    beside = f"{ROW}-notes"
    (holder / beside).write_bytes(b"a file\n")
    raw(holder, env, "add", "--", beside)
    commit_all(holder, env, "A file beside the row's path")
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit})

    lines = refused_and_unnamed(holder, commit, expected)

    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    assert raw(holder, env, "ls-files", "-s", "--", ROW).stdout == (
        f"160000 {commit} 0\t{ROW}\n".encode())
    assert raw(holder, env, "ls-files", "--", beside).stdout == (
        f"{beside}\n".encode())
    assert_passes_in_every_mode(holder, 2)


def test_a_gitlink_a_merge_left_unmerged_at_the_rows_path_is_replaced(
        holder, offline, tmp_path):
    """rv820's NIT 5: the row's path held at stages 1, 2 and 3 alone, as a
    conflicted merge of the member's gitlink leaves it, beside the
    variant's gitlink. The move's second line replaces the three stages,
    so nothing is said to be in the way; typed as printed and committed,
    the index records the member once, at stage 0, and the gate passes in
    every mode."""
    env = isolated(offline, tmp_path)
    commit = recorded_at(holder, env, MEMBER, VARIANT_PATH)
    stage_unmerged_gitlink(holder, ROW, commit)
    expected = variant_refused(ROW, commit, [VARIANT_PATH],
                               {VARIANT_PATH: commit})

    lines = refused_lines(holder)

    assert lines == expected
    type_all(holder, env, lines[2:])
    commit_all(holder, env, "Move the gitlink back, as printed")
    assert raw(holder, env, "ls-files", "-s", "--", ROW).stdout == (
        f"160000 {commit} 0\t{ROW}\n".encode())
    assert_passes_in_every_mode(holder, 2)


# --- a row's own staged un-registration ------------------------------------

#: How the row's gitlink was taken out: with its section and checkout, or
#: from the index alone.
TAKEN = {"git-rm": ("rm", "-q", "--"), "git-rm-cached": ("rm", "-q",
                                                       "--cached", "--")}

#: What the lines that put it back each put back, by how it was taken out.
PUT_BACK = {
    "git-rm": (
        "the lines below put the member back as HEAD has it: the first its "
        "gitlink, the second the .gitmodules section git rm took out, "
        "putting that file back as HEAD has it and dropping any other change "
        "to it, the third its checkout",
        [f"git reset -q -- {ROW}", "git checkout HEAD -- .gitmodules",
         f"git submodule update --init --recursive -- {ROW}"]),
    "git-rm-cached": (
        "the line below puts its gitlink back as HEAD records it",
        [f"git reset -q -- {ROW}"]),
}


def removal_staged(root: Path, commit: str, how: str) -> str:
    """`member-gitlink-removal-staged` WHOLE for MEMBER's gitlink at
    `commit`, taken out `how`, in `root`."""
    said, lines = PUT_BACK[how]
    remove = (f"{PYTHON} scripts/family.py remove --family-root "
              f"{shlex.quote(str(root))} --member {MEMBER}")
    switch = shlex.join(switch_argv(root, "remove", "irrs"))
    return "\n".join([
        f"FINDING member-gitlink-removal-staged: {ROW} is a gitlink at "
        f"{commit} that a row of members: names and HEAD records, and the "
        "index holds nothing at that path: its removal is staged and not "
        "committed, so the next commit un-registers the member under its "
        "row, and this gate then refuses member-gitlink-absent. If the "
        f"member is to stay, {said}, and nothing is left to commit. If it is "
        "to go, put it back the same way, then take it out with family.py "
        "remove, from a checkout of openRepoShape, which takes its row, its "
        "gitlink and its section out in one commit, on a branch other than "
        "the holder's tracking branch, which it refuses "
        f"(`{switch}` makes one): `{remove}`. {BRANCH_LEFT}",
        *(f"    {line}" for line in lines)])


@pytest.mark.parametrize("how", TAKEN)
def test_a_rows_staged_removal_is_named_and_put_back_as_printed(
        on_main, offline, tmp_path, how):
    """THE ISSUE'S STAGED UN-REGISTRATION, with `git rm --cached` and with
    a plain `git rm`, staged: `member-gitlink-removal-staged`, exit 1, in
    every mode, where the gate said `family ok` (or, after a plain `git
    rm`, refused `member-uninitialized` with an update that dies `No url
    found`). Typed as printed, nothing is left to commit, and the gate
    passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit = pinned(on_main, MEMBER)
    raw(on_main, env, *TAKEN[how], ROW)

    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(on_main, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        assert findings(result) == [removal_staged(on_main, commit, how)]
        assert f"  ok  {ROW}: gitlink == pin" not in result.stdout, extra

    type_all(on_main, env, commands(findings(validate(on_main))[0]))
    assert raw(on_main, env, "status", "--porcelain").stdout == b""
    assert_passes_in_every_mode(on_main, 2)


@pytest.mark.parametrize("how", TAKEN)
def test_a_rows_staged_removal_to_go_is_removed_as_printed(
        on_main, offline, tmp_path, how):
    """The other way out: put back as printed, then the `switch` and the
    `family.py remove` it names, typed as printed from a checkout of
    openRepoShape, take the member out in one commit, and the gate passes
    in every mode with one member."""
    env = fetching(isolated(offline, tmp_path))
    raw(on_main, env, *TAKEN[how], ROW)
    (finding,) = findings(validate(on_main))
    type_all(on_main, env, commands(finding))
    switch, remove = [command for command in re.findall(r"`([^`]*)`", finding)
                      if command.startswith(("git -C", PYTHON))]
    git(*shlex.split(switch)[1:], cwd=on_main.parent)
    argv = shlex.split(remove)
    removed = run_script(REPO / argv[1], *argv[2:], cwd=REPO, env=env)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert_passes_in_every_mode(on_main, 1)


def test_a_staged_removal_once_committed_is_member_gitlink_absent(
        holder, offline, tmp_path):
    """No misfire after the commit: the removal committed is no longer
    staged, and the gate refuses `member-gitlink-absent`, as it did."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "rm", "-q", "--cached", "--", ROW)
    commit_all(holder, env, "The removal committed")

    lines = refused_lines(holder)

    assert lines[0].startswith("REFUSED member-gitlink-absent: "), lines
    assert "member-gitlink-removal-staged" not in "\n".join(lines)


def test_a_staged_removal_head_gives_no_section_for_puts_none_back(
        on_main, offline, tmp_path):
    """rv820's NIT 6: no section of HEAD's `.gitmodules` gives the row's
    path (taken out by hand and committed), and the gitlink's removal is
    staged. The finding prints the reset alone, and no `git checkout HEAD
    -- .gitmodules`, which would put back no section."""
    env = isolated(offline, tmp_path)
    without_section(on_main, env, MEMBER)
    commit = pinned(on_main, MEMBER)
    raw(on_main, env, *TAKEN["git-rm-cached"], ROW)

    staged = [found for found in findings(validate(on_main, "--no-members"))
              if found.startswith("FINDING member-gitlink-removal-staged: ")]

    assert staged == [removal_staged(on_main, commit, "git-rm-cached")]


# --- member-commit-unresolvable ---------------------------------------------

#: The dates every `commit_ahead` commit carries, so that the clock never
#: tells two of them apart: their bytes do.
AHEAD_DATES = {"GIT_AUTHOR_DATE": "2031-01-01T00:00:00+0000",
               "GIT_COMMITTER_DATE": "2031-01-01T00:00:00+0000"}

#: The number each `commit_ahead` commit writes into `AHEAD.md`. Not
#: `tmp_path.name`, for the reason `test_family_bootstrap_gate_order.py`
#: gives for its `BRANCHES`: a passed test's directory is removed under
#: `tmp_path_retention_policy=failed`, and the next test is given its
#: number.
AHEAD = itertools.count()


def commit_ahead(family, tmp_path: Path, ref: str | None) -> tuple[str, str]:
    """A new commit of MEMBER, made in a scratch clone of its remote and
    pushed to `ref` there, or nowhere where `ref` is None. Returns the
    commit and its tree digest.

    ONE COMMIT PER TEST. The tests below share one remote (`family` is
    module-scoped), and a commit with the same parent, tree, message,
    identity and second IS the one an earlier test pushed: on CI (run
    39031276097) the no-remote test's commit, made in the same second as
    the on-no-branch test's, was the commit that test had pushed, so its
    fetch fetched it. `AHEAD.md` holds a number no other call writes
    (`AHEAD`) and the dates are fixed (`AHEAD_DATES`), so in every run the
    bytes keep two calls apart, never the clock."""
    scratch = tmp_path / "scratch"
    git("clone", "-q", str(family["remotes"] / f"{MEMBER}.git"), str(scratch),
        cwd=tmp_path)
    (scratch / "AHEAD.md").write_bytes(f"ahead {next(AHEAD)}\n".encode())
    git("add", "--", "AHEAD.md", cwd=scratch)
    raw(scratch, AHEAD_DATES, *IDENTITY_CONFIG, "commit", "-qm", "Ahead")
    commit = git("rev-parse", "HEAD", cwd=scratch).stdout.strip()
    if ref is not None:
        git("push", "-q", "origin", f"HEAD:{ref}", cwd=scratch)
    return commit, tree_digest(scratch, commit)


def pinned_by_hand(root: Path, env: dict, commit: str, digest: str) -> None:
    """MEMBER's gitlink and pin moved to `commit`, its digest `digest`,
    together and committed, with nothing fetched into its store."""
    old = pinned(root, MEMBER)
    rows = (root / "family.yaml").read_bytes()
    assert rows.count(old.encode()) == 1, "fixture drift: MEMBER's pin"
    rows = rows.replace(old.encode(), commit.encode())
    found = re.compile(rb'tree_sha256: "?([0-9a-f]{64})"?').search(
        rows, rows.index(commit.encode()))
    rows = rows[:found.start(1)] + digest.encode() + rows[found.end(1):]
    (root / "family.yaml").write_bytes(rows)
    raw(root, env, "update-index", "--cacheinfo", f"160000,{commit},{ROW}")
    raw(root, env, "add", "--", "family.yaml")
    commit_all(root, env, "Pin moved, the store not fetched")


def unresolvable(root: Path, commit: str) -> str:
    """`member-commit-unresolvable`'s remediation in `root`, its text up to
    THE LOCKSTEP RULE pinned, which it returns whole."""
    lines = refused_lines(root)
    assert lines[0].startswith(
        f"REFUSED member-commit-unresolvable: {ROW}: the pinned commit "
        f"{commit} is not in that member's object store ("), lines
    assert lines[1].startswith(
        "Remediation: where a remote of the member holds it, `git -C "
        f"{ROW} fetch origin {commit}` fetches it into that store, and this "
        "then reads it. Where none does, that fetch fails `not our ref`, exit "
        "128, as `git submodule update` does, and the pin names a commit no "
        "clone can fetch: move the gitlink and the pin to one a remote "
        f"holds. {RULE}"), lines[1]
    return "\n".join(lines[1:])


@pytest.mark.parametrize("ref", ["refs/heads/w762-ahead", "refs/w762/ahead"],
                         ids=["on-a-branch", "on-no-branch"])
def test_a_pin_a_remote_holds_is_fetched_as_printed(family, holder, offline,
                                                    tmp_path, ref):
    """rv681's P2, the pin on the remote and not in the member's store:
    refused, members checked and `--pins`, now with a remedy. Its fetch,
    typed as printed, brings the commit whether a branch holds it or not,
    and the gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit, digest = commit_ahead(family, tmp_path, ref)
    branches = git("branch", "--format=%(refname)", "--contains", commit,
                   cwd=family["remotes"] / f"{MEMBER}.git").stdout.split()
    assert branches == ([ref] if ref.startswith("refs/heads/") else []), (
        "premise: on that branch alone, or on none")
    pinned_by_hand(holder, env, commit, digest)
    remedy = unresolvable(holder, commit)
    assert refused_lines(holder, "--pins")[1:] == remedy.splitlines()
    (fetch,) = [command for command in re.findall(r"`([^`]*)`", remedy)
                if command.startswith("git -C ") and " fetch " in command]

    type_line(holder, env, fetch)

    assert_passes_in_every_mode(holder, 2)


def test_a_pin_no_remote_holds_is_bumped_as_printed(family, on_main, offline,
                                                    tmp_path):
    """rv681's P2, a pin no remote holds: the fetch the remedy names exits
    128 `not our ref`, as it says, and so does `git submodule update`. Its
    rule's `switch` and `bump`, typed as printed from a checkout of
    openRepoShape with a commit the remote holds as `--to`, put the gitlink
    and the pin back in step, and the gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    commit, digest = commit_ahead(family, tmp_path, None)
    on_remote = git("cat-file", "-e", commit,
                    cwd=family["remotes"] / f"{MEMBER}.git", check=False)
    assert on_remote.returncode == 1, "premise: no remote holds it"
    pinned_by_hand(on_main, env, commit, digest)
    remedy = unresolvable(on_main, commit)
    (fetch,) = [command for command in re.findall(r"`([^`]*)`", remedy)
                if command.startswith("git -C ") and " fetch " in command]
    fetched = raw(on_main, env, *shlex.split(fetch)[1:], check=False)
    assert fetched.returncode == 128, fetched.stderr
    assert b"not our ref" in fetched.stderr
    update = raw(on_main, env, "submodule", "update", "--init", "--", ROW,
                 check=False)
    assert update.returncode != 0, update.stderr
    assert b"not our ref" in update.stderr
    bump, switch = rule_commands(remedy)
    held = git("rev-parse", "main",
               cwd=family["remotes"] / f"{MEMBER}.git").stdout.strip()

    git(*shlex.split(switch)[1:], cwd=on_main.parent)
    argv = shlex.split(bump.replace("<commit>", held))
    bumped = run_script(REPO / argv[1], *argv[2:], cwd=REPO, env=env)

    assert bumped.returncode == 0, bumped.stdout + bumped.stderr
    assert_passes_in_every_mode(on_main, 2)


# --- S1, H1, U1 and H2: a plain clone whose update stops at another gitlink --

def url_less(holder: Path, env: dict, family) -> str:
    """rv648's U1: OTHER's section with its url taken out, committed.
    Returns OTHER's path, where git's init stops."""
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    committed_gitmodules(holder, env, without_url(data, OTHER))
    return f"members/{OTHER}"


def outside(holder: Path, env: dict, family) -> str:
    """rv648's H2: SPARE's gitlink recorded by hand at `vendor/<SPARE>`,
    with no row and no section, committed. Returns its path."""
    stage_gitlink(holder, f"vendor/{SPARE}", spare_commits(family)[1])
    commit_all(holder, env, "A gitlink mounted by hand outside members/")
    return f"vendor/{SPARE}"


def twice(holder: Path, env: dict, family) -> str:
    """rv648's D1: a second section, `dup`, giving OTHER's path and no url,
    after OTHER's own, committed: git reads the later. Returns OTHER's
    path, where git's init stops."""
    data = raw(holder, env, "show", "HEAD:.gitmodules").stdout
    committed_gitmodules(holder, env, data + DUPLICATE)
    return f"members/{OTHER}"


#: `(set-up, the cure members mode prints for where git stops)`.
STOPS = {
    "stray": (UNNAMED_STOPS["stray"], lambda path: UNNAMED_CURE),
    "hand-mount": (UNNAMED_STOPS["hand-mount"], lambda path: UNNAMED_CURE),
    "url-less": (url_less, lambda path: SECTION_CURE.format(path=path)),
    "twice": (twice, lambda path: TWICE_CURE),
    "outside": (outside, lambda path: OUTSIDE_CURE.format(path=path)),
}

#: What `member-uninitialized` says, before and after the update it names.
UNINITIALIZED = (
    f"REFUSED member-uninitialized: {ROW} is not an initialized submodule "
    "checkout, so neither the pinned digest nor the project it claims can be "
    "read. Presence is not identity and an unreadable surface must fail "
    "rather than degrade.")
UPDATE = ("`git submodule update --init --recursive`, or `make bootstrap`, "
          "which resolves a credential for private members first.")


def cured_as_printed(clone: Path, env: dict, stopper: str,
                     remedy: str) -> None:
    """What the refusal says cures `stopper`, done as it says: the
    `--no-members` run it names and every `git` line that run prints for
    the gitlink, its `.gitmodules` staged where a line writes it, or the
    `git rm --cached` it names itself; then the commit."""
    if "--no-members" in remedy:
        fallback = validate(clone, "--no-members")
        assert fallback.returncode == 1, fallback.stdout + fallback.stderr
        (finding,) = [found for found in findings(fallback)
                      if f" {stopper} " in found.split("\n", 1)[0]]
        type_all(clone, env, [line for line in commands(finding)
                              if line.startswith("git ")])
        if finding.startswith("FINDING gitmodules-path-twice: "):
            # Its words, `--unset-all submodule.<name>.<key>` for every key
            # of the section that is not the member's, filled in for `dup`.
            assert "`dup` (no url)" in finding, finding
            raw(clone, env, "config", "-f", ".gitmodules", "--unset-all",
                "submodule.dup.path")
            raw(clone, env, "add", "--", ".gitmodules")
    elif "back as `family.py add` writes one" in remedy:
        fallback = validate(clone, "--no-members")
        (finding,) = findings(fallback)
        assert finding.startswith(
            "FINDING member-gitmodules-url-absent: "), finding
        type_all(clone, env, commands(finding))
        raw(clone, env, "add", "--", ".gitmodules")
    else:
        (line,) = re.findall(r"`(git rm [^`]*)`", remedy)
        type_line(clone, env, line)
    commit_all(clone, env, "Cure where git stops, as printed")


@pytest.mark.parametrize("set_up, cure", STOPS.values(), ids=STOPS)
def test_a_plain_clone_stopped_at_another_gitlink_names_it_members_checked(
        family, holder, offline, tmp_path, set_up, cure):
    """rv648's S1, H1, U1 and H2 in a plain clone, after the update died
    there (exit 128, `No url found for submodule path`). Members checked
    and `--pins`, the first row's `member-uninitialized` named that same
    update; it names where git stops and the cure bootstrap names for it,
    word for word, before the update. Done as it says and committed, the
    update checks both members out, and the gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    stopper = set_up(holder, env, family)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    died = raw(clone, env, "submodule", "update", "--init", "--recursive",
               check=False)
    assert died.returncode == 128, died.stderr
    assert (f"No url found for submodule path '{stopper}'".encode()
            in died.stderr)

    for extra in ((), ("--pins",)):
        assert refused_lines(clone, *extra) == [
            UNINITIALIZED,
            f"Remediation: `git submodule update --init` stops at {stopper}, "
            "a gitlink it has no url for (No url found for submodule path, "
            f"exit 128), before it checks out any member. {cure(stopper)} "
            f"Then {UPDATE}"], extra

    cured_as_printed(clone, env, stopper, cure(stopper))
    raw(clone, env, *github_to(family["remotes"]), "submodule", "update",
        "--init", "--recursive")
    assert_passes_in_every_mode(clone, 2)


def test_a_holder_whose_update_stops_nowhere_keeps_the_plain_remedy(
        family, holder, offline, tmp_path):
    """No misfire: a plain clone of a good holder, nothing checked out yet,
    is refused `member-uninitialized` with the update alone, which then
    checks both members out."""
    env = fetching(isolated(offline, tmp_path))
    clone = cloned(holder, env, family, tmp_path, recurse=False)

    assert refused_lines(clone) == [UNINITIALIZED, f"Remediation: {UPDATE}"]
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert_passes_in_every_mode(clone, 2)


def test_a_recursive_clone_not_fetched_keeps_the_plain_remedy(
        family, holder, offline, tmp_path):
    """No misfire: a recursive clone sets `submodule.active`, and git's init
    then asks only the gitlinks a section gives a path, so a stray stops
    nothing there. With the members not fetched (no credential, as
    `protocol.file.allow=user` refuses them here), the refusal names the
    update alone, which, with the credential, checks both out."""
    env = fetching(isolated(offline, tmp_path))
    UNNAMED_STOPS["stray"](holder, env, family)
    remote = family["remotes"] / f"{NAME}.git"
    raw(holder, env, "push", "-q", str(remote), "HEAD:refs/heads/w762/active")
    clone = tmp_path / "clone"
    made = clone_just_pushed(remote, clone, "w762/active",
                             config=["-c", "protocol.file.allow=user"])
    assert made.returncode != 0, "premise: the members were not fetched"

    assert refused_lines(clone) == [UNINITIALIZED, f"Remediation: {UPDATE}"]
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert (clone / ROW / "project.yaml").is_file()


def test_a_url_an_earlier_init_registered_keeps_the_plain_remedy(
        family, holder, offline, tmp_path):
    """No misfire: `git submodule init` wrote each member's url into the
    clone's git config, then the work tree's section for OTHER lost its
    url. Git's init reads the url it wrote and stops nowhere, so the
    refusal names the update alone, which checks both members out."""
    env = fetching(isolated(offline, tmp_path))
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    raw(clone, env, "submodule", "init")
    (clone / ".gitmodules").write_bytes(
        without_url((clone / ".gitmodules").read_bytes(), OTHER))

    assert refused_lines(clone) == [UNINITIALIZED, f"Remediation: {UPDATE}"]
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert (clone / f"members/{OTHER}" / "project.yaml").is_file()


#: How `.gitmodules` is gone from a work tree, and what git's submodule
#: commands then read in its place, with the line that puts it back:
#: deleted and not staged, and its deletion staged (rv820's SHOULD 2).
GONE = {
    "deleted": ("the index's", "git checkout -- .gitmodules"),
    "deletion-staged": ("HEAD's, as the index holds none",
                        "git checkout HEAD -- .gitmodules"),
}


def gone(root: Path, env: dict, how: str) -> None:
    """`.gitmodules` taken out of `root`'s work tree, as `how` (`GONE`)
    says."""
    if how == "deleted":
        (root / ".gitmodules").unlink()
    else:
        raw(root, env, "rm", "-q", "--", ".gitmodules")


@pytest.mark.parametrize("how", GONE)
def test_a_plain_clone_whose_gitmodules_is_gone_keeps_the_plain_remedy(
        family, holder, offline, tmp_path, how):
    """rv820's SHOULD 2: a plain clone of a good holder whose `.gitmodules`
    is gone from the work tree. Git reads the index's, or HEAD's, so its
    update stops nowhere: the refusal names the update alone, where it
    said git stopped at the first row and printed a cure that, written
    with `git config -f`, made a file of that one section. The update then
    checks both members out."""
    env = fetching(isolated(offline, tmp_path))
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    gone(clone, env, how)

    for extra in ((), ("--pins",)):
        assert refused_lines(clone, *extra) == [
            UNINITIALIZED, f"Remediation: {UPDATE}"], extra
    raw(clone, env, "submodule", "update", "--init", "--recursive")
    assert (clone / ROW / "project.yaml").is_file()
    assert (clone / f"members/{OTHER}" / "project.yaml").is_file()


@pytest.mark.parametrize("how", GONE)
def test_a_url_less_section_whose_gitmodules_is_gone_is_put_back_first(
        family, holder, offline, tmp_path, how):
    """rv820's SHOULD 2, where git does stop: rv648's U1 in a plain clone
    whose `.gitmodules` is gone from the work tree. Git reads the index's,
    or HEAD's, and stops at OTHER's section, which gives no url; the
    refusal names that path, not the first row's, and the `git checkout`
    that puts the file back before the cure. Done as it says and
    committed, HEAD's `.gitmodules` keeps MEMBER's section, the update
    checks both members out, and the gate passes in every mode."""
    env = fetching(isolated(offline, tmp_path))
    stopper = url_less(holder, env, family)
    clone = cloned(holder, env, family, tmp_path, recurse=False)
    gone(clone, env, how)
    died = raw(clone, env, "submodule", "update", "--init", "--recursive",
               check=False)
    assert died.returncode == 128, died.stderr
    assert (f"No url found for submodule path '{stopper}'".encode()
            in died.stderr)
    whose, put_back = GONE[how]

    for extra in ((), ("--pins",)):
        assert refused_lines(clone, *extra) == [
            UNINITIALIZED,
            f"Remediation: `git submodule update --init` stops at {stopper}, "
            "a gitlink it has no url for (No url found for submodule path, "
            "exit 128), before it checks out any member. .gitmodules is gone "
            f"from the work tree, so git reads {whose}: `{put_back}` puts it "
            "back first, so that what follows keeps every other section. "
            f"{SECTION_CURE.format(path=stopper)} Then {UPDATE}"], extra

    type_line(clone, env, put_back)
    cured_as_printed(clone, env, stopper, SECTION_CURE.format(path=stopper))
    kept = raw(clone, env, "show", "HEAD:.gitmodules").stdout
    assert f'[submodule "{ROW}"]\n\tpath = {ROW}\n\turl = '.encode() in kept, (
        kept)
    raw(clone, env, *github_to(family["remotes"]), "submodule", "update",
        "--init", "--recursive")
    assert_passes_in_every_mode(clone, 2)


#: U1's own finding, whole, for OTHER's section in this fixture.
URL_ABSENT = (
    f"FINDING member-gitmodules-url-absent: members/{OTHER} is a gitlink at "
    "{commit} that a row of members: names, and the section of HEAD's "
    f".gitmodules that gives that path, \"members/{OTHER}\", gives no url, "
    "so in a plain clone of this holder git submodule update --init stops "
    "there (No url found for submodule path, exit 128) before it checks out "
    "any member, as make bootstrap's does, and a recursive clone checks out "
    "nothing there. Write its url back by hand, in a POSIX shell, as "
    "family.py add writes one, then stage and commit .gitmodules:\n"
    f"    git config -f .gitmodules submodule.members/{OTHER}.url "
    f"https://github.com/{ORG}/{OTHER}.git")


@pytest.mark.parametrize("extra", [(), ("--pins",), ("--no-members",)],
                         ids=["members-checked", "pins", "no-members"])
def test_a_section_with_no_url_is_a_finding_in_every_mode(
        family, holder, offline, tmp_path, extra):
    """U1 in the holder it was committed in, whose checkouts stay: no mode
    named it (`--no-members` said `family ok`). It is its own finding in
    every mode, exit 1; typed as printed, staged and committed, the gate
    passes in every mode."""
    env = isolated(offline, tmp_path)
    url_less(holder, env, family)

    result = validate(holder, *extra)

    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result) == [URL_ABSENT.format(
        commit=pinned(holder, OTHER))]
    type_all(holder, env, commands(findings(result)[0]))
    raw(holder, env, "add", "--", ".gitmodules")
    commit_all(holder, env, "OTHER's url written back, as printed")
    assert_passes_in_every_mode(holder, 2)


@pytest.mark.parametrize("how", GONE)
def test_a_section_with_no_url_whose_gitmodules_is_gone_is_put_back_first(
        family, holder, offline, tmp_path, how):
    """U1 in its holder, with `.gitmodules` gone from the work tree: the
    finding's line, `git config -f`, would make a file of that one key, so
    a line before it puts the file back from where git reads it (rv820's
    SHOULD 2). In every mode; typed as printed, staged and committed,
    HEAD's file keeps MEMBER's section, and the gate passes in every
    mode."""
    env = isolated(offline, tmp_path)
    url_less(holder, env, family)
    gone(holder, env, how)
    whose, put_back = GONE[how]
    said = "then stage and commit .gitmodules:\n"
    expected = URL_ABSENT.format(commit=pinned(holder, OTHER))
    assert expected.count(said) == 1
    expected = expected.replace(
        said, "then stage and commit .gitmodules, which is gone from the "
        f"work tree: the first line puts back {whose}, so that every other "
        f"section stays:\n    {put_back}\n")

    for extra in ((), ("--pins",), ("--no-members",)):
        result = validate(holder, *extra)
        assert result.returncode == 1, (extra, result.stdout + result.stderr)
        assert findings(result) == [expected], extra

    type_all(holder, env, commands(expected))
    raw(holder, env, "add", "--", ".gitmodules")
    commit_all(holder, env, "OTHER's url written back, as printed")
    assert f'[submodule "{ROW}"]'.encode() in raw(
        holder, env, "show", "HEAD:.gitmodules").stdout
    assert_passes_in_every_mode(holder, 2)


def test_a_recursive_clone_of_a_url_less_section_checks_out_nothing_there(
        family, holder, offline, tmp_path):
    """What U1's finding says of a recursive clone: nothing is checked out
    at OTHER's path, and the clone's gate names the finding where it was."""
    env = fetching(isolated(offline, tmp_path))
    url_less(holder, env, family)
    remote = family["remotes"] / f"{NAME}.git"
    raw(holder, env, "push", "-q", str(remote), "HEAD:refs/heads/w762/u1")
    clone = tmp_path / "clone"
    clone_just_pushed(remote, clone, "w762/u1")

    assert not (clone / f"members/{OTHER}" / "project.yaml").exists()
    fallback = validate(clone, "--no-members")
    assert codes(fallback) == ["member-gitmodules-url-absent"]


# --- `member-gitlink-unnamed`: what a recursive clone does -------------------

@pytest.mark.parametrize("set_up", UNNAMED_STOPS.values(), ids=UNNAMED_STOPS)
def test_a_recursive_clone_of_a_gitlink_no_section_gives_checks_out_nothing(
        family, holder, offline, tmp_path, set_up):
    """w648b's S2 and X1: a recursive clone of a holder with a stray case
    variant, or a hand mount with no section, checks out nothing at it (an
    empty directory), and the clone's `--no-members` says so, where it said
    a recursive clone fetches it. A plain clone's update stopping there is
    the test above."""
    env = fetching(isolated(offline, tmp_path))
    stopper = set_up(holder, env, family)
    commit = raw(holder, env, "rev-parse",
                 f"HEAD:{stopper}").stdout.decode("ascii").strip()
    clone = cloned(holder, env, family, tmp_path, recurse=True)

    assert list((clone / stopper).iterdir()) == []
    fallback = validate(clone, "--no-members")
    assert fallback.returncode == 1, fallback.stdout + fallback.stderr
    (finding,) = findings(fallback)
    assert finding.startswith(GITLINK_SAID.format(path=stopper,
                                                  commit=commit)), finding


def test_a_recursive_clone_of_a_hand_mount_with_its_section_fetches_it(
        family, holder, offline, tmp_path):
    """The other branch of the same sentence: a hand mount `git submodule
    add` made, with its section and url, is fetched by a recursive clone,
    and the clone's `--no-members` says it fetches it."""
    env = fetching(isolated(offline, tmp_path))
    hand = f"members/{SPARE}"
    raw(holder, env, "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), hand)
    commit_all(holder, env, "Mount IRQS by hand")
    commit = raw(holder, env, "rev-parse",
                 f"HEAD:{hand}").stdout.decode("ascii").strip()
    clone = cloned(holder, env, family, tmp_path, recurse=True)

    assert (clone / hand / "project.yaml").is_file()
    (finding,) = [found for found in findings(validate(clone, "--no-members"))
                  if found.startswith("FINDING member-gitlink-unnamed: ")]
    assert finding.startswith(GITLINK_SAID_FETCHED.format(path=hand,
                                                          commit=commit))


def test_a_hand_mount_whose_section_gives_no_url_is_checked_out_nowhere(
        family, holder, offline, tmp_path):
    """rv820's SHOULD 3: a hand mount `git submodule add` made, whose
    section's url was then taken out and committed. A section gives its
    path and none a url, so `--no-members` says a recursive clone checks
    out nothing at it, as for one no section gives, and not that a
    recursive clone fetches it."""
    env = fetching(isolated(offline, tmp_path))
    hand = f"members/{SPARE}"
    raw(holder, env, "submodule", "add", "-q", "--",
        str(family["remotes"] / f"{SPARE}.git"), hand)
    raw(holder, env, "config", "-f", ".gitmodules", "--unset",
        f"submodule.{hand}.url")
    raw(holder, env, "add", "--", ".gitmodules")
    commit_all(holder, env, "Mount IRQS by hand, its url taken out")
    commit = raw(holder, env, "rev-parse",
                 f"HEAD:{hand}").stdout.decode("ascii").strip()

    (finding,) = [found for found in findings(validate(holder, "--no-members"))
                  if found.startswith("FINDING member-gitlink-unnamed: ")]

    assert finding.startswith(GITLINK_SAID.format(path=hand,
                                                  commit=commit)), finding
