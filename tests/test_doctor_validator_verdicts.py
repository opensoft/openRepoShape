# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` reads a validator's output under ONE rule: a verdict is
a printed `FINDING` or `REFUSED`, anything else non-zero is a crash, and a
pass that printed `WARNING` or `  note ` lines is a `note` (#410, #448, with
#447 and #460's pins-note line riding along).

FOUR WAYS A ROW STILL SAID MORE, OR LESS, THAN THE CHILD DID.

- #447: `crashed()` needed a `Traceback` line, so a validator killed by a
  signal (a negative exit), ended by `os._exit(1)` with nothing printed,
  holding merge-conflict markers (a `SyntaxError`, which prints no traceback
  header) or failing argparse (`usage:`, exit 2) "reports a finding" or
  "refuses": a statement about the project from a child that never read it.
- #410: both `naming` rows read the exit code alone, so a checkout of the
  standard whose own naming script crashed made a compliant project
  `INVALID (naming)`, and a directory whose name is not UTF-8 got the
  script's `UnicodeEncodeError` quoted as a finding about the name.
- #448: `validate-manifest.py`'s `WARNING naming-referent-chain` on exit 0
  appeared nowhere in the report, and a red manifest row quoted that WARNING
  as its reason when an earlier leg printed it before a later leg's FINDING.
- #460's pins-note line: `validate-pins.py`'s `  note ` lines on exit 0 were
  dropped, and a note printed after a `  skip ` was read as that skip's text.

THE HARNESS IS #357's (`tests/test_doctor_validator_rows.py`), imported: its
crash builder, its copy of the standard and its `gh` stub, over the session's
standard and project from `tests/test_shape_doctor.py`. Every assertion is on
what a command does -- a row's status, its `detail`, the verdict, a NEXT that
is run -- and on the words a row quotes from its child, never on a `why`.

NOTHING HERE REACHES A NETWORK. The scaffolds use local bare remotes; a run
whose validator asks `gh api` for a neutral product's tree has #357's
logging stub first on `PATH`, ahead of the session guard, and is
`WINDOWS_SKIP` for its shebang.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from conftest import WINDOWS_SKIP, clone_just_pushed, run_script
#: The layer stand-in a chain descendant pins, from the module that scaffolds
#: one: a second way of building it would test a different one.
from test_scaffold_pin_and_reuse import layer_repo
#: #357's harness, and through it the session's standard and project. Each
#: fixture imported gives this module its own instance of it.
from test_doctor_validator_rows import (  # noqa: F401
    CRASH, DOCTOR, TEMPLATE_FALLBACK, assert_next_runs_the_roots_own,
    crashing, doctor, doctor_module, logging_gh, payload_of, project,
    rows_of, scaffolded_here, standard, standard_under,
)

NAMING_SCRIPT = "scripts/validate-repository-naming.py"
#: What every crash row says, the validators' and the naming rows' alike.
CRASHED = "crashed before reaching a verdict"
#: The tail #410's ruling gives a crashed naming script's row in a root.
NOT_THE_PROJECTS = ("that script is this checkout's, not the project's, so "
                    "nothing here is a statement about the project")


def command_of(row: dict) -> list:
    """The row's NEXT as the argv it runs; the paths here need no quoting."""
    return row["next"].split()


def run_argv(command: list) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


# --- #447: a crash is told by what the child printed -------------------------

#: The ways a root's own `validate-pins.py` ends with no verdict, as
#: `(source, expected exit, words the reason quotes)`. The signals are named,
#: not numbered, and read inside the test: Windows has no SIGKILL.
MERGE_MARKERS = "<<<<<<< HEAD\nimport sys\n=======\nimport os\n>>>>>>> theirs\n"
ENDINGS = {
    "sigkill": ("import os, signal\nos.kill(os.getpid(), signal.SIGKILL)\n",
                "SIGKILL", "it printed nothing and was ended by SIGKILL"),
    "sigterm": ("import os, signal\nos.kill(os.getpid(), signal.SIGTERM)\n",
                "SIGTERM", "it printed nothing and was ended by SIGTERM"),
    "os-exit": ("import os\nos._exit(1)\n", 1, "it printed nothing"),
    "merge-markers": (None, 1, "SyntaxError"),
    "usage": ("import sys\n"
              "print('usage: validate-pins.py [-h]', file=sys.stderr)\n"
              "print('validate-pins.py: error: unrecognized arguments: x', "
              "file=sys.stderr)\n"
              "sys.exit(2)\n",
              2, "validate-pins.py: error: unrecognized arguments: x"),
}


def ending(how: str, own: Path) -> tuple:
    """`(source, exit code, words)` for `how`, the source of a merge left
    unresolved being the root's own file with the markers appended."""
    source, code, words = ENDINGS[how]
    if source is None:
        source = own.read_text(encoding="utf-8") + MERGE_MARKERS
    if isinstance(code, str):
        code = -int(getattr(signal, code))
    return source, code, words


@pytest.mark.parametrize("how", [
    pytest.param("sigkill", marks=WINDOWS_SKIP),
    pytest.param("sigterm", marks=WINDOWS_SKIP),
    "os-exit", "merge-markers", "usage"])
def test_a_gate_that_ended_without_a_verdict_is_a_crash_whatever_it_printed(
        standard, project, tmp_path, how):
    """#447: the root's own `validate-pins.py` ended by a signal, by
    `os._exit(1)`, by a `SyntaxError` or by argparse is a CRASH row: it says
    it crashed, carries `detail.crashed`, quotes what the child last said
    (or that it said nothing, naming the signal), and never "reports a
    finding" or "refuses".

    THE ROOT'S OWN COPY IS STILL A FINDING about the project's gate, #357's
    line: a gate that cannot run is a broken gate. So the verdict is the one
    an edited copy gives, DRIFTED, exit 1, never CANNOT ANSWER, and the NEXT
    is that gate's own line. `WINDOWS_SKIP` for the two signals only: a
    process there is ended with the code its killer chose, not a negative
    one.
    """
    own = project / TEMPLATE_FALLBACK["pins"]["own"]
    source, code, words = ending(how, own)
    here, root, row_id, own_copy = crashing("own-pins", standard, project,
                                            None, tmp_path, source)
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)[row_id]
    assert row_id == "pins" and own_copy is True
    assert row["status"] == "FINDING", row
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["own_copy"] is True, row
    assert row["detail"]["exit"] == code, row
    assert "environment" not in row["detail"], row
    assert f"{CRASHED} (exit {code}): " in row["reason"], row
    assert words in row["reason"], row
    assert "reports a finding" not in row["reason"], row
    assert "refuses" not in row["reason"], row
    assert row["why"].startswith("read its output in full"), row
    assert_next_runs_the_roots_own(row, root, "validate-pins.py")
    assert result.returncode == 1, result.stdout + result.stderr
    assert payload["verdict"].startswith("DRIFTED"), payload


@pytest.mark.parametrize("how", [pytest.param("sigkill", marks=WINDOWS_SKIP),
                                 "os-exit"])
def test_the_standards_template_ended_without_a_verdict_cannot_answer(
        standard, project, tmp_path, how):
    """#447's other half: the standard's TEMPLATE copy, for a root with none
    of its own, killed or ended by `os._exit(1)` is this checkout's failure:
    `detail.environment`, CANNOT ANSWER, exit 3 -- as #357 already ruled for
    a template that raised, and as it did not for one that printed nothing.
    """
    template = standard / TEMPLATE_FALLBACK["manifest"]["template"]
    source, code, words = ending(how, template)
    here, root, row_id, own_copy = crashing("template", standard, project,
                                            None, tmp_path, source)
    result = doctor(here, root, "--json")
    row = rows_of(result)[row_id]
    assert own_copy is False
    assert row["status"] == "FINDING", row
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["environment"] is True, row
    assert row["detail"]["exit"] == code, row
    assert words in row["reason"], row
    assert "reports a finding" not in row["reason"], row
    assert result.returncode == 3, result.stdout + result.stderr
    assert payload_of(result)["verdict"].startswith(
        f"CANNOT ANSWER ({row['label']}: "), result.stdout


def test_crashed_reads_the_output_and_never_a_traceback(standard):
    """`crashed` on constructed outputs, on every platform: None for exit 0
    and for any output holding a `FINDING` or `REFUSED` line, a negative
    exit included (a finding printed before the child died still stands);
    otherwise the last non-empty line, or words naming what was printed and,
    for a negative exit, the signal."""
    crashed = doctor_module(standard).crashed
    assert crashed(0, "") is None
    assert crashed(0, "Traceback (most recent call last):\nE: x\n") is None
    assert crashed(1, "FINDING pin-x: a finding\nTraceback (most recent "
                      "call last):\nRuntimeError: boom\n") is None
    assert crashed(-9, "  ok  a\nFINDING pin-x: printed, then killed\n") \
        is None
    assert crashed(2, "REFUSED pin-y: a refusal\n") is None
    assert crashed(1, "") == "it printed nothing"
    assert crashed(-int(signal.SIGTERM), "") == \
        "it printed nothing and was ended by SIGTERM"
    assert crashed(-200, "") == "it printed nothing and was ended by " \
        "signal 200"
    assert crashed(-int(signal.SIGTERM), "  ok  a\n  ok  b\n\n") == "ok  b"
    assert crashed(1, '  File "x.py", line 3\n    <<<<<<< HEAD\n    ^^\n'
                      "SyntaxError: invalid syntax\n") == \
        "SyntaxError: invalid syntax"
    assert crashed(2, "usage: v [-h]\nv: error: the following arguments "
                      "are required: --root\n") == \
        "v: error: the following arguments are required: --root"
    assert crashed(4, "WARNING w: something\n") == "WARNING w: something"


# --- #410: the naming rows ask `crashed` too --------------------------------

def naming_crashes(standard: Path, tmp_path: Path) -> Path:
    """A COPY of the standard, history and all, whose own naming script
    raises: the case #410 was filed for, built as #357 builds its template
    crash."""
    here = standard_under(standard, tmp_path, "naming-crash")
    (here / NAMING_SCRIPT).write_text(CRASH, encoding="utf-8")
    return here


def test_a_crashed_naming_script_cannot_answer_for_a_compliant_project(
        standard, project, tmp_path):
    """(2) of the issue: a compliant project asked from a checkout whose
    naming script raises is CANNOT ANSWER, exit 3, never `INVALID (naming)`.

    The row carries `detail.crashed` and `detail.environment`, as a crashed
    TEMPLATE validator's does, says the script crashed, quotes the exception
    and ends saying nothing here is about the project. Its NEXT is still the
    script's own `--explain` line, and run it shows the exception the row
    quoted, with the exit the row records. THE CONTROL is the same project
    from the session's standard: `ok`.
    """
    root = project.resolve()
    control = rows_of(doctor(standard, root, "--json"))["naming"]
    assert control["status"] == "ok", control
    here = naming_crashes(standard, tmp_path)
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)["naming"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["environment"] is True, row
    assert row["detail"]["exit"] == 1, row
    assert (f"the standard's {NAMING_SCRIPT} {CRASHED} (exit 1): "
            "RuntimeError: boom; ") in row["reason"], row
    assert row["reason"].endswith(NOT_THE_PROJECTS), row
    assert "naming policy is not satisfied" not in row["reason"], row
    assert result.returncode == 3, result.stdout + result.stderr
    assert payload["verdict"].startswith("CANNOT ANSWER (naming: "), payload
    module = doctor_module(standard)
    assert row["next"] == (
        f"{module.PYTHON} {module.quote_arg(here.resolve() / NAMING_SCRIPT)} "
        f"--explain --project {module.quote_arg(root / 'project.yaml')}"), \
        row["next"]
    assert row["why"].startswith("read its output in full"), row
    ran = run_argv(command_of(row))
    assert ran.returncode == row["detail"]["exit"], ran.stdout + ran.stderr
    assert "RuntimeError: boom" in ran.stdout + ran.stderr
    text = doctor(here, root)
    assert text.returncode == 3, text.stdout + text.stderr
    assert "REFUSED shape-doctor-cannot-answer: " in text.stderr, text.stderr
    assert f"\n  Remediation: {row['next']}\n" in text.stderr, text.stderr


def test_a_crashed_naming_script_leaves_a_directory_not_a_shape_root(
        standard, tmp_path):
    """The same checkout asked about a directory that is NOT a root: the
    verdict stays NOT A SHAPE ROOT, exit 2, because `verdict_for` decides
    that before `cannot_answer`, and the row is the crash row, marked as in
    a root, not a FINDING quoting the exception as a fact about the name.

    AND THE TEXT REPORT PRINTS NO `shape-doctor-cannot-answer` refusal: one
    under a NOT A SHAPE ROOT verdict would contradict the line above it.
    """
    here = naming_crashes(standard, tmp_path)
    away = tmp_path / "elsewhere" / "Atlas"
    away.mkdir(parents=True)
    result = doctor(here, away, "--json")
    payload = payload_of(result)
    row = rows_of(result)["naming"]
    assert result.returncode == 2, result.stdout + result.stderr
    assert payload["verdict"] == "NOT A SHAPE ROOT", payload
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["environment"] is True, row
    assert row["reason"].startswith(
        f"Atlas: the standard's {NAMING_SCRIPT} {CRASHED} (exit 1): "
        "RuntimeError: boom; "), row
    assert not row["reason"].startswith("Atlas: RuntimeError"), row
    assert command_of(row)[-3:] == ["--explain", "--", "Atlas"], row["next"]
    assert row["why"].startswith("read its output in full"), row
    text = doctor(here, away)
    assert text.returncode == 2, text.stdout + text.stderr
    assert "NOT A SHAPE ROOT   (exit 2)" in text.stdout, text.stdout
    assert "shape-doctor-cannot-answer" not in text.stderr, text.stderr


@WINDOWS_SKIP
def test_a_name_that_is_not_utf8_is_never_an_exception_quoted_as_a_finding(
        standard, tmp_path):
    """(1) of the issue, with the stock standard: a directory whose name
    holds the byte `\\xff`. The row is never a FINDING quoting the script's
    exception about the name.

    MEASURED ON MAIN 5ed3e5d (Python 3.12.3, `LC_ALL=C.UTF-8`): the stock
    script, under the `PYTHONIOENCODING=utf-8` every validator child gets,
    still raises `UnicodeEncodeError` printing the name in its `--explain`
    block, and the row said `FINDING | Atl?as: UnicodeEncodeError: ...`. So
    today the row is the crash row; a script that prints such a name will
    make it the `naming-unclassified` FINDING, and either is a true row --
    what this test holds is that the exception is never the finding.
    `WINDOWS_SKIP`: Windows has no name that is not UTF-8, and a disk that
    refuses one (APFS) skips.
    """
    name = os.fsdecode(b"Atl\xffas")
    here = tmp_path / "elsewhere" / name
    try:
        here.mkdir(parents=True)
    except OSError as exc:
        pytest.skip(f"this filesystem refuses a name that is not UTF-8: "
                    f"{exc}")
    result = doctor(standard, here, "--json")
    payload = payload_of(result)
    row = rows_of(result)["naming"]
    assert result.returncode == 2, result.stdout + result.stderr
    assert payload["verdict"] == "NOT A SHAPE ROOT", payload
    assert row["status"] == "FINDING", row
    assert row["detail"]["names"] == [name], row
    if row["detail"].get("crashed"):
        assert row["detail"]["environment"] is True, row
        assert f"{CRASHED} (exit 1): UnicodeEncodeError" in row["reason"], row
        assert "this checkout's, not this directory's" in row["reason"], row
    else:
        assert "FINDING naming-unclassified" in row["reason"], row
        assert "Error" not in row["reason"], row
    assert not row["reason"].startswith("Atl?as: UnicodeEncodeError"), row


# --- #448: a pass that warned is a note, and a red row quotes its verdict ---

@pytest.fixture(scope="module")
def chain_descendant(standard, tmp_path_factory) -> dict:
    """#448's repro: `codexDox` pins the LAYER `openXdox` and records the
    chain `openXdox,openDox`, scaffolded from the session's standard with
    the layer's stand-in as `--pin-source`, then cloned AWAY from it, so no
    tree answers for the chain's middle link and nothing beside the clone
    holds one."""
    base = tmp_path_factory.mktemp("chain-descendant")
    layer, commit = layer_repo(base / "standin")
    made = run_script(
        standard / "scaffold-project.py", "--org", "codexSoft", "--project",
        "codexDox", "--elected-by", "Test Human", "--elected-on",
        "2026-09-05", "--pin", f"openXdox@{commit}", "--referent-chain",
        "openXdox,openDox", "--pin-source", str(layer),
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert made.returncode == 0, made.stderr + made.stdout
    clone = base / "away" / "codexDox"
    clone.parent.mkdir()
    cloned = clone_just_pushed(base / "remotes" / "codexDox.git", clone)
    assert cloned.returncode == 0, cloned.stderr
    assert not (clone.parent / "openXdox").exists()
    return {"clone": clone, "layer": layer}


def doctor_offline(standard: Path, root: Path, tmp_path: Path):
    """The doctor with #357's logging `gh` first on PATH, for the run whose
    `validate-pins.py` asks `gh api` for the layer's tree: it answers 97,
    and the validator prints its `skip`."""
    bin_dir, _calls = logging_gh(tmp_path / "gh")
    return run_script(standard / DOCTOR, "--root", str(root), "--json",
                      env={"PATH": f"{bin_dir}{os.pathsep}"
                                   f"{os.environ['PATH']}"})


@WINDOWS_SKIP
def test_a_chain_nothing_here_could_check_is_a_note_and_still_compliant(
        standard, chain_descendant, tmp_path):
    """#448: the root's own `validate-manifest.py` prints `WARNING
    naming-referent-chain` and exits 0, and the `manifest` row is a `note`
    whose reason quotes it, with `detail.warnings` holding it and no NEXT.
    A note moves no verdict: COMPLIANT, exit 0, as before."""
    result = doctor_offline(standard, chain_descendant["clone"], tmp_path)
    payload = payload_of(result)
    row = rows_of(result)["manifest"]
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["verdict"] == "COMPLIANT", payload
    assert row["status"] == "note", row
    assert row["next"] is None, row
    assert row["detail"]["exit"] == 0, row
    (warning,) = row["detail"]["warnings"]
    assert warning.startswith(
        "naming-referent-chain: leg 'assembly': declared-unverified: "), row
    assert "SHAPE_PIN_SOURCE_OPENXDOX" in warning, row
    assert row["reason"] == (
        "the project's own scripts/validate-manifest.py passes, but warns: "
        + warning), row
    assert "skipped" not in row["detail"], row
    assert "notes" not in row["detail"], row


def test_a_chain_whose_link_is_read_is_ok(standard, chain_descendant):
    """The control, on every platform: `SHAPE_PIN_SOURCE_OPENXDOX` names the
    layer's stand-in, so the link is read, the validator prints no WARNING
    and the row is `ok` -- and no `gh` is asked, the pin's digest
    recomputing from the same tree."""
    result = run_script(
        standard / DOCTOR, "--root", str(chain_descendant["clone"]),
        "--json",
        env={"SHAPE_PIN_SOURCE_OPENXDOX": str(chain_descendant["layer"])})
    payload = payload_of(result)
    rows = rows_of(result)
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["verdict"] == "COMPLIANT", payload
    assert rows["manifest"]["status"] == "ok", rows["manifest"]
    assert "warnings" not in rows["manifest"]["detail"], rows["manifest"]
    assert rows["pins"]["status"] == "ok", rows["pins"]


@WINDOWS_SKIP
def test_a_red_manifest_row_quotes_its_finding_and_never_the_warning(
        standard, chain_descendant, tmp_path):
    """#448's decision 4: the same root with the spec leg's `naming.role`
    set to `code`, a true `naming-role` finding. The validator prints the
    assembly leg's WARNING FIRST and the spec leg's FINDING after it (held
    below, so the test means something), and the row quotes the FINDING:
    a row that fails never names a note as its reason, and collects none."""
    root = tmp_path / "away" / "codexDox"
    shutil.copytree(chain_descendant["clone"], root, symlinks=True)
    manifest = root / "project.yaml"
    body = manifest.read_bytes()
    assert body.count(b"      role: spec\n") == 1, body
    manifest.write_bytes(body.replace(b"      role: spec\n",
                                      b"      role: code\n"))
    gate = run_script(root / "scripts" / "validate-manifest.py", cwd=root)
    assert gate.returncode == 1, gate.stdout + gate.stderr
    said = gate.stderr
    assert 0 <= said.index("WARNING naming-referent-chain") \
        < said.index("FINDING naming-role"), said
    result = doctor_offline(standard, root.resolve(), tmp_path)
    row = rows_of(result)["manifest"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["exit"] == 1, row
    assert "crashed" not in row["detail"], row
    assert "warnings" not in row["detail"], row
    assert ("reports a finding (exit 1): FINDING naming-role: leg 'spec': "
            in row["reason"]), row
    assert "WARNING" not in row["reason"], row
    assert "naming-referent-chain" not in row["reason"], row


@pytest.mark.parametrize("output, quoted", [
    ("WARNING w: a note\nFINDING f: the finding\n", "FINDING f: the finding"),
    ("WARNING w: a note\n  ok  a\nREFUSED r: a refusal\n",
     "REFUSED r: a refusal"),
    ("  ok  a\nWARNING w: a note\nWARNING v: another\nlast line\n",
     "WARNING w: a note"),
    ("  ok  a\nlast line\n\n", "last line"),
    ("", ""),
])
def test_run_validator_quotes_a_verdict_line_before_any_warning(
        standard, tmp_path, output, quoted):
    """`run_validator`'s quoted line, asked of a child that prints `output`
    on stderr and exits 1, on every platform: the first `FINDING` or
    `REFUSED`, else the first `WARNING`, else the last line (#448)."""
    module = doctor_module(standard)
    root = tmp_path / "root"
    root.mkdir()
    probe = root / "probe.py"
    probe.write_text("import sys\n"
                     f"sys.stderr.write({output!r})\n"
                     "sys.exit(1)\n", encoding="utf-8")
    code, said, whole = module.run_validator(module.Context(root), probe, [])
    assert code == 1, whole
    assert said == quoted, whole


# --- #460's pins-note line: a note is its own item ---------------------------

SKIP_LINES = ("  skip openGlass: pin commit 0123456789ab digest NOT rechecked "
              "(gh-unreadable: one\n"
              "two). A --pin-source would verify it offline.\n")
SKIP_TEXT = ("openGlass: pin commit 0123456789ab digest NOT rechecked "
             "(gh-unreadable: one two). A --pin-source would verify it "
             "offline.")
NOTE_LINE = ("  note neutral-pin-source-collides: project.yaml declares "
             "'open-glass' and 'open_glass'.\n")
NOTE_TEXT = ("neutral-pin-source-collides: project.yaml declares "
             "'open-glass' and 'open_glass'.")


@pytest.mark.parametrize("order", ["skip-then-note", "note-then-skip"])
def test_a_note_and_a_skip_each_land_in_their_own_key(standard, project,
                                                      tmp_path, order):
    """The root's own `validate-pins.py` replaced by a stub that passes after
    printing an `  ok `, a two-line `  skip ` and a `  note `, in each order,
    on every platform: the row is a `note`, the skip is `detail.skipped`
    WHOLE, the note is `detail.notes`, neither swallows the other, the
    reason quotes them in the order printed, and the `pins ok` summary is in
    neither."""
    blocks = [SKIP_LINES, NOTE_LINE]
    if order == "note-then-skip":
        blocks.reverse()
    stub = ("import sys\n"
            "sys.stdout.write(" + repr("  ok  spec: pin commit "
                                       "0123456789ab digest recomputes\n"
                                       + "".join(blocks) + "pins ok\n")
            + ")\n")
    here, root, row_id, _own = crashing("own-pins", standard, project, None,
                                        tmp_path, stub)
    row = rows_of(doctor(here, root, "--json"))[row_id]
    assert row["status"] == "note", row
    assert row["next"] is None, row
    assert row["detail"]["exit"] == 0, row
    assert row["detail"]["skipped"] == [SKIP_TEXT], row
    assert row["detail"]["notes"] == [NOTE_TEXT], row
    lead = "the project's own scripts/validate-pins.py passes, but "
    said = [f"did not recheck: {SKIP_TEXT}", f"notes: {NOTE_TEXT}"]
    if order == "note-then-skip":
        said.reverse()
    assert row["reason"] == lead + "; ".join(said), row
    for text in row["detail"]["skipped"] + row["detail"]["notes"]:
        assert "pins ok" not in text, row
        assert "  ok  " not in text, row


def test_reported_reads_every_kind_in_the_order_printed(standard):
    """`reported` on a constructed output, on every platform: each `  skip `,
    `WARNING ` and `  note ` block whole, less its prefix, up to the next
    item; and a line before any block, an `  ok` and the summary are none
    of them."""
    module = doctor_module(standard)
    whole = ("Notice: not part of a block\n"
             "  ok  a: fine\n"
             "  note n1: one\n"
             "  more of n1\n"
             "  skip s1: NOT rechecked (gh-unreadable: x\n"
             "y). A --pin-source.\n"
             "WARNING w1: a link not read\n"
             "  note n2: two\n"
             "  skip s2: NOT rechecked.\n"
             "pins ok\n")
    said = module.reported(whole)
    assert said == [
        ("notes", "n1: one more of n1"),
        ("skipped", "s1: NOT rechecked (gh-unreadable: x y). A --pin-source."),
        ("warnings", "w1: a link not read"),
        ("notes", "n2: two"),
        ("skipped", "s2: NOT rechecked.")]
    assert module.skipped(whole) == [
        "s1: NOT rechecked (gh-unreadable: x y). A --pin-source.",
        "s2: NOT rechecked."]
    assert module.passed_but(said) == (
        "notes: n1: one more of n1; did not recheck: s1: NOT rechecked "
        "(gh-unreadable: x y). A --pin-source.; warns: w1: a link not read; "
        "notes: n2: two; did not recheck: s2: NOT rechecked.")
    assert module.passed_but([("skipped", "a"), ("skipped", "b")]) == \
        "did not recheck: a; b"
    assert module.reported("  ok  a\nmanifest ok: x\n") == []

