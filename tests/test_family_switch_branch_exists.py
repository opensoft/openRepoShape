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
give the branch another name, which starts it where the holder stands, or,
only if that branch holds work not merged yet, the same command with
`switch` in place of `switch -c` goes back to it and keeps every commit on
it. Neither prints a command that resets or deletes it.

THE PROOF IS THE PRINTED LINE, TYPED, IN EVERY STATE. With no such branch,
the `switch -c` makes it. With one an earlier act left, holding a commit of
its own, the `switch -c` fails as git says and changes nothing, the same
command with `switch` for `switch -c` goes back to it, the act goes through
there, and the earlier commit is the parent of the act's. Another name is
the way out where going back is wrong, and the reason it comes first: where
`main` has moved on since the earlier act (a later member was squash-merged),
the new branch starts at that `main` and `add` goes through and merges with
no conflict; where the holder stands on a detached HEAD that carries a
commit, the new branch keeps it.

THE GUARD. Every remedy of the holder's validator that names `_switch_line`
ends its prose with the sentence, read from the template's source, so a
fourth remedy added later (#610's `_lockstep`) that forgets it fails here.

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

import ast
import re
import shlex
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, git, run_script
from repo_shape import PYTHON
from test_bump_leg import bump_leg_module  # noqa: F401
from test_family import (  # noqa: F401
    FAMILY, ORG, SPARE, family, family_module, manifest, mount_twice,
    scaffold_member, validate,
)
from test_family_printed_quoting import host_words
from test_family_tracking_branch import (  # noqa: F401
    TRACKING, act, next_push, on_main, refspec, remedy_switch, snapshot,
    suggested,
)
from test_setup_project_py import entry_point_module
# `BRANCH_LEFT` is the sentence the tools end the remedy with, pinned as
# text: a person, an agent and a holder's CI read it, so it is not rebuilt
# from any tool's own constant here.
from test_validate_family_branch_step import BRANCH_LEFT, TEMPLATE, gate_module
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
    """The same command with `switch` in place of `switch -c`, as the
    sentence says."""
    assert argv.count("-c") == 1, argv
    return [word for word in argv if word != "-c"]


def on_branch(holder: Path) -> str:
    return git("symbolic-ref", "--short", "HEAD", cwd=holder).stdout.strip()


def head(holder: Path) -> str:
    return git("rev-parse", "HEAD", cwd=holder).stdout.strip()


def remedy_lines(stderr: str) -> tuple[list[str], list[str]]:
    """The remedy's `switch -c` as the reader's shell reads it, and the
    lines under it."""
    lines = stderr.splitlines()
    switch = remedy_switch(stderr)
    at = next(i for i, line in enumerate(lines)
              if line.startswith("    ") and host_words(line) == switch)
    return switch, lines[at + 1:]


def refused_as_left(holder: Path, switch: list[str], branch: str) -> None:
    """The remedy's `switch -c`, typed as printed where `branch` is there:
    git's `fatal: a branch named ... already exists`, exit 128, and nothing
    changed."""
    before = head(holder)
    made = typed(switch)
    assert made.returncode == 128, made.stderr
    assert re.search(rf"fatal: a branch named '{re.escape(branch)}' "
                     "already exists", made.stderr, re.I), made.stderr
    assert head(holder) == before


def type_switch(holder: Path, switch: list[str], branch: str,
                earlier: str | None) -> None:
    """The remedy's `switch -c`, typed as printed. With no branch of that
    name (`earlier` None) it makes it. With one an earlier act left, it
    fails as #607 says and changes nothing, and the same command with
    `switch` in place of `switch -c` goes back to that branch, at its own
    commit."""
    if earlier is None:
        made = typed(switch)
        assert made.returncode == 0, made.stderr
    else:
        refused_as_left(holder, switch, branch)
        assert on_branch(holder) == TRACKING
        back = typed(without_c(switch))
        assert back.returncode == 0, back.stderr
        assert head(holder) == earlier
    assert on_branch(holder) == branch


def type_other_name(holder: Path, switch: list[str], branch: str) -> str:
    """The remedy's `switch -c` where `branch` is there, typed as printed
    (refused), then with another name: the new branch starts where the
    holder stands. Returns its name."""
    assert switch[-1] == branch, switch
    refused_as_left(holder, switch, branch)
    other = f"{branch}-2"
    before = head(holder)
    made = typed([*switch[:-1], other])
    assert made.returncode == 0, made.stderr
    assert head(holder) == before
    assert on_branch(holder) == other
    return other


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
    switch, under = remedy_lines(refused.stderr)
    assert under[0] == BRANCH_LEFT, under
    assert under[1].startswith("Then push that branch"), under
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
    assert push[-1] == refspec(branch), push
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


# --- family.py: another name, where going back to the branch is wrong --------

#: The member a later pull request adds, and squash-merges, while an earlier
#: act's branch sits: a project that is not one the fixture mounts or keeps
#: spare.
LATER = "IRXS"


def move_main_on(holder: Path, remotes_base: Path) -> None:
    """What `main` does while an earlier act's branch sits: another member is
    added on a branch of its own and its pull request squash-merged, so `main`
    holds one new commit with that branch's tree on the main the earlier
    branch was made from. The holder is back on `main` and clean."""
    scaffold_member(remotes_base, LATER)
    git("switch", "-q", "-c", f"family/add-{LATER.lower()}", cwd=holder)
    added = run_script(FAMILY, "add", "--family-root", str(holder),
                       "--member", f"{ORG}/{LATER}", "--local-remote-dir",
                       str(remotes_base / "remotes"))
    assert added.returncode == 0, added.stderr + added.stdout
    squash = git("commit-tree", "-p", TRACKING, "-m", f"Add {LATER} (#1)",
                 "HEAD^{tree}", cwd=holder).stdout.strip()
    git("update-ref", f"refs/heads/{TRACKING}", squash, cwd=holder)
    git("switch", "-q", TRACKING, cwd=holder)
    assert git("status", "--porcelain", cwd=holder).stdout == ""


def test_another_name_works_where_main_has_moved_since(family, on_main,
                                                       tmp_path):
    """STATE (d), the review's: an earlier act left `family/add-irqs` at the
    `main` of its day, holding no commit, and a later member has been
    squash-merged since. The refusal's `switch -c`, typed as printed, fails;
    the same line with another name starts the branch at the `main` the
    holder stands on, `add` goes through there, and what it commits merges
    into `main` with no conflict. That is what this test shows: the other
    name works. Going back to the old branch is the other way, and it
    conflicts here, but this test does not assert that; rv607's probe and
    decision 2's table in the PR body show it. The sentence puts that way
    second, for a branch that holds work not merged yet."""
    holder = on_main
    branch = suggested(family, "add")
    git("branch", branch, cwd=holder)
    later = tmp_path / "later"
    later.mkdir()
    move_main_on(holder, later)
    assert git("rev-parse", branch, cwd=holder).stdout == \
        git("rev-parse", f"{TRACKING}~1", cwd=holder).stdout
    refused = act(family, holder, "add")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    switch, under = remedy_lines(refused.stderr)
    assert under[0] == BRANCH_LEFT, under
    other = type_other_name(holder, switch, branch)
    done = act(family, holder, "add")
    assert done.returncode == 0, done.stdout + done.stderr
    merged = git("merge-tree", "--write-tree", TRACKING, other, cwd=holder,
                 check=False)
    assert merged.returncode == 0, merged.stdout
    projects = [row["project"] for row in manifest(holder)["members"]]
    assert LATER in projects
    assert SPARE in projects
    assert validate(holder).returncode == 0


def test_another_name_keeps_a_commit_made_on_a_detached_head(family, on_main):
    """`family-holder-detached` with a commit made on the detached HEAD, and
    the earlier act's branch there already. The refusal's `switch -c`, typed
    as printed, fails; the same line with another name keeps that commit:
    `git branch --contains` names the new branch and no other. (Going back
    to a branch with `switch` leaves a commit no branch holds behind, which
    is why the sentence says that way only for a branch with work on it.)"""
    holder = on_main
    branch = suggested(family, "add")
    git("branch", branch, cwd=holder)
    git("switch", "-q", "--detach", cwd=holder)
    git("commit", "-q", "--allow-empty", "-m", "Work done on a detached HEAD",
        cwd=holder)
    work = head(holder)
    refused = act(family, holder, "add")
    assert refused.returncode == 2, refused.stdout + refused.stderr
    assert "REFUSED family-holder-detached: " in refused.stderr
    switch, under = remedy_lines(refused.stderr)
    assert under[0] == BRANCH_LEFT, under
    other = type_other_name(holder, switch, branch)
    held = git("branch", "--contains", work, "--format=%(refname:short)",
               cwd=holder).stdout.split()
    assert held == [other]


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


def as_text(node: ast.expr) -> str:
    """A string expression as the text it builds, each value in it a
    `{expression}` placeholder: an f-string, a `+` of strings, a literal."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(as_text(part) for part in node.values)
    if isinstance(node, ast.FormattedValue):
        return "{" + ast.unparse(node.value) + "}"
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return as_text(node.left) + as_text(node.right)
    return "{" + ast.unparse(node) + "}"


def switch_remedies(source: str) -> list[tuple[int, str]]:
    """Each place `source` names `_switch_line`: its line and the PROSE of
    the string it stands in, as text up to the first line break (the
    command lines come under it). The string is the whole expression the
    call is written in: wherever the call stands inside the string
    expression that is passed on, as the f-string of a `Refusal` or a
    `report.finding`, or as the `return` of a helper."""
    tree = ast.parse(source)
    parents = {child: node for node in ast.walk(tree)
               for child in ast.iter_child_nodes(node)}
    found = []
    for call in ast.walk(tree):
        if not (isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == "_switch_line"):
            continue
        string = call
        while isinstance(parents.get(string),
                         (ast.FormattedValue, ast.JoinedStr, ast.BinOp)):
            string = parents[string]
        found.append((string.lineno, as_text(string).split("\n", 1)[0]))
    return found


def unguarded(source: str) -> list[int]:
    """The line of each remedy naming `_switch_line` whose prose does not
    end with `BRANCH_LEFT`."""
    return [line for line, prose in switch_remedies(source)
            if not prose.endswith("{BRANCH_LEFT}")]


def test_every_remedy_that_names_a_switch_line_ends_with_the_sentence():
    """THE GUARD (S2). The validator's three remedies that print a `git
    switch -c` (`member-gitlink-absent`, `member-duplicate-id` and
    `member-gitlink-unnamed`) end their prose with `BRANCH_LEFT`, and so
    does any remedy added later: the one that builds it cannot forget, as
    #610's `_lockstep` does, without this failing."""
    source = TEMPLATE.read_text(encoding="utf-8")
    assert len(switch_remedies(source)) >= 3, switch_remedies(source)
    assert unguarded(source) == []


def fourth_remedy(end: str) -> str:
    """A helper that returns a remedy naming `_switch_line`, as #610's
    `_lockstep` does, its prose ending with `end`."""
    return ("\n\ndef _lockstep_remedy(root):\n    return (\n"
            "        f\"(`{_switch_line(root, 'bump', None)}` makes one); \"\n"
            "        f\"moving one alone is what this refuses."
            + end + "\")\n")


def test_the_guard_sees_a_remedy_left_without_the_sentence():
    """The guard is not vacuous: the validator's source with the sentence
    taken out of any one of its remedies fails it, and so does a fourth
    remedy, built by a helper as `_lockstep` builds its, until the sentence
    ends it."""
    source = TEMPLATE.read_text(encoding="utf-8")
    placed = [m.start() for m in re.finditer(r"\{BRANCH_LEFT\}", source)]
    assert len(placed) >= 3, placed
    for at in placed:
        dropped = source[:at] + source[at + len("{BRANCH_LEFT}"):]
        assert len(unguarded(dropped)) == 1, source[at - 60:at]
    assert len(unguarded(source + fourth_remedy(""))) == 1
    assert unguarded(source + fourth_remedy(" {BRANCH_LEFT}")) == []


def test_the_tools_say_the_same_words(monkeypatch, bump_leg_module):
    """ONE ANSWER: `family.py` and the holder's validator, which a holder
    carries as a copy and which cannot import `family.py`, spell the
    sentence the same, word for word, and so do `setup-project.py`, which
    runs before any checkout of the standard exists, and `bump-leg.py`,
    which says "the project" where the others say "the holder" (#647)."""
    assert family_module().BRANCH_LEFT == BRANCH_LEFT
    assert gate_module(monkeypatch).BRANCH_LEFT == BRANCH_LEFT
    assert entry_point_module().BRANCH_LEFT == BRANCH_LEFT
    assert bump_leg_module.BRANCH_LEFT == BRANCH_LEFT.replace(
        "the holder", "the project")


# --- one placeholder for the member (L2-45) ----------------------------------

#: The `switch -c` and the first `add` of each doc's block, each read for the
#: placeholder it puts where the member goes. The docs say `<path>` where a
#: root goes, so a word with no space in it; what `init` prints says a real
#: root, which may hold one, so it is read with `host_words` instead.
BRANCH_WORD = re.compile(r" switch -c family/add-(\S+)")
MEMBER_WORD = re.compile(r" add +--family-root <path> --member \S*/(\S+)")


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
    block = [line.strip() for line in
             capsys.readouterr().out.split("NEXT STEPS", 1)[1].splitlines()
             if line.strip()]
    switch, add = host_words(block[0]), host_words(block[1])
    assert switch[-1] == "family/add-<Project>", block
    assert add[add.index("--member") + 1] == f"{ORG}/<Project>", block


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
    assert push[-1] == refspec(branch), push
    assert SPARE in [row["project"] for row in manifest(holder)["members"]]
