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

The review round (#543) adds: the child process keeps family.py's escaped
stdout (#214); `init --work-dir` no longer promises a `make siblings` that
stops; the printed move runs as typed on a disk that ignores case and at a
filesystem or drive root, each simulated in this process so all three
systems ask the same question; a `tracking_branch:` that is no branch name is
shown escaped and not used; and the stop comes before any `git` command.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import REPO, git, load_without_bytecode, run_script
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


@pytest.fixture
def placement(monkeypatch):
    """The TEMPLATE's `siblings.py` in this process, for its move arithmetic.

    `load_without_bytecode`, so nothing is written under `templates/`; its
    `bootstrap` import is answered by the template's own `bootstrap.py`, the
    copy beside it in a holder. `sys.path`, which the file extends, and
    `sys.modules` are put back when the test ends."""
    scripts = REPO / "templates" / "family-root" / "scripts"
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "bootstrap", load_without_bytecode(
        scripts / "bootstrap.py", "placement_family_bootstrap"))
    return load_without_bytecode(scripts / "siblings.py",
                                 "placement_family_siblings")


def stored(path) -> Path | None:
    """`path` as a disk that ignores case finds it, each part matched to a
    name in its folder whatever its case; None when a part is missing."""
    path = Path(os.path.abspath(path))
    found = Path(path.anchor)
    for part in path.parts[1:]:
        try:
            names = os.listdir(found)
        except OSError:
            return None
        match = [name for name in names if name.casefold() == part.casefold()]
        if not match:
            return None
        found = found / match[0]
    return found


def another_path_to(patched, alias: Path, folder: Path) -> None:
    """`alias` exists and is the same directory as `folder`, as a disk with
    a second path to that folder answers; every other path as it is."""
    exists, samefile = Path.exists, os.path.samefile

    def same(one, two) -> bool:
        pair = {Path(one), Path(two)}
        return pair == {alias, folder} if alias in pair else samefile(one,
                                                                       two)

    patched.setattr(Path, "exists",
                    lambda self, **_: self == alias or exists(self))
    patched.setattr(os.path, "samefile", same)


def ignoring_case(patched) -> None:
    """`Path.exists` and `os.path.samefile` answering as macOS and Windows
    disks do, here on any system: a spelling in another case exists, and is
    the same file."""
    samefile = os.path.samefile
    patched.setattr(Path, "exists",
                    lambda self, **_: stored(self) is not None)
    patched.setattr(os.path, "samefile", lambda one, two: (
        None not in (stored(one), stored(two))
        and samefile(stored(one), stored(two))))


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
    assert f"\n  family folder   {holder.parent}\n" in result.stdout
    said = clone_line(result.stdout, "IRSS")
    assert "would clone" in said
    assert said.endswith(
        ", on main, its tracking branch (members/IRSS/project.yaml)")
    assert not (holder.parent / "IRSS").exists()


@pytest.mark.parametrize("declared, shown, why", [
    (b'"\\x1b[2Jcleared"', r"'\x1b[2Jcleared'",
     "holds a character that does not print, so it is not used as a branch"),
    (b"5", "5", "is not a branch name"),
    (b"[main]", "['main']", "is not a branch name"),
    (b'"  "', "'  '", "is not a branch name"),
], ids=["escape-sequence", "a-number", "a-list", "blank"])
def test_a_tracking_branch_that_is_no_branch_name_is_shown_and_not_used(
        diverged, tmp_path, declared, shown, why):
    """A value no branch can have is not handed to git and not printed raw:
    an ESC sequence would clear the screen of whoever reads the output, a
    number or a list is not a name at all. Each is shown as `repr` shows it,
    and the clone keeps the remote's default branch."""
    holder = holder_in(diverged, tmp_path / NAME)
    manifest = holder / "members" / "IRSS" / "project.yaml"
    before = manifest.read_bytes()
    after = before.replace(b'tracking_branch: "main"',
                           b"tracking_branch: " + declared)
    assert after != before
    manifest.write_bytes(after)

    result = siblings(holder, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\x1b" not in result.stdout
    assert clone_line(result.stdout, "IRSS").endswith(
        ", on its remote's default branch: members/IRSS/project.yaml "
        f"declares tracking_branch {shown}, which {why}")


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
    1, and names no member it would clone. Its header calls that folder the
    PARENT folder: the warning below it says it is not the family's."""
    wrong = tmp_path / "somewhere-else"
    holder = holder_in(diverged, wrong)
    result = siblings(holder, "--dry-run")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "would clone" not in result.stdout
    assert "NOTHING WAS CLONED" in result.stderr
    assert sorted(os.listdir(wrong)) == [NAME]
    assert f"\n  parent folder   {wrong}\n" in result.stdout
    assert "family folder" not in result.stdout


def test_a_misplaced_holder_stops_before_any_git_command_runs(diverged,
                                                             tmp_path):
    """The stop asks nothing of git: no `.gitmodules` read, no credential
    used, no member cloned. `GIT_TRACE` names a file every `git` the run
    starts writes to, so the file is absent after the stop; a `git` run with
    the same variable writes it, so the probe is shown to work here."""
    holder = holder_in(diverged, tmp_path / "somewhere-else")
    trace = tmp_path / "git-trace.log"
    result = siblings(holder, env={"GIT_TRACE": str(trace)})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "stopped before cloning" in result.stderr
    assert not trace.exists(), trace.read_text(encoding="utf-8")
    control = tmp_path / "git-trace-control.log"
    subprocess.run(["git", "--version"], capture_output=True, check=True,
                   env={**os.environ, "GIT_TRACE": str(control)})
    assert control.is_file()


# --- the printed move runs as typed on every disk ----------------------------


def test_a_parent_folder_in_another_case_is_renamed_on_a_disk_that_ignores_it(
        placement, monkeypatch, tmp_path):
    """macOS and Windows: the holder sits in `inkrouter/`, and `InkRouter`
    "exists" because it IS that folder. The exact name test stops the run
    on every disk, so the remedy renames the FOLDER through a staging name,
    which a disk that ignores case can do and a one-step rename onto itself
    cannot. The moves, done as written, leave the holder where the next run
    finds no warning."""
    folder = tmp_path / NAME.lower()
    root = folder / NAME
    root.mkdir(parents=True)
    with monkeypatch.context() as patched:
        ignoring_case(patched)
        warning = placement.parent_folder_warning(root, NAME)
    staged = tmp_path / f"{NAME}.folder"
    commands = move_commands(warning)
    assert commands == [["mv", str(folder), str(staged)],
                        ["mv", str(staged), str(tmp_path / NAME)]]

    for _, source, target in commands:
        os.rename(source, target)
    assert sorted(os.listdir(tmp_path)) == [NAME]
    assert placement.parent_folder_warning(tmp_path / NAME / NAME,
                                           NAME) is None


@pytest.mark.parametrize("there", [
    "nothing",
    pytest.param("a folder", marks=pytest.mark.skipif(
        os.name == "nt", reason="the simulation assumes Windows' default "
        "path equality, which ignores case, so a separate folder whose name "
        "differs only in case cannot be told apart there (an NTFS folder "
        "made case-sensitive can hold one)")),
    "a link",
])
def test_a_case_sensitive_disk_keeps_its_move(placement, monkeypatch,
                                              tmp_path, there):
    """Linux, where `InkRouter` and `inkrouter` are two folders: with
    nothing at `InkRouter`, the holder moves there through a staging name;
    with a folder of its own there, the holder moves into it, as it always
    did. A LINK named `InkRouter` onto this folder is the family folder
    reached through a link, so nothing is printed at all: never a rename of
    the folder through it. Simulated, so a system that refuses to make a
    link asks it too."""
    folder = tmp_path / NAME.lower()
    root = folder / NAME
    root.mkdir(parents=True)
    wanted = tmp_path / NAME
    exists, samefile = Path.exists, os.path.samefile

    def same(one, two) -> bool:
        pair = {Path(one), Path(two)}
        if wanted in pair:
            return there == "a link" and pair == {wanted, folder}
        return samefile(one, two)

    with monkeypatch.context() as patched:
        patched.setattr(Path, "exists", lambda self, **_: (
            there != "nothing" if self == wanted else exists(self)))
        patched.setattr(Path, "is_symlink", lambda self: (
            self == wanted and there == "a link"))
        patched.setattr(os.path, "islink", lambda path: (
            Path(path) == wanted and there == "a link"))
        patched.setattr(os.path, "samefile", same)
        warning = placement.parent_folder_warning(root, NAME)
    staged = tmp_path / f"{NAME}.holder"
    expected = {
        "nothing": [["mv", str(root), str(staged)],
                    ["mkdir", "-p", str(wanted)],
                    ["mv", str(staged), str(wanted / NAME)]],
        "a folder": [["mkdir", "-p", str(wanted)],
                     ["mv", str(root), str(wanted / NAME)]],
    }
    if there in expected:
        assert move_commands(warning) == expected[there]
    else:
        assert warning is None


@pytest.mark.parametrize("root", [
    PurePosixPath(f"/{NAME}"),
    PureWindowsPath(f"C:\\{NAME}"),
    PureWindowsPath(f"C:\\{NAME.lower()}"),
], ids=["filesystem-root", "drive-root", "drive-root-other-case"])
def test_a_holder_at_a_filesystem_or_drive_root_moves_through_a_staging_name(
        placement, root):
    """`/InkRouter` or `C:\\InkRouter`: the parent is the root, whose name is
    empty, so `<root>/InkRouter` is the holder itself and `mv X X/X` cannot
    run. The holder moves through a staging name. Asked of the paths alone,
    which `PurePosixPath` and `PureWindowsPath` spell as each system does."""
    warning = placement.parent_folder_warning(root, NAME)
    assert f"parent folder is {str(root.parent)!r}, not {NAME!r}" in warning
    staged = root.parent / f"{NAME}.holder"
    wanted = root.parent / NAME
    assert move_commands(warning) == [
        ["mv", str(root), str(staged)], ["mkdir", "-p", str(wanted)],
        ["mv", str(staged), str(wanted / NAME)]]


# --- the family folder reached through a link --------------------------------


def link_or_skip(link: Path, target: Path) -> None:
    """`link`, a directory link to `target`, made before anything else the
    test does, or a skip where this system refuses one (Windows without the
    right to make links)."""
    try:
        os.symlink(target, link, target_is_directory=True)
    except (OSError, NotImplementedError) as refused:
        pytest.skip(f"this system makes no directory link here: {refused}")


def test_a_family_folder_reached_through_a_link_passes_and_clones_into_it(
        diverged, tmp_path):
    """`<t>/InkRouter` is a link to `<t>/real-x`, which holds the holder, so
    the holder is reachable as `<t>/InkRouter/InkRouter`: the layout holds
    through the link. Both entry points ask about the resolved holder and
    pass, and `make siblings`' own script clones each member into `real-x`,
    the link's target, beside the holder. The header names that folder and
    the link."""
    real = tmp_path / "real-x"
    real.mkdir()
    link = tmp_path / NAME
    link_or_skip(link, real)
    holder_in(diverged, real)
    logical = link / NAME

    shim = run_script(FAMILY, "siblings", "--family-root", str(logical),
                      "--dry-run", env=ALLOW_FILE_PROTOCOL)
    assert shim.returncode == 0, shim.stdout + shim.stderr
    assert "WARNING" not in shim.stderr

    result = siblings(logical)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "WARNING" not in result.stderr
    assert (f"\n  family folder   {real}   (through the link {link})\n"
            in result.stdout)
    for project in MEMBERS:
        assert (real / project / ".git").is_dir(), project
        assert branch_of(link / project) == "main", project


def test_a_link_named_after_the_family_to_another_folder_is_not_accepted(
        diverged, tmp_path):
    """`<t>/InkRouter` leads to `<t>/other`, not to `<t>/real-x`, where the
    holder is: no family folder of this holder, so the run stops. Its move,
    done as written, puts the holder into `other` through the link, where
    the next run passes."""
    real, other = tmp_path / "real-x", tmp_path / "other"
    real.mkdir()
    other.mkdir()
    link = tmp_path / NAME
    link_or_skip(link, other)
    holder = holder_in(diverged, real)

    stopped = siblings(holder, "--dry-run")
    assert stopped.returncode == 1, stopped.stdout + stopped.stderr
    assert "NOTHING WAS CLONED" in stopped.stderr
    assert f"\n  parent folder   {real}\n" in stopped.stdout
    commands = move_commands(stopped.stderr)
    assert commands == [["mkdir", "-p", str(link)],
                        ["mv", str(holder), str(link / NAME)]]
    for argv in commands:
        if argv[0] == "mkdir":
            Path(argv[2]).mkdir(parents=True, exist_ok=True)
        else:
            os.rename(argv[1], argv[2])
    assert (other / NAME / "family.yaml").is_file()
    moved = siblings(link / NAME, "--dry-run")
    assert moved.returncode == 0, moved.stdout + moved.stderr


def test_a_family_folder_reached_through_a_windows_junction_passes(
        placement, monkeypatch, tmp_path):
    """A directory junction, the link Windows makes without privilege:
    `os.path.islink` says no and `os.path.isjunction` (3.12) says yes, and
    `Path.resolve()` follows it as it follows a link. It is the family
    folder reached through a link. Simulated, so every system asks it."""
    folder = tmp_path / "real-x"
    root = folder / NAME
    root.mkdir(parents=True)
    junction = tmp_path / NAME
    with monkeypatch.context() as patched:
        another_path_to(patched, junction, folder)
        patched.setattr(os.path, "islink", lambda path: False)
        patched.setattr(os.path, "isjunction",
                        lambda path: Path(path) == junction, raising=False)
        found = placement.family_link(root, NAME)
        warning = placement.parent_folder_warning(root, NAME)
    assert found == junction
    assert warning is None


def test_a_folder_is_renamed_only_for_a_difference_of_case(
        placement, monkeypatch, tmp_path):
    """A second path to this folder under another NAME that is neither a
    link nor a junction (a bind mount, say) is not answered by renaming the
    folder: that rename is for a name that differs only in case."""
    folder = tmp_path / "real-x"
    root = folder / NAME
    root.mkdir(parents=True)
    alias = tmp_path / NAME
    with monkeypatch.context() as patched:
        another_path_to(patched, alias, folder)
        warning = placement.parent_folder_warning(root, NAME)
    assert ["mv", str(folder), str(tmp_path / f"{NAME}.folder")] \
        not in move_commands(warning)


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


def test_family_py_siblings_escapes_what_its_stdout_cannot_encode(
        diverged, tmp_path):
    """#214, kept across the child process: family.py escapes what its
    stdout cannot hold, and the holder's copy it now runs in a process of its
    own writes into that same stdout, so it is told the same encoding and a
    handler that cannot raise. An ASCII stdout gets `\\u2014` for the em dash
    of the first line, and the run goes on."""
    holder = holder_in(diverged, tmp_path / NAME)
    result = run_script(FAMILY, "siblings", "--family-root", str(holder),
                        "--dry-run", env={**ALLOW_FILE_PROTOCOL,
                                          "PYTHONIOENCODING": "ascii"})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "UnicodeEncodeError" not in result.stderr
    assert f"({holder}) \\u2014 2 member(s)" in result.stdout


# --- init --work-dir makes no family folder ----------------------------------


def test_init_with_a_work_dir_promises_no_family_folder(diverged):
    """`--work-dir <dir>` puts the holder at `<dir>/<Family>` and makes no
    family folder; `<dir>` is not named after the family, so `make
    siblings` there clones nothing. The NEXT STEPS say that, and no longer
    that it puts each member's working clone in the family folder."""
    said = diverged["init"].stdout
    work = (diverged["base"] / "fam").resolve()
    assert f"\nfamily folder  none: {work} is not named {NAME}\n" in said
    assert ("--work-dir made no family folder, so `make siblings` clones "
            "nothing: it prints the `mv` that puts the holder in a folder "
            f"named {NAME}, and stops until it is there.") in flat(said)
    assert "in the family folder, on its tracking branch" not in flat(said)


def test_init_with_a_work_dir_named_after_the_family_keeps_the_promise(
        tmp_path):
    """`--work-dir <t>/InkRouter` lands the holder at
    `<t>/InkRouter/InkRouter`: a folder named after the family, where `make
    siblings` runs to the end, so the NEXT STEPS promise the clones there."""
    work = tmp_path / NAME
    result = run_script(FAMILY, "init", "--org", NAME, "--family", NAME,
                        "--created-by", "Test Human",
                        "--created-on", "2026-10-15",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(work), cwd=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"\nfamily folder  {work.resolve()}\n" in result.stdout
    assert ("`make siblings` then puts each member's WORKING clone beside "
            "the holder, in the family folder, on its tracking branch."
            ) in flat(result.stdout)
