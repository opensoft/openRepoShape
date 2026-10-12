# SPDX-License-Identifier: Apache-2.0
"""`apply --add` past the operator's own excludes, and the rollback (#202).

`commit_on_branch` staged an `--add` file with a plain `git add --`, which
honours `.git/info/exclude`, a global `core.excludesFile` and a nested
`.gitignore`. An ignored addition therefore failed AFTER the copies, the
re-pin, the README line, the validators and `git checkout -b` had all run,
and `cmd_apply`'s `except CommandFailed` arm returned 2 with none of it
undone: the root was left on the new branch with the re-pin as uncommitted
edits, and every later run read those edits as the truth — `apply --add`
refused the path as already pinned, `apply` said "nothing to do", and `check`
exited 0 over an update that existed only as uncommitted bytes.

Three groups, each the half of the fix it pins:

  * AN IGNORED ADDITION LANDS. Under each of the three ignore sources the
    addition is staged FORCED (`shape_materialize.force_stage`, the spelling
    #175 gave the scaffold), so it is in the commit with the bytes and the
    row the pin records, and the project's own validators are green — while
    an ignored file nobody named stays out, because `-f` is over the named
    paths and never over `.`.
  * A FAILURE BEFORE THE COMMIT PUTS EVERYTHING BACK. A staging failure, a
    pre-commit hook, a branch git cannot create, and `--branch` postures
    around them (the current branch, a detached HEAD, an index entry somebody
    had already staged at the added path, a tag named like the branch HEAD
    is on), each injected after the copies are written, and each over an
    operator's own staged work — a new file and an edit — that no rollback
    may touch: the tree is compared byte for byte, with the index, HEAD and
    every branch, against what it was; the refusal names the step and lists
    what it put back; and `check` then prints exactly what it printed before,
    `upstream-added` rows included, never "nothing to do". A rollback git
    will not finish says so, `ROLLED BACK IN PART`, with a fix that can be
    pasted; and a failure AFTER the commit lands rolls nothing back, because
    the commit is the result.
  * A NON-IGNORED ADDITION IS UNCHANGED. The same files reach the same
    commit, and nothing the run did not write is swept into the index —
    not even an ignored file a glob character in an added name would match.

And a fourth, the rollback's own reads and the line it ends with, each
pinned where it could regress without any other test noticing:

  * HEAD IS READ AS UTF-8. A start branch `feature/café` is returned to
    under the ANSI code page too (simulated, so it runs on every platform;
    and for real in a child under `LC_ALL=C`), because `_git_answer` names
    its codec.
  * THE BRANCH HEAD IS ON IS NEVER DELETED. A switch back that fails — an
    `index.lock` held for a moment — leaves the branch and says switch
    first, then delete.
  * THE `NEXT` HINT PASTES WHOLE. Every path in it is quoted and the add is
    `--literal-pathspecs`, so a name holding `[` stages itself and nothing
    its glob matches, in the shell and in git.

THE FIXTURE is `tests/test_update_shape.py`'s: a clone of this repository at
A and `Atlas` scaffolded from it into bare repositories on disk, with a
README that ends in a `Shape:` line naming A, so a run moves that line too.
Commit B fixes one copied file and adds three to the assembly root's copy
lists — one at the top level, one executable script in `scripts/`, and one in
a directory the root does not have yet — which is every kind of write the
rollback ledger has to undo. Commit C, above B, adds one more whose NAME holds
a pathspec glob character, for the one test that runs `--at` it.
`PYTHONDONTWRITEBYTECODE=1` is set for every run, because the validators
`apply` runs import `scripts/repo_shape.py` from the root and would otherwise
leave `scripts/__pycache__/` behind, which is a difference in the tree that
is not the rollback's. Every git configuration a
run reads comes from `GIT_CONFIG_GLOBAL` pointed at a file the test writes,
so nothing here depends on the excludes or hooks of whoever runs the suite.
No network is used and `gh` is never invoked.
"""

from __future__ import annotations

import codecs
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import REPO, git, run_script
#: The upstream-and-project fixture, the copied file B fixes and the README
#: line, imported from the module that owns them rather than retyped — the
#: same reuse `test_update_shape.py` makes of `test_commit_trailers`.
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               give_readme, rendered_shape_line,
                               scaffold_upstream_and_project)
#: How a pull request adds a file to the copy lists, and the report parser
#: that knows the `upstream-added` verdict.
from test_update_shape_add import (MATERIALIZER, commit_all, name_in_list,
                                   validators_are_green, verdicts)
#: The operator whose excludes are a file this test writes (#175), and the
#: loader that imports a hyphenated tool in-process.
from test_scaffold_ignored_shape_files import (excluding, git_under, ignored,
                                               load)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import file_sha256, parse_yaml  # noqa: E402

UPDATE = REPO / "update-shape.py"
PROJECT = "Atlas"
PIN = "contracts/shape-pin.yaml"
MANIFEST = "project.yaml"
README = "README.md"

#: What B adds to the assembly root's lists: a file at the top level, an
#: EXECUTABLE in a directory the root already tracks, and a file in a
#: directory the root does not have, so the rollback has a directory to
#: remove as well as files.
ROOT_ADDED = "AGENTS-ignored-test.md"
SCRIPT_ADDED = "scripts/ignored-check.py"
DIR_ADDED = "docs/shape-guide.md"
ADDITIONS = (ROOT_ADDED, SCRIPT_ADDED, DIR_ADDED)
ADD_ARGS = tuple(arg for path in ADDITIONS for arg in ("--add", path))
BODIES = {
    ROOT_ADDED: b"# The shape's notes, added after this project was cut.\n",
    SCRIPT_ADDED: b"#!/usr/bin/env python3\nprint('a check the standard "
                  b"gained')\n",
    DIR_ADDED: b"# A guide the standard gained, in a directory of its own.\n",
}
#: Everything a run that takes all three writes: the copy B fixes, the pin,
#: the manifest's mirror of it, the README's `Shape:` line, and the three.
WRITTEN = (CHANGED, PIN, MANIFEST, README, *ADDITIONS)

#: What C adds: a name holding `[` and `]`, which a PATHSPEC reads as a glob
#: matching `docs/guide1.md`. Both characters are legal in a Windows file
#: name, so this runs on every platform.
GLOB_ADDED = "docs/guide[1].md"
GLOB_NEIGHBOUR = "docs/guide1.md"

BRANCH = "shape/update-ignored"


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it with a `Shape:` line naming A, B
    above them fixing one copied file and adding the three, and C above B
    adding `GLOB_ADDED`."""
    _base, upstream, a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-add-ignored")
    give_readme(clone, rendered_shape_line(a))

    for rel, body in BODIES.items():
        target = upstream / "templates" / "assembly-root" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        # Bytes, so the blob is LF on every platform and `--add` copies the
        # same bytes everywhere.
        target.write_bytes(body)
    fixed = upstream / CHANGED_SOURCE
    fixed.write_bytes(fixed.read_bytes() + UPSTREAM_FIX_LINE.encode("utf-8"))
    source = upstream / MATERIALIZER
    text = source.read_bytes().decode("utf-8")
    for rel in ADDITIONS:
        text = name_in_list(text, "COPIED_VERBATIM", rel)
    text = name_in_list(text, "EXECUTABLE", SCRIPT_ADDED)
    source.write_bytes(text.encode("utf-8"))
    b = commit_all(upstream, "Fix the manifest validator and add three "
                   "files to the assembly root", [
                       MATERIALIZER, CHANGED_SOURCE,
                       *(f"templates/assembly-root/{rel}" for rel in BODIES)])
    assert a != b

    (upstream / "templates" / "assembly-root" / GLOB_ADDED).write_bytes(
        b"# A guide whose name a pathspec would read as a glob.\n")
    source.write_bytes(name_in_list(
        source.read_bytes().decode("utf-8"), "COPIED_VERBATIM",
        GLOB_ADDED).encode("utf-8"))
    c = commit_all(upstream, "Add a file whose name holds a glob character",
                   [MATERIALIZER, f"templates/assembly-root/{GLOB_ADDED}"])
    assert c != b
    return {"upstream": upstream, "clone": clone, "a": a, "b": b, "c": c}


@pytest.fixture
def root(standard, tmp_path):
    """A private, mutable copy of the project as it was cut at A."""
    target = tmp_path / PROJECT
    shutil.copytree(standard["clone"], target, symlinks=True)
    return target


@pytest.fixture
def quiet(tmp_path) -> dict:
    """The environment of an operator with NO excludes and no hooks, so a
    test's own rule is the only one in play."""
    return {**excluding(tmp_path / "quiet", rules=b""),
            "PYTHONDONTWRITEBYTECODE": "1"}


def check(root, standard, env):
    return run_script(UPDATE, "check", "--root", str(root),
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], env=env)


def apply(root, standard, env, *extra, at: str | None = None):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", at or standard["b"], *extra, env=env)


def git_bytes(env: dict, *args: str, cwd: Path,
              data: bytes | None = None) -> bytes:
    """`git <args>`'s stdout as BYTES, with `data` as bytes on stdin: an
    index record or a blob must reach git untranslated on Windows."""
    proc = subprocess.run(["git", *args], cwd=str(cwd), input=data,
                          capture_output=True, check=False,
                          env={**os.environ, **env})
    assert proc.returncode == 0, (f"git {' '.join(args)} in {cwd}:\n"
                                  f"{proc.stderr.decode(errors='replace')}")
    return proc.stdout


def snapshot(root: Path, env: dict) -> dict:
    """Everything a rollback must put back, read off the disk and off git.

    EVERY FILE'S BYTES AND MODE and every directory under the root, the
    submodules' working trees included and every `.git` left out — a
    directory `--add` made and the undo forgot is a difference too, which a
    listing of files alone would miss. And git's half: where HEAD is, every
    branch and what it names, the index's `--stage` records (not the index
    FILE, whose stat cache moves whenever git looks), and `status` with the
    ignored files listed, which is what the issue's re-run read as the truth.
    """
    files: dict[str, tuple[bytes, int]] = {}
    dirs: set[str] = set()
    for directory, subdirs, names in os.walk(root):
        subdirs[:] = sorted(name for name in subdirs if name != ".git")
        here = Path(directory)
        dirs.update((here / name).relative_to(root).as_posix()
                    for name in subdirs)
        for name in names:
            if name == ".git":
                continue  # a submodule's gitfile
            path = here / name
            files[path.relative_to(root).as_posix()] = (
                path.read_bytes(), stat.S_IMODE(path.lstat().st_mode))
    return {
        "files": files,
        "dirs": dirs,
        "head": subprocess.run(
            ["git", "symbolic-ref", "-q", "HEAD"], cwd=str(root),
            capture_output=True, check=False).stdout
        + git_bytes(env, "rev-parse", "HEAD", cwd=root),
        "branches": git_bytes(env, "for-each-ref",
                              "--format=%(refname) %(objectname)",
                              "refs/heads", cwd=root),
        "index": git_bytes(env, "ls-files", "--stage", "-z", cwd=root),
        "status": git_bytes(env, "status", "--porcelain=v1", "-z",
                            "--ignored", "--untracked-files=all", cwd=root),
    }


def assert_same_tree(before: dict, after: dict) -> None:
    """`before == after`, said path by path when it is not, rather than as
    two dictionaries of bytes nobody can read."""
    added = sorted(set(after["files"]) - set(before["files"]))
    removed = sorted(set(before["files"]) - set(after["files"]))
    changed = sorted(path for path in set(before["files"]) & set(after["files"])
                     if before["files"][path] != after["files"][path])
    assert (added, removed, changed) == ([], [], []), (
        f"files left behind {added}, lost {removed}, not restored {changed}")
    assert sorted(after["dirs"] ^ before["dirs"]) == [], "directories differ"
    for key in ("head", "branches", "index", "status"):
        assert after[key] == before[key], (
            f"{key} is not what it was:\n  before {before[key]!r}\n"
            f"  after  {after[key]!r}")


def head_tree(root) -> set:
    return set(git("ls-tree", "-r", "--name-only", "HEAD",
                   cwd=root).stdout.splitlines())


def committed_files(root) -> set:
    return set(git("show", "--name-only", "--format=", "HEAD",
                   cwd=root).stdout.split())


def head_pin_rows(root) -> dict:
    """The pin's rows IN THE COMMIT, never on the disk, where every file
    `git add` refused is still sitting."""
    pin = parse_yaml(git("show", f"HEAD:{PIN}", cwd=root).stdout)
    return {row["path"]: row["sha256"].lower() for row in pin["files"]}


def upstream_bytes(standard, rel: str) -> bytes:
    return subprocess.run(
        ["git", "show", f"{standard['b']}:templates/assembly-root/{rel}"],
        cwd=str(standard["upstream"]), capture_output=True,
        check=True).stdout


def write_stray(root, rel: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"an operator's own file, which no pin names\n")


# ---------------------------------------------------------------------------
# An addition the operator's excludes ignore is committed
# ---------------------------------------------------------------------------
#
# Each source returns the environment the run is made under and a stray file
# the same rules hide, which must stay out of the index and the commit: a
# forced add of the named paths is the fix, and a forced add of anything else
# is the sweep `commit_on_branch`'s explicit pathspecs exist to prevent.


def by_info_exclude(root, base) -> tuple[dict, tuple, str]:
    """The repository's own ignore file — the issue's reproduction, which
    stood in for a global `core.excludesFile` with exactly this."""
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    old = exclude.read_bytes() if exclude.is_file() else b""
    exclude.write_bytes(old + f"{ROOT_ADDED}\n{SCRIPT_ADDED}\ndocs/\n"
                        "scratch-202.log\n".encode())
    return ({**excluding(base, rules=b""), "PYTHONDONTWRITEBYTECODE": "1"},
            ADDITIONS, "scratch-202.log")


def by_global_excludes(root, base) -> tuple[dict, tuple, str]:
    """A global `core.excludesFile` naming the directories the shape copies
    into, as #175's operator had: the scripts directory, any new docs, any
    `AGENTS-*` file, any log."""
    rules = b"AGENTS-*.md\nscripts/\ndocs/\n*.log\n"
    return ({**excluding(base, rules=rules), "PYTHONDONTWRITEBYTECODE": "1"},
            ADDITIONS, "scratch-202.log")


def by_nested_gitignore(root, base) -> tuple[dict, tuple, str]:
    """A `.gitignore` the project keeps in `scripts/`, committed. Not the
    root's: that one is a PINNED copy, and editing it would be drift the run
    refuses before it writes anything, rather than this."""
    (root / "scripts" / ".gitignore").write_bytes(b"ignored-check.py\n*.log\n")
    git("add", "--", "scripts/.gitignore", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "The project ignores its own scratch scripts", "--",
        "scripts/.gitignore", cwd=root)
    return ({**excluding(base, rules=b""), "PYTHONDONTWRITEBYTECODE": "1"},
            (SCRIPT_ADDED,), "scripts/scratch-202.log")


@pytest.mark.parametrize("source", [by_info_exclude, by_global_excludes,
                                    by_nested_gitignore],
                         ids=["info-exclude", "global-excludes",
                              "nested-gitignore"])
def test_an_ignored_addition_is_committed_and_the_root_stays_green(
        root, standard, tmp_path, source):
    env, hidden, stray = source(root, tmp_path / "operator")
    write_stray(root, stray)
    for path in (*hidden, stray):
        assert ignored(root, path, env), (
            f"{path} is not ignored, so this test no longer runs #202")

    result = apply(root, standard, env, *ADD_ARGS, "--branch", BRANCH)

    assert result.returncode == 0, result.stdout + result.stderr
    assert committed_files(root) == set(WRITTEN), (
        "the commit holds every file the run wrote, the ignored ones included")
    rows = head_pin_rows(root)
    for rel in ADDITIONS:
        assert git_bytes(env, "show", f"HEAD:{rel}", cwd=root) \
            == upstream_bytes(standard, rel)
        assert rows[rel] == file_sha256(root / rel), (
            "the pin in the commit records the bytes in the commit")
    if os.name != "nt":
        mode = git("ls-tree", "HEAD", "--", SCRIPT_ADDED,
                   cwd=root).stdout.split()[0]
        assert mode == "100755", (
            "`EXECUTABLE` names it, and the forced add records its mode")
    assert git_under(env, "status", "--porcelain", "--ignored", "--",
                     *WRITTEN, cwd=root).stdout == "", (
        "nothing the run wrote is left uncommitted")
    assert stray not in head_tree(root)
    assert git("ls-files", "--", stray, cwd=root).stdout == "", (
        "an ignored file nobody named is not forced in beside the additions")
    assert (root / stray).is_file()
    validators_are_green(root)


# ---------------------------------------------------------------------------
# A failure before the commit lands puts every byte, the index and the
# branch back, and says which step failed
# ---------------------------------------------------------------------------


def refuse_to_stage(root) -> None:
    """A required clean filter that fails on the top-level addition, so `git
    add -f` dies on it after every byte has been written — the stand-in for
    any reason git cannot stage a path. Set in the repository's own config
    and `info/attributes`, both under `.git/`, so the tree compared is the
    tree the run found."""
    git("config", "filter.refuse-202.clean", "exit 1", cwd=root)
    git("config", "filter.refuse-202.required", "true", cwd=root)
    attributes = root / ".git" / "info" / "attributes"
    attributes.parent.mkdir(parents=True, exist_ok=True)
    attributes.write_bytes(f"{ROOT_ADDED} filter=refuse-202\n".encode())


def refuse_the_commit(root) -> None:
    """A pre-commit hook that says no. `core.hooksPath` is set in the
    repository's own config so a global one cannot replace it, and the hook
    is a shebang script, which Git for Windows runs through its own `sh`."""
    hooks = root / ".git" / "refusing-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_bytes(b"#!/bin/sh\necho 'pre-commit: not this commit' >&2\n"
                     b"exit 1\n")
    hook.chmod(0o755)
    git("config", "core.hooksPath", hooks.as_posix(), cwd=root)


def a_branch_in_the_way(root) -> None:
    """`shape/update` exists, so `shape/update/ignored` cannot: a ref cannot
    be a file and a directory at once."""
    git("branch", "shape/update", cwd=root)


def the_branch_already_exists(root) -> None:
    git("branch", BRANCH, cwd=root)


def on_the_branch_already(root) -> None:
    """The posture AGENTS.md's `both` exit leaves: the branch is current, so
    `apply` commits onto it and creates nothing — and the rollback must not
    delete a branch this run did not make."""
    git("checkout", "-q", "-b", BRANCH, cwd=root)
    refuse_the_commit(root)


def detached(root) -> None:
    git("checkout", "-q", "--detach", cwd=root)
    refuse_the_commit(root)


def already_staged(root) -> None:
    """Somebody staged a blob at the top-level addition's path and then
    removed the file, which leaves the path free for `--add` and an index
    entry that `git reset` would NOT put back: it writes HEAD's entry, and
    HEAD has none. The record goes in through `update-index`, as bytes."""
    blob = git_bytes({}, "hash-object", "-w", "--stdin", cwd=root,
                     data=b"somebody's staged draft\n").strip()
    git_bytes({}, "update-index", "--add", "--cacheinfo",
              f"100644,{blob.decode('ascii')},{ROOT_ADDED}", cwd=root)
    refuse_the_commit(root)


def a_tag_named_like_the_branch(root) -> None:
    """A TAG called `main` beside the branch HEAD is on. `--short` then
    spells that branch `heads/main`, and `git checkout heads/main` DETACHES
    HEAD at the tag rather than returning to the branch — which is why
    `Rollback.new_branch` keeps the start under `refs/heads/`."""
    git("tag", "main", cwd=root)
    refuse_the_commit(root)


def refuse_to_delete_the_branch(root) -> None:
    """The pre-commit hook that starts the rollback, and a
    `reference-transaction` hook that then refuses to delete any
    `refs/heads/shape/*` — the one undo git can decline after it has been
    asked. Creating the branch, and moving HEAD, are let through."""
    refuse_the_commit(root)
    hook = root / ".git" / "refusing-hooks" / "reference-transaction"
    hook.write_bytes(
        b'#!/bin/sh\n'
        b'[ "$1" = prepared ] || exit 0\n'
        b'while read -r old new ref; do\n'
        b'  case "$new" in *[!0]*) continue ;; esac\n'
        b'  case "$ref" in refs/heads/shape/*)\n'
        b'    echo "reference-transaction: not deleting $ref" >&2; exit 1 ;;\n'
        b'  esac\n'
        b'done\n'
        b'exit 0\n')
    hook.chmod(0o755)


#: Somebody's work in progress, staged before the run. The edit is to a file
#: the operator tracks and the pin does not name, and has a further unstaged
#: edit on top, so the index and the disk disagree about it.
OPERATOR_NEW = "NOTES-operator.md"
OPERATOR_EDITED = "AGENTS.md"


def operators_staged_work(root) -> None:
    """A NEW file and an EDIT, both staged, in the checkout `apply` writes
    into. No rollback may touch either: one that put the index back by
    resetting all of it to HEAD would unstage both — `A ` and `MM` becoming
    `??` and ` M` — and still print "exactly as it was", which is the
    xFactory sweep `commit_on_branch`'s explicit pathspecs exist to prevent,
    arriving the other way round."""
    (root / OPERATOR_NEW).write_bytes(b"an operator's notes, staged\n")
    edited = root / OPERATOR_EDITED
    edited.write_bytes(edited.read_bytes() + b"\nAn operator's staged edit.\n")
    git("add", "--", OPERATOR_NEW, OPERATOR_EDITED, cwd=root)
    edited.write_bytes(edited.read_bytes() + b"And an unstaged one on top.\n")


#: `(id, injection, --branch, the step's first line, the git lines the
#: rollback must print, a line it must not)`. `{head}` is the commit HEAD
#: named before the run, twelve characters, as the rollback spells it.
FAILURES = [
    ("stage", refuse_to_stage, BRANCH,
     f"REFUSED staging the --add file(s) {', '.join(ADDITIONS)} on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)}", "switched  HEAD back to main",
      f"deleted   {BRANCH}"), None),
    ("pre-commit", refuse_the_commit, BRANCH,
     f"REFUSED committing the re-synced shape on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)}", "switched  HEAD back to main",
      f"deleted   {BRANCH}"), None),
    ("branch-df", a_branch_in_the_way, "shape/update/ignored",
     "REFUSED creating the branch shape/update/ignored",
     ("kept      HEAD on main, where it started",
      "absent    shape/update/ignored (never created)"), "unstaged"),
    ("branch-exists", the_branch_already_exists, BRANCH,
     f"REFUSED update-branch-exists: --branch {BRANCH} already exists", (),
     "deleted"),
    ("current-branch", on_the_branch_already, BRANCH,
     f"REFUSED committing the re-synced shape on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)}",), "deleted"),
    ("detached", detached, BRANCH,
     f"REFUSED committing the re-synced shape on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)}",
      "switched  HEAD back to {head} (detached)", f"deleted   {BRANCH}"),
     None),
    ("staged-before", already_staged, BRANCH,
     f"REFUSED committing the re-synced shape on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)} (the index holds what it held "
      "before this run)", "switched  HEAD back to main",
      f"deleted   {BRANCH}"), None),
    ("tag-main", a_tag_named_like_the_branch, BRANCH,
     f"REFUSED committing the re-synced shape on {BRANCH}",
     (f"unstaged  {' '.join(ADDITIONS)}", "switched  HEAD back to main",
      f"deleted   {BRANCH}"), "heads/main"),
]


@pytest.mark.parametrize("inject, branch, step, git_lines, never",
                         [case[1:] for case in FAILURES],
                         ids=[case[0] for case in FAILURES])
def test_a_failure_before_the_commit_puts_the_tree_back_and_names_the_step(
        root, standard, quiet, inject, branch, step, git_lines, never):
    inject(root)
    operators_staged_work(root)
    head = git("rev-parse", "HEAD", cwd=root).stdout.strip()[:12]
    checked = check(root, standard, quiet)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    before = snapshot(root, quiet)
    for staged in (f"A  {OPERATOR_NEW}", f"MM {OPERATOR_EDITED}"):
        assert f"{staged}\0".encode() in before["status"], (
            f"{staged!r} is not in the status, so nothing here would catch a "
            "rollback that wiped the operator's index")

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", branch)

    assert result.returncode == 2, result.stdout + result.stderr
    for line in ("re-pinned contracts/shape-pin.yaml", "pins ok",
                 *(f"added    {rel}" for rel in ADDITIONS)):
        assert line in result.stdout, (
            f"the failure is injected AFTER the writes; {line!r} is missing")
    assert step in result.stderr, result.stderr
    assert ("ROLLED BACK: every byte this command wrote has been put back"
            in result.stderr), result.stderr
    assert "ROLLED BACK IN PART" not in result.stderr
    for rel in (CHANGED, PIN, MANIFEST, README):
        assert f"restored  {rel}" in result.stderr
    for rel in ADDITIONS:
        assert f"removed   {rel} (written by --add)" in result.stderr
    assert "removed   docs/ (made to hold an --add file)" in result.stderr
    for line in git_lines:
        assert line.format(head=head) in result.stderr, result.stderr
    if never:
        assert never not in result.stderr, result.stderr
    assert_same_tree(before, snapshot(root, quiet))

    again = check(root, standard, quiet)
    assert again.returncode == 1, again.stdout + again.stderr
    assert again.stdout == checked.stdout, (
        "`check` must find the tree it found before the failed run")
    verdict = verdicts(again.stdout)
    assert {rel: verdict.get(rel) for rel in ADDITIONS} == {
        rel: "upstream-added" for rel in ADDITIONS}
    assert verdict.get(CHANGED) == "upstream-changed"
    assert "nothing to do" not in again.stdout


def test_a_branch_git_cannot_name_is_refused_before_any_write(
        root, standard, quiet):
    """`shape/update..ignored` WAS this file's branch-creation failure after
    the writes: `git checkout -b` refuses `..`, so the copies, the pin and
    the README line had to be put back. Since #204 `main` asks `git
    check-ref-format --branch` about `--branch` before anything is read or
    written, so the same name is refused as `update-branch-invalid`, with
    nothing on stdout and nothing to put back, and the operator's staged
    work is untouched. `branch-df` above still makes `git checkout -b` fail
    after the writes."""
    operators_staged_work(root)
    checked = check(root, standard, quiet)
    before = snapshot(root, quiet)

    result = apply(root, standard, quiet, *ADD_ARGS,
                   "--branch", "shape/update..ignored")

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED update-branch-invalid: --branch 'shape/update..ignored' "), (
        result.stderr)
    assert result.stdout == "", "refused before anything was written"
    assert "ROLLED BACK" not in result.stderr
    assert_same_tree(before, snapshot(root, quiet))
    assert check(root, standard, quiet).stdout == checked.stdout


def test_a_rollback_git_will_not_finish_says_so_and_names_the_fix(
        root, standard, quiet):
    """A PARTIAL ROLLBACK IS SAID TO BE ONE. Every undo is judged by reading
    the state afterwards, and what git would not put back is listed under
    `NOT put back` with the command that finishes it — never folded into
    "the tree is exactly as it was". Here the branch deletion is refused by
    a hook, so that branch is the one thing left: everything else in the
    tree, the index, HEAD and the operator's staged work is as it was, and
    the printed command, run once the hook is gone, makes it whole."""
    refuse_to_delete_the_branch(root)
    operators_staged_work(root)
    checked = check(root, standard, quiet)
    before = snapshot(root, quiet)

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH)

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"REFUSED committing the re-synced shape on {BRANCH}"
            in result.stderr), result.stderr
    assert ("ROLLED BACK IN PART: the tree is NOT as it was. Put back:"
            in result.stderr), result.stderr
    assert "ROLLED BACK: every byte" not in result.stderr
    for line in (f"unstaged  {' '.join(ADDITIONS)}",
                 "switched  HEAD back to main",
                 *(f"restored  {rel}" for rel in (CHANGED, PIN, MANIFEST,
                                                  README)),
                 *(f"removed   {rel} (written by --add)"
                   for rel in ADDITIONS)):
        assert line in result.stderr, result.stderr
    assert f"deleted   {BRANCH}" not in result.stderr
    heading = "  NOT put back — finish these by hand:\n"
    assert heading in result.stderr, result.stderr
    left = [line.strip() for line in
            result.stderr.split(heading, 1)[1].splitlines()
            if line.startswith("    ")]
    said = f"branch    {BRANCH}, which this run created, is still there: "
    assert len(left) == 1 and left[0].startswith(said), left
    fix = shlex.split(left[0][len(said):])
    assert fix == ["git", "-C", fix[2], "branch", "-D", BRANCH], fix
    assert Path(fix[2]).resolve() == root.resolve(), fix

    after = snapshot(root, quiet)
    assert after["branches"] != before["branches"]
    assert_same_tree({**before, "branches": b""}, {**after, "branches": b""})

    (root / ".git" / "refusing-hooks" / "reference-transaction").unlink()
    subprocess.run(fix, check=True, capture_output=True,
                   env={**os.environ, **quiet})
    assert_same_tree(before, snapshot(root, quiet))
    assert check(root, standard, quiet).stdout == checked.stdout


def test_an_index_left_staged_gets_a_pasteable_fix_and_never_a_reset(
        tmp_path, quiet, monkeypatch):
    """THE INDEX'S HAND FIX, built for each path as it was before the run.

    It printed `git reset -q -- <names>`: unquoted, so `docs/shape guide.md`
    pasted as two paths, and wrong for a path that HAD a staged entry,
    because `reset` writes HEAD's entry over it (`Rollback.stage`'s hazard).
    No injection reaches this message end to end — a `reference-transaction`
    hook refuses ref updates and the index is no ref, and nothing short of
    breaking `update-index` itself makes the index undo fail — so the
    ledger is driven in-process: `Rollback.stage` forces the paths as `apply`
    does, then `_undo_index` runs with `_git_quietly` answering as a git
    that could not be started, so nothing is put back and every path is
    left. The root's own path holds a space, and the three paths are one
    with no entry before, one with a staged draft that is NOT HEAD's, and
    one that was unmerged, its name holding a glob character too. Each
    command splits back into the arguments it names, and, run through `sh`
    where the suite has one, puts back exactly the records the index held."""
    for name, value in quiet.items():
        monkeypatch.setenv(name, value)
    update_shape = load(UPDATE, "update_shape_index_by_hand")
    work = tmp_path / "a root"
    work.mkdir()
    new, draft, unmerged = "docs/shape guide.md", "staged draft.md", \
        "both [1].md"

    def run(*args: str, data: bytes | None = None) -> bytes:
        return git_bytes(quiet, *args, cwd=work, data=data)

    run("init", "-q")
    (work / draft).write_bytes(b"HEAD's version\n")
    run("add", "--", draft)
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "HEAD has its own entry at the drafted path")
    (work / draft).write_bytes(b"somebody's staged draft\n")
    run("add", "--", draft)
    blobs = [run("hash-object", "-w", "--stdin",
                 data=f"stage {n}\n".encode()).strip() for n in (1, 2, 3)]
    run("update-index", "-z", "--index-info", data=b"".join(
        b"100644 " + blob + f" {n}\t{unmerged}\0".encode()
        for n, blob in zip((1, 2, 3), blobs)))
    paths = [new, draft, unmerged]
    for path in paths:
        (work / path).parent.mkdir(parents=True, exist_ok=True)
        (work / path).write_bytes(b"what --add wrote\n")
    ledger = update_shape.Rollback(work)
    ledger.stage(paths)
    before = ledger.index_before
    assert ledger._index_entries(paths) != before, "the stage changed nothing"
    monkeypatch.setattr(update_shape, "_git_quietly",
                        lambda *args, **kwargs: None)
    done: list[str] = []
    lines: list[str] = []

    ledger._undo_index(done, lines)

    assert done == [], done
    assert lines == update_shape._index_by_hand(work, paths, before)
    assert len(lines) == len(paths), lines
    commands = []
    for path, line in zip(paths, lines):
        assert line.startswith(
            f"index     {path} may still hold this run's entry; it "), line
        commands.append(line.split(": ", 1)[1])
    draft_sha = next(record.split(b" ")[1] for record in before.split(b"\0")
                     if record.endswith(f"\t{draft}".encode())).decode("ascii")
    assert f"had 100644 {draft_sha[:12]} staged before" in lines[1]
    assert "unmerged before (stages 1, 2, 3)" in lines[2]
    assert shlex.split(commands[0]) == [
        "git", "-C", str(work), "update-index", "--force-remove", "--", new]
    assert shlex.split(commands[1]) == [
        "git", "-C", str(work), "update-index", "--add", "--cacheinfo",
        f"100644,{draft_sha},{draft}"]
    for command in commands:
        words = shlex.split(command)
        assert "reset" not in words, (
            "`git reset` writes HEAD's entry, not the one that was there")
    if os.name != "nt":  # the fix is an `sh` line; Windows' stock shell is not
        for command in commands:
            subprocess.run(["sh", "-c", command], check=True,
                           capture_output=True, env={**os.environ, **quiet})
        assert ledger._index_entries(paths) == before, (
            "the printed fixes put back exactly what the index held")


def test_the_same_command_lands_once_the_failure_is_gone(root, standard,
                                                         quiet):
    """THE ISSUE'S SECOND RUN. Left half-done, the same `apply --add` was
    refused as `update-add-already-pinned` and the plain `apply` said
    "nothing to do". Rolled back, it is simply the first run again."""
    refuse_the_commit(root)
    failed = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH)
    assert failed.returncode == 2, failed.stdout + failed.stderr
    git("config", "--unset", "core.hooksPath", cwd=root)

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "update-add-already-pinned" not in result.stderr
    assert "nothing to do" not in result.stdout
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == BRANCH
    assert committed_files(root) == set(WRITTEN)
    validators_are_green(root)


def test_a_failure_after_the_commit_lands_rolls_nothing_back(root, standard,
                                                             quiet, tmp_path):
    """THE COMMIT IS THE RESULT. A push that fails after it must not write
    the old bytes back under a branch that holds the new ones — that would
    leave a tree reverting its own HEAD. What such a failure SAYS is #204's;
    this asserts only what it must not do."""
    git("remote", "set-url", "origin", (tmp_path / "nowhere.git").as_posix(),
        cwd=root)

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH,
                   "--push")

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"committed on {BRANCH}" in result.stdout
    assert "git push" in result.stderr, result.stderr
    assert "ROLLED BACK" not in result.stderr
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == BRANCH
    assert committed_files(root) == set(WRITTEN)
    assert git("status", "--porcelain", "--", *WRITTEN,
               cwd=root).stdout == "", "the tree is the commit, untouched"


# ---------------------------------------------------------------------------
# An addition nothing ignores lands exactly as it did before #202
# ---------------------------------------------------------------------------


def test_an_addition_nothing_ignores_lands_exactly_as_before(root, standard,
                                                             quiet):
    """Forced or not, a path no rule ignores is staged the same way, so the
    commit is the one it always was — and the forced add over the NAMED
    paths takes nothing else: another session's staged file stays staged
    and out of the commit, and an untracked file stays untracked."""
    for rel in ADDITIONS:
        assert not ignored(root, rel, quiet), f"{rel} is ignored here"
    (root / "unrelated.txt").write_bytes(b"another session's work\n")
    git("add", "--", "unrelated.txt", cwd=root)
    (root / "notes.txt").write_bytes(b"untracked, and nobody's business\n")

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH)

    assert result.returncode == 0, result.stdout + result.stderr
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root).stdout.strip() == BRANCH
    assert committed_files(root) == set(WRITTEN)
    assert git("diff", "--cached", "--name-only", cwd=root).stdout.split() \
        == ["unrelated.txt"]
    assert git("ls-files", "--others", "--exclude-standard", "--",
               "notes.txt", cwd=root).stdout.split() == ["notes.txt"]
    for rel in ADDITIONS:
        assert (root / rel).read_bytes() == upstream_bytes(standard, rel)
    validators_are_green(root)


def test_a_glob_character_in_an_added_name_forces_in_nothing_it_matches(
        root, standard, quiet):
    """`-f` OVER THE NAMED PATHS, TAKEN LITERALLY. Read as a pathspec,
    `docs/guide[1].md` is a glob that also matches the operator's ignored
    `docs/guide1.md`, and a forced add of it staged that file too — and the
    commit took it in, because the stage had put it in the index. Literal,
    the added name stages itself and nothing it happens to match."""
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes((exclude.read_bytes() if exclude.is_file() else b"")
                        + f"{GLOB_NEIGHBOUR}\n".encode())
    write_stray(root, GLOB_NEIGHBOUR)
    assert ignored(root, GLOB_NEIGHBOUR, quiet), (
        f"{GLOB_NEIGHBOUR} is not ignored, so -f would not be what stages it")
    assert not ignored(root, GLOB_ADDED, quiet)

    result = apply(root, standard, quiet, "--add", GLOB_ADDED,
                   "--branch", BRANCH, at=standard["c"])

    assert result.returncode == 0, result.stdout + result.stderr
    assert committed_files(root) == {CHANGED, PIN, MANIFEST, README,
                                     GLOB_ADDED}, (
        "the commit holds the named file and not its glob neighbour")
    assert git("ls-files", "--", GLOB_NEIGHBOUR, cwd=root).stdout == "", (
        "an ignored file the added name matches as a glob is not forced in")
    assert (root / GLOB_NEIGHBOUR).is_file()
    assert head_pin_rows(root)[GLOB_ADDED] == file_sha256(root / GLOB_ADDED)
    validators_are_green(root)


def test_force_stage_forces_exactly_the_named_paths_and_nothing_else(
        monkeypatch):
    """What reaches git: `add -f` over the paths `--add` named, each taken
    LITERALLY, and nothing else, never `-A` and never `.`; and with none,
    no git at all. The same helper is the forced half of `stage_written`
    (#175), so the scaffold and `apply --add` spell the forced add one
    way."""
    calls = []
    monkeypatch.setattr(shape_materialize, "run",
                        lambda args, cwd=None, capture=True: calls.append(args))
    shape_materialize.force_stage(Path("root"), [ROOT_ADDED, SCRIPT_ADDED])
    shape_materialize.force_stage(Path("root"), [])
    assert calls == [["git", "--literal-pathspecs", "add", "-f", "--",
                      ROOT_ADDED, SCRIPT_ADDED]]


# ---------------------------------------------------------------------------
# What the rollback reads from git, and the hint `apply` ends with
# ---------------------------------------------------------------------------


def a_repository_on(tmp_path: Path, env: dict, start: str) -> Path:
    """A repository with one commit and HEAD on a branch called `start`.
    The name is handed to git as the bytes it is, so a file system or a
    command-line codec that is not UTF-8 cannot change which branch this is."""
    work = tmp_path / "root"
    work.mkdir()

    def run(*args: str) -> bytes:
        return git_bytes(env, *args, cwd=work)

    run("init", "-q")
    (work / "a.md").write_bytes(b"a\n")
    run("add", "--", "a.md")
    run("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "one")
    run("checkout", "-q", "-b", os.fsdecode(start.encode("utf-8")))
    return work


#: Names HEAD may be on that a locale codec misreads. `é` is `c3 a9` in
#: UTF-8, which the ANSI code page (cp1252) reads as TWO letters, `Ã©`, so
#: `feature/café` comes back as another branch's name; `Ý` is `c3 9d`, and
#: cp1252 leaves `9d` undefined, so its strict decode RAISES. Both are legal
#: file names on Windows, macOS and Linux, so both run everywhere.
NON_ASCII_STARTS = [pytest.param("feature/café", id="read-as-other-letters"),
                    pytest.param("Ýmir", id="read-as-an-error")]


def under_the_ansi_code_page(patched) -> None:
    """`subprocess.run(..., text=True)` as Windows runs it when
    `PYTHONUTF8` is not set and no `encoding` is named: the ANSI code page,
    strictly. CI's Windows job sets `PYTHONUTF8=1`, which HIDES the
    difference, and Linux has no such default to switch to, so the codec is
    imposed on every text-mode call that does not name its own — argument
    encoding is left alone, which is what Windows does too (git receives
    UTF-16 and converts it)."""
    real = subprocess.run

    def run(*args, **kwargs):
        if (kwargs.get("text") or kwargs.get("universal_newlines")) \
                and not kwargs.get("encoding"):
            kwargs["encoding"] = "cp1252"
        return real(*args, **kwargs)

    patched.setattr(subprocess, "run", run)


@pytest.mark.parametrize("start", NON_ASCII_STARTS)
def test_a_non_ascii_start_branch_is_returned_to_under_the_ansi_code_page(
        tmp_path, quiet, monkeypatch, start):
    """HEAD IS READ AS UTF-8, NOT WITH THE LOCALE'S CODEC. `_symbolic_head`
    asks `_git_answer`, which decoded with the locale: on Windows a start
    branch `feature/café` was kept as `feature/cafÃ©`, the switch back named
    a branch that does not exist, and the rollback deleted the branch HEAD
    was on and printed a fix for the wrong name. The two names here fail two
    ways under that codec, the second by raising out of an answer that must
    not. The scenario is `apply --branch`'s failure at its smallest: the
    branch is made, then the undo runs."""
    for name, value in quiet.items():
        monkeypatch.setenv(name, value)
    update_shape = load(UPDATE, "update_shape_non_ascii_start")
    work = a_repository_on(tmp_path, quiet, start)
    new = "shape/update-x"
    with monkeypatch.context() as patched:
        under_the_ansi_code_page(patched)
        try:
            misread = subprocess.run(
                ["git", "symbolic-ref", "HEAD"], cwd=str(work),
                capture_output=True, text=True, check=False).stdout
        except UnicodeDecodeError:
            misread = None
        assert misread != f"refs/heads/{start}\n", (
            "the simulated code page reads the name correctly, so nothing "
            "here would catch a decode that does not name UTF-8")

        assert update_shape._symbolic_head(work) == f"refs/heads/{start}"
        ledger = update_shape.Rollback(work)
        ledger.new_branch(new)
        assert ledger.branch[1] == start, ledger.branch
        done: list[str] = []
        left: list[str] = []

        ledger._undo_branch(done, left)

    assert left == [], left
    assert f"switched  HEAD back to {start}" in done, done
    assert any(line.startswith(f"deleted   {new}") for line in done), done
    assert git_bytes(quiet, "symbolic-ref", "HEAD", cwd=work) \
        == b"refs/heads/" + start.encode("utf-8") + b"\n"
    assert subprocess.run(
        ["git", "show-ref", "--quiet", "--verify", f"refs/heads/{new}"],
        cwd=str(work), capture_output=True, check=False,
        env={**os.environ, **quiet}).returncode != 0, (
        "the branch this run created is gone")


#: What the child does: load the tool the way the tests do and read HEAD
#: through the function the rollback uses. It prints ONE line of ASCII JSON,
#: so a stdout that cannot encode `é` is not what is being measured, and the
#: branch's name travels back as `ascii()`'s escapes. A codec is fixed when
#: an interpreter starts, so this process cannot reproduce a C locale by
#: setting an environment variable afterwards.
CHILD = r"""
import importlib.util, json, locale, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("update_shape_c_locale", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
answer = {"codec": locale.getpreferredencoding(False)}
try:
    answer["head"] = ascii(module._symbolic_head(Path(sys.argv[2])))
except Exception as exc:
    answer["raised"] = type(exc).__name__ + ": " + str(exc)
print(json.dumps(answer))
"""


@pytest.mark.skipif(
    os.name == "nt",
    reason="a C locale is a POSIX idea: Windows decodes with the ANSI code "
           "page, which the in-process test above imposes on every platform")
@pytest.mark.parametrize("start", NON_ASCII_STARTS)
def test_head_is_read_as_utf8_by_an_interpreter_started_under_a_c_locale(
        tmp_path, quiet, start):
    """The same read, for real: a child started with `LC_ALL=C PYTHONUTF8=0`,
    whose text mode is ASCII. Only HEAD's name is asked for — the switch back
    itself cannot run in such a child on POSIX, where an `é` is not a
    command-line argument — which is all `_git_answer` decides."""
    work = a_repository_on(tmp_path, quiet, start)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("LC_", "LANG", "PYTHONUTF8",
                                  "PYTHONIOENCODING", "PYTHONCOERCE"))}
    env.update(quiet)
    env.update({"LC_ALL": "C", "PYTHONUTF8": "0",
                "PYTHONDONTWRITEBYTECODE": "1"})
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(UPDATE), str(work)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, f"the child died:\n{stderr}"
    answer = json.loads(proc.stdout.decode("ascii"))
    if codecs.lookup(answer["codec"]).name == "utf-8":
        pytest.skip(f"this platform reads a child's output as "
                    f"{answer['codec']} under LC_ALL=C PYTHONUTF8=0, so there "
                    "is no non-UTF-8 locale to reproduce the failure in")
    assert "raised" not in answer, (
        f"`_symbolic_head` raised under {answer['codec']}: {answer['raised']}")
    assert answer["head"] == ascii(f"refs/heads/{start}"), answer


def hold_the_index_once_the_branch_exists(root) -> None:
    """A `post-checkout` hook that takes `.git/index.lock` the first time it
    runs and keeps it — an editor's `git status` caught holding the index.
    `checkout -b` has finished with the index by the time the hook runs, so
    the branch exists and HEAD is on it; the staging that follows then finds
    the lock, and so does the switch back. One shot: the marker keeps the
    hook from taking the lock again after the test has cleared it."""
    hooks = root / ".git" / "refusing-hooks"
    hooks.mkdir()
    hook = hooks / "post-checkout"
    hook.write_bytes(b"#!/bin/sh\n"
                     b"[ -e .git/refusing-hooks/held ] && exit 0\n"
                     b": > .git/refusing-hooks/held\n"
                     b": > .git/index.lock\n"
                     b"exit 0\n")
    hook.chmod(0o755)
    git("config", "core.hooksPath", hooks.as_posix(), cwd=root)


def steps_of(command: str) -> list[list[str]]:
    """A line of `&&`-joined commands, split the way a POSIX shell would."""
    steps: list[list[str]] = [[]]
    for word in shlex.split(command):
        if word == "&&":
            steps.append([])
        else:
            steps[-1].append(word)
    return steps


def test_a_switch_back_git_will_not_make_leaves_the_branch_head_is_on(
        root, standard, quiet):
    """THE BRANCH HEAD IS ON IS NOT DELETED. The failure here is the one the
    review reproduced at the git level: the branch is made, then `.git/
    index.lock` appears — a concurrent `git status` from an editor — so the
    staging fails and the switch back exits 128. `update-ref -d` does not
    take that lock, and used to delete the branch under HEAD all the same:
    HEAD named a ref with no commit, and `git status` said "No commits yet"
    over a repository with a history. Now the branch is left, HEAD is left
    on it, both are listed, and the printed line switches FIRST — `git
    branch -D` refuses the branch that is checked out — and then deletes;
    run once the lock is gone, it makes the tree whole."""
    hold_the_index_once_the_branch_exists(root)
    operators_staged_work(root)
    commit = git("rev-parse", "HEAD", cwd=root).stdout.strip()
    checked = check(root, standard, quiet)
    before = snapshot(root, quiet)

    result = apply(root, standard, quiet, *ADD_ARGS, "--branch", BRANCH)

    assert result.returncode == 2, result.stdout + result.stderr
    assert (f"REFUSED staging the --add file(s) {', '.join(ADDITIONS)} on "
            f"{BRANCH}") in result.stderr, result.stderr
    assert "index.lock" in result.stderr, (
        "the failure injected is the held index, not some other one")
    assert ("ROLLED BACK IN PART: the tree is NOT as it was. Put back:"
            in result.stderr), result.stderr
    assert f"deleted   {BRANCH}" not in result.stderr, result.stderr
    assert git("symbolic-ref", "HEAD", cwd=root).stdout.strip() \
        == f"refs/heads/{BRANCH}", "the switch back did fail"
    assert git("rev-parse", "--verify", "--quiet", f"refs/heads/{BRANCH}",
               cwd=root).stdout.strip() == commit, (
        "HEAD is on a branch that still names the commit it was made at, "
        "never on one that names nothing")

    heading = "  NOT put back — finish these by hand:\n"
    assert heading in result.stderr, result.stderr
    left = [line.strip() for line in
            result.stderr.split(heading, 1)[1].splitlines()
            if line.startswith("    ")]
    assert len(left) == 2, left
    assert left[0].startswith("HEAD      is not back on main: "), left
    said = (f"branch    {BRANCH}, which this run created, was not deleted "
            "because HEAD is still on it (HEAD would name no commit); "
            "switch first, then delete: ")
    assert left[1].startswith(said), left
    switch, delete = steps_of(left[1][len(said):])
    assert Path(switch[2]).resolve() == root.resolve(), switch
    assert (switch[:2], switch[3:]) == (["git", "-C"], ["checkout", "main"])
    assert (delete[:2], delete[3:]) == (["git", "-C"],
                                        ["branch", "-D", BRANCH])
    assert steps_of(left[0].split(": ", 1)[1]) == [switch], (
        "the HEAD line and the branch line switch the same way")

    (root / ".git" / "index.lock").unlink()
    for step in (switch, delete):
        subprocess.run(step, check=True, capture_output=True,
                       env={**os.environ, **quiet})
    assert_same_tree(before, snapshot(root, quiet))
    assert check(root, standard, quiet).stdout == checked.stdout


def test_the_next_hint_quotes_every_path_and_adds_them_literally(capsys):
    """THE HINT IS A LINE A PERSON PASTES. `add -f` is the dangerous word in
    it: an added name holding `[` pasted bare is a pattern the shell expands
    to an ignored neighbour, and `-f` forces that in. So each path is quoted
    for the shell — the commit's list too, so the line pastes whole — and
    the add is `--literal-pathspecs`, which `force_stage` passes for the same
    reason and which quoting cannot replace: git reads a pathspec as a glob
    itself. Taken apart the way a shell would, the line is exactly three
    commands, whose words are exactly the names."""
    update_shape = load(UPDATE, "update_shape_next_hint")
    added = ["docs/guide[1].md", "docs/shape guide.md", "it's [x].md"]
    paths = sorted({"contracts/shape-pin.yaml", "project.yaml", *added})
    target = "ab" * 20
    args = SimpleNamespace(branch=None, pr=False, push=False)

    update_shape.next_line(Path("root"), args, paths, target, added)

    line = capsys.readouterr().out.strip()
    assert line.startswith("NEXT  "), line
    assert steps_of(line[len("NEXT  "):]) == [
        ["git", "-C", "root", "checkout", "-b", f"shape/update-{target[:12]}"],
        ["git", "-C", "root", "--literal-pathspecs", "add", "-f", "--",
         *added],
        ["git", "-C", "root", "commit", "-m",
         f"Re-sync the shape @ {target[:12]}", "--", *paths]], line

    update_shape.next_line(Path("root"), args, paths, target, [])
    plain = capsys.readouterr().out.strip()
    assert [step[3] for step in steps_of(plain[len("NEXT  "):])] \
        == ["checkout", "commit"], "nothing added, so nothing is staged"


@pytest.mark.skipif(
    os.name == "nt",
    reason="the hint is a POSIX-shell line, which Windows' stock shells do "
           "not run; the test above takes it apart on every platform")
def test_the_next_hint_pasted_into_a_shell_commits_the_named_file_alone(
        root, standard, quiet):
    """THE REVIEW'S REPRODUCTION, WHOLE. An ignored `docs/guide1.md` sits
    beside the added `docs/guide[1].md`, and the hint `apply` prints is
    pasted into `sh` from the root, where a bare `docs/guide[1].md` would be
    expanded to the neighbour. It makes the branch, force-stages the named
    file and commits it — and the neighbour stays out of the index, out of
    the commit and on the disk."""
    exclude = root / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    exclude.write_bytes((exclude.read_bytes() if exclude.is_file() else b"")
                        + f"{GLOB_NEIGHBOUR}\n".encode())
    write_stray(root, GLOB_NEIGHBOUR)
    assert ignored(root, GLOB_NEIGHBOUR, quiet)
    assert not ignored(root, GLOB_ADDED, quiet)
    applied = apply(root, standard, quiet, "--add", GLOB_ADDED,
                    at=standard["c"])
    assert applied.returncode == 0, applied.stdout + applied.stderr
    hints = [line for line in applied.stdout.splitlines()
             if line.startswith("NEXT  ")]
    assert len(hints) == 1, applied.stdout
    hint = hints[0][len("NEXT  "):]
    assert f"add -f -- '{GLOB_ADDED}' &&" in hint, hint

    pasted = subprocess.run(
        ["sh", "-c", hint], cwd=str(root), capture_output=True, text=True,
        check=False, env={**os.environ, **quiet,
                          "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                          "GIT_COMMITTER_NAME": "t",
                          "GIT_COMMITTER_EMAIL": "t@t"})

    assert pasted.returncode == 0, pasted.stderr + pasted.stdout
    assert git("symbolic-ref", "--short", "HEAD", cwd=root).stdout.strip() \
        == f"shape/update-{standard['c'][:12]}"
    assert committed_files(root) == {CHANGED, PIN, MANIFEST, README,
                                     GLOB_ADDED}, (
        "the commit holds the named file and not its glob neighbour")
    assert git("ls-files", "--", GLOB_NEIGHBOUR, cwd=root).stdout == ""
    assert (root / GLOB_NEIGHBOUR).is_file()
