# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py`'s validator rows: what a validator that did NOT answer
looks like (#278, #297, #298).

THREE WAYS A ROW USED TO SAY MORE THAN THE VALIDATOR DID.

- #278: a validator that CRASHED -- a traceback, exit 1 -- read as one that
  reported a finding, because 1 is also the code for findings. A standard
  checked out under a directory whose name holds `os.pathsep` gave the
  template copy a `PYTHONPATH` Python split in two, so the template died on
  `import repo_shape` and a valid manifest read `INVALID (manifest)`.
- #297: a project that pins a neutral product, with no local checkout of it,
  has a `validate-pins.py` that asks `gh api`, gets nothing, prints a `skip`
  line and exits 0. The doctor threw the output away and said `ok ...
  passes`, and the child had reached for GitHub on the operator's login.
- #298: the unloaded-manifest row promised its gate "refuses it the same
  way" for a root that had also lost `scripts/repo_shape.py`, where the gate
  dies on the import instead.

EVERY ASSERTION IS ON WHAT A COMMAND DOES -- the row's status, its `detail`,
the verdict, and a NEXT that is run -- and never on the words of a row's
`why`, the sentence beside its NEXT (#277). The fixtures are those of
`tests/test_shape_doctor.py`, imported, so the standard, the project and the
holder are the ones every other doctor test reads.

NOTHING HERE REACHES A NETWORK. The scaffolds use local bare remotes, the
`gh` the #297 rows see is this file's own stub, first on `PATH`, which runs
nothing and logs its environment, and no test here sets `GIT_ALLOW_PROTOCOL`.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import WINDOWS_SKIP, cloned_just_pushed, git, run_script
from conftest import PTY_SKIP, REPO, run_in_a_terminal
#: The neutral product's stand-in, from the module that scaffolds a declared
#: descendant: a second way of building one would test a different one.
from test_scaffold_pin_and_reuse import product_repo
#: The standard, the project, the holder and the helpers every doctor test
#: reads, imported from the module that owns them. Importing a fixture gives
#: this module its own instance of it.
from test_shape_doctor import (  # noqa: F401
    BREAKAGES, DOCTOR, FAMILY_BREAKAGES, FAMILY_NAME, TEMPLATE_FALLBACK,
    assert_next_runs_the_roots_own, break_manifest, doctor, doctor_module,
    holder, loader_line, pasted_from_elsewhere, project, red_root, rows_of,
    scaffolded_here, standard,
)
#: Doctor A's builders for a leg, and a member, whose gitlink is not its pin
#: (#276): the lockstep line these rows hand over is A's, so its fixtures are
#: too, from the module that owns them.
from test_doctor_legs_members_next import (
    holder_copy, make_gitlink_moved, make_member_gitlink_mismatch,
)

#: The four variables `gh` takes a token from, the proxy every validator
#: child is pointed at, and the variables that point it -- spelled here, from
#: the issue, rather than read back from the code under test.
TOKENS = ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN",
          "GITHUB_ENTERPRISE_TOKEN")
UNREACHABLE = "http://127.0.0.1:9"
PROXIES = ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy")
NO_PROXIES = ("NO_PROXY", "no_proxy")
#: What the operator's environment holds in these tests: values that are
#: plainly not real, so a run that leaked one leaks nothing.
SENTINEL_TOKEN = "sentinel-token-not-a-real-one"
SENTINEL_HOST = "sentinel.invalid"

PRODUCT = "openGlass"
CRASH = 'raise RuntimeError("boom")\n'
#: A validator that REPORTS a finding, as the real ones do -- a `FINDING` line
#: on stderr -- and then dies on a line of its own (#278, R278-1).
FINDING_THEN_CRASH = ("import sys\n"
                      "print('FINDING pin-x: a made-up finding', "
                      "file=sys.stderr)\n"
                      'raise RuntimeError("boom")\n')


def payload_of(result) -> dict:
    return json.loads(result.stdout)


def own_root(case: str, project: Path, holder: dict, tmp_path: Path) -> Path:
    """The root `case` is a row of: the project, or a COPY of the holder, so
    the session's stays intact. Resolved, as the doctor resolves `--root`."""
    if case != "family":
        return project.resolve()
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    return root.resolve()


def standard_under(standard: Path, tmp_path: Path, directory: str) -> Path:
    """A COPY of the whole standard, history and all, at
    `<tmp>/<directory>/openRepoShape`: the same commit, a different path."""
    here = tmp_path / directory / "openRepoShape"
    here.parent.mkdir()
    shutil.copytree(standard, here, symlinks=True)
    return here


def command_of(row: dict) -> list:
    """The row's NEXT as the argv it runs: the whole of it, since a NEXT is
    only the command (#277). The paths in these tests need no quoting on
    either platform, which is what lets the same list run on Windows, where
    no `sh` pastes it."""
    return row["next"].split()


def run_argv(command: list) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, text=True,
                          check=False, stdin=subprocess.DEVNULL,
                          env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})


# --- #278: a crash is not a finding -----------------------------------------

def crashing(setup: str, standard: Path, project: Path, holder: dict,
             tmp_path: Path, source: str = CRASH) -> tuple:
    """`(standard to run, root, row id, own_copy)` for one way a validator
    crashes: a root's OWN copy that raises (`own-manifest`, `own-pins`,
    `own-family`), or the standard's TEMPLATE copy that raises, for a root
    with none of its own (`template`). `source` is what the copy is made to
    run."""
    if setup == "template":
        here = standard_under(standard, tmp_path, "crashing")
        (here / TEMPLATE_FALLBACK["manifest"]["template"]).write_text(
            source, encoding="utf-8")
        root = project.resolve()
        (root / TEMPLATE_FALLBACK["manifest"]["own"]).unlink()
        return here, root, "manifest", False
    case = setup.removeprefix("own-")
    root = own_root(case, project, holder, tmp_path)
    (root / TEMPLATE_FALLBACK[case]["own"]).write_text(source,
                                                      encoding="utf-8")
    return standard, root, case, True


@pytest.mark.parametrize("setup", ["own-family", "own-manifest", "own-pins",
                                   "template"])
def test_a_validator_that_crashed_says_so_and_never_reports_a_finding(
        standard, project, holder, tmp_path, setup):
    """(b) of the issue: the row says it CRASHED, carries `detail.crashed`,
    and still quotes the exception.

    THE ROOT'S OWN COPY IS STILL A FINDING: a project whose gate cannot run
    has a broken gate, and the verdict is the one an edited copy gives
    (DRIFTED), never CANNOT ANSWER. THE TEMPLATE COPY IS THIS CHECKOUT'S, so
    its crash is `detail.environment` and the verdict is CANNOT ANSWER, exit
    3: nothing in it is a statement about the project.
    """
    here, root, row_id, own_copy = crashing(setup, standard, project, holder,
                                            tmp_path)
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)[row_id]
    assert row["status"] == "FINDING", row
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["own_copy"] is own_copy, row
    assert row["detail"]["exit"] == 1, row
    assert "crashed" in row["reason"], row
    assert "reports a finding" not in row["reason"], row
    assert "RuntimeError: boom" in row["reason"], row
    if own_copy:
        assert "environment" not in row["detail"], row
        assert result.returncode == 1, result.stdout + result.stderr
        assert not payload["verdict"].startswith("CANNOT ANSWER"), payload
        assert_next_runs_the_roots_own(
            row, root, Path(TEMPLATE_FALLBACK[row_id]["own"]).name)
    else:
        assert row["detail"]["environment"] is True, row
        assert result.returncode == 3, result.stdout + result.stderr
        assert payload["verdict"].startswith(
            f"CANNOT ANSWER ({row['label']}: "), payload
        shape = here.resolve()
        expected = doctor_module(here).validator_command(
            shape, shape / TEMPLATE_FALLBACK["manifest"]["template"], False,
            ["--root", root])
        # THE NEXT IS THE LINE ALONE and what to do with its output is the
        # row's `why` (#277).
        assert row["next"] == expected, row["next"]
        assert row["why"].startswith("read its output in full"), row
        # A ROW WITH A NEXT STILL PRINTS ITS REMEDIATION (the control of the
        # colon row below, which has none and prints no `Remediation:`), and
        # its `why` after it.
        stderr = doctor(here, root).stderr
        assert "REFUSED shape-doctor-cannot-answer: " in stderr, stderr
        assert (f"\n  Remediation: {row['next']}\n  Why: {row['why']}"
                in stderr), stderr


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
@pytest.mark.parametrize("setup", ["own-pins", "template"])
def test_a_crashed_validators_next_shows_the_traceback_when_pasted(
        standard, project, holder, tmp_path, setup):
    """The NEXT of a crashed row is still the validator's own line, and
    pasted from `/` with no `PYTHONPATH` it prints the traceback the row
    quoted, with the row's exit code."""
    here, root, row_id, _own = crashing(setup, standard, project, holder,
                                        tmp_path)
    row = rows_of(doctor(here, root, "--json"))[row_id]
    pasted = pasted_from_elsewhere(row["next"], tmp_path)
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == row["detail"]["exit"], whole
    assert "Traceback (most recent call last):" in whole, whole
    assert "RuntimeError: boom" in whole, whole


@pytest.mark.parametrize("setup", ["own-pins", "template"])
def test_a_validator_that_reported_a_finding_before_it_died_still_reports_one(
        standard, project, holder, tmp_path, setup):
    """R278-1's other half: a `FINDING` line is a verdict, and an exception
    after it does not take it back.

    `crashed` is true only of a validator that said nothing of its own before
    the traceback. Without that clause a template that reported a real finding
    and then raised would be CANNOT ANSWER -- "nothing here is a statement
    about the project" -- and the finding it printed would be hidden. Both
    copies are run: the root's own, whose row would say `crashed` and carry
    `detail.crashed`, and the template, whose row would be an environment row
    and exit 3. The row quotes the finding, as it always did.
    """
    here, root, row_id, own_copy = crashing(setup, standard, project, holder,
                                            tmp_path, FINDING_THEN_CRASH)
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)[row_id]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is own_copy, row
    assert row["detail"]["exit"] == 1, row
    assert "crashed" not in row["detail"], row
    assert "environment" not in row["detail"], row
    assert "reports a finding" in row["reason"], row
    assert "crashed" not in row["reason"], row
    assert "FINDING pin-x: a made-up finding" in row["reason"], row
    assert result.returncode == 1, result.stdout + result.stderr
    assert not payload["verdict"].startswith("CANNOT ANSWER"), payload


@WINDOWS_SKIP
def test_a_standard_under_a_colon_is_cannot_answer_and_runs_nothing(
        standard, project, tmp_path):
    """(a) of the issue, and (i) of the ruling: the template copy cannot be
    given its `PYTHONPATH`, so it is not run and no line is printed.

    The root has no `validate-manifest.py` of its own and a VALID manifest,
    so the template is the only gate for it, and `:` splits the directory
    that gate imports `repo_shape` from. The row is the doctor's own
    environment failing -- CANNOT ANSWER, exit 3 -- with no `exit` (nothing
    was run) and no NEXT, and not one `PYTHONPATH=` anywhere in either
    report, because no such line could be pasted and work. `WINDOWS_SKIP`:
    Windows refuses `:` in a file name; its separator is `;`, below.
    """
    here = standard_under(standard, tmp_path, "dir:with-colon")
    root = project.resolve()
    (root / TEMPLATE_FALLBACK["manifest"]["own"]).unlink()
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)["manifest"]
    assert result.returncode == 3, result.stdout + result.stderr
    assert payload["verdict"].startswith("CANNOT ANSWER (manifest: "), payload
    assert row["status"] == "FINDING", row
    assert row["detail"]["environment"] is True, row
    assert row["detail"]["own_copy"] is False, row
    assert row["detail"]["exit"] is None, row
    assert row["next"] is None, row
    assert "holds no ':'" in row["reason"], row
    assert "ModuleNotFoundError" not in row["reason"], row
    text = doctor(here, root)
    assert text.returncode == 3, text.stdout + text.stderr
    for said in (result.stdout, text.stdout, text.stderr):
        assert "PYTHONPATH=" not in said, said
    # THE REFUSAL ON STDERR HAS NO REMEDIATION TO NAME: a row with no NEXT
    # printed a literal `Remediation: None` after its reason.
    assert "REFUSED shape-doctor-cannot-answer: " in text.stderr, text.stderr
    assert "Remediation" not in text.stderr, text.stderr


@WINDOWS_SKIP
def test_a_colon_standard_leaves_an_unloaded_manifest_its_finding_and_no_line(
        standard, project, tmp_path):
    """(ii) of the ruling: the manifest does not load, so the FINDING stands
    -- exit 1, never CANNOT ANSWER -- but the template's line would carry a
    `PYTHONPATH` that splits, so the row has no NEXT, quotes the loader as it
    always did, and says why there is no line."""
    here = standard_under(standard, tmp_path, "dir:with-colon")
    root = project.resolve()
    (root / TEMPLATE_FALLBACK["manifest"]["own"]).unlink()
    refusal = break_manifest(root / "project.yaml", *BREAKAGES["tab-indent"])
    result = doctor(here, root, "--json")
    payload = payload_of(result)
    row = rows_of(result)["manifest"]
    assert result.returncode == 1, result.stdout + result.stderr
    assert not payload["verdict"].startswith("CANNOT ANSWER"), payload
    assert row["status"] == "FINDING", row
    assert "environment" not in row["detail"], row
    assert row["detail"]["own_copy"] is False, row
    assert row["next"] is None, row
    assert row["reason"].startswith(
        f"project.yaml does not load: {loader_line(refusal)}; "), row
    assert "holds no ':'" in row["reason"], row
    text = doctor(here, root)
    for said in (result.stdout, text.stdout, text.stderr):
        assert "PYTHONPATH=" not in said, said


def test_a_standard_under_a_semicolon_is_refused_only_where_it_separates(
        standard, project, tmp_path):
    """R278-3: Windows' `;` is the same `os.pathsep` and is claimed by the
    same helper, and on POSIX the same directory is the CONTROL -- an
    ordinary character, quoted in the line, and nothing refused.

    The root's own `validate-manifest.py` is gone and its manifest is red by
    a file that still loads, so the template is the gate. On Windows it is
    the environment row with no NEXT; on POSIX it is the template's real
    finding, and its NEXT, pasted, prints that finding.
    """
    here = standard_under(standard, tmp_path, "semi;colon")
    spec = TEMPLATE_FALLBACK["manifest"]
    root = red_root("manifest", project, {}, tmp_path)
    result = doctor(here, root, "--json")
    row = rows_of(result)["manifest"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    if os.pathsep == ";":
        assert row["detail"]["environment"] is True, row
        assert row["next"] is None, row
        assert result.returncode == 3, result.stdout + result.stderr
        return
    assert "environment" not in row["detail"], row
    assert row["detail"]["exit"] == 1, row
    assert spec["finding"] in row["reason"], row
    assert row["next"].startswith("env PYTHONPATH='"), row["next"]
    if shutil.which("sh") is not None:
        pasted = pasted_from_elsewhere(row["next"], tmp_path)
        whole = pasted.stdout + pasted.stderr
        assert pasted.returncode == 1, whole
        assert f"FINDING {spec['finding']}" in whole, whole


# --- #297: no validator child reaches a network, and a skip is said ---------

def logging_gh(where: Path, says: str = "", status: int = 97) -> tuple:
    """`(directory to put first on PATH, directory of calls)`: a `gh` that
    runs NOTHING. Each call writes its argv and its whole environment to a
    new file and exits `status` (97, which no real `gh` exits), so a test can
    say which process called it and what that process could have
    authenticated with. Given `says`, it prints that to stderr first, as a
    `gh` that is not logged in prints its help. A shebang script, so its
    tests are `WINDOWS_SKIP`."""
    bin_dir, calls = where / "bin", where / "calls"
    bin_dir.mkdir(parents=True)
    calls.mkdir()
    stub = bin_dir / "gh"
    stub.write_text(
        "#!/bin/sh\n"
        f"out=$(mktemp {shlex.quote(str(calls))}/call.XXXXXX)\n"
        "printf '%s\\n' \"$*\" > \"$out\"\n"
        "env >> \"$out\"\n"
        + (f"printf '%s\\n' {shlex.quote(says)} >&2\n" if says else "")
        + f"exit {status}\n", encoding="utf-8")
    stub.chmod(0o755)
    return bin_dir, calls


def gh_calls(calls: Path) -> list:
    """`[(argv as one string, {variable: value})]`, one per call."""
    found = []
    for path in sorted(calls.iterdir()):
        lines = path.read_text(encoding="utf-8",
                               errors="replace").splitlines()
        environment: dict = {}
        for line in lines[1:]:
            name, equals, value = line.partition("=")
            if equals and name.isidentifier():
                environment.setdefault(name, value)
        found.append((lines[0] if lines else "", environment))
    return found


@pytest.fixture(scope="module")
def descendant_run(standard, tmp_path_factory) -> dict:
    """MedxGlass, pinning `openGlass` with NO source the validator can find,
    and one doctor run of it with the stub first on `PATH`.

    Scaffolded from the session's standard with `--pin-source`, as
    `tests/test_scaffold_pin_and_reuse.py` does, then cloned AWAY from the
    stand-in, so neither `../openGlass` nor `--pin-source` answers and
    `SHAPE_PIN_SOURCE_OPENGLASS` is blanked by `run_script`. The scaffold's
    own `gh` calls go to a stub too, never a real one. The doctor's
    environment carries a sentinel for every token, a `GH_CONFIG_DIR` and a
    `NO_PROXY`, so what reached each `gh` call can be read back.
    """
    base = tmp_path_factory.mktemp("descendant")
    product, commit = product_repo(base / "standin", PRODUCT)
    quiet, _ignored = logging_gh(base / "scaffold-gh")
    made = run_script(
        standard / "scaffold-project.py", "--org", "MedxSoft", "--project",
        "MedxGlass", "--elected-by", "Test Human", "--elected-on",
        "2026-09-10", "--pin", f"{PRODUCT}@{commit}", "--pin-source",
        str(product), "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"),
        env={"PATH": f"{quiet}{os.pathsep}{os.environ['PATH']}"})
    assert made.returncode == 0, made.stderr + made.stdout
    clone = cloned_just_pushed(base / "remotes" / "MedxGlass.git",
                               base / "clones" / "MedxGlass")
    assert not (clone.parent / PRODUCT).exists()
    bin_dir, calls = logging_gh(base / "doctor-gh")
    operators_config = str(base / "operators-gh-config")
    result = run_script(
        standard / DOCTOR, "--root", str(clone), "--json",
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             **{name: SENTINEL_TOKEN for name in TOKENS},
             "GH_CONFIG_DIR": operators_config,
             **{name: SENTINEL_HOST for name in NO_PROXIES}})
    return {"result": result, "calls": gh_calls(calls), "clone": clone,
            "operators_config": operators_config}


@WINDOWS_SKIP
def test_a_skipped_digest_is_a_note_naming_the_product_and_still_compliant(
        descendant_run):
    """R297-2: exit 0 with a `skip` line is a `note`, not `ok ... passes`.

    The note moves no verdict, so the descendant is COMPLIANT, exit 0, as it
    was; the row says which product's digest was not rechecked, keeps the
    skip in `detail.skipped`, and has no NEXT -- the skip line names the
    three ways to give the validator a source.
    """
    result = descendant_run["result"]
    payload = payload_of(result)
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["verdict"] == "COMPLIANT", payload
    row = rows_of(result)["pins"]
    assert row["status"] == "note", row
    assert row["detail"]["exit"] == 0, row
    assert row["next"] is None, row
    assert PRODUCT in row["reason"], row
    assert "did not recheck" in row["reason"], row
    assert row["detail"]["skipped"], row
    for skip in row["detail"]["skipped"]:
        assert skip.startswith(f"{PRODUCT}: "), row


@WINDOWS_SKIP
def test_only_the_machine_rows_gh_keeps_the_login_and_the_proxies(
        descendant_run):
    """R297-1, both walls: the validator child's `gh` had no token, no
    configuration and a proxy that goes nowhere; the machine row's probes
    had the operator's environment exactly.

    THE CHILD IS FOUND BY WHAT IT ASKED: `api repos/.../git/trees/...` is
    `validate-pins.py` recomputing the digest. The machine row's preflight
    asks `--version`, `auth status` and `api user`. EVERY call that is not
    one of the machine's is held to the offline environment, whichever
    process made it, because the machine row is the one named exception.
    """
    calls = descendant_run["calls"]
    machine = [(argv, env) for argv, env in calls
               if argv.startswith(("--version", "auth ", "api user"))]
    others = [(argv, env) for argv, env in calls
              if (argv, env) not in machine]
    assert [argv for argv, _env in others
            if "/git/trees/" in argv], calls
    assert machine, calls
    for argv, env in others:
        for name in TOKENS + NO_PROXIES:
            assert name not in env, (argv, name, env.get(name))
        assert env.get("GH_CONFIG_DIR") == os.devnull, (argv, env)
        assert env.get("GH_NO_UPDATE_NOTIFIER") == "1", (argv, env)
        for name in PROXIES:
            assert env.get(name) == UNREACHABLE, (argv, name, env.get(name))
    for argv, env in machine:
        for name in TOKENS:
            assert env.get(name) == SENTINEL_TOKEN, (argv, name)
        assert env.get("GH_CONFIG_DIR") == descendant_run["operators_config"]
        for name in NO_PROXIES:
            assert env.get(name) == SENTINEL_HOST, (argv, name)
        for name in PROXIES:
            assert env.get(name) != UNREACHABLE, (argv, name)


#: What a `gh` that is not logged in prints, over TWO lines (its auth help;
#: under `GITHUB_ACTIONS` it is four).
GH_NOT_LOGGED_IN = (
    "To get started with GitHub CLI, please run:  gh auth login\n"
    "Alternatively, populate the GH_TOKEN environment variable with a GitHub "
    "API authentication token.")


@WINDOWS_SKIP
def test_a_two_line_gh_stderr_in_a_skip_keeps_the_ways_to_give_a_source(
        descendant_run, standard, tmp_path):
    """`validate-pins.py`'s skip embeds `gh`'s stderr verbatim, so a `gh` whose
    help is two lines splits the skip in two: the row's reason used to stop at
    the first, which told the reader to `gh auth login` -- a login the
    doctor's own offline environment would then undo -- and dropped the
    `--pin-source`, `SHAPE_PIN_SOURCE_<PRODUCT>` and `../<product>` ways to
    give the product a source, which are why the row has no NEXT.

    The same descendant, the same clone, with a stub that prints that help for
    every call and exits 4. The summary line the validator ends on is not
    folded into the reason.
    """
    bin_dir, _calls = logging_gh(tmp_path / "gh-help", GH_NOT_LOGGED_IN, 4)
    result = run_script(
        standard / DOCTOR, "--root", str(descendant_run["clone"]), "--json",
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 0, result.stdout + result.stderr
    row = rows_of(result)["pins"]
    assert row["status"] == "note", row
    assert row["next"] is None, row
    assert len(row["detail"]["skipped"]) == 1, row
    for said in (row["reason"], row["detail"]["skipped"][0]):
        assert "gh auth login" in said, row
        assert "GH_TOKEN environment variable" in said, row
        assert "--pin-source" in said, row
        assert f"SHAPE_PIN_SOURCE_{PRODUCT.upper()}" in said, row
        assert f"../{PRODUCT}" in said, row
        assert said.index("GH_TOKEN") < said.index("--pin-source"), row
        assert "pins ok" not in said, row


def test_skipped_keeps_the_whole_block_and_stops_at_the_next_item(standard):
    """`skipped` on a constructed output, on every platform: a block is the
    `  skip ` line and the lines after it up to the next item -- `  ok`,
    `  skip`, `FINDING`, `WARNING` or the validator's summary -- joined by a
    space, blank lines dropped; and a line before any skip is not one."""
    skipped = doctor_module(standard).skipped
    whole = ("Notice: not part of a block\n"
             "  ok  a: pin commit 0123456789ab digest recomputes\n"
             "  skip b: NOT rechecked -- no source (gh-unreadable: one\n"
             "two\n"
             "\n"
             "three). A --pin-source would verify it offline.\n"
             "  ok  c: fine\n"
             "  skip d: NOT rechecked (gh-unreadable: x). A --pin-source.\n"
             "WARNING w: a note\n"
             "  skip e: NOT rechecked.\n"
             "pins ok\n")
    assert skipped(whole) == [
        "b: NOT rechecked -- no source (gh-unreadable: one two three). A "
        "--pin-source would verify it offline.",
        "d: NOT rechecked (gh-unreadable: x). A --pin-source.",
        "e: NOT rechecked."]
    assert skipped("  ok  a: fine\nmanifest ok: x\n") == []


#: The variables the env probe below prints, in one list.
ASKED = TOKENS + ("GH_CONFIG_DIR", "GH_NO_UPDATE_NOTIFIER") + PROXIES + \
    NO_PROXIES


@pytest.mark.parametrize("reach_network", [False, True])
def test_run_validator_starts_a_child_offline_unless_its_caller_says(
        standard, tmp_path, monkeypatch, reach_network):
    """The contract of `run_validator`'s `env` block, asked of the child
    itself, as `test_run_validator_gives_the_child_exactly_the_pythonpath_it
    _is_given` asks it of `PYTHONPATH`: by default no token, `GH_CONFIG_DIR`
    the null device, the update notifier off, every proxy variable the
    unreachable one and no exception list; with `reach_network=True` -- the
    machine row's keyword -- the operator's values, untouched.

    ON EVERY PLATFORM, because the probe is a Python file and not a shebang:
    the Windows half of R297-1 is held here. The operator's environment is
    set through the upper-case names only, which on Windows are the same
    variables as the lower-case ones.
    """
    module = doctor_module(standard)
    for name in TOKENS:
        monkeypatch.setenv(name, SENTINEL_TOKEN)
    for name in ("https_proxy", "http_proxy", "no_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GH_CONFIG_DIR", str(tmp_path / "operators-gh-config"))
    monkeypatch.setenv("HTTPS_PROXY", "http://operators-proxy.invalid:3128")
    monkeypatch.setenv("NO_PROXY", SENTINEL_HOST)
    root = tmp_path / "root"
    root.mkdir()
    probe = root / "probe.py"
    probe.write_text(
        "import json, os\n"
        f"print(json.dumps({{n: os.environ.get(n) for n in {list(ASKED)!r}}}))"
        "\n", encoding="utf-8")
    ctx = module.Context(root)
    if reach_network:
        code, _quoted, whole = module.run_validator(ctx, probe, [],
                                                    reach_network=True)
    else:
        code, _quoted, whole = module.run_validator(ctx, probe, [])
    assert code == 0, whole
    seen = json.loads(whole)
    if reach_network:
        assert {name: seen[name] for name in TOKENS} == \
            {name: SENTINEL_TOKEN for name in TOKENS}, seen
        assert seen["GH_CONFIG_DIR"] == str(tmp_path / "operators-gh-config")
        assert seen["HTTPS_PROXY"] == "http://operators-proxy.invalid:3128"
        assert seen["NO_PROXY"] == SENTINEL_HOST, seen
        assert UNREACHABLE not in seen.values(), seen
        return
    assert {name: seen[name] for name in TOKENS + NO_PROXIES} == \
        dict.fromkeys(TOKENS + NO_PROXIES), seen
    assert seen["GH_CONFIG_DIR"] == os.devnull, seen
    assert seen["GH_NO_UPDATE_NOTIFIER"] == "1", seen
    assert {name: seen[name] for name in PROXIES} == \
        dict.fromkeys(PROXIES, UNREACHABLE), seen


# --- #298: a gate that cannot import repo_shape is not promised -------------

#: Per kind of root: the manifest, the gate that owns it, and the row.
UNLOADED_ROOT = {
    "project": ("project.yaml", "scripts/validate-manifest.py", "manifest",
                BREAKAGES),
    "family": ("family.yaml", "scripts/validate-family.py", "family",
               FAMILY_BREAKAGES),
}
LOST = "scripts/repo_shape.py"


def unloaded(kind: str, project: Path, holder: dict, tmp_path: Path,
             lose: str | None) -> tuple:
    """`(root, row id, refusal)`: a root of `kind` whose manifest has a TAB,
    so it does not load, and whose `scripts/repo_shape.py` is kept
    (`lose=None`, the control), deleted in the tree (`"tree"`), or deleted by
    a COMMIT (`"commit"`)."""
    name, own, row_id, breakages = UNLOADED_ROOT[kind]
    root = own_root("family" if kind == "family" else "manifest", project,
                    holder, tmp_path)
    assert (root / own).is_file(), own
    refusal = break_manifest(root / name, *breakages["tab-indent"])
    gone = root / LOST
    assert gone.is_file(), gone
    if lose == "tree":
        gone.unlink()
    elif lose == "commit":
        git("rm", "-q", "--", LOST, cwd=root)
        git("commit", "-q", "-m", "Drop repo_shape.py", "--", LOST, cwd=root)
    return root, row_id, refusal


def assert_the_gate_refuses_the_file(root: Path, row: dict, kind: str,
                                     refusal) -> None:
    """The row's NEXT is the root's own gate, and run it refuses the file
    with the loader's code and exit 2: the gate CAN say what the row said."""
    name, own, _row_id, _breakages = UNLOADED_ROOT[kind]
    assert_next_runs_the_roots_own(row, root, Path(own).name)
    ran = run_argv(command_of(row))
    said = ran.stdout + ran.stderr
    assert ran.returncode == 2, said
    assert f"REFUSED {refusal.code}: " in said, said
    assert refusal.detail[len(str(root / name)):] in said, said


@pytest.mark.parametrize("kind", sorted(UNLOADED_ROOT))
def test_a_root_that_lost_repo_shape_is_told_to_restore_it_first(
        standard, project, holder, tmp_path, kind):
    """R298-2 and R298-3: the reason is the loader's, unchanged, and the
    NEXT puts the file back -- run, it exits 0 and the file is there -- after
    which the doctor names the gate, and the gate refuses the manifest by its
    code, exit 2. The order the verdict already gives: DRIFTED (copy-missing)
    first, the gate after.
    """
    root, row_id, refusal = unloaded(kind, project, holder, tmp_path, "tree")
    name = UNLOADED_ROOT[kind][0]
    result = doctor(standard, root, "--json")
    row = rows_of(result)[row_id]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is True, row
    assert row["reason"] == f"{name} does not load: {loader_line(refusal)}"
    assert payload_of(result)["verdict"].startswith("DRIFTED"), result.stdout
    assert command_of(row)[:2] == ["git", "-C"], row["next"]
    assert Path(command_of(row)[2]).resolve() == root, row["next"]
    assert command_of(row)[3:] == ["checkout", "HEAD", "--", LOST], row["next"]
    restored = run_argv(command_of(row))
    assert restored.returncode == 0, restored.stdout + restored.stderr
    assert (root / LOST).is_file()
    after = rows_of(doctor(standard, root, "--json"))[row_id]
    assert_the_gate_refuses_the_file(root, after, kind, refusal)


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
@pytest.mark.parametrize("kind", sorted(UNLOADED_ROOT))
def test_the_restore_line_pasted_lets_the_gate_print_its_refusal(
        standard, project, holder, tmp_path, kind):
    """The same two lines PASTED, whole, from `/` with no `PYTHONPATH`: the
    restore, then the gate the doctor names next, which prints `REFUSED
    yaml-unparsable` and exits 2 -- where the old promise, pasted, printed
    `ModuleNotFoundError` and exited 1."""
    root, row_id, refusal = unloaded(kind, project, holder, tmp_path, "tree")
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    restore = pasted_from_elsewhere(row["next"], tmp_path)
    assert restore.returncode == 0, restore.stdout + restore.stderr
    after = rows_of(doctor(standard, root, "--json"))[row_id]
    gate = pasted_from_elsewhere(after["next"], tmp_path)
    whole = gate.stdout + gate.stderr
    assert gate.returncode == 2, whole
    assert f"REFUSED {refusal.code}: " in whole, whole
    assert "ModuleNotFoundError" not in whole, whole


@pytest.mark.parametrize("kind", sorted(UNLOADED_ROOT))
def test_a_root_that_keeps_repo_shape_is_still_sent_to_its_gate(
        standard, project, holder, tmp_path, kind):
    """The control: the same manifest, `scripts/repo_shape.py` kept, and the
    NEXT is the gate, which refuses the file the same way, exit 2."""
    root, row_id, refusal = unloaded(kind, project, holder, tmp_path, None)
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    assert row["status"] == "FINDING", row
    assert "checkout" not in command_of(row), row["next"]
    assert_the_gate_refuses_the_file(root, row, kind, refusal)


def test_a_committed_deletion_of_repo_shape_gets_no_head_line(
        standard, project, holder, tmp_path):
    """HEAD does not hold a file whose deletion was COMMITTED, so `checkout
    HEAD` could not restore it: the row has no NEXT, keeps the loader's
    words first, and says the file comes back from the parent of the commit
    that deleted it."""
    root, row_id, refusal = unloaded("project", project, holder, tmp_path,
                                     "commit")
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    assert row["status"] == "FINDING", row
    assert row["next"] is None, row
    assert row["reason"].startswith(
        f"project.yaml does not load: {loader_line(refusal)}; "), row
    assert "parent of the commit" in row["reason"], row


@pytest.mark.parametrize("kind", sorted(UNLOADED_ROOT))
def test_a_crash_for_want_of_repo_shape_says_which_file_is_not_there(
        standard, project, holder, tmp_path, kind):
    """R298-1's fact, in a CRASH reason (#298): a root's own gate that dies on
    `import repo_shape` because `scripts/repo_shape.py` is gone says that file
    is not there, after the exception it quotes -- so a reader is not left
    with `ModuleNotFoundError` and a guess. The manifest is VALID here, so the
    row runs the gate and the gate crashes, rather than the loader refusing.

    Only the root's own copy can be asked: the standard's template copy has no
    `repo_shape.py` beside it by design, and a standard that lost its own
    cannot start the doctor at all.
    """
    _name, _own, row_id, _breakages = UNLOADED_ROOT[kind]
    root = own_root("family" if kind == "family" else "manifest", project,
                    holder, tmp_path)
    (root / LOST).unlink()
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    assert row["status"] == "FINDING", row
    assert row["detail"]["crashed"] is True, row
    assert row["detail"]["own_copy"] is True, row
    assert "ModuleNotFoundError" in row["reason"], row
    assert (f"{LOST}, which it imports from beside itself, is not there"
            in row["reason"]), row


# --- #278: the lockstep line of the `legs` and `members` rows ----------------

def assert_no_pythonpath_line(*streams: str) -> None:
    """A `PYTHONPATH=` assignment, said anywhere: none could be pasted and
    work from a standard whose path holds the separator. (The environment
    row's own reason says `PYTHONPATH` with no `=` after it.)"""
    for said in streams:
        assert "PYTHONPATH=" not in said, said


@WINDOWS_SKIP
def test_a_colon_standard_withholds_the_legs_rows_lockstep_line(
        standard, project, tmp_path):
    """Doctor A's `legs` row hands a leg whose gitlink is not its pin the
    lockstep gate (#276), and where the root has no `validate-pins.py` of its
    own that gate is the standard's TEMPLATE copy, whose line carries
    `PYTHONPATH=<standard>/scripts`. Under a directory whose name holds
    `os.pathsep` no `PYTHONPATH` can name that, and the `pins` row beside it
    already says so: an environment row, nothing run, no NEXT. The `legs` row
    must not print the line that row refused, so its NEXT is None -- and its
    finding stands, since the gitlink is not the pin whatever the standard's
    path is (#278).

    THE CONTROL is the same root asked from a plain directory, where the line
    is printed and is the command the `pins` row hands over (the `why`s
    that explain it differ), so the None below is the separator's doing and
    not a fixture that never had a line.
    `WINDOWS_SKIP`: Windows refuses `:` in a file name; the semicolon half of
    the helper is held by the semicolon test above.
    """
    git("rm", "-q", "scripts/validate-pins.py", cwd=project)
    make_gitlink_moved(project)
    control = rows_of(doctor(standard, project, "--json"))
    plain = control["legs"]
    assert plain["status"] == "FINDING", plain
    assert plain["next"].startswith("env PYTHONPATH="), plain
    assert "validate-pins.py" in plain["next"], plain
    assert command_of(plain) == command_of(control["pins"]), (
        plain, control["pins"])

    here = standard_under(standard, tmp_path, "dir:with-colon")
    result = doctor(here, project, "--json")
    rows = rows_of(result)
    legs, pins = rows["legs"], rows["pins"]
    assert legs["status"] == "FINDING", legs
    assert legs["reason"] == plain["reason"], (legs, plain)
    assert legs["next"] is None, legs
    assert pins["status"] == "FINDING", pins
    assert pins["detail"]["environment"] is True, pins
    assert pins["detail"]["own_copy"] is False, pins
    assert pins["detail"]["exit"] is None, pins
    assert pins["next"] is None, pins
    assert "holds ':'" in pins["reason"], pins
    assert result.returncode == 3, result.stdout + result.stderr
    text = doctor(here, project)
    assert_no_pythonpath_line(result.stdout, text.stdout, text.stderr)


@WINDOWS_SKIP
def test_a_colon_standard_withholds_the_members_rows_lockstep_line_too(
        standard, holder, tmp_path):
    """The `members` row shares `lockstep_next` with the `legs` row, and the
    holder's gate is `validate-family.py`: a member whose gitlink is not its
    pin, a holder with no gate of its own, and a standard under a colon give
    the `family` row the environment row and the `members` row no NEXT
    (#278). The same control, from a plain directory, still prints the line.
    """
    root = holder_copy(holder, tmp_path)
    make_member_gitlink_mismatch(root)
    git("rm", "-q", "scripts/validate-family.py", cwd=root)
    control = rows_of(doctor(standard, root, "--json"))
    plain = control["members"]
    assert plain["status"] == "FINDING", plain
    assert plain["next"].startswith("env PYTHONPATH="), plain
    assert "validate-family.py" in plain["next"], plain
    assert command_of(plain) == command_of(control["family"]), (
        plain, control["family"])

    here = standard_under(standard, tmp_path, "dir:with-colon")
    result = doctor(here, root, "--json")
    rows = rows_of(result)
    members, family = rows["members"], rows["family"]
    assert members["status"] == "FINDING", members
    assert members["reason"] == plain["reason"], (members, plain)
    assert members["next"] is None, members
    assert family["status"] == "FINDING", family
    assert family["detail"]["environment"] is True, family
    assert family["next"] is None, family
    assert result.returncode == 3, result.stdout + result.stderr
    text = doctor(here, root)
    assert_no_pythonpath_line(result.stdout, text.stdout, text.stderr)


@PTY_SKIP
def test_the_doctor_in_a_persons_terminal_offers_nothing(tmp_path):
    """#492: `setup-project.py` asks at the CONTROLLING terminal when stdin
    is not one, and the `machine` row runs its `--preflight` with stdin
    closed. From a person's own terminal, on a machine whose `gh` is not
    logged in (the session's guard answers so), that preflight would offer
    `gh auth login` there and the doctor would sit waiting on it. Its
    children run in a session of their own, with no terminal to ask on: the
    row reports, nothing is offered, and the doctor finishes."""
    empty = tmp_path / "not-a-root"
    empty.mkdir()
    status, screen, _ = run_in_a_terminal(
        [sys.executable, str(REPO / DOCTOR), "--root", str(empty)],
        cwd=tmp_path, env=dict(os.environ), timeout=90)
    assert "Type yes to continue:" not in screen, screen
    assert "NOT A SHAPE ROOT" in screen, screen
    assert status == 2, screen
