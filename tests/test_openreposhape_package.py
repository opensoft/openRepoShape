# SPDX-License-Identifier: Apache-2.0
"""The openreposhape package (#563): its five commands, its stamp, its clone
of the standard, and the PATH its children get.

THE LAUNCHER'S CASES FIRST, UNCHANGED. `tests/test_openreposhape_command.py`
states the bash `openRepoShape`'s rules; the cases that run it through its
`run_cmd` are imported below, so pytest collects them here as well. A test
function reads `run_cmd` and `USAGE_LINES` from its OWN module when it runs,
so `the_python_command`, autouse here and only here, points both at the
package's `openRepoShape` for each test this module collects: one case, one
rule, both commands, and not a line of the launcher's module changed for
it. This module carries no Windows skip, so those cases run on the Windows
job too, where the launcher's own module skips. The four launcher cases that
run its FILE (from stdin, or by its path) are re-stated below for this
command.

`PythonCommand`, called, runs the package from this checkout's `src/`,
where it sits BESIDE a checkout of the standard and uses this one, as the
launcher uses the `setup.sh` beside it; `detached`, it runs an installed
copy of the package (its modules and `setup-project.py`, laid out as the
wheel lays them out) from a directory that is no checkout.

THEN THE PACKAGE'S OWN. A SYNTHETIC STANDARD stands in for this repository:
a bare repository whose tools are stubs that print what they were handed,
at three refs (the `PINNED` tag, the `OTHER` branch and `main`), with this
checkout's own `scripts/repo_shape.py`, because the package computes a
clone's digest with the clone's own module. A test stamps its installed copy
with that standard's commit and digest, or leaves it unstamped.

OFFLINE, LIKE THE REST OF THIS SUITE. Every clone is of a bare repository on
disk, and every cache is under the test's own directory: `$XDG_CACHE_HOME`,
`%LOCALAPPDATA%` and, for macOS's `~/Library/Caches`, `$HOME`. Nothing here
builds the wheel or installs it: that needs a build backend and
git-filter-repo from PyPI, so the `package` job in
`.github/workflows/tests.yml` does it, outside pytest.
"""

from __future__ import annotations

import ast
import importlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

import test_openreposhape_command as launcher_cases
from conftest import REPO, git
from repo_shape import tree_digest
# THE LAUNCHER'S CASES, collected again in this module, where
# `the_python_command` runs them against the package's command.
from test_openreposhape_command import (
    test_a_bare_run_prints_the_usage_and_exits_one,
    test_a_family_value_is_never_taken_as_the_project,
    test_any_scaffold_argument_keeps_the_old_behaviour,
    test_help_prints_every_usage_line,
    test_help_still_exits_zero,
    test_it_scaffolds_through_setup_sh,
    test_no_org_and_no_terminal_refuses_before_setup_sh_runs,
    test_no_project_and_no_terminal_refuses_with_the_usage,
    test_preflight_forwards_an_org_it_was_given,
    test_preflight_passes_through_without_an_org,
    test_scaffold_flags_after_a_double_dash_still_reach_the_scaffold,
    test_the_org_can_come_from_the_environment,
    test_two_modes_is_a_refusal_not_last_wins,
)
from test_openreposhape_command import USAGE_LINES as LAUNCHER_USAGE
from test_openreposhape_command import command_env

#: The launcher's cases this module runs again, named once more: they are
#: imported for pytest to collect, and nothing here calls them.
LAUNCHER_CASES = (
    test_a_bare_run_prints_the_usage_and_exits_one,
    test_a_family_value_is_never_taken_as_the_project,
    test_any_scaffold_argument_keeps_the_old_behaviour,
    test_help_prints_every_usage_line,
    test_help_still_exits_zero,
    test_it_scaffolds_through_setup_sh,
    test_no_org_and_no_terminal_refuses_before_setup_sh_runs,
    test_no_project_and_no_terminal_refuses_with_the_usage,
    test_preflight_forwards_an_org_it_was_given,
    test_preflight_passes_through_without_an_org,
    test_scaffold_flags_after_a_double_dash_still_reach_the_scaffold,
    test_the_org_can_come_from_the_environment,
    test_two_modes_is_a_refusal_not_last_wins,
)

SOURCE = REPO / "src"
PACKAGE = SOURCE / "openreposhape"

#: The package's first usage line, where the launcher's says what
#: `--install` places; the other four are the launcher's own.
USAGE_FIRST = ("openRepoShape --install            refused here: pipx "
               "upgrade openreposhape updates it")

#: What a console script does, for the entry named: the package's directory
#: first on `sys.path`, then the function. `-B`, so no bytecode lands in
#: this checkout's `src/`.
BOOT = ("import sys; sys.path.insert(0, sys.argv.pop(1)); "
        "import openreposhape.cli as cli; sys.exit(cli.{entry}())")

#: The synthetic standard's refs, as `test_openreposhape_command.py` names
#: its own.
PINNED = "v9.9.9"
OTHER = "other"

#: The tools a stub stands in for, each named as the package runs it.
TOOLS = ("setup-project.py", "scaffold-project.py", "adopt-project.py",
         "update-shape.py", "shape-doctor.py")

#: Every stub: one line, `STUB {json}`, naming the file, the ref it was
#: committed at, its arguments, where it ran, what it finds of
#: git-filter-repo, the first PATH entry and the hand-over variable; then
#: `$STUB_SIGNAL` sent to itself where it is set, or `$STUB_EXIT`, so a test
#: sees an exit status travel back.
STUB = '''\
import json, os, shutil, sys
print("STUB " + json.dumps({
    "tool": os.path.basename(__file__), "at": AT, "argv": sys.argv[1:],
    "cwd": os.getcwd(), "filter_repo": shutil.which("git-filter-repo"),
    "path0": os.environ.get("PATH", "").split(os.pathsep)[0],
    "self_bootstrap": os.environ.get("OPENREPOSHAPE_SELF_BOOTSTRAP")}),
    flush=True)
if os.environ.get("STUB_SIGNAL"):
    os.kill(os.getpid(), int(os.environ["STUB_SIGNAL"]))
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
'''


# --- the package, run ---------------------------------------------------------

def installed_copy(directory: Path, stamp: dict | None = None) -> Path:
    """The package as the wheel lays it out, under `<directory>/site`: its
    modules, `setup-project.py` beside them, and `stamp` (`version`, `tag`,
    `commit`, `digest`) written into `_release.py` where one is given. The
    directory above `site` is no checkout, so the copy is not BESIDE one."""
    package = directory / "site" / "openreposhape"
    package.mkdir(parents=True)
    for module in sorted(PACKAGE.glob("*.py")):
        shutil.copyfile(module, package / module.name)
    shutil.copyfile(REPO / "setup-project.py", package / "setup-project.py")
    if stamp is not None:
        (package / "_release.py").write_bytes("".join(
            f'{name.upper()} = "{stamp[name]}"\n'
            for name in ("version", "tag", "commit", "digest")).encode())
    return package.parent


def package_env(tmp_path: Path, home: Path | None = None,
                env: dict | None = None, detached: bool = False) -> dict:
    """`command_env`, with every per-user cache the package could reach
    under `tmp_path`. `HOME` too for a DETACHED run, where it is where
    macOS keeps the cache; a run beside the checkout keeps the person's."""
    caches = {"XDG_CACHE_HOME": str(tmp_path / "cache" / "xdg"),
              "LOCALAPPDATA": str(tmp_path / "cache" / "local")}
    if detached and home is None:
        home = tmp_path / "home"
    return command_env(home=home, setup_sh=None, env={**caches, **(env or {})})


def cache_dir(tmp_path: Path) -> Path:
    """Where `package_env` puts a detached run's clones, by the platform's
    own rule, said here a second time so the package's is checked."""
    if os.name == "nt":
        return tmp_path / "cache" / "local" / "openreposhape" / "checkouts"
    if sys.platform == "darwin":
        return (tmp_path / "home" / "Library" / "Caches" / "openreposhape"
                / "checkouts")
    return tmp_path / "cache" / "xdg" / "openreposhape" / "checkouts"


def run_package(site: Path, entry: str, args, env: dict,
                cwd: Path | None = None,
                python: Path | str = sys.executable
                ) -> subprocess.CompletedProcess:
    """The console script `entry` of the package at `site`, run as a person
    runs one: stdin a pipe, and a session of its own (no terminal)."""
    return subprocess.run(
        [str(python), "-B", "-c", BOOT.format(entry=entry), str(site),
         *args], capture_output=True, encoding="utf-8", errors="replace",
        check=False, input="", cwd=str(cwd) if cwd else None, env=env,
        start_new_session=True)


class PythonCommand:
    """The package's `openRepoShape`, run as the launcher's `run_cmd` runs
    the bash one: called with the same keywords, of which `setup_sh` and
    `command` mean nothing here, because this command fetches no `setup.sh`
    and has no file of its own to run.

    Either way `$OPENREPOSHAPE_REPO` names a repository that does not exist,
    unless the test names one, so a run that reached for a clone it should
    not need fails on disk rather than asking github.com where main is; and
    either way it runs in the test's own directory, so a scaffold that lost
    its `--into` lands there and never in this checkout."""

    usage_lines = (USAGE_FIRST, *LAUNCHER_USAGE[1:])

    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path

    def nowhere(self, env: dict | None) -> dict:
        """`env` over a `$OPENREPOSHAPE_REPO` that does not exist."""
        return {"OPENREPOSHAPE_REPO": str(self.tmp_path / "nowhere.git"),
                **(env or {})}

    def __call__(self, *args: str, home: Path | None = None,
                 env: dict | None = None, setup_sh: Path | None = None,
                 command: Path | None = None) -> subprocess.CompletedProcess:
        return run_package(SOURCE, "openreposhape", args,
                           package_env(self.tmp_path, home,
                                       self.nowhere(env)),
                           cwd=self.tmp_path)

    def detached(self, *args: str, home: Path | None = None,
                 env: dict | None = None,
                 cwd: Path | None = None) -> subprocess.CompletedProcess:
        site = self.tmp_path / "package" / "site"
        if not site.is_dir():
            installed_copy(self.tmp_path / "package")
        return run_package(site, "openreposhape", args,
                           package_env(self.tmp_path, home,
                                       self.nowhere(env), detached=True),
                           cwd=cwd or self.tmp_path)


@pytest.fixture
def cmd(tmp_path) -> PythonCommand:
    return PythonCommand(tmp_path)


@pytest.fixture(autouse=True)
def the_python_command(monkeypatch, cmd) -> None:
    """For each test THIS module collects, the launcher's module runs the
    package's command: its `run_cmd` is `cmd`, and the usage lines it
    expects are this command's. Put back after every test, so the
    launcher's own module, collected on its own, runs the bash command."""
    monkeypatch.setattr(launcher_cases, "run_cmd", cmd)
    monkeypatch.setattr(launcher_cases, "USAGE_LINES", cmd.usage_lines)


def stub_report(stdout: str) -> dict:
    """What the one stub that ran said about itself."""
    reports = [json.loads(line[len("STUB "):]) for line in stdout.splitlines()
               if line.startswith("STUB ")]
    assert len(reports) == 1, stdout
    return reports[0]


def said(result: subprocess.CompletedProcess) -> str:
    """stderr with its line breaks folded, for a refusal's sentences."""
    return " ".join(result.stderr.split())


# --- the synthetic standard -----------------------------------------------------

class Standard:
    """A bare repository on disk, its commit at each ref, and the
    `sorted-ls-tree-r-v1` digest of each commit's tree."""

    def __init__(self, bare: Path, commits: dict, digests: dict) -> None:
        self.bare = bare
        self.commits = commits
        self.digests = digests

    def stamp(self, ref: str = PINNED, **changed) -> dict:
        """The stamp a release at `ref` would carry, with `changed` over it."""
        return {"version": "9.9.9", "tag": PINNED,
                "commit": self.commits[ref], "digest": self.digests[ref],
                **changed}


def make_standard(directory: Path) -> Standard:
    """`PINNED` (a tag), then `OTHER` (a branch off it), then `main`, each a
    commit of every stub saying which ref it is."""
    seed = directory / "seed"
    seed.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=seed)
    (seed / "scripts").mkdir()
    shutil.copyfile(REPO / "scripts" / "repo_shape.py",
                    seed / "scripts" / "repo_shape.py")
    commits, digests = {}, {}

    def commit(name: str) -> None:
        for tool in TOOLS:
            (seed / tool).write_text(f"AT = {name!r}\n" + STUB,
                                     encoding="utf-8")
        git("add", "-A", cwd=seed)
        git("commit", "-q", "-m", name, cwd=seed)
        commits[name] = git("rev-parse", "HEAD", cwd=seed).stdout.strip()
        digests[name] = tree_digest(seed, commits[name])

    commit(PINNED)
    git("tag", PINNED, cwd=seed)
    git("switch", "-q", "-c", OTHER, cwd=seed)
    commit(OTHER)
    git("switch", "-q", "main", cwd=seed)
    commit("main")
    bare = directory / "standard.git"
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=directory)
    return Standard(bare, commits, digests)


@pytest.fixture(scope="module")
def shape_standard(tmp_path_factory) -> Standard:
    """One synthetic standard for the module: every test only clones it."""
    return make_standard(tmp_path_factory.mktemp("standard"))


def stamped_run(tmp_path: Path, standard: Standard, args, *,
                stamp: dict | None = None, entry: str = "openreposhape",
                env: dict | None = None, cwd: Path | None = None,
                site: Path | None = None) -> subprocess.CompletedProcess:
    """`entry` of a copy stamped at `PINNED` (or with `stamp`), cloning from
    the synthetic standard, in `cwd` (the test's directory by default)."""
    if site is None:
        site = installed_copy(tmp_path / "package",
                              standard.stamp() if stamp is None else stamp)
    return run_package(site, entry, args, package_env(
        tmp_path, env={"OPENREPOSHAPE_REPO": str(standard.bare),
                       **(env or {})}, detached=True), cwd=cwd or tmp_path)


# --- the stamp and the build ------------------------------------------------------

def stamp_values(source: bytes) -> dict:
    """The names `_release.py` assigns, and their values."""
    return {node.targets[0].id: node.value.value
            for node in ast.parse(source).body
            if isinstance(node, ast.Assign)}


def test_the_committed_stamp_is_unstamped():
    """0.0.0, and no tag, commit or digest: a build from a checkout, which
    the release workflow refuses to publish. A release build writes the four
    values; nothing commits them."""
    assert stamp_values((PACKAGE / "_release.py").read_bytes()) == {
        "VERSION": "0.0.0", "TAG": "", "COMMIT": "", "DIGEST": ""}


def test_pyproject_takes_its_version_from_the_stamp_and_names_five_commands(
        monkeypatch):
    """The version is written once, in the stamp; the one dependency is the
    git-filter-repo CI runs and install.sh installs; the wheel is the
    package plus `setup-project.py` beside its modules; and each of the five
    commands names a function the package has."""
    tomllib = pytest.importorskip("tomllib")
    data = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert project["name"] == "openreposhape"
    assert project["dynamic"] == ["version"]
    assert "version" not in project
    assert project["requires-python"] == ">=3.9"
    assert project["dependencies"] == ["git-filter-repo==2.47.0"]
    assert 'FILTER_REPO_PIN="git-filter-repo==2.47.0"' in \
        (REPO / "install.sh").read_text(encoding="utf-8")
    assert data["build-system"] == {"requires": ["hatchling==1.27.0"],
                                    "build-backend": "hatchling.build"}
    hatch = data["tool"]["hatch"]
    assert hatch["version"] == {"path": "src/openreposhape/_release.py"}
    # hatchling's own default pattern for a version file, read against the
    # stamp: the version it finds is the stamp's.
    found = re.search(r"(?i)^(__version__|VERSION) *= *(['\"])v?"
                      r"(?P<version>.+?)\2",
                      (PACKAGE / "_release.py").read_text(encoding="utf-8"),
                      re.M)
    assert found is not None
    assert found.group("version") == "0.0.0"
    wheel = hatch["build"]["targets"]["wheel"]
    assert wheel["packages"] == ["src/openreposhape"]
    assert wheel["force-include"] == {
        "setup-project.py": "openreposhape/setup-project.py"}
    scripts = project["scripts"]
    assert sorted(scripts) == ["adopt-project", "openRepoShape",
                               "scaffold-project", "shape-doctor",
                               "update-shape"]
    cli = package_module("cli", monkeypatch)
    for name, target in scripts.items():
        module, _, function = target.partition(":")
        assert module == "openreposhape.cli", name
        assert callable(getattr(cli, function)), name


def test_a_stamp_that_names_part_of_a_release_is_refused(tmp_path):
    """A commit with no digest would run unchecked: the whole stamp or
    none of it."""
    site = installed_copy(tmp_path, {"version": "9.9.9", "tag": PINNED,
                                     "commit": "a" * 40, "digest": ""})
    result = run_package(site, "openreposhape", ["--version"],
                         package_env(tmp_path, detached=True))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "names part of a release and not all of it" in said(result)
    assert result.stdout == ""


# --- --version ----------------------------------------------------------------------

def test_version_names_the_release_and_clones_nothing(tmp_path,
                                                      shape_standard):
    """The version, the tag, the commit, the digest and the clone, from the
    stamp alone: no network and no clone, before the first run or after."""
    stamp = shape_standard.stamp()
    result = stamped_run(tmp_path, shape_standard, ["--version"])
    assert result.returncode == 0, result.stdout + result.stderr
    clone = cache_dir(tmp_path) / stamp["commit"]
    assert result.stdout.splitlines() == [
        f"openRepoShape 9.9.9 ({shape_standard.bare} @ {stamp['commit']})",
        "  version   9.9.9",
        f"  tag       {PINNED}",
        f"  commit    {stamp['commit']}",
        f"  digest    {stamp['digest']} (sorted-ls-tree-r-v1)",
        f"  checkout  {clone} (not cloned yet: the first run that needs it "
        "clones it)"]
    assert not cache_dir(tmp_path).exists()


def test_version_says_an_unstamped_build_follows_main(cmd):
    """`$OPENREPOSHAPE_REPO` set EMPTY is unset, the shell's
    `${VAR:-default}`: the default repository, named."""
    result = cmd.detached("--version", env={"OPENREPOSHAPE_REPO": ""})
    assert result.returncode == 0, result.stderr
    lines = result.stdout.splitlines()
    assert lines[0] == "openRepoShape 0.0.0 (opensoft/openRepoShape @ main)"
    assert "  version   0.0.0, unstamped: a build from a checkout, not a " \
        "release, so it follows main" in lines


def test_version_beside_a_checkout_names_the_checkout(cmd):
    result = cmd("--version", env={"OPENREPOSHAPE_REF": OTHER})
    assert result.returncode == 0, result.stderr
    assert f"  checkout  {REPO}: this package sits in it, so every run uses " \
        "it as it stands and clones nothing" in result.stdout.splitlines()


# --- the launcher's cases that run its FILE, for this command -----------------------

def test_the_install_line_keeps_the_launchers_description_column(cmd):
    """The launcher's column rule (#546) for this command's usage: the
    `--install` line describes itself in the column `--preflight`'s does,
    and the doctor's description sits under its form, in that column."""
    lines = cmd("--help").stdout.splitlines()
    column = LAUNCHER_USAGE[1].index("check this MACHINE")
    assert lines[0] == USAGE_FIRST
    assert USAGE_FIRST.index("refused here") == column
    doctor = lines.index(LAUNCHER_USAGE[2])
    assert lines[doctor + 1] == \
        " " * column + "diagnose a REPOSITORY against this standard"


def test_a_bare_run_asks_nothing_of_git_gh_or_curl(cmd, tmp_path):
    """The usage, exit 1, and NO CALL: a `git`, a `gh` and a `curl` that
    log every call stand first on PATH (a POSIX script and a `.cmd` each),
    and the log must not exist afterwards. DETACHED, where the standard is
    a clone and so a git call away, with the repository nowhere: a bare run
    that reached for its standard would log a `git ls-remote` here."""
    log = tmp_path / "calls.log"
    fakes = tmp_path / "fakes"
    fakes.mkdir()
    for name in ("git", "gh", "curl"):
        posix = fakes / name
        posix.write_bytes(f"#!/bin/sh\necho {name} \"$*\" >> '{log}'\n"
                          "exit 1\n".encode("utf-8"))
        posix.chmod(0o755)
        (fakes / f"{name}.cmd").write_bytes(
            f'@echo {name} %* >> "{log}"\r\n@exit /b 1\r\n'.encode("utf-8"))
    result = cmd.detached(
        env={"PATH": f"{fakes}{os.pathsep}{os.environ['PATH']}"})
    assert result.returncode == 1, result.stdout + result.stderr
    assert USAGE_FIRST in result.stdout.splitlines()
    assert not log.exists(), log.read_text(encoding="utf-8")


@pytest.mark.parametrize("ref", ["-x", "--upload-pack=touch /tmp/pwned",
                                 "a" * 256, "refs/heads/..", "x.lock",
                                 "v1\nforged"])
def test_a_ref_is_checked_before_anything_is_cloned(cmd, tmp_path, ref):
    """`$OPENREPOSHAPE_REF` reaches `git checkout`, so it is checked first,
    in the launcher's three steps and its words. The repository named here
    does not exist, so a ref that got past the check would fail on the
    clone instead; the over-long and the two-line value are not echoed."""
    result = cmd.detached("--doctor", ".", env={
        "OPENREPOSHAPE_REPO": str(tmp_path / "never-cloned.git"),
        "OPENREPOSHAPE_REF": ref})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "$OPENREPOSHAPE_REF" in result.stderr
    assert "git checkout" in result.stderr
    assert "clone" not in said(result)
    assert "a" * 256 not in result.stderr
    assert "forged" not in result.stderr


def test_a_standard_with_no_doctor_is_refused_by_name(cmd, tmp_path):
    """A ref of the standard older than `shape-doctor.py` is refused by
    name, and the way out is a ref that carries it."""
    seed = tmp_path / "seed"
    seed.mkdir()
    git("init", "-q", "-b", "main", cwd=seed)
    (seed / "README.md").write_bytes(b"# an older standard\n")
    git("add", "-A", cwd=seed)
    git("commit", "-q", "-m", "before the doctor", cwd=seed)
    bare = tmp_path / "old.git"
    git("clone", "-q", "--bare", str(seed), str(bare), cwd=tmp_path)
    result = cmd.detached("--doctor", ".",
                          env={"OPENREPOSHAPE_REPO": str(bare)})
    assert result.returncode == 2, result.stdout + result.stderr
    assert "has no shape-doctor.py, so there is nothing to run" \
        in said(result)
    assert "Set $OPENREPOSHAPE_REF to a ref that carries it" in said(result)


def test_version_names_the_ref_set_for_the_run(cmd):
    result = cmd.detached("--version", env={"OPENREPOSHAPE_REF": "v1.2.3",
                                            "OPENREPOSHAPE_REPO": ""})
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines()[0] == \
        "openRepoShape 0.0.0 (opensoft/openRepoShape @ v1.2.3)"


# --- the clone: once per commit, and checked before every run ------------------------

def test_a_stamped_run_clones_its_commit_once_and_runs_from_it(
        tmp_path, shape_standard):
    """The first run clones the stamped commit into the cache and runs the
    clone's own tool; the second uses that clone as it is, and asks the
    repository nothing: it answers with the repository gone."""
    commit = shape_standard.stamp()["commit"]
    clone = cache_dir(tmp_path) / commit
    first = stamped_run(tmp_path, shape_standard, ["--doctor", "."])
    assert first.returncode == 0, first.stdout + first.stderr
    assert stub_report(first.stdout)["at"] == PINNED
    assert f"openRepoShape: cloning {shape_standard.bare} into " \
        f"{cache_dir(tmp_path)}, once for commit {commit}" in said(first)
    second = run_package(
        tmp_path / "package" / "site", "openreposhape", ["--doctor", "."],
        package_env(tmp_path, detached=True,
                    env={"OPENREPOSHAPE_REPO": str(tmp_path / "gone.git")}),
        cwd=tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    assert stub_report(second.stdout)["at"] == PINNED
    assert "cloning" not in second.stderr
    assert sorted(cache_dir(tmp_path).iterdir()) == [clone], (
        "a clone half made, or a second one, was left in the cache")
    assert git("rev-parse", "HEAD", cwd=clone).stdout.strip() == commit


def test_the_clone_is_full(tmp_path, shape_standard):
    """A FULL clone, never a shallow one: the doctor's currency row compares
    commits, and `update-shape.py` reads the standard's history. Cloned
    through a `file://` URL, because git ignores `--depth` in a clone from a
    plain path, so only a URL would show a shallow one: every commit of the
    standard is there, the stamped commit's parent and the other branch's
    included."""
    result = stamped_run(
        tmp_path, shape_standard, ["--doctor", "."],
        env={"OPENREPOSHAPE_REPO": shape_standard.bare.as_uri()})
    assert result.returncode == 0, result.stdout + result.stderr
    clone = cache_dir(tmp_path) / shape_standard.stamp()["commit"]
    assert git("rev-parse", "--is-shallow-repository",
               cwd=clone).stdout.strip() == "false"
    for ref, commit in shape_standard.commits.items():
        assert git("cat-file", "-e", commit, cwd=clone,
                   check=False).returncode == 0, f"{ref} ({commit}) is missing"


def test_a_clone_a_killed_run_left_is_swept_once_an_hour_has_passed(
        tmp_path, shape_standard):
    """A run killed mid-clone leaves its `.incoming-*` directory beside the
    clones. The next run that clones removes one nothing has touched for an
    hour, and leaves a newer one alone: another run may be cloning into it
    right now."""
    cache = cache_dir(tmp_path)
    old, new = cache / ".incoming-old", cache / ".incoming-new"
    for leftover in (old, new):
        (leftover / ".git").mkdir(parents=True)
        (leftover / ".git" / "HEAD").write_text("ref: refs/heads/main\n",
                                                encoding="utf-8")
    two_hours_ago = time.time() - 2 * 3600
    os.utime(old, (two_hours_ago, two_hours_ago))
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."])
    assert result.returncode == 0, result.stdout + result.stderr
    assert not old.exists(), "the killed run's leftover was not swept"
    assert (new / ".git" / "HEAD").is_file(), "a fresh one was swept"
    assert sorted(path.name for path in cache.iterdir()) == sorted(
        [new.name, shape_standard.stamp()["commit"]])


def test_a_clone_whose_digest_is_not_the_stamped_one_is_refused(
        tmp_path, shape_standard):
    """The digest is the clone's own `repo_shape.tree_digest`, compared with
    the stamp's; a clone that digests to anything else runs nothing."""
    wrong = "0" * 64
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."],
                         stamp=shape_standard.stamp(digest=wrong))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"its tree digests to {shape_standard.digests[PINNED]} " \
        f"(sorted-ls-tree-r-v1), not to {wrong}, the digest this package " \
        "was stamped with, so nothing was run from it" in said(result)
    assert "STUB" not in result.stdout


@pytest.mark.parametrize("change", ["modified", "untracked"])
def test_a_clone_with_changes_is_refused_and_left_as_it_is(
        tmp_path, shape_standard, change):
    """A run uses the commit exactly as it was made. A clone somebody
    changed, an untracked file included, runs nothing and is not repaired:
    what changed is theirs to look at first."""
    assert stamped_run(tmp_path, shape_standard,
                       ["--doctor", "."]).returncode == 0
    clone = cache_dir(tmp_path) / shape_standard.stamp()["commit"]
    name = "shape-doctor.py" if change == "modified" else "extra.txt"
    with open(clone / name, "ab") as handle:
        handle.write(b"# a change\n")
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."],
                         site=tmp_path / "package" / "site")
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"has changes ({name}), so nothing was run from it" in said(result)
    assert "Delete it and run this again" in said(result)
    assert "STUB" not in result.stdout
    assert (clone / name).read_bytes().endswith(b"# a change\n")


def test_a_clone_at_another_commit_is_refused(tmp_path, shape_standard):
    assert stamped_run(tmp_path, shape_standard,
                       ["--doctor", "."]).returncode == 0
    clone = cache_dir(tmp_path) / shape_standard.stamp()["commit"]
    git("checkout", "-q", "--detach", shape_standard.commits["main"],
        cwd=clone)
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."],
                         site=tmp_path / "package" / "site")
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"and it is at {shape_standard.commits['main']}, so nothing was " \
        "run from it" in said(result)
    assert "STUB" not in result.stdout


def test_a_commit_the_repository_lacks_leaves_nothing_in_the_cache(
        tmp_path, shape_standard):
    """The clone is made beside its place and moved in whole, so a clone
    that could not check out the commit leaves nothing to mistake for one."""
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."],
                         stamp=shape_standard.stamp(commit="b" * 40))
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"could not check out '{'b' * 40}'" in said(result)
    assert list(cache_dir(tmp_path).iterdir()) == []


# --- which commit -------------------------------------------------------------------

@pytest.mark.parametrize("ref", [OTHER, "main", PINNED])
def test_the_variable_overrides_the_stamp_for_one_run(tmp_path,
                                                      shape_standard, ref):
    """`$OPENREPOSHAPE_REF` names another branch, tag or commit for the run
    it is set for, and no digest is checked then: the stamped digest is the
    stamped commit's. (The stamp's digest here is wrong, which a stamped run
    would refuse.)"""
    stamp = shape_standard.stamp(digest="0" * 64)
    result = stamped_run(tmp_path, shape_standard, ["--doctor", "."],
                         stamp=stamp, env={"OPENREPOSHAPE_REF": ref})
    assert result.returncode == 0, result.stdout + result.stderr
    assert stub_report(result.stdout)["at"] == ref
    version = stamped_run(tmp_path, shape_standard, ["--version"],
                          site=tmp_path / "package" / "site",
                          env={"OPENREPOSHAPE_REF": ref})
    assert f"({shape_standard.bare} @ {ref})" in version.stdout
    assert f"  ref       {ref}, from $OPENREPOSHAPE_REF, for this run " \
        "instead of the commit above; no digest is checked" in version.stdout


def test_a_ref_that_is_a_tag_and_a_branch_is_the_tag(tmp_path):
    """A name that is a tag AND a branch is the tag, which is what `git
    checkout` in a fresh clone makes of it; an annotated tag is read through
    to its commit (`^{}`), never taken for one, by its short name and by
    its full `refs/tags/` name alike."""
    standard = make_standard(tmp_path / "both")
    commits = standard.commits
    git("branch", PINNED, commits[OTHER], cwd=standard.bare)
    git("tag", "-a", "-m", "annotated", "annotated", commits[OTHER],
        cwd=standard.bare)
    git("branch", "annotated", commits["main"], cwd=standard.bare)
    site = installed_copy(tmp_path / "package", standard.stamp())
    for ref, at in ((PINNED, PINNED), ("annotated", OTHER),
                    ("refs/tags/annotated", OTHER)):
        result = stamped_run(tmp_path, standard, ["--doctor", "."],
                             site=site, env={"OPENREPOSHAPE_REF": ref})
        assert result.returncode == 0, result.stdout + result.stderr
        assert stub_report(result.stdout)["at"] == at, ref


def test_an_unstamped_build_follows_main(tmp_path):
    """Each run asks the repository where main is: a commit landing there
    is the next run's standard, in a clone of its own."""
    standard = make_standard(tmp_path / "moving")
    site = installed_copy(tmp_path / "package")
    env = package_env(tmp_path, detached=True,
                      env={"OPENREPOSHAPE_REPO": str(standard.bare)})
    first = run_package(site, "openreposhape", ["--doctor", "."], env,
                        cwd=tmp_path)
    assert first.returncode == 0, first.stdout + first.stderr
    assert stub_report(first.stdout)["at"] == "main"
    seed = tmp_path / "moving" / "seed"
    (seed / "shape-doctor.py").write_text("AT = 'main, later'\n" + STUB,
                                          encoding="utf-8")
    git("commit", "-q", "-am", "later", cwd=seed)
    git("push", "-q", str(standard.bare), "main", cwd=seed)
    later = git("rev-parse", "HEAD", cwd=seed).stdout.strip()
    second = run_package(site, "openreposhape", ["--doctor", "."], env,
                         cwd=tmp_path)
    assert second.returncode == 0, second.stdout + second.stderr
    assert stub_report(second.stdout)["at"] == "main, later"
    assert sorted(path.name for path in cache_dir(tmp_path).iterdir()) == \
        sorted([standard.commits["main"], later])


# --- the five commands ------------------------------------------------------------

@pytest.mark.parametrize("entry, tool", [
    ("scaffold_project", "scaffold-project.py"),
    ("adopt_project", "adopt-project.py"),
    ("update_shape", "update-shape.py"),
    ("shape_doctor", "shape-doctor.py"),
])
def test_each_tool_command_runs_its_file_with_every_argument_unchanged(
        tmp_path, shape_standard, entry, tool):
    """The clone's own file, every argument as typed (an empty one, a `--`
    and a flag after it included), in the directory the command was typed
    in, and the file's exit status back."""
    args = ["plan", "--source", "a path/with a space", "--", "-x", "",
            "--json"]
    typed_in = tmp_path / "typed here"
    typed_in.mkdir()
    result = stamped_run(tmp_path, shape_standard, args, entry=entry,
                         env={"STUB_EXIT": "7"}, cwd=typed_in)
    assert result.returncode == 7, result.stdout + result.stderr
    report = stub_report(result.stdout)
    assert (report["tool"], report["at"]) == (tool, PINNED)
    assert report["argv"] == args
    assert Path(report["cwd"]).resolve() == typed_in.resolve()


@pytest.mark.skipif(os.name == "nt", reason="a POSIX signal's exit status: "
                    "Windows ends a process with the status it is handed")
def test_a_tool_killed_by_a_signal_exits_128_plus_the_signal(
        tmp_path, shape_standard):
    """As a shell reports it: a tool ended by SIGTERM exits 143, never the
    -15 `subprocess` reports, which an exit status would wrap to 241."""
    result = stamped_run(tmp_path, shape_standard, ["--json"],
                         entry="shape_doctor",
                         env={"STUB_SIGNAL": str(int(signal.SIGTERM))})
    assert result.returncode == 128 + signal.SIGTERM, (
        result.stdout + result.stderr)
    assert stub_report(result.stdout)["tool"] == "shape-doctor.py"


def test_a_scaffold_hands_over_to_the_clones_setup_project(tmp_path,
                                                          shape_standard):
    """setup.sh's hand-over from a clone it made: `--into` where the
    command was typed, FIRST, so a later one of the person's wins; then
    `--org` and `--project`; then every other argument; and
    `$OPENREPOSHAPE_SELF_BOOTSTRAP=1`, because no fork origin stands behind
    the person."""
    typed_in = tmp_path / "here"
    typed_in.mkdir()
    result = stamped_run(tmp_path, shape_standard,
                         ["Atlas", "--org", "TestOrg", "--visibility",
                          "private", "--", "--reference", "x.md"],
                         cwd=typed_in)
    assert result.returncode == 0, result.stdout + result.stderr
    report = stub_report(result.stdout)
    assert (report["tool"], report["at"]) == ("setup-project.py", PINNED)
    assert report["argv"][0] == "--into"
    assert Path(report["argv"][1]).resolve() == typed_in.resolve()
    assert report["argv"][2:] == ["--org", "TestOrg", "--project", "Atlas",
                                  "--visibility", "private", "--",
                                  "--reference", "x.md"]
    assert report["self_bootstrap"] == "1"
    commit = shape_standard.stamp()["commit"]
    assert f"openRepoShape: the standard is {shape_standard.bare} at " \
        f"{commit}, cloned at {cache_dir(tmp_path) / commit}." \
        in result.stdout.splitlines()


def test_a_typed_shape_ref_is_the_ref_of_the_scaffolds_clone(
        tmp_path, shape_standard):
    """`--shape-ref` reached setup.sh after the launcher's own ref, so it
    named the ref of the scaffold's clone. Here it does the same, over the
    stamp, with no digest checked, and still travels on to setup-project.py,
    which checks it as it checks every flag."""
    result = stamped_run(tmp_path, shape_standard,
                         ["Atlas", "--org", "TestOrg", "--shape-ref", OTHER],
                         stamp=shape_standard.stamp(digest="0" * 64))
    assert result.returncode == 0, result.stdout + result.stderr
    report = stub_report(result.stdout)
    assert report["at"] == OTHER
    assert report["argv"][-2:] == ["--shape-ref", OTHER]


def test_the_doctor_says_last_which_clone_it_kept(tmp_path, shape_standard):
    """Its NEXT lines name files in the clone, so the clone is kept and the
    report's last line says where; under `--json` that line goes to stderr
    and stdout stays the doctor's. The doctor's own flags arrive as the
    launcher hands them on."""
    clone = cache_dir(tmp_path) / shape_standard.stamp()["commit"]
    kept = (f"the standard this run used is kept at {clone}, for any NEXT "
            "command above that names it")
    plain = stamped_run(tmp_path, shape_standard, ["--doctor", "../x"])
    assert plain.returncode == 0, plain.stdout + plain.stderr
    assert plain.stdout.splitlines()[-1].startswith(kept), plain.stdout
    as_json = stamped_run(tmp_path, shape_standard,
                          ["--doctor", "--json", "../x",
                           "--placement-plan", "plan.yaml"],
                          site=tmp_path / "package" / "site")
    assert as_json.returncode == 0, as_json.stdout + as_json.stderr
    assert stub_report(as_json.stdout)["argv"] == [
        "--root", "../x", "--json", "--placement-plan=plan.yaml"]
    assert "kept at" not in as_json.stdout
    assert kept in as_json.stderr


def test_install_is_refused_and_names_pipx_upgrade(cmd, tmp_path):
    """pipx (or pip) placed this command and keeps it current, so
    `--install` places nothing, from a checkout or installed, and says how
    to update it."""
    for run in (cmd, cmd.detached):
        result = run("--install", home=tmp_path,
                     env={"OPENREPOSHAPE_BIN_DIR": str(tmp_path / "bin")})
        assert result.returncode == 2, result.stdout + result.stderr
        assert "--install places nothing here" in said(result)
        assert "pipx upgrade openreposhape" in said(result)
        assert not (tmp_path / "bin").exists()
        assert not (tmp_path / ".local").exists()


# --- with no git ----------------------------------------------------------------------

def no_git_path(tmp_path: Path) -> dict:
    """A PATH with nothing on it, and so no git."""
    empty = tmp_path / "nothing-on-path"
    empty.mkdir()
    return {"PATH": str(empty)}


def test_preflight_runs_before_git_is_installed(tmp_path):
    """`--preflight` runs the `setup-project.py` the package carries, so a
    machine with no git still gets the preflight, which says git is
    missing, rather than this command's refusal for want of a clone."""
    site = installed_copy(tmp_path)
    result = run_package(site, "openreposhape",
                         ["--preflight", "--local-remote-dir",
                          str(tmp_path / "remotes")],
                         package_env(tmp_path, detached=True,
                                     env=no_git_path(tmp_path)))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "(1) preflight" in result.stdout
    assert "git is not installed" in result.stderr
    assert "REFUSED" not in result.stderr
    assert not cache_dir(tmp_path).exists()


def test_with_no_git_a_run_that_needs_the_standard_is_refused(tmp_path):
    site = installed_copy(tmp_path)
    result = run_package(site, "openreposhape", ["--doctor", "."],
                         package_env(tmp_path, detached=True,
                                     env=no_git_path(tmp_path)),
                         cwd=tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "git is not installed, and this command runs the standard from " \
        "a clone of it" in said(result)


# --- git-filter-repo, for every child -------------------------------------------------

def package_module(name: str, monkeypatch):
    """`openreposhape.<name>` from this checkout's `src/`, imported in this
    process with no bytecode written; `sys.path` and the bytecode flag are
    put back when the test ends."""
    monkeypatch.syspath_prepend(str(SOURCE))
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    return importlib.import_module(f"openreposhape.{name}")


def fake_filter_repo(directory: Path) -> Path:
    """A `git-filter-repo` in `directory` a command line would start, as pip
    writes one: a script on POSIX, and on Windows a name `PATHEXT` knows."""
    if os.name == "nt":
        fake = directory / "git-filter-repo.cmd"
        fake.write_bytes(b"@exit /b 0\r\n")
    else:
        fake = directory / "git-filter-repo"
        fake.write_bytes(b"#!/bin/sh\nexit 0\n")
        fake.chmod(0o755)
    return fake


def test_children_get_the_scripts_directory_first_when_it_holds_filter_repo(
        tmp_path, monkeypatch):
    """First on PATH when a `git-filter-repo` is there, and PATH untouched
    when none is."""
    standard = package_module("standard", monkeypatch)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    monkeypatch.setattr(standard.sysconfig, "get_path",
                        lambda name, *rest: str(scripts))
    before = {"PATH": os.pathsep.join(["/one", "/two"]), "OTHER": "kept"}
    assert standard.child_environment(before) == before
    fake_filter_repo(scripts)
    assert standard.child_environment(before) == {
        "PATH": os.pathsep.join([str(scripts), "/one", "/two"]),
        "OTHER": "kept"}


def test_a_child_finds_the_git_filter_repo_of_the_packages_environment(
        tmp_path, shape_standard, monkeypatch):
    """THE PIPX CASE, END TO END: the package runs in an environment of its
    own whose scripts directory holds `git-filter-repo` and is on nobody's
    PATH. The tool it starts finds that one, first on its PATH; and before
    there is one there, it finds none, and PATH is as it was."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)],
                   check=True, capture_output=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    scripts = python.parent
    standard = package_module("standard", monkeypatch)
    elsewhere = [entry for entry in os.environ["PATH"].split(os.pathsep)
                 if entry and not standard.filter_repo_in(entry)]
    site = installed_copy(tmp_path / "package", shape_standard.stamp())
    env = package_env(tmp_path, detached=True, env={
        "OPENREPOSHAPE_REPO": str(shape_standard.bare),
        "PATH": os.pathsep.join(elsewhere)})

    def adopt():
        result = run_package(site, "adopt_project", ["plan"], env,
                             cwd=tmp_path, python=python)
        assert result.returncode == 0, result.stdout + result.stderr
        return stub_report(result.stdout)

    before = adopt()
    assert before["filter_repo"] is None
    assert before["path0"] == elsewhere[0]
    fake = fake_filter_repo(scripts)
    after = adopt()
    assert os.path.normcase(after["filter_repo"]) == os.path.normcase(
        str(fake))
    assert os.path.normcase(after["path0"]) == os.path.normcase(str(scripts))
