# SPDX-License-Identifier: Apache-2.0
"""`setup.sh` — fork, clone, run one command.

The end-to-end test drives the real script against BARE REPOSITORIES IN A
TEMPORARY DIRECTORY. `gh` is never invoked and no real repository is created;
that is what `--local-remote-dir` is for.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from pathlib import Path

from conftest import REPO, git

SETUP = REPO / "setup.sh"
DEGRADE_LINE = "authority is not wallet-carried in this org"

pytestmark = pytest.mark.skipif(shutil.which("bash") is None,
                                reason="setup.sh needs bash")


def run_setup(*args: str, stdin: str = "",
             cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    return subprocess.run(["bash", str(SETUP), *args], capture_output=True,
                          text=True, check=False, input=stdin, env=env,
                          cwd=str(cwd) if cwd is not None else str(REPO))


def make_fork_dir(tmp_path: Path, origin_url: str, upstream_url: str) -> Path:
    """A directory that IS a git repo (so setup.sh's origin/upstream remote
    reads have something to find) but is not itself an openRepoShape checkout.

    setup.sh reads its `origin`/`upstream` remotes from the directory it was
    RUN FROM ($INVOCATION_DIR), not from $SCRIPT_DIR (where setup.sh itself
    lives, still this REPO) — the two are the same for a real fork clone, and
    deliberately different here so this test does not depend on this
    checkout's own `origin`, whatever that happens to be.
    """
    fork = tmp_path / "fork"
    fork.mkdir()
    git("init", "-q", cwd=fork)
    git("remote", "add", "origin", origin_url, cwd=fork)
    git("remote", "add", "upstream", upstream_url, cwd=fork)
    return fork


@pytest.fixture(scope="module")
def setup_run(tmp_path_factory) -> dict:
    """One real `setup.sh` run, end to end, with no network.

    `--org` is explicit here (not what this fixture is testing) because
    local mode now reads the real `origin` remote of the directory it runs
    in — see `make_fork_dir` — and this suite must pass identically whether
    that directory happens to be a fork or, as in CI, opensoft's own clone.
    """
    base = tmp_path_factory.mktemp("setup")
    result = run_setup("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(base / "remotes"),
                       "--into", str(base / "work"))
    return {"base": base, "result": result, "clone": base / "work" / "Sample"}


def test_setup_runs_end_to_end(setup_run):
    result = setup_run["result"]
    assert result.returncode == 0, result.stderr + result.stdout


def test_it_creates_the_three_bare_remotes(setup_run):
    remotes = setup_run["base"] / "remotes"
    for name in ("Sample.git", "Sample-spec.git", "Sample-code.git"):
        assert (remotes / name).is_dir(), f"{name} was not created"


def test_the_assembly_root_is_cloned_where_into_says(setup_run):
    clone = setup_run["clone"]
    assert clone.is_dir(), f"{clone} does not exist"
    assert (clone / "project.yaml").is_file()
    assert (clone / ".gitmodules").is_file()


def test_both_legs_are_on_main_after_bootstrap(setup_run):
    """The whole point of step (7): nobody is left staring at a detached HEAD."""
    for leg in ("spec", "code"):
        branch = git("rev-parse", "--abbrev-ref", "HEAD",
                     cwd=setup_run["clone"] / leg).stdout.strip()
        assert branch == "main", f"{leg} is on {branch!r}, expected 'main'"


def test_bootstrap_ran_and_printed_the_degrade_line(setup_run):
    out = setup_run["result"].stdout
    assert DEGRADE_LINE in out
    assert "bootstrap ok" in out
    assert "pins ok" in out


def test_the_final_block_names_the_path_and_the_three_urls(setup_run):
    out = setup_run["result"].stdout
    assert "DONE. Sample is scaffolded and bootstrapped." in out
    assert str(setup_run["clone"]) in out
    for name in ("Sample.git", "Sample-spec.git", "Sample-code.git"):
        assert name in out
    assert "make validate" in out


def test_preflight_reports_each_prerequisite(setup_run):
    out = setup_run["result"].stdout
    assert "(1) preflight" in out
    assert "git " in out and "python3 " in out
    assert "gh not required" in out, "local mode must skip the gh preflight"


def test_the_naming_policy_runs_before_anything_is_created(setup_run):
    out = setup_run["result"].stdout
    assert out.index("(4) naming policy") < out.index("(6) scaffold")
    # `--explain` form: the winner, then every family the name satisfies.
    assert "Sample: project-leg / assembly" in out
    assert "Sample-spec: project-leg / spec" in out
    assert "Sample-code: project-leg / code" in out


# --- the refusals ----------------------------------------------------------

def test_help_exits_zero():
    result = run_setup("--help")
    assert result.returncode == 0
    assert "usage: ./setup.sh" in result.stdout


def test_an_unknown_argument_refuses():
    result = run_setup("--project", "Sample", "--wat")
    assert result.returncode == 2
    assert "unknown argument: --wat" in result.stderr


def test_a_bad_visibility_refuses():
    result = run_setup("--project", "Sample", "--visibility", "secret")
    assert result.returncode == 2
    assert "must be 'private' or 'public'" in result.stderr


def test_a_name_outside_the_naming_policy_stops_before_the_scaffold(tmp_path):
    result = run_setup("--project", "Sample_One", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr
    assert "(6) scaffold" not in result.stdout
    assert not (tmp_path / "remotes").exists()


def test_scaffolding_into_the_upstream_org_refuses(tmp_path):
    """Cloning the upstream instead of forking it looks identical from inside
    the directory. Only one of the two should be creating repositories."""
    result = run_setup("--project", "Sample", "--yes", "--org", "opensoft",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "which is the UPSTREAM" in result.stderr
    assert "--allow-upstream-org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_allow_upstream_org_lets_it_through(tmp_path):
    result = run_setup("--project", "Sample", "--yes", "--org", "opensoft",
                       "--allow-upstream-org",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: opensoft/Sample" in manifest


def test_org_is_detected_from_the_origin_remote_ssh_url(tmp_path):
    """The real-world defect: `gh repo fork opensoft/openRepoShape --org
    ExampleOrg --clone` leaves a clone with an `origin` (the fork) AND an
    `upstream` (opensoft) remote. `gh repo view` with no argument resolves
    the current repository by ITS OWN preference between the two, which can
    pick `upstream` and report `opensoft` for a perfectly correct fork — the
    upstream-org guard then refuses a clone that was never wrong. `origin`
    is unambiguous, so it is what gets read."""
    fork = make_fork_dir(tmp_path,
                         origin_url="git@github.com:ExampleOrg/openRepoShape.git",
                         upstream_url="git@github.com:opensoft/openRepoShape.git")
    result = run_setup("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=fork)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "which is the UPSTREAM" not in result.stderr
    assert "organisation ExampleOrg" in result.stdout
    assert "upstream is opensoft; scaffolding into ExampleOrg" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: ExampleOrg/Sample" in manifest
    assert "repository: ExampleOrg/Sample-spec" in manifest
    assert "repository: ExampleOrg/Sample-code" in manifest


def test_org_is_detected_from_the_origin_remote_https_url(tmp_path):
    """Same defect, HTTPS remotes instead of SSH."""
    fork = make_fork_dir(tmp_path,
                         origin_url="https://github.com/ExampleOrg/openRepoShape.git",
                         upstream_url="https://github.com/opensoft/openRepoShape.git")
    result = run_setup("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=fork)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "which is the UPSTREAM" not in result.stderr
    assert "organisation ExampleOrg" in result.stdout
    assert "upstream is opensoft; scaffolding into ExampleOrg" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "repository: ExampleOrg/Sample" in manifest
    assert "repository: ExampleOrg/Sample-spec" in manifest
    assert "repository: ExampleOrg/Sample-code" in manifest


def test_no_confirmation_and_no_terminal_refuses_after_showing_the_plan(tmp_path):
    result = run_setup("--project", "Sample", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "--dry-run: nothing was created." in result.stdout
    assert "no terminal to confirm on" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_no_project_and_no_terminal_refuses(tmp_path):
    # `--local-remote-dir` is what keeps this offline. Without it the run
    # reaches the real `gh auth status` preflight and refuses for THAT reason
    # instead — which is how this test passed on an authenticated laptop and
    # failed in CI. Every test here must be independent of `gh` being logged in.
    result = run_setup("--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "no --project given" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_passthrough_reaches_the_scaffold(tmp_path):
    result = run_setup("--project", "Sample", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"),
                       "--", "--reference", "a-staged-fragment.md")
    assert result.returncode == 0, result.stderr
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert 'reference: "a-staged-fragment.md"' in manifest


def test_no_test_here_depends_on_gh_being_authenticated():
    """Every invocation either stops before the preflight or runs offline.

    The three that stop early are argument-parsing refusals (`--help`, an
    unknown flag, a bad `--visibility`), which the script answers before it
    looks at the machine. Everything else must pass `--local-remote-dir`, or it
    reaches `gh auth status` and passes only on a laptop that happens to be
    logged in — which is exactly how the first version of this file went green
    locally and red in CI.
    """
    source = Path(__file__).read_text(encoding="utf-8")
    early = ("--help", "--wat", '"secret"')
    for match in re.finditer(r"(?<!def )run_setup\(", source):
        start = match.end()
        depth, index = 1, start
        while depth:
            if source[index] == "(":
                depth += 1
            elif source[index] == ")":
                depth -= 1
            index += 1
        call = source[start:index - 1]
        if any(marker in call for marker in early):
            continue
        assert "--local-remote-dir" in call, (
            "this run_setup call reaches the gh preflight and will fail "
            f"wherever gh is not authenticated:\n    {' '.join(call.split())}")
