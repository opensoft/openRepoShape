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
repositories on disk as origins), and the two shim tests put a `gh` and a
`curl` on `$PATH` that refuse loudly, so a run that tried to fetch would fail
rather than quietly succeed against github.com.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess

from pathlib import Path, PurePosixPath, PureWindowsPath

import pytest

from conftest import (FILE_PROTOCOL, REPO, WINDOWS_SKIP, git, rmtree,
                      run_script)

DOCTOR = "shape-doctor.py"
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
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(base / "remotes" / f"{PROJECT}.git"), str(clones / PROJECT)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return {"base": base, "clone": clones / PROJECT}


@pytest.fixture
def project(scaffolded_here, tmp_path) -> Path:
    """A private, mutable copy of that clone."""
    target = tmp_path / PROJECT
    shutil.copytree(scaffolded_here["clone"], target, symlinks=True)
    return target


def doctor(standard: Path, root, *args) -> subprocess.CompletedProcess:
    return run_script(standard / DOCTOR, "--root", str(root), *args)


def rows_of(result) -> dict:
    """`{id: row}` from a `--json` run, so a test names a row rather than a
    line number of a table that is free to be re-laid-out."""
    payload = json.loads(result.stdout)
    return {row["id"]: row for row in payload["rows"]}


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
                            "detail"}
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
    assert f"--accept-local {DRIFT_TARGET}" in result.stdout, (
        "a `locally-modified` row must hand over the exact flag that re-pins "
        "it, which is the one AGENTS.md says never to pass on your own "
        "initiative")
    # The pins row is red too, and is still printed with its own next step.
    rows = rows_of(doctor(standard, project, "--json"))
    assert rows["pins"]["status"] == "FINDING", rows["pins"]
    assert rows["shape-currency"]["detail"]["drifted"] is True
    assert rows["shape-currency"]["detail"]["paths"]["locally-modified"] == \
        [DRIFT_TARGET]


# --- the standard has moved on ---------------------------------------------

@pytest.fixture
def advanced_standard(standard, tmp_path) -> Path:
    """A COPY of the standard with one more commit on a copied template.

    A copy rather than a commit on the session-scoped fixture: every other
    test in this file is a claim about a project that is compliant with
    `standard`, and advancing it in place would make them all say `SHAPE
    BEHIND` depending on the order they ran in.
    """
    ahead = tmp_path / "standard-ahead"
    shutil.copytree(standard, ahead, symlinks=True)
    target = ahead / UPSTREAM_TARGET
    target.write_text(target.read_text(encoding="utf-8")
                      + "\n# an upstream fix, after this project was cut\n",
                      encoding="utf-8")
    commit_all(ahead, "An upstream fix to a copied file")
    return ahead


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

def test_a_leg_off_its_pin_is_a_finding_that_names_bootstrap(standard,
                                                             project):
    """A commit made INSIDE a mount, which is how a leg walks off its pin.

    The gitlink in the superproject's index is untouched, so
    `validate-pins.py` is still green — it reads what the next commit would
    RECORD — and the only thing that can notice is a tool that looks at the
    mount's HEAD. That is this row, and its exit is `make bootstrap`, which
    puts the leg back on its tracking branch AT the pin.
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
    assert "bootstrap.py" in result.stdout, (
        "the row must name what `make bootstrap` runs")
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
    assert "bootstrap" in (rows["legs"]["next"] or "")


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
    added = run_script(standard / "scripts" / "family.py", "add",
                       "--family-root", str(root),
                       "--member", f"{FAMILY_NAME}/{FAMILY_MEMBER}",
                       "--local-remote-dir", str(base / "remotes"))
    assert added.returncode == 0, added.stderr + added.stdout
    return {"base": base, "root": root}


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
    assert set(rows) == {"naming", "contents", "way-in", "machine"}
    assert "placement" not in rows, (
        "there are no legs here and no manifest declaring any, so there is "
        "no placement question to answer; the row is absent rather than n/a")
    assert "adopt-project.py plan" in rows["way-in"]["next"]
    assert rows["contents"]["detail"]["project_yaml"] is False


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
    assert "without --yes" in rows["way-in"]["next"]
    assert rows["way-in"]["detail"]["git_repository"] is False
    assert "an ordinary directory" in rows["contents"]["reason"]


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
    """A `$PATH` whose `gh` and `curl` fail loudly if anything calls them."""
    fake = tmp_path / "no-network"
    fake.mkdir(exist_ok=True)
    for name in ("gh", "curl"):
        script = fake / name
        script.write_text(
            "#!/bin/sh\n"
            f"printf 'fake {name}: no test here may reach the network\\n' >&2\n"
            "exit 1\n", encoding="utf-8")
        script.chmod(0o755)
    return {"PATH": f"{fake}{os.pathsep}{os.environ['PATH']}"}


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
    refuse — so a shim that reached for the network would fail this test
    rather than pass it slowly.
    """
    result = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor", str(project)],
        capture_output=True, text=True, check=False, input="",
        env=shim_env(tmp_path))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLIANT   (exit 0)" in result.stdout
    assert f"standard    {standard}" in result.stdout, (
        "the checkout beside the file is the standard it must use")
    assert "no test here may reach the network" not in result.stderr


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
    """
    result = subprocess.run(
        ["bash", "-s", "--", "--doctor", str(project)],
        capture_output=True, text=True, check=False,
        input=(REPO / "openRepoShape").read_text(encoding="utf-8"),
        cwd=str(tmp_path),
        env=shim_env(tmp_path, OPENREPOSHAPE_REPO=str(standard)))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COMPLIANT   (exit 0)" in result.stdout
    [reported] = [line.split(None, 1)[1].strip()
                  for line in result.stdout.splitlines()
                  if line.startswith("standard ")]
    assert reported != str(standard), (
        "with no checkout beside it the shim must clone one, not reach for "
        "the directory the project happens to sit next to")
    assert not Path(reported).exists(), (
        f"{reported} outlived the run; the EXIT trap did not fire")


@WINDOWS_SKIP
@pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")
def test_the_shim_doctor_takes_a_path_and_nothing_else(standard, tmp_path):
    result = subprocess.run(
        ["bash", str(standard / "openRepoShape"), "--doctor", "--org", "Foo"],
        capture_output=True, text=True, check=False, input="",
        env=shim_env(tmp_path))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "--doctor takes a path and nothing else" in result.stderr
    assert "openRepoShape --preflight" in result.stderr, (
        "the refusal must name the machine check, because `--doctor` meant "
        "that until 2026-09-10")


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
        assert check.id and check.label
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
    ahead = tmp_path / "standard-ahead"
    shutil.copytree(standard, ahead, symlinks=True)
    # A file no copy list names, so nothing a project holds can differ.
    (ahead / "README.md").write_text(
        (ahead / "README.md").read_text(encoding="utf-8") + "\nA fix.\n",
        encoding="utf-8")
    commit_all(ahead, "An upstream change to a file no project copies")
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
    assert "--root" in command, row["next"]
    assert Path(command[1]).is_file(), command
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
    assert "git -C" in row["next"] and "checkout --" in row["next"], \
        row["next"]


def test_a_missing_rendered_leg_file_is_not_offered_a_cp(standard, project):
    """`templates/<role>-root/AGENTS.md` is full of `{{PLACEHOLDER}}`s.

    A `cp` of it leaves a leg holding literal `{{PROJECT_NAME}}`, which is a
    command that produces an invalid leg — worse than no command at all. The
    verbatim files still get their `cp`, which is the other half.
    """
    (project / "spec" / "AGENTS.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    assert row["status"] == "note"
    assert not row["next"].startswith("cp "), row["next"]
    assert "RENDERED" in row["next"], row["next"]

    (project / "spec" / "CLAUDE.md").unlink()
    row = rows_of(doctor(standard, project, "--json"))["leg-shape-files"]
    assert row["next"].startswith("cp "), row["next"]
    source, target = row["next"].split("#")[0].split()[1:3]
    assert Path(source).is_file(), source
    assert target.endswith("CLAUDE.md"), target


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


def test_a_real_working_clone_beside_the_holder_is_counted(standard, holder,
                                                           tmp_path):
    """And the other direction, so the check above cannot pass by refusing
    everything: the member's own tree, beside the holder, IS the clone."""
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    shutil.copytree(holder["root"] / "members" / FAMILY_MEMBER,
                    base / FAMILY_MEMBER, symlinks=True)
    row = rows_of(doctor(standard, root, "--json"))["members"]
    assert row["detail"]["without_working_clone"] == [], row
    assert row["detail"]["members"][0]["working_clone"] is not None


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
    ahead = tmp_path / "standard-ahead"
    shutil.copytree(standard, ahead, symlinks=True)
    (ahead / "README.md").write_text(
        (ahead / "README.md").read_text(encoding="utf-8") + "\nA fix.\n",
        encoding="utf-8")
    commit_all(ahead, "An upstream change to a file no project copies")
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


def test_a_pin_this_standard_cannot_resolve_is_exit_three(standard, project,
                                                          tmp_path):
    """Not a verdict about the repository: this CHECKOUT cannot answer.

    A pin naming a commit this standard does not carry — a fork, a branch
    pin, a clone made before the commit landed — used to fall through to
    `INVALID`, telling somebody their repository was wrong on the evidence
    that our copy of the standard was short a commit.
    """
    stranger = tmp_path / "stranger"
    stranger.mkdir()
    for name in ("contracts", "scripts", "templates"):
        shutil.copytree(standard / name, stranger / name, symlinks=True)
    for name in ("update-shape.py", "shape-doctor.py", "scaffold-project.py",
                 "setup-project.py", "setup.sh", "openRepoShape"):
        shutil.copy2(standard / name, stranger / name)
    git("init", "-q", "-b", "main", ".", cwd=stranger)
    commit_all(stranger, "A standard with a history of its own")
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
        assert entry["misplaced"] == 0 and entry["review_required"] == 0
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
    findings = adopt._leg_findings(plan)
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
    assert adopt._leg_findings(plan) == []


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
            "path: spec", "path: ../outside", 1), encoding="utf-8")
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
    assert scaffolds.next_command == (
        module.scaffold_command(module.SHAPE_ROOT, "Loose", os.name)
        + "   # without --yes; it asks"), scaffolds.next_command
    # The other way in, from the same directory once it is a repository.
    git("init", "-q", "-b", "main", ".", cwd=here)
    adopts = module.check_the_way_in(module.Context(here))
    assert adopts.next_command == (
        f"{module.PYTHON} "
        f"{module.quote_arg(module.SHAPE_ROOT / 'adopt-project.py', os.name)} "
        f"plan --source {module.quote_arg(here, os.name)} "
        f"--project {module.quote_arg('Loose', os.name)}"), adopts.next_command


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
