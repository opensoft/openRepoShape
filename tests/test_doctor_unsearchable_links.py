# SPDX-License-Identifier: Apache-2.0
"""A name in the root that is a link into a folder this user cannot search is
named by the doctor and by the Triad advisory, never taken for nothing there:
#1110's slice A (`shape-doctor.py` and `scripts/shape_advisory.py`).

THE DEFECT. #430's rule is to `stat` a path and read only ENOENT, ENOTDIR,
EBADF and ELOOP as nothing there. Eight sites still asked `exists()` or
`is_file()` of a name directly in the root, and those follow a link: a `.git`
or an `AGENTS.md` that is a link into a folder at mode 000 raised
`PermissionError` up to Python 3.13, and from 3.14 answered False. Measured on
main `038dafba`, Python 3.12.3 and a 3.14-like shim (a `sitecustomize` whose
`is_file`, `is_dir` and `exists` answer False to any `OSError`), over a folder
`Atlas` whose `.git` links into such a folder, origin `acme/Orbit`:

  * 3.12: the `naming`, `what is here`, `the way in` and `the other way in`
    rows each `FINDING .git: cannot be read (Permission denied)`, with the
    same NEXT and the same `chmod` advice, four times; no Triad row;
  * the shim: `what is here` said `an ordinary directory`, and `the way in`
    said `there is no repository here to adopt` and sent the person to
    `setup.sh`, three new repositories; `naming` classified `Atlas` alone;
    `origin_org` and `repo_local_origin_name` gave None and
    `shape_advisory.repository_names` `['Atlas']`, the answers for a folder
    that is no repository, and `read()` said `not-a-repository`;
  * an `AGENTS.md` linked so: `absent: AGENTS.md` under the shim, with
    `scaffold-project.py --help` over a file that is there, in the `agent
    files` row of a project and in `what is here` elsewhere; on 3.12 a
    FINDING made of the raise, which put `agent-files` in the verdict for a
    file nothing pins.

NOW, ON EVERY PYTHON: `what is here`, the one row that reads every name in a
directory that is no shape root, says `<name>: cannot be read (<reason>)`, in
`validate-pins.py`'s words, with this doctor again as the NEXT and the gate's
advice as the WHY, once. `the way in` offers neither command while the `.git`
cannot be read, `the other way in` and the Triad row say nothing, and
`naming` classifies the folder's own name and says `origin`'s was not read.
The `agent files` row of a project says the same line, a `note` for a file
nothing pins and a FINDING for one the pin names, as for a file that is
absent. The advisory answers `not-answered`, silent, with the line in `why`.

TWO KINDS OF CASE, as `tests/test_doctor_unreadable_paths.py` has them. The
MODE cases make a real link into a real folder at 000 and run the doctor as a
person does; they skip on Windows and as root (`CANNOT_RUN_AS_ROOT`), and put
the mode back in a `finally` (`mode_of`). The STAND-IN cases refuse the
`stat` in process (`refused_stat`, which also answers `exists()` as 3.14
does, and `refusing` for another reason), so they run everywhere.
"""

from __future__ import annotations

import errno
import json
import os
import sys
from pathlib import Path

import pytest

from conftest import REPO, git
#: #827's stand-in for a `stat` the operating system refuses, answering
#: `exists()` and `is_file()` as Python 3.14 does, from the file that owns it.
from test_bump_leg_unopenable import refused_stat
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: #847's helpers and the gate's advice, word for word, from the file that
#: owns them.
from test_doctor_unreadable_pin import (
    DENIED, IO_ERROR, OTHER_WHY, PERMISSION_WHY, cannot, doctored, in_process,
    refusing,
)
#: The doctor's fixtures, from the module that owns them.
from test_shape_doctor import (  # noqa: F401
    doctor, doctor_module, project, rows_of, scaffolded_here, standard,
)
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it.
from test_validate_pins_unreadable_workflows_dir import mode_of

sys.path.insert(0, str(REPO / "scripts"))
import shape_advisory  # noqa: E402

#: The repository behind the link: a checkout of `Orbit`, in a folder that is
#: called something else, as a clone into another name is.
ORIGIN = "git@github.com:acme/Orbit.git"
GIT_LINE = cannot(".git")
AGENTS_LINE = cannot("AGENTS.md")
#: What `the way in` says while the `.git` cannot be read.
NO_WAY_IN = ("its .git cannot be read, so it is not known whether this is a "
             "git repository to adopt, and neither way in is offered until "
             "it can be: `what is here` says how")
#: What `naming` adds while the `.git` cannot be read.
ORIGIN_UNREAD = ("; origin's name is not read while .git cannot be read "
                 "(see `what is here`)")
#: What the advisory says of it, in `--json`'s `why`.
ADVISORY_WHY = (f"{GIT_LINE}, so whether this is a repository is not known "
                "here, and the advisory says nothing")
#: The words no row may say of a name that IS there, and the lines that send
#: a person to adopt or scaffold (the `machine` row's `--preflight` is neither).
SAYS_NOTHING_THERE = ("absent", "no repository", "an ordinary directory",
                      "SCAFFOLDED")
OFFERS_A_WAY_IN = (" --org ", "adopt-project.py")


def symlink(at: Path, to: Path) -> None:
    """`at`, a link to the relative path `to`; a skip where none can be
    made."""
    try:
        at.symlink_to(to)
    except OSError as exc:
        pytest.skip(f"no symlink here: {exc}")


def repository_here(root: Path) -> Path:
    """`root`, a git repository of its own whose `origin` is `ORIGIN`."""
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    git("remote", "add", "origin", ORIGIN, cwd=root)
    return root


def linked_repository(tmp_path: Path) -> Path:
    """`<tmp>/Atlas`, whose `.git` is a link to the git directory of the
    repository at `<tmp>/locked/repo`, whose `origin` is `ORIGIN`."""
    (tmp_path / "locked").mkdir()
    repository_here(tmp_path / "locked" / "repo")
    root = tmp_path / "Atlas"
    root.mkdir()
    symlink(root / ".git", Path("..", "locked", "repo", ".git"))
    (root / "README.md").write_text("# Atlas\n", encoding="utf-8")
    return root


def told_once(rows: dict, line: str) -> None:
    """`line` is the reason of ONE row, which alone carries this doctor
    again and the gate's advice; no other row says the line or the advice."""
    saying = [key for key, row in rows.items() if line in row["reason"]]
    advising = [key for key, row in rows.items()
                if PERMISSION_WHY in (row["why"] or "")
                or OTHER_WHY in (row["why"] or "")]
    assert len(saying) == 1, saying
    assert advising == saying, (saying, advising)


def no_way_in_over_it(rows: dict) -> None:
    """No row says nothing is there, and none sends the person to adopt or
    scaffold. The `machine` row is about the workstation, not the folder."""
    for key, row in rows.items():
        if key == "machine":
            continue
        for words in SAYS_NOTHING_THERE:
            assert words not in row["reason"], row
        for words in OFFERS_A_WAY_IN:
            assert words not in (row["next"] or ""), row


def by_id(rows) -> dict:
    """`{id: row}` as `--json` has them, for rows made in process."""
    return {row.id: {"status": row.status, "reason": row.reason,
                     "next": row.next_command, "why": row.why,
                     "detail": row.detail}
            for row in rows if row is not None}


def not_a_root_rows(module, ctx) -> dict:
    """The rows a directory with no manifest gets, but `machine`, in
    process."""
    return by_id([module.check_not_a_root_naming(ctx),
                  module.check_what_is_here(ctx),
                  module.check_the_way_in(ctx),
                  module.check_the_other_way_in(ctx),
                  module.check_triad_advisory(ctx)])


# --- the mode cases: a real link, the doctor run as a person runs it --------

@CANNOT_RUN_AS_ROOT
def test_a_git_linked_into_a_folder_nobody_may_search_offers_no_way_in(
        standard, tmp_path):
    """The issue's worst case. Readable, the folder is the repository it
    links to, adopted as `Orbit`. At 000 it was four FINDINGs of one line on
    3.12, and on 3.14 an ordinary directory sent to `setup.sh`. Now `what is
    here` names the `.git` once with the cure, `the way in` offers nothing,
    `the other way in` and the Triad row are silent, and nothing raises."""
    root = linked_repository(tmp_path)
    readable, _verdict = doctored(standard, root)
    assert "adopt-project.py" in readable["way-in"]["next"], readable
    assert "--project Orbit" in readable["way-in"]["next"], readable
    assert readable["naming"]["detail"]["names"] == ["Atlas", "Orbit"]
    denied = os.strerror(errno.EACCES)
    line = cannot(".git", denied)
    with mode_of(tmp_path, "locked", 0):
        result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "NOT A SHAPE ROOT"
    rows = rows_of(result)
    assert set(rows) == {"naming", "contents", "way-in", "machine"}, rows
    contents, way_in, naming = rows["contents"], rows["way-in"], rows["naming"]
    assert contents["status"] == "n/a", contents
    assert contents["reason"] == line
    assert contents["next"] == doctor_again(standard, root)
    assert contents["why"] == PERMISSION_WHY
    assert contents["detail"][".git"] is True
    assert contents["detail"]["cannot_be_read"] == [line]
    assert way_in["status"] == "n/a", way_in
    assert way_in["reason"] == NO_WAY_IN
    assert way_in["next"] is None, way_in
    assert way_in["detail"]["git_repository"] is None, way_in
    assert way_in["detail"]["cannot_be_read"] == line
    assert naming["reason"] == ("Atlas: classifies under the naming policy"
                                + ORIGIN_UNREAD)
    assert naming["detail"]["names"] == ["Atlas"]
    assert naming["detail"]["cannot_be_read"] == line
    told_once(rows, line)
    no_way_in_over_it(rows)


@CANNOT_RUN_AS_ROOT
def test_an_agents_md_linked_into_a_folder_nobody_may_search_is_there(
        standard, tmp_path):
    """A directory that is no shape root, with an `AGENTS.md` linked into a
    folder at 000: `what is here` names it with the cure, where 3.14 called
    the directory ordinary and 3.12 made a FINDING of the raise. With no
    `.git` here, the way in is still the scaffold."""
    locked, root = tmp_path / "locked", tmp_path / "Atlas"
    locked.mkdir()
    root.mkdir()
    (locked / "AGENTS.md").write_text("# agents\n", encoding="utf-8")
    symlink(root / "AGENTS.md", Path("..", "locked", "AGENTS.md"))
    readable, _verdict = doctored(standard, root)
    assert readable["contents"]["reason"] == "an AGENTS.md", readable
    line = cannot("AGENTS.md", os.strerror(errno.EACCES))
    with mode_of(tmp_path, "locked", 0):
        rows, verdict = doctored(standard, root)
    assert verdict == "NOT A SHAPE ROOT"
    contents = rows["contents"]
    assert contents["status"] == "n/a", contents
    assert contents["reason"] == line
    assert contents["next"] == doctor_again(standard, root)
    assert contents["why"] == PERMISSION_WHY
    assert contents["detail"]["AGENTS.md"] is True
    assert rows["way-in"]["detail"]["git_repository"] is False
    told_once(rows, line)


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("name", ["AGENTS.md", "CLAUDE.md"])
def test_a_projects_agent_file_linked_out_of_reach_is_a_note(
        standard, project, tmp_path, name):
    """A project's rendered agent file, a link into a folder at 000: the
    `agent files` row says the gate's line, with the cure, as a `note`, and
    the verdict is the project's own. 3.12 made a FINDING of the raise and
    `INVALID (agent-files)` of a COMPLIANT project; 3.14 said `absent` with
    `scaffold-project.py --help` over a file that is there."""
    locked = tmp_path / "locked"
    locked.mkdir()
    (project / name).rename(locked / name)
    symlink(project / name, Path("..", "locked", name))
    _rows, readable = doctored(standard, project)
    line = cannot(name, os.strerror(errno.EACCES))
    with mode_of(tmp_path, "locked", 0):
        rows, verdict = doctored(standard, project)
    files = rows["agent-files"]
    assert files["status"] == "note", files
    assert files["reason"] == line
    assert files["next"] == doctor_again(standard, project)
    assert files["why"] == PERMISSION_WHY
    assert files["detail"]["files"][name] is True
    assert files["detail"]["cannot_be_read"] == [line]
    assert verdict == readable
    told_once(rows, line)


# --- the stand-in cases: in process, on every platform and as root ----------

@pytest.mark.parametrize("ask", ["carries_git", "origin_org",
                                 "repo_local_origin_name"])
def test_the_git_questions_raise_a_refused_stat(standard, tmp_path,
                                                monkeypatch, ask):
    """Each question the doctor asks of the root's own `.git` raises a
    refused `stat` for its caller to name, where 3.14's `exists()` answered
    as for a folder with no repository: None from `origin_org` and from
    `repo_local_origin_name`."""
    module = doctor_module(standard)
    question = getattr(module, ask)
    root = repository_here(tmp_path / "Atlas")
    answered = {"carries_git": True, "origin_org": "acme",
                "repo_local_origin_name": "Orbit"}
    assert question(root) == answered[ask]
    # The controls: no `.git`, or a name under a file, is no repository.
    plain = tmp_path / "Plain"
    plain.mkdir()
    (tmp_path / "file").write_text("x\n", encoding="utf-8")
    for nothing in (plain, tmp_path / "file"):
        assert question(nothing) in (False, None)
    refused_stat(monkeypatch, ".git")
    with pytest.raises(PermissionError):
        question(root)


@pytest.mark.parametrize("error, line, why", [
    pytest.param(PermissionError(errno.EACCES, DENIED), GIT_LINE,
                 PERMISSION_WHY, id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), cannot(".git", IO_ERROR),
                 OTHER_WHY, id="io-error"),
])
def test_a_git_this_user_cannot_reach_is_named_once_on_every_python(
        standard, tmp_path, monkeypatch, error, line, why):
    """The rows of a directory with no manifest, in process, the `.git`'s
    `stat` refused: `what is here` names it with the advice for the cause,
    `the way in` offers nothing, `the other way in` and the Triad row are
    silent, and `naming` says `origin` was not read. An I/O error is told
    the gate's other advice, not `chmod`."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    ctx = module.Context(root.resolve())
    if isinstance(error, PermissionError):
        refused_stat(monkeypatch, ".git")
    else:
        refusing(monkeypatch, "stat", ".git", error)
    rows = not_a_root_rows(module, ctx)
    assert set(rows) == {"naming", "contents", "way-in"}, rows
    contents = rows["contents"]
    assert contents["reason"] == line
    assert contents["next"] == module.doctor_line(ctx)
    assert contents["why"] == why
    assert contents["status"] == module.NA
    assert rows["way-in"]["reason"] == NO_WAY_IN
    assert rows["way-in"]["next"] is None
    assert rows["way-in"]["detail"] == {
        "git_repository": None, "suggested_project": None,
        "origin_org": None, "cannot_be_read": line, "path": ".git"}
    assert rows["naming"]["reason"].endswith(ORIGIN_UNREAD), rows["naming"]
    told_once(rows, line)
    no_way_in_over_it(rows)


def test_beside_what_it_can_read_the_row_names_what_it_cannot_first(
        standard, tmp_path, monkeypatch):
    """`what is here` with a `Makefile` it can read and a `.git` it cannot:
    the line first, then what it found, and never `a git repository`."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    (root / "Makefile").write_text("all:\n", encoding="utf-8")
    ctx = module.Context(root.resolve())
    refused_stat(monkeypatch, ".git")
    row = module.check_what_is_here(ctx)
    assert row.reason == f"{GIT_LINE}; a Makefile"
    assert row.detail[".git"] is True
    assert row.detail["Makefile"] is True


def test_the_advisory_names_a_git_it_cannot_reach_and_says_nothing(
        tmp_path, monkeypatch):
    """`shape_advisory`: `repository_names` raises the refused `stat` where
    3.14 dropped `origin`'s name, and `read()` answers `not-answered`, which
    every reader keeps silent, naming the `.git` in `why`, where 3.14 said
    `not-a-repository`."""
    root = repository_here(tmp_path / "Atlas")
    quiet = tmp_path / "agent-protocol"
    quiet.mkdir()
    env = {"AGENT_PROTOCOL_ROOT": str(quiet)}
    assert shape_advisory.repository_names(root) == ["Atlas", "Orbit"]
    assert shape_advisory.read(root, env=env).state == shape_advisory.ADVISE
    refused_stat(monkeypatch, ".git")
    with pytest.raises(PermissionError):
        shape_advisory.repository_names(root)
    reading = shape_advisory.read(root, env=env)
    assert reading.state == shape_advisory.NOT_ANSWERED
    assert reading.why == ADVISORY_WHY
    assert reading.advise is False


def test_the_doctor_reads_the_advisory_as_silent(standard, tmp_path,
                                                 monkeypatch):
    """The doctor's two readers of the advisory over that `.git`: no Triad
    row, and not a leg clone."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    ctx = module.Context(root.resolve())
    refused_stat(monkeypatch, ".git")
    assert module.shape_advisory.read(ctx.root, ctx.shape).why == ADVISORY_WHY
    assert module.check_triad_advisory(ctx) is None
    assert module.leg_clone(ctx) is False


@pytest.mark.parametrize("refuse, status, line, why", [
    pytest.param(lambda patch: refused_stat(patch, "AGENTS.md"), "note",
                 AGENTS_LINE, PERMISSION_WHY, id="rendered"),
    pytest.param(lambda patch: refusing(patch, "stat", "AGENTS.md",
                                        OSError(errno.EIO, IO_ERROR)),
                 "note", cannot("AGENTS.md", IO_ERROR), OTHER_WHY,
                 id="io-error"),
    pytest.param(lambda patch: refused_stat(patch, "AGENTS-shape.md"),
                 "FINDING", cannot("AGENTS-shape.md"), PERMISSION_WHY,
                 id="pinned"),
])
def test_an_agent_file_this_user_cannot_reach_is_named_on_every_python(
        standard, project, monkeypatch, refuse, status, line, why):
    """The `agent files` row with one file's `stat` refused: the gate's
    line, this doctor again and the advice for the cause, never `absent`. A
    `note` for a file nothing pins, and a FINDING for the copy the pin
    names, which the project's own gate refuses by name."""
    module, ctx = in_process(standard, project)
    pinned = module.pinned_paths(ctx.root)
    assert "AGENTS-shape.md" in pinned and "AGENTS.md" not in pinned, pinned
    refuse(monkeypatch)
    row = module.check_agent_files(ctx)
    assert row.status == status
    assert row.reason == line
    assert row.next_command == doctor_again(standard, project)
    assert row.why == why
    assert all(row.detail["files"].values()), row.detail
    assert row.detail["cannot_be_read"] == [line]
    assert "absent" not in row.reason


def test_beside_an_absent_agent_file_its_command_stays_the_next(
        standard, project, monkeypatch):
    """`CLAUDE.md` gone and `AGENTS.md` out of reach: the absent file's
    command is the NEXT, said first, and the advice for the other follows
    its `why`, as the `legs` row keeps its checkout line beside a pin it
    cannot read."""
    module, ctx = in_process(standard, project)
    (project / "CLAUDE.md").unlink()
    alone = module.check_agent_files(ctx)
    refused_stat(monkeypatch, "AGENTS.md")
    row = module.check_agent_files(ctx)
    assert row.reason == f"absent: CLAUDE.md; {AGENTS_LINE}"
    assert row.next_command == alone.next_command
    assert row.why == f"{alone.why}. {PERMISSION_WHY}"
    assert row.status == alone.status == module.NOTE
    assert row.detail["files"] == {"AGENTS-shape.md": True, "AGENTS.md": True,
                                   "CLAUDE.md": False}
