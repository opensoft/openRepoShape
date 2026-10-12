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
from pathlib import Path

import pytest

from conftest import SCAFFOLD, WINDOWS_SKIP, git, run_script
from test_scaffold_pin_and_reuse import (assert_pin_digest_recomputed,
                                         product_repo)

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


# --- what a --pin-source value MEANS, and what is said of it (#295) ---------
#
# `--pin-source` is `[PRODUCT=]PATH`, and a path may hold an `=`. Splitting
# every value at its first `=` made `a=b/openGlass` a source keyed to a
# product `a` that nothing declares: never consulted, so the digest went to
# `gh api` and a `skip`, exit 0. Now the text before the first `=` is a
# product only when it names a declared pin; a source somebody named that
# cannot answer is a finding, never a traceback; and a value no pin used is
# said, never silent.

def logging_gh(tmp_path, **extra) -> tuple[dict, Path]:
    """`(env, log)`: a `gh` first on PATH that records its arguments in `log`
    and fails, as `tests/test_scaffold_pin_collisions.py`'s `world` installs
    one, plus `extra` variables. Every run below that could reach `gh api` on
    a regression carries it, so none can reach the forge where a `#!` script
    runs. Windows runs no `#!` script, so there the record stays empty
    whatever happens, and the `digest recomputes` line, or the finding,
    carries the claim on every platform."""
    bin_dir, log = tmp_path / "fakebin", tmp_path / "gh.log"
    bin_dir.mkdir()
    gh = bin_dir / "gh"
    gh.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import os, sys
        with open(os.environ["GH_STUB_LOG"], "a", encoding="utf-8") as log:
            log.write(" ".join(sys.argv[1:]) + "\\n")
        print("HTTP 404: Not Found", file=sys.stderr)
        sys.exit(97)
        """), encoding="utf-8")
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    env = {"PATH": f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}",
           "GH_STUB_LOG": str(log), **extra}
    return env, log


def gh_never_ran(log: Path) -> None:
    assert not log.exists(), (
        f"gh was run: {log.read_text(encoding='utf-8')}")


def standin_at(product: Path, target: Path) -> Path:
    """A clone of the pinned stand-in at `target`, so it holds the commit
    the pin names. `=` is a legal character in a path on all three
    platforms, so no test here is skipped for spelling one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    git("clone", "-q", "--", str(product), str(target), cwd=target.parent)
    return target


def validate_from(cwd: Path, root: Path, *args, env=None):
    """`validate-pins.py` run from `cwd`, so a relative `--pin-source` is
    read the way a person standing there typed it."""
    return run_script(root / "scripts" / "validate-pins.py", *args, cwd=cwd,
                      env=env)


def test_a_bare_pin_source_whose_path_holds_an_equals_sign_is_a_path(
        tmp_path):
    """THE DEFECT. The stand-in is cloned under a directory named `a=b` and
    passed BARE. `a` is not a declared pin, so the whole value is the path:
    the digest recomputes from it, nothing is skipped, and `gh` never runs.
    It used to be read as a source for a product `a`, which no pin looks
    up."""
    root, product, commit = scaffold_with_pin(tmp_path)
    standin_at(product, tmp_path / "a=b" / "openGlass")
    env, log = logging_gh(tmp_path)
    result = validate_from(tmp_path, root, "--pin-source", "a=b/openGlass",
                           env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert_pin_digest_recomputed(result, "openGlass", commit)
    assert "digest recomputes (--pin-source)\n" in result.stdout, (
        "the bare reading must be the one that answered")
    assert "note --pin-source" not in result.stdout
    assert "pins ok" in result.stdout
    gh_never_ran(log)


def test_a_declared_pin_before_the_equals_is_the_key_even_over_a_directory(
        tmp_path):
    """`openGlass=x/openGlass` where a directory `openGlass=x` holds the
    stand-in and `x/openGlass` does not exist. `openGlass` IS a declared pin,
    so the keyed reading wins — decided by the manifest, not by the disk —
    and the missing `x/openGlass` is the `neutral-pin-source-unreadable`
    finding, exit 1, where it used to be a `FileNotFoundError` traceback.
    The finding names the other reading, and `./` asks for it."""
    root, product, commit = scaffold_with_pin(tmp_path)
    standin_at(product, tmp_path / "openGlass=x" / "openGlass")
    env, log = logging_gh(tmp_path)
    keyed = validate_from(tmp_path, root, "--pin-source",
                          "openGlass=x/openGlass", env=env)
    assert keyed.returncode == 1, keyed.stderr + keyed.stdout
    assert "Traceback" not in keyed.stderr, keyed.stderr
    assert ("FINDING neutral-pin-source-unreadable: contracts/openglass-"
            f"pin.yaml: {Path('x', 'openGlass')} (--pin-source openGlass=...)"
            in keyed.stderr), keyed.stderr
    assert "no such directory" in keyed.stderr
    assert ("`openGlass=x/openGlass` is also a directory; `--pin-source "
            "./openGlass=x/openGlass` reads it as one." in keyed.stderr)
    assert "openGlass: pin commit" not in keyed.stdout

    whole = validate_from(tmp_path, root, "--pin-source",
                          "./openGlass=x/openGlass", env=env)
    assert whole.returncode == 0, whole.stderr + whole.stdout
    assert_pin_digest_recomputed(whole, "openGlass", commit)
    gh_never_ran(log)


@pytest.mark.parametrize("spelling, said", [
    ("openGlass={missing}", "no such directory"),
    ("openGlass={file}", "it is a file, not a directory"),
    ("{missing}", "no such directory"),
    ("$SHAPE_PIN_SOURCE_OPENGLASS={missing}", "no such directory"),
], ids=["keyed-missing", "keyed-file", "bare-missing", "env-missing"])
def test_an_explicit_pin_source_that_is_not_a_directory_is_a_finding(
        tmp_path, spelling, said):
    """A source somebody NAMED that is not there at all, or is a file, is
    the same `neutral-pin-source-unreadable` finding a directory that is not
    a checkout already was, with its remediation: never a skip, and never
    the traceback `git`'s `cwd=` raised before (#295)."""
    root, product, commit = scaffold_with_pin(tmp_path)
    missing, file = tmp_path / "missing", tmp_path / "a-file"
    file.write_text("not a checkout\n", encoding="utf-8")
    value = spelling.format(missing=missing, file=file)
    if value.startswith("$"):
        name, _, path = value[1:].partition("=")
        env, log = logging_gh(tmp_path, **{name: path})
        args = ()
    else:
        env, log = logging_gh(tmp_path)
        args = ("--pin-source", value)
    result = validate(root, *args, env=env)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert "FINDING neutral-pin-source-unreadable:" in result.stderr
    assert f"could not answer for opensoft/openGlass @ {commit}: {said}" \
        in result.stderr, result.stderr
    assert ("Remediation: point it at a clone of opensoft/openGlass that has "
            "that commit" in result.stderr)
    assert "skip openGlass" not in result.stdout
    gh_never_ran(log)


def test_a_pin_source_no_declared_pin_used_is_a_note_and_changes_no_exit(
        tmp_path):
    """Each value no pin read is NOTED on stdout, named as typed, with why,
    and the run still exits 0. Here the keyed value answers `openGlass`; the
    first bare one is replaced by a later bare one; and that later one is a
    MISTYPED key, `openGlas=`, read as a path because nothing declares
    `openGlas` — which used to be a silent `skip` and one `gh api` call."""
    root, product, commit = scaffold_with_pin(tmp_path)
    spare = tmp_path / "spare"
    spare.mkdir()
    env, log = logging_gh(tmp_path)
    typo = f"openGlas={product}"
    result = validate(root, "--pin-source", str(spare),
                      "--pin-source", f"openGlass={product}",
                      "--pin-source", typo, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == ""
    assert_pin_digest_recomputed(result, "openGlass", commit)
    assert "(--pin-source openGlass=...)" in result.stdout
    assert (f"  note --pin-source {spare}: not used — the later `--pin-source "
            f"{typo}` replaced it.\n" in result.stdout), result.stdout
    assert (f"  note --pin-source {typo}: not used — each declared pin had a "
            "more specific source" in result.stdout), result.stdout
    assert ("It was read as a PATH: `openGlas` is not a declared "
            "neutral-product pin (declared: openGlass).\n" in result.stdout)
    assert f"note --pin-source openGlass={product}" not in result.stdout
    assert result.stdout.endswith("pins ok\n")

    # A keyed value a later one for the same pin replaced, in any case.
    replaced = validate(root, "--pin-source", f"openGlass={spare}",
                        "--pin-source", f"OPENGLASS={product}", env=env)
    assert replaced.returncode == 0, replaced.stderr + replaced.stdout
    assert_pin_digest_recomputed(replaced, "openGlass", commit)
    assert (f"  note --pin-source openGlass={spare}: not used — the later "
            f"`--pin-source OPENGLASS={product}` replaced it.\n"
            in replaced.stdout), replaced.stdout
    gh_never_ran(log)


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
