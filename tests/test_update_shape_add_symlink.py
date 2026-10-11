# SPDX-License-Identifier: Apache-2.0
"""`apply --add` at a path the operator keeps a SYMLINK at (#239).

`find_additions` asked `(root / path).exists()`, and `Path.exists()` FOLLOWS a
link: one whose target is missing read as "nothing there". `check` then
offered the path as `upstream-added`, and `apply --add` wrote the standard's
file THROUGH the link, creating whatever it points at — outside the root, if
that is where it points. When the project's own validators then went red the
rollback unlinked the operator's symlink, left the file it had made at the
link's end, and printed that the tree was exactly as it was.

A path the root holds anything at is present, and a symlink at it or above it
is the operator's. These tests pin that for every kind of link, in the places
it matters:

  * `check` does not offer the path, as it offers none the root already has.
  * `apply --add` refuses it BY NAME, `update-add-symlink`, exit 2, before it
    writes anything — a pinned copy that also changed upstream, the pin, the
    branch `--branch` would create and the directory `docs/` would need are
    all untouched — whether the project's validators are green (main wrote
    the standard's bytes outside the root and exited 0) or red (main deleted
    the link and left the file it had made).
  * A LINK ABOVE THE PATH is the same: `docs` a directory link, live or
    dangling, under `docs/shape-guide.md`. A dangling one was a `FileExistsError`
    traceback from `mkdir`; a live one took the file into the directory it
    leads to.
  * THE CONTROLS HOLD: a path nothing is at is added as before, a link
    elsewhere in the root is none of its business, a root the command is
    pointed at THROUGH a link is not "a link on the way", and a directory or a
    FIFO at the path is still refused as a path the root already has.

Every assertion about "nothing was written" compares the whole tree — every
file's bytes and mode, every link by its `readlink`, every directory, and git's
HEAD, branches, index and status — before and after, and the directories
outside the root the links lead to as well.

THE FIXTURE is `tests/test_update_shape.py`'s: a clone of this repository at A
and `Atlas` scaffolded from it into bare repositories on disk. Commit B fixes
one copied file (so a pinned copy is ALSO owed, and the refusal has to leave it
as it was) and adds two files to the assembly root's copy lists: one at the
top level, and one in `docs/`, a directory the root does not have yet.
`PYTHONDONTWRITEBYTECODE=1` is set for every run, because the validators
`apply` runs import `scripts/repo_shape.py` from the root and would otherwise
leave `scripts/__pycache__/` behind. No network is used and `gh` is never
invoked.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               scaffold_upstream_and_project)
from test_update_shape_add import (MATERIALIZER, commit_all, name_in_list,
                                   validators_are_green, verdicts)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import file_sha256, load_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"
ENV = {"PYTHONDONTWRITEBYTECODE": "1"}

#: What B adds to the assembly root's lists: a file at the top level, and one
#: in a directory the root does not have, so a link can stand at either the
#: path or above it.
ADDED = "AGENTS-link-test.md"
DIR = "docs"
DIR_ADDED = f"{DIR}/shape-guide.md"
BODIES = {
    ADDED: b"# The shape's notes, added after this project was cut.\n",
    DIR_ADDED: b"# A guide the standard gained, in a directory of its own.\n",
}
#: What an operator's own file, outside the root, holds.
THEIRS = b"someone else's file, which no tool here may touch\n"


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it, and B above them."""
    _base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-add-symlink")
    for rel, body in BODIES.items():
        target = upstream / "templates" / "assembly-root" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, so the blob is LF on every platform.
        target.write_bytes(body)
    fixed = upstream / CHANGED_SOURCE
    fixed.write_bytes(fixed.read_bytes() + UPSTREAM_FIX_LINE.encode("utf-8"))
    source = upstream / MATERIALIZER
    text = source.read_bytes().decode("utf-8")
    for rel in BODIES:
        text = name_in_list(text, "COPIED_VERBATIM", rel)
    source.write_bytes(text.encode("utf-8"))
    b = commit_all(upstream, "Fix the manifest validator and add two files "
                   "to the assembly root", [
                       MATERIALIZER, CHANGED_SOURCE,
                       *(f"templates/assembly-root/{rel}" for rel in BODIES)])
    assert a != b
    return {"upstream": upstream, "clone": clone, "a": a, "b": b}


@pytest.fixture
def root(standard, tmp_path):
    """A private, mutable copy of the project as it was cut at A."""
    target = tmp_path / PROJECT
    shutil.copytree(standard["clone"], target, symlinks=True)
    assert not (target / DIR).exists() and not (target / ADDED).exists()
    return target


def outside_dir(tmp_path: Path) -> Path:
    """A directory beside the root that exists: somewhere a link can lead
    that is not the root, and where a write through one would land."""
    where = tmp_path / "outside"
    where.mkdir(exist_ok=True)
    return where


def check(root, standard, *extra):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def apply(root, standard, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=ENV)


def pin_rows(root) -> dict:
    pin = load_yaml(root / "contracts" / "shape-pin.yaml")
    return {row["path"]: row["sha256"].lower() for row in pin["files"]}


def make_validators_red(root) -> None:
    """A wrong `topic:` in the manifest, committed so the tree is otherwise
    clean: the project's own `validate-manifest.py` refuses after any rewrite
    — the issue's way of making the run roll back."""
    manifest = root / "project.yaml"
    lines = manifest.read_text(encoding="utf-8").splitlines(keepends=True)
    lines = ["topic: xf-project-wrong\n" if line.startswith("topic:")
             else line for line in lines]
    manifest.write_text("".join(lines), encoding="utf-8")
    git("add", "--", "project.yaml", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "wrong topic", "--", "project.yaml", cwd=root)
    assert run_script(root / "scripts" / "validate-manifest.py", cwd=root,
                      env=ENV).returncode != 0, "fixture: the manifest is red"


# ---------------------------------------------------------------------------
# What a "tree is as it was" means, read off the disk and off git
# ---------------------------------------------------------------------------


def listing(directory: Path, skip: tuple = ()) -> dict:
    """Every entry under `directory`, by `lstat`: a file's bytes and mode, a
    link by WHERE IT POINTS (it is never read through — a dangling one has no
    bytes), a directory as one. Every `.git` is left out, the root's and the
    submodules' gitfiles: git moves its own bookkeeping whenever it looks."""
    found: dict = {}
    for here, subdirs, names in os.walk(directory):
        here = Path(here)
        for name in sorted(subdirs + names):
            path = here / name
            rel = path.relative_to(directory).as_posix()
            if name == ".git" or rel in skip:
                continue
            info = path.lstat()
            if stat.S_ISLNK(info.st_mode):
                found[rel] = ("link", os.readlink(path))
            elif stat.S_ISDIR(info.st_mode):
                found[rel] = ("dir",)
            elif stat.S_ISREG(info.st_mode):
                found[rel] = ("file", path.read_bytes(),
                              stat.S_IMODE(info.st_mode))
            else:
                found[rel] = ("special", stat.S_IFMT(info.st_mode))
        subdirs[:] = [name for name in subdirs if name != ".git"
                      and (here / name).relative_to(directory).as_posix()
                      not in skip]
    return found


def git_bytes(*args: str, cwd: Path) -> bytes:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          check=False)
    assert proc.returncode == 0, (f"git {' '.join(args)} in {cwd}:\n"
                                  f"{proc.stderr.decode(errors='replace')}")
    return proc.stdout


def snapshot(root: Path) -> dict:
    """The root, and git's half of it: where HEAD is, every branch, the
    index's `--stage` records (not the index FILE, whose stat cache moves
    whenever git looks) and `status` with the ignored files listed."""
    return {
        "tree": listing(root),
        "head": git_bytes("rev-parse", "HEAD", cwd=root)
        + subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=str(root),
                         capture_output=True, check=False).stdout,
        "branches": git_bytes("for-each-ref",
                              "--format=%(refname) %(objectname)",
                              "refs/heads", cwd=root),
        "index": git_bytes("ls-files", "--stage", "-z", cwd=root),
        "status": git_bytes("status", "--porcelain=v1", "-z", "--ignored",
                            "--untracked-files=all", cwd=root),
    }


def beyond(tmp_path: Path) -> dict:
    """Everything beside the root under `tmp_path`: where the links lead."""
    return listing(tmp_path, skip=(PROJECT,))


def assert_untouched(before: dict, after: dict) -> None:
    """`before == after`, said entry by entry when it is not, rather than as
    two dictionaries of bytes nobody can read."""
    tree_before, tree_after = before["tree"], after["tree"]
    added = sorted(set(tree_after) - set(tree_before))
    removed = sorted(set(tree_before) - set(tree_after))
    changed = sorted(rel for rel in set(tree_before) & set(tree_after)
                     if tree_before[rel] != tree_after[rel])
    assert (added, removed, changed) == ([], [], []), (
        f"written {added}, lost {removed}, changed {changed}")
    for key in ("head", "branches", "index", "status"):
        assert after[key] == before[key], (
            f"{key} is not what it was:\n  before {before[key]!r}\n"
            f"  after  {after[key]!r}")


# ---------------------------------------------------------------------------
# The links the operator keeps AT the path
# ---------------------------------------------------------------------------
#
# Each builder makes the link at `root / ADDED` and returns the path the
# standard's file would be created at, THROUGH it, and what that path held
# (`None` when nothing).


def dangling_inside(root: Path, tmp_path: Path):
    """Its directory is the root's own, and it holds nothing at the end."""
    (root / ADDED).symlink_to("scripts/not-there.md")
    return root / "scripts" / "not-there.md", None


def dangling_outside(root: Path, tmp_path: Path):
    """The issue's: its directory exists beside the root, and nothing is at
    its end. Main creates `agents.md` there."""
    target = outside_dir(tmp_path) / "agents.md"
    (root / ADDED).symlink_to(target)
    return target, None


def dangling_into_a_missing_directory(root: Path, tmp_path: Path):
    """The issue's last row: main raises `FileNotFoundError` from
    `write_added`, with the pinned copy it had already written left behind."""
    target = tmp_path / "no-such-dir" / "agents.md"
    (root / ADDED).symlink_to(target)
    return target, None


def live(root: Path, tmp_path: Path):
    """The operator's link to a file somebody else owns. Main refused it as
    `update-add-would-overwrite`, and did not write through it."""
    target = outside_dir(tmp_path) / "agents.md"
    target.write_bytes(THEIRS)
    (root / ADDED).symlink_to(target)
    return target, THEIRS


LINKS = [
    pytest.param(dangling_inside, id="dangling-inside-the-root"),
    pytest.param(dangling_outside, id="dangling-outside-the-root"),
    pytest.param(dangling_into_a_missing_directory,
                 id="dangling-into-a-missing-directory"),
    pytest.param(live, id="live"),
]


def assert_the_target_is_as_it_was(target: Path, held) -> None:
    if held is None:
        assert not target.exists(), (
            f"{target} was created THROUGH the link: a write at the path "
            "went to wherever the link points")
    else:
        assert target.read_bytes() == held, f"{target} was written through"


# --- check -------------------------------------------------------------------

@WINDOWS_SKIP
@pytest.mark.parametrize("make_link", LINKS)
def test_check_does_not_offer_a_path_the_operator_keeps_a_link_at(
        root, standard, tmp_path, make_link):
    """A dangling link read as "nothing there", so `check` offered the path
    as `upstream-added` and a human, pasting its `--add`, took it. The root
    HOLDS something there: `check` stays as silent as it is for any path the
    root has, and the other addition still reports."""
    target, held = make_link(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = check(root, standard)
    assert result.returncode == 1, result.stdout + result.stderr
    assert ADDED not in verdicts(result.stdout), (
        "`check` offers the path the operator keeps a link at")
    assert f"--add {ADDED}" not in result.stdout
    assert verdicts(result.stdout)[DIR_ADDED] == "upstream-added", (
        "the addition the root does not hold still reports")
    assert verdicts(result.stdout)[CHANGED] == "upstream-changed"
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere
    assert_the_target_is_as_it_was(target, held)


# --- apply --add -------------------------------------------------------------

@WINDOWS_SKIP
@pytest.mark.parametrize("validators", ["green", "red"])
@pytest.mark.parametrize("make_link", LINKS)
def test_add_refuses_a_link_by_name_before_it_writes_anything(
        root, standard, tmp_path, make_link, validators):
    """THE ISSUE, as an invariant that holds whichever way the run would have
    ended. Green, main wrote the standard's bytes outside the root and exited
    0; red, it rolled back by unlinking the operator's symlink, left the file
    it had created at the link's end, and said the tree was exactly as it
    was. Refused at the resolve step, nothing has been written to roll back:
    the pinned copy B also changed, the pin and the manifest are as they were,
    and so is every directory the link leads to."""
    target, held = make_link(root, tmp_path)
    if validators == "red":
        make_validators_red(root)
    link_text = os.readlink(root / ADDED)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", ADDED)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert ADDED in result.stderr
    assert link_text in result.stderr, (
        "the refusal says where the link points")
    assert "remove or move" in result.stderr, (
        "and what the operator does about it")
    assert "update-validators-red" not in result.stderr
    assert "ROLLED BACK" not in result.stderr, (
        "nothing was written, so nothing is rolled back")
    assert f"added    {ADDED}" not in result.stdout
    assert (root / ADDED).is_symlink()
    assert os.readlink(root / ADDED) == link_text
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere
    assert_the_target_is_as_it_was(target, held)
    assert ADDED not in pin_rows(root)


@WINDOWS_SKIP
def test_add_refuses_before_it_creates_the_branch_or_stages_anything(
        root, standard, tmp_path):
    """`--branch` is a write too (#202): the refusal comes before the branch
    exists, so there is none to put back and HEAD never moved."""
    dangling_outside(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", ADDED, "--branch",
                   "shape/add-link")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere
    assert "shape/add-link" not in git(
        "branch", "--list", cwd=root).stdout


@WINDOWS_SKIP
def test_one_link_among_several_additions_refuses_them_all(
        root, standard, tmp_path):
    """ALL OR NOTHING. The good addition is named FIRST, and the link second:
    the refusal still comes before either is written, so `docs/` was never
    made for the one that would have been fine."""
    dangling_outside(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", DIR_ADDED, "--add", ADDED)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert not (root / DIR).exists()
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


# --- a link ABOVE the path ---------------------------------------------------

def live_directory_link(root: Path, tmp_path: Path):
    """`docs` is the operator's link to a directory beside the root. Main
    wrote `shape-guide.md` into it and exited 0."""
    (root / DIR).symlink_to(outside_dir(tmp_path), target_is_directory=True)
    return tmp_path / "outside" / "shape-guide.md"


def dangling_directory_link(root: Path, tmp_path: Path):
    """`docs` leads nowhere. Main's `mkdir` died with `FileExistsError`: a
    traceback, with the pinned copy already written."""
    (root / DIR).symlink_to(tmp_path / "no-such-dir", target_is_directory=True)
    return tmp_path / "no-such-dir" / "shape-guide.md"


DIRECTORY_LINKS = [
    pytest.param(live_directory_link, id="live-directory-link"),
    pytest.param(dangling_directory_link, id="dangling-directory-link"),
]


@WINDOWS_SKIP
@pytest.mark.parametrize("make_link", DIRECTORY_LINKS)
def test_check_does_not_offer_a_path_under_a_directory_link(
        root, standard, tmp_path, make_link):
    make_link(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = check(root, standard)
    assert result.returncode == 1, result.stdout + result.stderr
    assert DIR_ADDED not in verdicts(result.stdout)
    assert f"--add {DIR_ADDED}" not in result.stdout
    assert verdicts(result.stdout)[ADDED] == "upstream-added", (
        "the addition at a path nothing is above still reports")
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere


@WINDOWS_SKIP
@pytest.mark.parametrize("validators", ["green", "red"])
@pytest.mark.parametrize("make_link", DIRECTORY_LINKS)
def test_add_refuses_a_path_under_a_directory_link(
        root, standard, tmp_path, make_link, validators):
    target = make_link(root, tmp_path)
    if validators == "red":
        make_validators_red(root)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", DIR_ADDED)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert f"{DIR} in this root is a symlink, on the way to {DIR_ADDED}" \
        in result.stderr, "the refusal names the link, not only the path"
    assert (root / DIR).is_symlink()
    assert_untouched(before, snapshot(root))
    assert beyond(tmp_path) == elsewhere
    assert not target.exists(), f"{target} was created through the link"
    assert DIR_ADDED not in pin_rows(root)


# --- the controls ------------------------------------------------------------

def test_a_path_with_nothing_at_it_is_added_as_before(root, standard):
    """The posture is unchanged where nothing is held: both additions land,
    each with its bytes and a row appended to the pin, and the project's own
    validators stay green."""
    result = apply(root, standard, "--add", ADDED, "--add", DIR_ADDED)
    assert result.returncode == 0, result.stdout + result.stderr
    for rel, body in BODIES.items():
        assert (root / rel).read_bytes() == body
        assert pin_rows(root)[rel] == file_sha256(root / rel)
    validators_are_green(root)


@WINDOWS_SKIP
def test_a_link_elsewhere_in_the_root_does_not_stop_an_addition(
        root, standard, tmp_path):
    """Only a link AT the path or ABOVE it is the path's business: the
    operator's other links, a live one and a dangling one, are left alone and
    do not make an unrelated addition `present`."""
    (root / "notes-link").symlink_to(outside_dir(tmp_path),
                                     target_is_directory=True)
    (root / "later.md").symlink_to("not-yet.md")
    (root / "scripts" / "docs-link").symlink_to("../no-such-dir")

    result = apply(root, standard, "--add", ADDED, "--add", DIR_ADDED)
    assert result.returncode == 0, result.stdout + result.stderr
    for rel, body in BODIES.items():
        assert (root / rel).read_bytes() == body
    assert os.readlink(root / "later.md") == "not-yet.md"
    assert not (root / "not-yet.md").exists()


@WINDOWS_SKIP
def test_a_root_reached_through_a_link_is_not_a_link_on_the_way(
        root, standard, tmp_path):
    """`--root` is resolved before anything is asked of a path, so a root the
    operator names through a symlink (macOS's `/var`, a project kept under a
    link into a bigger disk) still takes an addition: the walk starts BELOW
    it."""
    via = tmp_path / "via"
    via.symlink_to(root, target_is_directory=True)

    result = apply(via, standard, "--add", ADDED, "--add", DIR_ADDED)
    assert result.returncode == 0, result.stdout + result.stderr
    for rel, body in BODIES.items():
        assert (root / rel).read_bytes() == body


@pytest.mark.parametrize("kind", ["directory", "fifo"])
def test_a_directory_or_a_fifo_at_the_path_is_still_a_path_the_root_has(
        root, standard, kind):
    """`lexists` answers for anything at all, so what `exists()` already said
    yes to still does: refused as `update-add-would-overwrite`, which is
    what a merge is, and not as a link."""
    if kind == "directory":
        (root / ADDED).mkdir()
        (root / ADDED / "keep").write_text("kept\n", encoding="utf-8")
    elif hasattr(os, "mkfifo"):
        os.mkfifo(root / ADDED)
    else:
        pytest.skip("no FIFOs on this platform")
    before = snapshot(root)

    checked = check(root, standard)
    assert ADDED not in verdicts(checked.stdout)

    result = apply(root, standard, "--add", ADDED)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-would-overwrite" in result.stderr, result.stderr
    assert "update-add-symlink" not in result.stderr
    assert_untouched(before, snapshot(root))
