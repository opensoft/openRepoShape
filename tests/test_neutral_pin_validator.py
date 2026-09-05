# SPDX-License-Identifier: Apache-2.0
"""THE NEUTRAL-PRODUCT PIN RE-CHECK.

`project.yaml`'s `neutral_product_pins:` names every `open<Product>` this
project claims descent from; `contracts/<product lowercased>-pin.yaml` is the
referent that claim needs (Brett Heap, 2026-09-02). `validate-pins.py`
recomputes that pin's digest the same way `scaffold-project.py` computed it
in the first place — from a local checkout when one can be found, else from
`gh api`, else a named SKIP that never fails the run.

NO NETWORK. Every test here that reaches the digest-recompute code path passes
`--pin-source` (or the env var, or a sibling checkout) so the LOCAL branch
answers; the one test that exercises the `gh api` fallback stubs out `gh`
itself, exactly as `test_scaffold_pin_and_reuse.py` does for the scaffold's
own unreadable-pin case.
"""

from __future__ import annotations

import os
import stat
import textwrap

from conftest import SCAFFOLD, WINDOWS_SKIP, run_script
from test_scaffold_pin_and_reuse import product_repo

PROJECT = "MedxGlass"


def validate(root, *args, env=None):
    return run_script(root / "scripts" / "validate-pins.py", *args, cwd=root,
                      env=env)


def scaffold_with_pin(tmp_path):
    """A `MedxGlass` scaffolded with a declared pin on `openGlass`."""
    product, commit = product_repo(tmp_path)
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--pin", f"openGlass@{commit}",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    return work / PROJECT, product, commit


def edit_pin(root, old: str, new: str) -> None:
    pin = root / "contracts" / "openglass-pin.yaml"
    text = pin.read_text()
    assert old in text, f"fixture drift: {old!r} not in openglass-pin.yaml"
    pin.write_text(text.replace(old, new, 1))


# --- the happy path: a local checkout answers -------------------------------

def test_a_neutral_pin_recomputes_from_a_bare_pin_source(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    result = validate(root, "--pin-source", str(product))
    assert result.returncode == 0, result.stderr + result.stdout
    assert (f"openGlass: pin commit {commit[:12]} digest recomputes"
            in result.stdout)
    assert "pins ok" in result.stdout


def test_a_neutral_pin_recomputes_from_a_keyed_pin_source(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    result = validate(root, "--pin-source", f"openGlass={product}")
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"pin commit {commit[:12]} digest recomputes" in result.stdout


def test_a_neutral_pin_recomputes_from_the_env_var(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    result = validate(root, env={"SHAPE_PIN_SOURCE_OPENGLASS": str(product)})
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"pin commit {commit[:12]} digest recomputes" in result.stdout


def test_a_neutral_pin_recomputes_from_a_sibling_checkout(tmp_path):
    """A checkout sitting BESIDE the assembly root, named for the pinned
    repository, is found with no flag and no env var at all."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    # `product_repo` makes its own parent; giving it `work` puts the product
    # at `work/openGlass`, a SIBLING of the `work/MedxGlass` assembly root
    # the scaffold is about to write — never `tmp_path/openGlass`, which
    # would sit beside `work` itself, not beside the assembly root.
    product, commit = product_repo(work, name="openGlass")
    result = run_script(SCAFFOLD, "--org", "MedxSoft", "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--pin", f"openGlass@{commit}",
                        "--pin-source", str(product),
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    root = work / PROJECT
    sibling = root.parent / "openGlass"
    assert sibling == product, "fixture drift: the product must sit beside root"
    result = validate(root)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"pin commit {commit[:12]} digest recomputes" in result.stdout
    assert "sibling checkout" in result.stdout


# --- drift: the digest no longer describes the referent's bytes ------------

def test_a_neutral_pin_digest_mismatch_is_a_finding(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    pin = (root / "contracts" / "openglass-pin.yaml").read_text()
    recorded = pin.split("tree_sha256: \"")[1].split("\"")[0]
    edit_pin(root, recorded, "0" * 64)
    result = validate(root, "--pin-source", str(product))
    assert result.returncode == 1
    assert "neutral-pin-digest-mismatch" in result.stderr
    assert "openglass-pin.yaml" in result.stderr


def test_an_explicit_pin_source_that_cannot_answer_is_a_finding(tmp_path):
    """An EXPLICIT --pin-source that turns out not to be a checkout of the
    product at all is a finding, not a silent skip: the user asked this
    specific place to answer and it could not."""
    root, product, commit = scaffold_with_pin(tmp_path)
    empty = tmp_path / "not-a-checkout"
    empty.mkdir()
    result = validate(root, "--pin-source", str(empty))
    assert result.returncode == 1
    assert "neutral-pin-source-unreadable" in result.stderr


# --- refusals: the question cannot be asked ---------------------------------

def test_a_neutral_pin_commit_that_is_not_40_hex_refuses(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    edit_pin(root, f'commit: "{commit}"', 'commit: "x"')
    result = validate(root, "--pin-source", str(product))
    assert result.returncode == 2
    assert "neutral-pin-tag-only" in result.stderr


def test_a_neutral_pin_that_is_not_a_commit_is_a_finding(tmp_path):
    root, product, commit = scaffold_with_pin(tmp_path)
    edit_pin(root, "revision_kind: commit", "revision_kind: tag")
    result = validate(root, "--pin-source", str(product))
    assert result.returncode == 1
    assert "neutral-pin-tag-only" in result.stderr
    assert "A tag can be moved" in result.stderr


def test_a_missing_neutral_pin_file_refuses(tmp_path):
    """`project.yaml` still declares the pin; the referent it needs is gone."""
    root, product, commit = scaffold_with_pin(tmp_path)
    (root / "contracts" / "openglass-pin.yaml").unlink()
    result = validate(root, "--pin-source", str(product))
    assert result.returncode == 2
    assert "neutral-pin-missing" in result.stderr
    assert "openglass-pin.yaml" in result.stderr


# --- no way to answer: a SKIP, never a failure ------------------------------

@WINDOWS_SKIP  # the stub `gh` is a `#!` script; Windows executes none
def test_a_neutral_pin_with_no_reachable_source_is_skipped(tmp_path):
    """No --pin-source, no env var, no sibling checkout, and `gh` itself
    cannot read the forge (stubbed here so this stays fully offline, exactly
    as `test_scaffold_pin_and_reuse.py` stubs it for the scaffold's own
    unreadable-pin case). The run must still exit 0: the absence of a way to
    verify a pin is not evidence that the pin is wrong.
    """
    root, product, commit = scaffold_with_pin(tmp_path)
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
    result = validate(root, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "skip" in result.stdout
    assert "openGlass" in result.stdout
    assert "gh-unreadable" in result.stdout
    assert "pins ok" in result.stdout


def test_a_project_with_no_declared_pins_is_unaffected(tmp_path):
    """The ordinary case — no `--pin` at all — runs the same validator with
    nothing new to check."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    result = run_script(SCAFFOLD, "--org", "testorg", "--project", "Atlas",
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    result = validate(work / "Atlas")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "pins ok" in result.stdout
