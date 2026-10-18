# SPDX-License-Identifier: Apache-2.0
"""`release.yml`'s install check: the children the doctor starts under `-S`
(#894).

THE HOLE. `shape-doctor.py` starts every child as `python -S` (#342, #636),
and the install check is the one run of the real doctor on macOS and
Windows. It ran the doctor over an empty repository and asserted the exit
and the machine row's `git-filter-repo` path, which the doctor finds itself.
The machine row's child, `setup-project.py --preflight`, could die on an
import under `-S` and the check still passed: that child exits 1 then, and 1
is also the exit of a runner with no `gh` login. Measured at `5017830` on
Linux, a `setup-project.py` importing a module that only `site` puts on the
path passed every step of the install check. No validator of a project ran
there at all, because an empty repository is not a shape root.

THE TWO STEPS HELD HERE. The empty repository's step now also requires the
preflight's report to hold the closing line its exit means, and prints the
report either way. A new step makes a shape root with the installed
`scaffold-project --local-remote-dir`, which needs no network, `gh` or
token, runs the doctor over it, and requires every row that ran a child to
have reached a verdict of its own.

EACH STEP'S OWN PYTHON IS RUN HERE, as `tests/test_release_workflow.py` runs
the other steps' scripts: over doctor reports written in the shapes the
doctor gave on a Linux run of the release's own wheel, and over the report
this checkout's doctor gives, for a clean standard and for one whose child
dies on an import. The step's own `scaffold-project` line is run too.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
#: The workflow, read once, and the helpers that read its steps, imported
#: from the module that owns them. Importing a fixture gives this module its
#: own instance of it.
from test_release_workflow import commands, heredoc, job_steps, named_step
from test_release_workflow import workflow  # noqa: F401

#: The two steps, by the start of their names.
EMPTY_STEP = "openRepoShape --doctor over an empty repository"
ROOT_STEP = "openRepoShape --doctor over a scaffolded root"

#: The preflight's closing line for each exit it chooses, as
#: `setup-project.py`'s `preflight_only` prints it and the doctor keeps it.
READY = "[ok] this machine is ready."
NOT_READY = "[!!] this machine is not ready yet (see above)."

#: The preflight's checks on a runner: git, Python, the bootstrap line and
#: `gh`, which is installed there and has no login.
CHECKS = ["[ok] git 2.43.0", "[ok] python 3.12.3 (/usr/bin/python3)",
          "[ok] bootstrap runs as `python3 scripts/bootstrap.py` (make is not "
          "required)", "[ok] gh 2.81.0"]
NO_LOGIN = "[!!] gh is not authenticated. Run: gh auth login"
LOGGED_IN = "[ok] gh is authenticated as release-check"
AUTOCRLF = ("[??] git core.autocrlf is true. Every file git checks out gets "
            "CRLF line endings")

#: The three checks every runner passes, each failed as the preflight says it
#: (the bootstrap line never fails, so its failure is its absence).
GIT_FAILED = ("[!!] git is not installed. Install it: "
              "https://git-scm.com/downloads")
PYTHON_FAILED = ("[!!] this interpreter is 3.8, and 3.9 or newer is required. "
                 "Install a newer Python and re-run it with that one")

#: What the step says for each way the child can fail.
NO_LINE = ("the machine row's preflight child reported no [ok], [!!] or [??] "
           "line")
PART_WAY = "it stopped part way through its checks"
QUIET = "the machine row's preflight child has no line starting {}"
ELSEWHERE = "not in the package's environment"
NO_CHILD = "the doctor ran no child for its {} row over the scaffolded root"

#: The machine row's reason for a child that died on an import, as measured.
DIED = ("this machine is missing something the fixes above may need "
        "(setup-project.py --preflight, exit 1): ModuleNotFoundError: No "
        "module named 'a_module_that_is_not_there'")
CRASH = ("the project's own scripts/validate-manifest.py crashed before "
         "reaching a verdict (exit 1): ModuleNotFoundError: No module named "
         "'git_filter_repo'")

#: The line every broken child here carries, after its `__future__` line.
FUTURE = "from __future__ import annotations\n"
BAD_IMPORT = "import a_module_that_is_not_there\n"


# --- helpers --------------------------------------------------------------------

@pytest.fixture
def pipx_home(tmp_path) -> Path:
    """A `PIPX_HOME` whose openreposhape environment holds a
    `git-filter-repo`, where the step looks for the one pipx installs."""
    home = tmp_path / "pipx"
    scripts = home / "venvs" / "openreposhape" / (
        "Scripts" if os.name == "nt" else "bin")
    scripts.mkdir(parents=True)
    tool = scripts / "git-filter-repo"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    return home


def filter_repo_in(home: Path) -> str:
    """The `git-filter-repo` the `pipx_home` fixture placed."""
    [found] = (home / "venvs" / "openreposhape").glob("*/git-filter-repo")
    return str(found)


def run_step(workflow: dict, prefix: str, tmp_path: Path, report: str,
             home: Path | None = None,
             status: str | None = None) -> subprocess.CompletedProcess:
    """The install step's own Python over `report`, the doctor's `--json`
    output, as the step hands it `doctor.json`, or `root.json` and the
    doctor's exit `status`."""
    script = tmp_path / "step.py"
    script.write_text(heredoc(named_step(workflow, "install", prefix)["run"]),
                      encoding="utf-8")
    data = tmp_path / "report.json"
    data.write_text(report, encoding="utf-8")
    env = {**os.environ}
    if home is not None:
        env["PIPX_HOME"] = str(home)
    extra = [] if status is None else [status]
    return subprocess.run([sys.executable, "-I", str(script), str(data),
                           *extra], capture_output=True, text=True,
                          check=False, env=env)


def empty_report(home: Path, code, lines, reason: str = "",
                 found: str | None = None) -> str:
    """The doctor's report over an empty repository, its machine row's child
    having exited `code` with `lines`; with `code` None, a row that ran no
    child (`setup-project.py` not there)."""
    detail = {"preflight": "/clone/setup-project.py",
              "git-filter-repo": found or filter_repo_in(home)}
    if code is not None:
        detail.update({"exit": code, "report": lines, "not_ready": []})
    return json.dumps({"verdict": "NOT A SHAPE ROOT", "rows": [
        {"id": "naming", "status": "ok", "reason": "empty: classifies under "
         "the naming policy", "detail": {"names": ["empty"], "exit": 0}},
        {"id": "machine", "status": "n/a", "reason": reason or "the machine",
         "detail": detail}]})


def a_copy_of_the_standard(tmp_path: Path, broken: str = "") -> Path:
    """This working tree's tracked files outside `tests/`, copied, and
    `broken`, a file of them, given an import that fails after its
    `__future__` line."""
    dest = tmp_path / "standard"
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z", "--",
                             ".", ":!tests"], capture_output=True, check=True)
    for name in filter(None, listed.stdout.decode("utf-8").split("\0")):
        if (REPO / name).is_file():
            (dest / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(REPO / name, dest / name)
    if broken:
        break_an_import(dest / broken)
    return dest


def break_an_import(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    assert text.count(FUTURE) == 1, path
    path.write_text(text.replace(FUTURE, FUTURE + BAD_IMPORT),
                    encoding="utf-8")


def child_row(name: str, status: str = "ok", code: int | None = 0,
              reason: str = "passes", **extra) -> dict:
    """A row of the doctor's that ran a child: its exit is `detail.exit`."""
    return {"id": name, "status": status, "reason": reason,
            "detail": {"exit": code, **extra}}


#: A fresh root's three rows that run a child, as the doctor gave them on
#: Linux over a root `scaffold-project --local-remote-dir` made.
FRESH = {
    "naming": child_row("naming", reason="every leg name classifies, and "
                        "each declared role agrees with its form"),
    "manifest": child_row("manifest", reason="the project's own "
                          "scripts/validate-manifest.py passes",
                          validator="/root/scripts/validate-manifest.py",
                          own_copy=True),
    "pins": child_row("pins", reason="the project's own "
                      "scripts/validate-pins.py passes",
                      validator="/root/scripts/validate-pins.py",
                      own_copy=True),
}


def root_report(**changed) -> str:
    """The doctor's report over a fresh root, its rows `changed` by name;
    the machine row's child is the empty repository step's to judge."""
    rows = {**FRESH, **changed}
    machine = child_row("machine", "n/a", 1, "this machine is missing "
                        "something", report=[])
    return json.dumps({"verdict": "COMPLIANT", "rows": [
        *rows.values(),
        {"id": "manifest-kinds", "status": "ok", "reason": "5 manifest(s)",
         "detail": {}}, machine]})


# --- the empty repository's step: the preflight child ----------------------------

def test_the_empty_repository_step_reads_its_report_after_the_preflight_step(
        workflow):
    """Right after `openRepoShape --preflight runs`, the package's own run
    of the preflight, and before the scaffolded root's step, whose clone it
    makes. The doctor's exit is still 2, NOT A SHAPE ROOT, and its report
    reaches the step's Python as `doctor.json`."""
    names = [step.get("name", "") for step in job_steps(workflow, "install")]
    [at] = [i for i, name in enumerate(names) if name.startswith(EMPTY_STEP)]
    assert names[at - 1] == "openRepoShape --preflight runs"
    assert names[at + 1].startswith(ROOT_STEP)
    lines = commands(named_step(workflow, "install", EMPTY_STEP)["run"])
    assert ('openRepoShape --doctor "$RUNNER_TEMP/empty" --json > doctor.json '
            '|| status=$?') in lines
    assert 'if [ "$status" -ne 2 ]; then' in lines
    assert "python - doctor.json <<'PY'" in lines


def test_the_closing_lines_are_the_preflights_own(workflow):
    """The step holds the two lines `setup-project.py` closes its report
    with, each for the exit it returns with, spelled as it spells them."""
    script = heredoc(named_step(workflow, "install", EMPTY_STEP)["run"])
    assert f'closing = {{0: "{READY}",' in script
    assert f'1: "{NOT_READY}"}}' in script
    source = (REPO / "setup-project.py").read_text(encoding="utf-8")
    assert 'TICK = "[ok]"' in source
    assert 'CROSS = "[!!]"' in source
    assert 'ok("this machine is ready.")' in source
    assert 'bad("this machine is not ready yet (see above).")' in source
    assert "return 0 if ready else 1" in source


def test_the_checks_every_runner_passes_open_as_the_preflight_prints_them(
        workflow):
    """The step requires the git, Python and bootstrap lines by how
    `setup-project.py`'s `ok()` opens each: its mark, then the words."""
    script = heredoc(named_step(workflow, "install", EMPTY_STEP)["run"])
    assert ('passed = ("[ok] git ", "[ok] python ", "[ok] bootstrap runs as")'
            in script)
    source = (REPO / "setup-project.py").read_text(encoding="utf-8")
    assert 'ok("git %s" % program_version(' in source
    assert 'ok("python %d.%d.%d (%s)" % (' in source
    assert 'ok("bootstrap runs as `%s %s` (make is not required)"' in source


@pytest.mark.parametrize("code, lines, reason, expected, says", [
    (1, [*CHECKS, NO_LOGIN, NOT_READY], "", 0, None),
    (0, [*CHECKS, LOGGED_IN, READY], "", 0, None),
    (0, [*CHECKS, LOGGED_IN, READY, AUTOCRLF], "", 0, None),
    (1, [], DIED, 1, NO_LINE),
    (None, [], "setup-project.py is not here", 1, NO_LINE),
    (1, CHECKS[:2], "", 1, PART_WAY),
    (1, [*CHECKS, NO_LOGIN, READY], "", 1, PART_WAY),
    (0, [*CHECKS, NO_LOGIN, NOT_READY], "", 1, PART_WAY),
    (2, [*CHECKS, NOT_READY], "", 1, "does not hold 'a closing line: it exits "
     "0 or 1'"),
    (1, [*CHECKS[1:], GIT_FAILED, NO_LOGIN, NOT_READY], "", 1,
     QUIET.format(["[ok] git "])),
    (1, [CHECKS[0], *CHECKS[2:], PYTHON_FAILED, NO_LOGIN, NOT_READY], "", 1,
     QUIET.format(["[ok] python "])),
    (1, [*CHECKS[:2], CHECKS[3], NO_LOGIN, NOT_READY], "", 1,
     QUIET.format(["[ok] bootstrap runs as"])),
], ids=["a-runner-with-no-gh-login", "a-machine-logged-in",
        "a-warning-after-the-closing-line", "a-child-that-died-on-an-import",
        "no-preflight-ran", "a-child-that-stopped-part-way",
        "exit-1-with-the-ready-line", "exit-0-with-the-not-ready-line",
        "a-refusal-exit-2", "git-failed-quietly", "python-failed-quietly",
        "no-bootstrap-line"])
def test_the_empty_repository_step_requires_the_closing_line_its_exit_means(
        workflow, tmp_path, pipx_home, code, lines, reason, expected, says):
    """Exit 1 with no login, or 0 with one, passes when the report holds the
    closing line for that exit, wherever a `[??]` warning falls (stderr
    comes after stdout). A child that reported no line, whose exit is the
    no-login one, fails, and so does one that stopped before its closing
    line, closed with the other exit's, or refused. So does a report whose
    git, Python or bootstrap check is not `[ok]`: each fails quietly into
    exit 1, a runner's own. Every line the child reported is printed either
    way."""
    done = run_step(workflow, EMPTY_STEP, tmp_path,
                    empty_report(pipx_home, code, lines, reason), pipx_home)
    assert done.returncode == expected, done.stdout + done.stderr
    for line in lines:
        assert f"\n    {line}\n" in done.stdout, line
    if says is None:
        assert "::error::" not in done.stdout, done.stdout
    else:
        assert says in done.stdout, done.stdout
        assert reason in done.stdout, done.stdout


def test_a_git_filter_repo_outside_the_package_environment_still_fails(
        workflow, tmp_path, pipx_home):
    """The step's first assertion, held: the machine row must find the
    `git-filter-repo` pipx put in the package's environment, and the report
    is printed whether or not that holds."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    report = empty_report(pipx_home, 1, [*CHECKS, NO_LOGIN, NOT_READY],
                          found=str(elsewhere / "git-filter-repo"))
    done = run_step(workflow, EMPTY_STEP, tmp_path, report, pipx_home)
    assert done.returncode == 1, done.stdout + done.stderr
    assert ELSEWHERE in done.stdout, done.stdout
    assert f"\n    {NOT_READY}\n" in done.stdout, done.stdout


@WINDOWS_SKIP  # the preflight's bare `gh` reaches the suite's guard on POSIX
@pytest.mark.parametrize("broken, expected", [
    ("", 0), ("setup-project.py", 1),
], ids=["this-checkouts-preflight", "a-preflight-that-dies-on-an-import"])
def test_the_empty_repository_step_over_the_doctors_own_report(
        workflow, tmp_path, pipx_home, broken, expected):
    """This checkout's doctor over an empty repository, under the suite's
    `gh`, which answers as an installed `gh` with no login, as a runner's
    does: its report passes the step. The same doctor from a copy whose
    `setup-project.py` dies on an import gives a report that fails it, with
    the machine row's own reason quoted."""
    standard = a_copy_of_the_standard(tmp_path, broken)
    empty = tmp_path / "empty"
    empty.mkdir()
    git("init", "-q", cwd=empty)
    scripts = Path(filter_repo_in(pipx_home)).parent
    doctor = run_script(standard / "shape-doctor.py", "--root", str(empty),
                        "--json", env={"PATH": str(scripts) + os.pathsep
                                       + os.environ["PATH"]})
    assert doctor.returncode == 2, doctor.stdout + doctor.stderr
    done = run_step(workflow, EMPTY_STEP, tmp_path, doctor.stdout, pipx_home)
    assert done.returncode == expected, done.stdout + done.stderr
    if broken:
        assert NO_LINE in done.stdout, done.stdout
        assert "a_module_that_is_not_there" in done.stdout, done.stdout
    else:
        assert f"\n    {NOT_READY}\n" in done.stdout, done.stdout


# --- the scaffolded root's step: every child reaches a verdict --------------------

def test_the_scaffolded_root_step_needs_no_network_gh_or_token(workflow):
    """The root is made by `scaffold-project --local-remote-dir`: bare
    repositories on this disk and no `gh`. The step runs no `gh` itself,
    names no token, and the job still reads its checkout and nothing more."""
    step = named_step(workflow, "install", ROOT_STEP)
    assert "env" not in step
    assert "token" not in step["run"].lower()
    lines = commands(step["run"])
    assert [line for line in lines if re.match(r"gh\b", line)] == []
    [scaffold] = [line for line in lines if line.startswith("scaffold-project ")]
    assert '--local-remote-dir "$RUNNER_TEMP/remotes"' in scaffold
    assert ('openRepoShape --doctor "$RUNNER_TEMP/work/Sample" --json > '
            'root.json || status=$?') in lines
    assert "python - root.json \"$status\" <<'PY'" in lines
    assert workflow["jobs"]["install"]["permissions"] == {"contents": "read"}


@pytest.mark.parametrize("changed, expected, says", [
    ({}, 0, None),
    ({"manifest": child_row("manifest", "FINDING", 1, CRASH, crashed=True,
                            own_copy=True)}, 1, f"::error::the manifest row: "
     f"{CRASH}"),
    ({"pins": child_row("pins", "FINDING", 1, "the project's own "
                        "scripts/validate-pins.py reports a finding (exit 1): "
                        "FINDING pin-drift: a file changed")}, 0, None),
    ({"naming": child_row("naming", "FINDING", 1, "the standard's naming "
                          "script stopped", crashed=True,
                          environment=True)}, 1, "::error::the naming row: "),
    ({"pins": child_row("pins", "FINDING", 1, "the project's own "
                        "scripts/validate-pins.py crashed before reaching a "
                        "verdict (exit 1): KeyError")}, 1, "::error::the pins "
     "row: "),
    ({"pins": child_row("pins", "FINDING", None, "was not run")}, 1,
     "::error::" + NO_CHILD.format("pins")),
], ids=["a-fresh-root", "a-validator-that-crashed", "a-finding-is-a-verdict",
        "the-crashed-flag-alone", "the-crashed-words-alone",
        "a-row-that-ran-no-child"])
def test_the_scaffolded_root_step_requires_every_child_to_reach_a_verdict(
        workflow, tmp_path, changed, expected, says):
    """A fresh root's naming, manifest and pins rows each ran a child that
    passed. A row whose child crashed fails the step, by the doctor's flag
    or by its words; a finding is a verdict and does not; and a row of the
    three that ran no child fails, since then no child was judged. Each row
    that ran a child is printed either way."""
    done = run_step(workflow, ROOT_STEP, tmp_path, root_report(**changed),
                    status="0")
    assert done.returncode == expected, done.stdout + done.stderr
    shown = {**FRESH, **changed}
    for name, row in shown.items():
        if row["detail"]["exit"] is not None:
            assert (f"\n    {name}: {row['status']}, exit "
                    f"{row['detail']['exit']}: {row['reason']}\n"
                    in done.stdout), name
    if says is None:
        assert "::error::" not in done.stdout, done.stdout
    else:
        assert says in done.stdout, done.stdout


@pytest.mark.parametrize("written, status", [
    ("", "1"),
    ("Traceback (most recent call last):\nKeyError: 'rows'\n", "1"),
    ('{"verdict": "COMPLIANT", "rows": [', "3"),
], ids=["nothing", "a-traceback", "cut-short"])
def test_the_scaffolded_root_step_names_the_doctors_exit_without_a_report(
        workflow, tmp_path, written, status):
    """A doctor that wrote no JSON report, or half of one, fails the step
    with one `::error::` naming the exit it ended with, and no traceback of
    the step's own."""
    done = run_step(workflow, ROOT_STEP, tmp_path, written, status=status)
    assert done.returncode == 1, done.stdout + done.stderr
    assert (f"::error::openRepoShape --doctor over the scaffolded root exited "
            f"{status} and wrote no JSON report" in done.stderr), done.stderr
    assert "Traceback (most recent call last)" not in done.stderr, \
        done.stderr


@WINDOWS_SKIP  # the doctor's machine row reaches the suite's `gh` on POSIX
@pytest.mark.parametrize("broken, expected", [
    ("", 0), ("scripts/validate-manifest.py", 1),
], ids=["a-fresh-root", "its-own-validator-dies-on-an-import"])
def test_the_steps_own_scaffold_line_makes_a_root_the_step_passes(
        workflow, tmp_path, broken, expected):
    """The step's own `scaffold-project` line, given to this checkout's
    `scaffold-project.py`, makes the root the step's doctor line names, and
    this checkout's doctor over it gives a report that passes the step.
    With the root's own `validate-manifest.py` dying on an import, the
    manifest row crashed and the step fails on it."""
    lines = commands(named_step(workflow, "install", ROOT_STEP)["run"])
    [scaffold] = [line for line in lines if line.startswith("scaffold-project ")]
    [doctor] = [line for line in lines if line.startswith("openRepoShape --doctor ")]
    here = str(tmp_path)
    argv = shlex.split(scaffold.replace("$RUNNER_TEMP", here))
    made = run_script(REPO / "scaffold-project.py", *argv[1:], cwd=tmp_path)
    assert made.returncode == 0, made.stdout + made.stderr
    root = Path(shlex.split(doctor.replace("$RUNNER_TEMP", here))[2])
    if broken:
        break_an_import(root / broken)
    report = run_script(REPO / "shape-doctor.py", "--root", str(root),
                        "--json")
    done = run_step(workflow, ROOT_STEP, tmp_path, report.stdout,
                    status=str(report.returncode))
    assert done.returncode == expected, done.stdout + done.stderr
    for name in ("naming", "manifest", "pins"):
        assert f"\n    {name}: " in done.stdout, name
    if broken:
        assert "::error::the manifest row: " in done.stdout, done.stdout
        assert "a_module_that_is_not_there" in done.stdout, done.stdout
