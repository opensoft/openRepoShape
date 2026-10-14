# SPDX-License-Identifier: Apache-2.0
"""`make siblings` and `family.py siblings`: where a member is cloned, on
which branch, and by which copy of the utility (#543).

Three defects, one file, because `scripts/siblings.py` is a pinned copy in
every family holder and the three are fixed in one change and one re-pin:

* A holder whose parent folder is not named after the family cloned every
  member into that folder FIRST and then printed the `mv` that moves the
  holder, so the re-run the warning asked for cloned each member a second
  time beside the moved holder. The folder is now asked first: the run stops,
  exit 1, nothing cloned, and the run after the move clones each member once.
* A new sibling was a plain `git clone`, on its remote's DEFAULT branch, not
  on the member's tracking branch. It is now cloned on the `tracking_branch:`
  the member's own `project.yaml` declares in the pinned copy under
  `members/`; with no pinned copy checked out it keeps the default branch
  and says so.
* `family.py siblings` ran the STANDARD's `templates/family-root/` copy, in
  its own process, so a holder pinned at another shape ran other code than
  `make siblings` does. It now runs the holder's own `scripts/siblings.py` as
  the Makefile runs it, and refuses a holder without one in the Makefile's
  words (#489, #503).

And the half of #461 that is product code: the clone is `--no-local`, so a
member remote that is a path on disk is read through git, not copied file by
file under a repack (#440).

THE SAME FAMILY AS `test_family.py` (its module fixture, this module's own
instance), with one change made once: IRSS's remote's default branch is moved
off `main`, the branch IRSS tracks, so a clone that took the default branch
is visibly on the wrong one. Each test works on its own copy of the holder.
"""

from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path

import pytest

from conftest import REPO, git, run_script
#: The family fixture, its names and the `make siblings` runner, imported
#: from the module that owns them.
from test_family import (  # noqa: F401
    ALLOW_FILE_PROTOCOL, FAMILY, MEMBERS, NAME, family, siblings,
)

#: The branch IRSS's remote is pointed at instead of `main`.
DEFAULT = "elsewhere"
MAKEFILE = REPO / "templates" / "family-root" / "Makefile"


@pytest.fixture(scope="module")
def diverged(family) -> dict:
    """The family, with IRSS's remote's DEFAULT branch made `elsewhere`
    (`main~1`) while IRSS still declares `tracking_branch: "main"`: what a
    member whose default branch is not its tracking branch looks like."""
    bare = family["remotes"] / "IRSS.git"
    git("branch", "-f", DEFAULT, "main~1", cwd=bare)
    git("symbolic-ref", "HEAD", f"refs/heads/{DEFAULT}", cwd=bare)
    return family


def holder_in(family: dict, parent: Path) -> Path:
    """A private copy of the holder at `<parent>/<NAME>`."""
    parent.mkdir(parents=True, exist_ok=True)
    holder = parent / NAME
    shutil.copytree(family["root"], holder, symlinks=True)
    return holder


def branch_of(path: Path) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=path).stdout.strip()


def clone_line(stdout: str, project: str) -> str:
    """The line that says how `project` is cloned, or would be."""
    lines = [line for line in stdout.splitlines()
             if line.startswith(f"  [{project}] ") and "clon" in line]
    assert len(lines) == 1, stdout
    return lines[0]


def move_commands(stderr: str) -> list[list[str]]:
    """The `mv` and `mkdir -p` lines the parent-folder warning prints, split
    as a POSIX shell splits them."""
    return [shlex.split(line) for line in stderr.splitlines()
            if line.startswith(" " * 12) and line.strip()[:3] in
            ("mv ", "mkd")]


def flat(text: str) -> str:
    return " ".join(text.split())


# --- the tracking branch -----------------------------------------------------


def test_the_fixture_member_tracks_main_and_its_remote_defaults_elsewhere(
        diverged):
    bare = diverged["remotes"] / "IRSS.git"
    head = git("symbolic-ref", "--short", "HEAD", cwd=bare).stdout.strip()
    assert head == DEFAULT
    declared = (diverged["root"] / "members" / "IRSS" /
                "project.yaml").read_text(encoding="utf-8")
    assert 'tracking_branch: "main"' in declared


def test_each_member_is_cloned_on_the_tracking_branch_it_declares(
        diverged, tmp_path):
    """Through `make siblings`' own script: IRSS lands on `main`, the branch
    its pinned `project.yaml` declares, and not on `elsewhere`, the branch a
    plain clone of its remote checks out; and that branch tracks `origin`'s,
    as a working clone's does."""
    holder = holder_in(diverged, tmp_path / NAME)
    result = siblings(holder)
    assert result.returncode == 0, result.stdout + result.stderr
    for project in MEMBERS:
        sibling = holder.parent / project
        assert branch_of(sibling) == "main", project
        upstream = git("rev-parse", "--abbrev-ref", "@{upstream}",
                       cwd=sibling).stdout.strip()
        assert upstream == "origin/main", project
    assert clone_line(result.stdout, "IRSS").endswith(
        " on main, its tracking branch (members/IRSS/project.yaml)")


def test_a_member_whose_pinned_copy_is_not_checked_out_keeps_the_default(
        diverged, tmp_path):
    """No pinned copy, no record of the branch here: the clone takes the
    remote's default branch, as it always did, and its line says why."""
    holder = holder_in(diverged, tmp_path / NAME)
    git("submodule", "deinit", "-q", "-f", "--", "members/IRSS", cwd=holder)
    assert not (holder / "members" / "IRSS" / "project.yaml").exists()

    result = siblings(holder)
    assert result.returncode == 0, result.stdout + result.stderr
    assert branch_of(holder.parent / "IRSS") == DEFAULT
    assert branch_of(holder.parent / "IRRS") == "main"
    said = clone_line(result.stdout, "IRSS")
    assert " on its remote's default branch: members/IRSS/project.yaml is " \
        "not checked out" in said, said


def test_a_tracking_branch_its_remote_lacks_is_a_finding_and_no_clone(
        diverged, tmp_path):
    """The member declares a branch its remote does not have: git refuses
    the clone, the run says so and exits 1, nothing is left at the path, and
    the other member is still placed."""
    holder = holder_in(diverged, tmp_path / NAME)
    manifest = holder / "members" / "IRSS" / "project.yaml"
    before = manifest.read_bytes()
    after = before.replace(b'tracking_branch: "main"',
                           b'tracking_branch: "no-such-branch"')
    assert after != before
    manifest.write_bytes(after)

    result = siblings(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "CLONE FAILED" in result.stdout
    assert "FINDING IRSS: git clone exited" in result.stderr
    assert "no-such-branch" in result.stderr
    assert not (holder.parent / "IRSS").exists()
    assert branch_of(holder.parent / "IRRS") == "main"


def test_the_dry_run_names_the_branch_it_would_clone_on(diverged, tmp_path):
    holder = holder_in(diverged, tmp_path / NAME)
    result = siblings(holder, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    said = clone_line(result.stdout, "IRSS")
    assert "would clone" in said
    assert said.endswith(
        ", on main, its tracking branch (members/IRSS/project.yaml)")
    assert not (holder.parent / "IRSS").exists()


def test_a_sibling_is_read_through_git_and_shares_no_file_with_its_remote(
        diverged, tmp_path):
    """`--no-local` (#461's product half, #440): a clone of a path on disk
    used to link or copy the remote's object files one by one, which a
    repack running in the remote can break half way. Read through git, the
    sibling's object store holds files of its own, none of them the
    remote's (a local clone hard-links them where the disk allows)."""
    holder = holder_in(diverged, tmp_path / NAME)
    result = siblings(holder)
    assert result.returncode == 0, result.stdout + result.stderr

    def inodes(objects: Path) -> set:
        found = set()
        for path in objects.rglob("*"):
            if path.is_file():
                stat = path.stat()
                found.add((stat.st_dev, stat.st_ino))
        return found

    remote = inodes(diverged["remotes"] / "IRRS.git" / "objects")
    sibling = inodes(holder.parent / "IRRS" / ".git" / "objects")
    assert remote
    assert sibling
    assert not remote & sibling


# --- the parent folder, asked before anything is cloned ----------------------


def test_a_misplaced_holder_clones_nothing_and_the_moved_one_clones_once(
        diverged, tmp_path):
    """The issue's own flow: `make siblings` in a holder under a folder not
    named after the family, the printed move, and `make siblings` again.
    The first run clones nothing; the second clones each member once,
    beside the moved holder; the old folder is left empty."""
    wrong = tmp_path / "somewhere-else"
    holder = holder_in(diverged, wrong)

    first = siblings(holder)
    assert first.returncode == 1, first.stdout + first.stderr
    assert "cloning" not in first.stdout
    assert "(a) the members" not in first.stdout
    assert "NOTHING WAS CLONED" in first.stderr
    assert "NOTHING WAS MOVED" in first.stderr
    assert flat(first.stderr).endswith(
        "siblings: stopped before cloning: the holder is not in a folder "
        f"named {NAME}. Nothing was cloned, fetched or moved.")
    assert sorted(os.listdir(wrong)) == [NAME]

    commands = move_commands(first.stderr)
    staged = tmp_path / f"{NAME}.holder"
    wanted = tmp_path / NAME
    assert commands == [["mv", str(holder), str(staged)],
                        ["mkdir", "-p", str(wanted)],
                        ["mv", str(staged), str(wanted / NAME)]]
    # The lines are a POSIX shell's (`test_family_printed_quoting.py` runs
    # them in one); here they are done as written on every system.
    for argv in commands:
        if argv[0] == "mkdir":
            Path(argv[2]).mkdir(parents=True, exist_ok=True)
        else:
            os.rename(argv[1], argv[2])

    moved = wanted / NAME
    second = siblings(moved)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "WARNING" not in second.stderr
    for project in MEMBERS:
        assert (wanted / project / ".git").is_dir(), project
        assert branch_of(wanted / project) == "main", project
    assert sorted(os.listdir(wrong)) == []


def test_a_misplaced_holders_dry_run_stops_in_the_same_words(diverged,
                                                            tmp_path):
    """A dry run asks what the real run asks: it stops at the folder, exit
    1, and names no member it would clone."""
    wrong = tmp_path / "somewhere-else"
    holder = holder_in(diverged, wrong)
    result = siblings(holder, "--dry-run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "would clone" not in result.stdout
    assert "NOTHING WAS CLONED" in result.stderr
    assert sorted(os.listdir(wrong)) == [NAME]


# --- family.py siblings runs the holder's own copy ---------------------------


def test_family_py_siblings_runs_the_holders_own_copy_with_its_imports(
        diverged, tmp_path):
    """The holder's `scripts/siblings.py` is made to say that it ran and
    which `repo_shape.py` it imported. `family.py siblings` runs THAT file,
    as `make siblings` does, in a process of its own, so the `repo_shape`
    it imports is the holder's copy beside it and not this checkout's."""
    holder = holder_in(diverged, tmp_path / NAME)
    script = holder / "scripts" / "siblings.py"
    text = script.read_bytes()
    entry = b"def main(argv: list[str] | None = None) -> int:\n"
    assert text.count(entry) == 1
    script.write_bytes(text.replace(entry, entry + (
        b"    import repo_shape as _shape\n"
        b"    print('HOLDER COPY RAN, repo_shape from',"
        b" Path(_shape.__file__).resolve())\n")))

    result = run_script(FAMILY, "siblings", "--family-root", str(holder),
                        "--dry-run", env=ALLOW_FILE_PROTOCOL)
    assert result.returncode == 0, result.stdout + result.stderr
    library = (holder / "scripts" / "repo_shape.py").resolve()
    assert f"HOLDER COPY RAN, repo_shape from {library}" in result.stdout


def test_family_py_siblings_refuses_a_holder_without_its_own_copy(
        diverged, tmp_path):
    """No `scripts/siblings.py` in the holder: refused by name, exit 2,
    nothing cloned, in the words the holder's Makefile refuses with (#503),
    the `--root` value quoted for a POSIX shell."""
    holder = holder_in(diverged, tmp_path / NAME)
    (holder / "scripts" / "siblings.py").unlink()

    result = run_script(FAMILY, "siblings", "--family-root", str(holder),
                        env=ALLOW_FILE_PROTOCOL)
    assert result.returncode == 2, result.stdout + result.stderr
    said = flat(result.stderr)
    assert said.startswith("REFUSED siblings-script-missing: family.py "
                           "siblings needs scripts/siblings.py, which this "
                           "holder does not have"), said
    assert sorted(os.listdir(holder.parent)) == [NAME]

    makefile = MAKEFILE.read_text(encoding="utf-8")
    start = makefile.index("SIBLINGS_MISSING = ")
    message = flat(makefile[start:makefile.index("SIBLINGS_GUARD", start)]
                   .replace("\\\n", " ")
                   .replace("$(SIBLINGS_SCRIPT)", "scripts/siblings.py"))
    head, tail = message.split(' --root "$(CURDIR)"`')
    head = head.split("which this holder does not have. ", 1)[1]
    assert head in said
    assert f" --root {shlex.quote(str(holder))}`" in said
    assert flat(tail) in said
