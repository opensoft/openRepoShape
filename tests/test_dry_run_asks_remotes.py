# SPDX-License-Identifier: Apache-2.0
"""`family.py init --dry-run` and `scaffold-project.py --dry-run` ask whether
the remotes already exist (#537).

WHAT WAS WRONG. Both dry runs printed the plan and exited 0 before the one
question their real runs ask of the remotes: `_checked_reuse` for the
family's holder and `_reusable_remotes` for the scaffold's three
repositories. Against a remote that already exists, the dry run said nothing
and the real run then refused: `family.py init` with `family-remote-exists`
after it had made the family folder, and the scaffold with
`scaffold-remote-exists` from step (6) of `setup-project.py`, after the yes.

THE CURE. Each dry run asks the real run's own question, never a second one
that could disagree with it, after the plan and before it says nothing was
created, and refuses what the real run refuses. It reads and writes nothing
that outlives it: `gh repo view` and a commit listing, or the bare
repositories on disk with `--local-remote-dir`, and for a scaffold leg that
is not empty the one commit it holds, fetched into a temporary directory the
real run's question deletes.

Most tests here run against bare repositories on disk. The GitHub route runs
against a stub `gh` on PATH that answers the two reads and refuses anything
else, and is POSIX only, as every `#!` stub in this suite is; where no `gh`
can be started at all, the refusal is asked in process, on every platform.
The step (5) test of `setup-project.py` and `setup.sh` is
`conftest.assert_the_plan_refuses_a_remote_that_exists`.
"""

from __future__ import annotations

import importlib.util
import os
import stat
import subprocess
from pathlib import Path

import pytest

from conftest import ORG, REPO, SCAFFOLD, WINDOWS_SKIP, git, run_script
from test_scaffold_reuse_seeded_legs import (REPOS, bare, commits,
                                             refused_at_the_root, tip)
from test_ruleset_hint_tracking_branch import template  # noqa: F401

FAMILY = REPO / "scripts" / "family.py"
HOLDER = "Contoso"
PROJECT = "Atlas"
DRY_RUN_DONE = "--dry-run: nothing was created."


def scratch_env(tmp_path: Path) -> dict:
    """`TMPDIR`, `TMP` and `TEMP` at an empty `tmp_path/tmp`, so a test sees
    whether a run left anything in the temporary directory."""
    scratch = tmp_path / "tmp"
    scratch.mkdir(exist_ok=True)
    return {"TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)}


def empty_bare(path: Path) -> Path:
    """A bare repository at `remotes/<name>.git` with zero commits: a
    reserved name."""
    path.parent.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "--bare", "-b", "main", str(path), cwd=path.parent)
    return path


def live_bare(path: Path) -> Path:
    """A bare repository at `remotes/<name>.git` holding one commit of
    somebody else's, made in a clone beside `remotes/`."""
    work = path.parent.parent / "somebody" / path.stem
    work.mkdir(parents=True)
    git("init", "-q", "-b", "main", str(work), cwd=work)
    (work / "README.md").write_bytes(b"# somebody's\n")
    git("add", "README.md", cwd=work)
    git("commit", "-q", "-m", "somebody's", cwd=work)
    git("push", "-q", str(empty_bare(path)), "main", cwd=work)
    return path


def refs(path: Path) -> str:
    return git("for-each-ref", cwd=path).stdout


def load(name: str, path: Path):
    """A tool as a module, for the in-process tests."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def assert_refused_after_the_plan(result, refusal: str, plan_line: str) -> None:
    """Exit 2 with `refusal`, after the plan was printed, and without the
    line that says the dry run is done."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert refusal in result.stderr, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert plan_line in result.stdout, result.stdout
    assert DRY_RUN_DONE not in result.stdout, result.stdout


# --- family.py init --dry-run --------------------------------------------------

def family_init(tmp_path: Path, *extra: str, into: str = "into",
                dry_run: bool = True, env: dict | None = None,
                local: bool = True):
    return run_script(
        FAMILY, "init", "--org", ORG, "--family", HOLDER,
        "--created-by", "Test Human", "--into", str(tmp_path / into),
        *(["--local-remote-dir", str(tmp_path / "remotes")] if local else []),
        *extra, *(["--dry-run"] if dry_run else []),
        env={**scratch_env(tmp_path), **(env or {})})


def holder_remote(tmp_path: Path) -> Path:
    return tmp_path / "remotes" / f"{HOLDER}.git"


@pytest.mark.parametrize("flag", [[], ["--reuse-empty-repo"]],
                         ids=["no-flag", "reuse-empty-repo"])
def test_init_dry_run_refuses_a_holder_remote_with_commits(tmp_path, flag):
    """The issue's line: on main this exited 0, and the real run then refused
    `family-remote-exists`, leaving an empty `<into>/<Family>/` behind."""
    remote = live_bare(holder_remote(tmp_path))
    before = refs(remote)
    result = family_init(tmp_path, *flag)
    assert_refused_after_the_plan(
        result, f"REFUSED family-remote-exists: {remote.resolve()} already "
                "exists and has commits", "  holder     ")
    assert "it HAS commits, so it is a live repository" in result.stderr
    assert not (tmp_path / "into").exists(), "the dry run made the folder"
    assert refs(remote) == before
    assert list((tmp_path / "tmp").iterdir()) == []


def test_init_dry_run_names_the_flag_for_an_empty_holder_remote(tmp_path):
    remote = empty_bare(holder_remote(tmp_path))
    result = family_init(tmp_path)
    assert_refused_after_the_plan(
        result, f"REFUSED family-remote-exists: {remote.resolve()} already "
                "exists\n", "  holder     ")
    assert "re-run with --reuse-empty-repo" in result.stderr
    assert not (tmp_path / "into").exists()


def test_init_dry_run_reuses_an_empty_holder_remote_when_asked(tmp_path):
    """The flag's answer, said by the dry run as the real run says it, and
    the reserved repository left with zero commits."""
    remote = empty_bare(holder_remote(tmp_path))
    result = family_init(tmp_path, "--reuse-empty-repo")
    assert result.returncode == 0, result.stderr + result.stdout
    reuse = f"  reuse {remote.resolve()} (zero commits)\n"
    assert reuse in result.stdout, result.stdout
    assert result.stdout.index(reuse) < result.stdout.index(DRY_RUN_DONE)
    assert git("rev-list", "--all", cwd=remote).stdout == ""
    assert not (tmp_path / "into").exists()


@pytest.mark.parametrize("state", ["live", "empty"])
def test_init_dry_run_refuses_in_the_real_runs_own_words(tmp_path, state):
    """ONE QUESTION: the dry run's refusal is the real run's, byte for byte,
    because it is the same call."""
    (live_bare if state == "live" else empty_bare)(holder_remote(tmp_path))
    dry = family_init(tmp_path, into="dry")
    real = family_init(tmp_path, into="real", dry_run=False)
    assert dry.returncode == real.returncode == 2, real.stderr + real.stdout
    assert dry.stderr == real.stderr
    assert "REFUSED family-remote-exists: " in dry.stderr


def test_init_dry_run_still_plans_where_no_remote_exists(tmp_path):
    result = family_init(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert "  reuse " not in result.stdout
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "into").exists()


# --- scaffold-project.py --dry-run --------------------------------------------

def scaffold(tmp_path: Path, *extra: str, work: str = "work",
             dry_run: bool = True, env: dict | None = None,
             local: bool = True):
    return run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--work-dir", str(tmp_path / work),
        *(["--local-remote-dir", str(tmp_path / "remotes")] if local else []),
        *extra, *(["--dry-run"] if dry_run else []),
        env={**scratch_env(tmp_path), **(env or {})})


def remote(tmp_path: Path, role: str) -> Path:
    return tmp_path / "remotes" / REPOS[role]


def remotes_there(tmp_path: Path) -> list:
    return sorted(p.name for p in (tmp_path / "remotes").iterdir()
                  if p.name.endswith(".git"))


@pytest.mark.parametrize("flag", [[], ["--reuse-empty-repo"]],
                         ids=["no-flag", "reuse-empty-repo"])
def test_scaffold_dry_run_refuses_a_leg_with_commits(tmp_path, flag):
    """The issue's line: on main the dry run exited 0 here, so
    `setup-project.py` asked for the yes and only step (6) refused."""
    leg = live_bare(remote(tmp_path, "spec"))
    before = refs(leg)
    result = scaffold(tmp_path, *flag)
    assert_refused_after_the_plan(
        result, f"REFUSED scaffold-remote-exists: {leg.resolve()} already "
                "exists and has commits", "legs mounted at spec/ and code/")
    assert "commits other than the one seed this scaffold would push" in (
        result.stderr)
    assert remotes_there(tmp_path) == [REPOS["spec"]]
    assert refs(leg) == before
    assert not (tmp_path / "work").exists()
    assert list((tmp_path / "tmp").iterdir()) == [], (
        "the question's temporary directory was left behind")


def test_scaffold_dry_run_sends_a_root_with_commits_to_adopt(tmp_path):
    root = live_bare(remote(tmp_path, "assembly"))
    result = scaffold(tmp_path, "--reuse-empty-repo")
    assert_refused_after_the_plan(
        result, f"REFUSED scaffold-remote-exists: {root.resolve()} already "
                "exists and has commits", "legs mounted at spec/ and code/")
    assert "adopt-project.py plan" in result.stderr
    assert remotes_there(tmp_path) == [REPOS["assembly"]]


def test_scaffold_dry_run_names_the_flag_for_an_empty_root(tmp_path):
    root = empty_bare(remote(tmp_path, "assembly"))
    result = scaffold(tmp_path)
    assert_refused_after_the_plan(
        result, f"REFUSED scaffold-remote-exists: {root.resolve()} already "
                "exists\n", "legs mounted at spec/ and code/")
    assert "re-run with --reuse-empty-repo" in result.stderr
    assert remotes_there(tmp_path) == [REPOS["assembly"]]


def test_scaffold_dry_run_reuses_empty_repositories_when_asked(tmp_path):
    for role in REPOS:
        empty_bare(remote(tmp_path, role))
    result = scaffold(tmp_path, "--reuse-empty-repo")
    assert result.returncode == 0, result.stderr + result.stdout
    for role in REPOS:
        reuse = f"  reuse {remote(tmp_path, role).resolve()} (zero commits)\n"
        assert reuse in result.stdout, result.stdout
        assert result.stdout.index(reuse) < result.stdout.index(DRY_RUN_DONE)
        assert git("rev-list", "--all", cwd=remote(tmp_path, role)).stdout == ""
    assert not (tmp_path / "work").exists()


def test_scaffold_dry_run_reuses_its_own_seed_and_changes_nothing(
        tmp_path, template):  # noqa: F811
    """A leg whose one commit is this scaffold's seed (#462) is asked as the
    real run asks it, by fetching that commit into a temporary directory:
    the dry run says it would reuse it, and leaves every remote, and the
    temporary directory, as it found them."""
    seeds = refused_at_the_root(tmp_path, template)
    before = {role: refs(bare(tmp_path, role)) for role in REPOS}
    result = scaffold(tmp_path, "--reuse-empty-repo", work="w2")
    assert result.returncode == 0, result.stderr + result.stdout
    for leg, seed in seeds.items():
        assert (f"  reuse {bare(tmp_path, leg).resolve()} (one commit, "
                f"{seed[:12]}: the seed this scaffold pushes)") in result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert {role: refs(bare(tmp_path, role)) for role in REPOS} == before
    assert commits(tmp_path, "assembly") == 0 and tip(tmp_path, "spec")
    assert not (tmp_path / "w2").exists()
    assert list((tmp_path / "tmp").iterdir()) == []


def test_scaffold_dry_run_still_plans_where_no_remote_exists(tmp_path):
    result = scaffold(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert "  reuse " not in result.stdout
    assert not (tmp_path / "remotes").exists()
    assert not (tmp_path / "work").exists()
    assert list((tmp_path / "tmp").iterdir()) == []


@pytest.mark.parametrize("state", ["live leg", "empty root"])
def test_scaffold_dry_run_refuses_in_the_real_runs_own_words(tmp_path, state):
    if state == "live leg":
        live_bare(remote(tmp_path, "code"))
    else:
        empty_bare(remote(tmp_path, "assembly"))
    dry = scaffold(tmp_path, work="dry")
    real = scaffold(tmp_path, work="real", dry_run=False)
    assert dry.returncode == real.returncode == 2, real.stderr + real.stdout
    assert dry.stderr == real.stderr
    assert "REFUSED scaffold-remote-exists: " in dry.stderr


# --- against GitHub: a stub `gh` that answers two reads and nothing else -------

#: `repo view <repo> --json name` and `api repos/<repo>/commits?per_page=1`,
#: the two reads `remote_is_empty` and `_remote_is_empty` make, answered for
#: the one repository in `$STUB_GH_LIVE` (with commits) or `$STUB_GH_EMPTY`
#: (none); `repo view` of any other is GitHub's not-found. Anything else is
#: refused, so a dry run that created or edited a repository fails here.
STUB_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_GH_LOG"
case "$*" in
  "repo view $STUB_GH_LIVE --json name"|"repo view $STUB_GH_EMPTY --json name")
    echo '{"name":"x"}'; exit 0 ;;
  "repo view "*)
    echo "GraphQL: Could not resolve to a Repository (NOT_FOUND)" >&2
    exit 1 ;;
  "api repos/$STUB_GH_LIVE/commits?per_page=1")
    echo '[{"sha":"0123456789abcdef0123456789abcdef01234567"}]'; exit 0 ;;
  "api repos/$STUB_GH_EMPTY/commits?per_page=1")
    echo 'gh: Git Repository is empty. (HTTP 409)' >&2; exit 1 ;;
esac
echo "stub gh: not one of the two reads: $*" >&2
exit 97
"""


def stub_gh(tmp_path: Path, live: str = "-", empty: str = "-"):
    """`(env, calls)`: the stub first on PATH, and a reader of its log."""
    directory = tmp_path / "ghbin"
    directory.mkdir()
    shim = directory / "gh"
    shim.write_text(STUB_GH, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "gh.log"
    env = {"PATH": f"{directory}{os.pathsep}{os.environ['PATH']}",
           "STUB_GH_LOG": str(log), "STUB_GH_LIVE": live,
           "STUB_GH_EMPTY": empty, "GH_TOKEN": "bogus-test",
           "GH_CONFIG_DIR": str(tmp_path / "ghconfig")}

    def calls() -> list:
        return (log.read_text(encoding="utf-8").splitlines()
                if log.exists() else [])
    return env, calls


def viewed(repository: str) -> str:
    return f"repo view {repository} --json name"


def listed(repository: str) -> str:
    return f"api repos/{repository}/commits?per_page=1"


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
def test_init_dry_run_asks_github_and_refuses_a_live_holder(tmp_path):
    repository = f"{ORG}/{HOLDER}"
    env, calls = stub_gh(tmp_path, live=repository)
    result = family_init(tmp_path, env=env, local=False)
    assert_refused_after_the_plan(
        result, f"REFUSED family-remote-exists: {repository} already exists "
                "on GitHub and has commits", "  holder     ")
    assert calls() == [viewed(repository), listed(repository)]
    assert not (tmp_path / "into").exists()


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
def test_init_dry_run_against_github_only_reads(tmp_path):
    env, calls = stub_gh(tmp_path)
    result = family_init(tmp_path, env=env, local=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert calls() == [viewed(f"{ORG}/{HOLDER}")]


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
def test_scaffold_dry_run_asks_github_and_names_the_flag(tmp_path):
    repository = f"{ORG}/{PROJECT}"
    env, calls = stub_gh(tmp_path, empty=repository)
    result = scaffold(tmp_path, env=env, local=False)
    assert_refused_after_the_plan(
        result, f"REFUSED scaffold-remote-exists: {repository} already exists "
                "on GitHub\n", "legs mounted at spec/ and code/")
    assert "re-run with --reuse-empty-repo" in result.stderr
    assert calls() == [viewed(repository), listed(repository)]


@WINDOWS_SKIP  # the `gh` stub is a `#!` script, which Windows does not run
def test_scaffold_dry_run_against_github_only_reads(tmp_path):
    env, calls = stub_gh(tmp_path)
    result = scaffold(tmp_path, env=env, local=False)
    assert result.returncode == 0, result.stderr + result.stdout
    assert DRY_RUN_DONE in result.stdout
    assert calls() == [viewed(f"{ORG}/{name}") for name in
                       (PROJECT, f"{PROJECT}-spec", f"{PROJECT}-code")]
    assert list((tmp_path / "tmp").iterdir()) == []


# --- no `gh` at all: asked in process, on every platform -----------------------

def without_gh(monkeypatch) -> list:
    """`subprocess.run` that cannot start `gh`, as on a machine with none on
    PATH, and runs everything else; returns the `gh` argvs it was asked."""
    asked: list = []
    real = subprocess.run

    def run(argv, *args, **kwargs):
        if list(argv)[:1] == ["gh"]:
            asked.append(list(argv))
            raise FileNotFoundError(2, "No such file or directory", "gh")
        return real(argv, *args, **kwargs)
    monkeypatch.setattr(subprocess, "run", run)
    return asked


def no_gh_run(tmp_path: Path, tool: str, reuse_empty_repo: bool):
    """A tool run with no `gh` on PATH, as `(module, argv, refusal, first)`:
    the tool as a module, its arguments (the caller adds `--dry-run` or not),
    the sentence its refusal opens with, and the one `gh` argv it asks before
    it is refused.

    The scaffold with `--reuse-empty-repo` reads the root's VISIBILITY before
    it asks whether the repositories exist (`_leg_visibility`, then
    `_reusable_remotes`), so it is refused at that read, in other words; every
    other run is refused at `gh repo view --json name`."""
    if tool == "family":
        module = load("dry_run_family", FAMILY)
        argv = ["init", "--org", ORG, "--family", HOLDER, "--created-by",
                "Test Human", "--work-dir", str(tmp_path / "work")]
        repository = f"{ORG}/{HOLDER}"
    else:
        module = load("dry_run_scaffold", SCAFFOLD)
        argv = ["--org", ORG, "--project", PROJECT, "--elected-by",
                "Test Human", "--elected-on", "2026-09-02",
                "--work-dir", str(tmp_path / "work")]
        repository = f"{ORG}/{PROJECT}"
    if reuse_empty_repo:
        argv.append("--reuse-empty-repo")
    reads_visibility = tool == "scaffold" and reuse_empty_repo
    question = (f"what visibility {repository} has on GitHub"
                if reads_visibility
                else f"whether {repository} already exists on GitHub")
    refusal = (f"REFUSED gh-not-found: the `gh` CLI is not on PATH, so "
               f"{question} cannot be asked: ")
    first = ["gh", "repo", "view", repository, "--json",
             "visibility" if reads_visibility else "name"]
    return module, argv, refusal, first


REUSE_EMPTY_REPO = pytest.mark.parametrize(
    "reuse_empty_repo", [False, True], ids=["fresh", "reuse-empty-repo"])


@REUSE_EMPTY_REPO
@pytest.mark.parametrize("tool", ["family", "scaffold"])
def test_a_dry_run_with_no_gh_is_refused_by_name(tmp_path, monkeypatch,
                                                 capsys, tool,
                                                 reuse_empty_repo):
    """The dry run asks `gh` now, and a machine with none on PATH gets
    `gh-not-found`, as a `--pin` read names it, and not a traceback; with and
    without `--reuse-empty-repo`, which the scaffold answers from a different
    `gh` read than it does without it."""
    module, argv, refusal, first = no_gh_run(tmp_path, tool, reuse_empty_repo)
    asked = without_gh(monkeypatch)
    assert module.main([*argv, "--dry-run"]) == 2
    captured = capsys.readouterr()
    assert refusal in captured.err, captured.err
    assert "put `gh` on PATH, logged in" in captured.err
    assert DRY_RUN_DONE not in captured.out
    assert asked == [first]
    assert not (tmp_path / "work").exists()


@REUSE_EMPTY_REPO
@pytest.mark.parametrize("tool", ["family", "scaffold"])
def test_a_real_run_with_no_gh_is_refused_in_the_dry_runs_words(
        tmp_path, monkeypatch, capsys, tool, reuse_empty_repo):
    """The real run asks the same question first and gets the same refusal:
    `gh-not-found`, in the dry run's own words, after the one `gh` read it
    shares with the dry run and before any `gh repo create`; not a
    `FileNotFoundError` traceback, which `--reuse-empty-repo` gave the
    scaffold before the visibility read refused by name."""
    module, argv, refusal, first = no_gh_run(tmp_path, tool, reuse_empty_repo)
    asked = without_gh(monkeypatch)
    assert module.main(argv) == 2
    captured = capsys.readouterr()
    assert refusal in captured.err, captured.err
    assert "put `gh` on PATH, logged in" in captured.err
    assert asked == [first]
