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
    had already staged at the added path), each injected after the copies are
    written: the tree is compared byte for byte, with the index, HEAD and
    every branch, against what it was; the refusal names the step and lists
    what it put back; and `check` then prints exactly what it printed before,
    `upstream-added` rows included, never "nothing to do". A failure AFTER
    the commit lands rolls nothing back, because the commit is the result.
  * A NON-IGNORED ADDITION IS UNCHANGED. The same files reach the same
    commit, and nothing the run did not write is swept into the index.

THE FIXTURE is `tests/test_update_shape.py`'s: a clone of this repository at
A and `Atlas` scaffolded from it into bare repositories on disk, with a
README that ends in a `Shape:` line naming A, so a run moves that line too.
Commit B fixes one copied file and adds three to the assembly root's copy
lists — one at the top level, one executable script in `scripts/`, and one in
a directory the root does not have yet — which is every kind of write the
rollback ledger has to undo. `PYTHONDONTWRITEBYTECODE=1` is set for every run,
because the validators `apply` runs import `scripts/repo_shape.py` from the
root and would otherwise leave `scripts/__pycache__/` behind, which is a
difference in the tree that is not the rollback's. Every git configuration a
run reads comes from `GIT_CONFIG_GLOBAL` pointed at a file the test writes,
so nothing here depends on the excludes or hooks of whoever runs the suite.
No network is used and `gh` is never invoked.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

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
#: The operator whose excludes are a file this test writes (#175).
from test_scaffold_ignored_shape_files import excluding, git_under, ignored

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

BRANCH = "shape/update-ignored"


@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> dict:
    """A clone at A, `Atlas` cut from it with a `Shape:` line naming A, and B
    above them fixing one copied file and adding the three."""
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
    return {"upstream": upstream, "clone": clone, "a": a, "b": b}


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


def apply(root, standard, env, *extra):
    return run_script(UPDATE, "apply", "--root", str(root), "--yes",
                      "--upstream", str(standard["upstream"]),
                      "--at", standard["b"], *extra, env=env)


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
    ("branch-invalid", lambda root: None, "shape/update..ignored",
     "REFUSED creating the branch shape/update..ignored",
     ("kept      HEAD on main, where it started",
      "absent    shape/update..ignored (never created)"), "unstaged"),
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
]


@pytest.mark.parametrize("inject, branch, step, git_lines, never",
                         [case[1:] for case in FAILURES],
                         ids=[case[0] for case in FAILURES])
def test_a_failure_before_the_commit_puts_the_tree_back_and_names_the_step(
        root, standard, quiet, inject, branch, step, git_lines, never):
    inject(root)
    head = git("rev-parse", "HEAD", cwd=root).stdout.strip()[:12]
    checked = check(root, standard, quiet)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    before = snapshot(root, quiet)

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


def test_force_stage_forces_exactly_the_named_paths_and_nothing_else(
        monkeypatch):
    """What reaches git: `add -f` over the paths `--add` named and nothing
    else, never `-A` and never `.`; and with none, no git at all. The same
    helper is the forced half of `stage_written` (#175), so the scaffold and
    `apply --add` spell the forced add one way."""
    calls = []
    monkeypatch.setattr(shape_materialize, "run",
                        lambda args, cwd=None, capture=True: calls.append(args))
    shape_materialize.force_stage(Path("root"), [ROOT_ADDED, SCRIPT_ADDED])
    shape_materialize.force_stage(Path("root"), [])
    assert calls == [["git", "add", "-f", "--", ROOT_ADDED, SCRIPT_ADDED]]
