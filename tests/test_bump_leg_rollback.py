# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: a bump that fails for ANY reason once its first byte
has moved puts every byte back (#253).

`_apply_rewrite` checks the leg out, writes the pin and each workflow file,
stages them and runs the validators. Its rollback used to be a handler for
`Refusal` and `CommandFailed` alone, so a `PermissionError` on a workflow
file, a `UnicodeError` from echoing a validator's output or an interrupt left
the pin rewritten, the leg on the new commit and the index changed, behind a
traceback. `tests/test_bump_leg.py` holds the red-validator rollback; this
file holds the failures that rollback never saw.

EVERY TEST COMPARES THE WHOLE TREE, not the one thing its failure touched:
the root's HEAD, the pin's bytes, every workflow's bytes, the gitlink the
index records, `git diff --cached --quiet`, the leg's HEAD and the branch the
leg stood on. A rollback that put the pin back and forgot the index is the
bug, so a test that read only the pin could not fail for it.

The failure that needs the operating system (a read-only file) runs
`bump-leg.py` as a subprocess. The ones that need a failure at an exact step
(a write that dies half way, a validator's output that cannot be decoded or
echoed, an interrupt, a rollback step that itself fails) call `main`
in-process with ONE module attribute replaced, and everything else, git
included, real.

THE ECHO IS A STREAM THAT RAISES, NOT A CODEC SETTING. A real `strict` stdout
(`PYTHONIOENCODING=cp1252`) is what #253 was found with, but
`escape_what_stdout_cannot_encode` (#214) reconfigures exactly that stream to
`backslashreplace` at the top of `main`, so a test built on it would stop
meaning anything the day #214 lands. A stream that raises
`UnicodeEncodeError` from `write` stays a failure in the echo whichever of
those fixes are in.
"""

from __future__ import annotations

import errno
import io
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PROJECT, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    branched, bump, bump_leg_module, reference_both_legs,
)

#: Where the advanced spec commit is pushed. Not `test_bump_leg.py`'s branch:
#: both modules share the session's bare remotes, and a second, different
#: commit pushed to the same branch name would be refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-rollback-advance"


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = tmp_path_factory.mktemp("spec-advance-rollback") / f"{PROJECT}-spec"
    proc = subprocess.run(
        ["git", "clone", "-q",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "ROLLBACK-CONTRACT.md").write_text("# a contract the leg gained\n")
    git("add", "--", "ROLLBACK-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the rollback tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def snapshot(project: Path) -> dict:
    """Everything a bump may change and a rollback has to put back."""
    leg = project / "spec"
    workflows = sorted((project / ".github" / "workflows").glob("*.y*ml"))
    return {
        "head": git("rev-parse", "HEAD", cwd=project).stdout.strip(),
        "pin": (project / "contracts" / "spec-pin.yaml").read_bytes(),
        "workflows": {path.name: path.read_bytes() for path in workflows},
        "gitlink": git("ls-files", "-s", "--", "spec", cwd=project).stdout,
        "status": git("status", "--porcelain", cwd=project).stdout,
        "leg_head": git("rev-parse", "HEAD", cwd=leg).stdout.strip(),
        "leg_branch": git("symbolic-ref", "--quiet", "HEAD", cwd=leg,
                          check=False).stdout.strip(),
    }


def assert_nothing_changed(project: Path, before: dict) -> None:
    after = snapshot(project)
    for key, value in before.items():
        assert after[key] == value, f"{key} is not as it was found"
    assert git("diff", "--cached", "--quiet", cwd=project,
               check=False).returncode == 0, "the index carries a staged change"


def prepared(project: Path) -> dict:
    """A bump-ready root: a workflow naming both legs, committed; the spec leg
    ON its branch, as `bootstrap.py` leaves it, so a rollback that restored the
    commit but left the leg detached is a failure too; a bump branch."""
    reference_both_legs(project)
    git("checkout", "-q", "-B", "main", cwd=project / "spec")
    branched(project)
    return snapshot(project)


def run_main(module, project: Path, scaffolded: dict, to: str) -> int:
    return module.main(["--root", str(project), "--leg", "spec", "--to", to,
                        "--local-remote-dir", str(scaffolded["remotes"])])


def raiser(exc: BaseException):
    def raise_it(*_args, **_kwargs):
        raise exc
    return raise_it


class CannotEncode(io.StringIO):
    """A stdout that holds what cp1252 holds and raises on anything else, as a
    redirected Windows stdout does: `…` is fine, U+FFFD is not."""

    def write(self, text):
        text.encode("cp1252")
        return super().write(text)


# --- the operating system's failures, run for real --------------------------

def test_a_workflow_file_the_operator_cannot_write_is_refused_and_put_back(
        project, scaffolded, advanced):
    """THE ISSUE'S OWN REPRODUCTION: a tracked workflow file with a
    read-only attribute. The leg was moved and the pin written before the
    write failed; the file itself was never opened, so it is the one thing
    the rollback must NOT report as unrestorable."""
    before = prepared(project)
    legs = project / ".github" / "workflows" / "legs.yml"
    legs.chmod(stat.S_IREAD)
    try:
        if os.access(legs, os.W_OK):
            pytest.skip("this account can write a read-only file (root)")
        result = bump(project, scaffolded, advanced)
    finally:
        legs.chmod(stat.S_IREAD | stat.S_IWRITE)

    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED bump-leg-rewrite-failed" in result.stderr
    assert "PermissionError" in result.stderr
    assert "Traceback" not in result.stderr, "a refusal, never a traceback"
    assert "rolled back" in result.stderr
    assert "rolling the bump back" not in result.stderr, (
        "the file was never changed, so there was nothing it could not put "
        "back")
    assert_nothing_changed(project, before)


# --- a failure at an exact step, called in-process --------------------------

def test_a_write_that_dies_half_way_leaves_the_file_as_it_was(
        project, scaffolded, advanced, bump_leg_module, monkeypatch, capsys):
    """A full disk after the file was truncated and part of it written: the
    bytes on disk are neither the old nor the new ones, and only the bytes
    kept before the write can put the file back."""
    before = prepared(project)
    real_write = bump_leg_module.write_lf

    def disk_full(path, text):
        if path.name != "legs.yml":
            return real_write(path, text)
        path.write_bytes(text.encode("utf-8")[:20])
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC), str(path))

    monkeypatch.setattr(bump_leg_module, "write_lf", disk_full)
    code = run_main(bump_leg_module, project, scaffolded, advanced)

    err = capsys.readouterr().err
    assert code == 2
    assert "REFUSED bump-leg-rewrite-failed" in err
    assert os.strerror(errno.ENOSPC) in err
    assert_nothing_changed(project, before)


@pytest.mark.parametrize("what", ["decoded", "echoed"])
def test_a_validator_output_that_cannot_be_decoded_or_echoed_is_refused_and_put_back(
        what, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        capsys):
    """The statement after the leg moved, the files were written and the
    index was staged: reading the validator's output (the decode error #230
    turns into a replacement character) and writing it to a stdout that
    cannot hold that character (the crash it moves to)."""
    before = prepared(project)
    if what == "decoded":
        monkeypatch.setattr(bump_leg_module, "run_validator", raiser(
            UnicodeDecodeError("utf-8", b"\x85", 0, 1, "invalid start byte")))
        expected = "UnicodeDecodeError"
    else:
        monkeypatch.setattr(
            bump_leg_module, "run_validator",
            lambda root, script: (0, "validator says: \ufffd\n"))
        monkeypatch.setattr(sys, "stdout", CannotEncode())
        expected = "UnicodeEncodeError"

    code = run_main(bump_leg_module, project, scaffolded, advanced)

    err = capsys.readouterr().err
    assert code == 2
    assert "REFUSED bump-leg-rewrite-failed" in err
    assert expected in err
    assert "rolled back" in err
    assert_nothing_changed(project, before)


@pytest.mark.parametrize("step, failure", [
    ("write_lf", KeyboardInterrupt()),
    ("run_validator", KeyboardInterrupt()),
    ("run_validator", RuntimeError("a defect in this tool")),
], ids=["interrupt-writing", "interrupt-validating", "defect-validating"])
def test_any_other_failure_puts_every_byte_back_and_is_re_raised_as_itself(
        step, failure, project, scaffolded, advanced, bump_leg_module,
        monkeypatch):
    """An interrupt, or a defect that is not the operator's to fix, is not
    made into a refusal: it reaches the interpreter as what it is, AFTER the
    tree is back. `write_lf` fails on the SECOND file, with the pin already
    rewritten; `run_validator` fails with the index staged."""
    before = prepared(project)
    if step == "write_lf":
        real_write = bump_leg_module.write_lf

        def second_write_fails(path, text):
            if path.name == "legs.yml":
                raise failure
            return real_write(path, text)
        monkeypatch.setattr(bump_leg_module, "write_lf", second_write_fails)
    else:
        monkeypatch.setattr(bump_leg_module, "run_validator", raiser(failure))

    with pytest.raises(type(failure)) as raised:
        run_main(bump_leg_module, project, scaffolded, advanced)

    assert raised.value is failure
    assert_nothing_changed(project, before)


@pytest.mark.parametrize("failure", ["validators-red", "unwritable"])
def test_a_rollback_step_that_fails_is_named_and_the_others_still_run(
        failure, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        capsys):
    """THE ROLLBACK NEVER RAISES OVER THE FAILURE: with the leg's checkout the
    one step that cannot be put back, the files and the index still are, the
    step is named, and the failure the person sees is the original one."""
    before = prepared(project)
    monkeypatch.setattr(bump_leg_module, "restore_leg", raiser(
        OSError(errno.EIO, "the leg's checkout is gone")))
    if failure == "validators-red":
        monkeypatch.setattr(bump_leg_module, "run_validator",
                            lambda root, script: (1, "pin-digest-mismatch\n"))
        original = "REFUSED bump-leg-validators-red"
    else:
        real_write = bump_leg_module.write_lf

        def refused(path, text):
            if path.name == "legs.yml":
                raise PermissionError(errno.EACCES, "Permission denied",
                                      str(path))
            return real_write(path, text)
        monkeypatch.setattr(bump_leg_module, "write_lf", refused)
        original = "REFUSED bump-leg-rewrite-failed"

    code = run_main(bump_leg_module, project, scaffolded, advanced)

    err = capsys.readouterr().err
    assert code == 2
    assert original in err, "the original failure is the one reported"
    assert "the checkout of spec/ could not be put back" in err
    assert "the leg's checkout is gone" in err
    if failure == "unwritable":
        assert "THE ROLLBACK WAS NOT COMPLETE" in err, (
            "a refusal does not claim a tree it did not restore")
    after = snapshot(project)
    for key in ("head", "pin", "workflows", "gitlink"):
        assert after[key] == before[key], f"{key} is not as it was found"
    assert git("diff", "--cached", "--quiet", cwd=project,
               check=False).returncode == 0, (
        "the index was still put back, though the leg's step failed before it")
