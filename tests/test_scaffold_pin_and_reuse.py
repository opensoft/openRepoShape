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

from conftest import ORG, REPO, SCAFFOLD, WINDOWS_SKIP, git, run_script

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
    assert pin["source_repository"] == "opensoft/openGlass", (
        "an unqualified --pin resolves under opensoft — the family's neutral-"
        "product owner — and NEVER under --org (MedxSoft here); MedxSoft owns "
        "no neutral product and a lookup there is a 404 waiting to happen")
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


# --- --referent-chain: a descendant that pins a LAYER (2026-09-05) ---------
#
# "elect the shape for both, follow the pin chain, no family yet" — Brett Heap,
# recorded on opensoft/openxFactory#656. `codexDox` pins `openXdox` and never
# pins `openDox` at all, so the referent is REACHED rather than pinned, and the
# manifest the scaffold writes has to be the one the project's own gate
# accepts: the writer and the checker are meant to be one rule.


def layer_repo(tmp_path, name: str = "openXdox", pins: str = "openDox"):
    """A stand-in for the LAYER, carrying its own declaration.

    `openXdox` is a chain link because openXdox's own `project.yaml` says
    `neutral_product_pins: [openDox]` — a fact in that tree, read from the
    disk here and from nowhere else.
    """
    path, commit = product_repo(tmp_path, name)
    (path / "project.yaml").write_text(
        f"schema_version: 1\nkind: project-manifest\n"
        f"neutral_product_pins:\n  - {pins}\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=str(path), check=True)
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "declare"], cwd=str(path), check=True)
    return path, git("rev-parse", "HEAD", cwd=path).stdout.strip()


def test_a_descendant_that_pins_a_layer_scaffolds_through_the_chain(tmp_path):
    """THE codexDox CASE, end to end. The pin this project holds is on the
    LAYER; the manifest RECORDS the chain that reaches `openDox`; and the pin
    file in the tree is the layer's, because `openDox` is the pin this family
    deliberately does not hold."""
    layer, commit = layer_repo(tmp_path)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "codexSoft", "--project", "codexDox",
                        "--elected-by", "Brett Heap",
                        "--elected-on", "2026-09-05",
                        "--pin", f"openXdox@{commit}",
                        "--referent-chain", "openXdox,openDox",
                        "--pin-source", str(layer),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "domain-descendant / assembly" in result.stdout
    assert "openXdox \u2192 openDox" in result.stdout, (
        "the plan must print the chain it classified on, not merely the "
        "verdict it reached")

    root = work / "codexDox"
    manifest = load_yaml(root / "project.yaml")
    assert manifest["neutral_product_pins"] == ["openXdox"]
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "domain-descendant"
    assert assembly["naming"]["descendant_referent"] == "openDox"
    assert assembly["naming"]["referent_declared"] is True
    assert assembly["naming"]["referent_chain"] == ["openXdox", "openDox"]
    assert (root / "contracts" / "openxdox-pin.yaml").is_file()
    assert not (root / "contracts" / "opendox-pin.yaml").exists(), (
        "a chain descendant pins the layer; the referent it reaches is not "
        "a pin it holds")

    # The gate the project runs on itself agrees with what was written for it.
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py", [])):
        check = run_script(root / "scripts" / validator, *args, cwd=root)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"
        if validator != "validate-pins.py":
            assert "declared-unverified" in check.stderr, (
                "openXdox is not checked out beside this root, so the link is "
                "unverified — a warning, and exit 0"
            )


# The three refusals below scaffold `MedxScribe` pinning `openInk`, NOT
# codexDox. `openXdox` casefolds onto the accepted x-stem spelling `openxDox`,
# so a pin on that layer reads as a DIRECT pin on a referent of `codexDox` —
# the case-folding coincidence the contract file writes down — and a direct
# pin stays sufficient by the ruling, which would make a broken chain beside
# it a warning rather than the refusal these tests are about. `openInk` is a
# referent of nothing, so the chain is the only thing that could reach one.


def test_a_chain_that_starts_where_nothing_is_pinned_is_refused(tmp_path):
    """The first entry is the pin this project actually HOLDS, so a chain
    that starts anywhere else is refused before anything is created."""
    layer, commit = layer_repo(tmp_path, "openInk", pins="openScribe")
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxScribe",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openInk@{commit}",
                        "--referent-chain", "openQuill,openScribe",
                        "--pin-source", str(layer),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "chain-not-declared" in result.stderr
    assert "begins at openQuill" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_chain_that_does_not_end_at_the_referent_is_refused(tmp_path):
    layer, commit = layer_repo(tmp_path, "openInk", pins="openScribe")
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxScribe",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openInk@{commit}",
                        "--referent-chain", "openInk,openLedger",
                        "--pin-source", str(layer),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "chain-not-declared" in result.stderr
    assert "ends at openLedger" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_link_whose_own_tree_declares_otherwise_is_refused(tmp_path):
    """The link's tree IS readable here — `--pin-source` is the same checkout
    the digest was computed from — and it declares something else, so the
    chain does not hold and the refusal names the link."""
    layer, commit = layer_repo(tmp_path, "openInk", pins="openQuill")
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxScribe",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openInk@{commit}",
                        "--referent-chain", "openInk,openScribe",
                        "--pin-source", str(layer),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "chain-not-declared" in result.stderr
    assert "openInk declares openQuill, not openScribe" in result.stderr
    assert not (tmp_path / "remotes").exists()


# --- --pin-owner: an unqualified --pin resolves under opensoft, never --org -

def test_pin_owner_can_be_overridden_explicitly(tmp_path):
    """`--pin-owner` re-points the DEFAULT for an unqualified --pin name —
    still never the project's own --org, which is the defect this exists
    to fix (`--org MedxSoft --pin openGlass@<sha>` must not go looking for
    `MedxSoft/openGlass`)."""
    product, commit = product_repo(tmp_path)
    work = tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openGlass@{commit}",
                        "--pin-owner", "MedxCorp",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    pin = load_yaml(work / "MedxGlass" / "contracts" / "openglass-pin.yaml")
    assert pin["source_repository"] == "MedxCorp/openGlass"


def test_pin_owner_named_in_the_pin_itself_wins_over_the_flag(tmp_path):
    """`--pin owner/openProduct@<sha>` always wins over `--pin-owner` and over
    the opensoft default — naming the owner in the value itself is the most
    specific spelling."""
    product, commit = product_repo(tmp_path)
    work = tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", f"ExplicitOwner/openGlass@{commit}",
                        "--pin-owner", "MedxCorp",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    pin = load_yaml(work / "MedxGlass" / "contracts" / "openglass-pin.yaml")
    assert pin["source_repository"] == "ExplicitOwner/openGlass"


def test_pin_owner_is_checked_like_any_other_command_line_value(tmp_path):
    """`--pin-owner` reaches a `gh api repos/<owner>/<product>/...` command
    line, so it is checked the same way `--org` and the rest are."""
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", "openGlass@" + "0" * 40,
                        "--pin-owner", "--upload-pack=touch /tmp/pwned",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "unsafe-value" in result.stderr
    assert not (tmp_path / "remotes").exists()


@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_an_unreadable_pin_names_the_exact_owner_repo_and_commit(tmp_path):
    """The refusal names the OWNER/REPO@COMMIT it actually tried (opensoft by
    default) and suggests the --pin owner/openProduct or --pin-owner form —
    the real-world defect this fixes was silent about both."""
    import os
    import stat
    import textwrap
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import sys
        print("HTTP 404: Not Found (https://api.github.com/...)",
              file=sys.stderr)
        sys.exit(1)
        """), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}"}
    commit = "1" * 40
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", "MedxGlass",
                        "--elected-by", "Brett Heap",
                        "--pin", f"openGlass@{commit}",
                        "--dry-run", "--work-dir", str(tmp_path / "work"),
                        env=env)
    assert result.returncode == 2
    assert "pin-unreadable" in result.stderr
    assert f"opensoft/openGlass @ {commit}" in result.stderr
    assert "MedxSoft/openGlass" not in result.stderr, (
        "the tool must never have gone looking under the project's own --org")
    assert "--pin <owner>/<openProduct>@<sha>" in result.stderr
    assert "--pin-owner" in result.stderr


# --- what may become an argument to git ------------------------------------

def test_a_branch_name_that_is_a_git_option_is_refused(tmp_path):
    """ARGUMENT injection, not shell injection: every command here is a list
    with `shell=False`, so there is no shell — but git reads its own
    arguments, and `--upload-pack=…` is a command rather than a branch."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--tracking-branch=--upload-pack=touch /tmp/pwned",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "unsafe-value" in result.stderr
    assert "git reads its own arguments" in result.stderr
    assert not (tmp_path / "remotes").exists()


def test_a_leg_path_with_a_shell_metacharacter_is_refused(tmp_path):
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--spec-path", "spec; rm -rf ~",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "unsafe-value" in result.stderr


# --- --pin: a NEUTRAL PRODUCT root that pins another neutral product -------
#
# Brett Heap, 2026-09-05: "elect the shape for both, follow the pin chain, no
# family yet". `openXdox` is the openxFactory-tuned layer of `openDox`: it is
# its own assembly root AND it declares a pin on the product below it. Nothing
# here is a descendant, which is the point — the `--pin` path must not assume
# the pinning project's name is in `<Domainx><Product>` form.

def test_a_neutral_product_root_may_also_pin_a_neutral_product(tmp_path):
    product, commit = product_repo(tmp_path, "openDox")
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "opensoft", "--project", "openXdox",
                        "--elected-by", "Brett Heap",
                        "--elected-on", "2026-09-05",
                        "--pin", f"openDox@{commit}",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "naming-role-mismatch" not in result.stderr
    assert "neutral-product / assembly" in result.stdout
    assert "may elect the shape (Brett Heap, 2026-09-05)" in result.stdout

    root = work / "openXdox"
    manifest = load_yaml(root / "project.yaml")
    assert manifest["neutral_product_pins"] == ["openDox"]
    assembly = next(leg for leg in manifest["legs"]
                    if leg["role"] == "assembly")
    assert assembly["naming"]["form"] == "neutral-product"
    assert assembly["naming"]["role"] == "assembly"
    assert assembly["naming"]["also_matches"] == ["project-leg/assembly"]
    assert "descendant_referent" not in assembly["naming"], (
        "`openXdox` is not in `<Domainx><Product>` form: it claims descent "
        "from nothing and the manifest must record no referent")
    spec = next(leg for leg in manifest["legs"] if leg["role"] == "spec")
    assert spec["naming"]["form"] == "project-leg"

    pin = load_yaml(root / "contracts" / "opendox-pin.yaml")
    assert pin["pin_role"] == "neutral-product"
    assert pin["commit"] == commit
    assert pin["source_repository"] == "opensoft/openDox"
    assert pin["digests"]["tree_sha256"] == tree_digest(product, commit)

    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py",
                             ["--pin-source", f"openDox={product}"])):
        check = run_script(root / "scripts" / validator, *args, cwd=root)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"


def test_the_dry_run_plans_a_pinned_neutral_product_root(tmp_path):
    """The refusal was first met on a dry run, so the dry run is asserted:
    three repositories planned, the pin resolved offline, nothing created."""
    product, commit = product_repo(tmp_path, "openDox")
    result = run_script(SCAFFOLD, "--org", "Example", "--project", "openXdox",
                        "--elected-by", "Brett Heap",
                        "--elected-on", "2026-09-05", "--dry-run",
                        "--pin", f"openDox@{commit}",
                        "--pin-source", str(product),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    for leg in ("Example/openXdox", "Example/openXdox-spec",
                "Example/openXdox-code"):
        assert leg in result.stdout
    assert "contracts/opendox-pin.yaml" in result.stdout
    assert "openXdox classifies as neutral-product / assembly" in result.stdout
    assert "--dry-run: nothing was created." in result.stdout
