# SPDX-License-Identifier: Apache-2.0
"""`scripts/bump-leg.py --dry-run` runs on the project's tracking branch
(#477).

STEP 1 OF "Advancing a leg" IS A DRY RUN, and every fresh project stands on
its tracking branch after setup. The tool refused to commit onto that branch
and refused the dry run for it as well, with `bump-leg-on-tracking-branch`,
before it printed the `old -> new` line the human is meant to read. A dry run
commits nothing, so it now runs there, prints everything it prints on a
branch, and ends with ONE line saying the real run needs a branch and naming
the `git switch -c` that makes it, quoted so that it pastes for a root with a
space in it.

WHAT DID NOT MOVE is pinned here too, because each is the other half of the
rule: the real run on the tracking branch is refused with the same words, a
dry run on a branch prints what it always printed, a root on no branch at all
is refused under `--dry-run` as before, and the checks that come AFTER the
branch (the remote having the commit) still run for a dry run on the tracking
branch, so lifting the refusal did not lift them.

NO NETWORK, NO `gh`, NO BASH: the bare remotes are the session's own, so this
runs on every OS the suite runs on.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import PROJECT, cloned_just_pushed, git
from test_bump_leg import branched, bump, reference_both_legs
from test_bump_leg_paste_lines import BRANCH_LEFT_PROJECT
from test_bump_leg_rollback import assert_nothing_changed, snapshot
from test_commit_trailers import TRAILERS

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-dry-run-tracking-advance"

DRY_RUN = "--dry-run"

#: Said once, by the last line of a dry run on the tracking branch, and by no
#: other run.
NEEDS_A_BRANCH = "needs a branch"

#: What the hint says directly before the command a person pastes.
PASTE_AFTER = "Create one first with: "


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-dry-run-tracking")
        / f"{PROJECT}-spec")
    (work / "DRY-RUN-TRACKING.md").write_text("# a contract gained\n")
    git("add", "--", "DRY-RUN-TRACKING.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the dry-run-on-tracking-branch tests",
        cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def tracking_branch(project: Path) -> str:
    return git("symbolic-ref", "--short", "HEAD", cwd=project).stdout.strip()


def switch_command(project: Path, to: str) -> str:
    """The command the tool prints, spelled as it prints it: the root
    resolved, which is what `Project.open` does to `--root`, and the words
    joined by `shlex.join`. Joined here too, because `shlex.quote` quotes
    every path that holds a backslash, which is every Windows root."""
    return shlex.join(["git", "-C", str(project.resolve()), "switch", "-c",
                       f"bump/spec-{to[:12]}"])


# --- a dry run on the tracking branch ---------------------------------------

def test_a_dry_run_on_the_tracking_branch_prints_the_move_and_names_a_branch(
        project, scaffolded, advanced):
    """THE FIX: exit 0, the whole report, and a last line that says what the
    real run needs, with the sentence for a branch that is there already
    under it (#647). The workflows and the trailers are printed too, so the
    run is shown to reach every part of the report a dry run on a branch
    reaches, not only the first line."""
    was, _ = reference_both_legs(project)
    assert tracking_branch(project) == "main", "a fresh project's branch"
    before = snapshot(project)

    result = bump(project, scaffolded, advanced, DRY_RUN,
                  "--trailer", TRAILERS[0], "--trailer", TRAILERS[1])
    assert result.returncode == 0, result.stderr + result.stdout
    assert result.stderr == "", "a dry run there refuses nothing"

    out = result.stdout
    old_to_new = f"{was[:12]} -> {advanced[:12]}"
    assert old_to_new in out
    assert ".github/workflows/legs.yml" in out
    for line in TRAILERS:
        assert line in out
    assert "--dry-run: nothing was changed." in out
    assert "bump-leg-on-tracking-branch" not in out

    *_, hint, sentence = out.splitlines()
    assert sentence == BRANCH_LEFT_PROJECT
    assert f"the real run {NEEDS_A_BRANCH}" in hint
    assert hint.endswith(switch_command(project, advanced)), hint
    assert out.index(old_to_new) < out.index(TRAILERS[0]), (
        "the line the human reads comes first")
    assert out.index(TRAILERS[0]) < out.index(hint), (
        "the branch hint comes last")
    assert out.count(NEEDS_A_BRANCH) == 1, "ONE line, said once"

    assert_nothing_changed(project, before)
    assert tracking_branch(project) == "main", (
        "the dry run does not switch the root onto a branch itself")


def test_the_branch_hint_is_the_only_difference_from_a_dry_run_on_a_branch(
        project, scaffolded, advanced):
    """The same root, the same arguments, first on `main` and then on a
    branch: the second report is the first minus its last three lines, a
    blank one, the hint and the sentence under it (#647), byte for byte. So
    "a dry run on a branch is unchanged" is a comparison, not a pasted copy
    of today's wording."""
    reference_both_legs(project)
    on_tracking = bump(project, scaffolded, advanced, DRY_RUN)
    branched(project)
    on_a_branch = bump(project, scaffolded, advanced, DRY_RUN)
    assert on_tracking.returncode == 0, on_tracking.stderr + on_tracking.stdout
    assert on_a_branch.returncode == 0, on_a_branch.stderr + on_a_branch.stdout

    assert NEEDS_A_BRANCH not in on_a_branch.stdout, (
        "a root already on a branch is told nothing about one")
    assert on_tracking.stdout.startswith(on_a_branch.stdout)
    tail = on_tracking.stdout[len(on_a_branch.stdout):]
    *_, hint, sentence = on_tracking.stdout.splitlines()
    assert tail.splitlines() == ["", hint, sentence]
    assert tail.endswith(switch_command(project, advanced) + "\n"
                         + BRANCH_LEFT_PROJECT + "\n")
    assert on_tracking.stderr == ""
    assert on_a_branch.stderr == ""


def test_the_printed_switch_command_pastes_for_a_root_with_a_space(
        scaffolded, advanced, tmp_path):
    """`My Projects/` and `C:\\Users\\Jane Doe\\` are ordinary roots, and
    the printed line is the step "Advancing a leg" in AGENTS.md has the
    assistant paste. A shell splits an unquoted root at its space and hands
    git `Projects/Atlas` as the subcommand, so the line is quoted: read back
    the way a shell reads it, it is exactly the argv that makes the branch,
    and running that argv makes it."""
    root = tmp_path / "My Projects" / PROJECT
    shutil.copytree(scaffolded["clone"], root, symlinks=True)
    assert " " in str(root.resolve())

    result = bump(root, scaffolded, advanced, DRY_RUN)
    assert result.returncode == 0, result.stderr + result.stdout
    _, found, command = result.stdout.splitlines()[-2].partition(PASTE_AFTER)
    assert found, result.stdout

    branch = f"bump/spec-{advanced[:12]}"
    argv = shlex.split(command)
    assert argv == ["git", "-C", str(root.resolve()), "switch", "-c", branch]

    proc = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert tracking_branch(root) == branch


def test_a_dry_run_already_pinned_on_the_tracking_branch_says_nothing_to_do(
        project, scaffolded):
    """Nothing to move means nothing to advise: exit 1 and no branch hint,
    where it used to be refused before the tool read the pin at all."""
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    result = bump(project, scaffolded, pinned, DRY_RUN)
    assert result.returncode == 1, result.stderr + result.stdout
    assert "nothing to do" in result.stdout
    assert NEEDS_A_BRANCH not in result.stdout


# --- what is still refused --------------------------------------------------

def test_the_real_run_on_the_tracking_branch_is_refused_byte_for_byte(
        project, scaffolded, advanced):
    """The refusal's every byte, spelled out, and nothing on stdout: this is
    the text the run had before #477, and a change to it is a change to what
    a lane that scripts around it reads. The `switch -c` is spelled as the
    dry run's hint is, by `shlex` (#532): a plain root prints the bytes it
    always did, and one that needs quoting prints quoted. The sentence for a
    branch that is there already ends it, under `and re-run.` (#647)."""
    root = project.resolve()
    before = snapshot(project)

    result = bump(project, scaffolded, advanced)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == ""
    assert result.stderr == (
        f"REFUSED bump-leg-on-tracking-branch: {root} is on 'main', which "
        "project.yaml declares as this project's tracking branch\n"
        "Remediation: these organisations are pull-request only, so this "
        "will not make a commit whose only next step is a push to the "
        f"default branch. Run:\n    {switch_command(project, advanced)}\n"
        f"and re-run.\n{BRANCH_LEFT_PROJECT}\n")
    assert_nothing_changed(project, before)


def test_a_dry_run_on_a_root_with_no_branch_is_still_refused(
        project, scaffolded, advanced):
    """Control: the issue is the tracking branch. A detached root has no
    branch to push from under either mode, and `--dry-run` did not change
    that."""
    git("checkout", "-q", "--detach", cwd=project)
    result = bump(project, scaffolded, advanced, DRY_RUN)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED bump-leg-root-detached" in result.stderr
    assert result.stdout == ""


def test_a_dry_run_on_the_tracking_branch_still_checks_the_remote(
        project, scaffolded):
    """The refusal that stood in front of every other check is gone for a dry
    run, so the checks behind it are what a dry run on the tracking branch now
    meets: a commit the leg's remote does not have is refused, and no branch
    hint is printed for a move that could not be made."""
    result = bump(project, scaffolded, "0123456789abcdef" * 2 + "01234567",
                  DRY_RUN)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED bump-leg-commit-not-on-remote" in result.stderr
    assert NEEDS_A_BRANCH not in result.stdout
    assert git("status", "--porcelain", cwd=project).stdout == ""
