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

TWO KINDS OF CASE. The MODE cases change a real mode and run the doctor as
a person does, so they skip on Windows, whose modes refuse no read, and as
root, who reads a file at 000 (`CANNOT_RUN_AS_ROOT`). The STAND-IN cases run
the doctor's rows in process with the refusal put in by hand, as #827's
`refused_stat` rows do: a refused `stat` (`refused_stat`, which also answers
`is_file()` as Python 3.14 does, False to any `OSError`), a refused read or
a refused listing (`refusing`). They run on every platform and as root.

NOTHING HERE REACHES A NETWORK: the doctor's own fixtures, a scaffold into
local bare remotes, and the session's `gh` guard for the `machine` row.
"""

from __future__ import annotations

import errno
import json
import os
import stat
from contextlib import contextmanager
from pathlib import Path

import pytest

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

SPEC_PIN = "contracts/spec-pin.yaml"
CODE_PIN = "contracts/code-pin.yaml"
#: A pinned copy that lives under `contracts/`.
NAMING_COPY = "contracts/repository-naming.yaml"

#: The reason every stand-in gives, as `refused_stat` raises it.
DENIED = "Permission denied"

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

#: What no row may name for a file this user cannot read (#847).
CHECKOUT = "checkout HEAD --"


def cannot(named: str, reason: str = DENIED) -> str:
    """The gate's line for a file it cannot reach or open."""
    return f"{named}: cannot be read ({reason})"


def leg_line(leg: str, pin: str, reason: str = DENIED) -> str:
    """The `legs` row's words for a leg whose pin cannot be read."""
    return (f"{leg}: {cannot(pin, reason)}, so there is no pinned commit to "
            "compare HEAD against")


@contextmanager
def mode(path: Path, bits: int):
    """`path` at `bits` for the block, and its own mode back after it, so
    the basetemp can be removed."""
    held = stat.S_IMODE(path.stat().st_mode)
    path.chmod(bits)
    try:
        yield
    finally:
        path.chmod(held)


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


# --- the mode cases: a real mode, the doctor run as a person runs it ---------

@CANNOT_RUN_AS_ROOT
def test_a_pin_at_mode_000_is_named_as_the_gate_names_it(standard, project):
    """The issue's first case. The `legs` row says the gate's line and is no
    drift; `manifest kinds` says it too, and neither names a checkout."""
    again = doctor_again(standard, project)
    denied = os.strerror(errno.EACCES)
    with mode(project / SPEC_PIN, 0):
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
    with mode(contracts, bits):
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
    with mode(project / SHAPE_PIN, 0):
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
    with mode(project / NAMING_COPY, 0):
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
             OSError(errno.EIO, "Input/output error"))
    legs = module.check_legs(ctx)
    kinds = module.check_manifest_kinds(ctx)
    assert legs.reason == leg_line("spec", SPEC_PIN, "Input/output error")
    assert legs.why == OTHER_WHY
    assert kinds.reason == cannot(SPEC_PIN, "Input/output error")
    assert kinds.why == OTHER_WHY


def test_a_shape_pin_whose_stat_is_refused_is_not_called_missing(
        standard, project, monkeypatch):
    """`read_pin` asks `is_file()`, which raised a refused `stat` up to
    Python 3.13 and calls the pin missing from 3.14 (`update-pin-missing`).
    The row asks first, and names the pin in the gate's words, with the
    NEXT and why `manifest kinds` gives it."""
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


def test_a_contracts_folder_that_cannot_be_listed_is_named(
        standard, project, monkeypatch):
    """`iterdir()` refused: the folder, in the gate's words for a directory
    it cannot list, where the row ended in `could not be run`."""
    module, ctx = in_process(standard, project)
    refusing(monkeypatch, "iterdir", "contracts",
             PermissionError(errno.EACCES, DENIED))
    kinds = module.check_manifest_kinds(ctx)
    assert kinds.reason == f"contracts: cannot be listed ({DENIED})"
    assert kinds.next_command == doctor_again(standard, project)
    assert kinds.why == PERMISSION_WHY


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
    refused, and nothing else: a file that is not there, or one outside the
    root, such as the checkout of the standard's own, stays an error."""
    module, ctx = in_process(standard, project)
    inside = str(ctx.root / NAMING_COPY)
    outside = str(standard.resolve() / NAMING_COPY)
    assert module.refused_in_root(ctx.root, PermissionError(
        errno.EACCES, DENIED, inside)) == NAMING_COPY
    assert module.refused_in_root(ctx.root, FileNotFoundError(
        errno.ENOENT, "No such file or directory", inside)) is None
    assert module.refused_in_root(ctx.root, PermissionError(
        errno.EACCES, DENIED, outside)) is None


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
