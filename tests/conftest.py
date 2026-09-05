# SPDX-License-Identifier: Apache-2.0
"""Shared fixtures: one real scaffold run, cloned, copied per test.

NO NETWORK AND NO GITHUB. Every test here runs `scaffold-project.py` with
`--local-remote-dir`, which creates three BARE repositories in a temporary
directory and uses them as origins. Nothing in this suite may create a real
repository; if a test ever needs `gh`, it is the wrong test.

The scaffold and the recursive clone happen ONCE per session because they are
the slow part; each test that mutates a tree gets its own `copytree` of the
clone. A submodule's `.git` is a file holding a RELATIVE path into
`../.git/modules/<name>`, so a plain copy of the whole clone stays internally
consistent — which is what makes the cheap fixture honest rather than merely
fast.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCAFFOLD = REPO / "scaffold-project.py"
PROJECT = "Atlas"
ORG = "testorg"

#: A local-path submodule is a `file://` clone, which git refuses by default
#: since the 2022 advisories. The scaffold passes this itself where it must;
#: the tests pass it for their own clones. It is a TEST-HARNESS concession to
#: using bare repositories on disk as origins, not something a real project
#: ever needs.
FILE_PROTOCOL = ["-c", "protocol.file.allow=always"]

#: THE ENTRY-POINT TESTS THAT CANNOT RUN ON WINDOWS. Two shapes of test wear
#: this: one that runs `bash`, and one that puts a `#!`-shebang script named
#: `gh` on PATH and expects the operating system to execute it. Windows has
#: neither — `bash.exe` IS on the GitHub runner, so a `shutil.which("bash")`
#: guard does not fire, but `setup.sh` shells out to a literal `python3` that
#: is not there, and a shebang means nothing to CreateProcess. Skipping is
#: honest because Windows has its OWN entry point with its OWN suite:
#: `setup-project.py`, covered case for case in `test_setup_project_py.py`.
#: A shared `skipif` object rather than a named marker because there is no
#: pytest.ini to register one in, and an unregistered marker is a warning.
WINDOWS_SKIP = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a POSIX shell and shebang execution; on Windows the entry "
           "point is setup-project.py (tests/test_setup_project_py.py)")


def rmtree(path: Path) -> None:
    """`shutil.rmtree` that also works over a git object store on Windows.

    Git writes loose objects and packs READ-ONLY, and Windows refuses to
    unlink a read-only file — so a plain `rmtree` over a checkout raises
    PermissionError there and succeeds everywhere else. The handler clears the
    read-only bit and retries the one call that failed. `onerror` rather than
    `onexc`: the newer spelling is 3.12+, and this standard runs on 3.9.
    """
    def clear_readonly(func, target, _exc):
        os.chmod(target, stat.S_IWRITE)
        func(target)

    shutil.rmtree(path, onerror=clear_readonly)


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} in {cwd} failed:\n"
                             f"{proc.stderr}{proc.stdout}")
    return proc


def run_script(script: Path, *args: str, cwd: Path | None = None,
               env: dict | None = None, input: str | None = None,
               stdin: int | None = None) -> subprocess.CompletedProcess:
    """Run one tool under test, with stdin closed by default.

    A test in this suite is often asserting what a tool does when nobody is
    there to answer a prompt — the whole point is that the run is
    unattended. Leaving stdin unset would inherit the pytest process's own
    console handle, and on Windows an inherited console reports isatty() as
    True even under CI, where the test runner has no real terminal either —
    the same assertion would then pass or fail depending on the OS, not on
    the tool. `subprocess.DEVNULL` makes every run non-interactive by
    default so the behaviour under test does not depend on how the test
    process itself was launched. A caller that DOES want to exercise the
    non-tty-but-readable path passes `input=` (a pipe), and one that wants
    something else entirely — a real pty, say — passes `stdin=` explicitly;
    `subprocess.run` itself refuses to accept `input` together with `stdin`,
    so there is nothing to reconcile between the two here.
    """
    env = {**os.environ, **(env or {})}
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    if input is None and stdin is None:
        stdin = subprocess.DEVNULL
    return subprocess.run([sys.executable, str(script), *args],
                          cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, check=False, env=env, input=input,
                          stdin=stdin)


@pytest.fixture(scope="session")
def scaffolded(tmp_path_factory) -> dict:
    """One real scaffold into local bare remotes, plus a recursive clone."""
    base = tmp_path_factory.mktemp("shape")
    remotes, work, clones = base / "remotes", base / "work", base / "clones"
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(remotes), "--work-dir", str(work),
    )
    assert result.returncode == 0, result.stderr + result.stdout
    clones.mkdir()
    proc = subprocess.run(
        ["git", *FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
         str(remotes / f"{PROJECT}.git"), str(clones / PROJECT)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    return {
        "base": base, "remotes": remotes, "work": work,
        "clone": clones / PROJECT, "stdout": result.stdout,
        "stderr": result.stderr,
    }


@pytest.fixture
def project(scaffolded, tmp_path) -> Path:
    """A private, mutable copy of the cloned assembly root."""
    target = tmp_path / PROJECT
    shutil.copytree(scaffolded["clone"], target, symlinks=True)
    return target


ADOPT = REPO / "adopt-project.py"

#: A repository shaped like the ones this standard is asked to adopt: a
#: specification side, an implementation side, project-level workflow tooling
#: that belongs to neither, and two genuinely ambiguous corners. Small enough
#: to assert every row of the plan against, which is the point.
SYNTHETIC_TREE = {
    # spec
    "specs/001-feature/spec.md": "# The feature\n",
    "specs/001-feature/tasks.md": "- [ ] one\n",
    "openspec/changes/add-thing/proposal.md": "## Why\n",
    "contracts/policy.yaml": "schema_version: 1\nkind: policy\n",
    "docs/architecture.md": "# Architecture\n",
    # code
    "src/app/main.py": "import contracts_reader\n",
    "src/app/util.py": "VALUE = 1\n",
    "tests/test_main.py": "def test_ok():\n    assert True\n",
    ".github/workflows/ci.yml": "on: [push]\n",
    "pyproject.toml": "[project]\nname = 'thing'\n",
    "sonar-project.properties": "sonar.projectKey=thing\n",
    "docker/Dockerfile": "FROM python:3.12\n",
    # code, by extension majority alone: no rule names this directory
    "pkg_core/__init__.py": "",
    "pkg_core/engine.py": "def run():\n    return 1\n",
    "pkg_core/table.json": "{}\n",
    # root
    "README.md": "# Thing\n",
    "LICENSE": "Apache-2.0\n",
    ".gitignore": "__pycache__/\n",
    "Makefile": "test:\n\tpytest\n",
    "AGENTS.md": "Follow the procedure.\n",
    "CLAUDE.md": "Follow the procedure.\n",
    ".specify/scripts/plan.sh": "#!/bin/sh\necho plan\n",
    ".specify/templates/spec.md": "# template\n",
    ".github/CODEOWNERS": "* @team\n",
    # ambiguous
    "examples/golden-run/expected.yaml": "result: ok\n",
    ".claude/commands/ship.md": "ship it\n",
    "release.yaml": "channel: stable\n",
}


#: The second and third commits of `make_source_repo`: `(path, new body,
#: message)`. They are DATA rather than statements so that a caller passing
#: its own `tree` can say which of ITS files the later commits touch — a
#: spec-only repository has no `src/app/main.py` to implement.
DEFAULT_EDITS = (
    ("specs/001-feature/spec.md", "# The feature\n\nA second paragraph.\n",
     "Extend the specification"),
    ("src/app/main.py",
     "import contracts_reader\n\n\ndef main():\n    return 0\n",
     "Implement main"),
)


def make_source_repo(path: Path, tree: dict | None = None,
                     branch: str = "main", edits: tuple | None = None) -> Path:
    """A local repository with SEVERAL commits, so history can be verified.

    Three commits, each touching a different side of the tree: an extraction
    that kept only the tip would still pass a file-count check, and would fail
    this one.
    """
    tree = dict(tree or SYNTHETIC_TREE)
    edits = DEFAULT_EDITS if edits is None else edits
    path.mkdir(parents=True, exist_ok=True)
    git("init", "-q", "-b", branch, ".", cwd=path)
    env = {"GIT_AUTHOR_NAME": "Source Human",
           "GIT_AUTHOR_EMAIL": "human@source.invalid",
           "GIT_COMMITTER_NAME": "Source Human",
           "GIT_COMMITTER_EMAIL": "human@source.invalid"}

    def commit(message: str) -> None:
        proc = subprocess.run(["git", "add", "-A", "--", "."], cwd=str(path),
                              capture_output=True, text=True, check=False)
        assert proc.returncode == 0, proc.stderr
        proc = subprocess.run(["git", "commit", "-q", "-m", message],
                              cwd=str(path), capture_output=True, text=True,
                              check=False, env={**os.environ, **env})
        assert proc.returncode == 0, proc.stderr + proc.stdout

    for name, body in tree.items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    commit("Initial import")
    for name, body, message in edits:
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        commit(message)
    return path


@pytest.fixture
def source_repo(tmp_path) -> Path:
    return make_source_repo(tmp_path / "Thing")


def write_plan(source: Path, out: Path, project: str = "Northwind",
               org: str = "testorg", extra: tuple = ()) -> subprocess.CompletedProcess:
    return run_script(ADOPT, "plan", "--source", str(source),
                      "--project", project, "--org", org,
                      "--elected-by", "Test Human",
                      "--elected-on", "2026-09-02",
                      "--out", str(out), *extra)


def resolve(plan_path: Path, path: str, leg: str,
            why: str = "answered by the test") -> None:
    """Answer one `review_required` entry the way a human or an AI would."""
    text = plan_path.read_text(encoding="utf-8")
    needle = f"  - path: {path}\n    leg: null\n"
    assert needle in text, f"{path} is not an unresolved entry in the plan"
    plan_path.write_text(
        text.replace(needle, f"  - path: {path}\n    leg: {leg}\n"
                             f"    resolution: \"{why}\"\n", 1),
        encoding="utf-8")
