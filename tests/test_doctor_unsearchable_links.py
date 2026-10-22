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

THE CONTROLS, true on main as well, hold the guard to #430's other answers: a
`.git` that is a link to itself or past a folder that is not there is no
repository, and a `.git` that is a gitdir file is one.

#1110'S TWELFTH SITE, `shape_advisory._leg_by_agents_md` (`except Exception:
return None`, "an unreadable file says nothing"). A leg's own `AGENTS.md`
that this user cannot read -- linked into a folder at 000, or itself at 000
-- was read as no leg's file on every Python. Measured on #1144's head
`89486f69`, over a clone of `acme/Orbit` whose `AGENTS.md` is the spec or
the code leg's: `the way in` offered `adopt-project.py plan ... --project
Orbit`, `the other way in` `setup.sh`, and the Triad row called it a single
repository, where the readable file is the leg, with no command at all. Now
`read()` answers `not-answered` with the line and the `OSError` it carries,
`leg_clone` raises it, `the way in` offers neither command and points at
`what is here`, which names the file with the cure (and reads it through, for
a file at 000), and `the other way in` and the Triad row are silent. A leg
known by its NAME is still one; a file that is not there, or is read and is
not UTF-8, is still no leg's file (controls); and `adopt-project.py`, which
reads the commit it plans, never reads the disk's file at all. `what is here`
reads through `AGENTS.md` alone, and only a regular one: a directory or a
named pipe of that name is listed and not read, and the pipe's row runs the
doctor under a timeout, since opening it would block for ever (controls).

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
import subprocess
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
#: A leg's `AGENTS.md`, rendered from its template as the scaffold renders
#: it, from the file that owns it.
from test_shape_advisory import rendered_leg_agents
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
#: a person to adopt or scaffold (`machine`'s `--preflight` is neither).
SAYS_NOTHING_THERE = ("absent", "no repository", "an ordinary directory",
                      "SCAFFOLDED")
OFFERS_A_WAY_IN = (" --org ", "adopt-project.py")
#: A `.git` that leads nowhere, for #430's rule that a link to itself (ELOOP)
#: and a link past a folder that is not there (ENOENT) are nothing there.
GIT_LINKS = {"loop": Path(".git"), "dangling": Path("..", "nowhere", ".git")}
#: A folder name the naming policy does not classify (exit 1), and what a
#: naming script that refuses for another reason than the policy says (exit 2).
UNCLASSIFIED = "my-service"
SCRIPT_REFUSES = "REFUSED naming-no-target: no names given."
#: What `the way in` says while a leg's `AGENTS.md` cannot be read.
NO_LEG_WAY_IN = ("its AGENTS.md cannot be read, so it is not known whether "
                 "this is a clone of a Triad's leg, which is not adopted or "
                 "scaffolded on its own, and neither way in is offered until "
                 "it can be: `what is here` says how")
#: How long one run of the doctor may take where an `AGENTS.md` it opened
#: would block it for ever (a named pipe nobody writes to): a run that takes
#: longer FAILS its row, rather than hanging the suite.
DOCTOR_SECONDS = 120
#: An `AGENTS.md` that leads nowhere, as `GIT_LINKS` above.
AGENTS_LINKS = {"loop": Path("AGENTS.md"),
                "dangling": Path("..", "nowhere", "AGENTS.md")}
#: The reads of a leg's `AGENTS.md` this user may be refused, in process:
#: its `stat`, as for a link into a folder this user cannot search, and its
#: read, as for a file at mode 000, whose `stat` succeeds; for a permission
#: and for an I/O error. `(refuse, the system's reason, the error's type)`.
AGENTS_REFUSALS = [
    pytest.param(lambda patch: refused_stat(patch, "AGENTS.md"), DENIED,
                 PermissionError, id="stat-permission"),
    pytest.param(lambda patch: refusing(patch, "stat", "AGENTS.md",
                                        OSError(errno.EIO, IO_ERROR)),
                 IO_ERROR, OSError, id="stat-io-error"),
    pytest.param(lambda patch: refusing(patch, "read_bytes", "AGENTS.md",
                                        PermissionError(errno.EACCES, DENIED)),
                 DENIED, PermissionError, id="read-permission"),
    pytest.param(lambda patch: refusing(patch, "read_bytes", "AGENTS.md",
                                        OSError(errno.EIO, IO_ERROR)),
                 IO_ERROR, OSError, id="read-io-error"),
]


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


def repository_apart(root: Path, kept: Path) -> Path:
    """`root`, a repository whose git directory is KEPT at `kept`, so that
    its `.git` is a gitdir FILE, as `--separate-git-dir`, a linked worktree or
    a submodule's checkout writes it; its `origin` is `ORIGIN`."""
    root.mkdir()
    git("init", "-q", "-b", "main", f"--separate-git-dir={kept}", ".",
        cwd=root)
    git("remote", "add", "origin", ORIGIN, cwd=root)
    assert (root / ".git").is_file()
    return root


def git_link(tmp_path: Path, kind: str) -> Path:
    """`<tmp>/Atlas`, whose `.git` is a link that leads nowhere: to itself
    (`loop`) or past a folder that is not there (`dangling`)."""
    root = tmp_path / "Atlas"
    root.mkdir()
    symlink(root / ".git", GIT_LINKS[kind])
    (root / "README.md").write_text("# Atlas\n", encoding="utf-8")
    return root


def refusing_standard(tmp_path: Path, said: str) -> Path:
    """A stand-in for the standard: this checkout's naming policy and a
    naming script that says `said` on stderr and exits 2, as
    `tests/test_doctor_validator_verdicts.py` makes one in a copy of the whole
    standard, here without the copy."""
    here = tmp_path / "standard"
    (here / "contracts").mkdir(parents=True)
    (here / "scripts").mkdir()
    (here / "contracts" / "repository-naming.yaml").write_bytes(
        (REPO / "contracts" / "repository-naming.yaml").read_bytes())
    (here / "scripts" / "validate-repository-naming.py").write_text(
        f"import sys\nprint({said!r}, file=sys.stderr)\nsys.exit(2)\n",
        encoding="utf-8")
    return here


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


def no_workspace(tmp_path: Path) -> dict:
    """An environment whose `AGENT_PROTOCOL_ROOT` holds no `workspace.yaml`,
    so no person's own configuration can change an answer."""
    quiet = tmp_path / "agent-protocol"
    quiet.mkdir()
    return {"AGENT_PROTOCOL_ROOT": str(quiet)}


def leg_clone_here(root: Path, role: str = "spec") -> Path:
    """`root`, a repository of its own whose `origin` is `ORIGIN` and whose
    `AGENTS.md` is the `role` leg's, as its template renders it: a leg
    cloned into a folder called something else."""
    repository_here(root)
    (root / "AGENTS.md").write_text(rendered_leg_agents(role),
                                    encoding="utf-8")
    return root


def leg_agents_why(reason: str = DENIED) -> str:
    """The advisory's `why` for a leg's `AGENTS.md` it cannot read."""
    return (f"{cannot('AGENTS.md', reason)}, so whether this is a leg clone "
            "is not known here, and the advisory says nothing")


def is_the_leg(rows: dict, role: str) -> None:
    """A clone of the `role` leg whose `AGENTS.md` this user can read: `the
    way in` is the leg's row, with no command, no scaffold is offered, and
    the Triad row sends it to its assembly root."""
    assert "AS A LEG" in rows["way-in"]["reason"], rows["way-in"]
    assert rows["way-in"]["next"] is None, rows["way-in"]
    assert "way-in-scaffold" not in rows, sorted(rows)
    assert (f"this is a clone of the {role} leg"
            in rows["triad-advisory"]["reason"]), rows["triad-advisory"]


def no_leg_way_in(rows: dict, line: str, again: str, why: str) -> None:
    """The same clone, its `AGENTS.md` refused (`line`): `what is here` names
    it with this doctor `again` and the advice for the cause, `the way in`
    offers neither command and points there, and `the other way in` and the
    Triad row are silent. `machine` is about the workstation."""
    assert set(rows) - {"machine"} == {"naming", "contents", "way-in"}, rows
    contents, way_in = rows["contents"], rows["way-in"]
    assert contents["status"] == "n/a", contents
    assert contents["reason"] == f"{line}; a git repository"
    assert contents["next"] == again
    assert contents["why"] == why
    assert contents["detail"]["AGENTS.md"] is True
    assert contents["detail"]["cannot_be_read"] == [line]
    assert way_in["status"] == "n/a", way_in
    assert way_in["reason"] == NO_LEG_WAY_IN
    assert way_in["next"] is None, way_in
    assert way_in["detail"] == {
        "git_repository": True, "suggested_project": None,
        "origin_org": "acme", "cannot_be_read": line, "path": "AGENTS.md"}
    told_once(rows, line)
    no_way_in_over_it(rows)


def offered_both_ways_in(module, ctx) -> None:
    """`offers_both_ways_in`, of the rows made in process."""
    offers_both_ways_in(module, not_a_root_rows(module, ctx))


def offers_both_ways_in(module, rows: dict) -> None:
    """A clone the advisory reads as no leg, with nothing it cannot read:
    advised, offered the adoption as `Orbit` and the scaffold, and no row
    says `cannot be read`. `machine`, which only a whole run gives, is about
    the workstation."""
    rows = {key: row for key, row in rows.items() if key != "machine"}
    assert set(rows) == {"naming", "contents", "way-in", "way-in-scaffold",
                         "triad-advisory"}, rows
    for row in rows.values():
        assert "cannot be read" not in row["reason"], row
    assert "adopt-project.py" in rows["way-in"]["next"], rows["way-in"]
    assert "--project Orbit" in rows["way-in"]["next"], rows["way-in"]
    assert rows["triad-advisory"]["status"] == module.ADVISORY


def doctor_within(standard: Path, root: Path) -> dict:
    """`{id: row}` from `doctor(standard, root, "--json")`, the run a person
    makes, given `DOCTOR_SECONDS` to end: `subprocess.run` is handed the
    timeout for this one call, so the environment is `run_script`'s own. A
    run that would block for ever on an `AGENTS.md` it opened fails the row
    by name, and the doctor is killed. It printed no traceback, and its exit
    is NOT A SHAPE ROOT's."""
    real = subprocess.run

    def bounded(*args, **kwargs):
        return real(*args, timeout=DOCTOR_SECONDS, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "run", bounded)
        try:
            result = doctor(standard, root, "--json")
        except subprocess.TimeoutExpired:
            pytest.fail(f"the doctor did not end within {DOCTOR_SECONDS} "
                        f"seconds over {root}: something opened its "
                        "AGENTS.md")
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "NOT A SHAPE ROOT"
    return rows_of(result)


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


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("role", ["spec", "code"])
def test_a_leg_agents_md_linked_into_a_folder_nobody_may_search_offers_no_way_in(
        standard, tmp_path, role):
    """#1110's twelfth site, the case r1144 measured. Readable, a clone of
    `acme/Orbit` whose `AGENTS.md` is a leg's is that leg: no command, and
    the Triad row sends it to its root. Linked into a folder at 000 it was
    no leg's file on every Python: `the way in` offered the adoption as
    `Orbit`, `the other way in` the scaffold, and the Triad row called it a
    single repository. Now `what is here` names it once with the cure, `the
    way in` offers neither command and points there, `the other way in` and
    the Triad row are silent, and the verdict and exit are unchanged."""
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "AGENTS.md").write_text(rendered_leg_agents(role),
                                      encoding="utf-8")
    root = repository_here(tmp_path / "Atlas")
    symlink(root / "AGENTS.md", Path("..", "locked", "AGENTS.md"))
    readable, _verdict = doctored(standard, root)
    is_the_leg(readable, role)
    with mode_of(tmp_path, "locked", 0):
        result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    assert result.returncode == 2, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "NOT A SHAPE ROOT"
    no_leg_way_in(rows_of(result),
                  cannot("AGENTS.md", os.strerror(errno.EACCES)),
                  doctor_again(standard, root), PERMISSION_WHY)


@CANNOT_RUN_AS_ROOT
def test_a_leg_agents_md_this_user_may_not_open_offers_no_way_in(
        standard, tmp_path):
    """The same leg's `AGENTS.md` as a regular file at mode 000: its `stat`
    succeeds and its read is refused. `what is here` said `an AGENTS.md`,
    and the rest as for the link. `what is here` reads it through now, so it
    names the file the advisory cannot read, and `the way in`'s pointer has
    a line to point at."""
    root = leg_clone_here(tmp_path / "Atlas", "code")
    readable, _verdict = doctored(standard, root)
    is_the_leg(readable, "code")
    with mode_of(root, "AGENTS.md", 0):
        rows, verdict = doctored(standard, root)
    assert verdict == "NOT A SHAPE ROOT"
    no_leg_way_in(rows, cannot("AGENTS.md", os.strerror(errno.EACCES)),
                  doctor_again(standard, root), PERMISSION_WHY)


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
    # The controls: a `.git` that is a gitdir FILE, as `--separate-git-dir`,
    # a linked worktree or a submodule's checkout writes it, is a repository;
    # no `.git`, or a name under a file, is none.
    separate = repository_apart(tmp_path / "Separate", tmp_path / "kept")
    assert question(separate) == answered[ask]
    plain = tmp_path / "Plain"
    plain.mkdir()
    (tmp_path / "file").write_text("x\n", encoding="utf-8")
    for nothing in (plain, tmp_path / "file"):
        assert question(nothing) in (False, None)
    refused_stat(monkeypatch, ".git")
    with pytest.raises(PermissionError):
        question(root)


@pytest.mark.parametrize("kind", sorted(GIT_LINKS))
def test_a_git_link_that_leads_nowhere_is_still_no_repository(
        standard, tmp_path, kind):
    """CONTROLS, true on main `038dafba` and on this change: a `.git` that is
    a link to itself (ELOOP) or past a folder that is not there (ENOENT) is
    nothing there, as `exists()` has always said. `the way in` is the
    scaffold and `what is here` an ordinary directory, with no cure and no
    `cannot be read`; no `origin` is asked. They hold the guard that reads a
    `stat` the system REFUSED as `cannot be read` to #430's other answers."""
    module = doctor_module(standard)
    root = git_link(tmp_path, kind)
    ctx = module.Context(root.resolve())
    rows = not_a_root_rows(module, ctx)
    assert set(rows) == {"naming", "contents", "way-in"}, rows
    for row in rows.values():
        assert "cannot be read" not in row["reason"], row
        assert "cannot_be_read" not in row["detail"], row
        assert PERMISSION_WHY not in (row["why"] or ""), row
    assert rows["naming"]["reason"] == ("Atlas: classifies under the "
                                        "naming policy")
    assert rows["naming"]["detail"]["names"] == ["Atlas"]
    assert "an ordinary directory" in rows["contents"]["reason"], rows
    way_in = rows["way-in"]
    assert way_in["detail"]["git_repository"] is False, way_in
    assert "SCAFFOLDED" in way_in["reason"], way_in
    assert "setup.sh" in way_in["next"], way_in
    assert "--project Atlas" in way_in["next"], way_in
    assert "adopt-project.py" not in way_in["next"], way_in
    assert module.origin_org(root) is None
    assert module.repo_local_origin_name(root) is None
    quiet = tmp_path / "agent-protocol"
    quiet.mkdir()
    env = {"AGENT_PROTOCOL_ROOT": str(quiet)}
    assert shape_advisory.repository_names(root) == ["Atlas"]
    assert (shape_advisory.read(root, env=env).state
            == shape_advisory.NOT_A_REPOSITORY)


@pytest.mark.parametrize("kind", sorted(GIT_LINKS))
def test_carries_git_says_no_to_a_link_that_leads_nowhere(
        standard, tmp_path, kind):
    """`carries_git`, asked of the same two links: False, not a repository
    and not a refusal. A new helper, so this fails on main by its absence."""
    module = doctor_module(standard)
    assert module.carries_git(git_link(tmp_path, kind)) is False


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


@pytest.mark.parametrize("name, code, status", [
    pytest.param("Atlas", 0, "ok", id="classifies"),
    pytest.param(UNCLASSIFIED, 1, "FINDING", id="does-not-classify"),
    pytest.param("Atlas", 2, "FINDING", id="script-refuses"),
])
def test_naming_says_origin_was_not_read_whatever_the_name_comes_to(
        standard, tmp_path, monkeypatch, name, code, status):
    """The `naming` row with the `.git`'s `stat` refused, for each exit the
    script gives: the folder's own name classified or not, and the same
    clause that `origin`'s name was not read, on every branch. The status is
    the policy's own, `ok` for a name that classifies: an unread `origin` is
    said, and is no finding. A name the policy refuses is a FINDING beside
    it, the clause still there, which `Atlas` alone never reaches."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / name)
    ctx = module.Context(root.resolve())
    if code == 2:
        ctx.shape = refusing_standard(tmp_path, SCRIPT_REFUSES)
    refused_stat(monkeypatch, ".git")
    row = module.check_not_a_root_naming(ctx)
    assert row.status == status, row
    assert row.detail["exit"] == code, row.detail
    assert row.detail["names"] == [name], row.detail
    assert row.reason.startswith(f"{name}: "), row
    assert row.reason.endswith(ORIGIN_UNREAD), row
    assert row.detail["cannot_be_read"] == GIT_LINE, row.detail
    assert (row.next_command is None) == (code == 0), row


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


@pytest.mark.parametrize("error, why", [
    pytest.param(PermissionError(errno.EACCES, DENIED), ADVISORY_WHY,
                 id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR),
                 ADVISORY_WHY.replace(DENIED, IO_ERROR), id="io-error"),
])
def test_the_advisory_names_a_git_it_cannot_reach_and_says_nothing(
        tmp_path, monkeypatch, error, why):
    """`shape_advisory`: `repository_names` raises the refused `stat` where
    3.14 dropped `origin`'s name, and `read()` answers `not-answered`, which
    every reader keeps silent, naming the `.git` and the system's reason in
    `why`, where 3.14 said `not-a-repository`."""
    root = repository_here(tmp_path / "Atlas")
    quiet = tmp_path / "agent-protocol"
    quiet.mkdir()
    env = {"AGENT_PROTOCOL_ROOT": str(quiet)}
    assert shape_advisory.repository_names(root) == ["Atlas", "Orbit"]
    assert shape_advisory.read(root, env=env).state == shape_advisory.ADVISE
    # The control: a `.git` that is a gitdir FILE is a repository to both
    # questions, its `origin`'s name kept and the advice given.
    apart = repository_apart(tmp_path / "Apart", tmp_path / "kept")
    assert shape_advisory.repository_names(apart) == ["Apart", "Orbit"]
    assert shape_advisory.read(apart, env=env).state == shape_advisory.ADVISE
    if isinstance(error, PermissionError):
        refused_stat(monkeypatch, ".git")
    else:
        refusing(monkeypatch, "stat", ".git", error)
    with pytest.raises(type(error)):
        shape_advisory.repository_names(root)
    reading = shape_advisory.read(root, env=env)
    assert reading.state == shape_advisory.NOT_ANSWERED
    assert reading.why == why
    assert reading.advise is False
    assert type(reading.refused) is type(error)


def test_the_doctor_reads_the_advisory_as_silent(standard, tmp_path,
                                                 monkeypatch):
    """The doctor's two readers of the advisory over that `.git`: no Triad
    row, and `leg_clone` raises the refused `stat` the reading carries
    (`refused`), as it raises a leg's `AGENTS.md` it cannot read (#1110's
    twelfth site), for its caller to name. `the way in` and `the other way
    in` ask `carries_git` first, so neither meets it here."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    ctx = module.Context(root.resolve())
    refused_stat(monkeypatch, ".git")
    reading = module.shape_advisory.read(ctx.root, ctx.shape)
    assert reading.why == ADVISORY_WHY
    assert type(reading.refused) is PermissionError
    assert module.check_triad_advisory(ctx) is None
    with pytest.raises(PermissionError):
        module.leg_clone(ctx)


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
    assert "AGENTS-shape.md" in pinned, pinned
    assert "AGENTS.md" not in pinned, pinned
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


def test_an_unreadable_pinned_agent_file_beside_an_absent_one_is_a_finding(
        standard, project, monkeypatch):
    """`CLAUDE.md` gone, which nothing pins, and the PINNED `AGENTS-shape.md`
    out of reach: a FINDING, as for a pinned file that is absent, with the
    absent file's command still the NEXT, and the verdict names `agent-files`.
    The status must not follow the absent file alone (a `note`): the project's
    own `validate-pins.py` refuses the unreadable copy by name."""
    module, ctx = in_process(standard, project)
    (project / "CLAUDE.md").unlink()
    alone = module.check_agent_files(ctx)
    assert alone.status == module.NOTE
    assert alone.detail["pinned"] == []
    refused_stat(monkeypatch, "AGENTS-shape.md")
    row = module.check_agent_files(ctx)
    assert row.reason == f"absent: CLAUDE.md; {cannot('AGENTS-shape.md')}"
    assert row.status == module.FINDING
    assert row.next_command == alone.next_command
    assert row.why == f"{alone.why}. {PERMISSION_WHY}"
    assert row.detail["pinned"] == []
    assert module.verdict_for(ctx, [row]) == ("INVALID (agent-files)", 1)


# --- #1110's twelfth site: a leg's `AGENTS.md` this user cannot read --------

@pytest.mark.parametrize("refuse, reason, error", AGENTS_REFUSALS)
def test_the_advisory_says_nothing_of_a_leg_agents_md_it_cannot_read(
        tmp_path, monkeypatch, refuse, reason, error):
    """`shape_advisory`: `_leg_by_agents_md` read ANY exception as "no leg's
    file", so a leg's `AGENTS.md` this user cannot read was no leg, and
    `read()` advised a single repository. It raises the refused `stat` or
    read now, and `read()` answers `not-answered`, silent, with the line in
    `why` and the `OSError` in `refused`, for the doctor to name."""
    root = leg_clone_here(tmp_path / "Atlas")
    env = no_workspace(tmp_path)
    assert shape_advisory.read(root, env=env).state == shape_advisory.LEG_CLONE
    refuse(monkeypatch)
    with pytest.raises(error):
        shape_advisory._leg_by_agents_md(shape_advisory.Tree(root))
    reading = shape_advisory.read(root, env=env)
    assert reading.state == shape_advisory.NOT_ANSWERED
    assert reading.why == leg_agents_why(reason)
    assert reading.advise is False
    assert reading.leg is None
    assert type(reading.refused) is error


@pytest.mark.parametrize("refuse, reason, error", AGENTS_REFUSALS)
def test_the_doctor_offers_no_way_in_over_a_leg_agents_md_it_cannot_read(
        standard, tmp_path, monkeypatch, refuse, reason, error):
    """The rows of a directory with no manifest, in process, over a clone of
    a leg whose `AGENTS.md` this user cannot read: `what is here` names it
    with the advice for the cause, `the way in` offers neither command and
    points there, `the other way in` and the Triad row are silent, and
    `leg_clone` raises the refusal. On #1144's head the same rows offered
    the adoption and the scaffold, and gave the advice. The read cases are
    a file at mode 000, which `what is here` names by reading it through."""
    module = doctor_module(standard)
    root = leg_clone_here(tmp_path / "Atlas")
    ctx = module.Context(root.resolve())
    is_the_leg(not_a_root_rows(module, ctx), "spec")
    refuse(monkeypatch)
    no_leg_way_in(not_a_root_rows(module, ctx), cannot("AGENTS.md", reason),
                  module.doctor_line(ctx),
                  PERMISSION_WHY if error is PermissionError else OTHER_WHY)
    with pytest.raises(error):
        module.leg_clone(ctx)


def test_an_agents_md_nobody_may_open_is_named_where_there_is_no_git(
        standard, tmp_path, monkeypatch):
    """`what is here` reads `AGENTS.md` through wherever it lists it, so a
    file at mode 000 in a directory that is no repository is named with the
    cure, as #1144 names one linked into a folder at 000 there
    (`test_an_agents_md_linked_into_a_folder_nobody_may_search_is_there`).
    Nothing reads it to choose a way in there, so the way in is still the
    scaffold, and no Triad row is given."""
    module = doctor_module(standard)
    root = tmp_path / "Atlas"
    root.mkdir()
    (root / "AGENTS.md").write_text(rendered_leg_agents("spec"),
                                    encoding="utf-8")
    ctx = module.Context(root.resolve())
    refusing(monkeypatch, "read_bytes", "AGENTS.md",
             PermissionError(errno.EACCES, DENIED))
    rows = not_a_root_rows(module, ctx)
    assert set(rows) == {"naming", "contents", "way-in"}, rows
    assert rows["contents"]["reason"] == AGENTS_LINE
    assert rows["contents"]["why"] == PERMISSION_WHY
    assert rows["way-in"]["detail"]["git_repository"] is False
    assert "setup.sh" in rows["way-in"]["next"], rows["way-in"]
    told_once(rows, AGENTS_LINE)


def test_a_leg_by_its_name_is_one_while_its_agents_md_cannot_be_read(
        standard, tmp_path, monkeypatch):
    """CONTROL, true on #1144's head `89486f69` as here: a folder named
    `Orbit-spec` is a leg by its NAME, a declared fact that needs no
    `AGENTS.md`, so a leg's `AGENTS.md` this user cannot read leaves it the
    leg its name says -- `named as`, the hedge for a name -- and `the way in`
    is the leg's row, with no command and no scaffold. `what is here` still
    names the file with the cure. It holds `_read`'s turn to the name when
    the file is refused, rather than `not-answered`."""
    module = doctor_module(standard)
    root = leg_clone_here(tmp_path / "Orbit-spec")
    ctx = module.Context(root.resolve())
    refused_stat(monkeypatch, "AGENTS.md")
    reading = shape_advisory.read(root, env=no_workspace(tmp_path))
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "name", reading.leg
    rows = not_a_root_rows(module, ctx)
    assert set(rows) == {"naming", "contents", "way-in", "triad-advisory"}, \
        rows
    assert "AS A LEG" in rows["way-in"]["reason"], rows["way-in"]
    assert rows["way-in"]["next"] is None, rows["way-in"]
    assert ("`Orbit-spec` is named as the spec leg of `Orbit`"
            in rows["triad-advisory"]["reason"]), rows["triad-advisory"]
    assert module.leg_clone(ctx) is True
    told_once(rows, AGENTS_LINE)


@pytest.mark.parametrize("kind", ["dangling", "gone-before-it-is-read",
                                  "loop"])
def test_an_agents_md_that_is_not_there_is_no_legs_file(
        standard, tmp_path, monkeypatch, kind):
    """CONTROLS, true on #1144's head as here, holding the reader that now
    raises a refused read to #430's other answers: an `AGENTS.md` that is a
    link past a folder that is not there (ENOENT) or to itself (ELOOP), or a
    file whose read finds nothing there (ENOENT, gone after its `stat`), is
    nothing there. No leg's file and no `cannot be read` anywhere: the clone
    is advised and offered both ways in, as one with no `AGENTS.md` is."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    if kind in AGENTS_LINKS:
        symlink(root / "AGENTS.md", AGENTS_LINKS[kind])
    else:
        (root / "AGENTS.md").write_text(rendered_leg_agents("spec"),
                                        encoding="utf-8")
        refusing(monkeypatch, "read_bytes", "AGENTS.md",
                 FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT)))
    assert shape_advisory._leg_by_agents_md(shape_advisory.Tree(root)) is None
    reading = shape_advisory.read(root, env=no_workspace(tmp_path))
    assert reading.state == shape_advisory.ADVISE, reading.as_dict()
    offered_both_ways_in(module, module.Context(root.resolve()))


@pytest.mark.parametrize("kind", ["directory", "named-pipe"])
def test_an_agents_md_that_is_no_regular_file_is_listed_and_not_read(
        standard, tmp_path, kind):
    """CONTROLS, true on #1144's head as here, for `read_through`'s one
    guard: it reads a REGULAR file. An `AGENTS.md` that is a directory or a
    named pipe is there and is no file, so `what is here` lists it and reads
    nothing of it, and the advisory, whose `Tree.text` reads a file alone,
    finds no leg's file: the clone is advised and offered both ways in. A
    read of the directory is refused (`Is a directory`), which the row
    would name as a file this user cannot read, and the open of a pipe
    nobody writes to blocks for ever, so the doctor runs as a person runs
    it, and a run past `DOCTOR_SECONDS` fails the row. Nothing here opens
    the pipe in this process."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    if kind == "directory":
        (root / "AGENTS.md").mkdir()
    elif hasattr(os, "mkfifo"):
        os.mkfifo(root / "AGENTS.md")
    else:
        pytest.skip("this platform makes no named pipe")
    rows = doctor_within(standard, root)
    contents = rows["contents"]
    assert contents["reason"] == "a git repository, an AGENTS.md", contents
    assert contents["detail"]["AGENTS.md"] is True
    assert "cannot_be_read" not in contents["detail"], contents
    offers_both_ways_in(module, rows)


def test_what_is_here_reads_through_agents_md_alone(standard, tmp_path,
                                                    monkeypatch):
    """CONTROL, true on #1144's head as here: `AGENTS.md` is the one name
    here whose CONTENT a reader of this directory reads, so it is the one
    `what is here` reads through. Every other name is asked, as it always
    was: in a leg's clone, a `Makefile` whose read is refused is listed like
    any other name, and no row says it cannot be read."""
    module = doctor_module(standard)
    root = leg_clone_here(tmp_path / "Atlas")
    (root / "Makefile").write_text("all:\n", encoding="utf-8")
    ctx = module.Context(root.resolve())
    refusing(monkeypatch, "read_bytes", "Makefile",
             PermissionError(errno.EACCES, DENIED))
    rows = not_a_root_rows(module, ctx)
    contents = rows["contents"]
    assert contents["reason"] == ("a git repository, an AGENTS.md, "
                                  "a Makefile"), contents
    assert contents["detail"]["Makefile"] is True
    for row in rows.values():
        assert "cannot be read" not in row["reason"], row
    is_the_leg(rows, "spec")


@pytest.mark.parametrize("encode", [
    pytest.param(lambda text: text.encode("utf-8") + b"caf" + bytes([0xE9])
                 + b"\n", id="a-legacy-byte-after-the-opening"),
    pytest.param(lambda text: text.encode("utf-16"), id="utf-16"),
])
def test_a_leg_agents_md_that_is_not_utf8_declares_no_leg(standard, tmp_path,
                                                          encode):
    """THE DECISION FOR A FILE THAT IS READ AND IS NOT UTF-8, true on #1144's
    head as here: no leg's file. A leg's `AGENTS.md` is its template rendered
    as UTF-8, and bytes that do not decode are not that text; none of them is
    salvaged, as no part of an origin URL that is not UTF-8 is (#385). It is
    not #1110's case: nothing was refused, `what is here` reads the file, and
    the clone is advised and offered both ways in. A leg's opening kept intact
    ahead of a byte in a legacy code page is read so too: the PR's known
    limit."""
    module = doctor_module(standard)
    root = repository_here(tmp_path / "Atlas")
    (root / "AGENTS.md").write_bytes(encode(rendered_leg_agents("spec")))
    assert shape_advisory._leg_by_agents_md(shape_advisory.Tree(root)) is None
    reading = shape_advisory.read(root, env=no_workspace(tmp_path))
    assert reading.state == shape_advisory.ADVISE, reading.as_dict()
    offered_both_ways_in(module, module.Context(root.resolve()))


def test_a_failure_the_leg_reader_does_not_expect_is_silence_not_advice(
        tmp_path, monkeypatch):
    """Anything `Tree.text` raises that is neither an `OSError` nor bytes
    that are not UTF-8 -- a git that cannot give the commit's blob, which
    `adopt-project.py`'s reading of a commit can meet -- is not expected by
    `_leg_by_agents_md`, and ends in `read()`'s net: `not-answered`, silent,
    with the exception's name, where no name says it is a leg (the row
    after). On #1144's head it was "no leg's file", and the advice. No
    `OSError` was refused, so `refused` is None."""
    root = leg_clone_here(tmp_path / "Atlas")
    real = shape_advisory.Tree.text

    def text(self, rel):
        if rel == "AGENTS.md":
            raise shape_advisory.Refusal("git-failed",
                                         "git could not give the blob")
        return real(self, rel)

    monkeypatch.setattr(shape_advisory.Tree, "text", text)
    reading = shape_advisory.read(root, env=no_workspace(tmp_path))
    assert reading.state == shape_advisory.NOT_ANSWERED, reading.as_dict()
    assert reading.why == ("the advisory could not be read here (Refusal), "
                           "so it says nothing")
    assert reading.refused is None


def test_a_leg_by_its_name_is_one_while_git_cannot_give_its_agents_md(
        tmp_path, monkeypatch):
    """CONTROL, true on #1144's head as here: `adopt-project.py` reads a
    leg's `AGENTS.md` out of the commit its plan is written against, and
    where git cannot give that blob (a `Refusal` from `cat-file blob`), a
    folder NAMED as a leg is still that leg, as it is where the disk's file
    is refused (the row `..._by_its_name_is_one_while_its_agents_md_cannot_
    be_read`), so `plan` and `check` print the leg's note. With no such
    name, the reading is `not-answered` (the row above)."""
    root = leg_clone_here(tmp_path / "Orbit-spec")
    git("add", "-A", "--", ".", cwd=root)
    git("commit", "-q", "-m", "Initial import", cwd=root)
    commit = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    env = no_workspace(tmp_path)
    committed = shape_advisory.read(root, env=env, commit=commit)
    assert committed.leg["by"] == "agents", committed.as_dict()
    real = shape_advisory.git_out

    def git_out(args, *rest, **kwargs):
        if args[:2] == ["cat-file", "blob"] and args[-1].endswith(
                ":AGENTS.md"):
            raise shape_advisory.Refusal("git-failed",
                                         "git could not give the blob")
        return real(args, *rest, **kwargs)

    monkeypatch.setattr(shape_advisory, "git_out", git_out)
    reading = shape_advisory.read(root, env=env, commit=commit)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "name", reading.leg
    assert reading.leg["role"] == "spec", reading.leg


def test_adopts_reader_reads_the_commits_agents_md_and_never_the_disks(
        tmp_path, monkeypatch):
    """`adopt-project.py` asks the advisory of the commit its plan is written
    against (`commit=`), and reads a leg's `AGENTS.md` out of that commit's
    objects: refused on the disk, the committed file is still the leg's, so
    `plan` and `check` print the leg's NOTE and offer nothing over the
    disk's file, on #1144's head as here. The disk, which the doctor reads,
    is `not-answered`."""
    root = leg_clone_here(tmp_path / "Atlas")
    git("add", "-A", "--", ".", cwd=root)
    git("commit", "-q", "-m", "Initial import", cwd=root)
    commit = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    env = no_workspace(tmp_path)
    refused_stat(monkeypatch, "AGENTS.md")
    reading = shape_advisory.read(root, env=env, commit=commit)
    assert reading.state == shape_advisory.LEG_CLONE, reading.as_dict()
    assert reading.leg["by"] == "agents", reading.leg
    assert (shape_advisory.read(root, env=env).state
            == shape_advisory.NOT_ANSWERED)
