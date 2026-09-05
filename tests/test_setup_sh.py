# SPDX-License-Identifier: Apache-2.0
"""`setup.sh` — self-bootstrap from a temp checkout, or run from one, then
scaffold and clean up.

The end-to-end test drives the real script against BARE REPOSITORIES IN A
TEMPORARY DIRECTORY. `gh` is never invoked and no real repository is created;
that is what `--local-remote-dir` is for. The self-bootstrap tests point
`OPENREPOSHAPE_REPO` at THIS checkout (a local path, so `git clone` stays
offline) instead of the real `opensoft/openRepoShape` on GitHub.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

from pathlib import Path

from conftest import REPO, WINDOWS_SKIP, git

SETUP = REPO / "setup.sh"
DEGRADE_LINE = "authority is not wallet-carried in this org"

#: `bash.exe` IS on the GitHub Windows runner, so the `which` guard alone
#: does not fire there — and `setup.sh` still cannot run: it is a POSIX shell
#: script, and it probes `python3` then `python` for the interpreter it hands
#: over to. The Windows entry point is `setup-project.py`, run directly, and
#: `tests/test_setup_project_py.py` mirrors this file case for case.
pytestmark = [pytest.mark.skipif(shutil.which("bash") is None,
                                 reason="setup.sh needs bash"),
              WINDOWS_SKIP]


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


def make_outside_checkout(tmp_path: Path) -> Path:
    """A directory holding a standalone COPY of setup.sh that is not inside
    any git checkout at all — no `.git`, no `scaffold-project.py`, no
    `contracts/`. This is what `curl -fsSL ... | bash -s --` looks like on
    disk: a script with nothing beside it, run from wherever the person
    happened to be standing.
    """
    outside = tmp_path / "outside"
    outside.mkdir()
    copy = outside / "setup.sh"
    shutil.copy(SETUP, copy)
    copy.chmod(0o755)
    return outside


def run_bare_setup(script: Path, *args: str, cwd: Path,
                   extra_env: dict | None = None) -> subprocess.CompletedProcess:
    """Like `run_setup`, but against an arbitrary script path and cwd — what
    the self-bootstrap tests need since `run_setup` always drives THIS
    checkout's own `setup.sh` from THIS checkout's own directory."""
    env = dict(os.environ)
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    env.update(extra_env or {})
    return subprocess.run(["bash", str(script), *args], capture_output=True,
                          text=True, check=False, cwd=str(cwd), env=env)


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
    # #50 — the preflight moved into `setup-project.py`, which reports the
    # RUNNING interpreter (`[ok] python 3.12.3 (/usr/bin/python3)`) rather
    # than the literal `python3` the old bash preflight shelled out to. The
    # shim picks `python3` off PATH and hands over, so what is named here is a
    # version and a path, not a constant. The old spelling would still pass —
    # off the `bootstrap runs as \`python3 scripts/bootstrap.py\`` line, which
    # is a different fact about a different program.
    assert "git " in out and re.search(r"python 3\.\d+\.\d+ \(", out), out
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
    # #50 — one usage banner, printed by the one implementation. `setup.sh`
    # execs `setup-project.py`, so `--help` is the Python's text, reached
    # under either of the two names a person can type.
    assert "usage: setup-project.py" in result.stdout


def test_an_unknown_argument_refuses():
    result = run_setup("--project", "Sample", "--wat")
    assert result.returncode == 2
    assert "unknown argument: --wat" in result.stderr


def test_a_bad_visibility_refuses():
    result = run_setup("--project", "Sample", "--visibility", "secret")
    assert result.returncode == 2
    assert "must be 'private', 'public' or 'internal'" in result.stderr


def test_an_internal_visibility_is_accepted(tmp_path):
    """`internal` is a real GitHub visibility (an enterprise org-internal
    repository, `gh repo view --json visibility` -> `INTERNAL`), not a typo."""
    result = run_setup("--project", "Sample", "--yes", "--org", "demoorg",
                       "--visibility", "internal",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "visibility   internal" in result.stdout
    manifest = (tmp_path / "work" / "Sample" / "project.yaml").read_text()
    assert "visibility: internal" in manifest


def test_a_name_outside_the_naming_policy_stops_before_the_scaffold(tmp_path):
    result = run_setup("--project", "Sample_One", "--yes", "--org", "demoorg",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 1
    assert "naming-unclassified" in result.stderr
    assert "(6) scaffold" not in result.stdout
    assert not (tmp_path / "remotes").exists()


def test_scaffolding_into_the_upstream_org_refuses(tmp_path):
    """`--org opensoft` is almost never what anyone means: opensoft is the
    UPSTREAM owner of openRepoShape itself, not a place to scaffold three
    fresh repositories into."""
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


# --- self-bootstrap ---------------------------------------------------------
#
# `curl -fsSL .../setup.sh | bash -s -- --org <org> --project <Project>` has
# no checkout on disk at all. These tests reproduce that shape: a lone COPY of
# setup.sh in a directory with no `.git`, no `scaffold-project.py`, run with
# $OPENREPOSHAPE_REPO pointed at THIS checkout so the clone it does is local
# and offline.

def test_self_bootstrap_scaffolds_from_a_temporary_checkout(tmp_path):
    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_bare_setup(outside / "setup.sh",
                            "--org", "demoorg", "--project", "Sample", "--yes",
                            "--local-remote-dir", str(base / "remotes"),
                            "--into", str(base / "work"),
                            cwd=outside, extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(0) self-bootstrap" in result.stdout
    assert DEGRADE_LINE in result.stdout
    clone = base / "work" / "Sample"
    assert clone.is_dir()
    assert (clone / "project.yaml").is_file()

    match = re.search(r"checkout: (\S+)", result.stdout)
    assert match, f"setup.sh never printed the shape checkout path:\n{result.stdout}"
    assert not Path(match.group(1)).exists(), (
        "the temporary shape checkout should have been removed on exit")


def test_self_bootstrap_keeps_the_checkout_when_asked(tmp_path):
    outside = make_outside_checkout(tmp_path)
    base = tmp_path / "run"
    result = run_bare_setup(outside / "setup.sh",
                            "--org", "demoorg", "--project", "Sample", "--yes",
                            "--keep-shape-checkout",
                            "--local-remote-dir", str(base / "remotes"),
                            "--into", str(base / "work"),
                            cwd=outside, extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert "kept the shape checkout:" in result.stdout

    match = re.search(r"checkout: (\S+)", result.stdout)
    assert match, f"setup.sh never printed the shape checkout path:\n{result.stdout}"
    kept = Path(match.group(1))
    try:
        assert kept.is_dir(), "--keep-shape-checkout should have kept the clone"
        assert (kept / "scaffold-project.py").is_file()
    finally:
        shutil.rmtree(kept, ignore_errors=True)


def test_self_bootstrap_clones_into_the_directory_it_was_run_from(tmp_path):
    """#39: the re-exec runs from a temporary checkout under `mktemp -d`, so
    the child's own default parent was `..` of THAT — /tmp — and the new
    project was cloned there, then left behind when the temporary checkout
    beside it was deleted. It belongs where the person was standing, and no
    `--into` is passed here: the default is the whole point.
    """
    outside = make_outside_checkout(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = run_bare_setup(outside / "setup.sh",
                            "--org", "demoorg", "--project", "Sample", "--yes",
                            "--local-remote-dir", str(tmp_path / "remotes"),
                            cwd=cwd, extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    clone = cwd / "Sample"
    assert clone.is_dir(), (
        f"Sample was not cloned into {cwd}, the directory setup.sh ran "
        f"in:\n{result.stdout}")
    assert (clone / "project.yaml").is_file()
    assert f"clone       {clone}" in result.stdout

    match = re.search(r"checkout: (\S+)", result.stdout)
    assert match, f"setup.sh never printed the shape checkout path:\n{result.stdout}"
    assert not (Path(match.group(1)).parent / "Sample").exists(), (
        "the clone landed beside the TEMPORARY checkout (/tmp), which is the "
        "defect #39 is about")


def test_into_still_wins_in_self_bootstrap_mode(tmp_path):
    """The invocation directory is passed as `--into` BEFORE the person's own
    arguments, so an explicit `--into` of theirs is parsed after it and wins."""
    outside = make_outside_checkout(tmp_path)
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    result = run_bare_setup(outside / "setup.sh",
                            "--org", "demoorg", "--project", "Sample", "--yes",
                            "--local-remote-dir", str(tmp_path / "remotes"),
                            "--into", str(tmp_path / "work"),
                            cwd=cwd, extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert (tmp_path / "work" / "Sample" / "project.yaml").is_file()
    assert not (cwd / "Sample").exists(), "--into was overridden, not honoured"


def test_running_from_the_upstream_checkout_without_org_refuses(tmp_path):
    """`origin` pointing at opensoft/openRepoShape itself means this checkout
    IS the upstream: there is no fork to inherit an organisation from, so the
    ask is the same as self-bootstrap's — pass --org — not the old blanket
    refusal."""
    checkout = tmp_path / "upstream-checkout"
    checkout.mkdir()
    git("init", "-q", cwd=checkout)
    git("remote", "add", "origin",
       "git@github.com:opensoft/openRepoShape.git", cwd=checkout)
    result = run_setup("--project", "Sample", "--yes",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"), cwd=checkout)
    assert result.returncode == 2
    assert "upstream checkout" in result.stderr
    assert "--org" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_self_bootstrap_without_org_refuses(tmp_path):
    """There is no fork `origin` to read an organisation from outside a
    checkout, so `--org` cannot be optional the way it is from inside one.

    `OPENREPOSHAPE_REPO` is set here where it once was not, for the same
    reason every other self-bootstrap test sets it: since #50 the refusal is
    the CLONED standard's, printed by `setup-project.py` under the
    `OPENREPOSHAPE_SELF_BOOTSTRAP` handshake rather than by the shim, so this
    run reaches a clone — and a test that reached GitHub for it would be the
    one test in this suite that needs a network.
    """
    outside = make_outside_checkout(tmp_path)
    result = run_bare_setup(outside / "setup.sh",
                            "--project", "Sample", "--yes",
                            "--local-remote-dir", str(tmp_path / "remotes"),
                            "--into", str(tmp_path / "work"),
                            cwd=outside,
                            extra_env={"OPENREPOSHAPE_REPO": str(REPO)})
    assert result.returncode == 2
    assert "--org" in result.stderr
    assert not (tmp_path / "remotes").exists()
