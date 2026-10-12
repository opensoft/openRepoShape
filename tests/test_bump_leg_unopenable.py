# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: a file or a directory it must READ and this user
cannot OPEN is refused by name, before anything moves (#383).

`tests/test_bump_leg_unreadable.py` (#289) covers a file whose BYTES are not
UTF-8. This is the other way a read fails: the operating system refuses it.
The tool reads `contracts/<role>-pin.yaml` and every `.yml` and `.yaml` file
under `.github/workflows/`, and lists that directory, with no handler, and
`main()` catches `Refusal` and `CommandFailed` only. A `PermissionError` (an
`OSError`) ended the run in a traceback, exit 1, naming Python's error and not
a refusal, under `--dry-run` as well, because every one of those reads comes
before its early return. Now each is the refusal of its own kind, exit 2, with
the ids #289 introduced, so one id says "this tool cannot read this file"
whichever the reason: `bump-leg-workflow-unreadable` for a workflow file or the
directory, `bump-leg-pin-unreadable` for the pin. Each names the path and the
operating system's reason, and the remedy is to make it readable by this user
and run the same command again, never the re-save a file that is not UTF-8
is given.

HOW THE TREE COMES TO BE ONE THE TOOL GETS THIS FAR WITH. With git's default
configuration `chmod 000` on a tracked file changes its ctime, git must re-read
it to compare, cannot, and reports ` M`: the run is then refused
`bump-leg-root-dirty`, which is another refusal and is not under test here.
The traceback is what the operator got when git read the tree as clean, so
each mode-000 test says `git update-index --assume-unchanged` of every tracked
file it makes unreadable, which needs no sleep and no second status, asserts
that `git status --porcelain` is empty WHILE the file is unreadable, and clears
the flag when the mode is restored (a flag left on is a `git add` that adds
nothing). The mode is restored in a `finally`, so the temporary directory can
be removed.

THE TESTS THAT NEED A MODE SKIP ON WINDOWS and when the suite runs as root,
who reads anything. The tests that make the operating system fail for another
reason (a file gone between the listing and the read, an I/O error) do it
with a stand-in for the call, so they run everywhere, root included.

A REFUSED `stat` IS ASKED OF THE OPERATING SYSTEM, NOT OF `Path.is_file()`.
Up to Python 3.13 `is_file` and `is_dir` raised a refused `stat`; from 3.14
they answer False to ANY `OSError`, and CI's 3.14 turned two mode tests here
red at e2c78ee (an unsearchable `contracts/` read as a missing pin, and the
files of a workflows directory listable but not searchable were skipped). The
last section stands in for 3.14's answer with a refused `stat`, in-process, so
a tool that leans on `is_file` raising fails on every Python, root included.

EVERY MODE-000 TEST COMPARES THE WHOLE TREE, as
`tests/test_bump_leg_rollback.py` does, from a snapshot taken BEFORE the mode
is changed (the snapshot reads the files): the root's HEAD, the pin's and
every workflow's bytes, the gitlink, the root's `git status`, an empty
`git diff --cached`, and the leg's HEAD and branch. A refused bump is then run
AGAIN with the mode restored, to show that the remedy the refusal gives is the
whole of it.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    bump, bump_leg_module, committed, ignore_locally, ignoring_case,
    reference_both_legs, respelled, validate,
)
from test_bump_leg_rollback import assert_nothing_changed, snapshot
from test_bump_leg_unreadable import (
    LATIN1_COMMENT, MODES, WORKFLOWS, commit_bytes, prepared,
)

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-unopenable-advance"

needs_a_mode = pytest.mark.skipif(
    sys.platform == "win32" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="a mode that refuses the owner is a POSIX mode, and root reads "
           "through every one (tests/test_family_add_refusals.py)")

#: A workflow that names no leg: no `@<sha>` of its own would ever move.
NAMES_NO_LEG = b"on: [pull_request]\njobs: {}\n"


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = (tmp_path_factory.mktemp("spec-advance-unopenable")
            / f"{PROJECT}-spec")
    proc = subprocess.run(
        ["git", "clone", "-q",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "UNOPENABLE-CONTRACT.md").write_text("# a contract gained\n")
    git("add", "--", "UNOPENABLE-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the unopenable-file tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


@contextlib.contextmanager
def made_unopenable(project: Path, *relatives: str, mode: int = 0):
    """Set `mode` on each of `relatives` (000 by default: no read, no search)
    while git still reads the tree as clean, and put everything back.

    Git first: `--assume-unchanged` on every file git tracks at or under each
    path, so `git status` neither re-reads a file it cannot nor reports it
    changed. The deepest path takes its mode first and the shallowest gives
    it back first, so a file inside a directory made mode 000 is never
    reached through that directory.
    """
    flagged: list[str] = []
    for relative in relatives:
        listing = git("ls-files", "-z", "--", relative, cwd=project).stdout
        for name in filter(None, listing.split("\0")):
            git("update-index", "--assume-unchanged", "--", name, cwd=project)
            flagged.append(name)
    paths = [project / relative for relative in relatives]
    modes = {path: stat.S_IMODE(path.stat().st_mode) for path in paths}
    try:
        for path in sorted(paths, key=lambda item: len(item.parts),
                           reverse=True):
            path.chmod(mode)
        yield
    finally:
        for path in sorted(modes, key=lambda item: len(item.parts)):
            path.chmod(modes[path])
        for name in flagged:
            git("update-index", "--no-assume-unchanged", "--", name,
                cwd=project)


def refused_while_unopenable(project: Path, scaffolded: dict, to: str,
                             code: str, *relatives: str, extra: tuple = (),
                             mode: int = 0) -> str:
    """Make `relatives` unopenable, bump, and assert EVERYTHING the issue's
    table asks of the row: git reads the tree as clean (so it is the read that
    fails and not `bump-leg-root-dirty`), exit 2, the refusal's id, "Permission
    denied", no traceback and no UTF-8 advice, the tree still clean while the
    mode is on, and, once it is back, the whole tree as it was found.
    Returns stderr for a test that asserts more."""
    before = snapshot(project)
    with made_unopenable(project, *relatives, mode=mode):
        assert git("status", "--porcelain", cwd=project).stdout == "", (
            "git must read the tree as clean, or the refusal under test is "
            "`bump-leg-root-dirty`")
        result = bump(project, scaffolded, to, *extra)
        assert git("status", "--porcelain", cwd=project).stdout == "", (
            "the tree is as clean after the run as before it")
    output = result.stderr + result.stdout
    assert result.returncode == 2, output
    assert f"REFUSED {code}" in result.stderr, output
    assert "Permission denied" in result.stderr, output
    assert "Traceback" not in output, output
    assert "PermissionError" not in output, output
    assert "re-save" not in result.stderr, (
        "the file's bytes are not the trouble")
    assert "UTF-8" not in result.stderr, output
    assert_nothing_changed(project, before)
    return result.stderr


def refused_again_fine(project: Path, scaffolded: dict, to: str, extra: tuple,
                       *moved: str) -> None:
    """THE REMEDY IS THE WHOLE OF IT: with the mode back, the same command
    runs, and a bump leaves a root the project's own validator passes, with
    every file in `moved` in the lockstep commit."""
    result = bump(project, scaffolded, to, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr
    if not extra:
        assert set(moved) <= committed(project)
        assert validate(project).returncode == 0
        assert git("status", "--porcelain", cwd=project).stdout == ""


# --- a workflow file ---------------------------------------------------------

@needs_a_mode
@MODES
def test_a_workflow_naming_the_leg_that_cannot_be_opened_is_refused(
        project, scaffolded, advanced, extra):
    """THE ISSUE'S ROW (a) AND (b): the file names the leg and is committed,
    so the tracked-files rule is met and only the read stands in the way. On
    the base it is `PermissionError` out of `plan_workflows`, exit 1, bump and
    `--dry-run` alike. The refusal names the file by its path in the
    repository and the system's reason, and says to make it readable and run
    the same command again; the tracked file's line is not marked untracked."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml", extra=extra)

    assert (".github/workflows/legs.yml: cannot be read: Permission denied"
            in stderr)
    assert "1 workflow file(s) cannot be opened" in stderr
    assert "chmod u+r" in stderr and "fix who owns it" in stderr
    assert "Then run the same command again" in stderr
    assert "(untracked or ignored)" not in stderr
    assert "Commit each file" not in stderr
    assert "commit it" not in stderr
    refused_again_fine(project, scaffolded, advanced, extra,
                       ".github/workflows/legs.yml")


@needs_a_mode
@MODES
@pytest.mark.parametrize("name", ["other.yml", "other.yaml"])
def test_a_workflow_naming_no_leg_that_cannot_be_opened_is_refused(
        project, scaffolded, advanced, extra, name):
    """THE REFUSAL COVERS THE FILE WHETHER OR NOT IT NAMES THE LEG, as #289's
    does: `plan_workflows` reads every file in the directory, and
    `validate-pins.py` does too. This file holds no `@<sha>`, so none of its
    own would move; it is read anyway. `.yaml` is read as well as `.yml`."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / name, NAMES_NO_LEG)

    refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        f".github/workflows/{name}", extra=extra)


@needs_a_mode
def test_every_workflow_that_cannot_be_opened_is_named_in_one_refusal(
        project, scaffolded, advanced):
    """Two unopenable files, one run: the operator fixes both rather than
    meeting them one refusal at a time."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "other.yml", NAMES_NO_LEG)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml", ".github/workflows/other.yml")

    assert "2 workflow file(s) cannot be opened" in stderr
    assert ".github/workflows/legs.yml: cannot be read" in stderr
    assert ".github/workflows/other.yml: cannot be read" in stderr


@needs_a_mode
@MODES
@pytest.mark.parametrize("how", ["untracked", "ignored"])
def test_an_unopenable_draft_is_marked_and_not_told_to_be_committed(
        project, scaffolded, advanced, extra, how):
    """#352's TRACKED/UNTRACKED MARKING, KEPT FOR THIS CAUSE. A draft nobody
    committed (or that the clone's own `info/exclude` ignores) names no leg
    and cannot be opened. It is refused all the same, because
    `validate-pins.py` reads every file on disk, but its line is marked, and
    nothing in the remediation tells its operator to commit it: that puts a
    draft workflow on the bump branch, which `bump-leg-workflow-untracked`
    exists to prevent, and `git add` refuses an ignored one. Making it
    readable, or moving it away, is enough, and with the mode back the bump
    goes through and leaves the draft out of the lockstep commit."""
    prepared(project)
    relative = ".github/workflows/draft.yml"
    draft = project / WORKFLOWS / "draft.yml"
    draft.write_bytes(NAMES_NO_LEG)
    if how == "ignored":
        ignore_locally(project, relative)
        assert git("check-ignore", "-q", relative, cwd=project,
                   check=False).returncode == 0, "the file is ignored"
    assert git("ls-files", "--", relative, cwd=project).stdout == "", (
        "git does not track it")

    before = snapshot(project)
    with made_unopenable(project, relative):
        result = bump(project, scaffolded, advanced, *extra)
    stderr = result.stderr
    assert result.returncode == 2, stderr + result.stdout
    assert "REFUSED bump-leg-workflow-unreadable" in stderr
    line = next(line for line in stderr.splitlines() if relative in line)
    assert line.rstrip().endswith("(untracked or ignored)"), line
    assert "Permission denied" in line
    assert "commit it" not in stderr and "Commit each file" not in stderr, (
        "an operator who commits the draft puts it on the bump branch")
    assert "is not in the repository" in stderr
    assert "Traceback" not in stderr
    assert_nothing_changed(project, before)

    result = bump(project, scaffolded, advanced, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert relative not in result.stdout, "the draft is nobody's business now"
    assert git("ls-files", "--", relative, cwd=project).stdout == ""
    if not extra:
        assert relative not in committed(project)
        assert validate(project).returncode == 0


@needs_a_mode
def test_a_non_utf8_file_and_an_unopenable_one_meet_in_one_refusal(
        project, scaffolded, advanced):
    """TWO CAUSES, ONE REFUSAL, EACH WITH ITS OWN ADVICE. A tracked Latin-1
    file and a tracked file made unreadable: both are named under their own
    header, the re-save advice and the commit advice are given for the first,
    and `chmod` for the second, which is told nothing about re-saving. The
    count line #352 wrote is unchanged for the first."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "latin1.yml", LATIN1_COMMENT)
    commit_bytes(project, WORKFLOWS / "other.yml", NAMES_NO_LEG)
    offset = (project / WORKFLOWS / "latin1.yml").read_bytes().index(b"\xe9")

    before = snapshot(project)
    with made_unopenable(project, ".github/workflows/other.yml"):
        result = bump(project, scaffolded, advanced)
    stderr = result.stderr
    assert result.returncode == 2, stderr + result.stdout
    assert "REFUSED bump-leg-workflow-unreadable" in stderr
    assert "Traceback" not in stderr
    assert "1 workflow file(s) are not UTF-8:" in stderr
    assert (f".github/workflows/latin1.yml: not UTF-8 at byte {offset} "
            "(invalid continuation byte)") in stderr
    assert "1 workflow file(s) cannot be opened:" in stderr
    assert (".github/workflows/other.yml: cannot be read: Permission denied"
            in stderr)
    assert stderr.index("are not UTF-8") < stderr.index("cannot be opened"), (
        "the same order every run: not UTF-8 first")
    assert "re-save" in stderr and "Commit each file git tracks" in stderr
    assert "chmod u+r" in stderr
    assert_nothing_changed(project, before)


@needs_a_mode
def test_an_unopenable_workflow_is_refused_before_nothing_to_do(
        project, scaffolded):
    """EXIT 1 MUST NOT HIDE IT. `--to` the commit every fact already names is
    `nothing to do` (exit 1), but the reads come before that decision: a tree
    the next real bump cannot read is not one this run may call settled."""
    prepared(project)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()

    refused_while_unopenable(
        project, scaffolded, pinned, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml")


# --- the directory -----------------------------------------------------------

@needs_a_mode
@MODES
def test_a_workflows_directory_that_cannot_be_listed_is_refused_naming_it(
        project, scaffolded, advanced, extra):
    """THE ISSUE'S ROW (e). `.github/workflows/` itself mode 000: git reads the
    tree as clean (its `Permission denied` goes to stderr and `git status`
    exits 0), the walk raised `PermissionError` out of `iterdir`, and the run
    ended in a traceback. The refusal names the DIRECTORY, with a trailing
    `/`, and says `chmod u+rx`."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows", extra=extra)

    assert (".github/workflows/: cannot be listed: Permission denied"
            in stderr)
    assert "chmod u+rx" in stderr
    assert "cannot be opened" not in stderr, "no file was reached"
    refused_again_fine(project, scaffolded, advanced, extra,
                       ".github/workflows/legs.yml")


@needs_a_mode
def test_a_workflows_directory_listable_but_not_searchable_is_refused(
        project, scaffolded, advanced):
    """A DIRECTORY WITH `r` AND NO `x`: its names list, and every `stat` of a
    name in it is refused. The listing succeeds, so it is the `stat` that
    raises, and it is a file-level refusal naming each: the same family, a
    different frame. Asked through `Path.is_file()`, Python 3.14 answers "no
    file" instead, every file is skipped, the bump goes ahead and
    `validate-pins.py` rolls it back as `bump-leg-validators-red` (CI at
    e2c78ee)."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows", mode=stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

    assert ".github/workflows/legs.yml: cannot be read: Permission denied" \
        in stderr
    assert "chmod u+rx" in stderr


@needs_a_mode
@MODES
def test_a_github_directory_that_cannot_be_searched_names_the_workflows(
        project, scaffolded, advanced, extra):
    """`.github/` mode 000, the directory ABOVE the workflows: the `stat` of
    `.github/workflows` is refused before any listing, and it is the
    directory refusal, whose `chmod u+rx` advice names every directory above
    it inside the root. Asked through `Path.is_dir()`, Python 3.14 answers
    "no directory", and the bump went on as if the project had no workflow
    to move."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github", extra=extra)

    assert (".github/workflows/: cannot be listed: Permission denied"
            in stderr)
    assert "chmod u+rx" in stderr and "every directory above it" in stderr
    refused_again_fine(project, scaffolded, advanced, extra,
                       ".github/workflows/legs.yml")


# --- the pin -----------------------------------------------------------------

@needs_a_mode
@MODES
def test_a_leg_pin_that_cannot_be_opened_is_refused_by_name(
        project, scaffolded, advanced, extra):
    """THE ISSUE'S ROW (c). The pin is read OUTSIDE `load_yaml`, so the
    refusal #289 gave a pin that is not UTF-8 has to be given one this user
    cannot open, under the same id. It names `contracts/spec-pin.yaml`."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-pin-unreadable",
        "contracts/spec-pin.yaml", extra=extra)

    assert ("contracts/spec-pin.yaml: cannot be read: Permission denied"
            in stderr)
    assert "chmod u+r" in stderr
    refused_again_fine(project, scaffolded, advanced, extra,
                       "contracts/spec-pin.yaml")


@needs_a_mode
def test_a_contracts_directory_that_cannot_be_searched_names_the_pin(
        project, scaffolded, advanced):
    """`contracts/` mode 000: the `stat` of the pin is refused before the read
    is reached. That is not an absent pin (`bump-leg-pin-missing`, whose
    remedy is to restore it from history): the file is there and cannot be
    reached, so it is the pin refusal, with the permission remedy. Python
    3.14's `Path.is_file()` answers "no file" here, which is how CI at e2c78ee
    got `bump-leg-pin-missing`."""
    prepared(project)

    stderr = refused_while_unopenable(
        project, scaffolded, advanced, "bump-leg-pin-unreadable", "contracts")

    assert ("contracts/spec-pin.yaml: cannot be read: Permission denied"
            in stderr)
    assert "bump-leg-pin-missing" not in stderr


# --- an OSError that is not a permission (on every platform, root too) -------

def refusal_of(module, call, *args):
    with pytest.raises(module.Refusal) as refused:
        call(*args)
    return refused.value


@pytest.mark.parametrize("failure", [
    FileNotFoundError(errno.ENOENT, "No such file or directory"),
    IsADirectoryError(errno.EISDIR, "Is a directory"),
    OSError(errno.EIO, "Input/output error"),
], ids=["vanished", "now-a-directory", "io-error"])
def test_a_workflow_that_fails_for_another_reason_is_refused_sans_chmod(
        bump_leg_module, project, advanced, monkeypatch, failure):
    """THE `OSError` FAMILY, NOT `PermissionError` ALONE (the issue's second
    point): a file that vanishes between the listing and the read, one that
    stopped being a file, an I/O error. The same refusal, the system's own
    reason on the line, and a remedy that does not tell the operator to
    `chmod` what is not a permission. Called in-process with the read
    replaced, so it runs on every platform and as root."""
    reference_both_legs(project)
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "legs.yml":
            raise type(failure)(failure.errno, failure.strerror, str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    refusal = refusal_of(bump_leg_module, bump_leg_module.plan_workflows,
                         project, f"{ORG}/{PROJECT}-spec", advanced)

    assert refusal.code == "bump-leg-workflow-unreadable"
    assert (f".github/workflows/legs.yml: cannot be read: {failure.strerror}"
            in refusal.detail)
    assert "chmod" not in refusal.remediation
    assert "Where the operating system gave another reason" in (
        refusal.remediation)
    assert "(untracked or ignored)" not in refusal.detail, "it is tracked"


def test_a_pin_that_fails_for_another_reason_is_refused_by_name(
        bump_leg_module, project, monkeypatch):
    """The pin's own `OSError` that is no permission: the same id, the
    system's reason, no `chmod`."""
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "spec-pin.yaml":
            raise OSError(errno.EIO, "Input/output error", str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    refusal = refusal_of(bump_leg_module, bump_leg_module._leg_pin_text,
                         project, project / "contracts" / "spec-pin.yaml")

    assert refusal.code == "bump-leg-pin-unreadable"
    assert refusal.detail == ("contracts/spec-pin.yaml: cannot be read: "
                              "Input/output error")
    assert "chmod" not in refusal.remediation
    assert "UTF-8" not in refusal.remediation


def test_a_listing_that_fails_for_another_reason_names_the_directory(
        bump_leg_module, project, advanced, monkeypatch):
    """`iterdir` failing with an I/O error: the directory refusal, with the
    system's reason and no `chmod`. Both listings go through one helper, so
    the first one `plan_workflows` makes is the one that is refused."""
    reference_both_legs(project)
    real = Path.iterdir

    def iterdir(self):
        if self.name == "workflows":
            raise OSError(errno.EIO, "Input/output error", str(self))
        return real(self)

    monkeypatch.setattr(Path, "iterdir", iterdir)
    refusal = refusal_of(bump_leg_module, bump_leg_module.plan_workflows,
                         project, f"{ORG}/{PROJECT}-spec", advanced)

    assert refusal.code == "bump-leg-workflow-unreadable"
    assert refusal.detail == (".github/workflows/: cannot be listed: "
                              "Input/output error")
    assert "chmod" not in refusal.remediation


def test_a_respelled_unopenable_workflow_is_refused_as_the_disk_spells_it(
        bump_leg_module, project, advanced, monkeypatch):
    """THE #344 COMPOSITION, through #344's own seam, so it runs on every
    disk. A tracked `legs.yml` renamed outside git to `Legs.yml` that cannot
    be opened. Every file is read before the loop asks `_tracked_spelling`
    anything, so it is refused under the spelling the DISK gives it, and its
    line is not marked untracked: it is the tracked file, under git's
    spelling, which is what the question is asked."""
    reference_both_legs(project)
    workflows = project / WORKFLOWS
    respelled(workflows, "legs.yml", "Legs.yml")
    monkeypatch.setattr(bump_leg_module, "_same_file", ignoring_case,
                        raising=False)
    real = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "Legs.yml":
            raise PermissionError(errno.EACCES, "Permission denied",
                                  str(self))
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    refusal = refusal_of(bump_leg_module, bump_leg_module.plan_workflows,
                         project, f"{ORG}/{PROJECT}-spec", advanced)

    assert refusal.code == "bump-leg-workflow-unreadable"
    assert (".github/workflows/Legs.yml: cannot be read: Permission denied"
            in refusal.detail)
    assert ".github/workflows/legs.yml" not in refusal.detail
    assert "(untracked or ignored)" not in refusal.detail
    assert "chmod u+r" in refusal.remediation


# --- a refused `stat`, as Python 3.14 answers it (everywhere, root too) -----

def refused_stat(monkeypatch, *names: str) -> None:
    """`Path.stat` refused (`Permission denied`) for each of `names`, as it is
    for a name inside a directory this user may not search, and
    `Path.is_file`, `is_dir` and `exists` answering as Python 3.14's do:
    False to ANY `OSError` (they call `os.path.isfile` and the like), where
    3.9 to 3.13 raised a refused `stat`.

    CI's 3.14 is where the mode tests above first met that answer (e2c78ee):
    `is_file` said "no file", and the tool took an unsearchable `contracts/`
    for a missing pin and skipped every file of a workflows directory it could
    list but not search. In-process, so this runs on every Python and every
    platform and as root, and on a Python before 3.14 it still fails a tool
    that asks `is_file` or `is_dir` and counts on the raise."""
    real = Path.stat

    def refusing(self, *args, **kwargs):
        if self.name in names:
            raise PermissionError(errno.EACCES, "Permission denied", str(self))
        return real(self, *args, **kwargs)

    def as_python_314(kind):
        def answer(self, *args, **kwargs):
            try:
                return kind(self.stat().st_mode)
            except (OSError, ValueError):
                return False
        return answer

    monkeypatch.setattr(Path, "stat", refusing)
    monkeypatch.setattr(Path, "is_file", as_python_314(stat.S_ISREG))
    monkeypatch.setattr(Path, "is_dir", as_python_314(stat.S_ISDIR))
    monkeypatch.setattr(Path, "exists", as_python_314(lambda mode: True))


def test_a_workflow_whose_stat_is_refused_is_named_not_skipped(
        bump_leg_module, project, advanced, monkeypatch):
    """A WORKFLOWS DIRECTORY LISTABLE BUT NOT SEARCHABLE, on every Python. The
    listing names `legs.yml` and its `stat` is refused: the file refusal names
    it, with the permission remedy. A file skipped as "not a file" is a bump
    that goes ahead without it and is rolled back by `validate-pins.py`."""
    reference_both_legs(project)
    refused_stat(monkeypatch, "legs.yml")

    refusal = refusal_of(bump_leg_module, bump_leg_module.plan_workflows,
                         project, f"{ORG}/{PROJECT}-spec", advanced)

    assert refusal.code == "bump-leg-workflow-unreadable"
    assert (".github/workflows/legs.yml: cannot be read: Permission denied"
            in refusal.detail)
    assert "1 workflow file(s) cannot be opened" in refusal.detail
    assert "chmod u+r" in refusal.remediation


def test_a_workflows_directory_whose_stat_is_refused_is_named(
        bump_leg_module, project, advanced, monkeypatch):
    """A `.github/` this user may not search, on every Python: the `stat` of
    `.github/workflows` is refused, and it is the directory refusal. A
    directory taken for "not there" is a bump that moves no workflow."""
    reference_both_legs(project)
    refused_stat(monkeypatch, "workflows")

    refusal = refusal_of(bump_leg_module, bump_leg_module.plan_workflows,
                         project, f"{ORG}/{PROJECT}-spec", advanced)

    assert refusal.code == "bump-leg-workflow-unreadable"
    assert refusal.detail == (".github/workflows/: cannot be listed: "
                              "Permission denied")
    assert "chmod u+rx" in refusal.remediation


def test_a_pin_whose_stat_is_refused_is_not_called_missing(
        bump_leg_module, project, monkeypatch):
    """A `contracts/` this user may not search, on every Python: the pin is
    there and cannot be reached, which is `bump-leg-pin-unreadable` with the
    permission remedy, never `bump-leg-pin-missing`, whose remedy restores a
    file nobody lost."""
    refused_stat(monkeypatch, "spec-pin.yaml")

    refusal = refusal_of(bump_leg_module, bump_leg_module._leg_pin_path,
                         project, "contracts/spec-pin.yaml")

    assert refusal.code == "bump-leg-pin-unreadable"
    assert refusal.detail == ("contracts/spec-pin.yaml: cannot be read: "
                              "Permission denied")
    assert "chmod u+r" in refusal.remediation


@pytest.mark.parametrize("missing", [
    "contracts/nowhere-pin.yaml",
    "contracts/spec-pin.yaml/below",
], ids=["no-such-file", "a-file-on-the-path"])
def test_a_pin_that_is_not_there_is_still_missing(
        bump_leg_module, project, missing):
    """THE OTHER HALF OF THE ANSWER: nothing at the name (`ENOENT`), or a part
    of the path that is a file (`ENOTDIR`), is the absent pin it always was,
    and not a file this user cannot open."""
    refusal = refusal_of(bump_leg_module, bump_leg_module._leg_pin_path,
                         project, missing)

    assert refusal.code == "bump-leg-pin-missing"
    assert refusal.detail.startswith(f"{missing} does not exist")
