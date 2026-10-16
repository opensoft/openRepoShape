# SPDX-License-Identifier: Apache-2.0
"""Git's automatic maintenance is off for every git the suite starts (#645).

The suite copies a repository file by file (`shutil.copytree`) a moment
after a fixture committed in it, fetched into it or pushed to it, and the
maintenance git starts as each of those finishes can be packing that
repository in the background, deleting the loose objects the copy is
reading. `tests/conftest.py`'s `no_auto_maintenance` turns `gc.auto` and
`maintenance.auto` off for the session, in git's command scope and in a
global config file. Each test here asks git what it starts or reads, so
none of them waits for a race and each holds on any git:

- a commit, a fetch and a merge run as a fixture runs them start no `git
  maintenance` and no `git gc`, with the session's global file and with a
  test's own (git's trace2 events name every child a git starts);
- `scaffold-project.py` into local bare remotes, a tool that starts its own
  gits, starts no `git maintenance` anywhere, the `receive-pack` its pushes
  start in the remotes included;
- the `receive-pack` a push into a local remote starts, which never sees
  command scope, reads both settings off: a hook in the remote reports them;
- the two are appended to the command scope the environment holds, and a
  person's own global config is still read, in git's order, beneath them.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import (NO_AUTO_MAINTENANCE, ORG, PROJECT, SCAFFOLD,
                      appended_to_command_scope, git, run_script,
                      session_global_config)

#: The verbs auto maintenance runs as: `git maintenance run --auto`, and
#: `git gc --auto`, which a git started itself before `maintenance` existed.
MAINTENANCE_VERBS = ("maintenance", "gc")

#: The two settings as a `receive-pack` must read them, one `key=value` a
#: line: spelled out, not read from `NO_AUTO_MAINTENANCE`, so a change to
#: that table is a change to this test too.
BOTH_OFF = b"gc.auto=0\nmaintenance.auto=false\n"


def traced(monkeypatch, tmp_path: Path) -> Path:
    """The file git's trace2 events go to for the rest of the test, from
    every git the test starts and every git those start: one JSON object a
    line."""
    trace = tmp_path / "trace2.json"
    monkeypatch.setenv("GIT_TRACE2_EVENT", str(trace))
    return trace


def events(trace: Path) -> list:
    return [json.loads(line)
            for line in trace.read_bytes().decode("utf-8").splitlines()
            if line.strip()]


def ran(trace: Path) -> set:
    """The verb of every git that wrote to `trace`."""
    return {event["name"] for event in events(trace)
            if event.get("event") == "cmd_name"}


def started(trace: Path, verbs=MAINTENANCE_VERBS) -> list:
    """The argv of every git child a git in `trace` started as one of
    `verbs`: `["git", "maintenance", "run", "--auto", ...]`."""
    found = []
    for event in events(trace):
        argv = event.get("argv") or []
        if event.get("event") == "child_start" and argv[1:2] and \
                argv[1] in verbs:
            found.append(argv)
    return found


def asked(*args: str, cwd: Path) -> str:
    """`git config <args>`'s answer, outside any repository."""
    return git("config", *args, cwd=cwd, check=False).stdout.strip()


@pytest.fixture
def behind(tmp_path) -> Path:
    """A clone of a local bare remote that has moved on by a commit, as a
    fixture leaves one: `fetch` brings something and `merge` makes a
    merge commit."""
    remote, work, other = (tmp_path / "remote.git", tmp_path / "work",
                           tmp_path / "other")
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("init", "-q", "-b", "main", str(other), cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "one", cwd=other)
    git("push", "-q", str(remote), "main", cwd=other)
    git("clone", "-q", "--no-local", str(remote), str(work), cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "two", cwd=other)
    git("push", "-q", str(remote), "main", cwd=other)
    return work


@pytest.mark.parametrize("own_global", [False, True],
                         ids=["the-session-global", "a-tests-own-global"])
def test_a_commit_a_fetch_and_a_merge_start_no_maintenance(
        behind, tmp_path, monkeypatch, own_global):
    """On the base each of the three started `git maintenance run --auto`
    (git 2.43). With a global config of the test's own, the command scope
    alone keeps it off."""
    if own_global:
        empty = tmp_path / "own.gitconfig"
        empty.write_bytes(b"")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(empty))
    trace = traced(monkeypatch, tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "three", cwd=behind)
    git("fetch", "-q", "origin", cwd=behind)
    git("merge", "-q", "--no-ff", "-m", "merge", "origin/main", cwd=behind)
    assert {"commit", "fetch", "merge"} <= ran(trace), ran(trace)
    assert started(trace) == []


def test_a_tool_and_the_remotes_it_pushes_to_start_no_maintenance(
        tmp_path, monkeypatch):
    """The scaffold commits in three working trees and pushes each into a
    bare remote, where `receive-pack` runs that remote's maintenance. On the
    base its commits started `git maintenance run --auto`. A `git gc --auto`
    child is not counted: 2.43's `receive-pack` starts one whatever the
    settings say, and `gc.auto=0`, which the next test shows it reads, makes
    it do nothing."""
    trace = traced(monkeypatch, tmp_path)
    result = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert {"commit", "receive-pack"} <= ran(trace), ran(trace)
    assert started(trace, ("maintenance",)) == []


def test_the_receive_pack_of_a_push_to_a_local_remote_reads_both_off(
        tmp_path):
    """Git starts `receive-pack` for a push to a path with no command scope,
    so only the session's global file reaches it. Its `post-receive` hook
    runs under it and writes down what git reads there. On the base it read
    neither."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    hook = remote / "hooks" / "post-receive"
    hook.write_bytes(
        b"#!/bin/sh\nfor key in gc.auto maintenance.auto; do\n"
        b'    printf "%s=%s\\n" "$key" "$(git config --get "$key")"\n'
        b"done > read-by-receive-pack\n")
    hook.chmod(0o755)
    git("init", "-q", "-b", "main", str(work), cwd=tmp_path)
    git("commit", "-q", "--allow-empty", "-m", "one", cwd=work)
    git("push", "-q", str(remote), "main", cwd=work)
    assert (remote / "read-by-receive-pack").read_bytes() == BOTH_OFF


def test_the_two_are_appended_to_the_command_scope_the_environment_holds(
        tmp_path):
    """The Windows job holds two entries in `GIT_CONFIG_COUNT` for the whole
    run, and a count that started again at 0 would drop both."""
    held = {"GIT_CONFIG_COUNT": "2",
            "GIT_CONFIG_KEY_0": "test.heldone", "GIT_CONFIG_VALUE_0": "one",
            "GIT_CONFIG_KEY_1": "test.heldtwo", "GIT_CONFIG_VALUE_1": "two"}
    added = appended_to_command_scope(held)
    assert added["GIT_CONFIG_COUNT"] == "4", added
    env = {**os.environ, **held, **added}
    lines = [subprocess.run(["git", "config", "--get", key], cwd=str(tmp_path),
                            capture_output=True, text=True, env=env,
                            check=False).stdout
             for key in ("test.heldone", "test.heldtwo",
                         *(key for key, _ in NO_AUTO_MAINTENANCE))]
    assert lines == ["one\n", "two\n",
                     *(f"{value}\n" for _, value in NO_AUTO_MAINTENANCE)]


@pytest.mark.parametrize("included", ["~/.gitconfig", "~/.config/git/config"])
def test_a_persons_own_global_config_is_still_read_beneath_the_two(
        included, no_auto_maintenance, tmp_path, monkeypatch):
    """The session's file includes the global config git would read without
    it, `~/` expanded from the `HOME` of the git that reads it, and sets the
    two settings after it: a person's own values are read, and their own
    `maintenance.auto = true` does not turn maintenance back on. A case is
    skipped where the file includes another path in its place, which a test
    cannot write: the session began with `GIT_CONFIG_GLOBAL` set, or, for
    the second, with `XDG_CONFIG_HOME` set."""
    if no_auto_maintenance.read_bytes() != session_global_config(None):
        pytest.skip("the session began with GIT_CONFIG_GLOBAL set, and its "
                    "file includes that one")
    if included.startswith("~/.config/") and os.environ.get("XDG_CONFIG_HOME"):
        pytest.skip("XDG_CONFIG_HOME is set, and the file includes the git "
                    "config under it")
    monkeypatch.setenv("HOME", str(tmp_path))
    own = tmp_path.joinpath(*included[2:].split("/"))
    own.parent.mkdir(parents=True, exist_ok=True)
    own.write_bytes(b"[openreposhape]\n\tprobe = " + included.encode()
                    + b"\n[maintenance]\n\tauto = true\n[gc]\n\tauto = 6700\n")
    assert asked("--get", "openreposhape.probe", cwd=tmp_path) == included
    for key, value in NO_AUTO_MAINTENANCE:
        assert asked("--global", "--includes", "--get", key,
                     cwd=tmp_path) == value, key
