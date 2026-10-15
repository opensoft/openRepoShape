# SPDX-License-Identifier: Apache-2.0
"""The `git switch -c family/<act>-<member>` remedy where an earlier act left
that branch, and one placeholder for the member in the branch (#607).

THE BRANCH THAT IS THERE ALREADY. `family.py add`, `bump` and `remove`
refuse the holder's tracking branch with `git -C <holder> switch -c
family/<act>-<member>` (#487), and the holder's `validate-family.py` names
the same line before each `add` and `remove` it prints (#539). Where an
earlier act left that branch the line fails, `fatal: a branch named
'family/add-irqs' already exists`, exit 128, and neither tool said what to
do next. Both now end the remedy with ONE sentence, the same words in both:
the same command without `-c` switches to the branch and keeps every commit
on it, or give the branch another name. Neither prints a command that
resets or deletes it.

THE PROOF IS THE PRINTED LINE, TYPED, IN BOTH STATES. With no such branch,
the `switch -c` makes it. With one an earlier act left, holding a commit of
its own, the `switch -c` fails as git says and changes nothing, the same
command without `-c` switches to it, the act goes through there, and the
earlier commit is the parent of the act's.

ONE PLACEHOLDER (L2-45). AGENTS.md, the holder's README and AGENTS-shape.md
and `init`'s NEXT STEPS spelled the branch `family/add-<project>` beside
`--member <org>/<Project>`, two spellings of one value; the holder's
validator already says `<Project>` for both (#539). All of them now say
`<Project>`, and the branch filled in as written, in the project's own case,
is one `add` commits on.

THE SAME FAMILY AS `tests/test_family.py`, in `on_main`'s private copy of
the holder on its tracking branch. Nothing here pushes.
"""

from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, git, run_script
from repo_shape import PYTHON
from test_family import (  # noqa: F401
    ORG, SPARE, family, family_module, manifest, mount_twice, validate,
)
from test_family_printed_quoting import host_words
from test_family_tracking_branch import (  # noqa: F401
    TRACKING, act, next_push, on_main, remedy_switch, snapshot, suggested,
)
# `BRANCH_LEFT` is the sentence both tools end the remedy with, pinned as
# text: a person, an agent and a holder's CI read it, so it is not rebuilt
# from either tool's own constant here.
from test_validate_family_branch_step import BRANCH_LEFT, gate_module
from test_validate_family_unnamed_mounts import spare_commits, stage_gitlink

#: Each state a remedy is typed in: no branch of that name, and one an
#: earlier act left.
STATES = pytest.mark.parametrize("left", [False, True],
                                 ids=["no-branch", "branch-left"])


def leave_branch(holder: Path, branch: str) -> str:
    """What an earlier act leaves: `branch`, made from the holder's HEAD and
    holding one commit of its own, while the holder stays where it stands.
    Written with `commit-tree` and `update-ref`, so nothing is checked out.
    Returns that commit."""
    earlier = git("commit-tree", "-p", "HEAD", "-m", "An earlier act's work",
                  "HEAD^{tree}", cwd=holder).stdout.strip()
    git("update-ref", f"refs/heads/{branch}", earlier, cwd=holder)
    return earlier


def typed(argv: list[str]) -> subprocess.CompletedProcess:
    """`argv` run as a person runs the line it was read from."""
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def without_c(argv: list[str]) -> list[str]:
    """The same command without `-c`, as the sentence says."""
    assert argv.count("-c") == 1, argv
    return [word for word in argv if word != "-c"]


def on_branch(holder: Path) -> str:
    return git("symbolic-ref", "--short", "HEAD", cwd=holder).stdout.strip()


def head(holder: Path) -> str:
    return git("rev-parse", "HEAD", cwd=holder).stdout.strip()


def type_switch(holder: Path, switch: list[str], branch: str,
                earlier: str | None) -> None:
    """The remedy's `switch -c`, typed as printed. With no branch of that
    name (`earlier` None) it makes it. With one an earlier act left, it
    fails as #607 says and changes nothing, and the same command without
    `-c` switches to that branch, at its own commit."""
    before = head(holder)
    made = typed(switch)
    if earlier is None:
        assert made.returncode == 0, made.stderr
    else:
        assert made.returncode == 128, made.stderr
        assert re.search(rf"fatal: a branch named '{re.escape(branch)}' "
                         "already exists", made.stderr, re.I), made.stderr
        assert head(holder) == before
        assert on_branch(holder) == TRACKING
        back = typed(without_c(switch))
        assert back.returncode == 0, back.stderr
        assert head(holder) == earlier
    assert on_branch(holder) == branch


# --- family.py: the refusal, typed as printed, in both states ---------------

@STATES
@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_the_refusal_typed_as_printed_puts_the_act_on_its_branch(
        family, on_main, verb, left):
    """THE ISSUE, for each act. Refused on `main`, the remedy's `switch -c`
    is followed by the sentence, and names no command that resets or
    deletes a branch. Typed as printed in either state, it puts the holder
    on the branch, and the act then commits there: where an earlier act left
    the branch, on top of the commit it holds."""
    holder = on_main
    branch = suggested(family, verb)
    earlier = leave_branch(holder, branch) if left else None
    before = snapshot(holder)
    refused = act(family, holder, verb)
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert snapshot(holder) == before
    lines = refused.stderr.splitlines()
    switch = remedy_switch(refused.stderr)
    at = next(i for i, line in enumerate(lines)
              if line.startswith("    ") and host_words(line) == switch)
    assert lines[at + 1] == BRANCH_LEFT, lines
    assert lines[at + 2].startswith("Then push that branch"), lines
    for discards in ("switch -C", "branch -D", "reset", "--discard-changes"):
        assert discards not in refused.stderr, refused.stderr

    type_switch(holder, switch, branch, earlier)
    done = act(family, holder, verb)
    assert done.returncode == 0, done.stdout + done.stderr
    assert on_branch(holder) == branch
    if earlier is not None:
        assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == \
            earlier
    push, _ = next_push(done.stdout)
    assert push[-1] == branch, push
    assert validate(holder).returncode == 0


@pytest.mark.parametrize("verb", ["add", "bump", "remove"])
def test_a_dry_run_on_the_tracking_branch_says_it_too(family, on_main, verb):
    """`--dry-run` names the real run's `switch -c` on a line of its own,
    and the sentence under it, as the real run's remedy does."""
    result = act(family, on_main, verb, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    at = lines.index(f"branch       {TRACKING} is the holder's tracking "
                     f"branch, where a real {verb} refuses "
                     "(family-on-tracking-branch); make a branch first:")
    assert host_words(lines[at + 1])[-2:] == ["-c", suggested(family, verb)]
    assert lines[at + 2] == "             " + BRANCH_LEFT


# --- validate-family.py: each remedy that names the branch ------------------

@STATES
def test_a_missing_gitlinks_remedy_typed_as_printed(on_main, left):
    """`member-gitlink-absent`: the remedy's prose ends with the sentence,
    and its first command, typed as printed, puts the holder on the branch
    the `add` under it needs, in either state."""
    holder = on_main
    git("rm", "-r", "-q", "-f", "--", "members/IRRS", cwd=holder)
    git("commit", "-qm", "Drop the gitlink but keep the row", cwd=holder)
    earlier = leave_branch(holder, "family/add-irrs") if left else None
    result = validate(holder)
    assert result.returncode == 2, result.stdout + result.stderr
    lines = result.stderr.splitlines()
    assert lines[0].startswith("REFUSED member-gitlink-absent: "), lines
    assert lines[1].endswith(
        "a row with no submodule is a claim about a tree that is not here. "
        + BRANCH_LEFT), lines[1]
    switch = shlex.split(lines[2])
    assert switch[-2:] == ["-c", "family/add-irrs"], lines[2]
    type_switch(holder, switch, "family/add-irrs", earlier)


@STATES
def test_a_duplicate_ids_remedy_typed_as_printed(family, on_main, left):
    """`member-duplicate-id`: the finding ends with the sentence. Its
    `switch -c`, typed as printed in either state, puts the holder on the
    branch, and the `remove` beside it, run as printed from a checkout of
    openRepoShape, then takes the later row out there."""
    holder = on_main
    mount_twice(holder, family["remotes"])
    earlier = leave_branch(holder, "family/remove-irrs") if left else None
    found = validate(holder)
    assert found.returncode == 1, found.stderr + found.stdout
    line = found.stderr.split("FINDING member-duplicate-id: ",
                              1)[1].splitlines()[0]
    assert line.endswith(". " + BRANCH_LEFT), line
    switch, remove = [command for command in re.findall(r"`([^`]*)`", line)
                      if command.startswith(("git -C", PYTHON))]
    type_switch(holder, shlex.split(switch), "family/remove-irrs", earlier)
    removed = run_script(REPO / "scripts" / "family.py",
                         *shlex.split(remove)[2:], cwd=REPO)
    assert removed.returncode == 0, removed.stderr + removed.stdout
    if earlier is not None:
        assert git("rev-parse", "HEAD~1", cwd=holder).stdout.strip() == \
            earlier
    assert "IRRS2" not in [row["project"]
                           for row in manifest(holder)["members"]]


@STATES
def test_an_unnamed_gitlinks_remedy_typed_as_printed(family, on_main, left):
    """`member-gitlink-unnamed` for a hand mount: the finding's prose ends
    with the sentence, and its first command, typed as printed in either
    state, puts the holder on the branch `add` needs."""
    holder = on_main
    _, tip = spare_commits(family)
    stage_gitlink(holder, f"members/{SPARE}", tip)
    branch = f"family/add-{SPARE.lower()}"
    earlier = leave_branch(holder, branch) if left else None
    result = validate(holder, "--no-members")
    assert result.returncode == 1, result.stderr + result.stdout
    finding = result.stderr.split("FINDING member-gitlink-unnamed: ", 1)[1]
    assert finding.splitlines()[0].endswith(
        "if one is still there. " + BRANCH_LEFT), finding
    switch = shlex.split(finding.splitlines()[1])
    assert switch[-2:] == ["-c", branch], switch
    type_switch(holder, switch, branch, earlier)


def test_the_two_tools_say_the_same_words(monkeypatch):
    """ONE ANSWER: `family.py` and the holder's validator, which a holder
    carries as a copy and which cannot import `family.py`, spell the
    sentence the same, word for word."""
    assert family_module().BRANCH_LEFT == BRANCH_LEFT
    assert gate_module(monkeypatch).BRANCH_LEFT == BRANCH_LEFT


# --- one placeholder for the member (L2-45) ----------------------------------

#: The `switch -c` and the first `add` of each doc's block, each read for the
#: placeholder it puts where the member goes.
BRANCH_WORD = re.compile(r" switch -c family/add-(\S+)")
MEMBER_WORD = re.compile(r" add +--family-root \S+ --member \S*/(\S+)")


@pytest.mark.parametrize("doc", [
    "AGENTS.md", "templates/family-root/AGENTS-shape.md",
    "templates/family-root/README.md"])
def test_each_doc_spells_the_branch_as_its_member(doc):
    """The branch and `--member` beside it stand for one project, so they
    say it one way, `<Project>`, the placeholder the holder's validator
    says for both (#539)."""
    text = (REPO / doc).read_text(encoding="utf-8")
    assert BRANCH_WORD.search(text).group(1) == "<Project>", doc
    assert MEMBER_WORD.search(text).group(1) == "<Project>", doc


def test_init_next_steps_spell_the_branch_as_its_member(capsys, tmp_path):
    """`init`'s NEXT STEPS open with the same pair, spelled the same way."""
    work = tmp_path / "Orbit" / "Orbit"
    family_module()._print_next_steps(
        SimpleNamespace(org=ORG, tracking_branch=TRACKING), work, None)
    printed = capsys.readouterr().out
    assert BRANCH_WORD.search(printed).group(1) == "<Project>", printed
    assert MEMBER_WORD.search(printed).group(1) == "<Project>", printed


def test_the_branch_filled_in_as_written_is_one_add_commits_on(family,
                                                               on_main):
    """`<Project>` filled in as the project is spelled makes a branch the
    act takes: any branch but the tracking one is (#487). `add`'s own
    refusal names it lowercased; the case is not what the act asks about."""
    holder = on_main
    branch = f"family/add-{SPARE}"
    git("switch", "-q", "-c", branch, cwd=holder)
    done = act(family, holder, "add")
    assert done.returncode == 0, done.stdout + done.stderr
    push, _ = next_push(done.stdout)
    assert push[-1] == branch, push
    assert SPARE in [row["project"] for row in manifest(holder)["members"]]
