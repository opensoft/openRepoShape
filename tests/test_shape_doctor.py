# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` and `openRepoShape --doctor`: the rows, and the verdict.

OFFLINE, AND AGAINST A STANDARD THIS FILE BUILT. Every other suite here
scaffolds from `REPO` — this checkout's WORKING TREE — and that is exactly
what a doctor cannot be tested against: the doctor compares a project's
copies against the standard AT A COMMIT, and a working tree with an
uncommitted edit in `templates/` would report a `locally-modified` row for a
file nobody touched, on one developer's machine and nowhere else.

So `standard` copies every tracked file into a temporary directory and makes
ONE commit of it. That repository is the upstream, the project is scaffolded
from it, and `shape-doctor.py` is run out of it — so the pin, the bytes and
the comparison all name the same commit, on any machine, in any working tree.
It also means these tests exercise the code as it is on disk right now rather
than as it was committed, which is the point of running them at all.

NOTHING HERE REACHES A NETWORK. The scaffolds use `--local-remote-dir` (bare
repositories on disk as origins), and the shim tests put a `gh` and a `curl`
on `$PATH` that refuse loudly and log every call, so a run that tried to
fetch would fail rather than quietly succeed against github.com. Every other
doctor run's `machine` row asks the session's `gh` guard (`tests/conftest.py`,
#296), which answers its two probes as a `gh` with no login and fails the
test on any other call.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import re
import shlex
import shutil
import subprocess
import sys

from pathlib import Path, PurePosixPath, PureWindowsPath
from types import SimpleNamespace

import pytest

from conftest import (FILE_PROTOCOL, REPO, WINDOWS_SKIP,
                      assert_read_through_git, clone_just_pushed,
                      cloned_just_pushed, git, load_without_bytecode, rmtree,
                      run_script)
from gh_guard import PROBES as GH_PROBES

sys.path.insert(0, str(REPO / "scripts"))
#: THE ONE DEFINITION of "is this the same repository" (#155), imported here
#: so the test below can assert that the doctor's name and the holder's name
#: ARE it -- an identity assertion, where two copies could only ever be
#: compared to each other.
import repo_shape  # noqa: E402
#: The lane a lane's run sets, imported from the file that owns that rule
#: rather than retyped -- see `tests/test_commit_trailers.py`.
from test_commit_trailers import LANE
#: The renderer of the README line #148 taught `update-shape.py apply` to
#: rewrite, imported from the module that owns its tests for the same reason:
#: a test that retyped the form would pass against a line nothing renders.
from test_update_shape import rendered_shape_line
#: An `origin` written as BYTES git hands back unchanged, and the start of a
#: URL holding the byte 0xE9 (#385), from the file that owns the advisory's
#: half of that issue, so the two halves write the same URL the same way.
from test_shape_advisory import NOT_UTF8, repository, with_origin

DOCTOR = "shape-doctor.py"
#: What both scaffold rows say beside their line (#545).
SCAFFOLD_WHY = ("replace <your-org> with the GitHub organisation to create "
                "it in; without --yes, it asks")
ORG = "testorg"
PROJECT = "Atlas"
FAMILY_NAME = "InkRouter"
FAMILY_MEMBER = "IRRS"

#: The shape copy every drift test edits. `scripts/bootstrap.py` is a pinned
#: `files:` row in `contracts/shape-pin.yaml`, it is not a file any of these
#: tests otherwise run, and a project editing its own bootstrap is the
#: concrete case `update-shape.py`'s `locally-modified` refusal was written
#: for.
DRIFT_TARGET = "scripts/bootstrap.py"

#: The upstream file the "the standard moved on" test changes. It is copied
#: VERBATIM into an assembly root as `Makefile`, so one commit here produces
#: exactly one `upstream-changed` row and no additions.
UPSTREAM_TARGET = "templates/assembly-root/Makefile"

GIT_IDENTITY = {"GIT_AUTHOR_NAME": "openRepoShape tests",
                "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
                "GIT_COMMITTER_NAME": "openRepoShape tests",
                "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid"}


def commit_all(repo: Path, message: str) -> None:
    """`git add -A && git commit`, with an identity that is never global."""
    subprocess.run(["git", "add", "-A", "--", "."], cwd=str(repo),
                   capture_output=True, check=True)
    proc = subprocess.run(["git", "commit", "-q", "-m", message],
                          cwd=str(repo), capture_output=True, text=True,
                          check=False, env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 0, proc.stderr + proc.stdout


@pytest.fixture(scope="session")
def standard(tmp_path_factory) -> Path:
    """This working tree's TRACKED files, committed once, as the upstream.

    `git ls-files` rather than a `copytree`: the untracked half of a
    developer's checkout is `__pycache__`, a `.venv` and whatever they were
    doing, none of which the standard ships — and `shutil.copy2` keeps the
    mode bit, which is what makes the copied validators executable.
    """
    dest = tmp_path_factory.mktemp("standard") / "openRepoShape"
    dest.mkdir()
    listed = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"],
                            capture_output=True, check=True)
    for name in listed.stdout.decode("utf-8").split("\0"):
        if not name:
            continue
        source = REPO / name
        if not source.is_file():
            continue
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    git("init", "-q", "-b", "main", ".", cwd=dest)
    commit_all(dest, "openRepoShape, as this working tree has it")
    return dest


def scaffold(standard: Path, base: Path, project: str,
             org: str = ORG) -> subprocess.CompletedProcess:
    result = run_script(
        standard / "scaffold-project.py", "--org", org, "--project", project,
        "--elected-by", "Test Human", "--elected-on", "2026-09-10",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    return result


@pytest.fixture(scope="session")
def scaffolded_here(standard, tmp_path_factory) -> dict:
    """One project scaffolded FROM `standard`, plus a recursive clone."""
    base = tmp_path_factory.mktemp("doctored")
    scaffold(standard, base, PROJECT)
    clones = base / "clones"
    clones.mkdir()
    proc = clone_just_pushed(base / "remotes" / f"{PROJECT}.git",
                             clones / PROJECT)
    assert proc.returncode == 0, proc.stderr
    return {"base": base, "clone": clones / PROJECT}


@pytest.fixture
def project(scaffolded_here, tmp_path) -> Path:
    """A private, mutable copy of that clone."""
    target = tmp_path / PROJECT
    shutil.copytree(scaffolded_here["clone"], target, symlinks=True)
    return target


def test_the_session_clone_was_read_through_git_not_through_the_remotes(
        scaffolded_here):
    """#440: `scaffolded_here` cloned what it had just pushed through the
    transport, so the root and both legs are ONE PACK each. A plain-path
    clone leaves the remotes' loose objects loose, and is the one that lost a
    file to background maintenance on the macOS runner, erroring every test
    in this file at setup (124 of them, then 118)."""
    assert_read_through_git(scaffolded_here["clone"])


def doctor(standard: Path, root, *args) -> subprocess.CompletedProcess:
    return run_script(standard / DOCTOR, "--root", str(root), *args)


def rows_of(result) -> dict:
    """`{id: row}` from a `--json` run, so a test names a row rather than a
    line number of a table that is free to be re-laid-out.

    AND EVERY ROW IT HANDS BACK IS HELD TO `assert_next_holds_no_prose`
    (#548), so each row any test here reads is a case of that guard."""
    payload = json.loads(result.stdout)
    for row in payload["rows"]:
        assert_next_holds_no_prose(row)
    return {row["id"]: row for row in payload["rows"]}


def outside_single_quotes(command: str) -> str:
    """`command` less what `sh` reads literally: single-quoted spans and the
    character after a backslash. A `$(` left in it is run -- inside double
    quotes as much as outside them -- which `shlex`'s tokens cannot show:
    they read `"$(make)"` as the one word `$(make)`, exactly as they read
    the quoted path `'$(make)'`, which runs nothing.

    HERE, beside `rows_of`, because the guard below reads a NEXT with it and
    `tests/test_doctor_next_is_a_command.py`, which imports this module,
    reads one with it too; `quote_arg`'s `'\\''` form is read as `sh` reads
    it, where a regular expression for a quoted span is not."""
    kept, single, double, at = [], False, False, 0
    while at < len(command):
        char = command[at]
        if single:
            single = char != "'"
        elif char == "\\":
            at += 1
        elif char == "'" and not double:
            single = True
        else:
            double = double != (char == '"')
            kept.append(char)
        at += 1
    return "".join(kept)


def assert_next_holds_no_prose(row: dict) -> None:
    """A row's NEXT is one command, or nothing (#548): no backtick outside a
    quoted value, and no `Remediation:`.

    A backtick runs the command it opens where the line is pasted into
    zsh, interactive or `-c`: the `manifest kinds` NEXT for a `family.yaml`
    beside `project.yaml` ran `family.py init` and `family.py add` there.
    `Remediation:` opens the prose a tool prints under its own refusal, and
    a check that let a refusal out printed it as the NEXT (#408).

    OVER THE ROWS, NOT THE SOURCE, which is #408's point: a remedy arrives at
    run time, out of another module, and no scan of `shape-doctor.py`'s
    strings sees it. `rows_of` asks this of every row a `--json` run
    returns, so every row the suite builds, from whichever builder, is a
    case; `tests/test_doctor_next_is_a_command.py` shows it catching each
    form and builds the rows a refusal makes.
    """
    command = row.get("next")
    if not command:
        return
    assert "`" not in outside_single_quotes(command), (row["id"], command)
    assert "Remediation:" not in command, (row["id"], command)


def verdict_line(result) -> str:
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return lines[-1]


# --- a project that is compliant -------------------------------------------

def test_a_freshly_scaffolded_project_is_compliant(standard, project):
    """The base case, and the one every other test here is a delta from.

    A project scaffolded from `standard` MINUTES AGO is compliant with it by
    construction — every copy is verbatim, the pin names that commit, both
    legs sit at their pins. A doctor that cannot say so about this project
    cannot say it about any.
    """
    result = doctor(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict_line(result).startswith("COMPLIANT   (exit 0)"), \
        result.stdout
    assert "FINDING" not in result.stdout, result.stdout


def test_every_row_of_a_compliant_project_is_ok_or_na(standard, project):
    """WHICH rows ran, by id, and that none of them is a finding.

    The ids are the `--json` contract: a caller acts on `rows[].id`, so a
    rename is a breaking change and belongs in a test rather than in
    somebody's surprise.
    """
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "project"
    assert payload["verdict"] == "COMPLIANT"
    assert payload["exit"] == 0
    assert payload["note"] is None
    rows = rows_of(result)
    assert set(rows) == {"naming", "manifest", "pins", "manifest-kinds",
                         "shape-currency", "legs", "leg-shape-files",
                         "placement", "agent-files", "machine"}
    for name, row in rows.items():
        assert row["status"] in ("ok", "n/a"), (name, row)
        assert row["status"] != "FINDING", (name, row)
        assert set(row) == {"id", "label", "status", "reason", "next",
                            "why", "detail"}
    # The project carries its OWN validators, so those are what ran.
    assert rows["pins"]["detail"]["own_copy"] is True
    assert rows["manifest"]["detail"]["own_copy"] is True
    assert rows["shape-currency"]["detail"]["pinned"] == \
        rows["shape-currency"]["detail"]["standard"]
    assert rows["machine"]["status"] == "n/a", (
        "the machine row is about the workstation and must never be able to "
        "move the verdict")


def test_the_agent_files_and_leg_files_are_reported(standard, project):
    result = doctor(standard, project, "--json")
    rows = rows_of(result)
    assert rows["agent-files"]["detail"]["files"] == {
        "AGENTS-shape.md": True, "AGENTS.md": True, "CLAUDE.md": True}
    legs = rows["leg-shape-files"]["detail"]["legs"]
    assert set(legs) == {"spec", "code"}
    for entry in legs.values():
        assert entry["state"] == "compared", entry
        # `.gitignore` and `CLAUDE.md` are copied verbatim out of
        # `templates/<role>-root/`; `AGENTS.md` is RENDERED from a template
        # full of `{{PLACEHOLDER}}`s, so it can only ever be reported as
        # rendered and never compared byte for byte.
        assert entry["files"][".gitignore"] == "identical", entry
        assert entry["files"]["AGENTS.md"] == "rendered", entry


# --- drift ------------------------------------------------------------------

def test_an_edited_shape_copy_is_drift_and_names_update_shape(standard,
                                                              project):
    """One edited copy: DRIFTED, exit 1, the FILE named and the fix named.

    DRIFT OUTRANKS THE RED VALIDATOR, deliberately: this same edit makes the
    project's own `validate-pins.py` red — that is what a per-file digest is
    FOR — and a verdict of `INVALID (pins)` would send the reader at the
    symptom while the exit is `update-shape.py`. Both rows are printed, and
    this asserts both.

    THE FIX IS NAMED WITHOUT `--accept-local` (#501). This test pinned the
    hand-over of that flag on purpose, on the reasoning that a reader would
    know not to paste it; but AGENTS.md tells the reader to run the command
    a row names, and pasted, it re-pinned the project's edit as the standard
    before `update-local-drift` could ask the human whether the project keeps
    it. Brett Heap ruled on 2026-10-13, "Stop pre-filling it", so the
    assertion is now the opposite one, in every line the report prints.
    """
    edited = project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8")
                      + "\n# a local edit nobody carried upstream\n",
                      encoding="utf-8")
    result = doctor(standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith("DRIFTED (1 locally-modified)"), \
        result.stdout
    assert DRIFT_TARGET in result.stdout
    assert "update-shape.py" in result.stdout
    assert "--accept-local" not in result.stdout, (
        "a `locally-modified` row must not hand over the flag that re-pins "
        "it: whether the project keeps its edit is the human's decision, and "
        "the `apply` it names asks it by refusing `update-local-drift`")
    # The pins row is red too, and is still printed with its own next step.
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    assert rows["shape-currency"]["detail"]["drifted"] is True
    assert rows["shape-currency"]["detail"]["paths"]["locally-modified"] == \
        [DRIFT_TARGET]


# --- the standard has moved on ---------------------------------------------

def standard_ahead(standard: Path, tmp_path: Path, path: str = "README.md",
                   appended: str = "\nA fix.\n",
                   message: str = "An upstream change to a file no project "
                                  "copies") -> Path:
    """A COPY of the standard at `<tmp>/standard-ahead`, with one more commit
    that appends `appended` to `path`. By default that is `README.md`, a file
    no copy list names, so nothing a project holds can differ and the pin
    alone is behind. One helper, because the tests here and the ones in
    `tests/test_doctor_next_is_a_command.py` each built it by hand (#277)."""
    ahead = tmp_path / "standard-ahead"
    shutil.copytree(standard, ahead, symlinks=True)
    target = ahead / path
    target.write_text(target.read_text(encoding="utf-8") + appended,
                      encoding="utf-8")
    commit_all(ahead, message)
    return ahead


@pytest.fixture
def advanced_standard(standard, tmp_path) -> Path:
    """A COPY of the standard with one more commit on a copied template.

    A copy rather than a commit on the session-scoped fixture: every other
    test in this file is a claim about a project that is compliant with
    `standard`, and advancing it in place would make them all say `SHAPE
    BEHIND` depending on the order they ran in.
    """
    return standard_ahead(standard, tmp_path, UPSTREAM_TARGET,
                          "\n# an upstream fix, after this project was cut\n",
                          "An upstream fix to a copied file")


def test_a_project_behind_the_standard_is_compliant_but_behind(
        advanced_standard, project):
    result = doctor(advanced_standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith(
        "COMPLIANT, SHAPE BEHIND (1 upstream-changed, 0 upstream-added)"), \
        result.stdout
    assert "Makefile" in result.stdout
    assert "update-shape.py" in result.stdout
    rows = rows_of(doctor(advanced_standard, project, "--json"))
    assert rows["shape-currency"]["detail"]["behind"] is True
    assert rows["shape-currency"]["detail"]["drifted"] is False
    assert rows["shape-currency"]["detail"]["paths"]["upstream-changed"] == \
        ["Makefile"]
    # Behind is not invalid: the project's own gate is still green.
    assert rows["pins"]["status"] == "ok"
    assert rows["manifest"]["status"] == "ok"


# --- a leg that is not at its pin ------------------------------------------

def test_a_leg_off_its_pin_is_a_finding_that_names_a_submodule_update(
        standard, project):
    """A commit made INSIDE a mount, which is how a leg walks off its pin.

    The gitlink in the superproject's index is untouched, so
    `validate-pins.py` is still green — it reads what the next commit would
    RECORD — and the only thing that can notice is a tool that looks at the
    mount's HEAD. That is this row, and its exit is `git submodule update`,
    which puts the leg back AT the gitlink, which is the pin. It names no
    script of the root's: `scripts/bootstrap.py` may be what is missing, and
    never moved an existing branch (#276; `test_doctor_legs_members_next.py`
    pastes the line).
    """
    leg = project / "spec"
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m",
                    "work in the leg, past the pin"], cwd=str(leg),
                   capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    result = doctor(standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith("DRIFTED ("), result.stdout
    assert "leg(s) not at the pin" in verdict_line(result), result.stdout
    assert "submodule update --init --recursive" in result.stdout, (
        "the row must name the command that puts the leg back at its pin")
    assert "bootstrap.py" not in result.stdout, (
        "and no script the root may lack (#276)")
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["legs"]["status"] == "FINDING"
    assert rows["pins"]["status"] == "ok", (
        "the gitlink did not move, so the lockstep validator is right to be "
        "green; this is exactly the gap the legs row closes")
    spec = [leg for leg in rows["legs"]["detail"]["legs"]
            if leg["role"] == "spec"][0]
    assert spec["head"] != spec["pin"]
    assert spec["populated"] is True


def test_an_unbootstrapped_mount_is_a_finding(standard, project):
    """An empty mount: a clone nobody passed `--recurse-submodules`."""
    rmtree(project / "code")
    (project / "code").mkdir()
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["legs"]["status"] == "FINDING"
    assert "unbootstrapped clone" in rows["legs"]["reason"]
    # `bootstrap.py` never initialises a mount (it prints `NOT INITIALIZED`
    # and stops), so the line is the submodule update that does (#276).
    assert "submodule update --init --recursive --checkout -- code" in \
        (rows["legs"]["next"] or ""), rows["legs"]["next"]
    assert "bootstrap.py" not in (rows["legs"]["next"] or "")


# --- a manifest kind nothing validates -------------------------------------

def test_a_contract_of_an_unregistered_kind_is_a_finding(standard, project):
    """The registry is what makes an unvalidated manifest visible.

    A `contracts/*.yaml` that declares a `kind:` no validator is registered
    for used to be invisible — nothing walked the directory — and "we did not
    notice it was there" is how a manifest ends up governed by nobody. A file
    with NO `kind:` stays invisible on purpose: that is somebody's data, not
    a manifest, and reporting it would be this tool policing a tree it does
    not own.
    """
    contracts = project / "contracts"
    (contracts / "inventory.yaml").write_text(
        "schema_version: 1\nkind: service-inventory\nservices: []\n",
        encoding="utf-8")
    (contracts / "notes.yaml").write_text("colour: blue\n", encoding="utf-8")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["manifest-kinds"]["status"] == "FINDING"
    assert rows["manifest-kinds"]["detail"]["unregistered"] == \
        ["contracts/inventory.yaml (service-inventory)"]
    assert "no validator registered for kind" in \
        rows["manifest-kinds"]["reason"]
    assert "notes.yaml" not in rows["manifest-kinds"]["reason"], (
        "a YAML file with no `kind:` is not a manifest and is nobody's "
        "business here")
    # Every kind the standard DOES ship is registered, which is the other
    # half: a project's own `contracts/` must not be a finding out of the box.
    assert set(rows["manifest-kinds"]["detail"]["registered_kinds"]) >= {
        "project-manifest", "family-manifest", "pinned_contract_manifest"}


# --- a family holder --------------------------------------------------------

@pytest.fixture(scope="session")
def holder(standard, tmp_path_factory) -> dict:
    """A family holder with one member, built from the same standard."""
    base = tmp_path_factory.mktemp("family")
    scaffold(standard, base, FAMILY_MEMBER, org=FAMILY_NAME)
    created = run_script(
        standard / "scripts" / "family.py", "init", "--org", FAMILY_NAME,
        "--family", FAMILY_NAME, "--created-by", "Test Human",
        "--created-on", "2026-09-10",
        "--local-remote-dir", str(base / "remotes"),
        "--work-dir", str(base / "fam"))
    assert created.returncode == 0, created.stderr + created.stdout
    root = base / "fam" / FAMILY_NAME
    # On a branch, as `add` requires: it refuses the tracking branch (#487).
    git("switch", "-q", "-c", "family/members", cwd=root)
    added = run_script(standard / "scripts" / "family.py", "add",
                       "--family-root", str(root),
                       "--member", f"{FAMILY_NAME}/{FAMILY_MEMBER}",
                       "--local-remote-dir", str(base / "remotes"))
    assert added.returncode == 0, added.stderr + added.stdout
    return {"base": base, "root": root}


@pytest.fixture(scope="module")
def siblings():
    """The HOLDER's `scripts/siblings.py`, for the definition of "same
    repository" this file's `members` row has to agree with.

    THE SAME LOAD `tests/test_windows_paths.py` DOES, and for the same
    reason: the filename is fine but the module imports `bootstrap`, which
    sits beside it in a materialized holder and nowhere on `sys.path` here,
    so it is pre-registered under that name and `sys.modules` is put back
    afterwards. Loading the template rather than re-typing its rules is the
    whole point — a copy of the rule in this file could not detect drift in
    the file it was copied from.
    """
    scripts = REPO / "templates" / "family-root" / "scripts"
    saved_path, saved_module = list(sys.path), sys.modules.get("bootstrap")
    try:
        sys.modules["bootstrap"] = load_without_bytecode(
            scripts / "bootstrap.py", "doctor_family_bootstrap")
        yield load_without_bytecode(scripts / "siblings.py",
                                    "doctor_family_siblings")
    finally:
        sys.path[:] = saved_path
        if saved_module is None:
            sys.modules.pop("bootstrap", None)
        else:
            sys.modules["bootstrap"] = saved_module


def test_a_family_holder_gets_the_family_rows(standard, holder):
    """A holder is a different set of questions, read from the tree.

    No legs and no `project.yaml`, so no `pins` row and no `naming` row —
    `validate-family.py` is the whole of a holder's gate and asks the naming
    policy its one question itself. What it gains is `members`.
    """
    result = doctor(standard, holder["root"], "--json")
    payload = json.loads(result.stdout)
    assert payload["kind"] == "family"
    rows = rows_of(result)
    assert set(rows) == {"family", "manifest-kinds", "shape-currency",
                         "placement", "agent-files", "members", "machine"}
    # A holder has no legs of its own, so it has no leg for a path to be in
    # the wrong one of. `n/a` rather than absent: a caller keying on row ids
    # reads the same set of ids from every root kind that HAS the question,
    # and gets told this one does not.
    assert rows["placement"]["status"] == "n/a", rows["placement"]
    assert "each member is an assembly root" in rows["placement"]["reason"]
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["verdict"] == "COMPLIANT"
    assert rows["family"]["status"] == "ok"
    assert rows["family"]["detail"]["own_copy"] is True
    members = rows["members"]["detail"]["members"]
    assert [row["project"] for row in members] == [FAMILY_MEMBER]
    assert members[0]["head"] == members[0]["pin"]
    # No working clone beside the holder is the ordinary state of a fresh
    # one, and `make siblings` is what places them. It is REPORTED and is not
    # a finding: the gate reads `members/<Project>`, which is there.
    assert rows["members"]["status"] == "ok"
    assert "make siblings" in rows["members"]["reason"]
    assert rows["members"]["detail"]["without_working_clone"] == \
        [FAMILY_MEMBER]


# --- a family.yaml beside project.yaml (#211) -------------------------------
#
# `Context` reads ONE manifest per root and `project.yaml` wins, so a
# `family.yaml` committed beside it -- hand-copied or mis-merged; no tool here
# writes both -- was listed among the manifests whose kind "has a registered
# validator", and the root was COMPLIANT, exit 0. That validator,
# `validate-family.py`, never runs on an assembly root, and run there by hand
# it refuses the same tree.


#: The words the `manifest kinds` row opens with for a holder's one-member
#: `family.yaml` beside an assembly root's `project.yaml`, spelt out here and
#: not imported from the doctor: a test that read the wording back from the
#: thing under test would pass whatever it said.
FAMILY_BESIDE_OPENING = (
    "family.yaml (family-manifest) sits beside project.yaml "
    "(project-manifest), and validate-family.py, the validator that kind is "
    "registered to, never runs on an assembly root -- a family holder is not "
    "a project -- so nothing checks the 1 member(s) it pins")

#: The row's other way out, the last sentence of its `why` (#548): it was the
#: NEXT, and its backticks ran `family.py init` and `family.py add` where the
#: line was pasted into zsh. NOT `family.py add` here, which is what
#: `validate-family.py`'s own refusal offers: run in an assembly root it
#: would mount the members inside a project.
FAMILY_BESIDE_WAY = (
    "Or move the membership family.yaml records to a holder of its own "
    "(`family.py init`, then `family.py add` there), as the human decides -- "
    "never `family.py add` here, which would mount the members inside a "
    "project")

#: What the `why` says first where the NEXT is a `git rm` of `names`.
TAKES_OUT = ("takes {names} out of this root: commit that on a branch and "
             "land it as a pull request")

#: The `manifest kinds` row's `--json` keys before #211, which every root
#: without a family.yaml beside its project.yaml must still get exactly.
MANIFEST_KINDS_DETAIL_KEYS = {"validated", "unregistered", "unreadable",
                              "registered_kinds"}

#: The other way out for the suite's `contracts/inventory.yaml`, which was
#: the NEXT an unregistered kind carried, less the removal (#548).
UNREGISTERED_WAY = ("Or register the kind contracts/inventory.yaml declares "
                    "in shape-doctor.py's MANIFEST_VALIDATORS, beside the "
                    "check that validates it, as the human decides")

def removal_command(payload: dict, verb: str, names: list) -> str:
    """The NEXT that takes `names` out of the root a `--json` run reports
    on, or shows them: `git -C <root> <verb> -- <names>`, every value
    spelled by the doctor's own `quote_arg`, as the reader's shell hands it
    back (#548)."""
    module = doctor_module(REPO)
    return (f"git -C {module.quote_arg(Path(payload['root']))} {verb} -- "
            + " ".join(module.quote_arg(name) for name in names))


#: The suite's manifest of a kind nothing registers, as the row names it.
INVENTORY = ["contracts/inventory.yaml"]

#: The NEXT for files git does not track: it shows them, and never deletes
#: them, which no history could undo (review of PR #555).
SHOW_UNTRACKED = "status --ignored"


def shown_untracked(payload: dict, names: list, ignored: bool = False) -> str:
    """What the `why` says first where the NEXT shows `names`, which git does
    not track: that deleting them cannot be undone, and the `git clean`
    that does it, for a person to run (review of PR #555). The command
    follows a colon and is in no backticks, which a shell the sentence was
    pasted into whole would run (round 2)."""
    them = "it" if len(names) == 1 else "them"
    clean = removal_command(payload, "clean -f -x" if ignored else "clean -f",
                            names)
    return (f"shows {', '.join(names)}, which git does not track: no commit "
            f"holds {them}, so deleting {them} cannot be undone and is a "
            f"person's act, never this row's, with nothing to commit after. "
            f"A person deletes {them} with: {clean}")


def family_beside(project: Path, holder: dict) -> str:
    """Commit the holder's `family.yaml` into an assembly root, beside its
    `project.yaml` -- the hand copy #211 was filed about -- and return the
    40-hex commit it pins its one member at, read out of the file itself."""
    shutil.copy2(holder["root"] / "family.yaml", project / "family.yaml")
    commit_all(project, "A hand-copied family.yaml")
    [row] = repo_shape.load_yaml(project / "family.yaml")["members"]
    assert row["project"] == FAMILY_MEMBER, row
    return str(row["pin"]["commit"])


def record_gitlink(root: Path, path: str, commit: str) -> None:
    """A gitlink at `path` in the root's INDEX, at `commit`, and nothing else.

    `stage_gitlink` below does this in a leg at the leg's own HEAD; here the
    commit is the argument, because whether it equals the pin is the question.
    The index is what `recorded_gitlink` asks first and what `ls-files` lists,
    so no commit and no working tree under it are needed.
    """
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{path}",
        cwd=root)


def beside_row(result) -> dict:
    """The `manifest kinds` row of a `--json` run, asserted to be the #211
    finding and to be the only row that is. Its NEXT takes the committed
    `family.yaml` out of the root, and its `why` says so and names the
    other way out (#548)."""
    rows = rows_of(result)
    row = rows["manifest-kinds"]
    assert row["status"] == "FINDING", row
    assert row["reason"].startswith(FAMILY_BESIDE_OPENING), row["reason"]
    assert row["next"] == removal_command(json.loads(result.stdout), "rm",
                                          ["family.yaml"]), row["next"]
    assert row["why"] == (TAKES_OUT.format(names="family.yaml") + ". "
                          + FAMILY_BESIDE_WAY), row["why"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {
        "family_beside"}, row["detail"]
    validated = row["detail"]["validated"]
    assert "family.yaml (family-manifest)" not in validated, (
        "a manifest whose gate never runs here is not counted validated",
        validated)
    others = {name: other["status"] for name, other in rows.items()
              if other["status"] == "FINDING" and name != "manifest-kinds"}
    assert others == {}, others
    return row


def test_a_family_yaml_whose_members_are_all_at_their_pins_is_still_invalid(
        standard, project, holder):
    """DELIBERATELY A FINDING, even with every member recorded at its pin.

    A family holder is not a project -- no `project.yaml`, no legs (README,
    "Families"; AGENTS.md, "Creating a family") -- and the gate registered
    for `family-manifest`, `validate-family.py`, is run by the `family` check,
    which applies to a holder and to nothing else. So a root declaring both
    is a manifest travelling with no gate behind it: the case
    `check_manifest_kinds` exists to report, whether or not its rows happen
    to agree with the gitlinks today. The issue asked for no verdict better
    than INVALID, and this is it: the row says each member is at its pin,
    and still names the exit.
    """
    pinned = family_beside(project, holder)
    record_gitlink(project, f"members/{FAMILY_MEMBER}", pinned)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "project"
    assert payload["verdict"] == "INVALID (manifest-kinds)", payload["verdict"]
    row = beside_row(result)
    assert row["reason"] == (FAMILY_BESIDE_OPENING
                             + ", though each is recorded at its pin today")
    assert row["detail"]["family_beside"] == {
        "manifest": "family.yaml",
        "members": [{"project": FAMILY_MEMBER,
                     "path": f"members/{FAMILY_MEMBER}", "pin": pinned,
                     "gitlink": pinned, "state": "at-pin"}],
        "undeclared_gitlinks": []}
    text = doctor(standard, project)
    assert text.returncode == 1, text.stdout + text.stderr
    assert verdict_line(text).startswith(
        "INVALID (manifest-kinds)   (exit 1)"), text.stdout


def test_a_family_yaml_whose_member_has_no_gitlink_names_it(standard,
                                                            project, holder):
    """THE DEFECT #211 WAS FILED FOR: a member pinned and not mounted.

    `validate-family.py` refuses this tree `member-gitlink-absent`, exit 2;
    the doctor said COMPLIANT, exit 0, and listed `family.yaml` among the
    manifests whose kind has a registered validator. It names the member and
    the mode now, and the verdict is INVALID.
    """
    pinned = family_beside(project, holder)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (manifest-kinds)"
    row = beside_row(result)
    assert row["reason"] == (
        f"{FAMILY_BESIDE_OPENING}: members/{FAMILY_MEMBER} has no gitlink "
        "(mode 160000)"), row["reason"]
    [entry] = row["detail"]["family_beside"]["members"]
    assert entry == {"project": FAMILY_MEMBER,
                     "path": f"members/{FAMILY_MEMBER}", "pin": pinned,
                     "gitlink": None, "state": "no-gitlink"}, entry


def test_a_family_yaml_whose_member_is_off_its_pin_names_both_commits(
        standard, project, holder):
    """A gitlink at a commit the row does not pin: `validate-family.py`'s
    `member-gitlink-mismatch`, said here with both commits."""
    pinned = family_beside(project, holder)
    elsewhere = git("rev-parse", "HEAD", cwd=project).stdout.strip().lower()
    assert elsewhere != pinned, "fixture: a commit that is not the pin"
    record_gitlink(project, f"members/{FAMILY_MEMBER}", elsewhere)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (manifest-kinds)"
    row = beside_row(result)
    assert row["reason"] == (
        f"{FAMILY_BESIDE_OPENING}: members/{FAMILY_MEMBER} records gitlink "
        f"{elsewhere[:12]} where family.yaml pins {pinned[:12]}"), \
        row["reason"]
    [entry] = row["detail"]["family_beside"]["members"]
    assert (entry["gitlink"], entry["pin"], entry["state"]) == (
        elsewhere, pinned, "off-pin"), entry


def test_a_family_yaml_whose_pin_is_not_40_hex_says_so(standard, project,
                                                       holder):
    """A `pin.commit` that is a branch name is not a commit to compare a
    gitlink against, so the row says the pin is missing rather than calling
    the member off it -- the reading `member_state` gives a holder's row."""
    pinned = family_beside(project, holder)
    manifest = project / "family.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        pinned, "main"), encoding="utf-8")
    commit_all(project, "A pin that is a branch name")
    # AFTER the commit: `git add -A` would stage a gitlink with no working
    # tree under it as a deletion.
    record_gitlink(project, f"members/{FAMILY_MEMBER}", pinned)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (manifest-kinds)"
    row = beside_row(result)
    assert row["reason"] == (
        f"{FAMILY_BESIDE_OPENING}: {FAMILY_MEMBER}'s row carries no 40-hex "
        "`pin.commit` to compare against"), row["reason"]
    [entry] = row["detail"]["family_beside"]["members"]
    assert (entry["gitlink"], entry["pin"], entry["state"]) == (
        pinned, None, "no-pin"), entry


def test_a_gitlink_under_members_that_no_row_names_is_named(standard,
                                                            project, holder):
    """The state `family.py add` refuses to mount over (`member-path-taken`):
    a submodule under the members directory that the manifest says nothing
    about. The member the row DOES name is at its pin, so the stray is the
    whole of what the sentence lists."""
    pinned = family_beside(project, holder)
    record_gitlink(project, f"members/{FAMILY_MEMBER}", pinned)
    record_gitlink(project, "members/Stray", pinned)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (manifest-kinds)"
    row = beside_row(result)
    assert row["reason"] == (
        f"{FAMILY_BESIDE_OPENING}: members/Stray is a gitlink no family.yaml "
        "row names"), row["reason"]
    beside = row["detail"]["family_beside"]
    assert beside["undeclared_gitlinks"] == ["members/Stray"], beside
    assert [entry["state"] for entry in beside["members"]] == ["at-pin"]


def test_the_text_report_and_json_carry_the_same_family_beside_row(
        standard, project, holder):
    """`--json` is the same report as one object: the row's reason and its
    next command are printed verbatim in the table, under the same label,
    and the verdict line is the JSON's verdict."""
    family_beside(project, holder)
    result = doctor(standard, project, "--json")
    payload = json.loads(result.stdout)
    row = beside_row(result)
    text = doctor(standard, project)
    assert text.returncode == payload["exit"] == 1
    lines = text.stdout.splitlines()
    [at] = [index for index, line in enumerate(lines)
            if "manifest kinds" in line]
    assert lines[at].split()[:3] == ["FINDING", "manifest", "kinds"], \
        lines[at]
    assert lines[at].endswith("  " + row["reason"]), lines[at]
    assert lines[at + 1].split()[0] == "NEXT", lines[at + 1]
    assert lines[at + 1].endswith("  " + row["next"]), lines[at + 1]
    assert lines[at + 2].split()[0] == "WHY", lines[at + 2]
    assert lines[at + 2].endswith("  " + row["why"]), lines[at + 2]
    assert verdict_line(text) == f"{payload['verdict']}   (exit 1)"


def write_inventory(root: Path) -> None:
    """The suite's manifest of a kind nothing registers, uncommitted."""
    (root / "contracts" / "inventory.yaml").write_bytes(
        b"schema_version: 1\nkind: service-inventory\nservices: []\n")


def test_a_family_yaml_beside_an_unregistered_kind_says_both(
        standard, project, holder):
    """Two reasons in one row, in the order the row has always listed them:
    the unregistered kind first. ONE command, not the two exits joined by
    `; ` (#548): the `git rm` of the committed `family.yaml`, and the `why`
    names the file that comes out another way and each fault's other way
    out. Run as printed, the next run names the untracked file's command,
    and run as printed that is COMPLIANT."""
    family_beside(project, holder)
    write_inventory(project)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["manifest-kinds"]
    assert row["status"] == "FINDING", row
    assert row["reason"] == (
        "no validator registered for kind contracts/inventory.yaml "
        f"(service-inventory); {FAMILY_BESIDE_OPENING}: "
        f"members/{FAMILY_MEMBER} has no gitlink (mode 160000)"), \
        row["reason"]
    payload = json.loads(result.stdout)
    assert row["next"] == removal_command(payload, "rm", ["family.yaml"]), \
        row["next"]
    assert row["why"] == (
        TAKES_OUT.format(names="family.yaml") + ". The next run names the "
        f"way out for contracts/inventory.yaml. {UNREGISTERED_WAY}. "
        f"{FAMILY_BESIDE_WAY}"), row["why"]
    assert row["detail"]["unregistered"] == [
        "contracts/inventory.yaml (service-inventory)"]

    run_pasted(row["next"])
    # What `git rm` staged and nothing else: the untracked file stays so.
    commit_in(project, "Take the family.yaml beside project.yaml out")
    again = doctor(standard, project, "--json")
    row = only_finding_is_manifest_kinds(again)
    payload = json.loads(again.stdout)
    assert row["next"] == removal_command(payload, SHOW_UNTRACKED,
                                          INVENTORY), row
    assert row["why"] == (shown_untracked(payload, INVENTORY) + ". "
                          + UNREGISTERED_WAY), row
    run_pasted(row["next"])
    assert (project / INVENTORY[0]).is_file()
    # The deletion the `why` names, as a person would run it.
    run_pasted(removal_command(payload, "clean -f", INVENTORY))
    compliant_again(standard, project)


def test_a_root_with_no_family_yaml_beside_gets_the_row_it_always_got(
        standard, project, holder):
    """NOTHING CHANGES WITHOUT A family.yaml BESIDE project.yaml, byte for
    byte: an assembly root, the same root with an unregistered kind, and a
    family holder -- whose own `family.yaml` is the manifest its `family`
    row validates, and stays `validated` here. The row's detail carries
    exactly the keys it carried, and the sentences are the ones it printed.
    The unregistered kind's NEXT alone is new (#548): a command, where it
    was the sentence its `why` now ends with.
    """
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["status"] == "ok", row
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS, row["detail"]
    assert row["reason"] == (
        f"{len(row['detail']['validated'])} manifest(s), every declared kind "
        "has a registered validator"), row["reason"]
    assert row["next"] is None
    assert "family" not in json.dumps(row["detail"]["validated"]), row

    write_inventory(project)
    result = doctor(standard, project, "--json")
    row = rows_of(result)["manifest-kinds"]
    assert row["status"] == "FINDING", row
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS, row["detail"]
    assert row["reason"] == ("no validator registered for kind "
                             "contracts/inventory.yaml (service-inventory)")
    payload = json.loads(result.stdout)
    assert row["next"] == removal_command(payload, SHOW_UNTRACKED,
                                          INVENTORY), row
    assert row["why"] == (shown_untracked(payload, INVENTORY) + ". "
                          + UNREGISTERED_WAY), row

    result = doctor(standard, holder["root"], "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    row = rows_of(result)["manifest-kinds"]
    assert row["status"] == "ok", row
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS, row["detail"]
    assert "family.yaml (family-manifest)" in row["detail"]["validated"], row


# --- a registered kind in a root that never runs its gate (#327) ------------
#
# #211 acted on ONE path: `family.yaml` at the top of an assembly root. Any
# other file declaring a registered kind was still counted `validated`
# wherever it sat, so a `contracts/family.yaml` in an assembly root and a
# `contracts/project.yaml` in a family holder were `ok` and COMPLIANT, exit
# 0, though the gate registered for each kind never runs on that kind of root.

#: The words the row's `why` closes with, spelt out here for the reason
#: `FAMILY_BESIDE_WAY` is: a test that read them back from the doctor would
#: pass whatever it said.
NEVER_RENAME = ("never rename it to project.yaml or family.yaml in this "
                "root: a family holder is not a project, and an assembly "
                "root is not a family holder")

#: Where each kind's manifest goes instead, as the `why` offers it.
FAMILY_HOME = ("a family holder of its own (`family.py init`, then "
               "`family.py add` there)")
#: `setup-project.py` beside `setup.sh`, on every OS: `setup.sh` is a bash
#: script, and a Windows reader has no bash to run it in.
PROJECT_HOME = ("an assembly root of its own (`setup.sh`, or "
                "`setup-project.py` on Windows, for a new one; "
                "`adopt-project.py plan` for a repository that exists), "
                "which a holder pins with `family.py add`")


def removal_named(row: dict, payload: dict, names: list) -> list:
    """The `git rm` a `manifest kinds` row's NEXT is, as the argv it is,
    after asserting the NEXT is exactly that command and nothing else (#548).

    The spelling is held to the doctor's own `quote_arg` -- the quoter whose
    two dialects the tests further down pin -- so the line is the one the
    reader's shell hands back whole, on Windows as on POSIX. Where the
    reader's shell IS POSIX `sh`, `shlex.split` reads the line back too.
    """
    assert row["next"] == removal_command(payload, "rm", names), row["next"]
    # Through `Path`: `--json` spells the root `as_posix()`, and the NEXT
    # spells it as the platform does.
    argv = ["git", "-C", str(Path(payload["root"])), "rm", "--", *names]
    assert pasted(row["next"]) == argv, row["next"]
    return argv


def run_the_removal(argv: list, root: Path) -> None:
    """Run the NEXT's own `git rm`, and commit it as its `why` says."""
    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    commit_all(root, "Take the manifest no gate here reads out of the root")


def only_finding_is_manifest_kinds(result) -> dict:
    rows = rows_of(result)
    others = {name: row["status"] for name, row in rows.items()
              if row["status"] == "FINDING" and name != "manifest-kinds"}
    assert others == {}, others
    return rows["manifest-kinds"]


def test_a_contracts_family_yaml_in_an_assembly_root_is_a_finding(
        standard, project, holder):
    """THE DEFECT #327 WAS FILED FOR, in an assembly root.

    The holder's own `family.yaml`, committed under the root's `contracts/`:
    it declares `family-manifest`, whose registered gate `validate-family.py`
    runs in a family holder and nowhere else. The doctor said `ok`, "every
    declared kind has a registered validator", COMPLIANT, exit 0. It is the
    FINDING the same bytes are at the top of the root (#211) now: not
    `validated`, named with the validator and where it runs, and a next
    command that exists -- run here, it puts the root back to COMPLIANT.
    The NEXT is that command alone, and the other way out is its `why`'s
    (#548).
    """
    shutil.copy2(holder["root"] / "family.yaml",
                 project / "contracts" / "family.yaml")
    commit_all(project, "A family manifest under contracts/")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"]) == (
        "project", "INVALID (manifest-kinds)"), payload
    row = only_finding_is_manifest_kinds(result)
    assert row["status"] == "FINDING", row
    assert row["reason"] == (
        "no validator that runs in an assembly root is registered for kind "
        "contracts/family.yaml (family-manifest: scripts/validate-family.py "
        "runs only in a family holder)"), row["reason"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {
        "registered_elsewhere"}, row["detail"]
    assert not any("contracts/family.yaml" in entry
                   for entry in row["detail"]["validated"]), row["detail"]
    assert row["detail"]["registered_elsewhere"] == [
        {"manifest": "contracts/family.yaml", "kind": "family-manifest",
         "validator": "scripts/validate-family.py", "runs_in": ["family"],
         "git": "committed"}]
    argv = removal_named(row, payload, ["contracts/family.yaml"])
    assert row["why"] == (
        TAKES_OUT.format(names="contracts/family.yaml") + ". Or move what "
        f"contracts/family.yaml describes to {FAMILY_HOME}, as the human "
        f"decides -- {NEVER_RENAME}"), row["why"]

    text = doctor(standard, project)
    assert text.returncode == 1, text.stdout + text.stderr
    lines = text.stdout.splitlines()
    [at] = [index for index, line in enumerate(lines)
            if "manifest kinds" in line]
    assert lines[at].split()[:3] == ["FINDING", "manifest", "kinds"], \
        lines[at]
    assert lines[at].endswith("  " + row["reason"]), lines[at]
    assert lines[at + 1].endswith("  " + row["next"]), lines[at + 1]
    assert lines[at + 2].endswith("  " + row["why"]), lines[at + 2]
    assert verdict_line(text) == "INVALID (manifest-kinds)   (exit 1)", \
        text.stdout

    run_the_removal(argv, project)
    after = doctor(standard, project, "--json")
    assert after.returncode == 0, after.stdout + after.stderr
    assert json.loads(after.stdout)["verdict"] == "COMPLIANT"


def test_a_contracts_project_yaml_in_a_family_holder_is_a_finding(
        standard, scaffolded_here, holder, tmp_path):
    """THE MIRROR CASE, in a family holder, which #220's review read from the
    code and #327 ran: an assembly root's `project.yaml` committed under the
    holder's `contracts/`. Its gate, `validate-manifest.py`, runs in an
    assembly root and nowhere else. The holder's own two contracts are still
    answered -- by `validate-family.py`, which reads the shape pin and the
    naming policy itself -- so they stay `validated`, and only this file is
    named."""
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    shutil.copy2(scaffolded_here["clone"] / "project.yaml",
                 root / "contracts" / "project.yaml")
    commit_all(root, "A project manifest under contracts/")
    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"]) == (
        "family", "INVALID (manifest-kinds)"), payload
    row = only_finding_is_manifest_kinds(result)
    assert row["status"] == "FINDING", row
    assert row["reason"] == (
        "no validator that runs in a family holder is registered for kind "
        "contracts/project.yaml (project-manifest: "
        "scripts/validate-manifest.py runs only in an assembly root)"), \
        row["reason"]
    assert row["detail"]["registered_elsewhere"] == [
        {"manifest": "contracts/project.yaml", "kind": "project-manifest",
         "validator": "scripts/validate-manifest.py", "runs_in": ["project"],
         "git": "committed"}]
    assert sorted(row["detail"]["validated"]) == [
        "contracts/repository-naming.yaml (repository-naming-policy)",
        "contracts/shape-pin.yaml (pinned_contract_manifest)",
        "family.yaml (family-manifest)"], row["detail"]
    argv = removal_named(row, payload, ["contracts/project.yaml"])
    assert row["why"].endswith(
        f". Or move what contracts/project.yaml describes to {PROJECT_HOME}, "
        f"as the human decides -- {NEVER_RENAME}"), row["why"]

    run_the_removal(argv, root)
    after = doctor(standard, root, "--json")
    assert after.returncode == 0, after.stdout + after.stderr
    assert json.loads(after.stdout)["verdict"] == "COMPLIANT"


def test_a_contracts_family_yaml_and_one_beside_project_yaml_say_both(
        standard, project, holder):
    """Two family manifests in one assembly root, one under `contracts/` and
    one at the top: two reasons in one row, the general one first and
    #211's -- which also checks the members -- after it, and ONE `git rm`
    that takes both out, with each one's other way out in the `why` (#548).
    Neither is counted `validated`."""
    shutil.copy2(holder["root"] / "family.yaml",
                 project / "contracts" / "family.yaml")
    family_beside(project, holder)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "INVALID (manifest-kinds)"
    row = only_finding_is_manifest_kinds(result)
    assert row["reason"] == (
        "no validator that runs in an assembly root is registered for kind "
        "contracts/family.yaml (family-manifest: scripts/validate-family.py "
        f"runs only in a family holder); {FAMILY_BESIDE_OPENING}: "
        f"members/{FAMILY_MEMBER} has no gitlink (mode 160000)"), \
        row["reason"]
    removal_named(row, json.loads(result.stdout),
                  ["contracts/family.yaml", "family.yaml"])
    assert row["why"].endswith(f"{NEVER_RENAME}. {FAMILY_BESIDE_WAY}"), \
        row["why"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {
        "registered_elsewhere", "family_beside"}, row["detail"]
    assert not any("family" in entry for entry in row["detail"]["validated"])


# --- the NEXT, for the file as git has it (#327, review of PR #375) ---------
#
# The doctor reads the disk, and `git rm` takes out only a file a commit
# holds whole. The NEXT named it for every file, and it said "did not match
# any files" (exit 128) for one git does not track, ignored or not, and
# refused one with changes no commit holds. Each state has its own command
# now, and the NEXT is that command alone (#548).

def plant_family_yaml(project: Path, holder: dict,
                      name: str = "family.yaml") -> Path:
    """The holder's `family.yaml`, copied under the root's `contracts/` as
    `name`, and nothing committed."""
    planted = project / "contracts" / name
    shutil.copy2(holder["root"] / "family.yaml", planted)
    return planted


def why_for_one(said: str) -> str:
    """The `why` for one `contracts/family.yaml`, opening with `said`."""
    return (f"{said}. Or move what contracts/family.yaml describes to "
            f"{FAMILY_HOME}, as the human decides -- {NEVER_RENAME}")


def git_rm_refuses(project: Path, planted: Path) -> None:
    """The `git rm` the NEXT used to name, run as it named it: it fails, and
    the file is still there."""
    proc = subprocess.run(
        ["git", "-C", str(project), "rm", "--",
         planted.relative_to(project).as_posix()],
        capture_output=True, text=True, check=False)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert planted.is_file()


@pytest.mark.parametrize("state", ["untracked", "ignored"])
def test_a_contracts_family_yaml_git_does_not_track_is_shown_not_deleted(
        standard, project, holder, state):
    """A `contracts/family.yaml` nobody has committed -- copied in and not
    added, or hidden by the root's own excludes -- is the same FINDING. Its
    NEXT is the `git status --ignored` that shows it, and never the deletion
    (review of PR #555): no commit holds it, so deleting it cannot be
    undone, and an agent runs the NEXT. The `why` names the `git clean -f`
    that deletes it, `-x` too where the excludes hide it, which `clean`
    otherwise leaves. It names no `git rm`, which fails on it. Run as
    printed, the NEXT leaves the file where it is; the `why`'s deletion, run
    as a person would, leaves the root COMPLIANT."""
    planted = plant_family_yaml(project, holder)
    if state == "ignored":
        exclude = project / git("rev-parse", "--git-path", "info/exclude",
                                cwd=project).stdout.strip()
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with open(exclude, "ab") as handle:
            handle.write(b"\ncontracts/family.yaml\n")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (manifest-kinds)", payload
    row = only_finding_is_manifest_kinds(result)
    names = ["contracts/family.yaml"]
    assert row["next"] == removal_command(payload, SHOW_UNTRACKED, names), \
        row
    assert row["why"] == why_for_one(
        shown_untracked(payload, names, state == "ignored")), row["why"]
    assert row["detail"]["registered_elsewhere"] == [
        {"manifest": "contracts/family.yaml", "kind": "family-manifest",
         "validator": "scripts/validate-family.py", "runs_in": ["family"],
         "git": state}]
    git_rm_refuses(project, planted)

    run_pasted(row["next"])
    assert planted.is_file(), "the NEXT deleted a file no commit holds"
    run_pasted(removal_command(
        payload, "clean -f -x" if state == "ignored" else "clean -f", names))
    assert not planted.exists()
    compliant_again(standard, project)


@pytest.mark.parametrize("state", ["edited", "staged"])
def test_a_contracts_family_yaml_with_changes_no_commit_holds(
        standard, project, holder, state):
    """Committed and then edited, or staged and never committed: `git rm`
    refuses both, because it will not discard changes no commit holds. The
    NEXT is the `git status` that shows them, the `why` says to commit or
    drop them, and the next run names the way out -- which, once they are
    committed, is the `git rm`, and running that is COMPLIANT again."""
    planted = plant_family_yaml(project, holder)
    if state == "edited":
        commit_all(project, "A family manifest under contracts/")
        with open(planted, "ab") as handle:
            handle.write(b"# an edit no commit holds\n")
    else:
        git("add", "--", "contracts/family.yaml", cwd=project)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (manifest-kinds)", payload
    row = only_finding_is_manifest_kinds(result)
    assert row["next"] == removal_command(payload, "status",
                                          ["contracts/family.yaml"]), row
    assert row["why"] == why_for_one(
        "shows the changes no commit holds in contracts/family.yaml, which "
        "git rm will not discard: commit or drop them, and the next run "
        "names the way out"), row["why"]
    assert [entry["git"] for entry in
            row["detail"]["registered_elsewhere"]] == ["changed"], row
    git_rm_refuses(project, planted)
    run_pasted(row["next"])

    commit_all(project, "Commit what the row said to commit first")
    again = doctor(standard, project, "--json")
    row = only_finding_is_manifest_kinds(again)
    argv = removal_named(row, json.loads(again.stdout),
                         ["contracts/family.yaml"])
    run_the_removal(argv, project)
    compliant_again(standard, project)


def test_manifests_that_come_out_differently_are_each_named(
        standard, project, holder):
    """Three family manifests under `contracts/` -- one committed, one git
    does not track, one edited since its commit -- get ONE command, the
    `git rm` of the committed one, and a `why` that names the other two for
    the next run, in the row's order (#548). It used to be one sentence
    with a way for each, three commands in backticks among them.

    AND THE DOCTOR ASKED GIT WITHOUT WRITING THE INDEX. The committed one is
    rewritten with its own bytes and a newer mtime, so its index entry is
    stat-dirty: a `git status` refreshes that entry and, without
    `--no-optional-locks`, writes `.git/index` back. It must stay byte for
    byte as it was, because the doctor writes nothing into the repository.
    """
    committed = plant_family_yaml(project, holder)
    edited = plant_family_yaml(project, holder, "x-family.yaml")
    commit_all(project, "Two family manifests under contracts/")
    with open(edited, "ab") as handle:
        handle.write(b"# an edit no commit holds\n")
    plant_family_yaml(project, holder, "old-family.yaml")
    committed.write_bytes(committed.read_bytes())
    stat = committed.stat()
    os.utime(committed, (stat.st_atime + 100, stat.st_mtime + 100))
    index = project / git("rev-parse", "--git-path", "index",
                          cwd=project).stdout.strip()
    before = index.read_bytes()

    result = doctor(standard, project, "--json")
    assert index.read_bytes() == before, "the doctor wrote the index"
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (manifest-kinds)", payload
    row = only_finding_is_manifest_kinds(result)
    removal_named(row, payload, ["contracts/family.yaml"])
    assert row["why"] == (
        TAKES_OUT.format(names="contracts/family.yaml") + ". The next run "
        "names the way out for contracts/old-family.yaml, "
        "contracts/x-family.yaml. Or move what contracts/family.yaml, "
        "contracts/old-family.yaml, contracts/x-family.yaml describe to "
        f"{FAMILY_HOME}, as the human decides -- never rename one to "
        "project.yaml or family.yaml in this root: a family holder is not a "
        "project, and an assembly root is not a family holder"), row["why"]
    assert [(entry["manifest"], entry["git"]) for entry in
            row["detail"]["registered_elsewhere"]] == [
        ("contracts/family.yaml", "committed"),
        ("contracts/old-family.yaml", "untracked"),
        ("contracts/x-family.yaml", "changed")], row["detail"]


#: Windows takes no `*` in a file name.
NO_STAR_IN_A_NAME = pytest.mark.skipif(
    os.name == "nt", reason="Windows takes no `*` in a file name")


@pytest.mark.parametrize("odd", [
    pytest.param("contracts/*-pin.yaml", id="every-pin",
                 marks=NO_STAR_IN_A_NAME),
    pytest.param("contracts/[s]hape-pin.yaml", id="the-shape-pin"),
])
def test_a_name_git_reads_as_a_pattern_is_passed_literally(standard, project,
                                                           odd):
    """A manifest of a kind nothing registers, committed under a name git's
    pathspec reads as a pattern: `contracts/*-pin.yaml` matches every pin in
    the root, `contracts/[s]hape-pin.yaml` the shape pin. The row's NEXT
    passes it after `--literal-pathspecs`, so run as printed it stages the
    removal of that file alone. Through the row, since a name that does not
    end `.yaml` is no candidate at all (review of PR #555); a name with no
    pattern in it is spelled as it always was."""
    module = doctor_module(standard)
    (project / odd).write_bytes(b"kind: service-inventory\n")
    commit_all(project, "a manifest named like a pattern")
    matched = git("ls-files", "-z", "--", odd, cwd=project).stdout
    assert len([name for name in matched.split("\0") if name]) > 1, matched
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["next"] == (f"git -C {module.quote_arg(project)} "
                           "--literal-pathspecs rm -- "
                           f"{module.quote_arg(odd)}"), row
    run_pasted(row["next"])
    staged = git("diff", "--cached", "--name-only", "-z", cwd=project).stdout
    assert [name for name in staged.split("\0") if name] == [odd], staged
    plain, _ = module.removal_next(SimpleNamespace(root=project),
                                   ["contracts/x.yaml"],
                                   {"contracts/x.yaml": "committed"})
    assert "--literal-pathspecs" not in plain, plain


def test_git_states_answers_only_in_a_repository_of_its_own(tmp_path):
    """`git -C` discovers. In a plain directory inside another repository,
    `status` answers about THAT repository, with paths relative to its top,
    so `contracts/family.yaml` was never listed, read as `committed`, and
    the NEXT named a `git rm` aimed at the enclosing repository. Now git is
    not asked there, and the row has no command at all: its `why` is #211's
    "take it out of this root", which holds in any state. Its own
    repository is asked."""
    module = doctor_module(REPO)
    outer = tmp_path / "outer"
    outer.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=outer)
    root = outer / PROJECT
    (root / "contracts").mkdir(parents=True)
    (root / "contracts" / "family.yaml").write_bytes(
        b"kind: family-manifest\n")
    names = ["contracts/family.yaml"]
    assert module.git_states(root, names) == {}
    assert module.removal_next(SimpleNamespace(root=root), names, {}) == (
        None, "take contracts/family.yaml out of this root")

    git("init", "-q", "-b", "main", ".", cwd=root)
    assert module.git_states(root, names) == {
        "contracts/family.yaml": "untracked"}


def test_a_registered_kind_is_answered_only_where_its_check_runs():
    """THE RULE, read straight off the registry (#327).

    A kind is answered on a kind of root only where a check it is
    `covered_by` APPLIES -- `CHECKS` says which, and nothing else does. So
    the two root manifests are answered each in its own kind of root and
    never in the other, and every kind a holder ships is answered there by
    `family`, which is what keeps a fresh holder COMPLIANT. Every check a
    kind names exists, or the kind would be answered nowhere at all.
    """
    module = doctor_module(REPO)
    runs = {kind: entry.runs_in()
            for kind, entry in module.MANIFEST_VALIDATORS.items()}
    assert runs == {
        "project-manifest": ("project",),
        "family-manifest": ("family",),
        "pinned_contract_manifest": ("project", "family"),
        "repository-naming-policy": ("project", "family"),
        "path-classification-policy": ("project", "family"),
    }, runs
    checks = {check.id for check in module.CHECKS}
    for kind, entry in module.MANIFEST_VALIDATORS.items():
        assert set(entry.covered_by) <= checks, (kind, entry.covered_by)


# --- a registered kind at a path no gate reads (#439) -----------------------
#
# #327 asked whether a kind's check RUNS on this kind of root, and not whether
# it READS the file's path, though every gate opens fixed paths. So each file
# below was `validated`, and its root COMPLIANT, exit 0, though nothing read
# it. Brett Heap ruled it on 2026-10-12: "#439 (registered kind at a path no
# check reads): FINDING".

#: A pin no leg and no product names, as #439 measured one.
STRAY_PIN = b"kind: pinned_contract_manifest\ncommit: not-a-commit\n"

#: #439's five files, each with the kind of root it is put in, its kind, its
#: bytes, and the paths a gate in that root reads the kind at. Spelt out here
#: for the reason `FAMILY_BESIDE_WAY` is.
READ_NOWHERE = {
    "contracts-project-yaml": (
        "project", "contracts/project.yaml", "project-manifest",
        b'kind: project-manifest\nid: "007"\n', ["project.yaml"]),
    "a-pin-nothing-declares": (
        "project", "contracts/release-pin.yaml", "pinned_contract_manifest",
        STRAY_PIN, ["contracts/code-pin.yaml", "contracts/shape-pin.yaml",
                    "contracts/spec-pin.yaml"]),
    "an-old-naming-policy": (
        "project", "contracts/naming-old.yaml", "repository-naming-policy",
        b"kind: repository-naming-policy\nforms: 7\n",
        ["contracts/repository-naming.yaml"]),
    "contracts-family-yaml-in-a-holder": (
        "family", "contracts/family.yaml", "family-manifest",
        b"kind: family-manifest\nmembers:\n  - project: Ghost\n",
        ["family.yaml"]),
    "a-leg-pin-in-a-holder": (
        "family", "contracts/spec-pin.yaml", "pinned_contract_manifest",
        STRAY_PIN, ["contracts/shape-pin.yaml"]),
}

#: The one other way out a pin in an assembly root has, and only it.
DECLARE_IT = ("the human names that product under `neutral_product_pins:` "
              "in project.yaml -- and nobody declares a pin the human has "
              "not asked for")


@pytest.mark.parametrize("case", list(READ_NOWHERE))
def test_a_registered_kind_at_a_path_no_gate_reads_is_a_finding(
        standard, project, holder, tmp_path, case):
    """Each of #439's files, committed in a root that was COMPLIANT: a
    FINDING naming the path, the kind and where a gate here reads that kind,
    listed under `unread` and never `validated`, and INVALID, exit 1.

    THE NEXT TAKES THE FILE OUT AS GIT HAS IT (the issue's direction), one
    command and nothing else (#548): run as printed, the root is COMPLIANT
    again. The `why` never suggests renaming the file onto a path a gate
    reads, and only the pin in an assembly root is offered the other way
    out, the human declaring the product it pins -- which the row never does
    itself.
    """
    where, rel, kind, body, read_at = READ_NOWHERE[case]
    root = project
    if where == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
    (root / rel).write_bytes(body)
    commit_all(root, f"{rel}, which no gate reads")
    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"]) == (
        where, "INVALID (manifest-kinds)"), payload
    row = only_finding_is_manifest_kinds(result)
    assert row["reason"] == (
        f"no gate here reads {rel} ({kind}, which a gate here reads only at "
        f"{', '.join(read_at)})"), row["reason"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {"unread"}, \
        row["detail"]
    assert row["detail"]["unread"] == [
        {"manifest": rel, "kind": kind, "read_at": read_at,
         "git": "committed"}], row["detail"]
    assert f"{rel} ({kind})" not in row["detail"]["validated"], row
    argv = removal_named(row, payload, [rel])
    assert row["why"].startswith(TAKES_OUT.format(names=rel) + ". "), row
    assert row["why"].endswith(
        ". Never rename it onto a path a gate here reads"), row["why"]
    assert (DECLARE_IT in row["why"]) == (
        case == "a-pin-nothing-declares"), row["why"]

    run_the_removal(argv, root)
    compliant_again(standard, root)


def test_each_kind_is_read_at_the_paths_its_gate_opens(standard, project,
                                                       holder):
    """THE TABLE #439 READS, off the registry: where the check that runs on
    each kind of root reads each kind. `validate-manifest.py` reads the
    root's `project.yaml` and the naming policy, `validate-pins.py` the shape
    pin and the two leg pins `project.yaml` declares, and `validate-family.py`
    the holder's `family.yaml`, the shape pin and the naming policy. The
    path policy is not decided by path, as before."""
    module = doctor_module(standard)

    def read_at(root: Path) -> dict:
        ctx = module.Context(root.resolve())
        return {kind: entry.reads(ctx)
                for kind, entry in module.MANIFEST_VALIDATORS.items()}

    both = {"project-manifest": {"project.yaml"},
            "family-manifest": {"family.yaml"},
            "repository-naming-policy": {"contracts/repository-naming.yaml"},
            "path-classification-policy": None}
    assert read_at(project) == {**both, "pinned_contract_manifest": {
        "contracts/code-pin.yaml", "contracts/shape-pin.yaml",
        "contracts/spec-pin.yaml"}}
    assert read_at(holder["root"]) == {
        **both, "pinned_contract_manifest": {"contracts/shape-pin.yaml"}}


def test_a_pin_a_gate_reads_stays_validated_by_any_name_it_has(standard,
                                                                project):
    """The other side of #439: what a gate here reads is `validated`, as it
    was, and the row says nothing new about it.

    A FILE IS READ BY ANY NAME IT HAS. A hard link to a leg pin is that pin.
    A leg pin spelled in another case is the pin `validate-pins.py` opens
    where the filesystem folds case, and is read by nothing where it does
    not: a NEXT taking it out on the first would take out a pin.

    A NEUTRAL PRODUCT PIN IS READ WHILE `project.yaml` DECLARES IT, and read
    by nothing once the declaration is gone, when the human declaring it is
    the other way out. And while `project.yaml` does not load it declares
    nothing this run can read, so no pin is called read by nothing: the
    `manifest` row names that file.

    IN PROCESS, through the row alone, as `declare_a_neutral_pin`'s other
    caller is: a declared neutral pin makes the `pins` row recheck its
    digest, which asks `gh`.
    """
    module = doctor_module(standard)

    def kinds() -> dict:
        row = module.check_manifest_kinds(module.Context(project)).as_dict()
        assert_next_holds_no_prose(row)
        return row

    pins = project / "contracts"
    spec = pins / "spec-pin.yaml"
    os.link(spec, pins / "linked-pin.yaml")
    row = kinds()
    assert row["status"] == "ok", row
    assert "contracts/linked-pin.yaml (pinned_contract_manifest)" in \
        row["detail"]["validated"], row
    (pins / "linked-pin.yaml").unlink()

    spec.rename(pins / "Spec-Pin.yaml")
    folds = spec.exists()
    row = kinds()
    named = "contracts/Spec-Pin.yaml"
    if folds:
        assert f"{named} (pinned_contract_manifest)" in \
            row["detail"]["validated"], row
    else:
        assert [entry["manifest"] for entry in row["detail"]["unread"]] == [
            named], row
    (pins / "Spec-Pin.yaml").rename(spec)

    declare_a_neutral_pin(project)
    neutral = project / NEUTRAL_PIN
    neutral.write_bytes(b"kind: pinned_contract_manifest\n"
                        + neutral.read_bytes())
    row = kinds()
    assert row["status"] == "ok", row
    assert f"{NEUTRAL_PIN} (pinned_contract_manifest)" in \
        row["detail"]["validated"], row
    manifest = project / "project.yaml"
    manifest.write_bytes(manifest.read_bytes().replace(
        b"neutral_product_pins:\n  - openGlass\n",
        b"neutral_product_pins: []\n"))
    row = kinds()
    assert [entry["manifest"] for entry in row["detail"]["unread"]] == [
        NEUTRAL_PIN], row
    assert DECLARE_IT in row["why"], row["why"]

    edit, code = BREAKAGES["tab-indent"]
    break_manifest(manifest, edit, code)
    row = kinds()
    assert row["status"] == "ok", row
    assert "unread" not in row["detail"], row
    for pin in (NEUTRAL_PIN, SPEC_PIN, CODE_PIN):
        assert f"{pin} (pinned_contract_manifest)" in \
            row["detail"]["validated"], (pin, row)


#: The review of PR #555's two roots: a file a gate reads, with the fault
#: somewhere else -- a typo in a leg's role, or a wrong `kind:` in the naming
#: policy -- as the file edited, the bytes before and after, the file the
#: `manifest kinds` row must still count `validated`, and the code the
#: `manifest` row names. Main said `manifest kinds ok` over both; the row
#: then called the spec leg's pin, and the naming policy, read by nothing,
#: and its NEXT took each out.
FAULT_ELSEWHERE = {
    "a-leg-role-typo": (
        "project.yaml", b"  - role: spec\n", b"  - role: specs\n",
        "contracts/spec-pin.yaml (pinned_contract_manifest)",
        "manifest-roles"),
    "a-wrong-kind-where-a-gate-reads": (
        "contracts/repository-naming.yaml",
        b"kind: repository-naming-policy\n",
        b"kind: pinned_contract_manifest\n",
        "contracts/repository-naming.yaml (pinned_contract_manifest)",
        "policy-wrong-kind"),
}


@pytest.mark.parametrize("case", list(FAULT_ELSEWHERE))
def test_a_file_a_gate_reads_is_never_unread_when_the_fault_is_elsewhere(
        standard, project, case):
    """THE GATE'S FINDING, NOT THIS ROW'S (review of PR #555). With a leg's
    role misspelt, `contracts/spec-pin.yaml` is still the spec leg's pin,
    the shape's own path (`own_pins`), which the gate reads again once the
    role is right. With the naming policy declaring another kind, it is
    still the file `validate-manifest.py` reads, and refuses. Each is the
    `manifest` row's FINDING; `manifest kinds` says `ok`, as main did, and
    lists the file `validated` -- never `unread`, so no NEXT takes it out.
    """
    rel, before, after, validated, code = FAULT_ELSEWHERE[case]
    path = project / rel
    body = path.read_bytes()
    assert body.count(before) == 1, body
    path.write_bytes(body.replace(before, after))
    commit_all(project, f"{case}, committed")
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["manifest"]["status"] == "FINDING", rows["manifest"]
    assert code in rows["manifest"]["reason"], rows["manifest"]["reason"]
    kinds = rows["manifest-kinds"]
    assert kinds["status"] == "ok", kinds
    assert set(kinds["detail"]) == MANIFEST_KINDS_DETAIL_KEYS, kinds
    assert validated in kinds["detail"]["validated"], kinds


def test_the_next_never_takes_out_a_file_a_gate_reads(standard, project):
    """A kind nothing registers in the naming policy is still this row's
    finding, as on main, but a NEXT that took the file out would take out
    the naming policy (review of PR #555). The NEXT shows the change that
    set the kind, the `why` names the kind a gate here reads that path as
    and the `manifest` row, whose gate checks it, and offers no other way
    out -- registering the kind is no answer for the naming policy (round
    2). Beside a file the row may take out, the next run names that one."""
    module = doctor_module(standard)
    naming = project / NAMING_COPY
    body = naming.read_bytes()
    assert body.count(b"kind: repository-naming-policy\n") == 1, body
    naming.write_bytes(body.replace(b"kind: repository-naming-policy\n",
                                    b"kind: service-inventory\n"))
    shown = (f"shows the change to {NAMING_COPY} that no commit holds. "
             f"{NAMING_COPY} declares kind service-inventory where a gate "
             "here reads it as repository-naming-policy, and the manifest "
             "row's gate finds that too: put its kind line back to "
             "repository-naming-policy")

    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["detail"]["unregistered"] == [
        "contracts/repository-naming.yaml (service-inventory)"], row
    assert row["next"] == (f"git -C {module.quote_arg(project)} diff HEAD "
                           f"-- {NAMING_COPY}"), row
    assert row["why"] == shown, row["why"]

    write_inventory(project)
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["next"] == (f"git -C {module.quote_arg(project)} diff HEAD "
                           f"-- {NAMING_COPY}"), row
    assert row["why"] == (f"{shown}. The next run names the way out for "
                          f"{INVENTORY[0]}. {UNREGISTERED_WAY}"), row["why"]


def test_gitlinks_under_lists_one_directory_and_nothing_above_it(project):
    """`gitlinks_under` is asked for the members directory a hand-edited
    manifest names, so an empty one, an absolute one and one that climbs
    list nothing -- never every gitlink in the root, the two legs included."""
    module = doctor_module(REPO)
    commit = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    record_gitlink(project, "members/One", commit)
    record_gitlink(project, "members/sub/Two", commit)
    assert module.gitlinks_under(project, "members") == [
        "members/One", "members/sub/Two"]
    assert module.gitlinks_under(project, "members/") == [
        "members/One", "members/sub/Two"]
    assert module.gitlinks_under(project, "members/sub") == [
        "members/sub/Two"]
    for directory in ("", ".", "/", "/members", "\\members", "..",
                      "members/..", "../members", "C:/members",
                      str(project / "members")):
        assert module.gitlinks_under(project, directory) == [], directory
    # A leg is a gitlink AT its directory, not under it.
    assert module.gitlinks_under(project, "spec") == []


def test_gitlinks_under_reads_names_unquoted_and_stage_0_only(project):
    """`-z` and stage 0, the two things `gitlinks_under` says it reads by.

    A member whose name is not ASCII is listed ONCE, as itself: without
    `-z`, `ls-files` prints it quoted and octal-escaped (`core.quotePath`),
    and a row naming it would then report it as a gitlink no row names. A
    gitlink left CONFLICTED under the directory -- stages 1, 2 and 3 and no
    stage 0, which is what a merge that disagreed about a submodule leaves
    -- is nobody's next commit and is not listed, rather than listed three
    times. Non-ASCII is the one character git quotes that every platform's
    index takes.

    Both are written with `update-index --index-info` from BYTES: a
    text-mode pipe on Windows turns each LF into CR LF and git stages the
    path with a CR on it (see `stage_unmerged`), and bytes also keep the
    name off a command line whose encoding differs by platform.
    """
    module = doctor_module(REPO)
    commit = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    unquoted = "members/Ünï"
    lines = f"160000 {commit} 0\t{unquoted}\n" + "".join(
        f"160000 {commit} {stage}\tmembers/Conflicted\n"
        for stage in (1, 2, 3))
    subprocess.run(["git", "update-index", "--index-info"],
                   cwd=str(project), input=lines.encode("utf-8"),
                   capture_output=True, check=True)
    staged = subprocess.run(["git", "ls-files", "-s", "-z", "--", "members"],
                            cwd=str(project), capture_output=True,
                            check=True).stdout.decode("utf-8")
    assert sorted(record.split()[2] for record in staged.split("\0")
                  if record) == ["0", "1", "2", "3"], staged
    assert module.gitlinks_under(project, "members") == [unquoted]


# --- not a shape root -------------------------------------------------------

def test_a_git_repository_with_no_manifest_says_adopt(standard, tmp_path):
    here = tmp_path / "Thing"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    (here / "README.md").write_text("# Thing\n", encoding="utf-8")
    (here / "src").mkdir()
    (here / "src" / "main.py").write_text("VALUE = 1\n", encoding="utf-8")
    commit_all(here, "Initial import")
    result = doctor(standard, here)
    assert result.returncode == 2, result.stdout + result.stderr
    assert verdict_line(result).startswith(
        "the machine check is `openRepoShape --preflight` now"), result.stdout
    assert "NOT A SHAPE ROOT   (exit 2)" in result.stdout
    assert "adopt-project.py plan" in result.stdout
    assert "--project Thing" in result.stdout
    assert "a git repository" in result.stdout


def test_an_empty_git_repository_is_not_a_shape_root(standard, tmp_path):
    here = tmp_path / "Empty"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "none"
    assert payload["verdict"] == "NOT A SHAPE ROOT"
    assert payload["note"].startswith("the machine check is")
    rows = rows_of(result)
    # `triad-advisory` since #163: an empty repository has elected nothing
    # and recorded nothing, so it hears the Triad advisory -- an `advisory`
    # row that the verdict steps over, which the exit code above shows.
    assert set(rows) == {"naming", "contents", "way-in", "way-in-scaffold",
                         "triad-advisory", "machine"}
    assert rows["triad-advisory"]["status"] == "advisory"
    assert "placement" not in rows, (
        "there are no legs here and no manifest declaring any, so there is "
        "no placement question to answer; the row is absent rather than n/a")
    assert "adopt-project.py plan" in rows["way-in"]["next"]
    assert rows["contents"]["detail"]["project_yaml"] is False


def test_a_root_named_like_an_option_still_gets_a_real_naming_verdict(
        standard, tmp_path):
    """A directory called `--help` is a NAME, not a flag -- to argparse too.

    `check_not_a_root_naming` used to call the validator as
    `run_validator(ctx, script, ["--explain", *names])`. With no `--` before
    the names, a root literally named `--help` reached
    `validate-repository-naming.py --explain --help`, and argparse's OWN
    `-h`/`--help` matched before either positional was ever read: exit 0,
    "classifies under the naming policy", for a name that classifies under
    NOTHING. That is a false COMPLIANT, not a crash -- which is exactly why a
    red row never caught it.
    """
    here = tmp_path / "--help"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "none"
    rows = rows_of(result)
    # `triad-advisory` since #163, as for any repository that has not
    # elected the Triad; it does not touch the naming row this test is about.
    assert set(rows) == {"naming", "contents", "way-in", "way-in-scaffold",
                         "triad-advisory", "machine"}
    row = rows["naming"]
    # The real verdict -- unclassified -- not the false OK argparse's own
    # help action used to produce.
    assert row["status"] == "FINDING", row
    assert row["detail"]["exit"] == 1, row
    assert "naming-unclassified" in row["reason"], row["reason"]
    assert "--explain -- --help" in row["next"], row["next"]

    # The counterexample, so the assertions above cannot be passing by
    # accident: called the OLD way -- no `--` -- this exact name reaches the
    # validator's own help action instead of being classified at all.
    unfixed = run_script(
        standard / "scripts" / "validate-repository-naming.py",
        "--explain", here.name)
    assert unfixed.returncode == 0, (
        "if this is no longer 0, `--help` stopped demonstrating the bug and "
        "the fixed row's test above needs a different name:\n"
        + unfixed.stdout + unfixed.stderr)
    assert "show this help message and exit" in unfixed.stdout


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_naming_rows_next_command_runs_when_it_is_pasted(standard,
                                                              tmp_path):
    """The whole promise, end to end: the printed line, into a shell, verbatim.

    `--explain -- --help` needs no shell quoting at all -- every character in
    it is in `quote_arg`'s safe set, so #101/#102 leave it untouched -- which
    is exactly why this row needed its OWN fix: the bug is a missing token in
    the argument list, not a missing quote, and the only way to prove a
    pasted line reaches the real classifier is to paste the line.
    """
    here = tmp_path / "--help"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = rows_of(doctor(standard, here, "--json"))["naming"]
    assert row["status"] == "FINDING", row

    pasted = subprocess.run(["bash", "-c", row["next"]], capture_output=True,
                            text=True, check=False,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == 1, (
        "a real classification exits 1 for an unclassified name; exit "
        f"{pasted.returncode} is argparse's own --help winning again.\n"
        f"{whole}")
    assert "naming-unclassified" in whole, whole
    assert "usage:" not in whole, whole


def test_a_directory_that_is_not_a_repository_says_scaffold(standard,
                                                            tmp_path):
    """No repository to adopt, so the way in is the scaffold — and it is
    named WITHOUT `--yes`, because the one yes is the human's."""
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    rows = rows_of(result)
    # THE READER'S OWN ENTRY POINT, which is not the same file on every
    # platform: `setup.sh` is bash and PowerShell cannot execute it, so on
    # Windows the way in is `setup-project.py`, which IS the flow -- and
    # `setup.sh` a shim over it (#49, #50; Copilot, PR #102).
    assert ("setup-project.py" if os.name == "nt" else "setup.sh") in \
        rows["way-in"]["next"], rows["way-in"]["next"]
    assert "--org <your-org>" in rows["way-in"]["next"]
    # Said beside the command, never on it (#277).
    assert rows["way-in"]["why"] == SCAFFOLD_WHY, rows["way-in"]
    assert rows["way-in"]["detail"]["git_repository"] is False
    assert "an ordinary directory" in rows["contents"]["reason"]
    # THE SCAFFOLD IS NOT PRINTED TWICE: it is this row, and a directory
    # with no repository has no adoption for a second row to sit beside (#545).
    assert "way-in-scaffold" not in rows, sorted(rows)


def test_a_manifest_declaring_the_wrong_kind_is_not_a_root(standard,
                                                           tmp_path):
    """`kind:` decides, not the filename.

    A file CALLED `project.yaml` that declares something else is not a
    project manifest, and reading the name alone would let any file assert
    whatever it liked about a directory.
    """
    here = tmp_path / "Pretend"
    here.mkdir()
    (here / "project.yaml").write_text(
        "schema_version: 1\nkind: something-else\nid: pretend\n",
        encoding="utf-8")
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["contents"]["detail"]["project_yaml"] is True
    assert "declares neither" in rows["contents"]["reason"]


# --- a manifest that is there and does not load (#205) ----------------------
#
# `Context` used to read a manifest `load_yaml` REFUSES exactly as a missing
# one, so an assembly root with both legs mounted and a merge conflict in its
# `project.yaml` was NOT A SHAPE ROOT, exit 2, its `the way in` row told the
# reader to `adopt-project.py plan` it -- cutting two new legs out of a
# repository that already has them -- and its Triad row called it "a single
# repository". The project's own `validate-manifest.py` named the real fault
# on the same file all along. A file that is there is not a file that is
# absent: the filename names the kind, the `manifest` row quotes the loader
# and names that validator, and the verdict is INVALID, exit 1.

#: Every row an assembly root gets, whatever is wrong with it: the same ids
#: `test_every_row_of_a_compliant_project_is_ok_or_na` holds a compliant one
#: to. None of the three rows a directory with no manifest gets is among them.
PROJECT_ROWS = {"naming", "manifest", "pins", "manifest-kinds",
                "shape-currency", "legs", "leg-shape-files", "placement",
                "agent-files", "machine"}
NOT_A_ROOT_ROWS = ("contents", "way-in", "way-in-scaffold",
                    "triad-advisory")

#: The rows that read what `project.yaml` DECLARES, which wait on the
#: `manifest` row while it does not load rather than answering a question
#: they cannot ask ("declares no non-assembly leg", a second copy of the
#: refusal under `validate-pins.py`'s lockstep remedy).
WAITING_ROWS = ("naming", "pins", "legs", "leg-shape-files", "placement")


def conflicted(body: bytes, nth: int = 0) -> bytes:
    """`body` with its `nth` `commit:` line inside a merge conflict.

    What a hand edit, or a merge that touches that one manifest alone,
    leaves in it: a conflict marker its reader will not take, and the case
    #205 was found by. It builds ONE conflicted file and nothing else in
    the tree; what a root reads where other files conflict as well -- the
    shape pin, say -- is not built here and not asserted. Bytes in and out,
    with the file's own `\\n`, so the edit is the same on every platform.
    """
    lines = body.split(b"\n")
    hits = [index for index, line in enumerate(lines)
            if line.lstrip().startswith(b'commit: "')]
    line = lines[hits[nth]]
    indent = line[:len(line) - len(line.lstrip())]
    lines[hits[nth]:hits[nth] + 1] = [
        b"<<<<<<< HEAD", line, b"=======",
        indent + b'commit: "' + b"1" * 40 + b'"',
        b">>>>>>> shape/update-1111"]
    return b"\n".join(lines)


#: Three ways a manifest stops loading, and the code `load_yaml` refuses
#: each with: a merge conflict and a tab are YAML its reader will not take
#: (`yaml-unparsable`), and a Latin-1 byte is not UTF-8 at all
#: (`yaml-unreadable`, #192). The edit is asserted to change the file, so a
#: scaffold that one day spells these lines differently is a red test and
#: not a manifest that quietly still loads.
BREAKAGES = {
    "merge-conflict": (conflicted, "yaml-unparsable"),
    "tab-indent": (lambda body: body.replace(
        b"\n  revision_kind:", b"\n\trevision_kind:", 1), "yaml-unparsable"),
    "not-utf8": (lambda body: body.replace(
        b'name: "Atlas"', b'name: "Atl\xe9s"', 1), "yaml-unreadable"),
}

#: The same three ways for a holder's `family.yaml`, which carries the same
#: indented `revision_kind:` in its `shape:` block. The conflict is in its
#: LAST `commit:` line, a member's pin, because two bumps of one member are
#: what leave one there; the byte goes into the family's own name.
FAMILY_BREAKAGES = {
    **BREAKAGES,
    "merge-conflict": (lambda body: conflicted(body, -1), "yaml-unparsable"),
    "not-utf8": (lambda body: body.replace(
        b'name: "' + FAMILY_NAME.encode() + b'"',
        b'name: "' + FAMILY_NAME.encode() + b'\xe9"', 1), "yaml-unreadable"),
}


def break_manifest(path: Path, edit, code: str) -> repo_shape.Refusal:
    """Break the manifest at `path` and return what `load_yaml` says of it.

    THE EXPECTED TEXT IS THE LOADER'S OWN, asked of the same file, so the
    doctor is held to repeating it rather than to a sentence this test made
    up. `path` is RESOLVED, because the doctor resolves `--root` before it
    names a file, and a temporary directory reached through a symlink would
    otherwise be two spellings of one path.
    """
    body = path.read_bytes()
    broken = edit(body)
    assert broken != body, "the edit did not change the manifest"
    path.write_bytes(broken)
    with pytest.raises(repo_shape.Refusal) as caught:
        repo_shape.load_yaml(path)
    assert caught.value.code == code, caught.value
    return caught.value


def loader_line(refusal: repo_shape.Refusal) -> str:
    """The line the loader's refusal prints first, and the gate prints too."""
    return f"REFUSED {refusal.code}: {refusal.detail}"


def assert_next_runs_the_roots_own(row: dict, root: Path, script: str) -> None:
    """The row's NEXT runs `<root>/scripts/<script>` itself, on `<root>`.

    THE PROJECT'S OWN COPY, AS A PATH, because a substring cannot say it:
    `"scripts/validate-manifest.py --root" in next` is just as true of the
    standard's template copy, so a NEXT that named the template passed it
    (review N1 on #205). The words are compared as paths, both sides
    RESOLVED, so a temporary directory reached through a symlink (macOS) or
    spelled with `\\` (Windows) is one path and not two. `detail.validator`
    is the same file by another route and is held to the same one.

    The file must be there, or the claim is empty: the root of these tests
    carries its own copy, a different file from the standard's.
    """
    own = root / "scripts" / script
    assert own.is_file(), own
    command = row["next"].split("#")[0].split()
    assert command[2] == "--root", command
    assert Path(command[1]).resolve() == own.resolve(), (
        f"the NEXT names {command[1]}, not the root's own {own}")
    assert Path(command[3]).resolve() == root.resolve(), command
    assert Path(row["detail"]["validator"]).resolve() == own.resolve(), \
        row["detail"]


#: The `machine` row's own line in the text report -- two spaces, its
#: status, its label -- which is the one line `no_adoption_offered` reads
#: around.
MACHINE_LINE = re.compile(r"^  \S+ +machine  ")


def no_adoption_offered(text: str = "", rows: dict | None = None,
                        payload: dict | None = None) -> None:
    """Not one `adopt-project.py` anywhere in the report, but a machine fact.

    THE `machine` ROW IS THE ONE PLACE THE NAME MAY APPEAR, and it is
    UNCHANGED by #205 (`machine_row_unchanged`): on a workstation without
    `git-filter-repo` -- never a CI runner since #471 installed it on all
    three -- it says that only `adopt-project.py` needs that tool, in a
    COMPLIANT report exactly as here. That is a sentence about the machine
    and never an offer to adopt anything, so the text report is read around
    that row's one line, and the row itself may name the tool only while the
    tool is missing. Everything
    else -- the kind line, every reason, every NEXT, every `detail`, the
    verdict -- names it not at all, `plan` or no `plan`.
    """
    outside = "\n".join(line for line in text.splitlines()
                        if not MACHINE_LINE.match(line))
    assert "adopt-project.py" not in outside, outside
    for name, row in (rows or {}).items():
        said = json.dumps(row)
        if name == "machine":
            assert "adopt-project.py" not in said or \
                row["detail"]["git-filter-repo"] is None, row
            continue
        assert "adopt-project.py" not in said, (name, row)
    if payload is not None:
        rest = {key: value for key, value in payload.items() if key != "rows"}
        assert "adopt-project.py" not in json.dumps(rest), rest


#: WHETHER THE `machine` ROW'S `gh` IS THE SESSION GUARD (#296). On POSIX the
#: preflight's bare `gh` is the guard `tests/conftest.py` puts first on PATH,
#: which answers every run the same, so the whole row can be held still. On
#: Windows CreateProcess looks a bare `gh` up as `gh.exe` alone, never the
#: guard's `gh.cmd`, so the row still asks whatever `gh.exe` is installed,
#: which answers from its host and may answer two runs differently.
GH_IS_THE_GUARD = os.name != "nt"


def machine_row_unchanged(before: dict, after: dict) -> None:
    """The `machine` row is the row the same root had before it broke.

    It is about the workstation, so nothing in a manifest can move it, and
    #205 is held to that rather than trusted with it. Where the row's `gh` is
    the session guard (`GH_IS_THE_GUARD`) it answers both runs the same, so
    the whole row must be the same, byte for byte. ONE PART IS NOT THIS
    TEST'S TO HOLD STILL where it is not: there the preflight asks a real
    `gh`, which answers from its host, so where it answered the two runs
    differently only the parts that do not come from it are compared.
    """
    for key in ("id", "label", "status"):
        assert after[key] == before[key], (key, before, after)
    for key in ("preflight", "git-filter-repo"):
        assert after["detail"].get(key) == before["detail"].get(key), \
            (key, before, after)
    if GH_IS_THE_GUARD or all(
            after["detail"].get(key) == before["detail"].get(key)
            for key in ("exit", "report")):
        assert after == before, (before, after)


@pytest.mark.parametrize("case", sorted(BREAKAGES))
def test_a_manifest_that_does_not_load_is_invalid_and_not_absent(
        standard, project, case):
    """(a) INVALID, exit 1, the loader's own line, and no way in offered.

    The root is still an assembly root: its kind line says so and says why
    the filename decided it, no row a manifest-less directory gets is
    printed -- not `the way in`, not the Triad row calling it "a single
    repository" -- and the `machine` row is the row it always was.
    """
    edit, code = BREAKAGES[case]
    refusal = break_manifest(project.resolve() / "project.yaml", edit, code)
    result = doctor(standard, project)
    whole = result.stdout + result.stderr
    assert result.returncode == 1, whole
    assert verdict_line(result) == "INVALID (manifest)   (exit 1)", whole
    assert "kind        assembly root (project.yaml, which does not load: " \
        "see the `manifest` row)" in result.stdout, result.stdout
    assert f"project.yaml does not load: {loader_line(refusal)}" in \
        result.stdout, result.stdout
    no_adoption_offered(whole)
    for never in ("NOT A SHAPE ROOT", "single repository", "the way in",
                  "what is here", "remove the file", "git submodule"):
        assert never not in whole, (never, whole)
    assert "  n/a      machine  " in result.stdout, result.stdout


@pytest.mark.parametrize("case", sorted(BREAKAGES))
def test_the_json_report_of_an_unloaded_manifest_is_the_same_report(
        standard, project, case):
    """(b) `--json` carries the same verdict, exit and rows, by id.

    The `manifest` row is the FINDING and carries the refusal as data; every
    row that reads what the manifest declares is `n/a` and names the row it
    waits on in `detail.waits_on`; `manifest kinds` does not list the same
    file a second time under a next command that says to remove it. And the
    text report says every one of those reasons and next commands, verbatim.
    The `machine` row is the row the same root had before its manifest
    broke.
    """
    intact = rows_of(doctor(standard, project, "--json"))["machine"]
    edit, code = BREAKAGES[case]
    refusal = break_manifest(project.resolve() / "project.yaml", edit, code)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"], payload["exit"]) == \
        ("project", "INVALID (manifest)", 1), payload
    assert payload["note"] is None and payload["placement_plan"] is None
    rows = rows_of(result)
    assert set(rows) == PROJECT_ROWS, sorted(rows)
    for absent in NOT_A_ROOT_ROWS:
        assert absent not in rows, rows.get(absent)
    no_adoption_offered(rows=rows, payload=payload)

    manifest = rows["manifest"]
    assert manifest["status"] == "FINDING", manifest
    assert manifest["reason"] == \
        f"project.yaml does not load: {loader_line(refusal)}", manifest
    assert manifest["detail"]["refusal"] == {"code": refusal.code,
                                             "detail": refusal.detail}
    assert manifest["detail"]["manifest"] == "project.yaml"
    assert manifest["detail"]["own_copy"] is True
    assert_next_runs_the_roots_own(manifest, project, "validate-manifest.py")
    # The file to fix is named in the row's `why`, off the command's line
    # (#277).
    assert "the file to fix is" in manifest["why"], manifest["why"]
    assert "project.yaml" in manifest["why"]

    for name in WAITING_ROWS:
        row = rows[name]
        assert row["status"] == "n/a", (name, row)
        assert row["detail"]["waits_on"] == "manifest", (name, row)
        assert row["reason"].startswith("project.yaml does not load, so "), \
            (name, row)
        assert row["next"] is None, (name, row)
    assert "declares no non-assembly leg" not in rows["legs"]["reason"]
    kinds = rows["manifest-kinds"]
    assert kinds["status"] == "ok", kinds
    assert kinds["detail"]["reported_by"] == {"project.yaml": "manifest"}
    assert "project.yaml" not in kinds["detail"]["unreadable"], kinds
    assert rows["machine"]["status"] == "n/a", rows["machine"]
    machine_row_unchanged(intact, rows["machine"])

    text = doctor(standard, project)
    assert text.returncode == payload["exit"], text.stdout + text.stderr
    assert verdict_line(text) == \
        f"{payload['verdict']}   (exit {payload['exit']})", text.stdout
    no_adoption_offered(text.stdout + text.stderr)
    for name, row in rows.items():
        if name == "machine" and not GH_IS_THE_GUARD:
            continue  # a real `gh` need not answer twice the same
        assert row["reason"] in text.stdout, (name, row["reason"])
        if row["next"]:
            assert row["next"] in text.stdout, (name, row["next"])


@pytest.mark.parametrize("case", sorted(BREAKAGES))
def test_the_manifest_rows_next_command_refuses_the_same_file_the_same_way(
        standard, project, case):
    """The NEXT line is the project's own gate, and it says what the row said.

    Pasted, it runs the project's own `validate-manifest.py`, which refuses
    the file with the same code and the same words after its path -- the
    path itself is the validator's spelling of the root, which is git's, and
    is compared no further than that. Exit 2 is that validator's refusal.
    """
    edit, code = BREAKAGES[case]
    path = project.resolve() / "project.yaml"
    refusal = break_manifest(path, edit, code)
    row = rows_of(doctor(standard, project, "--json"))["manifest"]
    assert_next_runs_the_roots_own(row, project, "validate-manifest.py")
    command = row["next"].split("#")[0].split()
    proc = subprocess.run(command, capture_output=True, text=True,
                          check=False, env={**os.environ,
                                            "PYTHONDONTWRITEBYTECODE": "1"})
    said = proc.stdout + proc.stderr
    assert proc.returncode == 2, said
    assert f"REFUSED {refusal.code}: " in said, said
    assert refusal.detail[len(str(path)):] in said, (refusal.detail, said)


def test_the_quoted_refusal_line_is_the_refusals_own_less_its_remediation():
    """One spelling of `REFUSED <code>: <detail>`, and it is the loader's.

    The `manifest` and `family` rows quote it through `refusal_line`, which
    takes it from `Refusal.__str__` instead of spelling it again (review N2
    on #205). It is `str(refusal)` less the remediation trailer, which is
    not the same as its first line: `detail` opens with the path the loader
    was given, and a path may hold a newline, where "up to the first
    newline" quotes it short. So the line is held to every shape a refusal
    takes -- the loader's default remedy, a one-line remedy of its own (the
    non-UTF-8 refusal has one), a remedy of several lines -- and to a path
    with a newline in it, here as a value and not as a file, because a
    Windows filesystem refuses the name. The expected line is spelled out
    in the test, apart from the code under test, so that moving it is a
    red test.
    """
    spec = importlib.util.spec_from_file_location(
        "shape_doctor_refusal_line", REPO / DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    remedies = (repo_shape.REMEDIATION, "Remediation: re-save it as UTF-8.",
                "Remediation: first line.\nsecond line.\nthird line.")
    for path in ("/r/Atlas/project.yaml", "/r/At\nlas/project.yaml"):
        for remedy in remedies:
            refusal = repo_shape.Refusal(
                "yaml-unparsable", f"{path}: line 77: merge keys are not "
                "supported", remedy)
            line = module.refusal_line(refusal)
            assert line == ("REFUSED yaml-unparsable: " + path
                            + ": line 77: merge keys are not supported"), line
            assert str(refusal) == line + "\n" + remedy, str(refusal)
            assert remedy not in line, line


@pytest.mark.parametrize("case", sorted(FAMILY_BREAKAGES))
def test_a_family_yaml_that_does_not_load_is_invalid_and_not_absent(
        standard, holder, tmp_path, case):
    """(c) A holder whose `family.yaml` does not load is still a holder.

    Before #205 it was NOT A SHAPE ROOT, offered `adopt-project.py plan
    --project InkRouter` and called "a single repository". Now the `family`
    row quotes the loader and names `validate-family.py` and the file, and
    `members` waits on it -- rather than saying "no members yet", an `ok`
    about an empty family, of a holder whose members nobody could read. The
    same three breakages as an assembly root's, the same report in text and
    in `--json`, and the `machine` row the row the holder had before.
    """
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    intact = rows_of(doctor(standard, root, "--json"))["machine"]
    edit, code = FAMILY_BREAKAGES[case]
    path = root.resolve() / "family.yaml"
    refusal = break_manifest(path, edit, code)
    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"], payload["exit"]) == \
        ("family", "INVALID (family)", 1), payload
    assert payload["note"] is None and payload["placement_plan"] is None
    rows = rows_of(result)
    assert set(rows) == {"family", "manifest-kinds", "shape-currency",
                         "placement", "agent-files", "members", "machine"}
    no_adoption_offered(rows=rows, payload=payload)
    family = rows["family"]
    assert family["status"] == "FINDING", family
    assert family["reason"] == \
        f"family.yaml does not load: {loader_line(refusal)}", family
    assert_next_runs_the_roots_own(family, root, "validate-family.py")
    # Named in the row's `why`, off the command's line (#277).
    assert "family.yaml" in family["why"], family["why"]
    members = rows["members"]
    assert members["status"] == "n/a", members
    assert members["detail"]["waits_on"] == "family", members
    assert "no members yet" not in members["reason"], members
    assert rows["placement"]["status"] == "n/a"
    assert "each member is an assembly root" in rows["placement"]["reason"]
    assert rows["manifest-kinds"]["detail"]["reported_by"] == \
        {"family.yaml": "family"}
    assert rows["machine"]["status"] == "n/a", rows["machine"]
    machine_row_unchanged(intact, rows["machine"])

    text = doctor(standard, root)
    whole = text.stdout + text.stderr
    assert text.returncode == 1, whole
    assert verdict_line(text) == "INVALID (family)   (exit 1)", text.stdout
    assert "kind        family holder (family.yaml, which does not load: " \
        "see the `family` row)" in text.stdout, text.stdout
    no_adoption_offered(whole)
    for never in ("NOT A SHAPE ROOT", "single repository", "the way in",
                  "what is here", "remove the file", "git submodule"):
        assert never not in whole, (never, whole)
    for name, row in rows.items():
        if name == "machine" and not GH_IS_THE_GUARD:
            continue  # a real `gh` need not answer twice the same
        assert row["reason"] in text.stdout, (name, row["reason"])
        if row["next"]:
            assert row["next"] in text.stdout, (name, row["next"])

    command = family["next"].split("#")[0].split()
    proc = subprocess.run(command, capture_output=True, text=True,
                          check=False, env={**os.environ,
                                            "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert refusal.detail[len(str(path)):] in proc.stdout + proc.stderr


@pytest.mark.parametrize("where", ["a-repository", "a-plain-directory"])
def test_a_manifest_that_is_absent_is_still_not_a_shape_root(standard,
                                                             project,
                                                             tmp_path,
                                                             where):
    """(d) Absent is unchanged: NOT A SHAPE ROOT, exit 2, and the way in.

    The assembly root of the tests above with its `project.yaml` DELETED
    rather than broken is a git repository with no manifest, and is offered
    the adoption; a directory that is not a repository is offered the
    scaffold. Those are the two ways in AGENTS.md names, each where it
    applies -- between the two cases, both commands -- and #205 changed
    neither, in `--json` or in the text report.
    """
    if where == "a-repository":
        (project / "project.yaml").unlink()
        here, way_in = project, "adopt-project.py plan"
    else:
        here = tmp_path / "Loose"
        here.mkdir()
        (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
        way_in = "setup-project.py" if os.name == "nt" else "setup.sh"
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert (payload["kind"], payload["verdict"], payload["exit"]) == \
        ("none", "NOT A SHAPE ROOT", 2), payload
    rows = rows_of(result)
    assert way_in in rows["way-in"]["next"], rows["way-in"]
    assert rows["contents"]["detail"]["project_yaml"] is False
    assert rows["contents"]["detail"]["family_yaml"] is False
    assert not set(rows) & (PROJECT_ROWS - {"naming", "machine"}), sorted(rows)

    text = doctor(standard, here)
    assert text.returncode == 2, text.stdout + text.stderr
    assert "kind        not a shape root" in text.stdout, text.stdout
    assert "NOT A SHAPE ROOT   (exit 2)" in text.stdout, text.stdout
    assert rows["way-in"]["next"] in text.stdout, text.stdout


def test_a_manifest_that_declares_its_kind_outranks_one_that_does_not_load(
        standard, holder, tmp_path):
    """A good `family.yaml` beside a broken stray `project.yaml` is a holder.

    `kind:` decides first, as it always has; the filename decides only where
    no file that loads declares a kind. So this root reads exactly as it did
    before #205 -- a family holder whose `family` row passes -- rather than
    as a broken assembly root.
    """
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    (root / "project.yaml").write_bytes(
        b"kind: project-manifest\n\tname: stray\n")
    result = doctor(standard, root, "--json")
    payload = json.loads(result.stdout)
    assert payload["kind"] == "family", payload
    rows = rows_of(result)
    assert rows["family"]["status"] == "ok", rows["family"]
    assert "manifest" not in rows, rows.get("manifest")
    assert "project.yaml" in rows["manifest-kinds"]["detail"]["unreadable"]


def test_a_manifest_that_does_not_load_writes_no_placement_plan(standard,
                                                                project,
                                                                tmp_path):
    """There is no leg to write a plan about until the manifest loads.

    The `placement` row is `n/a`, so `--placement-plan` refuses by name,
    exit 3 -- the flag's question, as for a family holder -- says why in the
    `placement` row's own words, and writes nothing.
    """
    break_manifest(project.resolve() / "project.yaml", conflicted,
                   "yaml-unparsable")
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--placement-plan", str(out))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "REFUSED shape-doctor-no-placement-audit" in result.stderr
    assert "project.yaml does not load, so there is no leg to classify" in \
        result.stderr, result.stderr
    assert not out.exists()


# --- usage and environment --------------------------------------------------

def test_a_path_that_is_not_there_is_exit_3(standard, tmp_path):
    result = doctor(standard, tmp_path / "nowhere")
    assert result.returncode == 3, result.stdout + result.stderr
    assert "shape-doctor-root-missing" in result.stderr
    assert "it never clones one" in result.stderr


def test_the_script_refuses_outside_a_checkout_of_the_standard(tmp_path,
                                                               project):
    """One copy of this file, on its own, can answer nothing.

    The standard it compares against is the checkout it is RUN FROM, so a
    `shape-doctor.py` sitting alone in a directory has no upstream, no
    templates and no naming policy — and it says which of them are missing
    rather than dying on the first import that fails.

    THE FILE IS COPIED OUT ALONE, which is the whole point and is what this
    test used to arrange away: it copied `scripts/repo_shape.py` in beside
    it — precisely the file whose absence caused the death — and so asserted
    the opposite of the sentence above. Alone, the module-level import used
    to raise ModuleNotFoundError and exit 1, which is this tool's code for
    "the repository has findings": a caller scripting on it read an
    interpreter crash as a verdict about somebody's repository.
    """
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    shutil.copy2(REPO / DOCTOR, lonely / DOCTOR)
    result = run_script(lonely / DOCTOR, "--root", str(project))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "shape-doctor-not-in-the-standard" in result.stderr
    assert "update-shape.py" in result.stderr
    assert "openRepoShape --doctor" in result.stderr


def test_the_doctor_writes_nothing(standard, project):
    """The claim in the first line of the module docstring, asserted.

    Every path under the root, with its size and mtime, before and after. A
    tool a person points at somebody else's repository has to be safe to
    point at somebody else's repository.
    """
    def snapshot():
        return sorted(
            (path.relative_to(project).as_posix(), path.stat().st_size)
            for path in project.rglob("*") if path.is_file())

    before = snapshot()
    result = doctor(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot() == before


# --- the shim ---------------------------------------------------------------

def refusing_network(tmp_path) -> dict:
    """A `$PATH` whose `gh` and `curl` fail loudly if anything calls them,
    and write down every call they are handed.

    THE LOG IS THE WITNESS, NOT STDERR (#296). The doctor's `machine` row
    calls this `gh` -- `gh --version` and `gh auth status`, from
    `setup-project.py --preflight` -- and the preflight CAPTURES what `gh`
    prints, so the refusal below never reaches the run's stderr and an
    assertion that it is absent there could not fail. Each call is one line
    in `CALLS` beside the two scripts: the program, then each argument, TAB
    separated. A stub of the test's own, it sits ahead of the session's `gh`
    guard (`tests/conftest.py`) and wins, exactly as before.
    """
    fake = tmp_path / "no-network"
    fake.mkdir(exist_ok=True)
    log = shlex.quote(str(fake / CALLS))
    for name in ("gh", "curl"):
        script = fake / name
        script.write_text(
            "#!/bin/sh\n"
            f"{{ printf '%s' {name}; [ \"$#\" -eq 0 ] || "
            f"printf '\\t%s' \"$@\"; printf '\\n'; }} >> {log}\n"
            f"printf 'fake {name}: no test here may reach the network\\n' >&2\n"
            "exit 1\n", encoding="utf-8")
        script.chmod(0o755)
    return {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}


#: `refusing_network`'s log, beside its two scripts.
CALLS = "calls.log"


def network_calls(tmp_path) -> list:
    """Every call `refusing_network`'s `gh` and `curl` were handed, as
    `[program, *arguments]`, in order; none when nothing called them."""
    log = tmp_path / "no-network" / CALLS
    if not log.exists():
        return []
    return [line.split("\t")
            for line in log.read_text(encoding="utf-8").splitlines()]


def beyond_the_machine_row(calls: list) -> list:
    """`calls` less the two the doctor's `machine` row makes -- `gh
    --version` and `gh auth status`, the session guard's own `PROBES` -- so
    what is left is a fetch, which no test here may make."""
    return [call for call in calls
            if not (call[0] == "gh" and tuple(call[1:]) in GH_PROBES)]


def fetched_nothing(tmp_path, doctor_ran: bool) -> None:
    """No call beyond the `machine` row's reached `refusing_network`'s `gh`
    or `curl` -- and, where the doctor ran, the row's two probes DID reach
    that `gh`, once each and in order, which is what shows the `gh` the run
    met was the stub rather than one further down PATH. Where it did not run
    (a refusal before it), nothing reached either."""
    calls = network_calls(tmp_path)
    assert beyond_the_machine_row(calls) == [], (
        f"a run that must fetch nothing called: {calls}")
    # The guard's own table, in its order, which is the preflight's: one
    # definition of the row's two calls, so a change to it moves this too.
    expected = [["gh", *argv] for argv in GH_PROBES] if doctor_ran else []
    assert calls == expected, calls


def shim_env(tmp_path, **extra) -> dict:
    environ = dict(os.environ)
    for name in ("OPENREPOSHAPE_ORG", "OPENREPOSHAPE_REF",
                 "OPENREPOSHAPE_REPO", "OPENREPOSHAPE_BIN_DIR",
                 "OPENREPOSHAPE_SETUP_SH"):
        environ.pop(name, None)
    environ.update(GIT_IDENTITY)
    environ.update(refusing_network(tmp_path))
    environ.update(extra)
    return environ


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_shim_runs_the_script_beside_it_and_fetches_nothing(
        standard, project, tmp_path):
    """Run from a file inside a checkout, THAT checkout answers.

    Nothing is faked here: the real shim runs the real `shape-doctor.py` out
    of the real (temporary) standard, and the `gh` and `curl` on `$PATH`
    refuse and log — so a shim that reached for the network would fail this
    test rather than pass it slowly. THE LOG is what is read (#296): the
    doctor's `machine` row calls that `gh` too, the preflight captures what
    it prints, and so the refusal never reaches stderr. The row's two probes
    are in the log, which shows the `gh` this run reached was the stub, and
    nothing else is.
    """
    result = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor", str(project)],
        capture_output=True, text=True, check=False, input="",
        env=shim_env(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLIANT   (exit 0)" in result.stdout
    assert f"standard    {standard}" in result.stdout, (
        "the checkout beside the file is the standard it must use")
    assert KEPT not in result.stdout + result.stderr, (
        "nothing was cloned beside a checkout, so there is nothing to keep "
        "or to name (#500)")
    fetched_nothing(tmp_path, doctor_ran=True)


#: The sentence the installed doctor ends on when it has kept its clone
#: (#500), cut where the directory's name begins and where it ends. It is
#: kept for the NEXT lines that NAME it (#546): "any NEXT command above runs
#: from it" was false of a `pins` row's, which can name no file in it, and
#: read as "cd into it", where the `placement` row's relative plan would be
#: written into the directory this line calls safe to delete.
KEPT = "the standard this run used is kept at "
KEPT_TAIL = (", for any NEXT command above that names it; it is safe to "
             "delete once you are done with them.")


def kept_by(text: str) -> Path:
    """The directory the installed doctor's LAST line says it kept.

    The last non-empty line and no other: Brett Heap's ruling on #500 puts
    the sentence there, so a report saved to a file still ends by saying what
    it left behind.
    """
    last = [line for line in text.splitlines() if line.strip()][-1]
    assert last.startswith(KEPT) and last.endswith(KEPT_TAIL), last
    return Path(last[len(KEPT):-len(KEPT_TAIL)])


def installed(tmp_path) -> Path:
    """`openRepoShape` alone in a directory, as `--install` places it: one
    file, no checkout beside it, so `--doctor` has to clone the standard."""
    target = tmp_path / "bin" / "openRepoShape"
    target.parent.mkdir(exist_ok=True)
    shutil.copy2(REPO / "openRepoShape", target)
    return target


def run_installed(standard: Path, tmp_path, *args,
                  cwd: Path | None = None) -> subprocess.CompletedProcess:
    """The installed command, cloning `standard` from a local PATH.

    `$TMPDIR` is a directory of the test's own, both because the clone now
    OUTLIVES the run (#500) and must not outlive it in the machine's `/tmp`,
    and because it is what shows what the run left behind.
    """
    temporary = tmp_path / "tmp"
    temporary.mkdir(exist_ok=True)
    return subprocess.run(
        ["bash", str(installed(tmp_path)), *args],
        capture_output=True, text=True, check=False, input="",
        cwd=str(cwd or tmp_path),
        env=shim_env(tmp_path, OPENREPOSHAPE_REPO=str(standard),
                     TMPDIR=str(temporary)))


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_shim_from_stdin_clones_the_standard_first(standard, project,
                                                       tmp_path):
    """Installed, or piped from `curl`, there is no checkout beside it.

    `$OPENREPOSHAPE_REPO` is a PATH here, which `shape_clone_url` passes to
    `git clone` untouched — the same offline hook `tests/test_setup_sh.py`
    uses for self-bootstrap — so the clone is real and the network is not
    touched. The standard it reports must be the temporary clone and not the
    directory the project lives in.

    AND THE CLONE OUTLIVES THE RUN (#500). This asserted the opposite until
    Brett Heap's ruling, "Keep the run's clone" (2026-10-13): an EXIT trap
    removed it, so every NEXT line naming a file in it failed when pasted. It
    is kept, it is the one thing left in `$TMPDIR`, and the report's last
    line names it.
    """
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    result = subprocess.run(
        ["bash", "-s", "--", "--doctor", str(project)],
        capture_output=True, text=True, check=False,
        input=(REPO / "openRepoShape").read_text(encoding="utf-8"),
        cwd=str(tmp_path),
        env=shim_env(tmp_path, OPENREPOSHAPE_REPO=str(standard),
                     TMPDIR=str(temporary)))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLIANT   (exit 0)" in result.stdout
    [reported] = [line.split(None, 1)[1].strip()
                  for line in result.stdout.splitlines()
                  if line.startswith("standard ")]
    assert reported != str(standard), (
        "with no checkout beside it the shim must clone one, not reach for "
        "the directory the project happens to sit next to")
    assert (Path(reported) / DOCTOR).is_file(), (
        f"{reported} did not outlive the run, and every NEXT line names a "
        "file in it (#500)")
    kept = kept_by(result.stdout)
    assert Path(reported).parent == kept, (reported, kept)
    assert [entry.resolve() for entry in temporary.iterdir()] == \
        [kept.resolve()], "the kept clone is the one thing the run left"
    assert kept.name.startswith("openRepoShape-doctor."), (
        "a kept directory carries the name of what made it, so a person can "
        f"find every one they have been left: {kept}")
    fetched_nothing(tmp_path, doctor_ran=True)


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_installed_doctors_next_lines_run_after_it_has_exited(
        standard, project, tmp_path):
    """#500: every NEXT the installed form printed named a file in a clone
    its EXIT trap had already removed, so each one, pasted, died with
    `python3: can't open file`, exit 2 -- the `shape currency` row's
    `update-shape.py check --upstream <clone>` included.

    The installed form here is the one file `--install` places, with nothing
    beside it, run over a project with one edited shape copy. Every NEXT
    that names a file in the kept clone is run AFTER the command has exited,
    as the reader's shell splits it, and the `shape currency` one must
    reproduce the finding it was printed for.
    """
    edited = project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8")
                      + "\n# a local edit nobody carried upstream\n",
                      encoding="utf-8")
    result = run_installed(standard, tmp_path, "--doctor", str(project))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "DRIFTED (1 locally-modified)   (exit 1)" in result.stdout, \
        result.stdout
    fetched_nothing(tmp_path, doctor_ran=True)
    kept = kept_by(result.stdout)
    shape = kept / "shape"
    nexts = [line.split("NEXT", 1)[1].strip()
             for line in result.stdout.splitlines()
             if line.lstrip().startswith("NEXT ")]
    from_the_clone = [line for line in nexts if str(shape) in line]
    assert any("update-shape.py" in line for line in from_the_clone), nexts
    for line in from_the_clone:
        argv = pasted(line)
        named = [Path(arg) for arg in argv if arg.startswith(str(shape))]
        for path in named:
            assert path.exists(), f"{line}\nnames {path}, which is gone"
        proc = subprocess.run(argv, capture_output=True, text=True,
                              check=False, stdin=subprocess.DEVNULL,
                              start_new_session=True, cwd=str(tmp_path),
                              env={**shim_env(tmp_path),
                                   "PYTHONDONTWRITEBYTECODE": "1"})
        assert "can't open file" not in proc.stdout + proc.stderr, (
            line + "\n" + proc.stdout + proc.stderr)
        if "update-shape.py" in argv[1]:
            assert proc.returncode == 1, line + "\n" + proc.stdout \
                + proc.stderr
            assert re.search(rf"locally-modified\s+{re.escape(DRIFT_TARGET)}",
                             proc.stdout), proc.stdout


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_installed_doctor_hands_on_json_and_keeps_stdout_one_object(
        standard, project, tmp_path):
    """`--json` reaches `shape-doctor.py` from the installed form (#500),
    which refused it outright -- AGENTS.md's doctor step 7 is "`--json` ...
    for when you have to act on a row".

    STDOUT IS THE JSON AND NOTHING ELSE. The line naming the kept clone
    goes to stderr under `--json`, because one line after the object makes
    a document `json.load` refuses; the object names the clone already, as
    `standard`. And the rows are the rows a checkout's `--json` gives, with
    only the standard's path differing.
    """
    result = run_installed(standard, tmp_path, "--doctor", str(project),
                           "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "COMPLIANT", payload["verdict"]
    kept = kept_by(result.stderr)
    assert KEPT not in result.stdout
    shape = Path(payload["standard"])
    assert shape.parent == kept and (shape / DOCTOR).is_file(), (shape, kept)
    beside = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor", str(project),
         "--json"],
        capture_output=True, text=True, check=False, input="",
        env=shim_env(tmp_path))
    assert beside.returncode == 0, beside.stdout + beside.stderr
    assert KEPT not in beside.stdout + beside.stderr
    checkout = json.loads(beside.stdout)
    assert Path(checkout["standard"]) == standard.resolve()
    rows = json.loads(result.stdout.replace(str(shape), checkout["standard"]))
    assert rows["rows"] == checkout["rows"]
    assert beyond_the_machine_row(network_calls(tmp_path)) == []


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize(("args", "inside"), [
    pytest.param(("--doctor", "{project}", "--placement-plan", "plan.yaml"),
                 False, id="path-then-flag"),
    pytest.param(("--doctor", "--placement-plan=plan.yaml", "{project}"),
                 False, id="flag-then-path"),
    pytest.param(("--doctor", "--placement-plan", "plan.yaml"),
                 True, id="standing-in-the-repository"),
])
def test_the_installed_doctors_placement_plan_lands_where_you_stand(
        args, inside, standard, project, tmp_path):
    """`--placement-plan <file>` reaches `shape-doctor.py` from the installed
    form (#500) -- it is the `placement` row's own NEXT, which the installed
    form refused -- and a RELATIVE `<file>` lands in the directory the
    command was run from: not in the kept clone, and in the repository only
    when that is where you stand (#546), as with `openRepoShape --doctor
    --placement-plan plan.yaml` typed there, the default path `.`.

    The plan is the only thing written, as AGENTS.md's doctor section says,
    and the doctor's own wording now says too: "writes nothing into it but"
    that file. The project's tree is compared file by file before and after.
    """
    here = project if inside else tmp_path / "here"
    here.mkdir(exist_ok=True)

    def snapshot():
        return sorted(
            (path.relative_to(project).as_posix(), path.stat().st_size)
            for path in project.rglob("*") if path.is_file())

    before = snapshot()
    result = run_installed(
        standard, tmp_path,
        *[arg.format(project=project) for arg in args], cwd=here)
    assert result.returncode == 0, result.stdout + result.stderr
    plan = here / "plan.yaml"
    assert "kind: placement-plan" in plan.read_text(encoding="utf-8")
    assert "placement plan written to plan.yaml" in result.stdout
    if inside:
        before = sorted(before + [("plan.yaml", plan.stat().st_size)])
    else:
        assert [entry.name for entry in here.iterdir()] == ["plan.yaml"]
    assert snapshot() == before
    assert not (kept_by(result.stdout) / "shape" / "plan.yaml").exists()


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_a_refused_doctor_still_names_its_kept_clone_without_next_lines(
        standard, tmp_path):
    """THE CLONE IS KEPT WHENEVER THE DOCTOR RAN, so the last line cannot say
    there are NEXT commands (#500, review of 9808aec, SHOULD-1).

    A `<path>` that is not there is refused by `shape-doctor.py` itself, exit
    3, with no report and so no NEXT line. The clone is kept all the same --
    Brett Heap's ruling keeps it once the doctor has run -- and the one line
    on stdout says where, as true of this run as of one that printed a dozen
    NEXT lines: "any NEXT command above" is empty here.
    """
    result = run_installed(standard, tmp_path, "--doctor",
                           str(tmp_path / "nonexistent"))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "shape-doctor-root-missing" in result.stderr
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    assert len(lines) == 1, result.stdout
    kept = kept_by(result.stdout)
    assert (kept / "shape" / DOCTOR).is_file(), (
        f"{kept} is named as kept and is not there")
    assert [entry.resolve() for entry in (tmp_path / "tmp").iterdir()] == \
        [kept.resolve()]


#: What `--doctor` says when it is handed something it does not take. Its
#: last clause said "and writes nothing into it" until #546, which was false
#: of a `--placement-plan <file>` named inside the repository.
NOTHING_ELSE = ("--doctor takes a path, --json and --placement-plan <file>, "
                "and nothing else; it reads a repository and writes nothing "
                "into it but that <file>.")
NO_PLAN_FILE = "--placement-plan needs the file"
TWO_PLANS = ("two placement plans, 'a.yaml' and 'b.yaml'. --doctor writes "
             "one: pass --placement-plan once.")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
@pytest.mark.parametrize(("args", "refusal"), [
    pytest.param(("--doctor", "--org", "Foo"), NOTHING_ELSE,
                 id="a-scaffold-flag"),
    pytest.param(("--doctor", ".", "Atlas"), NOTHING_ELSE, id="a-second-path"),
    pytest.param(("--doctor", ".", "--doctor", "Atlas"), NOTHING_ELSE,
                 id="a-second-path-after-a-second-doctor"),
    pytest.param(("--json", "--doctor", "."), NOTHING_ELSE,
                 id="json-before-doctor"),
    pytest.param(("--doctor", ".", "--placement-plan"), NO_PLAN_FILE,
                 id="plan-no-file"),
    pytest.param(("--doctor", ".", "--placement-plan="), NO_PLAN_FILE,
                 id="plan-empty"),
    pytest.param(("--doctor", ".", "--placement-plan", "--json"),
                 NO_PLAN_FILE, id="plan-a-flag"),
    pytest.param(("--doctor", ".", "--placement-plan", "a.yaml",
                  "--placement-plan", "b.yaml"), TWO_PLANS, id="two-plans"),
    pytest.param(("--doctor", "--placement-plan=a.yaml", ".",
                  "--placement-plan=b.yaml"), TWO_PLANS,
                 id="two-plans-around-the-path"),
])
def test_the_installed_doctor_refuses_before_it_clones(args, refusal,
                                                       standard, tmp_path):
    """What `--doctor` does not take is still refused by name, exit 2,
    before anything is cloned (#500 hands on two flags, and only those).

    A scaffold flag, a second path, or `--json` typed BEFORE `--doctor` --
    the doctor's flags follow it, as a subcommand's do, and anywhere else
    they are the lone flags a scaffold run passes on. `--placement-plan`
    with no file, an empty one, or a flag where the file goes is refused
    rather than handed to argparse or written to a file called `--json`.
    Nothing reaches stdout, `$TMPDIR` stays empty, and nothing is fetched.

    AND A SECOND OF EITHER IS A REFUSAL, NEVER LAST-WINS (#546), as two
    modes are. Two plans both reached `shape-doctor.py`, whose argparse kept
    the last, so `b.yaml` was written and `a.yaml` silently was not; a path
    after a second `--doctor` replaced the first. Neither file is written.
    """
    result = run_installed(standard, tmp_path, *args)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    assert "REFUSED: " + refusal in result.stderr
    assert list((tmp_path / "tmp").iterdir()) == []
    assert not list(tmp_path.glob("*.yaml"))
    fetched_nothing(tmp_path, doctor_ran=False)


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_shim_doctor_takes_a_path_and_nothing_else(standard, tmp_path):
    result = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor", "--org", "Foo"],
        capture_output=True, text=True, check=False, input="",
        env=shim_env(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert NOTHING_ELSE in result.stderr
    assert "openRepoShape --preflight" in result.stderr, (
        "the refusal must name the machine check, because `--doctor` meant "
        "that until 2026-09-10")
    fetched_nothing(tmp_path, doctor_ran=False)


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_shim_doctor_defaults_to_the_directory_you_are_in(standard,
                                                              project,
                                                              tmp_path):
    result = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor"],
        capture_output=True, text=True, check=False, input="",
        cwd=str(project), env=shim_env(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLIANT   (exit 0)" in result.stdout
    fetched_nothing(tmp_path, doctor_ran=True)


def test_the_shipped_doctor_is_executable_with_a_shebang():
    """The same rule every other Python entry point here is held to."""
    script = REPO / DOCTOR
    assert script.is_file()
    assert script.read_text(encoding="utf-8").startswith(
        "#!/usr/bin/env python3\n")
    if os.name != "nt":
        assert os.access(script, os.X_OK), f"{DOCTOR} must be executable"


def test_the_doctor_help_names_the_modes():
    result = run_script(REPO / DOCTOR, "--help")
    assert result.returncode == 0, result.stderr
    assert "--root" in result.stdout
    assert "--json" in result.stdout


def test_the_registry_leaves_a_fix_slot_for_the_repair_mode():
    """Every check carries `fix`, and every one of them is None today.

    The slot is the whole reason the checks are a registry rather than one
    long function, and a repair that lands by growing a second mechanism
    beside it would make this file the thing it was written to avoid. The
    assertion is that the slot EXISTS and is empty; the day one is filled,
    this test is what makes somebody say so out loud.
    """
    spec = importlib.util.spec_from_file_location("shape_doctor_under_test",
                                                  REPO / DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CHECKS, "the registry is empty"
    for check in module.CHECKS:
        assert check.id
        assert check.label
        assert check.applies_to
        assert callable(check.run)
        assert check.fix is None, (
            f"{check.id} has a fix; a `--fix` mode prints its plan and asks "
            "before it writes, and this test is where that is said out loud")
    # An id may REPEAT across root kinds -- `naming` asks a different
    # question of a project and of a directory that is not a root -- but two
    # checks with one id on the SAME kind would put two rows under one name
    # in `--json`, where a caller keys by it.
    for kinds in (module.PROJECT, module.FAMILY, module.NOT_A_ROOT):
        applying = [check.id for check in module.CHECKS
                    if kinds in check.applies_to]
        assert len(applying) == len(set(applying)), (
            f"two checks with one id apply to {kinds}")


# --- the fix round on PR #96 ------------------------------------------------
#
# Every test below is one finding from Copilot's review, kept as a test rather
# than as a fixed line: each of them is a remediation that LOOKED right and
# would have failed the person who pasted it.

def test_a_pin_behind_with_no_file_differing_is_still_behind(standard,
                                                             project,
                                                             tmp_path):
    """COMPLIANT is documented as "and the pin names this standard's commit".

    A commit that touches NO copied file leaves every row `unchanged` and
    the pin naming an older revision — and `update-shape.py check` exits 1
    there too, because `apply` would move the pin alone. Reporting COMPLIANT
    would have made the verdict disagree with the sentence that defines it.
    """
    # A file no copy list names, so nothing a project holds can differ.
    ahead = standard_ahead(standard, tmp_path)
    result = doctor(ahead, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"].startswith("COMPLIANT, SHAPE BEHIND"), payload
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING"
    assert row["detail"]["behind"] is True
    assert row["detail"]["pinned"] != row["detail"]["standard"]
    assert "apply` would move the pin alone" in row["reason"]


def test_a_red_validators_next_command_is_runnable(standard, project):
    """It used to print `python3 validate-pins.py in <root>`.

    `in` arrives as an argument and argparse refuses it — a remediation that
    reads like a command, is not one, and fails in front of whoever pasted
    it. Every validator here takes `--root`, so that is what is printed.
    """
    edited = project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# edit\n",
                      encoding="utf-8")
    row = rows_of(doctor(standard, project, "--json"))["pins"]
    assert row["status"] == "FINDING"
    command = row["next"].split("#")[0].split()
    assert "--root" in command, row["next"]
    assert "in" not in command, row["next"]
    # And it runs, and reproduces the finding.
    proc = subprocess.run(command, capture_output=True, text=True,
                          check=False, env={**os.environ,
                                            "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert DRIFT_TARGET in proc.stdout + proc.stderr


def test_the_legs_next_command_is_runnable(standard, project):
    leg = project / "spec"
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "past it"],
                   cwd=str(leg), capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    row = rows_of(doctor(standard, project, "--json"))["legs"]
    command = row["next"].split("#")[0].split()
    # A git line and not a script of the root's (#276): `git -C <root>
    # submodule update --init --recursive -- spec`.
    assert command[:2] == ["git", "-C"], row["next"]
    assert command[3:7] == ["submodule", "update", "--init", "--recursive"], \
        row["next"]
    assert command[-1] == "spec", row["next"]
    proc = subprocess.run(command, capture_output=True, text=True,
                          check=False, env={**os.environ, **GIT_IDENTITY,
                                            "PYTHONDONTWRITEBYTECODE": "1"})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    # And having run it, the leg is back at its pin.
    assert doctor(standard, project).returncode == 0


def test_a_deleted_pinned_agent_file_is_not_an_add(standard, project):
    """`--add` refuses a path the pin already names, by name.

    A deleted `AGENTS-shape.md` is `copy-missing` to `update-shape.py`, not
    `upstream-added`, so the remediation is to restore the bytes — not to
    pass a flag that will be refused for being about a file that is already
    pinned.
    """
    (project / "AGENTS-shape.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["agent-files"]
    assert row["status"] == "FINDING"
    assert row["detail"]["pinned"] == ["AGENTS-shape.md"]
    assert "--add" not in row["next"], row["next"]
    assert "git -C" in row["next"], row["next"]
    assert "checkout --" in row["next"], row["next"]


@WINDOWS_SKIP
def test_a_pinned_copy_kept_as_a_link_is_drifted_by_name(standard, project,
                                                         tmp_path):
    """`AGENTS-shape.md` moved outside the root, a committed symlink in its
    place, with the bytes unchanged (#286).

    `update-shape.py` reads that row as `copy-is-link`, a conflict its
    `apply` refuses: git holds the link, not the bytes the pin's digest
    describes. The doctor names it the way it names `copy-missing` --
    `DRIFTED (1 copy-is-link)` -- rather than reaching a verdict whose
    parenthesis says nothing about the file. Main read through the link and
    called this root COMPLIANT.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    shutil.move(str(project / "AGENTS-shape.md"),
                str(outside / "AGENTS-shape.md"))
    (project / "AGENTS-shape.md").symlink_to(outside / "AGENTS-shape.md")
    commit_all(project, "keep AGENTS-shape.md as a link")

    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "DRIFTED (1 copy-is-link)", payload["verdict"]
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["counts"] == {"copy-is-link": 1,
                                       "unchanged": 10}, row["detail"]
    assert row["detail"]["conflicts"] == ["AGENTS-shape.md"], row["detail"]
    assert "AGENTS-shape.md" in row["reason"], row["reason"]


def keep_as_committed_link(root: Path, linked: str, tmp_path: Path) -> Path:
    """`linked` moved beside the root, a symlink to it left in its place and
    committed, so the link is what git holds. Returns where it points."""
    end = tmp_path / "outside" / Path(linked).name
    end.parent.mkdir(exist_ok=True)
    shutil.move(str(root / linked), str(end))
    (root / linked).symlink_to(end, target_is_directory=end.is_dir())
    commit_all(root, f"keep {linked} as a link")
    return end


def assert_a_linked_record_is_their_finding(result, linked: str,
                                            record: str) -> None:
    """The `shape-currency` row for a root that keeps `record`, or the
    directory above it, as a committed link at `linked` (#286).

    A STATEMENT ABOUT THEIR REPOSITORY. `update-shape.py` refuses to
    re-pin through the link, and the doctor had filed that refusal with
    the ones about THIS checkout of the standard: `CANNOT ANSWER`, exit 3,
    with a `git fetch --all` that changes nothing. It is a finding now:
    `INVALID (shape-currency)`, exit 1, the refusal quoted, and the `why` is
    the refusal's own remedy. It has no NEXT: the remedy is a person's act,
    said and not a command, and a NEXT is one command or nothing (#548).
    """
    payload = json.loads(result.stdout)
    assert (payload["verdict"], payload["exit"]) == (
        "INVALID (shape-currency)", 1), payload["verdict"]
    assert result.returncode == 1, result.stdout + result.stderr
    assert "cannot-answer" not in result.stderr, result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING", row
    assert "environment" not in row["detail"], row["detail"]
    assert row["detail"]["error"] == "update-rewrite-symlink", row["detail"]
    assert (row["detail"]["path"], row["detail"]["link"]) == (
        record, linked), row["detail"]
    assert "REFUSED update-rewrite-symlink: `apply` would rewrite " \
        f"{record}, but {linked} in this root is a symlink" in row["reason"], \
        row["reason"]
    assert row["next"] is None, row
    assert row["why"].startswith(f"replace {linked} with the file or "
                                 "directory it points at"), row["why"]
    assert "run this doctor again" in row["why"], row["why"]
    # Every other row reads THROUGH the link and finds nothing wrong: the
    # verdict is this row's alone.
    red = [key for key, other in rows_of(result).items()
           if other["status"] == "FINDING"]
    assert red == ["shape-currency"], red


@WINDOWS_SKIP
@pytest.mark.parametrize("linked, record", [
    pytest.param("contracts/shape-pin.yaml", "contracts/shape-pin.yaml",
                 id="pin-at-a-link"),
    pytest.param("contracts", "contracts/shape-pin.yaml",
                 id="contracts-directory-link"),
    pytest.param("project.yaml", "project.yaml", id="manifest-at-a-link"),
])
def test_a_pin_or_manifest_kept_as_a_link_is_a_finding_not_cannot_answer(
        standard, project, tmp_path, linked, record):
    """The pin, the `contracts` directory above it, or `project.yaml` kept
    as a committed link, with the bytes unchanged and the pin naming this
    standard's commit. Main read through the link and said COMPLIANT; #286
    made `update-shape.py` refuse the root, and the doctor then answered
    CANNOT ANSWER. Neither is the truth: `apply` cannot re-pin this root
    until the link is replaced, and that is the root's to fix."""
    keep_as_committed_link(project, linked, tmp_path)
    result = doctor(standard, project, "--json")
    assert_a_linked_record_is_their_finding(result, linked, record)


@WINDOWS_SKIP
def test_a_family_manifest_kept_as_a_link_is_a_finding_not_cannot_answer(
        standard, holder, tmp_path):
    """A family holder's manifest is `family.yaml`, and `apply` rewrites it
    as it rewrites an assembly root's `project.yaml`: the doctor asks after
    the manifest of the KIND of root it was pointed at."""
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    keep_as_committed_link(root, "family.yaml", tmp_path)
    result = doctor(standard, root, "--json")
    assert json.loads(result.stdout)["kind"] == "family", result.stdout
    assert_a_linked_record_is_their_finding(result, "family.yaml",
                                            "family.yaml")


#: How the `leg shape files` row spells a copy ON THIS HOST. `cp` is not a
#: program on Windows, it is an alias of `Copy-Item` (Microsoft's own
#: reference: "PowerShell includes the following aliases for `Copy-Item`:
#: ... Windows: `cp`"), so the verb the row prints is a fact about the
#: runner -- and a test that hard-coded `cp ` was a test that could only
#: pass on two of this repository's three CI jobs (#105).
COPY_VERB = "Copy-Item " if os.name == "nt" else "cp "


def powershell_tokens(line: str) -> list[str]:
    """PowerShell's reading of a command line, as far as this row needs it.

    A QUOTE-AWARE PARSER, NOT `str.split()` (Copilot, PR #107). The row's
    own paths are quoted exactly when they need to be, so a checkout at
    `C:\\Users\\Jane Doe\\...` arrives as ONE token `'C:\\Users\\Jane
    Doe\\...'` -- and a test that split on whitespace tore that value in
    half and then failed a correct command. `#` has the same shape of
    answer: it opens a comment where a TOKEN starts and is an ordinary
    character anywhere else, so a path with one in it survives and a
    trailing `# and the rest are RENDERED...` does not. (The row appended
    that note until #277 moved it to its `why`; `RENDERED_NOTE` keeps it.)

    Verbatim `'...'` only, because that is the one quoting `quote_arg`
    emits: nothing inside is expanded and an apostrophe is doubled.
    """
    tokens: list[str] = []
    index, length = 0, len(line)
    while index < length:
        if line[index].isspace():
            index += 1
            continue
        if line[index] == "#":          # a comment, to the end of the line
            break
        if line[index] == "'":
            index += 1
            word = []
            while index < length:
                if line[index] != "'":
                    word.append(line[index])
                    index += 1
                elif line[index:index + 2] == "''":
                    word.append("'")    # a doubled apostrophe is one
                    index += 2
                else:
                    index += 1          # the quotation ends
                    break
            tokens.append("".join(word))
            continue
        start = index
        while index < length and not line[index].isspace():
            index += 1
        tokens.append(line[start:index])
    return tokens


def copied_paths(line: str, platform: str | None = None) -> tuple[str, str]:
    """The source and the target back out of the row's copy line.

    `shlex` on POSIX because that is the reader's own parser there --
    `comments=True` so it drops a trailing `#` note the way `sh` would,
    rather than a naive `split("#")` cutting a path that has one in it. On
    Windows the cmdlet's spelling, read by a parser that knows PowerShell's
    verbatim string; `platform` so either branch can be asserted from either
    host, as `copy_command` itself can be.
    """
    if (os.name if platform is None else platform) != "nt":
        parts = shlex.split(line, comments=True)
        assert parts[0] == "cp", line
        return parts[1], parts[2]
    words = powershell_tokens(line)
    assert words[0] == "Copy-Item", line
    assert words[1] == "-LiteralPath", line
    assert words[3] == "-Destination", line
    return words[2], words[4]


def test_a_missing_rendered_leg_file_is_not_offered_a_cp(standard, project):
    """`templates/<role>-root/AGENTS.md` is full of `{{PLACEHOLDER}}`s.

    A `cp` of it leaves a leg holding literal `{{PROJECT_NAME}}`, which is a
    command that produces an invalid leg — worse than no command at all. The
    verbatim files still get their `cp`, which is the other half.
    """
    (project / "spec" / "AGENTS.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    assert row["status"] == "note"
    assert not row["next"].startswith(COPY_VERB), row["next"]
    # What the file IS is the row's `why`; the NEXT is a command (#277).
    assert "RENDERED" in row["why"], row["why"]

    (project / "spec" / "CLAUDE.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    # `COPY_VERB`, not `cp `: on Windows the row says `Copy-Item`, because
    # `cp` there is that cmdlet's alias and reads `[` as a wildcard (#105).
    assert row["next"].startswith(COPY_VERB), row["next"]
    source, target = copied_paths(row["next"])
    assert Path(source).is_file(), source
    assert target.endswith("CLAUDE.md"), target


#: The two spellings of ONE copy, byte for byte, asserted for BOTH platforms
#: from whichever host runs the suite. The value that makes the difference
#: visible is a `[old]` in a path: `Copy-Item`'s `-Path` is documented
#: "Wildcard characters are permitted", so on Windows those brackets are a
#: character class and not a directory name -- which quoting cannot fix,
#: because quoting says where the argument ENDS and the cmdlet decides how
#: to read what arrived (#105).
#:
#: THE PATHS ARE PURE AND EACH IS ITS OWN PLATFORM'S FLAVOUR. `Path` is the
#: HOST's, so a `/srv/...` fixture rendered `\srv\...` on the Windows runner
#: and broke both `scaffold_command` rows there (job `tests-windows`, run
#: 34594408797, PR #102). `PurePosixPath` and `PureWindowsPath` render the
#: same string on every host. And a genuine `PureWindowsPath` is safe HERE
#: where it was not there, because `copy_command` threads the asked-for
#: `platform` into both of its `quote_arg` calls rather than letting them
#: fall back to the real host's `os.name` -- which is the whole of #103,
#: next door, and is why the `nt` rows below are quoted by PowerShell's
#: rules on Linux and macOS too.
COPY_COMMAND = [
    # The bracket in the TARGET: a project at `<root>/work[old]/Atlas`.
    ("posix",
     PurePosixPath("/srv/openRepoShape/templates/spec-root/CLAUDE.md"),
     PurePosixPath("/srv/work[old]/Atlas/spec/CLAUDE.md"),
     "cp /srv/openRepoShape/templates/spec-root/CLAUDE.md "
     "'/srv/work[old]/Atlas/spec/CLAUDE.md'"),
    ("nt",
     PureWindowsPath(r"C:\openRepoShape\templates\spec-root\CLAUDE.md"),
     PureWindowsPath(r"C:\work[old]\Atlas\spec\CLAUDE.md"),
     r"Copy-Item -LiteralPath C:\openRepoShape\templates\spec-root\CLAUDE.md"
     r" -Destination 'C:\work[old]\Atlas\spec\CLAUDE.md'"),
    # And in the SOURCE: a checkout of the standard at `<root>/shape[2]`,
    # which is the half a fix that only guarded the destination would miss.
    ("posix",
     PurePosixPath("/srv/shape[2]/templates/code-root/.gitignore"),
     PurePosixPath("/srv/Atlas/code/.gitignore"),
     "cp '/srv/shape[2]/templates/code-root/.gitignore' "
     "/srv/Atlas/code/.gitignore"),
    ("nt",
     PureWindowsPath(r"C:\shape[2]\templates\code-root\.gitignore"),
     PureWindowsPath(r"C:\Atlas\code\.gitignore"),
     r"Copy-Item -LiteralPath 'C:\shape[2]\templates\code-root\.gitignore'"
     r" -Destination C:\Atlas\code\.gitignore"),
]


@pytest.mark.parametrize("platform,source,target,expected", COPY_COMMAND)
def test_the_copy_line_is_literal_where_cp_is_a_cmdlet(platform, source,
                                                       target, expected):
    r"""`cp` on Windows is `Copy-Item`, and `-Path` is a PATTERN.

    The row printed one spelling for both platforms. On Windows that word is
    an alias of `Copy-Item`, whose `-Path` parameter is documented "Wildcard
    characters are permitted" -- so `C:\work[old]\Atlas` is read as a
    character class matching `C:\worko`, `C:\workl` or `C:\workd`, and the
    reader gets either `Cannot find path` for a directory that is plainly
    there or a copy out of a sibling that happens to match, silently.
    Quoting cannot reach it: `quote_arg` (#102) decides where the argument
    ends, and this is what the cmdlet does with the argument afterwards.

    `-LiteralPath` is the parameter that means this path -- "used exactly as
    it's typed. No characters are interpreted as wildcards" -- and the
    destination needs no twin, because `-Destination` is documented
    "Supports wildcards: False": it names where the copy lands rather than
    searching for what to copy.

    POSIX IS UNCHANGED AND IS ASSERTED TO BE, on the same values: there `cp`
    is `/bin/cp`, the glob belongs to the shell, and `quote_arg`'s
    single quotes already hand the brackets through intact.
    """
    module = doctor_module(REPO)
    line = module.copy_command(source, target, platform)
    assert line == expected
    # And both paths arrive whole: the bracket is IN the line, not expanded
    # away by whoever quoted it.
    assert str(source) in line, line
    assert str(target) in line, line


#: A path that breaks a naive parser three ways at once -- a space, an
#: apostrophe (doubled inside PowerShell's verbatim string, closed-escaped-
#: reopened by `sh`'s) and a `#`, which opens a comment where a TOKEN starts
#: and is an ordinary character anywhere else. The row appended a real
#: trailing comment of its own when only some of the missing files were
#: copyable, so a reader of these lines had to tell those two apart
#: (Copilot, PR #107). Each row is its own platform's spelling of a path,
#: and both are asserted from whichever host runs the suite.
AWKWARD_COPY = [
    ("posix", "/srv/open Repo'Shape/templates/spec-root/CLAUDE.md",
     "/srv/work #2/Atlas/spec/CLAUDE.md"),
    ("nt", "C:\\Users\\Jane Doe\\shape\\templates\\spec-root\\CLAUDE.md",
     "C:\\work #2\\O'Brien\\spec\\CLAUDE.md"),
]

#: What `check_leg_shape_files` APPENDED, until #277, when some of the
#: missing files are RENDERED per project and only the rest can be copied --
#: a real trailing comment on a real line. The row now prints that sentence
#: as its `why`, on a line of its own, and its NEXT is the copy alone; the
#: note is kept here verbatim so the parser above is still proved to drop a
#: comment without taking a `#` inside a quotation with it.
RENDERED_NOTE = ("   # and the rest are RENDERED per project (placeholders): "
                 "scaffold-project.py writes those, and copying a template "
                 "verbatim would not")


@pytest.mark.parametrize("platform,source,target", AWKWARD_COPY)
def test_the_copy_line_is_read_back_by_the_quoting_it_was_written_with(
        platform, source, target):
    """Round trip: what `copy_command` wrote, `copied_paths` reads.

    The parser is the test suite's, not the product's, and it was
    `str.split()` -- which tears `'C:\\Users\\Jane Doe\\...'` in half at the
    space and then fails a command that was perfectly correct, and truncates
    a path with a `#` in it before the assertion is even made (Copilot, PR
    #107). Both shells' quoting is now read by something that knows it, and
    a trailing comment is dropped without taking a `#` that sits inside a
    quotation with it.
    """
    module = doctor_module(REPO)
    line = module.copy_command(source, target, platform) + RENDERED_NOTE
    # The values really are ones the quoter quotes -- a round trip over two
    # bare words would prove nothing about either parser.
    assert "'" in line, line
    assert copied_paths(line, platform) == (source, target), line


def test_the_copy_line_asked_for_no_platform_is_this_hosts():
    """`platform=None` is every caller in `shape-doctor.py`.

    The argument exists so both spellings are testable from one machine
    (`quote_arg` and `scaffold_command` carry one for the same reason); the
    row itself asks for nothing and must get the shell of the person reading
    the report.
    """
    module = doctor_module(REPO)
    here = "nt" if os.name == "nt" else "posix"
    assert module.copy_command("a b", "c d") == \
        module.copy_command("a b", "c d", here)
    # And the two spellings are not one spelling, or the parametrized
    # assertions above would prove nothing about which host got which.
    assert module.copy_command("a", "b", "nt") != \
        module.copy_command("a", "b", "posix")


def test_the_only_shell_verb_this_file_spells_goes_through_copy_command():
    """The CLASS of the defect, not just the one line that had it.

    Every other remediation `shape-doctor.py` prints is `python3 ...` or
    `git -C ...` -- the same programs, with the same parsing, on both
    platforms. The copy was the one line that named a SHELL's own verb, and
    a shell verb is exactly where the two platforms stop agreeing. So the
    guard is that there is still only one of them in the file and it is
    inside the function that knows both spellings: a future row that reaches
    for a bare `cp`, `mv` or `rm` fails here, with this comment to read,
    rather than on somebody's Windows machine.
    """
    source = (REPO / DOCTOR).read_text(encoding="utf-8")
    tree = ast.parse(source)
    known = [node for node in tree.body
             if isinstance(node, ast.FunctionDef)
             and node.name == "copy_command"]
    assert len(known) == 1, "copy_command is where a shell verb may live"
    first, last = known[0].lineno, known[0].end_lineno
    verbs = re.compile(r"""["'](cp|mv|rm|ln|cat|touch|mkdir|chmod) """)
    outside = [source[:match.start()].count("\n") + 1
               for match in verbs.finditer(source)
               if not first <= source[:match.start()].count("\n") + 1 <= last]
    assert not outside, (
        f"{DOCTOR} spells a bare shell verb at line(s) {outside}; on Windows "
        "those words are cmdlet aliases read by cmdlet rules (#105) -- give "
        "the command a platform branch, as `copy_command` has.")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_copy_line_of_a_bracketed_root_lands_where_it_says(
        standard, tmp_path, scaffolded_here):
    """End to end, with the failure standing next door: `work[old]`.

    A root at `<tmp>/work[old]/Atlas` with a sibling `<tmp>/workd` -- which
    is what the character class `[old]` matches -- and the row's own line
    pasted into `bash -c` exactly as printed. Quoted, the shell hands the
    brackets to `/bin/cp` and the leg's file is restored from the template.
    Unquoted, the same line resolves to the SIBLING and overwrites a file in
    a repository the reader never named, leaving the one they were fixing
    still missing: silent, and in the wrong directory.

    THAT SECOND HALF IS THE WINDOWS CASE, WRITTEN WHERE IT CAN BE RUN. On
    PowerShell the expansion is `Copy-Item`'s own, so quoting does not
    prevent it and only `-LiteralPath` does; this test is the same mistake
    in the one shell this runner has, so what the Windows branch is for is
    a demonstrated failure rather than an argument.
    """
    root = tmp_path / "work[old]" / PROJECT
    root.parent.mkdir(parents=True)
    shutil.copytree(scaffolded_here["clone"], root, symlinks=True)
    decoy = tmp_path / "workd" / PROJECT / "spec"
    decoy.mkdir(parents=True)
    (decoy / "CLAUDE.md").write_text("a file nobody asked to touch\n",
                                     encoding="utf-8")
    missing = root / "spec" / "CLAUDE.md"
    template = standard / "templates" / "spec-root" / "CLAUDE.md"
    missing.unlink()

    row = rows_of(doctor(standard, root, "--json"))["leg-shape-files"]
    assert row["status"] == "note", row
    assert row["next"].startswith("cp "), row["next"]

    pasted = subprocess.run(["bash", "-c", row["next"]], capture_output=True,
                            text=True, check=False)
    assert pasted.returncode == 0, pasted.stdout + pasted.stderr
    assert missing.read_bytes() == template.read_bytes(), row["next"]
    assert (decoy / "CLAUDE.md").read_text(encoding="utf-8") == \
        "a file nobody asked to touch\n", "the quoted line went next door"

    # And the unquoted spelling of the same line is the failure, so the
    # assertions above cannot be passing by accident.
    missing.unlink()
    module = doctor_module(standard)
    quoted = module.quote_arg(missing, "posix")
    assert quoted != str(missing), "a bracketed target needs quoting"
    naive = row["next"].replace(quoted, str(missing))
    assert naive != row["next"], "the target was not quoted in the command"
    broken = subprocess.run(["bash", "-c", naive], capture_output=True,
                            text=True, check=False)
    assert broken.returncode == 0, broken.stdout + broken.stderr
    assert not missing.exists(), (
        "unquoted, `work[old]` must expand to the sibling; if it does not, "
        "this test is proving nothing about the wildcard")
    assert (decoy / "CLAUDE.md").read_bytes() == template.read_bytes(), (
        "the unquoted line is meant to land in the SIBLING -- that is the "
        "whole point of the quoted assertion above")


def test_a_member_on_a_branch_is_reported_and_is_not_a_finding(standard,
                                                               holder,
                                                               tmp_path):
    """The pinned copy is DETACHED in a fresh clone, and the commit alone
    does not say so — so the state is recorded and said.

    IT IS NOT A FINDING, and that is the half Copilot's review asked for and
    this suite refused: `family.py add` itself leaves the member on a
    branch, because `git submodule add` checks one out. A row that failed
    here would fail a holder the standard's own tool had just made.
    """
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    member = root / "members" / FAMILY_MEMBER
    subprocess.run(["git", "checkout", "-q", "-B", "local-work"],
                   cwd=str(member), capture_output=True, check=True)
    result = doctor(standard, root, "--json")
    row = rows_of(result)["members"]
    assert row["status"] == "ok", row
    assert row["detail"]["on_a_branch"] == [f"members/{FAMILY_MEMBER}"], row
    assert row["detail"]["members"][0]["detached"] is False
    assert row["detail"]["members"][0]["head"] == \
        row["detail"]["members"][0]["pin"]
    assert "on a BRANCH rather than detached" in row["reason"]


def test_a_member_detached_at_its_pin_is_recorded_as_detached(standard,
                                                              holder,
                                                              tmp_path):
    """The other direction, so the report above cannot be a constant."""
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    member = root / "members" / FAMILY_MEMBER
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(member),
                          capture_output=True, text=True,
                          check=True).stdout.strip()
    subprocess.run(["git", "checkout", "-q", "--detach", head],
                   cwd=str(member), capture_output=True, check=True)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["status"] == "ok", row
    assert row["detail"]["on_a_branch"] == []
    assert row["detail"]["members"][0]["detached"] is True


def test_an_unrelated_repository_beside_the_holder_is_not_the_member(
        standard, holder, tmp_path):
    """`scripts/siblings.py` asks whether the directory IS this project
    before it touches one, and so does this: a report that counted any clone
    at `../<Project>` would tell somebody their working clone is there when
    it is not."""
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    impostor = base / FAMILY_MEMBER
    impostor.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=impostor)
    (impostor / "README.md").write_text("# not that project\n",
                                        encoding="utf-8")
    commit_all(impostor, "Something else entirely")
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["detail"]["without_working_clone"] == [FAMILY_MEMBER], row
    assert row["detail"]["members"][0]["working_clone"] is None


def member_beside(holder: dict, tmp_path: Path) -> tuple[Path, Path]:
    """A holder in its own directory, with a real CLONE of its member beside
    it — which is the layout `make siblings` leaves behind.

    CLONED, NOT COPIED. These tests used to `copytree` the submodule
    checkout out of `members/`, and the `.git` FILE that git leaves in a
    submodule working tree carries a RELATIVE `gitdir:` into the holder's
    `.git/modules/` — so the copy beside the holder was a directory git
    itself refuses to answer any question about (`fatal: not a git
    repository`). It passed only because the row asked nothing of origin
    (#146). `git clone` from the url the holder mounts the member from is
    both a real clone and the exact thing `siblings.py` does, but for the
    one flag of #544: the member's remote was just pushed, so the clone is
    read through git (`cloned_just_pushed`) and not through its files.
    """
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    remote = holder["base"] / "remotes" / f"{FAMILY_MEMBER}.git"
    return root, cloned_just_pushed(remote, base / FAMILY_MEMBER,
                                    recurse=False)


def test_a_real_working_clone_beside_the_holder_is_counted(standard, holder,
                                                           tmp_path):
    """And the other direction, so the check above cannot pass by refusing
    everything: a clone of the member, beside the holder, IS the clone."""
    root, sibling = member_beside(holder, tmp_path)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["detail"]["without_working_clone"] == [], row
    assert row["detail"]["members"][0]["working_clone"] == sibling.as_posix()
    assert row["detail"]["members"][0]["other_origin"] is None
    # The url it was compared against is the one the holder MOUNTS it from —
    # a bare repository on disk here, which no `https://github.com/...`
    # derived from `repository:` would ever have matched.
    #
    # COMPARED WITH THE SEPARATORS FOLDED, and NOT against the raw bytes of
    # `.gitmodules`: git ESCAPES a backslash when it writes a config value,
    # so a Windows runner has `D:\\a\\...\\IRRS.git` in the file and hands
    # `D:\a\...\IRRS.git` back to the reader — the url is right and the two
    # spellings of it are not the same string.
    mounted = row["detail"]["members"][0]["mounted_from"]
    assert mounted.replace("\\", "/") == \
        str(holder["base"] / "remotes" / f"{FAMILY_MEMBER}.git").replace(
            "\\", "/")
    assert not mounted.startswith("https://github.com/"), mounted


# --- #146: the origin question, which `siblings.py` asks first -------------

def test_a_sibling_with_this_members_id_but_another_origin_is_not_counted(
        standard, holder, tmp_path):
    """THE DEFECT #146 WAS FILED FOR. A fork, or a stale clone of a
    repository that has since been renamed, carries this member's
    `project.yaml` byte for byte and is NOT the working clone: `make
    siblings` calls it `WRONG ORIGIN` and refuses to fetch into it, so a
    report that counted it would disagree with the tool about one directory
    on one disk.
    """
    root, sibling = member_beside(holder, tmp_path)
    elsewhere = str(holder["base"] / "remotes" / f"{FAMILY_NAME}.git")
    git("remote", "set-url", "origin", elsewhere, cwd=sibling)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    entry = row["detail"]["members"][0]
    assert entry["working_clone"] is None, entry
    # Separators folded for the same reason the test above folds them: a
    # Windows runner spells this path with backslashes at both ends of the
    # comparison, and git is free to hand back either.
    assert entry["other_origin"].replace("\\", "/") == \
        elsewhere.replace("\\", "/"), entry
    assert row["detail"]["without_working_clone"] == [FAMILY_MEMBER], row
    # REPORTED, NEVER REFUSED: where somebody keeps a checkout is the
    # workstation's layout, so the verdict is exactly what it is for a
    # member with no clone beside the holder at all.
    assert row["status"] == "ok", row
    assert "is a clone of" in row["reason"], row["reason"]
    assert entry["other_origin"] in row["reason"], row["reason"]
    assert json.loads(doctor(standard, root, "--json").stdout)["verdict"] == \
        "COMPLIANT"


# --- #605: what `make siblings` does, and on what condition ----------------
#
# Since #578 `scripts/siblings.py` asks about the holder's parent folder
# before it looks at any member. The `members` row names the command and
# that condition in STATIC words, and does not test the folder itself: the
# rule is the holder's own, and a second copy of it here would drift.

#: What the `no working clone` note ends with, spelt out here and not
#: imported from the doctor: a test that read the wording back from the thing
#: under test would pass whatever it said.
PLACES_NOTE = (
    "(`make siblings` places them when the holder is in a folder named after "
    "its repository, or in one a link of that name beside it leads to; with "
    "the holder anywhere else it clones nothing and prints the `mv` that "
    "moves it into such a folder; the pinned copy under members/ is "
    "detached by design)")

#: The same for a directory beside the holder that is a clone of another
#: repository.
STRANGER_NOTE = (
    "so it is not counted as its working clone (`make siblings`, from a "
    "holder in a folder named after its repository, calls the same "
    "directory WRONG ORIGIN and leaves it exactly as it is)")


@pytest.mark.parametrize("in_family_folder", [False, True],
                         ids=["any-other-folder", "the-family-folder"])
def test_the_no_working_clone_note_says_when_make_siblings_places_them(
        standard, holder, tmp_path, in_family_folder):
    """THE NOTE IS TRUE OF EVERY HOLDER, so it says WHEN, not that. After
    #578, from a holder whose parent folder is neither named after its
    repository nor reached through a link of that name beside it, `make
    siblings` places nothing (`NOTHING WAS CLONED`, exit 1), and a note that
    said `places them` unconditionally told that holder a thing its next
    command would not do.

    ITS REPOSITORY, NOT THE FAMILY'S NAME: `siblings.py::family_folder_name`
    is the basename of the holder's `repository:`, and `name:` is a display
    name (`family.py init --name`) that may differ, so a note that said "the
    family" sent that reader to the one folder `make siblings` refuses.

    THE SAME BYTES IN BOTH FOLDERS, which is the point: the row states the
    condition and the command that prints the `mv`, and never tests the
    folder (that is the holder's `siblings.py`'s rule, not a second copy of
    it here).
    """
    base = tmp_path / "fam"
    folder = base / FAMILY_NAME if in_family_folder else base
    folder.mkdir(parents=True)
    root = folder / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["status"] == "ok", row
    assert row["detail"]["without_working_clone"] == [FAMILY_MEMBER], row
    assert row["reason"].endswith(
        f"; no working clone beside the holder for {FAMILY_MEMBER} "
        + PLACES_NOTE), row["reason"]
    assert "`make siblings` places them;" not in row["reason"], row["reason"]


def test_the_stranger_note_says_from_which_folder_make_siblings_calls_it(
        standard, holder, tmp_path):
    """The other sentence the row says of `make siblings`: that it calls a
    clone of another repository `WRONG ORIGIN` and leaves it as it is. After
    #578 it asks about the holder's parent folder first and stops before it
    looks at any member, so the sentence holds from a holder in a folder
    named after its repository (not the family's display `name:`) and says
    so."""
    root, sibling = member_beside(holder, tmp_path)
    elsewhere = str(holder["base"] / "remotes" / f"{FAMILY_NAME}.git")
    git("remote", "set-url", "origin", elsewhere, cwd=sibling)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["detail"]["members"][0]["other_origin"] is not None, row
    assert STRANGER_NOTE in row["reason"], row["reason"]
    assert "(`make siblings` calls the same directory" not in row["reason"]
    # It is said before the absence it explains, and the green note follows
    # it on the same row.
    assert PLACES_NOTE in row["reason"], row["reason"]
    assert row["reason"].index(STRANGER_NOTE) < row["reason"].index(
        PLACES_NOTE), row["reason"]


def test_a_sibling_at_the_right_origin_with_another_id_is_not_the_member(
        standard, holder, tmp_path):
    """The `WRONG PROJECT` half, which was already asked and stays asked: a
    repository at the right url is not by itself the project the row
    claims."""
    root, sibling = member_beside(holder, tmp_path)
    manifest = sibling / "project.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace('id: "irrs"',
                                                     'id: "somethingelse"'),
        encoding="utf-8")
    row = rows_of(doctor(standard, root, "--json"))["members"]
    entry = row["detail"]["members"][0]
    assert entry["working_clone"] is None, entry
    # Not "a clone of something else": it never claimed to be this member,
    # so the row says what it said before #146 — there is no working clone.
    assert entry["other_origin"] is None, entry
    assert row["detail"]["without_working_clone"] == [FAMILY_MEMBER], row


def test_an_origin_spelled_scp_where_the_row_is_https_is_the_same_clone(
        standard, holder, tmp_path):
    """NOBODY'S OWN CLONE HAS TO SPELL THE REMOTE THE WAY A MANIFEST DOES.

    `git@github.com:InkRouter/IRRS.git` against a row that records
    `InkRouter/IRRS` is one repository, and a row that compared the two as
    text would have turned this fix from a false positive into a false
    negative — telling a person with a perfectly good working clone that it
    is a clone of something else.
    """
    root, sibling = member_beside(holder, tmp_path)
    git("remote", "set-url", "origin",
        f"git@github.com:{FAMILY_NAME}/{FAMILY_MEMBER}.git", cwd=sibling)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    entry = row["detail"]["members"][0]
    assert entry["working_clone"] == sibling.as_posix(), entry
    assert entry["other_origin"] is None, entry


def test_a_directory_that_is_not_a_clone_at_all_is_not_called_a_stranger(
        standard, holder, tmp_path):
    """A copied submodule checkout — a `.git` FILE whose relative `gitdir:`
    points nowhere — is a directory git answers nothing about. It carries
    this member's manifest, so it is reported as what it is rather than
    counted, and the wording is `siblings.py`'s own `(no origin)`.
    """
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    shutil.copytree(holder["root"] / "members" / FAMILY_MEMBER,
                    base / FAMILY_MEMBER, symlinks=True)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    entry = row["detail"]["members"][0]
    assert entry["working_clone"] is None, entry
    assert entry["other_origin"] == "(no origin)", entry
    assert row["status"] == "ok", row


@pytest.mark.parametrize("tail, counted", [
    (f"{FAMILY_NAME}/{FAMILY_MEMBER}.git", True),
    ("Someone/Fork.git", False),
], ids=["the-members-mirror", "a-stranger"])
def test_a_sibling_origin_not_utf8_is_read_as_make_siblings_reads_it(
        standard, holder, tmp_path, tail, counted):
    """#385, through `--root`: a holder whose member's clone beside it has an
    `origin` that is not UTF-8.

    On the base the `members` row's `origin_url` raised `UnicodeDecodeError`
    and the report ended in a traceback, exit 1. Now the URL is read with
    the byte replaced, as `make siblings` reads it: a mirror whose tail is
    the row's `repository:` IS the working clone, and a stranger's is
    reported with the replacement, printed as `?`, and the verdict is the
    one a holder with no clone beside it gets.
    """
    root, sibling = member_beside(holder, tmp_path)
    git("remote", "remove", "origin", cwd=sibling)
    url = NOT_UTF8 + tail.encode("ascii")
    with_origin(sibling, url)
    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    payload = json.loads(result.stdout)
    assert (payload["verdict"], result.returncode) == ("COMPLIANT", 0), \
        payload
    entry = rows_of(result)["members"]["detail"]["members"][0]
    if counted:
        assert entry["working_clone"] == sibling.as_posix(), entry
        assert entry["other_origin"] is None, entry
    else:
        assert entry["working_clone"] is None, entry
        assert entry["other_origin"] == url.decode("utf-8", "replace"), entry
    text = doctor(standard, root)
    assert text.returncode == 0, text.stdout + text.stderr
    assert "Traceback" not in text.stderr, text.stderr
    assert ("is a clone of ../caf?/Someone/Fork.git" in text.stdout) \
        is not counted, text.stdout


@pytest.mark.parametrize("relative", [False, True],
                         ids=["an-absolute-mount-url", "a-relative-mount-url"])
def test_a_holders_own_origin_not_utf8_is_read_as_make_siblings_reads_it(
        standard, holder, tmp_path, relative):
    """#385, the OTHER route into `origin_url`: the HOLDER'S own `origin`.

    The issue names two callers of `origin_url`. `working_clone` asks it of
    the SIBLING, which the test above pins. `mounted_from` asks it of the
    HOLDER, to resolve a relative `.gitmodules` url against, and it asks
    whatever the url is: the call is an argument of `resolved_remote`, which
    is handed an absolute url too and gives it straight back. So a holder
    cloned from a mirror under a directory named in Latin-1 reached the
    traceback through `mounted_from` with an ASCII `.gitmodules` as well.

    On the base both cases raised `UnicodeDecodeError` out of
    `origin_url`, called from `mounted_from` (the `members` row's own
    reader, before `working_clone` asks anything). Now the holder's URL is
    read with the byte replaced, as `make siblings` reads it, and:
      - an absolute mount url never needed it, so the row answers exactly as
        it does for an ASCII holder, and
      - a relative one is resolved against it, as git does, and the clone
        made from that resolved url is counted as the working clone. The
        `mounted_from` the row prints carries U+FFFD.
    The relative case is the one a lossy read could get WRONG: reading the
    holder's URL as `""` leaves `../IRRS.git` unresolved, which matches no
    sibling, so the member's clone is not counted.
    """
    root, sibling = member_beside(holder, tmp_path)
    git("remote", "remove", "origin", cwd=root)
    with_origin(root, NOT_UTF8 + f"{FAMILY_NAME}.git".encode("ascii"))
    if relative:
        git("config", "-f", str(root / ".gitmodules"),
            f"submodule.members/{FAMILY_MEMBER}.url",
            f"../{FAMILY_MEMBER}.git", cwd=root)
        commit_all(root, "Mount the member by a relative url")
        # The clone git would have made from the url that resolves to: the
        # holder's own directory, `caf\xe9`, with the member's name in it.
        git("remote", "remove", "origin", cwd=sibling)
        with_origin(sibling, NOT_UTF8 + f"{FAMILY_MEMBER}.git".encode("ascii"))
    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    payload = json.loads(result.stdout)
    assert (payload["verdict"], result.returncode) == ("COMPLIANT", 0), \
        payload
    entry = rows_of(result)["members"]["detail"]["members"][0]
    assert entry["working_clone"] == sibling.as_posix(), entry
    assert entry["other_origin"] is None, entry
    if relative:
        assert entry["mounted_from"] == f"../caf\ufffd/{FAMILY_MEMBER}.git", \
            entry
    else:
        # The bare repository the holder's `.gitmodules` names, as the
        # control above compares it: separators folded, since git ESCAPES a
        # Windows backslash on the way into the file.
        assert entry["mounted_from"].replace("\\", "/") == str(
            holder["base"] / "remotes" / f"{FAMILY_MEMBER}.git").replace(
                "\\", "/"), entry
    text = doctor(standard, root)
    assert text.returncode == 0, text.stdout + text.stderr
    assert "Traceback" not in text.stderr, text.stderr


def test_a_credential_in_an_origin_is_not_printed_or_put_in_the_json(
        standard, holder, tmp_path):
    """A REPORT PRINTS WHAT IT FINDS, AND WHAT IT FINDS CAN BE A TOKEN.

    Git permits a credential in a remote url and people do put one there;
    `--json` from this command is pasted into issues and kept as a CI
    artifact. So the origin a row quotes is redacted to `***` and the token
    appears NOWHERE in the output (Codex and Copilot, PR #147).
    """
    root, sibling = member_beside(holder, tmp_path)
    git("remote", "set-url", "origin",
        "https://x-access-token:SUPERSECRET@github.com/Someone/Fork.git",
        cwd=sibling)
    result = doctor(standard, root, "--json")
    entry = rows_of(result)["members"]["detail"]["members"][0]
    assert entry["working_clone"] is None, entry
    assert entry["other_origin"] == \
        "https://***@github.com/Someone/Fork.git", entry
    # Not in the row, and not anywhere else in the report either: the whole
    # of `--json` is what gets pasted, not the one field.
    assert "SUPERSECRET" not in result.stdout, result.stdout
    assert "SUPERSECRET" not in doctor(standard, root).stdout


@pytest.mark.parametrize("holder_origin,sibling_origin", [
    (f"https://mirror.example/team/{FAMILY_NAME}.git",
     f"git@mirror.example:team/{FAMILY_MEMBER}.git"),
    (f"git@mirror.example:team/{FAMILY_NAME}.git",
     f"https://mirror.example/team/{FAMILY_MEMBER}.git"),
])
def test_a_relative_mount_is_resolved_against_the_holders_own_remote(
        standard, holder, tmp_path, holder_origin, sibling_origin):
    """`../Repo.git` IS NOT A REMOTE. It is arithmetic against the
    SUPERPROJECT'S remote — git's own rule, one path component dropped per
    `..` — and git has already done it, into the holder's `.git/config`,
    for the mount that exists.

    THE MIRROR IS THE CASE THAT BITES. This family's remote is not
    `github.com`, so a row that compared the sibling's origin against the
    literal `../IRRS.git` and then against the manifest's `InkRouter/IRRS`
    would match neither and call a perfectly good working clone a stranger
    (Copilot, PR #147). Reading what git resolved is also the only answer
    that cannot DISAGREE with the tool: re-deriving the arithmetic here is
    how a report and `make siblings` come to hold two opinions about one url.

    BOTH SPELLINGS OF THE HOLDER'S REMOTE, and the sibling spelled the other
    way each time, because the two questions compose: git resolves the
    relative url in whatever spelling the holder's remote uses, and
    `same_repository` is what makes that the same repository as the clone.
    """
    root, sibling = member_beside(holder, tmp_path)
    git("remote", "set-url", "origin", holder_origin, cwd=root)
    git("config", "-f", str(root / ".gitmodules"),
        f"submodule.members/{FAMILY_MEMBER}.url", f"../{FAMILY_MEMBER}.git",
        cwd=root)
    # AND `git submodule sync` IS DELIBERATELY NOT RUN. The holder's own
    # `.git/config` still carries the url git cached when it initialized the
    # mount — the bare repository on disk this fixture was built from — so a
    # row that read the cache instead of the tracked declaration would answer
    # with that stale url and this assertion would catch it (Copilot, PR
    # #147). `make siblings` reads the declaration; so does this.
    git("remote", "set-url", "origin", sibling_origin, cwd=sibling)
    entry = rows_of(doctor(standard, root, "--json"))["members"]["detail"][
        "members"][0]
    assert entry["mounted_from"] == \
        f"{holder_origin.rsplit('/', 1)[0]}/{FAMILY_MEMBER}.git", entry
    assert not entry["mounted_from"].startswith(".."), entry
    assert entry["working_clone"] == sibling.as_posix(), entry
    assert entry["other_origin"] is None, entry


def test_a_relative_url_with_no_remote_leaves_the_manifest_the_only_judge(
        standard, holder, tmp_path):
    """A REFERENCE THIS ROW CANNOT RESOLVE CHANGES NOTHING ABOUT THE ANSWER.

    `../Repo.git` on a holder with no remote of its own is not a url: it
    matches nothing, and `family.yaml`'s `repository:` — the other reference
    `verify_sibling` accepts — is then the whole of the question. That is
    exactly the state `scripts/siblings.py` is in for the same holder, which
    is the point: counting a clone BECAUSE the mount url was unresolvable
    would put back the disagreement this change exists to remove, since
    `make siblings` calls a clone from somewhere else `WRONG ORIGIN` whether
    or not the url resolved (Copilot, PR #147).
    """
    root, sibling = member_beside(holder, tmp_path)
    git("config", "-f", str(root / ".gitmodules"),
        f"submodule.members/{FAMILY_MEMBER}.url", f"../{FAMILY_MEMBER}.git",
        cwd=root)
    git("remote", "remove", "origin", cwd=root)
    # Cloned from the repository the row NAMES: counted, on the manifest's
    # spelling alone.
    git("remote", "set-url", "origin",
        f"https://github.com/{FAMILY_NAME}/{FAMILY_MEMBER}.git", cwd=sibling)
    entry = rows_of(doctor(standard, root, "--json"))["members"]["detail"][
        "members"][0]
    assert entry["mounted_from"] == f"../{FAMILY_MEMBER}.git", entry
    assert entry["working_clone"] == sibling.as_posix(), entry
    assert entry["other_origin"] is None, entry

    # And cloned from somewhere else: reported, exactly as `make siblings`
    # would refuse it, rather than waved through because the mount url could
    # not be resolved. A host this suite has never named, because a
    # developer's own `url.<base>.insteadOf` rewrites `https://github.com/`
    # on the way into `.git/config` and the row would then quote a spelling
    # this test never wrote.
    git("remote", "set-url", "origin",
        f"https://elsewhere.example/{FAMILY_NAME}/SomethingElse.git",
        cwd=sibling)
    spelled = git("remote", "get-url", "origin", cwd=sibling).stdout.strip()
    entry = rows_of(doctor(standard, root, "--json"))["members"]["detail"][
        "members"][0]
    assert entry["working_clone"] is None, entry
    assert entry["other_origin"] == spelled, entry


def test_an_unresolvable_reference_does_not_excuse_an_originless_clone(
        standard, holder, tmp_path):
    """AN UNANSWERABLE REFERENCE IS NOT AN UNANSWERABLE CLONE.

    The fallback above says nothing about a directory when the ROW's url
    cannot be resolved — but a directory with no readable origin of its own
    is not a working clone under anybody's definition, and `verify_sibling`
    refuses that state too. Letting the one excuse the other would have made
    a dangling `.git` file count as a clone the moment a family mounted a
    member with a relative url (Copilot, PR #147).
    """
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    shutil.copytree(holder["root"] / "members" / FAMILY_MEMBER,
                    base / FAMILY_MEMBER, symlinks=True)
    git("config", "-f", str(root / ".gitmodules"),
        f"submodule.members/{FAMILY_MEMBER}.url", f"../{FAMILY_MEMBER}.git",
        cwd=root)
    git("remote", "remove", "origin", cwd=root)
    entry = rows_of(doctor(standard, root, "--json"))["members"]["detail"][
        "members"][0]
    assert entry["mounted_from"] == f"../{FAMILY_MEMBER}.git", entry
    assert entry["working_clone"] is None, entry
    assert entry["other_origin"] == "(no origin)", entry


def test_a_stranger_is_reported_even_when_a_pinned_copy_also_fails(
        standard, holder, tmp_path):
    """THE RED PATH SAYS IT TOO, AND SAYS IT IS NOT THE FINDING.

    A holder with one member checked out away from its pin returns the
    finding row and used to say nothing about the directory beside it — so
    a person would fix the mount, re-run, and only then hear about a clone
    that had been the wrong one all along (Codex, PR #147).
    """
    root, sibling = member_beside(holder, tmp_path)
    elsewhere = str(holder["base"] / "remotes" / f"{FAMILY_NAME}.git")
    git("remote", "set-url", "origin", elsewhere, cwd=sibling)
    manifest = root / "family.yaml"
    # The sha THIS ROW reads, rather than the first 40-hex string in the
    # file: a family manifest carries the shape's pin as well, and moving
    # that one would prove nothing about a member.
    pinned = rows_of(doctor(standard, root, "--json"))["members"]["detail"][
        "members"][0]["pin"]
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(pinned, "0" * 40),
        encoding="utf-8")
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["status"] == "FINDING", row
    assert "checked out at" in row["reason"], row["reason"]
    assert "though it is not what fails this row" in row["reason"], \
        row["reason"]
    assert "is a clone of" in row["reason"], row["reason"]


def test_the_doctor_and_siblings_run_ONE_definition_of_one_repository(
        siblings):
    """THE SAME FUNCTION OBJECT, ASSERTED BY IDENTITY, THEN HELD TO A TABLE.

    `shape-doctor.py`'s `members` row REPORTS whether the directory beside a
    holder is the member's working clone and `make siblings` REFUSES to fetch
    into it when it is not, and until #155 each answered out of its own copy
    of the rule -- the doctor's in `scripts/shape_materialize.py`, the tool's
    in `templates/family-root/scripts/siblings.py`. What held them together
    was a PARITY test over this table: the right instrument for two copies and
    the wrong one for a rule that should have one, because it can only ever
    say the two have not drifted YET and can never say that either is right.
    The rule is one function in `scripts/repo_shape.py` now, which both files
    import, so the first assertions here are that the names ARE that function
    and the table carries the ANSWER each row must get.

    THE CASE ROWS ARE #149'S RULE, the one behaviour the consolidation
    deliberately changed: a remote that names a HOST compares
    case-insensitively because GitHub treats an owner and a name that way, and
    a FILESYSTEM PATH does not, because `/srv/mirrors/IRRS.git` and
    `/srv/mirrors/irrs.git` are two different bare repositories on a
    case-sensitive host -- which is precisely how this suite's own fixtures,
    and any mirror-based family, mount their members. A RELATIVE path (`./`,
    `../`) is a path for the same reason.

    AND THE TRAILING `owner/repo` FALLBACK IS A FORGE QUESTION AND ONLY A
    FORGE QUESTION (#157). A mirror at `/srv/mirrors/InkRouter/IRRS.git` is
    matched against the row's bare `InkRouter/IRRS`, which is a name somebody
    typed into a manifest and is case-insensitive at the forge (Copilot and
    Codex, PR #156); TWO PATHS must be EQUAL, because `/srv/a/IRRS.git` and
    `/other/a/IRRS.git` are two bare repositories under two roots and the
    prefix the tail throws away is the only thing that says so.
    """
    spec = importlib.util.spec_from_file_location(
        "shape_doctor_remote_rule", REPO / DOCTOR)
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    assert doctor.same_repository is repo_shape.same_repository
    assert siblings.same_repository is repo_shape.same_repository
    assert doctor.resolved_remote is repo_shape.resolved_remote
    assert siblings.join_remote is repo_shape.join_remote
    assert doctor.redacted is repo_shape.redacted
    assert doctor.remote_local_path is repo_shape.remote_local_path
    assert siblings.remote_local_path is repo_shape.remote_local_path

    pairs = [
        # The same repository, spelled every way a human or a tool spells it
        ("https://github.com/Org/Repo.git", "https://github.com/Org/Repo",
         True),
        ("git@github.com:Org/Repo.git", "https://github.com/Org/Repo.git",
         True),
        ("ssh://git@github.com/Org/Repo.git", "git@github.com:Org/Repo", True),
        ("https://github.com/Org/Repo/", "https://github.com/Org/Repo.git",
         True),
        # A manifest's bare `Org/Repo`, which is matched by its tail
        ("https://github.com/Org/Repo.git", "Org/Repo", True),
        ("git@github.com:Org/Repo.git", "Org/Repo", True),
        # A bare repository on disk, which is what this suite clones from
        ("file:///srv/mirrors/Repo.git", "/srv/mirrors/Repo.git", True),
        ("/srv/mirrors/Repo.git/", "/srv/mirrors/Repo", True),
        # A HOST FOLDS CASE (#149): the owner, the name and the host itself,
        # through every spelling, because that is what the forge does
        ("https://GitHub.com/Org/Repo", "https://github.com/org/repo", True),
        ("https://GitHub.com/Org/Repo.git", "https://github.com/org/repo",
         True),
        ("git@GitHub.com:Org/Repo.git", "ssh://git@github.com/org/repo", True),
        ("Org/Repo", "org/repo", True),
        # A MIRROR ON DISK IS STILL MATCHED AGAINST THE MANIFEST'S BARE ROW
        # by its trailing `owner/repo` -- the InkRouter estate's own layout,
        # and the reason the tail comparison folds case whenever either side
        # is a forge name rather than a directory (Copilot, PR #156)
        ("/srv/mirrors/InkRouter/IRRS.git", "InkRouter/IRRS", True),
        ("/srv/mirrors/inkrouter/irrs.git", "InkRouter/IRRS", True),
        ("InkRouter/IRRS", "/srv/mirrors/InkRouter/IRRS.git", True),
        ("../InkRouter/IRRS.git", "InkRouter/IRRS", True),
        # ...and the tail still has to be the RIGHT two components
        ("/srv/mirrors/InkRouter/Other.git", "InkRouter/IRRS", False),
        # A PATH DOES NOT (#149), on every platform, deliberately: Windows and
        # macOS filesystems are case-INsensitive by default, and a report that
        # changed its answer with the machine it ran on would be worse than
        # one that is strict everywhere
        ("/srv/mirrors/IRRS.git", "/srv/mirrors/irrs.git", False),
        ("file:///srv/mirrors/IRRS.git", "file:///srv/mirrors/irrs.git",
         False),
        ("D:\\remotes\\Fam.git", "d:\\remotes\\fam.git", False),
        # A RELATIVE path is a path too -- `../mirrors/Fam.git` is as much on
        # a disk as `/srv/mirrors/Fam.git`, and git requires the `./` or
        # `../` of anybody who means one (Copilot and Codex, PR #156)
        ("../IRRS.git", "../irrs.git", False),
        ("../mirrors/Repo.git", "../mirrors/repo.git", False),
        # ...including through the tail, where two paths compare strictly
        ("/srv/mirrors/InkRouter/IRRS.git", "/srv/mirrors/inkrouter/irrs.git",
         False),
        # ...and a path still matches ITSELF, however it is spelled
        ("D:\\remotes\\Fam.git", "D:/remotes/Fam.git", True),
        ("/srv/mirrors/IRRS.git", "file:///srv/mirrors/IRRS.git", True),
        ("../mirrors/Repo.git", "../mirrors/Repo", True),
        # ...including the WINDOWS FILE URL, which carries an empty authority
        # AND a drive, so taking `file://` off it leaves a `/` that belongs
        # to the url and not to the path (Copilot, PR #160)
        ("file:///D:/mirrors/IRRS.git", "D:\\mirrors\\IRRS.git", True),
        ("file:///D:/mirrors/IRRS.git", "D:/mirrors/IRRS.git", True),
        ("file:///D:/mirrors/IRRS.git", "D:\\mirrors\\Other.git", False),
        # ...and ONLY the url's `/` comes off, because a remote with no
        # scheme never had one: `/D:/mirrors/IRRS.git` as a PATH is a
        # directory called `D:` under a POSIX root, which is not the Windows
        # drive of the same three characters (Copilot, PR #160)
        ("/D:/mirrors/IRRS.git", "D:/mirrors/IRRS.git", False),
        ("/D:/mirrors/IRRS.git", "file:///D:/mirrors/IRRS.git", False),
        # TWO PATHS ARE ONE REPOSITORY ONLY WHEN THEY ARE THE SAME PATH
        # (#157). The tail fallback threw the prefix away, and for a path the
        # prefix is the whole of what tells two bare repositories apart
        ("/srv/a/IRRS.git", "/other/a/IRRS.git", False),
        ("/srv/mirrors/InkRouter/IRRS.git", "/elsewhere/InkRouter/IRRS.git",
         False),
        ("file:///srv/a/IRRS.git", "/other/a/IRRS.git", False),
        ("../a/IRRS.git", "../../other/a/IRRS.git", False),
        ("D:\\a\\IRRS.git", "D:\\other\\a\\IRRS.git", False),
        # ...while a MIRROR or an ENTERPRISE HOST is what the tail was
        # written for, and #157 leaves it exactly where it was: the two
        # trailing components ARE a forge repository's whole identity
        ("https://github.com/Org/Repo.git", "https://gitlab.example/Org/Repo",
         True),
        ("git@github.com:Org/Repo.git", "https://forge.example/Org/Repo.git",
         True),
        # And the ones that are NOT one repository
        ("https://github.com/Other/Repo.git", "Org/Repo", False),
        ("https://github.com/Org/Other.git", "https://github.com/Org/Repo",
         False),
        ("https://github.com/Org/Repo.git", "", False),
        ("", "Org/Repo", False),
        ("/srv/mirrors/Other.git", "/srv/mirrors/Repo.git", False),
    ]
    for one, two, expected in pairs:
        assert repo_shape.same_repository(one, two) is expected, (one, two)
    # And the table is not all one answer, or it would prove nothing about the
    # function it is asked of.
    assert {expected for _, _, expected in pairs} == {True, False}

    # THE OTHER HALF OF THE SHARED RULE: git's arithmetic for a relative
    # submodule url, which `mounted_from` applies to the tracked declaration
    # and `siblings.py::clone_url` applies before it clones. The same table,
    # against the same one function, now with the string each row must
    # produce -- a url a person reads off a report and a url a tool fetches
    # from should not even be spelled differently.
    relative = [
        ("https://mirror.example/team/Fam.git", "../IRRS.git",
         "https://mirror.example/team/IRRS.git"),
        ("git@mirror.example:team/Fam.git", "../IRRS.git",
         "git@mirror.example:team/IRRS.git"),
        ("ssh://git@host/org/Fam.git", "../sub/IRRS.git",
         "ssh://git@host/org/sub/IRRS.git"),
        ("/srv/mirrors/Fam.git", "../IRRS.git", "/srv/mirrors/IRRS.git"),
        ("file:///srv/mirrors/Fam.git", "../IRRS.git",
         "file:///srv/mirrors/IRRS.git"),
        # A Windows remote, which has no `/` in it at all -- the walk that
        # split on one alone appended to the whole string (`siblings.py`,
        # PR #79), and this is the assertion that keeps it fixed.
        ("D:\\a\\remotes\\Fam.git", "../IRRS.git",
         "D:\\a\\remotes\\IRRS.git"),
        # A `..` too many, which consumes nothing rather than eating a
        # scheme or an scp host
        ("https://host/Fam.git", "../../../IRRS.git",
         "https://host/IRRS.git"),
        ("git@host:Fam.git", "../IRRS.git", "git@host:Fam.git/IRRS.git"),
        ("/Fam.git", "../IRRS.git", "/IRRS.git"),
        ("https://host/a/b/Fam.git", "./IRRS.git",
         "https://host/a/b/Fam.git/IRRS.git"),
    ]
    for base, url, expected in relative:
        assert repo_shape.join_remote(base, url) == expected, (base, url)
        # And the wrapper makes the same two choices `resolve_relative`
        # does: an absolute url is handed straight back, and so is a
        # relative one with no remote to resolve it against.
        assert repo_shape.resolved_remote(url, base) == expected, (base, url)
    assert repo_shape.resolved_remote("../IRRS.git", "") == "../IRRS.git"
    assert repo_shape.resolved_remote(
        "https://host/IRRS.git", "https://host/x") == "https://host/IRRS.git"


def test_a_port_and_githubs_ssh_host_are_not_part_of_a_remotes_key():
    """`remote_key` TAKES A PORT, AND `ssh.github.com`, OFF THE HOST (#190).

    `ssh://git@github.com:22/Acme/Widget.git`, and
    `ssh://git@ssh.github.com:443/Acme/Widget.git` as GitHub documents SSH
    over the HTTPS port, are the scp `git@github.com:Acme/Widget.git`
    reached another way, and keyed as `github.com/22/acme/widget`.
    `same_repository`'s forge-tail match hid that for an `Owner/Repo`, but
    not for a repository at a host's top level, and `adopt-project.py`
    compares keys and nothing else, so it refused a source cloned that way.
    """
    scp = repo_shape.remote_key("git@github.com:Acme/Widget.git")
    for url in ("ssh://git@github.com:22/Acme/Widget.git",
                "ssh://git@ssh.github.com:443/Acme/Widget.git",
                "ssh://git@SSH.GitHub.com:443/Acme/Widget.git",
                "https://github.com:443/Acme/Widget.git",
                "https://x-access-token:token@github.com:443/Acme/Widget.git",
                "git@ssh.github.com:Acme/Widget.git"):
        assert repo_shape.remote_key(url) == scp, url
    assert repo_shape.same_repository("ssh://git@host:2222/Repo.git",
                                      "git@host:Repo.git")
    # ...and nothing that is not a port: the scp spelling has none, so its
    # `22` is a path component; a drive's colon carries no digits; and
    # another repository, or another host, is still another.
    for url in ("git@github.com:22/Acme/Widget.git",
                "ssh://git@github.com:22/Acme/Other.git",
                "ssh://git@gitlab.com:22/Acme/Widget.git"):
        assert repo_shape.remote_key(url) != scp, url
    assert repo_shape.remote_key("file:///E:/mirrors/Widget.git") \
        == repo_shape.remote_key("E:\\mirrors\\Widget.git")


def test_a_symlinked_prefix_is_ONE_directory_to_both_callers(tmp_path,
                                                             siblings):
    """THE PREFIX CASE #157 MOVED OUT OF THE RULE AND INTO THE CALLERS.

    Two filesystem paths are one repository only when they are the SAME path
    now, which is what stops `/srv/a/IRRS.git` and `/other/a/IRRS.git` being
    one -- and, left there, it would also stop one directory reached through
    a SYMLINK being one. `/var/folders/...` and `/private/var/folders/...`
    are two spellings of the same temporary directory on macOS, this suite's
    own fixtures reach one through both, and the tail match is what made the
    doctor and `make siblings` agree about it before #157.

    ONLY A MACHINE CAN ANSWER THAT, so `scripts/repo_shape.py` does not:
    nothing in it may touch a disk, which is what lets
    `tests/test_windows_paths.py` ask the Windows questions from Linux. The
    resolution belongs to the two callers that HAVE a disk, as
    `same_repository_here` -- the same function in both, asking the STRING
    rule first and the disk only when it has said no, so the disk can add an
    answer and never take one away.

    THE SYMLINK IS A REAL ONE, so the question is asked wherever one can be
    made rather than only on the macOS runner where the estate would notice.
    """
    real = tmp_path / "private" / "remotes"
    real.mkdir(parents=True)
    bare = real / "IRRS.git"
    bare.mkdir()
    link = tmp_path / "var"
    try:
        # `target_is_directory` is ignored on POSIX and is what makes this a
        # DIRECTORY symlink on Windows; without it Windows builds a file
        # symlink that `link/remotes` cannot be walked through, and the test
        # would fail there rather than ask its question (Copilot, PR #160).
        os.symlink(tmp_path / "private", link, target_is_directory=True)
    except (AttributeError, NotImplementedError, OSError) as exc:
        # Windows needs Developer Mode or an elevated shell to make one, and
        # a runner without either is not a reason to fail: the POSIX legs of
        # CI -- macOS above all, where this case is real -- do run it.
        pytest.skip(f"this platform cannot create a symlink here: {exc}")
    through_link = str(link / "remotes" / "IRRS.git")

    spec = importlib.util.spec_from_file_location(
        "shape_doctor_same_repository_here", REPO / DOCTOR)
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    assert doctor.remote_local_path is repo_shape.remote_local_path
    assert siblings.remote_local_path is repo_shape.remote_local_path

    # THE RULE ITSELF SAYS NO, and that is the point: it compares strings,
    # and these are two of them.
    assert repo_shape.same_repository(through_link, str(bare)) is False
    for tool in (doctor, siblings):
        name = tool.__name__
        # ...the machine says yes, in either order, and through the `file://`
        # spelling of the same directory. THE THIRD SLASH IS THE POINT ON
        # WINDOWS (Copilot, PR #160): a file url's authority is empty, so a
        # drive-letter path is `file:///C:/...` and `"file://" + path` would
        # build `file://C:/...` -- a url with `C:` for an authority, which is
        # not the spelling `_remote_body`'s fold is about, and this assertion
        # would then pass on Windows without exercising it at all.
        assert tool.same_repository_here(through_link, str(bare)) is True, name
        assert tool.same_repository_here(str(bare), through_link) is True, name
        as_file_url = "file:///" + through_link.replace("\\", "/").lstrip("/")
        assert as_file_url.startswith("file:///"), as_file_url
        assert tool.same_repository_here(as_file_url, str(bare)) is True, name
        # ...and every answer that does not need a disk is exactly the
        # string rule's, which is what "first, and only then" means: a
        # remote that names no path here, a relative one, a path that is not
        # on this disk, and two directories that really are two
        for one, two in (("https://github.com/InkRouter/IRRS.git",
                          "InkRouter/IRRS"),
                         ("git@github.com:InkRouter/IRRS.git", "irrs.git"),
                         ("../remotes/IRRS.git", str(bare)),
                         (str(tmp_path / "nowhere" / "IRRS.git"), str(bare)),
                         (through_link, str(real / "Other.git")),
                         ("", "InkRouter/IRRS")):
            assert tool.same_repository_here(one, two) is \
                repo_shape.same_repository(one, two), (name, one, two)


def test_working_clone_and_verify_sibling_ACCEPT_a_symlinked_mirror(
        tmp_path, siblings):
    """THE TWO CALLERS THEMSELVES, OVER THE TWO SHAPES A SYMLINK MAKES.

    `same_repository_here` has exactly two callers and this is the test of
    THEM (Copilot, PR #160): either could resolve one side and not the other,
    or ask the raw strings and nothing else, and a test that only called the
    helper would pass through all of it.

    THE TWO SHAPES PULL IN OPPOSITE DIRECTIONS, which is why both are here.
    A mirror reached through a symlinked PREFIX must be ACCEPTED, and only
    the disk can say so -- `/var/folders/...` and `/private/var/folders/...`
    are one directory on macOS, and this suite's own fixtures reach one
    through both. A mirror that IS a symlink onto a storage path whose own
    tail is a serial number must be accepted too, through the row's
    `repository: InkRouter/IRRS` -- a FORGE name, matched by the origin's
    tail -- so the origin reaches that fallback exactly as git reported it
    and resolving it first would throw the name away (Codex, PR #160).
    """
    spec = importlib.util.spec_from_file_location(
        "shape_doctor_symlinked_mirror", REPO / DOCTOR)
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)

    prefix = tmp_path / "A"
    (prefix / "pool").mkdir(parents=True)
    git("init", "--bare", str(prefix / "pool" / f"{FAMILY_MEMBER}.git"),
        cwd=tmp_path)
    serial = tmp_path / "B"
    (serial / "storage").mkdir(parents=True)
    (serial / "mirrors" / FAMILY_NAME).mkdir(parents=True)
    git("init", "--bare", str(serial / "storage" / "uuid-123.git"),
        cwd=tmp_path)
    try:
        # Both targets are DIRECTORIES -- a mirror tree and a bare repository
        # -- and Windows needs to be told so or it writes a file symlink
        # neither of them can be reached through (Copilot, PR #160).
        os.symlink(prefix, tmp_path / "A-link", target_is_directory=True)
        os.symlink(serial / "storage" / "uuid-123.git",
                   serial / "mirrors" / FAMILY_NAME / f"{FAMILY_MEMBER}.git",
                   target_is_directory=True)
    except (AttributeError, NotImplementedError, OSError) as exc:
        pytest.skip(f"this platform cannot create a symlink here: {exc}")

    row = {"project": FAMILY_MEMBER, "id": "7c9f1b2d",
           "repository": f"{FAMILY_NAME}/{FAMILY_MEMBER}"}
    cases = [
        # THE PREFIX CASE: the clone was made through the symlink and the
        # mount names the directory it points at. The row's `repository:`
        # cannot rescue this one -- the mirror is in a `pool/`, not under
        # `InkRouter/` -- so only the resolved comparison can accept it.
        ("through a symlinked prefix",
         str(tmp_path / "A-link" / "pool" / f"{FAMILY_MEMBER}.git"),
         str(prefix / "pool" / f"{FAMILY_MEMBER}.git")),
        # THE SERIAL CASE: the mirror IS the symlink, its target's tail is a
        # storage id, and the mount names a path that is not here at all.
        # Only the row's `repository:` can accept this one, and only if the
        # origin reaches it unresolved.
        ("onto a storage path",
         str(serial / "mirrors" / FAMILY_NAME / f"{FAMILY_MEMBER}.git"),
         str(serial / "elsewhere" / f"{FAMILY_MEMBER}.git")),
    ]
    for index, (what, origin, mount) in enumerate(cases):
        work = tmp_path / f"work-{index}" / FAMILY_MEMBER
        work.mkdir(parents=True)
        git("init", cwd=work)
        git("remote", "add", "origin", origin, cwd=work)
        (work / "project.yaml").write_text(
            "kind: project-manifest\nid: 7c9f1b2d\n"
            f"name: {FAMILY_MEMBER}\n", encoding="utf-8")

        assert doctor.working_clone(work, row, mount) == (work.as_posix(),
                                                          None), what
        sibling = siblings.Sibling(FAMILY_MEMBER, work)
        assert siblings.verify_sibling(
            row, work, mount, row["repository"], sibling) is True, what
        assert sibling.state == "?", what

        # ...and a clone of something else at the same path is still refused
        # by both, so this is not a test that accepts everything
        git("remote", "set-url", "origin",
            str(tmp_path / "stranger" / "Other.git"), cwd=work)
        assert doctor.working_clone(work, row, mount)[0] is None, what
        stranger = siblings.Sibling(FAMILY_MEMBER, work)
        assert siblings.verify_sibling(
            row, work, mount, row["repository"], stranger) is False, what
        assert stranger.state == "WRONG ORIGIN", what


def test_working_clone_and_verify_sibling_agree_on_a_non_utf8_origin(
        tmp_path, siblings):
    """#385: AN ORIGIN THAT IS NOT UTF-8, ASKED OF BOTH CALLERS.

    `siblings.py::git_text` reads `origin` with `errors="replace"`, so a
    clone of a mirror under a directory named in Latin-1 is `make siblings`'
    member clone by the row's `repository:` tail, and a clone of something
    else under it is `WRONG ORIGIN`. On the base `working_clone` raised
    `UnicodeDecodeError` for both. The issue's draft would have read the URL
    as `""`, which calls the first one `(no origin)` and no working clone:
    the two tools disagreeing about one directory, which #146 removed. So
    the doctor reads it as `make siblings` does, and quotes the stranger's
    URL with the replacement character in it.
    """
    spec = importlib.util.spec_from_file_location(
        "shape_doctor_not_utf8_origin", REPO / DOCTOR)
    doctor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(doctor)
    row = {"project": FAMILY_MEMBER, "id": "7c9f1b2d",
           "repository": f"{FAMILY_NAME}/{FAMILY_MEMBER}"}
    mount = str(tmp_path / "elsewhere" / f"{FAMILY_MEMBER}.git")
    cases = [
        ("a mirror whose tail is the row's",
         f"{FAMILY_NAME}/{FAMILY_MEMBER}.git".encode("ascii"), True),
        ("a stranger", b"Someone/Fork.git", False),
    ]
    for index, (what, tail, accepted) in enumerate(cases):
        work = tmp_path / f"work-{index}" / FAMILY_MEMBER
        work.mkdir(parents=True)
        git("init", "-q", cwd=work)
        (work / "project.yaml").write_text(
            "kind: project-manifest\nid: 7c9f1b2d\n"
            f"name: {FAMILY_MEMBER}\n", encoding="utf-8")
        url = NOT_UTF8 + tail
        with_origin(work, url)
        read = url.decode("utf-8", "replace")
        assert doctor.origin_url(work) == read, what

        sibling = siblings.Sibling(FAMILY_MEMBER, work)
        assert siblings.verify_sibling(
            row, work, mount, row["repository"], sibling) is accepted, what
        assert doctor.working_clone(work, row, mount) == (
            (work.as_posix(), None) if accepted else (None, read)), what


# --- the adversarial review on #96 ------------------------------------------

def test_a_leg_file_the_standard_GAINED_is_reported_and_never_invalid(
        standard, tmp_path):
    """THE DEFECT THIS ROW WAS FAILING LIVE ESTATES WITH.

    `templates/spec-root/.gitignore` entered the standard at `be488ed`,
    AFTER InkRouter's services were scaffolded — so every project cut before
    that commit was told `INVALID (leg-shape-files)` by this command while
    `validate-manifest.py`, `validate-pins.py` and `update-shape.py` were
    all green on it. No pin names a leg file and no validator asserts one;
    the shape-currency row cannot even report it, because a leg file has no
    `files:` row to be `upstream-added` under.

    THE SUITE WAS BLIND TO IT because `standard` is this checkout and the
    fixture project therefore always had every leg file the current
    templates carry. So this test builds the real sequence: a standard
    WITHOUT the file, a project scaffolded from it, and then the file
    added — which is history as it actually happened.
    """
    before = tmp_path / "standard-before"
    shutil.copytree(standard, before, symlinks=True)
    gitignore = before / "templates" / "spec-root" / ".gitignore"
    kept = gitignore.read_bytes()
    gitignore.unlink()
    commit_all(before, "A standard whose spec template has no .gitignore")

    base = tmp_path / "cut-before"
    base.mkdir()
    scaffold(before, base, PROJECT)
    root = base / "work" / PROJECT
    assert not (root / "spec" / ".gitignore").exists()

    gitignore.write_bytes(kept)
    commit_all(before, "The standard gains templates/spec-root/.gitignore")

    result = doctor(before, root, "--json")
    payload = json.loads(result.stdout)
    rows = rows_of(result)
    assert rows["leg-shape-files"]["status"] == "note", rows["leg-shape-files"]
    assert ".gitignore absent" in rows["leg-shape-files"]["reason"]
    assert "INVALID" not in payload["verdict"], payload["verdict"]
    assert payload["verdict"].startswith("COMPLIANT"), payload["verdict"]
    assert result.returncode != 1 or "SHAPE BEHIND" in payload["verdict"], (
        "the only thing left to report is the pin, not the leg file")


def test_a_missing_leg_file_alone_is_compliant_exit_zero(standard, project):
    """And with the pin naming this very standard, it is plain COMPLIANT."""
    (project / "spec" / ".gitignore").unlink()
    result = doctor(standard, project, "--json")
    payload = json.loads(result.stdout)
    assert result.returncode == 0, result.stdout + result.stderr
    assert payload["verdict"] == "COMPLIANT"
    assert rows_of(result)["leg-shape-files"]["status"] == "note"


def test_a_rendered_root_agent_file_is_a_note_not_a_finding(standard,
                                                            project):
    """The same rule, one file along. `AGENTS.md` at the root is RENDERED
    and pinned by nothing, so its absence is nobody's assertion; the PINNED
    `AGENTS-shape.md` stays a FINDING, and `validate-pins.py` agrees."""
    (project / "AGENTS.md").unlink()
    result = doctor(standard, project, "--json")
    row = rows_of(result)["agent-files"]
    assert row["status"] == "note", row
    assert row["detail"]["pinned"] == []
    assert result.returncode == 0, result.stdout
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"


def test_shape_behind_names_the_pin_when_no_file_differs(standard, project,
                                                         tmp_path):
    """The parenthetical exists to say WHAT moved.

    On the no-file-differs branch the counts are zero by construction, so
    `(0 upstream-changed, 0 upstream-added)` under the words SHAPE BEHIND
    was a clause contradicting its own verdict — and it fired on both real
    estates on this machine, which makes it the common case.
    """
    ahead = standard_ahead(standard, tmp_path)
    result = doctor(ahead, project, "--json")
    payload = json.loads(result.stdout)
    assert result.returncode == 1
    assert payload["verdict"].startswith("COMPLIANT, SHAPE BEHIND (pin ")
    assert "no copied file differs" in payload["verdict"]
    assert "upstream-changed" not in payload["verdict"], payload["verdict"]
    assert rows_of(result)["shape-currency"]["detail"]["behind_pin_only"] \
        is True


def test_shape_behind_names_the_counts_when_a_file_differs(
        advanced_standard, project):
    """And the other branch keeps the counts, which are true there."""
    payload = json.loads(doctor(advanced_standard, project,
                                "--json").stdout)
    assert payload["verdict"] == \
        "COMPLIANT, SHAPE BEHIND (1 upstream-changed, 0 upstream-added)"


# --- the lane a printed `apply` offers (#111) -------------------------------
#
# `update-shape.py apply --branch` writes its own commit, and the
# lane-collision protocol wants the `Lane:` line on that commit as much as on
# the pull request -- so a row that printed the apply without it handed
# somebody a command whose result they then had to amend by hand. Four
# InkRouter re-pins landed on 2026-09-11 with no trailer at all, each run
# exactly as a printed line said (#111).


def behind_row(standard, root, lane: str | None):
    """The `shape-currency` row of a SHAPE BEHIND project, run with or
    without a lane in the environment.

    `LANES_LANE` is set to the empty string rather than left alone for the
    no-lane case: the suite inherits the environment it was launched in, and
    a runner that happened to be inside a lane would otherwise flip the
    assertion that today's line is unchanged.
    """
    result = run_script(standard / DOCTOR, "--root", str(root), "--json",
                        env={"LANES_LANE": "" if lane is None else lane})
    assert result.returncode == 1, result.stdout + result.stderr
    return rows_of(result)["shape-currency"]


def test_the_apply_a_behind_row_prints_carries_the_lane_when_one_is_set(
        advanced_standard, project):
    """The copied-file branch of the row: `--trailer` last, after
    `--branch`, quoted whole so the paste survives the space in it.

    THE `apply` IS THE ROW'S `why` since #277 -- the words that followed
    `   # ` on its NEXT line -- and the trailer is read there. The NEXT, the
    `check`, is the same line with or without a lane."""
    plain = behind_row(advanced_standard, project, None)
    laned = behind_row(advanced_standard, project, LANE)
    assert laned["next"] == plain["next"]
    lane = laned["why"]
    assert lane == plain["why"] + f" --trailer 'Lane: {LANE}'"
    assert shlex.split(lane)[-2:] == ["--trailer", f"Lane: {LANE}"]
    assert "Co-Authored-By" not in lane, (
        "the second trailer names a person or a model, which no environment "
        "variable knows; it is the caller's to pass")


def test_the_behind_pin_only_row_carries_it_too(standard, project, tmp_path):
    """The other branch of the same row -- no copied file differs and the pin
    alone is behind -- because it spells its own apply and would otherwise be
    the one line in the report that forgot."""
    ahead = standard_ahead(standard, tmp_path)
    row = behind_row(ahead, project, LANE)
    assert row["detail"]["behind_pin_only"] is True
    assert row["why"].endswith(f" --trailer 'Lane: {LANE}'")
    assert shlex.split(row["why"])[-2:] == ["--trailer", f"Lane: {LANE}"]
    assert "--trailer" not in row["next"], row["next"]


def test_a_row_says_nothing_about_a_lane_when_none_is_set(advanced_standard,
                                                          project):
    """Today's report, byte for byte, for everybody who is not in a lane."""
    row = behind_row(advanced_standard, project, None)
    assert "--trailer" not in row["next"]
    assert "--trailer" not in row["why"]
    assert row["why"].rstrip().endswith("--branch shape/update-"
                                        + row["detail"]["standard"][:12])


def test_no_other_row_grows_a_trailer(advanced_standard, project):
    """A `Lane:` trailer belongs on an `apply` and nowhere else: the row is
    naming the flag of a command that writes a commit, not decorating every
    remediation in the table. Read in `next` AND `why`, since the `apply`
    moved to the second (#277)."""
    result = run_script(advanced_standard / DOCTOR, "--root", str(project),
                        "--json", env={"LANES_LANE": LANE})
    rows = rows_of(result)
    carrying = [name for name, row in rows.items()
                if "--trailer" in (row["next"] or "") + (row["why"] or "")]
    assert carrying == ["shape-currency"], rows


def standard_of_another_history(standard: Path, tmp_path: Path) -> Path:
    """A standard that does not carry the commit a project's pin names: the
    standard's files under a history of their own, so the `shape currency`
    row is the CANNOT ANSWER one, exit 3. One helper, for the test below and
    the ones in `tests/test_doctor_next_is_a_command.py` (#277)."""
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    for name in ("contracts", "scripts", "templates"):
        shutil.copytree(standard / name, stranger / name, symlinks=True)
    for name in ("update-shape.py", "shape-doctor.py", "scaffold-project.py",
                 "setup-project.py", "setup.sh", "openRepoShape"):
        shutil.copy2(standard / name, stranger / name)
    git("init", "-q", "-b", "main", ".", cwd=stranger)
    commit_all(stranger, "A standard with a history of its own")
    return stranger


def test_a_pin_this_standard_cannot_resolve_is_exit_three(standard, project,
                                                          tmp_path):
    """Not a verdict about the repository: this CHECKOUT cannot answer.

    A pin naming a commit this standard does not carry — a fork, a branch
    pin, a clone made before the commit landed — used to fall through to
    `INVALID`, telling somebody their repository was wrong on the evidence
    that our copy of the standard was short a commit.
    """
    stranger = standard_of_another_history(standard, tmp_path)
    result = doctor(stranger, project, "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"].startswith("CANNOT ANSWER (shape currency:")
    assert payload["exit"] == 3
    assert rows_of(result)["shape-currency"]["detail"]["environment"] is True
    plain = doctor(stranger, project)
    assert plain.returncode == 3
    assert "REFUSED shape-doctor-cannot-answer" in plain.stderr
    assert "fetch --all" in plain.stderr


# --- a root's OWN pin that does not read is the root's fault (#237) ---------
#
# `check_shape_currency` took EVERY refusal `update-shape.py prepare` raised
# for this checkout failing to ask. Most of them are: the pin names a commit
# this standard does not carry, the standard cannot be read. But `prepare`
# also reads the ROOT's own `contracts/shape-pin.yaml`, and a merge conflict
# in it, a `commit:` that is not 40 hex, a deleted file are somebody's repository
# being wrong. They answered CANNOT ANSWER, exit 3, outranking every red
# gate, with a NEXT that sent the reader to `git fetch --all` in the
# standard. AGENTS.md says exit 3 is "never a statement about their
# repository"; each case below is one, and is INVALID, exit 1.

SHAPE_PIN = "contracts/shape-pin.yaml"


def pin_with(old: str, new: str):
    """A mutation of the pin's text: `old` (a regex, multiline) becomes `new`."""
    return lambda text: re.sub(old, new, text, count=1,
                               flags=re.MULTILINE).encode("utf-8")


#: The pin with a merge conflict left in it where its `commit:` line was: the
#: two sides of the realistic two-shape-update merge, markers and all.
conflicted_pin = pin_with(
    r'^commit: .*$',
    '<<<<<<< HEAD\ncommit: "' + "1" * 40 + '"\n=======\n'
    'commit: "' + "2" * 40 + '"\n>>>>>>> edit-a')

#: The one fault `validate-pins.py` PASSES, so the shape-currency row is the
#: only red one under it.
other_digest_definition = pin_with(r'^digest_definition: .*$',
                                   'digest_definition: other-v9')

#: `(what the pin becomes, the refusal `read_pin` raises for it)`. A mutation
#: returns the file's new bytes, or None to delete it. The code is asserted
#: on every case so the case under test is the case reached.
ROOT_PIN_FAULTS = [
    pytest.param(conflicted_pin, "yaml-unparsable",
                 id="a-merge-conflict-in-it"),
    pytest.param(lambda text: b"\t: : [\n", "yaml-unparsable",
                 id="not-yaml-at-all"),
    pytest.param(lambda text: text.encode("utf-8") + b"\xff\xfe\n",
                 "yaml-unreadable", id="a-byte-that-is-not-utf-8"),
    pytest.param(lambda text: b"- one\n- two\n", "update-pin-unreadable",
                 id="a-list-not-a-mapping"),
    pytest.param(pin_with(r'^commit: .*$', 'commit: "zzzz"'),
                 "update-pin-commit", id="a-commit-that-is-not-40-hex"),
    pytest.param(other_digest_definition, "update-pin-digest-definition",
                 id="another-digest-definition"),
    pytest.param(pin_with(r'(?s)^files:.*\Z', 'files: []\n'),
                 "update-pin-no-files", id="no-files-rows"),
    pytest.param(pin_with(r'^  - path: .*$', '  - nopath: x'),
                 "update-pin-row", id="a-row-with-no-path"),
    pytest.param(pin_with(r'(?s)^files:.*\Z', 'files: 5\n'),
                 "update-pin-row", id="files-5-not-a-list"),
    pytest.param(pin_with(r'(?s)^files:.*\Z', 'files: true\n'),
                 "update-pin-row", id="files-true-not-a-list"),
    pytest.param(pin_with(r'(?s)^files:.*\Z', 'files: 1.5\n'),
                 "update-pin-row", id="files-1.5-not-a-list"),
    pytest.param(lambda text: None, "update-pin-missing",
                 id="a-deleted-pin"),
]


def break_the_pin(root: Path, mutation) -> None:
    """Rewrite `root`'s `contracts/shape-pin.yaml` as `mutation` says.

    BYTES, never `write_text`: a Windows `write_text` would turn the `\\n`s
    into `\\r\\n` and make one more thing differ between the OSes than the
    case is about.
    """
    pin = root / SHAPE_PIN
    mutated = mutation(pin.read_text(encoding="utf-8"))
    if mutated is None:
        pin.unlink()
    else:
        pin.write_bytes(mutated)


#: Every code `read_pin` raises for a root's own pin, read off the faults
#: above rather than retyped: a row that still says one of these has not
#: read the pin.
READ_PIN_CODES = frozenset(param.values[1] for param in ROOT_PIN_FAULTS)


def pasted(line: str) -> list[str]:
    """The argv the reader's own shell makes of a printed NEXT.

    `shlex` on POSIX, over the whole line, the way
    `test_a_red_validators_next_command_is_runnable` reads one; on Windows
    PowerShell's reading, through `powershell_tokens`, which unquotes
    `quote_arg`'s verbatim strings and, as PowerShell does, ends the line at
    a `#` that opens a token.

    THE WHOLE LINE ON POSIX, NOT THE PART BEFORE A `   #` (#277). The row's
    sentence is its `why` and the NEXT is the command alone, so there is no
    note to cut off. A reader that cut one off anyway would pass a NEXT that
    had grown a tail back, and the argv assertions below would stop proving
    the move. (`tests/test_doctor_next_is_a_command.py` holds the same NEXTs
    to that on every OS.)
    """
    if os.name == "nt":
        return powershell_tokens(line)
    return shlex.split(line)


def run_pasted(line: str) -> None:
    """Run a printed NEXT exactly as a reader would, and require exit 0."""
    proc = subprocess.run(pasted(line), capture_output=True, text=True,
                          check=False, env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 0, line + "\n" + proc.stdout + proc.stderr


def assert_a_plain_next(row: dict) -> None:
    """The NEXT is the command alone and the sentence is the row's `why`
    (#277).

    The sentence rode on the line as `   # <note>` until #277, and this
    asserted the note held no `;`, apostrophe or backtick: pasted into an
    interactive zsh that does not take `#` as a comment, a `;` starts a
    second command, an apostrophe opens a quotation nothing closes and a
    backtick runs whatever follows it. Nothing follows the command now, so
    what is asserted is that none of the sentence is on the line, and that
    it is said in `why`.
    """
    assert "   #" not in row["next"], row["next"]
    assert row["why"], row


def commit_in(root: Path, message: str, *args: str) -> str:
    """`git commit` in `root` with an identity that is never global; the new
    HEAD."""
    proc = subprocess.run(["git", "commit", "-q", *args, "-m", message],
                          cwd=str(root), capture_output=True, text=True,
                          check=False, env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


def compliant_again(standard: Path, root: Path) -> None:
    result = doctor(standard, root, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"


@pytest.mark.parametrize("mutation, code", ROOT_PIN_FAULTS)
def test_a_root_pin_that_does_not_read_is_invalid_not_cannot_answer(
        standard, project, mutation, code):
    """Each way the ROOT's pin can fail `read_pin`: a finding, exit 1.

    Asserted in both outputs, because the two are read by different people:
    `--json` by a scheduled job (the verdict, the row's status and its
    `detail`), the text by the person who follows the NEXT. Neither says
    `environment`, and stderr carries no `REFUSED shape-doctor-cannot-answer`
    and no `fetch --all` for it.
    """
    break_the_pin(project, mutation)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["exit"] == 1
    assert payload["verdict"].startswith("INVALID ("), payload["verdict"]
    assert "CANNOT ANSWER" not in payload["verdict"]
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["error"] == code, row["detail"]
    assert row["detail"]["refusal"]["code"] == code
    assert row["detail"]["pin"] == SHAPE_PIN
    assert "environment" not in row["detail"], row["detail"]
    # The loader's own words, whole -- and not its `Remediation:` trailer,
    # which for a pin that does not parse is about submodules.
    assert f"REFUSED {code}: " in row["reason"], row["reason"]
    assert "Remediation" not in row["reason"]
    assert "submodule" not in row["reason"]
    # The NEXT puts back the pin a tool wrote, from the root's own history:
    # the change that broke it is not committed, so that is `checkout HEAD`.
    # It is not a fetch in the standard, which cannot change the pin, nor the
    # `update-shape.py check` that refuses the same file the same way.
    assert row["detail"]["restore"] == "uncommitted", row["detail"]
    assert f"checkout HEAD -- {SHAPE_PIN}" in row["next"], row["next"]
    assert pasted(row["next"])[:2] == ["git", "-C"], row["next"]
    assert "fetch" not in row["next"]
    assert "update-shape.py" not in row["next"]
    assert_a_plain_next(row)
    plain = doctor(standard, project)
    assert plain.returncode == 1, plain.stdout + plain.stderr
    assert "CANNOT ANSWER" not in plain.stdout
    assert "shape-doctor-cannot-answer" not in plain.stderr
    assert "fetch --all" not in plain.stdout + plain.stderr
    assert verdict_line(plain).startswith("INVALID (")
    # And run as printed, it fixes it.
    run_pasted(row["next"])
    compliant_again(standard, project)


def test_a_merge_conflict_in_the_pin_still_names_the_projects_own_validator(
        standard, project):
    """What the issue's reader saw and misread: the `pins` row was right.

    The validator the project carries refuses the same file, in its own
    words, and its row names it as the next command. The verdict names the
    gates that are red -- it used to be one row that was wrong outranking the
    two that were right -- and the shape-currency row is the third finding
    about the one file, not the verdict's reason for being.
    """
    break_the_pin(project, conflicted_pin)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["pins"]["status"] == "FINDING"
    assert "validate-pins.py" in rows["pins"]["next"]
    assert "yaml-unparsable" in rows["pins"]["reason"]
    assert json.loads(result.stdout)["verdict"] == \
        "INVALID (pins, manifest-kinds)"


def test_a_pin_only_update_shape_refuses_is_the_one_red_row(standard,
                                                            project):
    """`digest_definition: other-v9` is what `validate-pins.py` PASSES.

    So the shape-currency row is the only finding, and it is not on the
    ladder's named list: the catch-all names it, `INVALID (shape-currency)`,
    exit 1 -- which is why its NEXT is not the validator, whose exit 0 would
    send this reader nowhere, but the pin put back from the root's history.
    """
    break_the_pin(project, other_digest_definition)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["pins"]["status"] == "ok", rows["pins"]
    assert rows["manifest-kinds"]["status"] == "ok"
    assert [name for name, row in rows.items()
            if row["status"] == "FINDING"] == ["shape-currency"]
    assert json.loads(result.stdout)["verdict"] == "INVALID (shape-currency)"


def stranger_standard(standard: Path, tmp_path: Path) -> Path:
    """A standard whose history is not the one a project was scaffolded from,
    so a pin naming the scaffold's commit is a commit it does not carry.
    Built the way `test_a_pin_this_standard_cannot_resolve_is_exit_three`
    builds it; that test is left exactly as it was."""
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    for name in ("contracts", "scripts", "templates"):
        shutil.copytree(standard / name, stranger / name, symlinks=True)
    for name in ("update-shape.py", "shape-doctor.py", "scaffold-project.py",
                 "setup-project.py", "setup.sh", "openRepoShape"):
        shutil.copy2(standard / name, stranger / name)
    git("init", "-q", "-b", "main", ".", cwd=stranger)
    commit_all(stranger, "A standard with a history of its own")
    return stranger


def test_what_decides_is_the_pin_and_not_the_standard(standard, project,
                                                      tmp_path):
    """The control, and the pair that separates the two kinds of refusal.

    One standard that lacks the scaffold's commit. Asked about a root whose
    pin is good it cannot answer -- CANNOT ANSWER, exit 3, `fetch --all`, as
    on main, with `environment` in the row's `detail` and the standard's own
    refusal as its error. Asked about the same root with a conflicted pin it
    never gets as far as the commit: the file is wrong, so INVALID, exit 1.
    """
    stranger = stranger_standard(standard, tmp_path)
    result = doctor(stranger, project, "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["exit"] == 3
    assert payload["verdict"].startswith("CANNOT ANSWER (shape currency:")
    detail = rows_of(result)["shape-currency"]["detail"]
    assert detail["environment"] is True
    assert detail["error"] == "update-revision-unresolvable"
    plain = doctor(stranger, project)
    assert plain.returncode == 3
    assert "REFUSED shape-doctor-cannot-answer" in plain.stderr
    assert "fetch --all" in plain.stderr
    break_the_pin(project, conflicted_pin)
    broken = doctor(stranger, project, "--json")
    assert broken.returncode == 1, broken.stdout + broken.stderr
    assert json.loads(broken.stdout)["verdict"].startswith("INVALID (")
    row = rows_of(broken)["shape-currency"]
    assert row["detail"]["error"] == "yaml-unparsable"
    assert "environment" not in row["detail"]
    assert "shape-doctor-cannot-answer" not in broken.stderr


def test_a_family_holders_conflicted_pin_is_invalid_too(standard, holder,
                                                        tmp_path):
    """The row is registered for both kinds of root, and answers alike."""
    root = tmp_path / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    break_the_pin(root, conflicted_pin)
    result = doctor(standard, root, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["kind"] == "family"
    assert payload["verdict"].startswith("INVALID (")
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING" and "environment" not in row["detail"]
    assert row["detail"]["error"] == "yaml-unparsable"
    assert row["detail"]["restore"] == "uncommitted", row["detail"]
    run_pasted(row["next"])
    again = rows_of(doctor(standard, root, "--json"))["shape-currency"]
    assert again["detail"].get("error") not in READ_PIN_CODES, again


# --- the pin put back: the NEXT for each state git can be in (#237) ---------
#
# Each test below runs the printed NEXT and asks the doctor again. The NEXT
# is chosen from the pin's own git state, read-only: unmerged, then
# uncommitted (the parametrised test above), then hidden, then committed,
# then none.

#: `commit: "zzzz"`, the committed fault the review probed beside a deletion.
not_forty_hex = pin_with(r'^commit: .*$', 'commit: "zzzz"')


@pytest.mark.parametrize("mutation, code", [
    pytest.param(lambda text: None, "update-pin-missing",
                 id="the-pin-deleted-in-a-commit"),
    pytest.param(not_forty_hex, "update-pin-commit",
                 id="a-commit-line-not-40-hex-committed"),
])
def test_a_pin_broken_in_a_commit_is_put_back_from_before_that_commit(
        standard, project, mutation, code):
    """Clean status, so `checkout HEAD` would put back the broken pin.

    The NEXT names the last commit to change the pin, `~1`: the pin as it
    was before it. An unrelated commit after the break is what tells that
    apart from `HEAD~1`.
    """
    break_the_pin(project, mutation)
    git("add", "--", SHAPE_PIN, cwd=project)
    breaking = commit_in(project, "break the pin")
    commit_in(project, "an unrelated commit after it", "--allow-empty")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["detail"]["error"] == code, row["detail"]
    assert row["detail"]["restore"] == "committed", row["detail"]
    argv = pasted(row["next"])
    assert argv[:2] == ["git", "-C"], row["next"]
    assert argv[3:] == ["checkout", f"{breaking}~1", "--", SHAPE_PIN], argv
    assert breaking[:12] in row["why"], row["why"]
    assert_a_plain_next(row)
    run_pasted(row["next"])
    compliant_again(standard, project)


def test_the_issues_own_merge_takes_only_the_pin_whole(standard, project):
    """The issue's reproduction: two branches rewrite `commit:`, then merge.

    The pin is `UU`, and so are `Makefile`, a shape copy, and a file of the
    project's own. The NEXT took one side whole of the pin and the
    Makefile, as one tool's output. But a copy can hold an edit of the
    project, kept by `apply --accept-local`, and taken whole the other
    side's copy dropped it (#485). So the NEXT takes the pin alone, and its
    note and `left_for_a_person` give the Makefile to a person to merge by
    hand. The project's own file is left to its owner, unnamed. Run, the
    pin reads again and the Makefile is as the merge left it: the row then
    answers about the commit the pin names, which here is no commit at all.
    """
    makefile = project / "Makefile"
    own = project / "notes.md"
    own.write_bytes(b"base\n")
    git("add", "--", "notes.md", cwd=project)
    base = commit_in(project, "a file of the project's own")
    for branch, digit in (("edit-a", "1"), ("edit-b", "2")):
        git("checkout", "-q", "-b", branch, base, cwd=project)
        break_the_pin(project, pin_with(r'^commit: .*$',
                                        f'commit: "{digit * 40}"'))
        for name in ("Makefile", "notes.md"):
            path = project / name
            path.write_bytes(path.read_bytes() + f"# {branch}\n".encode())
        git("add", "--", SHAPE_PIN, "Makefile", "notes.md", cwd=project)
        commit_in(project, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"],
                            cwd=str(project), capture_output=True, text=True,
                            check=False, env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=project).stdout
    for name in (SHAPE_PIN, "Makefile", "notes.md"):
        assert f"UU {name}" in status, status
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["detail"]["error"] == "yaml-unparsable", row["detail"]
    assert row["detail"]["restore"] == "unmerged", row["detail"]
    assert row["next"].startswith("git -C "), row["next"]
    assert "checkout --ours -- " in row["next"], row["next"]
    argv = pasted(row["next"])
    assert argv[3:] == ["checkout", "--ours", "--", SHAPE_PIN], argv
    assert row["detail"]["left_for_a_person"] == ["Makefile"], row["detail"]
    note = row["why"]
    assert "Makefile is a copy conflicted too" in note, note
    assert "merges it by hand, keeping the hunks git merged" in note, note
    assert "notes.md" not in row["next"] and "notes.md" not in note, row
    assert_a_plain_next(row)
    held = makefile.read_bytes()
    assert b"# edit-a" in held and b"# edit-b" in held, held[-200:]
    run_pasted(row["next"])
    assert makefile.read_bytes() == held, "the NEXT took the Makefile whole"
    again = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert again["detail"]["error"] not in READ_PIN_CODES, again
    assert again["detail"]["error"] == "update-revision-unresolvable", again
    assert b"<<<<<<<" in own.read_bytes()


def test_a_readme_conflicted_over_the_projects_own_lines_is_left_to_a_person(
        standard, project):
    """Both branches rewrite the pin's `commit:` and README.md's first line,
    and edit-a also adds a paragraph at the end, which git merges cleanly.

    README.md holds no `Shape:` line here, so nothing in it is the shape's,
    and where it holds one every other line is still the project's own.
    Taken whole, edit-a's paragraph went with it (review of PR #267). The
    NEXT takes the pin alone, and its `why` and `left_for_a_person` say that
    README.md is a person's to merge.
    """
    readme = project / "README.md"
    assert b"Shape:" not in readme.read_bytes()
    base = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    for branch, digit in (("edit-a", "1"), ("edit-b", "2")):
        git("checkout", "-q", "-b", branch, base, cwd=project)
        break_the_pin(project, pin_with(r'^commit: .*$',
                                        f'commit: "{digit * 40}"'))
        lines = readme.read_bytes().split(b"\n")
        lines[0] = f"# Atlas, as {branch} writes it".encode()
        if branch == "edit-a":
            lines.append(b"A paragraph only edit-a wrote.\n")
        readme.write_bytes(b"\n".join(lines))
        git("add", "--", SHAPE_PIN, "README.md", cwd=project)
        commit_in(project, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"],
                            cwd=str(project), capture_output=True, text=True,
                            check=False, env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=project).stdout
    assert f"UU {SHAPE_PIN}" in status and "UU README.md" in status, status
    assert b"only edit-a wrote" in readme.read_bytes()
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["restore"] == "unmerged", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], row["next"]
    assert row["detail"]["left_for_a_person"] == ["README.md"], row["detail"]
    note = row["why"]
    assert "README.md is conflicted too" in note, note
    assert "a person merges it" in note, note
    assert_a_plain_next(row)
    run_pasted(row["next"])
    assert b"only edit-a wrote" in readme.read_bytes(), \
        "edit-a's paragraph was dropped"
    again = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert again["detail"]["error"] not in READ_PIN_CODES, again


def standard_moved_on(standard: Path, tmp_path: Path) -> tuple:
    """`(a copy of standard, C2, C3)`: two more commits, each moving
    `UPSTREAM_TARGET`, so two real `apply` runs re-pin one project to two
    different commits. A copy, byte for byte with its `.git`, so the
    session's `standard` is left as every other test finds it."""
    moved = tmp_path / "moved" / "openRepoShape"
    shutil.copytree(standard, moved, symlinks=True)
    commits = []
    for label in ("c2", "c3"):
        target = moved / UPSTREAM_TARGET
        target.write_bytes(target.read_bytes() + f"# {label}\n".encode())
        commit_all(moved, label)
        commits.append(git("rev-parse", "HEAD", cwd=moved).stdout.strip())
    return moved, commits[0], commits[1]


def test_the_issues_two_apply_merge_leaves_the_projects_manifest_to_a_person(
        standard, project, tmp_path):
    """The issue's own merge, with real re-pins: `apply --at C2` on shape/a,
    `apply --at C3` on shape/b, and shape/a merged into shape/b.

    Shape/a also renamed the project in `project.yaml` and added a README
    paragraph, lines of its own far from any `apply` writes. Git merges both
    cleanly, and `project.yaml` is still `UU` over its `shape:` block.
    Taking `project.yaml` whole dropped the rename, and the doctor then said
    COMPLIANT (review of PR #267). The NEXT takes the pin whole, and
    `project.yaml` is left to a person, and the rename survives the NEXT,
    that person's merge and the merge commit. So is the `UU` Makefile: it
    was taken whole with the pin until a copy kept by `--accept-local` was
    found to lose its edit that way (#485), and now the person merges it
    too, here to the side the NEXT took, which is the pin's own copy.

    The row is `check_shape_currency`'s own, asked in process: without
    #232 a `project.yaml` that does not load is NOT A SHAPE ROOT and the
    command runs no row, and with it the command prints this row.
    """
    moved, c2, c3 = standard_moved_on(standard, tmp_path)
    manifest, readme = project / "project.yaml", project / "README.md"
    for commit, branch in ((c2, "shape/a"), (c3, "shape/b")):
        git("checkout", "-q", "main", cwd=project)
        applied = run_script(moved / "update-shape.py", "apply", "--root",
                             str(project), "--upstream", str(moved), "--at",
                             commit, "--yes", "--branch", branch)
        assert applied.returncode == 0, applied.stdout + applied.stderr
        if branch == "shape/a":
            text = manifest.read_bytes()
            renamed = re.sub(rb'(?m)^name: .*$', b'name: "Atlas Renamed"',
                             text, count=1)
            assert renamed != text
            manifest.write_bytes(renamed)
            readme.write_bytes(readme.read_bytes()
                               + b"\nA paragraph only shape/a wrote.\n")
            git("add", "--", "project.yaml", "README.md", cwd=project)
            commit_in(project, "the project's own edits")
    merged = subprocess.run(["git", "merge", "-q", "shape/a"],
                            cwd=str(project), capture_output=True, text=True,
                            check=False, env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=project).stdout
    for name in ("Makefile", SHAPE_PIN, "project.yaml"):
        assert f"UU {name}" in status, status
    assert "UU README.md" not in status, status
    assert b'name: "Atlas Renamed"' in manifest.read_bytes()
    module = doctor_module(standard)
    row = module.check_shape_currency(module.Context(project)).as_dict()
    assert row["detail"]["error"] == "yaml-unparsable", row["detail"]
    assert row["detail"]["restore"] == "unmerged", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], row["next"]
    assert row["detail"]["left_for_a_person"] == ["Makefile",
                                                  "project.yaml"], \
        row["detail"]
    note = row["why"]
    assert "project.yaml is conflicted too" in note, note
    assert "Makefile is a copy conflicted too" in note, note
    assert_a_plain_next(row)
    held = (project / "Makefile").read_bytes()
    run_pasted(row["next"])
    assert b'name: "Atlas Renamed"' in manifest.read_bytes(), \
        "shape/a's rename was dropped"
    assert b"only shape/a wrote" in readme.read_bytes()
    assert (project / "Makefile").read_bytes() == held, \
        "the NEXT took the Makefile whole"
    again = module.check_shape_currency(module.Context(project)).as_dict()
    assert again["detail"].get("error") not in READ_PIN_CODES, again
    # A person's merge of `project.yaml` and of the Makefile: each
    # conflicting hunk to the side the NEXT took, each clean one kept, over
    # git's own three stages.
    for name in ("project.yaml", "Makefile"):
        stages = []
        for number in (1, 2, 3):
            held = subprocess.run(["git", "show", f":{number}:{name}"],
                                  cwd=str(project), capture_output=True,
                                  check=True).stdout
            stages.append(tmp_path / f"{name}.{number}")
            stages[-1].write_bytes(held)
        subprocess.run(["git", "merge-file", "--ours", str(stages[1]),
                        str(stages[0]), str(stages[2])],
                       capture_output=True, check=True)
        (project / name).write_bytes(stages[1].read_bytes())
    git("add", "--", "project.yaml", "Makefile", SHAPE_PIN, cwd=project)
    commit_in(project, "merge shape/a")
    kept = git("show", "HEAD:project.yaml", cwd=project).stdout
    assert 'name: "Atlas Renamed"' in kept, kept
    compliant_again(moved, project)


def test_a_bad_pin_staged_where_head_holds_none_is_put_back_from_history(
        standard, project):
    """`A ` in the status: the pin was deleted in a commit, then a bad one
    staged at its path. HEAD holds no pin, so `checkout HEAD` would name a
    path HEAD does not have; the NEXT reaches back past the deletion."""
    pin = project / SHAPE_PIN
    good = pin.read_text(encoding="utf-8")
    git("rm", "-q", "--", SHAPE_PIN, cwd=project)
    deleting = commit_in(project, "drop the pin")
    pin.write_bytes(not_forty_hex(good))
    git("add", "--", SHAPE_PIN, cwd=project)
    status = git("status", "--porcelain=v1", "--", SHAPE_PIN,
                 cwd=project).stdout
    assert status.startswith("A "), status
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["error"] == "update-pin-commit", row["detail"]
    assert row["detail"]["restore"] == "committed", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", f"{deleting}~1", "--", SHAPE_PIN], row["next"]
    run_pasted(row["next"])
    compliant_again(standard, project)


def test_a_merge_where_only_the_other_side_holds_a_pin_takes_theirs(
        standard, project):
    """`DU`: this branch deleted the pin and the other changed it, so only
    `--theirs` holds one -- `--ours` would refuse the path by name -- and the
    note says that one side is all there is.

    Git leaves the other side's pin in the tree, and that one reads; the
    row is reached once somebody keeping this branch's deletion removes it
    too, with the merge still unfinished.
    """
    base = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    git("checkout", "-q", "-b", "edit", base, cwd=project)
    break_the_pin(project, pin_with(r'^commit: .*$',
                                    'commit: "' + "1" * 40 + '"'))
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "edit the pin")
    git("checkout", "-q", "-b", "drop", base, cwd=project)
    git("rm", "-q", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "drop the pin")
    merged = subprocess.run(["git", "merge", "-q", "edit"],
                            cwd=str(project), capture_output=True, text=True,
                            check=False, env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    (project / SHAPE_PIN).unlink()
    status = git("status", "--porcelain=v1", "--", SHAPE_PIN,
                 cwd=project).stdout
    assert status.startswith("DU "), status
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["error"] == "update-pin-missing", row["detail"]
    assert row["detail"]["restore"] == "unmerged", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", "--theirs", "--", SHAPE_PIN], row["next"]
    assert "only that side" in row["why"], row["why"]
    assert_a_plain_next(row)
    run_pasted(row["next"])
    again = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert again["detail"]["error"] == "update-revision-unresolvable", again


def test_two_commits_that_each_broke_the_pin_are_reached_past(standard,
                                                              project):
    """`commit: "zzzz"` committed, then `commit: "yyyy"` committed over it.

    Rolling back the last commit put back the first break's pin, and the
    NEXT after it was `checkout HEAD`, which put back the second: a circle
    (review of PR #267). Each pin is read before it is named, so the NEXT
    reaches past both, to the pin before the first.
    """
    break_the_pin(project, not_forty_hex)
    git("add", "--", SHAPE_PIN, cwd=project)
    first = commit_in(project, "break the pin")
    break_the_pin(project, pin_with(r'^commit: .*$', 'commit: "yyyy"'))
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "break it again")
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["restore"] == "committed", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", f"{first}~1", "--", SHAPE_PIN], row["next"]
    assert first[:12] in row["why"], row["why"]
    assert_a_plain_next(row)
    run_pasted(row["next"])
    compliant_again(standard, project)


def test_an_uncommitted_change_over_a_committed_break_goes_to_history(
        standard, project):
    """HEAD's own pin does not read either, so `checkout HEAD` would put
    back a broken pin: the NEXT goes straight to the pin before the commit
    that broke it."""
    break_the_pin(project, not_forty_hex)
    git("add", "--", SHAPE_PIN, cwd=project)
    breaking = commit_in(project, "break the pin")
    break_the_pin(project, lambda text: b"\t: : [\n")
    status = git("status", "--porcelain=v1", "--", SHAPE_PIN,
                 cwd=project).stdout
    assert status.startswith(" M"), status
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["error"] == "yaml-unparsable", row["detail"]
    assert row["detail"]["restore"] == "committed", row["detail"]
    assert pasted(row["next"])[3:] == [
        "checkout", f"{breaking}~1", "--", SHAPE_PIN], row["next"]
    run_pasted(row["next"])
    compliant_again(standard, project)


def recommit_a_good_pin(root: Path) -> str:
    """A second commit to the pin that leaves it reading: a comment added.

    So a NEXT that rolled back the last commit to the pin has one to name,
    and the pin it would roll back is a good one. The new HEAD."""
    pin = root / SHAPE_PIN
    pin.write_bytes(pin.read_bytes() + b"# a comment a later commit added\n")
    git("add", "--", SHAPE_PIN, cwd=root)
    return commit_in(root, "a comment in the pin")


def assert_hidden(standard: Path, root: Path, code: str, letter: str) -> None:
    """The row says `hidden`, names no rollback, and its NEXT, run as
    printed, shows the index flag that hides the pin."""
    assert git("status", "--porcelain=v1", "--", SHAPE_PIN,
               cwd=root).stdout == ""
    row = rows_of(doctor(standard, root, "--json"))["shape-currency"]
    assert row["detail"]["error"] == code, row["detail"]
    assert row["detail"]["restore"] == "hidden", row["detail"]
    argv = pasted(row["next"])
    assert argv[3:] == ["ls-files", "-v", "--", SHAPE_PIN], row["next"]
    assert "checkout" not in argv, row["next"]
    assert_a_plain_next(row)
    shown = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert shown.returncode == 0, shown.stderr
    assert shown.stdout == f"{letter} {SHAPE_PIN}\n", shown.stdout


def test_a_broken_copy_assume_unchanged_hides_is_not_rolled_back(standard,
                                                                 project):
    """HEAD's pin reads, and `git status` shows no change to the copy here
    because assume-unchanged hides it. No commit broke the pin, so naming
    the commit before the last good re-pin rolled back a good pin (review
    of PR #267): the NEXT shows the flag instead."""
    recommit_a_good_pin(project)
    git("update-index", "--assume-unchanged", "--", SHAPE_PIN, cwd=project)
    break_the_pin(project, not_forty_hex)
    assert_hidden(standard, project, "update-pin-commit", "h")


def test_a_pin_a_sparse_checkout_leaves_out_is_not_rolled_back(standard,
                                                               project):
    """A sparse checkout leaves the pin out of the tree: `read_pin` finds no
    file, `git status` shows nothing, and HEAD's pin reads. The NEXT shows
    the `S` that says why, and names no rollback."""
    recommit_a_good_pin(project)
    sparse = project / git("rev-parse", "--git-path", "info/sparse-checkout",
                           cwd=project).stdout.strip()
    sparse.parent.mkdir(parents=True, exist_ok=True)
    sparse.write_bytes(b"/*\n!/" + SHAPE_PIN.encode() + b"\n")
    git("config", "core.sparseCheckout", "true", cwd=project)
    git("read-tree", "-mu", "HEAD", cwd=project)
    assert not (project / SHAPE_PIN).exists()
    assert_hidden(standard, project, "update-pin-missing", "S")


def test_reading_the_pins_git_state_leaves_a_stat_dirty_index_alone(
        standard, project):
    """The pin's `git status` must not refresh the root's index: that is the
    doctor writing into it. `--no-optional-locks` is what stops it, and a
    plain `git status`, as the control, does rewrite it."""
    break_the_pin(project, not_forty_hex)
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "break the pin")
    later = os.stat(project / SHAPE_PIN).st_mtime + 120
    for path in project.rglob("*"):
        if (".git" not in path.relative_to(project).parts and path.is_file()
                and not path.is_symlink()):
            os.utime(path, (later, later))
    index = project / ".git" / "index"
    before = index.read_bytes()
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["detail"]["restore"] == "committed", row["detail"]
    assert index.read_bytes() == before, "the doctor rewrote the root's index"
    subprocess.run(["git", "status", "--porcelain=v1", "--", SHAPE_PIN],
                   cwd=str(project), capture_output=True, check=False)
    assert index.read_bytes() != before, \
        "control: a plain status must refresh it"


def test_a_pin_with_no_good_copy_in_its_history_keeps_the_check_next(
        standard, project):
    """No history to put a pin back from: one root commit holds a bad pin.

    Nothing git can name fixes it, so the NEXT stays the tool that refused,
    and says that whether this root was ever scaffolded or adopted is a
    person's decision.
    """
    break_the_pin(project, not_forty_hex)
    git("checkout", "-q", "--orphan", "squashed", cwd=project)
    git("add", "--", SHAPE_PIN, cwd=project)
    commit_in(project, "the whole history, squashed into one commit")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["detail"]["error"] == "update-pin-commit", row["detail"]
    assert row["detail"]["restore"] == "none", row["detail"]
    assert "update-shape.py" in row["next"] and " check " in row["next"]
    assert "checkout" not in row["next"], row["next"]
    assert "fetch" not in row["next"]
    assert_a_plain_next(row)


def test_the_doctor_writes_no_bytecode_into_the_standard(standard, project,
                                                         tmp_path):
    """"It writes nothing" has to be true of the STANDARD too.

    `PYTHONDONTWRITEBYTECODE=1` covers the validators run as subprocesses;
    `repo_shape` and `update-shape.py` are imported IN PROCESS and were
    leaving `__pycache__/` in the standard's own checkout.
    """
    copy = tmp_path / "standard-clean"
    shutil.copytree(standard, copy, symlinks=True)
    for cached in copy.rglob("__pycache__"):
        rmtree(cached)
    assert doctor(copy, project).returncode == 0
    left = sorted(path.relative_to(copy).as_posix()
                  for path in copy.rglob("*.pyc"))
    assert left == [], left


# --- the `manifest kinds` row for a file that does not load (#291) ----------
#
# The row lists each file under `contracts/` that does not load as a mapping,
# and its NEXT was the unregistered kind's sentence: register the kind in
# shape-doctor.py's MANIFEST_VALIDATORS, or remove the file from the root.
# For a conflicted `contracts/shape-pin.yaml` that told the reader to delete
# the pin, and it was not a command a shell could even split. A file a tool
# wrote is now put back from the root's own history by `pin_restore`, the
# helper the `shape currency` row uses (#237). A file of the project's own
# is left to a person. A copy the shape pin has a row for, and a neutral
# product pin, can hold a person's edit, so the NEXT shows it and puts
# nothing back (review of PR #358). Each test runs the printed NEXT, then
# asks again.

SPEC_PIN = "contracts/spec-pin.yaml"
CODE_PIN = "contracts/code-pin.yaml"
#: The one shape copy a root keeps under `contracts/`.
NAMING_COPY = "contracts/repository-naming.yaml"
OWN_CONTRACT = "contracts/notes.yaml"
#: A file of the project's own that is NAMED like a pin. No leg has the role
#: `release`, `neutral_product_pins:` does not name it, and it is not a shape
#: copy, so it is the project's whatever it is called (codex, PR #358).
OWN_PIN_NAMED = "contracts/release-pin.yaml"
RELEASE = (b"schedule: weekly\nowner: release-team\nchannels:\n"
           b"  - stable\nnotes: first\n")
#: The pin `neutral_product_pins:` declares for `openGlass`, at the path
#: `scaffold-project.py --pin` writes it to.
NEUTRAL_PIN = "contracts/openglass-pin.yaml"
#: A slip that stops a file loading, appended to what it held.
SLIP = b"\t: : [\n"

#: How each restore's note names the file it puts back, `{what}` being
#: `pin` or `copy`.
NOTE_SAYS = {"unmerged": "never a hand-merged {what}",
             "uncommitted": "puts back the {what} as last committed",
             "committed": "the {what} as it was before"}


def conflict_in(root: Path, rel: str, key: str, *also: str) -> None:
    """Leave `rel` conflicted, `UU`, the way two branches leave it.

    Two branches from HEAD each give the `key:` line of `rel` their own
    40-digit value and append a line to each of `also`, and the second
    merges the first. Bytes throughout, as `break_the_pin` writes them.
    """
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    for branch, digit in (("edit-a", "1"), ("edit-b", "2")):
        git("checkout", "-q", "-b", branch, base, cwd=root)
        path = root / rel
        path.write_bytes(pin_with(rf"^{key}: .*$", f'{key}: "{digit * 40}"')(
            path.read_text(encoding="utf-8")))
        for name in also:
            other = root / name
            other.write_bytes(other.read_bytes() + f"# {branch}\n".encode())
        git("add", "--", rel, *also, cwd=root)
        commit_in(root, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"], cwd=str(root),
                            capture_output=True, text=True, check=False,
                            env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=root).stdout
    for name in (rel, *also):
        assert f"UU {name}" in status, status


def own_contract(root: Path) -> Path:
    """A committed `contracts/notes.yaml` with no `kind:`, the project's own
    data, which loads and which the row passes over in silence."""
    own = root / OWN_CONTRACT
    own.write_bytes(b"colour: blue\n")
    git("add", "--", OWN_CONTRACT, cwd=root)
    commit_in(root, "a contract of the project's own")
    return own


def kinds_and_currency(standard: Path, root: Path) -> tuple[dict, dict]:
    rows = rows_of(doctor(standard, root, "--json"))
    return rows["manifest-kinds"], rows["shape-currency"]


def assert_no_registration(row: dict) -> None:
    """The issue's (a) and (b): the NEXT is a command and never the
    unregistered kind's sentence, whose second half deletes the file."""
    assert row["next"], row
    for words in ("register the kind", "remove the file",
                  "MANIFEST_VALIDATORS"):
        assert words not in row["next"], (words, row["next"])
    assert_a_plain_next(row)


def shape_pin_conflicted(root: Path) -> list:
    conflict_in(root, SHAPE_PIN, "commit")
    return ["checkout", "--ours", "--", SHAPE_PIN]


def shape_pin_not_utf8_committed(root: Path) -> list:
    pin = root / SHAPE_PIN
    pin.write_bytes(pin.read_bytes() + b"\xff\xfe\n")
    git("add", "--", SHAPE_PIN, cwd=root)
    breaking = commit_in(root, "a byte that is not UTF-8")
    commit_in(root, "an unrelated commit after it", "--allow-empty")
    return ["checkout", f"{breaking}~1", "--", SHAPE_PIN]


def shape_pin_a_list(root: Path) -> list:
    (root / SHAPE_PIN).write_bytes(b"- one\n- two\n")
    return ["checkout", "HEAD", "--", SHAPE_PIN]


def leg_pin_conflicted(root: Path) -> list:
    # `Makefile`, a copy the shape writes, and README.md, which holds the
    # line `apply` writes, conflict beside it. Only the shape pin takes the
    # copies with it and names README.md for a person: a leg pin is named
    # alone, and its note says nothing of either.
    conflict_in(root, SPEC_PIN, "commit", "Makefile", "README.md")
    return ["checkout", "--ours", "--", SPEC_PIN]


def leg_pin_not_utf8(root: Path) -> list:
    pin = root / SPEC_PIN
    pin.write_bytes(pin.read_bytes() + b"\xff\n")
    return ["checkout", "HEAD", "--", SPEC_PIN]


def leg_pin_not_utf8_committed(root: Path) -> list:
    # The leg pin's own history, not the shape pin's: the walk lists the
    # commits that touched THIS file, and asks each parent for THIS file.
    pin = root / SPEC_PIN
    pin.write_bytes(pin.read_bytes() + b"\xff\n")
    git("add", "--", SPEC_PIN, cwd=root)
    breaking = commit_in(root, "a byte that is not UTF-8 in the spec pin")
    commit_in(root, "an unrelated commit after it", "--allow-empty")
    return ["checkout", f"{breaking}~1", "--", SPEC_PIN]


def leg_pin_past_a_list_in_its_history(root: Path) -> list:
    # Two commits in a row broke it, the first into a list, which loads and
    # is not a mapping. The walk steps past that parent to the pin before
    # both, because putting back the list would leave the row where it is.
    pin = root / SPEC_PIN
    good = pin.read_bytes()
    pin.write_bytes(b"- a\n")
    git("add", "--", SPEC_PIN, cwd=root)
    first = commit_in(root, "the spec pin made a list")
    pin.write_bytes(good + b"\xff\n")
    git("add", "--", SPEC_PIN, cwd=root)
    commit_in(root, "then a byte that is not UTF-8 in it")
    commit_in(root, "an unrelated commit after it", "--allow-empty")
    return ["checkout", f"{first}~1", "--", SPEC_PIN]


@pytest.mark.parametrize("breaks, rel, code, restore, what, compliant", [
    pytest.param(shape_pin_conflicted, SHAPE_PIN, "yaml-unparsable",
                 "unmerged", "pin", False, id="the-shape-pin-conflicted"),
    pytest.param(shape_pin_not_utf8_committed, SHAPE_PIN, "yaml-unreadable",
                 "committed", "pin", True,
                 id="the-shape-pin-not-utf-8-committed"),
    pytest.param(shape_pin_a_list, SHAPE_PIN, None, "uncommitted", "pin",
                 True, id="the-shape-pin-a-list"),
    pytest.param(leg_pin_conflicted, SPEC_PIN, "yaml-unparsable",
                 "unmerged", "pin", False, id="a-leg-pin-conflicted"),
    pytest.param(leg_pin_not_utf8, SPEC_PIN, "yaml-unreadable",
                 "uncommitted", "pin", True, id="a-leg-pin-not-utf-8"),
    pytest.param(leg_pin_not_utf8_committed, SPEC_PIN, "yaml-unreadable",
                 "committed", "pin", True,
                 id="a-leg-pin-not-utf-8-committed"),
    pytest.param(leg_pin_past_a_list_in_its_history, SPEC_PIN,
                 "yaml-unreadable", "committed", "pin", True,
                 id="a-leg-pin-past-a-list-in-its-history"),
])
def test_a_file_a_tool_wrote_that_does_not_load_is_put_back_from_git(
        standard, project, breaks, rel, code, restore, what, compliant):
    """The row names the git command for the file's own state, the loader's
    words for it, and never the unregistered kind's sentence.

    Run as printed, the command puts back the bytes a tool wrote, and the
    row reads every file again. Where the break was the only fault the
    doctor is COMPLIANT. A merge is left for its owner to finish.
    """
    expected = breaks(project)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    row = rows["manifest-kinds"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["unreadable"] == [rel], row["detail"]
    assert_no_registration(row)
    assert row["detail"]["restore"] == {rel: restore}, row["detail"]
    said = row["detail"]["refusals"][rel]
    assert said["code"] == code, said
    if code is None:
        # What a file that loads as something else is said to hold.
        assert said["detail"] == "it loads as a list, not a mapping", said
    # The loader's own words, less the path it opens with.
    words = f"{code}: {said['detail']}" if code else said["detail"]
    assert f"unreadable as YAML: {rel} ({words})" in row["reason"], \
        row["reason"]
    assert Path(rel).name not in said["detail"], said
    argv = pasted(row["next"])
    assert argv[:2] == ["git", "-C"], row["next"]
    assert argv[3:] == expected, argv
    note = row["why"]
    assert NOTE_SAYS[restore].format(what=what) in note, note
    assert "README.md" not in note and "a person merges" not in note, note
    if rel == SHAPE_PIN:
        # One helper, so the two rows about the one file name one command.
        assert row["next"] == rows["shape-currency"]["next"], rows
    run_pasted(row["next"])
    again = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert again["status"] == "ok", again
    assert again["detail"]["unreadable"] == [], again
    if compliant:
        compliant_again(standard, project)


def project_contract_conflicted(root: Path) -> tuple[str, str]:
    own_contract(root)
    conflict_in(root, OWN_CONTRACT, "colour")
    return OWN_CONTRACT, "project"


def leg_pin_in_a_squashed_root_commit(root: Path) -> tuple[str, str]:
    leg_pin_not_utf8(root)
    git("checkout", "-q", "--orphan", "squashed", cwd=root)
    git("add", "--", SPEC_PIN, cwd=root)
    commit_in(root, "the whole history, squashed into one commit")
    return SPEC_PIN, "none"


def leg_pin_added_back_after_its_deletion(root: Path) -> tuple[str, str]:
    # The walk stops at the commit that added the file back: its parent
    # holds none, so the pin from before the deletion is not this file's
    # history to put back, though the parent holds a shape pin.
    pin = root / SPEC_PIN
    good = pin.read_bytes()
    git("rm", "-q", "--", SPEC_PIN, cwd=root)
    commit_in(root, "the spec pin deleted")
    pin.write_bytes(good + b"\xff\n")
    git("add", "--", SPEC_PIN, cwd=root)
    commit_in(root, "the spec pin added back, with a byte that is not UTF-8")
    return SPEC_PIN, "none"


def own_pin_named(root: Path) -> Path:
    """`contracts/release-pin.yaml`, committed: the project's own file,
    named like a pin, which nothing in the root declares."""
    path = root / OWN_PIN_NAMED
    path.write_bytes(RELEASE)
    git("add", "--", OWN_PIN_NAMED, cwd=root)
    commit_in(root, "the project's own release train")
    return path


def own_pin_named_edited_with_a_slip(root: Path) -> tuple[str, str]:
    # A person's edit, not yet committed, with a slip in it. `checkout
    # HEAD` would drop `schedule: daily` along with the slip.
    own_pin_named(root).write_bytes(RELEASE.replace(b"weekly", b"daily")
                                    + SLIP)
    return OWN_PIN_NAMED, "project"


def own_pin_named_conflicted(root: Path) -> tuple[str, str]:
    # Both sides change `schedule:`, and the other side also adds a channel
    # that git merges cleanly. `checkout --ours` would take this side whole
    # and drop `- nightly`.
    own_pin_named(root)
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    for branch, body in (
            ("edit-a", RELEASE.replace(b"weekly", b"daily").replace(
                b"  - stable\n", b"  - stable\n  - nightly\n")),
            ("edit-b", RELEASE.replace(b"weekly", b"hourly"))):
        git("checkout", "-q", "-b", branch, base, cwd=root)
        (root / OWN_PIN_NAMED).write_bytes(body)
        git("add", "--", OWN_PIN_NAMED, cwd=root)
        commit_in(root, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"], cwd=str(root),
                            capture_output=True, text=True, check=False,
                            env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=root).stdout
    assert f"UU {OWN_PIN_NAMED}" in status, status
    assert b"  - nightly\n" in (root / OWN_PIN_NAMED).read_bytes()
    return OWN_PIN_NAMED, "project"


def own_pin_named_broken_by_a_commit(root: Path) -> tuple[str, str]:
    # A commit that hands the train to another team, with a slip in it.
    # `checkout <it>~1` would drop `owner: platform-team` with the slip.
    path = own_pin_named(root)
    path.write_bytes(RELEASE.replace(b"release-team", b"platform-team")
                     + SLIP)
    git("add", "--", OWN_PIN_NAMED, cwd=root)
    commit_in(root, "the release train moves to the platform team")
    commit_in(root, "an unrelated commit after it", "--allow-empty")
    return OWN_PIN_NAMED, "project"


@pytest.mark.parametrize("breaks", [
    pytest.param(project_contract_conflicted,
                 id="a-contract-of-the-projects-own-conflicted"),
    pytest.param(own_pin_named_edited_with_a_slip,
                 id="a-file-of-the-projects-own-named-like-a-pin-edited"),
    pytest.param(own_pin_named_conflicted,
                 id="a-file-of-the-projects-own-named-like-a-pin-conflicted"),
    pytest.param(own_pin_named_broken_by_a_commit,
                 id="a-file-of-the-projects-own-named-like-a-pin-committed"),
    pytest.param(leg_pin_in_a_squashed_root_commit,
                 id="a-leg-pin-with-no-good-copy-in-its-history"),
    pytest.param(leg_pin_added_back_after_its_deletion,
                 id="a-leg-pin-added-back-after-its-deletion"),
])
def test_a_file_git_cannot_put_back_is_left_to_a_person(standard, project,
                                                        breaks):
    """No git command to name: the NEXT is this doctor again, and its note
    says what the file should say is for a person to decide.

    A file of the project's own is never put back from git, because each
    of the three commands throws away an edit somebody made, so git is not
    asked (`project`). That holds for one named like a pin, in each of the
    three states: what the root declares decides, not the name. A pin with
    no good copy in its history has nothing to put back (`none`). Run as
    printed, the doctor finds the same file and touches none of it. Once a
    person mends the file, the row reads it.
    """
    rel, restore = breaks(project)
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["unreadable"] == [rel], row["detail"]
    assert_no_registration(row)
    assert row["detail"]["restore"] == {rel: restore}, row["detail"]
    assert "checkout" not in row["next"], row["next"]
    argv = pasted(row["next"])
    assert argv[0] == repo_shape.PYTHON, argv
    assert Path(argv[1]).name == DOCTOR and argv[2] == "--root", argv
    assert Path(argv[3]).resolve() == project.resolve(), argv
    assert "for a person to decide" in row["why"], row
    before = (project / rel).read_bytes()
    proc = subprocess.run(argv, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL,
                          env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert f"unreadable as YAML: {rel} (" in proc.stdout, proc.stdout
    assert (project / rel).read_bytes() == before
    if restore == "project":
        (project / rel).write_bytes(b"colour: green\n")
        again = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
        assert again["status"] == "ok", again


def test_an_unregistered_kind_beside_a_file_that_does_not_load(standard,
                                                               project):
    """Both in the reason, and the NEXT is the restore: the row cannot say
    what kind a file declares until it loads. Run, the row is the one the
    unregistered kind alone got, sentence, keys and all."""
    write_inventory(project)
    result = doctor(standard, project, "--json")
    alone = rows_of(result)["manifest-kinds"]
    assert alone["why"] == (
        shown_untracked(json.loads(result.stdout), INVENTORY) + ". "
        + UNREGISTERED_WAY), alone
    assert set(alone["detail"]) == {"validated", "unregistered", "unreadable",
                                    "registered_kinds"}, alone["detail"]
    break_the_pin(project, conflicted_pin)
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["unreadable"] == [SHAPE_PIN], row["detail"]
    assert_no_registration(row)
    assert row["reason"].startswith(
        "no validator registered for kind contracts/inventory.yaml "
        "(service-inventory); unreadable as YAML: contracts/shape-pin.yaml "
        "(yaml-unparsable: line "), row["reason"]
    assert row["detail"]["unregistered"] == alone["detail"]["unregistered"]
    assert row["detail"]["restore"] == {SHAPE_PIN: "uncommitted"}
    assert pasted(row["next"])[3:] == ["checkout", "HEAD", "--", SHAPE_PIN]
    run_pasted(row["next"])
    after = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert after == alone, (after, alone)


def test_the_shape_pin_goes_first_and_each_run_names_the_next_file(
        standard, project):
    """Three files that do not load: two pins and one of the project's own.

    The row prints one command. The shape pin's comes first, the command
    the `shape currency` row prints too, then the other pin's, then this
    doctor for the file a person mends. The project's file is never touched.
    """
    own = own_contract(project)
    for rel in (CODE_PIN, OWN_CONTRACT, SHAPE_PIN):
        path = project / rel
        path.write_bytes(path.read_bytes() + b"\xff\n")
    kinds, currency = kinds_and_currency(standard, project)
    assert kinds["detail"]["unreadable"] == [CODE_PIN, OWN_CONTRACT,
                                             SHAPE_PIN], kinds["detail"]
    assert_no_registration(kinds)
    assert kinds["detail"]["restore"] == {
        CODE_PIN: "uncommitted", OWN_CONTRACT: "project",
        SHAPE_PIN: "uncommitted"}, kinds["detail"]
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert pasted(kinds["next"])[3:] == ["checkout", "HEAD", "--", SHAPE_PIN]
    run_pasted(kinds["next"])
    kinds, _ = kinds_and_currency(standard, project)
    assert kinds["detail"]["unreadable"] == [CODE_PIN, OWN_CONTRACT], kinds
    assert pasted(kinds["next"])[3:] == ["checkout", "HEAD", "--", CODE_PIN]
    assert_no_registration(kinds)
    run_pasted(kinds["next"])
    kinds, _ = kinds_and_currency(standard, project)
    assert kinds["detail"]["unreadable"] == [OWN_CONTRACT], kinds
    assert kinds["detail"]["restore"] == {OWN_CONTRACT: "project"}, kinds
    assert Path(pasted(kinds["next"])[1]).name == DOCTOR, kinds["next"]
    assert_no_registration(kinds)
    assert own.read_bytes() == b"colour: blue\n\xff\n"


def declare_a_neutral_pin(root: Path) -> None:
    """`neutral_product_pins:` naming `openGlass` in `project.yaml`, and the
    pin it declares committed beside it, as `scaffold-project.py --pin`
    leaves the two."""
    manifest = root / "project.yaml"
    text = manifest.read_bytes()
    assert text.count(b"neutral_product_pins: []\n") == 1, text
    manifest.write_bytes(text.replace(b"neutral_product_pins: []\n",
                                      b"neutral_product_pins:\n"
                                      b"  - openGlass\n"))
    (root / NEUTRAL_PIN).write_bytes(
        b"pin_role: neutral-product\nproduct: openGlass\n"
        b'commit: "' + b"1" * 40 + b'"\n')
    git("add", "--", "project.yaml", NEUTRAL_PIN, cwd=root)
    commit_in(root, "a pin on the neutral product openGlass")


def test_a_pin_is_what_the_root_declares_not_what_it_is_called(standard,
                                                               project):
    """A neutral product pin `project.yaml` declares is asked of git, and a
    file of the project's own named like a pin is not.

    The declared pin's case is its git state, and its NEXT the `diff HEAD`
    that shows the change: no tool writes a neutral product pin after the
    scaffold, so the change is a person's and nothing is put back (review
    of PR #358). The file named like a pin is `project`, git not asked.
    Run as printed, neither file's bytes move.

    IN PROCESS, through the row alone: a declared neutral pin makes the
    `pins` row recheck its digest, and with no checkout of the product
    beside the root that asks `gh`, which no test here may reach.
    """
    declare_a_neutral_pin(project)
    own = own_pin_named(project)
    for rel in (NEUTRAL_PIN, OWN_PIN_NAMED):
        path = project / rel
        path.write_bytes(path.read_bytes() + b"\xff\n")
    neutral = (project / NEUTRAL_PIN).read_bytes()
    module = doctor_module(standard)
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["detail"]["unreadable"] == [NEUTRAL_PIN, OWN_PIN_NAMED], row
    assert row["detail"]["restore"] == {NEUTRAL_PIN: "uncommitted",
                                        OWN_PIN_NAMED: "project"}, row
    assert_no_registration(row)
    assert pasted(row["next"])[3:] == ["diff", "HEAD", "--",
                                       NEUTRAL_PIN], row["next"]
    # As bytes: the diff shows the byte that is not UTF-8.
    run_read_only(standard, project, row)
    again = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert again == row, (again, row)
    assert (project / NEUTRAL_PIN).read_bytes() == neutral
    assert own.read_bytes() == RELEASE + b"\xff\n"


def test_a_leg_pin_is_left_to_a_person_while_project_yaml_does_not_load(
        standard, project):
    """`project.yaml` declares the leg pins, so where it does not load it
    declares none, and a leg pin that does not load either is left alone
    for that run. The shape pin and the copies are declared by no manifest,
    and stay a tool's. Once `project.yaml` loads, the row puts the leg pin
    back.

    In process, because at this branch a root whose `project.yaml` does not
    load is not a shape root, and the doctor asks no row of it.
    """
    for rel in ("project.yaml", SPEC_PIN):
        path = project / rel
        path.write_bytes(path.read_bytes() + b"\xff\n")
    module = doctor_module(standard)
    ctx = module.Context(project)
    assert ctx.manifest is None
    row = module.check_manifest_kinds(ctx).as_dict()
    assert row["detail"]["restore"][SPEC_PIN] == "project", row["detail"]
    assert Path(pasted(row["next"])[1]).name == DOCTOR, row["next"]
    assert module.tool_written(ctx, SHAPE_PIN)
    assert module.tool_written(ctx, NAMING_COPY)
    git("checkout", "-q", "HEAD", "--", "project.yaml", cwd=project)
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["detail"]["restore"] == {SPEC_PIN: "uncommitted"}, row
    assert pasted(row["next"])[3:] == ["checkout", "HEAD", "--", SPEC_PIN]


def test_an_uncommitted_change_to_a_copy_is_shown_and_kept(standard,
                                                           project):
    """A copy can hold the project's own edit -- the merge by hand that
    `update-shape.py` asks for where a copy changed on both sides -- and
    git keeps no other copy of it until it is committed. So where HEAD's
    copy reads and the change here breaks it, the NEXT shows the change and
    puts nothing back. Run as printed, the bytes are still the person's.
    """
    copy = project / NAMING_COPY
    copy.write_bytes(copy.read_bytes() + SLIP)
    before = copy.read_bytes()
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["restore"] == {NAMING_COPY: "uncommitted"}, row
    assert_no_registration(row)
    assert pasted(row["next"])[3:] == ["diff", "HEAD", "--", NAMING_COPY], \
        row["next"]
    assert "checkout" not in row["next"], row["next"]
    assert "nothing is put back" in row["why"], row
    run_pasted(row["next"])
    assert copy.read_bytes() == before
    again = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert again["detail"]["restore"] == {NAMING_COPY: "uncommitted"}, again


def test_a_family_yaml_beside_a_file_that_does_not_load_names_the_restore_alone(
        standard, project, holder):
    """#211 and #291 in one row: the reason says both, and the NEXT is the
    restore ALONE, because joined to #211's sentence by `;` it would be a
    second command in a pasted line (#277). Run, the row is #211's."""
    family_beside(project, holder)
    break_the_pin(project, conflicted_pin)
    kinds, currency = kinds_and_currency(standard, project)
    assert FAMILY_BESIDE_OPENING in kinds["reason"], kinds["reason"]
    assert "unreadable as YAML: contracts/shape-pin.yaml (" in \
        kinds["reason"], kinds["reason"]
    assert_no_registration(kinds)
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert "family.py" not in kinds["next"], kinds["next"]
    run_pasted(kinds["next"])
    beside_row(doctor(standard, project, "--json"))


def test_a_contracts_family_yaml_beside_a_file_that_does_not_load_names_the_restore_alone(
        standard, project, holder):
    """#327 and #291 in one row: a `contracts/family.yaml` no gate in an
    assembly root reads, beside a conflicted pin. The reason and `detail`
    say both, and the NEXT is the restore ALONE, because #327's `take ...
    out of this root` joined to it by `;` would be a second command in a
    pasted line (#277). Run, the row is #327's, and its own NEXT, run in
    turn, leaves the root COMPLIANT."""
    elsewhere = ("no validator that runs in an assembly root is registered "
                 "for kind contracts/family.yaml (family-manifest: "
                 "scripts/validate-family.py runs only in a family holder)")
    shutil.copy2(holder["root"] / "family.yaml",
                 project / "contracts" / "family.yaml")
    commit_all(project, "A family manifest under contracts/")
    break_the_pin(project, conflicted_pin)
    kinds, currency = kinds_and_currency(standard, project)
    assert elsewhere in kinds["reason"], kinds["reason"]
    assert "unreadable as YAML: contracts/shape-pin.yaml (" in \
        kinds["reason"], kinds["reason"]
    assert set(kinds["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {
        "registered_elsewhere", "restore", "refusals"}, kinds["detail"]
    assert_no_registration(kinds)
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert " rm -- " not in kinds["next"], kinds["next"]
    run_pasted(kinds["next"])
    after = doctor(standard, project, "--json")
    row = only_finding_is_manifest_kinds(after)
    assert row["reason"] == elsewhere, row["reason"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | {
        "registered_elsewhere"}, row["detail"]
    run_the_removal(removal_named(row, json.loads(after.stdout),
                                  ["contracts/family.yaml"]), project)
    final = doctor(standard, project, "--json")
    assert final.returncode == 0, final.stdout + final.stderr
    assert json.loads(final.stdout)["verdict"] == "COMPLIANT"


# --- a copy or a neutral pin is a person's to mend (review of PR #358) ------
#
# Codex on 2745890, and rv358's probes P10 to P13. A copy can hold the
# project's own edit, above all the merge by hand `update-shape.py` asks for
# where a copy changed on both sides, so its `unmerged` and `committed`
# states get what its `uncommitted` state got: a read-only `git diff` and a
# person's merge, never one side taken whole and never a rollback (codex
# r4250578605). A copy is what the shape pin's `files:` rows name, not what
# this standard's copy lists name (codex r4250578619). And no tool writes a
# neutral product pin after the scaffold, so a change to one is a person's.

#: Lines a person writes into the naming copy. Comments, so that any copy
#: of the policy stays YAML, and the end of the file is where both sides of
#: a merge write, so git cannot merge the two tails.
PROJECT_LINE = b"# Atlas_docs: a line the project keeps in its copy\n"
PROJECT_TAIL = b"# a closing line the project wrote\n"
SHAPE_TAIL = b"# a closing line the shape wrote\n"
#: A conflict hunk, as git leaves one in the working file.
CONFLICT_HUNK = re.compile(
    rb"(?ms)^<<<<<<< [^\n]*\n(.*?)^=======\n(.*?)^>>>>>>> [^\n]*\n")


def insert_after_first_line(path: Path, line: bytes) -> None:
    first, rest = path.read_bytes().split(b"\n", 1)
    path.write_bytes(first + b"\n" + line + rest)


def append_to(path: Path, line: bytes) -> None:
    path.write_bytes(path.read_bytes() + line)


def repin(root: Path, rel: str) -> None:
    """The shape pin's `sha256:` for `rel` set to the file's bytes, as
    `update-shape.py apply` sets it once it has re-copied the file."""
    pin = root / SHAPE_PIN
    digest = hashlib.sha256((root / rel).read_bytes()).hexdigest()
    row = (rb'(?m)^(  - path: ' + re.escape(rel.encode())
           + rb'\n    sha256: )"[0-9a-f]{64}"$')
    text, count = re.subn(row, rb'\1"' + digest.encode() + rb'"',
                          pin.read_bytes())
    assert count == 1, rel
    pin.write_bytes(text)


def merge_two_edits(root: Path, edit_a, edit_b, *paths: str) -> str:
    """`edit-a` and `edit-b` from HEAD, each making its own edit of `paths`,
    and `edit-b` merging `edit-a`, so `--ours` is edit-b's side and git
    merges edit-a's hunks where it can. The status the merge leaves."""
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    for branch, edit in (("edit-a", edit_a), ("edit-b", edit_b)):
        git("checkout", "-q", "-b", branch, base, cwd=root)
        edit(root)
        git("add", "--", *paths, cwd=root)
        commit_in(root, branch)
    merged = subprocess.run(["git", "merge", "-q", "edit-a"], cwd=str(root),
                            capture_output=True, text=True, check=False,
                            env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    return git("status", "--porcelain=v1", cwd=root).stdout


def a_copy_conflicted_on_its_own(root: Path) -> None:
    """P10: edit-a is the project's own edit of the naming copy, a line
    near the top and a line at the end; edit-b is an `apply`-like re-copy
    that writes the end its own way and re-pins the copy. Git merges the
    project's line and conflicts on the end. Only the copy is `UU`: the
    shape pin changed on one side alone."""
    def project_edit(r: Path) -> None:
        insert_after_first_line(r / NAMING_COPY, PROJECT_LINE)
        append_to(r / NAMING_COPY, PROJECT_TAIL)

    def apply_like(r: Path) -> None:
        append_to(r / NAMING_COPY, SHAPE_TAIL)
        repin(r, NAMING_COPY)

    status = merge_two_edits(root, project_edit, apply_like, NAMING_COPY,
                             SHAPE_PIN)
    assert f"UU {NAMING_COPY}" in status and SHAPE_PIN not in status, status
    held = (root / NAMING_COPY).read_bytes()
    for line in (PROJECT_LINE, PROJECT_TAIL, SHAPE_TAIL):
        assert line in held, line


def merge_by_hand(path: Path) -> None:
    """A person's merge: both sides of every conflict hunk kept, and the
    hunks git merged left as they are."""
    held = path.read_bytes()
    merged, count = CONFLICT_HUNK.subn(rb"\1\2", held)
    assert count == 1 and b"<<<<<<<" not in merged, held[-400:]
    path.write_bytes(merged)


def run_read_only(standard: Path, root: Path, row: dict) -> bytes:
    """Run the printed NEXT, which must be `git -C <root> diff ...`, or the
    `git -C <root> log -p ...` that shows the last commit to change a file
    (review of PR #555, round 2), and require that it changed nothing: the
    file's bytes, the status, HEAD. Its output."""
    argv = pasted(row["next"])
    assert argv[:2] == ["git", "-C"], row["next"]
    assert argv[3] in ("diff", "log"), row["next"]
    assert "checkout" not in row["next"], row["next"]
    rel = argv[-1]
    before = ((root / rel).read_bytes(),
              git("status", "--porcelain=v1", cwd=root).stdout,
              git("rev-parse", "HEAD", cwd=root).stdout)
    proc = subprocess.run(argv, capture_output=True, check=False,
                          stdin=subprocess.DEVNULL,
                          env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert ((root / rel).read_bytes(),
            git("status", "--porcelain=v1", cwd=root).stdout,
            git("rev-parse", "HEAD", cwd=root).stdout) == before
    return proc.stdout


def test_a_copy_conflicted_on_its_own_is_shown_and_merged_by_a_person(
        standard, project):
    """P10 (codex r4250578605). The NEXT was `checkout --ours`, the
    apply-like side whole: run, and the merge finished as its note said,
    the root was COMPLIANT and HEAD's copy had lost the project's line and
    its tail, which git had merged or held for a person.

    Now the NEXT is the `diff` that shows the hunk git could not merge,
    its note says a person merges it, and it changes nothing. Merged by
    hand, both sides kept, the row reads the copy again.
    """
    a_copy_conflicted_on_its_own(project)
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["unreadable"] == [NAMING_COPY], row["detail"]
    assert row["detail"]["restore"] == {NAMING_COPY: "unmerged"}, row
    assert_no_registration(row)
    assert pasted(row["next"])[3:] == ["diff", "--", NAMING_COPY], \
        row["next"]
    note = row["why"]
    assert "neither side is taken whole" in note, note
    assert "merge it by hand, keeping the hunks git merged" in note, note
    shown = run_read_only(standard, project, row)
    assert SHAPE_TAIL.strip() in shown and PROJECT_TAIL.strip() in shown, \
        shown
    merge_by_hand(project / NAMING_COPY)
    git("add", "--", NAMING_COPY, cwd=project)
    commit_in(project, "the naming copy merged by hand")
    again = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert again["status"] == "ok", again
    kept = git("show", f"HEAD:{NAMING_COPY}", cwd=project).stdout
    for line in (PROJECT_LINE, PROJECT_TAIL, SHAPE_TAIL):
        assert line.decode() in kept, line


def test_a_conflicted_copys_next_agrees_with_shape_currency_and_agents_md(
        standard, project):
    """P10b. In the same report the `shape currency` row named `apply
    --accept-local` on the copy, which keeps the local bytes, while the
    `manifest kinds` row took one side whole. AGENTS.md says `both` is a
    merge: by hand, commit, then `--accept-local` on the file merged.

    Now the `manifest kinds` row asks for that merge, and the two rows
    are one path: the merge by hand, then the `shape currency` row's own
    NEXT, run as its note spells it, ends COMPLIANT with every line of
    both sides in the copy and its pin.

    THE FLAG IS THE PERSON'S, NOT THE ROW'S (#501). The `why`'s `apply`
    carries no `--accept-local`: run as printed it is refused
    `update-local-drift`, which asks whether the project keeps the merge,
    and with the person's `--accept-local` on the copy it ends COMPLIANT.
    """
    a_copy_conflicted_on_its_own(project)
    kinds, currency = kinds_and_currency(standard, project)
    assert "merge it by hand" in kinds["why"], kinds
    assert "checkout" not in kinds["next"], kinds["next"]
    assert "--accept-local" not in currency["next"] + currency["why"], \
        currency
    merge_by_hand(project / NAMING_COPY)
    git("add", "--", NAMING_COPY, cwd=project)
    commit_in(project, "the naming copy merged by hand")
    kinds, currency = kinds_and_currency(standard, project)
    assert kinds["status"] == "ok", kinds
    argv = pasted(currency["next"])
    assert Path(argv[1]).name == "update-shape.py" and argv[2] == "check", \
        currency["next"]
    then = currency["why"].split()
    assert then[:2] == ["then", "apply"], currency["why"]
    assert "--accept-local" not in then, then
    apply = (standard / "update-shape.py", "apply", "--root", str(project),
             "--upstream", str(standard), *then[2:])
    asked = run_script(*apply)
    assert asked.returncode == 2, asked.stdout + asked.stderr
    assert "REFUSED update-local-drift" in asked.stderr, asked.stderr
    assert f"--accept-local {NAMING_COPY}" in asked.stderr, asked.stderr
    applied = run_script(*apply, "--accept-local", NAMING_COPY)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    compliant_again(standard, project)
    kept = git("show", f"HEAD:{NAMING_COPY}", cwd=project).stdout
    for line in (PROJECT_LINE, PROJECT_TAIL, SHAPE_TAIL):
        assert line.decode() in kept, line


def drop_the_copys_row(root: Path) -> None:
    """The naming copy's `files:` row taken out of the shape pin and
    committed, as an adopted project that made the file its own does."""
    pin = root / SHAPE_PIN
    row = (rb'(?m)^  - path: ' + re.escape(NAMING_COPY.encode())
           + rb'\n    sha256: "[0-9a-f]{64}"\n')
    text, count = re.subn(row, b"", pin.read_bytes())
    assert count == 1
    pin.write_bytes(text)
    git("add", "--", SHAPE_PIN, cwd=root)
    commit_in(root, "the naming policy is the project's own now")


def test_a_file_the_shape_pin_has_no_row_for_is_the_projects(standard,
                                                            project):
    """P11a (codex r4250578619). The pin has no row for
    `contracts/repository-naming.yaml`, so the file there is the
    project's, and the root is COMPLIANT. A commit of the project's own
    breaks it: the NEXT was `checkout <that commit>~1`, the copy this
    standard's lists name, and it dropped the project's line.

    Now the copy is what the rows say, so the file is `project`, git is not
    asked, and the NEXT is this doctor again, which touches nothing.
    """
    drop_the_copys_row(project)
    compliant_again(standard, project)
    own = project / NAMING_COPY
    insert_after_first_line(own, PROJECT_LINE)
    append_to(own, SLIP)
    git("add", "--", NAMING_COPY, cwd=project)
    commit_in(project, "the project's own naming examples, with a slip")
    commit_in(project, "an unrelated commit after it", "--allow-empty")
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["restore"] == {NAMING_COPY: "project"}, row
    assert "checkout" not in row["next"], row["next"]
    argv = pasted(row["next"])
    assert Path(argv[1]).name == DOCTOR, row["next"]
    before = own.read_bytes()
    proc = subprocess.run(argv, capture_output=True, text=True, check=False,
                          stdin=subprocess.DEVNULL,
                          env={**os.environ, **GIT_IDENTITY})
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert own.read_bytes() == before and PROJECT_LINE in before
    module = doctor_module(standard)
    ctx = module.Context(project)
    assert NAMING_COPY not in module.pinned_copies(ctx)
    assert "Makefile" in module.pinned_copies(ctx)
    assert not module.tool_written(ctx, NAMING_COPY)


def collision_layout(root: Path) -> None:
    """An in-place adoption that collided on the naming policy: the shape's
    copy under `shape/`, the pin's row naming it there, as
    `shape_materialize` writes the two, and the source's own file at
    `contracts/repository-naming.yaml`, which no row names."""
    copy = (root / NAMING_COPY).read_bytes()
    (root / "shape" / "contracts").mkdir(parents=True)
    (root / "shape" / NAMING_COPY).write_bytes(copy)
    pin = root / SHAPE_PIN
    text = pin.read_bytes()
    row = f"  - path: {NAMING_COPY}\n".encode()
    assert text.count(row) == 1, text
    pin.write_bytes(text.replace(row, f"  - path: shape/{NAMING_COPY}\n"
                                 .encode()))
    git("add", "--", SHAPE_PIN, f"shape/{NAMING_COPY}", cwd=root)
    commit_in(root, "the shape's copy under shape/, the source's own file "
                    "at contracts/")


def test_the_sources_own_file_at_a_collided_copy_path_is_the_projects(
        standard, project):
    """P11b (codex r4250578619). In the collision layout the source's own
    `contracts/repository-naming.yaml` is conflicted, the other side's line
    merged cleanly. The NEXT was `checkout --ours`, which dropped that
    line. Now the file is `project`, and the NEXT is this doctor again,
    which leaves the merge as git left it."""
    collision_layout(project)
    compliant_again(standard, project)

    def ours(r: Path) -> None:
        insert_after_first_line(r / NAMING_COPY, PROJECT_LINE)
        append_to(r / NAMING_COPY, PROJECT_TAIL)

    status = merge_two_edits(
        project, ours, lambda r: append_to(r / NAMING_COPY, SHAPE_TAIL),
        NAMING_COPY)
    assert f"UU {NAMING_COPY}" in status, status
    own = project / NAMING_COPY
    before = own.read_bytes()
    assert PROJECT_LINE in before
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["restore"] == {NAMING_COPY: "project"}, row
    assert "checkout" not in row["next"], row["next"]
    assert Path(pasted(row["next"])[1]).name == DOCTOR, row["next"]
    run = subprocess.run(pasted(row["next"]), capture_output=True,
                         text=True, check=False, stdin=subprocess.DEVNULL,
                         env={**os.environ, **GIT_IDENTITY})
    assert run.returncode == 1, run.stdout + run.stderr
    assert own.read_bytes() == before
    assert f"UU {NAMING_COPY}" in git("status", "--porcelain=v1",
                                       cwd=project).stdout


def test_a_conflicted_shape_pin_takes_only_the_copies_its_side_has_rows_for(
        standard, project):
    """Codex r4250578619 in the shape pin's own merge (#267): the pin and
    the source's own `contracts/repository-naming.yaml` conflicted
    together, in the collision layout. The NEXT took that file whole with
    the pin, because this standard's copy lists name its path.

    Now the side taken is read for its rows, which name the copy under
    `shape/` and not the source's file, so the pin is named alone, by both
    rows, and the source's file keeps both sides for its owner.
    """
    collision_layout(project)

    def side(digit: str, tail: bytes):
        def edit(r: Path) -> None:
            break_the_pin(r, pin_with(r'^commit: .*$',
                                      f'commit: "{digit * 40}"'))
            append_to(r / NAMING_COPY, tail)
        return edit

    status = merge_two_edits(project, side("1", PROJECT_TAIL),
                             side("2", SHAPE_TAIL), SHAPE_PIN, NAMING_COPY)
    assert f"UU {SHAPE_PIN}" in status and f"UU {NAMING_COPY}" in status, \
        status
    own = project / NAMING_COPY
    before = own.read_bytes()
    kinds, currency = kinds_and_currency(standard, project)
    assert currency["detail"]["restore"] == "unmerged", currency["detail"]
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert kinds["detail"]["restore"] == {NAMING_COPY: "project",
                                          SHAPE_PIN: "unmerged"}, kinds
    run_pasted(currency["next"])
    assert own.read_bytes() == before
    again = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert again["detail"].get("error") not in READ_PIN_CODES, again


def test_a_committed_hand_merge_of_a_copy_is_shown_not_rolled_back(
        standard, project):
    """P12 (codex r4250578605, the committed state). A hand merge of the
    copy, as `update-shape.py`'s `both` exit asks for, committed with a
    slip in it. The NEXT was `checkout <that commit>~1`, which dropped the
    merge from the tree.

    Now the NEXT is the `diff` from the newest copy that reads, which shows
    the merge and the slip and changes nothing. Mended and committed, the
    row reads the copy again, with the merge in it.
    """
    copy = project / NAMING_COPY
    insert_after_first_line(copy, PROJECT_LINE)
    append_to(copy, SLIP)
    git("add", "--", NAMING_COPY, cwd=project)
    breaking = commit_in(project, "the hand merge, with a slip")
    commit_in(project, "an unrelated commit after it", "--allow-empty")
    row = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert row["detail"]["restore"] == {NAMING_COPY: "committed"}, row
    assert_no_registration(row)
    assert pasted(row["next"])[3:] == ["diff", f"{breaking}~1", "--",
                                       NAMING_COPY], row["next"]
    note = row["why"]
    assert breaking[:12] in note and "nothing is rolled back" in note, note
    shown = run_read_only(standard, project, row)
    assert PROJECT_LINE.strip() in shown and SLIP.strip() in shown, shown
    copy.write_bytes(copy.read_bytes()[:-len(SLIP)])
    git("add", "--", NAMING_COPY, cwd=project)
    commit_in(project, "the slip mended")
    again = rows_of(doctor(standard, project, "--json"))["manifest-kinds"]
    assert again["status"] == "ok", again
    assert PROJECT_LINE.decode() in git("show", f"HEAD:{NAMING_COPY}",
                                        cwd=project).stdout


def neutral_pin_body(digit: str) -> bytes:
    return (b"pin_role: neutral-product\nproduct: openGlass\n"
            b'commit: "' + digit.encode() * 40 + b'"\n')


def neutral_pin_re_pinned_by_hand(root: Path) -> tuple[str, list]:
    # P13: re-pinned by hand to another commit, with a slip, uncommitted.
    # `checkout HEAD` discarded the re-pin.
    (root / NEUTRAL_PIN).write_bytes(neutral_pin_body("2") + SLIP)
    return "uncommitted", ["diff", "HEAD", "--", NEUTRAL_PIN]


def neutral_pin_re_pin_committed(root: Path) -> tuple[str, list]:
    # The same re-pin committed. `checkout <it>~1` rolled it back.
    (root / NEUTRAL_PIN).write_bytes(neutral_pin_body("2") + SLIP)
    git("add", "--", NEUTRAL_PIN, cwd=root)
    breaking = commit_in(root, "openGlass re-pinned by hand, with a slip")
    commit_in(root, "an unrelated commit after it", "--allow-empty")
    return "committed", ["diff", f"{breaking}~1", "--", NEUTRAL_PIN]


def neutral_pin_re_pins_conflicted(root: Path) -> tuple[str, list]:
    # Two people re-pin it, each to their own commit. `checkout --ours`
    # took one of them whole.
    status = merge_two_edits(
        root,
        lambda r: (r / NEUTRAL_PIN).write_bytes(neutral_pin_body("2")),
        lambda r: (r / NEUTRAL_PIN).write_bytes(neutral_pin_body("3")),
        NEUTRAL_PIN)
    assert f"UU {NEUTRAL_PIN}" in status, status
    return "unmerged", ["diff", "--", NEUTRAL_PIN]


@pytest.mark.parametrize("breaks", [
    pytest.param(neutral_pin_re_pinned_by_hand,
                 id="re-pinned-by-hand-uncommitted"),
    pytest.param(neutral_pin_re_pin_committed, id="a-hand-re-pin-committed"),
    pytest.param(neutral_pin_re_pins_conflicted,
                 id="two-hand-re-pins-conflicted"),
])
def test_a_neutral_product_pin_is_shown_never_put_back(standard, project,
                                                        breaks):
    """P13. No tool writes a neutral product pin after the scaffold, and the
    manifest template says to add one by hand, so every change to one is a
    person's. In each git state the NEXT is a read-only `diff`, run as
    printed it changes nothing, and the person's re-pin is still there.

    In process, for the reason `test_a_pin_is_what_the_root_declares_not_
    what_it_is_called` gives: a declared neutral pin sends the `pins` row
    to `gh`.
    """
    declare_a_neutral_pin(project)
    restore, expected = breaks(project)
    before = (project / NEUTRAL_PIN).read_bytes()
    module = doctor_module(standard)
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert row["detail"]["unreadable"] == [NEUTRAL_PIN], row["detail"]
    assert row["detail"]["restore"] == {NEUTRAL_PIN: restore}, row
    assert_no_registration(row)
    assert pasted(row["next"])[3:] == expected, row["next"]
    assert "No tool of this standard writes a neutral product pin" in \
        row["why"], row
    # One `so` to a sentence (review of PR #358): the reason ended in its own
    # ", so every change to one was made by a person", and the note's ", so
    # neither side is taken whole" or ", so nothing is rolled back" followed.
    assert not any(sentence.count(", so ") > 1 for sentence in
                   row["why"].split(". ")), row["why"]
    run_read_only(standard, project, row)
    assert (project / NEUTRAL_PIN).read_bytes() == before
    assert b"2" * 40 in before


# --- a wrong `kind:` in a file a gate reads (review of PR #555, round 2) ----
#
# Round 1 kept such a file out of every NEXT and said that "its own row
# judges it". For the shape pin and a neutral product pin no row does:
# `validate-pins.py` reads their fields and never their kind. So the row was
# a FINDING with no NEXT, and its `why` sent the reader to a row that said
# `ok`. The NEXT now shows, read-only, how the file came to declare that
# kind, and the `why` names the kind a gate here reads its path as, and the
# row that judges it.

#: The kind a gate here reads every pin as.
PIN_KIND = "pinned_contract_manifest"
#: A kind one letter short of it, which nothing registers.
MISSPELT_KIND = "pinned_contract_manifes"

#: Each wrong kind given to the shape pin, whether it is committed, the
#: row's reason, and the `detail` keys beyond main's. E1 and E2 are the
#: review's: a kind nothing registers, and one registered to a gate that
#: runs only in a holder. E4 is a kind whose check runs here, which the row
#: counted `validated`, COMPLIANT, though no gate checks the shape pin's kind.
SHAPE_PIN_WRONG_KIND = {
    "e1-a-kind-nothing-registers": (
        MISSPELT_KIND, True,
        f"no validator registered for kind {SHAPE_PIN} ({MISSPELT_KIND})",
        set()),
    "e1-uncommitted": (
        MISSPELT_KIND, False,
        f"no validator registered for kind {SHAPE_PIN} ({MISSPELT_KIND})",
        set()),
    "e2-a-kind-a-holder-runs": (
        "family-manifest", True,
        "no validator that runs in an assembly root is registered for kind "
        f"{SHAPE_PIN} (family-manifest: scripts/validate-family.py runs only "
        "in a family holder)", {"registered_elsewhere"}),
    "e4-a-kind-checked-here": (
        "repository-naming-policy", True,
        f"{SHAPE_PIN} declares kind repository-naming-policy where a gate "
        f"here reads it as {PIN_KIND}, and no gate here checks the kind it "
        "declares", {"misdeclared"}),
}


def misdeclared_why(rel: str, kind: str, judge: str | None,
                    committed: bool) -> str:
    """The `manifest kinds` row's whole `why` for `rel`, a pin a gate here
    reads, declaring `kind`: what its NEXT shows, both kinds, which row
    judges it -- `judge`'s gate, or this row where no gate checks the kind
    -- and to put the kind line back. No other way out: registering the
    kind, or moving what the file describes to a holder, is no answer for a
    pin. Spelt out here for the reason `FAMILY_BESIDE_WAY` is."""
    shown = (f"shows the last commit that changed {rel}" if committed else
             f"shows the change to {rel} that no commit holds")
    judged = (f"the {judge} row's gate finds that too" if judge else
              "no gate here checks the kind it declares, so this row is the "
              "one that says so")
    return (f"{shown}. {rel} declares kind {kind} where a gate here reads "
            f"it as {PIN_KIND}, and {judged}: put its kind line back to "
            f"{PIN_KIND}")


def give_a_kind(root: Path, rel: str, kind: str, commit: bool) -> bytes:
    """`rel`'s `kind:` line made to declare `kind`, committed or not, and
    the bytes it held before, to put back."""
    path = root / rel
    body = path.read_bytes()
    line = f"kind: {PIN_KIND}\n".encode()
    assert body.count(line) == 1, body
    path.write_bytes(body.replace(line, f"kind: {kind}\n".encode()))
    if commit:
        commit_all(root, f"{rel} declares {kind}")
    return body


def shows_the_kind(standard: Path, root: Path, row: dict, kind: str) -> None:
    """Run the row's read-only NEXT, which changes nothing, and require that
    it shows the line that declares `kind`."""
    shown = run_read_only(standard, root, row).splitlines()
    assert f"+kind: {kind}".encode() in shown, shown


@pytest.mark.parametrize("case", list(SHAPE_PIN_WRONG_KIND))
def test_a_wrong_kind_in_the_shape_pin_is_shown_never_a_dead_end(
        standard, project, case):
    """E1, E2 and E4: the shape pin given another kind, a FINDING of this
    row alone, INVALID. Its NEXT is the `git log -p -1` of the commit that
    gave it that kind, or the `git diff HEAD` of a change no commit holds,
    and its `why` says no gate here checks the kind, so this row says so,
    and to put the kind line back -- nothing else. Run as printed, the NEXT
    shows the line and changes nothing; with the line put back, the root is
    COMPLIANT again.
    """
    kind, commit, reason, more = SHAPE_PIN_WRONG_KIND[case]
    body = give_a_kind(project, SHAPE_PIN, kind, commit)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (manifest-kinds)", payload
    row = only_finding_is_manifest_kinds(result)
    assert row["reason"] == reason, row["reason"]
    assert set(row["detail"]) == MANIFEST_KINDS_DETAIL_KEYS | more, row
    if "misdeclared" in more:
        assert row["detail"]["misdeclared"] == [
            {"manifest": SHAPE_PIN, "kind": kind, "read_as": PIN_KIND,
             "git": "committed"}], row["detail"]
    assert row["next"] == removal_command(
        payload, "log -p -1" if commit else "diff HEAD", [SHAPE_PIN]), row
    assert row["why"] == misdeclared_why(SHAPE_PIN, kind, None, commit), \
        row["why"]
    shows_the_kind(standard, project, row, kind)

    (project / SHAPE_PIN).write_bytes(body)
    if commit:
        commit_all(project, "Put the shape pin's kind line back")
    compliant_again(standard, project)


def test_a_leg_pin_of_the_wrong_kind_is_offered_no_registration(standard,
                                                                project):
    """E3: the spec leg's pin given a kind nothing registers. The `pins`
    row's gate refuses it `pin-wrong-kind`, and this row's `why` says that
    gate finds it too, where it offered to register the kind; the NEXT
    shows the commit that gave it."""
    give_a_kind(project, SPEC_PIN, MISSPELT_KIND, True)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "INVALID (pins, manifest-kinds)", payload
    rows = rows_of(result)
    assert "pin-wrong-kind" in rows["pins"]["reason"], rows["pins"]
    row = rows["manifest-kinds"]
    assert row["next"] == removal_command(payload, "log -p -1",
                                          [SPEC_PIN]), row
    assert row["why"] == misdeclared_why(SPEC_PIN, MISSPELT_KIND, "pins",
                                         True), row["why"]
    shows_the_kind(standard, project, row, MISSPELT_KIND)


def test_a_declared_neutral_pin_of_the_wrong_kind_is_this_rows_to_say(
        standard, project):
    """A neutral product pin `project.yaml` declares, given a kind nothing
    registers: like the shape pin's, no gate checks its kind, so this row
    is the one that says so, and its NEXT shows the commit.

    In process, for the reason `test_a_pin_is_what_the_root_declares_not_
    what_it_is_called` gives: a declared neutral pin sends the `pins` row
    to `gh`."""
    declare_a_neutral_pin(project)
    pin = project / NEUTRAL_PIN
    pin.write_bytes(f"kind: {MISSPELT_KIND}\n".encode() + pin.read_bytes())
    commit_all(project, "The neutral pin declares a kind nothing registers")
    module = doctor_module(standard)
    row = module.check_manifest_kinds(module.Context(project)).as_dict()
    assert_next_holds_no_prose(row)
    assert row["detail"]["unregistered"] == [
        f"{NEUTRAL_PIN} ({MISSPELT_KIND})"], row["detail"]
    assert row["next"] == (f"git -C {module.quote_arg(project)} log -p -1 "
                           f"-- {NEUTRAL_PIN}"), row
    assert row["why"] == misdeclared_why(NEUTRAL_PIN, MISSPELT_KIND, None,
                                         True), row["why"]
    shows_the_kind(standard, project, row, MISSPELT_KIND)


# --- the shape pin and a copy conflicted together (#485) --------------------
#
# Review of PR #358 (probes OD and OD2), filed as #485. Two branches that
# each re-pin the shape: on one a person edits a copy and keeps the edit
# with `update-shape.py apply --accept-local`, the exit the `shape currency`
# row names for it; on the other `apply` takes a newer standard that wrote
# the same end of that copy. Merged, the shape pin and the copy are both
# conflicted. The NEXT took the copy whole with the pin, as one tool's
# output, and with the update side as `--ours` the person's lines were gone,
# the hunk git had merged with them, and the doctor then said COMPLIANT.
# Now the NEXT takes the pin alone, and the copy is a person's to merge, as
# a copy conflicted on its own is.

#: The project's own Makefile target, and the one the standard's newer
#: Makefile gains: both at the end of the file, so git cannot merge them.
OWN_TARGET = b"\n# the project's own target\nship:\n\t@echo shipping Atlas\n"
NEWER_TARGET = b"\n# a target the standard gained\ndoctor:\n\t@echo doctor\n"


def standard_appended(standard: Path, tmp_path: Path, rel: str,
                      tail: bytes) -> tuple:
    """`(a copy of standard, S1, S2)`: S1 is the commit every project here
    is scaffolded at, S2 one more commit appending `tail` to the standard's
    `rel`, so `apply --at S2` re-copies the file made from it. A copy, with
    its `.git`, so the session's `standard` is left as every test finds it.
    """
    moved = tmp_path / "moved" / "openRepoShape"
    shutil.copytree(standard, moved, symlinks=True)
    s1 = git("rev-parse", "HEAD", cwd=moved).stdout.strip()
    append_to(moved / rel, tail)
    commit_all(moved, f"{rel} gains a line")
    return moved, s1, git("rev-parse", "HEAD", cwd=moved).stdout.strip()


def apply_and_commit(moved: Path, root: Path, *args: str) -> None:
    """The real `update-shape.py apply --yes`, and what it wrote committed."""
    applied = run_script(moved / "update-shape.py", "apply", "--root",
                         str(root), "--upstream", str(moved), "--yes", *args)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    commit_all(root, "update-shape.py apply " + " ".join(args))


def two_shape_updates_merged(moved: Path, s1: str, s2: str, root: Path,
                             copy: str, edit, ours: str) -> bytes:
    """Probe OD's state, built with the real `update-shape.py`.

    Branch `local`: `edit` changes `copy`, committed, then kept with `apply
    --at S1 --accept-local <copy>`, which re-pins it from the project's
    bytes. Branch `upgrade`: `apply --at S2`, which re-copies it from the
    newer standard and re-pins the shape. Both from HEAD, and `ours`
    merges the other, which leaves the copy and the shape pin `UU`. The
    copy's bytes as the merge left them.
    """
    base = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    git("checkout", "-q", "-b", "local", base, cwd=root)
    edit(root)
    git("add", "--", copy, cwd=root)
    commit_in(root, f"the project's own edit of {copy}")
    apply_and_commit(moved, root, "--at", s1, "--accept-local", copy)
    git("checkout", "-q", "-b", "upgrade", base, cwd=root)
    apply_and_commit(moved, root, "--at", s2)
    git("checkout", "-q", ours, cwd=root)
    theirs = "local" if ours == "upgrade" else "upgrade"
    merged = subprocess.run(["git", "merge", "-q", theirs], cwd=str(root),
                            capture_output=True, text=True, check=False,
                            env={**os.environ, **GIT_IDENTITY})
    assert merged.returncode != 0, merged.stdout + merged.stderr
    status = git("status", "--porcelain=v1", cwd=root).stdout
    assert f"UU {copy}" in status and f"UU {SHAPE_PIN}" in status, status
    return (root / copy).read_bytes()


def verdict_of(standard: Path, root: Path) -> tuple[str, dict]:
    result = doctor(standard, root, "--json")
    return json.loads(result.stdout)["verdict"], rows_of(result)


def assert_the_merge_is_unfinished(verdict: str, rows: dict,
                                   paths: list) -> None:
    """#424's rung over #485's state: while the index holds the copy and
    the shape pin unmerged, before the NEXT and after it, since `checkout
    --ours` writes the tree and leaves the index as it was, the verdict is
    `INVALID (merge)` and the `merge` row names both, with git's read-only
    `status` as its NEXT. The `shape currency` and `manifest kinds` rows
    still answer, and what they print is what the person finishing the
    merge reads."""
    assert verdict == "INVALID (merge)", (verdict, rows)
    merge = rows["merge"]
    assert merge["status"] == "FINDING", merge
    assert merge["detail"]["unmerged"] == sorted(paths), merge["detail"]
    assert merge["detail"]["merging"] is True, merge["detail"]
    argv = pasted(merge["next"])
    assert argv[:2] == ["git", "-C"] and argv[3:] == ["status"], merge


def assert_the_merge_is_finished(verdict: str, rows: dict,
                                 state: str) -> None:
    """Once the copy merged by hand is committed, the merge's own row is
    gone, and it is the copy, kept unlike the pin, that keeps the root
    from COMPLIANT: `state` is what `update-shape.py check` calls it."""
    assert "merge" not in rows, rows["merge"]
    assert verdict == f"DRIFTED (1 {state})", (verdict, rows)


def assert_the_pin_alone_is_taken(currency: dict, kinds: dict,
                                  copy: str) -> None:
    """The shape pin's NEXT names the pin alone, both rows print it, and
    its `why` and `left_for_a_person` give the copy to a person."""
    assert currency["detail"]["restore"] == "unmerged", currency["detail"]
    assert pasted(currency["next"])[3:] == [
        "checkout", "--ours", "--", SHAPE_PIN], currency["next"]
    assert currency["detail"]["left_for_a_person"] == [copy], currency
    assert kinds["next"] == currency["next"], (kinds, currency)
    assert kinds["why"] == currency["why"], (kinds, currency)
    assert kinds["detail"]["left_for_a_person"] == [copy], kinds["detail"]
    note = currency["why"]
    assert f"{copy} is a copy conflicted too" in note, note
    assert "merges it by hand, keeping the hunks git merged" in note, note
    assert "Take one side of the pin whole and never a hand-merged pin" \
        in note, note
    assert "every path named" not in note, note
    for words in ("update-shape.py apply --accept-local on that copy "
                  "re-pins it from the merge",
                  "The shape currency row never names it",
                  "check calls the copy locally-modified, the apply the row "
                  "names is refused as update-local-drift",
                  "where check calls it both, as update-conflict, and "
                  "either refusal asks for --accept-local on that path"):
        assert words in note, (words, note)
    assert_a_plain_next(currency)


def re_pinned_from_the_merge(moved: Path, root: Path, currency: dict,
                             copy: str, ours: str) -> None:
    """The `why`'s last sentences, followed from the `shape currency` row
    both ways round (review of PR #496, F1), to COMPLIANT.

    The row's `apply` names no `--accept-local` either way round, as
    AGENTS.md's rule 3 wants (#501): run as spelled it moves nothing and
    asks for the flag on that path. With the update side's pin taken, the
    copy as merged is `locally-modified`, and the refusal is
    `update-local-drift`; with the person's side's pin taken, behind the
    standard the copy was merged from, it is `both`, and the refusal is
    `update-conflict`. Either way the person's `apply --accept-local
    <copy>` re-pins the copy from the merge and the root is COMPLIANT.
    """
    then = currency["why"].split()
    assert then[:2] == ["then", "apply"], currency["why"]
    args = then[2:]
    apply = (moved / "update-shape.py", "apply", "--root", str(root),
             "--upstream", str(moved))
    assert "--accept-local" not in args, then

    def held() -> tuple:
        return (git("rev-parse", "HEAD", cwd=root).stdout,
                git("branch", "--list", cwd=root).stdout,
                git("status", "--porcelain=v1", cwd=root).stdout,
                (root / copy).read_bytes())

    before = held()
    refused = run_script(*apply, *args)
    said = refused.stdout + refused.stderr
    assert refused.returncode == 2, said
    if ours == "upgrade":
        assert "update-local-drift" in said, said
        assert f"--accept-local {copy}" in said, said
    else:
        assert "update-conflict" in said and f"    {copy}: " in said, said
        assert "--accept-local on that path" in said, said
    assert held() == before, "the refused apply moved something"
    args = [*args, "--accept-local", copy]
    applied = run_script(*apply, *args)
    assert applied.returncode == 0, applied.stdout + applied.stderr
    compliant_again(moved, root)


@pytest.mark.parametrize("ours", [
    pytest.param("upgrade", id="the-update-side-ours"),
    pytest.param("local", id="the-persons-side-ours"),
])
def test_a_copy_conflicted_with_the_shape_pin_is_left_to_a_person(
        standard, project, tmp_path, ours):
    """Probe OD (#485): the naming copy edited and accepted on `local`, its
    end rewritten by an upgrade on `upgrade`, merged either way.

    The NEXT was `checkout --ours -- <copy> contracts/shape-pin.yaml`.
    With the update side as ours it dropped the project's line, which git
    had merged, and its tail; the merge finished, the doctor said
    COMPLIANT. With the person's side as ours it dropped the upgrade's.

    Now, run as pasted, it leaves the copy as the merge left it. The
    `manifest kinds` row's `restore` calls the copy `unmerged`, the case
    it is in, where it said `project` while its NEXT overwrote the file.
    The next run names the copy's read-only `diff`, and the doctor is not
    COMPLIANT until a person has merged it and, where the merge differs
    from the pin, re-pinned it with `apply --accept-local` on their word:
    the `shape currency` row's `apply` never names the flag (#501), and
    refused, it asks for it, `update-local-drift` for a `locally-modified`
    copy and `update-conflict` for a `both` one. HEAD then holds every
    line of both sides, either way round.

    Until the merge is committed the verdict is #424's `INVALID (merge)`,
    the index holding the copy and the pin unmerged before the NEXT and
    after it. Once it is, the `merge` row is gone and the verdict is the
    copy's drift, so COMPLIANT still waits on the copy, not on the merge.
    """
    moved, s1, s2 = standard_appended(standard, tmp_path, NAMING_COPY,
                                      SHAPE_TAIL)

    def person(r: Path) -> None:
        insert_after_first_line(r / NAMING_COPY, PROJECT_LINE)
        append_to(r / NAMING_COPY, PROJECT_TAIL)

    held = two_shape_updates_merged(moved, s1, s2, project, NAMING_COPY,
                                    person, ours)
    for line in (PROJECT_LINE, PROJECT_TAIL, SHAPE_TAIL):
        assert line in held, line
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_unfinished(verdict, rows, [NAMING_COPY, SHAPE_PIN])
    kinds, currency = rows["manifest-kinds"], rows["shape-currency"]
    run_pasted(currency["next"])
    assert (project / NAMING_COPY).read_bytes() == held, \
        "the NEXT took one side of the copy whole"
    assert_the_pin_alone_is_taken(currency, kinds, NAMING_COPY)
    assert kinds["detail"]["restore"] == {NAMING_COPY: "unmerged",
                                          SHAPE_PIN: "unmerged"}, kinds
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_unfinished(verdict, rows, [NAMING_COPY, SHAPE_PIN])
    kinds = rows["manifest-kinds"]
    assert kinds["detail"]["restore"] == {NAMING_COPY: "unmerged"}, kinds
    assert pasted(kinds["next"])[3:] == ["diff", "--", NAMING_COPY], kinds
    shown = run_read_only(moved, project, kinds)
    assert PROJECT_TAIL.strip() in shown and SHAPE_TAIL.strip() in shown
    merge_by_hand(project / NAMING_COPY)
    git("add", "--", NAMING_COPY, SHAPE_PIN, cwd=project)
    commit_in(project, "the copy merged by hand")
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_finished(
        verdict, rows, "locally-modified" if ours == "upgrade" else "both")
    re_pinned_from_the_merge(moved, project, rows["shape-currency"],
                             NAMING_COPY, ours)
    kept = git("show", f"HEAD:{NAMING_COPY}", cwd=project).stdout
    for line in (PROJECT_LINE, PROJECT_TAIL, SHAPE_TAIL):
        assert line.decode() in kept, line


@pytest.mark.parametrize("ours", [
    pytest.param("upgrade", id="the-update-side-ours"),
    pytest.param("local", id="the-persons-side-ours"),
])
def test_a_makefile_conflicted_with_the_shape_pin_keeps_the_projects_target(
        standard, project, tmp_path, ours):
    """Probe OD2 (#485), the copy a project most often edits. The project
    appends its own target to the Makefile and keeps it with
    `--accept-local`, and the standard's newer Makefile appends another.
    Either branch merges the other (review of PR #496, N2).

    The NEXT named `Makefile` with the pin, and once the merge was finished
    HEAD's Makefile had lost the other side's target and, with the update
    side as ours, the doctor said COMPLIANT. Now the Makefile keeps both
    sides through the NEXT, the doctor is not COMPLIANT until a person has
    merged it and accepted the merge, and HEAD's Makefile then holds both
    targets. Until the merge is committed the verdict is #424's `INVALID
    (merge)`, and after it the Makefile's drift: `locally-modified` with
    the update side's pin taken, `both` with the person's.
    """
    moved, s1, s2 = standard_appended(standard, tmp_path, UPSTREAM_TARGET,
                                      NEWER_TARGET)
    held = two_shape_updates_merged(
        moved, s1, s2, project, "Makefile",
        lambda r: append_to(r / "Makefile", OWN_TARGET), ours)
    assert b"ship:" in held and b"doctor:" in held, held[-400:]
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_unfinished(verdict, rows, ["Makefile", SHAPE_PIN])
    kinds, currency = rows["manifest-kinds"], rows["shape-currency"]
    run_pasted(currency["next"])
    assert (project / "Makefile").read_bytes() == held, \
        "the NEXT took one side of the Makefile whole"
    assert_the_pin_alone_is_taken(currency, kinds, "Makefile")
    assert kinds["detail"]["restore"] == {SHAPE_PIN: "unmerged"}, kinds
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_unfinished(verdict, rows, ["Makefile", SHAPE_PIN])
    merge_by_hand(project / "Makefile")
    git("add", "--", "Makefile", SHAPE_PIN, cwd=project)
    commit_in(project, "the Makefile merged by hand")
    verdict, rows = verdict_of(moved, project)
    assert_the_merge_is_finished(
        verdict, rows, "locally-modified" if ours == "upgrade" else "both")
    re_pinned_from_the_merge(moved, project, rows["shape-currency"],
                             "Makefile", ours)
    kept = git("show", "HEAD:Makefile", cwd=project).stdout
    assert "ship:" in kept and "doctor:" in kept, kept[-400:]


# --- placement: code in spec, spec in code (#99) ----------------------------
#
# Brett Heap, 2026-09-10: "we have to look for code in spec and spec in code".
# The row runs the ADOPTION'S policy over a project that is already split, and
# every test below is a claim about one of the four answers it can give: `ok`,
# `note` for a path the policy will not call, `FINDING` for one in the wrong
# leg, and `n/a` where there is no leg to ask about.

def stage(leg: Path, name: str, body: str = "x\n") -> None:
    """Put a file in a leg's INDEX and leave that leg's HEAD where it is.

    `git add` and NO commit, deliberately. `ls-files` reads the index, so the
    doctor sees the file — and the leg stays AT ITS PIN, which keeps the
    verdict under test `MISPLACED` rather than `DRIFTED`. Those are two
    different claims about two different things, and a fixture that tripped
    both would prove neither. The committed case has its own test below, and
    what it asserts is the precedence between them.
    """
    target = leg / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", "--", name], cwd=str(leg),
                   capture_output=True, check=True)


def adoption_module(standard: Path):
    """`adopt-project.py` from the standard under test, as a module.

    The same load `shape-doctor.py` does, for the same reason — a hyphen in
    the filename — and it is how these tests read a placement plan with the
    reader that wrote it rather than with a second one.
    """
    spec = importlib.util.spec_from_file_location(
        "adopt_project_under_test", standard / "adopt-project.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_a_scaffolded_projects_legs_have_nothing_in_the_wrong_one(standard,
                                                                  project):
    """The base case: what the standard's own scaffold writes is `ok`.

    IT IS NOT A TAUTOLOGY, and this is the test that would have caught the
    obvious first version of this row. `templates/spec-root/` ships
    `README.md`, `AGENTS.md`, `CLAUDE.md` and `.gitignore`, and the path
    policy classifies all four as `root` — correctly, for a repository being
    SPLIT, where exactly one of each stays in the assembly root. A row that
    read that verdict literally would call every leg this standard has ever
    cut misplaced on its first day. So the four are read OUT OF THE TEMPLATES
    at run time and never judged, and `--json` says so.
    """
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "COMPLIANT"
    assert payload["placement_plan"] is None
    row = rows_of(result)["placement"]
    assert row["status"] == "ok", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == []
    assert row["detail"]["policy"].endswith("contracts/path-classification.yaml")
    everywhere = row["detail"]["everywhere"]
    for name in ("README.md", "AGENTS.md", "CLAUDE.md", ".gitignore"):
        assert name in everywhere, (name, everywhere)
    legs = {entry["role"]: entry for entry in row["detail"]["legs"]}
    assert set(legs) == {"spec", "code"}
    for entry in legs.values():
        assert entry["state"] == "audited", entry
        assert entry["misplaced"] == 0, entry
        assert entry["review_required"] == 0, entry
        assert entry["tracked"] > entry["classified"], (
            "every leg the scaffold writes carries files the row must ignore, "
            "so `classified` is strictly fewer than `tracked` here")


def test_code_in_the_spec_leg_and_spec_in_the_code_leg_is_misplaced(standard,
                                                                    project):
    """The question in Brett Heap's sentence, both directions at once.

    A `.py` in the spec leg is CODE by the extension table; a
    `requirements/*.md` in the code leg is SPEC by the `spec-governance` rule.
    Each is named with the rule that judged it, because the policy's whole
    posture is that a reader disagrees with a NAMED rule rather than with an
    opaque verdict — and a row that said "2 paths are wrong" without them
    would be exactly the opaque verdict.
    """
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    stage(project / "code", "requirements/one.md", "# a requirement\n")
    result = doctor(standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith("MISPLACED (2 paths)"), \
        result.stdout
    assert "spec/tool.py: code by rule extension-majority" in result.stdout
    assert "code/requirements/: spec by rule spec-governance" in result.stdout
    assert "1 code in the spec leg" in result.stdout
    assert "1 spec in the code leg" in result.stdout
    assert "--placement-plan" in result.stdout, (
        "a finding names its fix, and this one's is the plan")

    rows = rows_of(doctor(standard, project, "--json"))
    row = rows["placement"]
    assert row["status"] == "FINDING"
    assert row["detail"]["counts"] == {"misplaced": 2, "review_required": 0,
                                       "unread_legs": 0,
                                       "unwritable_names": 0}, (
        "both legs were read in full, so the two counts that qualify a clean "
        "answer are zero and the row is entitled to the word `FINDING`")
    found = {entry["path"]: entry for entry in row["detail"]["misplaced"]}
    assert set(found) == {"spec/tool.py", "code/requirements/"}
    assert found["spec/tool.py"]["leg"] == "spec"
    assert found["spec/tool.py"]["classified_as"] == "code"
    assert found["spec/tool.py"]["rule"] == "extension-majority"
    assert found["spec/tool.py"]["review_required"] is False
    assert found["code/requirements/"]["leg"] == "code"
    assert found["code/requirements/"]["classified_as"] == "spec"
    assert found["code/requirements/"]["rule"] == "spec-governance"
    # And nothing else went red: the legs are at their pins and every
    # validator is green, which is what makes MISPLACED the whole verdict.
    assert rows["legs"]["status"] == "ok"
    assert rows["pins"]["status"] == "ok"


def test_a_path_the_policy_will_not_call_is_a_note_and_still_compliant(
        standard, project):
    """`review_required` is a question for a human, never a finding.

    `examples/` is the policy's own worked example of an honest `ambiguous`:
    a golden-run corpus is the specification's acceptance evidence or the
    tests' fixture, and the directory name does not say which. A row that
    failed somebody's repository for a question nobody has answered would be
    the `leg shape files` mistake again — inventing a rule to fail them by.
    """
    stage(project / "spec", "examples/golden-run/expected.yaml", "result: ok\n")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    [entry] = row["detail"]["review_required"]
    assert entry["path"] == "spec/examples/"
    assert entry["classified_as"] is None
    assert entry["review_required"] is True
    assert entry["rule"] == "ambiguous-examples"
    assert "acceptance evidence" in entry["question"]
    assert "will not call" in row["reason"]


def test_the_files_every_repository_carries_are_never_misplaced(standard,
                                                                project):
    """The allowlist, asserted on the two cases that would otherwise bite.

    A `LICENSE` classifies as `root` and a `.github/workflows/*.yml` as
    `code` — so a spec leg with a licence and its own lint workflow, which is
    an ordinary spec leg, would be two findings under a row that read the
    policy literally. `.github/**` is ignored WHOLE for exactly this: a leg
    runs its own CI, and the workflow that runs it is not a file in the wrong
    repository.
    """
    stage(project / "spec", "LICENSE", "Apache-2.0\n")
    stage(project / "spec", ".github/workflows/lint.yml", "on: [push]\n")
    stage(project / "spec", ".gitattributes", "* text=auto eol=lf\n")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    row = rows_of(result)["placement"]
    assert row["status"] == "ok", row
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"


def test_a_directory_whose_files_agree_is_ONE_path_however_many_files(
        standard, project):
    """A thousand files in one misplaced directory are ONE decision.

    `walk()` is the adoption's own fold and this row borrows it rather than
    classifying file by file, for two reasons that are the same reason. A
    reader has to READ this: a thousand rows for one mistake would bury it.
    And the run has to finish: it is one `git ls-files` and one process, with
    no subprocess per path, so a leg of this size answers in seconds.
    """
    leg = project / "spec"
    (leg / "src").mkdir()
    for index in range(1000):
        (leg / "src" / f"mod_{index:04d}.py").write_text(
            f"VALUE = {index}\n", encoding="utf-8")
    subprocess.run(["git", "add", "--", "src"], cwd=str(leg),
                   capture_output=True, check=True)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "MISPLACED (1 path)"
    row = rows_of(result)["placement"]
    [entry] = row["detail"]["misplaced"]
    assert entry["path"] == "spec/src/"
    assert entry["files"] == 1000, entry
    assert entry["classified_as"] == "code"
    spec = [leg for leg in row["detail"]["legs"] if leg["role"] == "spec"][0]
    assert spec["paths"] < spec["classified"], (
        "the whole point of the fold: fewer paths to read than files read")


def test_a_leg_off_its_pin_outranks_a_misplaced_path(standard, project):
    """COMMITTING the misplaced file walks the leg off its pin, and DRIFTED
    wins the verdict line — while the placement row is still printed.

    The precedence is deliberate and this is the case that argues it: the
    paths this row read are the paths in a leg that is no longer the one the
    pin describes, so `make bootstrap` comes before deciding anything about
    where a file should live. Both rows are in the table, which is the rule
    the whole report is built on: the verdict names the most specific
    finding, the table names every one.
    """
    leg = project / "spec"
    stage(leg, "tool.py", "VALUE = 1\n")
    subprocess.run(["git", "commit", "-q", "-m", "a python file in the spec leg"],
                   cwd=str(leg), capture_output=True, check=True,
                   env={**os.environ, **GIT_IDENTITY})
    result = doctor(standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith("DRIFTED ("), result.stdout
    assert "leg(s) not at the pin" in verdict_line(result)
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["legs"]["status"] == "FINDING"
    assert rows["placement"]["status"] == "FINDING", (
        "the row is still asked and still printed; only the verdict LINE is "
        "somebody else's")
    assert [entry["path"] for entry in rows["placement"]["detail"]["misplaced"]] \
        == ["spec/tool.py"]


def test_a_leg_whose_role_the_policy_has_no_class_for_is_not_guessed_at(
        standard, project):
    """`spec`, `code`, `root`, ambiguous — and nothing else.

    A leg declaring some other role is a leg this policy has no opinion
    about, and the honest answer is to say so and audit the other one. The
    alternative is to compare its paths against a class that does not exist,
    which would report every file in it as misplaced.
    """
    manifest = project / "project.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "role: spec", "role: prose", 1), encoding="utf-8")
    row = rows_of(doctor(standard, project, "--json"))["placement"]
    legs = {entry["role"]: entry for entry in row["detail"]["legs"]}
    assert "prose" in legs, row["detail"]["legs"]
    assert "not one that the path policy classifies" in legs["prose"]["state"]
    assert legs["code"]["state"] == "audited"


# --- the placement plan -----------------------------------------------------

def test_the_placement_plan_is_written_and_the_root_is_untouched(standard,
                                                                 project,
                                                                 tmp_path):
    """The ONE thing this command writes, and it writes it where it was told.

    `test_the_doctor_writes_nothing` is the promise for every other run; this
    is the same promise for the run that takes a `--placement-plan`. The
    plan lands at the named path and NOTHING under the repository moves —
    which is the whole posture: a path changing legs is a pull request on
    each leg and a pin bump in the root, and none of those is an edit this
    command is entitled to make.
    """
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    stage(project / "code", "requirements/one.md", "# a requirement\n")

    def snapshot():
        return sorted(
            (path.relative_to(project).as_posix(), path.stat().st_size)
            for path in project.rglob("*") if path.is_file())

    before = snapshot()
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--placement-plan", str(out))
    assert result.returncode == 1, result.stdout + result.stderr
    assert snapshot() == before, "the repository under the root moved"
    assert out.is_file()
    assert f"placement plan written to {out.as_posix()}" in result.stdout
    assert verdict_line(result).startswith("MISPLACED (2 paths)")

    adopt = adoption_module(standard)
    data = adopt.load_yaml(out)
    assert data["kind"] == adopt.PLACEMENT_PLAN_KIND
    assert data["kind"] != adopt.PLAN_KIND
    entries = {entry["path"]: entry for entry in data["paths"]}
    assert set(entries) == {"spec/tool.py", "code/requirements/"}
    assert entries["spec/tool.py"]["in_leg"] == "spec"
    assert entries["spec/tool.py"]["leg"] == "code"
    assert entries["spec/tool.py"]["resolution"] == "", (
        "every entry's resolution is empty and is the human's line")
    assert "README.md" in data["ignored"], (
        "the plan says what it declined to look at, so a reader is not left "
        "to infer the allowlist from what is missing")
    # `--json` says where it went too, so a caller need not parse the table.
    as_json = doctor(standard, project, "--json", "--placement-plan", str(out))
    assert json.loads(as_json.stdout)["placement_plan"] == out.as_posix()


def test_the_placement_plans_entries_are_adoption_plan_entries(standard,
                                                               project,
                                                               tmp_path):
    """The claim that makes "resolve it as you resolve an adoption plan" true.

    Read by the ADOPTION'S OWN READER: the plan's `paths:` are handed to
    `adopt-project.py`'s `Plan` with nothing changed but the `kind:` this file
    carries on purpose, and its own `_leg_findings` is asked what it thinks of
    them. It must not refuse on their SHAPE — every key it reads is there and
    every `leg:` it can act on is one of its four words — and it must refuse
    on exactly the unresolved ones, which is what `review_required: true`
    means in both files.
    """
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    stage(project / "spec", "examples/golden-run/expected.yaml", "result: ok\n")
    out = tmp_path / "placement-plan.yaml"
    assert doctor(standard, project,
                  "--placement-plan", str(out)).returncode == 1

    adopt = adoption_module(standard)
    data = dict(adopt.load_yaml(out))
    data["kind"], data["mode"] = adopt.PLAN_KIND, "in-place"
    plan = adopt.Plan(out, data)
    assert len(plan.entries) == 2
    # A placement plan has no source tree, and `None` says so: its `legs:`
    # is a list, with no mount path the tree would be read for.
    findings = adopt._leg_findings(plan, None)
    assert [f.split(":")[0] for f in findings] == \
        ["FINDING plan-unresolved"], findings
    assert "spec/examples/" in findings[0]
    assert "acceptance evidence" in findings[0], (
        "the question travels with the entry, which is what a human answers")
    # Answering it the way `conftest.resolve` answers an adoption plan's
    # entry leaves nothing for the adoption reader to refuse.
    for entry in plan.entries:
        if entry.get("leg") is None:
            entry["leg"] = "spec"
    assert adopt._leg_findings(plan, None) == []


def test_the_adoption_tool_refuses_a_placement_plan_and_names_the_doctor(
        standard, project, tmp_path):
    """`kind:` is the boundary, and the boundary is a SAFETY property.

    An adoption plan is the input to `adopt-project.py execute`, which
    creates two repositories and rewrites history with `git filter-repo`. A
    placement plan describes a project that has already been split, so a file
    that called itself an adoption plan would be that command aimed at an
    assembly root, with `--yes` the only thing in the way. It is refused by
    name — and the refusal says which tool consumes one, because the two
    files look alike precisely because their entries are alike.
    """
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    out = tmp_path / "placement-plan.yaml"
    assert doctor(standard, project,
                  "--placement-plan", str(out)).returncode == 1
    result = run_script(standard / "adopt-project.py", "check",
                        "--plan", str(out))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED plan-wrong-kind" in result.stderr
    assert "'placement-plan', expected 'adoption-plan'" in result.stderr
    assert "shape-doctor.py --placement-plan" in result.stderr
    assert "aimed at an assembly root" in result.stderr


def test_a_root_with_no_placement_audit_refuses_the_flag_by_name(standard,
                                                                 holder,
                                                                 tmp_path):
    """A family holder has no legs, so there is no plan to write.

    Exit 3 — usage or environment — and not a verdict about the holder: the
    question is about the FLAG, and printing `COMPLIANT` under a refusal
    about a plan nobody could write would answer something nobody asked.
    """
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, holder["root"], "--placement-plan", str(out))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "REFUSED shape-doctor-no-placement-audit" in result.stderr
    assert "each member is an assembly root" in result.stderr
    assert not out.exists()


def test_the_placement_plan_creates_no_directory(standard, project, tmp_path):
    """A path whose parent is not there is a typo, and it is refused as one.

    A command that answered a mistyped path by making a directory tree is a
    command that writes where nobody will look for it.
    """
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    out = tmp_path / "nowhere" / "placement-plan.yaml"
    result = doctor(standard, project, "--placement-plan", str(out))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "shape-doctor-placement-plan-unwritable" in result.stderr
    assert "creates no directory" in result.stderr
    assert not out.parent.exists()


def test_a_directory_that_is_not_a_shape_root_refuses_the_flag_too(standard,
                                                                   tmp_path):
    """No manifest, so no legs, so no row and no plan — and it says which.

    A different sentence from the holder's, because it is a different fact: a
    holder HAS the question and does not have legs; this directory does not
    have the question. Exit 3 either way, because both are about the flag.
    """
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, here, "--placement-plan", str(out))
    assert result.returncode == 3, result.stdout + result.stderr
    assert "REFUSED shape-doctor-no-placement-audit" in result.stderr
    assert "not an assembly root (none)" in result.stderr
    assert not out.exists()


# --- the placement row declines to guess (the review on PR #100) -----------

def test_a_leg_that_is_not_its_own_repository_is_not_read(standard, project):
    """`git -C` DISCOVERS, and that is how this row could read the root.

    Run in a plain directory, `git` walks UP and answers from the enclosing
    repository — so a leg mount that is not a submodule at all would have the
    ASSEMBLY ROOT's index read as if it were the leg's contents. The row
    declines, names why, and — the half that matters — does NOT then say `ok`
    about a repository one of whose legs nobody read.
    """
    rmtree(project / "spec")
    (project / "spec").mkdir()
    (project / "spec" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    row = rows_of(doctor(standard, project, "--json"))["placement"]
    legs = {entry["role"]: entry for entry in row["detail"]["legs"]}
    assert "not a repository of its own" in legs["spec"]["state"], legs
    assert legs["code"]["state"] == "audited", legs
    assert row["status"] == "note", row
    assert row["detail"]["counts"]["unread_legs"] == 1
    assert "not everything could be" in row["reason"]
    assert row["detail"]["misplaced"] == [], (
        "spec/tool.py is in the ROOT's index, not the leg's, and reporting it "
        "would be this row telling somebody about a file it never read")


def test_a_leg_the_manifest_points_outside_the_root_is_never_read(standard,
                                                                  project,
                                                                  tmp_path):
    """`path:` comes out of `project.yaml`, which this command does not own.

    A `..`, an absolute path or a symlink makes `root / rel` a directory
    somewhere else, and a `git ls-files` there would put another checkout's
    paths and sizes into this report and into the plan. The manifest
    validator has its own opinion about such a `path:`; this row must not act
    on it in the meantime.
    """
    elsewhere = project.parent / "outside"
    elsewhere.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=elsewhere)
    (elsewhere / "secret.py").write_text("TOKEN = 1\n", encoding="utf-8")
    commit_all(elsewhere, "somebody else's repository")

    manifest = project / "project.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            'path: "spec"', 'path: "../outside"', 1), encoding="utf-8")
    row = rows_of(doctor(standard, project, "--json"))["placement"]
    legs = {entry["role"]: entry for entry in row["detail"]["legs"]}
    assert "outside" in legs["spec"]["state"], legs
    assert "nothing outside the root that was named is read" in \
        legs["spec"]["state"]
    assert row["status"] == "note", row
    assert "secret.py" not in json.dumps(row), (
        "not one path of the repository next door may appear in this report")


@pytest.mark.skipif(os.name == "nt",
                    reason="Windows has no filename with a newline in it")
def test_a_tracked_name_no_plan_can_carry_is_reported_and_never_written(
        standard, project, tmp_path):
    """Git allows any byte but `/` and NUL in a name; YAML does not.

    A newline in a filename would split one plan entry across two lines, and
    a name that is not UTF-8 at all raises `UnicodeEncodeError` in the
    writer — a traceback out of a command whose whole promise is that it
    reports. Such a path is excluded from the classification and REPORTED by
    `repr`, and the plan it is kept out of still parses.
    """
    stage(project / "spec", "tool\ns.py", "VALUE = 1\n")
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--json", "--placement-plan", str(out))
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["counts"]["unwritable_names"] == 1
    spec = [leg for leg in row["detail"]["legs"] if leg["role"] == "spec"][0]
    assert spec["unwritable"] == ["'tool\\ns.py'"], spec
    assert "no report or plan can carry" in row["reason"]
    # And the plan it was kept out of is still a file the reader can read.
    adopt = adoption_module(standard)
    data = adopt.load_yaml(out)
    assert data["kind"] == adopt.PLACEMENT_PLAN_KIND
    assert (data.get("paths") or []) == []


def test_the_misplaced_verdict_needs_an_actual_misplaced_path(standard,
                                                              project):
    """A red `placement` row with nothing in it is INVALID, not MISPLACED.

    `run_checks` turns an exception out of any check into a FINDING row with
    an empty detail — so the verdict branch, reading a length, would have
    answered `MISPLACED (0 paths)`: a verdict naming a count of zero, about a
    row that never got as far as classifying anything.
    """
    spec = importlib.util.spec_from_file_location("shape_doctor_verdicts",
                                                  standard / DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    ctx = module.Context(project)
    assert ctx.kind == module.PROJECT
    blown = module.Row("placement", "placement", module.FINDING,
                       "could not be run: [Errno 13] Permission denied",
                       None, {})
    verdict, code = module.verdict_for(ctx, [blown])
    assert verdict == "INVALID (placement)", verdict
    assert code == 1
    # And with a path in it, the same row IS the verdict.
    real = module.Row("placement", "placement", module.FINDING, "two of them",
                      None, {"misplaced": [{"path": "spec/a.py"},
                                           {"path": "code/b.md"}]})
    assert module.verdict_for(ctx, [real])[0] == "MISPLACED (2 paths)"


@pytest.mark.skipif(os.name == "nt",
                    reason="a symlink needs a privilege Windows CI has not")
def test_a_tracked_symlink_is_never_followed_out_of_the_leg(standard, project,
                                                            tmp_path):
    """`stat` follows; `lstat` does not, and here the two disagree about which
    file is being measured.

    A tracked symlink's BLOB is the target path it holds, so the link's own
    length is the honest size — and `secret -> /outside/big` would otherwise
    have this row read metadata outside the very root `outside_the_root`
    keeps it inside of, and put that size in the report and in the plan.
    """
    outside = tmp_path / "big.py"
    outside.write_text("X" * 5000, encoding="utf-8")
    link = project / "spec" / "borrowed.py"
    link.symlink_to(outside)
    subprocess.run(["git", "add", "--", "borrowed.py"],
                   cwd=str(project / "spec"), capture_output=True, check=True)
    row = rows_of(doctor(standard, project, "--json"))["placement"]
    [entry] = row["detail"]["misplaced"]
    assert entry["path"] == "spec/borrowed.py"
    assert entry["bytes"] == len(str(outside)), entry
    assert entry["bytes"] != 5000, (
        "the size reported is the link's, never the file it points at")


# --- placement: a submodule a leg keeps (#176) ------------------------------
#
# The path policy is globs, and a glob cannot tell a gitlink from a file: a
# submodule vendored at `.cursor` or `.specify/vendored` reads as the
# assistant instructions or the Spec-Kit tooling the 2026-09-02 ruling roots.
# But the assembly root keeps no submodule but its legs, so an adoption keeps
# such a submodule in a LEG (#166) -- and this row called that MISPLACED, exit
# 1, over a placement `adopt-project.py` had required.


#: What a `kept` submodule's note says, spelt out here and not imported from
#: the doctor: the wording is the coordinator's, and a test that read it back
#: from the thing under test would pass whatever it said (Codex review on
#: #186, round 2).
KEPT_NOTE = ("a submodule; the assembly root keeps no source submodule "
             "(#166), so a leg holds it")


def unverifiable_note(rule: str, leg: str) -> str:
    """What an `unverifiable` submodule's note says: a path the rule `rule`
    assigns to the `leg` leg, which the submodule is not in."""
    return (f"a submodule at a path rule `{rule}` assigns to the {leg} leg; "
            "a submodule's leg is the adoption plan's answer and the doctor "
            "cannot verify it here: confirm against the plan, or move it")


def stage_gitlink(leg: Path, name: str) -> None:
    """Record a SUBMODULE at `name` in a leg's index, as `stage` does a file.

    `git update-index --cacheinfo 160000,...` writes the gitlink and nothing
    else: no working tree under it, no `.gitmodules`, no commit. That is the
    whole of what the row reads -- the index, where a gitlink's MODE is -- and
    leaving the leg's HEAD alone keeps it at its pin, so the verdict under
    test is the placement row's and not `DRIFTED`. The commit it records is
    the leg's own HEAD: a real commit, which is all a gitlink names.
    """
    commit = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"160000,{commit},{name}",
        cwd=leg)


def path_policy(standard: Path):
    """The standard's own path policy, loaded by the adoption's own loader.

    So that a test can say what the POLICY makes of a name before it says
    what the row does with a submodule there: a test whose path the policy
    had stopped rooting would pass without proving anything.
    """
    return adoption_module(standard).PathPolicy.load(
        standard / "contracts" / "path-classification.yaml")


@pytest.mark.parametrize("name,rule", [
    (".cursor", "root-assistant-instructions"),
    (".specify/vendored", "root-spec-kit"),
])
def test_a_submodule_a_leg_keeps_under_a_root_ruled_path_is_a_note(
        standard, project, name, rule):
    """THE DEFECT #176 WAS FILED FOR, at both of its paths.

    The policy roots both NAMES, rightly for a file: the 2026-09-02 ruling
    keeps assistant instructions and Spec-Kit tooling in the assembly root.
    A SUBMODULE there cannot follow it, because the root keeps no submodule
    but its legs, so a leg keeps it -- and the row reported `code/.cursor:
    root by rule root-assistant-instructions` and exited 1. It is a `note`
    now, naming the submodule and why the leg keeps it, and the verdict is
    the one every other row makes it: COMPLIANT, exit 0.
    """
    verdict = path_policy(standard).classify_file(name)
    assert (verdict.leg, verdict.rule) == ("root", rule), (
        "the policy must still root this NAME, or this test proves nothing "
        "about a row that stopped believing it for a submodule")
    stage_gitlink(project / "code", name)
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == [], (
        "a submodule a leg keeps is no question either: the question was "
        "asked when the repository was adopted")
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == f"code/{name}", kept
    assert kept["leg"] == "code"
    assert kept["path_in_leg"] == name
    assert kept["placement"] == "kept", (
        "a root rule names this path, and the root keeps no source submodule: "
        "a leg holds it", kept)
    assert kept["rule"] == rule, kept
    assert kept["note"].startswith(KEPT_NOTE), kept
    assert f"`{rule}`" in kept["note"], (
        "the rule the doctor did not apply to a submodule is named", kept)
    assert row["detail"]["counts"]["submodules"] == 1
    assert f"code/{name}" in row["reason"], row["reason"]
    assert ("the assembly root keeps no source submodule (#166)"
            in row["reason"]), row["reason"]
    assert f"(rule {rule})" in row["reason"], row["reason"]
    assert "cannot verify" not in row["reason"], (
        "a submodule at a root-ruled path is not one a rule puts in the "
        "other leg", row["reason"])
    assert "root by rule" not in row["reason"], row["reason"]
    assert row["next"] is None, (
        "a note with nothing to resolve names no command to run")
    text = doctor(standard, project)
    assert text.returncode == 0, text.stdout + text.stderr
    assert verdict_line(text).startswith("COMPLIANT   (exit 0)"), text.stdout
    assert "root by rule" not in text.stdout, text.stdout


def test_a_file_beside_a_kept_submodule_is_still_judged(standard, project):
    """THE RULING STILL ROOTS THE FILES, and only the gitlink is set aside.

    An adoption that answered a whole `.specify/` `code` -- the vendored
    submodule AND the project's constitution beside it -- put a FILE in the
    code leg that the 2026-09-02 ruling keeps in the root, and that file is
    as misplaced as it ever was. So the row still says MISPLACED, for one
    path holding one file: the gitlink neither votes in the fold of
    `.specify/` nor counts as a file under it, and is named on its own.
    """
    def code_leg(row) -> dict:
        return [leg for leg in row["detail"]["legs"]
                if leg["role"] == "code"][0]

    before = code_leg(rows_of(doctor(standard, project, "--json"))[
        "placement"])
    stage_gitlink(project / "code", ".specify/vendored")
    stage(project / "code", ".specify/memory/constitution.md", "# rules\n")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "MISPLACED (1 path)"
    row = rows_of(result)["placement"]
    assert row["status"] == "FINDING", row
    [entry] = row["detail"]["misplaced"]
    assert entry["path"] == "code/.specify/", entry
    assert entry["rule"] == "root-spec-kit"
    assert entry["files"] == 1, (
        "the constitution is the one FILE under `.specify/`; a gitlink "
        "counted there would be a submodule judged by its path again")
    assert [kept["path"] for kept in row["detail"]["submodules"]] == \
        ["code/.specify/vendored"]
    assert "code/.specify/vendored" in row["reason"], row["reason"]
    assert "--placement-plan" in row["next"], (
        "the misplaced FILE still names its fix")
    after = code_leg(row)
    assert after["tracked"] == before["tracked"] + 2, (before, after)
    assert after["classified"] == before["classified"] + 1, (
        "the gitlink is TRACKED and is not CLASSIFIED; only the file is",
        before, after)


def test_a_submodule_at_a_path_no_rule_claims_leaves_the_verdict_alone(
        standard, project):
    """No rule names `vendor/lib`, and the verdict is what it was.

    Before #176 the policy's `default` asked its question about the gitlink
    as if it were a file -- `code/vendor/: ambiguous by rule default`, a
    `note` -- and a question about a submodule offering `root` among its
    answers is one a submodule cannot take. It is the submodule note now,
    and nothing a reader acts on moved: the row is a `note` either way and
    the verdict is COMPLIANT, exit 0.
    """
    verdict = path_policy(standard).classify_file("vendor/lib")
    assert (verdict.leg, verdict.rule) == (None, "default"), (
        "fixture: no rule may claim this path")
    stage_gitlink(project / "code", "vendor/lib")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == []
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == "code/vendor/lib", kept
    assert kept["placement"] == "kept", kept
    assert kept["rule"] is None, (
        "no rule names this path, so none is named", kept)
    assert kept["note"] == KEPT_NOTE, kept
    assert "cannot verify" not in row["reason"], row["reason"]


def test_a_submodule_the_policy_sends_to_the_other_leg_is_unverifiable(
        standard, project):
    """A PLACEMENT THE DOCTOR CANNOT VERIFY, NAMING THE RULE (#166, Codex
    review on #186, round 2).

    `adopt-project.py plan` asks the `.gitmodules` question of every entry
    that holds a gitlink, not only the root-ruled ones, so a theme submodule
    at `docs/theme` -- `spec` by `spec-governance` -- may be answered `code`
    by the person adopting, and was. Reporting it as spec in the code leg
    would be the same defect one rule along. But a project adopted before
    that question, or with a submodule added by hand, has the same gitlink in
    the same leg and NOBODY's answer behind it, and the assembly records
    which of the two this is nowhere. So the row says exactly that: it names
    the rule, says the doctor cannot verify the leg, and asks for it to be
    confirmed against the plan or moved. It is still a `note` and the verdict
    is still COMPLIANT: MISPLACED would call the answered case a finding,
    which is #176 over again.
    """
    verdict = path_policy(standard).classify_file("docs/theme")
    assert (verdict.leg, verdict.rule) == ("spec", "spec-governance")
    stage_gitlink(project / "code", "docs/theme")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == []
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == "code/docs/theme", kept
    assert kept["leg"] == "code"
    assert kept["placement"] == "unverifiable", kept
    assert kept["rule"] == "spec-governance", kept
    assert kept["note"] == unverifiable_note("spec-governance", "spec"), kept
    assert row["detail"]["counts"]["submodules"] == 1
    assert "code/docs/theme (rule spec-governance)" in row["reason"], (
        row["reason"])
    for phrase in ("assigns to the other leg", "cannot verify",
                   "adoption plan's answer",
                   "confirm against the plan, or move it"):
        assert phrase in row["reason"], (phrase, row["reason"])
    assert "keeps no source submodule" not in row["reason"], (
        "the kept sentence is not said of a submodule it does not describe",
        row["reason"])
    assert "root by rule" not in row["reason"], row["reason"]
    assert row["next"] is None, row

    text = doctor(standard, project)
    assert text.returncode == 0, text.stdout + text.stderr
    assert verdict_line(text).startswith("COMPLIANT   (exit 0)"), text.stdout
    assert "MISPLACED" not in text.stdout, text.stdout
    assert "confirm against the plan, or move it" in text.stdout, text.stdout


def test_a_submodule_in_the_leg_its_rule_assigns_is_kept_and_names_the_rule(
        standard, project):
    """THE SAME GITLINK IN THE LEG THE RULE ASSIGNS READS AS KEPT.

    `docs/theme` is `spec` by `spec-governance`, and in the SPEC leg there is
    nothing for the doctor to say it cannot verify: the leg agrees with the
    rule, and the root keeps no source submodule either way. It gets the
    `kept` wording, with the rule named, and not the unverifiable one.
    """
    stage_gitlink(project / "spec", "docs/theme")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == "spec/docs/theme", kept
    assert kept["leg"] == "spec"
    assert kept["placement"] == "kept", kept
    assert kept["rule"] == "spec-governance", kept
    assert kept["note"].startswith(KEPT_NOTE), kept
    assert "`spec-governance`" in kept["note"], kept
    assert ("spec/docs/theme (rule spec-governance)" in row["reason"]), (
        row["reason"])
    assert ("the assembly root keeps no source submodule (#166)"
            in row["reason"]), row["reason"]
    assert "cannot verify" not in row["reason"], row["reason"]


def test_a_code_rule_makes_a_submodule_in_the_spec_leg_unverifiable(
        standard, project):
    """THE OTHER WAY ROUND: a `code` rule, the gitlink in the SPEC leg.

    `src/vendored` is `code` by `code-source-and-tests`. In the spec leg it is
    a placement the doctor cannot verify, and it says the rule and `code` --
    the other leg is the rule's, not a fixed one.
    """
    verdict = path_policy(standard).classify_file("src/vendored")
    assert (verdict.leg, verdict.rule) == ("code", "code-source-and-tests")
    stage_gitlink(project / "spec", "src/vendored")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == "spec/src/vendored", kept
    assert kept["placement"] == "unverifiable", kept
    assert kept["rule"] == "code-source-and-tests", kept
    assert kept["note"] == unverifiable_note("code-source-and-tests", "code")
    assert "cannot verify" in row["reason"], row["reason"]


def test_both_classes_are_said_apart_in_one_row(standard, project):
    """A KEPT SUBMODULE AND AN UNVERIFIABLE ONE, each in its own clause.

    `.cursor` is rooted by a rule, so a leg holds it; `docs/theme` is spec's,
    in the code leg, so the doctor cannot verify it. One row names both in
    their own words, each submodule once, and neither moves the verdict.
    """
    stage_gitlink(project / "code", ".cursor")
    stage_gitlink(project / "code", "docs/theme")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    by_path = {kept["path"]: kept for kept in row["detail"]["submodules"]}
    assert sorted(by_path) == ["code/.cursor", "code/docs/theme"], by_path
    assert by_path["code/.cursor"]["placement"] == "kept"
    assert by_path["code/docs/theme"]["placement"] == "unverifiable"
    assert row["detail"]["counts"]["submodules"] == 2
    reason = row["reason"]
    assert reason.count("submodule(s)") == 2, reason
    kept_clause, apart, unverified_clause = reason.partition(
        "; 1 submodule(s) at a path a rule assigns")
    assert apart, ("the unverifiable clause follows the kept one", reason)
    assert "code/.cursor (rule root-assistant-instructions)" in kept_clause, (
        reason)
    assert "code/docs/theme" not in kept_clause, reason
    assert "cannot verify" in unverified_clause, reason
    assert "code/docs/theme (rule spec-governance)" in unverified_clause, (
        reason)
    assert "code/.cursor" not in unverified_clause, reason


def test_an_unverifiable_submodule_beside_a_misplaced_file_adds_its_clause(
        standard, project):
    """BESIDE A FINDING, THE CLAUSE IS ADDED AND THE VERDICT IS THE FILE'S.

    The misplaced file alone sets MISPLACED and its `next`. The submodule the
    doctor cannot verify adds its clause to that sentence and moves neither.
    """
    stage_gitlink(project / "code", "docs/theme")
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "MISPLACED (1 path)"
    row = rows_of(result)["placement"]
    assert row["status"] == "FINDING", row
    assert [entry["path"] for entry in row["detail"]["misplaced"]] == [
        "spec/tool.py"]
    assert "cannot verify" in row["reason"], row["reason"]
    assert "code/docs/theme (rule spec-governance)" in row["reason"], (
        row["reason"])
    assert "--placement-plan" in row["next"], row


#: The placement row's `--json` keys before #176, which a project with no
#: submodule in a leg must still get exactly.
PLACEMENT_DETAIL_KEYS = {"policy", "everywhere", "legs", "misplaced",
                         "review_required", "counts"}
PLACEMENT_COUNT_KEYS = {"misplaced", "review_required", "unread_legs",
                        "unwritable_names"}
PLACEMENT_LEG_KEYS = {"role", "path", "unwritable", "state", "tracked",
                      "classified", "paths", "misplaced", "review_required"}


def test_a_project_with_no_submodule_gets_the_row_it_always_got(standard,
                                                                project,
                                                                tmp_path):
    """NOTHING CHANGES WHERE NO LEG KEEPS A SUBMODULE, byte for byte.

    `submodules` is the one key the row gained, and only where there is one
    to name -- so the detail, its counts and every leg's entry carry exactly
    the keys they carried, the reason is the sentence it was, and the plan
    has no block it did not have. Asserted on the two rows a project without
    a submodule gets most: `ok` for the scaffold as it is, and a FINDING with
    a question beside it.
    """
    def audited(row) -> str:
        return "; ".join(
            f"{leg['path']}: {leg['paths']} path(s) over "
            f"{leg['classified']} of {leg['tracked']} tracked file(s)"
            for leg in row["detail"]["legs"])

    row = rows_of(doctor(standard, project, "--json"))["placement"]
    assert row["status"] == "ok", row
    assert set(row["detail"]) == PLACEMENT_DETAIL_KEYS, row["detail"]
    assert set(row["detail"]["counts"]) == PLACEMENT_COUNT_KEYS
    for leg in row["detail"]["legs"]:
        assert set(leg) == PLACEMENT_LEG_KEYS, leg
    assert row["reason"] == (
        "every tracked path classifies as the leg it is in: " + audited(row))

    stage(project / "spec", "tool.py", "VALUE = 1\n")
    stage(project / "spec", "examples/golden-run/expected.yaml",
          "result: ok\n")
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--json", "--placement-plan", str(out))
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["placement"]
    assert set(row["detail"]) == PLACEMENT_DETAIL_KEYS, row["detail"]
    assert set(row["detail"]["counts"]) == PLACEMENT_COUNT_KEYS
    for leg in row["detail"]["legs"]:
        assert set(leg) == PLACEMENT_LEG_KEYS, leg
    assert row["reason"] == (
        "1 path(s) sit in a leg the policy puts elsewhere: spec/tool.py: "
        "code by rule extension-majority (1 code in the spec leg); 1 more "
        f"path(s) need a human's reading  [{audited(row)}]"), row["reason"]
    assert "submodule" not in json.dumps(row), row
    plan = out.read_text(encoding="utf-8")
    assert "submodule" not in plan, plan
    assert "submodules" not in adoption_module(standard).load_yaml(out)


def test_the_placement_plan_lists_a_kept_submodule_and_asks_nothing(
        standard, project, tmp_path):
    """A NOTE, NOT THE `ambiguous-gitmodules` QUESTION, in the plan too.

    Which leg owns a submodule is asked when a repository is ADOPTED, and the
    leg it is in is the answer somebody gave. A plan for a project already
    split that asked it again would put an answered question back on every
    run -- and on this standard's policy the question a gitlink's name gets
    is `default`'s, which offers `root`, the one answer a submodule cannot
    take. So it is no entry under `paths:`; it
    is listed in `submodules:` with its leg and why it was not judged, and
    the adoption's own reader, handed the plan's entries, sees only the path
    a human is to resolve.
    """
    stage_gitlink(project / "code", ".cursor")
    stage(project / "spec", "tool.py", "VALUE = 1\n")
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--placement-plan", str(out))
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict_line(result).startswith("MISPLACED (1 path)"), \
        result.stdout

    adopt = adoption_module(standard)
    data = adopt.load_yaml(out)
    assert data["kind"] == adopt.PLACEMENT_PLAN_KIND
    assert [entry["path"] for entry in data["paths"]] == ["spec/tool.py"], (
        "a submodule a leg keeps is not a path to resolve")
    [kept] = data["submodules"]
    assert set(kept) == {"path", "in_leg", "placement", "rule", "note"}, (
        "no `leg:`, no `question:` and no `resolution:`: nothing is asked",
        kept)
    assert kept["path"] == "code/.cursor"
    assert kept["in_leg"] == "code"
    assert kept["placement"] == "kept", kept
    assert kept["rule"] == "root-assistant-instructions", kept
    assert kept["note"].startswith(KEPT_NOTE), kept
    as_plan = dict(data)
    as_plan["kind"], as_plan["mode"] = adopt.PLAN_KIND, "in-place"
    plan = adopt.Plan(out, as_plan)
    assert [entry["path"] for entry in plan.entries] == ["spec/tool.py"]
    assert adopt._leg_findings(plan, None) == []


def test_the_placement_plan_carries_the_class_of_each_submodule(
        standard, project, tmp_path):
    """THE PLAN SAYS `kept` OR `unverifiable`, AND THE RULE, AS `--json` DOES.

    Three submodules in the code leg, one of each way the doctor can tell
    them: a root rule's, the other leg's rule's, and no rule's. The plan
    names the class and the rule on each, `null` where no rule matched, and
    still asks nothing: the adoption's own reader sees no entry to resolve.
    """
    for name in (".cursor", "docs/theme", "vendor/lib"):
        stage_gitlink(project / "code", name)
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--placement-plan", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict_line(result).startswith("COMPLIANT   (exit 0)"), \
        result.stdout

    adopt = adoption_module(standard)
    data = adopt.load_yaml(out)
    assert data["paths"] == [], data
    by_path = {kept["path"]: kept for kept in data["submodules"]}
    assert sorted(by_path) == ["code/.cursor", "code/docs/theme",
                               "code/vendor/lib"], by_path
    for kept in by_path.values():
        assert set(kept) == {"path", "in_leg", "placement", "rule", "note"}
        assert kept["in_leg"] == "code"
    assert by_path["code/.cursor"]["placement"] == "kept"
    assert by_path["code/.cursor"]["rule"] == "root-assistant-instructions"
    theme = by_path["code/docs/theme"]
    assert theme["placement"] == "unverifiable", theme
    assert theme["rule"] == "spec-governance", theme
    assert theme["note"] == unverifiable_note("spec-governance", "spec"), (
        theme)
    assert by_path["code/vendor/lib"]["placement"] == "kept"
    assert by_path["code/vendor/lib"]["rule"] is None
    assert by_path["code/vendor/lib"]["note"] == KEPT_NOTE
    assert "confirm it" in out.read_text(encoding="utf-8"), (
        "the plan's own comment says what `unverifiable` asks of a reader")


# --- placement: what the gitlink rule must not swallow (Codex, PR #186) ------
#
# Two ways the rule above could drop something it should not have. A path the
# index holds in SEVERAL stages is a gitlink only if every stage is one; and a
# submodule at a path the doctor never judges for a file is still a submodule
# a leg keeps, which the row promises to name.


def stage_unmerged(leg: Path, name: str, kinds: dict) -> None:
    """Leave `name` UNMERGED in a leg's index, one stage per entry of `kinds`.

    `kinds` maps a stage number to `"file"` or `"gitlink"`, so a test says
    what each side of the conflict is: `{2: "file", 3: "gitlink"}` is the path
    one side added as a file and the other as a submodule. `git update-index
    --index-info` reads the `<mode> <object> <stage><TAB><path>` lines
    `ls-files --stage` prints, which is the one way to write a stage that is
    not 0, and it writes the index and nothing else -- the leg's HEAD stays at
    its pin, as `stage` and `stage_gitlink` leave it. A gitlink's second
    commit is a child of HEAD made with `commit-tree`, which moves no ref.

    Both pipes into git carry BYTES, not text. A text-mode pipe writes each
    LF as `os.linesep`, which is CR LF on Windows, so git read the path as
    `.cursor` plus a CR, accepted it (a CR is a legal byte in a path), staged
    the entries there and exited 0: `check=True` passed, `ls-files --stage
    .cursor` listed nothing, and the three tests that read it failed on the
    Windows job alone. NUL-terminated records (`update-index -z`) were not
    chosen: encoding them is what takes the translation out, on every system,
    and it leaves them in the very lines `ls-files --stage` prints.
    """
    commit = git("rev-parse", "HEAD", cwd=leg).stdout.strip()
    child = git("commit-tree", f"{commit}^{{tree}}", "-p", commit, "-m",
                "the other side", cwd=leg).stdout.strip()
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(leg), input=b"x\n", capture_output=True,
                          check=True).stdout.decode("utf-8").strip()
    lines = ""
    for number, kind in kinds.items():
        if kind == "file":
            mode, obj = "100644", blob
        else:
            mode, obj = "160000", commit if number == 2 else child
        lines += f"{mode} {obj} {number}\t{name}\n"
    subprocess.run(["git", "update-index", "--index-info"], cwd=str(leg),
                   input=lines.encode("utf-8"), capture_output=True,
                   check=True)


@pytest.mark.parametrize("kinds", [
    {2: "file", 3: "gitlink"},
    {2: "gitlink", 3: "file"},
], ids=["file-then-gitlink", "gitlink-then-file"])
def test_an_unmerged_path_with_a_file_stage_is_still_judged_as_a_file(
        standard, project, kinds):
    """A PATH IS A SUBMODULE ONLY IF EVERY STAGE IT HOLDS IS A GITLINK.

    `git ls-files --stage` lists an unmerged `.cursor` once per stage, here
    one side's file and the other's submodule. Keeping only the NAME of the
    paths with a gitlink stage dropped both records from the classification,
    so the file never reached the policy and the row said "a submodule" and
    COMPLIANT where the 2026-09-02 ruling says the assistant instructions are
    the root's. There is a file in the leg, and it is judged as one, in
    either order of the two sides.
    """
    verdict = path_policy(standard).classify_file(".cursor")
    assert (verdict.leg, verdict.rule) == (
        "root", "root-assistant-instructions"), (
        "the policy must still root this NAME, or this test proves nothing")
    stage_unmerged(project / "code", ".cursor", kinds)
    listed = git("ls-files", "--stage", ".cursor",
                 cwd=project / "code").stdout.splitlines()
    assert sorted(line.split()[0] for line in listed) == sorted(
        "100644" if kind == "file" else "160000" for kind in kinds.values()
    ), ("fixture: the index must hold both a file and a gitlink stage", listed)
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"].startswith("MISPLACED"), (
        result.stdout)
    row = rows_of(result)["placement"]
    assert row["status"] == "FINDING", row
    # `ls-files` lists an unmerged path once per stage, on main as here, so
    # how many entries the one path gets is not what is under test: that
    # every one of them is the file, judged by the rule that roots its name.
    assert row["detail"]["misplaced"], row
    for entry in row["detail"]["misplaced"]:
        assert entry["path"] == "code/.cursor", entry
        assert entry["rule"] == "root-assistant-instructions", entry
    assert "submodules" not in row["detail"], (
        "a path with a file in it is not a submodule a leg keeps",
        row["detail"])
    assert "root by rule root-assistant-instructions" in row["reason"], (
        row["reason"])
    assert "--placement-plan" in row["next"], row


def test_an_unmerged_path_whose_every_stage_is_a_gitlink_is_one_submodule(
        standard, project):
    """THE OTHER SIDE OF THAT RULE: two gitlink stages are still a submodule.

    Two sides that each moved a submodule to a different commit leave one
    path in two stages, and neither is a file. It is exempt from the policy
    exactly as a merged gitlink is, and named ONCE and not once per stage.
    """
    stage_unmerged(project / "code", ".cursor", {2: "gitlink", 3: "gitlink"})
    listed = git("ls-files", "--stage", ".cursor",
                 cwd=project / "code").stdout.splitlines()
    assert [line.split()[0] for line in listed] == ["160000", "160000"], (
        "fixture: two gitlink stages", listed)
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert [kept["path"] for kept in row["detail"]["submodules"]] == \
        ["code/.cursor"]
    assert row["detail"]["counts"]["submodules"] == 1


@pytest.mark.parametrize("name,pattern", [
    (".github/actions", ".github/**"),
    ("COPYING", "COPYING"),
], ids=["under-dot-github", "a-named-file"])
def test_a_submodule_at_a_path_the_doctor_never_judges_is_still_named(
        standard, project, tmp_path, name, pattern):
    """EVERY GITLINK A LEG KEEPS IS REPORTED, WHATEVER ELSE MATCHES ITS NAME.

    `.github/**` and `COPYING` are `everywhere`: a file there is carried by
    every repository and the row never calls it misplaced. The exclusion is
    for FILES, and applying it to the paths before the gitlinks were read
    dropped a submodule at one of them without a word -- the row stayed `ok`,
    and neither `--json` nor the plan named it. It is named in all three, and
    on its own it is the `note` any kept submodule is.
    """
    first = rows_of(doctor(standard, project, "--json"))["placement"]
    assert pattern in first["detail"]["everywhere"], (
        "fixture: this name must match a path the doctor never judges",
        first["detail"]["everywhere"])
    stage_gitlink(project / "code", name)
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--json", "--placement-plan", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == []
    [kept] = row["detail"]["submodules"]
    assert kept["path"] == f"code/{name}", kept
    assert kept["path_in_leg"] == name
    assert row["detail"]["counts"]["submodules"] == 1
    assert f"code/{name}" in row["reason"], row["reason"]

    text = doctor(standard, project)
    assert text.returncode == 0, text.stdout + text.stderr
    assert f"code/{name}" in text.stdout, text.stdout
    assert "submodule(s) the path policy does not judge" in text.stdout

    data = adoption_module(standard).load_yaml(out)
    assert [entry["path"] for entry in data["submodules"]] == [
        f"code/{name}"], data
    assert data["submodules"][0]["in_leg"] == "code"


# --- placement: a submodule held to the leg the adoption recorded (#189) ----
#
# Which leg holds a source submodule is a human's answer in the adoption plan
# (#166), and the plan is committed nowhere. So until `execute` wrote it into
# `project.yaml`, the row could only NOTE a submodule -- kept, or a placement
# it cannot verify -- and a submodule added by hand looked the same as one a
# person placed. With the record, one in the leg recorded is placed and one in
# the other leg is MISPLACED; one no record names is still #186's note.

#: The source commit a hand-written record names. Any 40 hex: the doctor reads
#: the leg, not the commit.
RECORDED_AT = "0123456789abcdef0123456789abcdef01234567"


def record_submodules(project: Path, *rows: tuple) -> None:
    """Append `project.yaml`'s `submodules:` block, as `adopt-project.py
    execute` writes it, one `(path, leg)` or `(path, leg, resolution)` row
    each.

    SPELT OUT HERE, not written by the adoption's own function: what is
    under test is that the doctor reads the record a manifest carries, and
    `test_an_adopted_submodule_is_recorded_and_placed` below proves the
    writer's own output is that record. Written as BYTES, so the file keeps
    the LF line endings it was written with on every platform.
    """
    lines = ["", "submodules:"]
    for path, leg, *why in rows:
        lines += [f'  - path: "{path}"', f"    leg: {leg}"]
        if why:
            lines.append(f'    resolution: "{why[0]}"')
        lines.append(f'    source_commit: "{RECORDED_AT}"')
    manifest = project / "project.yaml"
    manifest.write_bytes((manifest.read_text(encoding="utf-8")
                          + "\n".join(lines) + "\n").encode("utf-8"))


def recorded_note(leg: str) -> str:
    """What a `recorded` submodule's note says, spelt out (see KEPT_NOTE)."""
    return (f"a submodule project.yaml's `submodules:` records in the {leg} "
            "leg, where it is (#189)")


def audited_legs(row: dict) -> str:
    """The `[...]` the row's reason ends with, from the legs it printed."""
    return "; ".join(
        f"{leg['path']}: {leg['paths']} path(s) over "
        f"{leg['classified']} of {leg['tracked']} tracked file(s)"
        for leg in row["detail"]["legs"])


def test_a_submodule_in_the_leg_its_record_names_is_placed(standard,
                                                           project):
    """THE ANSWER IS CHECKED, AND THE ROW IS `ok`.

    `.cursor` is rooted by a rule for a FILE, and a leg keeps the submodule
    there because the root keeps none (#166). Recorded in the code leg, and
    in the code leg, it is placed: the row is `ok` and not the note #186 had
    to give it, it says the record placed it, and the project's own
    validator accepts the record.
    """
    stage_gitlink(project / "code", ".cursor")
    record_submodules(project, (".cursor", "code", "editor rules"))
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    rows = rows_of(result)
    assert rows["manifest"]["status"] == "ok", rows["manifest"]
    row = rows["placement"]
    assert row["status"] == "ok", row
    assert row["detail"]["misplaced"] == []
    assert row["detail"]["review_required"] == []
    assert row["detail"]["submodules"] == [{
        "path": "code/.cursor", "leg": "code", "path_in_leg": ".cursor",
        "placement": "recorded", "rule": "root-assistant-instructions",
        "recorded_leg": "code", "resolution": "editor rules",
        "note": recorded_note("code")}]
    assert row["reason"] == (
        "every tracked file classifies as the leg it is in; 1 submodule(s) "
        "in the leg project.yaml's `submodules:` records for them (#189): "
        f"code/.cursor  [{audited_legs(row)}]"), row["reason"]
    assert row["next"] is None, row

    text = doctor(standard, project)
    assert text.returncode == 0, text.stdout + text.stderr
    assert verdict_line(text).startswith("COMPLIANT   (exit 0)"), text.stdout


def test_a_submodule_in_the_other_leg_from_its_record_is_misplaced(
        standard, project, tmp_path):
    """THE RECORD SAYS SPEC AND THE CODE LEG HOLDS IT: MISPLACED (1 path).

    The manifest asserts where it belongs, so it is a path in the wrong leg
    like any other: in `misplaced`, counted in the verdict and the leg, named
    with the leg recorded, and an entry under `paths:` in the plan that the
    adoption's own reader accepts. Nothing else is in the wrong leg here, so
    the reason is that one clause and no separator hangs after it.
    """
    stage_gitlink(project / "code", ".cursor")
    record_submodules(project, (".cursor", "spec", "rules the spec reads"))
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--json", "--placement-plan", str(out))
    assert result.returncode == 1, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "MISPLACED (1 path)"
    row = rows_of(result)["placement"]
    assert row["status"] == "FINDING", row
    reason = ("project.yaml's `submodules:` records this submodule in the "
              "spec leg (#189): rules the spec reads")
    assert row["detail"]["misplaced"] == [{
        "path": "code/.cursor", "leg": "code", "path_in_leg": ".cursor",
        "classified_as": "spec", "rule": None, "reason": reason,
        "confidence": "recorded", "question": None, "files": 1, "bytes": 0,
        "review_required": False, "direction": "spec in the code leg",
        "submodule": True}]
    [held] = row["detail"]["submodules"]
    assert held["placement"] == "misplaced", held
    assert held["recorded_leg"] == "spec", held
    assert held["note"] == (
        "a submodule project.yaml's `submodules:` records in the spec leg, "
        "and it is in the code leg (#189)"), held
    code = [leg for leg in row["detail"]["legs"] if leg["role"] == "code"][0]
    assert code["misplaced"] == 1, code
    assert row["reason"] == (
        "1 submodule(s) sit in a leg other than the one project.yaml's "
        "`submodules:` records for them (#189): code/.cursor (recorded in "
        f"the spec leg)  [{audited_legs(row)}]"), row["reason"]
    assert "--placement-plan" in row["next"], row

    adopt = adoption_module(standard)
    data = adopt.load_yaml(out)
    [entry] = data["paths"]
    assert entry == {"path": "code/.cursor", "in_leg": "code", "leg": "spec",
                     "confidence": "recorded", "rule": None,
                     "reason": reason, "files": 1, "bytes": 0,
                     "review_required": False, "resolution": ""}, entry
    [listed] = data["submodules"]
    assert listed == {"path": "code/.cursor", "in_leg": "code",
                      "placement": "misplaced", "recorded_leg": "spec",
                      "rule": "root-assistant-instructions",
                      "note": held["note"]}, listed
    assert "`placement: misplaced`" in out.read_text(encoding="utf-8")
    as_plan = dict(data)
    as_plan["kind"], as_plan["mode"] = adopt.PLAN_KIND, "in-place"
    assert adopt._leg_findings(adopt.Plan(out, as_plan), None) == []

    text = doctor(standard, project)
    assert text.returncode == 1, text.stdout + text.stderr
    assert verdict_line(text).startswith("MISPLACED (1 path)"), text.stdout


def test_a_submodule_no_record_names_is_still_the_note(standard, project,
                                                        tmp_path):
    """A SUBMODULE ADDED BY HAND, beside one the adoption recorded.

    `docs/theme` is in no row, so the doctor still cannot tell an answer
    from none, and it is #186's `unverifiable` note, word for word, while
    `.cursor` beside it is placed. A row with a note in it is not `ok`, and
    nothing is MISPLACED. The plan lists both, the recorded one with the leg
    recorded and the other without one.
    """
    stage_gitlink(project / "code", ".cursor")
    stage_gitlink(project / "code", "docs/theme")
    record_submodules(project, (".cursor", "code"))
    out = tmp_path / "placement-plan.yaml"
    result = doctor(standard, project, "--json", "--placement-plan", str(out))
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(result.stdout)["verdict"] == "COMPLIANT"
    row = rows_of(result)["placement"]
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    by_path = {held["path"]: held for held in row["detail"]["submodules"]}
    assert by_path["code/.cursor"]["placement"] == "recorded"
    assert by_path["code/.cursor"]["resolution"] is None, (
        "a row with no `resolution:` gives none")
    theme = by_path["code/docs/theme"]
    assert theme == {"path": "code/docs/theme", "leg": "code",
                     "path_in_leg": "docs/theme", "placement": "unverifiable",
                     "rule": "spec-governance",
                     "note": unverifiable_note("spec-governance", "spec")}
    recorded, apart, unverified = row["reason"].partition(
        "; 1 submodule(s) at a path a rule assigns")
    assert apart, row["reason"]
    assert recorded == (
        "nothing is in the wrong leg; 1 submodule(s) in the leg "
        "project.yaml's `submodules:` records for them (#189): code/.cursor")
    assert "code/docs/theme (rule spec-governance)" in unverified
    data = adoption_module(standard).load_yaml(out)
    listed = {held["path"]: held for held in data["submodules"]}
    assert listed["code/.cursor"]["recorded_leg"] == "code"
    assert "recorded_leg" not in listed["code/docs/theme"]


def test_a_record_row_the_validator_refuses_decides_nothing(standard,
                                                            project):
    """`leg: root` IS NO ANSWER FOR A SUBMODULE, and it places nothing.

    The project's own validator names the row, which makes the verdict
    INVALID, and the placement row treats `.cursor` as one no record names:
    a row nobody can hold a submodule to must not make it look checked.
    """
    stage_gitlink(project / "code", ".cursor")
    record_submodules(project, (".cursor", "root"))
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["manifest"]["status"] == "FINDING", rows["manifest"]
    assert "manifest-submodule-leg" in json.dumps(rows["manifest"])
    [held] = rows["placement"]["detail"]["submodules"]
    assert held["placement"] == "kept", held
    assert "recorded_leg" not in held, held


@pytest.mark.parametrize("legs, placement, recorded_leg", [
    (("code", "spec"), "recorded", "code"),
    (("spec", "code"), "misplaced", "spec"),
    (("root", "code"), "kept", None),
], ids=["code-then-spec", "spec-then-code", "refused-leg-then-code"])
def test_where_two_rows_name_one_path_the_first_decides(standard, project,
                                                        legs, placement,
                                                        recorded_leg):
    """TWO ROWS FOR ONE PATH: THE FIRST DECIDES, AND THE VERDICT IS RED.

    The project's own validator accepts the first row and names the second
    as `recorded twice`, so the doctor holds `.cursor` to the first, as it
    ignores every row the validator refuses -- and where it refuses the
    first row's `leg: root`, nothing decides, and the second row does not
    stand in for it. `execute` writes one row per gitlink, so only an edit
    makes two; whichever row decides, the `manifest` row is a FINDING and
    the doctor exits 1.
    """
    stage_gitlink(project / "code", ".cursor")
    record_submodules(project, *((".cursor", leg) for leg in legs))
    named = run_script(project / "scripts" / "validate-manifest.py",
                       cwd=project)
    assert "submodules[1]: path '.cursor' is recorded twice" in (
        named.stderr), named.stderr
    result = doctor(standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    rows = rows_of(result)
    assert rows["manifest"]["status"] == "FINDING", rows["manifest"]
    [held] = rows["placement"]["detail"]["submodules"]
    assert held["placement"] == placement, held
    assert held.get("recorded_leg") == recorded_leg, held


#: A leg's `.gitmodules` registering `.cursor`, as an adoption leaves one.
CURSOR_GITMODULES = ('[submodule ".cursor"]\n\tpath = .cursor\n'
                     "\turl = https://example.invalid/rules.git\n")

#: What the row says of a `.gitmodules` whose question the record answered.
ANSWERED_CLAUSE = ("project.yaml's `submodules:` answers the question the "
                   "policy asks of code/.gitmodules: which leg owns the "
                   "submodules it registers")


@pytest.mark.parametrize("recorded, status, asked", [
    ("code", "ok", []),
    ("spec", "FINDING", ["code/.gitmodules"]),
    (None, "note", ["code/.gitmodules"]),
], ids=["recorded-in-this-leg", "recorded-in-the-other-leg", "no-record"])
def test_the_record_answers_the_question_about_the_gitmodules_beside_it(
        standard, project, recorded, status, asked):
    """THE POLICY ASKS WHICH LEG OWNS THE SUBMODULES A `.gitmodules`
    REGISTERS, AND THE RECORD SAYS (#189).

    An adoption's leg always holds the `.gitmodules` that registers its
    submodules, and rule `ambiguous-gitmodules` asks that of every one. In a
    leg that keeps a submodule the record places there, the record is the
    answer, and it is this leg: the file is placed, the row is `ok`, and the
    reason says where the answer came from. Where the record puts the
    submodule in the other leg, or there is no record, it says nothing about
    this file, which stays the question it was.
    """
    stage(project / "code", ".gitmodules", CURSOR_GITMODULES)
    stage_gitlink(project / "code", ".cursor")
    if recorded:
        record_submodules(project, (".cursor", recorded))
    result = doctor(standard, project, "--json")
    assert result.returncode == (1 if status == "FINDING" else 0), (
        result.stdout + result.stderr)
    row = rows_of(result)["placement"]
    assert row["status"] == status, row
    assert [item["path"] for item in row["detail"]["review_required"]] == (
        asked), row["detail"]["review_required"]
    code = [leg for leg in row["detail"]["legs"] if leg["role"] == "code"][0]
    if asked:
        assert "answered" not in code, code
        assert ANSWERED_CLAUSE not in row["reason"], row["reason"]
        return
    assert code["answered"] == ["code/.gitmodules"], code
    assert row["reason"] == (
        "every tracked file classifies as the leg it is in; 1 submodule(s) "
        "in the leg project.yaml's `submodules:` records for them (#189): "
        f"code/.cursor; {ANSWERED_CLAUSE}  [{audited_legs(row)}]"), (
        row["reason"])


@pytest.mark.parametrize("other, rows, status, unread", [
    ("vendor/lib", (), "note", []),
    ("docs/theme", (("docs/theme", "spec"),), "FINDING", []),
    pytest.param("bad\x01name", (), "note", ["'bad\\x01name'"],
                 marks=pytest.mark.skipif(
                     os.name == "nt", reason="Git for Windows records no "
                     "path that holds a control character")),
], ids=["one-no-row-names", "one-recorded-in-the-other-leg",
        "one-whose-name-cannot-be-read"])
def test_the_question_stays_where_the_record_does_not_place_every_submodule(
        standard, project, other, rows, status, unread):
    """THE RECORD ANSWERS FOR A `.gitmodules` ONLY WHERE IT PLACES EVERY
    SUBMODULE THE LEG KEEPS (#189).

    Beside the recorded `.cursor` the code leg keeps a second submodule,
    registered in the same `.gitmodules` as `git submodule add` registers
    one: added by hand, which no row names, or one the record puts in the
    spec leg. The record does not say this leg owns everything the file
    registers, so the file stays the policy's question, and the row never
    says the record answered it; the note or the finding about the second
    submodule is what it was.

    Or one whose name the doctor cannot read (#189's second review, F1). A
    control character, like a byte that is not UTF-8, sets the name aside
    before its mode is read, so no row was held to it: the leg reports the
    name by `repr`, and the question stays.
    """
    stage(project / "code", ".gitmodules", CURSOR_GITMODULES + (
        f'[submodule "{other}"]\n\tpath = {other}\n'
        "\turl = https://example.invalid/other.git\n"))
    stage_gitlink(project / "code", ".cursor")
    stage_gitlink(project / "code", other)
    record_submodules(project, (".cursor", "code"), *rows)
    result = doctor(standard, project, "--json")
    assert result.returncode == (1 if status == "FINDING" else 0), (
        result.stdout + result.stderr)
    row = rows_of(result)["placement"]
    assert row["status"] == status, row
    assert [item["path"] for item in row["detail"]["review_required"]] == [
        "code/.gitmodules"], row["detail"]["review_required"]
    code = [leg for leg in row["detail"]["legs"] if leg["role"] == "code"][0]
    assert "answered" not in code, code
    assert code["unwritable"] == unread, code
    assert ANSWERED_CLAUSE not in row["reason"], row["reason"]


#: Names the record cannot write raw -- `str.isprintable` refuses a character
#: in each -- and the doctor still reads: none holds a control character or a
#: byte that is not UTF-8, the names it reports as ones no report can carry.
ESCAPED_NAMES = ("vendor/nb\u00a0sp", "vendor/ideo\u3000graphic",
                 "vendor/zero\u200bwidth", "vendor/soft\u00adhyphen",
                 "vendor/nel\u0085x", "vendor/line\u2028sep")


def held_placements(result) -> dict:
    """`{path: placement}` of every submodule the `placement` row holds."""
    return {held["path"]: held["placement"] for held in
            rows_of(result)["placement"]["detail"].get("submodules") or []}


def append_written_record(standard: Path, project: Path, names,
                          leg: str = "code") -> str:
    """The record the adoption's OWN writer makes for `names` in `leg`,
    appended to `project.yaml` as bytes, and returned."""
    adopt = adoption_module(standard)
    block = adopt.submodule_record(
        [{"path": name, "leg": leg} for name in names],
        sorted((name, adopt.GITLINK_MODE, RECORDED_AT, 0) for name in names),
        RECORDED_AT)
    manifest = project / "project.yaml"
    manifest.write_bytes((manifest.read_text(encoding="utf-8")
                          + block).encode("utf-8"))
    return block


def test_a_name_the_record_spells_with_an_escape_still_names_its_submodule(
        standard, project):
    """THE ROW READS BACK AS THE NAME, so the submodule is held to it (#189).

    The adoption's own writer spells each of these names' unprintable
    character by its code point -- `\\xa0`, `\\u3000`, `\\u2028` -- and the
    reader resolves that escape. So in the leg recorded each submodule is
    placed, and staged in the other leg instead each one is MISPLACED. When
    the reader kept the backslash, no row named any of them: they were
    `kept`, and the move was COMPLIANT.
    """
    block = append_written_record(standard, project, ESCAPED_NAMES)
    spelled = [line for line in block.splitlines() if "- path:" in line]
    assert len(spelled) == len(ESCAPED_NAMES), block
    assert all("\\" in line for line in spelled), (
        "each name must be one the record spells with an escape", block)
    for name in ESCAPED_NAMES:
        stage_gitlink(project / "code", name)
    placed = doctor(standard, project, "--json")
    assert placed.returncode == 0, placed.stdout + placed.stderr
    assert rows_of(placed)["manifest"]["status"] == "ok"
    assert held_placements(placed) == {
        f"code/{name}": "recorded" for name in ESCAPED_NAMES}

    for name in ESCAPED_NAMES:
        git("rm", "-q", "--cached", "--", name, cwd=project / "code")
        stage_gitlink(project / "spec", name)
    moved = doctor(standard, project, "--json")
    assert moved.returncode == 1, moved.stdout + moved.stderr
    assert json.loads(moved.stdout)["verdict"] == (
        f"MISPLACED ({len(ESCAPED_NAMES)} paths)")
    assert held_placements(moved) == {
        f"spec/{name}": "misplaced" for name in ESCAPED_NAMES}


@pytest.mark.skipif(os.name == "nt",
                    reason="Git for Windows records no path with a backslash")
def test_a_recorded_name_with_a_backslash_is_valid_and_placed(standard,
                                                              project):
    """A BACKSLASH IS A CHARACTER OF THE NAME, and the record may hold it.

    On POSIX Git records `vendor/a\\b`, an adoption of a source with a
    submodule there records it, and the doctor holds the gitlink to that
    row. So the project's own validator accepts the row: the spelling rule
    it holds a recorded path to is the one Git records paths by (#189), and
    the leg-path rule's refusal of a backslash, which a person TYPING a path
    for Windows gets wrong, is not part of it.
    """
    name = "vendor/a\\b"
    append_written_record(standard, project, [name])
    stage_gitlink(project / "code", name)
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    assert rows_of(result)["manifest"]["status"] == "ok", (
        rows_of(result)["manifest"])
    assert held_placements(result) == {f"code/{name}": "recorded"}


# --- the record, written by a real adoption and read by the doctor (#189) ---

#: `execute` REQUIRES `git filter-repo`; see tests/test_adopt_e2e.py.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: Why the adoption below answered `.cursor` and its `.gitmodules` `code`.
CURSOR_ANSWER = "editor rules the code leg's tooling reads"


@pytest.fixture(scope="module")
def adopted_cursor(standard, tmp_path_factory) -> dict:
    """A source whose `.cursor` is a SUBMODULE, adopted by the standard
    under test with `.cursor` and `.gitmodules` answered `code`, and cloned
    recursively from the split branch."""
    base = tmp_path_factory.mktemp("adopted-cursor")
    dependency = base / "rules"
    dependency.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=dependency)
    (dependency / "rules.md").write_text("editor rules\n", encoding="utf-8")
    commit_all(dependency, "rules")
    source = base / "Thing"
    source.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=source)
    for name, body in (("README.md", "# Thing\n"),
                       ("src/app/util.py", "VALUE = 1\n"),
                       ("docs/index.md", "# Docs\n")):
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(body, encoding="utf-8")
    commit_all(source, "init")
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency), ".cursor",
        cwd=source)
    commit_all(source, "vendor the editor rules")
    adopt = standard / "adopt-project.py"
    plan = base / "adoption-plan.yaml"
    written = run_script(adopt, "plan", "--source", str(source), "--project",
                         "Northwind", "--org", ORG, "--elected-by", "T",
                         "--elected-on", "2026-09-02", "--out", str(plan))
    assert written.returncode == 0, written.stdout + written.stderr
    text = plan.read_text(encoding="utf-8")
    for path in (".cursor", ".gitmodules"):
        needle = f"  - path: {path}\n    leg: null\n"
        assert needle in text, (path, text)
        text = text.replace(needle, f"  - path: {path}\n    leg: code\n"
                            f"    resolution: \"{CURSOR_ANSWER}\"\n")
    plan.write_bytes(text.encode("utf-8"))
    done = run_script(adopt, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))
    assert done.returncode == 0, done.stdout + done.stderr
    clone = base / "clone"
    proc = clone_just_pushed(source, clone, branch="adopt/three-repo-shape")
    assert proc.returncode == 0, proc.stderr
    return {"clone": clone,
            "commit": git("rev-parse", "main", cwd=source).stdout.strip()}


@pytest.fixture
def cursor_clone(adopted_cursor, tmp_path) -> Path:
    """A private, mutable copy of that clone."""
    target = tmp_path / "Northwind"
    shutil.copytree(adopted_cursor["clone"], target, symlinks=True)
    return target


@needs_filter_repo
def test_the_adopted_clone_was_read_through_git_not_through_the_remotes(
        adopted_cursor):
    """#440: `execute` pushed the split branch into the source and each leg
    into a bare remote a moment before `adopted_cursor` cloned them, so
    the objects are loose there; read through the transport (as the
    scaffolded session fixtures are) the root and both legs are ONE PACK
    each, and read as plain paths (git's local clone) they stay loose.
    """
    assert_read_through_git(adopted_cursor["clone"])


def cursor_placement(standard, root: Path) -> tuple:
    """The verdict and the `.cursor` submodule's entry, from `--json`."""
    result = doctor(standard, root, "--json")
    row = rows_of(result)["placement"]
    held = {item["path"]: item for item in row["detail"]["submodules"]}
    return result, json.loads(result.stdout)["verdict"], row, held


@needs_filter_repo
def test_an_adopted_submodule_is_recorded_and_placed(standard,
                                                     adopted_cursor,
                                                     cursor_clone):
    """`execute` WRITES THE ANSWER, AND THE DOCTOR PLACES THE SUBMODULE BY IT.

    The split's `project.yaml` carries one row for `.cursor`: its path in
    the leg, the leg answered, the plan's `resolution:` and the source
    commit. The doctor holds the code leg's `.cursor` to it: recorded, and
    COMPLIANT. And the row is `ok`: the code leg's `.gitmodules`, which
    registers `.cursor`, is the policy's question about which leg owns that
    submodule, and the record is its answer.
    """
    manifest = adoption_module(standard).load_yaml(
        cursor_clone / "project.yaml")
    assert manifest["submodules"] == [{
        "path": ".cursor", "leg": "code", "resolution": CURSOR_ANSWER,
        "source_commit": adopted_cursor["commit"]}], manifest["submodules"]
    result, verdict, row, held = cursor_placement(standard, cursor_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == "COMPLIANT"
    assert rows_of(result)["manifest"]["status"] == "ok"
    assert row["status"] == "ok", row
    assert row["detail"]["review_required"] == [], row["detail"]
    assert held["code/.cursor"]["placement"] == "recorded", held
    assert held["code/.cursor"]["resolution"] == CURSOR_ANSWER
    assert ("1 submodule(s) in the leg project.yaml's `submodules:` records "
            "for them (#189): code/.cursor") in row["reason"], row["reason"]
    assert ANSWERED_CLAUSE in row["reason"], row["reason"]
    assert "keeps no source submodule" not in row["reason"], row["reason"]


@needs_filter_repo
def test_an_adopted_submodule_whose_record_is_edited_is_misplaced(
        standard, cursor_clone):
    """THE SAME ASSEMBLY, ITS RECORD EDITED TO SAY SPEC: MISPLACED (1 path)."""
    manifest = cursor_clone / "project.yaml"
    text = manifest.read_text(encoding="utf-8")
    assert text.count("    leg: code\n") == 1, text
    manifest.write_bytes(
        text.replace("    leg: code\n", "    leg: spec\n").encode("utf-8"))
    result, verdict, row, held = cursor_placement(standard, cursor_clone)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict == "MISPLACED (1 path)"
    assert row["status"] == "FINDING", row
    assert held["code/.cursor"]["placement"] == "misplaced", held
    assert [entry["path"] for entry in row["detail"]["misplaced"]] == [
        "code/.cursor"]


@needs_filter_repo
def test_a_submodule_added_by_hand_after_adoption_is_the_note(standard,
                                                              cursor_clone):
    """A SUBMODULE NOBODY ANSWERED, in the same leg as one somebody did.

    `vendor/lib` is in no row of the record, so it is #186's `kept` note;
    `.cursor` is still recorded, and the verdict stays COMPLIANT.
    """
    stage_gitlink(cursor_clone / "code", "vendor/lib")
    result, verdict, row, held = cursor_placement(standard, cursor_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == "COMPLIANT"
    assert row["status"] == "note", row
    assert held["code/.cursor"]["placement"] == "recorded", held
    assert held["code/vendor/lib"]["placement"] == "kept", held
    assert held["code/vendor/lib"]["note"] == KEPT_NOTE
    assert "code/vendor/lib" in row["reason"], row["reason"]


# --- the platform-aware quoter (#101) ---------------------------------------
#
# Copilot asked for shell quoting on PR #100, against the placement row. The
# finding was real and was never that row's: every next command since #96
# interpolates a path with an f-string, so a root, a leg or a project name
# with a space in it produced a command argparse reads as three arguments --
# in front of whoever pasted it. `shlex.quote` is not the answer either: it is
# POSIX quoting by its own documentation, and this file runs on Windows by
# contract (#49). So one quoter that knows both shells, asked for either.

#: A directory name that is wrong in every way a shell cares about: a space,
#: so an unquoted interpolation splits into two arguments, and an apostrophe,
#: so a naive `'...'` wrapper closes early. Short and distinctive on purpose --
#: a fragment of it appearing as a token of its own is unmistakable.
AWKWARD = "do ct'or"


def doctor_module(standard: Path):
    """`shape-doctor.py` from the standard under test, as a module.

    The same load the two tests above do and for the same reason -- the
    filename has a hyphen -- so the quoter under test is the one that file
    ships rather than a second copy of its rules written out here.
    """
    spec = importlib.util.spec_from_file_location("shape_doctor_quoting",
                                                  standard / DOCTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: What a report is mostly made of, and what must survive UNQUOTED: quoting
#: these would put `--root '/srv/work/Atlas'` on every line of every clean
#: run, in a table whose whole job is to be read.
ORDINARY = [
    "/srv/work/Atlas",
    "scripts/bootstrap.py",
    "--root",
    "AGENTS-shape.md",
    "shape/update-3d46ab5b9c1d",
    "3d46ab5b9c1dcafe0123456789abcdef01234567",
    "Atlas",
    "contracts/spec-pin.yaml",
]


@pytest.mark.parametrize("platform", ["posix", "nt"])
@pytest.mark.parametrize("value", ORDINARY)
def test_the_quoter_leaves_an_ordinary_value_alone(platform, value):
    """The half that keeps the report readable, on both platforms."""
    module = doctor_module(REPO)
    assert module.quote_arg(value, platform) == value


def test_the_quoter_asked_for_a_platform_ignores_the_host():
    """`platform=` is what makes both forms testable on one machine.

    Without it, half of this section could only ever run on the operating
    system the runner happened to be and the other half would be asserted
    nowhere -- which is exactly how a Windows-only spelling stays wrong for a
    year. Asked for a platform, the function answers for THAT one; asked for
    none it answers for this host, which is what every caller in
    `shape-doctor.py` passes.
    """
    module = doctor_module(REPO)
    here = "nt" if os.name == "nt" else "posix"
    # An apostrophe is where the two shells disagree, so it is the value that
    # proves the argument is read at all.
    assert module.quote_arg("O'Brien", "posix") == "'O'\\''Brien'"
    assert module.quote_arg("O'Brien", "nt") == "'O''Brien'"
    assert module.quote_arg("O'Brien") == module.quote_arg("O'Brien", here)


#: The three shapes the issue names, plus the empty string -- a value no row
#: produces today and one a `'...'` wrapper is the only honest spelling of.
AWKWARD_VALUES = [
    "/srv/my projects/Atlas",            # a space
    "/srv/O'Brien/Atlas",                # an apostrophe
    "/srv/my projects/O'Brien's Atlas",  # both
    r"C:\Users\Brett Heap\proj",         # a Windows drive path, with a space
    r"C:\Users\Jane O'Neill\proj",       # and with both
    "",                                  # and the value nothing else spells
]


@pytest.mark.parametrize("value", AWKWARD_VALUES)
def test_the_posix_form_round_trips_through_shlex(value):
    """THE PROOF, and it is the shell's own reader that gives it.

    `shlex.split` is the POSIX word-splitting `sh` performs, so a quoted value
    that comes back out of it as ONE token equal to what went in is a value
    the reader's shell will hand to argparse whole. Asserting a string the
    test itself spelled would only prove the test and the function agree about
    the wrong thing.
    """
    module = doctor_module(REPO)
    quoted = module.quote_arg(value, "posix")
    assert shlex.split(quoted) == [value], quoted
    # `'\''` -- close, escape, reopen -- rather than `shlex.quote`'s
    # `'"'"'`. Both are POSIX, both round-trip, and the difference is one a
    # person reading the report can see through; what has to agree is the
    # SHELL, which is the line above and this one.
    assert shlex.split(shlex.quote(value)) == shlex.split(quoted)


#: The PowerShell form, spelled out, because there is no `shlex` for it. A
#: verbatim single-quoted string expands nothing and escapes an apostrophe by
#: DOUBLING it -- where `sh` closes the quote, escapes, and reopens.
POWERSHELL = [
    ("/srv/my projects/Atlas", "'/srv/my projects/Atlas'"),
    ("/srv/O'Brien/Atlas", "'/srv/O''Brien/Atlas'"),
    (r"C:\Users\Brett Heap\proj", r"'C:\Users\Brett Heap\proj'"),
    (r"C:\Users\Jane O'Neill\proj", "'C:\\Users\\Jane O''Neill\\proj'"),
    ("", "''"),
    # A Windows path with nothing awkward in it passes through on Windows --
    # and is QUOTED on POSIX, where a backslash is an escape character and not
    # a separator. The same value, two right answers.
    (r"C:\projects\Atlas", r"C:\projects\Atlas"),
]


@pytest.mark.parametrize("value,expected", POWERSHELL)
def test_the_powershell_form_is_exactly_this(value, expected):
    module = doctor_module(REPO)
    assert module.quote_arg(value, "nt") == expected


def test_the_two_shells_are_not_one_dialect():
    """WHY THERE ARE TWO FORMS AT ALL, proved rather than asserted in prose.

    It would be cheaper to pick one spelling and print it everywhere, and this
    is the test that says what that would cost: `sh` reads PowerShell's
    doubled apostrophe as two adjacent quoted strings and concatenates them,
    so `'O''Brien'` arrives as `OBrien` -- a DIFFERENT path, with no error
    anywhere to tell the reader their command checked the wrong repository.
    That is the failure mode a report cannot have.
    """
    module = doctor_module(REPO)
    windows = module.quote_arg("O'Brien", "nt")
    assert windows == "'O''Brien'"
    assert shlex.split(windows) == ["OBrien"], (
        "if `sh` ever reads the PowerShell form correctly, the second form "
        "has stopped earning its place")
    assert shlex.split(module.quote_arg("O'Brien", "posix")) == ["O'Brien"]


#: Two characters `sh` is indifferent to and PowerShell is not, so the two
#: alphabets are NOT one alphabet (Copilot, PR #102). `,` is PowerShell's list
#: separator and a leading `@` is splatting syntax; both are ordinary bytes in
#: a `sh` word, and quoting them there would be noise for nothing.
#: `(value, on Windows, on POSIX)`.
POWERSHELL_METACHARACTERS = [
    ("@Atlas", "'@Atlas'", "@Atlas"),
    ("a,b", "'a,b'", "a,b"),
    ("release,2026@main", "'release,2026@main'", "release,2026@main"),
    # The issue's own example. It is quoted on BOTH, and for two different
    # reasons: the comma on Windows, and the backslashes on POSIX, where `\`
    # is an escape character rather than a separator.
    (r"C:\work,old\Atlas", r"'C:\work,old\Atlas'", r"'C:\work,old\Atlas'"),
]


@pytest.mark.parametrize("value,windows,posix", POWERSHELL_METACHARACTERS)
def test_powershell_metacharacters_are_quoted_there_and_bare_here(value,
                                                                  windows,
                                                                  posix):
    r"""One alphabet for both shells would have to be wrong somewhere.

    Admitted bare on Windows, `C:\work,old\Atlas` may reach the command as
    something other than one argument and `@Atlas` as an expansion rather than
    as itself -- neither with an error to say so, which is the failure mode a
    report cannot have. Quoted on POSIX, they would be noise on a line whose
    whole job is to be read. So the two constants differ, and this is what
    the difference is for.
    """
    module = doctor_module(REPO)
    assert module.quote_arg(value, "nt") == windows
    assert module.quote_arg(value, "posix") == posix
    assert shlex.split(module.quote_arg(value, "posix")) == [value]


def test_a_windows_path_is_quoted_on_posix_and_bare_on_windows():
    """The one case where the two platforms must NOT agree, said out loud.

    `C:\\projects\\Atlas` is a path on Windows and a word full of escape
    characters to `sh`, where `\\U` is just `U` and the reader silently gets
    `C:projectsAtlas`. One alphabet for both would have to choose which of
    the two to be wrong about.
    """
    module = doctor_module(REPO)
    value = "C:\\projects\\Atlas"
    assert module.quote_arg(value, "nt") == value
    assert module.quote_arg(value, "posix") == "'" + value + "'"
    assert shlex.split(module.quote_arg(value, "posix")) == [value]


def test_the_lane_trailer_is_quoted_for_the_platform_asked_for(monkeypatch):
    """`platform` IS PASSED ON, not merely branched on -- the rule
    `copy_command` and `scaffold_command` already state, kept here so this
    row cannot drift out of it.

    THE TWO SPELLINGS COINCIDE, AND THAT IS A PROPERTY RATHER THAN AN
    ACCIDENT: a trailer always carries the space after the colon, so it is
    never returned bare on either platform, and `shape_materialize
    .LANE_NAME_RE` excludes the apostrophe -- the one character the two
    dialects escape differently -- precisely because a printed argument
    cannot be quoted two ways at once. Both are asserted anyway: the day the
    alphabet or either dialect changes, this is where it is noticed.
    """
    module = doctor_module(REPO)
    monkeypatch.setenv("LANES_LANE", LANE)
    assert module.lane_trailer_command("posix") == \
        f" --trailer 'Lane: {LANE}'"
    assert module.lane_trailer_command("nt") == \
        f" --trailer 'Lane: {LANE}'"
    assert module.lane_trailer_command() == \
        module.lane_trailer_command(os.name)
    assert shlex.split(module.lane_trailer_command("posix")) == \
        ["--trailer", f"Lane: {LANE}"]


def test_the_lane_trailer_is_nothing_at_all_with_no_lane(monkeypatch):
    module = doctor_module(REPO)
    monkeypatch.delenv("LANES_LANE", raising=False)
    for platform in ("posix", "nt", None):
        assert module.lane_trailer_command(platform) == ""
    monkeypatch.setenv("LANES_LANE", "")
    assert module.lane_trailer_command("posix") == ""


def test_an_awkward_lane_name_is_quoted_and_not_merely_hoped_about(
        monkeypatch):
    """A name inside the alphabet but full of characters a shell cares
    about: parentheses, spaces and a slash all come back as ONE argument."""
    module = doctor_module(REPO)
    awkward = "xfactory-1 (spec/leg) @ home"
    monkeypatch.setenv("LANES_LANE", awkward)
    posix = module.lane_trailer_command("posix")
    assert shlex.split(posix) == ["--trailer", f"Lane: {awkward}"]
    assert module.lane_trailer_command("nt") == \
        f" --trailer 'Lane: {awkward}'"


#: THE WHOLE LINE, not a substring of it. `startswith("python")` was true of
#: `python3 ...` as well, which is exactly the spelling the Windows branch was
#: wrongly producing on a POSIX runner (Copilot, PR #102): an assertion that
#: cannot tell `python` from `python3` cannot check the one thing this
#: function's `platform` argument exists to make checkable.
#:
#: THE PATH IS PURE, not `Path`. `Path` is the HOST's flavour -- `WindowsPath`
#: on a Windows runner -- so `shape / 'setup.sh'` rendered `\srv\openRepoShape
#: \...` against this hard-coded `/srv/...` expectation no matter which
#: `platform` a row named: exactly what CI on Windows showed, on BOTH rows
#: (job `tests-windows`, run 34594408797). `PurePosixPath` is the same
#: flavour on every host, Windows included, so the rendering asserted below
#: no longer depends on which machine runs the suite.
#:
#: AND A `PureWindowsPath` IS NOW A STABLE FIXTURE, which it was not when
#: these rows were written (PR #102, commit 1f513c5). `scaffold_command`'s own
#: `quote_arg(shape / ...)` calls passed no `platform`, so each fell back to
#: the REAL host's `os.name` rather than the `platform` the row named -- and
#: `\` sits in `UNQUOTED_NT` but not in `UNQUOTED_POSIX`, so a genuine
#: `C:\...` fixture came back bare on a Windows runner and QUOTED on a POSIX
#: one, from the same row. That is #103, and it is fixed: one `target` now
#: governs the branch, the interpreter AND the quoting, so the two rows below
#: that name a Windows path render the same bytes on every host. The
#: `PurePosixPath` rows stay beside them because `/` is in both alphabets --
#: bare everywhere -- which is what makes them the pair that isolates the
#: ENTRY POINT and the INTERPRETER from the quoting; see `quote_arg` and
#: `UNQUOTED_NT`/`UNQUOTED_POSIX`.
SCAFFOLD_COMMAND = [
    ("posix", PurePosixPath("/srv/openRepoShape"),
     "/srv/openRepoShape/setup.sh --org <your-org> --project Atlas"),
    ("nt", PurePosixPath("/srv/openRepoShape"),
     "python /srv/openRepoShape/setup-project.py --org <your-org> "
     "--project Atlas"),
    # The path a Windows reader actually has, in the platform's own alphabet:
    # bare there, and quoted on POSIX where every `\` is an escape character.
    ("nt", PureWindowsPath(r"C:\srv\openRepoShape"),
     r"python C:\srv\openRepoShape\setup-project.py --org <your-org> "
     "--project Atlas"),
    ("posix", PureWindowsPath(r"C:\srv\openRepoShape"),
     r"'C:\srv\openRepoShape\setup.sh' --org <your-org> --project Atlas"),
]


@pytest.mark.parametrize("platform,shape,expected", SCAFFOLD_COMMAND)
def test_the_scaffold_command_is_the_readers_own_entry_point(platform,
                                                             shape,
                                                             expected):
    """`setup.sh` is bash, and Windows has no bash.

    The `way in` row's whole job is to hand somebody a line they can run, and
    on the one platform where this file has no shell to run that line in it
    was naming a path PowerShell cannot execute at all (Copilot, PR #102).
    `setup-project.py` is the standard's answer there and has been since #49:
    it IS the flow, and `setup.sh` is a shim over it (#50), which is why the
    README's Windows two-liner downloads that file and runs it.

    AND THE INTERPRETER IS THE ASKED-FOR PLATFORM'S, which is the half a
    loose assertion let through. `PYTHON` is decided once from `os.name`, so
    the Windows branch reading it printed `python3` on a POSIX runner -- the
    function claiming a spelling it did not produce, in the one place written
    to be read from the other platform. The expectation here is now the whole
    line, byte for byte, on both.
    """
    module = doctor_module(REPO)
    assert module.scaffold_command(shape, "Atlas", platform) == expected
    # And a project name with a space in it is still one argument.
    spaced = module.scaffold_command(shape, "My Thing", platform)
    assert spaced == expected.replace("--project Atlas",
                                      "--project 'My Thing'"), spaced


#: THE ONE VALUE THE TWO ALPHABETS DISAGREE ABOUT, as a path a Windows reader
#: actually has. `\` is in `UNQUOTED_NT` and not in `UNQUOTED_POSIX`, so this
#: is what tells the two PLATFORMS' spellings apart -- and, until #103, told
#: the two HOSTS apart instead, because `scaffold_command` quoted for
#: `os.name` while it spelled the entry point and the interpreter for the
#: `platform` it was handed.
WINDOWS_SHAPE = PureWindowsPath(r"C:\srv\openRepoShape")
#: The same path with the space every Windows machine has somewhere: NEITHER
#: alphabet admits it, so this one is quoted on both -- in each shell's own
#: form, which for a value with no apostrophe in it is the same form.
WINDOWS_SHAPE_SPACED = PureWindowsPath(r"C:\Program Files\openRepoShape")


def test_the_scaffold_lines_quoting_is_the_asked_for_platforms_too():
    r"""#103: half the line followed the argument and half followed the host.

    `platform` exists so this function can spell a line for the OTHER
    platform, and since #102 it threads that argument to the entry point
    (`setup-project.py` vs `setup.sh`) and to `python_command`. Its own
    `quote_arg` calls passed nothing, so they fell back to `os.name` -- and
    `\` is in one alphabet and not the other, so ONE call with ONE set of
    arguments produced two different strings depending on which machine
    asked: `python C:\srv\openRepoShape\setup-project.py ...` bare on a
    Windows host and `python 'C:\srv\openRepoShape\setup-project.py' ...` on
    Linux or macOS.

    BOTH SPELLINGS ARE ASSERTED BYTE FOR BYTE HERE, from whichever host runs
    the suite, which is the test PR #102 could not write: its `nt` row had to
    use a `PurePosixPath`, because `/` is in both alphabets and therefore
    hides the seam this one is about (commit 1f513c5, and the comment above
    `SCAFFOLD_COMMAND`). Every assertion below is the same on ubuntu, windows
    and macos, or the bug is back.
    """
    module = doctor_module(REPO)
    windows = module.scaffold_command(WINDOWS_SHAPE, "Atlas", "nt")
    posix = module.scaffold_command(WINDOWS_SHAPE, "Atlas", "posix")
    assert windows == (r"python C:\srv\openRepoShape\setup-project.py "
                       "--org <your-org> --project Atlas"), windows
    assert posix == (r"'C:\srv\openRepoShape\setup.sh' "
                     "--org <your-org> --project Atlas"), posix
    # And the POSIX form is a real `sh` word, not a string this suite spelled:
    # the shell's own reader hands the path back whole, backslashes and all.
    assert shlex.split(posix)[0] == r"C:\srv\openRepoShape\setup.sh"
    # A value NEITHER alphabet admits is quoted on both, so the fix is not
    # "never quote for Windows" -- it is "quote for the platform asked for".
    assert module.scaffold_command(WINDOWS_SHAPE_SPACED, "Atlas", "nt") == (
        r"python 'C:\Program Files\openRepoShape\setup-project.py' "
        "--org <your-org> --project Atlas")
    assert module.scaffold_command(WINDOWS_SHAPE_SPACED, "Atlas", "posix") == (
        r"'C:\Program Files\openRepoShape\setup.sh' "
        "--org <your-org> --project Atlas")
    # NO PLATFORM IS STILL THE HOST, unchanged: `quote_arg(value, None)`
    # resolves `os.name` exactly as `quote_arg(value, os.name)` does, so the
    # line every real run prints is the one it printed before.
    assert module.scaffold_command(WINDOWS_SHAPE, "Atlas") == (
        windows if os.name == "nt" else posix)


def test_the_way_in_row_matches_the_host_platform_end_to_end(standard,
                                                             tmp_path):
    """The row that PRINTS that line names no platform, and must not need to.

    `check_the_way_in` is where `scaffold_command` is actually called, and it
    passes no `platform` at all -- so every part of both its lines is the
    HOST's: the entry point, the interpreter and the quoting. That is the
    property #103 is about, so it is asserted here rather than assumed: the
    row's command is byte for byte what `scaffold_command` produces for this
    machine, and the adopt branch's is byte for byte what `quote_arg`
    produces for it. A `platform` threaded into this row later without being
    threaded through the quoting fails this test rather than shipping half a
    line.
    """
    module = doctor_module(standard)
    here = tmp_path / "Loose"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    scaffolds = module.check_the_way_in(module.Context(here))
    assert scaffolds.next_command == module.scaffold_command(
        module.SHAPE_ROOT, "Loose", os.name), scaffolds.next_command
    assert scaffolds.why == SCAFFOLD_WHY, scaffolds.why
    # The other way in, from the same directory once it is a repository.
    git("init", "-q", "-b", "main", ".", cwd=here)
    adopts = module.check_the_way_in(module.Context(here))
    assert adopts.next_command == (
        f"{module.PYTHON} "
        f"{module.quote_arg(module.SHAPE_ROOT / 'adopt-project.py', os.name)} "
        f"plan --source {module.quote_arg(here, os.name)} "
        f"--project {module.quote_arg('Loose', os.name)} "
        # No `origin` here, so `plan` reads no organisation (#545).
        "--org <your-org>"), adopts.next_command


def test_a_git_repository_is_told_of_both_ways_in(standard, tmp_path):
    """#545: AGENTS.md says to "report the verdict and both commands", and
    the report named the adoption alone for a repository.

    A row carries one NEXT, so the scaffold is the row after the adoption,
    for the same `--project`, printed as the non-repository row prints it.
    The verdict is untouched: both rows are `n/a`.
    """
    here = tmp_path / "Loose"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    result = doctor(standard, here, "--json")
    assert result.returncode == 2, result.stdout + result.stderr
    listed = json.loads(result.stdout)["rows"]
    ids = [row["id"] for row in listed]
    assert ids.index("way-in-scaffold") == ids.index("way-in") + 1, ids
    rows = rows_of(result)
    adopts, scaffolds = rows["way-in"], rows["way-in-scaffold"]
    module = doctor_module(standard)
    assert "adopt-project.py plan" in adopts["next"], adopts
    assert scaffolds["label"] == "the other way in", scaffolds
    assert scaffolds["status"] == "n/a", scaffolds
    assert scaffolds["next"] == module.scaffold_command(
        module.SHAPE_ROOT, "Loose"), scaffolds
    assert scaffolds["why"] == SCAFFOLD_WHY, scaffolds
    assert scaffolds["detail"]["suggested_project"] == "Loose", scaffolds

    text = doctor(standard, here)
    assert text.returncode == 2, text.stdout + text.stderr
    assert adopts["next"] in text.stdout, text.stdout
    assert scaffolds["next"] in text.stdout, text.stdout


def an_origin_of(path: Path, url: str | bytes | None) -> Path:
    """A repository at `path` whose `origin` is `url`: bytes through
    `with_origin`, so one that is not UTF-8 reaches git as written."""
    if isinstance(url, bytes):
        return with_origin(repository(path), url)
    return repository(path, origin=url)


#: `(origin URL, the organisation `adopt-project.py plan` reads from it)`, for
#: the spellings that matter: none at all (#545), an ordinary pair, one
#: ending `/`, which names its pair as the url without it does (#521), and
#: the other ways `plan` reads none -- a URL ending in no `org/repo`, a path
#: in any spelling, which names no repository (#521), and one that is not
#: UTF-8 -- which refuse `adopt-no-org` as a missing origin does
#: (`tests/test_adopt_git_reads.py`, `tests/test_adopt_origin_repository.py`).
ORIGIN_ORGS = [
    pytest.param(None, None, id="no-origin"),
    pytest.param("git@github.com:opensoft/Atlas.git", "opensoft", id="scp"),
    pytest.param("https://github.com/opensoft/Atlas", "opensoft", id="https"),
    pytest.param("Atlas.git", None, id="no-pair"),
    pytest.param("https://github.com/opensoft/Atlas/", "opensoft",
                 id="trailing-slash"),
    pytest.param("/srv/git/opensoft/Atlas.git", None, id="posix-path"),
    pytest.param("file:///srv/git/opensoft/Atlas.git", None, id="file-url"),
    pytest.param(r"D:\a\_work\1\s\Atlas.git", None, id="windows-path"),
    pytest.param(NOT_UTF8 + b"Atlas.git", None, id="not-utf8"),
]


@pytest.mark.parametrize("url, org", ORIGIN_ORGS)
def test_the_adoption_line_names_an_org_only_where_plan_reads_none(
        standard, tmp_path, url, org):
    """#545: pasted on a repository with no `origin`, the adoption line was
    refused `adopt-no-org`, exit 2, and so was one whose origin names no
    organisation `plan` can read. Where there is none the line ends in the
    placeholder the scaffold line already prints, and says to replace it;
    where `plan` reads one the line is what it always was.

    `ORIGIN_ORGS` IS NOT TRUSTED ON ITS OWN WORD: `origin_org` is
    `adopt-project.py`'s `_remote_repository` read for its organisation,
    through the one reading both import (`repo_shape.url_repository`,
    #521), and the same repository is put to both.
    """
    module = doctor_module(standard)
    here = an_origin_of(tmp_path / "Atlas", url)
    read = adoption_module(standard)._remote_repository(here)
    assert (read or "/").split("/")[0] == (org or ""), read
    assert module.origin_org(here) == org

    row = module.check_the_way_in(module.Context(here))
    assert row.detail["origin_org"] == org, row.detail
    named = f"--org {module.ORG_PLACEHOLDER}"
    assert row.next_command.endswith(named) is (org is None), row.next_command
    assert (row.why is None) is (org is not None), row.why
    if org is None:
        assert "replace <your-org> with the GitHub organisation" in row.why


def test_an_ancestors_origin_names_no_org_for_a_loose_directory(standard,
                                                                 tmp_path):
    """A directory with no `.git` of its own, inside a clone whose `origin`
    names `opensoft`, has no origin of its own to read an organisation from:
    `git remote get-url` would answer for the ancestor, as it does for the
    name (`test_the_way_in_row_never_leaks_an_ancestor_repository_origin`).
    """
    module = doctor_module(standard)
    parent = an_origin_of(tmp_path / "Parent",
                          "git@github.com:opensoft/Parent.git")
    loose = parent / "Loose"
    loose.mkdir()
    assert module.origin_org(parent) == "opensoft"
    assert module.origin_org(loose) is None


def test_the_way_in_row_emits_a_classifying_name_verbatim(standard, tmp_path):
    """#109: the derivation used to run unconditionally, respelling a name
    the `naming` row just above this one already classified.

    `openRepoProject` is `neutral-product` (`^open(?:[A-Z]|x[A-Z])
    [A-Za-z0-9]*$`), which admits the `assembly` role it would carry
    unchanged (2026-09-05). The old `"".join(part.capitalize() ...)`
    derivation turned it into `Openrepoproject` -- a bare
    `project-leg/assembly` token that ALSO classifies, so nothing in the
    naming policy caught the mismatch -- and the emitted
    `adopt-project.py plan` line proposed naming the two new legs off a
    token that loses the repository's own family, beside a root still
    called `openRepoProject`.
    """
    module = doctor_module(standard)
    here = tmp_path / "openRepoProject"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "openRepoProject", row.detail
    assert "--project openRepoProject" in row.next_command, row.next_command
    assert "Openrepoproject" not in row.next_command, row.next_command


def test_the_way_in_row_prefers_origins_name_over_the_local_folder(standard,
                                                                    tmp_path):
    """The identity that matters is the REPOSITORY's, not the folder it
    happens to sit in -- `check_not_a_root_naming`'s own docstring: "a clone
    into a differently named folder is ordinary, and the name that matters
    for the policy is the repository's." A folder named
    `clone-of-openrepoproject` (hyphenated, classifies nothing) beside an
    `origin` named `openRepoProject` must still emit `--project
    openRepoProject`, because that -- not the folder -- is what would
    actually be adopted.
    """
    module = doctor_module(standard)
    here = tmp_path / "clone-of-openrepoproject"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin",
        "git@github.com:opensoft/openRepoProject.git", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "openRepoProject", row.detail
    assert "--project openRepoProject" in row.next_command, row.next_command


def test_the_way_in_row_still_derives_a_token_for_a_name_that_does_not_classify(
        standard, tmp_path):
    """The fallback this row always had, kept for the case it exists for: a
    name the naming policy admits no form of at all has no valid
    `--project` to preserve, so the capitalized-parts derivation still runs
    -- unchanged from before #109.
    """
    module = doctor_module(standard)
    here = tmp_path / "my-repo"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "MyRepo", row.detail
    assert "--project MyRepo" in row.next_command, row.next_command


def test_the_way_in_row_also_keeps_a_classifying_name_when_scaffolding(
        standard, tmp_path):
    """The suggestion is computed ONCE, before the branch on `is_repo`, so a
    directory with no `.git` at all -- the SCAFFOLD half of this row --
    gets the identical treatment: a loose folder already named like a live
    neutral product (`openWidget`) is offered to `setup.sh` /
    `setup-project.py` as itself, never as `Openwidget`.
    """
    module = doctor_module(standard)
    here = tmp_path / "openWidget"
    here.mkdir()
    (here / "notes.txt").write_text("nothing to see\n", encoding="utf-8")
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["git_repository"] is False
    assert row.detail["suggested_project"] == "openWidget", row.detail
    assert "--project openWidget" in row.next_command, row.next_command


@pytest.mark.parametrize("name", ["openRepoProject", "openDox", "Thing",
                                  "my-repo", "brett-wip", "my.repo",
                                  "9lives"])
def test_the_way_in_rows_suggested_project_always_classifies(standard,
                                                              tmp_path, name):
    """Whichever branch answered -- verbatim or derived -- the value it
    handed back is always something `adopt-project.py` (and the scaffold)
    will actually accept as `--project`: the same `accepts_role` gate, role
    `assembly`, that `_check_names` runs. A suggestion nothing downstream
    would take is not a suggestion, checked here the way
    `tests/test_naming_policy.py` checks a classification -- in process,
    against the policy this run of the doctor itself loaded.

    `my.repo` and `9lives` are the two cases Copilot's review of #110 found
    the derivation still failed on -- a separator it did not split on, and a
    result with no leading letter -- kept here so the general property
    covers them alongside the cases #109 was filed for.
    """
    module = doctor_module(standard)
    here = tmp_path / name
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    policy = module.NamingPolicy.load(
        standard / "contracts" / "repository-naming.yaml")
    found = policy.classify(row.detail["suggested_project"], "assembly")
    assert module.accepts_role(found, "assembly"), (
        name, row.detail["suggested_project"], found)


def test_the_way_in_rows_fallback_normalizes_every_separator(standard,
                                                              tmp_path):
    """Copilot, PR #110: the fallback only split on `-` and `_`, so a `.`
    -- an ordinary character in a repository name, and now reachable through
    `origin`'s name and not only a directory's -- rode straight through into
    the suggested `--project`. `my.repo` must come back `MyRepo`, not
    `My.repo`.
    """
    module = doctor_module(standard)
    here = tmp_path / "my.repo"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "MyRepo", row.detail
    assert "--project MyRepo" in row.next_command, row.next_command


def test_the_way_in_rows_fallback_refuses_a_name_with_no_leading_letter(
        standard, tmp_path):
    """Copilot, PR #110: every family the policy declares starts with a
    letter, so a derivation that does not -- `9lives`, digit-led -- was
    never going to classify either, the same finding at the other end of
    the string. It falls back to the same `Project` placeholder a name
    with no letters or digits in it at all already used.
    """
    module = doctor_module(standard)
    here = tmp_path / "9lives"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "Project", row.detail
    assert "--project Project" in row.next_command, row.next_command


def test_the_way_in_row_never_leaks_an_ancestor_repository_origin(standard,
                                                                   tmp_path):
    """Copilot, PR #110: `git remote get-url origin` does not stop at
    `root` looking for one -- run from a directory that has none, it walks
    UP to the nearest ancestor repository and answers for THAT one. A loose
    folder with no `.git` of its own, sitting inside a clone of
    `openRepoProject`, must still scaffold itself as `Loose`, never adopt
    the ancestor's identity for a project this directory is not.
    """
    module = doctor_module(standard)
    parent = tmp_path / "ParentRepo"
    parent.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=parent)
    git("remote", "add", "origin",
        "git@github.com:opensoft/openRepoProject.git", cwd=parent)
    loose = parent / "Loose"
    loose.mkdir()
    row = module.check_the_way_in(module.Context(loose))
    assert row.detail["git_repository"] is False
    assert row.detail["suggested_project"] == "Loose", row.detail
    assert "--project Loose" in row.next_command, row.next_command
    assert "openRepoProject" not in row.next_command, row.next_command


def test_origin_name_reads_a_windows_style_local_path_remote(standard,
                                                              tmp_path):
    """Copilot, PR #110: a local-path `origin` git hands back exactly as
    configured, backslashes included, on any host -- the shape's own
    Windows CI lays a checkout out at a path spelled that way. The old
    basename split found no `/` to split a purely-backslash path on and
    returned the WHOLE path, which then read as an identity with a colon
    and a run of backslashes in it. Normalizing to `/` first must recover
    just `Atlas`, on every platform this suite runs on -- reading the
    remote back is a string operation, not a filesystem one, so the
    assertion holds without actually being on Windows.
    """
    module = doctor_module(standard)
    here = tmp_path / "winrepo"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", r"D:\a\_work\1\s\Atlas.git", cwd=here)
    assert module.origin_name(here) == "Atlas"
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "Atlas", row.detail
    assert "--project Atlas" in row.next_command, row.next_command


def test_an_origin_url_that_is_not_utf8_names_nothing_and_raises_nothing(
        standard, tmp_path):
    """#385: git keeps a URL as the bytes it was given, and all three of this
    file's readers of it raised `UnicodeDecodeError` on one that is not
    UTF-8 -- the `naming` row's, and so `--root`, first.

    THE NAME IS NONE, as for no origin, so `naming` and `the way in` read the
    directory alone, exactly as they do for the same directory with no
    `origin` (the twin, under another parent). THE URL IS READ AS `make
    siblings` READS IT, the byte replaced, because the `members` row must
    agree with `verify_sibling` about one directory (#146) -- the test of that
    agreement is `test_working_clone_and_verify_sibling_agree_on_a_non_utf8
    _origin`.
    """
    module = doctor_module(standard)
    here, twin = tmp_path / "a" / "latin1", tmp_path / "b" / "latin1"
    for path in (here, twin):
        path.mkdir(parents=True)
        git("init", "-q", "-b", "main", ".", cwd=path)
    with_origin(here, NOT_UTF8 + b"Atlas.git")
    assert module.origin_name(here) is None
    assert module.repo_local_origin_name(here) is None
    assert module.origin_url(here) == "../caf\ufffd/Atlas.git"
    for check in (module.check_not_a_root_naming, module.check_the_way_in):
        row, plain = check(module.Context(here)), check(module.Context(twin))
        assert row.detail == plain.detail, (row.detail, plain.detail)
        assert "Atlas" not in row.reason + (row.next_command or ""), row


def test_origin_name_reads_scp_like_syntax_with_no_slash_at_all(standard,
                                                                 tmp_path):
    """Copilot, second review of PR #110: `[user@]host:path` -- no group
    prefix, so no `/` anywhere in the URL -- hit the same "nothing to split
    on" failure the Windows path did: the whole string came back as the
    "name," and the derivation from it read `git@example.com:Atlas.git` as
    `GitExampleComAtlas`. Everything after the LAST `:`, once a URL scheme
    is ruled out, must recover just `Atlas`.
    """
    module = doctor_module(standard)
    here = tmp_path / "scprepo"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", "git@example.com:Atlas.git", cwd=here)
    assert module.origin_name(here) == "Atlas"
    row = module.check_the_way_in(module.Context(here))
    assert row.detail["suggested_project"] == "Atlas", row.detail
    assert "--project Atlas" in row.next_command, row.next_command


def test_origin_name_preserves_a_literal_backslash_in_a_posix_path(standard,
                                                                    tmp_path):
    """Copilot, second review of PR #110: normalizing EVERY backslash also
    rewrote a valid POSIX local-path remote whose basename merely contains
    one of its own -- `/tmp/foo\\bar.git` has `foo\\bar` as its basename,
    literally, and a blanket replace turned it into `bar`, silently
    discarding half of it. Only a recognizable Windows drive or UNC spelling
    gets its backslashes read as separators; everywhere else `\\` is an
    ordinary character and stays exactly where it was.
    """
    module = doctor_module(standard)
    here = tmp_path / "posixbs"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", r"/tmp/foo\bar.git", cwd=here)
    assert module.origin_name(here) == "foo\\bar"


def test_origin_name_preserves_a_colon_in_a_local_path_basename(standard,
                                                                 tmp_path):
    """Copilot, third review of PR #110: the SCP-syntax fix above read
    EVERY colon in a non-URL remote as `[user@]host:path`'s separator, so
    a local path whose own basename happens to contain one --
    `/tmp/openRepo:Project.git` -- was truncated the same way
    `git@example.com:Atlas.git` legitimately is, down to `Project` instead
    of `openRepo:Project`. Only a colon that FOLLOWS a drive letter or an
    SCP host -- neither of which ever contains a `/` -- is the separator;
    a colon anywhere else, including one already inside a path, is an
    ordinary character and stays exactly where it was.
    """
    module = doctor_module(standard)
    here = tmp_path / "coloninpath"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", "/tmp/openRepo:Project.git", cwd=here)
    assert module.origin_name(here) == "openRepo:Project"


def test_origin_name_reads_scp_like_syntax_with_a_colon_in_the_path(
        standard, tmp_path):
    """Copilot, fourth review of PR #110: the fix above reached for
    `rpartition`, the LAST colon, but the host's own colon is the FIRST
    one -- a group prefix in the path, `git@example.com:team:repo.git`,
    is ordinary SCP-like syntax and has two of them. Reading from the
    last one read `team:` as more of the HOST the first colon already
    separated, and dropped it along with the host: `repo` instead of
    `team:repo`.
    """
    module = doctor_module(standard)
    here = tmp_path / "scpgroup"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", "git@example.com:team:repo.git",
        cwd=here)
    assert module.origin_name(here) == "team:repo"


def test_origin_name_reads_a_bracketed_ipv6_host(standard, tmp_path):
    """Copilot, fourth review of PR #110: an IPv6 host is written
    `[host]` in this grammar because the address is already
    colon-separated -- `[::1]:repo.git`'s FIRST colon, by plain text
    position, sits INSIDE the brackets, part of the host, not at the
    host/path boundary. Splitting on it -- or on the last colon, equally
    wrong here since there is only the one -- would cut the host in
    half instead of finding the one real separator, right after the
    closing `]`.
    """
    module = doctor_module(standard)
    here = tmp_path / "ipv6host"
    here.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=here)
    git("remote", "add", "origin", "[::1]:repo.git", cwd=here)
    assert module.origin_name(here) == "repo"


def test_the_naming_row_also_never_leaks_an_ancestor_repository_origin(
        standard, tmp_path):
    """Copilot, second review of PR #110: the `way in` row's guard against
    an ancestor's `origin` (`test_the_way_in_row_never_leaks_an_ancestor
    _repository_origin`, above) meant nothing if the `naming` row right
    beside it still read one -- the two rows would disagree about the
    identity being classified for the exact same directory.
    `repo_local_origin_name` is the ONE guard both now share.
    """
    module = doctor_module(standard)
    parent = tmp_path / "ParentRepo"
    parent.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=parent)
    git("remote", "add", "origin",
        "git@github.com:opensoft/openRepoProject.git", cwd=parent)
    loose = parent / "Loose"
    loose.mkdir()
    row = module.check_not_a_root_naming(module.Context(loose))
    assert row.detail["names"] == ["Loose"], row.detail
    assert row.detail["origin"] is None, row.detail
    assert "openRepoProject" not in row.reason, row.reason


@pytest.mark.parametrize("platform,expected", [("posix", "python3"),
                                               ("nt", "python")])
def test_the_interpreter_named_is_the_asked_for_platforms(platform, expected):
    """`repo_shape.PYTHON`'s rule, per platform instead of per host.

    That constant is decided ONCE, at import, from `os.name`, and every other
    caller in this file wants exactly that -- they are spelling a command for
    the machine they are on. `scaffold_command` is the one that is not, and
    `python_command` is where the two readings are kept apart.
    """
    module = doctor_module(REPO)
    assert module.python_command(platform) == expected
    # `None` is the HOST, and it is the constant itself rather than a second
    # derivation of the same rule that could drift from it.
    assert module.python_command() is module.PYTHON
    assert module.python_command(None) == (
        "python" if os.name == "nt" else "python3")


#: The curly apostrophe this repository's OWN prose is written with, not the
#: straight one `AWKWARD_VALUES` already covers -- and the value that broke
#: `next_command`, because `ascii_text` maps it to `'` on the FAR side of
#: quoting rather than before it (Copilot, PR #102).
CURLY_APOSTROPHE = "O\u2019Neill"


def test_a_curly_apostrophe_is_normalized_before_it_is_quoted():
    """`quote_arg` must ascii-normalize FIRST, or `Row.__init__` breaks it.

    `Row.__init__` runs `ascii_text` again, after quoting, over the whole
    assembled command -- so a curly apostrophe that reached this function
    unconverted came back out of THAT pass as a bare, undoubled one, on the
    far side of the quoting it sat inside. `'O'Neill'` is an unterminated
    quotation to `sh`, and PowerShell's own verbatim string is exactly as
    broken by an apostrophe that never got doubled. Normalizing here first
    means the value quoted is already plain ASCII, so that later pass has
    nothing left to do.
    """
    module = doctor_module(REPO)
    posix = module.quote_arg(CURLY_APOSTROPHE, "posix")
    assert shlex.split(posix) == ["O'Neill"], posix
    assert module.quote_arg(CURLY_APOSTROPHE, "nt") == "'O''Neill'"


def test_a_trailing_newline_is_quoted_not_waved_through():
    r"""`$` matches just before a trailing newline; `.match` does not care.

    `re.match` only anchors the START of the string, so a pattern ending in
    `$` against `"Atlas\n"` matches the first five characters and stops --
    true, with the newline left over and never inspected. Bare, that
    newline would land in the middle of a command meant to run on one line
    (Copilot, PR #102). `.fullmatch` is what actually requires the alphabet
    to cover the WHOLE value, newline included.
    """
    module = doctor_module(REPO)
    value = "Atlas\n"
    posix = module.quote_arg(value, "posix")
    windows = module.quote_arg(value, "nt")
    assert posix != value, posix
    assert windows != value, windows
    assert shlex.split(posix) == [value], posix


@pytest.fixture
def awkward_project(scaffolded_here, tmp_path) -> Path:
    """The fixture project, at a path with a space and an apostrophe in it.

    A COPY rather than a scaffold into such a directory: the point under test
    is what the doctor PRINTS about a root, not what the scaffold does with
    one, and a submodule's `.git` is a file holding a RELATIVE path into
    `../.git/modules/<name>` -- which is what makes the copy honest as well as
    cheap (see `tests/conftest.py`).
    """
    target = tmp_path / AWKWARD / PROJECT
    target.parent.mkdir(parents=True)
    shutil.copytree(scaffolded_here["clone"], target, symlinks=True)
    return target


@pytest.mark.skipif(
    os.name == "nt",
    reason="shlex.split reads POSIX quoting; on Windows these commands are "
           "spelled for PowerShell, which the unit tests above assert")
def test_every_next_command_keeps_an_awkward_root_whole(standard,
                                                        awkward_project):
    """EVERY ROW, not the one a reviewer happened to look at.

    This is the shape of the defect: it was found against `placement` and it
    belonged to every row that interpolates a path, which is every row that
    names a fix. So the claim is made over a WHOLE report of a root with a
    space and an apostrophe in its path -- each row's next command read by
    `shlex.split`, which is the reader's own shell -- and the name that must
    survive is asserted to arrive in one piece rather than as two tokens
    nobody typed.
    """
    # Four separate faults, so that FIVE different rows go red at once and
    # each prints a next command of its own that names this root.
    edited = awkward_project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# an edit\n",
                      encoding="utf-8")
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "past it"],
                   cwd=str(awkward_project / "spec"), capture_output=True,
                   check=True, env={**os.environ, **GIT_IDENTITY})
    (awkward_project / "AGENTS-shape.md").unlink()
    stage(awkward_project / "spec", "tool.py", "VALUE = 1\n")

    rows = rows_of(doctor(standard, awkward_project, "--json"))
    naming = []
    for row in rows.values():
        command = (row["next"] or "").split("#")[0]
        if not command.strip():
            continue
        try:
            # THE FIRST ASSERTION IS THIS CALL. Unquoted, the apostrophe in
            # the directory name opens a quotation the line never closes, and
            # the reader's shell says so before the command has run at all.
            parts = shlex.split(command)
        except ValueError as exc:
            raise AssertionError(
                f"{row['id']}: no shell can read this line -- {exc}\n"
                f"  {command}")
        if not any(AWKWARD in part for part in parts):
            continue
        naming.append(row["id"])
        for part in parts:
            # The other failure: the name arrives as `.../do` and `ct'or/...`,
            # two arguments nobody typed.
            assert not part.endswith("/" + AWKWARD.split()[0]), \
                (row["id"], parts)
            assert AWKWARD in part or "ct'or" not in part, (row["id"], parts)
        # And the root itself is ONE argument wherever a command names it.
        if "--root" in parts:
            assert parts[parts.index("--root") + 1] == str(awkward_project), \
                (row["id"], parts)
    assert set(naming) >= {"pins", "shape-currency", "legs", "agent-files",
                           "placement"}, (
        "five rows are red and every one of them names this root; if a row "
        "has dropped out, the claim above is being made about less than it "
        f"says. Named it: {sorted(naming)}")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_a_drifted_roots_next_command_runs_when_it_is_pasted(
        standard, awkward_project):
    """The whole promise, end to end: the string, into a shell, verbatim.

    Not `shlex.split` this time and not an argv list the test assembled --
    `bash -c` with the printed line exactly as the reader would paste it,
    trailing `#` comment and all, because that is the act the row exists for.
    Unquoted, `--root <tmp>/do ct'or/Atlas` is a line the shell will not even
    parse -- the apostrophe opens a quotation it never closes -- and a root
    with only a SPACE in it gets as far as argparse, which reads the tail as
    positionals it has no argument for. Quoted, it is the one path: the check
    runs and reports the drift that made the row red, exit 1, naming the file.
    """
    edited = awkward_project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# an edit\n",
                      encoding="utf-8")
    result = doctor(standard, awkward_project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING", row
    assert "update-shape.py" in row["next"], row["next"]

    pasted = subprocess.run(["bash", "-c", row["next"]], capture_output=True,
                            text=True, check=False,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == 1, (
        f"`update-shape.py check` reports drift with exit 1; exit "
        f"{pasted.returncode} is a command that did not run.\n{whole}")
    assert DRIFT_TARGET in whole, whole
    assert "usage:" not in whole, whole
    assert "unrecognized arguments" not in whole, whole
    # And the unquoted spelling -- what this file printed before #101 -- is
    # the failure, so the assertion above cannot be passing by accident.
    quoted_root = doctor_module(standard).quote_arg(awkward_project, "posix")
    assert quoted_root != str(awkward_project), "the root needs quoting"
    naive = row["next"].replace(quoted_root, str(awkward_project))
    assert naive != row["next"], "the root was not quoted in the command"
    broken = subprocess.run(["bash", "-c", naive], capture_output=True,
                            text=True, check=False,
                            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
    said = broken.stdout + broken.stderr
    # It fails LOUDLY, which is the other half: exit 2 is argparse's usage
    # error and bash's syntax error alike. An apostrophe opens a quotation
    # the line never closes, so the shell refuses before `python3` is
    # reached; a path with only a space in it gets as far as argparse, which
    # reads the tail as positionals it has no argument for. Either way the
    # reader is stopped -- what they never get is the wrong repository
    # checked quietly.
    assert broken.returncode == 2, (
        "unquoted, the same line must not run and must say why; if it can, "
        f"this test is proving nothing.\n  exit {broken.returncode}\n"
        f"  {said[:400]}")
    assert "unexpected EOF" in said or "unrecognized arguments" in said, (
        "unquoted, the same line must not run and must say why; if it can, "
        f"this test is proving nothing.\n  exit {broken.returncode}\n"
        f"  {said[:400]}")


# --- a validator the root does not carry: its NEXT brings the environment ---
#
# When a root has no `scripts/validate-<x>.py` of its own, the doctor runs the
# standard's TEMPLATE copy and prints that file as the NEXT command. The
# template imports `repo_shape` from beside itself, and `repo_shape.py` is
# copied INTO a project out of the standard's `scripts/`, so the doctor's own
# child works only because `run_validator` puts `<standard>/scripts` on its
# `PYTHONPATH` -- and the line the row printed carried only the path. Pasted,
# it died on `ModuleNotFoundError: No module named 'repo_shape'` with exit 1,
# the code a validator uses for a finding (#238).
#
# Every other test of a validator's NEXT here runs a root that carries its OWN
# copy, which sits beside its own `repo_shape.py` -- so none of them could
# see it, and a `PYTHONPATH` exported by the person running the suite hides
# it from the ones that paste.

def _wrong_topic(body: bytes) -> bytes:
    return re.sub(rb"(?m)^topic: .*$", b"topic: xf-project-wrong", body)


def _zero_digest(body: bytes) -> bytes:
    return re.sub(rb'(tree_sha256: ")[0-9a-f]{64}(")',
                  rb"\g<1>" + b"0" * 64 + rb"\g<2>", body)


def _bad_family_id(body: bytes) -> bytes:
    return re.sub(rb"(?m)^id: .*$", b"id: Bad Id", body)


#: The three rows that go through `validator_row`, each made red by one edit
#: that LEAVES THE FILE LOADING (a manifest that does not load is another row,
#: `unloaded_manifest_row`, tested below): the validator it runs, the standard's
#: copy of it, the file the edit goes in, and the one finding that copy prints.
TEMPLATE_FALLBACK = {
    "manifest": {
        "own": "scripts/validate-manifest.py",
        "template": "templates/assembly-root/scripts/validate-manifest.py",
        "file": "project.yaml", "edit": _wrong_topic,
        "finding": "manifest-topic"},
    "pins": {
        "own": "scripts/validate-pins.py",
        "template": "templates/assembly-root/scripts/validate-pins.py",
        "file": "contracts/spec-pin.yaml", "edit": _zero_digest,
        "finding": "pin-digest-mismatch"},
    "family": {
        "own": "scripts/validate-family.py",
        "template": "templates/family-root/scripts/validate-family.py",
        "file": "family.yaml", "edit": _bad_family_id,
        "finding": "family-id"},
}


def red_root(case: str, project: Path, holder: dict, tmp_path: Path,
             keep_own: bool = False) -> Path:
    """A root whose `case` gate is red, with or without its own validator.

    `keep_own=False` is the fixture the issue was filed against: the root's
    copy of the validator is gone, so the row falls back to the standard's.
    `keep_own=True` is the same red gate with the root's own copy in place,
    which is the case that must not change. The holder is COPIED, as every
    test here that edits one does, so the session's stays intact.
    """
    spec = TEMPLATE_FALLBACK[case]
    if case == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
    else:
        root = project
    root = root.resolve()
    target = root / spec["file"]
    body = target.read_bytes()
    edited = spec["edit"](body)
    assert edited != body, "the edit did not change the file"
    target.write_bytes(edited)
    if not keep_own:
        (root / spec["own"]).unlink()
    return root


def pasted_from_elsewhere(command: str, tmp_path: Path):
    """The row's NEXT into `sh -c`, exactly as printed, from the filesystem
    root, with no `PYTHONPATH` in the environment.

    The three things a reader's shell can have that the doctor's child did
    not: a different working directory (the line names every path absolutely,
    so it needs none), a different environment (this is the one under test),
    and the whole line, exactly as printed, rather than an argv the test
    split. `PYTHONDONTWRITEBYTECODE` is the one thing put back, so
    that running the standard's validators from the session's `standard`
    leaves no `__pycache__` in it, as every other paste here does.
    """
    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(["sh", "-c", command], cwd=str(Path(tmp_path.anchor)),
                          capture_output=True, text=True, check=False,
                          env=env)


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_template_validators_next_command_runs_when_it_is_pasted(
        standard, project, holder, tmp_path, case):
    """(a) and (b): the row's NEXT, pasted, is the finding the row reported.

    ONE CLAIM, MADE OF THREE THINGS the doctor's own run already did: the
    validator's own finding is printed, the exit is the row's `detail.exit`,
    and there is no traceback. The bare-path spelling made all three false at
    once -- `ModuleNotFoundError`, exit 1, which is also what a finding exits
    with, so the exit code alone would have passed. That is why the finding
    id is asserted in the output and the import error is asserted absent.

    The root's own validator is GONE and the gate is red by a file that still
    loads, so the row is the one `validator_row` builds for the fallback and
    `shape-currency` separately calls the missing copy a drift.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = red_root(case, project, holder, tmp_path)
    result = doctor(standard, root, "--json")
    row = rows_of(result)[case]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    template = (standard / spec["template"]).resolve()
    assert Path(row["detail"]["validator"]).resolve() == template, row
    assert row["detail"]["exit"] == 1, row
    assert spec["finding"] in row["reason"], row

    pasted = pasted_from_elsewhere(row["next"], tmp_path)
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == row["detail"]["exit"], whole
    assert f"FINDING {spec['finding']}" in whole, whole
    for crash in ("Traceback", "ModuleNotFoundError", "repo_shape"):
        assert crash not in whole, (crash, whole)

    # AND THE TEST CAN SEE THE DEFECT: the same line without its environment
    # is the traceback, exit 1, and says nothing about the project.
    scripts = doctor_module(standard).quote_arg(standard.resolve() / "scripts",
                                                "posix")
    # `env`, not a bare `NAME=value` prefix, which csh and tcsh cannot run
    # (#277).
    assert row["next"].startswith(f"env PYTHONPATH={scripts} python3 "), \
        row["next"]
    bare = pasted_from_elsewhere(
        row["next"].removeprefix(f"env PYTHONPATH={scripts} "), tmp_path)
    assert bare.returncode == 1, bare.stdout + bare.stderr
    assert "ModuleNotFoundError: No module named 'repo_shape'" in \
        bare.stdout + bare.stderr, bare.stdout + bare.stderr
    assert spec["finding"] not in bare.stdout + bare.stderr


#: SKIPPED EVERYWHERE BUT WINDOWS, with the reason beside it: the `$env:` line
#: is only the one the doctor PRINTS on a Windows host (`validator_command`
#: asks `os.name`), and only a Windows runner carries `powershell.exe` to run
#: it. The dialect is held as text from every host by
#: `VALIDATOR_COMMAND` below; this is the one test that RUNS it (review N3).
@pytest.mark.skipif(os.name != "nt",
                    reason="the PowerShell line is printed, and powershell.exe "
                           "exists, only on a Windows host")
@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_template_validators_next_runs_when_pasted_into_powershell(
        standard, project, holder, tmp_path, case):
    """The `$env:` line, run for real in a FRESH `powershell`, is the finding.

    The same three claims as the `sh` paste above: the validator's own
    finding is printed, the exit is the row's `detail.exit`, and no
    `ModuleNotFoundError` -- from the filesystem root and with no
    `PYTHONPATH` in the environment, so the only `repo_shape` this run can
    find is the one the line itself put on the path.

    TWO THINGS ABOUT `-Command`. A native command's non-zero exit is
    `$LASTEXITCODE`, and `-Command` ends the session with 1 whatever it was,
    so `; exit $LASTEXITCODE` is appended to the line as printed -- which is
    the command alone since #277, with no trailing `#` comment to swallow
    the `exit` the way PowerShell reads one, to the end of the line. And
    the output is read as BYTES and decoded here as UTF-8 with replacement,
    on purpose: the finding id this asserts is ASCII, and what the console's
    code page does to anything else is not under test. Nothing is fed to
    stdin (`subprocess.DEVNULL`), so there is no path to encode.

    NOT RUN ON THE WRITER'S WORKSTATION, which has no PowerShell: the pull
    request's `tests-windows` job is this test's first run.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = red_root(case, project, holder, tmp_path)
    row = rows_of(doctor(standard, root, "--json"))[case]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    assert row["next"].startswith("$env:PYTHONPATH = '"), row["next"]
    line = row["next"]
    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    pasted = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command",
         f"{line}; exit $LASTEXITCODE"],
        cwd=str(Path(tmp_path.anchor)), capture_output=True,
        stdin=subprocess.DEVNULL, check=False, env=env)
    whole = (pasted.stdout + pasted.stderr).decode("utf-8", errors="replace")
    assert pasted.returncode == row["detail"]["exit"], whole
    assert f"FINDING {spec['finding']}" in whole, whole
    for crash in ("Traceback", "ModuleNotFoundError", "repo_shape"):
        assert crash not in whole, (crash, whole)


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_template_validators_row_carries_the_same_next_in_text_and_json(
        standard, project, holder, tmp_path, case):
    """`--json` and the table print ONE line, and it is the builder's for
    this host: the interpreter, the standard's template as a path, the
    environment in the dialect of the platform running -- PowerShell's
    assignment on Windows, `sh`'s prefix elsewhere.

    NOT SKIPPED ON WINDOWS, unlike the paste above, so the Windows job holds
    the row to its own dialect even though it cannot run the `sh` line.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = red_root(case, project, holder, tmp_path)
    row = rows_of(doctor(standard, root, "--json"))[case]
    module = doctor_module(standard)
    shape = standard.resolve()
    expected = module.validator_command(shape, shape / spec["template"],
                                        False, ["--root", root])
    assert expected.startswith("$env:PYTHONPATH = " if os.name == "nt"
                               else "env PYTHONPATH="), expected
    # THE COMMAND ALONE, and what to do with its output beside it (#277).
    assert row["next"] == expected, (expected, row["next"])
    assert row["next"] in doctor(standard, root).stdout
    assert row["why"].startswith("read its output in full"), row["why"]


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_a_roots_own_validators_next_command_is_unchanged(
        standard, project, holder, tmp_path, case):
    """(3): the root's OWN copy, byte for byte as it has always been.

    That copy sits beside its own `repo_shape.py`, so it needs no
    environment, and a `PYTHONPATH` in front of it would send the reader's
    run at the STANDARD's `repo_shape.py` instead -- the gate of a project
    that holds its own pinned copy, answered by a different one. The whole
    line is spelled here out of the pieces this file already trusts, rather
    than read back from the code that builds it.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = red_root(case, project, holder, tmp_path, keep_own=True)
    row = rows_of(doctor(standard, root, "--json"))[case]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is True, row
    module = doctor_module(standard)
    assert row["next"] == (
        f"{module.PYTHON} {module.quote_arg(root / spec['own'])} --root "
        f"{module.quote_arg(root)}"), row["next"]
    # The sentence that rode on the line as `   # ...` until #277.
    assert row["why"] == "read its output in full; it names what it refused"
    assert "PYTHONPATH" not in row["next"], row["next"]
    assert_next_runs_the_roots_own(row, root, Path(spec["own"]).name)


# --- a root's OWN validator is run, and printed, as its own gate runs it ----
#
# The template's `PYTHONPATH` is the doctor's to give, and only to the copy
# that has no `repo_shape.py` beside it. A root that keeps its OWN validator
# and has lost its own `scripts/repo_shape.py` has a gate that cannot import
# it: the doctor must run that gate the way the project does, so the row says
# what the gate says, and the line it prints says the same thing when pasted.
# Run under the standard's `PYTHONPATH` instead, the row answered "passes" or
# quoted the validator's own finding, and the pasted line died on
# `ModuleNotFoundError` -- the #238 symptom, with `own_copy: true` (review S1).

def root_without_its_repo_shape(case: str, project: Path, holder: dict,
                                tmp_path: Path, red: bool) -> Path:
    """A root with its OWN `case` validator and no `scripts/repo_shape.py`.

    `red=True` is the gate made red by the file edit `TEMPLATE_FALLBACK` names
    for the case, which still loads; `red=False` leaves the manifest valid, so
    the only thing wrong with the root is the file it lost. The holder is
    COPIED, as everywhere here, so the session's stays intact.
    """
    spec = TEMPLATE_FALLBACK[case]
    if red:
        root = red_root(case, project, holder, tmp_path, keep_own=True)
    elif case == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
        root = root.resolve()
    else:
        root = project.resolve()
    assert (root / spec["own"]).is_file(), spec["own"]
    gone = root / "scripts" / "repo_shape.py"
    assert gone.is_file(), gone
    gone.unlink()
    return root


def doctor_exporting(standard: Path, root: Path, pythonpath: str):
    """`rows_of` this root, from a doctor whose operator EXPORTED
    `PYTHONPATH=<pythonpath>`. `run_script` can set a variable but not remove
    one, so "none" is the empty value, which is no entry to Python."""
    return rows_of(run_script(standard / DOCTOR, "--root", str(root), "--json",
                              env={"PYTHONPATH": pythonpath}))


def doctor_with_no_pythonpath(standard: Path, root: Path):
    """`rows_of` this root, from a doctor whose environment has NO
    `PYTHONPATH`, so the tests that use it ask the import question and nothing
    else. Since #306 the doctor takes the variable out of every validator's
    child whatever the operator exported, so these tests would give the same
    answer without this; the ones below that EXPORT one are the ones that hold
    that."""
    return doctor_exporting(standard, root, "")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_an_own_validator_without_repo_shape_is_a_finding_the_paste_agrees(
        standard, project, holder, tmp_path, case):
    """(a): the row quotes the ImportError, and the own-copy NEXT, pasted from
    `/` with no `PYTHONPATH`, dies on that same import with the row's exit.

    THE RUN AND THE LINE ARE ONE PROCESS FOR THIS COPY: neither has a
    `PYTHONPATH` the root's own validator did not already have, so what the
    row quoted is what the reader gets. The finding the wrong file would have
    produced (`manifest-topic`, ...) is in NEITHER, because neither run got as
    far as reading it -- which is what separates this from a validator that
    ran and was red.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = root_without_its_repo_shape(case, project, holder, tmp_path,
                                       red=True)
    row = doctor_with_no_pythonpath(standard, root)[case]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is True, row
    assert row["detail"]["exit"] == 1, row
    assert "ModuleNotFoundError: No module named 'repo_shape'" in \
        row["reason"], row
    assert spec["finding"] not in row["reason"], row
    # The own copy's line is what it has always been: no environment.
    assert "PYTHONPATH" not in row["next"], row["next"]
    assert_next_runs_the_roots_own(row, root, Path(spec["own"]).name)

    pasted = pasted_from_elsewhere(row["next"], tmp_path)
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == row["detail"]["exit"], whole
    assert "ModuleNotFoundError: No module named 'repo_shape'" in whole, whole
    assert spec["finding"] not in whole, whole


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_an_own_validator_without_repo_shape_does_not_pass(
        standard, project, holder, tmp_path, case):
    """(b): a VALID manifest, the same lost file -- and no "passes".

    The row used to say `the project's own scripts/validate-manifest.py
    passes` over a gate that exits 1 on `ModuleNotFoundError` when the project
    runs it. It is now the gate's own failure, and the gate is run here
    directly to say so: the row and the project's own command agree on the
    exit code and on the line, not only on the absence of a pass.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = root_without_its_repo_shape(case, project, holder, tmp_path,
                                       red=False)
    row = doctor_with_no_pythonpath(standard, root)[case]
    assert row["status"] != "ok", row
    assert "passes" not in row["reason"], row
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is True, row
    assert "ModuleNotFoundError: No module named 'repo_shape'" in \
        row["reason"], row

    env = {name: value for name, value in os.environ.items()
           if name.upper() != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    gate = subprocess.run(
        [sys.executable, str(root / spec["own"]), "--root", str(root)],
        cwd=str(root), capture_output=True, encoding="utf-8",
        errors="replace", stdin=subprocess.DEVNULL, check=False, env=env)
    assert gate.returncode == row["detail"]["exit"], gate.stdout + gate.stderr
    assert "ModuleNotFoundError: No module named 'repo_shape'" in \
        gate.stdout + gate.stderr


# --- the child gets exactly the `PYTHONPATH` the row's NEXT prints (#306) ---
#
# `run_validator` used to start from the doctor's own environment and only ADD
# to it, so an operator whose `PYTHONPATH` reached a `repo_shape.py` was told
# that a root which lost its own passes its gate (#238 had removed that for
# everyone else), and the template copy's `PYTHONPATH` was the standard's
# `scripts/` IN FRONT OF theirs where the printed NEXT sets it ALONE. The child
# now has what the line prints: the one directory for the template's copy, and
# no `PYTHONPATH` at all for the root's own. The row is about the project's own
# gate as CI runs it, and CI exports nothing.

@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_an_exported_pythonpath_does_not_stand_in_for_a_lost_repo_shape(
        standard, project, holder, tmp_path, case):
    """(a): the standard's `scripts/` exported, the root's own `repo_shape.py`
    gone, the manifest VALID -- and the row is still the gate's failure.

    THE ONE OPERATOR WHO WAS TOLD "passes": the variable reaches a
    `repo_shape.py`, here the standard's own, which is exactly what stands in
    for the file the root lost. The project's own gate fails on it in CI
    (`test_an_own_validator_without_repo_shape_does_not_pass` runs that gate
    and says so), so the row must not read otherwise because of what the
    person running the doctor happens to have exported. The `pins` and
    `family` rows are held to the same sentence: the `pins` one was already a
    finding with a DIFFERENT message under an export, and the quoted import
    error is the project's own gate's.
    """
    root = root_without_its_repo_shape(case, project, holder, tmp_path,
                                       red=False)
    scripts = standard.resolve() / "scripts"
    assert (scripts / "repo_shape.py").is_file(), (
        "the standard's own repo_shape.py is the one an export reaches, or "
        "this test is proving nothing")
    row = doctor_exporting(standard, root, str(scripts))[case]
    assert row["status"] == "FINDING", row
    assert "passes" not in row["reason"], row
    assert row["detail"]["own_copy"] is True, row
    assert row["detail"]["exit"] == 1, row
    assert "ModuleNotFoundError: No module named 'repo_shape'" in \
        row["reason"], row


#: What the operator's directory holds in the test below, written out: a
#: `sitecustomize.py` that ends any VALIDATOR with a distinctive exit, and a
#: `repo_shape.py` that raises when it is imported.
#:
#: THE `sitecustomize.py` IS WHAT DOES THE WORK, and it catches every way the
#: directory can reach a validator. `PYTHONPATH` entries come ahead of the
#: standard library and of site-packages, so the first `sitecustomize` on a
#: child's path is this one wherever the directory sits in the value -- in
#: front of the standard's `scripts/`, behind it, or alone -- and it ends the
#: child at start-up, before a single import. Python imports ONE
#: `sitecustomize`, the first it finds, and the doctor is not that child: its
#: own script is not `validate-*`, so it runs on.
#:
#: A `repo_shape.py` ALONE CANNOT TELL PREPENDING FROM REPLACING: the
#: standard's `scripts/` comes first in a prepended value, so the standard's
#: `repo_shape` wins the import and the decoy behind it is never read. The
#: raising `repo_shape.py` decides an outcome only where `sitecustomize` does
#: not load from the path (site customisation off, or an earlier
#: `sitecustomize` ahead of this one), and there it is what a child that put
#: the operator's directory FIRST would import. It is a fallback, and no test
#: here depends on it.
DECOY_REPO_SHAPE = (
    "raise ImportError(\"the operator's repo_shape.py was imported by a "
    "validator\")\n")
DECOY_SITECUSTOMIZE = "\n".join([
    "import os",
    "import sys",
    "if os.path.basename((sys.argv or [''])[0]).startswith('validate-'):",
    "    sys.stderr.write('DECOY: a validator reached the decoy\\n')",
    "    os._exit(86)",
    ""])


@pytest.mark.parametrize("case", sorted(TEMPLATE_FALLBACK))
def test_an_exported_pythonpath_does_not_reach_a_template_validator(
        standard, project, holder, tmp_path, case):
    """(b): an operator's `PYTHONPATH` that holds a decoy, the root's own
    validator gone -- and the row is still the template's real verdict.

    The line the row prints SETS `PYTHONPATH=<standard>/scripts` and does not
    add to a variable (`validator_command`), so the run it describes must not
    either. It used to put the standard's directory in FRONT of the
    operator's and leave theirs behind it, where Python found the decoy's
    `sitecustomize` and ended the validator with exit 86; the line, pasted,
    never had that directory. The verdict asserted is the real one: the
    finding the red file produces, and the template's own exit `1`, as
    `test_a_template_validators_next_command_runs_when_it_is_pasted` has it
    for a doctor that exports nothing.
    """
    spec = TEMPLATE_FALLBACK[case]
    root = red_root(case, project, holder, tmp_path)
    decoy = tmp_path / "operators-pythonpath"
    decoy.mkdir()
    (decoy / "repo_shape.py").write_text(DECOY_REPO_SHAPE, encoding="utf-8")
    (decoy / "sitecustomize.py").write_text(DECOY_SITECUSTOMIZE,
                                            encoding="utf-8")
    rows = doctor_exporting(standard, root, str(decoy))
    row = rows[case]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    assert row["detail"]["exit"] == 1, row
    assert spec["finding"] in row["reason"], row
    for leaked in ("DECOY", "operator's repo_shape", "ImportError"):
        assert leaked not in row["reason"], row

    # AND NO OTHER ROW OF THE RUN REACHED THE DECOY. The row above is the one
    # that passes a directory; the `naming` rows and the machine's preflight
    # pass none. On main every row whose validator the decoy reached said so,
    # and this catches any row that reaches it, which is how it catches a
    # `run_validator` that kept the variable for the callers that pass none
    # (#306 review S1): popped only for a script inside the root, or with the
    # `else` dropped, the `naming` row reads `FINDING ... (exit 86): DECOY`
    # while `manifest` reads the real finding. So no row may quote the decoy
    # or say it exited 86, whichever caller handed it the variable.
    reached = [name for name, other in rows.items()
               if "DECOY" in other["reason"]
               or "(exit 86)" in other["reason"]
               or (other.get("detail") or {}).get("exit") == 86]
    assert not reached, (reached, rows)


#: Every combination of what the operator exported and what the caller asks
#: for. A caller that passes a directory gets that directory ALONE, however
#: much the operator had; a caller that passes none gets no variable at all --
#: the three callers that run the standard's own scripts (the two naming rows
#: and the machine's preflight) among them, which need none and are unaffected
#: (#238's review).
ABSENT = "<no PYTHONPATH>"
OPERATOR_AND_CALLER = [
    (None, None),
    ("", None),
    (os.pathsep.join(["/operator/a", "/operator/b"]), None),
    (None, "scripts-dir"),
    ("", "scripts-dir"),
    (os.pathsep.join(["/operator/a", "/operator/b"]), "scripts-dir"),
]


@pytest.mark.parametrize("exported,given", OPERATOR_AND_CALLER)
def test_run_validator_gives_the_child_exactly_the_pythonpath_it_is_given(
        standard, tmp_path, monkeypatch, exported, given):
    """The contract of `run_validator`'s `env` block, asked of the child
    itself: `str(pythonpath)` alone, or no variable, whatever the doctor's own
    environment held. The probe prints what it was started with, so nothing
    about a validator's imports comes into it.

    This is the assertion the two row tests above are made of, at the level a
    caller sees it, and it holds the callers which pass no `pythonpath` by
    where its probe lies: beside the root, as the standard's own naming and
    preflight scripts do, as well as inside it. Those scripts need nothing
    from the variable, so only a probe like this one, or (b)'s decoy, can see
    that they have none.
    """
    module = doctor_module(standard)
    if exported is None:
        monkeypatch.delenv("PYTHONPATH", raising=False)
    else:
        monkeypatch.setenv("PYTHONPATH", exported)
    root = tmp_path / "root"
    root.mkdir()
    pythonpath = None if given is None else tmp_path / given
    want = ABSENT if given is None else str(pythonpath)
    # THE PROBE ON BOTH SIDES OF THE ROOT: inside it, where a root's own
    # validator lives, and beside it, where the standard's own scripts (naming,
    # the preflight) live. A `run_validator` that took the variable out only
    # for a script that lies inside the root would pass the first and fail the
    # second (#306 review S1).
    for where in (root, tmp_path):
        probe = where / "probe.py"
        probe.write_text(
            "import os\n"
            f"print(os.environ.get('PYTHONPATH', {ABSENT!r}))\n",
            encoding="utf-8")
        code, _quoted, whole = module.run_validator(
            module.Context(root), probe, [], pythonpath)
        assert code == 0, whole
        assert whole.strip() == want, (exported, given, probe, whole)


#: One breakage per kind of root, and the three an assembly root's `project.yaml`
#: has, for `unloaded_manifest_row`: the manifest is THERE and does not load,
#: so it is that row's NEXT, not `validator_row`'s, that names the gate.
UNLOADED = [("project", case) for case in sorted(BREAKAGES)] + \
    [("family", "tab-indent")]


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
@pytest.mark.parametrize("kind,case", UNLOADED)
def test_an_unloaded_manifests_template_next_command_runs_when_it_is_pasted(
        standard, project, holder, tmp_path, kind, case):
    """`unloaded_manifest_row` names the gate through the same definition.

    A root with no `validate-manifest.py` of its own and a `project.yaml`
    that does not parse is told to run the standard's copy -- and that line
    was the bare template path too (#205 chose the file, #238 is what the
    file needs to run). Pasted, it refuses the file with the validator's exit
    2 and the loader's own words, the way the root's own copy does in
    `test_the_manifest_rows_next_command_refuses_the_same_file_the_same_way`.
    """
    if kind == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
        edit, code = FAMILY_BREAKAGES[case]
        name, own, row_id, script = ("family.yaml", "scripts/validate-family.py",
                                     "family", "validate-family.py")
    else:
        root = project
        edit, code = BREAKAGES[case]
        name, own, row_id, script = ("project.yaml",
                                     "scripts/validate-manifest.py",
                                     "manifest", "validate-manifest.py")
    root = root.resolve()
    (root / own).unlink()
    path = root / name
    refusal = break_manifest(path, edit, code)
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    assert Path(row["detail"]["validator"]).name == script, row
    assert Path(row["detail"]["validator"]).resolve() != \
        (root / own).resolve(), row
    assert row["next"].startswith("env PYTHONPATH="), row["next"]

    pasted = pasted_from_elsewhere(row["next"], tmp_path)
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == 2, whole
    assert f"REFUSED {refusal.code}: " in whole, whole
    assert refusal.detail[len(str(path)):] in whole, (refusal.detail, whole)
    for crash in ("Traceback", "ModuleNotFoundError"):
        assert crash not in whole, (crash, whole)


@pytest.mark.parametrize("kind,case", UNLOADED)
def test_an_unloaded_manifests_own_copy_next_command_is_unchanged(
        standard, project, holder, tmp_path, kind, case):
    """The same row, the root's own copy present: no environment, and the
    line is what #205 printed -- the interpreter, the root's own validator
    as a path, `--root` the root -- with the sentence that names the file to
    fix as the row's `why`, where #277 moved the comment that used to end it.
    """
    if kind == "family":
        root = tmp_path / FAMILY_NAME
        shutil.copytree(holder["root"], root, symlinks=True)
        edit, code = FAMILY_BREAKAGES[case]
        name, own, row_id = ("family.yaml", "scripts/validate-family.py",
                             "family")
    else:
        root = project
        edit, code = BREAKAGES[case]
        name, own, row_id = ("project.yaml", "scripts/validate-manifest.py",
                             "manifest")
    root = root.resolve()
    break_manifest(root / name, edit, code)
    row = rows_of(doctor(standard, root, "--json"))[row_id]
    assert row["detail"]["own_copy"] is True, row
    module = doctor_module(standard)
    assert row["next"] == (
        f"{module.PYTHON} {module.quote_arg(root / own)} --root "
        f"{module.quote_arg(root)}"), row["next"]
    assert row["why"].startswith(
        f"the file to fix is {module.quote_arg(root / name)}, where the line "
        "above says; "), row["why"]
    assert "PYTHONPATH" not in row["next"], row["next"]


#: THE LINE FOR EACH SHELL, whole, as `validator_command` is asked for it.
#: `quote_arg` is asserted on its own above and `copy_command` and
#: `scaffold_command` have their own rows; what is new here is the ENVIRONMENT
#: in front of the interpreter -- an assignment prefix for `sh`, a statement
#: before it for PowerShell -- and what each does to a path that needs quoting.
VALIDATOR_TEMPLATE = "templates/assembly-root/scripts/validate-manifest.py"
VALIDATOR_COMMAND = [
    # `sh`: `env NAME=value command ...` -- `env`, which csh, tcsh and fish
    # run too, where a bare `NAME=value` prefix is `sh` syntax (#277) -- and
    # a root's own copy has none.
    ("posix", PurePosixPath("/srv/openRepoShape"), False, PurePosixPath(
        "/srv/work/Atlas"),
     "env PYTHONPATH=/srv/openRepoShape/scripts python3 "
     "/srv/openRepoShape/templates/assembly-root/scripts/validate-manifest.py "
     "--root /srv/work/Atlas"),
    ("posix", PurePosixPath("/srv/openRepoShape"), True, PurePosixPath(
        "/srv/work/Atlas"),
     "python3 /srv/work/Atlas/scripts/validate-manifest.py "
     "--root /srv/work/Atlas"),
    # A standard checked out where a space is: both words are quoted whole,
    # and the assignment's quote closes at the value's end.
    ("posix", PurePosixPath("/srv/my shape"), False, PurePosixPath(
        "/srv/work/Atlas"),
     "env PYTHONPATH='/srv/my shape/scripts' python3 "
     "'/srv/my shape/templates/assembly-root/scripts/validate-manifest.py' "
     "--root /srv/work/Atlas"),
    # PowerShell: `$env:NAME = 'value'; command ...`, the value ALWAYS quoted.
    # The first row is the one a bare `C:\srv\openRepoShape\scripts` would
    # have got wrong: after `=` it is a command to run, not a string.
    ("nt", PureWindowsPath(r"C:\srv\openRepoShape"), False, PureWindowsPath(
        r"C:\work\Atlas"),
     r"$env:PYTHONPATH = 'C:\srv\openRepoShape\scripts'; python "
     r"C:\srv\openRepoShape\templates\assembly-root\scripts\validate-manifest.py "
     r"--root C:\work\Atlas"),
    ("nt", PureWindowsPath(r"C:\srv\openRepoShape"), True, PureWindowsPath(
        r"C:\work\Atlas"),
     r"python C:\work\Atlas\scripts\validate-manifest.py "
     r"--root C:\work\Atlas"),
    # An apostrophe is doubled, in the path and in the value.
    ("nt", PureWindowsPath(r"C:\Users\Jane O'Neill\openRepoShape"), False,
     PureWindowsPath(r"C:\work\Atlas"),
     r"$env:PYTHONPATH = 'C:\Users\Jane O''Neill\openRepoShape\scripts'; "
     r"python 'C:\Users\Jane O''Neill\openRepoShape\templates\assembly-root"
     r"\scripts\validate-manifest.py' --root C:\work\Atlas"),
    # And the quoting is the platform's asked for, not the host's: a Windows
    # path on `sh` is quoted whole, every `\` a literal character.
    ("posix", PureWindowsPath(r"C:\srv\openRepoShape"), False,
     PureWindowsPath(r"C:\work\Atlas"),
     r"env PYTHONPATH='C:\srv\openRepoShape\scripts' python3 "
     r"'C:\srv\openRepoShape\templates\assembly-root\scripts"
     r"\validate-manifest.py' --root 'C:\work\Atlas'"),
]


@pytest.mark.parametrize("platform,shape,own_copy,root,expected",
                         VALIDATOR_COMMAND)
def test_the_validator_line_carries_its_environment_in_the_readers_dialect(
        platform, shape, own_copy, root, expected):
    """(c): the Windows spelling, asserted as text from any host.

    No PowerShell runs here, as for the `Copy-Item` rows: the line is held
    to the exact string a PowerShell reader is meant to paste, which is the
    contract this file keeps for every dialect it prints.
    """
    module = doctor_module(REPO)
    used = (root / "scripts" / "validate-manifest.py" if own_copy
            else shape / VALIDATOR_TEMPLATE)
    assert module.validator_command(shape, used, own_copy,
                                    ["--root", root], platform) == expected


def test_the_posix_validator_line_is_read_back_whole_by_sh_quoting():
    """A standard at an awkward path arrives as one value, apostrophe and all.

    `shlex.split` is the reader's own shell for the `sh` dialect, as it is
    for every other line asserted that way here: the first word is `env`
    (#277), the next the assignment whole, the next the interpreter, the
    next the template.
    """
    module = doctor_module(REPO)
    shape = PurePosixPath("/srv/Jane O'Neill/open Repo Shape")
    line = module.validator_command(
        shape, shape / VALIDATOR_TEMPLATE, False,
        ["--root", PurePosixPath("/srv/work dir/Atlas")], "posix")
    assert shlex.split(line) == [
        "env",
        "PYTHONPATH=/srv/Jane O'Neill/open Repo Shape/scripts", "python3",
        f"/srv/Jane O'Neill/open Repo Shape/{VALIDATOR_TEMPLATE}", "--root",
        "/srv/work dir/Atlas"], line


def test_the_validator_line_asked_for_no_platform_is_this_hosts():
    """`platform=None` is `os.name`, so the line every real run prints is the
    one the rows above assert, byte for byte, on whichever host runs it."""
    module = doctor_module(REPO)
    shape = WINDOWS_SHAPE
    host = "nt" if os.name == "nt" else "posix"
    args = ["--root", PureWindowsPath(r"C:\work\Atlas")]
    template = shape / VALIDATOR_TEMPLATE
    assert module.validator_command(shape, template, False, args) == \
        module.validator_command(shape, template, False, args, host)
    assert module.validator_command(shape, template, True, args) == \
        module.validator_command(shape, template, True, args, host)


def test_the_quoter_can_be_made_to_quote_a_value_it_would_leave_bare():
    """`always` exists for the right-hand side of a PowerShell assignment, and
    changes nothing for any caller that does not pass it."""
    module = doctor_module(REPO)
    for platform in ("posix", "nt"):
        assert module.quote_arg("scripts", platform) == "scripts"
        assert module.quote_arg("scripts", platform, always=True) == \
            "'scripts'"
        assert module.quote_arg("it's", platform, always=True) == (
            "'it''s'" if platform == "nt" else "'it'\\''s'")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")
def test_a_template_validators_next_command_runs_from_an_awkward_standard(
        standard, project, tmp_path):
    """The assignment prefix, in front of a path `sh` has to be told about.

    The whole standard is COPIED to a directory with a space and an
    apostrophe in it and the doctor is run from there, so the line has the
    awkward path twice: in `PYTHONPATH=...` and in the template's own. An
    unquoted one is not a line `sh` will parse; a quoted interpreter and an
    unquoted assignment would be the other half of the same fault.
    """
    here = tmp_path / AWKWARD / "openRepoShape"
    here.parent.mkdir()
    shutil.copytree(standard, here, symlinks=True)
    spec = TEMPLATE_FALLBACK["manifest"]
    root = red_root("manifest", project, {}, tmp_path)
    row = rows_of(doctor(here, root, "--json"))["manifest"]
    assert row["status"] == "FINDING", row
    assert row["detail"]["own_copy"] is False, row
    assert Path(row["detail"]["validator"]).resolve() == \
        (here / spec["template"]).resolve(), row
    # The apostrophe is closed, escaped and reopened -- in BOTH paths.
    assert row["next"].count("ct'\\''or") == 2, row["next"]
    pasted = pasted_from_elsewhere(row["next"], tmp_path)
    whole = pasted.stdout + pasted.stderr
    assert pasted.returncode == 1, whole
    assert f"FINDING {spec['finding']}" in whole, whole
    for crash in ("Traceback", "ModuleNotFoundError", "unexpected EOF"):
        assert crash not in whole, (crash, whole)


@pytest.fixture
def curly_project(scaffolded_here, tmp_path) -> Path:
    """The fixture project, at a path with a CURLY apostrophe in it.

    Same shape as `awkward_project` and for the same reason -- a COPY, not a
    scaffold, so a submodule's `.git` file's relative path into
    `../.git/modules/<name>` still resolves (see `tests/conftest.py`) -- but
    a different character: `ascii_text` maps `'` to `'`, which is exactly
    what made this the value that reached `next_command` unconverted
    (Copilot, PR #102).
    """
    target = tmp_path / CURLY_APOSTROPHE / PROJECT
    target.parent.mkdir(parents=True)
    shutil.copytree(scaffolded_here["clone"], target, symlinks=True)
    return target


def test_a_curly_apostrophe_in_the_root_survives_the_real_report(
        standard, curly_project):
    """The bug lived in `Row.__init__`, on the far side of `quote_arg`.

    Proving `quote_arg` correct in isolation proves nothing about what a
    caller then PRINTS: `Row.__init__` ascii-normalizes the WHOLE assembled
    `next_command` a second time, after every value in it is already
    quoted. So this goes through a real report, and the claim is the
    strongest one available: whatever a row prints for `--root` is exactly
    what `quote_arg` itself returns for this path, not that string with its
    apostrophe knocked bare a second time (Copilot, PR #102).
    """
    edited = curly_project / DRIFT_TARGET
    edited.write_text(edited.read_text(encoding="utf-8") + "\n# an edit\n",
                      encoding="utf-8")
    row = rows_of(doctor(standard, curly_project,
                        "--json"))["shape-currency"]
    assert row["status"] == "FINDING", row
    here = "nt" if os.name == "nt" else "posix"
    quoted_root = doctor_module(standard).quote_arg(curly_project, here)
    assert quoted_root in row["next"], row["next"]


# --- the README's `Shape:` line, as a note (#148) ---------------------------
#
# A holder's README is rendered with the commit it was cut from and nothing
# moved it afterwards, so InkRouter's read `6fe09a41535a` four re-pins after
# the pin had moved. The doctor now READS that line — and says so as a
# `note`, because the authority on what revision a root is a copy of is
# `contracts/shape-pin.yaml`, and prose that has fallen behind it is a
# difference worth a reader's eye rather than a verdict about the repository.


def give_readme(root, *lines: str):
    """Append Shape: lines to this root's README, COMMITTED.

    Committed because that is what a holder's README is -- the line lands in
    the scaffold's own commit -- and because `update-shape.py` refuses to
    carry a README that has changes of its own (Copilot, PR #152), which the
    doctor reads through the same classifier: an uncommitted line is one
    `apply` would not move, and therefore one this row says nothing about.
    """
    readme = root / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n"
                      + "".join(line + "\n" for line in lines),
                      encoding="utf-8")
    commit_all(root, "The README names the shape it was cut from")
    return readme


def test_a_readme_naming_another_commit_is_a_note_and_not_a_verdict(
        standard, project):
    """COMPLIANT, exit 0, and the difference said out loud.

    The row that would otherwise read `ok` reads `note` instead, which is
    the same posture `leg shape files` takes: `verdict_for` steps over a note,
    so a sentence cannot fail a repository whose every pin is current — and a
    reader scanning the status column still sees that something is off.
    """
    give_readme(project, rendered_shape_line("0" * 40))
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "COMPLIANT"
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "note", row
    assert "README.md's Shape: line names 000000000000" in row["reason"]
    assert "`apply` owns that line" in row["reason"]
    assert row["detail"]["readme_shape_line"]["names"] == "0" * 40
    assert row["detail"]["readme_shape_line"]["pin"] == row["detail"]["pinned"]
    assert row["next"] is None, (
        "a note about prose offers no command: `apply` carries the line with "
        "the next re-pin, and there is nothing here for a human to run")


def test_a_readme_naming_the_pin_itself_says_nothing_at_all(standard,
                                                            project):
    """The holder case that is WELL, and the one every re-pin now leaves
    behind: a note that fired whenever a README mentioned a commit would be
    noise nobody could clear."""
    pinned = git("rev-parse", "HEAD", cwd=standard).stdout.strip()
    give_readme(project, rendered_shape_line(pinned))
    row = rows_of(doctor(standard, project, "--json"))["shape-currency"]
    assert row["status"] == "ok", row
    assert "note:" not in row["reason"], row
    assert "readme_shape_line" not in row["detail"]


@pytest.mark.parametrize("lines", [
    # Another standard's revision, in the same form: this doctor pins one
    # repository and knows nothing about that one.
    ["octo/Elsewhere"],
    # Two of them: `apply` will not choose between a project's own
    # sentences, so a note asking for a rewrite nothing performs would be a
    # chore with no exit.
    [None, None],
])
def test_a_line_apply_would_not_rewrite_draws_no_note(standard, project,
                                                      lines):
    """THE NOTE AND THE REWRITE ANSWER THE SAME QUESTION. Every reading the
    tool leaves alone is one the doctor stays quiet about, or the report
    would be asking for something no command does."""
    give_readme(project, *[rendered_shape_line("0" * 40, repository=name)
                           if name else rendered_shape_line("0" * 40)
                           for name in lines])
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "ok", row
    assert "note:" not in row["reason"], row
    assert "readme_shape_line" not in row["detail"]


def test_a_behind_project_whose_readme_names_its_own_pin_draws_no_note(
        advanced_standard, project):
    """THE COMPARISON IS AGAINST THE PIN, NOT THIS STANDARD'S HEAD.

    `contracts/shape-pin.yaml` is the authority on what revision this root is
    a copy of, so a README naming it is RIGHT — the repository is merely
    behind, which the row's own verdict already says. Comparing the line
    against the target instead would put a note on every behind project in
    the estate, and a note that fires on a correct file is one nobody can
    clear (Copilot, PR #152).
    """
    before = rows_of(doctor(advanced_standard, project, "--json"))
    pinned = before["shape-currency"]["detail"]["pinned"]
    assert pinned != before["shape-currency"]["detail"]["standard"], (
        "fixture: the standard has moved past this project's pin")

    give_readme(project, rendered_shape_line(pinned))
    result = doctor(advanced_standard, project, "--json")
    assert result.returncode == 1, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "FINDING", row
    assert "note:" not in row["reason"], row
    assert "readme_shape_line" not in row["detail"]
    assert json.loads(result.stdout)["verdict"].startswith(
        "COMPLIANT, SHAPE BEHIND"), result.stdout


def test_an_uncommitted_readme_line_is_nobodys_to_note(standard, project):
    """THE NOTE AND THE REWRITE ANSWER THE SAME QUESTION, and `apply` will
    not carry a README that has changes of its own — committing somebody's
    half-written paragraph into a shape re-pin is the sweep the tool's
    explicit pathspecs exist to prevent. So a line that is behind in a file
    nobody has committed draws no note either."""
    readme = project / "README.md"
    readme.write_text(readme.read_text(encoding="utf-8") + "\n"
                      + rendered_shape_line("0" * 40) + "\n",
                      encoding="utf-8")
    result = doctor(standard, project, "--json")
    assert result.returncode == 0, result.stdout + result.stderr
    row = rows_of(result)["shape-currency"]
    assert row["status"] == "ok", row
    assert "readme_shape_line" not in row["detail"]


def test_the_pin_alone_clause_and_the_readme_note_never_say_opposite_things(
        standard, project, tmp_path):
    """THE ROW AND ITS NOTE ARE PRINTED AS ONE SENTENCE, so they have to
    agree (#158).

    `readme_shape_note` is appended to the `behind_pin_only` reason
    unconditionally, and that reason used to promise "`apply` would move the
    pin alone" whatever the note said next — a line claiming in one clause
    that the pin moves by itself and in the next that the README moves with
    it. `update-shape.py check` carried the same defect and baa77d0 took it
    out; the doctor's copy of the wording was missed.

    THE CLAUSE IS SETTLED AGAINST THE TARGET, NOT AGAINST THE NOTE, because
    the two questions have different answers in both directions. A README
    naming its own pin — the commonest holder re-pin of all — draws NO note
    and is rewritten anyway; a README that has run ahead to the commit this
    re-pin is about to record draws one and is left alone. Reading an empty
    note as "the README stays put" would have kept the false promise in
    precisely the case it is made most often.
    """
    pinned = git("rev-parse", "HEAD", cwd=standard).stdout.strip()
    ahead = standard_ahead(standard, tmp_path)
    target = git("rev-parse", "HEAD", cwd=ahead).stdout.strip()
    assert pinned != target, "fixture: the standard has moved past the pin"

    readme = project / "README.md"
    scaffolded = readme.read_text(encoding="utf-8")

    readme.write_text(scaffolded + "\n" + rendered_shape_line(pinned) + "\n",
                      encoding="utf-8")
    commit_all(project, "The README names the shape it was cut from")
    row = rows_of(doctor(ahead, project, "--json"))["shape-currency"]
    assert row["detail"]["behind_pin_only"] is True, row
    assert "note:" not in row["reason"], row
    assert "`apply` would move the pin and README.md's Shape: line" \
        in row["reason"], row

    readme.write_text(scaffolded + "\n" + rendered_shape_line(target) + "\n",
                      encoding="utf-8")
    commit_all(project, "The README runs ahead of the pin")
    row = rows_of(doctor(ahead, project, "--json"))["shape-currency"]
    assert row["detail"]["behind_pin_only"] is True, row
    assert "note:" in row["reason"], row
    assert "`apply` would move the pin alone" in row["reason"], row
