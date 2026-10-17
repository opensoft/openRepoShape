# SPDX-License-Identifier: Apache-2.0
"""The session's `gh` guard (#296): it is reached, it answers the two probes
and whether a repository exists (#798), its check fails a test that ran `gh`,
and the doctor's `machine` row meets it.

`tests/conftest.py` puts the guard first on PATH for every child and checks,
after each test, that the guard refused none of that test's calls. Each test
here that runs the guard ON PURPOSE takes its own log lines with
`gh_guard.take()` and asserts on them, which is also what keeps them out of
that check. One row runs an inner pytest, in a plain subprocess, to show the
check itself failing a test: the decision function alone cannot show that.

WINDOWS. The tools under test start `gh` as a bare `["gh", ...]` argv, and
CreateProcess looks that up as `gh.exe` alone, so on Windows those calls never
reach the guard's `gh.cmd`; the two rows that need the bare lookup to land on
the guard wear `WINDOWS_SKIP`. `shutil.which` reads PATHEXT and does find
`gh.cmd`, so the rows that run the launcher it names run on all three
operating systems, and the Windows job is what proves `gh.cmd` works.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import REPO, WINDOWS_SKIP, run_script
from gh_guard import (GUARD_EXIT, NEEDS_A_LOGIN, NO_LOGIN_EXIT,
                      NOT_LOGGED_IN, VERSION_LINE, failure, record)

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


def test_whether_a_repository_exists_is_answered_as_a_gh_with_no_login(
        gh_guard, request):
    """`adopt-project.py check` asks `gh repo view <owner>/<name> --json
    nameWithOwner` of each leg it would create (#798). The guard answers as
    a `gh` with no login does, exit 4 and gh's own words, logs it as a
    probe, and the per-test check passes it. Any other `repo view` is still
    refused."""
    asked = ["repo", "view", "testorg/Northwind-spec", "--json",
             "nameWithOwner"]
    result = run([guard_launcher(gh_guard), *asked])
    assert result.returncode == NO_LOGIN_EXIT, result.stdout + result.stderr
    assert result.stdout == ""
    assert result.stderr == NEEDS_A_LOGIN + "\n"
    lines = gh_guard.take()
    assert [(kind, argv) for kind, argv, _ in calls(lines)] == [
        ("probe", asked)]
    assert calls(lines)[0][2].startswith(this_test(request))
    assert failure(lines) is None
    for near in (["repo", "view", "testorg/Northwind-spec"],
                 ["repo", "view", "testorg/Northwind", "--json",
                  "visibility"],
                 ["repo", "view", "testorg/Northwind-spec", "--json",
                  "name"],
                 ["repo", "view", "--web", "--json", "nameWithOwner"],
                 ["repo", "view", "testorg/a/b", "--json", "nameWithOwner"],
                 ["repo", "create", "testorg/Northwind-spec", "--json",
                  "nameWithOwner"]):
        assert failure([record(near, "")]) is not None, near


#: The argv `scaffold-project.py` (`remote_is_empty`) and `family.py` run to
#: ask whether a repository of their own exists, as each source spells it.
THEIR_VIEW = '["gh", "repo", "view", repository, "--json", "name"]'


def test_the_view_scaffold_and_family_ask_is_still_refused(gh_guard,
                                                           request):
    """The guard answers adopt's `--json nameWithOwner` alone (#798).
    `scaffold-project.py` and `family.py` ask `gh repo view <owner>/<name>
    --json name`, so a test of either that reaches gh with no stub of its
    own is refused, exit 97, and failed at teardown, as before #798."""
    for tool in (REPO / "scaffold-project.py", REPO / "scripts" / "family.py"):
        assert THEIR_VIEW in tool.read_text(encoding="utf-8"), tool
    asked = ["repo", "view", "acme/Atlas", "--json", "name"]
    result = run([guard_launcher(gh_guard), *asked])
    assert result.returncode == GUARD_EXIT, result.stdout + result.stderr
    assert "tests/conftest.py" in result.stderr, result.stderr
    lines = gh_guard.take()
    assert [(kind, argv) for kind, argv, _ in calls(lines)] == [
        ("refused", asked)]
    assert calls(lines)[0][2].startswith(this_test(request))
    message = failure(lines)
    assert message is not None
    assert "gh repo view acme/Atlas --json name " in message, message


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
        "(setup-project.py --preflight, exit 1): gh is not authenticated"
        ), machine["reason"]
    # The failed check's line, and not the closing verdict (#549): the
    # preflight's own words, which `setup-project.py` is still the author of.
    # The reason keeps its first sentence; its remedy is the row's NEXT.
    assert machine["detail"]["not_ready"] == [
        "gh is not authenticated. Run: gh auth login"], machine
    assert "see above" not in machine["reason"], machine["reason"]
    assert "gh auth login" not in machine["reason"], machine["reason"]
    taken = calls(gh_guard.take())
    assert [(kind, argv) for kind, argv, _ in taken] == [
        ("probe", ["--version"]), ("probe", ["auth", "status"])], taken
    assert all(test.startswith(this_test(request)) for _, _, test in taken)


#: THE INNER SUITE `test_the_check_fails_the_test_that_ran_gh_and_no_other`
#: runs: two modules, so a module fixture is finalized by the last test of
#: ITS module, and the session fixture by the last test of the run.
INNER_A = """\
import subprocess

import pytest


def gh(*args):
    return subprocess.run(["gh", *args], capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, check=False).returncode


@pytest.fixture(scope="module")
def calls_gh_at_module_end():
    yield
    gh("api", "module-end")


def test_probes_only():
    assert gh("--version") == 0
    assert gh("auth", "status") == 1


def test_refused_call():
    assert gh("api", "user") == 97


def test_module_fixture(calls_gh_at_module_end):
    pass
"""

INNER_B = """\
import subprocess

import pytest


@pytest.fixture(scope="session")
def calls_gh_at_session_end():
    yield
    subprocess.run(["gh", "api", "session-end"], capture_output=True,
                   stdin=subprocess.DEVNULL, check=False)


def test_innocent():
    pass


def test_last(calls_gh_at_session_end):
    pass
"""

#: One `ERROR at teardown of <test>` section of the inner run's report: the
#: test's name, then everything up to the next section or the summary.
TEARDOWN_ERROR = re.compile(
    r"^_+ ERROR at teardown of (\S+) _+\n(.*?)(?=^_{3,} |^=+ )",
    re.M | re.S)


@WINDOWS_SKIP  # the inner tests' bare `gh` is `gh.exe` to CreateProcess
def test_the_check_fails_the_test_that_ran_gh_and_no_other(tmp_path):
    """The teardown check itself, in a real pytest run: a test that ran `gh`
    ERRORS at its teardown naming the call, and a test that did not, passes.

    AN INNER PYTEST IN A SUBPROCESS, the one row here that needs one (the
    review of b111b51, S1): with the check disabled every other row stays
    green, because each takes its own lines. `-p conftest`, with `tests/` on
    PYTHONPATH, loads THIS suite's `conftest.py` as a plugin -- guard, hook
    and all -- and writes nothing under `tests/`; the `pytest.ini` beside the
    inner files makes their directory the inner run's root.

    Of the inner run's five tests, three must error at teardown, each naming
    its own call and phase: `gh api user` from a test's call; `gh api
    module-end` from a module fixture's finalizer, charged to the last test
    of ITS module and not to `test_innocent` after it; and `gh api
    session-end` from a session fixture's, charged to the last test of the
    run. `test_probes_only` asks the two probes and passes.
    """
    inner = tmp_path / "inner"
    inner.mkdir()
    (inner / "pytest.ini").write_bytes(b"[pytest]\n")
    (inner / "test_a.py").write_bytes(INNER_A.encode("utf-8"))
    (inner / "test_b.py").write_bytes(INNER_B.encode("utf-8"))
    env = {name: value for name, value in os.environ.items()
           if name not in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS")}
    here = str(Path(__file__).resolve().parent)
    env["PYTHONPATH"] = here + (os.pathsep + env["PYTHONPATH"]
                                if env.get("PYTHONPATH") else "")
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "conftest",
         "-p", "no:cacheprovider", f"--basetemp={tmp_path / 'inner-temp'}",
         "-q", "test_a.py", "test_b.py"],
        cwd=str(inner), env=env, capture_output=True, text=True,
        check=False, stdin=subprocess.DEVNULL)
    whole = result.stdout + result.stderr
    assert result.returncode == 1, whole
    assert re.search(r"\b5 passed, 3 errors\b", result.stdout), whole
    sections = dict(TEARDOWN_ERROR.findall(result.stdout))
    expected = {"test_refused_call": ("api user", "test_a.py", "call"),
                "test_module_fixture": ("api module-end", "test_a.py",
                                        "teardown"),
                "test_last": ("api session-end", "test_b.py", "teardown")}
    assert set(sections) == set(expected), whole
    for name, (call, module, phase) in expected.items():
        section = sections[name]
        assert "tests/conftest.py's gh guard logged 1 line(s)" in section, \
            section
        assert f"  gh {call}    [{module}::{name} ({phase})]" in section, \
            section
