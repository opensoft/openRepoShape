# SPDX-License-Identifier: Apache-2.0
"""The scaffold's and `family.py init`'s dry runs ask what their real runs
refuse before the first write, and the real runs refuse it by name (#609).

WHAT WAS WRONG, three lines of #459's review of #573:
- L2-34. Neither dry run asked `scaffold-target-exists` or
  `family-target-exists`, or whether `--work-dir`, `--local-remote-dir` or
  the family folder could be made. In the seven cases measured (four
  scaffold, three `init`) each dry run exited 0 with `--dry-run: nothing was
  created.`, and the real runs gave two clean refusals and five tracebacks
  (`FileExistsError` where a file stood where a folder must go,
  `NotADirectoryError` where a file stood where a working tree goes).
- L2-36. Any `gh repo view` failure read as "the repository does not exist":
  with a `gh` answering `HTTP 401: Bad credentials` both dry runs exited 0,
  the real scaffold failed at `gh repo create`, and the real `init` left an
  empty family folder.
- L2-35. A real `init` made `<into>/<Family>/` before it asked whether the
  holder's remote exists, so a refusal left that folder empty behind it.
- L2-60 (#459's review of #622). An EXISTING EMPTY working tree or holder this
  user cannot write in was not asked: the dry run exited 0, and the real run
  made the remotes and then died with a `PermissionError` traceback.
- L2-67 (#461's review of #622). Two tests spelled POSIX `strerror` text;
  `mkdir_says` asks the system for its own words.
- rv622r's two problems with the L2-60 change: `init` with `--into` named for
  the family raised `PermissionError` for a holder with no search bit before
  any question was asked, and a folder that is only unwritable was told to
  "move what stands in the way aside".

THE CURE. One question, asked by both runs before anything is made: every
folder the run makes (`shape_materialize.folder_cannot_be_made`), each
working tree it writes into (`target_in_the_way`), then every remote, where
only gh's own not-found answer means "absent"
(`refuse_unless_not_found`). The real run makes its folders only after all
of it, and a folder that still cannot be made is refused by name
(`make_folder`).

The GitHub route runs against a stub `gh` on PATH that answers `repo view`
as the test says and refuses anything else, and is POSIX only, as every
`#!` stub in this suite is.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ORG, REPO, SCAFFOLD, WINDOWS_SKIP, run_script
from test_dry_run_asks_remotes import (DRY_RUN_DONE, live_bare, load,
                                       no_gh_run, scratch_env, without_gh)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import Refusal  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
PROJECT = "Atlas"
HOLDER = "Orbit"
SCAFFOLD_FOLDER = "REFUSED scaffold-folder-cannot-be-made"
FAMILY_FOLDER = "REFUSED family-folder-cannot-be-made"


def touch(path: Path) -> None:
    """A file at `path`, somebody's, made with every folder above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"somebody's\n")


def mkdir_says(path: Path) -> str:
    """The system's own words for `path.mkdir(parents=True, exist_ok=True)`
    failing, as `make_folder` quotes them: its `strerror`. POSIX says `File
    exists` and `Not a directory`; Windows says `Cannot create a file when
    that file already exists`. A test asks the system, and spells neither.
    The call fails, so it makes nothing (L2-67)."""
    with pytest.raises(OSError) as caught:
        path.mkdir(parents=True, exist_ok=True)
    return caught.value.strerror or str(caught.value)


def snapshot(root: Path, leave_out=("ghbin", "gh.log")) -> dict:
    """Every path under `root` and what it is (a folder, a file's bytes, a
    link's target), so a test sees whether a run made, changed or removed
    anything. `leave_out` is what the test's own `gh` stub writes."""
    seen: dict = {}
    for here, folders, files in os.walk(root):
        folders[:] = [name for name in folders if name not in leave_out]
        for name in folders + [name for name in files
                               if name not in leave_out]:
            path = Path(here) / name
            key = path.relative_to(root).as_posix()
            seen[key] = (("link", os.readlink(path)) if path.is_symlink()
                         else ("folder",) if path.is_dir()
                         else ("file", path.read_bytes()))
    return seen


def scaffold(tmp_path: Path, *extra: str, dry_run: bool,
             env: dict | None = None):
    return run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02", *extra,
        *(["--dry-run"] if dry_run else []),
        env={**scratch_env(tmp_path), **(env or {})})


def family_init(tmp_path: Path, *extra: str, dry_run: bool,
                env: dict | None = None):
    return run_script(
        FAMILY, "init", "--org", ORG, "--family", HOLDER,
        "--created-by", "Test Human", "--created-on", "2026-09-02", *extra,
        *(["--dry-run"] if dry_run else []),
        env={**scratch_env(tmp_path), **(env or {})})


def refused_line(result) -> str:
    """The `REFUSED` line a run ended on, whatever WARNING came before it."""
    return next((line for line in result.stderr.splitlines()
                 if line.startswith("REFUSED ")), "")


def remediation_line(result) -> str:
    """The `Remediation:` line a refusal ended on."""
    return next((line for line in result.stderr.splitlines()
                 if line.startswith("Remediation:")), "")


def assert_refused(result, said: str) -> None:
    """Exit 2 with the refusal `said`, its whole line, and no traceback."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert refused_line(result) == said, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert DRY_RUN_DONE not in result.stdout, result.stdout


def assert_both_runs_refuse(tmp_path: Path, run, said: str):
    """THE ISSUE'S CLAIM, for one case: the dry run refuses `said`, the real
    run refuses it in the same words after the same plan, and neither makes,
    changes or removes anything under `tmp_path`, a temporary directory of
    its own included. Returns the real run."""
    scratch_env(tmp_path)
    before = snapshot(tmp_path)
    dry = run(dry_run=True)
    assert_refused(dry, said)
    assert snapshot(tmp_path) == before, "the dry run made something"
    real = run(dry_run=False)
    assert_refused(real, said)
    assert (real.stdout, real.stderr) == (dry.stdout, dry.stderr)
    assert snapshot(tmp_path) == before, (
        "the real run made something before it refused")
    return real


# --- L2-34: the seven cases measured, and the ones beside them ----------------

def scaffold_in(tmp_path: Path, work: str = "wd", remotes: str = "r"):
    """A scaffold run with `--work-dir <work>` and `--local-remote-dir
    <remotes>` under `tmp_path`, as `assert_both_runs_refuse` calls it."""
    def run(dry_run: bool):
        return scaffold(tmp_path, "--work-dir", str(tmp_path / work),
                        "--local-remote-dir", str(tmp_path / remotes),
                        dry_run=dry_run)
    return run


def init_in(tmp_path: Path, *landing: str, remotes: str = "r"):
    """A `family.py init` run landing as `landing` says (`--into <into>` by
    default) with `--local-remote-dir <remotes>` under `tmp_path`."""
    flags = ([landing[0], str(tmp_path / landing[1])] if landing
             else ["--into", str(tmp_path / "into")])

    def run(dry_run: bool):
        return family_init(tmp_path, *flags, "--local-remote-dir",
                           str(tmp_path / remotes), dry_run=dry_run)
    return run


def at(tmp_path: Path, relative: str) -> Path:
    """A path under `tmp_path` as the tools name it: resolved."""
    return (tmp_path / relative).resolve()


#: The scaffold's four measured cases and two beside them: `(what the test
#: puts in the way, the --work-dir and --local-remote-dir it passes, the
#: REFUSED line both runs end on)`. On main 2989b4c each dry run exited 0;
#: the real runs raised `FileExistsError` (a file at the work dir or the
#: remote dir), `NotADirectoryError` (a file named for the root inside the
#: work dir), or `FileExistsError`/`NotADirectoryError` from a file above
#: either, and refused only the non-empty tree.
SCAFFOLD_CASES = {
    "work-dir-is-a-file": (
        "wd", ("wd", "r"),
        lambda t: f"{SCAFFOLD_FOLDER}: --work-dir {at(t, 'wd')} cannot be "
                  f"made: {at(t, 'wd')} is a file, not a folder"),
    "work-dir-holds-a-file-named-Atlas": (
        "wd/Atlas", ("wd", "r"),
        lambda t: f"REFUSED scaffold-target-exists: {at(t, 'wd/Atlas')} "
                  "already exists and is a file, not a folder"),
    "work-dir-holds-a-nonempty-Atlas": (
        "wd/Atlas/f", ("wd", "r"),
        lambda t: f"REFUSED scaffold-target-exists: {at(t, 'wd/Atlas')} "
                  "already exists and is not empty"),
    "local-remote-dir-is-a-file": (
        "r", ("wd", "r"),
        lambda t: f"{SCAFFOLD_FOLDER}: --local-remote-dir {at(t, 'r')} "
                  f"cannot be made: {at(t, 'r')} is a file, not a folder"),
    "a-folder-above-the-work-dir-is-a-file": (
        "up", ("up/wd", "r"),
        lambda t: f"{SCAFFOLD_FOLDER}: --work-dir {at(t, 'up/wd')} cannot "
                  f"be made: {at(t, 'up')} is a file, not a folder"),
    "a-folder-above-the-remote-dir-is-a-file": (
        "up", ("wd", "up/r"),
        lambda t: f"{SCAFFOLD_FOLDER}: --local-remote-dir {at(t, 'up/r')} "
                  f"cannot be made: {at(t, 'up')} is a file, not a folder"),
}


@pytest.mark.parametrize("case", list(SCAFFOLD_CASES))
def test_a_scaffold_dry_run_refuses_what_its_real_run_refuses(tmp_path, case):
    """L2-34, the scaffold: on main every dry run here exited 0 and every
    real run but the non-empty tree's ended in a traceback, exit 1."""
    put, (work, remotes), said = SCAFFOLD_CASES[case]
    touch(tmp_path / put)
    assert_both_runs_refuse(tmp_path, scaffold_in(tmp_path, work, remotes),
                            said(tmp_path))


#: `family.py init`'s three measured cases and four beside them, as
#: `SCAFFOLD_CASES` holds the scaffold's: `(what the test puts in the way,
#: the landing flags, the REFUSED line)`. On main 2989b4c each dry run exited
#: 0, and the real runs raised `FileExistsError` or `NotADirectoryError`, or
#: refused only the non-empty holder.
FAMILY_CASES = {
    "family-folder-is-a-file": (
        "into/Orbit", (),
        lambda t: f"{FAMILY_FOLDER}: the family folder {at(t, 'into/Orbit')} "
                  f"cannot be made: {at(t, 'into/Orbit')} is a file, not a "
                  "folder"),
    "holder-is-a-file": (
        "into/Orbit/Orbit", (),
        lambda t: f"REFUSED family-target-exists: "
                  f"{at(t, 'into/Orbit/Orbit')} already exists and is a "
                  "file, not a folder"),
    "holder-nonempty": (
        "into/Orbit/Orbit/f", (),
        lambda t: f"REFUSED family-target-exists: "
                  f"{at(t, 'into/Orbit/Orbit')} already exists and is not "
                  "empty"),
    "into-is-a-file": (
        "into", (),
        lambda t: f"{FAMILY_FOLDER}: the family folder {at(t, 'into/Orbit')} "
                  f"cannot be made: {at(t, 'into')} is a file, not a folder"),
    "work-dir-is-a-file": (
        "wd", ("--work-dir", "wd"),
        lambda t: f"{FAMILY_FOLDER}: --work-dir {at(t, 'wd')} cannot be "
                  f"made: {at(t, 'wd')} is a file, not a folder"),
    "work-dir-holds-a-file-named-Orbit": (
        "wd/Orbit", ("--work-dir", "wd"),
        lambda t: f"REFUSED family-target-exists: {at(t, 'wd/Orbit')} "
                  "already exists and is a file, not a folder"),
    "local-remote-dir-is-a-file": (
        "r", (),
        lambda t: f"{FAMILY_FOLDER}: --local-remote-dir {at(t, 'r')} cannot "
                  f"be made: {at(t, 'r')} is a file, not a folder"),
}


@pytest.mark.parametrize("case", list(FAMILY_CASES))
def test_an_init_dry_run_refuses_what_its_real_run_refuses(tmp_path, case):
    """L2-34, `init`: on main every dry run here exited 0, and every real
    run but the non-empty holder's ended in a traceback, exit 1."""
    put, landing, said = FAMILY_CASES[case]
    touch(tmp_path / put)
    assert_both_runs_refuse(tmp_path, init_in(tmp_path, *landing),
                            said(tmp_path))


@pytest.fixture
def unwritable_folder(tmp_path):
    """A maker of folders this user cannot write in, where the test says:
    `make(relative, mode, holding=None)` makes `tmp_path/relative` (every
    folder above it writable), puts the file `holding` in it if told to,
    sets `mode` and returns it. Each is made writable again for pytest to
    delete. Skipped where nothing is refused to this user (root) and on
    Windows, whose folders have no such mode."""
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("a folder's mode refuses nothing to this user here")
    made: list = []

    def make(relative: str, mode: int, holding: str | None = None) -> Path:
        folder = tmp_path / relative
        folder.mkdir(parents=True)
        if holding:
            touch(folder / holding)
        folder.chmod(mode)
        made.append(folder)
        return folder
    yield make
    for folder in made:
        folder.chmod(0o755)


@pytest.fixture
def unwritable(unwritable_folder):
    """`tmp_path/ro`, a folder this user can read and enter but not write
    in."""
    return unwritable_folder("ro", 0o555)


@pytest.mark.parametrize("tool", ["scaffold", "family"])
def test_a_folder_that_cannot_be_written_in_is_refused_by_both_runs(
        tmp_path, unwritable, tool):
    """CAN BE MADE, NOT ONLY "IS NO FILE": a work directory under a folder
    this user cannot write in failed the real run's `mkdir` with a
    `PermissionError` traceback, and its dry run exited 0."""
    run = (scaffold_in(tmp_path, "ro/wd") if tool == "scaffold"
           else init_in(tmp_path, "--work-dir", "ro/wd"))
    folder = SCAFFOLD_FOLDER if tool == "scaffold" else FAMILY_FOLDER
    real = assert_both_runs_refuse(
        tmp_path, run,
        f"{folder}: --work-dir {at(tmp_path, 'ro/wd')} cannot be made: "
        f"{unwritable.resolve()} is a folder this user cannot write in")
    assert remediation_line(real) == unwritable_remediation("--work-dir")


#: Where a folder a run makes can be one this user cannot write in, as `(the
#: folder the test makes empty and unwritable, how a run lands, the REFUSED
#: line both runs end on, the flag the remediation names)`: one row per
#: flag, in each tool that has it.
CANNOT_WRITE_TEXT = "is a folder this user cannot write in"
UNWRITABLE_FOLDER_AT = {
    "scaffold-work-dir": (
        "wd", lambda t: scaffold_in(t),
        lambda t: f"{SCAFFOLD_FOLDER}: --work-dir {at(t, 'wd')} cannot be "
                  f"made: {at(t, 'wd')} {CANNOT_WRITE_TEXT}", "--work-dir"),
    "scaffold-local-remote-dir": (
        "r", lambda t: scaffold_in(t),
        lambda t: f"{SCAFFOLD_FOLDER}: --local-remote-dir {at(t, 'r')} "
                  f"cannot be made: {at(t, 'r')} {CANNOT_WRITE_TEXT}",
        "--local-remote-dir"),
    "family-into": (
        "into/Orbit", lambda t: init_in(t),
        lambda t: f"{FAMILY_FOLDER}: the family folder {at(t, 'into/Orbit')} "
                  f"cannot be made: {at(t, 'into/Orbit')} "
                  f"{CANNOT_WRITE_TEXT}", "--into"),
    "family-work-dir": (
        "wd", lambda t: init_in(t, "--work-dir", "wd"),
        lambda t: f"{FAMILY_FOLDER}: --work-dir {at(t, 'wd')} cannot be "
                  f"made: {at(t, 'wd')} {CANNOT_WRITE_TEXT}", "--work-dir"),
    "family-local-remote-dir": (
        "r", lambda t: init_in(t),
        lambda t: f"{FAMILY_FOLDER}: --local-remote-dir {at(t, 'r')} cannot "
                  f"be made: {at(t, 'r')} {CANNOT_WRITE_TEXT}",
        "--local-remote-dir"),
}

#: What every OTHER refusal of a folder says to do, as it always said it.
FOLDER_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Move what stands in the way aside, or pass a path where a folder can be "
    "made. There is no --force.")


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("case", list(UNWRITABLE_FOLDER_AT))
def test_an_unwritable_folder_a_run_makes_is_told_what_fits(
        tmp_path, unwritable_folder, case, dry_run):
    """rv622r's nit: an existing EMPTY `--work-dir`, `--local-remote-dir` or
    family folder whose only fault is its permissions was told to "move what
    stands in the way aside", nothing standing in the way. Each flag, in each
    tool, now says to give this user write and search permission or to
    choose another folder by that flag, and the run makes nothing."""
    put, lands, said, flag = UNWRITABLE_FOLDER_AT[case]
    unwritable_folder(put, CANNOT_WRITE["no-w"])
    scratch_env(tmp_path)
    before = snapshot(tmp_path)
    result = lands(tmp_path)(dry_run=dry_run)
    assert_refused(result, said(tmp_path))
    assert remediation_line(result) == unwritable_remediation(flag)
    assert snapshot(tmp_path) == before, "the run made something"


@pytest.mark.parametrize("tool, case", [
    ("scaffold", "work-dir-is-a-file"),
    ("scaffold", "local-remote-dir-is-a-file"),
    ("scaffold", "a-folder-above-the-work-dir-is-a-file"),
    ("scaffold", "a-folder-above-the-remote-dir-is-a-file"),
    ("family", "family-folder-is-a-file"),
    ("family", "into-is-a-file"),
    ("family", "work-dir-is-a-file"),
    ("family", "local-remote-dir-is-a-file")])
def test_a_folder_a_file_stands_in_keeps_its_remediation(
        tmp_path, tool, case):
    """Every other refusal of a folder says what it always said: a file at
    the folder or above it is told to be moved aside, which is true of it."""
    if tool == "scaffold":
        put, (work, remotes), said = SCAFFOLD_CASES[case]
        run = scaffold_in(tmp_path, work, remotes)
    else:
        put, landing, said = FAMILY_CASES[case]
        run = init_in(tmp_path, *landing)
    touch(tmp_path / put)
    real = assert_both_runs_refuse(tmp_path, run, said(tmp_path))
    assert remediation_line(real) == FOLDER_REMEDIATION


def test_the_folder_remediation_is_chosen_by_what_stands_in_the_way(
        tmp_path, monkeypatch):
    """`refuse_unmakeable_folder`: the permissions sentence for an answer
    that ends `CANNOT_WRITE_IN` (the folder or one above it), naming `choose`
    or, with none, `named`; `FOLDER_REMEDIATION` for any other."""
    ask = shape_materialize.refuse_unmakeable_folder
    for why, remediation in (
            (f"/x {shape_materialize.CANNOT_WRITE_IN}",
             unwritable_remediation("--flag")),
            ("/x is a file, not a folder", FOLDER_REMEDIATION),
            ("/x cannot be used as a folder: No such file or directory",
             FOLDER_REMEDIATION)):
        monkeypatch.setattr(shape_materialize, "folder_cannot_be_made",
                            lambda path, why=why: why)
        with pytest.raises(Refusal) as refused:
            ask("x-code", "--named", tmp_path, "--flag")
        assert refused.value.remediation == remediation
    monkeypatch.setattr(shape_materialize, "folder_cannot_be_made",
                        lambda path: f"/x {shape_materialize.CANNOT_WRITE_IN}")
    with pytest.raises(Refusal) as refused:
        ask("x-code", "--named", tmp_path)
    assert refused.value.remediation == unwritable_remediation("--named")


# --- L2-60: an EMPTY working tree this user cannot write in ------------------

#: A folder this user cannot write in, two ways: with no `w` (nothing may be
#: made in it) and with no `x` (nothing may be entered, so nothing made in
#: it either, though it still lists as empty). `os.access` is asked for
#: both, and each mode kills the question that asks for only one.
CANNOT_WRITE = {"no-w": 0o555, "no-x": 0o600}

#: Where each tool writes a working tree, as `(the tree's path under the
#: test's directory, how a run lands there, the code it refuses an occupied
#: tree by, the flag the person met the folder by)`.
TREE_AT = {
    "scaffold": ("wd/Atlas", scaffold_in, "scaffold-target-exists",
                 "--work-dir"),
    "family": ("into/Orbit/Orbit", init_in, "family-target-exists", "--into"),
}


def unwritable_remediation(flag: str) -> str:
    """What the refusal of an EMPTY working tree this user cannot write in
    says to do: not "choose an empty folder", which is about a tree that
    holds something."""
    return ("Remediation: nothing was created, and `--dry-run` refuses the "
            "same. Give this user write and search permission on that "
            f"folder, or choose another {flag}, and run this again.")


#: What each tool says to do about a tree that HOLDS something, as it always
#: said it; the empty unwritable tree no longer says it.
HOLDS_REMEDIATION = {
    "scaffold": "Remediation: choose an empty --work-dir. There is no "
                "--force: re-running over a live tree is not a scaffold.",
    "family": "Remediation: choose another --into (or an empty --work-dir); "
              "if that IS the holder, it is already a family and `family.py "
              "add` is what grows it. There is no --force.",
}


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("how", list(CANNOT_WRITE))
@pytest.mark.parametrize("tool", list(TREE_AT))
def test_an_empty_working_tree_this_user_cannot_write_in_is_refused_by_name(
        tmp_path, unwritable_folder, tool, how, dry_run):
    """L2-60, one run each: an existing EMPTY working tree (the scaffold's
    root, `init`'s holder) that this user cannot write in is refused by name
    before any remote is made, by the dry run and by the real run, which no
    longer dies in a `PermissionError` traceback once the bare remote
    exists. On main 396c0ff4 every dry run here exited 0, and every real
    run made the bare remote and then raised."""
    put, lands, code, flag = TREE_AT[tool]
    tree = unwritable_folder(put, CANNOT_WRITE[how])
    scratch_env(tmp_path)
    before = snapshot(tmp_path)
    result = lands(tmp_path)(dry_run=dry_run)
    assert_refused(result, f"REFUSED {code}: {tree.resolve()} already exists "
                           "and is a folder this user cannot write in")
    assert remediation_line(result) == unwritable_remediation(flag)
    assert snapshot(tmp_path) == before, "the run made something"
    assert not list(tmp_path.rglob("*.git")), "a remote was made"


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
def test_an_unwritable_holder_under_work_dir_says_to_choose_another_work_dir(
        tmp_path, unwritable_folder, dry_run):
    """The remediation names the flag the person landed by: with
    `--work-dir` there is no family folder, so `--into` would not move the
    holder it names."""
    tree = unwritable_folder("wd/Orbit", CANNOT_WRITE["no-w"])
    result = init_in(tmp_path, "--work-dir", "wd")(dry_run=dry_run)
    assert_refused(result, f"REFUSED family-target-exists: {tree.resolve()} "
                           "already exists and is a folder this user cannot "
                           "write in")
    assert remediation_line(result) == unwritable_remediation("--work-dir")


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("how", list(CANNOT_WRITE))
def test_an_unwritable_holder_in_the_family_folder_one_stands_in_is_refused(
        tmp_path, unwritable_folder, how, dry_run):
    """rv622r's problem 1: with `--into` named for the family, `Orbit/Orbit`
    is the holder, and `_landing` asked `(into / family / MANIFEST).is_file()`
    of it. For a holder with no search bit that raised `PermissionError`, a
    traceback from both runs before any question was asked; with the search
    bit it was refused by name. Both are refused by name now, and nothing is
    made."""
    tree = unwritable_folder("Orbit/Orbit", CANNOT_WRITE[how])
    scratch_env(tmp_path)
    before = snapshot(tmp_path)
    result = init_in(tmp_path, "--into", "Orbit")(dry_run=dry_run)
    assert_refused(result, f"REFUSED family-target-exists: {tree.resolve()} "
                           "already exists and is a folder this user cannot "
                           "write in")
    assert remediation_line(result) == unwritable_remediation("--into")
    assert snapshot(tmp_path) == before, "the run made something"
    assert not list(tmp_path.rglob("*.git")), "a remote was made"


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real-run"])
@pytest.mark.parametrize("held", ["a-file", "a-nonempty-folder"])
@pytest.mark.parametrize("tool", list(TREE_AT))
def test_a_working_tree_that_holds_something_keeps_its_remediation(
        tmp_path, tool, held, dry_run):
    """A tree that holds something, a file included, is told what both tools
    always told it, "choose an empty folder; there is no --force", and not
    the permissions sentence that fits an empty one."""
    put, lands, code, _ = TREE_AT[tool]
    touch(tmp_path / put if held == "a-file" else tmp_path / put / "f")
    result = lands(tmp_path)(dry_run=dry_run)
    assert refused_line(result).startswith(f"REFUSED {code}: ")
    assert remediation_line(result) == HOLDS_REMEDIATION[tool]


def test_a_working_tree_this_user_cannot_write_in_is_named_last(
        unwritable_folder):
    """`target_in_the_way`: an EMPTY folder this user cannot write in is
    named, and a folder that holds anything is still `is not empty`
    whatever its mode, the sentence both tools always gave."""
    ask = shape_materialize.target_in_the_way
    for how, mode in CANNOT_WRITE.items():
        assert (ask(unwritable_folder(f"empty-{how}", mode))
                == "is a folder this user cannot write in")
        assert (ask(unwritable_folder(f"full-{how}", mode, holding="f"))
                == "is not empty")


def test_the_remediation_is_chosen_by_what_stands_in_the_way():
    """`target_remediation`: the permissions sentence for the one answer
    that says so, and the tool's own sentence, unchanged, for every other."""
    pick = shape_materialize.target_remediation
    assert pick(shape_materialize.CANNOT_WRITE_IN, "holds", "--x") == (
        unwritable_remediation("--x"))
    for why in ("is not empty", "is a file, not a folder",
                "cannot be read: Permission denied"):
        assert pick(why, "holds", "--x") == "holds"


# --- L2-35, and the scaffold's own: a refused real run leaves no folder -------

def test_a_real_init_refused_for_its_remote_leaves_no_family_folder(
        tmp_path):
    """L2-35: on main the real run made `into/Orbit/` and then refused
    `family-remote-exists`, leaving it empty; #537's first line names it."""
    remote = live_bare(tmp_path / "r" / f"{HOLDER}.git")
    real = assert_both_runs_refuse(
        tmp_path, init_in(tmp_path),
        f"REFUSED family-remote-exists: {remote.resolve()} already exists "
        "and has commits")
    assert "it HAS commits" in real.stderr
    assert not (tmp_path / "into").exists()


def test_a_real_scaffold_refused_for_a_remote_leaves_no_work_dir(tmp_path):
    """The same order in the scaffold: on main its real run made
    `--work-dir` before it asked whether the remotes exist."""
    leg = live_bare(tmp_path / "r" / f"{PROJECT}-spec.git")
    assert_both_runs_refuse(
        tmp_path, scaffold_in(tmp_path),
        f"REFUSED scaffold-remote-exists: {leg.resolve()} already exists "
        "and has commits")
    assert not (tmp_path / "wd").exists()


@pytest.mark.parametrize("tool", ["family", "scaffold"])
def test_a_real_run_with_no_gh_leaves_no_work_dir(tmp_path, monkeypatch,
                                                  capsys, tool):
    """`gh-not-found` from the real run, as from the dry run (#537), and now
    before the work directory is made: on main the scaffold had made
    `--work-dir` and `init` its parent before they asked `gh`."""
    module, argv, refusal, first = no_gh_run(tmp_path, tool, False)
    asked = without_gh(monkeypatch)
    assert module.main(argv) == 2
    assert refusal in capsys.readouterr().err
    assert asked == [first]
    assert not (tmp_path / "work").exists()


# --- the real run's own `mkdir`, when the question said yes -------------------

#: Where each real run makes a folder, as `(tool, the folder flags, what the
#: test puts in the way, how the refusal names the folder, the start of the
#: REFUSED line)`. The question is answered "yes" by a stand-in, as a folder
#: made or replaced between the question and the `mkdir` would answer it.
MKDIR_CASES = {
    "scaffold-work-dir": (
        "scaffold", ("--work-dir", "wd", "--local-remote-dir", "r"), "wd",
        f"{SCAFFOLD_FOLDER}: --work-dir"),
    "scaffold-local-remote-dir": (
        "scaffold", ("--work-dir", "wd", "--local-remote-dir", "r"), "r",
        f"{SCAFFOLD_FOLDER}: --local-remote-dir"),
    "family-folder": (
        "family", ("--into", "into", "--local-remote-dir", "r"), "into/Orbit",
        f"{FAMILY_FOLDER}: the family folder"),
    "family-local-remote-dir": (
        "family", ("--into", "into", "--local-remote-dir", "r"), "r",
        f"{FAMILY_FOLDER}: --local-remote-dir"),
}


@pytest.mark.parametrize("case", list(MKDIR_CASES))
def test_a_folder_the_real_run_cannot_make_is_refused_not_raised(
        tmp_path, monkeypatch, capsys, case):
    """THE REAL RUN'S `mkdir` IS ANSWERED TOO: a folder that cannot be made
    when the run makes it is the same refusal, in the system's words, and
    never a `FileExistsError` traceback out of `main`. No remote is made."""
    tool, flags, put, said = MKDIR_CASES[case]
    touch(tmp_path / put)
    if tool == "scaffold":
        module = load("parity_scaffold", SCAFFOLD)
        argv = ["--org", ORG, "--project", PROJECT, "--elected-by",
                "Test Human", "--elected-on", "2026-09-02"]
    else:
        module = load("parity_family", FAMILY)
        argv = ["init", "--org", ORG, "--family", HOLDER, "--created-by",
                "Test Human"]
    argv += [str(tmp_path / value) if index % 2 else value
             for index, value in enumerate(flags)]
    monkeypatch.setattr(shape_materialize, "folder_cannot_be_made",
                        lambda path: None)
    assert module.main(argv) == 2
    err = capsys.readouterr().err
    assert (f"{said} {at(tmp_path, put)} cannot be made: "
            f"{mkdir_says(tmp_path / put)}\n"
            "Remediation: no remote was created.") in err, err
    assert not list(tmp_path.rglob("*.git"))


# --- L2-36: only gh's not-found answer means "absent" -------------------------

#: A `gh` that answers `repo view` with `$STUB_GH_SAYS` on stderr, `%s` being
#: the repository asked about, and exits `$STUB_GH_EXIT`; anything else, a
#: `repo create` included, is refused with exit 97 and logged, so a run that
#: went on to create something is seen and never reaches GitHub.
STUB_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_GH_LOG"
case "$*" in
  "repo view "*)
    printf "$STUB_GH_SAYS\\n" "$3" >&2
    exit "$STUB_GH_EXIT" ;;
esac
echo "stub gh: not a repo view: $*" >&2
exit 97
"""

#: GitHub's answer for a repository it does not have, as gh 2.x prints it
#: (`api.FetchRepository` and go-gh's `GraphQLError`), exit 1: the ONE
#: failure that means "absent".
NOT_FOUND = (1, "GraphQL: Could not resolve to a Repository with the name "
                "'%s'. (repository)")

#: Every other way `gh repo view` fails, as `(exit, what gh says)`: a bad
#: token, a rate limit, no network, gh's "authentication required" (exit 4),
#: and the not-found words under an exit that is not gh's not-found one.
FAILURES = {
    "http-401": (1, "HTTP 401: Bad credentials "
                    "(https://api.github.com/graphql)\\nTry authenticating "
                    "with:  gh auth login"),
    "rate-limit": (1, "GraphQL: API rate limit exceeded for user ID 1."),
    "no-network": (1, "error connecting to api.github.com\\ncheck your "
                      "internet connection or https://githubstatus.com"),
    "auth-required": (4, "To get started with GitHub CLI, please run:  gh "
                         "auth login"),
    "not-found-words-exit-4": (4, NOT_FOUND[1]),
}


def stub_gh(tmp_path: Path, answer: tuple):
    """`(env, calls)`: the stub first on PATH answering `repo view` with
    `answer`, no real login reachable, and a reader of its log."""
    directory = tmp_path / "ghbin"
    directory.mkdir()
    shim = directory / "gh"
    shim.write_bytes(STUB_GH.encode("utf-8"))
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "gh.log"
    code, says = answer
    env = {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
           "STUB_GH_LOG": str(log), "STUB_GH_SAYS": says,
           "STUB_GH_EXIT": str(code), "GH_TOKEN": "bogus-w609",
           "GH_CONFIG_DIR": str(tmp_path / "ghconfig")}

    def calls() -> list:
        return (log.read_text(encoding="utf-8").splitlines()
                if log.exists() else [])
    return env, calls


def first_line(answer: tuple, repository: str) -> str:
    """What the refusal quotes of gh's answer: its first line."""
    return answer[1].split("\\n")[0].replace("%s", repository)


def on_github(tmp_path: Path, tool: str, env: dict, *extra: str):
    """A run of `tool` against GitHub (no `--local-remote-dir`) with `env`,
    as `assert_both_runs_refuse` calls it."""
    def run(dry_run: bool):
        if tool == "scaffold":
            return scaffold(tmp_path, "--work-dir", str(tmp_path / "work"),
                            *extra, dry_run=dry_run, env=env)
        return family_init(tmp_path, "--into", str(tmp_path / "into"),
                           *extra, dry_run=dry_run, env=env)
    return run


def unreadable(repository: str, answer: tuple) -> str:
    """The REFUSED line for a `gh repo view` failure that is not gh's
    not-found answer."""
    return (f"REFUSED remote-unreadable: whether {repository} already exists "
            "on GitHub cannot be told: `gh repo view "
            f"{repository} --json name` exited {answer[0]}: "
            f"{first_line(answer, repository)}")


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
@pytest.mark.parametrize("failure", list(FAILURES))
@pytest.mark.parametrize("tool", ["scaffold", "family"])
def test_a_gh_failure_that_is_not_not_found_is_refused_by_both_runs(
        tmp_path, tool, failure):
    """L2-36: on main a 401 read as "does not exist", so both dry runs
    exited 0, the real scaffold failed at `gh repo create` and the real
    `init` left an empty family folder. Now both runs refuse at the first
    `repo view`, in the same words, and nothing is made or asked after."""
    answer = FAILURES[failure]
    env, calls = stub_gh(tmp_path, answer)
    repository = f"{ORG}/{PROJECT if tool == 'scaffold' else HOLDER}"
    real = assert_both_runs_refuse(tmp_path, on_github(tmp_path, tool, env),
                                   unreadable(repository, answer))
    assert ("Only gh's own answer that a repository does not exist (exit 1, "
            "`Could not resolve to a Repository`)") in real.stderr
    assert calls() == [f"repo view {repository} --json name"] * 2
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "into").exists()


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
def test_a_reused_root_whose_existence_gh_cannot_tell_is_refused(tmp_path):
    """`--reuse-empty-repo` reads the root's visibility first, and a failure
    there is still "visibility unknown" (it only says which visibility the
    legs inherit); the existence question that follows refuses it."""
    answer = FAILURES["http-401"]
    env, calls = stub_gh(tmp_path, answer)
    repository = f"{ORG}/{PROJECT}"
    assert_both_runs_refuse(
        tmp_path, on_github(tmp_path, "scaffold", env, "--reuse-empty-repo"),
        unreadable(repository, answer))
    assert calls() == [f"repo view {repository} --json visibility",
                       f"repo view {repository} --json name"] * 2


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
@pytest.mark.parametrize("tool", ["scaffold", "family"])
def test_gh_not_found_still_means_absent_in_both_runs(tmp_path, tool):
    """The control: gh's not-found answer is "absent", so the dry run plans
    and exits 0 having asked each repository once, and the real run goes on
    to `gh repo create`, which the stub refuses."""
    env, calls = stub_gh(tmp_path, NOT_FOUND)
    run = on_github(tmp_path, tool, env)
    names, created = (([PROJECT, f"{PROJECT}-spec", f"{PROJECT}-code"],
                       f"{PROJECT}-spec") if tool == "scaffold"
                      else ([HOLDER], HOLDER))
    views = [f"repo view {ORG}/{name} --json name" for name in names]
    dry = run(dry_run=True)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert DRY_RUN_DONE in dry.stdout
    assert calls() == views
    assert not (tmp_path / "work").exists()
    assert not (tmp_path / "into").exists()
    real = run(dry_run=False)
    assert real.returncode == 2, real.stdout + real.stderr
    assert "REFUSED a git or gh command failed" in real.stderr
    assert calls()[:-1] == views * 2
    assert calls()[-1].startswith(f"repo create {ORG}/{created} ")


# --- one definition, both tools -----------------------------------------------

@pytest.mark.parametrize("tool", ["scaffold", "family"])
def test_both_tools_ask_the_one_definition(tool):
    module = (load("parity_scaffold_names", SCAFFOLD) if tool == "scaffold"
              else load("parity_family_names", FAMILY))
    for name in ("refuse_unmakeable_folder", "make_folder",
                 "target_in_the_way", "target_remediation",
                 "refuse_unless_not_found"):
        assert getattr(module, name) is getattr(shape_materialize, name), name


def probe(code: int, stderr: str, stdout: str = ""):
    return subprocess.CompletedProcess(
        ["gh", "repo", "view", "o/r", "--json", "name"], code, stdout, stderr)


def test_only_exit_1_with_gh_s_not_found_words_is_absent():
    shape_materialize.refuse_unless_not_found("o/r", probe(
        1, "GraphQL: Could not resolve to a Repository with the name 'o/r'. "
           "(repository)\n"))
    for code, said in ((1, "HTTP 401: Bad credentials\n"), (1, ""),
                       (4, "GraphQL: Could not resolve to a Repository\n"),
                       (1, "\n\n"), (2, "")):
        with pytest.raises(Refusal) as refused:
            shape_materialize.refuse_unless_not_found("o/r",
                                                      probe(code, said))
        assert refused.value.code == "remote-unreadable"
        assert refused.value.detail == (
            "whether o/r already exists on GitHub cannot be told: `gh repo "
            f"view o/r --json name` exited {code}"
            + (f": {said.strip()}" if said.strip() else ""))


def test_the_refusal_quotes_gh_s_first_line_and_escapes_what_is_unprintable():
    with pytest.raises(Refusal) as refused:
        shape_materialize.refuse_unless_not_found("o/r", probe(
            1, "\n  HTTP 503: down\x1b[0m\nsecond line\n"))
    assert refused.value.detail.endswith(
        "exited 1: 'HTTP 503: down\\x1b[0m'")
    with pytest.raises(Refusal) as refused:
        shape_materialize.refuse_unless_not_found(
            "o/r", probe(1, "", "only on stdout\n"))
    assert refused.value.detail.endswith("exited 1: only on stdout")


def test_what_stands_where_a_folder_must_go(tmp_path):
    """`folder_cannot_be_made`, by kind: nothing there and a folder are
    fine; a file there or above it, and a link to nothing, are named."""
    ask = shape_materialize.folder_cannot_be_made
    assert ask(tmp_path / "a" / "b") is None
    assert ask(tmp_path) is None
    touch(tmp_path / "f")
    assert ask(tmp_path / "f") == f"{tmp_path / 'f'} is a file, not a folder"
    assert ask(tmp_path / "f" / "g" / "h") == (
        f"{tmp_path / 'f'} is a file, not a folder")
    if os.name != "nt":
        (tmp_path / "nowhere").symlink_to(tmp_path / "gone")
        assert ask(tmp_path / "nowhere" / "x") == (
            f"{tmp_path / 'nowhere'} cannot be used as a folder: No such "
            "file or directory")
        (tmp_path / "there").symlink_to(tmp_path / "a", True)
        (tmp_path / "a").mkdir()
        assert ask(tmp_path / "there" / "x") is None


def test_what_stands_where_a_working_tree_goes(tmp_path):
    ask = shape_materialize.target_in_the_way
    assert ask(tmp_path / "none") is None
    (tmp_path / "empty").mkdir()
    assert ask(tmp_path / "empty") is None
    touch(tmp_path / "full" / "x")
    assert ask(tmp_path / "full") == "is not empty"
    touch(tmp_path / "file")
    assert ask(tmp_path / "file") == "is a file, not a folder"
    if os.name != "nt":
        (tmp_path / "nowhere").symlink_to(tmp_path / "gone")
        assert ask(tmp_path / "nowhere") == (
            "cannot be used as a folder: No such file or directory")


def test_make_folder_names_the_folder_and_the_system_s_reason(tmp_path):
    touch(tmp_path / "f")
    with pytest.raises(Refusal) as refused:
        shape_materialize.make_folder("x-code", "--some-dir",
                                      tmp_path / "f" / "g")
    assert refused.value.code == "x-code"
    assert refused.value.detail == (
        f"--some-dir {tmp_path / 'f' / 'g'} cannot be made: "
        f"{mkdir_says(tmp_path / 'f' / 'g')}")
    shape_materialize.make_folder("x-code", "--d", tmp_path / "a" / "b")
    assert (tmp_path / "a" / "b").is_dir()
