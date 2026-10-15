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
from test_family import SPARE, family  # noqa: F401
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
#: What a verb must leave as it found it, and the three verbs, as the dry-run
#: tests spell them: the order of each comparison names the first fact that
#: moved, and `add`'s differs from `bump`'s and `remove`'s.
from test_family_dry_run import (
    BUMP_ORDER, REMOVE_ORDER, add, add_state, assert_add_as_it_was,
    assert_as_it_was, bump, isolated, remove, state,
)
from test_family_member_path import MEMBER, OTHER, older, raw

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
                         expected_stderr) -> None:
    """THE PROOF OF A REFUSAL BEFORE THE FIRST WRITE, under both runs: exit 2,
    the one paragraph `expected_stderr` (a compiled pattern for the REFUSED
    line, the remediation exactly) and nothing on stdout, so the member was
    not read; the holder as it was; and the dry run's words the real run's."""
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
    assert said[0] == said[1], "the two runs refuse in different words"


# --- an act git has unfinished ---------------------------------------------

#: `{kind: (what, the mark git keeps, how it is finished, how it is given
#: up, what the commit would do)}`, as the refusal says each. `{verb}` is the
#: verb that asked.
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
        "git rebase --abort",
        "git does not refuse that during a rebase, so the commit would land "
        "on the HEAD the rebase has detached, inside its sequence, where no "
        "branch can carry it to a pull request"),
    "revert": (
        "a revert", "REVERT_HEAD", "git revert --continue",
        "git revert --abort",
        "git does not refuse that during a revert, so the commit would be "
        "made inside the revert and end it as the revert's own"),
    "am": (
        "a `git am`", "rebase-apply", "git am --continue", "git am --abort",
        "git does not refuse that during a `git am`, so the commit would "
        "land on the branch, in the middle of the patches being applied"),
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
    remedy = ("Remediation: end it, whichever way suits the work in it: "
              f"finish it with `{finish}` once whatever stopped it is "
              f"resolved and staged, or give it up with `{abort}`. Then run "
              "the same command again.")
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


def begin(kind: str, root: Path, env: dict, tmp_path: Path) -> None:
    """Leave `root` in the middle of `kind`, with git, and check the mark git
    keeps for it is there: the premise of every test that calls this."""
    if kind == "merge":
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
    mark = OPERATIONS[kind][1]
    assert os.path.lexists(mark_of(root, env, mark)), f"premise: {mark}"


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
@pytest.mark.parametrize("verb", VERBS)
def test_each_verb_refuses_a_merge_in_progress_before_it_writes(
        family, holder, offline, tmp_path, verb, dry_run):
    """THE ISSUE'S PROBE (p07), for each verb: during a `--no-commit` merge
    every verb exited 2 at `git commit`, `fatal: cannot do a partial commit
    during a merge.`, after its first writes. Now `family-operation-in-
    progress`, before them: HEAD, the index, `family.yaml`, the work tree and
    the git config as they were, no member read, and the dry run's words the
    real run's. The real run and the dry run are each asked of the holder
    the merge left, which neither changes."""
    env = isolated(offline, tmp_path)
    begin("merge", holder, env, tmp_path)
    before = snapshot(verb, holder, env)
    manifest = (holder / "family.yaml").read_bytes()
    extra = ("--dry-run",) if dry_run else ()
    ran = run_verb(verb, family, holder, env, *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == "", ran.stdout
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = operation_said("merge", verb)
    assert expected_line.fullmatch(line), line
    assert remedy == expected_remedy
    assert "partial commit" in line and "after" in line
    assert (holder / "family.yaml").read_bytes() == manifest
    assert_untouched(verb, holder, env, before)
    assert os.path.lexists(mark_of(holder, env, "MERGE_HEAD"))


@pytest.mark.parametrize("kind, verb", [
    ("merge", "add"), ("merge", "bump"), ("merge", "remove"),
    ("cherry-pick", "add"), ("cherry-pick", "remove"),
    ("rebase", "bump"), ("rebase", "add"), ("revert", "remove"),
    ("revert", "bump"), ("am", "add"), ("am", "remove"),
])
def test_every_unfinished_act_is_named_and_refused_alike_in_both_runs(
        family, holder, offline, tmp_path, kind, verb):
    """A merge, a cherry-pick, a rebase, a revert and a `git am`, each
    stopped on a conflict by git: each named, with its own finish and its
    own give-up, by the real run and the dry run in the same words, the
    holder untouched. A rebase and an `am` were no failure at the commit at
    all (git does not refuse a partial commit there); the real run met a
    rebase as `family-holder-detached`, the dry run printed a plan."""
    env = isolated(offline, tmp_path)
    begin(kind, holder, env, tmp_path)
    assert_refused_alike(verb, family, holder, env, operation_said(kind, verb))


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


def restored_by_hand(root: Path, env: dict) -> None:
    """THE ISSUE'S STATE (571(d)): the rules leave `.gitmodules` out, the file
    is back on disk because a person put it there, and git's skip-worktree
    mark is CLEAR, so #407's check, which reads the mark, passes. Built with
    git's own `sparse-checkout set`, then the file written back as bytes and
    the mark taken off."""
    sparse_set(root, env, "/*", f"!/{GITMODULES}")
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
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_remove_refuses_a_gitmodules_the_rules_leave_out_before_deinit(
        family, holder, offline, tmp_path, dry_run):
    """THE ISSUE'S p06: sparse rules leave `.gitmodules` out, the file is put
    back by hand, git clears the mark, #407's check passes, and `remove` did
    `deinit` and `git rm` and failed at `git add` (`outside of your
    sparse-checkout definition`), then rolled back. Now refused before
    `deinit`: the mount, the registration in the git config and the index are
    untouched, which `REMOVE_ORDER` reads key by key. The pattern the
    remediation names is typed as printed, and `remove` then goes through."""
    env = isolated(offline, tmp_path)
    restored_by_hand(holder, env)
    before = state(holder, env)
    extra = ("--dry-run",) if dry_run else ()
    ran = remove(holder, env, *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = sparse_said(
        "remove", [GITMODULES], f"/{GITMODULES}")
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


@needs_check_rules
@pytest.mark.parametrize("cone", [False, True], ids=["non-cone", "cone"])
@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
def test_add_refuses_a_members_the_rules_leave_out_before_it_reads_the_member(
        family, holder, offline, tmp_path, cone, dry_run):
    """574/5 (p12b): `add` printed `mounting ...`, then `git submodule add`
    refused the mount as outside the sparse-checkout definition, and the
    unwind restored the holder. Now refused first, naming `git
    sparse-checkout add members`, which works in cone mode and in non-cone
    mode: it is typed as printed, and `add` then mounts the member. Nothing
    on stdout: not even the line that says the member is being read."""
    env = isolated(offline, tmp_path)
    if cone:
        sparse_set(holder, env, "contracts", cone=True)
    else:
        sparse_set(holder, env, "/*", "!/members/")
    assert outside(holder, env, f"members/{SPARE}"), "premise: out"
    before = add_state(holder, env)
    extra = ("--dry-run",) if dry_run else ()
    ran = add(holder, env, family["remotes"], *extra)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    line, remedy = refusal(ran.stderr)
    expected_line, expected_remedy = sparse_said(
        "add", [f"members/{SPARE}"], "members")
    assert expected_line.fullmatch(line), line
    assert remedy == expected_remedy
    assert_add_as_it_was(holder, env, before)

    type_the_remedy(holder, env, ran.stderr)
    done = add(holder, env, family["remotes"])
    assert done.returncode == 0, done.stdout + done.stderr
    assert (holder / "members" / SPARE / "project.yaml").is_file()


@needs_check_rules
@pytest.mark.parametrize("verb", ["bump", "remove"])
def test_bump_and_remove_refuse_a_members_the_rules_leave_out_too(
        family, holder, offline, tmp_path, verb):
    """The same helper covers `bump`'s staged paths, `members/<P>` and
    `family.yaml`, and `remove`'s: before it, `bump` checked the member out
    at `--to` and failed at `git add` of the gitlink, `remove` ran `deinit`
    and failed at `git rm`, each rolled back. Refused first, both runs."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, "/*", "!/members/")
    assert outside(holder, env, f"members/{MEMBER}"), "premise: out"
    # `remove` stages `.gitmodules`, the gitlink and `family.yaml`; only the
    # gitlink is out here, so it alone is named, as for `bump`.
    assert_refused_alike(verb, family, holder, env,
                         sparse_said(verb, [f"members/{MEMBER}"], "members"))


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
    assert GITMODULES not in line and "family.yaml" not in line, line


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
        f"/{GITMODULES}", "members", "/family.yaml")
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


def test_a_members_directory_is_not_refused_as_a_file(
        family, holder, offline, tmp_path):
    """THE CONTROL: `members` is the directory every holder has, and `add`
    mounts beside what is there."""
    env = isolated(offline, tmp_path)
    ran = add(holder, env, family["remotes"])
    assert ran.returncode == 0, ran.stdout + ran.stderr
