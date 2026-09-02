# SPDX-License-Identifier: Apache-2.0
"""Properties of THIS repository that a fork depends on and nobody re-checks."""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, SCAFFOLD

SHIPPED = [
    REPO / "scaffold-project.py",
    REPO / "bootstrap",
    REPO / "scripts" / "repo_shape.py",
    REPO / "scripts" / "validate-repository-naming.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-pins.py",
    REPO / "templates" / "assembly-root" / "scripts" / "validate-manifest.py",
    REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
]
LOCAL_MODULES = {"repo_shape", "conftest"}


@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.name)
def test_shipped_code_imports_only_the_standard_library(path):
    """No pip, ever.

    The shape must run in an organisation that forked it and cannot install
    anything on the machine where the scaffold runs. That constraint is what
    forces the small YAML reader in `repo_shape.py`; this test is what keeps
    somebody from quietly undoing it with a one-line `import yaml`.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    foreign = imported - sys.stdlib_module_names - LOCAL_MODULES
    assert not foreign, f"{path.name} imports outside the standard library: {foreign}"


def test_every_shipped_script_compiles():
    for path in SHIPPED:
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_the_scaffold_accounts_for_every_template_file():
    """A file added to the assembly-root template but not to the scaffold's
    copy lists would silently never reach a scaffolded project."""
    source = SCAFFOLD.read_text(encoding="utf-8")
    template_root = REPO / "templates" / "assembly-root"
    for path in sorted(template_root.rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(template_root).as_posix()
        assert f'"{rel}"' in source, (
            f"{rel} is in templates/assembly-root/ but is named in neither "
            "TEMPLATED nor COPIED_VERBATIM in scaffold-project.py, so the "
            "scaffold would never copy it"
        )


def test_the_shape_pin_template_carries_a_files_block():
    text = (REPO / "templates" / "assembly-root" / "contracts" /
            "shape-pin.yaml").read_text()
    assert "{{SHAPE_FILES}}" in text
    assert "materialization: copied" in text


def test_agents_md_is_short_enough_to_be_read():
    lines = (REPO / "AGENTS.md").read_text().splitlines()
    assert len(lines) <= 80, f"AGENTS.md is {len(lines)} lines; the cap is 80"


def test_claude_md_points_at_agents_md():
    assert "AGENTS.md" in (REPO / "CLAUDE.md").read_text()


def test_readme_is_short_enough_to_be_read():
    lines = (REPO / "README.md").read_text().splitlines()
    assert len(lines) <= 150, f"README.md is {len(lines)} lines; the cap is 150"


def test_setup_sh_is_executable_and_fails_loudly():
    setup = REPO / "setup.sh"
    assert setup.is_file()
    assert os.access(setup, os.X_OK), "setup.sh must be executable: chmod +x"
    text = setup.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text, (
        "the first script a person runs in a fork must stop on the first "
        "failure, not carry on with an unset variable")


def test_setup_sh_parses_under_bash():
    if shutil.which("bash") is None:
        pytest.skip("bash is not installed")
    proc = subprocess.run(["bash", "-n", str(REPO / "setup.sh")],
                          capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_setup_sh_is_the_documented_front_door():
    assert "./setup.sh --project" in (REPO / "README.md").read_text()
    assert "What setup.sh does" in (REPO / "README.md").read_text()
    agents = (REPO / "AGENTS.md").read_text()
    assert "without `--yes`" in agents
    assert "--allow-upstream-org" in agents
