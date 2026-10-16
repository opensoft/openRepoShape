# SPDX-License-Identifier: Apache-2.0
"""The `git switch -c` line of `bump-leg.py` and of `setup-project.py`'s
family block, where an earlier act left that branch (#647).

THE BRANCH THAT IS THERE ALREADY. #607 gave `family.py` and the holder's
`validate-family.py` one sentence for a `switch -c` that fails `fatal: a
branch named '<branch>' already exists` (exit 128): give the branch another
name, which starts it where the holder stands, or, only if that branch holds
work not merged yet, the same command with `switch` in place of `switch -c`
goes back to it and keeps every commit on it. Two tools of this standard
still printed a `switch -c` and said nothing more: `bump-leg.py`, in both
refusals of `_branch_to_bump_from` (`bump-leg-on-tracking-branch`,
`bump-leg-root-detached`) and in the dry run's closing hint (#477), and
`setup-project.py`, in the family block it ends on (#487). Each now says the
SAME sentence under that line, `bump-leg.py` with "the project" where the
others say "the holder". No command line changes.

THE TEXT IS PINNED HERE, as a person, an agent and a holder's CI read it, and
each tool's own constant is held to it: one rule, in the same words.

THE PROOF IS THE PRINTED LINE, TYPED. In a real local project (`bump-leg.py`)
and a real local holder (the family block), an earlier act leaves the branch
with a commit of its own, the printed `switch -c` fails `already exists`
(exit 128) and changes nothing, and each choice the sentence gives works:
another name starts at the commit the root stands on, and the same command
with `switch` for `switch -c` goes back to the branch at its own commit. The
act then goes through on either, and the commit it writes sits on top of the
commit it started from.

NO NETWORK, NO `gh`, NO SHELL: each line is read back the way a shell reads
it and typed as an argv, so the tests hold on every OS the suite runs on.
Nothing here pushes.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest

from conftest import PROJECT, REPO, cloned_just_pushed, git
from test_bump_leg import bump, bump_leg_module  # noqa: F401
from test_bump_leg_paste_lines import (
    BRANCH_LEFT_PROJECT, detached_remedy, switch_argv, tracking_remedy, words,
)
from test_family import ORG, SPARE, family  # noqa: F401
from test_family_printed_quoting import FOLDERS, host_words
from test_family_tracking_branch import (  # noqa: F401
    act, on_main, suggested,
)
from test_setup_project_py import run_entry

SETUP = REPO / "setup-project.py"

#: The sentence of `family.py` and the holder's `validate-family.py` (#607),
#: pinned as text. `bump-leg.py` says the same sentence with a project where
#: this has a holder: `BRANCH_LEFT_PROJECT`, pinned in
#: `test_bump_leg_paste_lines.py` beside the lines it follows.
BRANCH_LEFT_HOLDER = (
    "If `git switch -c` says that branch already exists, an earlier act left "
    "it: give the branch another name, which starts it where the holder "
    "stands, or, only if that branch holds work not merged yet, the same "
    "command with `switch` in place of `switch -c` goes back to it and keeps "
    "every commit on it.")

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "bump-leg-branch-left-advance"

#: The three places `bump-leg.py` names a `switch -c`.
KINDS = pytest.mark.parametrize("kind", ["tracking", "detached", "dry-run"])

#: What stands under the command in each, to the end of the output: the
#: tracking-branch remedy ends `and re-run.` under its command line, the
#: others carry the command on the line they stand on.
UNDER_THE_COMMAND = {
    "tracking": ["and re-run.", BRANCH_LEFT_PROJECT],
    "detached": [BRANCH_LEFT_PROJECT],
    "dry-run": [BRANCH_LEFT_PROJECT],
}

#: Needle the dry run's hint puts directly before the command.
PASTE_AFTER = "Create one first with: "


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-branch-left")
        / f"{PROJECT}-spec")
    (work / "BRANCH-LEFT.md").write_text("# a contract gained\n")
    git("add", "--", "BRANCH-LEFT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the branch-left tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def setup_module():
    """`setup-project.py` as a module (the name has a hyphen in it)."""
    spec = importlib.util.spec_from_file_location("setup_branch_left", SETUP)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the text, one rule ---------------------------------------------------------

def test_bump_leg_says_the_sentence_with_the_project(bump_leg_module):
    assert bump_leg_module.BRANCH_LEFT == BRANCH_LEFT_PROJECT


def test_setup_says_the_sentence_with_the_holder():
    assert setup_module().BRANCH_LEFT == BRANCH_LEFT_HOLDER


def test_the_two_texts_differ_in_the_one_word_only():
    assert BRANCH_LEFT_HOLDER.count("the holder") == 1
    assert BRANCH_LEFT_HOLDER.replace("the holder", "the project") == \
        BRANCH_LEFT_PROJECT


# --- what is typed ------------------------------------------------------------

def head(root: Path) -> str:
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


def on_branch(root: Path) -> str:
    return git("symbolic-ref", "--short", "-q", "HEAD", cwd=root,
               check=False).stdout.strip()


def typed(argv: list[str]) -> subprocess.CompletedProcess:
    """`argv` run as a person runs the line it was read from."""
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def without_c(argv: list[str]) -> list[str]:
    """The same command with `switch` in place of `switch -c`, as the
    sentence says."""
    assert argv.count("-c") == 1, argv
    return [word for word in argv if word != "-c"]


def leave_branch(root: Path, branch: str) -> str:
    """What an earlier act leaves: `branch`, made from the root's HEAD and
    holding one commit of its own, while the root stays where it stands.
    Written with `commit-tree` and `update-ref`, so nothing is checked out.
    Returns that commit."""
    earlier = git("commit-tree", "-p", "HEAD", "-m", "An earlier act's work",
                  "HEAD^{tree}", cwd=root).stdout.strip()
    git("update-ref", f"refs/heads/{branch}", earlier, cwd=root)
    return earlier


def refused_as_left(root: Path, switch: list[str], branch: str) -> None:
    """The printed `switch -c`, typed where `branch` is there: git's `fatal:
    a branch named ... already exists`, exit 128, and nothing changed."""
    before = head(root)
    stood_on = on_branch(root)
    made = typed(switch)
    assert made.returncode == 128, made.stderr
    assert re.search(rf"fatal: a branch named '{re.escape(branch)}' "
                     "already exists", made.stderr, re.I), made.stderr
    assert head(root) == before
    assert on_branch(root) == stood_on


def type_where_none_is_left(root: Path, switch: list[str],
                            branch: str) -> None:
    """The control: with no such branch, the printed line makes it."""
    made = typed(switch)
    assert made.returncode == 0, made.stderr
    assert on_branch(root) == branch


def type_another_name(root: Path, switch: list[str], branch: str) -> str:
    """The printed line where `branch` is there (refused), then with another
    name: the new branch starts where the root stands. Returns its name."""
    assert switch[-1] == branch, switch
    refused_as_left(root, switch, branch)
    other = f"{branch}-2"
    before = head(root)
    made = typed([*switch[:-1], other])
    assert made.returncode == 0, made.stderr
    assert head(root) == before
    assert on_branch(root) == other
    return other


def type_going_back(root: Path, switch: list[str], branch: str,
                    earlier: str) -> None:
    """The printed line where `branch` is there (refused), then the same
    command with `switch` in place of `switch -c`: back on the branch, at the
    commit it holds."""
    refused_as_left(root, switch, branch)
    back = typed(without_c(switch))
    assert back.returncode == 0, back.stderr
    assert on_branch(root) == branch
    assert head(root) == earlier


def parent(root: Path) -> str:
    return git("rev-parse", "HEAD~1", cwd=root).stdout.strip()


# --- bump-leg.py: what is printed, under the command ---------------------------

def put_where(kind: str, root: Path) -> None:
    """The root where `kind` meets it: on its tracking branch (what a fresh
    project is), or on no branch."""
    if kind == "detached":
        git("checkout", "-q", "--detach", cwd=root)


def printed(kind: str, root: Path, scaffolded: dict, advanced: str):
    """`bump-leg.py` run where `kind` meets the root: the printed
    `switch -c` as the argv a POSIX shell reads out of it, and every line
    under the command to the end of what was printed, which ends with the
    sentence."""
    put_where(kind, root)
    if kind == "dry-run":
        result = bump(root, scaffolded, advanced, "--dry-run")
        assert result.returncode == 0, result.stderr + result.stdout
        lines = result.stdout.splitlines()
        command = lines[-2].partition(PASTE_AFTER)[2]
        assert command, result.stdout
        under = lines[-1:]
    else:
        result = bump(root, scaffolded, advanced)
        assert result.returncode == 2, result.stderr + result.stdout
        assert result.stdout == ""
        lines = result.stderr.splitlines()
        if kind == "detached":
            command = detached_remedy(result.stderr)
            at = lines.index(f"Remediation: `{command}` and re-run.")
        else:
            command = tracking_remedy(result.stderr)
            at = lines.index("    " + command)
        under = lines[at + 1:]
    assert under[-1] == BRANCH_LEFT_PROJECT, under
    return words(command), under


@KINDS
def test_each_place_says_the_sentence_under_its_command(
        project, scaffolded, advanced, kind):
    """THE ISSUE, for each of the three places. The command line is the one
    it always was, and what stands under it, to the end, is the sentence:
    after `and re-run.` in the tracking-branch remedy, alone under the other
    two."""
    switch, under = printed(kind, project, scaffolded, advanced)
    assert switch == switch_argv(project, advanced)
    assert under == UNDER_THE_COMMAND[kind]


@KINDS
def test_the_printed_line_makes_the_branch_where_none_is_left(
        project, scaffolded, advanced, kind):
    """The control: with no such branch, the printed `switch -c` makes it,
    and the run it refused goes through on it."""
    switch, _ = printed(kind, project, scaffolded, advanced)
    before = head(project)
    type_where_none_is_left(project, switch, switch[-1])
    done = bump(project, scaffolded, advanced)
    assert done.returncode == 0, done.stderr + done.stdout
    assert parent(project) == before


@KINDS
def test_another_name_works_where_an_earlier_bump_left_the_branch(
        project, scaffolded, advanced, kind):
    """CHOICE ONE. An earlier bump left `bump/spec-<id>` holding a commit of
    its own: the printed line fails `already exists`, the same line with
    another name starts a branch where the root stands, and the bump goes
    through there, on top of the commit it started from."""
    branch = f"bump/spec-{advanced[:12]}"
    put_where(kind, project)
    leave_branch(project, branch)
    switch, _ = printed(kind, project, scaffolded, advanced)
    other = type_another_name(project, switch, branch)
    before = head(project)
    done = bump(project, scaffolded, advanced)
    assert done.returncode == 0, done.stderr + done.stdout
    assert on_branch(project) == other
    assert parent(project) == before
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == \
        advanced


@KINDS
def test_going_back_works_where_an_earlier_bump_left_the_branch(
        project, scaffolded, advanced, kind):
    """CHOICE TWO. The same command with `switch` in place of `switch -c`
    goes back to the branch at its own commit, and the bump goes through
    there, on top of the earlier commit, which it keeps."""
    branch = f"bump/spec-{advanced[:12]}"
    put_where(kind, project)
    earlier = leave_branch(project, branch)
    switch, _ = printed(kind, project, scaffolded, advanced)
    type_going_back(project, switch, branch, earlier)
    done = bump(project, scaffolded, advanced)
    assert done.returncode == 0, done.stderr + done.stdout
    assert on_branch(project) == branch
    assert parent(project) == earlier
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == \
        advanced


# --- setup-project.py: the family block ----------------------------------------

def family_block(landing, capsys, project: str = "Sample",
                 org: str = "demoorg") -> list[str]:
    """What `family_next_command` prints for `landing`, line by line."""
    setup_module().family_next_command(project, org, landing)
    return capsys.readouterr().out.splitlines()


def landing_for(holder: Path):
    return setup_module().Landing(holder.parent, holder.name, holder)


@pytest.mark.parametrize("folder", FOLDERS)
def test_setup_says_the_sentence_under_its_switch_line(tmp_path, folder,
                                                       capsys):
    """THE ISSUE. The `switch -c` line is the one it was, then its two
    comment lines, then ONE more comment line, the sentence, in the holder's
    words, before the `add` line; and the commands are the same two."""
    holder = tmp_path / folder / "Orbit" / "Orbit"
    lines = family_block(landing_for(holder), capsys)
    assert host_words(lines[0].strip()) == [
        "git", "-C", str(holder), "switch", "-c", "family/add-sample"]
    assert lines[1].strip() == "# a branch first: `add` refuses the"
    assert lines[2].strip() == "#   holder's tracking branch"
    assert lines[3] == " " * 27 + "# " + BRANCH_LEFT_HOLDER
    assert host_words(lines[4].strip())[1:4] == ["scripts/family.py", "add",
                                                 "--family-root"]
    commands = [line for line in lines
                if line.strip() and not line.strip().startswith("#")]
    assert len(commands) == 2, lines


def test_a_real_run_prints_the_sentence_once_under_the_switch_line(tmp_path):
    """The block as `hand_over` prints it, from a real run into a family
    folder: the sentence stands once, in the same words, right after the
    comment that says why a branch comes first."""
    result = run_entry("Sample", "--yes", "--org", "demoorg",
                       "--family", "Zephyr",
                       "--local-remote-dir", str(tmp_path / "remotes"),
                       "--into", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    lines = result.stdout.splitlines()
    assert lines.count(" " * 27 + "# " + BRANCH_LEFT_HOLDER) == 1, lines
    at = lines.index(" " * 27 + "# " + BRANCH_LEFT_HOLDER)
    assert lines[at - 1].strip() == "#   holder's tracking branch"
    assert " switch -c family/add-sample" in lines[at - 3]


def setup_switch(holder: Path, capsys) -> list[str]:
    """The `switch -c` the family block prints for the fixture's spare
    member, as the reader's shell reads it, with the sentence under it."""
    lines = family_block(landing_for(holder), capsys, SPARE, ORG)
    assert lines[3] == " " * 27 + "# " + BRANCH_LEFT_HOLDER
    return host_words(lines[0].strip())


def test_the_family_blocks_line_makes_the_branch_where_none_is_left(
        family, on_main, capsys):
    """The control, in a real holder: the block's `switch -c` makes the
    branch, and the `add` under it goes through on it."""
    holder = on_main
    switch = setup_switch(holder, capsys)
    assert switch[-1] == suggested(family, "add")
    type_where_none_is_left(holder, switch, switch[-1])
    done = act(family, holder, "add")
    assert done.returncode == 0, done.stdout + done.stderr
    assert on_branch(holder) == switch[-1]


def test_another_name_works_where_an_earlier_try_left_the_family_branch(
        family, on_main, capsys):
    """CHOICE ONE, in a real holder that has `family/add-<project>` from an
    earlier try, with a commit of its own: the block's line fails `already
    exists`, another name starts where the holder stands, and the `add`
    goes through there."""
    holder = on_main
    switch = setup_switch(holder, capsys)
    leave_branch(holder, switch[-1])
    other = type_another_name(holder, switch, switch[-1])
    before = head(holder)
    done = act(family, holder, "add")
    assert done.returncode == 0, done.stdout + done.stderr
    assert on_branch(holder) == other
    assert parent(holder) == before


def test_going_back_works_where_an_earlier_try_left_the_family_branch(
        family, on_main, capsys):
    """CHOICE TWO, in the same holder: the same command with `switch` goes
    back to the branch at its own commit, and the `add` goes through on top
    of it."""
    holder = on_main
    switch = setup_switch(holder, capsys)
    earlier = leave_branch(holder, switch[-1])
    type_going_back(holder, switch, switch[-1], earlier)
    done = act(family, holder, "add")
    assert done.returncode == 0, done.stdout + done.stderr
    assert parent(holder) == earlier
