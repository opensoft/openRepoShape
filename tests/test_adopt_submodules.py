# SPDX-License-Identifier: Apache-2.0
"""Adoption preserves an existing dependency through the nested leg mount.

All repositories and remotes are local fixtures; no network is used.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, REPO, git, make_source_repo,
                      resolve, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402


pytestmark = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.mark.parametrize("dependency_leg", ["code", "spec"])
def test_adopt_moves_existing_gitmodules_with_its_dependency(tmp_path,
                                                            dependency_leg):
    dependency = make_source_repo(
        tmp_path / "dependency", tree={"value.txt": "first\n"},
        edits=(("value.txt", "second\n", "Update dependency"),))
    dependency_remote = tmp_path / "dependency.git"
    git("clone", "-q", "--bare", str(dependency), str(dependency_remote),
        cwd=tmp_path)
    source = make_source_repo(tmp_path / "Thing")
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency_remote),
        "upstream/dependency", cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Pin existing dependency", cwd=source)
    source_head = git("rev-parse", "HEAD", cwd=source).stdout.strip()
    original_modules = git("rev-parse", "HEAD:.gitmodules",
                           cwd=source).stdout.strip()
    dependency_head = git("rev-parse", "HEAD:upstream/dependency",
                          cwd=source).stdout.strip()
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in (("examples/", "spec"), (".claude/", "root"),
                      ("release.yaml", "root"),
                      (".gitmodules", dependency_leg),
                      ("upstream/", dependency_leg)):
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout

    clone = tmp_path / "assembly"
    git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules", "-b",
        "adopt/three-repo-shape", str(source), str(clone), cwd=tmp_path)
    leg = clone / dependency_leg
    assert git("rev-parse", "HEAD:.gitmodules", cwd=leg).stdout.strip() \
        == original_modules
    assert git("rev-parse", "HEAD:upstream/dependency",
               cwd=leg).stdout.strip() == dependency_head
    assert git("ls-tree", "HEAD", "--", "upstream/dependency",
               cwd=leg).stdout.startswith("160000 commit ")
    assert git("rev-parse", "HEAD", cwd=leg / "upstream/dependency") \
        .stdout.strip() == dependency_head
    assert (leg / "upstream/dependency/value.txt").read_text() == "second\n"
    assert "Pin existing dependency" in git(
        "log", "--format=%s", "--", ".gitmodules", cwd=leg).stdout
    root_modules = git("config", "-f", ".gitmodules", "--get-regexp",
                       r"^submodule\..*\.path$", cwd=clone).stdout.splitlines()
    assert sorted(root_modules) == ["submodule.code.path code",
                                    "submodule.spec.path spec"]
    assert git("rev-parse", "HEAD", cwd=source).stdout.strip() == source_head
    assert git("status", "--porcelain", cwd=source).stdout == ""

    # The generated assembly still satisfies the standard's contracts.
    for validator, args in (("validate-repository-naming.py",
                             ("--project", "project.yaml")),
                            ("validate-manifest.py", ()),
                            ("validate-pins.py", ())):
        checked = run_script(clone / "scripts" / validator, *args, cwd=clone)
        assert checked.returncode == 0, checked.stderr + checked.stdout
    pin = load_yaml(clone / "contracts/shape-pin.yaml")
    assert pin["commit"] == git("rev-parse", "HEAD", cwd=REPO) \
        .stdout.strip()
    bootstrapped = run_script(clone / "scripts/bootstrap.py", cwd=clone)
    assert bootstrapped.returncode == 0, bootstrapped.stderr + bootstrapped.stdout
    assert git("rev-parse", "HEAD", cwd=leg / "upstream/dependency") \
        .stdout.strip() == dependency_head


@pytest.fixture
def mount_fixture(tmp_path):
    """Real Git mount boundary, including registrations kept in assembly."""
    module_spec = importlib.util.spec_from_file_location("adopt_submodules", ADOPT)
    adopter = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = adopter
    module_spec.loader.exec_module(adopter)
    dependency = make_source_repo(tmp_path / "dependency",
                                  tree={"value.txt": "dependency\n"}, edits=())
    source = make_source_repo(tmp_path / "source")
    for name in ("kept", "moved"):
        git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency),
            f"upstream/{name}", cwd=source)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Register dependencies", cwd=source)
    work = tmp_path / "work"
    work.mkdir()
    names = {role: f"Northwind-{role}" for role in ("spec", "code")}
    for role in names:
        make_source_repo(work / names[role], tree={"file.txt": role}, edits=())
    urls = {role: str(work / names[role]) for role in names}
    return adopter, source, work, names, urls


def test_mount_preserves_registration_kept_in_assembly(mount_fixture, tmp_path):
    adopter, source, work, names, urls = mount_fixture
    assembly = tmp_path / "assembly"
    git("clone", "-q", str(source), str(assembly), cwd=tmp_path)
    kept = git("rev-parse", "HEAD:upstream/kept", cwd=source).stdout.strip()
    adopter._mount_the_legs(
        assembly, work, names, urls,
        {"spec": [], "code": ["upstream/moved"], "drop": []}, "spec", "code")
    registrations = git("config", "-f", ".gitmodules", "--get-regexp",
                        r"^submodule\..*\.path$", cwd=assembly).stdout.splitlines()
    assert sorted(registrations) == ["submodule.code.path code",
                                     "submodule.spec.path spec",
                                     "submodule.upstream/kept.path upstream/kept"]
    assert git("rev-parse", ":upstream/kept", cwd=assembly).stdout.strip() == kept
    assert git("config", "-f", ".gitmodules", "--get",
               "submodule.upstream/kept.url", cwd=assembly).stdout.strip() \
        == str(source.parent / "dependency")


def test_failed_mount_leaves_source_reusable(mount_fixture, tmp_path):
    adopter, source, work, names, urls = mount_fixture
    before = git("show-ref", cwd=source).stdout
    modules = (source / ".gitmodules").read_bytes()
    paths = {"spec": [], "code": [".gitmodules", "upstream/"], "drop": []}
    failed = tmp_path / "failed-assembly"
    git("clone", "-q", str(source), str(failed), cwd=tmp_path)
    unavailable = {**names, "code": "missing-code"}
    with pytest.raises(adopter.CommandFailed):
        adopter._mount_the_legs(failed, work, unavailable, urls,
                                paths, "spec", "code")
    assert git("show-ref", cwd=source).stdout == before
    assert (source / ".gitmodules").read_bytes() == modules
    assert git("status", "--porcelain", cwd=source).stdout == ""

    fresh = tmp_path / "fresh-assembly"
    git("clone", "-q", str(source), str(fresh), cwd=tmp_path)
    adopter._mount_the_legs(fresh, work, names, urls, paths, "spec", "code")
    for role in names:
        assert (fresh / role / "file.txt").read_text() == role
