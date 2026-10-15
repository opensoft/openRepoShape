# SPDX-License-Identifier: Apache-2.0
"""`.github/workflows/release.yml`: what keeps the release safe (#563).

OFFLINE. The workflow uploads to TestPyPI and PyPI, and nothing here runs
it. What can be checked with no network is the file itself, read with
`repo_shape.load_yaml`, the fail-closed reader for the YAML subset every
file of this standard is written in, so a construct outside that subset
fails here first. And one of its scripts is RUN: the step that writes the
stamp, against the committed `src/openreposhape/_release.py`, and the file
it writes is read back through the package's own `standard.read_stamp`.

The properties, each a test below: a dispatch is the only trigger; only
the two upload jobs can mint an identity token, each in its own
environment and on a `v*` tag alone; every action is pinned by a full
commit; the build refuses a tag that is not `v<version>`, annotated, at the
run's commit, and a commit without passing `tests`, `tests-macos` and
`tests-windows`; and every tool the release installs comes from a hash
lock, by digest.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO
from repo_shape import load_yaml

WORKFLOWS = REPO / ".github" / "workflows"
WORKFLOW = WORKFLOWS / "release.yml"
BUILD_LOCK = REPO / ".github" / "release-build-requirements.txt"
PIPX_LOCK = REPO / ".github" / "release-pipx-requirements.txt"
STAMP = REPO / "src" / "openreposhape" / "_release.py"

#: Each upload job, and the one environment it deploys to.
UPLOADS = {"testpypi": "testpypi", "pypi": "pypi"}

#: The three-OS gate this repository lands by: `tests.yml`'s three jobs.
GATE = ("tests", "tests-macos", "tests-windows")

#: The guard on both upload jobs: a `v*` tag, nothing else.
ON_A_V_TAG = "startsWith(github.ref, 'refs/tags/v')"

#: `owner/repository[/path]@<40 hex>`: an action pinned by a full commit.
COMMIT_PIN = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+@[0-9a-f]{40}")

#: A `uses:` line as written: the reference, then its release tag as a
#: comment, the way `tests.yml` writes every one.
USES_LINE = re.compile(r"^\s*(?:- )?uses:\s*(\S+)(.*)$")

#: The release a stamp test writes, and the shapes of its commit and digest.
RELEASE = {"VERSION": "1.1.0", "TAG": "v1.1.0", "COMMIT": "a" * 40,
           "DIGEST": "b" * 64}


@pytest.fixture(scope="module")
def workflow() -> dict:
    return load_yaml(WORKFLOW)


def job_steps(workflow: dict, job: str) -> list:
    return workflow["jobs"][job]["steps"]


def named_step(workflow: dict, job: str, prefix: str) -> dict:
    """The one step of `job` whose name starts with `prefix`."""
    [found] = [step for step in job_steps(workflow, job)
               if step.get("name", "").startswith(prefix)]
    return found


def heredoc(script: str) -> str:
    """The Python a `run:` script hands to `python3 ... <<'PY'`."""
    lines = script.splitlines()
    [start] = [at for at, line in enumerate(lines)
               if line.rstrip().endswith("<<'PY'")]
    return "\n".join(lines[start + 1:lines.index("PY", start)]) + "\n"


def lock_entries(path: Path) -> dict:
    """`name==version ; marker` -> its sha256 digests, from a hash lock;
    continuation lines joined, comment lines dropped."""
    text = "\n".join(line for line in path.read_text(encoding="utf-8")
                     .splitlines() if not line.lstrip().startswith("#"))
    entries = {}
    for entry in re.sub(r"\\\n", " ", text).splitlines():
        if entry.strip():
            requirement = entry.split("--hash=")[0].strip()
            entries[requirement] = re.findall(r"--hash=sha256:(\S+)", entry)
    return entries


# --- the trigger and the token -------------------------------------------------

def test_a_dispatch_with_a_version_is_the_only_trigger(workflow):
    """Nothing runs on a push, a tag or a pull request: an upload is an act
    Brett Heap approves. Nothing is granted by default, and a running
    release is never cancelled halfway."""
    assert list(workflow["on"]) == ["workflow_dispatch"]
    inputs = workflow["on"]["workflow_dispatch"]["inputs"]
    assert list(inputs) == ["version"]
    assert inputs["version"]["required"] is True
    assert inputs["version"]["type"] == "string"
    assert workflow["permissions"] == {}
    assert workflow["concurrency"]["cancel-in-progress"] is False


def test_only_the_two_upload_jobs_can_mint_an_identity_token(workflow):
    """`id-token: write` is trusted publishing's OIDC grant, on the two
    upload jobs and on no other. Every job states its own permissions, and
    every other grant reads."""
    jobs = workflow["jobs"]
    assert set(jobs) == {"build", "testpypi", "install", "pypi"}
    assert "id-token" not in workflow["permissions"]
    minting = set()
    for name, job in jobs.items():
        granted = job.get("permissions")
        assert isinstance(granted, dict), name
        if "id-token" in granted:
            minting.add(name)
            assert granted["id-token"] == "write", name
        others = {scope: level for scope, level in granted.items()
                  if scope != "id-token"}
        assert set(others.values()) <= {"read"}, (name, others)
    assert minting == set(UPLOADS)


def test_each_upload_runs_in_its_own_environment_on_a_v_tag_alone(workflow):
    """`testpypi` and `pypi`, each the environment Brett Heap limits to the
    tags `v*`, and each job guarded by a `v*` tag besides. No other job
    names an environment, and PyPI waits for TestPyPI and every leg of the
    install check."""
    for name, job in workflow["jobs"].items():
        if name in UPLOADS:
            assert job["environment"]["name"] == UPLOADS[name]
            assert job["if"] == ON_A_V_TAG
        else:
            assert "environment" not in job, name
    assert workflow["jobs"]["testpypi"]["needs"] == "build"
    assert workflow["jobs"]["pypi"]["needs"] == ["build", "testpypi",
                                                 "install"]


def test_a_branch_dispatch_rehearses_and_both_environments_admit_v_tags_alone(
        workflow):
    """A branch is the rehearsal: the install check runs over the build's
    own wheel when the testpypi job is skipped on a branch, never when it
    failed. The build job refuses unless both environments' deployment
    limit is the one rule, the tags `v*`, and each upload job reads that
    and this run's approval again at use time."""
    guard = workflow["jobs"]["install"]["if"]
    assert "needs.testpypi.result == 'success'" in guard
    assert ("needs.testpypi.result == 'skipped' && "
            "!startsWith(github.ref, 'refs/tags/')") in guard
    limit = "[(\"tag\", \"v*\")]"
    build = named_step(workflow, "build", "both environments")
    assert 'for environment in ("testpypi", "pypi")' in build["run"]
    assert f"rules != {limit}" in build["run"]
    for job in UPLOADS:
        at_use = named_step(workflow, job, "this environment still")
        assert at_use["env"]["ENVIRONMENT"] == UPLOADS[job]
        assert f"rules != {limit}" in at_use["run"]
        assert "/approvals" in at_use["run"]


# --- what the workflow runs ----------------------------------------------------

def test_every_action_is_pinned_by_a_full_commit(workflow):
    """A tag can be moved after review and a commit cannot, which matters
    most in the one workflow whose output is published. Each `uses:` line
    carries its release tag as a comment, and checkout and setup-python sit
    at the commits `tests.yml` pins them to."""
    parsed = [step["uses"] for job in workflow["jobs"].values()
              for step in job["steps"] if "uses" in step]
    written = [USES_LINE.match(line) for line in
               WORKFLOW.read_text(encoding="utf-8").splitlines()]
    written = [found for found in written if found]
    assert sorted(found.group(1) for found in written) == sorted(parsed)
    for found in written:
        assert COMMIT_PIN.fullmatch(found.group(1)), found.group(0)
        assert re.fullmatch(r"\s+# v\S+", found.group(2)), found.group(0)
    tests = load_yaml(WORKFLOWS / "tests.yml")
    pinned = {step["uses"] for job in tests["jobs"].values()
              for step in job["steps"] if "uses" in step}
    for action in ("actions/checkout@", "actions/setup-python@"):
        here = {ref for ref in parsed if ref.startswith(action)}
        assert here, action
        assert here == {ref for ref in pinned if ref.startswith(action)}


def test_the_build_refuses_a_tag_that_is_not_the_annotated_v_version_at_this_commit(
        workflow):
    """On a tag, the ref must be `refs/tags/v<version>`, and the forge's
    tag must be an annotated tag object naming this run's commit; git's own
    copy of it must agree. Any other ref but a branch refuses."""
    script = named_step(workflow, "build", "the dispatched ref")["run"]
    assert '"refs/tags/$tag") ;;' in script
    assert "refs/heads/*)" in script
    assert 'git/ref/tags/$tag' in script
    assert "select(.object.type == \"tag\")" in script
    assert '[ "$commit" != "$GITHUB_SHA" ]' in script
    assert 'git cat-file -t "refs/tags/$tag"' in script
    version = named_step(workflow, "build", "the version is")["run"]
    assert ("^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$"
            in version)
    for job in UPLOADS:
        again = named_step(workflow, job, "the tag v<version> still")["run"]
        assert '[ "$commit" != "$GITHUB_SHA" ]' in again


def test_the_build_refuses_a_commit_without_the_three_os_checks(workflow):
    """`tests`, `tests-macos` and `tests-windows` must have passed on the
    commit itself, run by `tests.yml`, whose three jobs those are (a check
    run is named after its job, and none of the three renames itself)."""
    build = workflow["jobs"]["build"]
    assert build["permissions"]["checks"] == "read"
    script = named_step(workflow, "build", "the commit carries")["run"]
    gate = ", ".join(f'"{name}"' for name in GATE)
    assert (f'gate, workflow = ({gate}), ".github/workflows/tests.yml"'
            in heredoc(script))
    assert "check-runs" in script
    assert "check_suite_id" in script
    tests = load_yaml(WORKFLOWS / "tests.yml")
    for name in GATE:
        assert name in tests["jobs"], name
        assert "name" not in tests["jobs"][name], name


def test_the_digest_is_the_checkouts_own_and_the_forges(workflow):
    """The stamp's digest comes from the checkout's own
    `scripts/repo_shape.py` and must equal the forge's reading of the same
    commit, after the checkout is shown clean."""
    names = [step.get("name", "") for step in job_steps(workflow, "build")]
    clean = names.index("the checkout is this commit, and clean")
    digest = names.index("the commit's tree digest is the forge's")
    assert clean < digest
    script = heredoc(named_step(workflow, "build", "the commit's tree")["run"])
    assert 'sys.path[:0] = [str(here / "scripts"), str(here / "src")]' \
        in script
    assert "repo_shape.tree_digest(here, sha)" in script
    assert "repo_shape.tree_digest_from_gh(repo, sha)" in script


# --- the tools, by digest -------------------------------------------------------

@pytest.mark.parametrize("job, prefix, lock", [
    ("build", "install the release tools", BUILD_LOCK),
    ("install", "pipx installs", PIPX_LOCK),
])
def test_every_tool_the_release_installs_comes_from_a_hash_lock(
        workflow, job, prefix, lock):
    """`--require-hashes`, wheels only, from a lock in which every
    requirement is pinned to one version and named by its sha256."""
    script = named_step(workflow, job, prefix)["run"]
    relative = lock.relative_to(REPO).as_posix()
    assert re.search(r"--only-binary :all: --require-hashes \\\n\s+-r "
                     + re.escape(relative), script), script
    entries = lock_entries(lock)
    assert entries
    for requirement, digests in entries.items():
        assert re.fullmatch(r"[a-z0-9-]+==[0-9][0-9A-Za-z.]*( ; .+)?",
                            requirement), requirement
        assert digests, requirement
        for digest in digests:
            assert re.fullmatch(r"[0-9a-f]{64}", digest), requirement


def test_the_build_lock_holds_hatchling_at_its_pin_and_its_requirements():
    """RV590, SHOULD 6: `pyproject.toml` pins hatchling alone, so the lock
    names hatchling at that same pin, and each of its own requirements, and
    the `build` frontend the release runs it with."""
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    [backend] = data["build-system"]["requires"]
    names = {requirement.split("==")[0]: requirement.split(" ;")[0]
             for requirement in lock_entries(BUILD_LOCK)}
    assert names["hatchling"] == backend
    for name in ("packaging", "pathspec", "pluggy", "trove-classifiers",
                 "tomli", "build"):
        assert name in names, name
    assert "pipx" in {requirement.split("==")[0]
                      for requirement in lock_entries(PIPX_LOCK)}


def test_the_wheel_is_built_twice_from_two_extractions_and_compared(workflow):
    """A wheel only, from two `git archive` extractions of the commit in
    two directories, at the commit's own time, with the locked backend;
    the two must be one file before anything else reads them."""
    extract = named_step(workflow, "build", "extract the commit twice")["run"]
    assert extract.count("git archive") == 1
    assert 'for tree in "$tree_a" "$tree_b"; do' in extract
    build = named_step(workflow, "build", "build the wheel")["run"]
    assert 'SOURCE_DATE_EPOCH="$(git log -1 --format=%ct "$GITHUB_SHA")"' \
        in build
    assert "-m build --wheel --no-isolation" in build
    assert "--sdist" not in build
    assert 'cmp "$RUNNER_TEMP/dist-a/$wheel" "$RUNNER_TEMP/dist-b/$wheel"' \
        in build


# --- the stamp, written and read back --------------------------------------------

def write_stamp(workflow: dict, tmp_path: Path, release: dict):
    """The stamp step's own script, run as the workflow runs it over two
    copies of the committed `_release.py`."""
    script = tmp_path / "stamp.py"
    script.write_text(heredoc(named_step(
        workflow, "build", "write the stamp")["run"]), encoding="utf-8")
    copies = [tmp_path / side / "_release.py" for side in ("a", "b")]
    for copy in copies:
        copy.parent.mkdir()
        copy.write_bytes(STAMP.read_bytes())
    env = {**os.environ, "VERSION": release["VERSION"],
           "GITHUB_SHA": release["COMMIT"], "DIGEST": release["DIGEST"]}
    done = subprocess.run([sys.executable, "-I", str(script),
                           *map(str, copies)], env=env, capture_output=True,
                          text=True, check=False)
    return done, copies


def test_the_stamp_the_workflow_writes_is_one_the_package_reads(
        workflow, tmp_path, monkeypatch):
    """Both copies carry the release's four values, hatchling finds the
    version in it the way it reads the committed one, and every other line
    is the committed file's."""
    done, copies = write_stamp(workflow, tmp_path, RELEASE)
    assert done.returncode == 0, done.stderr
    monkeypatch.syspath_prepend(str(REPO / "src"))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    standard = importlib.import_module("openreposhape.standard")
    committed = STAMP.read_text(encoding="utf-8").splitlines()
    for copy in copies:
        spec = importlib.util.spec_from_file_location(
            f"stamped_{copy.parent.name}", copy)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        stamp = standard.read_stamp(module)
        assert stamp.stamped
        assert (stamp.version, stamp.tag, stamp.commit, stamp.digest) == (
            RELEASE["VERSION"], RELEASE["TAG"], RELEASE["COMMIT"],
            RELEASE["DIGEST"])
        text = copy.read_text(encoding="utf-8")
        found = re.search(r"(?i)^(__version__|VERSION) *= *(['\"])v?"
                          r"(?P<version>.+?)\2", text, re.M)
        assert found.group("version") == RELEASE["VERSION"]
        changed = [(old, new) for old, new in
                   zip(committed, text.splitlines()) if old != new]
        assert len(text.splitlines()) == len(committed)
        assert sorted(new for _, new in changed) == sorted(
            f'{name} = "{value}"' for name, value in RELEASE.items())


@pytest.mark.parametrize("changed", [
    {"VERSION": "0.0.0"},
    {"VERSION": "1.1"},
    {"VERSION": "1.1.0rc1"},
    {"COMMIT": "A" * 40},
    {"DIGEST": "b" * 63},
])
def test_the_stamp_step_refuses_a_value_no_release_carries(
        workflow, tmp_path, changed):
    """The unstamped 0.0.0, a version that is not X.Y.Z, and a commit or a
    digest of the wrong shape are each refused, and nothing is written."""
    done, copies = write_stamp(workflow, tmp_path, {**RELEASE, **changed})
    assert done.returncode != 0
    for copy in copies:
        assert copy.read_bytes() == STAMP.read_bytes()


def test_the_stamp_step_refuses_a_file_already_stamped(workflow, tmp_path):
    """It stamps the committed, unstamped file and nothing else: a second
    run over its own output finds no `VERSION = "0.0.0"` to replace."""
    done, copies = write_stamp(workflow, tmp_path, RELEASE)
    assert done.returncode == 0, done.stderr
    stamped = copies[0].read_bytes()
    script = tmp_path / "stamp.py"
    env = {**os.environ, "VERSION": "1.1.1", "GITHUB_SHA": RELEASE["COMMIT"],
           "DIGEST": RELEASE["DIGEST"]}
    again = subprocess.run([sys.executable, "-I", str(script),
                            str(copies[0])], env=env, capture_output=True,
                           text=True, check=False)
    assert again.returncode != 0
    assert copies[0].read_bytes() == stamped


# --- the install check ------------------------------------------------------------

def test_the_install_check_runs_on_three_systems_and_python_3_9(workflow):
    """ubuntu, macOS and Windows, and the oldest Python the package
    supports; every pip it runs reads PyPI alone, so git-filter-repo never
    comes from TestPyPI, and TestPyPI's wheel is taken from its own file
    host by the recorded digest."""
    install = workflow["jobs"]["install"]
    legs = install["strategy"]["matrix"]["include"]
    assert {leg["os"] for leg in legs} == {"ubuntu-latest", "macos-latest",
                                            "windows-latest"}
    assert {"os": "ubuntu-latest", "python": "3.9"} in legs
    assert install["strategy"]["fail-fast"] is False
    assert install["env"]["PIP_INDEX_URL"] == "https://pypi.org/simple/"
    for step in install["steps"]:
        assert "--index-url" not in step.get("run", ""), step.get("name")
        assert "--extra-index-url" not in step.get("run", ""), step.get("name")
    fetch = named_step(workflow, "install", "fetch the wheel from TestPyPI")
    assert 'parts.hostname != "test-files.pythonhosted.org"' in fetch["run"]
    names = [step.get("name", "") for step in install["steps"]]
    verified = names.index("the wheel is the one the build job verified")
    assert verified < names.index(
        "pipx installs the wheel into a fresh environment, its dependency "
        "from PyPI")


def test_the_header_says_how_to_release(workflow):
    """No `docs/release-notes/v1.1.0.md` exists yet, so the header carries
    the steps the docs pull request will point at."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "# RELEASING TO PyPI." in text
    assert "gh workflow run release.yml --ref v<version> -f version=<version>" \
        in text
    assert "# A DISPATCH ON A BRANCH IS THE REHEARSAL, AND IT CANNOT DEPLOY." \
        in text
