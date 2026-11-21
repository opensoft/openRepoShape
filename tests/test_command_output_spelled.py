# SPDX-License-Identifier: Apache-2.0
"""A refused command's words reach a terminal spelled, whatever names them
(#1213, W1195's leftovers; it follows #1152 and #1195).

#1195 spelled the REFUSED block a refused command prints in
`adopt-project.py` and left three groups of sites that print a command's
words with no helper at all. Each is a row here.

GROUP 1, `_init_refused` (`adopt-project.py`). The NOTE `check` prints where
git refused to make a probe's throwaway repository names the `git init` it
ran, and its last argument is a directory made under the `--work-dir`. The
output beside it was `_spelled`; the arguments were not, so a bidirectional
control or an ESC in the work directory reached the terminal, and a line feed
split the NOTE.

GROUP 2, two refusals and a notice that print git's or gh's output.
`source-unclonable` (`Source.clone`) printed up to 400 characters of gh's
words; `adopt-remote-unreadable` (`_refuse_a_tracking_branch_the_remote_lacks`)
printed git's output on one line, or an `OSError`'s text; and the other route
to that code (`_in_the_way_on_github`) spelled gh's first line but printed an
`OSError`'s text as it was.

GROUP 3, `CommandFailed.loudly` (`scripts/shape_materialize.py`). It prints
the command, the directory it ran in and the output as they were, and sixteen
calls in `scaffold-project.py`, `update-shape.py`, `scripts/family.py` and
`scripts/bump-leg.py` print what it makes. THE CHOICE, WRITTEN WHERE THE NEXT
WRITER READS IT: `loudly` spells once, with `shape_materialize.unacted`, and
no tool spells at its call. The cost the issue names, that it moves every
tool's REFUSED block, was measured and is nil for every row that asserts
printable text, which is all of them: see `CommandFailed.loudly`. So there is
a row per call below, and each fails when its call prints the block raw.

WHAT EACH ROW IS. A command that fails with the character in its arguments,
in the directory it ran in or in what it printed, run as a person runs it
where that is cheap (a child process, a hook that refuses every push, a `gh`
stub), and where the failing command is the tool's own and the fixture is
costly, the function that prints the block, called with a `CommandFailed` it
would raise. The control is the same run with no such character: it passes on
the old code as well. A row asserts the block as it is spelled, and that no
raw U+202E, ESC or byte 0xff reaches stdout or stderr.

THE TEST SOURCE IS ASCII: every character that is not printable is built
with `chr`, and POSIX only: no Windows file name holds an escape or a line
feed, and the stubs are `#!/bin/sh` scripts.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import types
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, IDENTITY_EMAIL, IDENTITY_NAME, REPO, SCAFFOLD,
                      blank_unnamed_pin_sources, git, load_without_bytecode,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_the_environment_cannot_carry)
from test_adopt_check_throwaway_repos import linked_github_plan
from test_adopt_root_symlinks import links_as_links  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.name == "nt",
    reason="no Windows file name holds an escape or a line feed, and the "
           "stubs are `#!/bin/sh` scripts")

BACKSLASH = chr(92)
BIDI = chr(0x202E)
ESCAPE = chr(0x1B)
LINE_FEED = chr(0x0A)
TAB = chr(0x09)
RETURN = chr(0x0D)
#: A byte that is not UTF-8, as `os.fsdecode` keeps it in a name and `argv`.
BYTE = chr(0xDCFF)
E_ACUTE = chr(0xE9)
REPLACEMENT = chr(0xFFFD)

#: What a child's streams are given and read back with: a byte that is not
#: UTF-8 is written as itself, and read back as the surrogate that stands
#: for it, so a raw byte is the lone surrogate here.
ENCODING = "utf-8:surrogateescape"
ORG = "testorg"
PROJECT = "Thing"
FAMILY = "Fam"


def spelled(char: str) -> str:
    """`char` as a plan's `path:` writes it (`repo_shape.double_quoted`),
    written out here and not asked of the tool."""
    named = {LINE_FEED: "n", RETURN: "r", TAB: "t"}
    if char in named:
        return BACKSLASH + named[char]
    code = ord(char)
    return BACKSLASH + (f"x{code:02x}" if code < 0x100 else f"u{code:04x}")


def in_words(typed: str) -> str:
    """`typed` as the spelling writes it, and nothing for the control."""
    return spelled(typed) if typed else ""


#: The character each row names a refused command with, and the control. The
#: byte and the line feed are for the rows that can hold them.
UNSAFE = [
    pytest.param(BIDI, id="bidi-override-U+202E"),
    pytest.param(ESCAPE, id="escape"),
    pytest.param("", id="plain-control"),
]
EVERY = [*UNSAFE[:2],
         pytest.param(BYTE, id="byte-0xff-not-utf-8"),
         pytest.param(LINE_FEED, id="line-feed"),
         UNSAFE[2]]


def assert_none_raw(*texts: str, typed: str = "") -> None:
    """Nothing in `texts` holds U+202E, ESC or the byte 0xff, or `typed`:
    the characters this file names a command with, as they were typed."""
    said = "".join(texts)
    for raw in {BIDI, ESCAPE, BYTE, *([typed] if typed else [])}:
        if raw != LINE_FEED:
            assert raw not in said, said


def a_block(step: str, command: str, where: str | None, output: str,
            code: int = 128) -> str:
    """The REFUSED block `CommandFailed.loudly` prints, written out here."""
    return (f"REFUSED {step}. THE EXACT COMMAND WAS:\n    {command}\n"
            + ("" if where is None else f"    (in {where})\n")
            + f"    exit {code}\n--- output ---\n{output}\n--- end output ---")


# --- the modules ------------------------------------------------------------

def a_module(path: Path, name: str):
    return load_without_bytecode(path, name)


@pytest.fixture(scope="module")
def materializer():
    return a_module(REPO / "scripts" / "shape_materialize.py",
                    "materialize_command_output_spelled")


@pytest.fixture(scope="module")
def adopter():
    return a_module(ADOPT, "adopt_command_output_spelled")


@pytest.fixture(scope="module")
def scaffold():
    return a_module(SCAFFOLD, "scaffold_command_output_spelled")


@pytest.fixture(scope="module")
def updater():
    return a_module(REPO / "update-shape.py", "update_command_output_spelled")


@pytest.fixture(scope="module")
def familiar():
    return a_module(REPO / "scripts" / "family.py",
                    "family_command_output_spelled")


@pytest.fixture(scope="module")
def bumper():
    return a_module(REPO / "scripts" / "bump-leg.py",
                    "bump_command_output_spelled")


def refused_push(module, typed: str):
    """A `CommandFailed` as a refused push raises it, `typed` in the remote
    it was pushed to, the directory it ran in and what git said."""
    return module.CommandFailed(
        ["git", "push", "-q", f"/remotes/re{typed}mote/Thing.git",
         "HEAD:refs/heads/main"], f"/work/wo{typed}rk/Thing", 128,
        f"To /remotes/re{typed}mote/Thing.git\n"
        f" ! [remote rejected] (the hook said {typed}no)\n"
        "error: failed to push some refs\n")


def the_block_of_it(step: str, typed: str) -> str:
    """The block `refused_push` is said in, with `typed` spelled."""
    said = in_words(typed)
    return a_block(
        step, f"git push -q /remotes/re{said}mote/Thing.git "
        "HEAD:refs/heads/main", f"/work/wo{said}rk/Thing",
        f"To /remotes/re{said}mote/Thing.git\n"
        f" ! [remote rejected] (the hook said {said}no)\n"
        "error: failed to push some refs")


# --- `unacted` and `CommandFailed.loudly` -----------------------------------

@pytest.mark.parametrize("typed", [BIDI, ESCAPE, BYTE, TAB, RETURN,
                                   LINE_FEED, chr(0), chr(0x7F), chr(0x85)])
def test_unacted_spells_a_character_a_terminal_acts_on(materializer, typed):
    """Each character `str.isprintable` refuses is written as the plan's
    `path:` writes it, between the characters around it, as they are."""
    assert materializer.unacted(f"a{typed}b") == f"a{spelled(typed)}b"


@pytest.mark.parametrize("text", [
    "plain /tmp/Thing-spec", f"caf{E_ACUTE}", "a b `c` d", "back" + BACKSLASH
    + "slash", BACKSLASH + "u202e", "a'b\"c", ""])
def test_unacted_prints_a_printable_text_as_it_is(materializer, text):
    """A path of printable characters prints as it was typed: no backticks
    around it, no escape for a backslash, a quote or a backtick, and a
    spelling that was typed stays as typed (the two read alike: #1233)."""
    assert materializer.unacted(text) == text


def test_unacted_keeps_the_characters_it_is_told_to(materializer):
    said = f"a{LINE_FEED}b{TAB}c{LINE_FEED}"
    assert materializer.unacted(said, kept=LINE_FEED) == (
        f"a{LINE_FEED}b{BACKSLASH}tc{LINE_FEED}")


@pytest.mark.parametrize("typed", EVERY)
def test_loudly_spells_the_command_the_directory_and_the_output(
        materializer, typed):
    """The three the issue names. The command and the directory name what
    the caller typed; a line feed is spelled there, and kept in the output,
    which reads a line to a line (#1195's choice, which `adopt-project.py`
    made first)."""
    said = in_words(typed)
    shown = typed if typed == LINE_FEED else said
    block = refused_push(materializer, typed).loudly("pushing the split")
    assert block == a_block(
        "pushing the split", f"git push -q /remotes/re{said}mote/Thing.git "
        "HEAD:refs/heads/main", f"/work/wo{said}rk/Thing",
        f"To /remotes/re{shown}mote/Thing.git\n"
        f" ! [remote rejected] (the hook said {shown}no)\n"
        "error: failed to push some refs")
    assert_none_raw(block, typed=typed if typed != LINE_FEED else "")


@pytest.mark.parametrize("typed", EVERY)
def test_loudly_spells_the_step_it_is_named_for(materializer, typed):
    """`family.py` names a member's path in two of its steps."""
    said = in_words(typed)
    block = refused_push(materializer, "").loudly(
        f"listing members/Th{typed}ing in the index")
    assert block.startswith(
        f"REFUSED listing members/Th{said}ing in the index. THE EXACT "
        "COMMAND WAS:\n")


def test_loudly_spells_a_tab_and_a_return_in_the_output_and_keeps_its_lines(
        materializer):
    """`_first_said` spells a tab, and #1195's `_loudly` does: the output
    keeps its line breaks and nothing else a terminal acts on."""
    failed = materializer.CommandFailed(
        ["git", "status"], None, 1,
        f"one{TAB}two{RETURN}three{LINE_FEED}  four{LINE_FEED}")
    assert failed.loudly("reading") == a_block(
        "reading", "git status", None,
        f"one{BACKSLASH}ttwo{BACKSLASH}rthree\n  four", code=1)


def test_loudly_prints_a_plain_block_as_it_always_did(materializer):
    """The control: printable text, a printable character outside ASCII, a
    path that is a `Path` and a command with no directory print as they did
    before #1213, so that no row that asserts such a block moves."""
    failed = materializer.CommandFailed(
        ["git", "-C", f"/srv/caf{E_ACUTE}", "status", BACKSLASH + "x"],
        Path("/srv") / f"caf{E_ACUTE}", 128,
        f"fatal: not a repository: /srv/caf{E_ACUTE}\n")
    assert failed.loudly("reading the holder") == a_block(
        "reading the holder",
        f"git -C /srv/caf{E_ACUTE} status {BACKSLASH}x",
        f"/srv/caf{E_ACUTE}", f"fatal: not a repository: /srv/caf{E_ACUTE}")
    bare = materializer.CommandFailed(["gh", "x"], None, 4, "")
    assert bare.loudly("asking") == (
        "REFUSED asking. THE EXACT COMMAND WAS:\n    gh x\n    exit 4\n"
        "--- output ---\n\n--- end output ---")


# --- group 3: each call that prints `loudly`'s block -------------------------

@pytest.mark.parametrize("typed", UNSAFE)
def test_scaffold_says_a_refused_command_it_never_caught_spelled(
        scaffold, monkeypatch, capsys, typed):
    """`scaffold-project.py` `main`'s catch-all (about :486)."""
    def refused(_args):
        raise refused_push(scaffold, typed)

    monkeypatch.setattr(scaffold, "_scaffold", refused)
    code = scaffold.main(["--org", ORG, "--project", PROJECT,
                          "--elected-by", "Test Human",
                          "--elected-on", "2026-09-02"])
    out, err = capsys.readouterr()
    assert code == 2, err
    assert err == the_block_of_it("a git or gh command failed", typed) + "\n"
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_scaffold_says_a_refused_push_spelled(scaffold, capsys, typed):
    """`scaffold-project.py` `_refused_push`'s (about :2481), which says the
    block and then the hint."""
    scaffold._refused_push(refused_push(scaffold, typed),
                           "pushing the spec leg", "o/r", "main", False, True)
    out, err = capsys.readouterr()
    assert err.startswith(the_block_of_it("pushing the spec leg", typed)
                          + "\n\n"), err
    assert out == ""
    assert_none_raw(out, err, typed=typed)


class Ledger:
    """What `update-shape.py` `_rolled_back` asks of its `Rollback`: what it
    undid, if it undid anything, and the step it was in."""

    def __init__(self, undone: str | None, step: str) -> None:
        self.undone = undone
        self.step = step

    def undo(self) -> str | None:
        return self.undone


@pytest.mark.parametrize("typed", UNSAFE)
def test_update_shape_says_a_commit_that_failed_before_any_write_spelled(
        updater, capsys, typed):
    """`update-shape.py` `_rolled_back`, nothing to put back (about :5419)."""
    code = updater._rolled_back(refused_push(updater, typed),
                                Ledger(None, "staging"))
    out, err = capsys.readouterr()
    assert code == 2
    assert err == the_block_of_it("committing the re-synced shape",
                                  typed) + "\n"
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_update_shape_says_a_commit_that_failed_after_writes_spelled(
        updater, capsys, typed):
    """`_rolled_back`, with what it undid below the block (about :5421). The
    step is the ledger's, and it is spelled as the rest is."""
    said = in_words(typed)
    code = updater._rolled_back(
        refused_push(updater, typed),
        Ledger("put back: a, b", f"creating the branch x{typed}y"))
    out, err = capsys.readouterr()
    assert code == 2
    assert err == the_block_of_it(f"creating the branch x{said}y",
                                  typed) + "\nput back: a, b\n"
    assert_none_raw(out, err, typed=typed)


@pytest.fixture
def a_root(tmp_path):
    """A repository with one commit, for the step that asks git where HEAD
    is."""
    root = tmp_path / "root"
    git("init", "-q", "-b", "main", str(root), cwd=tmp_path)
    (root / "f").write_text("x\n", encoding="utf-8")
    git("add", "f", cwd=root)
    git("commit", "-qm", "m", cwd=root)
    return root


@pytest.mark.parametrize("typed", UNSAFE)
def test_update_shape_says_a_push_that_failed_after_the_commit_spelled(
        updater, capsys, a_root, typed):
    """`landing_failed`'s (about :5501), which says the block, what stands
    and the NEXT line."""
    args = Namespace(branch="feature", pr=False, push=True)
    updater.landing_failed(a_root, args, refused_push(updater, typed),
                           "pushing the branch", ["gh", "pr", "create"])
    out, err = capsys.readouterr()
    assert err.startswith(the_block_of_it("pushing the branch", typed)
                          + "\nfeature carries the re-pin at "), err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_update_shape_says_a_refused_command_it_never_caught_spelled(
        updater, monkeypatch, capsys, typed):
    """`update-shape.py` `main`'s catch-all (about :6334)."""
    def refused(_args):
        raise refused_push(updater, typed)

    monkeypatch.setattr(updater, "cmd_apply", refused)
    monkeypatch.setattr(updater, "build_parser", lambda: types.SimpleNamespace(
        parse_args=lambda _argv: Namespace(
            command="apply", branch=None, push=False, pr=False, trailer=[])))
    assert updater.main(["apply"]) == 2
    out, err = capsys.readouterr()
    assert err == the_block_of_it("updating the shape", typed) + "\n"
    assert_none_raw(out, err, typed=typed)


@pytest.fixture
def a_holder(tmp_path):
    """A family holder on its own work branch, as `init --no-push` makes it
    and a person switches to a branch for `add`."""
    done = run_tool(REPO / "scripts" / "family.py", "init", "--org", ORG,
                    "--family", FAMILY, "--created-by", "Test Human",
                    "--created-on", "2026-09-04", "--local-remote-dir",
                    str(tmp_path / "remotes"), "--work-dir",
                    str(tmp_path / "fam"), "--no-push")
    assert done[0] == 0, done
    root = tmp_path / "fam" / FAMILY
    git("switch", "-q", "-c", "family/members", cwd=root)
    return root


def an_add(holder: Path, tmp_path: Path) -> Namespace:
    return Namespace(family_root=holder, member=f"{ORG}/{PROJECT}", at=None,
                     dry_run=False, local_remote_dir=tmp_path / "remotes",
                     trailer=[])


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_member_it_could_not_read_spelled(
        familiar, monkeypatch, capsys, a_holder, tmp_path, typed):
    """`family.py add`'s read of the member (about :7608), then the hint."""
    def unreadable(*_args):
        raise refused_push(familiar, typed)

    monkeypatch.setattr(familiar, "_probe_member", unreadable)
    assert familiar.cmd_add(an_add(a_holder, tmp_path)) == 2
    out, err = capsys.readouterr()
    assert err == (the_block_of_it(f"reading {ORG}/{PROJECT}", typed) + "\n"
                   + familiar.UNREADABLE_HINT + "\n"), err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_mount_that_failed_spelled(
        familiar, monkeypatch, capsys, a_holder, tmp_path, typed):
    """`family.py add`'s mount (about :7631), where the rollback's step names
    it and what the rollback put back follows the block."""
    def refused(*_args, **_kwargs):
        raise refused_push(familiar, typed)

    monkeypatch.setattr(familiar, "_probe_member",
                        lambda *_args: ("a" * 40, None))
    monkeypatch.setattr(familiar, "_mount_and_pin", refused)
    step = familiar.MountRollback(a_holder, f"members/{PROJECT}").step
    assert familiar.cmd_add(an_add(a_holder, tmp_path)) == 2
    out, err = capsys.readouterr()
    assert err.startswith(the_block_of_it(step, typed) + "\n"), err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_dry_run_that_could_not_read_the_member_spelled(
        familiar, capsys, tmp_path, typed):
    """`family.py add --dry-run`'s read (about :7484): the clone git is
    asked for is the member's url, and git writes the path it was given
    back, so the path is in the command and in git's own line."""
    skip_where_the_environment_cannot_carry(typed)
    said = in_words(typed)
    url = f"{tmp_path}/no{typed}where"
    code = familiar._add_dry_run(None, f"{ORG}/{PROJECT}", PROJECT,
                                 f"members/{PROJECT}", url, [], "a" * 40,
                                 None, [], "")
    out, err = capsys.readouterr()
    assert code == 2, err
    lines = err.split("\n")
    assert lines[0] == (f"REFUSED reading {ORG}/{PROJECT}. THE EXACT COMMAND "
                        "WAS:"), err
    assert lines[1].startswith(
        f"    git clone -q --bare -- {tmp_path}/no{said}where "), err
    assert lines[2:4] == ["    exit 128", "--- output ---"], err
    assert lines[4].startswith("fatal: repository '"), err
    assert "does not exist" in lines[4], err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_bump_that_cannot_resolve_the_commit_spelled(
        familiar, capsys, tmp_path, typed):
    """`family.py bump --dry-run`'s read of the member (about :9326), where
    the path is in the step, and the directory it ran in."""
    skip_where_the_environment_cannot_carry(typed)
    said = in_words(typed)
    member = tmp_path / f"me{typed}mber"
    member.mkdir()
    code = familiar._bump_dry_run(
        types.SimpleNamespace(root=tmp_path),
        {"project": PROJECT, "repository": f"{ORG}/{PROJECT}"},
        f"me{typed}mber", "b" * 40, [], False, "")
    out, err = capsys.readouterr()
    assert code == 2, err
    lines = err.split("\n")
    assert lines[0] == (f"REFUSED resolving {'b' * 12} in me{said}mber, "
                        "where a real bump checks it out. THE EXACT COMMAND "
                        "WAS:"), err
    assert lines[1:4] == [f"    git rev-parse --verify {'b' * 40}^{{commit}}",
                          f"    (in {tmp_path}/me{said}mber)",
                          "    exit 128"], err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_write_that_failed_spelled(familiar, capsys, typed):
    """`family.py`'s `_put_back_on_failure` (about :9490), for `bump` and
    `remove`: the block, then what the rollback put back."""
    said = in_words(typed)

    def write():
        raise refused_push(familiar, typed)

    rollback = types.SimpleNamespace(undo=lambda: "Put back.\n",
                                     step=f"staging the gitlink {typed}")
    assert familiar._put_back_on_failure(rollback, write) == 2
    out, err = capsys.readouterr()
    assert err == (the_block_of_it(f"staging the gitlink {said}", typed)
                   + "\nPut back.\n"), err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_remove_that_cannot_list_the_index_spelled(
        familiar, capsys, a_root, typed):
    """`family.py remove --dry-run`'s read of the index (about :10389): the
    path is in the step, in the command, and in git's own line."""
    skip_where_the_environment_cannot_carry(typed)
    said = in_words(typed)
    path = f"members/Th{typed}ing"
    code = familiar._remove_dry_run(
        types.SimpleNamespace(root=a_root, members=[{"project": "Thing"}],
                              rewritten=lambda _rows: None),
        {"project": "Thing"}, path, "", True)
    out, err = capsys.readouterr()
    assert code == 2, err
    lines = err.split("\n")
    assert lines[0] == (f"REFUSED listing members/Th{said}ing in the index, "
                        "where a real remove unmounts it. THE EXACT COMMAND "
                        "WAS:"), err
    assert lines[1:4] == [
        f"    git --literal-pathspecs ls-files -s -z --error-unmatch -- "
        f"members/Th{said}ing", f"    (in {a_root})", "    exit 1"], err
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_says_a_refused_command_it_never_caught_spelled(
        familiar, monkeypatch, capsys, typed):
    """`family.py` `main`'s catch-all (about :10781)."""
    def refused(_args):
        raise refused_push(familiar, typed)

    monkeypatch.setattr(
        familiar, "build_parser", lambda: types.SimpleNamespace(
            parse_args=lambda _argv: Namespace(func=refused)))
    assert familiar.main(["add"]) == 2
    out, err = capsys.readouterr()
    assert err == the_block_of_it("a git or gh command failed", typed) + "\n"
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_bump_leg_says_a_rollback_step_that_failed_spelled(
        bumper, capsys, typed):
    """`scripts/bump-leg.py`'s `_put_back` (about :2104)."""
    def undo():
        raise refused_push(bumper, typed)

    bumper._put_back("the new pin", undo)
    out, err = capsys.readouterr()
    assert err == the_block_of_it("rolling the bump back", typed) + "\n"
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_bump_leg_says_a_refused_command_it_never_caught_spelled(
        bumper, monkeypatch, capsys, typed):
    """`scripts/bump-leg.py` `main`'s catch-all (about :2609)."""
    def refused(_args):
        raise refused_push(bumper, typed)

    monkeypatch.setattr(bumper, "cmd_bump", refused)
    monkeypatch.setattr(bumper, "build_parser", lambda: types.SimpleNamespace(
        parse_args=lambda _argv: Namespace()))
    assert bumper.main([]) == 2
    out, err = capsys.readouterr()
    assert err == the_block_of_it("advancing a leg", typed) + "\n"
    assert_none_raw(out, err, typed=typed)


# --- group 3, run as a person runs it ----------------------------------------

def run_tool(script: Path, *args: str, env: dict | None = None,
             cwd: Path | None = None) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run of `script`, in a child, as text a
    byte that is not UTF-8 survives in (`surrogateescape`)."""
    asked = env or {}
    environment = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": ENCODING,
         **asked}, asked)
    for key, value in (("GIT_AUTHOR_NAME", IDENTITY_NAME),
                       ("GIT_AUTHOR_EMAIL", IDENTITY_EMAIL),
                       ("GIT_COMMITTER_NAME", IDENTITY_NAME),
                       ("GIT_COMMITTER_EMAIL", IDENTITY_EMAIL)):
        environment.setdefault(key, value)
    done = subprocess.run(
        [sys.executable, str(script), *args], capture_output=True,
        env=environment, stdin=subprocess.DEVNULL, check=False,
        cwd=str(cwd) if cwd else None)
    return (done.returncode,
            done.stdout.decode("utf-8", "surrogateescape"),
            done.stderr.decode("utf-8", "surrogateescape"))


HOOK_SAYS = "this remote takes no push"


def a_config_whose_hook_refuses_every_push(base: Path, says: str) -> Path:
    """A global git config holding the session's and a `core.hooksPath`
    whose `pre-receive` hook says `says` and refuses every push. Given as
    `GIT_CONFIG_GLOBAL`, it reaches the `receive-pack` a push to a local
    path starts, so the first push of the run is refused.

    It also sets git's `sideband.allowControlCharacters`. A git that masks
    the control characters a remote sends (its default is `color`, which lets
    only ANSI colour sequences through; the runner's 2.56.0 hands the tool an
    ESC as `^[`) would change the hook's words before the tool read them, and
    a row would judge git's masking and not the tool's spelling. `true` hands
    them over as the hook wrote them, on every git; an older git ignores the
    key."""
    hooks = base / "hooks"
    hooks.mkdir()
    hook = hooks / "pre-receive"
    hook.write_bytes(("#!/bin/sh\nprintf '%s" + BACKSLASH + "n' '" + says
                      + "' >&2\nexit 1\n").encode("utf-8"))
    hook.chmod(0o755)
    config = base / "gitconfig"
    config.write_text(
        f'[include]\n\tpath = "{os.environ["GIT_CONFIG_GLOBAL"]}"\n'
        f'[core]\n\thooksPath = "{hooks}"\n'
        '[sideband]\n\tallowControlCharacters = true\n', encoding="utf-8")
    return config


def assert_a_push_refused(err: str, step: str, where: str, said: str) -> None:
    """The block a refused push prints, as `err` holds it: the command, the
    directory it ran in, and the hook's own words after git's `remote:`."""
    lines = err.split("\n")
    start = lines.index(f"REFUSED {step}. THE EXACT COMMAND WAS:")
    assert lines[start + 1:start + 5] == [
        "    git push -q -u origin HEAD:refs/heads/main", f"    (in {where})",
        "    exit 1", "--- output ---"], err
    told = lines[start + 5:lines.index("--- end output ---", start)]
    assert f"remote: {said}" in [line.rstrip() for line in told], err


@pytest.mark.parametrize("typed", UNSAFE)
def test_scaffold_names_a_refused_push_spelled(tmp_path, typed):
    """A real `scaffold-project.py --local-remote-dir`, a hook that refuses
    every push and says `typed`, and a `--work-dir` that holds it: the push
    of the spec leg is refused, and the directory it ran in and git's
    `remote:` line each name it. (`--local-remote-dir` itself is refused
    for it before anything is made, `scaffold-unwritable-value`.)"""
    skip_where_the_environment_cannot_carry(typed)
    said = in_words(typed)
    config = a_config_whose_hook_refuses_every_push(
        tmp_path, f"{HOOK_SAYS} {typed}x")
    code, out, err = run_tool(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(tmp_path / "remote"),
        "--work-dir", str(tmp_path / f"wo{typed}rk"),
        env={"GIT_CONFIG_GLOBAL": str(config)})
    assert code == 2, out + err
    assert_a_push_refused(
        err, "pushing the spec leg",
        f"{os.path.realpath(tmp_path)}/wo{said}rk/{PROJECT}-spec",
        f"{HOOK_SAYS} {said}x")
    assert_none_raw(out, err, typed=typed)


@pytest.mark.parametrize("typed", UNSAFE)
def test_family_init_names_a_refused_push_spelled(tmp_path, typed):
    """The same for `family.py init`'s push of the holder (about :3420)."""
    skip_where_the_environment_cannot_carry(typed)
    said = in_words(typed)
    config = a_config_whose_hook_refuses_every_push(
        tmp_path, f"{HOOK_SAYS} {typed}x")
    code, out, err = run_tool(
        REPO / "scripts" / "family.py", "init", "--org", ORG,
        "--family", FAMILY, "--created-by", "Test Human",
        "--created-on", "2026-09-04",
        "--local-remote-dir", str(tmp_path / "remote"),
        "--work-dir", str(tmp_path / f"wo{typed}rk"),
        env={"GIT_CONFIG_GLOBAL": str(config)})
    assert code == 2, out + err
    assert_a_push_refused(
        err, "pushing the family holder",
        f"{os.path.realpath(tmp_path)}/wo{said}rk/{FAMILY}",
        f"{HOOK_SAYS} {said}x")
    assert_none_raw(out, err, typed=typed)


# --- group 1: `_init_refused` ------------------------------------------------

@pytest.mark.parametrize("typed", EVERY)
def test_init_refused_names_the_command_spelled(adopter, typed):
    """`git init -q <probe>` names a directory made under the `--work-dir`.
    The output beside it was `_spelled` and the command was not."""
    said = in_words(typed)
    failed = adopter.CommandFailed(
        ["git", "init", "-q", f"/work/wo{typed}rk/symlinks-probe-x"], None,
        128, "fatal: unknown hash algorithm 'bogus'")
    told = adopter._init_refused(failed)
    assert told == (f"`git init -q /work/wo{said}rk/symlinks-probe-x` "
                    "exited 128: `fatal: unknown hash algorithm 'bogus'`")
    assert_none_raw(told, typed=typed if typed != LINE_FEED else "")
    assert LINE_FEED not in told


def test_init_refused_leaves_a_refusal_as_it_was(adopter):
    refusal = adopter.Refusal("git-failed", f"detail {BIDI} kept")
    assert adopter._init_refused(refusal) == f"detail {BIDI} kept"


@pytest.mark.usefixtures("links_as_links")
@pytest.mark.parametrize("typed", EVERY)
def test_check_names_the_probes_command_spelled_where_git_refuses_it(
        tmp_path, typed):
    """A real `check` whose `git init` of the symlink probe fails
    (`GIT_DEFAULT_HASH=bogus`), in a `--work-dir` that holds the character:
    the NOTE names the work directory `_spelled` and, now, the command's
    directory as it does, on one line."""
    skip_where_the_environment_cannot_carry(typed)
    if typed == BYTE:
        skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    said = in_words(typed)
    work = tmp_path / f"wo{typed}rk"
    work.mkdir()
    plan = linked_github_plan(tmp_path)
    code, out, err = run_tool(
        ADOPT, "check", "--plan", str(plan), "--work-dir", str(work),
        env={"GIT_DEFAULT_HASH": "bogus"})
    assert code == 1, out + err
    where = f"{os.path.realpath(tmp_path)}/wo{said}rk"
    assert re.search(
        re.escape(f"in `{where}`, the work directory: `git init -q {where}/"
                  "symlinks-probe-") + r"[^/` ]+"
        + re.escape("` exited 128: `fatal: unknown hash algorithm 'bogus'`"),
        out), out
    assert_none_raw(out, err, typed=typed if typed != LINE_FEED else "")


@pytest.mark.parametrize("typed", EVERY)
def test_the_refs_probe_names_its_command_spelled_too(
        adopter, monkeypatch, tmp_path, typed):
    """`_clone_ref_store`'s `git init` of a probe (#904), which `check` asks
    the first time a walk is led into the clone's own `.git`: the other
    caller of `_init_refused`."""
    skip_where_the_environment_cannot_carry(typed)
    if typed == BYTE:
        skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    said = in_words(typed)
    work = tmp_path / f"wo{typed}rk"
    work.mkdir()
    monkeypatch.setenv("GIT_DEFAULT_HASH", "bogus")
    probe = adopter._SymlinkProbe(work)
    probe.ref_store()
    assert re.fullmatch(
        re.escape(f"`git init -q {work.parent}/wo{said}rk/refs-probe-")
        + r"[^/` ]+" + re.escape(
            "` exited 128: `fatal: unknown hash algorithm 'bogus'`"),
        probe.refs_unasked), probe.refs_unasked
    assert_none_raw(probe.refs_unasked,
                    typed=typed if typed != LINE_FEED else "")


# --- group 2: git's and gh's output in two refusals --------------------------

def a_gh_that_refuses_the_clone(base: Path, said: bytes) -> dict:
    """The environment of a `gh` that fails every call and prints `said`
    first, which reaches `plan`'s `gh repo clone`."""
    stub = base / "ghbin"
    stub.mkdir()
    gh = stub / "gh"
    gh.write_bytes(b"#!/bin/sh\ncat >&2 <<'GH_SAID'\n" + said
                   + b"\nGH_SAID\nexit 1\n")
    gh.chmod(0o755)
    (base / "gh-config").mkdir()
    return {"PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
            "GH_TOKEN": "bogus-1213", "GH_CONFIG_DIR": str(base / "gh-config")}


def an_unclonable_plan(tmp_path: Path, said: bytes):
    return run_tool(
        ADOPT, "plan", "--source", f"{ORG}/{PROJECT}", "--project", PROJECT,
        "--org", ORG, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--out", str(tmp_path / "plan.yaml"),
        "--work-dir", str(tmp_path / "work"),
        env=a_gh_that_refuses_the_clone(tmp_path, said))


@pytest.mark.parametrize("typed", UNSAFE)
def test_source_unclonable_names_what_gh_said_spelled(tmp_path, typed):
    """`plan --source org/repo` with a `gh` that refuses the clone and says
    `typed`: the refusal quotes gh's words, up to 400 characters of them,
    and printed them as they were. The line break between its lines is
    kept."""
    said = in_words(typed)
    code, out, err = an_unclonable_plan(
        tmp_path, f"stub gh: could not {typed}clone{LINE_FEED}second "
        f"line{typed}".encode("utf-8"))
    assert code == 2, out + err
    assert err.startswith(
        f"REFUSED source-unclonable: could not clone {ORG}/{PROJECT}: stub "
        f"gh: could not {said}clone\nsecond line{said}\nRemediation: "), err
    assert_none_raw(out, err, typed=typed)


def test_source_unclonable_names_a_byte_that_is_not_utf_8_as_run_reads_it(
        tmp_path):
    """The control for byte 0xff: `run` decodes with `replace`, so gh's byte
    reaches the refusal as U+FFFD, which prints as it is, and no raw 0xff
    does (it passes before #1213 as well)."""
    code, out, err = an_unclonable_plan(tmp_path, b"stub gh: caf\xff")
    assert code == 2, out + err
    assert (f"could not clone {ORG}/{PROJECT}: stub gh: caf{REPLACEMENT}\n"
            in err)
    assert_none_raw(out, err)


@pytest.mark.parametrize("typed", [BIDI, ESCAPE])
def test_source_unclonable_cuts_gh_s_words_before_it_spells_them(
        adopter, monkeypatch, tmp_path, typed):
    """A spelling is never cut: 400 characters of gh's words are kept, and
    then each is spelled, so a character at the 400th place is written out
    whole and the words after it are gone."""
    said = in_words(typed)
    words = "a" * 399 + typed + "tail"

    def refused(command, *_args, **_kwargs):
        raise adopter.CommandFailed(command, None, 1, words)

    monkeypatch.setattr(adopter, "run", refused)
    work = tmp_path / "work"
    work.mkdir()
    with pytest.raises(adopter.Refusal) as caught:
        adopter.Source.clone(f"{ORG}/{PROJECT}", work)
    assert caught.value.code == "source-unclonable"
    assert caught.value.detail == (
        f"could not clone {ORG}/{PROJECT}: " + "a" * 399 + said)


def an_unreadable_remote(adopter, monkeypatch, raised: BaseException):
    """`adopt-remote-unreadable`'s refusal for the `git ls-remote` that
    `raised` ended."""
    def refused(*_args, **_kwargs):
        raise raised

    monkeypatch.setattr(adopter, "run", refused)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_a_tracking_branch_the_remote_lacks(
            {"assembly": "https://github.com/o/Thing.git"}, "main", False)
    assert caught.value.code == "adopt-remote-unreadable"
    return caught.value.detail


@pytest.mark.parametrize("typed", UNSAFE)
def test_a_remote_git_could_not_read_is_refused_in_git_s_words_spelled(
        adopter, monkeypatch, typed):
    """`git ls-remote`'s output, on one line, and spelled: it names the url
    it was given, and whatever the remote said."""
    said = in_words(typed)
    detail = an_unreadable_remote(adopter, monkeypatch, adopter.CommandFailed(
        ["git", "ls-remote", "u", "refs/heads/main"], None, 128,
        f"fatal: unable {typed}to access{LINE_FEED}  {typed}evil{LINE_FEED}"))
    assert detail.endswith(
        f"the plan's `tracking_branch`: exit 128: fatal: unable {said}to "
        f"access {said}evil"), detail
    assert_none_raw(detail, typed=typed)


@pytest.mark.parametrize("typed", [BIDI, ESCAPE])
def test_a_remote_git_could_not_run_for_is_refused_spelled(
        adopter, monkeypatch, typed):
    """The `OSError` branch of the same refusal: its text, spelled."""
    said = in_words(typed)
    detail = an_unreadable_remote(
        adopter, monkeypatch, OSError(2, f"no such{typed} file", "git"))
    assert detail.endswith(
        f"the plan's `tracking_branch`: [Errno 2] no such{said} file: 'git'")
    assert_none_raw(detail, typed=typed)


def test_a_remote_git_names_back_in_its_own_line_is_refused_spelled(
        adopter, tmp_path):
    """The real `git ls-remote` of a path that holds U+202E: git writes the
    path back in its own `fatal:` line, as it is, and the url above it is
    `_spelled`. (An ESC it writes as `?` itself, so the rows above, which
    put one in what git said, are its rows.)"""
    said = in_words(BIDI)
    url = f"{tmp_path}/no{BIDI}where"
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_a_tracking_branch_the_remote_lacks(
            {"assembly": url}, "main", False)
    assert caught.value.code == "adopt-remote-unreadable"
    detail = caught.value.detail
    assert f"could not read `{tmp_path}/no{said}where`" in detail, detail
    assert f"exit 128: fatal: '{tmp_path}/no{said}where' does not appear" \
        in detail, detail
    assert_none_raw(detail, typed=BIDI)


@pytest.mark.parametrize("typed", [BIDI, ESCAPE])
def test_a_gh_that_could_not_be_run_is_named_spelled(
        adopter, monkeypatch, typed):
    """`_in_the_way_on_github`, which spells gh's first line and printed an
    `OSError`'s text as it was."""
    said = in_words(typed)

    def not_found(*_args, **_kwargs):
        raise OSError(2, f"no such{typed} file", "gh")

    monkeypatch.setattr(adopter, "run", not_found)
    code, detail, _fix, _more = adopter._in_the_way_on_github(
        "spec", "o/Thing-spec")
    assert code == "adopt-remote-unreadable"
    assert detail.endswith(
        f"`gh` could not be run: [Errno 2] no such{said} file: 'gh'"), detail
    assert_none_raw(detail, typed=typed)
