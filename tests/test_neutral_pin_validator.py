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

import errno
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (SCAFFOLD, WINDOWS_SKIP, blank_unnamed_pin_sources, git,
                      run_script)
from repo_shape import tree_digest
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
# `gh api` and a `skip`, exit 0. Now the text before an `=` is a product
# only when it names a declared pin (the longest that leaves a path, #1053,
# below); a source somebody named that cannot answer is a finding, never a
# traceback; and a value no pin used is said, never silent.

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
    assert "  note " not in keyed.stdout, (
        "a source that was asked and failed is a finding, never also a note")

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
    assert "  note " not in result.stdout, (
        "a source that was asked and failed is a finding, never also a note")
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

    # The same value given twice is one value: noted once, for its own
    # reason, and never as having replaced itself.
    twice = validate(root, "--pin-source", f"openGlass={product}",
                     "--pin-source", str(spare), "--pin-source", str(spare),
                     env=env)
    assert twice.returncode == 0, twice.stderr + twice.stdout
    assert twice.stdout.count("  note ") == 1, twice.stdout
    assert (f"  note --pin-source {spare}: not used — each declared pin had a "
            "more specific source" in twice.stdout), twice.stdout
    assert "replaced it" not in twice.stdout
    gh_never_ran(log)


#: A directory mode denies nothing on Windows, where `chmod` has no search
#: bit to clear, and nothing to root.
SEARCH_DENIED = pytest.mark.skipif(
    os.name == "nt" or getattr(os, "geteuid", lambda: 1)() == 0,
    reason="needs a POSIX directory mode that denies search: Windows has no "
           "search bit for chmod to clear, and root is not stopped by one")


@pytest.mark.parametrize("case", [
    pytest.param("parent-not-searchable", marks=SEARCH_DENIED),
    pytest.param("source-not-searchable", marks=SEARCH_DENIED),
    "name-too-long",
])
def test_a_pin_source_that_cannot_be_entered_or_named_is_a_finding(
        tmp_path, case):
    """Every `OSError` a named source raises is the finding, with the
    system's own reason (#295 review, SHOULD-1). `exists()`/`is_dir()`
    before 3.14 raise anything but a missing path, so a source under a
    parent this user cannot enter, or a name longer than the filesystem
    takes, was a traceback on 3.9 to 3.13 and, on 3.14, "no such directory"
    for a directory that is there. A source that exists but cannot be
    entered fails in `git`'s `cwd=`, which the second guard answers.

    Each value is RELATIVE, run from `tmp_path`, so the long name is one
    path component the system has to refuse by name, both when the source
    is looked at and when the finding asks whether the whole value is a
    directory; an absolute one stops at its first missing component
    instead. It runs everywhere:
    whatever Windows calls it, it is an `OSError`, so there the finding and
    the absent traceback are asserted, and the reason is POSIX's
    `ENAMETOOLONG` only where that is the call."""
    root, product, commit = scaffold_with_pin(tmp_path)
    locked = tmp_path / "locked"
    said = os.strerror(errno.EACCES)
    if case == "parent-not-searchable":
        source = Path("locked", "openGlass")
    elif case == "source-not-searchable":
        source = Path("locked")
    else:
        source, locked = Path("n" * 300), None
        said = None if os.name == "nt" else os.strerror(errno.ENAMETOOLONG)
    if locked is not None:
        standin_at(product, tmp_path / source)
    env, log = logging_gh(tmp_path)
    if locked is not None:
        locked.chmod(0)
    try:
        result = validate_from(tmp_path, root, "--pin-source",
                               f"openGlass={source.as_posix()}", env=env)
    finally:
        if locked is not None:
            locked.chmod(0o700)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert ("FINDING neutral-pin-source-unreadable: contracts/openglass-"
            f"pin.yaml: {source} (--pin-source openGlass=...) could not "
            f"answer for opensoft/openGlass @ {commit}: " in result.stderr)
    if said is not None:
        assert f"@ {commit}: {said}\n" in result.stderr, result.stderr
    if locked is not None:
        assert "no such directory" not in result.stderr, result.stderr
    assert "  note " not in result.stdout
    gh_never_ran(log)


@pytest.mark.parametrize("encoding, spelled", [
    ("cp1252", "\\u65e5\\u672c"),
    ("cp1252:surrogateescape", "\\u65e5\\u672c"),
    ("cp1252:replace", "??"),
])
def test_a_note_naming_what_stdout_cannot_encode_never_raises(
        tmp_path, encoding, spelled):
    """The note echoes a `--pin-source` as typed, so a value stdout cannot
    encode raised `UnicodeEncodeError` and turned a passing run into exit 1
    (#295 review, SHOULD-2); main's copy, which printed no such line, exits
    0 on the same arguments. cp1252 is what Windows gives a stdout that is
    not the console, with `surrogateescape` its default handler; `cp1252`
    alone is `strict`. Those two, the handlers that raise, now escape the
    name as stderr would write it. A handler somebody CHOSE is theirs and
    is kept: under `cp1252:replace` the name is `??`, never escaped over
    their choice. The child's stdout is read as BYTES and decoded strictly
    as cp1252, so a byte the code page could not hold fails here."""
    root, product, commit = scaffold_with_pin(tmp_path)
    unused = tmp_path / "日本"
    env, log = logging_gh(tmp_path, PYTHONIOENCODING=encoding)
    full = blank_unnamed_pin_sources({**os.environ, **env}, env)
    result = subprocess.run(
        [sys.executable, str(root / "scripts" / "validate-pins.py"),
         "--pin-source", f"openGlass={product}", "--pin-source", str(unused)],
        cwd=str(root), capture_output=True, env=full,
        stdin=subprocess.DEVNULL, check=False)
    stderr = result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, stderr
    assert "Traceback" not in stderr, stderr
    stdout = result.stdout.decode("cp1252")
    assert f"openGlass: pin commit {commit[:12]} digest recomputes" in stdout
    shown = str(unused).replace("日本", spelled)
    assert f"  note --pin-source {shown}: not used — " in stdout, stdout
    assert stdout.endswith("pins ok\n") or stdout.endswith("pins ok\r\n")
    gh_never_ran(log)


def test_a_pin_source_that_is_a_symlink_to_a_checkout_recomputes(tmp_path):
    """A named source that is itself a symlink to the stand-in answers, as
    it always did: `_digest_from_source` asks `stat()`, which follows the
    link to the directory, and never `lstat()`, which would call the link a
    file and refuse a checkout somebody linked into place (#295 review,
    NIT-B). Skipped on Windows, where a symlink needs a privilege the
    runner's user may not hold, and wherever `os.symlink` refuses."""
    if os.name == "nt":
        pytest.skip("a symlink on Windows needs a privilege (or developer "
                    "mode) this run may not have")
    root, product, commit = scaffold_with_pin(tmp_path)
    link = tmp_path / "linked-openGlass"
    try:
        os.symlink(product, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"this platform will not make a symlink here: {exc}")
    env, log = logging_gh(tmp_path)
    result = validate(root, "--pin-source", f"openGlass={link}", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert_pin_digest_recomputed(result, "openGlass", commit)
    assert "(--pin-source openGlass=...)" in result.stdout
    assert "  note " not in result.stdout
    gh_never_ran(log)


# --- #1053: a key is the longest declared pin that leaves a path ------------
#
# The text before an `=` is a product only where it names a declared pin, and
# of the texts that do, the longest that leaves a path after it is the key, as
# the naming gate has read a `--link-source` key since #980. Read at the first
# `=`, `open=y=<tree>` was a bare PATH where `open=y` alone is declared, and
# `open`'s where both are. Where no declared pin holds `=`, every value is
# read as before. No scaffold writes a pin holding `=` (`--pin` names are
# `[A-Za-z0-9_.-]`), so each row declares its pins by hand.

def declare_by_hand(root: Path, *pins: tuple[str, Path, str],
                    seed: str = "openGlass") -> None:
    """`root`'s `neutral_product_pins:` made `pins` BY HAND, each `(name,
    tree, commit)`, in place of the scaffolded pin on `seed`, and each with
    a pin file written from `seed`'s: `contracts/<name lowercased>-pin.yaml`,
    its `source_repository` `opensoft/<name>` and its commit and digest that
    tree's. `=` is legal in a file name on all three platforms
    (`standin_at`)."""
    manifest = root / "project.yaml"
    text = manifest.read_bytes().decode("utf-8")
    entry = f"\n  - {seed}\n"
    assert entry in text, f"fixture drift: no {seed} entry"
    declared = "".join(f"  - {name}\n" for name, _tree, _commit in pins)
    manifest.write_bytes(
        text.replace(entry, f"\n{declared}", 1).encode("utf-8"))
    seeded = root / "contracts" / f"{seed.lower()}-pin.yaml"
    written = seeded.read_bytes().decode("utf-8")
    seeded.unlink()
    old_commit = written.split('commit: "')[1].split('"')[0]
    old_digest = written.split('tree_sha256: "')[1].split('"')[0]
    for name, tree, commit in pins:
        digest = tree_digest(tree, commit)
        pin = (written.replace(f'"{old_commit}"', f'"{commit}"', 1)
               .replace(f'"{old_digest}"', f'"{digest}"', 1)
               .replace(f'product: "{seed}"', f'product: "{name}"', 1)
               .replace(f"source_repository: opensoft/{seed}\n",
                        f"source_repository: opensoft/{name}\n", 1))
        assert pin.count(commit) == 1, "fixture drift: the pin's commit"
        assert f"source_repository: opensoft/{name}\n" in pin, (
            "fixture drift: the pin's source_repository")
        (root / "contracts" / f"{name.lower()}-pin.yaml").write_bytes(
            pin.encode("utf-8"))


def recomputes_from(result, product: str, commit: str, how: str) -> None:
    """`product`'s digest recomputed from the source `how` names."""
    line = (f"{product}: pin commit {commit[:12]} digest recomputes "
            f"({how})\n")
    assert line in result.stdout, result.stderr + result.stdout


@pytest.mark.parametrize("typed", ["open=y={tree}", "OPEN=Y={tree}"],
                         ids=["as-declared", "in-capitals"])
def test_a_declared_pin_holding_an_equals_sign_is_its_own_key(tmp_path,
                                                              typed):
    """THE DEFECT. `open=y` is declared, and `--pin-source open=y=<tree>`
    is typed as `--pin-source openGlass=<tree>` is. It is `open=y`'s source
    and its digest recomputes from it, in capitals too, by
    `pin_product_key`. Read at the first `=`, `open` named no pin, so the
    whole value was a bare PATH that is not there: the
    `neutral-pin-source-unreadable` FINDING, exit 1, saying `open` is not a
    declared pin."""
    root, product, commit = scaffold_with_pin(tmp_path)
    declare_by_hand(root, ("open=y", product, commit))
    env, log = logging_gh(tmp_path)
    result = validate(root, "--pin-source", typed.format(tree=product),
                      env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == ""
    recomputes_from(result, "open=y", commit, "--pin-source open=y=...")
    assert "  note " not in result.stdout, result.stdout
    assert result.stdout.endswith("pins ok\n")
    gh_never_ran(log)


@pytest.mark.parametrize("first, then", [
    pytest.param("open={a}", "open=y={b}", id="open-first"),
    pytest.param("open=y={b}", "open={a}", id="open=y-first"),
    pytest.param("open=./y=dir", "open=y={b}",
                 id="a-path-that-begins-like-the-longer-pin"),
])
def test_each_pin_reads_its_own_source_where_one_name_begins_another(
        tmp_path, first, then):
    """`open` and `open=y` both declared, each with a tree of its own:
    `open=y=<b>` is `open=y`'s and `open=<a>` is `open`'s, in either order,
    and neither replaces the other. A path that begins like the longer
    pin's name is given after `./`: `open=./y=dir` is `open`'s. Read at the
    first `=`, both values were `open`'s, the later replaced the earlier,
    and `open=y` read neither."""
    root, product, commit = scaffold_with_pin(tmp_path)
    other, other_commit = product_repo(tmp_path / "second", name="openInk")
    a = standin_at(product, tmp_path / "y=dir")
    declare_by_hand(root, ("open", a, commit),
                    ("open=y", other, other_commit))
    env, log = logging_gh(tmp_path)
    result = validate_from(tmp_path, root,
                           "--pin-source", first.format(a=a, b=other),
                           "--pin-source", then.format(a=a, b=other),
                           env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == ""
    recomputes_from(result, "open", commit, "--pin-source open=...")
    recomputes_from(result, "open=y", other_commit, "--pin-source open=y=...")
    assert "  note " not in result.stdout, result.stdout
    gh_never_ran(log)


def test_a_shorter_pin_that_leaves_a_path_is_the_key(tmp_path):
    """`open=y=` with `open` declared too: `open=y` leaves no path, `open`
    leaves `y=`, so the value is `open`'s, with the path `y=`, as the naming
    gate reads `--link-source open=y=` where a chain names `open`. It is
    never refused as naming no path: a shorter pin is named, with one."""
    root, product, commit = scaffold_with_pin(tmp_path)
    other, other_commit = product_repo(tmp_path / "second", name="openInk")
    declare_by_hand(root, ("open", product, commit),
                    ("open=y", other, other_commit))
    env, log = logging_gh(tmp_path)
    result = validate(root, "--pin-source", "open=y=",
                      "--pin-source", f"open=y={other}", env=env)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert ("FINDING neutral-pin-source-unreadable: contracts/open-pin.yaml: "
            f"y= (--pin-source open=...) could not answer for opensoft/open "
            f"@ {commit}: no such directory\n" in result.stderr), (
        result.stderr)
    recomputes_from(result, "open=y", other_commit, "--pin-source open=y=...")
    gh_never_ran(log)


@pytest.mark.parametrize("typed", [" open=y=x", "opensoft/open=y=x",
                                   "open=z=x"],
                         ids=["a-blank", "an-owner", "no-declared-pin"])
def test_a_value_naming_no_declared_pin_is_a_bare_path_whole(tmp_path,
                                                             typed):
    """A key is read WHOLE, never stripped and never cut at a `/`: with
    `open=y` declared, ` open=y=x` and `opensoft/open=y=x` name no pin, and
    `open=z=x` names none at any of its `=`, so each is a bare PATH, the
    whole value, and the directory spelled so answers, as it did when every
    key ended at the first `=`."""
    root, product, commit = scaffold_with_pin(tmp_path)
    standin_at(product, tmp_path / typed)
    declare_by_hand(root, ("open=y", product, commit))
    env, log = logging_gh(tmp_path)
    result = validate_from(tmp_path, root, "--pin-source", typed, env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == ""
    recomputes_from(result, "open=y", commit, "--pin-source")
    assert "  note " not in result.stdout, result.stdout
    gh_never_ran(log)


def test_a_value_read_as_a_path_names_the_text_before_its_first_equals(
        tmp_path):
    """The note's second sentence for a value no declared pin is named in
    keeps its words: the text before the first `=`, the shortest that
    `_read_source` tried, as it named it when that was the only text tried."""
    root, product, commit = scaffold_with_pin(tmp_path)
    declare_by_hand(root, ("open=y", product, commit))
    env, log = logging_gh(tmp_path)
    result = validate(root, "--pin-source", f"open=y={product}",
                      "--pin-source", "open=z=x", env=env)
    assert result.returncode == 0, result.stderr + result.stdout
    recomputes_from(result, "open=y", commit, "--pin-source open=y=...")
    assert ("  note --pin-source open=z=x: not used — each declared pin had "
            "a more specific source (a keyed --pin-source, "
            "SHAPE_PIN_SOURCE_<PRODUCT>, or a checkout beside this assembly "
            "root) or was not recomputed. It was read as a PATH: `open` is "
            "not a declared neutral-product pin (declared: open=y).\n"
            in result.stdout), result.stdout
    gh_never_ran(log)


def test_a_keyed_pin_is_named_as_the_manifest_spells_it(tmp_path):
    """A value keyed in capitals names the pin as `project.yaml` spells it,
    never as the value does: `OPEN=Y=<tree>` is `open=y`'s, and where the
    pin's recorded digest is malformed, so nothing is ever recomputed, the
    note says `open=y`'s digest was not recomputed and not `OPEN=Y`'s
    (#1053, after #712). The pin file is `open=y-pin.yaml`, as written."""
    root, product, commit = scaffold_with_pin(tmp_path)
    declare_by_hand(root, ("open=y", product, commit))
    pin = root / "contracts" / "open=y-pin.yaml"
    written = pin.read_bytes().decode("utf-8")
    digest = written.split('tree_sha256: "')[1].split('"')[0]
    pin.write_bytes(written.replace(f'"{digest}"', '"x"', 1).encode("utf-8"))
    env, log = logging_gh(tmp_path)
    typed = f"OPEN=Y={product}"
    result = validate(root, "--pin-source", typed, env=env)
    assert result.returncode == 1, result.stderr + result.stdout
    assert ("FINDING neutral-pin-digest-malformed: contracts/open=y-pin.yaml: "
            "digests.tree_sha256 is 'x', not 64 hex" in result.stderr), (
        result.stderr)
    assert (f"  note --pin-source {typed}: not used — open=y's digest was not "
            "recomputed from any source.\n" in result.stdout), result.stdout
    gh_never_ran(log)


@pytest.mark.parametrize("typed, path", [
    pytest.param("openGlass==x", "=x", id="a-path-that-begins-with-equals"),
    pytest.param("openGlass= ", " ", id="a-blank-path"),
])
def test_a_keyed_path_at_the_old_split_s_corners_is_still_keyed(
        tmp_path, typed, path):
    """Where no declared pin holds `=`, every value is read as before: a
    path that begins with `=` and a blank path are still `openGlass`'s,
    asked and named, and neither is refused as naming no path or said to
    have been read as a PATH."""
    root, product, commit = scaffold_with_pin(tmp_path)
    env, log = logging_gh(tmp_path)
    result = validate(root, "--pin-source", typed, env=env)
    assert result.returncode == 1, result.stderr + result.stdout
    assert ("FINDING neutral-pin-source-unreadable: contracts/openglass-"
            f"pin.yaml: {path} (--pin-source openGlass=...) could not answer "
            f"for opensoft/openGlass @ {commit}: no such directory\n"
            in result.stderr), result.stderr
    assert "REFUSED" not in result.stderr
    assert "read as a PATH" not in result.stderr + result.stdout
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
