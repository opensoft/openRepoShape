# SPDX-License-Identifier: Apache-2.0
"""The session's `gh` guard (#296): it is reached, it answers the two probes,
its check fails a test that ran `gh`, and the doctor's `machine` row meets it.

`tests/conftest.py` puts the guard first on PATH for every child and checks,
after each test, that the guard refused none of that test's calls. Each test
here that runs the guard ON PURPOSE takes its own log lines with
`gh_guard.take()` and asserts on them, which is also what keeps them out of
that check.

WINDOWS. The tools under test start `gh` as a bare `["gh", ...]` argv, and
CreateProcess looks that up as `gh.exe` alone, so on Windows those calls never
reach the guard's `gh.cmd`; the two rows that need the bare lookup to land on
the guard wear `WINDOWS_SKIP`. `shutil.which` reads PATHEXT and does find
`gh.cmd`, so the rows that run the launcher it names run on all three
operating systems, and the Windows job is what proves `gh.cmd` works.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from conftest import REPO, WINDOWS_SKIP, run_script
from gh_guard import (GUARD_EXIT, NOT_LOGGED_IN, VERSION_LINE, failure,
                      record)

DOCTOR = REPO / "shape-doctor.py"


def calls(lines) -> list:
    """The guard's log lines, parsed: `(kind, argv, test)` each."""
    return [(entry["kind"], entry["argv"], entry["test"])
            for entry in map(json.loads, lines)]


def this_test(request) -> str:
    """How `$PYTEST_CURRENT_TEST` names the running test, before its phase."""
    return request.node.nodeid + " ("


def guard_launcher(gh_guard) -> str:
    """The `gh` PATH lookup finds, asserted to be the guard's own launcher:
    `gh` on POSIX, `gh.cmd` on Windows (PATHEXT)."""
    found = shutil.which("gh")
    assert found, "no gh on PATH at all: the session guard is not installed"
    assert Path(found).resolve().parent == gh_guard.directory.resolve(), (
        f"PATH finds {found}, not the session guard in {gh_guard.directory}")
    return found


def run(argv) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL)


@WINDOWS_SKIP  # a bare `gh` is `gh.exe` to CreateProcess, never `gh.cmd`
def test_a_bare_gh_reaches_the_guard_and_is_refused(gh_guard, request):
    """A child that runs `gh api user` by bare name, under the session's
    PATH, meets the guard: exit 97, one line naming `tests/conftest.py`, and
    one log line carrying the argv and this test's id."""
    guard_launcher(gh_guard)
    result = run(["gh", "api", "user"])
    assert result.returncode == GUARD_EXIT, result.stdout + result.stderr
    assert result.stdout == ""
    [line] = result.stderr.splitlines()
    assert "tests/conftest.py" in line and "`gh api user`" in line, line
    [(kind, argv, test)] = calls(gh_guard.take())
    assert (kind, argv) == ("refused", ["api", "user"])
    assert test.startswith(this_test(request)), test


def test_the_launcher_path_lookup_finds_is_the_guard(gh_guard, request):
    """The same refusal through the launcher `shutil.which("gh")` names, run
    by its path: the `#!/bin/sh` one on POSIX, `gh.cmd` on Windows, so the
    Windows job runs the batch launcher and its exit status."""
    result = run([guard_launcher(gh_guard), "api", "user"])
    assert result.returncode == GUARD_EXIT, result.stdout + result.stderr
    assert "tests/conftest.py" in result.stderr, result.stderr
    [(kind, argv, test)] = calls(gh_guard.take())
    assert (kind, argv) == ("refused", ["api", "user"])
    assert test.startswith(this_test(request)), test


def test_the_two_probes_answer_as_a_gh_with_no_login(gh_guard, request):
    """`gh --version` prints ONE line whose third word is what
    `setup-project.py`'s `program_version` reports, and exits 0; `gh auth
    status` exits 1 with gh's own not-logged-in words on stderr. Both are
    logged as probes, and the per-test check passes them."""
    gh = guard_launcher(gh_guard)
    version = run([gh, "--version"])
    assert version.returncode == 0, version.stderr
    assert version.stdout.splitlines() == [VERSION_LINE], version.stdout
    assert version.stdout.split()[2] == "test-guard"
    assert "tests/conftest.py" in VERSION_LINE
    status = run([gh, "auth", "status"])
    assert status.returncode == 1, status.stdout + status.stderr
    assert status.stdout == ""
    assert status.stderr == NOT_LOGGED_IN + "\n"
    lines = gh_guard.take()
    assert [(kind, argv) for kind, argv, _ in calls(lines)] == [
        ("probe", ["--version"]), ("probe", ["auth", "status"])]
    assert all(test.startswith(this_test(request))
               for _, _, test in calls(lines))
    assert failure(lines) is None


def test_the_check_fails_on_a_refused_call_and_passes_on_probes_alone():
    """The per-test check's decision, called directly on log lines.

    Probes alone, or nothing, pass. One refused call fails, and the message
    names the call, the test that made it and `tests/conftest.py`. A call
    that only LOOKS like a probe is not one, and a line the guard did not
    write fails rather than being skipped."""
    probes = [record(["--version"], "tests/x.py::t (call)"),
              record(["auth", "status"], "tests/x.py::t (call)")]
    assert failure([]) is None
    assert failure(probes) is None

    message = failure(probes + [record(["api", "user"],
                                       "tests/x.py::t (call)")])
    assert message is not None
    assert "gh api user" in message and "tests/x.py::t (call)" in message
    assert "tests/conftest.py" in message
    assert "--version" not in message and "auth status" not in message, (
        "the probes beside the refused call are not calls to name")

    for near in (["version"], ["--version", "--json"],
                 ["auth", "status", "--hostname", "github.com"],
                 ["auth", "token"], []):
        assert failure([record(near, "")]) is not None, near
    for foreign in ("not json", "[]", '{"argv": "--version"}', "{}"):
        assert failure([foreign]) is not None, foreign


@WINDOWS_SKIP  # the preflight's bare `gh` reaches the guard only on POSIX
def test_the_doctors_machine_row_meets_the_guard(gh_guard, project, request):
    """One doctor run over a scaffolded project: its `machine` row asked the
    guard exactly the two probes, and says what a `gh` with no login makes
    it say, on every machine.

    `[ok] gh test-guard` is the version line's third word; `gh is not
    authenticated` is the answer to `gh auth status`; the preflight exits 1
    and so never reaches `gh api user`. Only the `machine` row is read: this
    project is scaffolded from the working tree, which the doctor's own
    suite (`tests/test_shape_doctor.py`) explains is not a standard to judge
    the other rows against."""
    result = run_script(DOCTOR, "--root", str(project), "--json")
    payload = json.loads(result.stdout)
    [machine] = [row for row in payload["rows"] if row["id"] == "machine"]
    assert machine["status"] == "n/a", machine
    assert machine["detail"]["exit"] == 1, machine
    report = machine["detail"]["report"]
    assert "[ok] gh test-guard" in report, report
    assert "[!!] gh is not authenticated. Run: gh auth login" in report, \
        report
    assert not any("gh is authenticated" in line for line in report), report
    assert machine["reason"].startswith(
        "this machine is missing something the fixes above may need "
        "(setup-project.py --preflight, exit 1)"), machine["reason"]
    taken = calls(gh_guard.take())
    assert [(kind, argv) for kind, argv, _ in taken] == [
        ("probe", ["--version"]), ("probe", ["auth", "status"])], taken
    assert all(test.startswith(this_test(request)) for _, _, test in taken)
