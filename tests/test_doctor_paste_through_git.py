# SPDX-License-Identifier: Apache-2.0
"""A line the doctor tests paste reads a just-pushed remote through git, as
every other clone of the suite does (#835).

`paste()` runs a row's NEXT exactly as printed, and the NEXT of a `legs` or
`members` row is `git -C <root> submodule update --init --recursive
--checkout -- <paths>`, which CLONES a mount that is empty. The URL
`.gitmodules` records for it is the plain path of a bare repository the
fixtures pushed into, so git's clone of it is the LOCAL clone: it links the
remote's `objects/` one file at a time, which is the walk #440's race needs
(#645 keeps maintenance from starting, so nothing breaks today, and #662 puts
every other read of these remotes through git as a second guard).

WHAT IS MEASURED, on a pasted `submodule update --init` of an empty mount:

- with no rewrite, the clone's store holds the remote's 8 loose objects, each
  with a link count of 2, and no pack. `GIT_TRACE` shows `upload-pack`, which a
  local clone starts to list the refs, and so tells the two apart no better
  than `git clone` does: what it does not show is `pack-objects`;
- with `read_through_git`'s `url.<file URI>.insteadOf` entries, the clone's
  store holds one pack and no loose object, and `GIT_TRACE` shows
  `pack-objects` and `index-pack` as well. The clone's `origin`, and the
  `submodule.<name>.url` the superproject records, keep the plain path.

Each test here asks one of those of git, and the last holds every `paste` of
`test_doctor_legs_members_next.py` to handing the remotes it can clone from.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from conftest import (NO_AUTO_MAINTENANCE, WINDOWS_SKIP,
                      appended_to_command_scope, assert_read_through_git,
                      assert_store_read_through_git, git, insteadof_entries)
from test_doctor_legs_members_next import (
    FAMILY_MEMBER, holder_copy, holder_without, make_empty_mount,
    member_unbootstrapped, paste, remotes_of, row_of)
from test_shape_doctor import (  # noqa: F401
    holder, project, scaffolded_here, standard)

#: What `GIT_TRACE` prints for a child git runs: the line names the command
#: after `run_command:`.
PACK_OBJECTS = re.compile(r"run_command: git pack-objects ")
INDEX_PACK = re.compile(r"run_command: git index-pack ")


def assert_the_trace_shows_a_transfer(result) -> None:
    """The pasted line fetched a pack: `pack-objects` ran in the remote and
    `index-pack` in the clone. `upload-pack` alone is a local clone's ref
    listing."""
    assert result.returncode == 0, result.stdout + result.stderr
    assert PACK_OBJECTS.search(result.stderr), result.stderr[-2000:]
    assert INDEX_PACK.search(result.stderr), result.stderr[-2000:]


def assert_no_rewrite_is_stored(root: Path, leg: Path) -> None:
    """The rewrite was for the one run: neither the superproject's config
    nor the clone's holds an `insteadOf`."""
    for repo in (root, leg):
        stored = git("config", "--local", "--list", cwd=repo).stdout
        assert "insteadof" not in stored.lower(), stored


@WINDOWS_SKIP
def test_a_pasted_update_of_an_empty_mount_reads_the_remote_through_git(
        standard, project, scaffolded_here, tmp_path, monkeypatch):
    made = make_empty_mount(project)
    row = row_of(standard, project, "legs")
    monkeypatch.setenv("GIT_TRACE", "1")
    result = paste(row, tmp_path / "elsewhere", remotes_of(scaffolded_here))
    assert_the_trace_shows_a_transfer(result)
    leg = project / made["paths"][0]
    assert_store_read_through_git(leg, f"the {leg.name} leg the line cloned")
    plain = git("config", "--file", ".gitmodules",
                f"submodule.{leg.name}.url", cwd=project).stdout.strip()
    assert git("remote", "get-url", "origin",
               cwd=leg).stdout.strip() == plain
    assert not plain.startswith("file:"), plain
    assert_no_rewrite_is_stored(project, leg)


@WINDOWS_SKIP
def test_a_pasted_update_of_a_members_mount_reads_it_and_its_legs_through_git(
        standard, holder, tmp_path, monkeypatch):
    """`--recursive` clones the member's own legs too, from the plain paths
    the member's `.gitmodules` records."""
    root = holder_copy(holder, tmp_path)
    holder_without(root, "bootstrap.py")
    member_unbootstrapped(root)
    row = row_of(standard, root, "members")
    monkeypatch.setenv("GIT_TRACE", "1")
    result = paste(row, tmp_path / "elsewhere", remotes_of(holder))
    assert_the_trace_shows_a_transfer(result)
    assert_read_through_git(root / "members" / FAMILY_MEMBER)
    assert_no_rewrite_is_stored(root, root / "members" / FAMILY_MEMBER)


@WINDOWS_SKIP
def test_a_paste_without_the_remotes_is_the_local_clone_it_was(
        standard, project, tmp_path, monkeypatch):
    """The measurement the others stand on: handed no remotes, the same line
    leaves the mount's store as the remote's own files, loose and linked,
    and `pack-objects` is never run. A test that asked for none of this
    would pass on the plain path as it does on the rewrite."""
    made = make_empty_mount(project)
    row = row_of(standard, project, "legs")
    monkeypatch.setenv("GIT_TRACE", "1")
    result = paste(row, tmp_path / "elsewhere")
    assert result.returncode == 0, result.stdout + result.stderr
    assert not PACK_OBJECTS.search(result.stderr), result.stderr[-2000:]
    with pytest.raises(AssertionError, match="loose objects"):
        assert_store_read_through_git(project / made["paths"][0], "the leg")


@WINDOWS_SKIP
def test_the_rewrite_follows_the_entries_the_environment_holds(
        scaffolded_here, tmp_path, monkeypatch):
    """The Windows job's two entries and the session's two settings, put in
    the environment after the doctor tests were imported, come first; then
    `protocol.file.allow`; then each `insteadOf` entry `read_through_git`
    would add, in its order. `GIT_CONFIG_PARAMETERS` is taken away first:
    git lists its entries after the count's."""
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    held = appended_to_command_scope(
        {}, [("test.heldone", "one"), ("test.heldtwo", "two")])
    for name, value in {**held, **appended_to_command_scope(
            held, NO_AUTO_MAINTENANCE)}.items():
        monkeypatch.setenv(name, value)
    remotes = remotes_of(scaffolded_here)
    shown = paste({"next": "git config --show-origin --list"},
                  tmp_path / "elsewhere", remotes)
    assert shown.returncode == 0, shown.stderr + shown.stdout
    from_the_command_line = [
        line.split("\t", 1)[1] for line in shown.stdout.splitlines()
        if line.startswith("command line:")]

    def as_listed(key: str, value: str) -> str:
        """git lists the variable name lower-cased, and the URL in the
        subsection as it was written."""
        section, _, name = key.rpartition(".")
        return f"{section}.{name.lower()}={value}"

    assert from_the_command_line == [
        "test.heldone=one", "test.heldtwo=two",
        *(f"{key}={value}" for key, value in NO_AUTO_MAINTENANCE),
        "protocol.file.allow=always",
        *(as_listed(key, prefix)
          for key, prefix in insteadof_entries(remotes))]


def pastes_in(path: Path) -> list:
    """Each call of `paste` in the Python file at `path`, as `(line, number of
    arguments it is given)`: positional ones and keywords alike."""
    return [(node.lineno, len(node.args) + len(node.keywords))
            for node in ast.walk(ast.parse(path.read_bytes()))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "paste"]


def test_every_paste_of_the_doctor_tests_is_handed_the_remotes():
    """`paste(row, cwd, remotes)`: a pasted line is run exactly as printed,
    so the rewrite is the only way its clone of a mount is read through git,
    and a call that leaves it out is not told apart from one that is by any
    test of the line. Every `paste` in `test_doctor_legs_members_next.py`
    names the remotes the root was made from (`remotes_of`)."""
    found = pastes_in(Path(__file__).resolve().parent
                      / "test_doctor_legs_members_next.py")
    assert found, "no `paste` call was found: the walk reads the wrong file"
    assert [line for line, given in found if given < 3] == []


@pytest.mark.parametrize("source, expected", [
    ("paste(row, cwd)", [(1, 2)]),
    ("paste(row, cwd, remotes_of(holder))", [(1, 3)]),
    ("paste(row, cwd, remotes=remotes)", [(1, 3)]),
    ("x = paste(row_of(a, b, 'legs'), cwd,\n          remotes_of(here))",
     [(1, 3)]),
    ("pasted(row, cwd)", []),
], ids=["without", "positional", "keyword", "over-two-lines", "other-name"])
def test_the_walk_counts_what_each_paste_is_given(tmp_path, source, expected):
    walked = tmp_path / "walked.py"
    walked.write_bytes(source.encode("utf-8"))
    assert pastes_in(walked) == expected
