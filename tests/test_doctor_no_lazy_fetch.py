# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` starts every git with `GIT_NO_LAZY_FETCH=1` (#787).

THE PROMISE WAS KEPT READ BY READ. The doctor "never fetches", and a
partial clone (`git clone --filter`) fetches an object it lacks on any read
that needs one. #683 and #754 ask a partial clone of the standard, with
`rev-list --missing=print`, before anything reads it; a read nothing asked
about first fetched. Measured on #787 with git 2.43: a partial clone of a
ROOT whose HEAD commit broke its pin made one lazy fetch (`blob:none`) or
two (`tree:0`), when `pin_restore` walked the pin's history.

NOW `main` runs under `lazy_fetch_off`, so every git the doctor starts,
and every git its validators start, fails a read that would fetch. Such a
read was a fetch that failed where the remote is out of reach, and the
doctor already answers those; `pin_restore`'s walk now says, of a partial
clone that lacks the pin's history, `partial`, and names the fetch.

"FETCHED NOTHING" IS ASKED OF GIT. `GIT_TRACE2_EVENT` names a folder, and
each git the run starts writes its events there: a lazy fetch is a
`child_start` of `git ... fetch`, logged even where the fetch then fails,
so a remote out of reach hides nothing. `rev-list --objects --all
--missing=print` before and after says the same of a remote in reach.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, git, run_script
from test_doctor_partial_clone import (  # noqa: F401
    currency_of, missing, moved, out_of_reach, partial_clone_of,
    second_promisor,
)
from test_shape_doctor import (  # noqa: F401
    SHAPE_PIN, doctor_module, pasted, project, run_pasted, scaffolded_here,
    standard,
)

#: The variable `lazy_fetch_off` sets for the doctor's run.
NO_LAZY_FETCH = "GIT_NO_LAZY_FETCH"


def traced(shape: Path, root: Path, trace: Path, *args: str,
           path: str | None = None):
    """`shape`'s doctor on `root`, every git it starts logging its trace2
    events into the folder `trace`; `path`, where given, is the `PATH` it
    runs with."""
    trace.mkdir()
    env = {"GIT_TRACE2_EVENT": str(trace)}
    if path is not None:
        env["PATH"] = path
    return run_script(shape / "shape-doctor.py", "--root", str(root), *args,
                      env=env)


def events(trace: Path) -> list:
    """Every trace2 event the run's gits wrote into `trace`."""
    found = []
    for log in sorted(trace.iterdir()):
        for line in log.read_text(encoding="utf-8",
                                  errors="replace").splitlines():
            found.append(json.loads(line))
    return found


def fetches(trace: Path) -> list:
    """Each `fetch` a git of the run started, as its argv: a lazy fetch is
    one, `git -c fetch.negotiationAlgorithm=noop fetch <remote> ...`."""
    return [event["argv"] for event in events(trace)
            if event.get("event") == "child_start"
            and "fetch" in event.get("argv", [])]


def gits(trace: Path) -> int:
    """How many git processes the run started: one trace2 log each."""
    return len(list(trace.iterdir()))


@pytest.mark.parametrize("reachable", [False, True])
@pytest.mark.parametrize("filter_spec", ["blob:none", "tree:0"])
def test_every_row_from_a_partial_clone_of_the_standard_starts_no_fetch(
        moved, project, tmp_path, filter_spec, reachable):
    """Every row, asked of a partial clone of C2 behind the pin at C1:
    no git of the run started a fetch, and the clone lacks what it lacked.
    The trace saw the run's gits, so "none" is an answer."""
    clone = partial_clone_of(moved["ahead"], tmp_path / "partial",
                             filter_spec)
    if not reachable:
        out_of_reach(clone, tmp_path)
    before = missing(clone)
    result = traced(clone, project, tmp_path / "trace", "--json")
    assert result.returncode == 3, result.stdout + result.stderr
    assert gits(tmp_path / "trace") > 1, "the trace saw no git"
    assert fetches(tmp_path / "trace") == [], "a git of the run fetched"
    assert missing(clone) == before, "the doctor fetched"


def without_the_variable(tmp_path: Path) -> str:
    """A `PATH` whose first `git` unsets `GIT_NO_LAZY_FETCH` and runs the
    real one: every git the doctor starts runs as before #787."""
    shim = tmp_path / "shim"
    shim.mkdir()
    script = shim / "git"
    script.write_text("#!/bin/sh\nunset GIT_NO_LAZY_FETCH\nexec "
                      f"{shlex.quote(shutil.which('git'))} \"$@\"\n",
                      encoding="utf-8")
    script.chmod(0o755)
    return f"{shim}{os.pathsep}{os.environ['PATH']}"


def clone_of_the_standard(kind: str, standard: Path, moved: dict,
                          tmp_path: Path) -> Path:
    """The standard itself, a full clone, or a partial clone of C2 behind
    the pin with its remote out of reach, by `kind`."""
    if kind == "full":
        return standard
    return out_of_reach(partial_clone_of(moved["ahead"], tmp_path / "partial",
                                         kind), tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="the git shim is a sh script")
@pytest.mark.parametrize("args", [["--json"], []])
@pytest.mark.parametrize("kind", ["full", "blob:none", "tree:0"])
def test_the_report_is_the_same_byte_for_byte_with_the_variable_ignored(
        standard, moved, project, tmp_path, kind, args):
    """The doctor's report, `--json` and the table, as it is and with every
    git it starts run without `GIT_NO_LAZY_FETCH`: the same bytes, the
    same exit. A full clone lacks nothing, and every read of a partial
    clone of the standard is asked first, so the variable changes no row
    there."""
    shape = clone_of_the_standard(kind, standard, moved, tmp_path)
    now = traced(shape, project, tmp_path / "now", *args)
    before = traced(shape, project, tmp_path / "before", *args,
                    path=without_the_variable(tmp_path))
    assert now.stdout == before.stdout
    assert now.stderr == before.stderr
    assert now.returncode == before.returncode


def broken_pin_remote(project: Path, tmp_path: Path) -> Path:
    """A bare copy of `project`, filters allowed, whose HEAD commit broke
    its pin: a partial clone of it lacks the pin before that commit, which
    `pin_restore` puts back, and in `tree:0` the trees down to it."""
    (project / SHAPE_PIN).write_bytes(b"files: 5\n")
    git("commit", "-q", "-am", "A pin that does not read", cwd=project)
    bare = tmp_path / "project.git"
    git(*FILE_PROTOCOL, "clone", "-q", "--bare", "--no-local",
        project.as_uri(), str(bare), cwd=tmp_path)
    git("config", "uploadpack.allowFilter", "true", cwd=bare)
    return bare


#: Each partial clone of `broken_pin_remote` asked about: its filter,
#: whether its HEAD is then moved back one commit without a checkout
#: (`reset --soft`, RV-f on #791), and what the doctor run after the
#: fetch says puts the pin back.
PARTIAL_ROOTS = {
    "blob:none": ("blob:none", False, "committed"),
    "tree:0": ("tree:0", False, "committed"),
    "HEAD moved back by reset --soft": ("blob:none", True, "uncommitted"),
}


@pytest.mark.parametrize("case", list(PARTIAL_ROOTS))
def test_a_partial_root_whose_pin_history_is_not_here_names_the_fetch(
        standard, project, tmp_path, case):
    """The pin's history is not in the partial clone of the root: the
    doctor fetched it before #787. It starts no fetch, `restore` is
    `partial`, the `why` says the history, HEAD's included, is not all
    here, and the NEXT is the fetch of the root's promisor remote; run as
    printed, the doctor run again names what puts the pin back: the
    commit before the one that broke it, or, where HEAD was moved back
    without a checkout, HEAD's own pin (`uncommitted`)."""
    filter_spec, moved_back, answer = PARTIAL_ROOTS[case]
    root = partial_clone_of(broken_pin_remote(project, tmp_path),
                            tmp_path / "partial-root", filter_spec)
    if moved_back:
        git("reset", "-q", "--soft", "HEAD~1", cwd=root)
    result = traced(standard, root, tmp_path / "trace", "--json")
    row = currency_of(result)
    assert fetches(tmp_path / "trace") == [], "a git of the run fetched"
    assert row["detail"]["restore"] == "partial", row
    assert ("the pin's history, HEAD's included, is not all in this "
            "clone") in row["why"], row["why"]
    assert pasted(row["next"]) == [
        "git", "-C", str(root.resolve()), "fetch", "--refetch",
        "--no-filter", "origin"], row["next"]
    run_pasted(row["next"])
    again = currency_of(traced(standard, root, tmp_path / "again", "--json"))
    assert again["detail"]["restore"] == answer, again


def test_the_why_spells_out_the_fetch_from_each_other_promisor_remote(
        standard, moved, project, tmp_path):
    """The pin's history is on the second promisor remote alone: `origin`
    now names another repository (RV-f on #791, N3). The NEXT fetches
    `origin`, and run as printed the row comes back the same; the `why`
    spells out that fetch from `second`, and run as printed, the doctor
    names the commit that puts the pin back."""
    bare = broken_pin_remote(project, tmp_path)
    root = partial_clone_of(bare, tmp_path / "partial-root")
    git("remote", "set-url", "origin", moved["ahead"].as_uri(), cwd=root)
    second_promisor(root, bare, fetched=False)
    row = currency_of(traced(standard, root, tmp_path / "trace", "--json"))
    run_pasted(row["next"])
    same = currency_of(traced(standard, root, tmp_path / "same", "--json"))
    assert same["detail"]["restore"] == "partial", same
    offered = re.search(r"from second: `([^`]+)`", same["why"])
    assert offered, same["why"]
    run_pasted(offered.group(1))
    again = currency_of(traced(standard, root, tmp_path / "again", "--json"))
    assert again["detail"]["restore"] == "committed", again


def recording(tmp_path: Path, log: Path) -> str:
    """A `PATH` whose first `git` appends to `log`, for each git started,
    its `GIT_NO_LAZY_FETCH` (`unset` where it has none), the command line
    of the process that started it and its own arguments, a tab between
    each, then runs the real one."""
    shim = tmp_path / "recording"
    shim.mkdir()
    script = shim / "git"
    script.write_text(
        "#!/bin/sh\n"
        "printf '%s\\t%s\\t%s\\n' \"${GIT_NO_LAZY_FETCH-unset}\" "
        "\"$(ps -o args= -p \"$PPID\")\" \"$*\" >> "
        + shlex.quote(str(log)) + "\n"
        "exec " + shlex.quote(shutil.which("git")) + " \"$@\"\n",
        encoding="utf-8")
    script.chmod(0o755)
    return f"{shim}{os.pathsep}{os.environ['PATH']}"


@pytest.mark.skipif(os.name == "nt", reason="the git shim is a sh script")
def test_every_git_the_run_starts_has_the_variable(
        standard, project, tmp_path):
    """Every git a doctor run starts, logged by a `git` first on `PATH`
    (RV-f on #791, N2), has `GIT_NO_LAZY_FETCH=1`: the doctor's own, those
    of `update-shape.py`'s `Upstream` as the doctor drives it in its own
    process (`cat-file blob <commit>:<path>` of the standard's copies),
    and those of a validator `run_validator` starts with a copy of its
    environment (`validate-pins.py`)."""
    log = tmp_path / "gits.log"
    result = run_script(standard / "shape-doctor.py", "--root", str(project),
                        "--json", env={"PATH": recording(tmp_path, log)})
    assert result.returncode == 0, result.stdout + result.stderr
    gits_started = [line.split("\t", 2) for line in
                    log.read_text(encoding="utf-8").splitlines()]
    assert {value for value, _parent, _args in gits_started} == {"1"}, \
        gits_started
    assert any("validate-pins.py" in parent
               for _value, parent, _args in gits_started), gits_started
    assert any("shape-doctor.py" in parent and args.startswith("cat-file blob")
               and ":templates/" in args
               for _value, parent, args in gits_started), gits_started


@pytest.mark.parametrize("before", [None, "0"])
def test_lazy_fetch_off_sets_the_variable_and_puts_it_back(
        standard, monkeypatch, before):
    """`lazy_fetch_off`, which `main` runs under: `GIT_NO_LAZY_FETCH=1`
    inside, and outside the environment as it was, unset or not, for a
    caller that runs `main` in its own process."""
    module = doctor_module(standard)
    if before is None:
        monkeypatch.delenv(NO_LAZY_FETCH, raising=False)
    else:
        monkeypatch.setenv(NO_LAZY_FETCH, before)
    with module.lazy_fetch_off():
        inside = os.environ.get(NO_LAZY_FETCH)
    assert inside == "1"
    assert os.environ.get(NO_LAZY_FETCH) == before
