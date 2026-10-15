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
  * THE REFUSAL quotes where the link points as a literal, so a newline in it
    cannot print a line of its own.
  * THE LEDGER'S OWN GUARD, #239's second change: a link (or a file) that
    arrives after `prepare` looked, while an interactive `apply` waits in
    `confirm`, meets `write_added`'s exclusive create, which refuses it by
    name and records only what it made; `apply`'s refusal arm then puts back
    the copies already written.
  * A WINDOWS JUNCTION is a link: how an `lstat` result is read, and the walk
    handed a junction's, on every platform; real junctions on NTFS only.

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
from types import SimpleNamespace

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
#: The loader that imports a hyphenated tool in-process, for the tests that
#: call the walk and the ledger directly.
from test_scaffold_ignored_shape_files import load
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
    assert not (target / DIR).exists()
    assert not (target / ADDED).exists()
    return target


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module: the walk is asked about a junction no
    POSIX runner can make, and the ledger is handed a link `prepare` never
    saw."""
    return load(UPDATE, "update_shape_add_symlink")


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
    # THE INVARIANT FIRST, the wording after: this is the part that is wrong
    # on main, and it is what a failure there should name. The link's end
    # first of all — a file made THROUGH the link is the bug itself.
    assert_the_target_is_as_it_was(target, held)
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert (root / ADDED).is_symlink()
    assert os.readlink(root / ADDED) == link_text
    assert ADDED not in pin_rows(root)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert ADDED in result.stderr
    assert repr(link_text) in result.stderr, (
        "the refusal says where the link points, quoted as a literal")
    assert "remove or move" in result.stderr, (
        "and what the operator does about it")
    # The promise is the whole command's again (#286): a pinned copy, the
    # pin and the manifest kept as a link are refused too. It says SYMLINK:
    # a hard-linked copy has a refusal of its own (#422).
    assert "this command never writes through a symlink" in result.stderr
    assert "never writes through a link" not in result.stderr
    assert "update-validators-red" not in result.stderr
    assert "ROLLED BACK" not in result.stderr, (
        "nothing was written, so nothing is rolled back")
    assert f"added    {ADDED}" not in result.stdout


@WINDOWS_SKIP
def test_add_refuses_before_it_creates_the_branch_or_stages_anything(
        root, standard, tmp_path):
    """`--branch` is a write too (#202): the refusal comes before the branch
    exists, so there is none to put back and HEAD never moved."""
    dangling_outside(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", ADDED, "--branch",
                   "shape/add-link")
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert "shape/add-link" not in git(
        "branch", "--list", cwd=root).stdout
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr


@WINDOWS_SKIP
def test_one_link_among_several_additions_refuses_them_all(
        root, standard, tmp_path):
    """ALL OR NOTHING. The good addition is named FIRST, and the link second:
    the refusal still comes before either is written, so `docs/` was never
    made for the one that would have been fine."""
    dangling_outside(root, tmp_path)
    before, elsewhere = snapshot(root), beyond(tmp_path)

    result = apply(root, standard, "--add", DIR_ADDED, "--add", ADDED)
    assert not (root / DIR).exists()
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr


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
    assert not target.exists(), f"{target} was created through the link"
    assert beyond(tmp_path) == elsewhere
    assert_untouched(before, snapshot(root))
    assert (root / DIR).is_symlink()
    assert DIR_ADDED not in pin_rows(root)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert f"{DIR} in this root is a symlink, on the way to {DIR_ADDED}" \
        in result.stderr, "the refusal names the link, not only the path"


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


# --- what the refusal prints of the link -------------------------------------

@WINDOWS_SKIP
def test_where_a_link_points_is_quoted_and_cannot_print_a_line_of_its_own(
        root, standard, tmp_path):
    """Where a link points is the operator's text, and a name may hold a
    newline. Printed as it was, `.../out<LF>REFUSED fake` put a line on
    stderr that reads as a second refusal; quoted as a literal, it stays
    inside the one sentence that names the link."""
    outside = outside_dir(tmp_path)
    forged = os.fsencode(str(outside)) + b"/out\nREFUSED fake"
    os.symlink(forged, os.fsencode(str(root / ADDED)))

    result = apply(root, standard, "--add", ADDED)
    assert os.listdir(outside) == [], "a file was created THROUGH the link"
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    lines = result.stderr.splitlines()
    assert not [line for line in lines if line.startswith("REFUSED fake")], (
        "the link's target printed a line of its own:\n" + result.stderr)
    assert [line for line in lines if line.startswith("REFUSED")] == [
        line for line in lines
        if line.startswith("REFUSED update-add-symlink:")], result.stderr
    assert repr(os.fsdecode(forged)) in result.stderr


# --- the ledger's own guard (#239's second change) ---------------------------
#
# `prepare` walks the path and `resolve_additions` refuses what it finds, but
# `apply` writes LATER: an interactive run waits in `confirm` for a human to
# type yes. A link that arrived in between was written through, and the ledger
# had already recorded the path, so a red validator's undo unlinked the
# operator's link and left the file at its end. `write_added` now creates the
# file exclusively and records it only once it exists, and a name already
# taken is a refusal, so `apply`'s refusal arm puts back what it had written.


def a_dangling_link_at_the_path(root: Path, tmp_path: Path):
    target = outside_dir(tmp_path) / "agents.md"
    (root / ADDED).symlink_to(target)
    return ADDED, ADDED, target


def a_dangling_directory_link_above_it(root: Path, tmp_path: Path):
    target = tmp_path / "no-such-dir"
    (root / DIR).symlink_to(target, target_is_directory=True)
    return DIR_ADDED, DIR, target


@WINDOWS_SKIP
@pytest.mark.parametrize("make_link", [
    pytest.param(a_dangling_link_at_the_path, id="at-the-path"),
    pytest.param(a_dangling_directory_link_above_it, id="above-the-path"),
])
def test_the_ledger_never_writes_an_addition_through_a_link(
        update_shape, tmp_path, make_link):
    """The guard alone, with no walk in front of it. Main recorded the path
    and wrote through the link at it, and a dangling directory link above it
    was a `FileExistsError` traceback from `mkdir`. Now each is refused by
    name, the ledger holds nothing, and the link and its end are as they
    were."""
    root = tmp_path / PROJECT
    root.mkdir()
    rel, name, target = make_link(root, tmp_path)
    link_text = os.readlink(root / name)
    ledger = update_shape.Rollback(root)

    with pytest.raises(update_shape.Refusal) as refused:
        ledger.write_added(root / rel, b"x", False)
    assert not target.exists(), f"{target} was created THROUGH the link"
    assert ledger.created == [], "the ledger recorded a path it did not make"
    assert os.readlink(root / name) == link_text
    assert refused.value.code == "update-add-symlink"
    assert f"{name} in this root is a symlink" in refused.value.detail


def test_the_ledger_never_overwrites_a_file_that_arrived_after_the_check(
        update_shape, tmp_path):
    """The same window with no link in it: somebody's file at the path,
    made after `prepare` found nothing there. Main overwrote it, and a red
    validator's undo then deleted it. The exclusive create refuses it as a
    path the root has, and the bytes stay theirs."""
    root = tmp_path / PROJECT
    root.mkdir()
    (root / ADDED).write_bytes(THEIRS)
    ledger = update_shape.Rollback(root)

    with pytest.raises(update_shape.Refusal) as refused:
        ledger.write_added(root / ADDED, b"x", False)
    assert (root / ADDED).read_bytes() == THEIRS
    assert ledger.created == []
    assert refused.value.code == "update-add-would-overwrite"


def test_the_ledger_records_what_it_made_once_it_exists(update_shape,
                                                         tmp_path):
    """The control: with nothing in the way, the directory it had to make
    and the file are both recorded, in the order made, for the undo."""
    root = tmp_path / PROJECT
    root.mkdir()
    ledger = update_shape.Rollback(root)

    ledger.write_added(root / DIR_ADDED, BODIES[DIR_ADDED], False)
    assert ledger.created == [root / DIR, root / DIR_ADDED]
    assert (root / DIR_ADDED).read_bytes() == BODIES[DIR_ADDED]


@WINDOWS_SKIP
def test_a_link_that_arrives_while_apply_waits_is_refused_and_rolled_back(
        update_shape, root, standard, tmp_path, monkeypatch):
    """THE WINDOW ITSELF, in-process. `confirm` is where an interactive
    `apply` waits for a human, after `prepare` has looked; the operator's
    dangling link arrives there. The pinned copy B fixed is written before
    any addition, so the refusal has something to put back: `cmd_apply`'s
    refusal arm restores it, and the tree is exactly as it was when the run
    began to write. Main wrote the standard's file outside the root and
    finished the run."""
    target = outside_dir(tmp_path) / "agents.md"
    seen: dict = {}

    def a_link_arrives(*_args, **_kwargs) -> None:
        (root / ADDED).symlink_to(target)
        seen["root"], seen["beyond"] = snapshot(root), beyond(tmp_path)

    monkeypatch.setattr(update_shape, "confirm", a_link_arrives)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    args = update_shape.build_parser().parse_args([
        "apply", "--root", str(root), "--yes",
        "--upstream", str(standard["upstream"]), "--at", standard["b"],
        "--add", ADDED])

    with pytest.raises(update_shape.Refusal) as refused:
        update_shape.cmd_apply(args)
    assert not target.exists(), f"{target} was created THROUGH the link"
    assert beyond(tmp_path) == seen["beyond"]
    assert_untouched(seen["root"], snapshot(root))
    assert ADDED not in pin_rows(root)
    assert refused.value.code == "update-add-symlink"
    assert "ROLLED BACK: every byte" in refused.value.detail, (
        refused.value.detail)
    assert f"restored  {CHANGED}" in refused.value.detail


# --- an NTFS junction is a link too ------------------------------------------
#
# Windows' ordinary directory link is a JUNCTION. `lstat` reads one as a
# directory — CPython sets `S_IFLNK` for IO_REPARSE_TAG_SYMLINK only — so
# `is_symlink()` said no, and the walk let the standard's file through it. Its
# reparse tag is what says junction (CPython 3.12's own `ntpath.isjunction`
# asks the same, and `st_reparse_tag` exists since 3.8). The first two tests
# run on every platform: how an `lstat` result is read, and the walk handed a
# junction's. The last makes real junctions, which only NTFS has.

#: `IO_REPARSE_TAG_MOUNT_POINT` and `IO_REPARSE_TAG_SYMLINK`, spelled out:
#: `stat` names them on Windows only.
JUNCTION_TAG = 0xA0000003
SYMLINK_TAG = 0xA000000C


@pytest.mark.parametrize("info, is_link", [
    pytest.param(SimpleNamespace(st_mode=stat.S_IFDIR | 0o755,
                                 st_reparse_tag=JUNCTION_TAG),
                 True, id="junction"),
    pytest.param(SimpleNamespace(st_mode=stat.S_IFLNK | 0o777,
                                 st_reparse_tag=SYMLINK_TAG),
                 True, id="windows-symlink"),
    pytest.param(SimpleNamespace(st_mode=stat.S_IFLNK | 0o777),
                 True, id="posix-symlink"),
    pytest.param(SimpleNamespace(st_mode=stat.S_IFDIR | 0o755,
                                 st_reparse_tag=0),
                 False, id="windows-directory"),
    pytest.param(SimpleNamespace(st_mode=stat.S_IFDIR | 0o755),
                 False, id="posix-directory"),
    # A OneDrive placeholder or a deduplicated file: `lstat` stops only at a
    # link and traverses any other reparse point, so the tag it reports is
    # 0, while the attribute bits it read still say "reparse point". Asking
    # those bits would call a plain directory in a synced checkout a link.
    pytest.param(SimpleNamespace(
        st_mode=stat.S_IFDIR | 0o755, st_reparse_tag=0,
        st_file_attributes=(stat.FILE_ATTRIBUTE_DIRECTORY
                            | stat.FILE_ATTRIBUTE_REPARSE_POINT)),
        False, id="a-reparse-point-lstat-traverses"),
])
def test_an_lstat_result_says_symlink_or_junction(update_shape, info,
                                                  is_link):
    assert update_shape.is_link_info(info) == is_link


def test_the_walk_stops_at_a_junction_at_the_path_or_above_it(
        update_shape, tmp_path, monkeypatch):
    """The walk handed what Windows' `lstat` gives for a junction — a
    directory carrying the mount point's tag — at `docs`, above the path, and
    at the path itself. `os.readlink` reads a junction since 3.8, as the
    `\\\\?\\` path it leads to, so the refusal can still say where."""
    root = tmp_path / PROJECT
    for rel in (DIR, ADDED, "plain"):
        (root / rel).mkdir(parents=True)
    junctions = {root / DIR: r"\\?\C:\elsewhere",
                 root / ADDED: r"\\?\C:\elsewhere\agents"}
    real_lstat, real_readlink = os.lstat, os.readlink

    def lstat(path, *args, **kwargs):
        info = real_lstat(path, *args, **kwargs)
        if Path(path) in junctions:
            return SimpleNamespace(st_mode=info.st_mode,
                                   st_reparse_tag=JUNCTION_TAG)
        return info

    def readlink(path, *args, **kwargs):
        if Path(path) in junctions:
            return junctions[Path(path)]
        return real_readlink(path, *args, **kwargs)

    monkeypatch.setattr(os, "lstat", lstat)
    monkeypatch.setattr(os, "readlink", readlink)
    assert update_shape.symlink_on_the_way(root, DIR_ADDED) == (
        DIR, junctions[root / DIR]), "a junction above the path is missed"
    assert update_shape.symlink_on_the_way(root, ADDED) == (
        ADDED, junctions[root / ADDED]), "a junction at the path is missed"
    assert update_shape.symlink_on_the_way(root, "plain/x.md") is None
    assert update_shape.symlink_on_the_way(root, "missing/x.md") is None


JUNCTIONS_ONLY = pytest.mark.skipif(os.name != "nt",
                                    reason="junctions are NTFS's")


def make_junction(link: Path, target: Path) -> None:
    """An NTFS junction at `link`, leading to the directory `target`, which
    must exist while it is made. Neither way needs admin rights or Developer
    Mode, as a symlink on Windows does: CPython's own tests make theirs with
    `_winapi.CreateJunction`, and `mklink /J` is the shell's."""
    try:
        import _winapi
        create = _winapi.CreateJunction
    except (ImportError, AttributeError):
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)],
                       check=True, capture_output=True)
    else:
        create(str(target), str(link))


def a_live_junction_above(root: Path, tmp_path: Path):
    """`docs` leads to a directory beside the root, which must stay empty."""
    make_junction(root / DIR, outside_dir(tmp_path))
    return DIR_ADDED, DIR, tmp_path / "outside", []


def a_dangling_junction_above(root: Path, tmp_path: Path):
    """`docs` leads to a directory that has since gone, and must stay gone."""
    gone = tmp_path / "gone"
    gone.mkdir()
    make_junction(root / DIR, gone)
    gone.rmdir()
    return DIR_ADDED, DIR, gone, None


def a_junction_at_the_path(root: Path, tmp_path: Path):
    """The path itself is a junction. Without the tag it was refused, but as
    `update-add-would-overwrite`, a merge, which it is not."""
    make_junction(root / ADDED, outside_dir(tmp_path))
    return ADDED, ADDED, tmp_path / "outside", []


@JUNCTIONS_ONLY
@pytest.mark.parametrize("make_junction_for", [
    pytest.param(a_live_junction_above, id="live-junction-above"),
    pytest.param(a_dangling_junction_above, id="dangling-junction-above"),
    pytest.param(a_junction_at_the_path, id="junction-at-the-path"),
])
def test_a_junction_at_or_above_the_path_is_refused_as_a_link(
        root, standard, tmp_path, make_junction_for):
    """Asserted fact by fact rather than through `listing()`: `lstat` reads a
    junction as a directory, so the tree walk would follow it."""
    rel, name, where, held = make_junction_for(root, tmp_path)
    other = ADDED if rel == DIR_ADDED else DIR_ADDED
    status = git("status", "--porcelain", cwd=root, check=False)
    copy = (root / CHANGED).read_bytes()

    checked = check(root, standard)
    assert "Traceback" not in checked.stderr, checked.stderr
    assert rel not in verdicts(checked.stdout), checked.stdout
    assert f"--add {rel}" not in checked.stdout
    assert verdicts(checked.stdout).get(other) == "upstream-added", (
        checked.stdout)

    result = apply(root, standard, "--add", rel)
    assert (os.listdir(where) if where.exists() else None) == held, (
        f"{where} was written THROUGH the junction")
    assert result.returncode == 2, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert "REFUSED update-add-symlink" in result.stderr, result.stderr
    assert f"{name} in this root is a symlink" in result.stderr
    assert "ROLLED BACK" not in result.stderr
    assert rel not in pin_rows(root)
    assert (root / CHANGED).read_bytes() == copy
    after = git("status", "--porcelain", cwd=root, check=False)
    assert (after.returncode, after.stdout) == (status.returncode,
                                                status.stdout)
