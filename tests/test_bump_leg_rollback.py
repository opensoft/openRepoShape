# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: a bump that fails for ANY reason once its first byte
has moved puts every byte back (#253).

`_apply_rewrite` checks the leg out, writes the pin and each workflow file,
stages them, runs the validators and commits. Its rollback used to be a
handler for `Refusal` and `CommandFailed` alone, so a `PermissionError` on a
workflow file, a `UnicodeError` from echoing a validator's output or an
interrupt left the pin rewritten, the leg on the new commit and the index
changed, behind a traceback. `tests/test_bump_leg.py` holds the red-validator
rollback; this file holds the failures that rollback never saw: those, a
commit git refuses, a forward checkout that moved the leg and then failed or
was cut off before it moved it, and a rollback step that fails or is
interrupted itself. It also holds the one failure that must NOT be rolled
back: one after the commit landed.

A REPORT NEVER CLAIMS A TREE THE ROLLBACK DID NOT RESTORE. Every failure
says, as a refusal's own text or as a line before the traceback, either that
every byte is back or that THE ROLLBACK WAS NOT COMPLETE.

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
import shlex
import stat
import sys
from pathlib import Path

import pytest

from conftest import PROJECT, cloned_just_pushed, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    branched, bump, bump_leg_module, reference_both_legs,
)

#: Where the advanced spec commit is pushed. Not `test_bump_leg.py`'s branch:
#: both modules share the session's bare remotes, and a second, different
#: commit pushed to the same branch name would be refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-rollback-advance"

#: The two things a report may say about the tree, spelled here rather than
#: imported, so a test reads what the operator reads.
ROLLED_BACK = "and the tree is exactly as it was"
NOT_COMPLETE = "THE ROLLBACK WAS NOT COMPLETE"


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-rollback") / f"{PROJECT}-spec")
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
        monkeypatch, capsys):
    """An interrupt, or a defect that is not the operator's to fix, is not
    made into a refusal: it reaches the interpreter as what it is, AFTER the
    tree is back. `write_lf` fails on the SECOND file, with the pin already
    rewritten; `run_validator` fails with the index staged.

    The traceback alone does not say whether the tree is back, so one line
    before it does: an operator who pressed Ctrl-C should not have to run
    `git status` to learn that nothing is left half-applied."""
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
    err = capsys.readouterr().err
    assert (f"{type(failure).__name__} while the bump was being applied"
            in err), err
    assert ROLLED_BACK in err, "the line says the tree is back"
    assert NOT_COMPLETE not in err


@pytest.mark.parametrize("failure",
                         ["validators-red", "unwritable", "command-failed"])
def test_a_rollback_step_that_fails_is_named_and_the_others_still_run(
        failure, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        capsys):
    """THE ROLLBACK NEVER RAISES OVER THE FAILURE: with the leg's checkout the
    one step that cannot be put back, the files and the index still are, the
    step is named, and the failure the person sees is the original one.

    AND NOTHING CLAIMS THE TREE IS BACK. A red validator's refusal, the
    refusal an `OSError` becomes and the line printed above a git command
    that failed all say THE ROLLBACK WAS NOT COMPLETE, and none of them says
    the tree is exactly as it was."""
    before = prepared(project)
    monkeypatch.setattr(bump_leg_module, "restore_leg", raiser(
        OSError(errno.EIO, "the leg's checkout is gone")))
    if failure == "validators-red":
        monkeypatch.setattr(bump_leg_module, "run_validator",
                            lambda root, script: (1, "pin-digest-mismatch\n"))
        original = "REFUSED bump-leg-validators-red"
    elif failure == "unwritable":
        real_write = bump_leg_module.write_lf

        def refused(path, text):
            if path.name == "legs.yml":
                raise PermissionError(errno.EACCES, "Permission denied",
                                      str(path))
            return real_write(path, text)
        monkeypatch.setattr(bump_leg_module, "write_lf", refused)
        original = "REFUSED bump-leg-rewrite-failed"
    else:
        real_run = bump_leg_module.run

        def add_fails(args, *rest, **kwargs):
            if args[:2] == ["git", "add"]:
                raise bump_leg_module.CommandFailed(
                    args, project, 128, "fatal: the index is locked")
            return real_run(args, *rest, **kwargs)
        monkeypatch.setattr(bump_leg_module, "run", add_fails)
        original = "REFUSED advancing a leg"

    code = run_main(bump_leg_module, project, scaffolded, advanced)

    err = capsys.readouterr().err
    assert code == 2
    assert original in err, "the original failure is the one reported"
    assert "the checkout of spec/ could not be put back" in err
    assert "the leg's checkout is gone" in err
    assert NOT_COMPLETE in err, (
        "a refusal does not claim a tree it did not restore")
    assert ROLLED_BACK not in err, (
        "and nothing says the tree is exactly as it was")
    after = snapshot(project)
    for key in ("head", "pin", "workflows", "gitlink"):
        assert after[key] == before[key], f"{key} is not as it was found"
    assert git("diff", "--cached", "--quiet", cwd=project,
               check=False).returncode == 0, (
        "the index was still put back, though the leg's step failed before it")


def test_an_interrupt_inside_a_rollback_step_is_named_and_the_steps_after_it_still_run(
        project, scaffolded, advanced, bump_leg_module, monkeypatch, capsys):
    """A SECOND Ctrl-C, while the rollback checks the leg out again — the
    likeliest next keystroke when a large leg is slow to check out. The step
    it lands in is named as not put back; the index step after it still
    runs, so the new pin, workflow and gitlink are not left staged; and the
    failure reported is still the first one, saying the rollback was not
    complete."""
    before = prepared(project)
    monkeypatch.setattr(bump_leg_module, "run_validator",
                        lambda root, script: (1, "pin-digest-mismatch\n"))
    monkeypatch.setattr(bump_leg_module, "restore_leg",
                        raiser(KeyboardInterrupt()))

    try:
        code = run_main(bump_leg_module, project, scaffolded, advanced)
    except KeyboardInterrupt:
        pytest.fail("the interrupt in a rollback step escaped the rollback, "
                    "so no step after it ran")

    err = capsys.readouterr().err
    assert code == 2
    assert "REFUSED bump-leg-validators-red" in err
    assert "the checkout of spec/ could not be put back: interrupted" in err
    assert NOT_COMPLETE in err
    assert ROLLED_BACK not in err
    after = snapshot(project)
    for key in ("head", "pin", "workflows", "gitlink"):
        assert after[key] == before[key], f"{key} is not as it was found"
    assert git("diff", "--cached", "--quiet", cwd=project,
               check=False).returncode == 0, (
        "the index step ran after the interrupted one")


# --- the leg, decided from the leg ------------------------------------------

def hook(repository: Path, hooks: Path, name: str, body: bytes) -> None:
    """A hook for `repository`, set the way `test_update_shape_add_ignored.py`
    sets one: `core.hooksPath` in the repository's own config, so a global
    one cannot replace it; a shebang script, which Git for Windows runs
    through its own `sh`; and a directory outside the tree, so `git status`
    never sees it."""
    hooks.mkdir(exist_ok=True)
    script = hooks / name
    script.write_bytes(b"#!/bin/sh\n" + body)
    script.chmod(0o755)
    git("config", "core.hooksPath", hooks.as_posix(), cwd=repository)


@pytest.mark.parametrize("how", ["interrupted", "hook-failed"])
def test_a_forward_checkout_that_moved_the_leg_and_then_failed_puts_it_back(
        how, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        tmp_path):
    """git moves the leg's HEAD BEFORE it runs `post-checkout`, so a checkout
    can fail after the move: a hook that exits non-zero (git-lfs's, with no
    `git-lfs` on PATH), or an interrupt that lands while the tool is still
    waiting on git. Whether the leg is put back is read off the leg, not off
    whether the checkout returned. The hook here refuses the NEW commit only,
    so the checkout that puts the leg back is not refused too."""
    before = prepared(project)
    if how == "interrupted":
        real_run = bump_leg_module.run

        def moved_then_interrupted(args, *rest, **kwargs):
            out = real_run(args, *rest, **kwargs)
            if args[:4] == ["git", "checkout", "-q", "--detach"] and \
                    args[-1] == advanced:
                raise KeyboardInterrupt()
            return out
        monkeypatch.setattr(bump_leg_module, "run", moved_then_interrupted)
        with pytest.raises(KeyboardInterrupt):
            run_main(bump_leg_module, project, scaffolded, advanced)
        assert_nothing_changed(project, before)
        return

    hook(project / "spec", tmp_path / "leg-hooks", "post-checkout",
         b'[ "$2" = "' + advanced.encode("ascii") + b'" ] || exit 0\n'
         b"echo 'post-checkout: git-lfs was not found on your path' >&2\n"
         b"exit 1\n")
    result = bump(project, scaffolded, advanced)

    assert_nothing_changed(project, before)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED advancing a leg" in result.stderr
    assert f"checkout -q --detach {advanced}" in result.stderr
    assert ROLLED_BACK in result.stderr, result.stderr


@pytest.mark.parametrize("how", [
    "cut-off-interrupted", "cut-off-command-failed", "moved-then-interrupted"])
def test_a_forward_checkout_that_left_files_in_the_leg_is_not_called_put_back(
        how, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        capsys):
    """git writes the new commit's files BEFORE it moves the leg's index and
    HEAD, and a terminal's Ctrl-C reaches git and this tool together, so a
    large checkout can be cut off with the leg's branch and HEAD unmoved and
    the files it wrote left in the leg. Read off the branch and the HEAD
    alone, that leg looked put back, the report said the tree was exactly as
    it was, and the re-run then failed on `untracked working tree files would
    be overwritten`. The `cut-off` cases are that checkout, interrupted or
    failed; `moved-then-interrupted` is one that did move the leg and left a
    file the checkout back cannot remove, so the comparison is made after a
    restore as well.

    The leg's `git status` is read before the checkout and compared in the
    rollback: the step is named, the operator is sent to `git -C <leg>
    status`, and the report says THE ROLLBACK WAS NOT COMPLETE. NOTHING IN
    THE LEG IS REMOVED: an untracked file of the operator's own is allowed
    there, and the rollback cannot tell it from one the checkout wrote."""
    prepared(project)
    leg = project / "spec"
    mine = leg / "OPERATOR-NOTES.md"
    mine.write_bytes(b"the operator's own untracked file\n")
    before = snapshot(project)
    real_run = bump_leg_module.run

    def cut_off(args, *rest, **kwargs):
        if args == ["git", "checkout", "-q", "--detach", advanced]:
            if how == "moved-then-interrupted":
                real_run(args, *rest, **kwargs)
            (leg / "PARTIAL.md").write_bytes(b"# written before the cut\n")
            if how == "cut-off-command-failed":
                raise bump_leg_module.CommandFailed(args, leg, 130, "")
            raise KeyboardInterrupt()
        return real_run(args, *rest, **kwargs)
    monkeypatch.setattr(bump_leg_module, "run", cut_off)

    if how != "cut-off-command-failed":
        with pytest.raises(KeyboardInterrupt):
            run_main(bump_leg_module, project, scaffolded, advanced)
        lead = "KeyboardInterrupt"
    else:
        assert run_main(bump_leg_module, project, scaffolded, advanced) == 2
        lead = "The command below failed"

    err = capsys.readouterr().err
    assert (f"{lead} while the bump was being applied. {NOT_COMPLETE}"
            in err), err
    assert ROLLED_BACK not in err, "nothing says the tree is exactly as it was"
    assert "the checkout of spec/ could not be put back: its `git status`" \
        in err, "the step is named"
    where = shlex.join(["git", "-C", str((project / "spec").resolve()),
                        "status"])
    assert f"`{where}` before anything else" in err, err
    after = snapshot(project)
    for key in ("head", "pin", "workflows", "gitlink", "leg_head",
                "leg_branch"):
        assert after[key] == before[key], f"{key} is not as it was found"
    assert git("diff", "--cached", "--quiet", cwd=project,
               check=False).returncode == 0, "the index was put back"
    assert mine.read_bytes() == b"the operator's own untracked file\n"
    assert (leg / "PARTIAL.md").is_file(), (
        "the rollback removes nothing from the leg: only the operator can "
        "tell a file of theirs from one the checkout wrote")


def test_an_untracked_file_the_operator_keeps_in_the_leg_is_left_alone_and_not_counted(
        project, scaffolded, advanced, bump_leg_module, monkeypatch, capsys):
    """The other side of the comparison above: an untracked file that was in
    the leg before the bump is in its `git status` before and after, so a
    rollback that put everything back still says so, and the file is not
    touched."""
    prepared(project)
    mine = project / "spec" / "OPERATOR-NOTES.md"
    mine.write_bytes(b"the operator's own untracked file\n")
    before = snapshot(project)
    monkeypatch.setattr(bump_leg_module, "run_validator",
                        lambda root, script: (1, "pin-digest-mismatch\n"))

    code = run_main(bump_leg_module, project, scaffolded, advanced)

    err = capsys.readouterr().err
    assert code == 2
    assert "REFUSED bump-leg-validators-red" in err
    assert ROLLED_BACK in err, err
    assert NOT_COMPLETE not in err
    assert_nothing_changed(project, before)
    assert mine.read_bytes() == b"the operator's own untracked file\n"


def test_a_leg_detached_at_the_commit_it_stood_on_is_put_back_on_its_branch(
        project, scaffolded, bump_leg_module, monkeypatch, capsys):
    """`--to` the commit already pinned, with a workflow reference left
    behind by a bump made by hand: not `nothing to do`, and the forward
    checkout detaches the leg AT THE COMMIT IT STOOD ON. Its HEAD is where it
    was and its branch is not, so a rollback that compared the HEAD alone
    would leave the leg detached, which `bootstrap.py` never leaves it."""
    prepared(project)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    legs = project / ".github" / "workflows" / "legs.yml"
    spec_ref = f"{PROJECT}-spec/.github/workflows/x.yml@"
    text = legs.read_text(encoding="utf-8")
    assert text.count(spec_ref + pinned) == 1
    legs.write_text(text.replace(spec_ref + pinned, spec_ref + "0" * 40),
                    encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "A workflow reference the last bump missed", "--",
        ".github/workflows/legs.yml", cwd=project)
    before = snapshot(project)
    assert before["leg_branch"] == "refs/heads/main"
    monkeypatch.setattr(bump_leg_module, "run_validator",
                        lambda root, script: (1, "pin-digest-mismatch\n"))

    code = run_main(bump_leg_module, project, scaffolded, pinned)

    err = capsys.readouterr().err
    assert code == 2
    assert "REFUSED bump-leg-validators-red" in err
    assert ROLLED_BACK in err, err
    assert_nothing_changed(project, before)


# --- the commit, inside the rollback's reach --------------------------------

@pytest.mark.parametrize("refusal", ["signing", "commit-msg"])
def test_a_commit_git_refuses_puts_every_byte_back(
        refusal, project, scaffolded, advanced, tmp_path):
    """The validators were green, so everything was written, staged and
    checked; then git refused the commit itself. A signing key that cannot
    sign and a `commit-msg` hook are both common on a developer's machine,
    and the operator's next act is to fix that and run the same command
    again, which a root left with the bump staged refuses as dirty. The
    signer is a program that does not exist, which needs no hook and runs
    the same on every platform."""
    before = prepared(project)
    if refusal == "signing":
        git("config", "commit.gpgsign", "true", cwd=project)
        git("config", "gpg.program", (tmp_path / "no-signer").as_posix(),
            cwd=project)
    else:
        hook(project, tmp_path / "root-hooks", "commit-msg",
             b"echo 'commit-msg: not this message' >&2\nexit 1\n")

    result = bump(project, scaffolded, advanced)

    assert_nothing_changed(project, before)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED advancing a leg" in result.stderr
    assert "git commit" in result.stderr, "the refusal names the commit"
    assert ROLLED_BACK in result.stderr, result.stderr
    assert NOT_COMPLETE not in result.stderr


def assert_the_commit_landed_and_nothing_was_rolled_back(
        project: Path, before: dict, advanced: str) -> str:
    head = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    assert head != before["head"], "the commit landed"
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == \
        advanced
    assert git("status", "--porcelain", cwd=project).stdout == "", (
        "the tree agrees with the commit: nothing was rolled back under it")
    assert git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip() == \
        advanced
    return head


@pytest.mark.parametrize("after", ["interrupt", "refusal", "oserror"])
def test_a_failure_after_the_commit_landed_rolls_nothing_back(
        after, project, scaffolded, advanced, bump_leg_module, monkeypatch,
        capsys):
    """THE HEAD GUARD. Once the root's HEAD has moved, the bump IS a commit,
    and putting the files, the leg and the index back under it would leave a
    tree that contradicts the commit just made. An interrupt after `git
    commit` returned, the `git rev-parse HEAD` that reads it back failing, or
    an `OSError` once it landed rolls nothing back, and says the commit
    landed. The `OSError` is not made into `bump-leg-rewrite-failed`, whose
    remediation says nothing was committed."""
    before = prepared(project)
    real_commit = bump_leg_module.commit_once
    failure = {
        "interrupt": KeyboardInterrupt(),
        "refusal": bump_leg_module.Refusal("git-failed",
                                           "`git rev-parse HEAD` exited 128"),
        "oserror": OSError(errno.EIO, "the disk went away after the commit"),
    }[after]

    def lands_then_fails(*args, **kwargs):
        real_commit(*args, **kwargs)
        raise failure
    monkeypatch.setattr(bump_leg_module, "commit_once", lands_then_fails)

    if after == "refusal":
        assert run_main(bump_leg_module, project, scaffolded, advanced) == 2
    else:
        with pytest.raises(type(failure)) as raised:
            run_main(bump_leg_module, project, scaffolded, advanced)
        assert raised.value is failure

    head = assert_the_commit_landed_and_nothing_was_rolled_back(
        project, before, advanced)
    err = capsys.readouterr().err
    assert f"committed as {head[:12]}" in err, err
    assert ROLLED_BACK not in err
    if after == "refusal":
        assert "REFUSED git-failed" in err
    if after == "oserror":
        assert "OSError while the bump was being applied" in err, err
        assert "bump-leg-rewrite-failed" not in err
        assert "Nothing was committed" not in err


def test_a_head_that_cannot_be_read_after_the_commit_rolls_nothing_back(
        project, scaffolded, advanced, bump_leg_module, monkeypatch, capsys):
    """THE HEAD GUARD'S THIRD ANSWER. Once the commit has been asked for,
    every `git rev-parse HEAD` in the root fails: the one `commit_once`
    reads the new commit back with, and the guard's own. Whether the commit
    landed is then unknown, and a rollback under a commit that did land is
    the worse mistake, so nothing is rolled back and the report says it
    could not be read."""
    before = prepared(project)
    asked = []
    real_check = bump_leg_module.check_program
    real_git_out = bump_leg_module.git_out

    def notes_the_commit(args):
        if args[:2] == ["git", "commit"]:
            asked.append(args)
        return real_check(args)

    def head_unreadable_once_asked(args, cwd, binary=False):
        if asked and args == ["rev-parse", "HEAD"]:
            raise bump_leg_module.Refusal(
                "git-failed", "`git rev-parse HEAD` exited 128: bad HEAD")
        return real_git_out(args, cwd=cwd, binary=binary)
    monkeypatch.setattr(bump_leg_module, "check_program", notes_the_commit)
    monkeypatch.setattr(bump_leg_module, "git_out", head_unreadable_once_asked)

    code = run_main(bump_leg_module, project, scaffolded, advanced)

    assert asked, "the commit was asked for"
    assert code == 2
    assert_the_commit_landed_and_nothing_was_rolled_back(
        project, before, advanced)
    err = capsys.readouterr().err
    assert "REFUSED git-failed" in err
    assert "Whether the commit landed could not be read" in err, err
    assert ROLLED_BACK not in err
    assert NOT_COMPLETE not in err
