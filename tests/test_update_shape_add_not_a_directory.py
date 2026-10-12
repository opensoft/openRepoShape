# SPDX-License-Identifier: Apache-2.0
"""`apply --add <dir>/<file>` where the root holds something at `<dir>` that is
NOT A DIRECTORY, or a directory this process cannot write (#285).

`find_additions` asked only whether something is AT the path, and a path under
a plain file is not there: `lexists` says no, because the kernel answers
`ENOTDIR`. So `check` offered it, with the `--add` to paste, and `apply --add`
took it. `_write_copies` rewrote every `upstream-changed` copy, then
`Rollback.write_added` died making the directory under the file
(`NotADirectoryError`), or creating the file in a directory it cannot write
(`PermissionError`). `cmd_apply` rolled back on `Refusal` and `CommandFailed`
only, so the run printed a traceback over a tree with the copies rewritten and
the pin unmoved, and the next `check` read that copy as `already-at-target`.

Two changes, and these tests pin both:

  * (1) A path under something that is not a directory is refused BY NAME,
    `update-add-not-a-directory`, before anything is written. `check` keeps
    reporting the path, since the root holds nothing there, but no longer
    prints an `--add` it knows will be refused, and neither does `apply`'s
    note. Reverting it fails the plain-file and FIFO tests.
  * (2) An `OSError` out of the write phase (the copies, the additions, the
    pin and the manifest) is a refusal, `update-write-failed`, that names the
    step, the path and the error, and `cmd_apply`'s refusal arm puts back
    every byte written before it. Reverting it fails the read-only tests and
    the arrives-while-`apply`-waits test.
  * THE CONTROLS: nothing at `docs`, or `docs` a directory holding the
    project's own file, still adds.

THE FIXTURE, and what "untouched" means, are
`tests/test_update_shape_add_symlink.py`'s, imported rather than restated: a
clone of this repository at A, `Atlas` cut from it, and a commit B that fixes
`scripts/validate-manifest.py`, a pinned copy (so any run that writes, writes
that first), and adds `docs/shape-guide.md`, in a directory the root does not
have, and `AGENTS-link-test.md` at the top level.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP
from test_update_shape import CHANGED
from test_update_shape_add import commit_all, validators_are_green, verdicts
#: The fixtures are IMPORTED, which is how pytest finds them for this module
#: too: one scaffold, built the one way, rather than a second copy of it.
from test_update_shape_add_symlink import (  # noqa: F401 (fixtures)
    ADDED, BODIES, DIR, DIR_ADDED, ENV, apply, assert_untouched, check,
    pin_rows, root, snapshot, standard, update_shape)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

#: A directory's mode stops a write only for an account the kernel holds to
#: it: root writes anyway, and Windows ignores the bits on a directory.
POSIX_UNPRIVILEGED = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0,
    reason="a read-only directory or file stops a write only for an "
           "unprivileged POSIX account; root and Windows write anyway")

#: What the operator keeps at `docs`.
THEIRS = b"the operator's own notes, kept in a file named docs\n"


def pinned_commit(root: Path) -> str:
    return str(load_yaml(root / "contracts" / "shape-pin.yaml")["commit"])


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------


def test_the_walk_names_the_first_directory_the_root_holds_as_something_else(
        update_shape, tmp_path):
    """`lstat`, one component ABOVE the path at a time. What is AT the path
    is `present`'s question, not this one's, and a component that is missing
    ends the walk with no answer: nothing below it can be there either."""
    root = tmp_path / "Atlas"
    (root / "plain").mkdir(parents=True)
    (root / "a").mkdir()
    (root / "a" / "b").write_bytes(THEIRS)
    (root / DIR).write_bytes(THEIRS)

    walk = update_shape.not_a_directory_on_the_way
    assert walk(root, DIR_ADDED) == DIR
    assert walk(root, "a/b/c/d.md") == "a/b", "the FIRST one, by its path"
    assert walk(root, "plain/x.md") is None
    assert walk(root, "missing/x.md") is None
    assert walk(root, ADDED) is None
    assert walk(root, DIR) is None, "the path itself is `present`'s question"


@WINDOWS_SKIP
def test_the_walk_leaves_a_link_to_the_link_walk(update_shape, tmp_path):
    """A symlink above the path is `update-add-symlink`'s, asked first: this
    walk stops there with no answer of its own, rather than reading through
    the link to whatever it leads to."""
    root = tmp_path / "Atlas"
    root.mkdir()
    (tmp_path / "elsewhere").write_bytes(THEIRS)
    (root / DIR).symlink_to(tmp_path / "elsewhere")

    assert update_shape.not_a_directory_on_the_way(root, DIR_ADDED) is None
    assert update_shape.symlink_on_the_way(root, DIR_ADDED) == (
        DIR, str(tmp_path / "elsewhere"))


# ---------------------------------------------------------------------------
# (1) A path under something that is not a directory
# ---------------------------------------------------------------------------


def a_committed_file(root: Path) -> None:
    """The issue's: a plain file the project keeps, committed."""
    (root / DIR).write_bytes(THEIRS)
    commit_all(root, "a file named docs", [DIR])


def an_untracked_file(root: Path) -> None:
    (root / DIR).write_bytes(THEIRS)


def a_fifo(root: Path) -> None:
    if not hasattr(os, "mkfifo"):
        pytest.skip("no FIFOs on this platform")
    os.mkfifo(root / DIR)


NOT_DIRECTORIES = [
    pytest.param(a_committed_file, id="a-committed-file"),
    pytest.param(an_untracked_file, id="an-untracked-file"),
    pytest.param(a_fifo, id="a-fifo"),
]


def test_check_reports_a_path_under_a_file_without_an_add_for_it(
        root, standard):
    """The root holds nothing AT `docs/shape-guide.md`, so the path is still
    `upstream-added` and still reported. What `check` stops doing is print
    the `--add` for it: `apply` refuses that, and a line to paste that is
    known to fail is the tool handing a human a wrong answer. The addition
    nothing is in the way of keeps its `--add`."""
    an_untracked_file(root)
    before = snapshot(root)

    result = check(root, standard)
    assert_untouched(before, snapshot(root))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert verdicts(result.stdout).get(DIR_ADDED) == "upstream-added", (
        result.stdout)
    assert f"--add {DIR_ADDED}" not in result.stdout, (
        "`check` offers an --add it knows `apply` refuses:\n" + result.stdout)
    assert f"{DIR} in this root is not a directory" in result.stdout, (
        "the row says why there is no --add for it")
    assert f"--add {ADDED}" in result.stdout, (
        "the addition nothing is in the way of is still offered")


@pytest.mark.parametrize("make", NOT_DIRECTORIES)
def test_add_refuses_a_path_under_something_that_is_not_a_directory(
        root, standard, make):
    """(a), THE ISSUE: refused by name, exit 2, no traceback, before the
    first write, so there is nothing to roll back. The pinned copy B fixed
    is as it was, the pin still names A, and the operator's `docs` holds
    what it held."""
    make(root)
    pinned = pinned_commit(root)
    before = snapshot(root)

    result = apply(root, standard, "--add", DIR_ADDED)
    # THE INVARIANT FIRST: on the base the copy was rewritten and left.
    assert_untouched(before, snapshot(root))
    assert pinned_commit(root) == pinned
    assert DIR_ADDED not in pin_rows(root)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-not-a-directory" in result.stderr, (
        result.stderr)
    assert f"--add {DIR_ADDED}" in result.stderr
    assert f"{DIR} in this root is not a directory" in result.stderr, (
        "the refusal names what is in the way, not only the path")
    assert f"move {DIR} out of the way" in result.stderr, (
        "and what the operator does about it")
    assert "the same --add" in result.stderr
    assert "ROLLED BACK" not in result.stderr, (
        "nothing was written, so nothing is rolled back")
    assert f"copied   {CHANGED}" not in result.stdout


def test_one_blocked_addition_among_several_refuses_them_all(root, standard):
    """ALL OR NOTHING, as for a link: the addition that would have been fine
    is named FIRST, and is not written either."""
    an_untracked_file(root)
    before = snapshot(root)

    result = apply(root, standard, "--add", ADDED, "--add", DIR_ADDED)
    assert_untouched(before, snapshot(root))
    assert not (root / ADDED).exists()
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-not-a-directory" in result.stderr, (
        result.stderr)


def test_apply_does_not_tell_the_operator_to_pass_an_add_it_refuses(
        root, standard):
    """`apply`'s note for an addition it was not asked to take said `pass
    --add <path>`: for this one that is the line it refuses. The run itself,
    taking the other addition, goes ahead."""
    an_untracked_file(root)

    result = apply(root, standard, "--add", ADDED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / ADDED).read_bytes() == BODIES[ADDED]
    assert (root / DIR).read_bytes() == THEIRS
    notes = [line for line in result.stdout.splitlines()
             if line.strip().startswith(f"note     {DIR_ADDED}")]
    assert len(notes) == 1, result.stdout
    assert f"pass --add {DIR_ADDED}" not in notes[0], notes[0]
    assert f"{DIR} in this root is not a directory" in notes[0], notes[0]
    validators_are_green(root)


# ---------------------------------------------------------------------------
# (2) A write that fails after the copies
# ---------------------------------------------------------------------------


def an_unwritable_directory(root: Path):
    """(b), the issue's: `docs/` is there, empty, and this process cannot
    create a file in it. The walk has nothing to say about a directory, so
    the write is where it fails, after the copy."""
    (root / DIR).mkdir()
    (root / DIR).chmod(0o555)
    return (root / DIR, "writing the copies and the --add files", DIR_ADDED,
            [])


def an_unwritable_pin(root: Path):
    """The re-pin's half: `contracts/shape-pin.yaml` read-only. The copy AND
    the addition, with the directory made for it, are written before it, and
    all of them have to go."""
    pin = root / "contracts" / "shape-pin.yaml"
    pin.chmod(0o444)
    return (pin, "re-pinning contracts/shape-pin.yaml and project.yaml",
            "contracts/shape-pin.yaml",
            [f"removed   {DIR_ADDED} (written by --add)",
             f"removed   {DIR}/ (made to hold an --add file)"])


@POSIX_UNPRIVILEGED
@pytest.mark.parametrize("make", [
    pytest.param(an_unwritable_directory, id="an-unwritable-directory"),
    pytest.param(an_unwritable_pin, id="an-unwritable-pin"),
])
def test_a_write_that_fails_after_the_copies_is_refused_and_rolled_back(
        root, standard, make):
    """(b): exit 2 with a refusal that names the step, the path and the
    error, `ROLLED BACK`, and the tree as it was. On the base this was a
    `PermissionError` traceback with the copy left rewritten."""
    stuck, step, where, removed = make(root)
    pinned = pinned_commit(root)
    before = snapshot(root)
    try:
        result = apply(root, standard, "--add", DIR_ADDED)
        after = snapshot(root)
    finally:
        stuck.chmod(0o755 if stuck.is_dir() else 0o644)
    assert_untouched(before, after)
    assert pinned_commit(root) == pinned
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert (f"REFUSED update-write-failed: {step} failed at {where}: "
            f"{os.strerror(errno.EACCES)}") in result.stderr, result.stderr
    assert "ROLLED BACK: every byte" in result.stderr, result.stderr
    assert f"restored  {CHANGED}" in result.stderr
    for line in removed:
        assert line in result.stderr, result.stderr
    assert "Remediation:" in result.stderr


def test_a_file_that_arrives_where_a_directory_goes_is_refused_and_rolled_back(
        update_shape, root, standard, monkeypatch):
    """THE SAME WRITE, REACHED THE OTHER WAY. `prepare` found nothing at
    `docs`, so (1) has nothing to refuse; the operator's file arrives while an
    interactive `apply` waits in `confirm`. The pinned copy is written, then
    the addition meets the file where its directory goes. On the base that
    was a `NotADirectoryError` out of `cmd_apply` with the copy left
    rewritten; now the refusal arm puts it back and says so."""
    seen: dict = {}

    def a_file_arrives(*_args, **_kwargs) -> None:
        (root / DIR).write_bytes(THEIRS)
        seen["root"] = snapshot(root)

    monkeypatch.setattr(update_shape, "confirm", a_file_arrives)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    args = update_shape.build_parser().parse_args([
        "apply", "--root", str(root), "--yes",
        "--upstream", str(standard["upstream"]), "--at", standard["b"],
        "--add", DIR_ADDED])

    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.cmd_apply(args)
    assert_untouched(seen["root"], snapshot(root))
    assert (root / DIR).read_bytes() == THEIRS
    assert DIR_ADDED not in pin_rows(root)
    assert refused.value.code == "update-write-failed", refused.value
    assert refused.value.detail.startswith(
        "writing the copies and the --add files failed at "), (
        refused.value.detail)
    assert DIR_ADDED in refused.value.detail.splitlines()[0]
    assert "ROLLED BACK: every byte" in refused.value.detail, (
        refused.value.detail)
    assert f"restored  {CHANGED}" in refused.value.detail


# ---------------------------------------------------------------------------
# (c) The controls
# ---------------------------------------------------------------------------


def nothing_at_docs(root: Path) -> dict:
    return {}


def a_directory_of_the_projects(root: Path) -> dict:
    """`docs/` exists and holds the project's own file: a directory, so the
    walk has nothing to say, and the addition lands beside that file."""
    (root / DIR).mkdir()
    (root / DIR / "notes.md").write_bytes(THEIRS)
    commit_all(root, "the project's docs", [f"{DIR}/notes.md"])
    return {f"{DIR}/notes.md": THEIRS}


@pytest.mark.parametrize("make", [
    pytest.param(nothing_at_docs, id="nothing-at-docs"),
    pytest.param(a_directory_of_the_projects, id="a-directory-of-the-projects"),
])
def test_a_path_under_a_directory_or_under_nothing_still_adds(
        root, standard, make):
    """(c): `check` offers the `--add`, and `apply` takes it, writes the
    standard's bytes, appends the row and stays green; the project's own
    file beside it is as it was."""
    kept = make(root)

    checked = check(root, standard)
    assert f"--add {DIR_ADDED}" in checked.stdout, checked.stdout
    result = apply(root, standard, "--add", DIR_ADDED)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (root / DIR_ADDED).read_bytes() == BODIES[DIR_ADDED]
    assert DIR_ADDED in pin_rows(root)
    for rel, body in kept.items():
        assert (root / rel).read_bytes() == body
    validators_are_green(root)
