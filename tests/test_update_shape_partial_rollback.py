# SPDX-License-Identifier: Apache-2.0
"""A rollback that cannot put a byte back names it, and does the rest (#428).

When `apply` fails after its first write, `_rolled_back` asks
`Rollback.undo` to put the tree back. The git half of `undo` never raised
over the refusal that started it; the byte half restored each file with a
bare `write_bytes` and took away what `--add` made with a bare `unlink` and
`rmdir`. One file that would not take its old bytes — a permission a
validator took away, a full disk, a lock — escaped `_rolled_back` and
`main` as a traceback, exit 1, the refusal surviving only as the
exception's context, and the loop stopped there: the paths after it were
never tried, so a pin put back sat under a manifest left re-pinned.

IN PROCESS, as the issue asks. `Path.write_bytes`, `Path.unlink` or
`Path.rmdir` is made to raise `PermissionError` for one path, and ONLY while
`undo` runs: nothing is patched at the write. A file is `chmod`ed to make
it fail only where the permission is the point — a directory nobody may
write into, which a checkout's unlink needs — and that test is POSIX-only.
The rollback is started by the project's validators going red
(`run_validator` answers 1, and may first do what a validator could: put
a file back, move it out and link it, give it a second name), or by a git
command that fails, so the refusal under test is the real one. Each test
reads the refusal and the tree:

  * the refusal that started it is still the one reported — its code, its
    remediation, exit 2 — with `ROLLED BACK IN PART` under its detail;
  * every other path is restored or removed, the first one failing
    included, so nothing after it is skipped;
  * the path that failed is under `NOT put back`, with a line that finishes
    it by hand: `git checkout HEAD -- <path>` where that writes the file's
    bytes before this run, and otherwise `git cat-file blob <id> > <path>`
    from the object store, where those bytes were kept; or, when git will
    keep nothing either, a line that says so;
  * a removal that failed is `rm --` or `rmdir --`, the directory above a
    file that stayed listed after it;
  * a path a symlink or a second name reached between the write and the
    undo is never written or removed through, and is listed, so the block
    never says the tree is exactly as it was while one is left; a
    symlink on the way to the path, a directory moved out and linked
    back, counts as much as one at the path, and its line says the
    directory has to be this root's own again;
  * a directory a validator deleted does not take the checkout line
    away from the file in it: git makes the missing directories, and
    the line says nothing of making a file writable that is not there;
    where the bytes are not HEAD's, the `cat-file` redirect, which
    never makes a directory, is preceded by a `mkdir -p` of it.

The pastes run where the suite has a POSIX `sh`, or with no shell at all
where the line is one command. THE FIXTURE is
`tests/test_update_shape_rewrite_symlink.py`'s, with B adding two files to
the assembly root's lists, one in a directory the root does not have, and C
editing the manifest validator again. No network is used and `gh` is never
invoked.
"""

from __future__ import annotations

import errno
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git
from test_scaffold_ignored_shape_files import load
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               scaffold_upstream_and_project)
from test_update_shape_add import MATERIALIZER, commit_all, name_in_list
from test_update_shape_add_symlink import assert_untouched, snapshot

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"

AGENTS = "AGENTS-shape.md"
AGENTS_SOURCE = f"templates/assembly-root/{AGENTS}"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"
#: The files `apply` rewrites here, in the order the ledger writes them.
REWRITTEN = (CHANGED, AGENTS, PIN, MANIFEST)
#: What B adds to the assembly root's lists: a file at the top level, and
#: one in a directory the root does not have, which `--add` has to make.
ADDED = "AGENTS-rollback-test.md"
DIR = "docs"
DIR_ADDED = f"{DIR}/shape-guide.md"
BODIES = {
    ADDED: b"# The shape's notes, added after this project was cut.\n",
    DIR_ADDED: b"# A guide the standard gained, in a directory of its own.\n",
}
BRANCH = "shape/update-partial"
DENIED = os.strerror(errno.EACCES)
HEADING = "  NOT put back — finish these by hand:\n"


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it, B above them, and C above B."""
    _base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-partial-rollback")
    for source, edit in ((AGENTS_SOURCE, b"<!-- an upstream edit -->\n"),
                         (CHANGED_SOURCE, UPSTREAM_FIX_LINE.encode("utf-8"))):
        path = upstream / source
        # Bytes, so the blob is what was appended on every platform.
        path.write_bytes(path.read_bytes() + edit)
    lists = upstream / MATERIALIZER
    text = lists.read_bytes().decode("utf-8")
    for rel, body in BODIES.items():
        target = upstream / "templates" / "assembly-root" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        text = name_in_list(text, "COPIED_VERBATIM", rel)
    lists.write_bytes(text.encode("utf-8"))
    b = commit_all(upstream, "Edit two copies and add two files", [
        AGENTS_SOURCE, CHANGED_SOURCE, MATERIALIZER,
        *(f"templates/assembly-root/{rel}" for rel in BODIES)])
    path = upstream / CHANGED_SOURCE
    path.write_bytes(path.read_bytes() + b"# A second upstream fix.\n")
    c = commit_all(upstream, "Fix the manifest validator again",
                   [CHANGED_SOURCE])
    return {"upstream": upstream, "clone": clone, "a": a, "b": b, "c": c}


@pytest.fixture
def root(standard, tmp_path):
    """A private, mutable copy of the project as it was cut at A, by the
    path `prepare` resolves it to, so every path the ledger holds is one
    this test can name."""
    target = tmp_path / PROJECT
    shutil.copytree(standard["clone"], target, symlinks=True)
    return target.resolve()


@pytest.fixture
def update_shape(monkeypatch):
    """`update-shape.py` as a module, fresh for each test, since each one
    patches its ledger."""
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    return load(UPDATE, "update_shape_partial_rollback")


def validators(monkeypatch, update_shape, code: int) -> None:
    """The project's validators answer `code`, for every script: 1 starts
    the rollback with the real `update-validators-red` refusal."""
    monkeypatch.setattr(update_shape, "run_validator",
                        lambda _root, _script: code)


def refusing(real, paths: set):
    """`real`, a `Path` method, raising `PermissionError` for `paths`."""
    def method(path, *args, **kwargs):
        if path in paths:
            raise PermissionError(errno.EACCES, DENIED, str(path))
        return real(path, *args, **kwargs)
    return method


def failing_in_undo(monkeypatch, update_shape, *, write=(), unlink=(),
                    rmdir=(), git_keeps=True) -> None:
    """While `Rollback.undo` runs, and only then: `Path.write_bytes` refuses
    the paths in `write`, `Path.unlink` those in `unlink`, `Path.rmdir`
    those in `rmdir`, all relative to the ledger's root; and with
    `git_keeps` False, no git the rollback starts runs at all."""
    real_undo = update_shape.Rollback.undo

    def undo(self):
        with monkeypatch.context() as patch:
            for name, rels in (("write_bytes", write), ("unlink", unlink),
                               ("rmdir", rmdir)):
                if rels:
                    patch.setattr(Path, name, refusing(
                        getattr(Path, name), {self.root / rel
                                              for rel in rels}))
            if not git_keeps:
                patch.setattr(update_shape, "_git_quietly",
                              lambda *_args, **_kwargs: None)
            return real_undo(self)

    monkeypatch.setattr(update_shape.Rollback, "undo", undo)


def apply_args(standard, root: Path, at: str, *extra: str) -> list[str]:
    return ["apply", "--root", str(root), "--yes",
            "--upstream", str(standard["upstream"]), "--at", standard[at],
            *extra]


def refused_by(update_shape, standard, root: Path, at: str, *extra: str):
    """`cmd_apply` in process; the refusal it ends with."""
    args = update_shape.build_parser().parse_args(
        apply_args(standard, root, at, *extra))
    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.cmd_apply(args)
    return refused.value


def put_back(said: str) -> list[str]:
    """The lines under `Put back:`, stripped."""
    block = said.split("Put back:\n", 1)[1].split(HEADING, 1)[0]
    return [line.strip() for line in block.splitlines()
            if line.startswith("    ")]


def left(said: str) -> list[str]:
    """The lines under `NOT put back — finish these by hand:`, stripped."""
    assert HEADING in said, said
    return [line.strip() for line in said.split(HEADING, 1)[1].splitlines()
            if line.startswith("    ")]


def held(root: Path) -> dict:
    return {rel: (root / rel).read_bytes() for rel in REWRITTEN}


def head_line(root: Path, rel: str) -> str:
    """The line a file holding HEAD's bytes is finished with."""
    return (f"file      {rel} was not put back ({DENIED}); it held HEAD's "
            "bytes, so make it writable, then: " + shlex.join([
                "git", "-C", str(root), "--literal-pathspecs", "checkout",
                "HEAD", "--", rel]))


def assert_reported_as_red(refusal) -> None:
    """The refusal that started the rollback is the one reported."""
    assert refusal.code == "update-validators-red", refusal
    assert refusal.detail.startswith("after the rewrite, "), refusal.detail
    assert refusal.remediation.startswith(
        "Remediation: read the finding above."), refusal.remediation
    assert ("ROLLED BACK IN PART: the tree is NOT as it was. Put back:"
            in refusal.detail), refusal.detail
    assert "ROLLED BACK: every byte" not in refusal.detail


# ---------------------------------------------------------------------------
# A file that will not take its bytes back
# ---------------------------------------------------------------------------


def test_the_manifest_not_put_back_is_named_and_the_rest_are_restored(
        update_shape, root, standard, monkeypatch):
    """THE ISSUE'S RUN. The validators go red, and the manifest will not
    take its bytes back. Main died there with a traceback and exit 1,
    leaving the pin restored under a re-pinned manifest. The refusal is
    `update-validators-red` still, every other file is put back, and the
    manifest is listed with the line that puts it back — HEAD's bytes
    here, since `--branch` ran over a tree HEAD commits — which, run,
    leaves the tree exactly as it was."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])
    before, bytes_before = snapshot(root), held(root)

    refusal = refused_by(update_shape, standard, root, "b", "--branch",
                         BRANCH)
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [f"restored  {rel}"
                                        for rel in (CHANGED, AGENTS, PIN)]
    assert left(refusal.detail) == [head_line(root, MANIFEST)]
    for rel in (CHANGED, AGENTS, PIN):
        assert (root / rel).read_bytes() == bytes_before[rel], rel
    assert (root / MANIFEST).read_bytes() != bytes_before[MANIFEST], (
        "the manifest was put back after all: the patch did not hold")

    fix = shlex.split(left(refusal.detail)[0].split(", then: ", 1)[1])
    subprocess.run(fix, check=True, capture_output=True)
    assert_untouched(before, snapshot(root))


def test_the_first_path_failing_does_not_stop_the_paths_after_it(
        update_shape, root, standard, monkeypatch):
    """The FIRST file the ledger wrote will not take its bytes back. Main's
    loop stopped there, so the copy, the pin and the manifest after it kept
    the re-pin. Each of them is put back now, and only the first is left."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[CHANGED])
    bytes_before = held(root)

    refusal = refused_by(update_shape, standard, root, "b")
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [f"restored  {rel}"
                                        for rel in (AGENTS, PIN, MANIFEST)]
    assert left(refusal.detail) == [head_line(root, CHANGED)]
    for rel in (AGENTS, PIN, MANIFEST):
        assert (root / rel).read_bytes() == bytes_before[rel], rel


def test_main_exits_2_with_the_refusal_and_no_traceback(
        update_shape, root, standard, monkeypatch, capsys):
    """THE EXIT, through `main`: 2 with the refusal on stderr, where main
    raised the `PermissionError` and exited 1. `die` is pointed at the
    stderr this test reads; it bound the one it was imported under."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])
    real_die = update_shape.die
    monkeypatch.setattr(update_shape, "die",
                        lambda exc: real_die(exc, stream=sys.stderr))

    code = update_shape.main(apply_args(standard, root, "b"))
    err = capsys.readouterr().err
    assert code == 2, err
    assert err.startswith("REFUSED update-validators-red: "), err
    assert "ROLLED BACK IN PART" in err
    assert head_line(root, MANIFEST) in err
    assert "Traceback" not in err


def test_a_failed_git_command_is_still_the_one_reported(
        update_shape, root, standard, monkeypatch, capsys):
    """A `CommandFailed` start, which `_rolled_back` prints itself with the
    step the ledger was in: creating the branch fails after every byte is
    written, and the manifest will not take its bytes back. The failed
    command is the report, exit 2, with the same block under it."""
    validators(monkeypatch, update_shape, 0)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])

    def no_branch(self, branch):
        raise update_shape.CommandFailed(
            ["git", "checkout", "-q", "-b", branch], self.root, 128,
            "fatal: not a branch git will make\n")

    monkeypatch.setattr(update_shape.Rollback, "new_branch", no_branch)
    args = update_shape.build_parser().parse_args(
        apply_args(standard, root, "b", "--branch", BRANCH))

    assert update_shape.cmd_apply(args) == 2
    err = capsys.readouterr().err
    assert err.startswith(f"REFUSED creating the branch {BRANCH}. THE EXACT "
                          "COMMAND WAS:"), err
    assert "ROLLED BACK IN PART: the tree is NOT as it was." in err
    assert left(err) == [head_line(root, MANIFEST)]
    assert "Traceback" not in err


# ---------------------------------------------------------------------------
# Bytes HEAD does not commit
# ---------------------------------------------------------------------------


def uncommitted_then_red(update_shape, standard, root: Path, monkeypatch):
    """The issue's tree, measured: an `apply` without `--branch` to B, left
    uncommitted, then a second one to C that goes red and cannot put the
    copy back. The copy held B's bytes, which HEAD (at A) does not commit.
    Returns the refusal and the tree as the second run found it."""
    validators(monkeypatch, update_shape, 0)
    args = update_shape.build_parser().parse_args(
        apply_args(standard, root, "b"))
    assert update_shape.cmd_apply(args) == 0
    before, bytes_before = snapshot(root), held(root)
    head = git("show", f"HEAD:{CHANGED}", cwd=root).stdout.encode("utf-8")
    assert bytes_before[CHANGED] != head, "fixture: the copy is HEAD's"

    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[CHANGED])
    return refused_by(update_shape, standard, root, "c"), before, bytes_before


def kept_line(refusal, root: Path) -> list[str]:
    """`left`'s one line, checked, as the words of the command it ends with:
    `git -C <root> cat-file blob <id> > <path>`."""
    lines = left(refusal.detail)
    said = (f"file      {CHANGED} was not put back ({DENIED}); its bytes "
            "before this run are kept as blob ")
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(said), (
        f"the line does not begin as it should: {lines[0]!r}")
    words = shlex.split(lines[0].split(", then: ", 1)[1])
    assert words[:5] == ["git", "-C", str(root), "cat-file", "blob"], words
    assert words[6:] == [">", str(root / CHANGED)], words
    assert lines[0][len(said):].startswith(words[5][:12])
    return words


def test_bytes_head_does_not_commit_are_kept_in_the_object_store(
        update_shape, root, standard, monkeypatch):
    """`git checkout HEAD` would write A's copy over B's, which is not a
    rollback. So the bytes the copy held are written into the repository's
    objects, and the line names that blob: `git cat-file blob` hands back
    exactly those bytes. The pin and the manifest, also not HEAD's, are
    put back; C leaves `AGENTS-shape.md` as B had it, so it was never
    written."""
    refusal, _before, bytes_before = uncommitted_then_red(
        update_shape, standard, root, monkeypatch)
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [f"restored  {rel}"
                                        for rel in (PIN, MANIFEST)]
    words = kept_line(refusal, root)
    blob = subprocess.run(words[:6], capture_output=True, check=True).stdout
    assert blob == bytes_before[CHANGED]
    assert (root / CHANGED).read_bytes() != bytes_before[CHANGED]


def test_bytes_a_checkout_would_write_otherwise_are_not_sent_to_head(
        update_shape, root, standard, monkeypatch):
    """HEAD'S BLOB IS NOT THE QUESTION; WHAT A CHECKOUT WRITES IS. With
    `eol=crlf` on the manifest in `.git/info/attributes`, the manifest the
    run found is HEAD's blob byte for byte — LF, as it was checked out
    before the rule — but `git checkout HEAD -- project.yaml` would now
    write it with CRLF. So its line keeps the bytes in the object store
    instead, and they are the LF bytes the file held."""
    info = root / ".git" / "info"
    info.mkdir(exist_ok=True)
    (info / "attributes").write_bytes(b"/project.yaml text eol=crlf\n")
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])
    bytes_before = held(root)
    head = subprocess.run(["git", "cat-file", "blob", f"HEAD:{MANIFEST}"],
                          cwd=root, capture_output=True, check=True).stdout
    assert bytes_before[MANIFEST] == head, "fixture: not HEAD's blob"

    refusal = refused_by(update_shape, standard, root, "b")
    assert_reported_as_red(refusal)
    lines = left(refusal.detail)
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert "kept as blob" in lines[0], (
        f"the bytes were not kept in the object store: {lines[0]!r}")
    assert "HEAD's bytes" not in lines[0]
    words = shlex.split(lines[0].split(", then: ", 1)[1])
    assert subprocess.run(words[:6], capture_output=True,
                          check=True).stdout == bytes_before[MANIFEST]


@WINDOWS_SKIP
def test_the_object_store_line_pasted_puts_the_bytes_back(
        update_shape, root, standard, monkeypatch):
    """The line as printed, through `sh`, redirect and all: the tree is
    then exactly as the second run found it."""
    refusal, before, _bytes = uncommitted_then_red(update_shape, standard,
                                                   root, monkeypatch)
    kept_line(refusal, root)
    subprocess.run(["sh", "-c", left(refusal.detail)[0].split(", then: ",
                                                              1)[1]],
                   check=True)
    assert_untouched(before, snapshot(root))


def test_bytes_nowhere_are_said_to_be_nowhere_and_nothing_is_put_back(
        update_shape, root, standard, monkeypatch):
    """No file takes its bytes back and git will keep none of them: the
    block says `nothing` was put back, rather than run its heading into the
    list, and each file's line says its bytes are nowhere this run can
    point at, instead of naming a command that cannot work."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=REWRITTEN,
                    git_keeps=False)

    refusal = refused_by(update_shape, standard, root, "b")
    assert_reported_as_red(refusal)
    assert "Put back:\n    nothing\n" + HEADING in refusal.detail
    assert left(refusal.detail) == [
        f"file      {rel} was not put back ({DENIED}); and git would not "
        "keep its bytes before this run either, so they are nowhere this "
        f"run can point at: only a copy of {rel} made before it can put it "
        "back" for rel in REWRITTEN]


# ---------------------------------------------------------------------------
# What `--add` made, and will not go
# ---------------------------------------------------------------------------


ADDING = ("--add", ADDED, "--add", DIR_ADDED)


def test_an_add_file_that_will_not_go_is_named_with_the_directory_above_it(
        update_shape, root, standard, monkeypatch):
    """`docs/shape-guide.md` will not be unlinked. Main raised there; the
    directory made for it then read as holding "something this run did not
    write". It is the file's own `rm` line now, then the directory's
    `rmdir` once that is gone, and the other addition and every copy are
    taken away or restored around them."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, unlink=[DIR_ADDED])

    refusal = refused_by(update_shape, standard, root, "b", *ADDING)
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [
        *(f"restored  {rel}" for rel in REWRITTEN),
        f"removed   {ADDED} (written by --add)"]
    assert left(refusal.detail) == [
        f"file      {DIR_ADDED}, written by --add, was not removed "
        f"({DENIED}): " + shlex.join(["rm", "--", str(root / DIR_ADDED)]),
        f"directory {DIR}/, made to hold an --add file, still holds the one "
        "above; once that is gone: "
        + shlex.join(["rmdir", "--", str(root / DIR)])]
    assert not (root / ADDED).exists()
    assert (root / DIR_ADDED).read_bytes() == BODIES[DIR_ADDED]


def test_a_directory_that_will_not_go_is_named_with_its_rmdir_line(
        update_shape, root, standard, monkeypatch):
    """The file goes, and the directory made for it will not."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, rmdir=[DIR])

    refusal = refused_by(update_shape, standard, root, "b", *ADDING)
    assert_reported_as_red(refusal)
    assert f"removed   {DIR_ADDED} (written by --add)" in put_back(
        refusal.detail)
    assert left(refusal.detail) == [
        f"directory {DIR}/, made to hold an --add file, was not removed "
        f"({DENIED}): " + shlex.join(["rmdir", "--", str(root / DIR)])]
    assert (root / DIR).is_dir(), (
        f"{DIR}/ is gone, and the patched rmdir should have kept it")
    assert not any((root / DIR).iterdir()), (
        f"{DIR}/ still holds {sorted((root / DIR).iterdir())}, and the "
        "undo should have removed the file it made there")


@WINDOWS_SKIP
def test_the_removal_lines_pasted_leave_the_tree_as_it_was(
        update_shape, root, standard, monkeypatch):
    """The two lines, in the order printed, through `sh`: the file, then the
    directory, and the tree is exactly as it was before the run."""
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, unlink=[DIR_ADDED])
    before = snapshot(root)

    refusal = refused_by(update_shape, standard, root, "b", *ADDING)
    for line in left(refusal.detail):
        subprocess.run(["sh", "-c", line.rsplit(": ", 1)[1]], check=True)
    assert_untouched(before, snapshot(root))


# ---------------------------------------------------------------------------
# Which line, and when (review of PR #560)
# ---------------------------------------------------------------------------


def test_an_index_holding_another_blob_is_never_sent_to_head(
        update_shape, root, standard, monkeypatch):
    """`git checkout HEAD -- <path>` writes the index too. With another
    blob staged at the manifest and the working tree at HEAD's bytes, that
    checkout would throw the staged entry away, so the line keeps the bytes
    in the object store instead, and the index is left as it was."""
    staged = (root / MANIFEST).read_bytes() + b"# somebody's staged draft\n"
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"], cwd=root,
                          input=staged, capture_output=True,
                          check=True).stdout.decode("ascii").strip()
    git("update-index", "--cacheinfo", f"100644,{blob},{MANIFEST}", cwd=root)
    index = git("ls-files", "--stage", "--", MANIFEST, cwd=root).stdout
    validators(monkeypatch, update_shape, 1)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])
    bytes_before = held(root)

    refusal = refused_by(update_shape, standard, root, "b")
    assert_reported_as_red(refusal)
    lines = left(refusal.detail)
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert "kept as blob" in lines[0], (
        f"the bytes were not kept in the object store: {lines[0]!r}")
    assert "checkout" not in lines[0], (
        f"a checkout was offered over a staged blob: {lines[0]!r}")
    assert "HEAD's bytes" not in lines[0], (
        f"the staged blob was called HEAD's: {lines[0]!r}")
    words = shlex.split(lines[0].split(", then: ", 1)[1])
    assert subprocess.run(words[:6], capture_output=True,
                          check=True).stdout == bytes_before[MANIFEST]
    assert git("ls-files", "--stage", "--", MANIFEST,
               cwd=root).stdout == index


@WINDOWS_SKIP
def test_a_directory_nobody_may_write_into_gets_the_line_that_writes_in_place(
        update_shape, root, standard, monkeypatch):
    """A checkout unlinks the file and creates it again, which a directory
    nobody may write into refuses however writable the file is made. With
    `contracts/` at 0555 and the pin at 0444 when the validators go red,
    the pin's line is the `cat-file` redirect, which writes in place: made
    writable, as the line says, the pin takes its bytes back with the
    directory still shut."""
    pin, contracts = root / PIN, root / "contracts"
    bytes_before = held(root)

    def red_and_shut(_root, _script):
        pin.chmod(0o444)
        contracts.chmod(0o555)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", red_and_shut)
    try:
        refusal = refused_by(update_shape, standard, root, "b")
        if f"restored  {PIN}" in refusal.detail:  # pragma: no cover
            pytest.skip("this user is not stopped by permission bits")
        assert_reported_as_red(refusal)
        assert put_back(refusal.detail) == [
            f"restored  {rel}" for rel in (CHANGED, AGENTS, MANIFEST)]
        lines = left(refusal.detail)
        said = (f"file      {PIN} was not put back ({DENIED}); its bytes "
                "before this run are kept as blob ")
        assert len(lines) == 1, (
            f"one line was expected, and {len(lines)} were printed: {lines}")
        assert lines[0].startswith(said), (
            f"the line does not begin as it should: {lines[0]!r}")
        assert "checkout" not in lines[0]
        pin.chmod(0o644)
        subprocess.run(["sh", "-c", lines[0].split(", then: ", 1)[1]],
                       check=True)
        assert pin.read_bytes() == bytes_before[PIN]
    finally:
        contracts.chmod(0o755)
        pin.chmod(0o644)


@WINDOWS_SKIP
def test_a_directory_a_validator_deleted_still_gets_the_checkout_line(
        update_shape, root, standard, monkeypatch):
    """ROUND 1'S REGRESSION (review of PR #560, round 2). Round 1 asked
    `os.access` of the pin's own parent, and a validator that deletes
    `contracts/` leaves none: the answer was no, so the pin's line fell to a
    `cat-file` redirect into a directory that does not exist ("Directory
    nonexistent"), and said "make it writable" of a file that is not there.
    git makes the missing directories, so the question is asked of the
    nearest one that exists, and the line is the checkout again: which,
    pasted, puts the pin's bytes back."""
    contracts, pin = root / "contracts", root / PIN
    bytes_before = held(root)

    def red_and_deleted(_root, _script):
        if contracts.exists():
            shutil.rmtree(contracts)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", red_and_deleted)

    refusal = refused_by(update_shape, standard, root, "b", "--branch",
                         BRANCH)
    assert not contracts.exists(), "the validator did not delete contracts/"
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [
        f"restored  {rel}" for rel in (CHANGED, AGENTS, MANIFEST)]
    lines = left(refusal.detail)
    said = (f"file      {PIN} was not put back "
            f"({os.strerror(errno.ENOENT)}); it held HEAD's bytes, then: ")
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(said), (
        f"the line does not begin as it should: {lines[0]!r}")
    assert "make it writable" not in lines[0], (
        f"a file that is not there was called not writable: {lines[0]!r}")
    command = lines[0][len(said):]
    assert shlex.split(command) == [
        "git", "-C", str(root), "--literal-pathspecs", "checkout", "HEAD",
        "--", PIN], command

    subprocess.run(["sh", "-c", command], check=True, capture_output=True)
    assert pin.read_bytes() == bytes_before[PIN]


@WINDOWS_SKIP
def test_the_object_store_line_makes_the_directory_a_validator_deleted(
        update_shape, root, standard, monkeypatch):
    """THE SAME DELETED DIRECTORY, WHERE HEAD IS NOT THE ANSWER (round 2,
    out of the first report). An `apply` without `--branch` left
    uncommitted, then a second one whose validator deletes `contracts/`:
    the pin held B's bytes, which HEAD does not commit, so its line is the
    `cat-file` redirect, and a redirect creates the file and never the
    directory above it ("Directory nonexistent"). The line makes the
    directory first, in the same command, so that pasted through `sh` the
    pin's bytes come back, exit 0."""
    contracts, pin = root / "contracts", root / PIN
    validators(monkeypatch, update_shape, 0)
    args = update_shape.build_parser().parse_args(
        apply_args(standard, root, "b"))
    assert update_shape.cmd_apply(args) == 0
    bytes_before = held(root)

    def red_and_deleted(_root, _script):
        if contracts.exists():
            shutil.rmtree(contracts)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", red_and_deleted)

    refusal = refused_by(update_shape, standard, root, "c")
    assert not contracts.exists(), "the validator did not delete contracts/"
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [
        f"restored  {rel}" for rel in (CHANGED, MANIFEST)]
    lines = left(refusal.detail)
    said = (f"file      {PIN} was not put back "
            f"({os.strerror(errno.ENOENT)}); its bytes before this run are "
            "kept as blob ")
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(said), (
        f"the line does not begin as it should: {lines[0]!r}")
    command = lines[0].split(", then: ", 1)[1]
    prefix = f"mkdir -p {shlex.quote(str(contracts))} && "
    assert command.startswith(prefix), (
        f"the directory is not made first: {command!r}")
    words = shlex.split(command)
    assert words[:4] == ["mkdir", "-p", str(contracts), "&&"], words
    assert words[4:9] == ["git", "-C", str(root), "cat-file", "blob"], words
    assert words[10:] == [">", str(pin)], words
    blob = subprocess.run(words[4:10], capture_output=True,
                          check=True).stdout
    assert blob == bytes_before[PIN], "the kept blob is not the pin's bytes"

    subprocess.run(["sh", "-c", command], check=True, capture_output=True)
    assert pin.read_bytes() == bytes_before[PIN]


def test_a_file_already_holding_its_old_bytes_is_not_written_again(
        update_shape, root, standard, monkeypatch):
    """A validator put the manifest's own bytes back before it went red,
    and the manifest would refuse a write. It holds what it held, so it is
    not written — the write it does not need would fail — and the rollback
    is whole."""
    original = (root / MANIFEST).read_bytes()

    def put_back_then_red(_root, _script):
        (root / MANIFEST).write_bytes(original)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", put_back_then_red)
    failing_in_undo(monkeypatch, update_shape, write=[MANIFEST])

    refusal = refused_by(update_shape, standard, root, "b")
    assert refusal.code == "update-validators-red"
    assert ("ROLLED BACK: every byte this command wrote has been put back, "
            "and the tree is exactly as it was:") in refusal.detail
    assert f"restored  {MANIFEST}" in refusal.detail
    assert HEADING not in refusal.detail


# ---------------------------------------------------------------------------
# A link that arrives between the write and the undo (review of PR #560)
# ---------------------------------------------------------------------------


def outside(tmp_path: Path) -> Path:
    """A directory beside the root, where a link can lead."""
    where = tmp_path / "outside"
    where.mkdir(exist_ok=True)
    return where


def hard_links_or_skip(tmp_path: Path) -> None:
    """Skip where this filesystem will not make a second name."""
    probe = outside(tmp_path) / "probe"
    probe.write_bytes(b"x")
    try:
        os.link(probe, outside(tmp_path) / "probe-too")
    except (OSError, NotImplementedError) as exc:  # pragma: no cover
        pytest.skip(f"this filesystem will not hard-link: {exc}")


@WINDOWS_SKIP
def test_a_symlink_that_arrives_before_the_undo_is_never_written_through(
        update_shape, root, standard, monkeypatch, tmp_path):
    """The reviewer's run: a validator moves `project.yaml` out of the root,
    links it back, and goes red. The undo wrote the old bytes at the link's
    end and said "the tree is exactly as it was" over a root holding a
    link. The link's end is left as the validator left it now, and the
    manifest is listed, with the line that puts it back once it is not a
    link, which, run so, leaves the tree exactly as it was."""
    away = outside(tmp_path) / MANIFEST
    seen: dict = {}

    def moved_and_linked(_root, _script):
        if not (root / MANIFEST).is_symlink():
            shutil.move(str(root / MANIFEST), str(away))
            (root / MANIFEST).symlink_to(away)
            seen["away"] = away.read_bytes()
        return 1

    monkeypatch.setattr(update_shape, "run_validator", moved_and_linked)
    before = snapshot(root)

    refusal = refused_by(update_shape, standard, root, "b")
    assert away.read_bytes() == seen["away"], (
        "the old bytes were written THROUGH the link, outside the root")
    assert (root / MANIFEST).is_symlink()
    assert_reported_as_red(refusal)
    assert "exactly as it was" not in refusal.detail
    assert put_back(refusal.detail) == [f"restored  {rel}"
                                        for rel in (CHANGED, AGENTS, PIN)]
    lines = left(refusal.detail)
    said = (f"file      {MANIFEST} was not put back: since this run wrote "
            f"it, {MANIFEST} in this root is a symlink, pointing at "
            f"{str(away)!r}, and this run never writes through one; it held "
            f"HEAD's bytes, so once {MANIFEST} is not a link: ")
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(said), (
        f"the line does not begin as it should: {lines[0]!r}")
    fix = shlex.split(lines[0][len(said):])
    assert fix == ["git", "-C", str(root), "--literal-pathspecs", "checkout",
                   "HEAD", "--", MANIFEST], fix

    (root / MANIFEST).unlink()
    subprocess.run(fix, check=True, capture_output=True)
    assert_untouched(before, snapshot(root))


@WINDOWS_SKIP
def test_a_directory_linked_in_above_the_path_is_never_written_through(
        update_shape, root, standard, monkeypatch, tmp_path):
    """THE SAME RUN, ONE LEVEL UP (R560v's mutant MS3, which the test above
    let through): a validator moves `contracts/` out of the root and links
    it back. The pin is a plain file at the link's end, so only a walk of
    every component finds the link. Narrowed to the pin's own `is_symlink`,
    the undo wrote the old bytes outside the root and said "exactly as it
    was" over a root holding a link. The pin is left as the validator left
    it, and listed; the line says the directory has to be this root's own
    again, rather than "not a link", which read as removing the link and
    then failed, "Directory nonexistent". Moved back, the line puts the
    bytes back and leaves the tree exactly as it was."""
    contracts, away = root / "contracts", outside(tmp_path) / "contracts"
    seen: dict = {}

    def moved_and_linked(_root, _script):
        if not contracts.is_symlink():
            shutil.move(str(contracts), str(away))
            contracts.symlink_to(away, target_is_directory=True)
            seen["pin"] = (away / Path(PIN).name).read_bytes()
        return 1

    monkeypatch.setattr(update_shape, "run_validator", moved_and_linked)
    before = snapshot(root)

    refusal = refused_by(update_shape, standard, root, "b")
    assert (away / Path(PIN).name).read_bytes() == seen["pin"], (
        "the old bytes were written THROUGH the directory link, outside "
        "the root")
    assert contracts.is_symlink()
    assert_reported_as_red(refusal)
    assert "exactly as it was" not in refusal.detail
    assert put_back(refusal.detail) == [
        f"restored  {rel}" for rel in (CHANGED, AGENTS, MANIFEST)]
    lines = left(refusal.detail)
    said = (f"file      {PIN} was not put back: since this run wrote it, "
            f"contracts in this root is a symlink, on the way to {PIN}, "
            f"pointing at {str(away)!r}, and this run never writes through "
            "one; it held HEAD's bytes, so once contracts is this root's "
            "own directory again: ")
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(said), (
        f"the line does not begin as it should: {lines[0]!r}")
    assert "is not a link" not in lines[0], lines[0]
    command = lines[0][len(said):]
    assert shlex.split(command) == [
        "git", "-C", str(root), "--literal-pathspecs", "checkout", "HEAD",
        "--", PIN], command

    contracts.unlink()
    shutil.move(str(away), str(contracts))
    subprocess.run(["sh", "-c", command], check=True, capture_output=True)
    assert_untouched(before, snapshot(root))


def second_name_said(root: Path) -> str:
    """The manifest's line, up to the command that puts its bytes back."""
    here = str(root / MANIFEST)
    copy = f"{here}.update-shape-copy"
    return (f"file      {MANIFEST} was not put back: since this run wrote "
            "it, it has gained another name on this filesystem (2 names), "
            "and a write in place would change that file too; it held "
            "HEAD's bytes, so replace it with a copy of itself first: "
            + shlex.join(["cp", "-p", "--", here, copy]) + " && "
            + shlex.join(["mv", "-f", "--", copy, here]) + ", then: ")


def second_name_then_red(update_shape, standard, root: Path, monkeypatch,
                         tmp_path: Path):
    """A validator gives the re-pinned manifest a second name outside the
    root and goes red. Returns the refusal, that name, and what it held."""
    hard_links_or_skip(tmp_path)
    other = outside(tmp_path) / MANIFEST
    seen: dict = {}

    def linked(_root, _script):
        if not other.exists():
            os.link(root / MANIFEST, other)
            seen["held"] = other.read_bytes()
        return 1

    monkeypatch.setattr(update_shape, "run_validator", linked)
    return refused_by(update_shape, standard, root, "b"), other, seen


def test_a_second_name_that_arrives_before_the_undo_is_never_written_through(
        update_shape, root, standard, monkeypatch, tmp_path):
    """The undo's `write_bytes` writes in place, so the old bytes would
    have landed under the other name too. The manifest is not written and
    is listed, with the copy line that breaks the link from this side
    first; the other name keeps the bytes it was given."""
    refusal, other, seen = second_name_then_red(update_shape, standard, root,
                                                monkeypatch, tmp_path)
    assert other.read_bytes() == seen["held"], (
        "the old bytes were written THROUGH the second name")
    assert os.path.samefile(root / MANIFEST, other)
    assert_reported_as_red(refusal)
    assert "exactly as it was" not in refusal.detail
    lines = left(refusal.detail)
    assert len(lines) == 1, (
        f"one line was expected, and {len(lines)} were printed: {lines}")
    assert lines[0].startswith(second_name_said(root)), (
        f"the line does not begin as it should: {lines[0]!r}")
    assert shlex.split(lines[0][len(second_name_said(root)):]) == [
        "git", "-C", str(root), "--literal-pathspecs", "checkout", "HEAD",
        "--", MANIFEST]


@WINDOWS_SKIP
def test_the_second_name_lines_pasted_put_the_bytes_back_and_leave_it_be(
        update_shape, root, standard, monkeypatch, tmp_path):
    """Both commands, as printed: the manifest holds its old bytes as a
    file of its own, and the other name still holds what it was given."""
    bytes_before = held(root)
    refusal, other, seen = second_name_then_red(update_shape, standard, root,
                                                monkeypatch, tmp_path)
    line = left(refusal.detail)[0]
    copy, checkout = line.split("first: ", 1)[1].split(", then: ", 1)
    subprocess.run(["sh", "-c", copy], check=True)
    subprocess.run(["sh", "-c", checkout], check=True, capture_output=True)
    assert (root / MANIFEST).read_bytes() == bytes_before[MANIFEST]
    assert other.read_bytes() == seen["held"]
    assert not os.path.samefile(root / MANIFEST, other)


@WINDOWS_SKIP
def test_a_link_at_an_add_path_is_never_removed_by_the_undo(
        update_shape, root, standard, monkeypatch, tmp_path):
    """The `--add` file is replaced by the operator's link while the
    validators run. Unlinking it would delete their link, which #239
    measured; it is left, and listed, and the other addition and the
    directory made for it go as before."""
    theirs = outside(tmp_path) / "theirs.md"
    theirs.write_bytes(b"someone else's file\n")

    def replaced(_root, _script):
        if not (root / ADDED).is_symlink():
            (root / ADDED).unlink()
            (root / ADDED).symlink_to(theirs)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", replaced)

    refusal = refused_by(update_shape, standard, root, "b", *ADDING)
    assert (root / ADDED).is_symlink()
    assert os.readlink(root / ADDED) == str(theirs)
    assert theirs.read_bytes() == b"someone else's file\n"
    assert_reported_as_red(refusal)
    assert left(refusal.detail) == [
        f"file      {ADDED}, written by --add, was not removed: since this "
        f"run wrote it, {ADDED} in this root is a symlink, pointing at "
        f"{str(theirs)!r}, and this run never removes at or through a link "
        "it did not make; what it leads to is yours to judge"]
    assert f"removed   {DIR_ADDED} (written by --add)" in put_back(
        refusal.detail)
    assert not (root / DIR).exists()


@WINDOWS_SKIP
def test_a_directory_linked_in_above_an_add_path_is_never_removed_under(
        update_shape, root, standard, monkeypatch, tmp_path):
    """THE SAME RUN, ONE LEVEL UP (R560v's mutant MR2, which the test above
    let through): the validators move the `docs/` that `--add` made out of
    the root and link it back. `docs/shape-guide.md` is a plain file at the
    link's end, so only a walk of every component finds the link; narrowed
    to the path's own `is_symlink`, the undo deleted that file OUTSIDE the
    root and said it had removed it, which is #239's hazard. Both the file
    and the directory are left and listed, each with what stands there; the
    file at the link's end is as the validators left it, and the other
    addition and every copy are put back as before."""
    docs, away = root / DIR, outside(tmp_path) / DIR

    def moved_and_linked(_root, _script):
        if not docs.is_symlink():
            shutil.move(str(docs), str(away))
            docs.symlink_to(away, target_is_directory=True)
        return 1

    monkeypatch.setattr(update_shape, "run_validator", moved_and_linked)

    refusal = refused_by(update_shape, standard, root, "b", *ADDING)
    assert (away / Path(DIR_ADDED).name).read_bytes() == BODIES[DIR_ADDED], (
        "the file at the link's end was removed, outside the root")
    assert docs.is_symlink()
    assert_reported_as_red(refusal)
    assert put_back(refusal.detail) == [
        *(f"restored  {rel}" for rel in REWRITTEN),
        f"removed   {ADDED} (written by --add)"]
    leads = ("and this run never removes at or through a link it did not "
             "make; what it leads to is yours to judge")
    assert left(refusal.detail) == [
        f"file      {DIR_ADDED}, written by --add, was not removed: since "
        f"this run wrote it, {DIR} in this root is a symlink, on the way to "
        f"{DIR_ADDED}, pointing at {str(away)!r}, {leads}",
        f"directory {DIR}/, made to hold an --add file, was not removed: "
        f"since this run wrote it, {DIR} in this root is a symlink, "
        f"pointing at {str(away)!r}, {leads}"]
