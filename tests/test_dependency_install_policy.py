# SPDX-License-Identifier: Apache-2.0
"""The runtime lock and CI retain the declared dependency and wheels-only policy."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from repo_shape import load_yaml


def test_runtime_lock_matches_declared_dependency_and_hashes_the_wheel():
    project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert 'dependencies = ["git-filter-repo==2.47.0"]' in project
    assert re.findall(r"^([a-z-]+==[\d.]+)", lock, flags=re.M) == ["git-filter-repo==2.47.0"]
    assert "--hash=sha256:2cd04929b9024e83e65db571cbe36aec65ead0cb5f9ec5abe42158654af5ad83" in lock


def test_all_pytest_installations_require_wheels_and_adoption_uses_the_runtime_lock():
    workflow = load_yaml(ROOT / ".github/workflows/tests.yml")
    runners = []
    adoption = []
    for job in workflow["jobs"].values():
        for step in job.get("steps", []):
            run = step.get("run", "")
            if "pip install" in run and "pytest==8.3.4" in run:
                runners.append(run)
                assert "--only-binary=:all:" in run
            if step.get("name") == "install git-filter-repo":
                adoption.append(run)
                assert "--only-binary=:all:" in run
                assert "--require-hashes -r requirements.txt" in run
    assert len(runners) == 2
    assert len(adoption) == 1
