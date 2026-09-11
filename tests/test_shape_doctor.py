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
import shutil
import subprocess

from pathlib import Path

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
    assert "setup.sh" in rows["way-in"]["next"]
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
    assert row["detail"]["counts"] == {"misplaced": 2, "review_required": 0}
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
    assert "not one the path policy classifies" in legs["prose"]["state"]
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
