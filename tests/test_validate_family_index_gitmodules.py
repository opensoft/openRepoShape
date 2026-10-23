# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/validate-family.py`: its
`.gitmodules` checks read the file git reads, and a section's lines leave
nothing for a plain `git commit` to get wrong (#1077).

Git's submodule commands read the work tree's `.gitmodules`, and, where
that is gone from disk, the index's, then HEAD's (git 2.43; #1036 measured
it, and #1077's body measured that the index's is read over HEAD's).
`gitmodules-path-unnamed` reads that file since #1036. RV1069's review of
#1069 found two checks that did not, and two more things, each reproduced
on main 2a119f28 before this change:

- NIT 1. `gitmodules-path-twice` read the work tree's file alone: a second
  section for `members/IRRS`, staged in the index's file alone and the
  work tree's deleted, was no finding in any mode, and a clean clone of
  the commit after it failed its update and its gate.
- NIT 2. The check for values git dies on read the work tree's file and
  HEAD's: an `update = !true` staged in the index's file alone, in a named
  member's section, the work tree's deleted, was no finding, while git's
  own `submodule status` dies on it. Its finding puts back the file git
  reads now, not HEAD's, and where HEAD's alone gives the value it says
  to commit the index's, with no line, so a `member-gitmodules-absent`
  after it puts the file back itself.
- NIT 3. Where HEAD's file holds the section, its lines ended "then commit
  .gitmodules" and staged nothing, so a plain `git commit` after them
  left the section in HEAD, and a clone's gate failed. They end with `git
  add -- .gitmodules` now, saying "then stage and commit".
- NIT 4. No row covered the case-variant branch's stage line where HEAD's
  holds no section of the name. RV1069's probe `test_r2_stray_not_in_head`
  is that row here.

Every row types only the printed `git` lines, in order, and does by hand
only what the text says in words, then commits what is staged with a
plain `git commit`, the way #1036's Verify commits: HEAD's `.gitmodules`
is then right, the gate passes in every mode, and a plain clone checks
both members out.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

import pytest

from test_family import family, validate  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_bootstrap_gate_order import type_line
from test_family_head_lost_gitmodules import (
    absent, committed_gitmodules, pinned,
)
from test_family_holder_bootstrap_texts import (
    put_back_first, section_taken_out,
)
from test_family_holder_remedies_compose import (
    MODES, OTHER_ROW, cloning, codes_of, ends_well, found_alike, head_paths,
    typed_in_order,
)
from test_family_member_path import OTHER, raw
from test_family_unnamed_gitlink import at_tools
from test_validate_family_typed_states import GONE, ROW, gone
from test_validate_family_unnamed_mounts import (
    SECTION_SAID, STAGE, VARIANT, commands, removal, with_section,
)

GITMODULES = ".gitmodules"


def staged_only(root: Path, env: dict, data: bytes) -> None:
    """`data` staged as `.gitmodules` in the index alone, hashed into
    git's objects as BYTES, and the work tree's file deleted: git reads
    the index's in its place."""
    blob = raw(root, env, "hash-object", "-w", "--stdin",
               stdin=data).stdout.decode("ascii").strip()
    raw(root, env, "update-index", "--cacheinfo",
        f"100644,{blob},{GITMODULES}")
    (root / GITMODULES).unlink(missing_ok=True)


def committed_as_staged(root: Path, env: dict) -> None:
    """A plain `git commit` of what is staged, and nothing else: no `git
    add` the text does not print or say. Where nothing is staged it exits
    1, `nothing to commit`, and HEAD is as it was."""
    raw(root, env, "commit", "-q", "-m", "What is staged", check=False)


def head_bytes(root: Path, env: dict) -> bytes:
    """HEAD's `.gitmodules`."""
    return raw(root, env, "show", f"HEAD:{GITMODULES}").stdout


# --- NIT 1: gitmodules-path-twice --------------------------------------------

SECOND = (f'[submodule "second"]\n\tpath = {ROW}\n'
          "\turl = https://github.com/InkRouter/Second.git\n").encode()

#: What `gitmodules-path-twice` says where the work tree's file is gone,
#: before what it says to take out.
TWICE_PUT_BACK = (", put .gitmodules, gone from the work tree, back first "
                  "from the index's, `git checkout -- .gitmodules`, so that "
                  "every other section stays, and take each other out by "
                  "hand")


def test_1077_a_second_section_the_index_alone_gives_is_path_twice(
        family, holder, offline, tmp_path):
    """NIT 1: a second section for `members/IRRS`, `second`, staged in the
    index's `.gitmodules` alone, the work tree's deleted. Git reads the
    index's file, so a recursive clone of the commit after it fetches
    `members/IRRS` from `second`'s url. Main read the work tree's file
    alone and said `family ok`. It is `gitmodules-path-twice` now, in
    every mode, naming the put-back first. Done as it says, the put-back
    line typed, `second`'s keys taken out by hand, then staged and
    committed: HEAD gives the two members alone, and the gate and a plain
    clone pass."""
    env = cloning(offline, tmp_path, family)
    staged_only(holder, env, head_bytes(holder, env) + SECOND)

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["gitmodules-path-twice"]
    (twice,) = found
    assert f"gives the path {ROW} to 2 submodules" in twice, twice
    assert TWICE_PUT_BACK in twice, twice
    assert twice.endswith("then stage and commit .gitmodules."), twice
    type_line(holder, env, re.search(r"`(git checkout [^`]*)`",
                                     twice).group(1))
    for key in ("path", "url"):
        type_line(holder, env, shlex.join(
            ["git", "config", "-f", GITMODULES, "--unset-all",
             f"submodule.second.{key}"]))
    raw(holder, env, "add", "--", GITMODULES)
    committed_as_staged(holder, env)
    assert b"second" not in head_bytes(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


#: A section for a path no row names, in HEAD's file as the work tree's was
#: committed: `gitmodules-path-unnamed`'s, after path-twice's.
STALE = (b'[submodule "members/Old"]\n\tpath = members/Old\n'
         b"\turl = /nowhere/old.git\n")


@pytest.mark.parametrize("how", GONE)
def test_1077_path_twice_records_its_put_back_for_the_next_finding(
        family, holder, offline, tmp_path, how):
    """RV1124's N3(b): HEAD's file holds `second`, a second section for
    `members/IRRS`, and a stale `members/Old`, and `.gitmodules` is gone
    from the work tree. Path-twice names the put-back first; it is
    recorded (`_file_put_back`), so `gitmodules-path-unnamed` after it
    puts nothing back. Unrecorded, that finding printed the put-back
    again, and typed in order it put the file back over the hand edit:
    the commit then kept `second` and `members/Old` in HEAD. Typed in
    order as printed, then a plain `git commit`: HEAD loses both, and the
    gate passes in every mode."""
    env = cloning(offline, tmp_path, family)
    committed_gitmodules(holder, env,
                         head_bytes(holder, env) + SECOND + STALE)
    gone(holder, env, how)

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["gitmodules-path-twice",
                               "gitmodules-path-unnamed"], found
    twice, unnamed = found
    put_back = GONE[how][1]
    assert f"`{put_back}`" in twice, twice
    assert put_back not in unnamed, unnamed
    type_line(holder, env, put_back)
    for key in ("path", "url"):
        type_line(holder, env, shlex.join(
            ["git", "config", "-f", GITMODULES, "--unset-all",
             f"submodule.second.{key}"]))
    raw(holder, env, "add", "--", GITMODULES)
    for command in commands(unnamed):
        if command.startswith("git "):
            type_line(holder, env, command)
    committed_as_staged(holder, env)
    kept = head_bytes(holder, env)
    assert b"second" not in kept and b"members/Old" not in kept
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


# --- NIT 2: a value git dies on, in the index's file -------------------------

def valued(data: bytes, path: str, line: bytes) -> bytes:
    """`.gitmodules` bytes with `line` after the section giving `path`'s
    path line."""
    given = f"\tpath = {path}\n".encode()
    assert data.count(given) == 1, data
    return data.replace(given, given + line)


#: What `gitmodules-value-refused` says of `update = !true` in MEMBER's
#: section, by where it is given, up to its remedy.
VALUE_SAID = (
    "FINDING gitmodules-value-refused: .gitmodules gives "
    f"`submodule.{ROW}.update` the value `!true` {{where}}, and git dies "
    "reading a file that does, {dies}. Git takes one of `none`, "
    "`checkout`, `rebase` or `merge` for that key. ")
DIES_HERE = ("before `git submodule update` checks out any member, so "
             "neither that nor make bootstrap checks one out")
DIES_IN_A_CLONE = ("so in a clone neither `git submodule update` nor make "
                   "bootstrap checks out any member")


def test_1077_a_value_the_index_alone_gives_is_named_and_taken_out(
        family, holder, offline, tmp_path):
    """NIT 2: `update = !true` in MEMBER's own section, a named member's,
    staged in the index's `.gitmodules` alone, the work tree's deleted.
    Git reads the index's file and dies on it (`git submodule status`,
    exit 128). Main read the work tree's file and HEAD's and said `family
    ok`. It is `gitmodules-value-refused` now, in every mode, naming the
    index's file, and its lines put that file back, not HEAD's, and take
    the key out; the text says to stage the file. Typed, staged as it
    says and committed: nothing is left, and the gate and a plain clone
    pass."""
    env = cloning(offline, tmp_path, family)
    staged_only(holder, env, valued(head_bytes(holder, env), ROW,
                                    b"\tupdate = !true\n"))
    status = raw(holder, env, "submodule", "status", check=False)
    assert status.returncode == 128, "premise: git dies reading it"

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="in the index's file, which git reads here, "
                          "not in HEAD", dies=DIES_HERE)
        + "The work tree holds no .gitmodules, so the first line below puts "
        "back the index's. Take the key out by hand, in a POSIX shell, then "
        "stage .gitmodules:\n    git checkout -- .gitmodules\n    git "
        f"config -f .gitmodules --unset-all submodule.{ROW}.update"]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    raw(holder, env, "add", "--", GITMODULES)
    committed_as_staged(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_1077_a_value_head_alone_gives_says_to_commit_the_index_s_file(
        family, holder, offline, tmp_path):
    """NIT 2's other half, lane 1's NIT 1 on #889: `update = !true`
    committed in MEMBER's section, then the file mended and staged, and
    the work tree's deleted. Git reads the index's, which does not give
    it, and a clone reads HEAD's, which does. Main put HEAD's file back
    over the staged fix and took the key out of it again. It says to
    commit the index's file now, with no line. A plain `git commit` then
    records the fix, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    staged_only(holder, env, valued(data, ROW, b"\tupdate = !true\n"))
    raw(holder, env, "commit", "-q", "-m", "update = !true committed")
    staged_only(holder, env, data)

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="in HEAD, which a clone reads, not in the "
                          "index's file, which git reads here",
                          dies=DIES_IN_A_CLONE)
        + "Commit the index's .gitmodules, which git reads here and does "
        "not give it."]
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    raw(holder, env, "checkout", "--", GITMODULES)
    ends_well(holder, env, family, tmp_path)


def test_1077_where_head_alone_gives_a_value_a_section_puts_the_file_back(
        family, holder, offline, tmp_path):
    """NIT 2's other half beside `member-gitmodules-absent`: `update =
    !true` committed in MEMBER's section, with OTHER's section taken out,
    then the file mended and staged, OTHER's still out, and the work
    tree's deleted. The value's finding says to commit the index's file
    and puts nothing back, so OTHER's finding puts it back first itself:
    with no file there, its `git config -f` lines made a file of OTHER's
    section alone, and staged and committed, MEMBER's was lost. Typed as
    printed, staged and committed as it says: HEAD gives both members and
    no value, and the gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    committed_gitmodules(holder, env, section_taken_out(
        valued(data, ROW, b"\tupdate = !true\n"), OTHER))
    staged_only(holder, env, section_taken_out(data, OTHER))

    found = found_alike(holder, *MODES)

    assert found == [
        VALUE_SAID.format(where="in HEAD, which a clone reads, not in the "
                          "index's file, which git reads here",
                          dies=DIES_IN_A_CLONE)
        + "Commit the index's .gitmodules, which git reads here and does "
        "not give it.",
        put_back_first(absent(OTHER, pinned(holder, OTHER), held=True),
                       "deleted")]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    raw(holder, env, "add", "--", GITMODULES)
    committed_as_staged(holder, env)
    assert b"!true" not in head_bytes(holder, env)
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)


def test_1077_a_url_git_dies_on_is_written_back_as_the_file_git_reads_gave_it(
        family, holder, offline, tmp_path):
    """RV1124's N3(a): the index's file, the work tree's deleted, gives
    MEMBER's section a `url` that is not HEAD's, then a `url` with no
    value, which git dies on. The line that writes the url back, as it
    last gave one, takes it from the file git reads (the index's), not
    HEAD's: from HEAD's it undid what was staged. Typed in order, then
    staged and committed: HEAD gives the staged url, and the gate passes
    in `--no-members`."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    url = "https://github.com/InkRouter/Staged.git"
    edited, count = re.subn(
        rb"(\tpath = " + re.escape(ROW.encode()) + rb"\n)\turl = [^\n]*\n",
        rb"\1\turl = " + url.encode() + rb"\n\turl\n", data)
    assert count == 1, data
    assert url.encode() not in data
    staged_only(holder, env, edited)
    assert raw(holder, env, "submodule", "status",
               check=False).returncode == 128, "premise: git dies reading it"

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["gitmodules-value-refused"], found
    lines = commands(found[0])
    assert lines[0] == "git checkout -- .gitmodules", lines
    assert lines[-1] == (f"git config -f .gitmodules submodule.{ROW}.url "
                         f"{url}"), lines
    typed_in_order(holder, env, validate(holder, "--no-members"))
    raw(holder, env, "add", "--", GITMODULES)
    committed_as_staged(holder, env)
    assert url.encode() in head_bytes(holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    assert validate(holder, "--no-members").returncode == 0


# --- NIT 3: where HEAD's file holds the section ------------------------------

def stale_section(root: Path, env: dict, family) -> str:
    """A section for `members/Old`, which no row names and no gitlink is
    at, committed. Returns its name."""
    with_section(root, root.parent, "members/Old", "members/Old",
                 "/nowhere/old.git")
    return "members/Old"


def committed_tools_x(root: Path, env: dict, family) -> str:
    """IRSS mounted at tools/x with `git submodule add` and committed
    (rv882's SHOULD 2 state). Returns its section's name."""
    return at_tools(root, env, family)[0]


#: `(how the section HEAD holds is made, what is left untracked)`.
HELD = {"a-stale-section": (stale_section, b""),
        "tools-x-committed": (committed_tools_x, b"?? tools/\n")}

#: How the work tree's `.gitmodules` is, or is not, there.
DISKS = ["on-disk", *GONE]


@pytest.mark.parametrize("disk", DISKS)
@pytest.mark.parametrize("make, left", HELD.values(), ids=HELD)
def test_1077_a_section_head_holds_comes_out_under_a_plain_commit(
        family, holder, offline, tmp_path, make, left, disk):
    """NIT 3: a section HEAD's `.gitmodules` holds and no row names, a
    stale one or tools/x's with its gitlink, with the work tree's file on
    disk, deleted, or its deletion staged. The lines ended "then commit
    .gitmodules" and staged nothing: a plain `git commit` after them left
    the section in HEAD (exit 1, `no changes added`, or, for tools/x, exit
    0 with the gitlink's removal alone), the local gate passed and a
    clone's failed. They end with `git add -- .gitmodules` now, saying
    "then stage and commit". Only the printed lines typed, then a plain
    `git commit`: HEAD gives the two members alone, and the gate and a
    plain clone pass."""
    env = cloning(offline, tmp_path, family)
    name = make(holder, env, family)
    if disk != "on-disk":
        gone(holder, env, disk)

    found = found_alike(holder, *MODES)

    assert codes_of(found) == ["gitmodules-path-unnamed"]
    assert commands(found[0])[-1] == STAGE, found[0]
    assert "then stage and commit .gitmodules:" in found[0], found[0]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert f'[submodule "{name}"]'.encode() not in head_bytes(holder, env)
    assert head_paths(holder, env) == {ROW, OTHER_ROW}
    assert raw(holder, env, "status", "--porcelain").stdout == left
    ends_well(holder, env, family, tmp_path)


# --- NIT 4: the case-variant branch, HEAD's holding no such section ----------

@pytest.mark.parametrize("disk", ["on-disk", "deleted"])
def test_1077_a_stray_section_head_does_not_hold_is_staged_out(
        family, holder, offline, tmp_path, disk):
    """NIT 4, RV1069's probe `test_r2_stray_not_in_head`: a section named
    `ghost` giving `Members/IRRS`, a case variant of MEMBER's path, staged
    in the index's `.gitmodules` alone, the work tree's on disk or
    deleted. HEAD's holds no section of that name, so the lines end with
    `git add -- .gitmodules`; without it, a plain `git commit` after them
    recorded `ghost`, and no row said so. Only the printed lines typed,
    then a plain `git commit`: HEAD is as it was, nothing is left, and the
    gate and a plain clone pass."""
    env = cloning(offline, tmp_path, family)
    data = head_bytes(holder, env)
    ghost = (b'[submodule "ghost"]\n\tpath = Members/IRRS\n'
             b"\turl = /nowhere/ghost.git\n")
    if disk == "deleted":
        staged_only(holder, env, data + ghost)
    else:
        (holder / GITMODULES).write_bytes(data + ghost)
        raw(holder, env, "add", "--", GITMODULES)

    found = found_alike(holder, *MODES)

    put_back = [GONE["deleted"][1]] if disk == "deleted" else []
    assert found == [
        SECTION_SAID.format(path="Members/IRRS", name="ghost",
                            url="url /nowhere/ghost.git")
        + VARIANT.format(row_path=ROW, project="IRRS")
        + " Take the section out by hand, in a POSIX shell, every key it "
        "holds, so a submodule later given its name inherits none of them, "
        + ("after the line that puts .gitmodules, gone from the work tree, "
           "back from the index's, so that every other section stays, "
           if put_back else "")
        + "then stage .gitmodules: HEAD's holds no section of that name, so "
        "nothing of it is left to commit:"
        + "".join(f"\n    {line}" for line in
                  [*put_back, *removal("ghost", "path", "url"), STAGE])]
    typed_in_order(holder, env, validate(holder, "--no-members"))
    committed_as_staged(holder, env)
    assert head_bytes(holder, env) == data
    assert raw(holder, env, "status", "--porcelain").stdout == b""
    ends_well(holder, env, family, tmp_path)
