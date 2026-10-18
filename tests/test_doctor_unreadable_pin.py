# SPDX-License-Identifier: Apache-2.0
"""A pin, or a `contracts/`, this user cannot read is named by the doctor's
rows as `validate-pins.py` names it (#847).

THE DEFECT. #712 (PR #827) makes the gate refuse a pin the operating system
will not let it reach or open by name: `REFUSED yaml-unreadable:
contracts/spec-pin.yaml: cannot be read (Permission denied)`, with a remedy
for the permission. Three of the doctor's rows read the same files
themselves, and said something else:

  * `legs`, through `pin_commit`: `spec: contracts/spec-pin.yaml carries no
    40-hex commit to compare HEAD against`, which the verdict counted as a
    leg off its pin, `DRIFTED (1 leg(s) not at the pin)`, for a pin at mode
    000 and for a `contracts/` at 000;
  * `manifest kinds`: `unreadable as YAML: ... [Errno 13] Permission denied:
    '<root>/...'` for a pin at 000, with `git checkout HEAD -- <the pin>` as
    its NEXT, which discards what the file holds that no commit does, and
    `could not be run: [Errno 13] ...` for a `contracts/` at 000;
  * `shape currency`: `could not be run: [Errno 13] ...` for a `contracts/`
    at 000 or a pinned copy at 000, and for a shape pin at 000 the same
    `git checkout HEAD --`.

Each now says the gate's line, `<path>: cannot be read (<reason>)` (a
`contracts/` it cannot list: `contracts: cannot be listed (<reason>)`, the
gate's words for a directory, #434), its NEXT is this doctor again and its
`why` the gate's advice for the cause, word for word, and the verdict is the
gate's INVALID, never DRIFTED.

THREE KINDS OF CASE. The MODE cases change a real mode and run the doctor as
a person does, so they skip on Windows, whose modes refuse no read, and as
root, who reads a file at 000 (`CANNOT_RUN_AS_ROOT`). The STAND-IN cases run
the doctor's rows in process with the refusal put in by hand, as #827's
`refused_stat` rows do: a refused `stat` (`refused_stat`, which also answers
`is_file()` as Python 3.14 does, False to any `OSError`), a refused read or
a refused listing (`refusing`). They run on every platform and as root. The
PARITY cases hold the doctor's copies of the gate's lists and words equal to
the gate's and to `bump-leg.py`'s, each file loaded by path (rv860's SHOULD
1): a copy that drifts is the disagreement #847 was about.

NOTHING HERE REACHES A NETWORK: the doctor's own fixtures, a scaffold into
local bare remotes, and the session's `gh` guard for the `machine` row.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, git, load_without_bytecode, rmtree
#: #827's stand-in for a `stat` the operating system refuses, from the file
#: that owns it (#383), as `test_validate_pins_unreadable_workflows_dir.py`
#: takes it.
from test_bump_leg_unopenable import refused_stat
#: This doctor's own line for a root, as `unreadable_next` spells it.
from test_doctor_recorded_answers import doctor_again
#: The doctor's fixtures and helpers, from the module that owns them.
from test_shape_doctor import (  # noqa: F401
    SHAPE_PIN, doctor, doctor_module, project, rows_of, scaffolded_here,
    standard,
)
#: The one skip for a mode that root reads through and Windows ignores.
from test_validate_pins_unreadable_workflow import CANNOT_RUN_AS_ROOT
#: A mode for the block and the old one back after it, from the file that
#: owns it, as `test_validate_pins_named_and_spelled.py` takes it.
from test_validate_pins_unreadable_workflows_dir import mode_of

SPEC_PIN = "contracts/spec-pin.yaml"
CODE_PIN = "contracts/code-pin.yaml"
#: A pinned copy that lives under `contracts/`.
NAMING_COPY = "contracts/repository-naming.yaml"

#: The reason every stand-in gives, as `refused_stat` raises it.
DENIED = "Permission denied"
#: The reason the stand-ins for another cause give.
IO_ERROR = "Input/output error"

#: `validate-pins.py`'s advice for a refused permission, word for word
#: (`_unreadable_file`, #712), and the doctor's own last sentence.
PERMISSION_WHY = (
    "Make what this user may not open readable by this user: `chmod u+r` on "
    "a file, `chmod u+rx` on a directory (and on every directory above it "
    "inside the root), or fix who owns it. Then run this doctor again")
#: The same gate's advice for any other cause (`OTHER_REASON`, #712).
OTHER_WHY = (
    "Where the operating system gave another reason, put a regular file this "
    "user can open back in its place, or take away one nobody wants, and make "
    "sure nothing is changing the directory while this runs. Then run this "
    "doctor again")
#: The same gate's advice for a DIRECTORY it cannot list for any other
#: cause (`_workflows_unlistable`, #434).
OTHER_FOLDER_WHY = (
    "Where the operating system gave another reason, put a directory this "
    "user can list back in its place, and make sure nothing is changing it "
    "while this runs. Then run this doctor again")

#: What no row may name for a file this user cannot read (#847).
CHECKOUT = "checkout HEAD --"

#: The gate as the template ships it, and `bump-leg.py`: the two files whose
#: lists and words the doctor copies (rv860's SHOULD 1).
GATE = REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py"
BUMP = REPO / "scripts" / "bump-leg.py"
#: The directory the gate's own words for an unlistable one are about.
WORKFLOWS_DIR = ".github/workflows"


def cannot(named: str, reason: str = DENIED) -> str:
    """The gate's line for a file it cannot reach or open."""
    return f"{named}: cannot be read ({reason})"


def leg_line(leg: str, pin: str, reason: str = DENIED) -> str:
    """The `legs` row's words for a leg whose pin cannot be read."""
    return (f"{leg}: {cannot(pin, reason)}, so there is no pinned commit to "
            "compare HEAD against")


def doctored(standard: Path, root: Path) -> tuple[dict, str]:
    """`({id: row}, verdict)` from one `--json` run that printed no
    traceback."""
    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    return rows_of(result), json.loads(result.stdout)["verdict"]


def assert_no_checkout(rows: dict) -> None:
    """No row names a `git checkout HEAD --`, as its NEXT or in its why."""
    for row in rows.values():
        assert CHECKOUT not in (row["next"] or ""), row
        assert CHECKOUT not in (row["why"] or ""), row


def refusing(monkeypatch, method: str, name: str, error: OSError) -> None:
    """`Path.<method>` raising `error`, with the path as its filename, for a
    path called `name`, and the real method for every other: a read
    (`read_text`, `read_bytes`) or a listing (`iterdir`) the operating
    system refused, in process, on every platform and as root."""
    real = getattr(Path, method)

    def refused(self, *args, **kwargs):
        if self.name == name:
            raise type(error)(error.errno, error.strerror, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, method, refused)


def in_process(standard: Path, project: Path):
    """`(the doctor as a module, its Context over the root)`, the root
    resolved as `main` resolves it."""
    module = doctor_module(standard)
    return module, module.Context(project.resolve())


@pytest.fixture(scope="module")
def sources():
    """The doctor, the gate and `bump-leg.py` of this working tree, each
    loaded by path with no bytecode written beside it, and `sys.path` put
    back after: each of the three puts its own `scripts/` on it."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(sys, "path", list(sys.path))
        return SimpleNamespace(
            doctor=load_without_bytecode(REPO / "shape-doctor.py",
                                         "doctor_unreadable_pin_parity"),
            gate=load_without_bytecode(GATE, "gate_unreadable_pin_parity"),
            bump=load_without_bytecode(BUMP, "bump_leg_unreadable_pin_parity"))


# --- the mode cases: a real mode, the doctor run as a person runs it ---------

@CANNOT_RUN_AS_ROOT
def test_a_pin_at_mode_000_is_named_as_the_gate_names_it(standard, project):
    """The issue's first case. The `legs` row says the gate's line and is no
    drift; `manifest kinds` says it too, and neither names a checkout."""
    again = doctor_again(standard, project)
    denied = os.strerror(errno.EACCES)
    with mode_of(project, SPEC_PIN, 0):
        rows, verdict = doctored(standard, project)
    legs, kinds = rows["legs"], rows["manifest-kinds"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == leg_line("spec", SPEC_PIN, denied)
    assert legs["next"] == again
    assert legs["why"] == PERMISSION_WHY
    assert kinds["status"] == "FINDING", kinds
    assert kinds["reason"] == cannot(SPEC_PIN, denied)
    assert kinds["next"] == again
    assert kinds["why"] == PERMISSION_WHY
    assert verdict == "INVALID (pins, manifest-kinds)"
    assert_no_checkout(rows)


@CANNOT_RUN_AS_ROOT
@pytest.mark.parametrize("bits", [
    pytest.param(0, id="contracts-000"),
    pytest.param(0o444, id="contracts-r--"),
])
def test_a_contracts_folder_this_user_cannot_search_is_named(
        standard, project, bits):
    """The issue's second case, and its listable cousin. At 000 the folder
    cannot be listed; at `r--` it can, and no file in it can be reached.
    Every row that reads it names what it cannot read, in the gate's words,
    and the verdict is no drift."""
    again = doctor_again(standard, project)
    denied = os.strerror(errno.EACCES)
    contracts = project / "contracts"
    listed = sorted(path.name for path in contracts.iterdir()
                    if path.suffix in (".yaml", ".yml"))
    with mode_of(project, "contracts", bits):
        rows, verdict = doctored(standard, project)
    expected = (f"contracts: cannot be listed ({denied})" if bits == 0 else
                ", ".join(cannot(f"contracts/{name}", denied)
                          for name in listed))
    assert rows["manifest-kinds"]["reason"] == expected
    assert rows["legs"]["reason"] == "; ".join((
        leg_line("spec", SPEC_PIN, denied),
        leg_line("code", CODE_PIN, denied)))
    assert rows["shape-currency"]["reason"] == (
        "the copies cannot be compared: " + cannot(SHAPE_PIN, denied))
    for row in ("manifest-kinds", "legs", "shape-currency"):
        assert rows[row]["next"] == again, rows[row]
        assert rows[row]["why"] == PERMISSION_WHY, rows[row]
    assert verdict == "INVALID (manifest, pins, manifest-kinds)"
    assert_no_checkout(rows)


@CANNOT_RUN_AS_ROOT
def test_a_shape_pin_at_mode_000_gets_one_answer_from_both_rows(
        standard, project):
    """The shape pin at 000: `shape currency` and `manifest kinds` print the
    same NEXT and the same why for the same file, as they do for a pin that
    does not load (#291), and neither is `git checkout HEAD --`."""
    denied = os.strerror(errno.EACCES)
    with mode_of(project, SHAPE_PIN, 0):
        rows, verdict = doctored(standard, project)
    shape, kinds = rows["shape-currency"], rows["manifest-kinds"]
    assert shape["reason"] == ("the copies cannot be compared: "
                               + cannot(SHAPE_PIN, denied))
    assert kinds["reason"] == cannot(SHAPE_PIN, denied)
    assert shape["next"] == doctor_again(standard, project)
    assert shape["next"] == kinds["next"]
    assert shape["why"] == PERMISSION_WHY
    assert shape["why"] == kinds["why"]
    assert "environment" not in shape["detail"], shape
    assert verdict == "INVALID (pins, manifest-kinds)"
    assert_no_checkout(rows)


@CANNOT_RUN_AS_ROOT
def test_a_pinned_copy_at_mode_000_stops_the_comparison_by_name(
        standard, project):
    """A pinned copy that lives under `contracts/`, at 000: `shape currency`
    was `could not be run: [Errno 13] ...`, and `manifest kinds` a `git
    diff HEAD` whose why spoke of an uncommitted change. Both name it."""
    denied = os.strerror(errno.EACCES)
    with mode_of(project, NAMING_COPY, 0):
        rows, _verdict = doctored(standard, project)
    assert rows["shape-currency"]["reason"] == (
        "the copies cannot be compared: " + cannot(NAMING_COPY, denied))
    assert rows["manifest-kinds"]["reason"] == cannot(NAMING_COPY, denied)
    assert rows["manifest-kinds"]["why"] == PERMISSION_WHY
    assert_no_checkout(rows)


# --- the stand-in cases: in process, on every platform and as root ----------

def refused_stat_of(monkeypatch, name: str) -> None:
    """A `contracts/` this user cannot search, for the one file `name`."""
    refused_stat(monkeypatch, name)


def refused_read_of(monkeypatch, name: str) -> None:
    """A file at mode 000: there, and its read refused."""
    refusing(monkeypatch, "read_text", name,
             PermissionError(errno.EACCES, DENIED))


@pytest.mark.parametrize("refuse", [
    pytest.param(refused_stat_of, id="stat-refused"),
    pytest.param(refused_read_of, id="read-refused"),
])
def test_a_refused_pin_is_named_on_every_python(standard, project,
                                                monkeypatch, refuse):
    """The `legs` and `manifest kinds` rows for a pin whose `stat` or read
    is refused. A refused `stat` reaches `pin_commit` as Python 3.14's
    `is_file()` would answer it, so the pin is asked as the gate asks it,
    `stat` first; and a leg whose pin cannot be read is no drift."""
    module, ctx = in_process(standard, project)
    again = doctor_again(standard, project)
    refuse(monkeypatch, "spec-pin.yaml")
    legs = module.check_legs(ctx)
    kinds = module.check_manifest_kinds(ctx)
    assert legs.reason == leg_line("spec", SPEC_PIN)
    assert legs.next_command == again
    assert legs.why == PERMISSION_WHY
    assert legs.detail["legs"][0]["cannot_be_read"] == cannot(SPEC_PIN)
    assert module.drifted_reasons({"legs": legs}, {}) == []
    assert kinds.reason == cannot(SPEC_PIN)
    assert kinds.next_command == again
    assert kinds.why == PERMISSION_WHY
    assert kinds.detail["cannot_be_read"] == [cannot(SPEC_PIN)]


def test_another_reason_is_given_the_gates_other_advice(
        standard, project, monkeypatch):
    """A read refused for a reason that is no permission (an I/O error): the
    system's reason, and the gate's other advice, which is not told to
    `chmod`."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "read_text", "spec-pin.yaml",
             OSError(errno.EIO, IO_ERROR))
    legs = module.check_legs(ctx)
    kinds = module.check_manifest_kinds(ctx)
    assert legs.reason == leg_line("spec", SPEC_PIN, IO_ERROR)
    assert legs.why == OTHER_WHY
    assert kinds.reason == cannot(SPEC_PIN, IO_ERROR)
    assert kinds.why == OTHER_WHY


def test_a_shape_pin_whose_stat_is_refused_is_not_called_missing(
        standard, project, monkeypatch):
    """`read_pin` asks `is_file()`, which raised a refused `stat` up to
    Python 3.13 and calls the pin missing from 3.14 (`update-pin-missing`).
    The row asks why, and names the pin in the gate's words, with the NEXT
    and why `manifest kinds` gives it."""
    module, ctx = in_process(standard, project)
    refused_stat(monkeypatch, "shape-pin.yaml")
    shape = module.check_shape_currency(ctx)
    kinds = module.check_manifest_kinds(ctx)
    assert shape.status == "FINDING"
    assert shape.reason == ("the copies cannot be compared: "
                            + cannot(SHAPE_PIN))
    assert shape.next_command == doctor_again(standard, project)
    assert shape.next_command == kinds.next_command
    assert shape.why == PERMISSION_WHY
    assert shape.why == kinds.why
    assert shape.detail == {"path": SHAPE_PIN,
                            "cannot_be_read": cannot(SHAPE_PIN)}


@pytest.mark.parametrize("error, why", [
    pytest.param(PermissionError(errno.EACCES, DENIED), PERMISSION_WHY,
                 id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), OTHER_FOLDER_WHY,
                 id="another-reason"),
])
def test_a_contracts_folder_that_cannot_be_listed_is_named(
        standard, project, monkeypatch, error, why):
    """`iterdir()` refused: the folder, in the gate's words for a directory
    it cannot list, where the row ended in `could not be run`. For another
    reason than permission (rv860's NIT 3) it is told what the gate tells a
    directory, to put one back in its place, and not a regular file."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "iterdir", "contracts", error)
    kinds = module.check_manifest_kinds(ctx)
    assert kinds.reason == f"contracts: cannot be listed ({error.strerror})"
    assert kinds.next_command == doctor_again(standard, project)
    assert kinds.why == why


def test_a_file_this_user_cannot_read_is_said_first(standard, project,
                                                    monkeypatch):
    """Beside another fault, here a manifest of a kind nothing registers, a
    file this user cannot read is said first, as its NEXT comes first: the
    row cannot say what kind it declares until it can be read."""
    module, ctx = in_process(standard, project)
    (project / "contracts" / "stray.yaml").write_text(
        "kind: nothing-registers-this\n", encoding="utf-8")
    refused_read_of(monkeypatch, "spec-pin.yaml")
    kinds = module.check_manifest_kinds(ctx)
    assert kinds.reason.split("; ")[0] == cannot(SPEC_PIN), kinds.reason
    assert "no validator registered for kind" in kinds.reason, kinds.reason
    assert kinds.next_command == doctor_again(standard, project)


def test_a_copy_whose_read_is_refused_stops_the_comparison_by_name(
        standard, project, monkeypatch):
    """`update-shape.py`'s comparison reads each copy, and a refused read of
    one in the root is the row's FINDING, named, where it ended the row in
    `could not be run`."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "read_bytes", "repository-naming.yaml",
             PermissionError(errno.EACCES, DENIED))
    shape = module.check_shape_currency(ctx)
    assert shape.reason == ("the copies cannot be compared: "
                            + cannot(NAMING_COPY))
    assert shape.next_command == doctor_again(standard, project)
    assert shape.why == PERMISSION_WHY


def test_only_a_refused_read_inside_the_root_is_the_roots(standard, project):
    """`refused_in_root` names a file inside the root whose read was
    refused, and nothing else: a file that is not there, one outside the
    root, such as the checkout of the standard's own, or a refusal that
    names no file at all stays an error."""
    module, ctx = in_process(standard, project)
    inside = str(ctx.root / NAMING_COPY)
    outside = str(standard.resolve() / NAMING_COPY)
    assert module.refused_in_root(ctx.root, PermissionError(
        errno.EACCES, DENIED, inside)) == NAMING_COPY
    assert module.refused_in_root(ctx.root, FileNotFoundError(
        errno.ENOENT, "No such file or directory", inside)) is None
    assert module.refused_in_root(ctx.root, PermissionError(
        errno.EACCES, DENIED, outside)) is None
    assert module.refused_in_root(ctx.root, PermissionError(
        errno.EACCES, DENIED)) is None


@pytest.mark.parametrize("raised", [
    pytest.param(lambda standard, _root: PermissionError(
        errno.EACCES, DENIED, str(standard.resolve() / "update-shape.py")),
        id="outside-the-root"),
    pytest.param(lambda _standard, _root: PermissionError(
        errno.EACCES, DENIED), id="no-file-named"),
    pytest.param(lambda _standard, root: FileNotFoundError(
        errno.ENOENT, "No such file or directory", str(root / NAMING_COPY)),
        id="nothing-there"),
])
def test_an_oserror_the_root_did_not_refuse_is_raised_as_it_was(
        standard, project, monkeypatch, raised):
    """Only a refused read of a file inside the root is the `shape currency`
    row's FINDING. An `OSError` out of the comparison about a file
    elsewhere, one that names no file, or one that says nothing is there is
    raised as it was, which `run_checks` reports as a check that could not
    be run: it is not a statement about the repository."""
    module, ctx = in_process(standard, project)
    error = raised(standard, ctx.root)

    def prepare(_args):
        raise error

    monkeypatch.setattr(ctx.update_shape(), "prepare", prepare)
    with pytest.raises(type(error)):
        module.check_shape_currency(ctx)


def test_a_refused_stat_is_raised_on_every_python(standard, project,
                                                  monkeypatch):
    """`is_a` raises a refused `stat` where `is_file()` on 3.14 answers
    False, and answers False only where nothing is there."""
    module, _ctx = in_process(standard, project)
    refused_stat(monkeypatch, "spec-pin.yaml")
    with pytest.raises(PermissionError):
        module.is_a(project / SPEC_PIN, stat.S_ISREG)
    assert module.is_a(project / "contracts" / "absent.yaml",
                       stat.S_ISREG) is False


def test_beside_the_checkout_line_the_why_gives_the_advice_too(
        standard, project, monkeypatch):
    """One leg's pin cannot be read, and the other leg has a commit past its
    pin while its gitlink is at the pin, which the checkout line cures. The
    line is the NEXT, and its why says what it does, that the next run names
    what it leaves (the pin it cannot read), and then the gate's advice, as
    beside the gate's line (rv860's NIT 5)."""
    module, ctx = in_process(standard, project)
    git("commit", "-q", "--allow-empty", "-m", "past its pin",
        cwd=project / "code")
    refused_read_of(monkeypatch, "spec-pin.yaml")
    legs = module.check_legs(ctx)
    assert legs.next_command.endswith(" -- code"), legs.next_command
    assert legs.why.endswith(
        module.rerun_sentence("leg") + ". " + PERMISSION_WHY), legs.why


def test_beside_an_unborn_head_the_doctor_again_still_names_it(
        standard, project, monkeypatch):
    """One leg's pin cannot be read, and the other leg's HEAD names a branch
    with no commit, which no line cures: the NEXT is this doctor again, and
    its why is the gate's advice and then what the unborn HEAD needs."""
    module, ctx = in_process(standard, project)
    git("symbolic-ref", "HEAD", "refs/heads/never-made",
        cwd=project / "code")
    refused_read_of(monkeypatch, "spec-pin.yaml")
    legs = module.check_legs(ctx)
    assert legs.next_command == doctor_again(standard, project)
    assert legs.why == (PERMISSION_WHY + ". "
                        + module.unborn_sentence("code", "leg"))


def test_where_the_gates_line_cannot_be_built_the_advice_is_still_said(
        standard, project, monkeypatch):
    """`lockstep_next` names no line where no `PYTHONPATH` can name the
    template's `scripts/` (#278), a standard checked out under a directory
    whose name holds `os.pathsep`: stood in for here, with the root's own
    copy of the gate gone so the template's is the one asked. The missing
    pin's lockstep fact then has no line, and the refused pin's advice is
    still the row's why."""
    module, ctx = in_process(standard, project)
    (project / CODE_PIN).unlink()
    (project / "scripts" / "validate-pins.py").unlink()
    monkeypatch.setattr(module, "pythonpath_unnamable",
                        lambda _shape, _own_copy: "no PYTHONPATH names it")
    refused_read_of(monkeypatch, "spec-pin.yaml")
    legs = module.check_legs(ctx)
    assert legs.next_command is None
    assert legs.why == PERMISSION_WHY


# --- the doctor's own helpers, asked directly -----------------------------

@pytest.mark.parametrize("contracts", [
    pytest.param(None, id="no-contracts"),
    pytest.param(b"a file, not a folder\n", id="contracts-a-file"),
])
def test_a_root_without_a_contracts_folder_refuses_nothing(
        sources, tmp_path, contracts):
    """A root with no `contracts/`, or with a `contracts` that is a file, has
    nothing under it to list and nothing this user cannot read: `is_a` is
    asked before `iterdir`, which raises `FileNotFoundError` or
    `NotADirectoryError` there."""
    if contracts is not None:
        (tmp_path / "contracts").write_bytes(contracts)
    assert sources.doctor.manifest_candidates(tmp_path) == ([], [])


def test_is_a_answers_for_the_kind_and_for_a_name_no_system_takes(
        sources, tmp_path):
    """`is_a` answers whether the path is of `kind`, so a folder named like a
    pin is no pin; and a name the operating system cannot take at all, a
    NUL in it, is nothing there, as `is_file()` answered it, and not a
    `ValueError` out of the row."""
    folder = tmp_path / "spec-pin.yaml"
    folder.mkdir()
    assert sources.doctor.is_a(folder, stat.S_ISREG) is False
    assert sources.doctor.is_a(folder, stat.S_ISDIR) is True
    assert sources.doctor.is_a(tmp_path / "a\0b.yaml", stat.S_ISREG) is False


@pytest.mark.parametrize("winerror", [21, 123, 1921])
def test_a_windows_error_that_says_nothing_is_there_is_no_refusal(
        sources, winerror):
    """Windows' "not ready", "invalid name" and "cannot resolve" say nothing
    is there, whatever errno they carry, as `is_file()` answered them; the
    same errno with no such `winerror` is a refusal. Built by hand, since
    only Windows raises one: an `OSError` with `winerror` set on it."""
    error = OSError(errno.EINVAL, "Invalid argument")
    error.winerror = winerror
    assert sources.doctor.refused_read(error) is None
    assert sources.doctor.refused_read(
        OSError(errno.EINVAL, "Invalid argument")) is not None


@pytest.mark.parametrize("beside, expected", [
    pytest.param([], ["1 leg(s) not at the pin"], id="alone"),
    pytest.param(["spec-pin.yaml"], [], id="beside-a-pin-it-cannot-read"),
])
def test_a_red_legs_row_with_no_leg_off_its_pin(standard, project,
                                                monkeypatch, beside,
                                                expected):
    """An empty `code` mount whose pin is gone has no HEAD and no pin, so no
    leg's HEAD is off its pin, and the red row is drift by the fallback
    count, `len(off) or 1`, as on main. Beside a pin this user cannot read
    the fallback is not said: the gate refuses that pin before anything
    else, and its INVALID is the verdict (`drifted_reasons`, rv860's NIT 4,
    documented as intended)."""
    module, ctx = in_process(standard, project)
    (project / CODE_PIN).unlink()
    rmtree(project / "code")
    (project / "code").mkdir()
    for name in beside:
        refused_read_of(monkeypatch, name)
    legs = module.check_legs(ctx)
    assert legs.status == "FINDING", legs
    assert module.drifted_reasons({"legs": legs}, {}) == expected


# --- parity: the doctor's copies of the gate's lists and words (SHOULD 1) ----

@pytest.mark.parametrize("owner", ["gate", "bump"])
def test_what_the_doctor_calls_nothing_there_is_what_the_gate_calls_so(
        sources, owner):
    """`ABSENT_ERRNOS` and `ABSENT_WINERRORS` copy `_ABSENT_ERRNOS` and
    `_ABSENT_WINERRORS` from the gate and from `bump-leg.py`. A copy that
    drifts makes the doctor call missing a pin the gate refuses by name, or
    name one the gate calls missing."""
    other = getattr(sources, owner)
    assert (sources.doctor.ABSENT_ERRNOS, sources.doctor.ABSENT_WINERRORS) \
        == (other._ABSENT_ERRNOS, other._ABSENT_WINERRORS)


def test_the_gates_other_reason_is_the_doctors_and_the_space_it_joins_on(
        sources):
    """The gate's `OTHER_REASON` is the doctor's and one space: the gate
    joins its sentences with `+`, so each ends on the space before the next,
    and the doctor joins with `" ".join`, so none does. Neither is changed
    to match the other; the space is asked for exactly, not stripped."""
    assert sources.gate.OTHER_REASON == sources.doctor.OTHER_REASON + " "


@pytest.mark.parametrize("error, sentence", [
    pytest.param(PermissionError(errno.EACCES, DENIED), "PERMISSION_ADVICE",
                 id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), "OTHER_REASON",
                 id="another-reason"),
])
def test_the_doctor_gives_the_gates_advice_word_for_word(sources, error,
                                                         sentence):
    """The gate's permission advice is written inline in `_unreadable_file`,
    so it is read as a person reads it: the remedy the gate's own function
    builds for the cause, which ends on the doctor's sentence for that
    cause, one space and the gate's `RUN_AGAIN`."""
    remedy = sources.gate._unreadable_file("yaml-unreadable", SPEC_PIN,
                                           error).remediation
    said = getattr(sources.doctor, sentence)
    assert remedy.endswith(f". {said} {sources.gate.RUN_AGAIN}"), remedy


def test_the_doctor_gives_the_gates_folder_advice_word_for_word(sources):
    """The gate's sentence for a directory it cannot list for another reason
    is inline in `_workflows_unlistable`, and read the same way."""
    root = Path("root")
    remedy = sources.gate._workflows_unlistable(
        root, root / WORKFLOWS_DIR, OSError(errno.EIO, IO_ERROR)).remediation
    said = sources.doctor.OTHER_REASON_FOLDER
    assert remedy.endswith(f". {said} {sources.gate.RUN_AGAIN}"), remedy


@pytest.mark.parametrize("errors", [
    pytest.param([PermissionError(errno.EACCES, DENIED)], id="permission"),
    pytest.param([OSError(errno.EIO, IO_ERROR)], id="another-reason"),
    pytest.param([PermissionError(errno.EACCES, DENIED),
                  OSError(errno.EIO, IO_ERROR)], id="both"),
])
def test_the_doctor_gives_bump_legs_advice_for_each_cause(sources, errors):
    """`bump-leg.py`'s `_cannot_open_advice` (#383), whose words the gate
    took: each cause's sentence once, the permission's first, for files
    whose causes are mixed as much as for one."""
    assert sources.doctor.cannot_read_why(errors) == (
        sources.bump._cannot_open_advice(errors)
        + "Then run this doctor again")


@pytest.mark.parametrize("error", [
    pytest.param(PermissionError(errno.EACCES, DENIED), id="permission"),
    pytest.param(OSError(errno.EIO, IO_ERROR), id="another-reason"),
    pytest.param(OSError(), id="no-reason-given"),
])
def test_the_doctor_names_a_file_and_a_folder_in_the_gates_words(sources,
                                                                 error):
    """`cannot_be_read` is the gate's `_cannot_read`, and `cannot_be_listed`
    the line of its `_workflows_unlistable`, the error's name standing in
    where the operating system gives no reason."""
    root = Path("root")
    assert sources.doctor.cannot_be_read(SPEC_PIN, error) == \
        sources.gate._cannot_read(SPEC_PIN, error)
    assert sources.doctor.cannot_be_listed(WORKFLOWS_DIR, error) == \
        sources.gate._workflows_unlistable(root, root / WORKFLOWS_DIR,
                                           error).detail


# --- controls: what must not change ------------------------------------------

def test_a_missing_pin_keeps_its_words_and_is_still_drift(standard, project):
    """A pin that is not there is what the gate calls `pin-missing`, not a
    file it cannot read: the row's words and the drift are main's."""
    module, ctx = in_process(standard, project)
    (project / SPEC_PIN).unlink()
    legs = module.check_legs(ctx)
    assert legs.reason == (f"spec: {SPEC_PIN} carries no 40-hex commit to "
                           "compare HEAD against")
    assert "cannot_be_read" not in legs.detail["legs"][0]
    assert module.drifted_reasons({"legs": legs}, {}) == [
        "1 leg(s) not at the pin"]


def test_a_pin_that_does_not_load_for_another_reason_keeps_its_words(
        standard, project):
    """A pin this user can read that is not UTF-8 does not load, and is no
    file this user cannot read: `pin_read` gives no cause for it, so the
    row keeps main's words, as `validate-pins.py` keeps its own refusal."""
    module, ctx = in_process(standard, project)
    (project / SPEC_PIN).write_bytes(b"commit: \xff\n")
    legs = module.check_legs(ctx)
    assert legs.reason == (f"spec: {SPEC_PIN} carries no 40-hex commit to "
                           "compare HEAD against")
    assert "cannot_be_read" not in legs.detail["legs"][0]


def test_beside_a_lockstep_fact_the_gate_stays_the_next(standard, project,
                                                        monkeypatch):
    """One leg's pin cannot be read and the other's is not there: the
    missing pin is the gate's lockstep fact, so its line is the NEXT, the
    gate's advice is said in the why, and the other leg is drift."""
    module, ctx = in_process(standard, project)
    (project / CODE_PIN).unlink()
    refused_read_of(monkeypatch, "spec-pin.yaml")
    legs = module.check_legs(ctx)
    gate, _said = module.lockstep_next(ctx, module.PINS_GATE, "leg")
    assert legs.next_command == gate
    assert legs.why.endswith(". " + PERMISSION_WHY), legs.why
    assert module.drifted_reasons({"legs": legs}, {}) == [
        "1 leg(s) not at the pin"]
