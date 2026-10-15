# SPDX-License-Identifier: Apache-2.0
"""Reusing an EMPTY assembly root, and scaffolding a DECLARED descendant.

Both are the 2026-09-02 rulings made runnable, and both run entirely against
local bare repositories: `--local-remote-dir` for the remotes and
`--pin-source` for the pinned product's digest, so nothing here touches a
network or a real repository.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys

import pytest

from conftest import (ORG, REPO, SCAFFOLD, WINDOWS_SKIP, clone_just_pushed,
                      git, run_script)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (double_quoted, load_yaml, parse_yaml,  # noqa: E402
                        pin_source_env_name, tree_digest)
from shape_materialize import neutral_pin_path, render  # noqa: E402

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


def test_an_existing_LEG_with_commits_is_still_refused_outright(tmp_path):
    """`--reuse-empty-repo` reuses an EMPTY leg, and one holding only this
    scaffold's own seed (#462, `test_scaffold_reuse_seeded_legs.py`). A leg
    holding anything else is somebody's repository, and is refused whatever
    the flag says."""
    spec = seeded_bare(tmp_path, f"{PROJECT}-spec")
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human", "--reuse-empty-repo",
                        "--local-remote-dir", str(spec.parent),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "scaffold-remote-exists" in result.stderr
    assert "has commits" in result.stderr
    assert "other than the one seed this scaffold would push" in result.stderr
    assert not (spec.parent / f"{PROJECT}-code.git").exists()


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


def assert_pin_digest_recomputed(check, product: str, commit: str) -> None:
    """The pin's digest was RECOMPUTED from the stand-in, not skipped (#272).

    `validate-pins.py` finds a neutral pin's source in four places and no
    other (`resolve_neutral_pin_source`): `--pin-source <product>=<path>`,
    `SHAPE_PIN_SOURCE_<PRODUCT>`, a checkout beside the assembly root, a bare
    `--pin-source`. When none answers it runs a real `gh api`, and when that
    fails it prints a `skip` line and still exits 0 — so a run with no source
    is green on a digest nobody rechecked, and these tests depended on the
    operator's `gh` login and network to get there. The exit code cannot tell
    the two apart; the line on stdout can."""
    recomputed = f"{product}: pin commit {commit[:12]} digest recomputes"
    assert recomputed in check.stdout, (
        f"the digest this test vouches for ({product} @ {commit[:12]}) must be "
        "recomputed from the stand-in it pinned, never skipped: "
        f"{check.stderr}{check.stdout}")
    assert f"skip {product}:" not in check.stdout, (
        f"`validate-pins.py` skipped {product}'s digest instead of "
        "recomputing it — it found no source and went to `gh api`, which a "
        f"test must never reach: {check.stdout}")


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

    # The stand-in is not beside `work/MedxGlass`, so `validate-pins.py` is
    # told where it is, or it asks `gh api` and skips the digest (#272).
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py",
                             ["--pin-source", f"openGlass={product}"])):
        check = run_script(root / "scripts" / validator, *args, cwd=root)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"
        if validator == "validate-pins.py":
            assert_pin_digest_recomputed(check, "openGlass", commit)


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
    # `validate-pins.py` is told where the layer's stand-in is, or it asks
    # `gh api` and skips the digest (#272); the other two take no source, and
    # the link stays unverified for them.
    for validator, args in (("validate-repository-naming.py",
                             ["--project", "project.yaml"]),
                            ("validate-manifest.py", []),
                            ("validate-pins.py",
                             ["--pin-source", f"openXdox={layer}"])):
        check = run_script(root / "scripts" / validator, *args, cwd=root)
        assert check.returncode == 0, f"{validator}: {check.stderr}{check.stdout}"
        if validator != "validate-pins.py":
            assert "declared-unverified" in check.stderr, (
                "openXdox is not checked out beside this root, so the link is "
                "unverified — a warning, and exit 0"
            )
        else:
            assert_pin_digest_recomputed(check, "openXdox", commit)


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
    """The leg paths are asked the leg-path question first (#179), as adopt's
    are, so the code is `scaffold-bad-leg-path` and no longer `unsafe-value`;
    the sentence is `checked_value`'s own, and nothing is created."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--spec-path", "spec; rm -rf ~",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "REFUSED scaffold-bad-leg-path" in result.stderr
    assert ("--spec-path is 'spec; rm -rf ~', which is not a value this tool "
            "will put on a `git` or `gh` command line") in result.stderr
    assert not (tmp_path / "remotes").exists()


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
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    for leg in ("Example/openXdox", "Example/openXdox-spec",
                "Example/openXdox-code"):
        assert leg in result.stdout
    assert "contracts/opendox-pin.yaml" in result.stdout
    assert "openXdox classifies as neutral-product / assembly" in result.stdout
    assert "--dry-run: nothing was created." in result.stdout


# --- a product the project's reader would take for a number (#516) ---------
#
# On main fc48854 `--pin 007@<commit>` scaffolded and exited 0, and the root
# listed the product in `neutral_product_pins:` bare, `  - 007`, which the
# project's own reader reads back as the number 7 (and `2026` and `1.5` as
# numbers). The root's own `validate-pins.py` then refused the entry as
# `neutral-pin-entry-malformed`, and its `validate.yml` runs that, so the new
# project's first CI run was red. The pin file said `product: 007`, read back
# as 7 too. Each now reads back as the text given. `openGlass` is the
# control: its manifest line does not move by a byte.

#: `(the product, how its `neutral_product_pins:` entry is spelled)`.
AS_TEXT = [
    pytest.param(("007", '"007"'), id="007"),
    pytest.param(("2026", '"2026"'), id="2026"),
    pytest.param(("1.5", '"1.5"'), id="1.5"),
    pytest.param(("openGlass", "openGlass"), id="openGlass"),
]


@pytest.fixture(scope="module", params=AS_TEXT)
def pinned_as_text(request, tmp_path_factory):
    """One real scaffold with `--pin <product>@<commit> --pin-source <a local
    clone>` into local bare remotes, and a recursive clone of the root, which
    is the root a person gets."""
    product, spelled = request.param
    base = tmp_path_factory.mktemp("scaffold-pin-text")
    source, commit = product_repo(base, product)
    remotes = base / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--pin", f"{product}@{commit}",
                        "--pin-source", str(source),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(base / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = base / "clone" / PROJECT
    proc = clone_just_pushed(remotes / f"{PROJECT}.git", clone)
    assert proc.returncode == 0, proc.stderr
    return {"product": product, "spelled": spelled, "commit": commit,
            "source": source, "clone": clone}


def committed(clone, rel: str) -> bytes:
    """`rel` as the clone's checked-out commit holds it, read from git in
    bytes, whatever a checkout on this platform wrote to the working tree."""
    return subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=str(clone),
                          capture_output=True, check=True).stdout


#: The reader the scaffolded root ships, its own `scripts/repo_shape.py`,
#: asked what the text it is handed on stdin holds.
ROOTS_READER = ("import json, sys; sys.path.insert(0, sys.argv[1]); "
                "from repo_shape import parse_yaml; "
                "print(json.dumps(parse_yaml(sys.stdin.buffer.read()"
                ".decode('utf-8')), default=repr))")


def read_by_the_root(clone, rel: str) -> dict:
    """`rel`, as the clone's commit holds it, read by the reader the root
    ships, which is what its validators read with, and not by the one this
    test imported."""
    proc = subprocess.run([sys.executable, "-I", "-c", ROOTS_READER,
                           str(clone / "scripts")],
                          input=committed(clone, rel), capture_output=True,
                          check=False)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    return json.loads(proc.stdout)


def test_a_pinned_product_is_listed_as_the_text_given(pinned_as_text):
    """The manifest lists the product so that the root's own reader reads it
    back as the text given: `"007"`, and `openGlass` as it always was. That
    reader is a copy of this standard's `scripts/repo_shape.py`, byte for
    byte, which is the reader the scaffold asks and the tables below ask."""
    pinned = pinned_as_text
    blob = committed(pinned["clone"], "project.yaml")
    line = f"\nneutral_product_pins: \n  - {pinned['spelled']}\n\n".encode()
    at = blob.find(b"\nneutral_product_pins:")
    assert line in blob, blob[at:at + len(line) + 16]
    manifest = read_by_the_root(pinned["clone"], "project.yaml")
    assert manifest["neutral_product_pins"] == [pinned["product"]]
    shipped = committed(pinned["clone"], "scripts/repo_shape.py")
    own = (REPO / "scripts" / "repo_shape.py").read_bytes()
    assert shipped == own.replace(b"\r\n", b"\n"), (
        "the root's reader is not this standard's")


def test_a_pinned_products_pin_file_names_it_as_the_text_given(
        pinned_as_text):
    """`contracts/<product lowercased>-pin.yaml` names the product as the
    text given, where it said `product: 007` and was read back as 7."""
    pinned = pinned_as_text
    product = pinned["product"]
    pin = read_by_the_root(pinned["clone"], neutral_pin_path(product))
    assert pin["product"] == product
    assert pin["source_repository"] == f"opensoft/{product}"
    assert pin["commit"] == pinned["commit"]


def test_a_pinned_product_passes_the_scaffolded_roots_own_gate(
        pinned_as_text):
    """The point of #516: the scaffold exited 0, so the root's own
    `validate-manifest.py --root .` and `validate-pins.py --root .` pass in a
    recursive clone, the second with the pin's digest recomputed from the
    stand-in (#272)."""
    pinned = pinned_as_text
    product, clone = pinned["product"], pinned["clone"]
    env = {pin_source_env_name(product): str(pinned["source"])}
    for validator in ("validate-manifest.py", "validate-pins.py"):
        check = run_script(clone / "scripts" / validator, "--root", ".",
                           cwd=clone, env=env)
        said = check.stdout + check.stderr
        assert check.returncode == 0, f"{validator}: {said}"
        assert "neutral-pin-entry-malformed" not in said, said
    assert_pin_digest_recomputed(check, product, pinned["commit"])


def test_pins_are_listed_in_the_order_they_were_given(tmp_path):
    """Two `--pin`s given out of sorted order are listed as given, one line
    each: the scaffold has always kept the `--pin` order (`adopt-project.py`
    sorts its plan's), and the root's own gate passes both."""
    source, commit = product_repo(tmp_path, "openGlass")
    given = ("openGlass", "2026")
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        *(arg for product in given
                          for arg in ("--pin", f"{product}@{commit}")),
                        "--pin-source", str(source),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    clone = tmp_path / "clone" / PROJECT
    proc = clone_just_pushed(remotes / f"{PROJECT}.git", clone)
    assert proc.returncode == 0, proc.stderr
    blob = committed(clone, "project.yaml")
    assert b'\nneutral_product_pins: \n  - openGlass\n  - "2026"\n\n' \
        in blob, blob[blob.find(b"\nneutral_product_pins:"):][:80]
    manifest = read_by_the_root(clone, "project.yaml")
    assert manifest["neutral_product_pins"] == list(given)
    env = {pin_source_env_name(product): str(source) for product in given}
    check = run_script(clone / "scripts" / "validate-pins.py", "--root", ".",
                       cwd=clone, env=env)
    assert check.returncode == 0, check.stdout + check.stderr
    for product in given:
        assert_pin_digest_recomputed(check, product, commit)


@pytest.fixture(scope="module")
def scaffolder():
    """`scaffold-project.py` as a module, to ask how it spells an entry."""
    spec = importlib.util.spec_from_file_location("scaffold_for_pin_text",
                                                  SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


#: Product names `PIN_ARG_RE` admits that the project's reader, given them
#: bare as a list entry, reads as something else: a number, a bool or None,
#: and `-`, which it reads as a list of its own. Each is double-quoted.
MISREAD_BARE = {
    "number": ("007", "2026", "1.5", "-1", "-0.5", "20261011"),
    "keyword": ("true", "True", "TRUE", "false", "False", "FALSE", "null",
                "Null", "NULL"),
    "list": ("-",),
}
#: Names it reads back bare as the same text, so each is written bare, as
#: main wrote it: the plain names, and those that only look like a number
#: or a word to a reader other than the project's.
READ_BARE = ("openGlass", "Openglass", "open-glass", "open_glass",
             "openGlass2", "_x", "x.y", ".5", "3dGlass", "-x", "--", "0x1F",
             "1e3", "1_000", ".inf", "yes", "off")
#: Text the reader refuses outright bare. `--pin` admits none of it, and
#: each is double-quoted all the same, which the reader reads back.
REFUSED_BARE = ("[", "{", "&a", "*a", "!t", "'a", '"a')


def listed(entries: str) -> object:
    """`entries`, a `NEUTRAL_PRODUCT_PINS` value, in the manifest template's
    own `neutral_product_pins:` line, rendered by `render` as the scaffold
    renders it, and read as the project reads its manifest."""
    template = REPO / "templates" / "assembly-root" / "project.yaml"
    line, = (line for line in template.read_text(encoding="utf-8")
             .splitlines() if "{{NEUTRAL_PRODUCT_PINS}}" in line)
    text = render(f"{line}\n", {"NEUTRAL_PRODUCT_PINS": entries},
                  "project.yaml")
    return parse_yaml(text)["neutral_product_pins"]


@pytest.mark.parametrize("product", [
    *(pytest.param(name, id=f"{kind}-{name}")
      for kind, names in MISREAD_BARE.items() for name in names),
    *(pytest.param(name, id=f"bare-{name}") for name in READ_BARE),
])
def test_each_entry_reads_back_as_the_product(scaffolder, product):
    """Every product reads back as its text. A name the reader reads back
    bare is written bare, so a root's `openGlass` line does not move by a
    byte; every other is double-quoted, which the reader always reads back."""
    entries = scaffolder._neutral_product_pins([product])
    assert listed(entries) == [product]
    spelled = product if product in READ_BARE else double_quoted(product)
    assert entries == f"\n  - {spelled}"


def test_every_entry_together_reads_back_in_the_order_given(scaffolder):
    """All of them in one list, as many `--pin`s write it: one line each, in
    the order the pins were given, as the scaffold has always listed them."""
    every = [*(name for names in MISREAD_BARE.values() for name in names),
             *READ_BARE]
    entries = scaffolder._neutral_product_pins(every)
    assert entries.count("\n") == len(every)
    assert listed(entries) == every


@pytest.mark.parametrize("text", REFUSED_BARE)
def test_an_entry_the_reader_refuses_bare_is_double_quoted(scaffolder,
                                                           text):
    """A spelling the reader raises on is read back as nothing, so it is
    double-quoted, not passed through to fail the manifest."""
    entry = scaffolder._neutral_pin_entry(text)
    assert entry == double_quoted(text)
    assert listed(f"\n  - {entry}") == [text]


def test_no_pin_is_an_empty_list(scaffolder):
    """With no `--pin` the manifest lists none, as it always has."""
    assert scaffolder._neutral_product_pins({}) == "[]"
    assert listed("[]") == []
