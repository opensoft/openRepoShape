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
run's commit, a commit on neither main nor its release branch, and a commit
whose own tree has not passed the `tests` job; and every tool the release
installs comes from a hash lock, by digest.
RV599's mutations each fail one of them: a condition or an early exit
added to a step, a check dropped from one upload job, a credential kept, a
`PIP_*` index added. Four steps run as scripts here: the stamp, the wheel
check over a wheel made from HEAD's own blobs, and the main-or-release-
branch check and the `tests` gate, each under a `gh` that answers as the
forge does.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import zipfile
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

#: The gate this repository lands by: `tests`, which `tests.yml` runs on
#: every trigger since #597. Named here, never read from a run, so a job
#: that goes missing is a refusal and not a smaller gate.
GATE = ("tests",)

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


def commands(script: str) -> list:
    """A `run:` script's command lines as the shell reads them: each
    continuation joined to the line it continues, comment lines dropped."""
    joined = re.sub(r"\s*\\\n\s*", " ", script)
    return [line.strip() for line in joined.splitlines()
            if line.strip() and not line.strip().startswith("#")]


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
    assert workflow["jobs"]["install"]["if"] == (
        "${{ !cancelled() && needs.build.result == 'success' && "
        "(needs.testpypi.result == 'success' || "
        "(needs.testpypi.result == 'skipped' && "
        "!startsWith(github.ref, 'refs/tags/'))) }}")
    rule = ('if policy.get("custom_branch_policies") is not True '
            'or rules != [("tag", "v*")]:')
    build = heredoc(named_step(workflow, "build", "both environments")["run"])
    assert 'for environment in ("testpypi", "pypi"):' in build
    assert rule in build
    assert "if not reviewers:" in build
    for job in UPLOADS:
        at_use = named_step(workflow, job, "this environment still")
        assert at_use["env"]["ENVIRONMENT"] == UPLOADS[job]
        assert rule in heredoc(at_use["run"])
        assert "if not reviewers:" in heredoc(at_use["run"])
        assert "if not approved:" in heredoc(at_use["run"])


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


def test_the_build_refuses_a_commit_without_a_passing_tests_job(workflow):
    """RV599, MUST 1 and MUST 2: the gate requires the `tests` job alone,
    which `tests.yml` runs on every trigger since #597. It must have passed
    in a `push` or `workflow_dispatch` run of `tests.yml`
    whose head is the commit (a `pull_request` run tests a merge, another
    tree), read from that run's own jobs, never from the commit's check
    runs, which an Actions token can create. The gate names the job; it is
    a job of `tests.yml` and does not rename itself, so its name is its
    id."""
    build = workflow["jobs"]["build"]
    assert "checks" not in build["permissions"]
    assert build["permissions"]["actions"] == "read"
    step = named_step(workflow, "build", "the commit carries")
    assert step["name"] == "the commit carries a passing tests job"
    script = heredoc(step["run"])
    assert GATE == ("tests",)
    assert 'gate, workflow = ("tests",), ".github/workflows/tests.yml"' in script
    assert ('if run.get("path") == workflow and run.get("head_sha") == sha\n'
            '        and run.get("event") in ("push", "workflow_dispatch")]'
            in script)
    assert '/jobs?filter=all&per_page=100", "jobs")' in script
    assert "check-runs" not in script
    assert "check_suite" not in script
    assert 'if newest["conclusion"] != "success":' in script
    tests = load_yaml(WORKFLOWS / "tests.yml")
    for name in GATE:
        assert name in tests["jobs"], name
        assert "name" not in tests["jobs"][name], name


#: A `gh` that answers the gate's two reads from a JSON file, as the forge
#: does through `--jq '.<key>[]'`, one object per line: the commit's runs
#: for `actions/runs?head_sha=`, and a run's jobs for `actions/runs/<id>/
#: jobs`. Each call is logged.
RUNS_GH = """\
import json, os, re, sys
args = sys.argv[1:]
with open(os.environ["GH_LOG"], "a", encoding="utf-8") as log:
    log.write(" ".join(args) + "\\n")
path = next(arg for arg in args if arg.startswith("repos/"))
with open(os.environ["GH_DATA"], encoding="utf-8") as handle:
    data = json.load(handle)
found = re.search(r"/actions/runs/([0-9]+)/jobs", path)
for row in data["jobs"].get(found.group(1), []) if found else data["runs"]:
    print(json.dumps(row))
"""

#: The commit every gate case is about.
GATE_SHA = "c" * 40


def a_run(number: int, event: str = "push", head_sha: str = GATE_SHA,
          path: str = ".github/workflows/tests.yml") -> dict:
    return {"id": number, "event": event, "head_sha": head_sha, "path": path}


def a_job(when: str = "2026-10-15T17:00:00Z", conclusion: str = "success",
          status: str = "completed", name: str = "tests") -> dict:
    return {"name": name, "status": status, "conclusion": conclusion,
            "completed_at": when if status == "completed" else None,
            "html_url": f"https://github.invalid/job/{name}/{when}"}


@pytest.mark.skipif(os.name == "nt", reason="the step runs on ubuntu; this "
                    "runs it under a `gh` started by its shebang")
@pytest.mark.parametrize("runs, jobs, code, says", [
    ([a_run(1)], {1: [a_job()]}, 0, "tests: success at 2026-10-15T17:00:00Z"),
    ([a_run(1, "workflow_dispatch")], {1: [a_job()]}, 0, "tests: success"),
    ([a_run(1, "pull_request")], {1: [a_job()]}, 1, "`tests` has not run"),
    ([a_run(1, head_sha="d" * 40)], {1: [a_job()]}, 1, "`tests` has not run"),
    ([a_run(1, path=".github/workflows/other.yml")], {1: [a_job()]}, 1,
     "`tests` has not run"),
    ([a_run(1)], {1: [a_job(conclusion="skipped")]}, 1, "`tests` has not run"),
    ([a_run(1)], {1: [a_job(name="lint")]}, 1, "`tests` has not run"),
    ([a_run(1)], {1: [a_job(status="in_progress", conclusion=None)]}, 1,
     "`tests` is in_progress"),
    ([a_run(1), a_run(2, "workflow_dispatch")],
     {1: [a_job("2026-10-15T17:00:00Z")],
      2: [a_job("2026-10-15T18:00:00Z", "failure")]}, 1,
     "`tests`'s newest run on " + GATE_SHA + " ended failure"),
    ([a_run(1), a_run(2, "workflow_dispatch")],
     {1: [a_job("2026-10-15T17:00:00Z", "failure")],
      2: [a_job("2026-10-15T18:00:00Z")]}, 0,
     "tests: success at 2026-10-15T18:00:00Z"),
    ([a_run(1)], {1: [a_job(conclusion="cancelled")]}, 1,
     "`tests`'s newest run on " + GATE_SHA + " ended cancelled"),
    ([a_run(1), a_run(2, "workflow_dispatch")],
     {1: [a_job("2026-10-15T17:00:00Z", "cancelled")],
      2: [a_job("2026-10-15T18:00:00Z")]}, 0,
     "tests: success at 2026-10-15T18:00:00Z"),
], ids=["a-push-run-passed", "a-dispatch-run-passed", "a-pull-request-run-alone",
        "a-run-of-another-head", "a-run-of-another-workflow", "skipped",
        "no-tests-job", "still-in-progress", "older-success-newer-failure",
        "older-failure-newer-success", "a-landing-cancelled-the-push-run",
        "a-dispatch-after-a-cancelled-push-run"])
def test_the_gate_decides_from_the_runs_jobs(workflow, tmp_path, runs, jobs,
                                            code, says):
    """RV599, SHOULD 6: the gate's own script under a `gh` that answers as
    the forge does. Only a push or dispatch run of tests.yml at the commit
    counts, and only its jobs are read; a job still running refuses; and
    the newest finished `tests` decides, whichever way the older went."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(f"#!{sys.executable}\n" + RUNS_GH,
                                encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    data = tmp_path / "forge.json"
    data.write_text(json.dumps({"runs": runs, "jobs": {str(k): v for k, v
                                                       in jobs.items()}}),
                    encoding="utf-8")
    log = tmp_path / "gh.log"
    log.write_text("", encoding="utf-8")
    script = tmp_path / "gate.py"
    script.write_text(heredoc(named_step(workflow, "build",
                                         "the commit carries")["run"]),
                      encoding="utf-8")
    done = subprocess.run(
        [sys.executable, "-I", str(script)], capture_output=True, text=True,
        check=False, env={**os.environ, "GH_LOG": str(log), "GH_DATA": str(data),
                          "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
                          "GITHUB_REPOSITORY": "opensoft/openRepoShape",
                          "GITHUB_SHA": GATE_SHA, "VERSION": "1.1.0"})
    assert done.returncode == code, done.stdout + done.stderr
    assert says in done.stdout + done.stderr
    if "has not run" in says or " ended " in says:
        # RV599, SHOULD 7: a refusal names the dispatch that answers it.
        for remedy in ("`gh workflow run tests.yml --ref <branch>`",
                       "`gh workflow run tests.yml --ref v1.1.0`",
                       "`--ref main` tests main's current head"):
            assert remedy in done.stdout + done.stderr, remedy
    counted = [run["id"] for run in runs
               if run["event"] in ("push", "workflow_dispatch")
               and run["head_sha"] == GATE_SHA
               and run["path"] == ".github/workflows/tests.yml"]
    asked = [int(found) for found in re.findall(
        r"/actions/runs/([0-9]+)/jobs\?filter=all", log.read_text(
            encoding="utf-8"))]
    assert asked == counted


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
    assert "if local != forge:" in script


# --- the tools, by digest -------------------------------------------------------

def test_every_pip_install_is_from_a_hash_lock_by_digest(workflow):
    """Every `pip install` the workflow runs, read as the shell reads it
    (continuations joined, comments dropped), is `--require-hashes`, wheels
    only, from one of the two locks: the build's tools in the build job,
    pipx in the install check, and nothing else anywhere."""
    used = set()
    for name, job in workflow["jobs"].items():
        for step in job["steps"]:
            for command in commands(step.get("run", "")):
                if not re.search(r"\bpip install\b", command):
                    continue
                assert "--require-hashes" in command, command
                assert "--only-binary :all:" in command, command
                [lock] = re.findall(r"-r (\S+)", command)
                used.add((name, lock))
    assert used == {
        ("build", BUILD_LOCK.relative_to(REPO).as_posix()),
        ("install", PIPX_LOCK.relative_to(REPO).as_posix())}


@pytest.mark.parametrize("lock", [BUILD_LOCK, PIPX_LOCK], ids=["build", "pipx"])
def test_every_lock_entry_is_one_version_named_by_its_sha256(lock):
    """A lock in which every requirement is pinned to one version and named
    by its sha256."""
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
    assert ('if ! cmp "$RUNNER_TEMP/dist-a/$wheel" "$RUNNER_TEMP/dist-b/$wheel"; then'
            in commands(build))
    stamp = commands(named_step(workflow, "build", "write the stamp")["run"])
    assert stamp[0] == ('python3 -I - "$TREE_A/src/openreposhape/_release.py" '
                        '"$TREE_B/src/openreposhape/_release.py" <<\'PY\'')


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
    assert {leg["os"] for leg in legs} == {"ubuntu-latest", "ubuntu-24.04",
                                            "macos-latest", "windows-latest"}
    assert {"os": "ubuntu-24.04", "python": "3.9"} in legs
    # #1094: `ubuntu-latest` now gives out Ubuntu 26.04, which has no 3.9
    # build for setup-python, so the 3.9 row stays on 24.04 and every row on
    # the latest image asks for a Python 26.04 has.
    assert [leg["python"] for leg in legs if leg["os"] == "ubuntu-latest"] \
        == ["3.x"]
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


def test_the_package_job_runs_its_python_3_9_on_ubuntu_24_04():
    """#1094: `tests.yml`'s `package` job builds and installs on 3.9, the
    floor of `requires-python`, and the Ubuntu 26.04 that `ubuntu-latest` now
    gives out has no 3.9 build for setup-python, so a run that landed there
    failed in setup-python. The job names 24.04 and asks for 3.9 once; the
    next test holds every other job of both workflows to what 26.04 has."""
    jobs = load_yaml(WORKFLOWS / "tests.yml")["jobs"]
    package = jobs["package"]
    assert package["runs-on"] == "ubuntu-24.04"
    pythons = [step["with"]["python-version"] for step in package["steps"]
               if step.get("uses", "").startswith("actions/setup-python@")]
    assert pythons == ["3.9"]


def setup_python_pairs():
    """Every (file, job, runner, Python) a setup-python step of `tests.yml`
    or `release.yml` asks for, as text. A job with a matrix gives one pair
    for each `include` row, with `${{ matrix.os }}` and `${{ matrix.python }}`
    filled from it; a job with none gives one. `str()` makes an unquoted
    `python-version: 3.9`, which `load_yaml` reads as the float 3.9, the text
    Actions hands setup-python."""
    for path in (WORKFLOWS / "tests.yml", WORKFLOWS / "release.yml"):
        for name, job in load_yaml(path)["jobs"].items():
            rows = job.get("strategy", {}).get("matrix", {}).get("include")
            steps = [step for step in job.get("steps", [])
                     if step.get("uses", "").startswith(
                         "actions/setup-python@")]
            for step in steps:
                for row in rows or [{}]:
                    fill = {"${{ matrix.os }}": str(row.get("os")),
                            "${{ matrix.python }}": str(row.get("python"))}
                    runner = str(job["runs-on"])
                    python = str(step["with"]["python-version"])
                    for key, value in fill.items():
                        runner = runner.replace(key, value)
                        python = python.replace(key, value)
                    yield path.name, name, runner, python


def test_no_setup_python_on_ubuntu_latest_asks_for_a_python_26_04_lacks():
    """#1094: the Ubuntu 26.04 that `ubuntu-latest` gives out has setup-python
    builds for 3.10 to 3.15 alone, so every job of both workflows that is on
    `ubuntu-latest` asks for `3.x` or `3.12`, and a 3.9 job is on 24.04. An
    allow list over the expanded matrix rows, so it holds for an unquoted
    3.9, for `release.yml`'s `build` job, and for a Python or a runner that a
    matrix gives."""
    pairs = list(setup_python_pairs())
    for file, job, runner, python in pairs:
        where = (file, job, runner, python)
        assert "${{" not in runner + python, where
        if runner == "ubuntu-latest":
            assert python in {"3.x", "3.12"}, where
        if python.split(".")[:2] == ["3", "9"]:
            assert runner == "ubuntu-24.04", where
    # The two 3.9 jobs are among the pairs, so the loop is not vacuous.
    assert ("tests.yml", "package", "ubuntu-24.04", "3.9") in pairs
    assert ("release.yml", "install", "ubuntu-24.04", "3.9") in pairs


def test_the_header_says_how_to_release(workflow):
    """The release notes (`docs/release-notes/v1.1.0.md` and `v1.1.1.md`)
    point at this header for the steps, so it carries them: Brett Heap's
    acts, with the trusted publisher's environment REQUIRED and why (RV599,
    SHOULD 1), and the limits carried over from openDox-code."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "# RELEASING TO PyPI." in text
    assert "gh workflow run release.yml --ref v<version> -f version=<version>" \
        in text
    assert "# A DISPATCH ON A BRANCH IS THE REHEARSAL, AND IT CANNOT DEPLOY." \
        in text
    assert "#     THE ENVIRONMENT IS REQUIRED in both" in text
    assert "# ACCEPTED LIMITS, carried over from openDox-code's release.yml" \
        in text
    assert "lane\n#     sessions act as brettheap" in text
    # #850's section, and the two sentences RV852 asked it to carry: a push
    # runs the tests.yml its own commit holds, and the branch's newer push run
    # decides after a fast-forward.
    assert "# RELEASE BRANCHES AND BACK-PORTS (#850)" in text
    assert "#   - a push runs the tests.yml its own commit holds, so a release" \
        in text
    assert "and that newer run decides. Tag once it has finished green." \
        in text


# --- RV599, SHOULD 2: the commit is on main or its release branch -------------------

ON_BRANCH = "the commit is on main or on the version's release branch"

#: A `gh` that answers `compare` from the environment, as the forge would,
#: and logs each call: STATUS_MAIN for main, STATUS_RELEASE for any other
#: branch, and a 404 where the one it reads is empty.
COMPARE_GH = """#!/bin/sh
echo "$*" >> "$GH_LOG"
case "$2" in
  *...refs/heads/main) status="$STATUS_MAIN" ;;
  *) status="$STATUS_RELEASE" ;;
esac
if [ -z "$status" ]; then echo "gh: Not Found (HTTP 404)" >&2; exit 1; fi
echo "$status"
"""


def test_the_commit_must_be_on_main_or_its_release_branch(workflow):
    """After the tag's checks and before anything from the checkout runs:
    the forge's compare must call `main` or `release/v<major>.<minor>`
    identical to the commit or ahead of it, by `refs/heads/`."""
    names = [step.get("name", "") for step in job_steps(workflow, "build")]
    assert names.index(ON_BRANCH) == names.index(
        "the dispatched ref is the annotated tag v<version> at this commit, "
        "or a branch to rehearse on") + 1
    lines = commands(named_step(workflow, "build", ON_BRANCH)["run"])
    assert 'for branch in main "release/v${VERSION%.*}"; do' in lines
    assert ('status="$(gh api "repos/$GITHUB_REPOSITORY/compare/'
            '$GITHUB_SHA...refs/heads/$branch" --jq .status 2>/dev/null)" '
            '|| status=') in lines
    assert "identical|ahead)" in lines


@pytest.mark.skipif(os.name == "nt", reason="the step is bash on ubuntu; "
                    "this runs it under a POSIX `gh` stub")
@pytest.mark.parametrize("ref, version, main, release, code, asked", [
    ("refs/tags/v1.1.0", "1.1.0", "ahead", "", 0, ["main"]),
    ("refs/tags/v1.1.0", "1.1.0", "identical", "", 0, ["main"]),
    ("refs/tags/v1.0.1", "1.0.1", "diverged", "identical", 0,
     ["main", "release/v1.0"]),
    ("refs/tags/v1.1.0", "1.1.0", "diverged", "", 1, ["main", "release/v1.1"]),
    ("refs/tags/v1.1.0", "1.1.0", "behind", "diverged", 1,
     ["main", "release/v1.1"]),
    ("refs/heads/rehearse", "1.1.0", "", "", 0, []),
])
def test_the_on_branch_step_answers_from_the_forges_compare(
        workflow, tmp_path, ref, version, main, release, code, asked):
    """Run with a `gh` that answers as the forge did for v1.0.1 (diverged
    from main, identical to `release/v1.0`) and for an unmerged head
    (diverged, no release branch); a branch rehearsal asks nothing."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(COMPARE_GH, encoding="utf-8")
    (bin_dir / "gh").chmod(0o755)
    script = tmp_path / "step.sh"
    script.write_text(named_step(workflow, "build", ON_BRANCH)["run"],
                      encoding="utf-8")
    log = tmp_path / "gh.log"
    log.write_text("", encoding="utf-8")
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
           "GH_LOG": str(log), "STATUS_MAIN": main, "STATUS_RELEASE": release,
           "GITHUB_REF": ref, "GITHUB_REF_NAME": ref.rsplit("/", 1)[-1],
           "GITHUB_SHA": "c" * 40, "GITHUB_REPOSITORY": "opensoft/openRepoShape",
           "VERSION": version}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail",
                           str(script)], env=env, capture_output=True,
                          text=True, check=False)
    assert done.returncode == code, done.stdout + done.stderr
    called = [line.split("refs/heads/")[1].split()[0]
              for line in log.read_text(encoding="utf-8").splitlines()]
    assert called == asked


# --- RV599, SHOULD 3: what the mutations got past -------------------------------------

#: The only steps that run conditionally, and their conditions: the tag
#: path's TestPyPI fetch, the rehearsal's own wheel, and PowerShell.
STEP_CONDITIONS = {
    ("install", "fetch the wheel from TestPyPI"):
        "startsWith(github.ref, 'refs/tags/')",
    ("install", "take the build's own wheel, on a branch (the rehearsal)"):
        "${{ !startsWith(github.ref, 'refs/tags/') }}",
    ("install", "PowerShell runs openRepoShape by its name (Windows)"):
        "runner.os == 'Windows'",
}

#: Each upload job's steps, in their order: the artifact, its digest, the
#: environment and this run's approval, the tag, the index before, the
#: upload, the index after.
UPLOAD_STEPS = [
    "actions/download-artifact",
    "dist holds the wheel the build job verified, and nothing else",
    "this environment still asks a reviewer and admits only the tags v*, and "
    "this run's deployment to it was approved",
    "the tag v<version> still names this commit",
    "the index holds no file of this version but the verified wheel",
    "pypa/gh-action-pypi-publish",
    "the index serves exactly the verified wheel",
]


def label(step: dict) -> str:
    return step.get("name") or step["uses"].split("@")[0]


def test_only_the_intended_steps_and_jobs_run_conditionally(workflow):
    """(a) An `if:` on any other step, or another condition on these,
    could skip a check; and nothing continues past a failed step."""
    found = {(name, label(step)): step["if"]
             for name, job in workflow["jobs"].items()
             for step in job["steps"] if "if" in step}
    assert found == STEP_CONDITIONS
    assert "if" not in workflow["jobs"]["build"]
    for name, job in workflow["jobs"].items():
        assert "continue-on-error" not in job, name
        for step in job["steps"]:
            assert "continue-on-error" not in step, (name, label(step))


def test_every_checkout_keeps_no_credentials(workflow):
    """(b) The token is never left in a checkout's git config, where code
    the job then runs could read it."""
    checkouts = [step for job in workflow["jobs"].values()
                 for step in job["steps"]
                 if step.get("uses", "").startswith("actions/checkout@")]
    assert len(checkouts) == 2
    for step in checkouts:
        assert step["with"]["persist-credentials"] is False


def test_no_pip_setting_but_pypi_as_the_install_checks_only_index(workflow):
    """(c) `PIP_*` appears in no environment and no script but the install
    check's two settings: PyPI as the one index, and no version check."""
    scopes = [workflow.get("env") or {}]
    for job in workflow["jobs"].values():
        scopes.append(job.get("env") or {})
        scopes.extend(step.get("env") or {} for step in job["steps"])
    pip = sorted(key for scope in scopes for key in scope
                 if key.startswith("PIP_"))
    assert pip == ["PIP_DISABLE_PIP_VERSION_CHECK", "PIP_INDEX_URL"]
    assert workflow["jobs"]["install"]["env"]["PIP_INDEX_URL"] == \
        "https://pypi.org/simple/"
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            assert "PIP_" not in step.get("run", ""), label(step)
            assert "--index-url" not in step.get("run", ""), label(step)


@pytest.mark.parametrize("job", sorted(UPLOADS))
def test_each_upload_job_checks_in_its_fixed_order(workflow, job):
    """(d) The digest, the environment and approval, the tag, the index
    before, the upload, the index after, in that order; each check is the
    same script in both jobs; TestPyPI's upload names TestPyPI and PyPI's
    names no other index."""
    steps = job_steps(workflow, job)
    assert [label(step) for step in steps] == UPLOAD_STEPS
    assert ('echo "$WHEEL_SHA256  dist/$WHEEL" | sha256sum --strict -c -'
            in commands(steps[1]["run"]))
    other = job_steps(workflow, ({*UPLOADS} - {job}).pop())
    for mine, theirs in zip(steps, other):
        assert mine.get("run") == theirs.get("run"), label(mine)
    publish = steps[UPLOAD_STEPS.index("pypa/gh-action-pypi-publish")]["with"]
    if job == "testpypi":
        assert publish == {"repository-url": "https://test.pypi.org/legacy/",
                           "skip-existing": True, "print-hash": True}
    else:
        assert publish == {"skip-existing": True, "print-hash": True}
    index = {"testpypi": "https://test.pypi.org/pypi/openreposhape/",
             "pypi": "https://pypi.org/pypi/openreposhape/"}
    assert workflow["jobs"][job]["env"]["JSON_BASE"] == index[job]


WHEEL_CHECK = "the wheel holds the commit's own files, byte for byte, and the stamp"


def test_the_wheel_is_checked_against_the_commit_before_it_is_recorded(
        workflow):
    """(e) RV599, SHOULD 5 besides: right after the two builds and before
    the digest is recorded, with each of its comparisons."""
    names = [step.get("name", "") for step in job_steps(workflow, "build")]
    check = names.index(WHEEL_CHECK)
    assert names[check - 1] == ("build the wheel from each extraction, and "
                                "the two are one file")
    assert names[check + 1] == "record the wheel and its sha256"
    script = heredoc(named_step(workflow, "build", WHEEL_CHECK)["run"])
    for line in (
            "elif wheel.read(name) != committed(source):",
            "for name in sorted(wanted - set(names)):",
            "if changed != release or assigned != release:",
            "if shown != declared:",
            'if entry_points.sections() != ["console_scripts"]:',
            'if scripts != project["scripts"]:',
            'if described != sorted(["METADATA", "WHEEL", "RECORD", '
            '"entry_points.txt",',
            'if wheel.read(info + "licenses/LICENSE") != committed("LICENSE"):',
            "sys.exit(1 if problems else 0)"):
        assert line in script, line


def fake_wheel(path: Path, sha: str, version: str, digest: str,
               change: dict) -> None:
    """The wheel the build writes for `sha`, laid out as hatchling lays it
    out, from git's own blobs; `change` replaces entries, None drops one."""
    tomllib = pytest.importorskip("tomllib")

    def blob(name: str) -> bytes:
        return subprocess.run(["git", "cat-file", "blob", f"{sha}:{name}"],
                              cwd=REPO, capture_output=True, check=True).stdout

    project = tomllib.loads(blob("pyproject.toml").decode())["project"]
    listed = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only", sha,
                             "--", "src/openreposhape/"], cwd=REPO,
                            capture_output=True, check=True).stdout.decode()
    files = {name[len("src/"):]: blob(name)
             for name in listed.split("\0") if name}
    files["openreposhape/setup-project.py"] = blob("setup-project.py")
    stamp = files["openreposhape/_release.py"].decode()
    for name, old, new in (("VERSION", "0.0.0", version),
                           ("TAG", "", f"v{version}"), ("COMMIT", "", sha),
                           ("DIGEST", "", digest)):
        stamp = stamp.replace(f'{name} = "{old}"', f'{name} = "{new}"', 1)
    files["openreposhape/_release.py"] = stamp.encode()
    info = f"openreposhape-{version}.dist-info/"
    files[info + "METADATA"] = "".join(
        [f"Metadata-Version: 2.4\nName: {project['name']}\n",
         f"Version: {version}\nRequires-Python: {project['requires-python']}\n",
         *(f"Requires-Dist: {r}\n" for r in project["dependencies"])]).encode()
    files[info + "WHEEL"] = b"Wheel-Version: 1.0\nTag: py3-none-any\n"
    files[info + "entry_points.txt"] = "".join(
        ["[console_scripts]\n",
         *(f"{k} = {v}\n" for k, v in project["scripts"].items())]).encode()
    files[info + "licenses/LICENSE"] = blob("LICENSE")
    files[info + "RECORD"] = b""
    files.update({name.replace("<info>", info): data
                  for name, data in change.items()})
    with zipfile.ZipFile(path, "w") as wheel:
        for name, data in sorted(files.items()):
            if data is not None:
                wheel.writestr(name, data)


@pytest.mark.parametrize("change, code", [
    ({}, 0),
    ({"openreposhape/cli.py": b"# not the commit's\n"}, 1),
    ({"openreposhape/extra.py": b"import os\n"}, 1),
    ({"openreposhape/standard.py": None}, 1),
    ({"<info>top_level.txt": b"openreposhape\n"}, 1),
    ({"<info>RECORD": None}, 1),
    ({"<info>entry_points.txt": b"[console_scripts]\n[gui_scripts]\n"}, 1),
], ids=["the-commits-own", "a-changed-module", "an-extra-module",
        "a-missing-module", "an-extra-dist-info-file", "no-record",
        "a-second-entry-point-section"])
def test_the_wheel_check_refuses_any_file_that_is_not_the_commits(
        workflow, tmp_path, change, code):
    """The step's own script, over a wheel made from this checkout's HEAD:
    the commit's own files pass, and a changed, extra or missing module, an
    extra or missing `.dist-info/` file, or an entry-point section beside
    `console_scripts` refuses (RV599, SHOULD 5)."""
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                         capture_output=True, text=True, check=True).stdout.strip()
    wheel = tmp_path / "openreposhape-1.1.0-py3-none-any.whl"
    fake_wheel(wheel, sha, "1.1.0", "d" * 64, change)
    script = tmp_path / "check.py"
    script.write_text(heredoc(named_step(workflow, "build", WHEEL_CHECK)["run"]),
                      encoding="utf-8")
    done = subprocess.run([sys.executable, "-I", str(script), str(wheel)],
                          cwd=REPO, capture_output=True, text=True, check=False,
                          env={**os.environ, "VERSION": "1.1.0",
                               "GITHUB_SHA": sha, "DIGEST": "d" * 64})
    assert done.returncode == code, done.stdout + done.stderr


def test_a_bare_success_exit_is_the_rehearsal_or_a_404_alone(workflow):
    """(f) `exit 0` ends a step early only on a branch rehearsal, inside
    its `refs/heads/*)` arm, and `sys.exit(0)` only where an index answers
    404 for a version it holds no file of."""
    found = {}
    for name, job in workflow["jobs"].items():
        for step in job["steps"]:
            lines = step.get("run", "").splitlines()
            for at, line in enumerate(lines):
                if re.fullmatch(r"\s*exit 0\s*", line):
                    assert "refs/heads/*)" in "\n".join(lines[at - 2:at])
                    found.setdefault((name, label(step)), []).append("exit 0")
                if "sys.exit(0)" in line:
                    assert "!= 404" in "\n".join(lines[at - 4:at])
                    found.setdefault((name, label(step)), []).append(
                        "sys.exit(0)")
    assert found == {
        ("build", "the dispatched ref is the annotated tag v<version> at this "
                  "commit, or a branch to rehearse on"): ["exit 0"],
        ("build", ON_BRANCH): ["exit 0"],
        ("testpypi", UPLOAD_STEPS[4]): ["sys.exit(0)"],
        ("pypi", UPLOAD_STEPS[4]): ["sys.exit(0)"],
    }


# --- RV599, SHOULD 4: the release workflow is linted on every pull request ----------

def test_tests_yml_lints_the_release_workflow():
    """`tests.yml`'s actionlint step hands it this file, so a workflow no
    pull request ever runs is still read by the linter on each one."""
    tests = load_yaml(WORKFLOWS / "tests.yml")
    [lint] = [step for step in tests["jobs"]["tests"]["steps"]
              if step.get("name", "").startswith("actionlint")]
    assert ".github/workflows/release.yml" in lint["run"].split()
