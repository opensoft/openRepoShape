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


def git(*args: str, cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    proc = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, check=False)
    if check and proc.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} in {cwd} failed:\n"
                             f"{proc.stderr}{proc.stdout}")
    return proc


def run_script(script: Path, *args: str, cwd: Path | None = None,
               env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env or {})}
    env.setdefault("GIT_AUTHOR_NAME", "openRepoShape tests")
    env.setdefault("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid")
    env.setdefault("GIT_COMMITTER_NAME", "openRepoShape tests")
    env.setdefault("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")
    return subprocess.run([sys.executable, str(script), *args],
                          cwd=str(cwd) if cwd else None, capture_output=True,
                          text=True, check=False, env=env)


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
