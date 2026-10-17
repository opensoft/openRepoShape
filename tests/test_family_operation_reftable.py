# SPDX-License-Identifier: Apache-2.0
"""A cherry-pick or a revert stopped in a holder whose refs are a REFTABLE is
refused as one on the files backend is (#684, #612's review E4).

THE PROBE, lane 5's (#684 issuecomment-6237529261, the full result on #764),
on git 2.47.1 in a repository made by `git init --ref-format=reftable`: a
stopped cherry-pick and a stopped revert keep `CHERRY_PICK_HEAD` and
`REVERT_HEAD` in the REF STORE, and no file in `.git`; `MERGE_HEAD`,
`rebase-merge/` and `sequencer/todo` stay files. `_operation_in_progress`
asked for files alone, so `add`, `bump` and `remove` found nothing in
progress there and went on to the commit `family-operation-in-progress` is
there to keep them from.

THE RULE NOW. Where neither file is there, each of the two is asked of the
ref store too, by its EXACT name (`git show-ref --exists`, git 2.43 and
later): exit 0 is held and 2 is not; 129 is a git before 2.43, which cannot
open a reftable at all, so its holder's refs are files; any other exit is
git's own failure, printed as a failed git command, exit 2, before the first
write. The refusal says git keeps the mark `in its ref store, not as a
file`, with the same exit; a mark that is a file is named at its path, as
before. `git rev-parse -q --verify` is NOT the ask: it resolves a branch or
a tag of that name too.

A GIT BEFORE 2.45 MAKES NO REFTABLE: `git init --ref-format=reftable` says
`unknown option` on git 2.43, the git these tests were written on, and CI's
git, 2.55, makes one. So the refusal under both runs is held on any git by a
STAND-IN: a `git` first on PATH that answers `git show-ref --exists <name>`
as the probe says a reftable answers (exit 0 for a mark its store holds),
with the mark's file moved out of the git directory into that store, as a
reftable keeps none, and runs the real git for everything else. It logs the
directory each ask runs in, which must be the holder's. The same stand-in
answers as a git before 2.43 does (exit 129, `unknown option`, measured on
git 2.40.4) and as a git that cannot read its ref store would (exit 1 and
128). The stand-in is a `sh` script, so those rows skip on Windows. The
REAL reftable rows build a repository with `git init --ref-format=reftable`
and skip, saying why, where git cannot make one. The exact-name rows and
the order rows run on every git.
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

#: The family fixture and its names, imported from the modules that own them.
from test_family import family, family_module  # noqa: F401
from test_family_add_refusals import holder, offline  # noqa: F401
from test_family_dry_run import isolated
from test_family_holder_states import runs_after, unparsable_line
from test_family_member_path import raw, recorded
#: #612's proof of a refusal before the first write, and its states.
from test_family_refuse_up_front import (
    NOTES, OPERATIONS, VERBS, assert_refused_alike, assert_untouched, begin,
    commit_file, conflicting_history, mark_of, operation_said, run_verb,
    snapshot, work_branch,
)

MANIFEST = "family.yaml"
#: Where the refusal says git keeps a mark the ref store holds and no file
#: does (`family.py`'s `IN_THE_REF_STORE`).
HELD = "in its ref store, not as a file"
#: The two marks a reftable keeps as refs (`family.py`'s `REF_STORE_MARKS`).
REFS = ("CHERRY_PICK_HEAD", "REVERT_HEAD")


def reftable_available() -> bool:
    """Can this machine's git make a reftable repository? Asked of git, in a
    directory of its own: `git init --ref-format=reftable` (git 2.45 and
    later; git 2.43 says `unknown option`, exit 129), then `git rev-parse
    --show-ref-format`, which git 2.43 echoes back as it was given."""
    with tempfile.TemporaryDirectory() as scratch:
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
        made = subprocess.run(
            ["git", "init", "-q", "--ref-format=reftable", scratch],
            env=env, capture_output=True, check=False)
        if made.returncode != 0:
            return False
        said = subprocess.run(["git", "rev-parse", "--show-ref-format"],
                              cwd=scratch, env=env, capture_output=True,
                              check=False)
        return said.returncode == 0 and said.stdout.strip() == b"reftable"


needs_reftable = pytest.mark.skipif(
    not reftable_available(),
    reason="this git cannot make a reftable repository (`git init "
           "--ref-format=reftable` needs git 2.45 or later); the stand-in "
           "rows hold the refusal in its place, but not on Windows, where "
           "they skip too")

needs_sh = pytest.mark.skipif(
    sys.platform == "win32",
    reason="the stand-in git is a `sh` script put first on PATH, which "
           "Windows does not run as `git`")


# --- the stand-in -----------------------------------------------------------

def stand_in(tmp_path: Path, env: dict, answer: str) -> tuple[dict, Path]:
    """`env` with a `git` first on PATH that answers `git show-ref --exists
    <name>` with the `sh` lines `answer` (`$3` is the name), and runs the
    real git for everything else, an `answer` that does not exit included;
    and the file it logs each name so asked to, one a line. The directory
    each ask runs in goes to `asked_where(log)`."""
    real = shutil.which("git")
    assert real, "premise: git is on PATH"
    shim = tmp_path / "stand-in"
    shim.mkdir()
    log = tmp_path / "show-ref.log"
    (shim / "git").write_text(
        "#!/bin/sh\n"
        'if [ "$1" = show-ref ] && [ "$2" = --exists ] && [ "$#" = 3 ]; then\n'
        f"  printf '%s\\n' \"$3\" >> '{log.as_posix()}'\n"
        f"  pwd -P >> '{asked_where(log).as_posix()}'\n"
        f"{answer}"
        "fi\n"
        f"exec '{real}' \"$@\"\n", encoding="utf-8")
    (shim / "git").chmod((shim / "git").stat().st_mode | stat.S_IXUSR)
    return {**env, "PATH": str(shim) + os.pathsep + env["PATH"]}, log


def asked(log: Path) -> list[str]:
    """The names the stand-in was asked, in order; none where it never was."""
    return log.read_text(encoding="utf-8").split() if log.exists() else []


def asked_where(log: Path) -> Path:
    """Where the stand-in logs the directory each ask runs in (`pwd -P`)."""
    return log.with_name("show-ref-dirs.log")


def asked_in(log: Path) -> set[str]:
    """The directories the stand-in was asked in. It must be the holder's
    alone: `_in_ref_store` asks the holder's own ref store, and an ask made
    in any other directory passed every row on git 2.43 (#846's review,
    M10, which asked in the process's working directory)."""
    where = asked_where(log)
    if not where.exists():
        return set()
    return set(where.read_text(encoding="utf-8").splitlines())


def a_reftable_of(holder: Path, env: dict, mark: str,
                  tmp_path: Path) -> tuple[dict, Path]:
    """THE STAND-IN FOR A REFTABLE: `mark`'s file moved out of the holder's
    git directory into the stand-in's store, as a reftable keeps none (the
    premise, asked as `_git_paths` asks it), and a `git` that answers `git
    show-ref --exists` with 0 for a name that store holds and runs the real
    git, which answers 2, for any other."""
    store = tmp_path / "ref-store"
    store.mkdir()
    mark_of(holder, env, mark).rename(store / mark)
    assert not os.path.lexists(mark_of(holder, env, mark)), "premise: no file"
    return stand_in(tmp_path, env,
                    f"  [ -e '{store.as_posix()}/'\"$3\" ] && exit 0\n")


def held_said(kind: str, verb: str) -> tuple:
    """`(the REFUSED line as a pattern, the remediation)` for `kind` held in
    the ref store, asked by `verb`: the line says where git keeps the mark
    and nothing else changes, the remediation included."""
    what, mark, _, _, effect = OPERATIONS[kind]
    line = re.compile(re.escape(
        f"REFUSED family-operation-in-progress: {what} is unfinished in the "
        f"family root: git keeps {mark} {HELD}. `{verb}` makes its commit "
        f"with `git commit -- <paths>`, and {effect.format(verb=verb)}. No "
        "git command that writes was run and nothing was written."))
    return line, operation_said(kind, verb)[1]


# --- a mark the ref store holds (the stand-in) ------------------------------

@needs_sh
@pytest.mark.parametrize("kind, verb", [
    ("cherry-pick", "add"), ("cherry-pick", "bump"),
    ("revert", "remove"), ("revert", "add")])
def test_a_mark_the_ref_store_holds_and_no_file_does_is_refused_alike(
        family, holder, offline, tmp_path, kind, verb):
    """E4, BY THE STAND-IN: a cherry-pick or a revert stopped on a conflict
    by git, its mark then held as a reftable holds it, in the ref store and
    in no file. The file check alone found nothing, and the verb went on to
    its commit. Now it is refused under both runs in the same words, the
    line saying git keeps the mark in its ref store and the remediation the
    act's own, as on the files backend; the holder is untouched, and the
    stand-in was asked for the mark once a run."""
    env = isolated(offline, tmp_path)
    begin(kind, holder, env, tmp_path)
    mark = OPERATIONS[kind][1]
    held, log = a_reftable_of(holder, env, mark, tmp_path)
    assert_refused_alike(verb, family, holder, held, held_said(kind, verb))
    assert asked(log).count(mark) == 2, asked(log)
    assert asked_in(log) == {str(holder.resolve())}, asked_in(log)


@needs_sh
def test_a_cherry_pick_conflicted_in_family_yaml_names_the_ref_store(
        family, holder, offline, tmp_path):
    """THE SECOND CALLER, `_unparsable_in_an_act` (#684's N4): a cherry-pick
    that conflicted in `family.yaml` itself leaves a manifest the reader
    cannot parse (`<<<<<<<` reads as a YAML merge key), and its mark held in
    the ref store. `yaml-unparsable` keeps its code and its line, and its
    remediation names the cherry-pick, says git keeps its mark in its ref
    store, and gives its exits, under both runs alike."""
    env = isolated(offline, tmp_path)
    work = work_branch(holder, env)
    text = (holder / MANIFEST).read_bytes()
    raw(holder, env, "switch", "-q", "-c", "side")
    commit_file(holder, env, MANIFEST, text + b"# side\n", "side")
    raw(holder, env, "switch", "-q", work)
    commit_file(holder, env, MANIFEST, text + b"# work\n", "work")
    picked = raw(holder, env, "cherry-pick", "side", check=False)
    assert picked.returncode != 0, "premise: the cherry-pick conflicts"
    lines = (holder / MANIFEST).read_bytes().split(b"\n")
    at = next(number for number, line in enumerate(lines, 1)
              if line.startswith(b"<<<<<<<"))
    held, log = a_reftable_of(holder, env, "CHERRY_PICK_HEAD", tmp_path)
    remedy = (
        "Remediation: a cherry-pick is unfinished in the family root: git "
        f"keeps CHERRY_PICK_HEAD {HELD}, and where it left family.yaml "
        "conflicted, the reader cannot parse the lines git marks the "
        "conflict with (`<<<<<<<` reads as a YAML merge key). End it, "
        "whichever way suits the work in it: finish it with `git "
        "cherry-pick --continue` once whatever stopped it is resolved and "
        "staged, or give it up with `git cherry-pick --abort`. Then run the "
        "same command again.")
    line = re.compile(re.escape(unparsable_line(holder, at)))
    assert_refused_alike("add", family, holder, held, (line, remedy))
    assert asked(log) == ["CHERRY_PICK_HEAD"] * 2, asked(log)
    assert asked_in(log) == {str(holder.resolve())}, asked_in(log)


# --- what git answers that is not 0 or 2 (the stand-in) ---------------------

@needs_sh
def test_a_git_before_2_43_answers_from_the_files_alone(
        family, holder, offline, tmp_path):
    """A GIT THAT KNOWS NO `--exists` (before 2.43) exits 129, `error:
    unknown option `exists'`, as git 2.40.4 does. Such a git cannot open a
    reftable at all, so the holder's refs are files and the file check is
    the whole answer: with nothing in progress, both marks are asked, the
    answer is "not held", and the verb makes its one commit as it always
    did."""
    env = isolated(offline, tmp_path)
    old, log = stand_in(tmp_path, env,
                        "  echo \"error: unknown option \\`exists'\" >&2\n"
                        "  exit 129\n")
    runs_after("add", family, holder, old)
    assert asked(log) == list(REFS), asked(log)
    assert asked_in(log) == {str(holder.resolve())}, asked_in(log)


#: `{exit: what the stand-in says}`: a git that could not read its ref store.
#: `git show-ref --exists` exits 1 where the look-up fails for any reason but
#: a missing ref, and 128 where git dies.
FAILURES = {1: "error: failed to look up reference: Input/output error",
            128: "fatal: the stand-in's ref store cannot be read"}


@needs_sh
@pytest.mark.parametrize("code, verb", [(1, "add"), (128, "remove")])
def test_git_failing_to_answer_stops_the_verb_before_its_first_write(
        family, holder, offline, tmp_path, code, verb):
    """GIT'S OWN FAILURE IS NEVER "NOTHING IN PROGRESS". Where `git show-ref
    --exists` exits with neither 0 nor 2 (nor a git before 2.43's 129), the
    verb stops as it stops on every failed git command, exit 2, the command,
    its exit and git's words, before its first write and under `--dry-run`
    alike, and the holder is as it was."""
    env = isolated(offline, tmp_path)
    failing, log = stand_in(tmp_path, env,
                            f"  echo \"{FAILURES[code]}\" >&2\n"
                            f"  exit {code}\n")
    expected = re.compile(
        re.escape("REFUSED a git or gh command failed. THE EXACT COMMAND "
                  "WAS:\n    git show-ref --exists CHERRY_PICK_HEAD\n"
                  "    (in ")
        + r"[^\n]+"
        + re.escape(f")\n    exit {code}\n--- output ---\n{FAILURES[code]}\n"
                    "--- end output ---\n"))
    before = snapshot(verb, holder, env)
    for extra in ((), ("--dry-run",)):
        ran = run_verb(verb, family, holder, failing, *extra)
        assert ran.returncode == 2, (extra, ran.stdout, ran.stderr)
        assert ran.stdout == "", (extra, ran.stdout)
        assert expected.fullmatch(ran.stderr), (extra, ran.stderr)
        assert_untouched(verb, holder, env, before)
    assert asked(log) == ["CHERRY_PICK_HEAD"] * 2, asked(log)
    assert asked_in(log) == {str(holder.resolve())}, asked_in(log)


# --- the exact name, and the order (this git) -------------------------------

@pytest.mark.parametrize("verb", VERBS)
def test_a_branch_and_a_tag_named_as_the_marks_are_no_operation(
        family, holder, offline, tmp_path, verb):
    """THE EXACT NAME, on every git: a branch called `CHERRY_PICK_HEAD` and a
    tag called `REVERT_HEAD`, with nothing in progress. `git rev-parse -q
    --verify` resolves both names, which is why it is not the ask, and `git
    show-ref --exists` neither (the premises); each verb makes its one
    commit as it always did."""
    env = isolated(offline, tmp_path)
    raw(holder, env, "branch", "CHERRY_PICK_HEAD")
    raw(holder, env, "tag", "REVERT_HEAD")
    head = raw(holder, env, "rev-parse", "HEAD").stdout
    for name in REFS:
        assert raw(holder, env, "rev-parse", "-q", "--verify", name
                   ).stdout == head, f"premise: {name} resolves"
        assert raw(holder, env, "show-ref", "--exists", name,
                   check=False).returncode == 2, f"premise: {name} is no ref"
    runs_after(verb, family, holder, env)


@pytest.mark.parametrize("kind, refs", [
    (None, list(REFS)), ("revert", ["CHERRY_PICK_HEAD"]), ("cherry-pick", [])],
    ids=["nothing", "revert", "cherry-pick"])
def test_the_file_is_asked_first_and_the_ref_store_only_where_none_is(
        family, holder, offline, tmp_path, monkeypatch, kind, refs):
    """THE ORDER, on the files backend: each of the two marks is asked of
    the ref store in its own row, only where its file is not there, by
    `git show-ref --exists <mark>` alone, and in the holder. With nothing in
    progress both are asked; a revert's file is found after the
    cherry-pick's mark was asked; a cherry-pick's file is found before any
    ask. A mark found as a file is named at its path, as before #684."""
    env = isolated(offline, tmp_path)
    if kind is not None:
        begin(kind, holder, env, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    calls = recorded(monkeypatch)
    module = family_module()
    real = module._git_bytes
    where = []

    def git_bytes(args, cwd, data=None):
        where.append((args[0], cwd))
        return real(args, cwd, data)

    monkeypatch.setattr(module, "_git_bytes", git_bytes)
    found = module._operation_in_progress(holder)
    shown = [argv for argv in calls if "show-ref" in argv]
    assert shown == [["git", "show-ref", "--exists", name] for name in refs]
    assert [cwd for sub, cwd in where if sub == "show-ref"] == (
        [holder] * len(refs)), where
    if kind is None:
        assert found is None
    else:
        mark = OPERATIONS[kind][1]
        assert found[1:3] == (mark, mark_of(holder, env, mark)), found


# --- a real reftable (git 2.45 and later) -----------------------------------

def reftable_repository(tmp_path: Path, env: dict) -> Path:
    """A repository made by `git init --ref-format=reftable`, on `main`; its
    ref format, asked of git, is the premise."""
    repo = tmp_path / "reftable"
    raw(tmp_path, env, "init", "-q", "--ref-format=reftable", "-b", "main",
        str(repo))
    assert raw(repo, env, "rev-parse", "--show-ref-format"
               ).stdout.strip() == b"reftable", "premise: a reftable"
    return repo


def stop(kind: str, root: Path, env: dict) -> None:
    """`kind` stopped in `root` by git itself, as `begin` stops it (a
    cherry-pick and a revert on a conflict, a merge with `--no-commit`),
    with no premise yet about where git keeps its mark."""
    if kind == "merge":
        work = work_branch(root, env)
        commit_file(root, env, NOTES, b"base\n", "base")
        raw(root, env, "switch", "-q", "-c", "side")
        commit_file(root, env, "other.txt", b"other\n", "other")
        raw(root, env, "switch", "-q", work)
        raw(root, env, "merge", "--no-commit", "--no-ff", "side")
        return
    conflicting_history(root, env)
    if kind == "revert":
        commit_file(root, env, NOTES, b"later\n", "later")
        stopped = raw(root, env, "revert", "--no-edit", "HEAD~1", check=False)
    else:
        stopped = raw(root, env, "cherry-pick", "side", check=False)
    assert stopped.returncode != 0, f"premise: the {kind} conflicts"


@needs_reftable
@pytest.mark.parametrize("kind", ["cherry-pick", "revert", "merge"])
def test_on_a_reftable_each_act_is_found_where_git_keeps_its_mark(
        offline, tmp_path, monkeypatch, kind):
    """E4 ON A REAL REFTABLE. The premises are the probe's: a stopped
    cherry-pick and a stopped revert leave no file at the path git names for
    the mark, and `git show-ref --exists` finds it; a stopped merge leaves
    `MERGE_HEAD` a file. `family-operation-in-progress` is raised, the line
    saying git keeps the mark in its ref store (a merge's at its path, as
    before), with the act's own remediation. The exit it prints, typed as
    printed, ends the act, and then nothing is in progress."""
    env = isolated(offline, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    repo = reftable_repository(tmp_path, env)
    stop(kind, repo, env)
    mark = OPERATIONS[kind][1]
    if kind == "merge":
        assert os.path.lexists(mark_of(repo, env, mark)), "premise: a file"
        line, remedy = operation_said(kind, "add")
    else:
        assert not os.path.lexists(mark_of(repo, env, mark)), (
            "premise: no file")
        assert raw(repo, env, "show-ref", "--exists", mark,
                   check=False).returncode == 0, "premise: in the ref store"
        line, remedy = held_said(kind, "add")
    module = family_module()
    with pytest.raises(module.Refusal) as refused:
        module._checked_no_operation_in_progress(repo, "add")
    said, exit_line = str(refused.value).split("\n")
    assert line.fullmatch(said), said
    assert exit_line == remedy, exit_line
    abort = OPERATIONS[kind][3]
    assert f"`{abort}`" in exit_line
    raw(repo, env, *shlex.split(abort)[1:])
    assert module._operation_in_progress(repo) is None
    assert not os.path.lexists(mark_of(repo, env, mark))
    if kind != "merge":
        # `MERGE_HEAD` is a file on a reftable too (the premise above), so
        # its file is the whole answer: only the two refs are asked.
        assert raw(repo, env, "show-ref", "--exists", mark,
                   check=False).returncode == 2


@needs_reftable
def test_on_a_reftable_a_branch_and_a_tag_named_as_the_marks_are_no_act(
        offline, tmp_path, monkeypatch):
    """THE EXACT NAME ON A REAL REFTABLE: a branch called `CHERRY_PICK_HEAD`
    and a tag called `REVERT_HEAD`, with nothing in progress, which `git
    rev-parse -q --verify` resolves (the premise): nothing is in progress."""
    env = isolated(offline, tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    repo = reftable_repository(tmp_path, env)
    commit_file(repo, env, NOTES, b"base\n", "base")
    raw(repo, env, "branch", "CHERRY_PICK_HEAD")
    raw(repo, env, "tag", "REVERT_HEAD")
    for name in REFS:
        assert raw(repo, env, "rev-parse", "-q", "--verify", name,
                   check=False).returncode == 0, f"premise: {name} resolves"
    assert family_module()._operation_in_progress(repo) is None
