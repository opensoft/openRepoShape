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
  person's own global config is still read, in git's order, beneath them;
- the file is one git can read where `HOME` is unset, and where
  `GIT_CONFIG_GLOBAL` is empty, which is git's "no global config";
- the fixture is in place before any session fixture builds a repository;
- a line pasted through the doctor tests' `paste()` runs under the entries the
  environment holds when it is pasted, with `protocol.file.allow` appended
  (#758), and no test file sets `GIT_CONFIG_COUNT` to a number of its own,
  which would drop the entries the session and the Windows job set.
"""

from __future__ import annotations

import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from conftest import (NO_AUTO_MAINTENANCE, ORG, PROJECT, SCAFFOLD,
                      WINDOWS_SKIP, appended_to_command_scope, git,
                      home_is_known, run_script, session_global_config)
from test_doctor_legs_members_next import paste

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


def probe_read_from_the_session_file(named, tmp_path, monkeypatch) -> str:
    """`session_global_config(named)` written to a file that is the whole
    global config for the rest of the test, read back with its includes: the
    two settings are asserted, and what the `openreposhape.probe` key reads
    is returned (empty where no included file sets it)."""
    config = tmp_path / "session.gitconfig"
    config.write_bytes(session_global_config(named))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    for key, value in NO_AUTO_MAINTENANCE:
        assert asked("--global", "--includes", "--get", key,
                     cwd=tmp_path) == value, key
    return asked("--global", "--includes", "--get", "openreposhape.probe",
                 cwd=tmp_path)


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
    neither. The remote's own `core.hooksPath` keeps the hook found where a
    person's global config sets one of its own."""
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    git("config", "core.hooksPath", (remote / "hooks").as_posix(), cwd=remote)
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
    cannot write: the session began with `GIT_CONFIG_GLOBAL` set, with
    `HOME` unset, or, for the second, with `XDG_CONFIG_HOME` set."""
    if not home_is_known():
        pytest.skip("HOME was unset, and the file includes no `~/` path")
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


@pytest.mark.skipif(os.name == "nt",
                    reason="Git for Windows finds a home of its own")
@pytest.mark.parametrize("xdg", [False, True], ids=["no-xdg", "xdg"])
def test_where_home_is_unset_the_file_is_one_git_can_read(
        xdg, tmp_path, monkeypatch):
    """With `HOME` unset git cannot expand a `~/` path, and an include of one
    made every git the session started die `could not expand include path`
    (a hermetic runner, `env -i`). The file leaves them out, and an
    `XDG_CONFIG_HOME` that is set is still included."""
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    if xdg:
        under = tmp_path / "xdg"
        (under / "git").mkdir(parents=True)
        (under / "git" / "config").write_bytes(
            b"[openreposhape]\n\tprobe = xdg\n")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(under))
    assert probe_read_from_the_session_file(
        None, tmp_path, monkeypatch) == ("xdg" if xdg else "")


def test_an_empty_GIT_CONFIG_GLOBAL_is_no_global_config_and_includes_nothing(
        tmp_path, monkeypatch):
    """Git reads an empty `GIT_CONFIG_GLOBAL` as "no global config" (2.43),
    and the file the fixture writes over it does not bring `~/.gitconfig`
    back."""
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_bytes(b"[openreposhape]\n\tprobe = home\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    assert probe_read_from_the_session_file("", tmp_path, monkeypatch) == ""


@pytest.fixture(scope="session")
def seen_by_a_session_fixture() -> dict:
    """The session's two variables as a SESSION fixture sees them when it is
    built, which is when a session fixture that makes a repository (`standard`,
    `scaffolded`) makes it. Pytest builds the higher scope first, and within a
    scope an autouse fixture first and then the arguments in order."""
    return {name: os.environ.get(name)
            for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_COUNT")}


def test_the_settings_are_in_place_before_a_session_fixture_builds_a_repo(
        seen_by_a_session_fixture, no_auto_maintenance):
    """`no_auto_maintenance` at function scope, or without `autouse`, is
    built after a session fixture and every test here but this one still
    passes: the fixture must be session scope and autouse. A session fixture
    sees the file and the count that the test sees."""
    assert seen_by_a_session_fixture == {
        name: os.environ.get(name)
        for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_COUNT")}
    assert seen_by_a_session_fixture["GIT_CONFIG_GLOBAL"] == \
        str(no_auto_maintenance)


# --- the doctor tests' pasted lines, and the counts a test may not set (#758)
#
# `test_doctor_legs_members_next.py` pastes the NEXT a row prints into `sh`.
# Its environment was a copy of `os.environ` made when the module was
# imported, at collection, with `GIT_CONFIG_COUNT` set to 1: it held none of
# the session's settings, which `no_auto_maintenance` puts there at session
# start, and it dropped the entries the Windows job sets.

@WINDOWS_SKIP
def test_a_pasted_line_keeps_the_entries_the_environment_holds_at_the_call(
        no_auto_maintenance, tmp_path, monkeypatch):
    """The environment holds what the Windows job sets (two entries) and what
    the session fixture appends (the two settings), put there AFTER the doctor
    tests were imported. `git config --show-origin --list`, pasted through
    `paste()`, lists all four in git's command scope, in order, and then the
    `protocol.file.allow` the paste adds for its own sake, and reads the two
    settings from the session's global file too. On the base it listed that
    one alone, and no global file: the import-time copy held none of it.
    `GIT_CONFIG_PARAMETERS` is taken away first: git lists its entries
    after the count's, and a run started under `git -c` holds some."""
    monkeypatch.delenv("GIT_CONFIG_PARAMETERS", raising=False)
    held = appended_to_command_scope(
        {}, [("test.heldone", "one"), ("test.heldtwo", "two")])
    for name, value in {**held, **appended_to_command_scope(
            held, NO_AUTO_MAINTENANCE)}.items():
        monkeypatch.setenv(name, value)
    shown = paste({"next": "git config --show-origin --list"},
                  tmp_path / "elsewhere")
    assert shown.returncode == 0, shown.stderr + shown.stdout
    from_the_command_line = [
        line.split("\t", 1)[1] for line in shown.stdout.splitlines()
        if line.startswith("command line:")]
    assert from_the_command_line == [
        "test.heldone=one", "test.heldtwo=two",
        *(f"{key}={value}" for key, value in NO_AUTO_MAINTENANCE),
        "protocol.file.allow=always"]
    for key, value in NO_AUTO_MAINTENANCE:
        assert f"file:{no_auto_maintenance}\t{key}={value}" in \
            shown.stdout.splitlines()


#: The files beside this one (every `.py`, `conftest.py` and the helper
#: modules too) that may set a count of their own, and how many times. Each
#: is a test that BUILDS an environment holding entries, to see that the code
#: under test keeps them: this file's test of `appended_to_command_scope`
#: writes its two out, and the test above starts from none;
#: `test_adopt_git_reads.py` and `test_clone_just_pushed.py` do the same for
#: `command_scope` and for `read_through_git`.
OWN_COUNTS = {"test_no_auto_maintenance.py": 2,
              "test_adopt_git_reads.py": 1, "test_clone_just_pushed.py": 1}

COUNT = "GIT_CONFIG_COUNT"
APPENDER = "appended_to_command_scope"
#: The calls that put a value in the environment: `monkeypatch.setenv(name,
#: value)`, `env.setdefault(name, value)` and `os.putenv(name, value)`. Not
#: `env.get(name, default)`, which reads.
SETTERS = ("setenv", "setdefault", "putenv")


def is_the_count(node, names=frozenset()) -> bool:
    """The string constant `"GIT_CONFIG_COUNT"`, or one of `names`, the names
    the module binds to it."""
    return (isinstance(node, ast.Constant) and node.value == COUNT) or (
        isinstance(node, ast.Name) and node.id in names)


def is_a_written_count(node) -> bool:
    """A string constant git reads as a count: digits alone (`"1"`), or
    nothing (`""`), which git reads as no entries at all (2.43 and 2.47.1).
    Constants only: a count built by a call (`str(1)`) is not read."""
    return (isinstance(node, ast.Constant) and isinstance(node.value, str)
            and (node.value.isdigit() or not node.value))


def bound_names(node) -> list:
    """The plain names an assignment binds: `A = B = ...`, `A: str = ...`."""
    if isinstance(node, ast.Assign):
        return [target.id for target in node.targets
                if isinstance(target, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return [node.target.id]
    return []


def names_of_the_count(tree) -> frozenset:
    """Each name `tree` binds to `"GIT_CONFIG_COUNT"`: after `CONFIG_COUNT =
    "GIT_CONFIG_COUNT"`, a `{CONFIG_COUNT: "1"}` sets the count as the string
    itself would."""
    return frozenset(name for node in ast.walk(tree)
                     if is_the_count(getattr(node, "value", None))
                     for name in bound_names(node))


def is_a_setter(node) -> bool:
    """`setenv`, `setdefault` or `putenv`, called bare or on an object."""
    return (isinstance(node, ast.Name) and node.id in SETTERS) or (
        isinstance(node, ast.Attribute) and node.attr in SETTERS)


def is_the_appender(node) -> bool:
    """`appended_to_command_scope`, called bare or through a module."""
    return (isinstance(node, ast.Name) and node.id == APPENDER) or (
        isinstance(node, ast.Attribute) and node.attr == APPENDER)


def in_a_dict(node: ast.Dict, names: frozenset) -> list:
    """`{"GIT_CONFIG_COUNT": "1"}`: the line of each such key."""
    return [key.lineno for key, value in zip(node.keys, node.values)
            if is_the_count(key, names) and is_a_written_count(value)]


def in_a_call(node: ast.Call, names: frozenset) -> list:
    """`dict(GIT_CONFIG_COUNT="1")`, `monkeypatch.setenv("GIT_CONFIG_COUNT",
    "1")` and `appended_to_command_scope({}, ...)`."""
    lines = [keyword.value.lineno for keyword in node.keywords
             if keyword.arg == COUNT and is_a_written_count(keyword.value)]
    if (is_a_setter(node.func) and len(node.args) >= 2
            and is_the_count(node.args[0], names)
            and is_a_written_count(node.args[1])):
        lines.append(node.lineno)
    if (is_the_appender(node.func) and node.args
            and isinstance(node.args[0], ast.Dict)):
        lines.append(node.lineno)
    return lines


def by_subscript(node: ast.Assign, names: frozenset) -> list:
    """`env["GIT_CONFIG_COUNT"] = "1"`."""
    if not is_a_written_count(node.value):
        return []
    return [target.lineno for target in node.targets
            if isinstance(target, ast.Subscript)
            and is_the_count(target.slice, names)]


#: The nodes a count can be set in, and the reader of each.
READERS = {ast.Dict: in_a_dict, ast.Call: in_a_call, ast.Assign: by_subscript}


def counts_set_to_a_number(source: bytes) -> list:
    """The line of each place `source` sets a git command scope of its own
    instead of appending to the environment's:

    - `GIT_CONFIG_COUNT` set to a number it writes out: in a dict
      (`{"GIT_CONFIG_COUNT": "1"}`), as a keyword
      (`dict(GIT_CONFIG_COUNT="1")`), in a call that names the variable and
      gives its value (`monkeypatch.setenv("GIT_CONFIG_COUNT", "1")`), or by
      subscript (`env["GIT_CONFIG_COUNT"] = "1"`), the variable spelled out
      or held in a name the module binds to it;
    - `appended_to_command_scope` handed a dict written out (`{}`), where the
      environment goes: it counts from nothing, and the entries the
      environment holds are no longer in the count it returns.

    A count worked out from the one the environment holds is not one of
    them. The scan reads the count's value as a constant only: a value built
    by a call (`str(len(pairs))`), or held in a variable, is not read."""
    tree = ast.parse(source)
    names = names_of_the_count(tree)
    lines = []
    for node in ast.walk(tree):
        reader = READERS.get(type(node))
        if reader:
            lines += reader(node, names)
    return sorted(lines)


@pytest.mark.parametrize("source", [
    '{"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "protocol.file.allow"}',
    'dict(GIT_CONFIG_COUNT="2")',
    'monkeypatch.setenv("GIT_CONFIG_COUNT", "1")',
    'setenv("GIT_CONFIG_COUNT", "1")',
    'env.setdefault("GIT_CONFIG_COUNT", "2")',
    'os.putenv("GIT_CONFIG_COUNT", "1")',
    'env["GIT_CONFIG_COUNT"] = "3"',
    '{"GIT_CONFIG_COUNT": ""}',
    'CONFIG_COUNT = "GIT_CONFIG_COUNT"; SYMLINKS_OFF = {CONFIG_COUNT: "1"}',
    'COUNT: str = "GIT_CONFIG_COUNT"; monkeypatch.setenv(COUNT, "1")',
    'KEY = "GIT_CONFIG_COUNT"; env[KEY] = "2"',
    'appended_to_command_scope({}, [("k", "v")])',
    'conftest.appended_to_command_scope({"A": "1"}, [])',
], ids=["dict", "keyword", "setenv", "a-bare-setenv", "setdefault", "putenv",
        "subscript", "nothing", "a-name-bound-to-it", "an-annotated-name",
        "a-name-by-subscript", "appended-to-nothing", "through-a-module"])
def test_the_scan_sees_each_way_a_test_can_set_a_count(source):
    assert counts_set_to_a_number(source.encode("utf-8")) == [1]


@pytest.mark.parametrize("source", [
    '{"GIT_CONFIG_COUNT": str(held + 1)}',
    '{**held, "GIT_CONFIG_KEY_0": "k"}',
    'monkeypatch.setenv("GIT_CONFIG_COUNT", str(held))',
    'index = int(env.get("GIT_CONFIG_COUNT", "0"))',
    'env["GIT_CONFIG_COUNT"] = count',
    '"GIT_CONFIG_COUNT is 1"',
    'KEY = "GIT_CONFIG_KEY_0"; env = {KEY: "1"}',
    'appended_to_command_scope(os.environ, [("k", "v")])',
    'appended_to_command_scope(held, [("k", "v")])',
], ids=["worked-out", "a-splat", "a-call", "a-read-with-a-default", "a-name",
        "a-sentence", "a-name-bound-to-another-key",
        "appended-to-the-environment", "appended-to-a-name"])
def test_the_scan_leaves_a_count_that_is_worked_out(source):
    assert counts_set_to_a_number(source.encode("utf-8")) == []


def files_off_their_count(directory: Path) -> dict:
    """Each `.py` file in `directory` whose places that set a count of their
    own are not as many as `OWN_COUNTS` allows it, with their lines: more
    drops the entries the environment holds, and fewer is an allowance no
    test needs any more."""
    found = {}
    for path in sorted(directory.glob("*.py")):
        lines = counts_set_to_a_number(path.read_bytes())
        if len(lines) != OWN_COUNTS.get(path.name, 0):
            found[path.name] = lines
    return found


def test_the_walk_reads_every_python_file_and_holds_each_to_its_count(
        tmp_path):
    """`conftest.py` and a helper module are read as a test file is, a file
    that is not Python is not read, and a file `OWN_COUNTS` allows a count
    is named when it sets fewer than that as well as more."""
    one = b'{"GIT_CONFIG_COUNT": "1"}\n'
    for name, source in {"conftest.py": one, "gh_guard.py": one,
                         "notes.txt": one, "test_adopt_git_reads.py": one,
                         "test_clone_just_pushed.py": b"",
                         "test_no_auto_maintenance.py": one * 3}.items():
        (tmp_path / name).write_bytes(source)
    assert files_off_their_count(tmp_path) == {
        "conftest.py": [1], "gh_guard.py": [1],
        "test_clone_just_pushed.py": [],
        "test_no_auto_maintenance.py": [1, 2, 3]}


def test_no_test_sets_a_git_config_count_of_its_own():
    """A `GIT_CONFIG_COUNT` of 1, laid over `os.environ`, replaces the one the
    session fixture and the Windows job set: the entries it counted are no
    longer git's, so a session setting or a job's `core.autocrlf` does not
    reach the git the test starts. Every test gives git a setting by
    appending to the entries the environment holds, built at the call by
    `appended_to_command_scope` (`conftest.py`, which is read too, and
    works its count out). Before #758 `PASTE_ENV`, `ALLOW_FILE_PROTOCOL`,
    `NO_MAINTENANCE`, `QUOTE_PATH_OFF`, `SYMLINKS_OFF` and eight one-off
    environments each wrote one."""
    found = files_off_their_count(Path(__file__).resolve().parent)
    assert not found, (
        "a `GIT_CONFIG_COUNT` written as a number, or `appended_to_command_"
        "scope` handed a dict written out, replaces the entries the "
        "environment holds; build it with `appended_to_command_scope` and "
        "`os.environ` instead, or, for a test that builds an environment "
        f"on purpose, change `OWN_COUNTS`: {found}")
