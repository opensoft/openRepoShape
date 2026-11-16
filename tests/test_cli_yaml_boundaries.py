# SPDX-License-Identifier: Apache-2.0
"""Untrusted explicit CLI YAML paths stay within the invocation directory."""
from pathlib import Path
import sys

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, cli_yaml_path, load_yaml


@pytest.mark.parametrize("spelling", ["local.yaml", "sub/../local.yaml"])
def test_local_yaml_reaches_the_existing_parser(tmp_path, monkeypatch, spelling):
    (tmp_path / "sub").mkdir()
    (tmp_path / "local.yaml").write_text("kind: local\n")
    monkeypatch.chdir(tmp_path)
    assert load_yaml(cli_yaml_path(Path(spelling))) == {"kind": "local"}


@pytest.mark.parametrize("spelling", ["../outside.yaml", "absolute", "prefix-sibling"])
def test_outside_paths_refuse_before_the_reader(tmp_path, monkeypatch, spelling):
    inside = tmp_path / "workspace"
    inside.mkdir()
    sibling = tmp_path / "workspace-secret"
    sibling.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("kind: secret\n")
    (sibling / "data.yaml").write_text("kind: secret\n")
    path = {"absolute": outside, "prefix-sibling": sibling / "data.yaml"}.get(
        spelling, Path(spelling))
    monkeypatch.chdir(inside)
    with pytest.raises(Refusal) as caught:
        cli_yaml_path(path)
    assert caught.value.code == "yaml-path-outside-cwd"


def test_symlink_escape_refuses(tmp_path, monkeypatch):
    inside = tmp_path / "workspace"
    inside.mkdir()
    outside = tmp_path / "outside.yaml"
    outside.write_text("kind: secret\n")
    (inside / "link.yaml").symlink_to(outside)
    monkeypatch.chdir(inside)
    with pytest.raises(Refusal) as caught:
        cli_yaml_path(Path("link.yaml"))
    assert caught.value.code == "yaml-path-outside-cwd"


@pytest.mark.parametrize("option", ["--policy", "--project"])
def test_naming_cli_refuses_outside_yaml(tmp_path, option):
    inside = tmp_path / "workspace"
    inside.mkdir()
    outside = tmp_path / "outside.yaml"
    # Invalid bytes prove the CLI refused before YAML decode, not after it.
    outside.write_bytes(bytes([255]))
    result = run_script(REPO / "scripts/validate-repository-naming.py",
                        option, str(outside), cwd=inside)
    assert result.returncode == 2
    assert "yaml-path-outside-cwd" in result.stderr
    assert "not UTF-8" not in result.stderr


def test_manifest_cli_refuses_outside_policy(project, tmp_path):
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(bytes([255]))
    result = run_script(project / "scripts/validate-manifest.py",
                        "--policy", str(outside), cwd=project)
    assert result.returncode == 2
    assert "yaml-path-outside-cwd" in result.stderr
    assert "not UTF-8" not in result.stderr
