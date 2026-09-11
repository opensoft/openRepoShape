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
                         "agent-files", "machine"}
    for name, row in rows.items():
        assert row["status"] in ("ok", "n/a"), (name, row)
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
                         "agent-files", "members", "machine"}
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
    """
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    shutil.copy2(REPO / DOCTOR, lonely / DOCTOR)
    (lonely / "scripts").mkdir()
    shutil.copy2(REPO / "scripts" / "repo_shape.py",
                 lonely / "scripts" / "repo_shape.py")
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
    assert row["status"] == "FINDING"
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
