# SPDX-License-Identifier: Apache-2.0
"""Local legacy paths must not make a leg's documents root manifests."""
import pytest

from conftest import git, load_without_bytecode, REPO

doctor = load_without_bytecode(REPO / "shape-doctor.py", "doctor_local_aliases")


@pytest.fixture
def root(tmp_path):
    git("init", "-q", ".", cwd=tmp_path)
    (tmp_path / "contracts").mkdir()
    (tmp_path / "spec" / "contracts").mkdir(parents=True)
    (tmp_path / "spec" / "contracts" / "domain.yaml").write_text(
        "kind: domain-contract\n", encoding="utf-8")
    # Record the actual repository boundary without needing a second clone.
    git("update-index", "--add", "--cacheinfo",
        "160000," + "a" * 40 + ",spec", cwd=tmp_path)
    (tmp_path / ".git" / "info" / "exclude").write_text(
        "/contracts/legacy.yaml\n", encoding="utf-8")
    (tmp_path / "contracts" / "legacy.yaml").symlink_to(
        "../spec/contracts/domain.yaml")
    return tmp_path


def context(root):
    ctx = doctor.Context(root)
    ctx.kind = doctor.PROJECT
    ctx.manifest = {"legs": [{"role": "spec", "path": "spec"}]}
    return ctx


def test_ignored_local_link_into_recorded_leg_is_not_root_manifest(root):
    assert doctor.local_leg_alias(
        context(root), root / "contracts/legacy.yaml", {})


@pytest.mark.parametrize("case", [
    "tracked", "not-ignored", "ordinary-file", "outside-leg",
    "not-gitlink", "gate-input", "not-project", "missing-target"])
def test_real_manifests_and_unproven_aliases_stay_candidates(root, case):
    link = root / "contracts/legacy.yaml"
    ctx = context(root)
    read_as = {}
    if case == "tracked":
        git("add", "-f", "--", "contracts/legacy.yaml", cwd=root)
    elif case == "not-ignored":
        (root / ".git/info/exclude").write_text("", encoding="utf-8")
    elif case == "ordinary-file":
        link.unlink()
        link.write_text("kind: unregistered\n", encoding="utf-8")
    elif case == "outside-leg":
        link.unlink()
        (root / "domain.yaml").write_text("kind: unregistered\n")
        link.symlink_to("../domain.yaml")
    elif case == "not-gitlink":
        git("update-index", "--force-remove", "--", "spec", cwd=root)
    elif case == "gate-input":
        read_as["contracts/legacy.yaml"] = "pinned_contract_manifest"
    elif case == "not-project":
        ctx.kind = doctor.FAMILY
    elif case == "missing-target":
        (root / "spec/contracts/domain.yaml").unlink()
    assert not doctor.local_leg_alias(ctx, link, read_as)
