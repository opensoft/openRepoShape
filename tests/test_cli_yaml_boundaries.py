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


@pytest.mark.parametrize("script", ["validate-repository-naming.py", "validate-manifest.py"])
@pytest.mark.parametrize("spelling", ["absolute", "traversal", "prefix-sibling", "symlink"])
def test_legacy_library_fallback_refuses_outside_policy(project, tmp_path, script, spelling):
    from test_chain_pin_sources import V1_1_1, library_at

    (project / "scripts/repo_shape.py").write_bytes(library_at(V1_1_1))
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(bytes([255]))
    sibling = project.parent / (project.name + "-secret")
    sibling.mkdir()
    (sibling / "data.yaml").write_bytes(bytes([255]))
    link = project / "escaped.yaml"
    if spelling == "symlink":
        link.symlink_to(outside)
    paths = {"absolute": outside, "traversal": Path("..") / outside.name,
             "prefix-sibling": sibling / "data.yaml", "symlink": link}
    result = run_script(project / "scripts" / script, "--policy",
                        str(paths[spelling]), cwd=project)
    assert result.returncode == 2, result.stdout + result.stderr
    assert "yaml-path-outside-cwd" in result.stderr
    assert "not UTF-8" not in result.stderr
    assert "Traceback" not in result.stderr
