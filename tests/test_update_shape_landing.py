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
another's non-fast-forward. `gh` is a shell script on PATH that logs its argv
and answers from a state directory — the shape `test_free_plan_hint.py`
already uses — so nothing here reaches a network or a real repository. A test
that needs that script carries `WINDOWS_SKIP` (CreateProcess reads no
shebang); the ones that never reach `gh`, and one that stubs it in-process,
run on every platform.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
from types import SimpleNamespace

import pytest

from conftest import REPO, WINDOWS_SKIP, blank_unnamed_pin_sources, git, \
    run_script
from test_update_shape import (CHANGED, CHANGED_SOURCE, PROJECT,
                               UPSTREAM_FIX_LINE, commit_upstream_changes,
                               next_line_of, scaffold_upstream_and_project)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402
from shape_materialize import SHAPE_REPOSITORY, CommandFailed  # noqa: E402

UPDATE = REPO / "update-shape.py"
BRANCH = "shape/update-landing"
PIN = "contracts/shape-pin.yaml"
URL = "https://github.invalid/testorg/Atlas/pull/7"
PR_OPEN_NEXT = "NEXT  the pull request is open; ask a human to review and merge it"

#: The stub. One line per call, each argument ended by a unit separator, so
#: the log keeps argument boundaries (the `--title` and `--body` values have
#: spaces in them) without a shell-quoting round trip.
GH_STUB = """#!/bin/sh
{ printf '%s\\037' "$@"; printf '\\n'; } >> "$GH_LOG"
case "$1 $2" in
  "pr list") cat "$GH_STATE/list" 2>/dev/null || echo '[]' ;;
  "pr create")
    if [ -e "$GH_STATE/create-fails" ]; then
      echo "HTTP 422: Validation Failed (stub)" >&2; exit 97
    fi
    echo "__URL__"
    printf '[{"state":"OPEN","url":"__URL__"}]\\n' > "$GH_STATE/list" ;;
  *) echo "stub gh: unexpected $*" >&2; exit 64 ;;
esac
""".replace("__URL__", URL)


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A, its bare remotes, and an upstream moved to B."""
    base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-landing")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b, "remote": base / "remotes" / f"{PROJECT}.git"}


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
    """The `gh` stub on PATH, and what it was asked."""
    binary = tmp_path / "bin"
    binary.mkdir()
    script = binary / "gh"
    script.write_text(GH_STUB, encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
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

    env = {"PATH": f"{binary}{os.pathsep}{os.environ['PATH']}",
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

@WINDOWS_SKIP
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


@WINDOWS_SKIP
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


@WINDOWS_SKIP
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


@WINDOWS_SKIP
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


@WINDOWS_SKIP
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
        assert line.endswith(f"&& gh pr create --base main --head {BRANCH}")
        assert "run again" not in result.stderr, (
            "a re-run without --pr finishes nothing, so none is promised")
    the_commit_stands(root, project)
    assert on_the_remote(root) is None


@WINDOWS_SKIP
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


# --- what does not change ---------------------------------------------------

@pytest.mark.parametrize("flags", [(), ("--push",)], ids=["branch", "push"])
def test_without_pr_a_rerun_on_the_branch_is_still_nothing_to_do(
        root, project, gh, flags):
    """No `--pr`, no re-run behaviour: the second run prints main's one line
    and exits 0, and `gh` is never asked (on Windows the stub is not a
    program, which a call would turn into a failure)."""
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


@WINDOWS_SKIP
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


@pytest.mark.parametrize("branch", ["shape/update-landing", "shape/update-v1.2",
                                    "lane-3/shape+fix@eagle", "x"])
def test_a_branch_git_would_create_is_taken_as_written(update_shape, branch):
    """A NAME WITH A `/` IS THE ORDINARY CASE, and so is the rest of the
    alphabet `checked_value` always allowed: each is returned unchanged."""
    assert update_shape.checked_branch(branch) == branch


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
    """THE WINDOWS JOB'S COVERAGE of the two runs above: `gh` stubbed at
    `update_shape.run`, the one function every command goes through, and
    `git` — the commit and the push — run for real."""
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
