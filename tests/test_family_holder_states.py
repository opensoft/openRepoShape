# SPDX-License-Identifier: Apache-2.0
"""`add`, `bump` and `remove` meet five holder states #612's checks did not
model, and each refusal now fits the state it names (#684, from #612's
review lines on #459: E1, E2, E3, E5 and N4).

- **A bisect** (E2). `BISECT_LOG` is asked with the other marks, LAST, and
  the act is named with its own exit, `git bisect reset`, under both runs.
  The real run said `family-holder-detached`, whose `git switch -c` would
  branch from the commit under test; the dry run printed a plan.
- **A rebase directory git can read nothing of** (E5). An empty
  `rebase-merge/` was named a rebase with `git rebase --abort`, which fails
  there as `--continue` does; `git rebase --quit` is named, the exit that
  works. `rebase-apply/` with no `applying` (no `git am`) is its twin.
- **Non-cone sparse rules that hold no pattern** (E3). Every staged path is
  refused, as before, and the remedy names `git sparse-checkout disable`
  alone: the `git sparse-checkout add ...` it printed took every other file
  out of the work tree.
- **A merge conflicted in `family.yaml` itself** (N4). `yaml-unparsable`
  keeps its code and its line, and gains a remediation naming the merge
  and its exits; asked only once the parse has failed.
- **A `members` file HEAD holds and the work tree no longer does** (E1):
  the move #612's own remedy names, staged and not committed, or a removal
  staged; or the file deleted and the deletion not staged. `add` went
  through and its commit took `D members` into itself; now it is refused
  before the member is read. The unstaged deletion is taken out of the
  index with `git rm --cached` and the removal committed: the issue's `git
  mv` fails there (the premise, measured here).
- **A `family.yaml` holding a change HEAD does not** (#459's line from
  #571's review, on Brett Heap's word relayed by lane 5 on #473 at
  2026-10-16T13:56:50Z, "refuse a dirty `family.yaml`"). `add`, `bump` and
  `remove` commit the file as the work tree has it, so a comment line
  edited by hand went into their commit; each now refuses it, staged or
  not, and git's two ways out, typed as printed, let the command run.
  `member-path`'s remedy says to commit a row put back by hand, so it no
  longer leads into this refusal.

#612's review E4 (reftable) is NOT here: this host's git is 2.43, and
the issue asks for it to be measured on git 2.45 or later first.

THE PROOF IS #612's, with the helpers of `test_family_refuse_up_front.py`:
exit 2 and one REFUSED paragraph, nothing on stdout (no member was read),
the holder as it was under the real run and `--dry-run` alike; then the
remedy typed as printed, and the same command makes its one commit. Each
state is made with git itself where git can make it; a stale, empty rebase
directory is what a crash leaves, and is made with `mkdir`, as the issue's
probe made it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from conftest import run_script
#: The family fixture and its names, imported from the modules that own them.
from test_family import FAMILY, ORG, SPARE, family, family_module  # noqa: F401
from test_family_add_excludes import empty_holder  # noqa: F401
from test_family_add_refusals import holder, offline, refusal  # noqa: F401
from test_family_dry_run import add, add_state, assert_add_as_it_was, isolated
from test_family_member_path import GLOB, MEMBER, hand_edit, raw
#: #612's proof of a refusal before the first write, and its states.
from test_family_refuse_up_front import (
    NOTES, VERBS, assert_refused_alike, commit_file, head_of, mark_of,
    needs_check_rules, operation_said, outside, run_verb, sparse_said,
    sparse_set, type_the_remedy, work_branch,
)

MANIFEST = "family.yaml"


def act_said(what: str, mark: str, effect: str, verb: str,
             remedy: str) -> tuple:
    """`(the REFUSED line as a pattern, the remediation)` of
    `family-operation-in-progress` for an act `operation_said` does not
    list: the path git keeps `mark` at is the one part that varies."""
    line = re.compile(
        re.escape(f"REFUSED family-operation-in-progress: {what} is "
                  f"unfinished in the family root: git keeps {mark} at ")
        + r".+/" + re.escape(mark)
        + re.escape(f". `{verb}` makes its commit with `git commit -- "
                    f"<paths>`, and {effect}. No git command that writes "
                    "was run and nothing was written."))
    return line, remedy


def runs_after(verb: str, family, root: Path, env: dict) -> None:
    """The same command once the remedy is typed: exit 0, and ONE commit, a
    child of the HEAD it started from."""
    was = head_of(root, env)
    done = run_verb(verb, family, root, env)
    assert done.returncode == 0, done.stdout + done.stderr
    assert raw(root, env, "rev-parse", "HEAD~1").stdout.decode().strip() \
        == was


# --- a bisect (E2) ----------------------------------------------------------

BISECT_EFFECT = (
    "git does not refuse that during a bisect: once the bisect has checked "
    "out a commit to test, the commit would be made on it, on no branch, "
    "and `git bisect reset` would leave it behind")
BISECT_REMEDY = (
    "Remediation: end the bisect with `git bisect reset` once you have what "
    "it was for: it takes HEAD back to where the bisect started. Then run "
    "the same command again.")


def bisect_said(verb: str) -> tuple:
    return act_said("a bisect", "BISECT_LOG", BISECT_EFFECT, verb,
                    BISECT_REMEDY)


def bisecting(root: Path, env: dict, good: str | None = None) -> None:
    """THE ISSUE'S PROBE: `git bisect start`, `git bisect bad`, `git bisect
    good <root>` (or `good`), which checks out a commit to test and leaves
    HEAD detached there, the state the real run met as
    `family-holder-detached`. Each fact is a premise."""
    if good is None:
        good = raw(root, env, "rev-list", "--max-parents=0", "HEAD"
                   ).stdout.decode().split()[0]
    raw(root, env, "bisect", "start")
    raw(root, env, "bisect", "bad")
    raw(root, env, "bisect", "good", good)
    assert raw(root, env, "symbolic-ref", "-q", "HEAD",
               check=False).returncode != 0, "premise: HEAD is detached"
    assert os.path.lexists(mark_of(root, env, "BISECT_LOG")), "premise"


@pytest.mark.parametrize("verb", VERBS)
def test_a_bisect_is_named_with_its_own_exit_in_both_runs(
        family, holder, offline, tmp_path, verb):
    """E2: the real run said `family-holder-detached` and offered `git
    switch -c`, which branches from the commit under test, and the dry run
    printed a plan. Now `family-operation-in-progress` names the bisect and
    `git bisect reset`, in the same words under both runs, the holder
    untouched and `BISECT_LOG` still there. Typed as printed, the reset
    puts the holder back on its branch, and the verb runs."""
    env = isolated(offline, tmp_path)
    bisecting(holder, env)
    assert_refused_alike(verb, family, holder, env, bisect_said(verb),
                         mark="BISECT_LOG")
    raw(holder, env, "bisect", "reset")
    assert not os.path.lexists(mark_of(holder, env, "BISECT_LOG"))
    runs_after(verb, family, holder, env)


def test_what_the_bisect_refusal_says_the_commit_would_do_is_what_git_does(
        family, holder, offline, tmp_path):
    """`BISECT_EFFECT`, TIED TO GIT: the partial commit the verbs make is
    made at the commit under test (git does not refuse it), on no branch,
    and `git bisect reset` leaves it behind: no branch contains it."""
    env = isolated(offline, tmp_path)
    bisecting(holder, env)
    manifest = holder / MANIFEST
    manifest.write_bytes(manifest.read_bytes() + b"# a change\n")
    raw(holder, env, "commit", "-q", "-m", "THE VERB'S COMMIT", "--",
        f":(literal){MANIFEST}")
    made = head_of(holder, env)
    raw(holder, env, "bisect", "reset")
    assert raw(holder, env, "branch", "--contains", made).stdout == b""


def test_an_act_begun_inside_a_bisect_is_named_first_and_each_exit_works(
        family, holder, offline, tmp_path):
    """THE BISECT IS ASKED LAST. A cherry-pick stopped on a conflict at the
    commit under test leaves `CHERRY_PICK_HEAD` beside `BISECT_LOG`, and
    `git bisect reset` fails over it (`you need to resolve your current
    index first`, the premise, measured here). So the cherry-pick is named
    first, and its exit typed as printed works; the bisect is named next,
    and its exit works; and `add` then runs."""
    env = isolated(offline, tmp_path)
    work = work_branch(holder, env)
    commit_file(holder, env, NOTES, b"base\n", "base")
    good = head_of(holder, env)
    raw(holder, env, "switch", "-q", "-c", "side")
    commit_file(holder, env, NOTES, b"side\n", "side")
    raw(holder, env, "switch", "-q", work)
    for name, data in ((NOTES, b"main\n"), ("x1.txt", b"1\n"),
                       ("x2.txt", b"2\n")):
        commit_file(holder, env, name, data, name)
    bisecting(holder, env, good)
    assert raw(holder, env, "cherry-pick", "side",
               check=False).returncode != 0, "premise: it conflicts"
    stuck = raw(holder, env, "bisect", "reset", check=False)
    assert stuck.returncode != 0, "premise: the reset fails over it"
    assert b"resolve your current index first" in stuck.stderr
    assert_refused_alike("add", family, holder, env,
                         operation_said("cherry-pick", "add"),
                         mark="CHERRY_PICK_HEAD")
    raw(holder, env, "cherry-pick", "--abort")
    assert_refused_alike("add", family, holder, env, bisect_said("add"),
                         mark="BISECT_LOG")
    raw(holder, env, "bisect", "reset")
    runs_after("add", family, holder, env)


# --- a rebase directory git can read nothing of (E5) ------------------------

STALE_EFFECT = (
    "git does not refuse that, and the commit would land beside a `{mark}/` "
    "directory that holds no `head-name`, so git can read no rebase from it "
    "and `git rebase --continue` and `--abort` both fail there")
STALE_REMEDY = (
    "Remediation: `{mark}/` is what a rebase left behind, and it holds no "
    "`head-name`, so git can read no rebase from it and there is nothing to "
    "continue or give up: clear it without moving HEAD with `git rebase "
    "--quit`. Then run the same command again.")


@pytest.mark.parametrize("mark, verb", [
    ("rebase-merge", "add"), ("rebase-merge", "bump"),
    ("rebase-merge", "remove"), ("rebase-apply", "add")])
def test_an_empty_rebase_directory_is_named_with_the_exit_that_works(
        family, holder, offline, tmp_path, mark, verb):
    """E5 (and N5), THE ISSUE'S PROBE: `mkdir .git/rebase-merge`. It was
    refused as a rebase whose remedy named `git rebase --abort`, and that
    fails there (`could not read '.git/rebase-merge/head-name'`), as `git
    rebase --continue` does: both premises, measured here, the directory
    left as it was. Now named with `git rebase --quit`, under both runs;
    typed as printed, it takes the directory away, and the verb runs. An
    empty `rebase-apply/`, which holds no `applying` and so is no `git am`,
    is the same."""
    env = isolated(offline, tmp_path)
    mark_of(holder, env, mark).mkdir()
    for step in ("--abort", "--continue"):
        tried = raw(holder, env, "rebase", step, check=False)
        assert tried.returncode != 0, (step, tried.stderr)
        assert f"{mark}/head-name".encode() in tried.stderr, tried.stderr
        assert mark_of(holder, env, mark).is_dir()
    ran = assert_refused_alike(
        verb, family, holder, env,
        act_said("a rebase", mark, STALE_EFFECT.format(mark=mark), verb,
                 STALE_REMEDY.format(mark=mark)), mark=mark)
    assert "`git rebase --quit`" in ran.stderr
    raw(holder, env, "rebase", "--quit")
    assert not os.path.lexists(mark_of(holder, env, mark))
    runs_after(verb, family, holder, env)


# --- non-cone sparse rules that hold no pattern (E3) ------------------------

EMPTY_RULES_REMEDY = (
    "Remediation: the rules hold no pattern at all, so they leave out every "
    "path, and `git sparse-checkout add` would keep only the paths it is "
    "given and take every other file out of the work tree: bring them back "
    "with `git sparse-checkout disable`, which brings back every path the "
    "sparse checkout leaves out and leaves a copy already on disk as it is. "
    "Then run the same command again.")

#: What each verb stages, in the order its refusal names them.
STAGED = {"add": [".gitmodules", f"members/{SPARE}", MANIFEST],
          "bump": [f"members/{MEMBER}", MANIFEST],
          "remove": [".gitmodules", f"members/{MEMBER}", MANIFEST]}


def rules_emptied(root: Path, env: dict, init: bool = False) -> None:
    """THE ISSUE'S STATE: sparse checkout on, NON-CONE rules, and the rules
    file emptied by hand. `init` is the issue's own probe, `git
    sparse-checkout init --no-cone`, whose rules (`/*`, `!/*/`) take every
    directory but a member's checkout out of the work tree first; without
    it the rules are `/*`, which keeps everything, so nothing is out of the
    work tree before the file is emptied. Each fact is a premise: `list`
    prints no pattern, and the cone setting is off."""
    if init:
        raw(root, env, "sparse-checkout", "init", "--no-cone")
    else:
        sparse_set(root, env, "/*")
    mark_of(root, env, "info/sparse-checkout").write_bytes(b"")
    assert raw(root, env, "sparse-checkout", "list").stdout == b""
    assert raw(root, env, "config", "--bool", "core.sparseCheckoutCone",
               check=False).stdout.strip() in (b"", b"false")


@needs_check_rules
@pytest.mark.parametrize("verb, init", [
    ("add", True), ("add", False), ("bump", False), ("remove", False)],
    ids=["add-init", "add", "bump", "remove"])
def test_rules_that_hold_no_pattern_name_disable_alone(
        family, holder, offline, tmp_path, verb, init):
    """E3: every path the verb stages is outside (the premise, asked of git
    as the tool asks it), and it is refused as before, in both runs alike.
    The remedy names `git sparse-checkout disable` ALONE, and says why: the
    `git sparse-checkout add` of the paths it named took every other file
    out of the work tree (the next test). Typed as printed, `disable` lets
    the same command run."""
    env = isolated(offline, tmp_path)
    rules_emptied(holder, env, init)
    for path in STAGED[verb]:
        assert outside(holder, env, path), f"premise: {path} is outside"
    line, _ = sparse_said(verb, STAGED[verb])
    assert_refused_alike(verb, family, holder, env,
                         (line, EMPTY_RULES_REMEDY))
    raw(holder, env, "sparse-checkout", "disable")
    runs_after(verb, family, holder, env)


@needs_check_rules
def test_the_add_the_refusal_named_there_takes_every_other_file_away(
        family, holder, offline, tmp_path):
    """WHY `disable` ALONE, tied to git (#612's review E3): with the rules
    emptied, the `git sparse-checkout add` of the three paths `add`'s
    refusal named before #684 leaves the holder's top level with nothing
    but those, and `.git`; `disable`, the exit named now, brings every
    entry back."""
    env = isolated(offline, tmp_path)
    rules_emptied(holder, env)
    before = sorted(os.listdir(holder))
    raw(holder, env, "sparse-checkout", "add", *STAGED["add"])
    assert sorted(os.listdir(holder)) == [
        ".git", ".gitmodules", MANIFEST, "members"], before
    assert len(before) > 4, before
    raw(holder, env, "sparse-checkout", "disable")
    assert sorted(os.listdir(holder)) == before


@needs_check_rules
def test_a_cone_of_no_directories_keeps_its_add_remedy(
        family, holder, offline, tmp_path):
    """ONLY NON-CONE RULES ARE ASKED. In cone mode `git sparse-checkout
    list` names the cone's directories, and prints nothing for a cone of
    none (`set --cone` alone, the premise), whose root files are inside:
    there `git sparse-checkout add members` brings the mount back, and it
    is still named. Typed as printed, the verb runs."""
    env = isolated(offline, tmp_path)
    sparse_set(holder, env, cone=True)
    assert raw(holder, env, "sparse-checkout", "list").stdout == b""
    ran = assert_refused_alike(
        "remove", family, holder, env,
        sparse_said("remove", [f"members/{MEMBER}"], "members"))
    type_the_remedy(holder, env, ran.stderr)
    runs_after("remove", family, holder, env)


# --- a merge conflicted in family.yaml (N4) ---------------------------------

def conflicted_manifest(root: Path, env: dict) -> int:
    """THE ISSUE'S STATE (#612's review N4): two branches that change
    `family.yaml` in the same place, merged, so `git merge` stops on
    `CONFLICT (content): Merge conflict in family.yaml` and keeps
    `MERGE_HEAD` (premises). Returns the number of the line holding git's
    `<<<<<<<`, the one the reader stops at."""
    work = work_branch(root, env)
    text = (root / MANIFEST).read_bytes()
    raw(root, env, "switch", "-q", "-c", "side")
    commit_file(root, env, MANIFEST, text + b"# side\n", "side")
    raw(root, env, "switch", "-q", work)
    commit_file(root, env, MANIFEST, text + b"# work\n", "work")
    merged = raw(root, env, "merge", "side", check=False)
    assert merged.returncode != 0, merged.stdout
    assert b"Merge conflict in family.yaml" in merged.stdout, merged.stdout
    lines = (root / MANIFEST).read_bytes().split(b"\n")
    return next(number for number, line in enumerate(lines, 1)
                if line.startswith(b"<<<<<<<"))


def unparsable_line(root: Path, at: int) -> str:
    return (f"REFUSED yaml-unparsable: {root.resolve() / MANIFEST}: line "
            f"{at}: merge keys are not supported")


@pytest.mark.parametrize("verb", VERBS)
def test_a_merge_conflicted_in_family_yaml_is_named_as_a_merge(
        family, holder, offline, tmp_path, verb):
    """N4: every verb parses `family.yaml` first, so the commonest holder
    merge conflict said only `yaml-unparsable ... merge keys are not
    supported`, with no remediation. The refusal keeps its code and that
    line, in both runs alike, and gains a remediation that names the merge,
    where git keeps it, and its two exits; the holder is untouched. Typed as
    printed, `git merge --abort` lets the same command run."""
    env = isolated(offline, tmp_path)
    at = conflicted_manifest(holder, env)
    where = (holder.resolve() / ".git" / "MERGE_HEAD").as_posix()
    remedy = (
        f"Remediation: a merge is unfinished in the family root: git keeps "
        f"MERGE_HEAD at {where}, and where it left family.yaml conflicted, "
        "the reader cannot parse the lines git marks the conflict with "
        "(`<<<<<<<` reads as a YAML merge key). End it, whichever way suits "
        "the work in it: finish it with `git commit` once whatever stopped "
        "it is resolved and staged, or give it up with `git merge --abort`. "
        "Then run the same command again.")
    line = re.compile(re.escape(unparsable_line(holder, at)))
    assert_refused_alike(verb, family, holder, env, (line, remedy),
                         mark="MERGE_HEAD")
    raw(holder, env, "merge", "--abort")
    runs_after(verb, family, holder, env)


def test_an_unparsable_family_yaml_with_no_act_in_progress_is_as_before(
        family, holder, offline, tmp_path):
    """THE CONTROL: the same `<<<<<<<` line put there by hand, with no act
    in progress, is `yaml-unparsable` alone, one line and no remediation,
    as before #684."""
    env = isolated(offline, tmp_path)
    manifest = holder / MANIFEST
    text = manifest.read_bytes()
    manifest.write_bytes(text + b"<<<<<<< HEAD\n")
    at = text.count(b"\n") + 1
    for extra in ((), ("--dry-run",)):
        ran = run_verb("add", family, holder, env, *extra)
        assert ran.returncode == 2, ran.stdout + ran.stderr
        assert ran.stdout == ""
        assert ran.stderr == unparsable_line(holder, at) + "\n", ran.stderr


def test_a_family_yaml_outside_any_repository_keeps_its_refusal(
        offline, tmp_path):
    """THE FALLBACK IS A REMEDIATION AND NOTHING ELSE: where git cannot
    answer (no repository here, `GIT_CEILING_DIRECTORIES` stopping its
    search, the premise), the refusal stays `yaml-unparsable`, one line,
    exit 2, never a failed git command of its own."""
    env = {**isolated(offline, tmp_path),
           "GIT_CEILING_DIRECTORIES": str(tmp_path)}
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / MANIFEST).write_bytes(b"kind: family-manifest\n<<<<<<< HEAD\n")
    assert raw(plain, env, "rev-parse", "--git-dir",
               check=False).returncode != 0, "premise: no repository"
    ran = run_script(FAMILY, "add", "--family-root", str(plain), "--member",
                     f"{ORG}/{SPARE}", env=env)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stderr == unparsable_line(plain, 2) + "\n", ran.stderr


# --- a members file HEAD holds and the work tree no longer does (E1) --------

MOVED_LINE = (
    "REFUSED member-path-unaddable: git would add the mount path "
    f"members/{SPARE} and take `members` out of the holder with it: "
    "`members` is a file HEAD holds and the index no longer does, a move or "
    "a removal staged and not committed, and the add's commit, putting a "
    "directory where the file was, would take that deletion into itself (`D "
    "members`) and leave any new name staged alone. No git command that "
    "writes was run and nothing was written.")
MOVED_REMEDY = (
    "Remediation: every member is mounted under members/, which must be a "
    "plain directory of the holder's own. Commit that change on its own "
    "first (`git commit`), since the add's own commit names .gitmodules, "
    f"members/{SPARE} and family.yaml alone, and run the same command "
    "again.")
DELETED_LINE = (
    "REFUSED member-path-unaddable: git would add the mount path "
    f"members/{SPARE} and take `members` out of the holder with it: "
    "`members` is a file HEAD and the index hold and the work tree no "
    "longer does, its deletion not staged, and the add's mount, putting a "
    "directory where the file was, would take it out of the index, and its "
    "commit would take that deletion into itself (`D members`). No git "
    "command that writes was run and nothing was written.")
DELETED_REMEDY = (
    "Remediation: every member is mounted under members/, which must be a "
    "plain directory of the holder's own. Take the file out of the index, "
    "which touches no file (`git rm --cached -- members`), and commit the "
    "removal on its own first (`git commit`), since the add's own commit "
    f"names .gitmodules, members/{SPARE} and family.yaml alone, and run the "
    "same command again.")

#: `{id: the git command that leaves the tracked file staged away}`: the
#: move #612's remedy names, and the file's removal.
STAGED_AWAY = {"git mv": ("mv", "--", "members", "members-file"),
               "git rm": ("rm", "-q", "--", "members")}

#: What is at `members` once the file is deleted and the deletion is not
#: staged: nothing, or a directory a hand made there with a file of the
#: person's in it, which `git checkout -- members` would take away.
LEFT_THERE = {"nothing": None, "a-directory": "NOTES.txt"}


def a_members_file(root: Path, env: dict) -> None:
    """A FILE named `members`, committed: what `_members_is_a_file` refuses
    while it is on disk."""
    (root / "members").write_bytes(b"a file where the directory goes\n")
    raw(root, env, "add", "-f", "--", "members")
    raw(root, env, "commit", "-q", "-m", "a file named members")


def add_refused(family, root: Path, env: dict, dry_run: bool, line: str,
                remedy: str) -> None:
    """`add`, or its dry run, refused with `line` and `remedy` before the
    member is read: nothing on stdout, and the holder as it was."""
    before = add_state(root, env)
    ran = add(root, env, family["remotes"],
              *(("--dry-run",) if dry_run else ()))
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert ran.stdout == ""
    assert refusal(ran.stderr) == (line, remedy)
    assert_add_as_it_was(root, env, before)


def adds_its_own_three_paths(family, root: Path, env: dict) -> None:
    """`add` once the remedy is typed: exit 0 and a commit of `.gitmodules`,
    `family.yaml` and the mount, and of nothing else (no `D members`)."""
    done = add(root, env, family["remotes"])
    assert done.returncode == 0, done.stdout + done.stderr
    shown = raw(root, env, "show", "--name-status", "--format=", "HEAD"
                ).stdout.decode().split("\n")
    assert sorted(entry.split("\t")[1] for entry in shown if entry) == [
        ".gitmodules", MANIFEST, f"members/{SPARE}"], shown


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
@pytest.mark.parametrize("change", STAGED_AWAY.values(), ids=STAGED_AWAY)
def test_add_refuses_a_members_file_whose_move_is_staged_not_committed(
        family, empty_holder, offline, tmp_path, change, dry_run):
    """E1: a tracked `members` FILE moved aside with #612's own remedy, `git
    mv -- members <new name>`, and not committed, or removed with `git rm`:
    nothing is at `members` on disk or in the index (premises), `add` went
    through, and its commit took `D members` into itself beside the mount,
    leaving the new name staged alone. Now `member-path-unaddable`, nothing
    on stdout, the holder as it was. The remedy typed as printed, `git
    commit`, and `add` then makes a commit of its own three paths alone,
    and leaves nothing staged."""
    holder = empty_holder
    env = isolated(offline, tmp_path)
    a_members_file(holder, env)
    raw(holder, env, *change)
    assert not os.path.lexists(holder / "members"), "premise: not on disk"
    assert b"\tmembers\0" not in raw(holder, env, "ls-files", "-s", "-z"
                                     ).stdout, "premise: not in the index"
    add_refused(family, holder, env, dry_run, MOVED_LINE, MOVED_REMEDY)

    raw(holder, env, "commit", "-q", "-m", "the change, on its own")
    adds_its_own_three_paths(family, holder, env)
    assert raw(holder, env, "status", "--porcelain").stdout == b""


@pytest.mark.parametrize("dry_run", [False, True], ids=["real", "dry-run"])
@pytest.mark.parametrize("left", LEFT_THERE.values(), ids=LEFT_THERE)
def test_add_refuses_a_members_file_deleted_and_the_deletion_not_staged(
        family, empty_holder, offline, tmp_path, left, dry_run):
    """E1's OTHER HALF: the tracked `members` file deleted from disk, the
    deletion not staged, and nothing at `members` but, it may be, a
    directory a hand made there. The index still holds the file, and the
    `git mv` the issue proposed fails there, exit 128, changing nothing
    (premises, measured here). `add` went through and its commit took `D
    members`; now `member-path-unaddable`, nothing on stdout, the holder as
    it was. Typed as printed, `git rm --cached -- members` and the commit
    of the removal, `add` makes its commit of its own three paths alone,
    and the person's directory and the file in it are still there."""
    holder = empty_holder
    env = isolated(offline, tmp_path)
    a_members_file(holder, env)
    (holder / "members").unlink()
    if left is not None:
        (holder / "members").mkdir()
        (holder / "members" / left).write_bytes(b"the person's own\n")
    assert b"\tmembers\0" in raw(holder, env, "ls-files", "-s", "-z"
                                 ).stdout, "premise: the index holds it"
    status = raw(holder, env, "status", "--porcelain").stdout
    moved = raw(holder, env, "mv", "--", "members", "members-file",
                check=False)
    assert moved.returncode == 128, moved.stderr
    assert raw(holder, env, "status", "--porcelain").stdout == status
    add_refused(family, holder, env, dry_run, DELETED_LINE, DELETED_REMEDY)

    raw(holder, env, "rm", "-q", "--cached", "--", "members")
    raw(holder, env, "commit", "-q", "-m", "the removal, on its own")
    adds_its_own_three_paths(family, holder, env)
    if left is None:
        assert raw(holder, env, "status", "--porcelain").stdout == b""
    else:
        assert (holder / "members" / left).read_bytes() == \
            b"the person's own\n"
        assert raw(holder, env, "status", "--porcelain").stdout == (
            f"?? members/{left}\n".encode())


# --- a family.yaml holding a change HEAD does not (#459's line 66) ----------

#: The line's own example, a hand edit outside `members:`: a comment line,
#: put first in the file, where no verb's rewrite of `members:` reaches.
COMMENT = b"# a comment line, edited by hand\n"

#: What the refusal says of each way the file holds such a change.
SAID_UNSTAGED = ("git lists the work tree's copy as modified, a change "
                 "nobody has staged")
SAID_STAGED = "a change to it is staged and not committed"
SAID_UNMERGED = "it is unmerged in the index"
SAID_DELETION = "its deletion is staged, so the index holds no copy"

UNCOMMITTED_REMEDY = (
    "Remediation: which change to keep is a person's to say. To keep it, "
    "commit it on its own first, `git commit -- family.yaml`; to drop it, "
    "put back HEAD's copy, in the index and the work tree, `git checkout "
    "HEAD -- family.yaml`. Then run the same command again.")

#: The remedy's two ways out, as printed.
KEEP = ("commit", "-q", "-m", "the hand edit, on its own", "--", MANIFEST)
DROP = ("checkout", "HEAD", "--", MANIFEST)


def uncommitted_said(verb: str, *said: str) -> tuple:
    """`(the REFUSED line as a pattern, the remediation)` of
    `family-manifest-uncommitted` for `verb`, saying each of `said`."""
    line = (
        "REFUSED family-manifest-uncommitted: family.yaml holds a change "
        f"HEAD does not: {', and '.join(said)}. `{verb}` rewrites "
        "family.yaml as the work tree has it and commits it, so that change "
        "would go into the command's commit beside its own. No git command "
        "that writes was run and nothing was written.")
    return re.compile(re.escape(line)), UNCOMMITTED_REMEDY


def commented(root: Path, comment: bytes = COMMENT) -> None:
    """`comment` written first in `family.yaml` by hand, not staged."""
    manifest = root / MANIFEST
    manifest.write_bytes(comment + manifest.read_bytes())


@pytest.mark.parametrize("verb", VERBS)
def test_an_unstaged_hand_edit_to_family_yaml_is_refused_in_both_runs(
        family, holder, offline, tmp_path, verb):
    """THE LINE'S CASE: a comment line edited into `family.yaml` by hand
    and never staged went into the verb's commit beside its own row. Each
    verb now refuses it, in both runs alike, nothing on stdout, the holder
    as it was and the edit still in the work tree. Typed as printed, `git
    commit -- family.yaml` commits the edit on its own, and the verb then
    makes its one commit on top: the comment is the person's commit's, and
    the verb's commit leaves it as it was."""
    env = isolated(offline, tmp_path)
    commented(holder)
    assert_refused_alike(verb, family, holder, env,
                         uncommitted_said(verb, SAID_UNSTAGED))
    assert (holder / MANIFEST).read_bytes().startswith(COMMENT)
    raw(holder, env, *KEEP)
    runs_after(verb, family, holder, env)
    for commit in ("HEAD~1", "HEAD"):
        assert raw(holder, env, "show", f"{commit}:{MANIFEST}"
                   ).stdout.startswith(COMMENT), commit


def staged(root: Path, env: dict) -> None:
    """The comment, staged and not committed."""
    commented(root)
    raw(root, env, "add", "--", MANIFEST)


def staged_then_edited(root: Path, env: dict) -> None:
    """The comment staged, and a second one written after it, not staged."""
    staged(root, env)
    commented(root, b"# and another\n")


def deletion_staged(root: Path, env: dict) -> None:
    """`git rm --cached -- family.yaml`: the copy on disk is HEAD's, and the
    index holds none."""
    raw(root, env, "rm", "-q", "--cached", "--", MANIFEST)


def unmerged(root: Path, env: dict) -> None:
    """`family.yaml` unmerged with NO ACT in progress, as a `git stash pop`
    that conflicted leaves it (git keeps no `MERGE_HEAD` for it, the
    premise), resolved in the work tree by hand, both lines kept, and not
    staged."""
    commented(root, b"# stashed\n")
    raw(root, env, "stash", "-q")
    commented(root, b"# committed\n")
    raw(root, env, "commit", "-q", "-m", "a comment", "--", MANIFEST)
    popped = raw(root, env, "stash", "pop", check=False)
    assert popped.returncode != 0, popped.stdout
    assert not os.path.lexists(mark_of(root, env, "MERGE_HEAD")), "premise"
    (root / MANIFEST).write_bytes(
        b"# stashed\n" + raw(root, env, "show", f"HEAD:{MANIFEST}").stdout)


#: `{id: (how the holder gets the change, what the refusal says of it, the
#: way out typed)}`.
STATES = {
    "staged": (staged, (SAID_STAGED,), DROP),
    "staged-then-edited": (staged_then_edited,
                           (SAID_STAGED, SAID_UNSTAGED), KEEP),
    "deletion-staged": (deletion_staged, (SAID_DELETION,), DROP),
    "unmerged": (unmerged, (SAID_UNMERGED,), KEEP),
}


@pytest.mark.parametrize("set_up, said, typed", STATES.values(), ids=STATES)
def test_a_change_to_family_yaml_in_the_index_is_refused_too(
        family, holder, offline, tmp_path, set_up, said, typed):
    """A CHANGE STAGED AND NOT COMMITTED IS REFUSED AS WELL, since the
    commit takes the work tree's copy all the same: staged, staged and then
    edited again, a deletion staged over HEAD's own copy, and a copy left
    unmerged with no act in progress. `remove` refuses each in both runs
    alike, saying which it is, with the holder as it was; the way out typed
    as printed lets it run."""
    env = isolated(offline, tmp_path)
    set_up(holder, env)
    assert_refused_alike("remove", family, holder, env,
                         uncommitted_said("remove", *said))
    raw(holder, env, *typed)
    runs_after("remove", family, holder, env)


def test_a_row_put_back_as_member_path_says_is_committed_and_the_verb_runs(
        family, holder, offline, tmp_path):
    """THE REMEDY THAT EDITS `family.yaml` NO LONGER LEADS INTO THIS
    REFUSAL. A `path:` edited by hand AND COMMITTED is `member-path`'s,
    whose remedy now says to commit the row put back. Typed so, the verb
    runs; put back and not committed, it is refused as uncommitted."""
    env = isolated(offline, tmp_path)
    good = (holder / MANIFEST).read_bytes()
    hand_edit(holder, MEMBER, GLOB)
    raw(holder, env, "commit", "-q", "-m", "a hand edit", "--", MANIFEST)
    ran = run_verb("remove", family, holder, env)
    assert ran.returncode == 2, ran.stdout + ran.stderr
    assert refusal(ran.stderr)[1] == (
        "Remediation: this tool writes that field itself, so a different "
        f"value is a hand edit. Put `path: members/{MEMBER}` back in "
        "family.yaml and commit that, or `git checkout -- family.yaml` if "
        "the edit is not committed, then run the same command again.")
    (holder / MANIFEST).write_bytes(good)
    assert_refused_alike("remove", family, holder, env,
                         uncommitted_said("remove", SAID_UNSTAGED))
    raw(holder, env, "commit", "-q", "-m", "the row put back", "--",
        MANIFEST)
    runs_after("remove", family, holder, env)
