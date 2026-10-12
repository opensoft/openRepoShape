# SPDX-License-Identifier: Apache-2.0
"""A shape pin whose `files:` is not a list is reported, not iterated (#290).

Four readers took `pin.get("files") or []` and looped over it: `read_pin` in
`update-shape.py` (so `check`, `apply` and the doctor's shape-currency row),
`_check_shape_pin` in the assembly root's `scripts/validate-pins.py`,
`_check_shape_pin_files` in the holder's `scripts/validate-family.py`, and
`pinned_paths` in `shape-doctor.py`. `or []` rescues the falsy values, which
reach the `no files` refusal or finding. A TRUTHY scalar was iterated:
`files: 5`, `files: true` and `files: 1.5` ended every one of them in
`TypeError: 'int' object is not iterable` (or `'bool'`, `'float'`), exit 1,
and the doctor, whose one job is to say what is wrong, printed nothing at all.

Each case below commits one such pin over a clean scaffold or a clean holder
and runs a reader on it. On the code before #290 each one is a traceback.

The doctor's VERDICT for a root pin `read_pin` refuses is #237's business
(PR #267 moves it from CANNOT ANSWER, exit 3, to INVALID, exit 1), so the
doctor's cases assert the ROW and that a verdict was printed at all, never
which one.

NOTHING HERE REACHES A NETWORK: the scaffold and the holder use
`--local-remote-dir`, and `read_pin` refuses before `--upstream` is opened.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shlex
import shutil
import sys

import pytest

from conftest import REPO, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
DOCTOR = REPO / "shape-doctor.py"
FAMILY = REPO / "scripts" / "family.py"
SHAPE_PIN = "contracts/shape-pin.yaml"
HOLDER = "Fam"

#: `(what follows `files:` in the pin, how the reader shows the value back)`.
#: Python's `repr`, because each reader names the value with `!r` the way it
#: already names a `commit:` or a `revision_kind:` it cannot use.
NOT_A_LIST = [
    pytest.param("5", "5", id="files-5"),
    pytest.param("true", "True", id="files-true"),
    pytest.param("1.5", "1.5", id="files-1.5"),
]

#: Every verdict the doctor's text report can end on.
VERDICT = re.compile(r"^(COMPLIANT|DRIFTED|MISPLACED|INVALID|NOT A SHAPE ROOT"
                     r"|CANNOT ANSWER)\b")


def commit_files(root, files_text: str, message: str) -> None:
    """Replace the pin's `files:` rows by `files_text` and commit it.

    `files:` is the pin's last key, so the rest of the pin is untouched.
    BYTES, never `write_text`, so the file stays LF on every OS. Committed,
    as in the issue's reproduction: the pin is wrong in the repository, not
    only in a working tree.
    """
    pin = root / SHAPE_PIN
    text = pin.read_bytes().decode("utf-8")
    cut = text.index("\nfiles:\n") + 1
    pin.write_bytes((text[:cut] + files_text).encode("utf-8"))
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "-m", message, "--", SHAPE_PIN, cwd=root)


def scalar_files(root, value: str) -> None:
    """`files: <value>`, committed: a pin whose `files:` is not a list."""
    commit_files(root, f"files: {value}\n", f"files: {value}")
    assert not isinstance(load_yaml(root / SHAPE_PIN)["files"], list), \
        "fixture drift: the pin still carries a list of rows"


def pin_log_command(root) -> str:
    """The remediation's `git log`, as `update-shape.py` spells it for `root`.

    COMPUTED here with `shlex.join`, the quoter `update-shape.py`'s
    `_by_hand` uses, and not written as a literal: a root holding a space or,
    on Windows, a backslash is quoted, so a literal would pass on one OS and
    fail on the next. The root is `resolve()`d because the tool resolves its
    `--root` (a Windows temp directory can arrive as an 8.3 short name).
    """
    return shlex.join(["git", "-C", str(root.resolve()), "log", "--",
                       SHAPE_PIN])


def no_traceback(result) -> None:
    assert "Traceback" not in result.stderr, result.stderr
    assert "is not iterable" not in result.stderr, result.stderr


def rows_of(result) -> dict:
    return {row["id"]: row for row in json.loads(result.stdout)["rows"]}


def findings(result, code: str) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith(f"FINDING {code}:")]


def assert_refused_update_pin_row(result, shown: str, root) -> None:
    """`read_pin`'s refusal: by name, exit 2, the value shown, and a remedy
    about the pin -- not `repo_shape`'s default one about submodules. The
    `git log` it points at is `git -C <root>`, never the bare one: this tool
    is run from the openRepoShape checkout with `--root <project>`, so a bare
    `git log` would read the checkout's history, not the project's."""
    no_traceback(result)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED update-pin-row: " in result.stderr, result.stderr
    assert f"`files:` is {shown}, not a list" in result.stderr
    assert pin_log_command(root) in result.stderr, result.stderr
    assert "git log" not in result.stderr, result.stderr
    assert "submodule" not in result.stderr


def assert_one_shape_pin_row_finding(result, shown: str) -> None:
    """A validator's finding, once, for the whole `files:` -- exit 1."""
    no_traceback(result)
    assert result.returncode == 1, result.stdout + result.stderr
    rows = findings(result, "shape-pin-row")
    assert len(rows) == 1, result.stderr
    assert f"`files:` is {shown}, not a list" in rows[0], rows[0]


def assert_shape_currency_row(result, shown: str) -> dict:
    """The doctor printed a report, and its shape-currency row names the
    refusal `read_pin` raised for the pin."""
    no_traceback(result)
    assert result.returncode in (1, 3), result.stdout + result.stderr
    rows = rows_of(result)
    row = rows["shape-currency"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["error"] == "update-pin-row", row["detail"]
    assert f"`files:` is {shown}, not a list" in row["reason"], row["reason"]
    return rows


# --- an assembly root ------------------------------------------------------

@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_update_shape_check_and_apply_refuse_it_by_name(project, value,
                                                        shown):
    scalar_files(project, value)
    before = (project / SHAPE_PIN).read_bytes()
    checked = run_script(UPDATE, "check", "--root", str(project),
                         "--upstream", str(REPO))
    assert_refused_update_pin_row(checked, shown, project)
    applied = run_script(UPDATE, "apply", "--root", str(project), "--yes",
                         "--upstream", str(REPO))
    assert_refused_update_pin_row(applied, shown, project)
    assert (project / SHAPE_PIN).read_bytes() == before, \
        "a refused apply writes nothing"


PIN_LOG_SAID = re.compile(r"`(git -C [^`]+)` names the commit that changed")


def printed_pin_log(result) -> str:
    """The `git log` the remediation prints, exactly as it is printed."""
    said = PIN_LOG_SAID.search(result.stderr)
    assert said, result.stderr
    return said.group(1)


def test_the_remediations_git_log_reads_the_root_it_was_run_on(project,
                                                               tmp_path):
    """THE CWD IS NOT THE ROOT, and the root holds a space.

    The documented way to run this tool is from the openRepoShape checkout,
    `update-shape.py check --root /path/to/project`. A bare `git log --
    contracts/shape-pin.yaml` printed for that run inspects the CHECKOUT and
    shows no pin history, so the person cannot follow the remediation
    (codex, PR #343). The printed command is run here, from the checkout, and
    must show the project's own commits to the pin.
    """
    spaced = tmp_path / "a root with space" / "Atlas"
    spaced.parent.mkdir()
    shutil.copytree(project, spaced, symlinks=True)
    scalar_files(spaced, "5")
    checked = run_script(UPDATE, "check", "--root", str(spaced),
                         "--upstream", str(REPO), cwd=REPO)
    assert_refused_update_pin_row(checked, "5", spaced)
    command = printed_pin_log(checked)
    assert command == pin_log_command(spaced), command
    # The space did not split the root into two words.
    assert shlex.split(command) == ["git", "-C", str(spaced.resolve()), "log",
                                    "--", SHAPE_PIN], command

    shown = git(*shlex.split(command)[1:], cwd=REPO).stdout
    history = git("log", "--format=%H", "--", SHAPE_PIN, cwd=spaced)
    commits = history.stdout.split()
    assert len(commits) >= 2, history.stdout
    for sha in commits:
        assert sha in shown, f"{sha} is a commit to the pin, not shown:\n{shown}"
    assert git("rev-parse", "HEAD", cwd=spaced).stdout.strip() in shown


def test_a_row_that_is_not_a_mapping_carries_the_same_remediation(project,
                                                                  tmp_path):
    """`read_pin` raises `update-pin-row` twice, and both carry the remedy:
    `files:` is a list here, but its one row is `5`, not `path:`/`sha256:`."""
    spaced = tmp_path / "a root with space" / "Atlas"
    spaced.parent.mkdir()
    shutil.copytree(project, spaced, symlinks=True)
    commit_files(spaced, "files:\n  - 5\n", "files: - 5")
    assert load_yaml(spaced / SHAPE_PIN)["files"] == [5], \
        "fixture drift: the pin does not carry one scalar row"
    checked = run_script(UPDATE, "check", "--root", str(spaced),
                         "--upstream", str(REPO), cwd=REPO)
    no_traceback(checked)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert "REFUSED update-pin-row: " in checked.stderr, checked.stderr
    assert "a `files:` row is not `path:`/`sha256:`" in checked.stderr
    assert printed_pin_log(checked) == pin_log_command(spaced)
    assert "git log" not in checked.stderr, checked.stderr
    assert "submodule" not in checked.stderr


@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_the_projects_validate_pins_reports_it_once(project, value, shown):
    scalar_files(project, value)
    result = run_script(project / "scripts" / "validate-pins.py",
                        cwd=project)
    assert_one_shape_pin_row_finding(result, shown)


@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_the_doctor_reports_it_in_the_shape_currency_row(project, value,
                                                         shown):
    scalar_files(project, value)
    rows = assert_shape_currency_row(
        run_script(DOCTOR, "--root", str(project), "--json"), shown)
    # The project's own validator, run by the `pins` row, says the same.
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    assert "shape-pin-row" in rows["pins"]["reason"], rows["pins"]
    plain = run_script(DOCTOR, "--root", str(project))
    no_traceback(plain)
    assert f"`files:` is {shown}, not a list" in plain.stdout, plain.stdout
    last = [line for line in plain.stdout.splitlines() if line.strip()][-1]
    assert VERDICT.match(last), plain.stdout
    assert not last.startswith("COMPLIANT"), last


@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_the_doctor_reaches_the_agent_files_row_past_it(project, value,
                                                        shown):
    """`pinned_paths` is read only when an agent file is missing, so the root
    under test has no `AGENTS.md`: the row is reached, and the pin -- which
    names no file -- names none of the absent ones."""
    scalar_files(project, value)
    (project / "AGENTS.md").unlink()
    rows = assert_shape_currency_row(
        run_script(DOCTOR, "--root", str(project), "--json"), shown)
    agent = rows["agent-files"]
    assert agent["detail"]["pinned"] == [], agent
    assert agent["reason"] == "absent: AGENTS.md", agent


@pytest.fixture(scope="module")
def doctor_module():
    spec = importlib.util.spec_from_file_location("shape_doctor_pin_files",
                                                  DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_pinned_paths_of_it_is_the_empty_set(doctor_module, project, value,
                                             shown):
    scalar_files(project, value)
    assert doctor_module.pinned_paths(project) == set()


# --- a family holder -------------------------------------------------------

@pytest.fixture(scope="module")
def initialised_holder(tmp_path_factory):
    """One `family.py init`, no members: the holder's pin and its validator
    are all these cases need, and the validator passes it as it stands."""
    base = tmp_path_factory.mktemp("pin-files-holder")
    created = run_script(
        FAMILY, "init", "--org", "testorg", "--family", HOLDER,
        "--created-by", "Test Human", "--created-on", "2026-09-04",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = base / "fam" / HOLDER
    clean = run_script(root / "scripts" / "validate-family.py", cwd=root)
    assert clean.returncode == 0, clean.stderr + clean.stdout
    return root


@pytest.fixture
def holder(initialised_holder, tmp_path):
    target = tmp_path / HOLDER
    shutil.copytree(initialised_holder, target, symlinks=True)
    return target


@pytest.mark.parametrize("value, shown", NOT_A_LIST)
def test_the_holders_validate_family_and_update_shape_and_doctor(holder,
                                                                 value,
                                                                 shown):
    scalar_files(holder, value)
    assert_one_shape_pin_row_finding(
        run_script(holder / "scripts" / "validate-family.py", cwd=holder),
        shown)
    assert_refused_update_pin_row(
        run_script(UPDATE, "check", "--root", str(holder),
                   "--upstream", str(REPO)), shown, holder)
    rows = assert_shape_currency_row(
        run_script(DOCTOR, "--root", str(holder), "--json"), shown)
    assert rows["family"]["status"] == "FINDING", rows["family"]
    assert "shape-pin-row" in rows["family"]["reason"], rows["family"]


# --- the control: a falsy `files:` keeps the refusal it had ----------------

@pytest.mark.parametrize("value", ["0", "false"])
def test_a_falsy_files_is_still_no_files(project, value):
    """NOT A #290 CASE, and it passes before #290 too. `or []` turns `0` and
    `false` into no rows, and they keep `update-pin-no-files` and
    `shape-pin-no-files`: the new guard is for what `or []` let through."""
    scalar_files(project, value)
    checked = run_script(UPDATE, "check", "--root", str(project),
                         "--upstream", str(REPO))
    no_traceback(checked)
    assert checked.returncode == 2
    assert "REFUSED update-pin-no-files: " in checked.stderr
    validated = run_script(project / "scripts" / "validate-pins.py",
                           cwd=project)
    no_traceback(validated)
    assert validated.returncode == 1
    assert len(findings(validated, "shape-pin-no-files")) == 1
    assert not findings(validated, "shape-pin-row")
