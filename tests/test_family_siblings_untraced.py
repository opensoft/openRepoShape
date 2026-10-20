# SPDX-License-Identifier: Apache-2.0
"""The family holder's pinned `scripts/siblings.py` writes the token in
`SHAPE_LEGS_TOKEN` or `SHAPE_LEGS_APP_TOKEN` to no trace the caller asked
git for (#1055), as the holder's `bootstrap.py` writes it to none (#996).

WHAT LANE 5 MEASURED, at main `1a47ed07`, on git 2.43.0 and 2.47.1: `make
siblings` run twice, so it clones both members and then fetches both, and
`family.py siblings`, with a token set and traces asked for, ended
`siblings ok`, exit 0, with the token in no output. But every trace2 target
the caller named held it, in the environment, in the global config or in
the system config: the `start` event of the clone in `place` and of the
fetch, which carry the credential's `-c url...insteadOf` rewrite in their
argv, one line for each member. `GIT_TRACE_PERFORMANCE`, which the issue did
not ask for, writes the same argv (`TRACE_VARIABLES`).

WHAT IT DOES NOW. Where a token is in use, the clone and the fetch run in
`untraced()`'s environment, which `siblings.py` imports from the
`bootstrap.py` beside it (`rewrite_environment`): every `GIT_TRACE*`
variable taken out, and trace2's three targets set to `0`, which turns off
a target the global or the system config names too. With no token, both
keep the caller's environment and are traced where the caller asked. The
member's own `scripts/bootstrap.py`, which `place` runs after a clone, is
given no token in its argv (it inherits the token variables, and the shipped
one reads neither), and keeps the caller's traces either way.

THE ROWS. Each entry point (`ENTRIES`: `make siblings` cloning, `make
siblings` again fetching, `family.py siblings` cloning) is run with each way
of asking for a trace (`TRACED_BY`), with each variable a credential arrives
in, and with none:
- with a token: exit 0, `siblings ok`, every trace the way asks for written,
  the member's own bootstrap traced where a member was cloned, and the token
  in no output and in no file under the test's directory: the run's TMPDIR,
  every trace and config file, and the clones' `.git/config` among them;
- with none, the control: the same, and the trace holds the clone, or the
  fetch, that `siblings.py` itself ran, at each member.

THE SAME FAMILY as `tests/test_family.py`, laid out as its `estate` lays it
out, and offline: a `gh` that refuses (`offline`), with TMPDIR a directory
of the test's own, and every remote a local path that the token's rewrite of
GitHub's urls never reaches, so the clones and the fetches succeed with the
fake token too.

AND ONE ROW WITH AN HTTPS MEMBER (`HTTPS_MEMBER`), which the rewrite does
reach, as it reaches a `github.com` member. A local path is no https url, so
`GIT_TRACE`'s own file holds no token for it; for an https one the clone's
`run_command: git remote-https` lines hold the rewritten url, measured on git
2.43.0 and 2.47.1 by lane 5's review of #1075. The row stays offline behind a
dead proxy: the clone fails at once, `siblings.py` says so, and nothing
leaves the host.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import (
    NO_BYTECODE, appended_to_command_scope, command_scope_at, run_script,
)
from test_family import (  # noqa: F401 (the `family` and `estate` fixtures)
    FAMILY, MEMBERS, ORG, allow_file_protocol, estate, family,
)
from test_family_add_refusals import offline  # noqa: F401
from test_family_bootstrap_stops_named import CREDENTIALS, files_holding
from test_siblings_family_name import MAKE, NO_CREDENTIAL, needs_make

#: A token for the runs with a credential in use: the fixture's members are
#: local paths, which its rewrite of GitHub's urls never reaches.
TOKEN = "w1055-a-token-no-forge-takes"

#: What a run that placed both members says last.
PLACED = "siblings ok: 2 member(s) beside the holder in "

#: A proxy nothing listens at (port 9, `discard`): an https clone through it
#: fails at once, and nothing leaves the host.
DEAD_PROXY = "http://127.0.0.1:9"

#: The member the https row gives a GitHub url, and the member it leaves a
#: local path.
HTTPS_MEMBER, LOCAL_MEMBER = MEMBERS

#: The trace variables lane 5's probe set (#1055), each to a file under the
#: run's TMPDIR, and `GIT_TRACE_PERFORMANCE`, whose file holds each git's
#: whole command line, `-c` and all (measured, git 2.43.0 and 2.47.1).
TRACE_VARIABLES = {
    "GIT_TRACE": "trace.txt",
    "GIT_TRACE2": "trace2-normal.txt",
    "GIT_TRACE2_EVENT": "trace2-event.json",
    "GIT_TRACE2_PERF": "trace2-perf.txt",
    "GIT_TRACE_PACKET": "trace-packet.txt",
    "GIT_TRACE_CURL": "trace-curl.txt",
    "GIT_TRACE_PERFORMANCE": "trace-performance.txt",
}

#: trace2's three targets as a config file names them, and the file each is
#: given, after a prefix that says which config named it.
TARGETS = {"eventTarget": "event.json", "normalTarget": "normal.txt",
           "perfTarget": "perf.txt"}


def targets_section(temp: Path, prefix: str) -> bytes:
    """A `[trace2]` section naming each of `TARGETS` as a file in `temp`."""
    return "".join([
        "\n[trace2]\n",
        *(f'\t{key} = "{(temp / (prefix + name)).as_posix()}"\n'
          for key, name in TARGETS.items())]).encode("utf-8")


def by_the_variables(env: dict, temp: Path, tmp_path: Path) -> dict:
    """`env` with each of `TRACE_VARIABLES` set to its file in `temp`."""
    return {**env, **{name: str(temp / file)
                      for name, file in TRACE_VARIABLES.items()}}


def by_the_global_config(env: dict, temp: Path, tmp_path: Path) -> dict:
    """`env` with a global config of the test's own: the session's, which
    turns git's automatic maintenance off, with trace2's three targets
    added."""
    config = tmp_path / "traced-global-gitconfig"
    config.write_bytes(Path(os.environ["GIT_CONFIG_GLOBAL"]).read_bytes()
                       + targets_section(temp, "cfg-"))
    return {**env, "GIT_CONFIG_GLOBAL": str(config)}


def by_the_system_config(env: dict, temp: Path, tmp_path: Path) -> dict:
    """`env` with a system config of the test's own, naming trace2's three
    targets, and read whatever the environment running the suite says."""
    config = tmp_path / "traced-system-gitconfig"
    config.write_bytes(targets_section(temp, "sys-"))
    return {**env, "GIT_CONFIG_SYSTEM": str(config),
            "GIT_CONFIG_NOSYSTEM": "0"}


class Traced(NamedTuple):
    """A way a caller asks git for traces: `asks` lays it over a run's
    environment; `event` is the file trace2's events go to; `written` the
    files a run writes, with a token in use or none, since the run's other
    gits are traced either way. `GIT_TRACE_PACKET` is written by a clone or
    a fetch alone, and `GIT_TRACE_CURL` for an http remote alone."""

    asks: Callable[[dict, Path, Path], dict]
    event: str
    written: tuple[str, ...]


#: The three ways the issue measured: the variables, and trace2's targets
#: in the global config and in the system config.
TRACED_BY = {
    "variables": Traced(by_the_variables, "trace2-event.json", (
        "trace.txt", "trace2-normal.txt", "trace2-event.json",
        "trace2-perf.txt", "trace-performance.txt")),
    "global-config": Traced(by_the_global_config, "cfg-event.json", tuple(
        f"cfg-{name}" for name in TARGETS.values())),
    "system-config": Traced(by_the_system_config, "sys-event.json", tuple(
        f"sys-{name}" for name in TARGETS.values())),
}


def events(path: Path) -> list[dict]:
    """The trace2 events in `path`, a line each; a line that is no event is
    skipped."""
    found = []
    for line in path.read_bytes().decode("utf-8", "replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            found.append(event)
    return found


def traced_runs(path: Path) -> list[tuple[list, str]]:
    """`(argv, work tree)` of each git whose `start` event `path` holds:
    the work tree is its own repository's (`def_repo`, repository 1), as a
    real path, or `""` where its events name none."""
    runs: dict[str, dict] = {}
    for event in events(path):
        run = runs.setdefault(str(event.get("sid")), {})
        if event.get("event") == "start":
            run["argv"] = event.get("argv") or []
        elif (event.get("event") == "def_repo" and event.get("repo") == 1
              and isinstance(event.get("worktree"), str)):
            run["worktree"] = os.path.realpath(event["worktree"])
    return [(run["argv"], run.get("worktree", "")) for run in runs.values()
            if "argv" in run]


def siblings_clones(path: Path) -> list[str]:
    """Where each `git clone -q --no-local` traced in `path` cloned to, as
    a real path: the clone `place` runs with no token, whose last argument
    is the member's slot beside the holder."""
    return sorted(os.path.realpath(argv[-1])
                  for argv, _ in traced_runs(path)
                  if argv[1:4] == ["clone", "-q", "--no-local"])


def siblings_fetches(path: Path) -> list[str]:
    """The work tree of each `git fetch --quiet origin` traced in `path`:
    the fetch `place` runs in a member's clone with no token."""
    return sorted(worktree for argv, worktree in traced_runs(path)
                  if argv[1:] == ["fetch", "--quiet", "origin"])


def in_a_leg(path: Path, folder: Path) -> list[str]:
    """Each member some git traced in `path` ran in a leg of, a work tree
    under its clone beside the holder that is not the clone itself: only
    the member's own bootstrap runs a git there, where a clone with a token
    in use is not traced."""
    trees = [Path(worktree) for _, worktree in traced_runs(path) if worktree]
    return [project for project in MEMBERS
            if any(Path(os.path.realpath(folder / project)) in tree.parents
                   for tree in trees)]


def make_siblings(holder: Path, env: dict) -> subprocess.CompletedProcess:
    """`make siblings` in `holder`, under `env` laid over this process's
    environment, with this interpreter as `PYTHON` and no flags handed
    down from a make above (`test_family_makefile_siblings.make`)."""
    laid = {name: value for name, value in {**os.environ, **env}.items()
            if name not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}
    return subprocess.run([MAKE, "siblings", f"PYTHON={sys.executable}"],
                          cwd=str(holder), env=laid, capture_output=True,
                          text=True, encoding="utf-8", errors="replace",
                          stdin=subprocess.DEVNULL, check=False)


def cloning_by_make(estate: dict, env: dict, setup: dict
                    ) -> subprocess.CompletedProcess:
    """`make siblings`, with no member beside the holder: it clones both."""
    return make_siblings(estate["holder"], env)


def fetching_by_make(estate: dict, env: dict, setup: dict
                     ) -> subprocess.CompletedProcess:
    """`make siblings` again: a first run under `setup`, with no token and
    no trace, clones both members, and the second, under `env`, fetches
    both."""
    first = make_siblings(estate["holder"], setup)
    assert first.returncode == 0, first.stdout + first.stderr
    return make_siblings(estate["holder"], env)


def cloning_by_family_py(estate: dict, env: dict, setup: dict
                         ) -> subprocess.CompletedProcess:
    """`family.py siblings --family-root <holder>`, which runs the holder's
    own `scripts/siblings.py` in the caller's environment (#543): it clones
    both."""
    return run_script(FAMILY, "siblings", "--family-root",
                      str(estate["holder"]), env={**NO_BYTECODE, **env})


class Entry(NamedTuple):
    """An entry point of `make siblings` and what it does: `run` runs it;
    `ran` reads, from a trace, where `siblings.py`'s own clone or fetch ran;
    `bootstrapped` says whether each member's own bootstrap runs."""

    run: Callable[[dict, dict, dict], subprocess.CompletedProcess]
    ran: Callable[[Path], list[str]]
    bootstrapped: bool


ENTRIES = {
    "make-clone": pytest.param(Entry(cloning_by_make, siblings_clones, True),
                               marks=needs_make, id="make-clone"),
    "make-fetch": pytest.param(Entry(fetching_by_make, siblings_fetches,
                                     False),
                               marks=needs_make, id="make-fetch"),
    "family-py": pytest.param(Entry(cloning_by_family_py, siblings_clones,
                                    True), id="family-py"),
}


def offline_env(offline) -> dict:
    """The environment every run here starts from: `offline`'s `gh` and
    TMPDIR, the file transport allowed to the fixture's local remotes as
    the suite allows it, and no credential, whatever the machine running
    the suite exports."""
    return {**offline.env, **allow_file_protocol(), **NO_CREDENTIAL}


def written(temp: Path, traced: Traced) -> list[str]:
    """Those of `traced.written` that are files in `temp`."""
    return [name for name in traced.written if (temp / name).is_file()]


def given_a_github_url(holder: Path, project: str) -> None:
    """`project`'s url in the holder's `.gitmodules`, a local path, spelled
    as GitHub's: `https://github.com/<org>/<project>.git`, which the token's
    rewrite reaches. The file is read by `siblings.py` as it stands."""
    path = holder / ".gitmodules"
    spelled, found = re.subn(
        rf"(?m)^(\turl = ).*/{project}\.git$",
        rf"\g<1>https://github.com/{ORG}/{project}.git",
        path.read_text(encoding="utf-8"))
    assert found == 1, path.read_text(encoding="utf-8")
    path.write_text(spelled, encoding="utf-8")


def behind_a_dead_proxy(env: dict) -> dict:
    """`env` with `http.proxy` at `DEAD_PROXY` in git's command scope, after
    the entries `env` and this process hold, and with no list of hosts that
    skip a proxy: no https clone made under it leaves the host."""
    held = {**os.environ, **env}
    return {**env, **appended_to_command_scope(
        held, [("http.proxy", DEAD_PROXY)]), "NO_PROXY": "", "no_proxy": ""}


@pytest.mark.parametrize("variable", CREDENTIALS)
@pytest.mark.parametrize("traced", TRACED_BY.values(), ids=TRACED_BY)
@pytest.mark.parametrize("entry", ENTRIES.values())
def test_with_a_token_in_use_the_token_is_in_no_trace(
        family, estate, offline, tmp_path, entry, traced, variable):
    """#1055: a token in `variable`, and traces asked for `traced`'s way.
    The run places both members and says so, every trace is written by the
    run's other gits, and the member's own bootstrap, after a clone, is
    traced; the token is in no output and in no file under the test's
    directory. Before, the clone's and the fetch's `start` events wrote it
    to every trace2 target, and `GIT_TRACE_PERFORMANCE` wrote it too."""
    setup = offline_env(offline)
    env = traced.asks({**setup, variable: TOKEN}, offline.temp, tmp_path)

    result = entry.run(estate, env, setup)

    assert result.returncode == 0, result.stdout + result.stderr
    assert PLACED in result.stdout, result.stdout
    assert TOKEN not in result.stdout + result.stderr
    assert files_holding(tmp_path, TOKEN) == []
    assert written(offline.temp, traced) == list(traced.written)
    assert in_a_leg(offline.temp / traced.event, estate["folder"]) == (
        list(MEMBERS) if entry.bootstrapped else [])


@pytest.mark.parametrize("traced", TRACED_BY.values(), ids=TRACED_BY)
@pytest.mark.parametrize("entry", ENTRIES.values())
def test_with_no_token_the_clone_and_the_fetch_are_traced_as_asked(
        family, estate, offline, tmp_path, entry, traced):
    """The control (#1055): with no credential, the clone and the fetch
    `siblings.py` runs keep the caller's environment, so the trace asked
    for `traced`'s way holds each, at each member."""
    env = traced.asks(offline_env(offline), offline.temp, tmp_path)

    result = entry.run(estate, env, offline_env(offline))

    assert result.returncode == 0, result.stdout + result.stderr
    assert PLACED in result.stdout, result.stdout
    assert written(offline.temp, traced) == list(traced.written)
    assert entry.ran(offline.temp / traced.event) == sorted(
        os.path.realpath(estate["folder"] / project) for project in MEMBERS)


@needs_make
def test_an_https_member_with_a_token_in_use_is_in_no_trace(
        family, estate, offline, tmp_path):
    """#1055, lane 5's review of #1075 (rv1075): the token in
    `SHAPE_LEGS_TOKEN`, the trace variables set, and one member whose remote
    is GitHub's (`HTTPS_MEMBER`), behind a dead proxy. The rewrite reaches
    its clone, which fails with git's 128, whichever way this git is built
    to fail an https clone (at the proxy, or for want of its https helper),
    and `make siblings` exits 2; the other member is placed. Before,
    `GIT_TRACE`'s file held the token in the clone's `run_command: git
    remote-https` lines, and so did the trace2 files; the token is now in no
    output and in no file under the test's directory, every trace the
    variables ask for is written by the run's other gits, and a mutant that
    keeps the caller's `GIT_TRACE` for the clone is found."""
    traced = TRACED_BY["variables"]
    setup = offline_env(offline)
    env = behind_a_dead_proxy(
        traced.asks({**setup, "SHAPE_LEGS_TOKEN": TOKEN}, offline.temp,
                    tmp_path))
    given_a_github_url(estate["holder"], HTTPS_MEMBER)
    assert f"http.proxy={DEAD_PROXY}" in command_scope_at(
        env, estate["holder"])

    result = cloning_by_make(estate, env, setup)

    assert result.returncode == 2, result.stdout + result.stderr
    assert f"{HTTPS_MEMBER}: git clone exited 128:" in result.stderr
    assert (estate["folder"] / LOCAL_MEMBER / ".git").is_dir()
    assert not (estate["folder"] / HTTPS_MEMBER).exists()
    assert TOKEN not in result.stdout + result.stderr
    assert files_holding(tmp_path, TOKEN) == []
    assert written(offline.temp, traced) == list(traced.written)
