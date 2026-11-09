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

#1175 BUILDS THE BRANCHES NO CASE REACHED: a leg with no gitlink over a mount
this user cannot reach, and a member it cannot reach beside one a checkout
cures, by the holder's own bootstrap and by the git line. And the `leg shape
files` note for a leg file it cannot read now carries the gate's advice as
its WHY, as every other path here does.

#1174 ASKS A MOUNT'S GIT DIRECTORY TOO, as `validate-pins.py` asks it (#968).
A leg's or a member's git directory this user cannot search -- the one its
gitfile names under `.git/modules/`, or a `.git` that is a directory of its
own -- or a gitfile it cannot open made git fail in the mount, so the `legs`
or `members` row read no HEAD and the verdict was DRIFTED for a mount at its
pin, and `placement` called the leg not a git repository; for a `.git`
directory git read the ROOT's HEAD as the leg's, and a checkout was named
over it. Each of those rows now names the directory as the gate does, and
the verdict is the gate's INVALID. The `leg shape files` row runs no git, so
it still compares the files of such a leg.

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
#: A private copy of the session's holder, and the ways a leg or a member can
#: be wrong, from the file that owns the `legs` and `members` rows' tests.
from test_doctor_legs_members_next import (
    add_member_row, holder_copy, holder_without, make_no_gitlink,
    member_unbootstrapped,
)
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: #847's helpers and the gate's advice, word for word, from the file that
#: owns them.
from test_doctor_unreadable_pin import (
    DENIED, GATE, IO_ERROR, OTHER_FOLDER_WHY, OTHER_WHY, PERMISSION_WHY,
    cannot, doctored, in_process, refusing, sources,
)
#: The doctor's fixtures, from the module that owns them.
from test_shape_doctor import (  # noqa: F401
    FAMILY_MEMBER, doctor, holder, project, record_gitlink, scaffolded_here,
    standard,
)
#: A leg whose `.git` is a git directory of its own, from the file that owns
#: the gate's cases for one (#968).
from test_validate_pins_spelled_and_named import leg_with_its_own_git_directory
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
#: A second member, which the cases beside a checkout make unreachable.
GHOST = "members/Ghost"
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


def with_a_member_beside_one_a_checkout_cures(root: Path) -> None:
    """A holder with TWO members (#1175): `Ghost`, at the first one's
    commit, with a `.gitmodules` section that gives its path and the first
    one's url and an empty mount that each case makes unreachable; and the
    first member emptied, so a checkout cures it and the row names a line.
    The session's holder has one member, so no other case needs one."""
    add_member_row(root, "Ghost")
    record_gitlink(root, GHOST, git("rev-parse", f"HEAD:{MEMBER}",
                                    cwd=root).stdout.strip())
    url = git("config", "-f", ".gitmodules", f"submodule.{MEMBER}.url",
              cwd=root).stdout.strip()
    for key, value in (("path", GHOST), ("url", url)):
        git("config", "-f", ".gitmodules", f"submodule.{GHOST}.{key}", value,
            cwd=root)
    (root / GHOST).mkdir()
    member_unbootstrapped(root)


def beside_the_checkout(module, why: str) -> bool:
    """Whether a `members` row's why ends as it must beside a member this
    user cannot reach: the sentence that the next run names what the line
    leaves (`rerun_sentence`, which only the refusal asks for here), then
    the gate's advice. The advice's own "Then run this doctor again" is not
    that sentence, so the two are told apart."""
    return why.endswith(module.rerun_sentence("member") + ". "
                        + PERMISSION_WHY)


def bootstrap_line(module, root: Path) -> str:
    """The holder's own bootstrap, as the `members` row names it."""
    resolved = root.resolve()
    return (f"{module.PYTHON} "
            f"{module.quote_arg(resolved / 'scripts' / 'bootstrap.py')} "
            f"--root {module.quote_arg(resolved)}")


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


#: `(whether the leg's .git is a directory of its own, the path set to the
#: mode, the mode, the line the leg is named by)` for each git directory of a
#: leg this user cannot search, and the gitfile it cannot open: the gate's
#: cells (#968), each the path the gate names (#1174).
GIT_DIR_CELLS = [
    pytest.param(False, ".git/modules/spec", 0, "spec: .git/modules/spec",
                 id="modules-000"),
    pytest.param(False, ".git/modules/spec", 0o444,
                 "spec: .git/modules/spec", id="modules-r--"),
    pytest.param(False, "spec/.git", 0, "spec/.git", id="gitfile-000"),
    pytest.param(True, "spec/.git", 0, "spec/.git", id="git-directory-000"),
    pytest.param(True, "spec/.git", 0o444, "spec/.git",
                 id="git-directory-r--"),
]


def assert_compared(row: dict) -> None:
    """The `leg shape files` row, as `--json` prints it, over legs whose git
    directory this user cannot read (#1174): it compares files on disk and
    runs no git, so each leg's files are compared, as before, the row is
    `ok`, and it has no WHY. The `legs` row names the git directory."""
    assert row["status"] == "ok", row
    assert [leg["state"] for leg in row["detail"]["legs"].values()] == [
        "compared", "compared"], row
    assert row["why"] is None, row


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("own_directory, relative, bits, named",
                         GIT_DIR_CELLS)
def test_a_leg_whose_git_directory_this_user_cannot_search_is_no_drift(
        standard, project, own_directory, relative, bits, named):
    """rv975's cell, `.git/modules/spec` at 000, and the gate's others
    (#968). Each was DRIFTED (#1174): `spec: populated, but git cannot read
    a HEAD in it` with the lockstep gate as its NEXT, or, for a `.git` that
    is a directory, the ROOT's HEAD quoted as the leg's with a checkout over
    it; and `placement` said the leg was no repository. The `legs` and
    `placement` rows now name the path the `pins` row names, after the leg
    where it is outside the mount, no HEAD is read, the NEXT is this doctor
    again, and the verdict is the gate's INVALID. The `leg shape files` row
    reads no git, so it compares the leg's files as it always did."""
    if own_directory:
        leg_with_its_own_git_directory(project)
    denied = os.strerror(errno.EACCES)
    line = cannot(named, denied)
    with mode_of(project, relative, bits):
        rows, verdict = doctored(standard, project)
    assert cannot(relative, denied) in rows["pins"]["reason"], rows["pins"]
    legs = rows["legs"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == unread_mount(line)
    spec = legs["detail"]["legs"][0]
    assert spec["mount_cannot_be_read"] == line
    assert spec["head"] is None, spec
    assert legs["next"] == doctor_again(standard, project)
    assert legs["why"] == PERMISSION_WHY
    assert_compared(rows["leg-shape-files"])
    placement = rows["placement"]["reason"]
    assert f": {line}; code: " in placement, placement
    assert "repository" not in placement, placement
    assert verdict == "INVALID (pins)"
    assert_nothing_could_not_run(rows)


#: The git directory of the session holder's member, where its gitfile
#: says it is.
MEMBER_GIT_DIR = f".git/modules/{MEMBER}"


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("bits", [pytest.param(0, id="000"),
                                  pytest.param(0o444, id="r--")])
def test_a_member_whose_git_directory_this_user_cannot_search_is_no_drift(
        standard, holder, tmp_path, bits):
    """A member's git directory this user cannot search: the `members` row
    said `checked out at ?`, and the verdict was DRIFTED (#1174). It names
    the directory after the member, no HEAD is read, and the verdict is the
    `family` row's INVALID."""
    root = holder_copy(holder, tmp_path)
    line = cannot(f"{MEMBER}: {MEMBER_GIT_DIR}", os.strerror(errno.EACCES))
    with mode_of(root, MEMBER_GIT_DIR, bits):
        rows, verdict = doctored(standard, root)
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert members["reason"] == unread_mount(line)
    entry = members["detail"]["members"][0]
    assert entry["mount_cannot_be_read"] == line
    assert entry["head"] is None, entry
    assert members["next"] == doctor_again(standard, root)
    assert members["why"] == PERMISSION_WHY
    assert verdict == "INVALID (family)"
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


@CANNOT_RUN_AS_ROOT
def test_a_member_at_mode_000_beside_one_a_checkout_cures(standard, holder,
                                                          tmp_path):
    """A member's mount at 000 beside a member the holder's own bootstrap
    cures (#1175): the row names both, the bootstrap is the NEXT, and its why
    ends on the advice for the mount. Up to Python 3.13 the `.gitmodules`
    asked in each member to say what the bootstrap carries raised the
    refused `stat` out of the row, so that member is not asked."""
    root = holder_copy(holder, tmp_path)
    with_a_member_beside_one_a_checkout_cures(root)
    module = in_process(standard, root)[0]
    with mode_of(root, GHOST, 0):
        rows, _verdict = doctored(standard, root)
    members = rows["members"]
    assert members["status"] == "FINDING", members
    assert members["reason"].split("; ")[:2] == [
        f"{MEMBER}: {UNBOOTSTRAPPED} submodule",
        unread_mount(listed(GHOST, os.strerror(errno.EACCES)))]
    assert members["next"] == bootstrap_line(module, root)
    assert beside_the_checkout(module, members["why"]), members["why"]
    assert_nothing_could_not_run(rows)


@CANNOT_RUN_AS_ROOT
def test_a_leg_file_at_mode_000_is_told_the_cure_and_gates_nothing(
        standard, project):
    """`spec/CLAUDE.md` at 000, as rv975 measured it (#1175): the `leg shape
    files` note names the file and has no NEXT, as before, and its why is
    now the gate's advice. The verdict stays COMPLIANT: no leg file gates
    anything, so one nobody could read changes nothing."""
    denied = os.strerror(errno.EACCES)
    with mode_of(project, "spec/CLAUDE.md", 0):
        rows, verdict = doctored(standard, project)
    row = rows["leg-shape-files"]
    assert row["status"] == "note", row
    assert f"spec: AGENTS.md rendered, CLAUDE.md cannot be read ({denied})" \
        in row["reason"], row
    assert row["next"] is None, row
    assert row["why"] == PERMISSION_WHY
    assert verdict == "COMPLIANT"


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


def git_dir_line(leg: str, reason: str = DENIED) -> str:
    """The line for a leg whose gitfile names `.git/modules/<leg>`, outside
    the mount, where the `stat` of that directory's `HEAD` is refused: the
    gate's line after the leg's path (#1174)."""
    return f"{leg}: {cannot(f'.git/modules/{leg}', reason)}"


def refused_head(error: OSError):
    """A stand-in for a git directory this user cannot search: the `stat`
    of the `HEAD` in each one is refused with `error`, except the root's
    own `.git/HEAD`, so the root's repository stays one this user can read
    and each row reaches the mounts (#1174)."""
    def refuse(monkeypatch, root: Path) -> None:
        real = Path.stat
        own = root / ".git" / "HEAD"

        def refused(self, *args, **kwargs):
            if self.name == "HEAD" and self != own:
                raise type(error)(error.errno, error.strerror, str(self))
            return real(self, *args, **kwargs)

        monkeypatch.setattr(Path, "stat", refused)
    return refuse


def refused_gitfile(monkeypatch, _root: Path) -> None:
    """The read of each gitfile `.git` refused (#1174)."""
    refusing(monkeypatch, "read_bytes", ".git",
             PermissionError(errno.EACCES, DENIED))


@pytest.mark.parametrize("refuse, spec, code, why", [
    pytest.param(refused_head(PermissionError(errno.EACCES, DENIED)),
                 git_dir_line("spec"), git_dir_line("code"), PERMISSION_WHY,
                 id="head-stat"),
    pytest.param(refused_head(OSError(errno.EIO, IO_ERROR)),
                 git_dir_line("spec", IO_ERROR),
                 git_dir_line("code", IO_ERROR), OTHER_WHY,
                 id="head-io-error"),
    pytest.param(refused_gitfile, cannot("spec/.git"), cannot("code/.git"),
                 PERMISSION_WHY, id="gitfile-read"),
])
def test_a_leg_git_directory_refused_is_named_on_every_python(
        standard, project, monkeypatch, refuse, spec, code, why):
    """The `legs` and `placement` rows for legs whose gitfile cannot be
    read, or whose git directory's `HEAD` cannot be `stat`ed (#1174), in
    process: each row says the gate's line, no HEAD is read, the NEXT is
    this doctor again with the advice for the cause, and no leg is drift.
    The `leg shape files` row, which reads no git, compares the files."""
    module, ctx = in_process(standard, project)
    refuse(monkeypatch, ctx.root)
    legs = module.check_legs(ctx)
    assert legs.reason == f"{unread_mount(spec)}; {unread_mount(code)}"
    assert [leg["head"] for leg in legs.detail["legs"]] == [None, None]
    assert legs.next_command == doctor_again(standard, project)
    assert legs.why == why
    assert module.drifted_reasons({"legs": legs}, {}) == []
    shape_files = module.check_leg_shape_files(ctx)
    assert_compared({"status": shape_files.status,
                     "detail": shape_files.detail, "why": shape_files.why})
    placement = module.check_placement(ctx)
    assert placement.reason.endswith(f"{spec}; {code}"), placement.reason


def test_a_git_directory_of_its_own_refused_is_not_the_roots(
        standard, project, monkeypatch):
    """A leg whose `.git` is a directory of its own, whose `HEAD` cannot be
    `stat`ed: git, run in the leg, passed over it to the root's repository,
    and the row quoted the ROOT's HEAD as the leg's with a checkout over it
    (#1174). It names the leg's `.git`, as the gate does."""
    leg_with_its_own_git_directory(project)
    module, ctx = in_process(standard, project)
    refused_head(PermissionError(errno.EACCES, DENIED))(monkeypatch, ctx.root)
    legs = module.check_legs(ctx)
    assert legs.reason == (f"{unread_mount(cannot('spec/.git'))}; "
                           f"{unread_mount(git_dir_line('code'))}")
    assert [leg["head"] for leg in legs.detail["legs"]] == [None, None]
    assert legs.next_command == doctor_again(standard, project)
    assert module.drifted_reasons({"legs": legs}, {}) == []


def test_a_member_git_directory_refused_is_named_on_every_python(
        standard, holder, tmp_path, monkeypatch):
    """The `members` row for a member whose git directory's `HEAD` cannot
    be `stat`ed (#1174): named after the member, no HEAD read, the advice,
    and no drift."""
    root = holder_copy(holder, tmp_path)
    module, ctx = in_process(standard, root)
    refused_head(PermissionError(errno.EACCES, DENIED))(monkeypatch, ctx.root)
    members = module.check_members(ctx)
    line = cannot(f"{MEMBER}: {MEMBER_GIT_DIR}")
    assert members.reason == unread_mount(line)
    entry = members.detail["members"][0]
    assert entry["mount_cannot_be_read"] == line
    assert entry["head"] is None, entry
    assert members.next_command == doctor_again(standard, root)
    assert members.why == PERMISSION_WHY
    assert module.drifted_reasons({"members": members}, {}) == []


def gitfile_naming_nothing(project: Path, _aside: Path) -> None:
    """`spec/.git` a file with no `gitdir: ` line."""
    (project / "spec" / ".git").write_bytes(b"not a gitfile\n")


def git_directory_moved_away(project: Path, aside: Path) -> None:
    """The git directory `spec`'s gitfile names moved out of the root."""
    (project / ".git" / "modules" / "spec").rename(aside)


@pytest.mark.parametrize("unmake", [
    pytest.param(gitfile_naming_nothing, id="gitfile-names-none"),
    pytest.param(git_directory_moved_away, id="git-directory-gone"),
])
def test_a_git_directory_that_is_not_there_is_left_to_git(
        standard, project, tmp_path, unmake):
    """The controls: a gitfile that names no directory, and a git directory
    that is not there, are no read this user was refused. They are left to
    git, as the gate leaves them, and the row says what it said."""
    unmake(project, tmp_path / "spec-git-directory-aside")
    module, ctx = in_process(standard, project)
    legs = module.check_legs(ctx)
    assert legs.reason == "spec: populated, but git cannot read a HEAD in it"
    assert "mount_cannot_be_read" not in legs.detail["legs"][0]


#: What a gitfile may hold, as the gate's own cases write it (#968).
GITFILES = [
    pytest.param(b"gitdir: ../.git/modules/spec\n", id="relative"),
    pytest.param(b"gitdir: ../m\r\n", id="cr-lf"),
    pytest.param(b"gitdir: ../m", id="no-line-end"),
    pytest.param(b"gitdir: ../m\n\n", id="blank-line-after"),
    pytest.param(b"not a gitfile\n", id="names-none"),
    pytest.param(None, id="a-directory"),
]


@pytest.mark.parametrize("written", GITFILES)
def test_the_doctor_finds_a_git_directory_as_the_gate_finds_it(
        sources, tmp_path, written):
    """`git_dir_of` is the gate's `_leg_git_dir` (#968): the same directory,
    or None, for each gitfile and for a `.git` that is a directory, so the
    doctor asks the `HEAD` the gate asks (#1174)."""
    dotgit = tmp_path / "leg" / ".git"
    if written is None:
        dotgit.mkdir(parents=True)
    else:
        dotgit.parent.mkdir()
        dotgit.write_bytes(written)
    assert sources.doctor.git_dir_of(dotgit) == \
        sources.gate._leg_git_dir(dotgit)


@pytest.mark.parametrize("rel, gitdir, named", [
    pytest.param("spec", ("spec", ".git"), "spec/.git", id="its-own"),
    pytest.param("spec", ("spec", "..", ".git", "modules", "spec"),
                 "spec: .git/modules/spec", id="under-the-root"),
    pytest.param(MEMBER, (MEMBER, "..", "..", ".git", "modules", MEMBER),
                 f"{MEMBER}: {MEMBER_GIT_DIR}", id="a-members"),
    pytest.param("spec", ("..", "elsewhere", "spec"), None,
                 id="outside-the-root"),
])
def test_a_git_directory_is_named_as_the_gate_names_it_after_its_mount(
        sources, tmp_path, rel, gitdir, named):
    """`git_dir_named` is the gate's `_named` of the normalized directory,
    from the root, or whole where it is outside the root, and the mount's
    path goes first where the directory is not under the mount (#1174)."""
    root = tmp_path / "root"
    path = root.joinpath(*gitdir)
    gate = sources.gate._named(root, Path(os.path.normpath(path)))
    if named is None:
        named = f"spec: {tmp_path / 'elsewhere' / 'spec'}"
    assert sources.doctor.git_dir_named(root, rel, path) == named
    assert named.endswith(gate), (named, gate)


def test_beside_a_checkout_line_the_unread_mount_gets_the_advice(
        standard, project, monkeypatch):
    """One leg's mount cannot be listed, and the other leg has a commit past
    its pin while its gitlink is at the pin: the checkout line is the NEXT
    for that leg, and its why ends on the advice for the mount. The `leg
    shape files` note for that mount has no why: the `legs` row gives the
    mount's advice, and only a leg FILE this user cannot read is told it
    there (#1175, RV1193's NIT 1)."""
    module, ctx = in_process(standard, project)
    git("commit", "-q", "--allow-empty", "-m", "past its pin",
        cwd=project / "code")
    refusing(monkeypatch, "iterdir", "spec",
             PermissionError(errno.EACCES, DENIED))
    legs = module.check_legs(ctx)
    assert legs.next_command.endswith(" -- code"), legs.next_command
    assert legs.why.endswith(". " + PERMISSION_WHY), legs.why
    assert module.check_leg_shape_files(ctx).why is None


def test_a_leg_with_no_gitlink_names_the_mount_it_cannot_reach_too(
        standard, project, monkeypatch):
    """A leg the root records no gitlink for, over a mount this user cannot
    list (#1175): the lockstep fact is said first, the mount's line follows
    it, the gate's line is the NEXT with the advice in its why, and the leg
    is no drift."""
    make_no_gitlink(project)
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "iterdir", "spec",
             PermissionError(errno.EACCES, DENIED))
    legs = module.check_legs(ctx)
    assert legs.reason == ("spec: no gitlink recorded, so this leg is not "
                           "mounted as a submodule at all, and "
                           + listed("spec"))
    assert legs.detail["legs"][0]["mount_cannot_be_read"] == listed("spec")
    assert legs.next_command == module.lockstep_next(ctx, module.PINS_GATE,
                                                     "leg")[0]
    assert legs.why.endswith(". " + PERMISSION_WHY), legs.why
    assert module.drifted_reasons({"legs": legs}, {}) == []


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


def gitmodules_refused_in(monkeypatch, folder: Path) -> None:
    """`Path.is_file` raising a refused `stat` for a name in `folder`, as
    Python 3.9 to 3.13 raise it in a folder this user cannot search. 3.14
    answers False, so this stand-in reaches it on every Python."""
    real = Path.is_file

    def is_file(self, *args, **kwargs):
        if self.parent == folder:
            raise PermissionError(errno.EACCES, DENIED, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "is_file", is_file)


@pytest.mark.parametrize("own_bootstrap", [
    pytest.param(True, id="the-holders-bootstrap"),
    pytest.param(False, id="the-git-line"),
])
def test_beside_a_member_checkout_the_unreached_member_gets_the_advice(
        standard, holder, tmp_path, monkeypatch, own_bootstrap):
    """One member's mount cannot be listed, and the other's is empty, which
    a checkout cures (#1175): the holder's own bootstrap where it can run,
    else the git line. Either way the row names both, its why says that the
    next run names what the line leaves and ends on the advice for the
    mount, and the unreached member's `.gitmodules`, whose `stat` would be
    refused, is never asked."""
    root = holder_copy(holder, tmp_path)
    with_a_member_beside_one_a_checkout_cures(root)
    if not own_bootstrap:
        holder_without(root, "bootstrap.py")
    module, ctx = in_process(standard, root)
    refusing(monkeypatch, "iterdir", "Ghost",
             PermissionError(errno.EACCES, DENIED))
    gitmodules_refused_in(monkeypatch, ctx.root / GHOST)
    members = module.check_members(ctx)
    assert members.reason.split("; ")[:2] == [
        f"{MEMBER}: {UNBOOTSTRAPPED} submodule", unread_mount(listed(GHOST))]
    assert members.detail["members"][1]["mount_cannot_be_read"] == \
        listed(GHOST)
    if own_bootstrap:
        assert members.next_command == bootstrap_line(module, root)
    else:
        assert members.next_command.endswith(f" -- {MEMBER}"), \
            members.next_command
    assert beside_the_checkout(module, members.why), members.why


def test_a_member_whose_git_directory_is_refused_is_not_asked_what_it_carries(
        standard, holder, tmp_path, monkeypatch):
    """A member whose git directory this user cannot read, beside one the
    holder's own bootstrap cures (#1174): its mount can be read, and so can
    the `.gitmodules` in it, but the row does not ask that file whether the
    bootstrap's recursive update checks out legs the member carries. Git can
    move nothing in a member whose repository it cannot read, so the why
    says no keep line for one: it is the same with that file and without
    it, and it ends on the advice for the git directory."""
    root = holder_copy(holder, tmp_path)
    with_a_member_beside_one_a_checkout_cures(root)
    ghost = root / GHOST
    (ghost / ".git").write_bytes(b"gitdir: ../../.git/modules/members/Ghost\n")
    gitmodules = ghost / ".gitmodules"
    gitmodules.write_bytes(b'[submodule "spec"]\n\tpath = spec\n')
    module, ctx = in_process(standard, root)
    refused_head(PermissionError(errno.EACCES, DENIED))(monkeypatch, ctx.root)
    members = module.check_members(ctx)
    assert members.reason.split("; ")[:2] == [
        f"{MEMBER}: {UNBOOTSTRAPPED} submodule",
        unread_mount(cannot(f"{GHOST}: .git/modules/{GHOST}"))]
    assert members.next_command == bootstrap_line(module, root)
    assert beside_the_checkout(module, members.why), members.why
    assert "git -C LEG branch NAME" not in members.why, members.why
    gitmodules.rename(tmp_path / "ghost-gitmodules-aside")
    assert module.check_members(ctx).why == members.why


def test_a_leg_file_this_user_cannot_read_is_said_not_called_absent(
        standard, project, monkeypatch):
    """A leg's shape file whose `stat`, or whose read, is refused is `cannot
    be read`, never `absent` with a copy over it: the row is a `note` with
    no NEXT, and its why is the gate's advice (#1175)."""
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
    assert row.why == PERMISSION_WHY


@pytest.mark.parametrize("method, name", [
    pytest.param("stat", ".gitignore", id="stat"),
    pytest.param("read_bytes", "CLAUDE.md", id="read"),
])
def test_a_leg_file_refused_for_another_reason_gets_the_other_advice(
        standard, project, monkeypatch, method, name):
    """A leg file whose `stat`, or whose read, alone fails for a reason that
    is no permission (an I/O error): the system's reason, a `note`, and the
    gate's other advice, which is not told to `chmod` (#1175)."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, method, name, OSError(errno.EIO, IO_ERROR))
    row = module.check_leg_shape_files(ctx)
    assert row.detail["legs"]["spec"]["files"][name] == \
        f"cannot be read ({IO_ERROR})"
    assert row.status == module.NOTE
    assert row.next_command is None
    assert row.why == OTHER_WHY


@pytest.mark.parametrize("name", [".gitignore", "AGENTS.md"])
def test_beside_a_missing_leg_file_the_advice_follows_its_line(
        standard, project, monkeypatch, name):
    """A leg file missing beside one this user cannot read (#1175): the
    NEXT is the missing file's line, as before, and the advice is the why
    where that line's says nothing (a copy), or follows it (a file the
    scaffold renders, which no copy makes)."""
    module, ctx = in_process(standard, project)
    (project / "code" / name).unlink()
    refusing(monkeypatch, "read_bytes", "CLAUDE.md",
             PermissionError(errno.EACCES, DENIED))
    row = module.check_leg_shape_files(ctx)
    line, said = module.missing_shape_file_fix(ctx, [("code", "code", name)])
    assert row.status == module.NOTE
    assert row.reason.endswith(f"(missing: code/{name})"), row.reason
    assert row.next_command == line
    if name == ".gitignore":
        assert said is None
        assert row.why == PERMISSION_WHY
    else:
        assert said.startswith("the missing file(s) are RENDERED"), said
        # `Row` flattens the typography of what it is handed (`ascii_text`).
        assert row.why == module.ascii_text(f"{said}. {PERMISSION_WHY}")


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
