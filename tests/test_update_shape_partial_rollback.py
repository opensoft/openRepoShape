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
`undo` runs: nothing is patched at the write. A file is never `chmod`ed to
make it fail, which is POSIX-shaped. The rollback is started by the
project's validators going red (`run_validator` answers 1), or by a git
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
    file that stayed listed after it.

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
    assert len(lines) == 1 and lines[0].startswith(said), lines
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
    assert len(lines) == 1 and "kept as blob" in lines[0], lines
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
    assert (root / DIR).is_dir() and not any((root / DIR).iterdir())


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
