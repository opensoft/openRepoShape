# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py`: a committed file it must READ and cannot is refused
by name, before anything moves (#289).

The tool reads `contracts/<role>-pin.yaml` and every `.yml` and `.yaml` file
under `.github/workflows/` as UTF-8, to rewrite them as text. A Latin-1
comment (`# caf\\xe9`) or a UTF-16 file with a byte-order mark is not UTF-8,
and `read_text(encoding="utf-8")` raised `UnicodeDecodeError` on it, which
`main()` does not catch: a traceback, exit 1, with no word about which file,
and `--dry-run` died the same way because both reads run before its early
return. Now each is a refusal of its own, exit 2: `bump-leg-workflow-
unreadable` for a workflow file and `bump-leg-pin-unreadable` for the pin.

EVERY TEST COMPARES THE WHOLE TREE, as `tests/test_bump_leg_rollback.py` does,
because "nothing moved" is the promise: the root's HEAD, the pin's and every
workflow's bytes, the gitlink the index records, the root's `git status`, an
empty `git diff --cached`, and the leg's HEAD and branch.

THE BYTES ARE WRITTEN WITH `write_bytes`, never `write_text`, so what a test
commits is the same bytes on every platform. A control keeps the refusal from
being wider than the failure: a UTF-8 file with a non-ASCII comment, with a
byte-order mark, and a non-UTF-8 file the validator never reads, all still
bump.

THE REFUSAL SAYS WHICH ADVICE APPLIES. A file git does not track (untracked,
or ignored) is refused all the same, because `validate-pins.py` reads every
file on disk, but re-saving it is enough: committing it would put a draft on
the bump branch, which `bump-leg-workflow-untracked` exists to prevent, and
`git add` refuses an ignored one. Each such line is marked, and the
remediation tells a tracked file's operator to commit it and an untracked
one's not to.

THE #344 COMPOSITION is pinned through #344's own seam (`_same_file`), so it
runs on every disk: a tracked workflow renamed by case alone outside git that
is not UTF-8 is refused under the DISK's spelling, because every file is read
before any spelling question is asked.
"""

from __future__ import annotations

import codecs
import subprocess
from pathlib import Path

import pytest

from conftest import ORG, PROJECT, git
# A fixture is used by being named in this module's namespace, which is what
# the import of `bump_leg_module` is for.
from test_bump_leg import (  # noqa: F401
    branched, bump, bump_leg_module, committed, ignore_locally, ignoring_case,
    reference_both_legs, respelled, validate,
)
from test_bump_leg_rollback import assert_nothing_changed, snapshot

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-unreadable-advance"

WORKFLOWS = Path(".github") / "workflows"

#: A Latin-1 comment: `é` is the single byte 0xE9, a UTF-8 lead byte with no
#: continuation after it.
LATIN1_COMMENT = b"# caf\xe9\n"

#: A whole workflow saved as UTF-16 with a byte-order mark (what a Windows
#: editor's "Unicode" save writes). `ff fe` is not a UTF-8 start byte, so the
#: first byte is already the bad one.
UTF16_WORKFLOW = (codecs.BOM_UTF16_LE
                  + "on: [pull_request]\n".encode("utf-16-le"))


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = (tmp_path_factory.mktemp("spec-advance-unreadable")
            / f"{PROJECT}-spec")
    proc = subprocess.run(
        ["git", "clone", "-q",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "UNREADABLE-CONTRACT.md").write_text("# a contract gained\n")
    git("add", "--", "UNREADABLE-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the unreadable-file tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def commit_bytes(project: Path, relative: Path, data: bytes, *,
                 append: bool = False) -> None:
    """Write `data` at `relative` (or append it) and COMMIT it, so the root is
    clean when the bump starts and the file is one git tracks."""
    target = project / relative
    if append:
        data = target.read_bytes() + data
    target.write_bytes(data)
    git("add", "--", relative.as_posix(), cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        f"Commit {relative.as_posix()}", cwd=project)


def prepared(project: Path) -> None:
    """A bump-ready root: a workflow naming both legs, committed; the spec leg
    ON its branch, as `bootstrap.py` leaves it; a bump branch."""
    reference_both_legs(project)
    git("checkout", "-q", "-B", "main", cwd=project / "spec")
    branched(project)


def refused_and_untouched(project: Path, scaffolded: dict, to: str, code: str,
                          *names: str, extra: tuple = ()) -> str:
    """Bump, and assert EVERYTHING the issue's table asks of the row: exit 2,
    the refusal's id, every file named, no traceback, and the whole tree as it
    was. Returns stderr for a test that asserts more."""
    before = snapshot(project)
    result = bump(project, scaffolded, to, *extra)
    output = result.stderr + result.stdout
    assert result.returncode == 2, output
    assert f"REFUSED {code}" in result.stderr, output
    for name in names:
        assert name in result.stderr, f"{name} is not named:\n{output}"
    assert "Traceback" not in output, output
    assert "UnicodeDecodeError" not in output, output
    assert_nothing_changed(project, before)
    return result.stderr


MODES = pytest.mark.parametrize("extra", [(), ("--dry-run",)],
                                ids=["bump", "dry-run"])


# --- a workflow file ---------------------------------------------------------

@MODES
def test_a_latin1_byte_in_a_workflow_naming_the_leg_is_refused_by_name(
        project, scaffolded, advanced, extra):
    """THE ISSUE'S FIRST ROW: the file names the leg, holds one Latin-1 byte
    and is committed, so the tracked-files rule is met and only the read
    stands in the way. The refusal names the file by its path in the
    repository, the byte and the reason, in the words `load_yaml` uses."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "legs.yml", LATIN1_COMMENT, append=True)
    offset = (project / WORKFLOWS / "legs.yml").read_bytes().index(b"\xe9")

    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml",
        f"not UTF-8 at byte {offset} (invalid continuation byte)",
        extra=extra)
    assert "re-save" in stderr and "UTF-8" in stderr, (
        "the remediation says what to do about it")
    assert "Commit each file git tracks" in stderr, (
        "a file git tracks is committed after the re-save")
    assert "(untracked or ignored)" not in stderr
    assert "needs no commit" not in stderr


@MODES
@pytest.mark.parametrize("name", ["other.yml", "other.yaml"])
def test_a_utf16_workflow_naming_no_leg_is_refused_by_name(
        project, scaffolded, advanced, extra, name):
    """THE REFUSAL COVERS THE FILE WHETHER OR NOT IT NAMES THE LEG. The file
    holds no `@<sha>`, so no reference of its own would move; it is read
    anyway, because `validate-pins.py` reads every workflow on disk and could
    not read it either. `.yaml` is read as well as `.yml`, as the validator
    does. Skipping it would be a silent pass over a file the gate dies on."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / name, UTF16_WORKFLOW)

    refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        f".github/workflows/{name}",
        "not UTF-8 at byte 0 (invalid start byte)", extra=extra)


def test_every_unreadable_workflow_is_named_in_one_refusal(project, scaffolded,
                                                           advanced):
    """Two bad files, one run: the operator re-saves both rather than meeting
    them one refusal at a time."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "legs.yml", LATIN1_COMMENT, append=True)
    commit_bytes(project, WORKFLOWS / "other.yml", UTF16_WORKFLOW)

    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml", ".github/workflows/other.yml")
    assert "2 workflow file(s) are not UTF-8" in stderr


DRAFT_UNREADABLE = b"on: [push]\n" + LATIN1_COMMENT
DRAFT_RESAVED = "on: [push]\n# café\n".encode("utf-8")


@MODES
@pytest.mark.parametrize("how", ["untracked", "ignored"])
def test_an_unreadable_workflow_git_does_not_track_is_not_told_to_be_committed(
        project, scaffolded, advanced, extra, how):
    """A DRAFT THE OPERATOR NEVER COMMITTED IS REFUSED ALL THE SAME, and told
    the truth about it. The file names no leg, holds a Latin-1 byte and is
    untracked (or ignored through the clone's own `info/exclude`).
    `validate-pins.py` reads every file on disk, so the bump cannot go past
    it; but the remediation said "commit it", which for an untracked file
    puts a draft workflow on the bump branch, the thing the untracked
    refusal exists to prevent, and for an ignored one `git add` refuses. The
    line is marked, the remediation says no commit is needed, and once the
    file is re-saved as UTF-8 and STILL not committed the bump goes through
    without it: the draft is not in the lockstep commit.

    It also kills the mutant that skips an unreadable file git does not
    track: the draft would then reach the validator, which dies on it in a
    traceback inside `bump-leg-validators-red`.
    """
    prepared(project)
    relative = ".github/workflows/draft.yml"
    draft = project / WORKFLOWS / "draft.yml"
    draft.write_bytes(DRAFT_UNREADABLE)
    if how == "ignored":
        ignore_locally(project, relative)
        assert git("check-ignore", "-q", relative, cwd=project,
                   check=False).returncode == 0, "the file is ignored"
    assert git("ls-files", "--", relative, cwd=project).stdout == "", (
        "git does not track it")
    offset = DRAFT_UNREADABLE.index(b"\xe9")

    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        f"{relative}: not UTF-8 at byte {offset} (invalid continuation byte)",
        extra=extra)
    assert "commit it" not in stderr, (
        "an operator who commits the draft puts it on the bump branch")
    assert "Commit each file git tracks" not in stderr
    assert "needs no commit" in stderr, (
        "the remediation says what is true of a file git does not track")
    line = next(line for line in stderr.splitlines() if relative in line)
    assert line.rstrip().endswith("(untracked or ignored)"), line

    draft.write_bytes(DRAFT_RESAVED)
    result = bump(project, scaffolded, advanced, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert relative not in result.stdout, "the draft is nobody's business now"
    assert draft.read_bytes() == DRAFT_RESAVED, "left exactly as it was saved"
    assert git("ls-files", "--", relative, cwd=project).stdout == ""
    if not extra:
        assert relative not in committed(project), (
            "re-saving was enough: the draft is not in the lockstep commit")
        assert validate(project).returncode == 0


def test_each_unreadable_workflow_line_says_whether_git_tracks_it(
        project, scaffolded, advanced):
    """A tracked file and an untracked one in ONE refusal: the tracked one's
    line is unmarked, the untracked one's is marked, and the remediation
    gives each its own advice, so neither operator is told the other's."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "legs.yml", LATIN1_COMMENT, append=True)
    (project / WORKFLOWS / "draft.yml").write_bytes(DRAFT_UNREADABLE)

    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-workflow-unreadable",
        ".github/workflows/legs.yml", ".github/workflows/draft.yml")
    assert "2 workflow file(s) are not UTF-8" in stderr
    tracked_line = next(line for line in stderr.splitlines()
                        if ".github/workflows/legs.yml" in line)
    draft_line = next(line for line in stderr.splitlines()
                      if ".github/workflows/draft.yml" in line)
    assert "(untracked or ignored)" not in tracked_line
    assert draft_line.rstrip().endswith("(untracked or ignored)")
    assert "Commit each file git tracks" in stderr
    assert "needs no commit" in stderr


def test_an_unreadable_workflow_is_refused_before_nothing_to_do(
        project, scaffolded):
    """EXIT 1 MUST NOT HIDE IT. `--to` the commit every fact already names is
    `nothing to do` (exit 1), but the reads come before that decision: a tree
    the next real bump cannot read is not one this run may call settled."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "legs.yml", LATIN1_COMMENT, append=True)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()

    refused_and_untouched(project, scaffolded, pinned,
                          "bump-leg-workflow-unreadable",
                          ".github/workflows/legs.yml")


def test_a_respelled_unreadable_workflow_is_refused_as_the_disk_spells_it(
        bump_leg_module, project, advanced, monkeypatch):
    """THE #344 COMPOSITION, through #344's own seam, so it runs on every
    disk. A tracked `legs.yml` holding a Latin-1 byte, renamed outside git to
    `Legs.yml`. `_workflow_texts` reads every file before the loop asks
    `_tracked_spelling` anything, so the file is refused under the spelling
    the DISK gives it, `.github/workflows/Legs.yml`, and never reaches the
    question; a UTF-8 file respelled the same way is planned under git's
    (`test_a_respelled_tracked_workflow_is_planned_under_gits_spelling`).
    The line is not marked untracked: the file is tracked, under git's
    spelling, which is what `_tracked_spelling` is asked. On main this is a
    `UnicodeDecodeError`. The file is not touched."""
    reference_both_legs(project)
    commit_bytes(project, WORKFLOWS / "legs.yml", LATIN1_COMMENT, append=True)
    workflows = project / WORKFLOWS
    respelled(workflows, "legs.yml", "Legs.yml")
    monkeypatch.setattr(bump_leg_module, "_same_file", ignoring_case,
                        raising=False)
    before = (workflows / "Legs.yml").read_bytes()
    offset = before.index(b"\xe9")

    with pytest.raises(bump_leg_module.Refusal) as refused:
        bump_leg_module.plan_workflows(project, f"{ORG}/{PROJECT}-spec",
                                       advanced)

    assert refused.value.code == "bump-leg-workflow-unreadable"
    assert (f".github/workflows/Legs.yml: not UTF-8 at byte {offset} "
            "(invalid continuation byte)") in refused.value.detail, (
        "named under the disk's spelling, with the file's own offset")
    assert ".github/workflows/legs.yml" not in refused.value.detail, (
        "not under git's")
    assert "(untracked or ignored)" not in refused.value.detail, (
        "it is the tracked file, whichever way the disk spells it")
    assert (workflows / "Legs.yml").read_bytes() == before, (
        "nothing was written")


# --- the pin -----------------------------------------------------------------

@MODES
def test_a_latin1_byte_in_the_legs_pin_is_refused_by_name(
        project, scaffolded, advanced, extra):
    """The pin is read OUTSIDE `load_yaml` (the bump rewrites its lines, not a
    parsed mapping), so it needs the refusal `load_yaml` gives every other
    reader. It names `contracts/spec-pin.yaml`."""
    prepared(project)
    commit_bytes(project, Path("contracts") / "spec-pin.yaml", LATIN1_COMMENT,
                 append=True)
    offset = (project / "contracts" / "spec-pin.yaml").read_bytes().index(
        b"\xe9")

    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-pin-unreadable",
        "contracts/spec-pin.yaml",
        f"not UTF-8 at byte {offset} (invalid continuation byte)", extra=extra)
    assert "re-save" in stderr and "UTF-8" in stderr


def test_the_other_legs_pin_stays_the_validators_refusal(project, scaffolded,
                                                         advanced):
    """THE SHAPE THE ISSUE HELD UP AS RIGHT, kept: the CODE leg's pin is not
    read by this tool at all, so a Latin-1 byte in it reaches the project's
    own validator after the rewrite, which refuses `yaml-unreadable` and the
    bump rolls every byte back. This change must not turn that into a second,
    earlier refusal for a file the tool never reads."""
    prepared(project)
    commit_bytes(project, Path("contracts") / "code-pin.yaml", LATIN1_COMMENT,
                 append=True)

    # The file is named by the VALIDATOR, whose `load_yaml` prints the Path it
    # was given, absolute and in the platform's own spelling:
    # `...\Atlas\contracts\code-pin.yaml` on Windows. This tool's own refusals
    # name a file by its repository path, `as_posix()`, and are asserted as
    # such everywhere else in this module; this one is not its text.
    pin = str(Path("contracts") / "code-pin.yaml")
    stderr = refused_and_untouched(
        project, scaffolded, advanced, "bump-leg-validators-red",
        "yaml-unreadable", pin)
    assert "bump-leg-pin-unreadable" not in stderr
    assert "bump-leg-workflow-unreadable" not in stderr


# --- the controls: the refusal is not wider than the failure -----------------

def test_a_utf8_workflow_with_non_ascii_comments_still_bumps_byte_for_byte(
        project, scaffolded, advanced):
    """A non-ASCII file is not a non-UTF-8 file. The comment survives the
    lockstep rewrite BYTE FOR BYTE, and so does the BOM of a second file a
    Windows editor saved as 'UTF-8 with BOM': a tool that refused or
    normalised either would be a tool nobody could run in that project."""
    prepared(project)
    comment = "# café, 日本, ☃\n".encode("utf-8")
    commit_bytes(project, WORKFLOWS / "legs.yml", comment, append=True)
    bom = codecs.BOM_UTF8 + b"on: [pull_request]\n# caf\xc3\xa9\n"
    commit_bytes(project, WORKFLOWS / "bom.yml", bom)
    before = (project / WORKFLOWS / "legs.yml").read_bytes()

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr

    after = (project / WORKFLOWS / "legs.yml").read_bytes()
    assert after.endswith(comment), "the comment survives, byte for byte"
    assert after != before, "and the reference did move"
    assert (project / WORKFLOWS / "bom.yml").read_bytes() == bom
    assert validate(project).returncode == 0
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_a_non_utf8_file_the_validator_never_reads_does_not_stop_the_bump(
        project, scaffolded, advanced):
    """The refusal is over the set `validate-pins.py` reads: `.yml` and
    `.yaml` under `.github/workflows/`. A Latin-1 `notes.txt` beside them is
    nobody's input, and a refusal over it would be the tool having an opinion
    about a file it never opens."""
    prepared(project)
    commit_bytes(project, WORKFLOWS / "notes.txt", LATIN1_COMMENT)
    commit_bytes(project, Path("NOTES.md"), LATIN1_COMMENT)

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 0, result.stderr + result.stdout
    assert validate(project).returncode == 0
    assert (project / WORKFLOWS / "notes.txt").read_bytes() == LATIN1_COMMENT
