# SPDX-License-Identifier: Apache-2.0
"""What `update-shape.py apply` says, and does next, when a step AFTER its
commit fails (#204).

`apply --branch --push --pr` makes three acts after a clean rewrite: the
commit, the push, the pull request. Until #204 a failure in either of the last
two reached `cmd_apply`'s one `except CommandFailed` arm, which called every
failure "committing the re-synced shape", printed no NEXT line and did not
flush stdout first. And the run after a failed `gh pr create` found the pin
already at the target, said "nothing to do" and exited 0, so the tool never
opened the pull request it was asked for.

THE UPSTREAM IS A CLONE OF THIS REPOSITORY, the project is scaffolded out of
it into bare repositories in a temporary directory, and every test gets its
own copy of the root AND of its bare remote, so one test's push cannot make
another's non-fast-forward. `gh` is a Python program that logs its argv and
answers from a state directory, so nothing here reaches a network or a real
repository, and no test in this file is skipped for the operating system it
runs on (#334).

HOW A PROGRAM NAMED `gh` REACHES THE CHILD WITHOUT A FILE NAMED `gh`. On
Windows `subprocess.run(["gh", ...])` is `CreateProcess`, which appends `.exe`
to a program name that has no extension (its documented rule) and reads no
shebang: a `#!/bin/sh` script is not a program there, a `gh.cmd` beside it is
not what `gh` names, and a real `gh.exe` further down PATH would be the one
that ran. No file this suite can write without a compiler is a `gh` on that
OS. So the update's child interpreter is started with a `sitecustomize.py`
first on its `PYTHONPATH` (`GH_ON_PATH`) that does the one thing PATH
resolution would have done: a `subprocess.Popen` whose program is `gh` is
started as `python <the stub> <the same arguments>`. Everything after that is
real: the stub is a process, its exit code and its two streams cross real
pipes, and the arguments cross the OS's own command-line quoting. `git`, a
real executable everywhere, is never touched. What this does not exercise is
the OS finding a `gh` by searching PATH; `test_a_gh_missing_from_path_...` and
the in-process tests at the end cover the other half of that, a `gh` it cannot
find.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import REPO, blank_unnamed_pin_sources, git, run_script
from test_update_shape import (CHANGED, CHANGED_SOURCE, PROJECT,
                               UPSTREAM_FIX_LINE, commit_upstream_changes,
                               next_line_of, scaffold_upstream_and_project)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402
from shape_materialize import SHAPE_REPOSITORY, CommandFailed  # noqa: E402

UPDATE = REPO / "update-shape.py"
BRANCH = "shape/update-landing"
PIN = "contracts/shape-pin.yaml"
#: The copied file upstream commit C changes, and only C (#333).
PINS = "scripts/validate-pins.py"
URL = "https://github.invalid/testorg/Atlas/pull/7"
PR_OPEN_NEXT = "NEXT  the pull request is open; ask a human to review and merge it"

#: The stub, as a program: what the shell script it replaces did, in Python,
#: because Python is the one interpreter every CI job has. One line per call,
#: each argument ended by a unit separator, so the log keeps argument
#: boundaries (the `--title` and `--body` values have spaces in them) without
#: a shell-quoting round trip. The log is written as bytes (`\n` on every OS,
#: UTF-8, never the console's code page), and `pr create` fails with exit 97
#: while the state directory holds `create-fails`.
GH_STUB = """\
import os
import sys

URL = "__URL__"
arguments = sys.argv[1:]
state = os.environ["GH_STATE"]
with open(os.environ["GH_LOG"], "ab") as log:
    log.write(b"".join(a.encode("utf-8", "surrogateescape") + b"\\x1f"
                       for a in arguments) + b"\\n")
listing = os.path.join(state, "list")
if arguments[:2] == ["pr", "list"]:
    try:
        with open(listing, "rb") as answer:
            sys.stdout.buffer.write(answer.read())
    except FileNotFoundError:
        sys.stdout.buffer.write(b"[]\\n")
elif arguments[:2] == ["pr", "create"]:
    if os.path.exists(os.path.join(state, "create-fails")):
        sys.stderr.write("HTTP 422: Validation Failed (stub)\\n")
        sys.exit(97)
    sys.stdout.write(URL + "\\n")
    with open(listing, "wb") as answer:
        answer.write(b'[{"state":"OPEN","url":"' + URL.encode() + b'"}]\\n')
else:
    sys.stderr.write("stub gh: unexpected " + " ".join(arguments) + "\\n")
    sys.exit(64)
""".replace("__URL__", URL)

#: What stands where `gh` would be found. Python imports `sitecustomize` at
#: start-up from `PYTHONPATH`, so the update's child interpreter, and the
#: validators it runs, load this before the tool's first line. A program named
#: `gh` (by its file name, as `check_program` reads one) is started as the
#: stub run through this interpreter; every other program is untouched, and
#: with no `GH_STUB` in the environment the module does nothing at all.
GH_ON_PATH = """\
import os
import subprocess
import sys

_STUB = os.environ.get("GH_STUB")


class _Popen(subprocess.Popen):
    def __init__(self, args, *rest, **kwargs):
        if (_STUB and isinstance(args, (list, tuple)) and args
                and os.path.basename(args[0]) in ("gh", "gh.exe")):
            args = [sys.executable, _STUB, *args[1:]]
        super().__init__(args, *rest, **kwargs)


subprocess.Popen = _Popen
"""


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A, its bare remotes, and an upstream moved to B, then
    to C, which changes `PINS` and nothing else."""
    base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-landing")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    commit_c = commit_upstream_changes(
        upstream, "Fix the pins validator",
        {f"templates/assembly-root/{PINS}": UPSTREAM_FIX_LINE})
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b, "c": commit_c,
            "remote": base / "remotes" / f"{PROJECT}.git"}


@pytest.fixture
def root(project, tmp_path):
    """A private copy of the root, pushing to a private copy of its remote.

    `refs/remotes/origin/main` comes with the copy, which is the ref
    `_awaits_its_pull_request` compares the branch's pin against."""
    remote = tmp_path / f"{PROJECT}.git"
    shutil.copytree(project["remote"], remote, symlinks=True)
    target = tmp_path / PROJECT
    shutil.copytree(project["clone"], target, symlinks=True)
    git("remote", "set-url", "origin", str(remote), cwd=target)
    return SimpleNamespace(path=target, remote=remote)


@pytest.fixture
def gh(tmp_path):
    """The `gh` stub in the update's child, and what it was asked."""
    binary = tmp_path / "gh-stub"
    binary.mkdir()
    stub = binary / "gh_stub.py"
    stub.write_text(GH_STUB, encoding="utf-8")
    (binary / "sitecustomize.py").write_text(GH_ON_PATH, encoding="utf-8")
    state = tmp_path / "gh-state"
    state.mkdir()
    log = tmp_path / "gh.log"

    def calls() -> list:
        if not log.exists():
            return []
        return [line.split("\x1f")[:-1]
                for line in log.read_text(encoding="utf-8").splitlines()]

    def failing(fails: bool) -> None:
        marker = state / "create-fails"
        if fails:
            marker.touch()
        elif marker.exists():
            marker.unlink()

    def answer(pulls: list) -> None:
        (state / "list").write_text(json.dumps(pulls) + "\n",
                                    encoding="utf-8")

    def forget() -> None:
        if log.exists():
            log.unlink()

    inherited = os.environ.get("PYTHONPATH")
    path = [str(binary), inherited] if inherited else [str(binary)]
    env = {"PYTHONPATH": os.pathsep.join(path), "GH_STUB": str(stub),
           "GH_LOG": str(log), "GH_STATE": str(state)}
    return SimpleNamespace(env=env, calls=calls, failing=failing,
                           answer=answer, forget=forget)


def apply(root, project, *extra, env=None, at=None):
    return run_script(UPDATE, "apply", "--root", str(root.path), "--yes",
                      "--upstream", str(project["upstream"]),
                      "--at", at or project["b"], *extra, env=env)


def listing(branch: str = BRANCH) -> list:
    """The `gh pr list` a re-run asks before it pushes or opens anything."""
    return ["pr", "list", "--repo", f"testorg/{PROJECT}", "--head", branch,
            "--state", "all", "--json", "state,url"]


def the_commit_stands(root, project) -> str:
    """The re-pin is COMMITTED on the branch and nothing was rolled back:
    the checkout is on the branch, HEAD's pin names B, and the tree holds
    exactly HEAD's bytes. Returns HEAD."""
    path = root.path
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=path).stdout.strip() == BRANCH
    assert load_yaml(path / PIN)["commit"].lower() == project["b"]
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=path).stdout.split() == [PIN, "project.yaml", CHANGED]
    assert git("status", "--porcelain", cwd=path).stdout == "", (
        "nothing was rolled back under the commit")
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


def on_the_remote(root, branch: str = BRANCH) -> str | None:
    proc = git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}",
               cwd=root.remote, check=False)
    return proc.stdout.strip() or None


def commits_on_the_branch(root) -> int:
    return int(git("rev-list", "--count", "origin/main..HEAD",
                   cwd=root.path).stdout.strip())


# --- the pull request fails after the commit and the push -----------------

def test_a_failed_pull_request_is_named_and_its_next_line_is_the_command(
        root, project, gh):
    """THE ISSUE'S FIRST RUN. The commit and the push landed, so the refusal
    names the step that failed, says what stands, and ends on a NEXT line
    that is the very `gh pr create` that failed — title and body included,
    quoted to survive being pasted."""
    gh.failing(True)
    result = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED opening the pull request for {BRANCH}" in result.stderr
    assert "committing the re-synced shape" not in result.stderr
    assert "origin has it" in result.stderr
    assert "nothing was rolled back" in result.stderr
    assert f"`apply --pr` run again on {BRANCH}" in result.stderr
    assert f"committed on {BRANCH}" in result.stdout
    assert f"pushed {BRANCH} to origin" in result.stdout

    calls = gh.calls()
    assert len(calls) == 1, calls
    assert calls[0][:2] == ["pr", "create"], calls
    create = ["gh", *calls[0]]
    line = next_line_of(result.stdout)
    assert line == "NEXT  " + shlex.join(create)
    assert shlex.split(line)[1:] == create, "it pastes as the same argv"
    assert create[create.index("--head") + 1] == BRANCH

    head = the_commit_stands(root, project)
    assert on_the_remote(root) == head


def test_a_failed_pull_request_on_an_unpushed_branch_pushes_first(
        root, project, gh):
    """`--pr` WITHOUT `--push`: the branch never reached origin, so the NEXT
    line pushes before it opens the pull request, and the re-run it promises
    is the one that pushes too, `apply --push --pr`, since a re-run with
    `--pr` alone would ask `gh` for a pull request from a branch origin
    lacks."""
    gh.failing(True)
    result = apply(root, project, "--branch", BRANCH, "--pr", env=gh.env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED opening the pull request for {BRANCH}" in result.stderr
    assert "origin does not have it yet" in result.stderr
    assert f"`apply --push --pr` run again on {BRANCH}" in result.stderr
    assert f"pushed {BRANCH}" not in result.stdout

    calls = gh.calls()
    assert len(calls) == 1, calls
    assert calls[0][:2] == ["pr", "create"], calls
    push = shlex.join(["git", "-C", str(root.path), "push", "-u", "--",
                       "origin", BRANCH])
    assert next_line_of(result.stdout) == (
        f"NEXT  {push} && " + shlex.join(["gh", *calls[0]]))
    the_commit_stands(root, project)
    assert on_the_remote(root) is None


def test_the_commit_and_the_push_print_above_the_refusal_in_one_log(
        root, project, gh):
    """STDOUT IS FLUSHED BEFORE THE REFUSAL. With both streams in one pipe,
    main printed the REFUSED block above the "committed on" and "pushed"
    lines it was refusing after (#204, measured: line 13 against 21)."""
    gh.failing(True)
    env = blank_unnamed_pin_sources(
        {**os.environ, **gh.env, "LANES_LANE": ""}, gh.env)
    proc = subprocess.run(
        [sys.executable, str(UPDATE), "apply", "--root", str(root.path),
         "--yes", "--upstream", str(project["upstream"]),
         "--at", project["b"], "--branch", BRANCH, "--push", "--pr"],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, env=env, check=False)
    assert proc.returncode == 2, proc.stdout
    lines = proc.stdout.splitlines()
    found = {prefix: [i for i, line in enumerate(lines)
                      if line.lstrip().startswith(prefix)]
             for prefix in ("committed on", "pushed", "REFUSED", "NEXT")}
    assert all(len(at) == 1 for at in found.values()), (found, proc.stdout)
    order = [at[0] for at in found.values()]
    assert order == sorted(order), (found, proc.stdout)


def test_a_rerun_on_the_branch_opens_the_missing_pull_request(root, project,
                                                              gh):
    """THE ISSUE'S SECOND RUN. Nothing is left to write, and the pull request
    `--pr` asked for is still missing, so the same command opens it: `gh` is
    asked first, the push is a no-op, and the `gh pr create` is the one the
    first run tried. No second commit. A third run finds it open and opens
    no second one."""
    gh.failing(True)
    first = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert first.returncode == 2, first.stdout + first.stderr
    head = the_commit_stands(root, project)
    create = gh.calls()[0]

    gh.failing(False)
    gh.forget()
    second = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env)
    assert second.returncode == 0, second.stdout + second.stderr
    assert "nothing to do" not in second.stdout
    assert f"nothing to write: every copied file matches {SHAPE_REPOSITORY}" \
        in second.stdout
    assert f"pull request {URL}" in second.stdout
    assert next_line_of(second.stdout) == PR_OPEN_NEXT
    assert gh.calls() == [listing(), create], (
        "asked first, then the very command the first run tried")
    assert git("rev-parse", "HEAD", cwd=root.path).stdout.strip() == head
    assert commits_on_the_branch(root) == 1, "no second commit"
    assert on_the_remote(root) == head

    gh.forget()
    third = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert third.returncode == 0, third.stdout + third.stderr
    assert f"pull request {URL} is already open" in third.stdout
    assert next_line_of(third.stdout) == PR_OPEN_NEXT
    assert gh.calls() == [listing()], "no second pull request"
    assert commits_on_the_branch(root) == 1


@pytest.mark.parametrize("state", ["MERGED", "CLOSED"])
def test_a_branch_whose_pull_request_was_merged_or_closed_gets_no_second_one(
        root, project, gh, state):
    """`gh` IS ASKED BEFORE ANYTHING IS PUSHED. GitHub deletes a merged
    branch; a re-run that pushed first would have put it back. The branch is
    deleted on the remote here to show that it stays deleted."""
    gh.failing(True)
    first = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert first.returncode == 2, first.stdout + first.stderr
    git("update-ref", "-d", f"refs/heads/{BRANCH}", cwd=root.remote)

    gh.failing(False)
    gh.forget()
    gh.answer([{"state": state, "url": URL}])
    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert f"pull request {URL} for {BRANCH} is {state.lower()}; a re-run " \
        "opens no second one" in rerun.stdout
    assert gh.calls() == [listing()]
    assert on_the_remote(root) is None, "nothing was pushed"


# --- the push fails after the commit ----------------------------------------

@pytest.mark.parametrize("flags", [("--push",), ("--push", "--pr")],
                         ids=["push", "push-pr"])
def test_a_failed_push_is_named_and_its_next_line_pushes_first(root, project,
                                                               tmp_path,
                                                               flags):
    """A PUSH ORIGIN REFUSES is the same arm's other half: main called it
    "committing the re-synced shape" as well. Named now, the commit kept,
    and the NEXT line pushes and then opens the pull request — under `--pr`
    with the command `--pr` would have run, without it with the bare form
    the `--branch` NEXT line prints. `gh` is never reached, so this runs on
    every platform."""
    git("remote", "set-url", "--push", "origin",
        str(tmp_path / "no-such-remote.git"), cwd=root.path)
    result = apply(root, project, "--branch", BRANCH, *flags)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED pushing {BRANCH}" in result.stderr
    assert f"git push -q -u -- origin {BRANCH}" in result.stderr, (
        "`--` ends git's options before the branch")
    assert "committing the re-synced shape" not in result.stderr
    assert "origin does not have it yet" in result.stderr
    assert "nothing was rolled back" in result.stderr
    assert f"committed on {BRANCH}" in result.stdout
    assert f"pushed {BRANCH}" not in result.stdout

    line = next_line_of(result.stdout)
    push = shlex.join(["git", "-C", str(root.path), "push", "-u", "--",
                       "origin", BRANCH])
    assert line.startswith(f"NEXT  {push} && gh pr create "), line
    if "--pr" in flags:
        assert f"--repo testorg/{PROJECT} --base main --head {BRANCH} " \
            "--title " in line
        assert f"`apply --push --pr` run again on {BRANCH}" in result.stderr
    else:
        assert line.endswith(f"&& gh pr create --repo testorg/{PROJECT} "
                             f"--base main --head {BRANCH}"), line
        assert "run again" not in result.stderr, (
            "a re-run without --pr finishes nothing, so none is promised")
    the_commit_stands(root, project)
    assert on_the_remote(root) is None


def test_a_rerun_after_a_failed_push_pushes_and_opens_the_pull_request(
        root, project, gh, tmp_path):
    git("remote", "set-url", "--push", "origin",
        str(tmp_path / "no-such-remote.git"), cwd=root.path)
    first = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert first.returncode == 2, first.stdout + first.stderr
    assert gh.calls() == [], "the pull request was never attempted"
    head = the_commit_stands(root, project)

    git("remote", "set-url", "--push", "origin", str(root.remote),
        cwd=root.path)
    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert f"pushed {BRANCH} to origin" in rerun.stdout
    assert f"pull request {URL}" in rerun.stdout
    assert [call[:2] for call in gh.calls()] == [["pr", "list"],
                                                 ["pr", "create"]]
    assert on_the_remote(root) == head
    assert commits_on_the_branch(root) == 1


# --- a failure BEFORE the commit is still rolled back (#202) ----------------

def refuse_the_commit(root) -> None:
    """A pre-commit hook that says no, as `test_update_shape_add_ignored.py`
    injects it: `core.hooksPath` in the repository's own config, and a
    shebang script, which Git for Windows runs through its own `sh`."""
    hooks = root.path / ".git" / "refusing-hooks"
    hooks.mkdir()
    hook = hooks / "pre-commit"
    hook.write_bytes(b"#!/bin/sh\necho 'pre-commit: not this commit' >&2\n"
                     b"exit 1\n")
    hook.chmod(0o755)
    git("config", "core.hooksPath", hooks.as_posix(), cwd=root.path)


def test_a_failure_before_the_commit_under_push_and_pr_is_rolled_back(
        root, project, gh):
    """THE COMMIT IS WHERE ROLLING BACK STOPS, FROM BOTH SIDES. #202 rolls
    back a branch, a stage or a commit that fails; this PR keeps the commit
    when a push or a pull request fails after it. With `--push --pr` passed,
    a commit a hook refuses is still #202's: the copies, the pin and the
    branch are put back and the step is named, and nothing of the landing
    happens — no push, no `gh`, no NEXT line, no re-run promised — because
    there is no commit for any of it to finish. `gh` is never reached, so
    this runs on every platform."""
    refuse_the_commit(root)
    head = git("rev-parse", "HEAD", cwd=root.path).stdout

    result = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED committing the re-synced shape on {BRANCH}" \
        in result.stderr, result.stderr
    assert ("ROLLED BACK: every byte this command wrote has been put back"
            in result.stderr), result.stderr
    for rel in (PIN, "project.yaml", CHANGED):
        assert f"restored  {rel}" in result.stderr, result.stderr
    assert "switched  HEAD back to main" in result.stderr, result.stderr
    assert f"deleted   {BRANCH}" in result.stderr, result.stderr
    assert "nothing was rolled back" not in result.stderr
    assert "run again" not in result.stderr
    assert f"committed on {BRANCH}" not in result.stdout
    assert "pushed" not in result.stdout
    assert "NEXT" not in result.stdout, result.stdout
    assert gh.calls() == []
    assert on_the_remote(root) is None
    assert git("rev-parse", "HEAD", cwd=root.path).stdout == head
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root.path).stdout.strip() == "main"
    assert git("status", "--porcelain", cwd=root.path).stdout == ""
    assert git("for-each-ref", "--format=%(refname)", "refs/heads/",
               cwd=root.path).stdout.split() == ["refs/heads/main"]


def test_the_same_command_after_a_rolled_back_commit_lands_and_opens(
        root, project, gh):
    """ROLLED BACK, THE NEXT RUN IS THE FIRST RUN AGAIN. With the hook gone
    the same `apply --branch --push --pr` has work to write, so it is not
    the re-run `_awaits_its_pull_request` recognises: it commits once,
    pushes, and opens the pull request with the one `gh pr create` the first
    run path makes, asking `gh pr list` nothing."""
    refuse_the_commit(root)
    failed = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env)
    assert failed.returncode == 2, failed.stdout + failed.stderr
    git("config", "--unset", "core.hooksPath", cwd=root.path)

    result = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to" not in result.stdout
    assert f"committed on {BRANCH}" in result.stdout
    assert f"pushed {BRANCH} to origin" in result.stdout
    assert f"pull request {URL}" in result.stdout
    assert next_line_of(result.stdout) == PR_OPEN_NEXT
    assert [call[:2] for call in gh.calls()] == [["pr", "create"]]
    head = the_commit_stands(root, project)
    assert commits_on_the_branch(root) == 1
    assert on_the_remote(root) == head


# --- what does not change ---------------------------------------------------

@pytest.mark.parametrize("flags", [(), ("--push",)], ids=["branch", "push"])
def test_without_pr_a_rerun_on_the_branch_is_still_nothing_to_do(
        root, project, gh, flags):
    """No `--pr`, no re-run behaviour: the second run prints main's one line
    and exits 0, and `gh` is never asked."""
    first = apply(root, project, "--branch", BRANCH, *flags, env=gh.env)
    assert first.returncode == 0, first.stdout + first.stderr
    again = apply(root, project, "--branch", BRANCH, *flags, env=gh.env)
    assert again.returncode == 0, again.stdout + again.stderr
    assert again.stdout == (
        f"nothing to do: every copied file matches {SHAPE_REPOSITORY} @ "
        f"{project['b'][:12]}, which the pin already names\n")
    assert again.stderr == ""
    assert gh.calls() == []


def test_a_branch_that_proposes_no_repin_is_nothing_to_do_under_pr(
        root, project, gh):
    """A BRANCH WITH COMMITS IS NOT A PULL REQUEST OWED. The root is pinned
    at A and asked for A, on a branch carrying an unrelated commit: its pin
    is the one `origin/main` holds, so there is nothing for a pull request to
    propose, and `--pr` does not invent one."""
    git("checkout", "-q", "-b", BRANCH, cwd=root.path)
    (root.path / "notes.txt").write_text("somebody's work\n",
                                         encoding="utf-8")
    git("add", "--", "notes.txt", cwd=root.path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Unrelated work", "--", "notes.txt", cwd=root.path)
    result = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                   env=gh.env, at=project["a"])
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        f"nothing to do: every copied file matches {SHAPE_REPOSITORY} @ "
        f"{project['a'][:12]}, which the pin already names\n")
    assert gh.calls() == []
    assert on_the_remote(root) is None


def test_a_rerun_from_another_branch_is_still_nothing_to_do(root, project,
                                                           gh):
    """THE RE-RUN ACTS ONLY ON THE BRANCH CHECKED OUT. A checkout that moved
    off `--branch` after the failed run, here onto a second branch at the
    same commit, so the pin it holds still differs from `origin/main`'s, gets
    main's "nothing to do", and `gh` is never asked: the tool pushes and opens
    nothing for a branch it is not standing on."""
    gh.failing(True)
    first = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert first.returncode == 2, first.stdout + first.stderr
    git("checkout", "-q", "-b", "elsewhere", cwd=root.path)

    gh.failing(False)
    gh.forget()
    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)
    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert rerun.stdout == (
        f"nothing to do: every copied file matches {SHAPE_REPOSITORY} @ "
        f"{project['b'][:12]}, which the pin already names\n")
    assert gh.calls() == []


def test_a_rerun_naming_the_tracking_branch_pushes_nothing(root, project,
                                                         gh):
    """`--branch <tracking>` IS NEVER A PULL REQUEST OWED. Here main itself
    carries a local re-pin commit, made from an in-place `apply`, so its pin
    is not the one `origin/main` holds. `apply --branch main --push --pr`
    still finds nothing to do: it asks `gh` nothing and pushes nothing,
    because a pull request from the tracking branch onto itself is not one
    to open, and pushing it would be a push to the default branch."""
    in_place = apply(root, project, env=gh.env)
    assert in_place.returncode == 0, in_place.stdout + in_place.stderr
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-a",
        "-m", "Re-pin in place", cwd=root.path)
    landed = git("rev-parse", "refs/heads/main", cwd=root.remote).stdout

    result = apply(root, project, "--branch", "main", "--push", "--pr",
                   env=gh.env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == (
        f"nothing to do: every copied file matches {SHAPE_REPOSITORY} @ "
        f"{project['b'][:12]}, which the pin already names\n")
    assert gh.calls() == []
    assert git("rev-parse", "refs/heads/main",
               cwd=root.remote).stdout == landed, "nothing was pushed"


# --- `--branch` is checked before anything runs ------------------------------

ALPHABET = "must start with a letter or a digit"
GIT_SAYS = "`git check-ref-format --branch` refuses it"


@pytest.mark.parametrize("branch, why", [
    ("-shape", ALPHABET),
    ("--upload-pack=touch", ALPHABET),
    ("shape/a b", ALPHABET),
    ("shape/x@{1}", ALPHABET),
    ("shape/a..b", GIT_SAYS),
    ("shape/x.lock", GIT_SAYS),
    ("shape/.x", GIT_SAYS),
    ("shape//x", GIT_SAYS),
    ("shape/x/", GIT_SAYS),
], ids=["leading-dash", "option", "space", "at-brace", "dot-dot", "dot-lock",
        "dot-part", "double-slash", "trailing-slash"])
def test_a_branch_git_would_not_create_is_refused_before_anything_runs(
        root, project, gh, branch, why):
    """`--branch` BECOMES `git` AND `gh` ARGUMENTS and a word in a NEXT line
    somebody pastes, the re-run's included, so `main` checks it before
    anything is read, written or run: the alphabet first, so nothing that
    reads as an option reaches git, then `git check-ref-format --branch`.
    `--branch=<value>` is how a value starting with `-` gets past argparse."""
    head = git("rev-parse", "HEAD", cwd=root.path).stdout
    result = apply(root, project, f"--branch={branch}", "--push", "--pr",
                   env=gh.env)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED update-branch-invalid: --branch {branch!r} "), result.stderr
    assert why in result.stderr
    assert "Remediation: pass a branch name such as `shape/update-<sha>`" \
        in result.stderr
    assert result.stdout == "", "refused before anything was read or written"
    assert git("rev-parse", "HEAD", cwd=root.path).stdout == head
    assert git("status", "--porcelain", cwd=root.path).stdout == ""
    assert git("for-each-ref", "--format=%(refname)", "refs/heads/",
               cwd=root.path).stdout.split() == ["refs/heads/main"]
    assert gh.calls() == []


def test_a_bad_branch_is_refused_even_with_nothing_to_write(root, project, gh):
    """THE CHECK DOES NOT WAIT FOR WORK. Pinned at A and asked for A, main
    answered "nothing to do" and exit 0 whatever `--branch` said; that path
    can now push the branch and hand it to `gh`, so a value refused on a run
    with work is refused on this one too."""
    result = apply(root, project, "--branch=-shape", "--push", "--pr",
                   env=gh.env, at=project["a"])
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED update-branch-invalid: --branch '-shape' "), result.stderr
    assert result.stdout == ""
    assert gh.calls() == []


@pytest.mark.parametrize("branch", ["shape/update-landing", "shape/update-v1.2",
                                    "lane-3/shape+fix@eagle", "x"])
def test_a_branch_git_would_create_is_taken_as_written(update_shape, branch):
    """A NAME WITH A `/` IS THE ORDINARY CASE, and so is the rest of the
    alphabet `checked_value` always allowed: each is returned unchanged."""
    assert update_shape.checked_branch(branch) == branch


# --- `gh` is not installed ----------------------------------------------------

GH_MISSING = "`gh` could not be started ("


def test_a_gh_missing_from_path_is_the_step_that_failed_on_both_runs(
        root, project):
    """`gh` NOT INSTALLED is the likeliest way `gh pr create` fails on a
    fresh machine, and `subprocess` raises for it instead of exiting: main
    and the first cut of #204 both ended in a traceback, exit 1, after the
    commit and the push. Now it is the named step, exit 127 in the block,
    the NEXT line is the `gh pr create` to run once `gh` is installed, and a
    re-run still without it says the same about its own first `gh` call.

    PATH is git's directory and Python's, nothing else. Where `gh` lives
    beside one of them (Linux runners put all three in /usr/bin) no PATH
    can hide it, and the in-process test after this one covers both runs."""
    git_dir = os.path.dirname(shutil.which("git"))
    path = os.pathsep.join(dict.fromkeys(
        [git_dir, os.path.dirname(sys.executable)]))
    if shutil.which("gh", path=path):
        pytest.skip("gh is installed beside git or Python here")
    env = {"PATH": path}
    first = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=env)
    assert first.returncode == 2, first.stdout + first.stderr
    assert "Traceback" not in first.stderr, first.stderr
    assert f"REFUSED opening the pull request for {BRANCH}" in first.stderr
    assert GH_MISSING in first.stderr
    assert "    exit 127" in first.stderr
    line = next_line_of(first.stdout)
    assert line.startswith(f"NEXT  gh pr create --repo testorg/{PROJECT} "
                           f"--base main --head {BRANCH} --title "), line
    head = the_commit_stands(root, project)
    assert on_the_remote(root) == head

    again = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=env)
    assert again.returncode == 2, again.stdout + again.stderr
    assert "Traceback" not in again.stderr, again.stderr
    assert f"REFUSED asking gh for {BRANCH}'s pull request" in again.stderr
    assert GH_MISSING in again.stderr
    assert next_line_of(again.stdout) == line
    assert commits_on_the_branch(root) == 1


# --- the same two runs in-process, on every platform -------------------------

@pytest.fixture
def update_shape():
    spec = importlib.util.spec_from_file_location("update_shape_landing",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_failed_pull_request_and_its_rerun_in_process(
        root, project, update_shape, monkeypatch, capsys):
    """THE SAME TWO RUNS WITH NO SUBPROCESS FOR `gh`: stubbed at
    `update_shape.run`, the one function every command goes through, and
    `git` — the commit and the push — run for real. Added (#227) as the
    Windows job's coverage while the runs above were skipped there; they run
    there now (#334) and this one stays, with no process for `gh` at all."""
    real = update_shape.run
    calls: list = []
    fails = [True]

    def run(command, *args, **kwargs):
        if command[0] != "gh":
            return real(command, *args, **kwargs)
        calls.append(list(command))
        if command[1:3] == ["pr", "list"]:
            return "[]"
        if fails[0]:
            raise CommandFailed(command, kwargs.get("cwd"), 97,
                                "HTTP 422: Validation Failed (stub)")
        return URL

    monkeypatch.setattr(update_shape, "run", run)
    for name, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                        ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                        ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                        ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid"),
                        ("LANES_LANE", "")):
        monkeypatch.setenv(name, value)
    argv = ["apply", "--root", str(root.path), "--yes",
            "--upstream", str(project["upstream"]), "--at", project["b"],
            "--branch", BRANCH, "--push", "--pr"]

    assert update_shape.main(argv) == 2
    out, err = capsys.readouterr()
    assert f"REFUSED opening the pull request for {BRANCH}" in err
    assert len(calls) == 1
    assert next_line_of(out) == "NEXT  " + shlex.join(calls[0])
    head = the_commit_stands(root, project)
    assert on_the_remote(root) == head

    fails[0] = False
    assert update_shape.main(argv) == 0
    out, err = capsys.readouterr()
    assert next_line_of(out) == PR_OPEN_NEXT, out + err
    assert calls[1] == ["gh", *listing()]
    assert calls[2] == calls[0]
    assert commits_on_the_branch(root) == 1


def test_a_gh_that_cannot_be_started_in_process(root, project, update_shape,
                                                monkeypatch, capsys):
    """A MISSING `gh`, WHERE NO PATH CAN HIDE ONE: `update_shape.run` raises
    for every `gh` call exactly as `subprocess.run` does when the program is
    not on PATH, and `git` runs for real. The first run and the re-run each
    name their step and end on the same `gh pr create`. The subprocess test
    before it skips where `gh` lives beside `git` or Python, which a Linux
    runner's `/usr/bin` is."""
    real = update_shape.run
    calls: list = []

    def run(command, *args, **kwargs):
        if command[0] != "gh":
            return real(command, *args, **kwargs)
        calls.append(list(command))
        raise FileNotFoundError(2, "No such file or directory", "gh")

    monkeypatch.setattr(update_shape, "run", run)
    for name, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                        ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                        ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                        ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid"),
                        ("LANES_LANE", "")):
        monkeypatch.setenv(name, value)
    argv = ["apply", "--root", str(root.path), "--yes",
            "--upstream", str(project["upstream"]), "--at", project["b"],
            "--branch", BRANCH, "--push", "--pr"]

    assert update_shape.main(argv) == 2
    out, err = capsys.readouterr()
    assert f"REFUSED opening the pull request for {BRANCH}" in err
    assert GH_MISSING in err
    assert "    exit 127" in err
    assert next_line_of(out) == "NEXT  " + shlex.join(calls[0])
    head = the_commit_stands(root, project)
    assert on_the_remote(root) == head

    assert update_shape.main(argv) == 2
    out, err = capsys.readouterr()
    assert f"REFUSED asking gh for {BRANCH}'s pull request" in err
    assert GH_MISSING in err
    assert calls[1] == ["gh", *listing()]
    assert next_line_of(out) == "NEXT  " + shlex.join(calls[0])
    assert commits_on_the_branch(root) == 1


# --- a re-run over a tree HEAD does not commit (#333) -------------------------
#
# `_awaits_its_pull_request` judges HEAD; "nothing to write" judges the working
# tree, and so does the manifest read for the pull request's base and
# repository. Over a tree that is HEAD's those agree. Over an uncommitted
# change to the pin, the manifest or a pinned copy they did not, and the re-run
# pushed HEAD under a pull request named for the working tree. Each run is the
# update as a child with the `gh` fixture's stub in it (#334), so a tool that
# asked `gh` would be heard asking, on every platform.

def landed_without_its_pull_request(root, project, env) -> None:
    """B committed on BRANCH and pushed, with no pull request: what a `gh pr
    create` failing after the push leaves, reached without `gh`."""
    first = apply(root, project, "--branch", BRANCH, "--push", env=env)
    assert first.returncode == 0, first.stdout + first.stderr
    assert on_the_remote(root) == the_commit_stands(root, project)


def apply_c_in_place(root, project, env) -> None:
    """THE ISSUE'S CASE: then an in-place `apply --at C`, left uncommitted."""
    landed_without_its_pull_request(root, project, env)
    in_place = apply(root, project, env=env, at=project["c"])
    assert in_place.returncode == 0, in_place.stdout + in_place.stderr


def put_the_repin_back_by_hand(root, project, env) -> None:
    """Then the branch's re-pin put back to `origin/main`'s, staged too."""
    landed_without_its_pull_request(root, project, env)
    git("checkout", "origin/main", "--", PIN, "project.yaml", CHANGED,
        cwd=root.path)


def edit_the_manifest(root, project, env) -> None:
    """Then an edit to `project.yaml` alone, the pin untouched."""
    landed_without_its_pull_request(root, project, env)
    manifest = root.path / "project.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"# not committed\n")


def commit_the_pin_without_its_copy(root, project, env) -> None:
    """An in-place `apply --at B` committed by hand on BRANCH, the copy
    left out: HEAD's pin names B over A's validator, and the working tree
    holds B's."""
    in_place = apply(root, project, env=env)
    assert in_place.returncode == 0, in_place.stdout + in_place.stderr
    git("checkout", "-q", "-b", BRANCH, cwd=root.path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Re-pin by hand", "--", PIN, "project.yaml", cwd=root.path)


def hidden_from_the_index(flag: str):
    """THE ISSUE'S CASE, then every path it left uncommitted marked `flag`
    in the index. `git status` and `git diff HEAD` then report nothing, so
    a check that asked the index would have taken the re-run; the bytes on
    disk are still not HEAD's."""
    def prepare(root, project, env) -> None:
        apply_c_in_place(root, project, env)
        git("update-index", flag, "--", PIN, "project.yaml", PINS,
            cwd=root.path)
        assert git("status", "--porcelain", cwd=root.path).stdout == ""
        assert git("diff", "--quiet", "HEAD", "--", PIN, "project.yaml", PINS,
                   cwd=root.path, check=False).returncode == 0, (
            f"{flag} hides the in-place apply from `git diff HEAD`")
    return prepare


@pytest.mark.parametrize("prepare, at, differ, two_pins", [
    (apply_c_in_place, "c", [PIN, "project.yaml", PINS], True),
    (hidden_from_the_index("--assume-unchanged"), "c",
     [PIN, "project.yaml", PINS], True),
    (hidden_from_the_index("--skip-worktree"), "c",
     [PIN, "project.yaml", PINS], True),
    (put_the_repin_back_by_hand, "a", [PIN, "project.yaml", CHANGED], True),
    (edit_the_manifest, "b", ["project.yaml"], False),
    (commit_the_pin_without_its_copy, "b", [CHANGED], False),
], ids=["in-place-apply", "assume-unchanged", "skip-worktree",
        "put-back-by-hand", "manifest-edit", "copy-uncommitted"])
def test_a_rerun_over_a_tree_head_does_not_commit_is_refused_by_name(
        root, project, gh, prepare, at, differ, two_pins):
    """THE ISSUE (#333). `apply --branch --push --pr` on BRANCH finds nothing
    to write in the working tree while HEAD proposes a pin, so main took the
    re-run: it pushed HEAD and opened a pull request titled with the
    working tree's commit (in-place-apply: C over B; put-back-by-hand: A
    over B), or one whose base and repository came from an uncommitted
    manifest, or one carrying a copy HEAD never committed. Now each is
    refused by name, listing exactly the paths HEAD does not commit, before
    `gh` is asked or anything is pushed, and the tree is left as it was.
    The comparison is of bytes, so the in-place apply is refused the same
    with its paths marked `--assume-unchanged` or `--skip-worktree`, which
    hide it from every question put to the index."""
    prepare(root, project, gh.env)
    head = git("rev-parse", "HEAD", cwd=root.path).stdout.strip()
    remote = on_the_remote(root)
    status = git("status", "--porcelain", cwd=root.path).stdout
    gh.forget()

    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env, at=project[at])

    assert rerun.returncode == 2, rerun.stdout + rerun.stderr
    assert rerun.stderr.startswith(
        f"REFUSED update-rerun-uncommitted: --pr would finish the landing of "
        f"{BRANCH} from what HEAD ({head[:12]}) commits, under a pull request "
        f"naming {project[at][:12]}, but the working tree does not hold what "
        f"HEAD commits at {', '.join(differ)}. "), rerun.stderr
    carried = (f"there the pin names {project[at][:12]} and HEAD's names "
               f"{project['b'][:12]}, so the pull request would name one "
               "commit and carry another.")
    assert (carried in rerun.stderr) == two_pins, rerun.stderr
    assert "Nothing was written or pushed, and gh was not asked." \
        in rerun.stderr
    assert rerun.stdout == "", "no `nothing to write`, no push, no NEXT line"
    assert gh.calls() == []
    assert on_the_remote(root) == remote, "nothing was pushed"
    assert git("rev-parse", "HEAD", cwd=root.path).stdout.strip() == head
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root.path).stdout.strip() == BRANCH
    assert git("status", "--porcelain", cwd=root.path).stdout == status, (
        "nothing was written and nothing rolled back")


def test_dirt_neither_decision_reads_leaves_the_rerun_as_it_was(
        root, project, gh):
    """WHAT THE REFUSAL DOES NOT TOUCH. An uncommitted README edit and an
    untracked note are read by neither decision, so the re-run still asks
    `gh`, finds HEAD already on origin and opens the pull request for B, as
    #227's does, and leaves both where they were."""
    landed_without_its_pull_request(root, project, gh.env)
    head = git("rev-parse", "HEAD", cwd=root.path).stdout.strip()
    readme = root.path / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\nNot committed.\n")
    (root.path / "notes.txt").write_bytes(b"untracked\n")
    gh.forget()

    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)

    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert f"pull request {URL}" in rerun.stdout
    assert next_line_of(rerun.stdout) == PR_OPEN_NEXT
    calls = gh.calls()
    assert [call[:2] for call in calls] == [["pr", "list"],
                                            ["pr", "create"]], calls
    assert calls[0] == listing()
    assert calls[1][calls[1].index("--title") + 1].endswith(
        f"@ {project['b'][:12]}")
    assert on_the_remote(root) == head
    assert git("rev-parse", "HEAD", cwd=root.path).stdout.strip() == head
    assert git("status", "--porcelain", cwd=root.path).stdout.splitlines() \
        == [" M README.md", "?? notes.txt"]


def test_a_crlf_pin_and_manifest_still_hold_what_head_commits(root, project,
                                                              gh):
    """THE CLEAN FILTER RUNS. The project's `.gitattributes` is `* text=auto
    eol=lf`, so a pin and a manifest whose lines end CRLF and are otherwise
    HEAD's are what git would commit there: HEAD's blobs. The re-run is not
    refused for them and opens the pull request for B, as a clean re-run
    does; a comparison of the raw bytes would have named both. A pinned
    copy cannot show this here: CRLF makes it `locally-modified` before the
    re-run is recognised."""
    landed_without_its_pull_request(root, project, gh.env)
    head = git("rev-parse", "HEAD", cwd=root.path).stdout.strip()
    crlf = {}
    for path in (PIN, "project.yaml"):
        file = root.path / path
        crlf[path] = file.read_bytes().replace(b"\r\n", b"\n").replace(
            b"\n", b"\r\n")
        file.write_bytes(crlf[path])
        committed = git("rev-parse", f"HEAD:{path}",
                        cwd=root.path).stdout.strip()
        assert git("hash-object", "--no-filters", "--", path,
                   cwd=root.path).stdout.strip() != committed, (
            f"{path}'s raw bytes are not HEAD's blob")
        assert git("hash-object", "--", path,
                   cwd=root.path).stdout.strip() == committed, (
            f"{path}, cleaned as git commits it, is HEAD's blob")
    gh.forget()

    rerun = apply(root, project, "--branch", BRANCH, "--push", "--pr",
                  env=gh.env)

    assert rerun.returncode == 0, rerun.stdout + rerun.stderr
    assert f"pull request {URL}" in rerun.stdout
    assert next_line_of(rerun.stdout) == PR_OPEN_NEXT
    calls = gh.calls()
    assert [call[:2] for call in calls] == [["pr", "list"],
                                            ["pr", "create"]], calls
    assert calls[1][calls[1].index("--title") + 1].endswith(
        f"@ {project['b'][:12]}")
    assert on_the_remote(root) == head
    assert git("rev-parse", "HEAD", cwd=root.path).stdout.strip() == head
    for path, data in crlf.items():
        assert (root.path / path).read_bytes() == data, (
            f"{path} was left as it was")


# --- a first `--branch` run over a tree HEAD does not commit (#436) ----------
#
# #333's comparison, asked of every `--branch` run before its first write. The
# verdicts — what to copy, what to re-pin, whether there is anything to do —
# are read from the working tree, and the commit is HEAD plus only the paths
# the run writes. Over an in-place `apply` left uncommitted, main exited 0 on a
# commit its own `validate-pins.py` refused, died on git's "nothing to commit",
# or said "nothing to do" and made no branch; over an accepted local edit or a
# manifest edit left uncommitted, it committed without the one or with the
# other. Each is refused by name now, with nothing written.

#: A pinned copy neither B nor C changes upstream, for the local edits.
LOCAL = "scripts/bootstrap.py"
#: The branch a first run creates.
FRESH = "shape/update-first"


def in_place(root, project, env, at) -> None:
    """An `apply` without `--branch`, left uncommitted."""
    result = apply(root, project, env=env, at=project[at])
    assert result.returncode == 0, result.stdout + result.stderr


def b_in_place_on_main(root, project, env) -> None:
    """THE ISSUE'S STARTING POINT: an in-place `apply --at B` on main."""
    in_place(root, project, env, "b")


def c_in_place_over_b_on_branch(root, project, env) -> None:
    """THE ISSUE'S CASE (b): B committed on BRANCH and pushed, then an
    in-place `apply --at C` there."""
    landed_without_its_pull_request(root, project, env)
    in_place(root, project, env, "c")


def edit_a_copy(root, project, env) -> None:
    """A local edit to a pinned copy, left uncommitted."""
    path = root.path / LOCAL
    path.write_bytes(path.read_bytes() + b"\n# edited here, not committed\n")


def edit_the_manifest_on_main(root, project, env) -> None:
    """An edit to `project.yaml` alone, left uncommitted."""
    manifest = root.path / "project.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"# not committed\n")


def delete_a_copy(root, project, env) -> None:
    """A pinned copy deleted, the deletion left uncommitted."""
    (root.path / LOCAL).unlink()


@pytest.mark.parametrize("flags", [(), ("--push", "--pr")],
                         ids=["branch", "push-pr"])
@pytest.mark.parametrize("prepare, extra, at, branch, differ, pins", [
    (b_in_place_on_main, (), "c", FRESH, [PIN, "project.yaml", CHANGED],
     ("b", "a")),
    (c_in_place_over_b_on_branch, (), "b", BRANCH,
     [PIN, "project.yaml", PINS], ("c", "b")),
    (b_in_place_on_main, (), "b", FRESH, [PIN, "project.yaml", CHANGED],
     ("b", "a")),
    (edit_a_copy, ("--accept-local", LOCAL), "b", FRESH, [LOCAL], None),
    (edit_the_manifest_on_main, (), "b", FRESH, ["project.yaml"], None),
    (delete_a_copy, (), "b", FRESH, [LOCAL], None),
], ids=["moves-on", "moves-back", "stays", "accepted-edit", "manifest-edit",
        "copy-deleted"])
def test_a_first_branch_run_over_a_tree_head_does_not_commit_is_refused(
        root, project, gh, flags, prepare, extra, at, branch, differ, pins):
    """THE ISSUE (#436). Main, on each: `moves-on` (the issue's (a)) exited
    0 over a commit of C's re-pin without B's copy, red under its own
    `validate-pins.py`, and left that copy modified; `moves-back` ((b)) said
    REFUSED with git's "nothing to commit" after writing and rolling back;
    `stays` ((c)) said "nothing to do", exit 0, and made no branch;
    `accepted-edit` committed a pin recording a digest of an edit the commit
    did not carry; `manifest-edit` committed the uncommitted manifest line
    under the re-pin's message; `copy-deleted` called it `update-conflict`.
    Now each is refused by name, listing exactly the paths HEAD does not
    commit, before anything is written, a branch made, `gh` asked or
    anything pushed."""
    prepare(root, project, gh.env)
    head = git("rev-parse", "HEAD", cwd=root.path).stdout.strip()
    here = git("symbolic-ref", "--short", "HEAD", cwd=root.path).stdout
    branches = git("for-each-ref", "--format=%(refname)", "refs/heads/",
                   cwd=root.path).stdout
    remote = on_the_remote(root, branch)
    status = git("status", "--porcelain", cwd=root.path).stdout
    gh.forget()

    result = apply(root, project, *extra, "--branch", branch, *flags,
                   env=gh.env, at=project[at])

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED update-branch-uncommitted: --branch {branch} would commit "
        f"what HEAD ({head[:12]}) commits plus only the paths this run "
        "writes, but the working tree does not hold what HEAD commits at "
        f"{', '.join(differ)}. "), result.stderr
    if pins:
        named, committed = (project[key][:12] for key in pins)
        assert (f"there the pin names {named} and HEAD's names {committed}"
                in result.stderr), result.stderr
    else:
        assert "there the pin names" not in result.stderr, result.stderr
    assert "commit those changes first" in result.stderr
    assert "Nothing was written, committed or pushed." in result.stderr
    assert "nothing to commit" not in result.stderr
    assert "ROLLED BACK" not in result.stderr
    assert result.stdout == "", "nothing copied, re-pinned or said done"
    assert gh.calls() == []
    assert on_the_remote(root, branch) == remote, "nothing was pushed"
    assert git("rev-parse", "HEAD", cwd=root.path).stdout.strip() == head
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root.path).stdout == here
    assert git("for-each-ref", "--format=%(refname)", "refs/heads/",
               cwd=root.path).stdout == branches, "no branch was made"
    assert git("status", "--porcelain", cwd=root.path).stdout == status, (
        "nothing was written and nothing rolled back")


def test_a_first_branch_run_reads_no_readme_and_no_untracked_dirt(
        root, project, gh):
    """WHAT THE REFUSAL DOES NOT TOUCH, on a first run as on #333's re-run:
    an uncommitted README edit and an untracked note are read by no
    decision, so the run commits B's re-pin as it does on a clean tree —
    the three paths it wrote, green — and leaves both where they were."""
    readme = root.path / "README.md"
    readme.write_bytes(readme.read_bytes() + b"\nNot committed.\n")
    (root.path / "notes.txt").write_bytes(b"untracked\n")

    result = apply(root, project, "--branch", BRANCH, env=gh.env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert f"committed on {BRANCH}" in result.stdout
    assert git("show", "--name-only", "--format=", "HEAD",
               cwd=root.path).stdout.split() == [PIN, "project.yaml",
                                                 CHANGED]
    assert git("status", "--porcelain", cwd=root.path).stdout.splitlines() \
        == [" M README.md", "?? notes.txt"]
    assert gh.calls() == []


def test_a_copy_deleted_and_committed_is_still_a_conflict(root, project, gh):
    """NEITHER SIDE HOLDS IT, SO NOTHING DIFFERS. A pinned copy whose
    deletion HEAD commits is not a change left uncommitted; it is
    `update-conflict`'s `copy-missing`, as it was, and nothing is written."""
    git("rm", "-q", "--", LOCAL, cwd=root.path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Drop a copy", "--", LOCAL, cwd=root.path)

    result = apply(root, project, "--branch", BRANCH, env=gh.env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith("REFUSED update-conflict: "), \
        result.stderr
    assert f"{LOCAL}: pinned but absent from the root" in result.stderr
    assert "update-branch-uncommitted" not in result.stderr
    assert git("status", "--porcelain", cwd=root.path).stdout == ""


@pytest.mark.skipif(
    os.name == "nt",
    reason="a committed symlink is checked out as a plain file on Windows "
           "unless core.symlinks is on, and making one needs a privilege "
           "the runners do not grant")
def test_a_copy_kept_as_a_committed_link_is_what_head_commits(root, project,
                                                              gh):
    """GIT COMMITS THE LINK, NOT WHAT IT LEADS TO. `hash-object` on the path
    reads through a link, so a pinned copy kept as one that HEAD commits
    would read as a change HEAD does not commit, and every `--branch` run
    would be refused as that, whatever else was true. Its own text is
    compared with HEAD's entry for it instead, so this refusal does not
    stand in front of the run. What `apply` then does with a link is not
    this test's question (#347 answers it), so what is asserted holds
    either way: no `update-branch-uncommitted`, and the link is still the
    one HEAD commits."""
    real = "scripts/bootstrap-real.py"
    os.replace(root.path / LOCAL, root.path / real)
    (root.path / LOCAL).symlink_to("bootstrap-real.py")
    git("add", "--", LOCAL, real, cwd=root.path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "Keep the bootstrap copy as a link", cwd=root.path)
    link = git("rev-parse", f"HEAD:{LOCAL}", cwd=root.path).stdout

    result = apply(root, project, "--branch", BRANCH, env=gh.env)

    assert "Traceback" not in result.stderr, result.stderr
    assert "update-branch-uncommitted" not in result.stderr, result.stderr
    assert (root.path / LOCAL).is_symlink()
    assert git("rev-parse", f"HEAD:{LOCAL}", cwd=root.path).stdout == link
    assert git("status", "--porcelain", cwd=root.path).stdout == ""


# --- the same tree without `--branch`: no commit line to get wrong (#436) -----

@pytest.mark.parametrize("prepare, extra, at, left", [
    (b_in_place_on_main, (), "c", [CHANGED]),
    (edit_a_copy, ("--accept-local", LOCAL), "b", [LOCAL]),
], ids=["in-place-twice", "accepted-edit"])
def test_an_in_place_run_names_what_its_commit_line_would_leave_out(
        root, project, gh, prepare, extra, at, left):
    """THE ISSUE'S (a'). In place, the run writes as it always did: the
    copies, the pin and the manifest, green. Main then printed `NEXT  git
    checkout -b … && git commit -- <the paths it wrote>`, which, pasted,
    made the red commit `--branch` now refuses: the pin recorded the bytes
    of copies the line left out. The NEXT line names those copies now, and
    prints no commit to paste."""
    prepare(root, project, gh.env)

    result = apply(root, project, *extra, env=gh.env, at=project[at])

    assert result.returncode == 0, result.stdout + result.stderr
    assert load_yaml(root.path / PIN)["commit"].lower() == project[at]
    wrote = [line.split()[-1] for line in result.stdout.splitlines()
             if line.startswith("  copied   ")]
    paths = sorted({*wrote, PIN, "project.yaml"})
    assert next_line_of(result.stdout) == (
        "NEXT  no commit line: the working tree does not hold what HEAD "
        f"commits at {', '.join(left)}, paths this run did not write and "
        "whose bytes the pin it wrote records, so a commit of "
        f"{', '.join(paths)} alone would record digests for bytes it does "
        "not carry. Commit those changes with them if this re-pin is to "
        "carry them, or put both back to HEAD's bytes and run apply again")
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=root.path).stdout.strip() == "main", "nothing committed"
    assert gh.calls() == []
