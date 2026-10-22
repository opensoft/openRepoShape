# SPDX-License-Identifier: Apache-2.0
"""A path in the root this user cannot reach is named by the doctor, and the
verdict follows the rows: #430's slice C (`shape-doctor.py` and
`scripts/shape_advisory.py`).

THE DEFECT. Up to Python 3.13 `Path.is_file()`, `is_dir()` and `exists()`
raise a `stat` the operating system refuses; from 3.14 they answer False to
any `OSError`. The doctor asked them of the root's own paths, so one tree gave
two wrong answers (measured on main `50178305`, Python 3.12.3 and a 3.14-like
shim):

  * `scripts/` at 444: the `manifest` and `pins` rows `could not be run:
    [Errno 13] ...` on 3.12; on 3.14 `validator_for` took the project's own
    `scripts/validate-manifest.py` for a copy the root lacks and ran the
    standard's TEMPLATE in its place: `ok manifest the standard's
    templates/assembly-root/scripts/validate-manifest.py passes`;
  * a leg mount at 000: the `legs`, `leg shape files` and `placement` rows
    `could not be run`, and the verdict `DRIFTED (1 leg(s) not at the pin)`
    beside them, on both, because `drifted_reasons` counted a red `legs` row
    with no leg in it as one leg off its pin; at 444, on 3.14, `spec:
    populated, but with no .git of its own` and every leg file `absent`;
  * a holder's `members/` at 000: `DRIFTED (a member is not at its pin)`
    with the `members` row `could not be run` on 3.12, and `members/IRRS: not
    populated -- the pinned copy is an unbootstrapped submodule` on 3.14;
  * the root at 000 or 444: a traceback on 3.12, `NOT A SHAPE ROOT` on 3.14;
    a directory above it at 000: a traceback, or `REFUSED
    shape-doctor-root-missing: ... is not a directory on this machine`.

Each is now one answer on every Python: the path, in `validate-pins.py`'s
words (`<path>: cannot be read (<reason>)`, or `cannot be listed` for a
folder), this doctor again as the NEXT and the gate's advice as the WHY; the
verdict is INVALID naming the red rows and never DRIFTED; and a root this user
cannot search is refused by name, exit 3, before any row.

NOT HERE: the `shape currency` row's `copy-missing` under 3.14 for a `scripts/`
or a `.github/workflows/` this user cannot search comes from
`update-shape.py`'s comparison, which #430's slice B fixes. No test here
depends on it, so none asserts the verdict of those two cells.

TWO KINDS OF CASE, as `tests/test_doctor_unreadable_pin.py` (#847) has them.
The MODE cases change a real mode and run the doctor as a person does; they
skip on Windows and as root (`CANNOT_RUN_AS_ROOT`), and restore the mode in a
`finally` (`mode_of`). The STAND-IN cases put the refusal in by hand, in
process, so they run everywhere: `refused_stat` (#383), which also answers
`is_file()` as Python 3.14 does, and `refusing` (#847) for a read or a
listing. Each fix is held by a case of each kind where both can reach it.

NOTHING HERE REACHES A NETWORK: the doctor's own fixtures, a scaffold into
local bare remotes, and the session's `gh` guard for the `machine` row.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from conftest import REPO, git, load_without_bytecode
#: #827's stand-in for a `stat` the operating system refuses, from the file
#: that owns it (#383).
from test_bump_leg_unopenable import refused_stat
#: A private copy of the session's holder, from the file that owns the
#: `members` row's tests.
from test_doctor_legs_members_next import holder_copy
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: #847's helpers and the gate's advice, word for word, from the file that
#: owns them.
from test_doctor_unreadable_pin import (
    DENIED, GATE, IO_ERROR, OTHER_FOLDER_WHY, OTHER_WHY, PERMISSION_WHY,
    cannot, doctored, in_process, refusing,
)
#: The doctor's fixtures, from the module that owns them.
from test_shape_doctor import (  # noqa: F401
    FAMILY_MEMBER, doctor, holder, project, scaffolded_here, standard,
)
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it.
from test_validate_pins_unreadable_workflows_dir import mode_of
#: A `stat` refused at one path, from the file that owns it (#1146).
from test_root_git_unreadable import as_python_314

sys.path.insert(0, str(REPO / "scripts"))
import shape_advisory  # noqa: E402

MANIFEST_GATE = "scripts/validate-manifest.py"
MANIFEST_TEMPLATE = "templates/assembly-root/scripts/validate-manifest.py"
PINS_GATE = "scripts/validate-pins.py"
MEMBER = f"members/{FAMILY_MEMBER}"
#: What every row said of a path it could not reach, and what none may say.
COULD_NOT_RUN = "could not be run"
#: The `members` row's words for an empty mount, which a member this user
#: cannot reach is not.
UNBOOTSTRAPPED = "not populated -- the pinned copy is an unbootstrapped"


def listed(named: str, reason: str = DENIED) -> str:
    """The gate's line for a folder it cannot list (#434)."""
    return f"{named}: cannot be listed ({reason})"


def unread_mount(line: str) -> str:
    """The `legs` and `members` rows' words for a mount this user cannot
    reach, after the gate's line for it."""
    return f"{line}, so no HEAD in it is compared with the pin"


def unread_gate(own: str, reason: str = DENIED) -> str:
    """A validator row's words for an own copy this user cannot reach."""
    return (f"{cannot(own, reason)}, so the project's own gate was not run, "
            "and the standard's copy is not run in its place")


def assert_nothing_could_not_run(rows: dict) -> None:
    """No row says it could not be run."""
    for row in rows.values():
        assert COULD_NOT_RUN not in row["reason"], row


# --- the mode cases: a real mode, the doctor run as a person runs it ---------

@CANNOT_RUN_AS_ROOT
def test_an_own_gate_this_user_cannot_reach_is_named_never_the_template(
        standard, project):
    """`scripts/` at 444: each validator row names the project's own copy it
    cannot reach, and the standard's template is never run in its place, so
    no row says `passes`. The verdict is not asserted: on 3.14 the `shape
    currency` row's `copy-missing` is slice B's (`update-shape.py`)."""
    denied = os.strerror(errno.EACCES)
    again = doctor_again(standard, project)
    with mode_of(project, "scripts", 0o444):
        rows, verdict = doctored(standard, project)
    for row_id, own in (("manifest", MANIFEST_GATE), ("pins", PINS_GATE)):
        row = rows[row_id]
        assert row["status"] == "FINDING", row
        assert row["reason"] == unread_gate(own, denied)
        assert row["next"] == again
        assert row["why"] == PERMISSION_WHY
        assert row["detail"]["own_copy"] is True, row
        assert row["detail"]["cannot_be_read"] == cannot(own, denied)
    assert not verdict.startswith("COMPLIANT"), verdict
    assert_nothing_could_not_run(rows)


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("bits, line", [
    pytest.param(0, listed("spec", os.strerror(errno.EACCES)), id="spec-000"),
    pytest.param(0o444, cannot("spec/.git", os.strerror(errno.EACCES)),
                 id="spec-r--"),
])
def test_a_leg_mount_this_user_cannot_reach_is_named_and_no_drift(
        standard, project, bits, line):
    """The verdict bug: a leg mount at 000 made `legs`, `leg shape files`
    and `placement` say `could not be run`, and the verdict DRIFTED. Each
    row names the mount, the leg carries the line, and the verdict is the
    gate's INVALID: `validate-pins.py` refuses `spec/.git` by name."""
    again = doctor_again(standard, project)
    with mode_of(project, "spec", bits):
        rows, verdict = doctored(standard, project)
    legs = rows["legs"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == unread_mount(line)
    assert legs["detail"]["legs"][0]["mount_cannot_be_read"] == line
    assert legs["next"] == again
    assert legs["why"] == PERMISSION_WHY
    shape_files, placement = rows["leg-shape-files"], rows["placement"]
    assert shape_files["status"] == "note", shape_files
    assert shape_files["reason"].startswith(f"{line}; code: "), shape_files
    assert shape_files["next"] is None, shape_files
    assert placement["status"] == "note", placement
    assert f": {line}; code: " in placement["reason"], placement
    assert verdict == "INVALID (pins)"
    assert_nothing_could_not_run(rows)


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("relative, bits, line", [
    pytest.param("members", 0, cannot(MEMBER, os.strerror(errno.EACCES)),
                 id="members-000"),
    pytest.param(MEMBER, 0, listed(MEMBER, os.strerror(errno.EACCES)),
                 id="member-000"),
    pytest.param(MEMBER, 0o444,
                 cannot(f"{MEMBER}/.git", os.strerror(errno.EACCES)),
                 id="member-r--"),
])
def test_a_member_this_user_cannot_reach_is_named_and_no_drift(
        standard, holder, tmp_path, relative, bits, line):
    """A holder's `members/`, or a member's mount, this user cannot search:
    the `members` row names the mount where 3.12 said `could not be run` and
    3.14 called it unbootstrapped, and the verdict is the `family` row's
    INVALID, never a member off its pin."""
    root = holder_copy(holder, tmp_path)
    with mode_of(root, relative, bits):
        rows, verdict = doctored(standard, root)
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert members["reason"] == unread_mount(line)
    assert members["detail"]["members"][0]["mount_cannot_be_read"] == line
    assert members["next"] == doctor_again(standard, root)
    assert members["why"] == PERMISSION_WHY
    assert UNBOOTSTRAPPED not in members["reason"]
    assert verdict == "INVALID (family)"
    assert_nothing_could_not_run(rows)


def root_refusal(root: Path, reason: str) -> str:
    """The first line of the doctor's refusal of a root it cannot search."""
    return (f"REFUSED shape-doctor-root-unreadable: --root {root}: cannot be "
            f"read ({reason})")


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("above, bits", [
    pytest.param(False, 0, id="root-000"),
    pytest.param(False, 0o444, id="root-r--"),
    pytest.param(True, 0, id="above-000"),
])
def test_a_root_this_user_cannot_search_is_refused_by_name(
        standard, project, above, bits):
    """A root this user cannot search, or one under a directory it cannot
    search: one refusal, exit 3, before any row, naming the root and the
    cure. It was a traceback on 3.12, and on 3.14 `NOT A SHAPE ROOT` or
    `shape-doctor-root-missing`."""
    target = project.parent if above else project
    with mode_of(target, ".", bits):
        result = doctor(standard, project, "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    assert result.stdout == "", result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    lines = result.stderr.splitlines()
    assert lines[0] == root_refusal(project, os.strerror(errno.EACCES))
    assert "chmod u+rx" in lines[1], lines
    assert lines[1].endswith("Then run this doctor again"), lines


@CANNOT_RUN_AS_ROOT
def test_a_root_this_user_can_search_and_not_list_is_not_refused(
        standard, project):
    """The control: only SEARCH is asked. A root at 111 is read through
    names the doctor already knows, and it was COMPLIANT on both Pythons."""
    with mode_of(project, ".", 0o111):
        result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "shape-doctor-root" not in result.stderr, result.stderr


# --- the stand-in cases: in process, on every platform and as root ----------

def test_validator_for_raises_a_refused_stat_and_names_the_own_copy(
        standard, project, monkeypatch):
    """`validator_for` with the own copy's `stat` refused, as 3.14's
    `is_file()` would answer it: it raises, and the `manifest` row names the
    copy rather than running the standard's template in its place."""
    module, ctx = in_process(standard, project)
    refused_stat(monkeypatch, "validate-manifest.py")
    with pytest.raises(PermissionError):
        module.validator_for(ctx, MANIFEST_GATE, MANIFEST_TEMPLATE)
    row = module.check_manifest(ctx)
    assert row.status == module.FINDING
    assert row.reason == unread_gate(MANIFEST_GATE)
    assert row.next_command == doctor_again(standard, project)
    assert row.why == PERMISSION_WHY
    assert row.detail["own_copy"] is True, row.detail
    assert row.detail["exit"] is None, row.detail


def test_another_reason_for_the_own_copy_gets_the_other_advice(
        standard, project, monkeypatch):
    """A `stat` of the own copy refused for a reason that is no permission:
    the system's reason, and the gate's other advice."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "stat", "validate-pins.py",
             OSError(errno.EIO, IO_ERROR))
    row = module.check_pins(ctx)
    assert row.reason == unread_gate(PINS_GATE, IO_ERROR)
    assert row.why == OTHER_WHY


def test_an_own_copy_that_is_not_there_still_falls_back_to_the_template(
        standard, project):
    """The control: a root that lacks its own copy is given the standard's
    template, as before."""
    module, ctx = in_process(standard, project)
    (project / MANIFEST_GATE).unlink()
    used, which, own_copy = module.validator_for(ctx, MANIFEST_GATE,
                                                 MANIFEST_TEMPLATE)
    assert own_copy is False
    assert which == f"the standard's {MANIFEST_TEMPLATE}"
    assert used == ctx.shape / MANIFEST_TEMPLATE


def test_no_lockstep_line_is_named_for_a_gate_this_user_cannot_reach(
        standard, project, monkeypatch):
    """`gate_line` names no line for an own copy it cannot reach, so the
    `legs` row's lockstep NEXT and the `agent files` confirm clause say
    nothing of a gate that cannot run, and no row ends in a traceback."""
    module, ctx = in_process(standard, project)
    refused_stat(monkeypatch, "validate-pins.py")
    used, own_copy, command = module.gate_line(ctx, module.PINS_GATE)
    assert command is None
    assert own_copy is True
    assert used == ctx.root / PINS_GATE
    assert module.confirm_digest(ctx) == ""


def test_an_unloaded_manifest_names_an_own_gate_it_cannot_reach(
        standard, project, monkeypatch):
    """A `project.yaml` that does not load beside an own gate this user
    cannot reach: the row quotes the manifest's refusal and names the gate's
    copy, and runs nothing."""
    module = in_process(standard, project)[0]
    manifest = project / "project.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8") + "\tbad: tab\n",
                        encoding="utf-8")
    ctx = module.Context(project.resolve())
    assert ctx.manifest_refusal is not None
    refused_stat(monkeypatch, "validate-manifest.py")
    row = module.check_manifest(ctx)
    assert row.status == module.FINDING
    assert row.reason.startswith("project.yaml does not load: "), row.reason
    assert row.reason.endswith("; " + unread_gate(MANIFEST_GATE)), row.reason
    assert row.next_command == doctor_again(standard, project)
    assert row.why == PERMISSION_WHY


@pytest.mark.parametrize("refuse, line, why", [
    pytest.param(lambda patch: refused_stat(patch, "spec"),
                 cannot("spec"), PERMISSION_WHY, id="mount-stat"),
    pytest.param(lambda patch: refusing(
        patch, "iterdir", "spec", PermissionError(errno.EACCES, DENIED)),
        listed("spec"), PERMISSION_WHY, id="mount-listing"),
    pytest.param(lambda patch: refusing(
        patch, "iterdir", "spec", OSError(errno.EIO, IO_ERROR)),
        listed("spec", IO_ERROR), OTHER_FOLDER_WHY, id="listing-io-error"),
])
def test_a_leg_mount_refused_is_named_on_every_python(
        standard, project, monkeypatch, refuse, line, why):
    """The `legs` row for a mount whose `stat` or listing is refused: named
    in the gate's words, no checkout and no lockstep line, the advice for
    the cause, and no drift."""
    module, ctx = in_process(standard, project)
    refuse(monkeypatch)
    legs = module.check_legs(ctx)
    assert legs.reason == unread_mount(line)
    assert legs.detail["legs"][0]["mount_cannot_be_read"] == line
    assert legs.next_command == doctor_again(standard, project)
    assert legs.why == why
    assert module.drifted_reasons({"legs": legs}, {}) == []


def test_a_mount_whose_git_cannot_be_reached_is_not_one_without_a_git(
        standard, project, monkeypatch):
    """A mount this user can list and not search: its `.git`'s `stat` is
    refused, which 3.14 answered as "no `.git` of its own", and the row sent
    a checkout over it. Every row that reads the mount says the same line.
    Only the legs' `.git` is refused: the root's own is #1146's case, which
    the `legs` row names once, before any leg."""
    module, ctx = in_process(standard, project)
    as_python_314(monkeypatch, {
        ctx.root / leg / ".git": PermissionError(errno.EACCES, DENIED)
        for leg in ("spec", "code")})
    legs = module.check_legs(ctx)
    shape_files = module.check_leg_shape_files(ctx)
    placement = module.check_placement(ctx)
    spec, code = cannot("spec/.git"), cannot("code/.git")
    assert legs.reason == f"{unread_mount(spec)}; {unread_mount(code)}"
    assert legs.next_command == doctor_again(standard, project)
    assert shape_files.status == module.NOTE
    assert shape_files.reason == f"{spec}; {code}"
    assert placement.status == module.NA
    assert placement.reason.endswith(f"{spec}; {code}"), placement.reason


def test_beside_a_checkout_line_the_unread_mount_gets_the_advice(
        standard, project, monkeypatch):
    """One leg's mount cannot be listed, and the other leg has a commit past
    its pin while its gitlink is at the pin: the checkout line is the NEXT
    for that leg, and its why ends on the advice for the mount."""
    module, ctx = in_process(standard, project)
    git("commit", "-q", "--allow-empty", "-m", "past its pin",
        cwd=project / "code")
    refusing(monkeypatch, "iterdir", "spec",
             PermissionError(errno.EACCES, DENIED))
    legs = module.check_legs(ctx)
    assert legs.next_command.endswith(" -- code"), legs.next_command
    assert legs.why.endswith(". " + PERMISSION_WHY), legs.why


def test_a_member_mount_refused_is_named_on_every_python(
        standard, holder, tmp_path, monkeypatch):
    """The `members` row for a member whose mount's `stat` is refused (a
    `members/` this user cannot search): named, no bootstrap line, the
    advice, and no drift."""
    root = holder_copy(holder, tmp_path)
    module, ctx = in_process(standard, root)
    refused_stat(monkeypatch, FAMILY_MEMBER)
    members = module.check_members(ctx)
    # First, and alone among the row's findings: the stand-in refuses the
    # `stat` of `../IRRS` beside the holder too, which the row then says
    # stands there, as "not what fails this row".
    assert members.reason.split("; ")[0] == unread_mount(cannot(MEMBER))
    assert members.next_command == doctor_again(standard, root)
    assert members.why == PERMISSION_WHY
    assert module.drifted_reasons({"members": members}, {}) == []


def test_a_leg_file_this_user_cannot_read_is_said_not_called_absent(
        standard, project, monkeypatch):
    """A leg's shape file whose `stat`, or whose read, is refused is `cannot
    be read`, never `absent` with a copy over it: the row is a `note`."""
    module, ctx = in_process(standard, project)
    refused_stat(monkeypatch, ".gitignore")
    refusing(monkeypatch, "read_bytes", "CLAUDE.md",
             PermissionError(errno.EACCES, DENIED))
    row = module.check_leg_shape_files(ctx)
    files = row.detail["legs"]["spec"]["files"]
    assert files[".gitignore"] == f"cannot be read ({DENIED})"
    assert files["CLAUDE.md"] == f"cannot be read ({DENIED})"
    assert row.status == module.NOTE
    assert row.next_command is None
    assert "absent" not in row.reason, row.reason


def test_a_bootstrap_this_user_cannot_reach_cannot_run_on_every_python(
        standard, project, monkeypatch):
    """`own_bootstrap` asks whether the root's own bootstrap can RUN: a
    refused `stat` is "no", where 3.12 raised it out of the row."""
    module, ctx = in_process(standard, project)
    assert module.own_bootstrap(ctx.root) is True
    refusing(monkeypatch, "stat", "bootstrap.py",
             PermissionError(errno.EACCES, DENIED))
    assert module.own_bootstrap(ctx.root) is False


def legs_over_a_kept_repository(module, ctx):
    """The `legs` row over a `spec` with files and no `.git` of its own,
    whose repository git kept: `checkout_reach` asks that repository for a
    `modules/` of its own."""
    (ctx.root / "spec" / ".git").unlink()
    return module.check_legs(ctx)


@pytest.mark.parametrize("names, ask", [
    pytest.param(("modules",),
                 lambda module, ctx: module.keeps_modules(ctx.root / "spec"),
                 id="keeps_modules"),
    pytest.param(("spec",),
                 lambda module, ctx: module.kept_gitdir(ctx.root, "spec"),
                 id="kept_gitdir"),
    pytest.param(("modules",), legs_over_a_kept_repository,
                 id="checkout_reach"),
])
def test_a_git_directory_this_user_cannot_reach_is_raised(
        standard, project, monkeypatch, names, ask):
    """The reads of a repository's git directory raise a refused `stat`,
    which `run_checks` names, where 3.14 called a kept repository this user
    cannot reach gone, or one with no `modules/`."""
    module, ctx = in_process(standard, project)
    refused_stat(monkeypatch, *names)
    with pytest.raises(PermissionError):
        ask(module, ctx)


def test_a_root_whose_stat_is_refused_is_refused_on_every_python(
        standard, project, monkeypatch, capsys):
    """The root's own `stat` refused, as under a folder this user cannot
    search, in process: 3.14's `is_dir()` answered no directory, and the
    doctor said `shape-doctor-root-missing`. It is the same refusal by name
    as a root it cannot search, on every Python."""
    module = in_process(standard, project)[0]
    refused_stat(monkeypatch, project.name)
    code = module.main(["--root", str(project)])
    err = capsys.readouterr().err
    assert code == 3
    assert err.splitlines()[0] == root_refusal(project, DENIED)
    assert "shape-doctor-root-missing" not in err


def test_a_refused_read_out_of_a_check_is_named_by_run_checks(
        standard, project):
    """An `OSError` out of a check: a refused read of a path inside the root
    is the row's FINDING in the gate's words; any other keeps `could not be
    run`."""
    module, ctx = in_process(standard, project)
    inside = PermissionError(errno.EACCES, DENIED, str(ctx.root / "spec"))
    elsewhere = PermissionError(errno.EACCES, DENIED, "/elsewhere/x")

    def raising(error):
        def run(_ctx):
            raise error
        return run

    module.CHECKS = (
        module.Check("legs", "legs", (module.PROJECT,), raising(inside)),
        module.Check("members", "members", (module.PROJECT,),
                     raising(elsewhere)))
    named, other = module.run_checks(ctx)
    assert named.reason == cannot("spec")
    assert named.next_command == doctor_again(standard, project)
    assert named.why == PERMISSION_WHY
    assert named.detail == {"cannot_be_read": cannot("spec"), "path": "spec"}
    assert other.reason.startswith(f"{COULD_NOT_RUN}: "), other.reason


# --- the verdict ------------------------------------------------------------

def test_a_row_that_could_not_be_run_is_invalid_never_drift(standard,
                                                            project):
    """A `legs` or `members` row with no entry in it, which is what
    `run_checks` makes of a check that raised, is no leg off its pin: the
    verdict is INVALID naming it. A leg that is off its pin still is."""
    module, ctx = in_process(standard, project)
    for row_id in ("legs", "members"):
        raised = module.Row(row_id, row_id, module.FINDING,
                            f"{COULD_NOT_RUN}: [Errno 13] {DENIED}", None, {})
        assert module.verdict_for(ctx, [raised]) == (
            f"INVALID ({row_id})", 1)
    off = module.Row("legs", "legs", module.FINDING, "off", None,
                     {"legs": [{"head": "1" * 40, "pin": "2" * 40}]})
    assert module.verdict_for(ctx, [off]) == (
        "DRIFTED (1 leg(s) not at the pin)", 1)


def test_a_member_this_user_cannot_reach_is_no_drift_beside_one_that_is(
        standard, holder, tmp_path, monkeypatch):
    """The `members` row is drift for the members it could read and found
    wrong, and for no other."""
    root = holder_copy(holder, tmp_path)
    module, ctx = in_process(standard, root)
    refused_stat(monkeypatch, FAMILY_MEMBER)
    members = module.check_members(ctx)
    entries = members.detail["members"]
    assert module.drifted_reasons({"members": members}, {}) == []
    moved = dict(entries[0])
    del moved["mount_cannot_be_read"]
    moved.update({"populated": True, "own_git": True, "head": "1" * 40,
                  "pin": "2" * 40})
    members.detail["members"] = [*entries, moved]
    assert module.drifted_reasons({"members": members}, {}) == [
        "a member is not at its pin"]


# --- scripts/shape_advisory.py ---------------------------------------------

def test_a_record_this_user_cannot_reach_silences_nothing_on_every_python(
        tmp_path, monkeypatch):
    """`Tree.kind` asks the operating system: a refused `stat` of
    `single-repository.yaml` raises, and the record is "there and could not
    be read", which silences nothing and says why, where 3.14 called it
    absent and said nothing."""
    (tmp_path / shape_advisory.RECORD_FILE).write_text("kind: x\n")
    refused_stat(monkeypatch, shape_advisory.RECORD_FILE)
    with pytest.raises(PermissionError):
        shape_advisory.Tree(tmp_path).kind(shape_advisory.RECORD_FILE)
    state, why, _notes = shape_advisory.read_record(tmp_path)
    assert state == shape_advisory.RECORD_SILENCES_NOTHING
    assert why == ["it could not be read (PermissionError)"]


@CANNOT_RUN_AS_ROOT
def test_a_record_in_a_folder_this_user_cannot_search(tmp_path):
    """The same, under a real mode: a folder this user can list and not
    search."""
    folder = tmp_path / "single"
    folder.mkdir()
    (folder / shape_advisory.RECORD_FILE).write_text("kind: x\n")
    with mode_of(tmp_path, "single", 0o444):
        state, why, _notes = shape_advisory.read_record(folder)
    assert state == shape_advisory.RECORD_SILENCES_NOTHING
    assert why == ["it could not be read (PermissionError)"]


def test_a_record_that_is_not_there_is_still_absent(tmp_path):
    """The control: no file, or a name under a file, is absent."""
    assert shape_advisory.Tree(tmp_path).kind("nothing.yaml") is None
    (tmp_path / "plain").write_text("x\n")
    assert shape_advisory.Tree(tmp_path).kind("plain/inside") is None
    assert shape_advisory.Tree(tmp_path).kind("plain") == "file"
    assert shape_advisory.Tree(REPO).kind("scripts") == "dir"
    assert shape_advisory.read_record(tmp_path)[0] == \
        shape_advisory.RECORD_ABSENT


def test_the_advisory_calls_nothing_there_what_the_gate_calls_so():
    """`shape_advisory.py`'s `_ABSENT_ERRNOS` and `_ABSENT_WINERRORS` are
    the gate's and the doctor's (#430's rule: one errno set)."""
    gate = load_without_bytecode(GATE, "gate_unreadable_paths_parity")
    assert (shape_advisory._ABSENT_ERRNOS, shape_advisory._ABSENT_WINERRORS) \
        == (gate._ABSENT_ERRNOS, gate._ABSENT_WINERRORS)
