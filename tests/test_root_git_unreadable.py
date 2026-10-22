# SPDX-License-Identifier: Apache-2.0
"""An assembly root whose OWN `.git` this user cannot read is named by the
doctor and by the root's two validators, and is never a root that records
no gitlink (#1146).

THE DEFECT, measured on main `038dafba` in a scaffold's recursive clone whose
`.git` is a link into a folder at mode 000, on Python 3.12.3 and under a
`sitecustomize` that answers as Python 3.14's `Path.is_file()`, `is_dir()`,
`exists()` and `is_symlink()` do, False to ANY `OSError`:

  * the doctor: `DRIFTED (2 leg(s) not at the pin)`, exit 1. Its `legs` row
    said `no gitlink recorded` of each leg, and `placement` that each leg
    `is not a git repository`: git could not read the root's index, and
    `recorded_gitlink` takes a listing git refused for none. The gitlinks
    were UNKNOWN, not absent. The same report on both Pythons, since the
    doctor runs each validator with `-S`, where no `sitecustomize` loads.
  * `scripts/validate-manifest.py` and `scripts/validate-pins.py`, the
    pinned copies: a `PermissionError` traceback out of `repo_shape`'s
    `find_repo_root`, exit 1, on 3.12, which the doctor's rows called a
    validator that `crashed`; under the shim `REFUSED not-a-git-repo: no .git
    found at or above <root>`, exit 2, about a root that has one.

And, measured the same way, three more roots git cannot read, which the base
also read as DRIFTED, `validate-pins.py` refusing `pin-gitlink-absent` (no
gitlink recorded at `spec`) under the lockstep remedy: a `.git` directory at
mode 000 or 444, a `.git` gitfile at mode 000, and a `.git` gitfile that names
a git directory inside a folder at mode 000.

THE RULE NOW is #430's. `.git` is `stat`ed: ENOENT, ENOTDIR, EBADF and ELOOP
(and Windows' 21, 123 and 1921) mean absent, and any other `OSError` is named
`<path>: cannot be read (<reason>)`, with the gate's advice for the cause.

  * Each validator asks every `.git` `find_repo_root` would ask, with its own
    `_is_a`, and refuses one this user cannot reach `git-repo-unreadable`,
    exit 2. `validate-pins.py`, which reads the gitlinks through git, also
    asks the first `.git` that is there what it asks a leg's (#968): a
    gitfile it cannot open, or a git directory whose `HEAD` it cannot reach,
    named by what it is. `validate-manifest.py` runs no git and asks only
    the `stat`.
  * The doctor's `legs` row says the gate's line ONCE, a FINDING with this
    doctor again as its NEXT and the gate's advice as its `why`, and keeps it
    in each leg's `gitlink_cannot_be_read`, which `drifted_reasons` does not
    count. `placement` says it too, `n/a`. The verdict is the validators'
    INVALID, never DRIFTED.

A `.git` that answers absent (a link that leads nowhere or to itself, nothing
there) is left as it was, and so is one the user can read: those rows are the
controls here.

TWO KINDS OF CASE, as `tests/test_doctor_unreadable_paths.py` (#430) has them.
The MODE cases change a real mode and run the tools as a person does; they
skip on Windows and as root (`CANNOT_RUN_AS_ROOT`), and restore the mode in a
`finally` (`mode_of`). The STAND-IN cases put the refusal in by hand, in
process, so they run everywhere: `refused_stat`, which also answers
`exists()` as Python 3.14 does, and `refusing` for another cause or a read.

A `.git` LINKED INTO A FOLDER IS NOT RESTORED TO A ROOT THAT PASSES. The legs'
own repositories under `.git/modules/` keep a `core.worktree` relative to
their real path, which the link moves, so once the mode is put back git
cannot find the legs' work trees. The mode cases that move `.git` assert the
locked state only; the readable control is the scaffold's own clone.

NOTHING HERE REACHES A NETWORK: the doctor's own fixtures, a scaffold into
local bare remotes, and the session's `gh` guard for the `machine` row.
"""

from __future__ import annotations

import errno
import os
import shutil
from pathlib import Path

import pytest

from conftest import REPO, load_without_bytecode, run_script
#: #827's stand-in for a `stat` the operating system refuses (#383).
from test_bump_leg_unopenable import refused_stat
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: #847's helpers and the gate's advice, word for word.
from test_doctor_unreadable_pin import (
    DENIED, IO_ERROR, OTHER_WHY, PERMISSION_WHY, cannot, doctored, in_process,
    refusing,
)
#: The doctor's fixtures, from the module that owns them.
from test_shape_doctor import (  # noqa: F401
    project, scaffolded_here, standard,
)
#: The gate's own advice, word for word, from the file that owns it.
from test_validate_pins_named_and_spelled import AGAIN, OTHER, PERMISSION
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it.
from test_validate_pins_unreadable_workflows_dir import mode_of

TEMPLATES = REPO / "templates" / "assembly-root" / "scripts"
CODE = "git-repo-unreadable"
#: What each gate says it reads its `.git` for.
READS = {
    "validate-manifest.py": (
        "Remediation: this validator reads the root's `.git`, which is how "
        "it finds the root, and one it cannot read is a question it cannot "
        "answer, never a pass. "),
    "validate-pins.py": (
        "Remediation: this validator reads the root's own repository, where "
        "it finds the root and each leg's gitlink, and one it cannot read is "
        "a question it cannot answer, never a pass. "),
}
GATES = pytest.mark.parametrize("gate", sorted(READS))
#: What no row may say of a root whose `.git` cannot be read.
NO_GITLINK = "no gitlink recorded"
CRASHED = "crashed"
#: A symlink a test makes, which a Windows account may not.
POSIX_LINKS = pytest.mark.skipif(
    os.name == "nt", reason="makes a symlink, which Windows may refuse")


def legs_said(line: str) -> str:
    """The `legs` row's reason for a root whose `.git` cannot be read."""
    return f"{line}, so no gitlink is read and no leg is compared with its pin"


def placement_said(line: str) -> str:
    """The `placement` row's reason for the same root."""
    return (f"{line}, so no leg's tracked paths are read and nothing was "
            "classified")


def gate_said(gate: str, line: str) -> str:
    """A validator row's reason for its own copy's refusal of the root."""
    return (f"the project's own scripts/{gate} refuses (exit 2): REFUSED "
            f"{CODE}: {line}")


def refused(gate: str, line: str, advice: str = PERMISSION) -> str:
    """The whole of a gate's stderr for a `.git` it cannot read."""
    return f"REFUSED {CODE}: {line}\n{READS[gate]}{advice}{AGAIN}\n"


def linked_into(root: Path, folder: str = "locked") -> Path:
    """Move the root's `.git` into `<folder>/projgit` beside the root and
    leave a symlink to it in its place; returns the git directory."""
    locked = root.parent / folder
    locked.mkdir()
    shutil.move(str(root / ".git"), str(locked / "projgit"))
    (root / ".git").symlink_to(Path("..") / folder / "projgit")
    return locked / "projgit"


def gitfile_into(root: Path, folder: str = "locked") -> Path:
    """Move the root's `.git` into `<folder>/projgit` beside the root and
    leave a gitfile naming it in its place; returns the git directory."""
    locked = root.parent / folder
    locked.mkdir()
    shutil.move(str(root / ".git"), str(locked / "projgit"))
    (root / ".git").write_bytes(f"gitdir: ../{folder}/projgit\n".encode())
    return locked / "projgit"


def assert_nothing_unasked_said(rows: dict) -> None:
    """No row says a gitlink is missing, or that a validator crashed."""
    for row in rows.values():
        assert NO_GITLINK not in row["reason"], row
        assert CRASHED not in row["reason"], row


def assert_legs_name(rows: dict, line: str, standard: Path,
                     root: Path) -> None:
    """The `legs` row says `line` once, as a person's to mend, and keeps it
    in each leg; `placement` says it, `n/a`."""
    legs = rows["legs"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == legs_said(line)
    assert legs["next"] == doctor_again(standard, root)
    assert legs["why"] == PERMISSION_WHY
    assert legs["detail"]["legs"] == [
        {"role": role, "path": role, "gitlink": None,
         "gitlink_cannot_be_read": line} for role in ("spec", "code")]
    placement = rows["placement"]
    assert placement["status"] == "n/a", placement
    assert placement["reason"] == placement_said(line)
    assert placement["next"] is None


@pytest.fixture(scope="module")
def gates():
    """The standard's two assembly-root validators, loaded by path."""
    return {name: load_without_bytecode(TEMPLATES / name, f"root_git_{index}")
            for index, name in enumerate(sorted(READS))}


def as_python_314(monkeypatch, refused: dict) -> None:
    """`Path.stat` raising `refused[path]` for each of those exact paths, and
    `exists()` answering as Python 3.14's does, False to ANY `OSError`: a
    `.git` this user cannot reach at ONE place in a walk, where
    `refused_stat` refuses every `.git` by name."""
    real = Path.stat

    def stat_(self, *args, **kwargs):
        error = refused.get(self)
        if error is not None:
            raise type(error)(error.errno, error.strerror, str(self))
        return real(self, *args, **kwargs)

    def exists(self, *args, **kwargs):
        try:
            self.stat(*args, **kwargs)
        except (OSError, ValueError):
            return False
        return True

    monkeypatch.setattr(Path, "stat", stat_)
    monkeypatch.setattr(Path, "exists", exists)


# --- the mode cases: a real mode, each tool run as a person runs it ----------

@CANNOT_RUN_AS_ROOT
def test_a_root_git_linked_into_a_locked_folder_is_invalid_never_drift(
        standard, project):
    """The issue's case. The base said DRIFTED, `no gitlink recorded` of each
    leg, and that both validators crashed. Now the `legs` row names `.git`
    once with the cure, `placement` says it could not ask, each validator
    refuses it by name, and the verdict is theirs: INVALID."""
    linked_into(project)
    line = cannot(".git", os.strerror(errno.EACCES))
    with mode_of(project.parent, "locked", 0):
        rows, verdict = doctored(standard, project)
    assert verdict == "INVALID (manifest, pins)"
    assert_legs_name(rows, line, standard, project)
    for row_id, gate in (("manifest", "validate-manifest.py"),
                         ("pins", "validate-pins.py")):
        assert rows[row_id]["status"] == "FINDING", rows[row_id]
        assert rows[row_id]["reason"] == gate_said(gate, line)
    assert_nothing_unasked_said(rows)


@CANNOT_RUN_AS_ROOT
@GATES
def test_each_gate_refuses_a_root_git_it_cannot_reach_by_name(project,
                                                              gate):
    """Run as the project runs it, from the root with no argument: the base
    ended in a `PermissionError` traceback, exit 1. One refusal now, exit
    2, naming `.git` with the cure."""
    linked_into(project)
    with mode_of(project.parent, "locked", 0):
        result = run_script(project / "scripts" / gate, cwd=project)
    assert result.stderr == refused(
        gate, cannot(".git", os.strerror(errno.EACCES))), result.stderr
    assert result.returncode == 2
    assert result.stdout == ""


@CANNOT_RUN_AS_ROOT
@GATES
def test_a_root_git_above_the_root_given_is_named_whole(project, gate):
    """`--root` a folder inside the root, which `find_repo_root` walks up
    from: the `.git` it reaches is asked as the first one is, and named
    whole, since it is not under the folder given."""
    linked_into(project)
    dotgit = project.resolve() / ".git"
    with mode_of(project.parent, "locked", 0):
        result = run_script(project / "scripts" / gate, "--root",
                            str(project / "contracts"), cwd=project)
    assert result.stderr == refused(
        gate, cannot(str(dotgit), os.strerror(errno.EACCES))), result.stderr
    assert result.returncode == 2


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("bits", [pytest.param(0, id="git-000"),
                                  pytest.param(0o444, id="git-r--")])
def test_a_root_git_directory_this_user_cannot_search_is_named(
        standard, project, bits):
    """`.git` itself at 000 or 444: its `stat` works and its `HEAD` cannot
    be reached, and git took the root for one with no gitlink. `validate-
    pins.py` refuses `.git` by name; `validate-manifest.py`, which runs no
    git, passes; and with the mode put back the root is COMPLIANT."""
    line = cannot(".git", os.strerror(errno.EACCES))
    with mode_of(project, ".git", bits):
        rows, verdict = doctored(standard, project)
    assert verdict == "INVALID (pins)"
    assert_legs_name(rows, line, standard, project)
    assert rows["pins"]["reason"] == gate_said("validate-pins.py", line)
    assert rows["manifest"]["status"] == "ok", rows["manifest"]
    assert_nothing_unasked_said(rows)
    assert doctored(standard, project)[1] == "COMPLIANT"


@CANNOT_RUN_AS_ROOT
def test_a_gitfile_into_a_locked_folder_is_named_by_its_git_directory(
        standard, project):
    """A `.git` gitfile naming a git directory in a folder this user cannot
    search: its own `stat` works, so it is not refused as `.git`; the git
    directory it names is, whole, since it is outside the root."""
    gitdir = gitfile_into(project)
    line = cannot(str(gitdir.resolve()), os.strerror(errno.EACCES))
    with mode_of(project.parent, "locked", 0):
        rows, verdict = doctored(standard, project)
        pins = run_script(project / "scripts" / "validate-pins.py",
                          cwd=project)
        manifest = run_script(project / "scripts" / "validate-manifest.py",
                              cwd=project)
    assert verdict == "INVALID (pins)"
    assert_legs_name(rows, line, standard, project)
    assert pins.stderr == refused("validate-pins.py", line), pins.stderr
    assert pins.returncode == 2
    assert manifest.returncode == 0, manifest.stderr
    assert_nothing_unasked_said(rows)


def test_a_root_whose_git_can_be_read_is_unchanged(standard, project):
    """The control, which the base passed too: the scaffold's own clone is
    COMPLIANT, and both gates pass, run as the project runs them."""
    rows, verdict = doctored(standard, project)
    assert verdict == "COMPLIANT"
    assert rows["legs"]["status"] == "ok"
    assert rows["placement"]["status"] == "ok"
    for gate in READS:
        assert run_script(project / "scripts" / gate,
                          cwd=project).returncode == 0


# --- the stand-in cases: in process, on every platform and as root ----------

@pytest.mark.parametrize("refuse, reason, why", [
    pytest.param(lambda patch: refused_stat(patch, ".git"), DENIED,
                 PERMISSION_WHY, id="permission"),
    pytest.param(lambda patch: refusing(patch, "stat", ".git",
                                        OSError(errno.EIO, IO_ERROR)),
                 IO_ERROR, OTHER_WHY, id="io-error"),
])
def test_the_rows_name_a_refused_root_git_on_every_python(
        standard, project, monkeypatch, refuse, reason, why):
    """`.git`'s `stat` refused, as Python 3.14's `exists()` answers it: the
    `legs` row says the line once with the advice for the cause, no leg is
    drift, and `placement` says it could not ask."""
    module, ctx = in_process(standard, project)
    refuse(monkeypatch)
    line = cannot(".git", reason)
    legs = module.check_legs(ctx)
    assert legs.status == module.FINDING
    assert legs.reason == legs_said(line)
    assert legs.next_command == doctor_again(standard, project)
    assert legs.why == why
    assert [entry[module.GITLINK_UNREAD] for entry in legs.detail["legs"]] \
        == [line, line]
    assert module.drifted_reasons({"legs": legs}, {}) == []
    placement = module.check_placement(ctx)
    assert placement.status == module.NA
    assert placement.reason == placement_said(line)


def moved_out(root: Path) -> None:
    """The root's `.git` moved to `elsewhere/projgit` beside it, and a
    gitfile naming it in its place."""
    gitfile_into(root, "elsewhere")


def moved_in(root: Path) -> None:
    """The root's `.git` renamed `.gitdir`, a folder inside the root, and a
    gitfile naming it in its place."""
    (root / ".git").rename(root / ".gitdir")
    (root / ".git").write_bytes(b"gitdir: .gitdir\n")


@pytest.mark.parametrize("arrange, name, method, named", [
    pytest.param(lambda root: None, "HEAD", "stat", lambda root: ".git",
                 id="git-directory-head"),
    pytest.param(moved_out, ".git", "read_bytes", lambda root: ".git",
                 id="gitfile-open"),
    pytest.param(moved_out, "HEAD", "stat",
                 lambda root: str(root.resolve().parent / "elsewhere"
                                  / "projgit"),
                 id="gitfile-names-a-directory-outside"),
    pytest.param(moved_in, "HEAD", "stat", lambda root: ".gitdir",
                 id="gitfile-names-a-directory-inside"),
])
def test_the_doctor_and_the_gate_name_one_git_directory(
        standard, project, gates, monkeypatch, capsys, arrange, name,
        method, named):
    """What `.git` is or names, refused: a git directory whose `HEAD` cannot
    be reached, or a gitfile that cannot be opened. The doctor's line and
    `validate-pins.py`'s refusal are one sentence, naming the git directory
    relative to the root where it is inside it and whole where it is not."""
    arrange(project)
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, method, name,
             PermissionError(errno.EACCES, DENIED))
    line = cannot(named(project), DENIED)
    assert module.root_git_read(ctx.root)[0] == line
    assert module.check_legs(ctx).reason == legs_said(line)
    assert gates["validate-pins.py"].main(["--root", str(project)]) == 2
    assert capsys.readouterr().err == refused("validate-pins.py", line)


#: What answers absent, and what git answers for itself: the controls.
ABSENT = [
    pytest.param(lambda root: shutil.move(str(root / ".git"),
                                          str(root.parent / "kept")),
                 id="nothing-there"),
    pytest.param(lambda root: (shutil.move(str(root / ".git"),
                                           str(root.parent / "kept")),
                               (root / ".git").symlink_to("nowhere")),
                 id="link-to-nothing", marks=POSIX_LINKS),
    pytest.param(lambda root: (shutil.move(str(root / ".git"),
                                           str(root.parent / "kept")),
                               (root / ".git").symlink_to(".git")),
                 id="link-loop", marks=POSIX_LINKS),
    pytest.param(lambda root: (shutil.move(str(root / ".git"),
                                           str(root.parent / "kept")),
                               (root / ".git").write_bytes(b"no gitdir\n")),
                 id="gitfile-naming-nothing"),
    pytest.param(lambda root: (root / ".git" / "HEAD").unlink(),
                 id="git-directory-without-head"),
]


@pytest.mark.parametrize("arrange", ABSENT)
def test_what_answers_absent_is_left_to_git_as_before(
        standard, project, arrange):
    """The controls, which the base passed too: a `.git` that answers absent
    (nothing there, a link that leads nowhere or to itself), and one git
    answers for itself (a gitfile naming no directory, a git directory with
    no `HEAD`), are not a `.git` this user cannot read: neither row that
    reads the root's repository says `cannot be read`."""
    arrange(project)
    module, ctx = in_process(standard, project)
    assert "cannot be read" not in module.check_legs(ctx).reason
    assert "cannot be read" not in module.check_placement(ctx).reason


@pytest.mark.parametrize("arrange", ABSENT)
def test_the_gates_ask_nothing_more_of_what_answers_absent(project, gates,
                                                           arrange):
    """The same five, asked of each gate's own question: none is refused
    `git-repo-unreadable`, and `find_repo_root` answers for it as before."""
    arrange(project)
    for gate in gates.values():
        assert gate._refuse_an_unreadable_root(project) is None


@GATES
@pytest.mark.parametrize("failure, reason, advice", [
    pytest.param(None, DENIED, PERMISSION, id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), IO_ERROR, OTHER,
                 id="io-error"),
])
def test_each_gate_refuses_a_refused_root_git_on_every_python(
        project, gates, monkeypatch, capsys, gate, failure, reason, advice):
    """In process, where the base's 3.14 `exists()` refused `not-a-git-repo`
    over a root that has a `.git`: one refusal by name, the advice for the
    cause, exit 2."""
    if failure is None:
        refused_stat(monkeypatch, ".git")
    else:
        refusing(monkeypatch, "stat", ".git", failure)
    assert gates[gate].main(["--root", str(project)]) == 2
    seen = capsys.readouterr()
    assert seen.err == refused(gate, cannot(".git", reason), advice)
    assert seen.out == ""


@GATES
def test_a_root_git_above_the_folder_given_is_asked_and_named_whole(
        project, gates, monkeypatch, capsys, gate):
    """The walk, in process: `--root` a folder inside the root, which holds
    no `.git`, and the root's own refused. The base's 3.14 walked past it,
    to `not-a-git-repo` or to a repository above."""
    dotgit = project.resolve() / ".git"
    as_python_314(monkeypatch, {dotgit: PermissionError(errno.EACCES,
                                                        DENIED)})
    assert gates[gate].main(["--root", str(project / "contracts")]) == 2
    assert capsys.readouterr().err == refused(gate,
                                              cannot(str(dotgit), DENIED))


@GATES
def test_a_git_above_the_root_is_never_asked(project, gates, monkeypatch,
                                             capsys, gate):
    """`find_repo_root` stops at the first `.git` that is there, and so does
    the question: a `.git` above the root that cannot be read is not this
    root's, and each gate passes."""
    module_root = project.resolve()
    as_python_314(monkeypatch, {
        module_root.parent / ".git": PermissionError(errno.EACCES, DENIED)})
    assert gates[gate].main(["--root", str(project)]) == 0, \
        capsys.readouterr().err


def test_a_leg_whose_gitlink_cannot_be_read_is_never_drift(standard,
                                                           project):
    """`drifted_reasons` counts no leg that carries `gitlink_cannot_be_read`
    and still counts a leg beside it that it could read and is off its
    pin."""
    module = in_process(standard, project)[0]
    assert module.GITLINK_UNREAD == "gitlink_cannot_be_read"
    unread = {"role": "spec", "path": "spec", "gitlink": None,
              module.GITLINK_UNREAD: cannot(".git")}
    off = {"role": "code", "path": "code", "gitlink": "1" * 40,
           "head": "1" * 40, "pin": "2" * 40}
    row = module.Row("legs", "legs", module.FINDING, "x", None,
                     {"legs": [unread, dict(unread, role="code")]})
    assert module.drifted_reasons({"legs": row}, {}) == []
    row.detail["legs"] = [unread, off]
    assert module.drifted_reasons({"legs": row}, {}) == [
        "1 leg(s) not at the pin"]


def test_a_git_under_a_file_answers_absent(standard, project):
    """A name the system takes for nothing, a `.git` under a file, is no
    `.git` there, as `exists()` answered it: no line."""
    module = in_process(standard, project)[0]
    assert module.root_git_read(project / "project.yaml") is None
