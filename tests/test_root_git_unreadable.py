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
    count. The verdict is never DRIFTED.
  * `placement` gives that line to each leg git cannot read because of it,
    a leg whose `.git` leads under the root's, and says it once, `n/a`,
    where that is every leg. It still audits a leg whose own repository git
    reads (r1147's S2): a path in the wrong leg there is still MISPLACED,
    the verdict the ladder puts over the validators' INVALID.

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
import stat
import sys
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
    project, scaffolded_here, stage, standard,
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
#: A folder name holding an ESC, which a line names as `repr` spells it.
UNPRINTABLE = ".git\x1bdir"
#: A name with a control character in it, which Windows refuses.
POSIX_NAMES = pytest.mark.skipif(
    os.name == "nt", reason="a control character in a name, which Windows "
                            "refuses")


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
    in each leg, whose entry has every key a leg's has (r1147's N7);
    `placement` says it, `n/a`, and keeps it in each leg it could not read
    (N2)."""
    legs = rows["legs"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == legs_said(line)
    assert legs["next"] == doctor_again(standard, root)
    assert legs["why"] == PERMISSION_WHY
    assert legs["detail"]["legs"] == [
        {"role": role, "path": role, "pin": None, "gitlink": None,
         "populated": None, "head": None, "own_git": None, "unborn": None,
         "gitlink_cannot_be_read": line} for role in ("spec", "code")]
    placement = rows["placement"]
    assert placement["status"] == "n/a", placement
    assert placement["reason"] == placement_said(line)
    assert placement["next"] is None
    assert placement["detail"]["legs"] == [
        {"role": role, "path": role, "state": line,
         "gitlink_cannot_be_read": line} for role in ("spec", "code")]
    assert placement["detail"]["counts"]["unread_legs"] == 2


@pytest.fixture(scope="module")
def gates():
    """The standard's two assembly-root validators, loaded by path, and
    `sys.path` put back after: each puts its own `scripts/` on it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "path", list(sys.path))
        return {name: load_without_bytecode(TEMPLATES / name,
                                            f"root_git_{index}")
                for index, name in enumerate(sorted(READS))}


def as_python_314(monkeypatch, failures: dict) -> None:
    """`Path.stat` raising `failures[path]` for each of those exact paths,
    and `is_file()`, `is_dir()` and `exists()` answering as Python 3.14's
    do, False to ANY `OSError`: a `.git` this user cannot reach at ONE place,
    where `refused_stat` refuses every `.git` by name, the root's own among
    them."""
    real = Path.stat

    def stat_(self, *args, **kwargs):
        error = failures.get(self)
        if error is not None:
            raise type(error)(error.errno, error.strerror, str(self))
        return real(self, *args, **kwargs)

    def answering(kind):
        def answer(self, *args, **kwargs):
            try:
                return kind(self.stat(*args, **kwargs).st_mode)
            except (OSError, ValueError):
                return False
        return answer

    monkeypatch.setattr(Path, "stat", stat_)
    monkeypatch.setattr(Path, "is_file", answering(stat.S_ISREG))
    monkeypatch.setattr(Path, "is_dir", answering(stat.S_ISDIR))
    monkeypatch.setattr(Path, "exists", answering(lambda _mode: True))


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


def own_repository(root: Path, leg: str = "spec") -> None:
    """The leg's repository moved out of the root's `.git/modules/` into a
    `.git` directory of its own, without the `core.worktree` its old place
    needed: a leg git reads without the root's `.git`."""
    mount = root / leg
    (mount / ".git").unlink()
    shutil.move(str(root / ".git" / "modules" / leg), str(mount / ".git"))
    config = mount / ".git" / "config"
    config.write_text("".join(
        line for line in config.read_text(encoding="utf-8").splitlines(True)
        if not line.strip().startswith("worktree =")), encoding="utf-8")


@CANNOT_RUN_AS_ROOT
def test_placement_still_audits_a_leg_whose_own_repository_it_can_read(
        standard, project):
    """r1147's S2. `.git` at 000, and the spec leg's repository in a `.git`
    directory of its own, holding a path the policy puts in the root. The
    base said this path in a FINDING beside a DRIFTED verdict. A `placement`
    that declined every leg once the root's `.git` could not be read hid it,
    and the verdict was `INVALID (pins)`. It audits the leg git reads and
    names the path, the code leg it could not read is given the root's
    line, and the verdict is MISPLACED, which the ladder puts over the
    validators' INVALID, beside the `legs` and `pins` rows naming `.git`."""
    own_repository(project)
    stage(project / "spec", ".specify/memory.md", "misplaced\n")
    line = cannot(".git", os.strerror(errno.EACCES))
    with mode_of(project, ".git", 0):
        rows, verdict = doctored(standard, project)
    assert verdict == "MISPLACED (1 path)"
    assert rows["legs"]["status"] == "FINDING", rows["legs"]
    assert rows["legs"]["reason"] == legs_said(line)
    assert rows["pins"]["reason"] == gate_said("validate-pins.py", line)
    placement = rows["placement"]
    assert placement["status"] == "FINDING", placement
    assert placement["reason"].startswith(
        "1 path(s) sit in a leg the policy puts elsewhere: spec/.specify/: "
        "root by rule root-spec-kit"), placement["reason"]
    assert placement["reason"].endswith(
        f"; code: read through the root's repository, and {line}]")
    assert [entry["path"] for entry in placement["detail"]["misplaced"]] \
        == ["spec/.specify/"]
    spec, code = placement["detail"]["legs"]
    assert spec["state"] == "audited", spec
    assert code == {"role": "code", "path": "code", "state": line,
                    "gitlink_cannot_be_read": line}
    assert_nothing_unasked_said(rows)


@CANNOT_RUN_AS_ROOT
def test_a_leg_with_no_git_of_its_own_keeps_gits_answer(standard, project):
    """`.git` at 000, and the spec leg left with no `.git` of its own: it is
    not its own repository whatever the root's `.git` says, so it keeps
    git's answer, and only the code leg, read through the root's
    repository, is given the root's line."""
    (project / "spec" / ".git").unlink()
    line = cannot(".git", os.strerror(errno.EACCES))
    with mode_of(project, ".git", 0):
        rows, verdict = doctored(standard, project)
    assert verdict == "INVALID (pins)"
    placement = rows["placement"]
    assert placement["status"] == "n/a", placement
    assert placement["reason"] == (
        "no leg could be read, so nothing was classified: spec: it is not a "
        "git repository, so it has no tracked paths of its own to read; "
        f"code: read through the root's repository, and {line}")


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
    """Every `.git`'s `stat` refused, the root's and each leg's, as Python
    3.14's `exists()` answers it: the `legs` row says the root's line once
    with the advice for the cause, and no leg is drift. `placement` asks
    each leg's own `.git` before any git runs, and names it: that, not the
    root's, is what kept the leg from being read."""
    module, ctx = in_process(standard, project)
    refuse(monkeypatch)
    line = cannot(".git", reason)
    legs = module.check_legs(ctx)
    assert legs.status == module.FINDING
    assert legs.reason == legs_said(line)
    assert legs.next_command == doctor_again(standard, project)
    assert legs.why == why
    assert legs.detail["legs"] == [
        {"role": role, "path": role, "pin": None, "gitlink": None,
         "populated": None, "head": None, "own_git": None, "unborn": None,
         module.GITLINK_UNREAD: line} for role in ("spec", "code")]
    assert module.drifted_reasons({"legs": legs}, {}) == []
    placement = module.check_placement(ctx)
    assert placement.status == module.NA
    assert placement.reason == (
        "no leg could be read, so nothing was classified: "
        f"{cannot('spec/.git', reason)}; {cannot('code/.git', reason)}")


def moved_out(root: Path) -> None:
    """The root's `.git` moved to `elsewhere/projgit` beside it, and a
    gitfile naming it in its place."""
    gitfile_into(root, "elsewhere")


def moved_in(root: Path, folder: str = ".gitdir",
             ending: bytes = b"\n") -> None:
    """The root's `.git` renamed `folder`, a folder inside the root, and a
    gitfile naming it in its place, its line ending in `ending`."""
    (root / ".git").rename(root / folder)
    (root / ".git").write_bytes(b"gitdir: " + os.fsencode(folder) + ending)


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
    pytest.param(lambda root: moved_in(root, ending=b"\r\n"), "HEAD", "stat",
                 lambda root: ".gitdir",
                 id="gitfile-ending-in-cr-lf-names-a-directory-inside"),
    pytest.param(lambda root: moved_in(root, UNPRINTABLE), "HEAD", "stat",
                 lambda root: repr(UNPRINTABLE),
                 id="gitfile-names-an-unprintable-directory",
                 marks=POSIX_NAMES),
])
def test_the_doctor_and_the_gate_name_one_git_directory(
        standard, project, gates, monkeypatch, capsys, arrange, name,
        method, named):
    """What `.git` is or names, refused: a git directory whose `HEAD` cannot
    be reached, or a gitfile that cannot be opened. The doctor's line and
    `validate-pins.py`'s refusal are one sentence, naming the git directory
    relative to the root where it is inside it and whole where it is not,
    from a gitfile whose line ends in CR LF as from one ending in LF, and
    as `repr` spells a name that is not printable (r1147's N1)."""
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


@GATES
def test_a_relative_root_is_walked_from_where_it_resolves(
        project, gates, monkeypatch, capsys, gate):
    """r1147's S1 (a). Run from `<root>/contracts` with `--root .`, and the
    root's `.git` refused: the walk starts where `.` resolves, as
    `find_repo_root`'s does, reaches the root's `.git` and names it whole.
    `Path(".")` has no parents, so a walk from it unresolved asks `.git` in
    `contracts/` alone and leaves the root's to `find_repo_root`, whose
    `exists()` raised on 3.12 and answers False from 3.14."""
    dotgit = project.resolve() / ".git"
    as_python_314(monkeypatch, {dotgit: PermissionError(errno.EACCES,
                                                        DENIED)})
    monkeypatch.chdir(project / "contracts")
    assert gates[gate].main(["--root", "."]) == 2
    assert capsys.readouterr().err == refused(gate,
                                              cannot(str(dotgit), DENIED))


@GATES
def test_the_walk_stops_at_a_git_that_is_a_gitfile(project, gates,
                                                   monkeypatch, capsys, gate):
    """r1147's S1 (b). The root's `.git` a readable gitfile, and a `.git`
    above the root refused: `find_repo_root` stops at the gitfile, the
    first `.git` that is there whatever it is, and so does the question.
    Each gate passes. Each leg's gitfile follows its repository to
    `.gitdir/modules/`, so git still reads the legs `validate-pins.py`
    asks about."""
    moved_in(project)
    for leg in ("spec", "code"):
        (project / leg / ".git").write_bytes(
            f"gitdir: ../.gitdir/modules/{leg}\n".encode())
    as_python_314(monkeypatch, {
        project.resolve().parent / ".git": PermissionError(errno.EACCES,
                                                           DENIED)})
    assert gates[gate].main(["--root", str(project)]) == 0, \
        capsys.readouterr().err


def test_the_git_directory_above_the_folder_given_is_named_whole(
        project, gates, monkeypatch, capsys):
    """r1147's N3. `--root` a folder inside the root, and the root's `.git`
    a directory whose `HEAD` cannot be reached: `validate-pins.py`'s
    git-directory step names it whole, as its `stat` step does, since it
    is not under the folder given."""
    refusing(monkeypatch, "stat", "HEAD",
             PermissionError(errno.EACCES, DENIED))
    assert gates["validate-pins.py"].main(
        ["--root", str(project / "contracts")]) == 2
    assert capsys.readouterr().err == refused(
        "validate-pins.py", cannot(str(project.resolve() / ".git"), DENIED))


def test_placement_audits_each_leg_git_reads_beside_a_refused_root_git(
        standard, project, monkeypatch):
    """r1147's S2, on every platform and as root. Only the root's own `.git`
    refused, in process, and git, which no stand-in reaches, reads each
    leg's repository: a stand-in for a leg git reads without the root's
    `.git`, as the mode case above has one. The `legs` row names the root's
    `.git`, and `placement` still audits both legs."""
    module, ctx = in_process(standard, project)
    as_python_314(monkeypatch, {
        ctx.root / ".git": PermissionError(errno.EACCES, DENIED)})
    assert module.check_legs(ctx).reason == legs_said(cannot(".git"))
    placement = module.check_placement(ctx)
    assert placement.status == module.OK, placement.reason
    assert [entry["state"] for entry in placement.detail["legs"]] \
        == ["audited", "audited"]


#: What git answers for a leg in another repository's top level.
ELSEWHERE = ("it is not a repository of its own -- `git` answers from "
             "/elsewhere -- so `ls-files` there would report that "
             "repository's paths, not this leg's")


@pytest.mark.parametrize("arrange, spec_said", [
    pytest.param(lambda root: None, ELSEWHERE,
                 id="git-answers-from-another-repository"),
    pytest.param(lambda root: (root / "spec" / ".git").unlink(), None,
                 id="no-git-of-its-own"),
])
def test_only_a_leg_git_names_no_repository_for_is_given_the_roots_line(
        standard, project, monkeypatch, arrange, spec_said):
    """git's answers put in by hand, in process, beside a refused root
    `.git`: the code leg, whose `.git` is there and git names no top level
    for, is given the root's line. The spec leg keeps git's answer where git
    answers from another repository's top level, or where it has no `.git`
    of its own: it is not its own repository whatever the root's `.git`
    says."""
    arrange(project)
    module, ctx = in_process(standard, project)
    spec_said = spec_said or module.NOT_A_GIT_REPOSITORY
    answers = {ctx.root / "spec": spec_said,
               ctx.root / "code": module.NOT_A_GIT_REPOSITORY}
    monkeypatch.setattr(module, "not_its_own_repository",
                        lambda mount: answers[mount])
    as_python_314(monkeypatch, {
        ctx.root / ".git": PermissionError(errno.EACCES, DENIED)})
    line = cannot(".git")
    placement = module.check_placement(ctx)
    assert placement.status == module.NA
    assert placement.reason == (
        f"no leg could be read, so nothing was classified: spec: {spec_said}; "
        f"code: read through the root's repository, and {line}")
    assert placement.detail["legs"] == [
        {"role": "spec", "path": "spec", "state": spec_said},
        {"role": "code", "path": "code", "state": line,
         module.GITLINK_UNREAD: line}]


def legs_under_a_moved_root(root: Path) -> None:
    """The root's `.git` moved to `elsewhere/projgit` with a gitfile naming
    it, and each leg's gitfile naming its git directory under that one, as
    git writes it for a root that is a linked worktree or a submodule
    itself (`../../elsewhere/projgit/modules/<leg>`)."""
    moved_out(root)
    for leg in ("spec", "code"):
        (root / leg / ".git").write_bytes(
            f"gitdir: ../../elsewhere/projgit/modules/{leg}\n".encode())


def every_head_refused(monkeypatch) -> None:
    """The `stat` of every `HEAD` refused, the root's and each leg's: a
    stand-in, in process, for a root's git directory this user cannot
    search, and the legs' git directories inside it."""
    refusing(monkeypatch, "stat", "HEAD", PermissionError(errno.EACCES,
                                                          DENIED))


@pytest.mark.parametrize("arrange, named", [
    pytest.param(lambda root: None, lambda root: ".git",
                 id="under-the-roots-git"),
    pytest.param(legs_under_a_moved_root,
                 lambda root: str(root.parent / "elsewhere" / "projgit"),
                 id="under-the-directory-the-roots-gitfile-names"),
])
def test_a_leg_git_directory_inside_the_roots_is_given_the_roots_line(
        standard, project, monkeypatch, arrange, named):
    """#1146 over #1174, in process, on every platform and as root. Each
    leg's git directory is inside the root's own, and every `HEAD` is
    refused: `mount_read` refuses each leg's git directory, and the merge of
    the two said `<leg>: .git/modules/<leg>: cannot be read` of each, so
    `placement` could not say the root's line once. The root's line now
    comes first, for a root's `.git` that is the git directory and for one
    that is a gitfile naming it, and both rows say it once."""
    arrange(project)
    module, ctx = in_process(standard, project)
    every_head_refused(monkeypatch)
    line = cannot(named(ctx.root))
    assert module.root_git_read(ctx.root)[0] == line
    assert module.check_legs(ctx).reason == legs_said(line)
    placement = module.check_placement(ctx)
    assert placement.status == module.NA
    assert placement.reason == placement_said(line)
    assert placement.detail["legs"] == [
        {"role": role, "path": role, "state": line,
         module.GITLINK_UNREAD: line} for role in ("spec", "code")]


def test_a_git_directory_of_the_legs_own_keeps_its_own_line(
        standard, project, monkeypatch):
    """The control, in process: every `HEAD` refused, and the spec leg's
    repository in a `.git` directory of its own. Its git directory is not
    inside the root's, so the root's `.git` is not what kept it from being
    read: it keeps `mount_read`'s line, `spec/.git: cannot be read` (#1174),
    and only the code leg, read through the root's repository, is given the
    root's line."""
    own_repository(project)
    module, ctx = in_process(standard, project)
    every_head_refused(monkeypatch)
    line = cannot(".git")
    own = cannot("spec/.git")
    placement = module.check_placement(ctx)
    assert placement.status == module.NA
    assert placement.reason == (
        f"no leg could be read, so nothing was classified: {own}; "
        f"code: read through the root's repository, and {line}")
    assert placement.detail["legs"] == [
        {"role": "spec", "path": "spec", "state": own,
         module.MOUNT_UNREAD: own},
        {"role": "code", "path": "code", "state": line,
         module.GITLINK_UNREAD: line}]


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
