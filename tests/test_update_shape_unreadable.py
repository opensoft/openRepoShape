# SPDX-License-Identifier: Apache-2.0
"""`update-shape.py`: a path this user cannot read is refused by name, and
is never read as a path that is not there (#430, slice B).

THE DEFECT. Up to Python 3.13 `Path.is_file()`, `is_dir()`, `exists()` and
`is_symlink()` raise a refused `stat`; from 3.14 they answer False to any
`OSError`, and `os.path.lexists` always has. Measured on main `50178305`, in
a scaffolded root with local remotes:

  * `scripts/` at 444: `check` and `apply --yes` ended in a traceback on
    3.12, and on 3.14 `check` called five copies `copy-missing` and `apply`
    refused `update-conflict` over copies "pinned and gone from the root";
  * `contracts/` at 000: `check` a traceback at `read_pin` on 3.12, and on
    3.14 `REFUSED update-pin-missing: ...shape-pin.yaml does not exist`,
    whose remedy is to adopt the project;
  * `.github/workflows/` at 444: a traceback, or a false `copy-missing`.

Every one of those files is there. Each cell now refuses `update-unreadable`,
`<path from the root>: cannot be read (Permission denied)`, with the remedy
`validate-pins.py`'s `_unreadable_file` gives, exit 2, on every Python.

TWO KINDS OF CASE. The MODE cases change a real mode and run the tool as a
person does, so they skip on Windows and as root (`needs_a_mode`). The
STAND-IN cases run it in process with a `stat` refused by name
(`refused_stat`, which also answers `is_file()` and the rest as 3.14 does),
or an `lstat` (`refused_lstat`), so they hold 3.14's answer on any Python,
root included. The CONTROLS hold the other half: a copy, a pin, a validator
that is not there is absent as it always was.

NOTHING HERE REACHES A NETWORK: the session's scaffold into local bare
remotes, with this checkout as `--upstream`, and `test_update_shape.py`'s
own upstream clone for the one `apply` that writes.
"""

from __future__ import annotations

import errno
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (IDENTITY_EMAIL, IDENTITY_NAME, REPO, git,
                      load_without_bytecode, run_script)
#: The skip for a mode root reads through, and the stand-in for a refused
#: `stat`, from the file that owns them (#383), as the doctor's and
#: `validate-pins.py`'s #430 tests take them.
from test_bump_leg_unopenable import needs_a_mode, refused_stat
#: A mode for the block and the old one back after it, from the file that
#: owns it.
from test_validate_pins_unreadable_workflows_dir import mode_of
#: `update-shape.py` loaded as a module, and the A -> B upstream whose B
#: changes one copy, from the file that owns them.
from test_update_shape import (  # noqa: F401
    CHANGED, root, update_shape, upstream_and_project,
)
#: Everything a rollback must put back, and the comparison that says what
#: it did not, from the file that owns them.
from test_update_shape_add_ignored import assert_same_tree, snapshot

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, load_yaml  # noqa: E402
from shape_materialize import SHAPE_REPOSITORY  # noqa: E402

UPDATE = REPO / "update-shape.py"
#: The gate whose words `update-unreadable` gives (`_unreadable_file`, #712).
GATE = REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py"
UNREADABLE = "update-unreadable"
DENIED = "Permission denied"
PIN = "contracts/shape-pin.yaml"

#: The pinned copies under `scripts/`, in the pin's order: a `scripts/` this
#: user cannot search refuses the `stat` of every one, and the first is
#: named.
SCRIPTS = ("validate-pins.py", "validate-manifest.py", "bootstrap.py",
           "repo_shape.py", "validate-repository-naming.py")

#: The words no refusal of a file that IS there may say.
ABSENT_WORDS = ("copy-missing", "does not exist", "pinned and gone",
                "pinned but absent", "SKIPPED", "Traceback")

#: #430's measured cells: where the mode goes, the mode, the names whose
#: `stat` the stand-in refuses, and the path the refusal names.
CELLS = [
    pytest.param("scripts", 0o444, SCRIPTS, "scripts/validate-pins.py",
                 id="scripts-444"),
    pytest.param("contracts", 0o000, ("shape-pin.yaml",), PIN,
                 id="contracts-000"),
    pytest.param(".github/workflows", 0o444, ("validate.yml",),
                 ".github/workflows/validate.yml", id="workflows-444"),
]


@pytest.fixture(autouse=True)
def refusals_where_capsys_reads_them(update_shape, monkeypatch):
    """`main`'s refusals, run in this process, printed to `sys.stderr` as
    it is when they are printed: `repo_shape.die` takes the stream as a
    default bound when that module was imported, which is not the one a
    test's `capsys` reads."""
    real = update_shape.die
    monkeypatch.setattr(update_shape, "die",
                        lambda exc: real(exc, stream=sys.stderr))


def cannot(named: str) -> str:
    """`validate-pins.py`'s line for a path it cannot reach or open."""
    return f"{named}: cannot be read ({DENIED})"


def args_for(command: str, project: Path, *extra: str) -> list[str]:
    """`check` or `apply --yes`, on `project`, with this checkout upstream."""
    return [command, "--root", str(project), "--upstream", str(REPO),
            *(["--yes"] if command == "apply" else []), *extra]


def run(command: str, project: Path, *extra: str) -> tuple[int, str]:
    """The tool in a subprocess: `(exit, stdout + stderr)`."""
    result = run_script(UPDATE, *args_for(command, project, *extra))
    return result.returncode, result.stdout + result.stderr


def run_here(update_shape, capsys, command: str, project: Path,
             *extra: str) -> tuple[int, str]:
    """The tool in this process, where a stand-in reaches it."""
    code = update_shape.main(args_for(command, project, *extra))
    out, err = capsys.readouterr()
    return code, out + err


def assert_named(code: int, said: str, named: str, *,
                 inside: bool = True) -> None:
    """The refusal every unreadable path gets: exit 2, `update-unreadable`
    naming it first, the permission remedy, and none of the words for a
    path that is not there."""
    assert code == 2, said
    assert f"REFUSED {UNREADABLE}: {cannot(named)}\n" in said, said
    assert "`chmod u+r` on a file, `chmod u+rx` on a directory" in said
    above = ("(and on every directory above it inside the root)" if inside
             else "(and on every directory above it)")
    assert above in said, said
    for words in ABSENT_WORDS:
        assert words not in said, said


def pin_bytes(project: Path) -> bytes:
    return (project / PIN).read_bytes()


def refused_lstat(monkeypatch, *suffixes: str) -> None:
    """`os.lstat` refused (`Permission denied`) for a path ending in any of
    `suffixes` (spelled with `/`), as for a name inside a directory this
    user may not search; and `Path.is_symlink` answering as 3.14's does,
    False to any `OSError`. `os.path.lexists` reads `os.lstat`, so it says
    False here, as it says on every Python for a refused one."""
    real = os.lstat

    def refusing(path, *args, **kwargs):
        if any(Path(os.fspath(path)).as_posix().endswith("/" + suffix)
               for suffix in suffixes):
            raise PermissionError(errno.EACCES, DENIED, os.fspath(path))
        return real(path, *args, **kwargs)

    def is_symlink(self):
        try:
            return stat.S_ISLNK(os.lstat(self).st_mode)
        except (OSError, ValueError):
            return False

    monkeypatch.setattr(os, "lstat", refusing)
    monkeypatch.setattr(Path, "is_symlink", is_symlink)


# --- the measured cells, under a real mode ----------------------------------

@needs_a_mode
@pytest.mark.parametrize("relative, mode, _names, named", CELLS)
def test_check_names_what_it_cannot_read(project, relative, mode, _names,
                                         named):
    """THE ISSUE'S CELLS, `check`: a traceback on 3.12 and `copy-missing` or
    `update-pin-missing` on 3.14, over files that are there."""
    with mode_of(project, relative, mode):
        code, said = run("check", project)
    assert_named(code, said, named)


@needs_a_mode
def test_apply_names_what_it_cannot_read_and_writes_nothing(project):
    """`scripts/` at 444, `apply --yes`: it was a traceback, or on 3.14
    `update-conflict` asking for copies to be put back from history. The
    refusal comes from `prepare`, before the first write."""
    before = pin_bytes(project)
    with mode_of(project, "scripts", 0o444):
        code, said = run("apply", project)
    assert_named(code, said, "scripts/validate-pins.py")
    assert "update-conflict" not in said
    assert pin_bytes(project) == before


# --- the measured cells, as Python 3.14 answers them (in process) -----------

@pytest.mark.parametrize("command", ["check", "apply"])
@pytest.mark.parametrize("_relative, _mode, names, named", CELLS)
def test_a_refused_stat_is_named_on_every_python(
        update_shape, project, capsys, monkeypatch, command, _relative,
        _mode, names, named):
    """The same cells with each file's `stat` refused, and `is_file()`
    answering False to it as 3.14's does: a tool that leans on `is_file()`
    calls the files missing here, on any Python."""
    before = pin_bytes(project)
    refused_stat(monkeypatch, *names)
    code, said = run_here(update_shape, capsys, command, project)
    assert_named(code, said, named)
    assert pin_bytes(project) == before


@pytest.fixture
def temporaries(update_shape, monkeypatch, tmp_path):
    """Every upstream a run opens, handed a temporary directory of its own
    to close, as `open_upstream` hands the bare clone it makes of the pin's
    `owner/repo`: `--upstream` here is this checkout, which has none. The
    list holds the directories, for a test to ask whether each is gone."""
    real = update_shape.open_upstream
    made: list[Path] = []

    def opening(spec):
        upstream = real(spec)
        temporary = tmp_path / f"openreposhape-upstream-{len(made)}"
        temporary.mkdir()
        (temporary / "HEAD").write_bytes(b"ref: refs/heads/main\n")
        upstream._temporary = temporary
        made.append(temporary)
        return upstream

    monkeypatch.setattr(update_shape, "open_upstream", opening)
    return made


@pytest.mark.parametrize("command", ["check", "apply"])
def test_a_read_refused_in_prepare_closes_the_upstream(
        update_shape, project, capsys, monkeypatch, temporaries, command):
    """`prepare` closed the upstream it had opened on a `Refusal` alone, so
    a refused `stat` out of `classify` went on to `main`'s refusal past it,
    and the bare clone of the pin's `owner/repo` stayed in the temporary
    directory, one per run (review of PR #976). It is closed on either."""
    refused_stat(monkeypatch, *SCRIPTS)
    code, said = run_here(update_shape, capsys, command, project)
    assert_named(code, said, "scripts/validate-pins.py")
    assert len(temporaries) == 1, temporaries
    assert not os.path.lexists(temporaries[0]), said


# --- the controls: what is not there is absent, as it always was ------------

@pytest.mark.parametrize("as_314", [False, True], ids=["this-python",
                                                         "as-3.14"])
def test_a_copy_that_is_gone_is_still_copy_missing(
        update_shape, project, capsys, monkeypatch, as_314):
    """A pinned copy that is NOT there is `copy-missing`, and `apply`'s
    `update-conflict`, as before, with 3.14's `is_file()` or this Python's."""
    (project / "scripts" / "bootstrap.py").unlink()
    if as_314:
        refused_stat(monkeypatch, "nothing-is-called-this")
    code, said = run_here(update_shape, capsys, "check", project)
    assert code == 1, said
    assert "  copy-missing       scripts/bootstrap.py\n" in said, said
    assert UNREADABLE not in said
    code, said = run_here(update_shape, capsys, "apply", project)
    assert code == 2, said
    assert "REFUSED update-conflict: " in said, said
    assert "scripts/bootstrap.py is pinned and gone from the root" in said
    assert UNREADABLE not in said


def test_a_pin_that_is_gone_is_still_missing(update_shape, project, capsys,
                                             monkeypatch):
    (project / PIN).unlink()
    refused_stat(monkeypatch, "nothing-is-called-this")
    code, said = run_here(update_shape, capsys, "check", project)
    assert code == 2, said
    assert "REFUSED update-pin-missing: " in said
    assert "shape-pin.yaml does not exist" in said
    assert UNREADABLE not in said


def test_a_readable_root_has_nothing_to_do(project):
    code, said = run("check", project)
    assert code == 0, said
    assert "nothing to do" in said


# --- the other reads `check` and `apply` make --------------------------------

@needs_a_mode
def test_a_pin_this_user_cannot_open_is_named_from_the_root(project):
    """A pin at mode 000 in a readable `contracts/`: its `stat` answers, and
    its read is refused. `load_yaml`'s `yaml-unreadable` named the absolute
    path and gave no remedy; the read's `OSError` is raised out of
    `read_pin`, as a refused `stat` is, and refused the same way."""
    with mode_of(project, PIN, 0):
        code, said = run("check", project)
    assert_named(code, said, PIN)
    assert "yaml-unreadable" not in said


@needs_a_mode
def test_a_copy_this_user_cannot_open_is_named(project):
    """A copy at mode 000 in a readable directory: `is_file()` says yes on
    every Python, and the read of its bytes raised out of `main` as a
    traceback, exit 1, on every Python."""
    with mode_of(project, "scripts/bootstrap.py", 0):
        code, said = run("check", project)
    assert_named(code, said, "scripts/bootstrap.py")


@pytest.mark.parametrize("method, name, named", [
    pytest.param("read_text", "shape-pin.yaml", PIN, id="the-pin"),
    pytest.param("read_bytes", "bootstrap.py", "scripts/bootstrap.py",
                 id="a-copy"),
])
def test_a_read_refused_is_named_on_every_python(
        update_shape, project, capsys, monkeypatch, method, name, named):
    """The two cases above in this process, the read refused by hand: the
    pin's (`load_yaml`'s `read_text`) and a copy's (`read_bytes`)."""
    real = getattr(Path, method)

    def refusing(self, *args, **kwargs):
        if self.name == name:
            raise PermissionError(errno.EACCES, DENIED, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, refusing)
    code, said = run_here(update_shape, capsys, "check", project)
    assert_named(code, said, named)


@pytest.fixture(scope="module")
def gate():
    """`validate-pins.py` of this working tree, loaded by path with no
    bytecode written beside it, and `sys.path` put back after it puts its
    own `scripts/` on it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "path", list(sys.path))
        return load_without_bytecode(GATE, "gate_update_shape_unreadable")


@pytest.mark.parametrize("cause, reason", [
    pytest.param(errno.EIO, "Input/output error", id="EIO"),
    pytest.param(errno.ENAMETOOLONG, "File name too long",
                 id="ENAMETOOLONG"),
])
def test_a_read_refused_for_another_reason_gets_the_gates_other_advice(
        update_shape, project, gate, cause, reason):
    """A read refused, and not for a permission: `chmod` cannot help it, so
    the remedy is the gate's `OTHER_REASON`, word for word, and never the
    permission advice every other test here reads (review of PR #976)."""
    refusal = update_shape.unreadable_refusal(
        project, OSError(cause, reason, str(project / "scripts" / "x.py")))
    assert refusal.code == UNREADABLE
    assert refusal.detail == f"scripts/x.py: cannot be read ({reason})"
    assert refusal.remediation.endswith(
        f"never an absence. {gate.OTHER_REASON}{gate.RUN_AGAIN}"), \
        refusal.remediation
    assert "chmod" not in refusal.remediation


# --- the root itself ---------------------------------------------------------

@needs_a_mode
def test_a_root_this_user_cannot_search_is_named_in_full(project):
    """A root at 600: it is a directory, and nothing in it can be reached.
    It was asked first as `root_kind`'s `family.yaml`, a file a project has
    not got; it is named whole, as the directory it is, and the remedy does
    not say "inside the root" of the root."""
    with mode_of(project, ".", 0o600):
        code, said = run("check", project)
    assert_named(code, said, str(project.resolve()), inside=False)
    assert "family.yaml" not in said


@needs_a_mode
def test_a_root_under_a_folder_this_user_cannot_search_is_not_missing(
        project):
    """The root's own `stat` refused, its parent at 000: it was
    `update-root-missing`, "is not a directory", on 3.14."""
    with mode_of(project.parent, ".", 0):
        code, said = run("check", project)
    assert_named(code, said, str(project), inside=False)
    assert "update-root-missing" not in said


def test_a_root_whose_stat_is_refused_is_not_missing(update_shape, project,
                                                     capsys, monkeypatch):
    refused_stat(monkeypatch, project.name)
    code, said = run_here(update_shape, capsys, "check", project)
    assert_named(code, said, str(project.resolve()), inside=False)
    assert "update-root-missing" not in said


@pytest.mark.parametrize("present, refused", [
    pytest.param((), "family.yaml", id="the-family-manifest"),
    pytest.param(("family.yaml",), "project.yaml", id="the-project-manifest"),
])
def test_root_kind_raises_a_refused_stat(update_shape, tmp_path, monkeypatch,
                                         present, refused):
    """`root_kind` asks both manifests as `validate-pins.py` asks a file:
    a refused `stat` is raised, never read as "no such manifest", which
    would pick the other kind of root."""
    for name in present:
        (tmp_path / name).write_text("kind: family\n", encoding="utf-8")
    refused_stat(monkeypatch, refused)
    with pytest.raises(PermissionError):
        update_shape.root_kind(tmp_path)


def test_root_kind_still_reads_what_is_there(update_shape, tmp_path):
    assert update_shape.root_kind(tmp_path) is update_shape.PROJECT_KIND
    (tmp_path / "family.yaml").write_text("kind: family\n", encoding="utf-8")
    assert update_shape.root_kind(tmp_path) is update_shape.FAMILY_KIND


# --- `--upstream` ------------------------------------------------------------

@needs_a_mode
@pytest.mark.parametrize("locked, named", [
    pytest.param("folder", "folder/shape", id="its-parent-at-000"),
    pytest.param("folder/shape", "folder/shape/.git", id="itself-at-000"),
])
def test_an_upstream_this_user_cannot_read_is_named(project, tmp_path,
                                                    locked, named):
    """`--upstream` under a folder this user cannot search was, on 3.14,
    "neither a path on this machine nor an `owner/repo` name" (and a
    relative `a/b` spelling would have been cloned from github.com); one it
    cannot search itself was `update-upstream-not-a-repo`. Named whole: it
    is not inside the root."""
    (tmp_path / "folder" / "shape").mkdir(parents=True)
    with mode_of(tmp_path, locked, 0):
        result = run_script(UPDATE, "check", "--root", str(project),
                            "--upstream", str(tmp_path / "folder" / "shape"))
    assert_named(result.returncode, result.stdout + result.stderr,
                 str(tmp_path.resolve() / named), inside=False)


@pytest.mark.parametrize("refused", [
    pytest.param("shape", id="the-path-itself"),
    pytest.param(".git", id="its-git"),
    pytest.param("HEAD", id="a-bare-repositorys-head"),
])
def test_open_upstream_raises_a_refused_stat(update_shape, tmp_path,
                                             monkeypatch, refused):
    """Each of `open_upstream`'s three questions raises a refused `stat`,
    where 3.14's answer refused `update-upstream-unresolvable` or
    `update-upstream-not-a-repo` of a path that is there. `.git` is asked
    first and a bare repository's `HEAD` only where it is not there."""
    shape = tmp_path / "shape"
    shape.mkdir()
    refused_stat(monkeypatch, refused)
    with pytest.raises(PermissionError):
        update_shape.open_upstream(str(shape))


# --- a merged-away copy, and an addition -------------------------------------

def merged_root(tmp_path: Path, *, collision: bool) -> Path:
    """A root holding `Makefile`, and `shape/Makefile` where `collision`."""
    (tmp_path / "shape").mkdir()
    (tmp_path / "Makefile").write_text("all:\n", encoding="utf-8")
    if collision:
        (tmp_path / "shape" / "Makefile").write_text("all:\n",
                                                     encoding="utf-8")
    return tmp_path


@needs_a_mode
def test_a_shape_folder_this_user_cannot_search_is_no_merge(update_shape,
                                                            tmp_path):
    """`os.path.lexists` answers False to a refused `lstat` on EVERY Python,
    so a `shape/` this user cannot search held "nothing" at `shape/Makefile`,
    the row read `merged-away`, and `apply` would have dropped its pin row."""
    root = merged_root(tmp_path, collision=True)
    with mode_of(root, "shape", 0), pytest.raises(PermissionError):
        update_shape.merged_into(root, "shape/Makefile")


@pytest.mark.parametrize("collision, refuse", [
    pytest.param(True, "lstat", id="the-copy"),
    pytest.param(False, "stat", id="the-file-it-was-merged-into"),
])
def test_merged_into_raises_a_refused_read(update_shape, tmp_path,
                                           monkeypatch, collision, refuse):
    root = merged_root(tmp_path, collision=collision)
    if refuse == "lstat":
        refused_lstat(monkeypatch, "shape/Makefile")
    else:
        refused_stat(monkeypatch, "Makefile")
    with pytest.raises(PermissionError):
        update_shape.merged_into(root, "shape/Makefile")


def test_merged_into_still_reads_what_is_there(update_shape, tmp_path):
    root = merged_root(tmp_path, collision=False)
    assert update_shape.merged_into(root, "shape/Makefile") == "Makefile"
    (root / "shape" / "Makefile").write_text("all:\n", encoding="utf-8")
    assert update_shape.merged_into(root, "shape/Makefile") is None


class AddingUpstream:
    """An upstream whose copy lists, at any commit, add `docs/new.md`."""

    def blob(self, _rev: str, path: str) -> bytes | None:
        if path == "scripts/shape_materialize.py":
            return (b'COPIED_VERBATIM = ("docs/new.md",)\n'
                    b'COPIED_FROM_SHAPE = ()\nEXECUTABLE = ()\n')
        if path == "templates/assembly-root/docs/new.md":
            return b"the standard's\n"
        return None


def additions(update_shape, root: Path) -> list[tuple[str, bool]]:
    return [(add.path, add.present) for add in update_shape.find_additions(
        root, [], AddingUpstream(), "0" * 40, update_shape.PROJECT_KIND)]


@needs_a_mode
def test_an_addition_under_a_folder_this_user_cannot_search_is_named(
        update_shape, tmp_path):
    """The root HAS `docs/new.md`, in a `docs/` at 000: it was `present`
    False (`os.path.lexists`), so `check` offered `--add` over the
    project's own file."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "new.md").write_text("ours\n", encoding="utf-8")
    with mode_of(tmp_path, "docs", 0), pytest.raises(PermissionError):
        additions(update_shape, tmp_path)


def test_an_addition_whose_lstat_is_refused_is_raised(update_shape, tmp_path,
                                                      monkeypatch):
    (tmp_path / "docs").mkdir()
    refused_lstat(monkeypatch, "docs/new.md")
    with pytest.raises(PermissionError):
        additions(update_shape, tmp_path)


def test_an_addition_still_reads_what_is_there(update_shape, tmp_path):
    assert additions(update_shape, tmp_path) == [("docs/new.md", False)]
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "new.md").write_text("ours\n", encoding="utf-8")
    assert additions(update_shape, tmp_path) == [("docs/new.md", True)]


# --- the README's line, a reading that never raises --------------------------

@pytest.mark.parametrize("refuse", ["stat", "lstat"])
def test_a_readme_this_user_cannot_stat_is_unreadable_not_absent(
        update_shape, project, monkeypatch, refuse):
    """`README.md`'s `stat` or `lstat` refused: 3.12 raised out of a
    classification that promises never to, and 3.14 answered `absent`. It
    is `unreadable`, with the system's reason, which `check` prints and
    `apply` leaves alone: prose, so no exit code moves."""
    if refuse == "stat":
        refused_stat(monkeypatch, "README.md")
    else:
        refused_lstat(monkeypatch, "README.md")
    line = update_shape.ReadmeShapeLine(project, SHAPE_REPOSITORY, "0" * 40)
    assert line.state == "unreadable"
    assert line.verdict == f"unreadable (README.md is not readable — {DENIED})"


# --- `apply`'s validators, and a read refused after the first write ----------

def test_a_validator_whose_stat_is_refused_is_not_skipped(update_shape,
                                                          project, capsys,
                                                          monkeypatch):
    refused_stat(monkeypatch, "validate-pins.py")
    with pytest.raises(Refusal) as raised:
        update_shape.run_validator(project, "scripts/validate-pins.py")
    assert raised.value.code == UNREADABLE
    assert raised.value.detail == cannot("scripts/validate-pins.py")
    assert "SKIPPED" not in capsys.readouterr().out


def test_a_validator_that_is_not_there_is_still_skipped(update_shape,
                                                        project, capsys):
    assert update_shape.run_validator(project, "scripts/not-there.py") == 0
    assert "  scripts/not-there.py is absent; SKIPPED\n" in \
        capsys.readouterr().out


def apply_b(update_shape, root: Path, project: dict) -> int:
    """`apply --at B --yes` in this process: B changes `CHANGED`, so the
    run writes a copy, the pin and the manifest before its validators."""
    return update_shape.main(["apply", "--root", str(root), "--yes",
                              "--upstream", str(project["upstream"]),
                              "--at", project["b"]])


def assert_rolled_back(said: str, root: Path, project: dict,
                       changed: bytes) -> None:
    assert f"REFUSED {UNREADABLE}: {cannot('scripts/validate-pins.py')}\n" \
        in said, said
    assert ("ROLLED BACK: every byte this command wrote has been put back, "
            "and the tree is exactly as it was:") in said, said
    assert "SKIPPED" not in said
    assert load_yaml(root / PIN)["commit"].lower() == project["a"]
    assert (root / CHANGED).read_bytes() == changed


def test_a_validator_unreadable_after_the_writes_rolls_them_back(
        update_shape, root, upstream_and_project, capsys, monkeypatch):
    """MID-RUN: the copies, the pin and the manifest are written, and then
    the validator's `stat` is refused. 3.14's `is_file()` said "absent;
    SKIPPED" and the run went on without its gate; 3.12's raise left the
    writes behind a traceback. It is a refusal, and every byte goes back."""
    changed = (root / CHANGED).read_bytes()
    real = update_shape._refuse_red_validators

    def turning_unreadable(where, kind):
        refused_stat(monkeypatch, "validate-pins.py")
        return real(where, kind)

    monkeypatch.setattr(update_shape, "_refuse_red_validators",
                        turning_unreadable)
    assert apply_b(update_shape, root, upstream_and_project) == 2
    out, err = capsys.readouterr()
    assert "  copied   scripts/validate-manifest.py" in out
    assert_rolled_back(out + err, root, upstream_and_project, changed)


def test_any_read_refused_after_the_writes_rolls_them_back(
        update_shape, root, upstream_and_project, capsys, monkeypatch):
    """MID-RUN, a refused read raised as an `OSError` by whatever reads
    after the first write: `apply` rolls back on a `Refusal` alone, so it
    is made one, `update-unreadable`, and the rollback says what it put
    back."""
    changed = (root / CHANGED).read_bytes()

    def refusing(where, _kind):
        raise PermissionError(errno.EACCES, DENIED,
                              str(where / "scripts" / "validate-pins.py"))

    monkeypatch.setattr(update_shape, "_refuse_red_validators", refusing)
    assert apply_b(update_shape, root, upstream_and_project) == 2
    out, err = capsys.readouterr()
    assert_rolled_back(out + err, root, upstream_and_project, changed)


# --- any other `OSError` after the first write (#1173) -----------------------

#: The `OSError`s after the first write that no refusal can name, each made
#: of the root the run is in: a file gone between its `stat` and its read,
#: and two that name no path, a flush into a pipe nobody reads any more and
#: an `EIO`. `unreadable_refusal` answers None to all three.
UNNAMED = [
    pytest.param(lambda where: FileNotFoundError(
        errno.ENOENT, "No such file or directory",
        str(where / "scripts" / "validate-pins.py")), id="a-file-gone"),
    pytest.param(lambda _where: BrokenPipeError(errno.EPIPE, "Broken pipe"),
                 id="a-broken-pipe"),
    pytest.param(lambda _where: OSError(errno.EIO, "Input/output error"),
                 id="EIO-naming-no-path"),
]

#: What stderr says first when every byte `apply --at B` wrote went back:
#: the copy, then the pin and the manifest, in the order they were written.
ROLLED_BACK = (
    "ROLLED BACK: every byte this command wrote has been put back, and the "
    "tree is exactly as it was:\n"
    + "".join(f"    restored  {path}\n"
              for path in (CHANGED, PIN, "project.yaml")))


@pytest.mark.parametrize("error", UNNAMED)
def test_any_oserror_after_the_writes_rolls_them_back_and_is_raised(
        update_shape, root, upstream_and_project, capsys, monkeypatch, error):
    """MID-RUN, an `OSError` no refusal can name (#1173): it was raised as
    it was, with the copy, the pin and the manifest left written behind the
    traceback. Every byte goes back, stderr says which, and the SAME error
    is raised: the traceback is the answer to an error the tool cannot
    name, over a tree as it was."""
    before = snapshot(root, {})
    raised: list[OSError] = []

    def failing(where, _kind):
        raised.append(error(where))
        raise raised[0]

    monkeypatch.setattr(update_shape, "_refuse_red_validators", failing)
    with pytest.raises(OSError) as escaped:
        apply_b(update_shape, root, upstream_and_project)
    assert escaped.value is raised[0]
    out, err = capsys.readouterr()
    assert f"  copied   {CHANGED}" in out, out
    assert err == ROLLED_BACK, err
    assert_same_tree(before, snapshot(root, {}))


def test_a_stdout_nobody_reads_is_rolled_back_under_its_broken_pipe(
        root, upstream_and_project):
    """THE TOOL AS A PERSON RUNS IT, no stand-in (#1173): its stdout a pipe
    whose reader is gone, as `apply --yes | head -1` leaves it once `head`
    has its line. The flush before the root's validators raised over the
    written tree. It still raises, over a tree as it was, and what went
    back reaches stderr, above the traceback, though stdout will not take
    the flush that comes first."""
    before = snapshot(root, {})
    reader, writer = os.pipe()
    os.close(reader)
    try:
        proc = subprocess.run(
            [sys.executable, str(UPDATE), "apply", "--root", str(root),
             "--yes", "--upstream", str(upstream_and_project["upstream"]),
             "--at", upstream_and_project["b"]],
            stdin=subprocess.DEVNULL, stdout=writer, stderr=subprocess.PIPE,
            text=True, check=False, env={**os.environ, "LANES_LANE": ""})
    finally:
        os.close(writer)
    assert proc.returncode != 0, proc.stderr
    assert proc.stderr.startswith(
        ROLLED_BACK + "Traceback (most recent call last):\n"), proc.stderr
    assert_same_tree(before, snapshot(root, {}))


def test_an_oserror_before_the_first_write_is_raised_and_says_nothing(
        update_shape, root, upstream_and_project, capsys, monkeypatch):
    """The other side: before the first write there is nothing to put
    back, so the error is raised as it always was, and stderr says
    nothing at all."""
    before = snapshot(root, {})
    error = OSError(errno.EIO, "Input/output error")

    def failing(*_args):
        raise error

    monkeypatch.setattr(update_shape, "_read_readme", failing)
    with pytest.raises(OSError) as escaped:
        apply_b(update_shape, root, upstream_and_project)
    assert escaped.value is error
    assert capsys.readouterr().err == ""
    assert_same_tree(before, snapshot(root, {}))


def test_an_oserror_after_the_commit_puts_nothing_back(
        update_shape, root, upstream_and_project, capsys, monkeypatch):
    """And after the commit, which IS the result (`Rollback.land`): the
    error is raised as it always was, nothing is said, and the commit and
    its tree stand."""
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", IDENTITY_NAME)
        monkeypatch.setenv(f"GIT_{role}_EMAIL", IDENTITY_EMAIL)
    error = OSError(errno.EIO, "Input/output error")

    def failing(*_args, **_kwargs):
        raise error

    monkeypatch.setattr(update_shape, "next_line", failing)
    with pytest.raises(OSError) as escaped:
        update_shape.main(["apply", "--root", str(root), "--yes",
                           "--upstream", str(upstream_and_project["upstream"]),
                           "--at", upstream_and_project["b"],
                           "--branch", "shape-at-b"])
    assert escaped.value is error
    out, err = capsys.readouterr()
    assert "  committed on shape-at-b: " in out, out
    assert err == ""
    assert load_yaml(root / PIN)["commit"].lower() == \
        upstream_and_project["b"]
    assert git("status", "--porcelain", cwd=root).stdout == ""


def test_a_rollback_that_cannot_stat_what_it_made_says_so(update_shape,
                                                          tmp_path,
                                                          monkeypatch):
    """An `--add` file whose `stat` is refused when the rollback comes for
    it: 3.14's `exists()` said False, nothing was removed or listed, and the
    rollback said the tree was "exactly as it was"."""
    ledger = update_shape.Rollback(tmp_path)
    ledger.write_added(tmp_path / "docs" / "new.md", b"x\n", False)
    refused_stat(monkeypatch, "new.md")
    said = ledger.undo()
    assert said.startswith("ROLLED BACK IN PART: the tree is NOT as it was.")
    assert (f"file      docs/new.md, written by --add, was not removed "
            f"({DENIED}): rm -- {tmp_path / 'docs' / 'new.md'}") in said


def test_an_add_file_gone_before_the_rollback_is_not_listed(update_shape,
                                                             tmp_path):
    """An `--add` file something else took away between the write and the
    rollback, a validator or the operator: there is nothing left to remove,
    so nothing is listed as left, and the directory made for it goes as it
    would have. An `unlink` asked regardless listed it `was not removed (No
    such file or directory)` under "the tree is NOT as it was" (review of
    PR #976)."""
    ledger = update_shape.Rollback(tmp_path)
    ledger.write_added(tmp_path / "docs" / "new.md", b"x\n", False)
    (tmp_path / "docs" / "new.md").unlink()
    said = ledger.undo()
    assert said.startswith("ROLLED BACK: every byte this command wrote has "
                           "been put back"), said
    assert "    removed   docs/ (made to hold an --add file)" in said, said
    assert "new.md" not in said, said
