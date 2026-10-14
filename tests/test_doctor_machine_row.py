# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py`'s `machine` row names what is NOT READY (#549).

THE DEFECT. A machine that failed the preflight read, in the table:

    this machine is missing something the fixes above may need
    (setup-project.py --preflight, exit 1): [!!] this machine is not ready yet
    (see above).

The reason appended the child's LAST line, which is the preflight's closing
verdict, and the verdict points "above" at the lines of the check that failed
-- lines the doctor keeps only in `--json`'s `detail.report`. Nothing above
the row said what was wrong.

THE FIX READS THE CHILD'S OWN LINES. The `[!!]` ones, one per failed check,
without the verdict that carries the same mark, and the reason keeps the
FIRST SENTENCE of each (`gh is not installed`): what follows it is the
scaffold's remedy, `re-run with --local-remote-dir <dir>` for one, a flag the
doctor refuses and under which the preflight says the machine is ready. The
whole lines are `detail.not_ready`. `setup-project.py` is not changed: its
mark is already the thing a line of its report is read by.

THE CHILD IS A SCRIPT THIS FILE WRITES, printing what the real preflight
prints, so the rows are the same on every host and none reaches `gh`. The one
run of the REAL preflight is `tests/test_gh_guard.py`'s machine-row test, where
the session guard answers `gh`; it holds this row to the wording
`setup-project.py` actually prints, and so would fail if the verdict's opening
ever stopped being the one `PREFLIGHT_VERDICT` names.
"""

from __future__ import annotations

import pytest

#: The doctor under test and the standard it is loaded from, imported from
#: the module that owns them. Importing a fixture gives this module its own
#: instance of it.
from test_shape_doctor import doctor_module, standard  # noqa: F401

#: The lines `setup-project.py --preflight` prints on STDOUT for a machine
#: whose first three checks pass: `ok()` and `say()` write there.
PASSED = (
    "openRepoShape setup\n"
    "\n"
    "(1) preflight\n"
    "  [ok] git 2.43.0\n"
    "  [ok] python 3.12.3 (/usr/bin/python3)\n"
    "  [ok] bootstrap runs as `python3 scripts/bootstrap.py` (make is not "
    "required)\n"
    "\n"
    "  nothing was created; this checked the machine only.\n")
#: The checks that failed, as `bad()` writes them to STDERR: `GIT_MISSING`
#: and the `gh` line, spelled out from `setup-project.py`.
GIT_MISSING = "git is not installed. Install it: https://git-scm.com/downloads"
GH_MISSING = ("gh is not installed. Install it: https://cli.github.com - or "
              "re-run with --local-remote-dir <dir> to try this offline "
              "against bare repositories on disk.")
#: What each of those says before its remedy, which is the part the row's
#: reason keeps.
GIT_FACT = "git is not installed"
GH_FACT = "gh is not installed"
#: The closing line, on the same stream and with the same mark.
VERDICT = "  [!!] this machine is not ready yet (see above).\n"

HEAD = ("this machine is missing something the fixes above may need "
        "(setup-project.py --preflight, exit 1)")
#: What the row adds when `git-filter-repo` is not on PATH.
ASIDE = ("; git-filter-repo is not on PATH, which only `adopt-project.py` "
         "needs")


def machine_row(module, tmp_path, monkeypatch, *, out="", err="", code=1,
                adoption=True) -> dict:
    """The `machine` row of a standard whose `setup-project.py` writes `out`
    to stdout and `err` to stderr and exits `code`, on a machine that does
    (`adoption`) or does not have `git-filter-repo` on PATH."""
    shape = tmp_path / "standard"
    shape.mkdir()
    (shape / "setup-project.py").write_text(
        "import sys\n"
        f"sys.stdout.write({out!r})\n"
        f"sys.stderr.write({err!r})\n"
        f"sys.exit({code})\n", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    ctx = module.Context(root)
    ctx.shape = shape
    monkeypatch.setattr(module.shutil, "which",
                        lambda name: f"/bin/{name}" if adoption else None)
    return module.check_machine(ctx).as_dict()


@pytest.mark.parametrize("adoption", [True, False])
def test_a_machine_that_is_not_ready_says_which_checks_failed(
        standard, tmp_path, monkeypatch, adoption):
    """Both failed checks, in the order the preflight made them, each by the
    first sentence of the line it printed, so no remedy of the scaffold's
    (`re-run with --local-remote-dir`, a flag the doctor refuses) is in the
    reason; the closing verdict is not among them; the adoption aside, when
    there is one, follows them; `detail.not_ready` keeps the whole lines; and
    the row still hands over the preflight as its one NEXT."""
    row = machine_row(
        doctor_module(standard), tmp_path, monkeypatch, out=PASSED,
        err=f"  [!!] {GIT_MISSING}\n  [!!] {GH_MISSING}\n{VERDICT}",
        adoption=adoption)
    said = f"{GIT_FACT}; {GH_FACT}"
    assert row["reason"] == f"{HEAD}: {said}{'' if adoption else ASIDE}"
    assert row["detail"]["not_ready"] == [GIT_MISSING, GH_MISSING]
    assert row["status"] == "n/a"
    assert row["next"].endswith(" --preflight")


def test_a_child_that_fails_without_naming_a_check_is_quoted_by_its_last_line(
        standard, tmp_path, monkeypatch):
    """A preflight that CRASHED printed no `[!!]` line, so there is nothing
    to name and the row keeps what it quoted before: the child's last line,
    here the exception."""
    row = machine_row(
        doctor_module(standard), tmp_path, monkeypatch,
        err="Traceback (most recent call last):\n"
            "  File \"setup-project.py\", line 1, in <module>\n"
            "ZeroDivisionError: division by zero\n")
    assert row["reason"] == f"{HEAD}: ZeroDivisionError: division by zero"
    assert row["detail"]["not_ready"] == []


def test_a_child_that_prints_only_the_verdict_is_not_quoted_as_the_reason(
        standard, tmp_path, monkeypatch):
    """Not reachable through the real preflight, which marks a failed check
    before it says the machine is not ready, and closed all the same: the
    last line the child printed is the verdict, which points at lines this
    table does not show, so it is not quoted and the reason is the head
    alone."""
    row = machine_row(doctor_module(standard), tmp_path, monkeypatch,
                      err=VERDICT)
    assert row["reason"] == HEAD
    assert row["detail"]["not_ready"] == []


@pytest.mark.parametrize("adoption", [True, False])
def test_a_machine_that_is_ready_says_so_and_names_nothing_missing(
        standard, tmp_path, monkeypatch, adoption):
    row = machine_row(doctor_module(standard), tmp_path, monkeypatch,
                      out=PASSED, code=0, adoption=adoption)
    ready = "this machine is ready (setup-project.py --preflight, exit 0)"
    assert row["reason"] == ready + ("" if adoption else ASIDE)
    assert row["detail"]["not_ready"] == []
    assert row["next"] is None


def test_preflight_failures_reads_the_marked_lines_of_a_constructed_report(
        standard):
    """`preflight_failures` on a report built here: only `[!!]` lines count,
    indented or not and in the order printed; `[ok]` and `[??]` lines, the
    report's other lines and the closing verdict do not; typography is
    flattened as `detail.report` is; and a report with nothing marked, or
    only the verdict, names nothing."""
    failures = doctor_module(standard).preflight_failures
    report = ("(1) preflight\n"
              "  [ok] git 2.43.0\n"
              "  [!!] gh is not authenticated \u2014 run: gh auth login\n"
              "  [??] git core.autocrlf is true.\n"
              "[!!] python 3.8 is too old\n"
              "  [!!]\n"
              "  [!!] this machine is not ready yet (see above).\n"
              "  nothing was created; this checked the machine only.\n")
    assert failures(report) == [
        "gh is not authenticated -- run: gh auth login",
        "python 3.8 is too old"]
    assert failures("  [ok] git 2.43.0\n") == []
    assert failures(VERDICT) == []
    assert failures("") == []


def test_first_sentence_stops_at_the_first_full_stop_that_ends_one(standard):
    """`first_sentence` keeps what is not ready and drops the remedy after
    it: the real preflight lines, a full stop inside a version number that
    ends nothing, a line that ends on its stop, and one with none."""
    first = doctor_module(standard).first_sentence
    lines = [
        "gh is not authenticated. Run: gh auth login",
        GH_MISSING,
        "this interpreter is 3.8, and 3.9 or newer is required. Install a "
        "newer Python and re-run it with that one: https://www.python.org/",
        "ends on its stop.",
        "no stop at all",
        "a.b and 3.9 end nothing",
        ""]
    assert [first(line) for line in lines] == [
        "gh is not authenticated",
        GH_FACT,
        "this interpreter is 3.8, and 3.9 or newer is required",
        "ends on its stop",
        "no stop at all",
        "a.b and 3.9 end nothing",
        ""]
