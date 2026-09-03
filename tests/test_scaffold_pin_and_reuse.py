# SPDX-License-Identifier: Apache-2.0
"""Reusing an EMPTY assembly root, and scaffolding a DECLARED descendant.

Both are the 2026-09-02 rulings made runnable, and both run entirely against
local bare repositories: `--local-remote-dir` for the remotes and
`--pin-source` for the pinned product's digest, so nothing here touches a
network or a real repository.
"""

from __future__ import annotations

import subprocess
import sys

from conftest import ORG, REPO, SCAFFOLD, git, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, tree_digest  # noqa: E402

PROJECT = "Northwind"


def bare(path, branch: str = "main"):
    subprocess.run(["git", "init", "-q", "--bare", "-b", branch, str(path)],
                   check=True)
    return path


def seeded_bare(tmp_path, name: str):
    """A bare repository with ONE commit — a live repository, not a slot."""
    work = tmp_path / f"{name}-work"
    work.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(work)], check=True)
    (work / "README.md").write_text("# live\n")
    subprocess.run(["git", "add", "-A"], cwd=str(work), check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "seed"], cwd=str(work), check=True)
    target = bare(tmp_path / "remotes" / f"{name}.git")
    subprocess.run(["git", "push", "-q", str(target), "main"], cwd=str(work),
                   check=True)
    return target


# --- --reuse-empty-repo ----------------------------------------------------

def test_an_empty_assembly_root_is_reused_when_asked(tmp_path):
    """An organisation that created the repository first and asked for the
    shape second is the ordinary case. An EMPTY repository is a reserved
    name, and reserving a name is not starting a project."""
    remotes = tmp_path / "remotes"
    remotes.mkdir(parents=True)
    bare(remotes / f"{PROJECT}.git")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--reuse-empty-repo",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "(zero commits)" in result.stdout
    tip = git("rev-parse", "main", cwd=remotes / f"{PROJECT}.git").stdout.strip()
    assert len(tip) == 40, "the reused repository must have been pushed to"
    assert (remotes / f"{PROJECT}-spec.git").is_dir()


def test_an_existing_empty_root_without_the_flag_names_the_flag(tmp_path):
    remotes = tmp_path / "remotes"
    remotes.mkdir(parents=True)
    bare(remotes / f"{PROJECT}.git")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "--reuse-empty-repo" in result.stderr, (
        "a refusal that does not name the flag that answers it puts the exit "
        "in tribal memory")


def test_a_root_with_commits_is_refused_and_sent_to_adopt(tmp_path):
    """The line between the two tools, in the message: a repository with
    commits is a live project, and converting one is `adopt-project.py`."""
    remotes_root = seeded_bare(tmp_path, PROJECT)
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--local-remote-dir", str(remotes_root.parent),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "has commits" in result.stderr
    assert "adopt-project.py plan" in result.stderr
    assert "keeps its name, its identity and its history" in result.stderr


def test_an_existing_LEG_is_still_refused_outright(tmp_path):
    """`--reuse-empty-repo` is about the assembly root alone. The legs are
    created and seeded here, so one that exists is somebody else's."""
    remotes = tmp_path / "remotes"
    remotes.mkdir(parents=True)
    bare(remotes / f"{PROJECT}-spec.git")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "the two legs must not exist yet" in result.stderr


# --- --pin: a DECLARED descendant that carries legs ------------------------

def product_repo(tmp_path, name: str = "openGlass"):
    """A local stand-in for the neutral product, and its commit."""
    path = tmp_path / name
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    (path / "README.md").write_text(f"# {name}\n")
    (path / "contracts").mkdir()
    (path / "contracts" / "glass.yaml").write_text("schema_version: 1\n")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "seed"], cwd=str(path), check=True)
    commit = git("rev-parse", "HEAD", cwd=path).stdout.strip()
    return path, commit


def test_a_declared_descendant_scaffolds_with_legs(tmp_path):
    """THE MedxGlass CASE, end to end. `MedxGlass` declares a pin on
    `openGlass` and is STILL the assembly root that mounts two legs."""
    product, commit = product_repo(tmp_path)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--elected-on", "2026-09-02",
                        "--pin", f"openGlass@{commit}",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "naming-role-mismatch" not in result.stderr
    assert "domain-descendant / assembly" in result.stdout
    assert "a descendant may carry legs" in result.stdout

    root = work / "MedxGlass"
    manifest = load_yaml(root / "project.yaml")
    assert manifest["neutral_product_pins"] == ["openGlass"]
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "domain-descendant"
    assert assembly["naming"]["role"] == "assembly"
    assert assembly["naming"]["descendant_referent"] == "openGlass"
    assert assembly["naming"]["referent_declared"] is True
    spec = next(leg for leg in manifest["legs"] if leg["role"] == "spec")
    assert spec["naming"]["form"] == "project-leg", (
        "`MedxGlass-spec` carries the lowercase suffix: it descends from "
        "nothing and the manifest must say so")

    pin = load_yaml(root / "contracts" / "openglass-pin.yaml")
    assert pin["kind"] == "pinned_contract_manifest"
    assert pin["pin_role"] == "neutral-product"
    assert pin["revision_kind"] == "commit"
    assert pin["commit"] == commit
    assert pin["digests"]["tree_sha256"] == tree_digest(product, commit), (
        "the pin's digest must be the `sorted-ls-tree-r-v1` digest of the "
        "product's tree at that commit")
    assert "local-clone" in pin["digest_source"]

    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py", [])):
        check = run_script(root / "scripts" / validator, *args, cwd=root)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"


def test_a_pin_that_is_not_a_full_commit_is_refused(tmp_path):
    product, commit = product_repo(tmp_path)
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openGlass@{commit[:12]}",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "pin-malformed" in result.stderr
    assert "a tag can be moved" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_pin_the_source_does_not_have_is_refused(tmp_path):
    product, _ = product_repo(tmp_path)
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", "openGlass@" + "0" * 40,
                        "--pin-source", str(product),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "pin-source-unreadable" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_an_undeclared_descendant_form_is_unchanged(tmp_path):
    """The other half of the ruling still holds: with no pin, `MedxGlass` is
    an ordinary assembly root and the overlap is RECORDED."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr
    manifest = load_yaml(work / "MedxGlass" / "project.yaml")
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "project-leg"
    assert assembly["naming"]["referent_declared"] is False
    assert manifest["neutral_product_pins"] == []
