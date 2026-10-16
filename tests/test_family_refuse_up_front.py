# SPDX-License-Identifier: Apache-2.0
"""`add`, `bump` and `remove` refuse, BEFORE their first write, a holder they
cannot commit in (#612, from #459's 571(e), 571(d) and 574/5).

Each of the three ends in ONE `git commit -- <paths>`, made after the verb's
first writes (`add` mounts the member, `bump` checks it out at `--to`,
`remove` unmounts it), and a rollback puts the holder back when that commit
or anything else after the first write fails. Three states made it fail, or
land where nobody wanted it, every time:

- **An act git has unfinished in the holder** (571(e)). A merge or a
  cherry-pick: `fatal: cannot do a partial commit during a merge.`, after
  the writes, rolled back. A revert, a rebase and a `git am`: git does NOT
  refuse the partial commit (measured on git 2.43), so it was made inside
  the act, and for a rebase the real run met the branch refusal first
  (`family-holder-detached`, whose `git switch -c` is the wrong advice
  there) while the dry run printed a plan. One refusal now, `family-
  operation-in-progress`, under both runs, naming the act and its own exit.
- **A path the sparse checkout leaves out** (571(d), 574/5). `.gitmodules`
  put back on disk by hand, its skip-worktree mark cleared by git, passed
  #407's check by mark and failed `remove` at `git add`; a `members/` the
  rules leave out failed `add` at `git submodule add` and `bump` and
  `remove` at `git add` and `git rm`. Asked of git's own rules (`git
  sparse-checkout check-rules`), `family-sparse-excluded`, and only where
  sparse checkout is on and git can answer.
- **A FILE named `members`** (574/5): `add` read the member, then failed at
  the mount (`Not a directory`). `member-path-unaddable` now, before the
  member is read.

THE PROOF IS THE SAME FOR EACH: exit 2 and one REFUSED paragraph, nothing on
stdout (so no member was read: `add` says `checking ... before mounting it`
before it reads), the holder byte for byte as it was (HEAD, index,
`family.yaml`, work tree, git config) under the real run and `--dry-run`
alike; then the remedy typed as printed, and the same command goes through.

THE SAME FAMILY AS `test_family.py`, this module's own instance of its
fixture, in a private copy of the holder that stands on the work branch. Each
file written is written as bytes, every git command runs under the offline,
identity-carrying environment the dry-run tests use, and a rebase or a merge
is made with git itself, never by writing its state files.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

#: The family fixture and its names, imported from the module that owns them.
from test_family import SPARE, family, family_module  # noqa: F401
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: What a verb must leave as it found it, and the three verbs, as the dry-run
#: tests spell them: the order of each comparison names the first fact that
#: moved, and `add`'s differs from `bump`'s and `remove`'s.
from test_family_dry_run import (
    BUMP_ORDER, REMOVE_ORDER, add, add_state, assert_add_as_it_was,
    assert_as_it_was, bump, isolated, remove, state,
)
from test_family_member_path import MEMBER, OTHER, older, raw, recorded

GITMODULES = ".gitmodules"
NOTES = "NOTES.txt"


def check_rules_available() -> bool:
    """Does this machine's git have `git sparse-checkout check-rules`? Asked
    of git, in a repository of its own that has sparse checkout on, so an
    unknown subcommand and a git that cannot read the rules both say no."""
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
        for args in (["init", "-q", "."],
                     ["-c", "user.name=t", "-c", "user.email=t@t.invalid",
                      "commit", "-q", "--allow-empty", "-m", "c"],
                     ["sparse-checkout", "set", "--no-cone", "/*"]):
            if subprocess.run(["git", *args], cwd=scratch, env=env,
                              capture_output=True, check=False
                              ).returncode != 0:
                return False
        asked = subprocess.run(
            ["git", "sparse-checkout", "check-rules", "-z"], cwd=scratch,
            env=env, input=b"a\0", capture_output=True, check=False)
        return asked.returncode == 0 and asked.stdout == b"a\0"


needs_check_rules = pytest.mark.skipif(
    not check_rules_available(),
    reason="this git has no `git sparse-checkout check-rules`, which the "
           "refusal asks; without it the verb cannot tell and refuses "
           "nothing, as `test_a_git_that_cannot_tell_refuses_nothing` shows "
           "where it can run")


# --- the three verbs --------------------------------------------------------

VERBS = ("add", "bump", "remove")


def run_verb(verb: str, family, root: Path, env: dict, *extra: str):
    """`verb` against `root`, as a person types it: `add` mounts SPARE,
    `bump` moves MEMBER to an older commit, `remove` takes MEMBER out."""
    if verb == "add":
        return add(root, env, family["remotes"], *extra)
    if verb == "bump":
        return bump(root, env, older(family), *extra)
    return remove(root, env, *extra)


def snapshot(verb: str, root: Path, env: dict) -> dict:
    """Everything the verb's refusal must leave as it found it."""
    return add_state(root, env) if verb == "add" else state(root, env)


def assert_untouched(verb: str, root: Path, env: dict, before: dict) -> None:
    if verb == "add":
        assert_add_as_it_was(root, env, before)
    else:
        assert_as_it_was(root, env, before,
                         BUMP_ORDER if verb == "bump" else REMOVE_ORDER)


def head_of(root: Path, env: dict) -> str:
    return raw(root, env, "rev-parse", "HEAD").stdout.decode().strip()


def assert_refused_alike(verb: str, family, root: Path, env: dict,
                         expected_stderr, mark: str | None = None):
    """THE PROOF OF A REFUSAL BEFORE THE FIRST WRITE, under both runs: exit 2,
    the one paragraph `expected_stderr` (a compiled pattern for the REFUSED
    line, the remediation exactly) and nothing on stdout, so the member was
    not read; the holder as it was, and `mark`, the act's own mark in git's
    directory, still there; and the dry run's words the real run's. Returns
    the last run."""
    before = snapshot(verb, root, env)
    said = []
    for extra in ((), ("--dry-run",)):
        ran = run_verb(verb, family, root, env, *extra)
        assert ran.returncode == 2, (extra, ran.stdout, ran.stderr)
        assert ran.stdout == "", (extra, ran.stdout)
        line, remedy = refusal(ran.stderr)
        said.append((line, remedy))
        expected_line, expected_remedy = expected_stderr
        assert expected_line.fullmatch(line), (extra, line)
        assert remedy == expected_remedy, (extra, remedy)
        assert_untouched(verb, root, env, before)
        if mark is not None:
            assert os.path.lexists(mark_of(root, env, mark)), mark
    assert said[0] == said[1], "the two runs refuse in different words"
    return ran


# --- an act git has unfinished ---------------------------------------------

#: `{kind: (what, the mark git keeps, how it is finished, how it is given
#: up, what the commit would do)}`, as the refusal says each. `{verb}` is the
#: verb that asked. `finish` is None where git can continue nothing.
REBASE_EFFECT = (
    "git does not refuse that during a rebase: the commit would land on the "
    "HEAD the rebase has detached, in the middle of its sequence, where "
    "`git rebase --continue` replays the rest on top of it into the rebased "
    "branch and `git rebase --abort` drops it")


def series_effect(command: str) -> str:
    return ("git does not refuse that between the steps of a series, so the "
            f"commit would land in the middle of it: `{command} --continue` "
            f"replays the rest on top of it, and `{command} --abort` stops "
            "and leaves it where it is (`You seem to have moved HEAD. Not "
            "rewinding`)")


OPERATIONS = {
    "merge": (
        "a merge", "MERGE_HEAD", "git commit", "git merge --abort",
        "git refuses that during a merge (`fatal: cannot do a partial "
        "commit during a merge.`), after `{verb}`'s first writes, which are "
        "then put back"),
    "cherry-pick": (
        "a cherry-pick", "CHERRY_PICK_HEAD", "git cherry-pick --continue",
        "git cherry-pick --abort",
        "git refuses that during a cherry-pick (`fatal: cannot do a partial "
        "commit during a cherry-pick.`), after `{verb}`'s first writes, "
        "which are then put back"),
    "rebase": (
        "a rebase", "rebase-merge", "git rebase --continue",
        "git rebase --abort", REBASE_EFFECT),
    "revert": (
        "a revert", "REVERT_HEAD", "git revert --continue",
        "git revert --abort",
        "git does not refuse that during a revert: the commit is made on "
        "the branch as `{verb}`'s own, and git takes it as the end of the "
        "revert, so `git revert --continue` and `--abort` then say `no "
        "cherry-pick or revert in progress` and the revert's changes are "
        "left half done in the index and the work tree"),
    "am": (
        "a `git am`", "rebase-apply", "git am --continue", "git am --abort",
        "git does not refuse that during a `git am`, so the commit would "
        "land on the branch, in the middle of the patches being applied"),
    "cherry-pick series": (
        "a cherry-pick series", "sequencer", "git cherry-pick --continue",
        "git cherry-pick --abort", series_effect("git cherry-pick")),
    "revert series": (
        "a revert series", "sequencer", "git revert --continue",
        "git revert --abort", series_effect("git revert")),
    "unreadable series": (
        "a cherry-pick or revert series", "sequencer", None,
        "git cherry-pick --abort",
        "git does not refuse that, and the commit would land beside a "
        "`sequencer/` directory git can read no series from, which "
        "`--continue` fails on"),
}


def operation_said(kind: str, verb: str) -> tuple:
    """`(the REFUSED line as a pattern, the remediation)` for `kind`, asked by
    `verb`: the path git keeps the mark at is the one part that varies."""
    what, mark, finish, abort, effect = OPERATIONS[kind]
    line = re.compile(
        re.escape(f"REFUSED family-operation-in-progress: {what} is "
                  f"unfinished in the family root: git keeps {mark} at ")
        + r".+/" + re.escape(mark)
        + re.escape(f". `{verb}` makes its commit with `git commit -- "
                    f"<paths>`, and {effect.format(verb=verb)}. No git "
                    "command that writes was run and nothing was written."))
    if finish is None:
        remedy = ("Remediation: `sequencer/` is what a cherry-pick or revert "
                  "series left behind, and git can read no step from it, so "
                  "there is nothing to continue: give it up with "
                  f"`{abort}` (`git revert --abort` is the same), or clear "
                  "it without moving HEAD with `git cherry-pick --quit`. "
                  "Then run the same command again.")
    else:
        remedy = ("Remediation: end it, whichever way suits the work in it: "
                  f"finish it with `{finish}` once whatever stopped it is "
                  f"resolved and staged, or give it up with `{abort}`. Then "
                  "run the same command again.")
    return line, remedy


def commit_file(root: Path, env: dict, name: str, data: bytes,
                message: str) -> None:
    (root / name).write_bytes(data)
    raw(root, env, "add", "--", name)
    raw(root, env, "commit", "-q", "-m", message)


def work_branch(root: Path, env: dict) -> str:
    return raw(root, env, "symbolic-ref", "--short", "HEAD"
               ).stdout.decode().strip()


def conflicting_history(root: Path, env: dict) -> str:
    """`NOTES.txt` as `base` on the work branch, `side` on a branch made from
    it, and `main` on the work branch again: a cherry-pick of `side`, a rebase
    of it, an `am` of its patch all stop on that file. Returns the work
    branch, which the holder is left on."""
    work = work_branch(root, env)
    commit_file(root, env, NOTES, b"base\n", "notes")
    raw(root, env, "switch", "-q", "-c", "side")
    commit_file(root, env, NOTES, b"side\n", "side")
    raw(root, env, "switch", "-q", work)
    commit_file(root, env, NOTES, b"main\n", "main")
    return work


def mark_of(root: Path, env: dict, name: str) -> Path:
    shown = raw(root, env, "rev-parse", "--git-path", name
                ).stdout.decode().strip()
    return root / shown


def series(kind: str, root: Path, env: dict) -> None:
    """A cherry-pick or a revert of SEVERAL commits, stopped on its first step
    and that step committed by hand, so no `CHERRY_PICK_HEAD` or
    `REVERT_HEAD` is left and `sequencer/` holds the steps still to take
    (#612's review, F2). `unreadable series` has its `todo` taken away."""
    work = work_branch(root, env)
    if kind == "revert series":
        commit_file(root, env, NOTES, b"zero\n", "zero")
        base = head_of(root, env)
        commit_file(root, env, "x1.txt", b"1\n", "x1")
        commit_file(root, env, "x2.txt", b"2\n", "x2")
        commit_file(root, env, NOTES, b"mid\n", "y")
        commit_file(root, env, NOTES, b"late\n", "z")
        stopped = raw(root, env, "revert", "--no-edit", f"{base}..HEAD~1",
                      check=False)
    else:
        commit_file(root, env, NOTES, b"base\n", "base")
        base = head_of(root, env)
        raw(root, env, "switch", "-q", "-c", "side")
        commit_file(root, env, NOTES, b"side\n", "side1")
        commit_file(root, env, "side2.txt", b"2\n", "side2")
        commit_file(root, env, "side3.txt", b"3\n", "side3")
        raw(root, env, "switch", "-q", work)
        commit_file(root, env, NOTES, b"main\n", "main")
        stopped = raw(root, env, "cherry-pick", f"{base}..side", check=False)
    assert stopped.returncode != 0, "premise: the first step conflicts"
    commit_file(root, env, NOTES, b"resolved\n", "the stopped step, by hand")
    for gone in ("CHERRY_PICK_HEAD", "REVERT_HEAD"):
        assert not os.path.lexists(mark_of(root, env, gone)), (
            f"premise: only `sequencer/` is left, not {gone}")
    if kind == "unreadable series":
        mark_of(root, env, "sequencer/todo").unlink()


def begin(kind: str, root: Path, env: dict, tmp_path: Path) -> None:
    """Leave `root` in the middle of `kind`, with git, and check the mark git
    keeps for it is there: the premise of every test that calls this."""
    if kind.endswith(" series"):
        series(kind, root, env)
    elif kind == "rebase and merge":
        # A merge begun at a rebase's stop leaves `MERGE_HEAD` and
        # `rebase-merge/` both. `-x "exit 1"` stops the rebase after a step.
        work = work_branch(root, env)
        base = head_of(root, env)
        raw(root, env, "switch", "-q", "-c", "other")
        commit_file(root, env, "other.txt", b"other\n", "other")
        raw(root, env, "switch", "-q", work)
        raw(root, env, "switch", "-q", "-c", "topic")
        commit_file(root, env, "topic.txt", b"topic\n", "topic")
        stopped = raw(root, env, "rebase", "-x", "exit 1", base, check=False)
        assert stopped.returncode != 0, "premise: the rebase stops"
        raw(root, env, "merge", "--no-commit", "--no-ff", "other")
        assert os.path.lexists(mark_of(root, env, "MERGE_HEAD")), (
            "premise: the merge is in progress too")
    elif kind == "merge":
        # `--no-commit`: no conflict at all, the state the issue's probe made.
        work = work_branch(root, env)
        raw(root, env, "switch", "-q", "-c", "side")
        commit_file(root, env, "other.txt", b"other\n", "other")
        raw(root, env, "switch", "-q", work)
        raw(root, env, "merge", "--no-commit", "--no-ff", "side")
    elif kind == "cherry-pick":
        conflicting_history(root, env)
        stopped = raw(root, env, "cherry-pick", "side", check=False)
        assert stopped.returncode != 0, "premise: the cherry-pick conflicts"
    elif kind == "rebase":
        work = conflicting_history(root, env)
        raw(root, env, "switch", "-q", "side")
        stopped = raw(root, env, "rebase", work, check=False)
        assert stopped.returncode != 0, "premise: the rebase conflicts"
    elif kind == "revert":
        conflicting_history(root, env)
        commit_file(root, env, NOTES, b"later\n", "later")
        stopped = raw(root, env, "revert", "--no-edit", "HEAD~1", check=False)
        assert stopped.returncode != 0, "premise: the revert conflicts"
    else:
        work = conflicting_history(root, env)
        patch = tmp_path / "side.patch"
        patch.write_bytes(raw(root, env, "format-patch", "-1", "side",
                              "--stdout").stdout)
        stopped = raw(root, env, "am", str(patch), check=False)
        assert stopped.returncode != 0, "premise: the am conflicts"
        assert work_branch(root, env) == work
    mark = OPERATIONS.get(kind, OPERATIONS["rebase"])[1]
    assert os.path.lexists(mark_of(root, env, mark)), f"premise: {mark}"


@pytest.mark.parametrize("kind, verb", [
    ("merge", "add"), ("merge", "bump"), ("merge", "remove"),
    ("cherry-pick", "add"), ("cherry-pick", "remove"),
    ("rebase", "bump"), ("rebase", "add"), ("revert", "remove"),
    ("revert", "bump"), ("am", "add"), ("am", "remove"),
    ("cherry-pick series", "add"), ("cherry-pick series", "bump"),
    ("revert series", "remove"), ("revert series", "add"),
    ("unreadable series", "remove"), ("unreadable series", "bump"),
])
def test_every_unfinished_act_is_named_and_refused_alike_in_both_runs(
        family, holder, offline, tmp_path, kind, verb):
    """THE ISSUE'S PROBE (p07) for a merge, and the other acts: a merge
    (stopped with `--no-commit`, no conflict at all), a cherry-pick, a
    rebase, a revert and a `git am`, each stopped on a conflict by git, and a
    cherry-pick or revert SERIES with only `sequencer/` left, and one whose
    `todo` git cannot read. Each is named, with its own finish and its own
    give-up, by the real run and the dry run in the same words, the holder
    untouched and the act's mark still there. A revert, a rebase and an `am`
    were no failure at the commit (git does not refuse a partial commit
    there); the real run met a rebase as `family-holder-detached`, which
    committed nothing, the dry run printed a plan."""
    env = isolated(offline, tmp_path)
    begin(kind, holder, env, tmp_path)
    assert_refused_alike(verb, family, holder, env, operation_said(kind, verb),
                         mark=OPERATIONS[kind][1])


@pytest.mark.parametrize("kind, refused", [
    ("merge", "a merge"), ("cherry-pick", "a cherry-pick"),
    ("revert", None), ("rebase", None), ("am", None),
    ("cherry-pick series", None), ("revert series", None)])
def test_what_each_refusal_says_the_commit_would_do_is_what_git_does(
        family, holder, offline, tmp_path, kind, refused):
    """THE EFFECT SENTENCES ARE TIED TO GIT, so they cannot drift from it
    (#612's review, F1). The partial commit the verbs make is made here with
    git itself, `git commit -- :(literal)family.yaml`: a merge and a
    cherry-pick are refused (`cannot do a partial commit during ...`); a
    revert takes it as the END of the revert (`REVERT_HEAD` goes, and `git
    revert --continue` says `no cherry-pick or revert in progress`); a
    rebase and an `am` keep their mark; and in a series git commits it, and
    `--continue` then replays the rest on top of it."""
    env = isolated(offline, tmp_path)
    begin(kind, holder, env, tmp_path)
    manifest = holder / "family.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"# a change\n")
    made = raw(holder, env, "commit", "-q", "-m", "THE VERB'S COMMIT", "--",
               ":(literal)family.yaml", check=False)
    mark = OPERATIONS[kind][1]
    if refused:
        assert made.returncode == 128, made.stderr
        assert (f"cannot do a partial commit during {refused}".encode()
                in made.stderr)
        return
    assert made.returncode == 0, made.stderr
    if kind == "revert":
        assert not os.path.lexists(mark_of(holder, env, mark))
        stuck = raw(holder, env, "revert", "--continue", check=False)
        assert stuck.returncode == 128
        assert b"no cherry-pick or revert in progress" in stuck.stderr
    elif kind.endswith(" series"):
        command = kind.split()[0]
        raw(holder, env, command, "--continue")
        subjects = raw(holder, env, "log", "--format=%s", "-6"
                       ).stdout.decode().split("\n")
        assert "THE VERB'S COMMIT" in subjects[1:], subjects
        assert subjects[0] != "THE VERB'S COMMIT", subjects
    else:
        assert os.path.lexists(mark_of(holder, env, mark))


#: `{id: (kind, verb, the command the remediation names, what is added to it
#: to run without an editor)}`: `git commit` finishes a merge that stopped
#: with no conflict, once it has a message.
EXITS = {
    "merge, finished": ("merge", "add", "git commit", ("-q", "-m", "merged")),
    "merge, given up": ("merge", "remove", "git merge --abort", ()),
    "cherry-pick, given up": ("cherry-pick", "bump", "git cherry-pick --abort",
                              ()),
    "rebase, given up": ("rebase", "add", "git rebase --abort", ()),
    "revert, given up": ("revert", "remove", "git revert --abort", ()),
    "am, given up": ("am", "bump", "git am --abort", ()),
    "cherry-pick series, continued": (
        "cherry-pick series", "add", "git cherry-pick --continue", ()),
    "cherry-pick series, given up": (
        "cherry-pick series", "bump", "git cherry-pick --abort", ()),
    "revert series, continued": (
        "revert series", "remove", "git revert --continue", ()),
    "unreadable series, given up": (
        "unreadable series", "add", "git cherry-pick --abort", ()),
}


@pytest.mark.parametrize("kind, verb, printed, added", EXITS.values(),
                         ids=EXITS)
def test_the_remedy_typed_as_printed_lets_the_same_command_run(
        family, holder, offline, tmp_path, kind, verb, printed, added):
    """THE REMEDY IS THE ACT'S OWN EXIT, and it works: the command it prints
    is read back out of the refusal and run, and the same verb then makes its
    ONE commit, a child of the HEAD it started from."""
    env = isolated(offline, tmp_path)
    begin(kind, holder, env, tmp_path)
    ran = run_verb(verb, family, holder, env)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    _, remedy = refusal(ran.stderr)
    assert printed in re.findall(r"`(git [^`]+)`", remedy), remedy
    raw(holder, env, *shlex.split(printed)[1:], *added)
    assert not os.path.lexists(mark_of(holder, env, OPERATIONS[kind][1]))
    was = head_of(holder, env)
    done = run_verb(verb, family, holder, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert raw(holder, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
        == was
    assert raw(holder, env, "status", "--porcelain").stdout == b""


@pytest.mark.parametrize("verb", VERBS)
def test_a_rebase_is_asked_before_a_merge_begun_inside_it(
        family, holder, offline, tmp_path, verb):
    """"A REBASE IS ASKED FIRST": a merge begun at a rebase's stop leaves
    `MERGE_HEAD` and `rebase-merge/` both, and the refusal names the rebase,
    whose `git rebase --abort` clears both in one step, where `git merge
    --abort` would leave `rebase-merge/` and a second refusal (#612's
    review, N2). The exit is typed as printed, and the verb then runs."""
    env = isolated(offline, tmp_path)
    begin("rebase and merge", holder, env, tmp_path)
    ran = assert_refused_alike(verb, family, holder, env,
                               operation_said("rebase", verb),
                               mark="rebase-merge")
    assert "git rebase --abort" in ran.stderr
    raw(holder, env, "rebase", "--abort")
    assert not os.path.lexists(mark_of(holder, env, "MERGE_HEAD"))
    assert not os.path.lexists(mark_of(holder, env, "rebase-merge"))
    done = run_verb(verb, family, holder, env)
    assert done.returncode == 0, done.stdout + done.stderr


def test_every_mark_is_asked_in_one_git_call(
        family, holder, offline, tmp_path, monkeypatch):
    """ONE `git rev-parse` answers every mark (#612's review, N8): up to eight
    `--git-path` arguments, one line each, where a process per mark cost
    eight on every verb, and more on Windows."""
    for key, value in isolated(offline, tmp_path).items():
        monkeypatch.setenv(key, value)
    calls = recorded(monkeypatch)
    assert family_module()._operation_in_progress(holder) is None
    asked = [argv for argv in calls if "--git-path" in argv]
    assert len(asked) == 1, asked
    assert asked[0].count("--git-path") >= 8, asked


def test_a_merge_in_a_linked_worktree_is_found_where_git_keeps_it(
        family, holder, offline, tmp_path):
    """`.git` is a FILE in a linked worktree, which is where a lane opens its
    pull request, and the merge's mark is under `.git/worktrees/<name>/`,
    never `.git/MERGE_HEAD`: asked of `git rev-parse --git-path`, the mark is
    found, and the refusal names the path git keeps it at."""
    env = isolated(offline, tmp_path)
    linked = tmp_path / "linked"
    raw(holder, env, "worktree", "add", "-q", "-b", "linked-branch",
        str(linked))
    begin("merge", linked, env, tmp_path)
    assert (linked / ".git").is_file()
    for extra in ((), ("--dry-run",)):
        ran = add(linked, env, family["remotes"], *extra)
        assert ran.returncode == 2, ran.stdout + ran.stderr
        assert ran.stdout == ""
        line, _ = refusal(ran.stderr)
        assert re.search(r"git keeps MERGE_HEAD at \S+/worktrees/[^/]+/"
                         r"MERGE_HEAD\. ", line), line


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows refuses a newline in a file name; Linux "
                           "and APFS take it")
def test_a_holder_path_with_a_newline_still_shows_its_merge(
        family, holder, offline, tmp_path):
    """V-F1 of #612's verification. A linked worktree's `git rev-parse
    --git-path` answers with an ABSOLUTE path through the holder's own
    `.git`, so a holder in a directory whose name holds a newline makes every
    answer two lines, and `_git_paths` asks each name alone. It once kept
    only that answer's FIRST line, which named a directory that does not
    exist: no mark was found, `add --dry-run` printed a plan, and the real
    `add` mounted and failed at the commit, #612's own defect back for that
    path. The whole answer, less git's final newline, is the path."""
    env = isolated(offline, tmp_path)
    broken = tmp_path / "Ink\nRouter"
    shutil.copytree(holder, broken, symlinks=True)
    linked = tmp_path / "linked"
    raw(broken, env, "worktree", "add", "-q", "-b", "linked-branch",
        str(linked))
    begin("merge", linked, env, tmp_path)
    shown = raw(linked, env, "rev-parse", "--git-path", "MERGE_HEAD"
                ).stdout.decode()
    assert shown.count("\n") == 2, f"premise: a newline in the path: {shown!r}"
    for extra in ((), ("--dry-run",)):
        ran = add(linked, env, family["remotes"], *extra)
        assert ran.returncode == 2, (extra, ran.stdout, ran.stderr)
        assert ran.stdout == ""
        assert ran.stderr.startswith(
            "REFUSED family-operation-in-progress: a merge is unfinished in "
            "the family root: git keeps MERGE_HEAD at "), ran.stderr
        assert "Ink\nRouter/.git/worktrees/" in ran.stderr, ran.stderr


def test_with_no_act_and_no_sparse_checkout_each_verb_runs_as_it_always_did(
        family, holder, offline, tmp_path):
    """THE CONTROL: no act in progress, no sparse checkout; each verb commits
    as it did, in a holder of its own."""
    env = isolated(offline, tmp_path)
    for verb in VERBS:
        copy = tmp_path / f"control-{verb}"
        shutil.copytree(holder, copy, symlinks=True)
        was = head_of(copy, env)
        ran = run_verb(verb, family, copy, env)
        assert ran.returncode == 0, (verb, ran.stdout, ran.stderr)
        assert raw(copy, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
            == was


# --- a path the sparse checkout leaves out ----------------------------------

def sparse_set(root: Path, env: dict, *rules: str, cone: bool = False) -> None:
    raw(root, env, "sparse-checkout", "set",
        "--cone" if cone else "--no-cone", *rules)


#: The rules that leave `.gitmodules` out, by what names it: the file
#: anchored, the file anywhere, and every dotfile at the root.
GITMODULES_OUT = {"anchored": ("/*", f"!/{GITMODULES}"),
                  "unanchored": ("/*", f"!{GITMODULES}"),
                  "every dotfile": ("/*", "!/.*")}


def restored_by_hand(root: Path, env: dict, shape: str = "anchored") -> None:
    """THE ISSUE'S STATE (571(d)): the rules leave `.gitmodules` out, the file
    is back on disk because a person put it there, and git's skip-worktree
    mark is CLEAR, so #407's check, which reads the mark, passes. Built with
    git's own `sparse-checkout set`, then the file written back as bytes and
    the mark taken off."""
    sparse_set(root, env, *GITMODULES_OUT[shape])
    put_back(root, env, GITMODULES)


def put_back(root: Path, env: dict, name: str) -> None:
    """`name`, a file the rules leave out, written back by a hand with the
    index's own bytes, and git's mark taken off it: the file is on disk, the
    mark is clear and the rules still leave it out. Each is a premise."""
    if not (root / name).exists():
        (root / name).write_bytes(raw(root, env, "show", f":{name}").stdout)
    raw(root, env, "update-index", "--no-skip-worktree", "--", name)
    listed = raw(root, env, "ls-files", "-v", "--", name).stdout
    assert listed.startswith(b"H "), f"premise: the mark is clear: {listed!r}"
    assert outside(root, env, name), "premise: the rules leave it out"


def outside(root: Path, env: dict, path: str) -> bool:
    """Do the holder's sparse rules leave `path` out? Asked of git as the
    tool asks it."""
    kept = raw(root, env, "sparse-checkout", "check-rules", "-z",
               stdin=path.encode() + b"\0").stdout
    return kept == b""


SPARSE_LINE = (
    "REFUSED family-sparse-excluded: the holder's sparse checkout leaves out "
    "{names}, which `{verb}` stages, and git will not update an index entry "
    "outside the sparse-checkout definition: `git sparse-checkout "
    "check-rules` says {are} outside, so `{verb}` would fail after its first "
    "writes. No git command that writes was run and nothing was written.")


def sparse_remedy(*patterns: str, one: bool = True) -> str:
    adding = ("" if not patterns else
              f"`git sparse-checkout add {' '.join(patterns)}`, or ")
    return (f"Remediation: bring {'it' if one else 'them'} back into the "
            f"rules: {adding}`git sparse-checkout disable`, which brings "
            "back every path the sparse checkout leaves out and leaves a "
            "copy already on disk as it is. Then run the same command "
            "again.")


def sparse_said(verb: str, paths: list[str], *patterns: str) -> tuple:
    names = ", ".join(f"`{path}`" for path in paths)
    line = SPARSE_LINE.format(names=names, verb=verb,
                              are="it is" if len(paths) == 1 else "they are")
    return re.compile(re.escape(line)), sparse_remedy(
        *patterns, one=len(paths) == 1)


def type_the_remedy(root: Path, env: dict, stderr: str) -> None:
    """Run the `git sparse-checkout add ...` the refusal prints, as printed."""
    typed = re.search(r"`git sparse-checkout add ([^`]+)`", stderr)
    assert typed, stderr
    raw(root, env, "sparse-checkout", "add", *typed.group(1).split())


@needs_check_rules
@pytest.mark.parametrize("shape", GITMODULES_OUT)
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_remove_refuses_a_gitmodules_the_rules_leave_out_before_deinit(
        family, holder, offline, tmp_path, dry_run, shape):
    """THE ISSUE'S p06: sparse rules leave `.gitmodules` out, the file is put
    back by hand, git clears the mark, #407's check passes, and `remove` did
    `deinit` and `git rm` and failed at `git add` (`outside of your
    sparse-checkout definition`), then rolled back. Now refused before
    `deinit`: the mount, the registration in the git config and the index are
    untouched, which `REMOVE_ORDER` reads key by key. The pattern the
    remediation names is typed as printed, and `remove` then goes through.
    The pattern is the file UNANCHORED, `.gitmodules`: appended after each
    of the rules that leave it out (the file named with a slash, without
    one, and every dotfile) it brings the file back (#612's review, N7)."""
    env = isolated(offline, tmp_path)
    restored_by_hand(holder, env, shape)
    before = state(holder, env)
    extra = ("--dry-run",) if dry_run else ()
    ran = remove(holder, env, *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = sparse_said(
        "remove", [GITMODULES], GITMODULES)
    assert expected_line.fullmatch(line), line
    assert remedy == expected_remedy
    assert_as_it_was(holder, env, before, REMOVE_ORDER)
    assert (holder / "members" / MEMBER / "project.yaml").is_file()

    type_the_remedy(holder, env, ran.stderr)
    done = remove(holder, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert raw(holder, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
        == before["HEAD"].decode().strip()
    assert not (holder / "members" / MEMBER).exists()


#: The rules that leave a member's mount out: cone mode, which keeps only
#: what it names, and non-cone rules that leave out the whole of `members/`,
#: or name the member, or glob under it. `{p}` is the member's name.
MOUNT_OUT = {
    "cone": (True, ("contracts",)),
    "non-cone, members/": (False, ("/*", "!/members/")),
    "non-cone, the member named": (False, ("/*", "!/members/{p}")),
    "non-cone, members/*": (False, ("/*", "!/members/*")),
}


def mount_out(root: Path, env: dict, rows: str, member: str) -> str:
    """Put the rules `rows` in force, and name the pattern the refusal must
    print: `members` in cone mode, the mount path itself otherwise (#612's
    review, F3)."""
    cone, rules = MOUNT_OUT[rows]
    sparse_set(root, env, *[rule.format(p=member) for rule in rules],
               cone=cone)
    assert outside(root, env, f"members/{member}"), "premise: out"
    return "members" if cone else f"members/{member}"


@needs_check_rules
@pytest.mark.parametrize("rows", MOUNT_OUT)
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_add_refuses_a_members_the_rules_leave_out_before_it_reads_the_member(
        family, holder, offline, tmp_path, rows, dry_run):
    """574/5 (p12b): `add` printed `mounting ...`, then `git submodule add`
    refused the mount as outside the sparse-checkout definition, and the
    unwind restored the holder. Now refused first, naming the pattern that
    brings the mount back: `git sparse-checkout add members` in cone mode,
    and the mount path itself, `members/<Project>`, under non-cone rules. A
    bare `members` does not win over a rule that names the member (`!/members/
    <P>`, `!/members/*`: it exits 0 and the verb was refused again with the
    same remedy, #612's review, F3). The printed command is typed as printed,
    and `add` then mounts the member. Nothing on stdout: not even the line
    that says the member is being read."""
    env = isolated(offline, tmp_path)
    pattern = mount_out(holder, env, rows, SPARE)
    before = add_state(holder, env)
    extra = ("--dry-run",) if dry_run else ()
    ran = add(holder, env, family["remotes"], *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = sparse_said(
        "add", [f"members/{SPARE}"], pattern)
    assert expected_line.fullmatch(line), line
    assert remedy == expected_remedy
    assert_add_as_it_was(holder, env, before)

    type_the_remedy(holder, env, ran.stderr)
    done = add(holder, env, family["remotes"])
    assert done.returncode == 0, done.stdout + done.stderr
    assert (holder / "members" / SPARE / "project.yaml").is_file()


@needs_check_rules
@pytest.mark.parametrize("rows", MOUNT_OUT)
@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_bump_and_remove_refuse_a_members_the_rules_leave_out_too(
        family, holder, offline, tmp_path, verb, rows):
    """The same helper covers `bump`'s staged paths, `members/<P>` and
    `family.yaml`, and `remove`'s: before it, `bump` checked the member out
    at `--to` and failed at `git add` of the gitlink, `remove` ran `deinit`
    and failed at `git rm`, each rolled back. Refused first, both runs, with
    the pattern of `mount_out`; typed as printed, the verb then runs."""
    env = isolated(offline, tmp_path)
    pattern = mount_out(holder, env, rows, MEMBER)
    # `remove` stages `.gitmodules`, the gitlink and `family.yaml`; only the
    # gitlink is out here, so it alone is named, as for `bump`.
    ran = assert_refused_alike(
        verb, family, holder, env,
        sparse_said(verb, [f"members/{MEMBER}"], pattern))
    type_the_remedy(holder, env, ran.stderr)
    done = run_verb(verb, family, holder, env)
    assert done.returncode == 0, done.stdout + done.stderr


@needs_check_rules
def test_the_cone_keeps_every_root_file_so_only_the_mount_is_refused(
        family, holder, offline, tmp_path):
    """MEASURED, as the docstring says: in cone mode git keeps every file at
    the root inside (`.gitmodules` and `family.yaml`), so a cone that leaves
    out `members/` is refused for the mount path ALONE and never for the two
    files; and a root file is never offered a pattern there."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, "contracts", cone=True)
    assert not outside(holder, env, GITMODULES)
    assert not outside(holder, env, "family.yaml")
    assert outside(holder, env, f"members/{OTHER}")
    ran = remove(holder, env, "--dry-run")
    line, _ = refusal(ran.stderr)
    assert ran.returncode == 2
    assert f"leaves out `members/{MEMBER}`, which" in line, line
    assert GITMODULES not in line, line
    assert "family.yaml" not in line, line


@needs_check_rules
def test_every_excluded_path_is_named_and_one_command_brings_them_all_back(
        family, holder, offline, tmp_path):
    """Non-cone rules can leave any of the three out: all three are named, in
    the order the verb stages them, and the one `git sparse-checkout add` the
    refusal prints, typed as printed, brings every one back."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, "/*", f"!/{GITMODULES}", "!/members/",
               "!/family.yaml")
    # `family.yaml` is what the tool opens first: a sparse checkout that
    # removed it from disk is `family-root-missing`, so, as for `.gitmodules`,
    # a hand put it back.
    put_back(holder, env, GITMODULES)
    put_back(holder, env, "family.yaml")
    before = add_state(holder, env)
    ran = add(holder, env, family["remotes"])
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = sparse_said(
        "add", [GITMODULES, f"members/{SPARE}", "family.yaml"],
        GITMODULES, f"members/{SPARE}", "family.yaml")
    assert expected_line.fullmatch(line), line
    assert remedy == expected_remedy
    assert_add_as_it_was(holder, env, before)
    type_the_remedy(holder, env, ran.stderr)
    assert not outside(holder, env, GITMODULES)
    assert not outside(holder, env, f"members/{SPARE}")
    assert not outside(holder, env, "family.yaml")
    done = add(holder, env, family["remotes"])
    assert done.returncode == 0, done.stdout + done.stderr


@needs_check_rules
@pytest.mark.parametrize("verb", VERBS)
def test_rules_that_keep_every_path_refuse_nothing(
        family, holder, offline, tmp_path, verb):
    """THE CONTROL for the sparse check: sparse checkout is ON, and keeps
    everything the verb stages, so the verb runs as it did."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, "/*")
    was = head_of(holder, env)
    ran = run_verb(verb, family, holder, env)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert raw(holder, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
        == was


@needs_check_rules
@pytest.mark.parametrize("verb", VERBS)
def test_a_sparse_checkout_that_was_disabled_refuses_nothing(
        family, holder, offline, tmp_path, verb):
    """THE GATE: `git sparse-checkout disable` turns `core.sparseCheckout` off
    and LEAVES `.git/info/sparse-checkout` as it was, and `check-rules`, asked
    bare, still reads it and says `members/<P>` is outside (the premise,
    measured). A holder that is no longer sparse must not be refused for
    rules git no longer applies: the verb runs."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, "/*", "!/members/")
    raw(holder, env, "sparse-checkout", "disable")
    assert raw(holder, env, "config", "--bool", "core.sparseCheckout"
               ).stdout.strip() == b"false"
    assert (holder / ".git" / "info" / "sparse-checkout").is_file()
    assert outside(holder, env, f"members/{MEMBER}"), (
        "premise: check-rules still reads the file the disable left")
    was = head_of(holder, env)
    ran = run_verb(verb, family, holder, env)
    assert ran.returncode == 0, ran.stdout + ran.stderr
    assert raw(holder, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
        == was


def test_rules_git_cannot_read_are_cannot_tell_and_refuse_nothing(
        family, holder, offline, tmp_path):
    """`core.sparseCheckout` on and no rules file: `git sparse-checkout
    check-rules` exits non-zero (`unable to load existing sparse-checkout
    patterns`), which is "cannot tell", not a refusal: the verb runs. The
    same road a git with NO `check-rules` takes (an unknown subcommand, exit
    129), asked for here without needing such a git."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "config", "core.sparseCheckout", "true")
    assert not (holder / ".git" / "info" / "sparse-checkout").exists()
    ran = add(holder, env, family["remotes"])
    assert ran.returncode == 0, ran.stdout + ran.stderr


@pytest.mark.skipif(sys.platform == "win32",
                    reason="the git that lacks `check-rules` is a `sh` "
                           "script put first on PATH, which Windows does not "
                           "run as `git`")
@needs_check_rules
def test_a_git_that_cannot_tell_refuses_nothing_and_the_late_failure_stays(
        family, holder, offline, tmp_path):
    """A GIT WITHOUT `check-rules`, made with a `git` first on PATH that says
    `unknown subcommand` (exit 129) to that one subcommand and runs the real
    git for everything else. `remove` in the issue's 571(d) state is NOT
    refused: it fails where it always failed, at its commit, and its
    rollback leaves the holder as it was. So a git that cannot tell costs
    nothing but the earliness."""
    env = isolated(offline, tmp_path)
    restored_by_hand(holder, env)
    real = shutil.which("git")
    assert real
    shim = tmp_path / "oldgit"
    shim.mkdir()
    (shim / "git").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "sparse-checkout" ] && [ "$2" = "check-rules" ]; then\n'
        "  echo \"error: unknown subcommand: \\`check-rules'\" >&2\n"
        "  exit 129\n"
        "fi\n"
        f"exec '{real}' \"$@\"\n", encoding="utf-8")
    (shim / "git").chmod((shim / "git").stat().st_mode | stat.S_IXUSR)
    old = {**env, "PATH": str(shim) + os.pathsep + env["PATH"]}
    before = state(holder, env)
    config = sorted(raw(holder, env, "config", "--local", "--list"
                        ).stdout.splitlines())
    ran = remove(holder, old)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert "family-sparse-excluded" not in ran.stderr
    assert "outside of your sparse-checkout definition" in ran.stderr
    # EVERY FACT BUT TWO. The config's keys and values are the same and their
    # order is not: the rollback puts the member's section back written LAST
    # (`PinRollback`); and the failed commit had already written the blobs it
    # staged, loose objects no rollback takes out of the store and nothing
    # refers to. The rest is as it was: HEAD, the index, `.gitmodules`,
    # `family.yaml`, the work tree and the member's checkout.
    kept = tuple(key for key in REMOVE_ORDER
                 if key not in (".git/config", "objects"))
    assert_as_it_was(holder, env, before, kept)
    assert sorted(raw(holder, env, "config", "--local", "--list"
                      ).stdout.splitlines()) == config


# --- a FILE named `members` -------------------------------------------------

FILE_LINE = (
    "REFUSED member-path-unaddable: git will not add the mount path "
    f"members/{SPARE}: `members` is {{kind}} file in the family root, not a "
    "directory, so nothing can be mounted under it, and `git submodule add` "
    "would fail at its mount (`Not a directory`) after the member was read. "
    "No git command that writes was run and nothing was written.")
FILE_REMEDY = (
    "Remediation: every member is mounted under members/, which must be a "
    "plain directory of the holder's own. Move the file aside, `{move} -- "
    "members <new name>`{commit}, and run the same command again.")


@pytest.mark.parametrize("tracked", [False, True],
                         ids=["untracked", "tracked"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_add_refuses_a_file_named_members_before_it_reads_the_member(
        family, empty_holder, offline, tmp_path, tracked, dry_run):
    """574/5 (p12a): with a FILE named `members`, `add` printed `mounting
    ...`, then `git submodule add` died cloning into it (`Not a directory`),
    after the member was read. Now refused first, with nothing on stdout, as
    `member-path-unaddable`, the code of a mount path git will not take. The
    move the remediation names is made as printed, a tracked file with `git
    mv` and the move committed, and `add` then mounts the member."""
    holder = empty_holder
    env = isolated(offline, tmp_path)
    (holder / "members").write_bytes(b"a file where the directory goes\n")
    if tracked:
        raw(holder, env, "add", "-f", "--", "members")
        raw(holder, env, "commit", "-q", "-m", "a file named members")
    before = add_state(holder, env)
    extra = ("--dry-run",) if dry_run else ()
    ran = add(holder, env, family["remotes"], *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    assert line == FILE_LINE.format(
        kind="a tracked" if tracked else "an untracked")
    assert remedy == FILE_REMEDY.format(
        move="git mv" if tracked else "mv",
        commit=(", and commit the move on its own first, since the add's own "
                f"commit names .gitmodules, members/{SPARE} and family.yaml "
                "alone" if tracked else ""))
    assert_add_as_it_was(holder, env, before)

    if tracked:
        raw(holder, env, "mv", "--", "members", "members-file")
        raw(holder, env, "commit", "-q", "-m", "move the file aside")
    else:
        (holder / "members").rename(holder / "members-file")
    done = add(holder, env, family["remotes"])
    assert done.returncode == 0, done.stdout + done.stderr
    assert (holder / "members" / SPARE / "project.yaml").is_file()
