# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/validate-family.py`: the check for
values git dies on reads the index's `.gitmodules` beside the work tree's,
an index's file git cannot parse is refused, and no file is read while a
merge leaves `.gitmodules` unmerged (#1150).

RV1124's review of #1124 (pull/1124#issuecomment-6321372469) found three
things, each older than #1124, and each measured again on #1124's head
8dfa32bd and on main 961640c6 before this change:

- N1. Where the work tree's file is on disk, the check never read the
  index's, which a plain `git commit` records. An `update = !true` given
  in the work tree's file and staged was taken out of the work tree's by
  a line that staged nothing, so a plain `git commit` after it recorded
  the value in HEAD; one given in the index's file alone, the work tree's
  clean on disk, was `family ok`, exit 0, in every mode.
- N2. An index's file with a line git cannot parse was read as nothing,
  since `git config --blob` exits 128 there: an `update = !true` before
  the line was `family ok` while git's own `submodule status` died on it
  (exit 128), and a section before the line was never named.
- N6. While a merge leaves `.gitmodules` unmerged in the index, git reads
  no file at all, and the checks read the work tree's, or HEAD's where
  that was gone: a value HEAD's gave was "here and in HEAD", its line put
  HEAD's back "as the index holds none", and a section HEAD's gave was
  named with that same line, which resolves the merge to HEAD's side. A
  value the work tree's file alone gives, on disk, while the merge is
  unresolved, is no finding now, as git reads no file; once the merge is
  resolved and staged, it is named as N1's is.

Every row types only the printed `git` lines, in order, and does by hand
only what the text says in words, then commits what is staged with a
plain `git commit`, as `tests/test_validate_family_index_gitmodules.py`
does: HEAD's `.gitmodules` is then right, the gate passes in every mode,
and a plain clone checks both members out.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from test_family import NAME, family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import cloned, type_line
from test_family_head_lost_gitmodules import committed_gitmodules
from test_family_holder_remedies_compose import (
    MODES, cloning, codes_of, ends_well, found_alike, typed_in_order,
)
from test_family_member_path import raw
from test_validate_family_index_gitmodules import (
    DIES_HERE, DIES_IN_A_CLONE, STALE, VALUE_SAID, committed_as_staged,
    head_bytes, staged_only, valued,
)
from test_validate_family_typed_states import ROW
from test_validate_family_unnamed_mounts import STAGE, commands

GITMODULES = ".gitmodules"
NOT_RUN = b"\tupdate = !true\n"

#: What the value's finding adds where the work tree's file gives it, not
#: HEAD's, and the index's does too.
INDEX_TOO = ("The index's file, which a plain `git commit` records, gives "
             "it too.")

#: What the value's finding says where the work tree's file and the
#: index's give it, not HEAD's: the key taken out, then the file staged.
INDEX_TOO_TAKEN_OUT = (
    VALUE_SAID.format(where="in the work tree, not in HEAD", dies=DIES_HERE)
    + INDEX_TOO + " Take the key out by hand, in a POSIX shell, then stage "
    ".gitmodules:\n    git config -f .gitmodules --unset-all "
    f"submodule.{ROW}.update\n    {STAGE}")

#: How git dies on a value the index's file alone gives.
DIES_IN_THE_COMMIT = ("so in a clone of the commit that records it neither "
                      "`git submodule update` nor make bootstrap checks out "
                      "any member")

#: A line git cannot parse, as `tests/test_family_gitmodules_values.py`'s
#: RV1124 probe P9 has it.
UNPARSED = b"this is no config line\n"


def a_plain_clone_of_what_is_staged(root: Path, env: dict, family,
                                    tmp_path: Path):
    """A copy of `root` whose staged `.gitmodules` a plain `git commit`
    records, then a plain clone of that commit and its `git submodule
    update --init --recursive`, whose result is returned: what the text
    says a clone of the commit that records the file does."""
    copy = tmp_path / "staged-copy" / NAME
    shutil.copytree(root, copy, symlinks=True)
    raw(copy, env, "commit", "-q", "-m", "What is staged, committed")
    where = tmp_path / "staged-clone"
    where.mkdir()
    clone = cloned(copy, env, family, where, recurse=False)
    return raw(clone, env, "submodule", "update", "--init", "--recursive",
               check=False)


# --- N1: the index's file beside the work tree's on disk ---------------------

def test_a_value_the_work_tree_s_file_and_the_index_s_give_ends_staging_it(
        family, holder, offline, tmp_path):
    """RV1124's P1: `update = !true` in MEMBER's section, in the work
    tree's file on disk and staged; HEAD's does not give it. The line
    took the key out of the work tree's file and staged nothing, so a
    plain `git commit` after it recorded the value in HEAD, and a plain
    clone's update died on it. The text says the index's file gives it
    too, and the lines end staging the file. Typed, then a plain `git
    commit`: HEAD is as it was, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    (holder / GITMODULES).write_bytes(valued(data, ROW, NOT_RUN))
    raw(holder, env, "add", "--", GITMODULES)

    found = found_alike(holder, *MODES)

    assert found == [INDEX_TOO_TAKEN_OUT]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_a_value_the_index_s_file_alone_gives_is_named_beside_a_clean_one(
        family, holder, offline, tmp_path):
    """RV1124's P1b: `update = !true` in MEMBER's section of the index's
    file alone; the work tree's, on disk, and HEAD's do not give it. Git
    reads the work tree's here, and `submodule status` exits 0, but a
    plain `git commit` records the index's, and a plain clone of that
    commit dies on it (exit 128). The gate said `family ok` in every
    mode. It is `gitmodules-value-refused` now, naming the index's file
    and the clone of the commit that records it, and its line stages the
    work tree's file. Typed, then a plain `git commit`: HEAD is as it was,
    and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    staged_only(holder, env, valued(data, ROW, NOT_RUN))
    (holder / GITMODULES).write_bytes(data)
    raw(holder, env, "submodule", "status")
    died = a_plain_clone_of_what_is_staged(holder, env, family, tmp_path)
    assert died.returncode == 128, ("premise: a clone of the commit dies",
                                    died.stderr)

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="in the index's file alone, which a plain "
                          "`git commit` records, not in the work tree or in "
                          "HEAD", dies=DIES_IN_THE_COMMIT)
        + "Stage the work tree's .gitmodules, which does not give it:"
        f"\n    {STAGE}"]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_a_value_here_and_in_head_ends_staging_it_with_no_index_s_file(
        family, holder, offline, tmp_path):
    """`update = !true` committed in MEMBER's section, the work tree's
    file on disk giving it too, and `git rm --cached` has taken
    `.gitmodules` out of the index: git reads the work tree's here, and
    the index's, which a plain `git commit` records, gives nothing. HEAD's
    giving the value is what makes the lines end staging the work tree's
    file, not the index's: with no stage line, a plain `git commit` after
    them records `.gitmodules` gone from HEAD. Typed, then a plain `git
    commit`: HEAD gives no value, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    committed_gitmodules(holder, env, valued(data, ROW, NOT_RUN))
    raw(holder, env, "rm", "-q", "--cached", "--", GITMODULES)

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="here and in HEAD, which a clone reads",
                          dies=DIES_HERE)
        + "Take the key out by hand, in a POSIX shell, then stage and "
        "commit .gitmodules:\n    git config -f .gitmodules --unset-all "
        f"submodule.{ROW}.update\n    {STAGE}"]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- N2: an index's file git cannot parse ------------------------------------

#: What comes before the line git cannot parse in the index's file, the
#: work tree's deleted: `(the edit of HEAD's bytes, what git's own
#: `submodule status` exits, a word of what it says, the code the gate
#: finds once the line is mended)`. Before a value, git dies on the value
#: (RV1124's P9); after a section, it reads up to the line, says it, and
#: goes on.
BEFORE_THE_LINE = {
    "a-value": (lambda data: valued(data, ROW, NOT_RUN), 128,
                b"invalid value", "gitmodules-value-refused"),
    "a-section": (lambda data: data + STALE, 0, b"bad config line",
                  "gitmodules-path-unnamed"),
}

#: What the gate says of the index's file git cannot parse.
UNREADABLE_LEAD = ("REFUSED gitmodules-unreadable: the index's .gitmodules "
                   "could not be read as git reads it: `git config -z "
                   "--blob :.gitmodules --list` in ")
UNREADABLE_REMEDY = (
    "Remediation: git reads it only up to that line where the work tree "
    "holds no .gitmodules, and a clone of a commit that records it dies "
    "reading it, before it checks out any member. Mend .gitmodules in the "
    "work tree by hand (`git config -f .gitmodules --list` says where it "
    "breaks; where the work tree holds none, `git checkout -- .gitmodules` "
    "puts the index's back first), stage it with `git add -- .gitmodules`, "
    "then run this again.")


@pytest.mark.parametrize("edit, status, said, then",
                         BEFORE_THE_LINE.values(), ids=BEFORE_THE_LINE)
def test_an_index_s_file_git_cannot_parse_is_refused_unreadable(
        family, holder, offline, tmp_path, edit, status, said, then):
    """RV1124's P9: the index's file, the work tree's deleted, is HEAD's
    with `update = !true` in MEMBER's section, or a stale section, and
    then a line git cannot parse. `git config --blob` printed the entries
    before the line and exited 128, and the gate read nothing: `family
    ok` in every mode, while git's own `submodule status` died on the
    value, or read the section. It is `gitmodules-unreadable` now, exit 2,
    as HEAD's file is, and a clone of a commit that records the file dies
    reading it, as the remediation says. Done as it says, the line taken
    out by hand: the gate finds what the file gave before it, and that
    finding's lines, typed, then a plain `git commit`, leave HEAD as it
    was, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    staged_only(holder, env, edit(data) + UNPARSED)
    git_said = raw(holder, env, "submodule", "status", check=False)
    assert git_said.returncode == status, git_said.stderr
    assert said in git_said.stderr, git_said.stderr
    died = a_plain_clone_of_what_is_staged(holder, env, family, tmp_path)
    assert died.returncode == 128, ("premise: a clone of the commit dies",
                                    died.stderr)

    for extra in MODES:
        gate = validate(holder, *extra)
        assert gate.returncode == 2, (extra, gate.stdout + gate.stderr)
        lead, remedy = gate.stderr.splitlines()
        assert lead.startswith(UNREADABLE_LEAD), lead
        assert "bad config line" in lead, lead
        assert remedy == UNREADABLE_REMEDY, remedy
    type_line(holder, env, re.search(r"`(git checkout [^`]*)`",
                                     UNREADABLE_REMEDY).group(1))
    put_back = (holder / GITMODULES).read_bytes()
    assert put_back.endswith(UNPARSED), put_back
    (holder / GITMODULES).write_bytes(put_back[:-len(UNPARSED)])
    type_line(holder, env, re.search(r"`(git add [^`]*)`",
                                     UNREADABLE_REMEDY).group(1))
    assert codes_of(found_alike(holder, *MODES)) == [then]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- N6: an unmerged .gitmodules ---------------------------------------------

def unmerged(root: Path, env: dict, base: bytes, ours: bytes,
             theirs: bytes) -> None:
    """`.gitmodules` held at a merge's conflict stages 1 to 3, `base`,
    `ours` and `theirs`, and not at stage 0, as a conflicted merge leaves
    it, by index records written as BYTES on stdin: first the zero-mode
    record that drops the stage-0 entry, as
    `tests/test_validate_family_unnamed_mounts.py`'s
    `stage_unmerged_gitlink` does it."""
    def blob(data: bytes) -> str:
        return raw(root, env, "hash-object", "-w", "--stdin",
                   stdin=data).stdout.decode("ascii").strip()

    records = (f"0 {'0' * 40}\t{GITMODULES}\n"
               f"100644 {blob(base)} 1\t{GITMODULES}\n"
               f"100644 {blob(ours)} 2\t{GITMODULES}\n"
               f"100644 {blob(theirs)} 3\t{GITMODULES}\n")
    raw(root, env, "update-index", "--index-info", stdin=records.encode())
    staged = raw(root, env, "ls-files", "-s", "--", GITMODULES).stdout
    assert [line.split()[2] for line in staged.splitlines()] == [
        b"1", b"2", b"3"], staged


def git_reads_none(root: Path, env: dict) -> None:
    """Git's `submodule status` in `root` reads no `.gitmodules` and dies
    at the first gitlink (exit 128)."""
    said = raw(root, env, "submodule", "status", check=False)
    assert said.returncode == 128, said.stderr
    assert b"no submodule mapping found" in said.stderr, said.stderr


#: How the work tree's file is left beside the unmerged index: deleted, or
#: on disk as the merge left it, HEAD's side, which gives the value.
LEFT = ["deleted", "on-disk"]


@pytest.mark.parametrize("left", LEFT)
def test_a_value_head_gives_while_a_merge_leaves_the_file_unmerged(
        family, holder, offline, tmp_path, left):
    """RV1124's P6: `update = !true` committed in MEMBER's section, then
    `.gitmodules` at a merge's conflict stages, HEAD's side giving the
    value and the other mending it, with the work tree's file deleted, or
    on disk as HEAD's side. Git reads no file here, and its `submodule
    status` dies at the first gitlink. The gate read HEAD's, or the work
    tree's: "here and in HEAD", with a line that put HEAD's back "as the
    index holds none", or "here" with no word of the merge. It names
    HEAD's, which a clone reads, says git reads none here, and says to
    resolve the merge without the key and stage it. Resolved by hand as
    it says, the line typed, then a plain `git commit`: HEAD gives no
    value, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    given = valued(data, ROW, NOT_RUN)
    committed_gitmodules(holder, env, given)
    unmerged(holder, env, data, given, data)
    if left == "deleted":
        (holder / GITMODULES).unlink()
    git_reads_none(holder, env)

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="in HEAD, which a clone reads, not in the "
                          "file git reads here, which is none while a merge "
                          "leaves .gitmodules unmerged", dies=DIES_IN_A_CLONE)
        + "Resolve the merge in .gitmodules by hand, leaving that key out, "
        f"then stage and commit .gitmodules:\n    {STAGE}"]
    (holder / GITMODULES).write_bytes(data)
    for line in commands(found[0]):
        type_line(holder, env, line)
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_a_value_the_work_tree_alone_gives_while_unmerged_waits_for_git(
        family, holder, offline, tmp_path):
    """RV1124's P6b, the one change of finding this makes: `.gitmodules`
    at a merge's conflict stages, the other side giving `update = !true`
    in MEMBER's section, and the work tree's file on disk giving it, as a
    merge resolved by hand to that side and not yet staged leaves it;
    HEAD's does not give it. Git reads no file here, and its `submodule
    status` dies at the first gitlink, not on the value. The gate read the
    work tree's file and named the value "in the work tree, not in HEAD";
    it reads none while the merge is unresolved now, and every mode
    passes, since no file git reads gives the value. Once the merge is
    resolved with a plain `git add`, git reads the work tree's file, and
    the gate names the value as N1's: its lines typed, then a plain `git
    commit`, HEAD is as it was, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    given = valued(data, ROW, NOT_RUN)
    unmerged(holder, env, data, data, given)
    (holder / GITMODULES).write_bytes(given)
    git_reads_none(holder, env)

    for extra in MODES:
        gate = validate(holder, *extra)
        assert gate.returncode == 0, (extra, gate.stdout + gate.stderr)
    raw(holder, env, "add", "--", GITMODULES)
    assert found_alike(holder, *MODES) == [INDEX_TOO_TAKEN_OUT]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_no_section_is_read_while_a_merge_leaves_the_file_unmerged(
        family, holder, offline, tmp_path):
    """RV1124's N6, its sections: a stale section for `members/Old`
    committed, then `.gitmodules` at a merge's conflict stages, HEAD's
    side keeping it and the other taking it out, the work tree's deleted.
    Git reads no file here. `gitmodules-path-unnamed` read HEAD's and
    named the section with `git checkout HEAD -- .gitmodules` first, put
    back "as the index holds none", which resolves the merge to HEAD's
    side. No section is read here now, and no line resolves the merge.
    Resolved by hand to HEAD's side and staged, git reads it, and the
    section is named; its lines typed, then a plain `git commit`: HEAD
    gives the two members alone, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    committed_gitmodules(holder, env, data + STALE)
    unmerged(holder, env, data + STALE, data + STALE, data)
    (holder / GITMODULES).unlink()
    git_reads_none(holder, env)

    for extra in MODES:
        gate = validate(holder, *extra)
        assert gate.returncode == 0, (extra, gate.stdout + gate.stderr)
        assert "git checkout HEAD" not in gate.stderr, gate.stderr
    (holder / GITMODULES).write_bytes(data + STALE)
    raw(holder, env, "add", "--", GITMODULES)
    assert codes_of(found_alike(holder, *MODES)) == [
        "gitmodules-path-unnamed"]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)
