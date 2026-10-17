# SPDX-License-Identifier: Apache-2.0
"""Without `--work-dir`, an adoption's run removes the work directory it made
when it holds nothing, a recorded `plan --source org/repo` clone that is
gone is cloned again, and the suite keeps its temporary directories in
pytest's basetemp (#526; the lines of #457 and #461 it closes).

ON MAIN AT 2247dbff (2026-10-15), with `TMPDIR` at a fresh directory:
- `plan` and `check` of a local source each left one EMPTY
  `openreposhape-adopt-*` directory; so did an `execute` that was refused,
  and a `plan --source org/repo` whose clone failed left one holding an
  empty `source-readonly/`. A successful `execute` left one holding the
  split and both legs (511 entries for the conftest source) and said
  nothing about it.
- With the clone `plan --source testorg/Northwind` recorded in
  `source.local_path` deleted, `check` and `execute` both handed that PATH
  to `gh repo clone` as an `org/repo` and refused `source-unclonable`,
  `could not clone /…/source-readonly/Northwind`, telling the person to
  check `gh auth status`. Passing `--source testorg/Northwind` again
  recovered.
- One run of `tests/test_adopt_pins.py` (107 tests) left 117 empty
  `openreposhape-adopt-*` directories in the system temp folder.

NO NETWORK AND NO GITHUB. A run that would clone `org/repo` runs in this
process, with `gh repo clone` stood in for by a `git clone` of a repository
on disk (`gh_clones`); every other run is a child given its own `TMPDIR`.
"""

from __future__ import annotations

import importlib.util
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NamedTuple

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, rmtree, run_script,
                      spelled)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

ORG = "testorg"
PROJECT = "Thing"
REPOSITORY = f"{ORG}/{PROJECT}"
#: What `_work_root` names each directory it makes, without `--work-dir`.
PREFIX = "openreposhape-adopt-"
PLAN = "adoption-plan.yaml"
TEMPORARY = "tmp"
REMOTES = "remotes"
LOCAL_REMOTE_DIR = "--local-remote-dir"
PLAN_FLAG = "--plan"
PLAN_VERB = "plan"
OUT = "--out"
YES = "--yes"
SOURCE_FLAG = "--source"
CHECK, EXECUTE = "check", "execute"
#: A source small enough that `plan` asks no question.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}
#: `plan`'s arguments after `--source <it>`.
PLANNED = ["--project", PROJECT, "--org", ORG, "--elected-by", "Test Human",
           "--elected-on", "2026-09-02"]
#: How the NOTE about a recorded clone that is gone begins.
GONE = "NOTE the plan's `source.local_path`, "
#: What `gh`'s own parser says of a repository that is not `[HOST/]OWNER/REPO`.
NOT_A_REPOSITORY = 'expected the "[HOST/]OWNER/REPO" format, got "{}"'
GH_REPOSITORY = re.compile(r"(?:[\w.-]+/)?[\w.-]+/[\w.-]+")
STALE = "plan-stale"
BROKEN = "a defect in the middle of `check`"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_temp_work_roots",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def left_in(temporary: Path) -> list[str]:
    """The `openreposhape-adopt-*` directories `temporary` holds, by name."""
    return sorted(path.name for path in temporary.glob(f"{PREFIX}*"))


def kept(root: Path) -> str:
    """The line `execute` ends on when the work directory it made stays."""
    return (f"NOTE the work directory this run made, {spelled(root)}, is "
            "kept, because it holds what the run made there: delete it once "
            "nothing in it is needed.")


def gone(local_path: str) -> str:
    """The NOTE `check` and `execute` print when they clone `REPOSITORY`
    again, its recorded clone at `local_path` being gone."""
    return (f"{GONE}{spelled(local_path)}, no longer exists, so its "
            f"`source.repository`, {REPOSITORY}, is cloned again from "
            "GitHub, as `plan` cloned it.")


def adopt(temporary: Path, *args: str) -> subprocess.CompletedProcess:
    """`adopt-project.py <args>` in a child whose `TMPDIR` is `temporary`,
    the system temp folder as `tempfile` finds it on every platform."""
    temporary.mkdir(exist_ok=True)
    return run_script(ADOPT, *args, env={"TMPDIR": str(temporary)})


def local_plan(tmp_path: Path) -> tuple[Path, Path]:
    """A local source and the plan `plan` wrote for it, with `--work-dir`,
    so that `TMPDIR` is untouched: `(source, plan)`."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    plan = tmp_path / PLAN
    written = run_script(ADOPT, PLAN_VERB, SOURCE_FLAG, str(source), *PLANNED,
                         OUT, str(plan), "--work-dir",
                         str(tmp_path / "plan-work"))
    assert written.returncode == 0, written.stderr + written.stdout
    return source, plan


def moved(source: Path) -> str:
    """A commit on the source's `main` after the plan's; its sha."""
    (source / "README.md").write_bytes(b"# Thing, moved on\n")
    git("commit", "-q", "-am", "Move on", cwd=source)
    return git("rev-parse", "HEAD", cwd=source).stdout.strip()


def gh_clones(adopter, monkeypatch, origin: Path) -> list:
    """`gh repo clone REPOSITORY <directory>` stood in for by a `git clone`
    of `origin`, its `origin` then set to the GitHub URL, as gh leaves it;
    a repository gh's own parser refuses -- a path -- fails as gh fails it,
    and any other repository is not found. Returns the list each `gh`
    call's arguments are recorded in."""
    real = adopter.run
    calls: list = []

    def stand_in(args, *rest, **keywords):
        if args[0] != "gh":
            return real(args, *rest, **keywords)
        calls.append(list(args))
        if not GH_REPOSITORY.fullmatch(args[3]):
            raise adopter.CommandFailed(args, None, 1,
                                        NOT_A_REPOSITORY.format(args[3]))
        if args[3] != REPOSITORY:
            raise adopter.CommandFailed(
                args, None, 1, "GraphQL: Could not resolve to a Repository")
        real(["git", "clone", "-q", "--no-local", str(origin), args[4]])
        return real(["git", "-C", args[4], "remote", "set-url", "origin",
                     f"https://github.com/{REPOSITORY}.git"])

    monkeypatch.setattr(adopter, "run", stand_in)
    return calls


def in_a_fresh_temp_folder(monkeypatch, temporary: Path) -> Path:
    """`temporary`, made, as the system temp folder of this process."""
    temporary.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temporary))
    return temporary


class Planned(NamedTuple):
    """What `planned_from_github` made: the plan, the clone it records as
    `source.local_path`, the repository `gh` clones and the `gh` calls."""
    plan: Path
    clone: str
    origin: Path
    calls: list


def planned_from_github(adopter, monkeypatch, tmp_path: Path) -> Planned:
    """`plan --source REPOSITORY`, in this process, without `--work-dir`.
    stdin is no terminal, as in CI, so a run with no `--yes` is refused as
    `adopt-unconfirmed`, never asked; and `git filter-repo` is not asked
    for, because nothing here gets as far as using it."""
    origin = make_source_repo(tmp_path / "github" / PROJECT,
                              tree=SMALL_TREE, edits=())
    calls = gh_clones(adopter, monkeypatch, origin)
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    in_a_fresh_temp_folder(monkeypatch, tmp_path / "plan-temp")
    plan = tmp_path / PLAN
    assert adopter.main([PLAN_VERB, SOURCE_FLAG, REPOSITORY, *PLANNED, OUT,
                         str(plan)]) == 0
    return Planned(plan, str(recorded(plan)["local_path"]), origin, calls)


def recorded(plan: Path) -> dict:
    """The plan's `source:`, as `plan` recorded it."""
    return load_yaml(plan)["source"]


# --- the work directory `_work_root` makes (#457, line 1) -------------------

def test_plan_and_check_remove_the_empty_work_directory_they_made(tmp_path):
    """A local source is read in place, so `plan` and `check` build nothing
    in their work directory, and leave none behind. A `--work-dir` the
    person gave is theirs, and stays, empty or not."""
    source = make_source_repo(tmp_path / PROJECT, tree=SMALL_TREE, edits=())
    temporary, plan = tmp_path / TEMPORARY, tmp_path / PLAN
    planned = adopt(temporary, PLAN_VERB, SOURCE_FLAG, str(source), *PLANNED,
                    OUT, str(plan))
    assert planned.returncode == 0, planned.stderr + planned.stdout
    assert left_in(temporary) == []
    given = tmp_path / "given"
    checked = adopt(temporary, CHECK, PLAN_FLAG, str(plan), "--work-dir",
                    str(given))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert given.is_dir()
    checked = adopt(temporary, CHECK, PLAN_FLAG, str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert left_in(temporary) == []


def test_a_check_with_findings_and_a_refused_execute_leave_none(tmp_path):
    """However the command ends: `check` with a finding, exit 1, and
    `execute` refused, exit 2 -- for the moved source, or, where `git
    filter-repo` is missing, for that -- before anything exists. Neither
    says it kept a work directory, because it kept none."""
    source, plan = local_plan(tmp_path)
    moved(source)
    temporary = tmp_path / TEMPORARY
    checked = adopt(temporary, CHECK, PLAN_FLAG, str(plan))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert f"FINDING {STALE}" in checked.stderr
    executed = adopt(temporary, EXECUTE, PLAN_FLAG, str(plan), YES,
                     LOCAL_REMOTE_DIR, str(tmp_path / REMOTES))
    assert executed.returncode == 2, executed.stderr + executed.stdout
    assert "REFUSED " in executed.stderr
    assert "is kept" not in executed.stderr + executed.stdout
    assert left_in(temporary) == []


def test_a_defect_still_removes_the_empty_work_directory_and_propagates(
        adopter, monkeypatch, tmp_path):
    """An exception no step anticipates is not hidden: it reaches the caller
    as it was raised, and the empty work directory goes all the same."""
    _, plan = local_plan(tmp_path)
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / TEMPORARY)

    def defect(*_args, **_keywords):
        raise RuntimeError(BROKEN)

    monkeypatch.setattr(adopter, "_print_triad_advisory", defect)
    argv = [CHECK, PLAN_FLAG, str(plan)]
    with pytest.raises(RuntimeError, match=re.escape(BROKEN)):
        adopter.main(argv)
    assert left_in(temporary) == []


def test_a_refused_clone_leaves_no_work_directory(adopter, monkeypatch,
                                                  capsys, tmp_path):
    """`plan --source <org/repo>` makes `source-readonly/` in its work
    directory before it asks `gh` to clone into it; refused, the clone
    leaves that directory empty, and the work directory holds no file, so
    it goes too."""
    gh_clones(adopter, monkeypatch, tmp_path / "nowhere")
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / TEMPORARY)
    code = adopter.main([PLAN_VERB, SOURCE_FLAG, f"{ORG}/Elsewhere", *PLANNED,
                         OUT, str(tmp_path / PLAN)])
    assert code == 2
    assert "REFUSED source-unclonable: " in capsys.readouterr().err
    assert left_in(temporary) == []


def test_a_refused_execute_says_which_work_directory_it_keeps(
        adopter, monkeypatch, capsys, tmp_path):
    """`execute --source <org/repo>` clones the source into the work
    directory it made, so that directory is not empty when the run is
    refused, and stays: the run's last line names it, after the refusal."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    temporary = in_a_fresh_temp_folder(monkeypatch, tmp_path / TEMPORARY)
    capsys.readouterr()
    code = adopter.main([EXECUTE, PLAN_FLAG, str(planned.plan),
                         SOURCE_FLAG, REPOSITORY, LOCAL_REMOTE_DIR,
                         str(tmp_path / REMOTES)])
    err = capsys.readouterr().err
    assert code == 2, err
    assert "REFUSED adopt-unconfirmed: " in err
    [root] = left_in(temporary)
    assert err.splitlines()[-1] == kept(temporary / root)


@needs_filter_repo
def test_an_execute_that_built_keeps_its_work_directory_and_says_where(
        tmp_path):
    """The legs and the split are built in the work directory, and are
    what a person reads when the verification fails, so it stays; its last
    line, after the verification and the next steps, names it."""
    _, plan = local_plan(tmp_path)
    temporary = tmp_path / TEMPORARY
    done = adopt(temporary, EXECUTE, PLAN_FLAG, str(plan), YES,
                 LOCAL_REMOTE_DIR, str(tmp_path / REMOTES))
    assert done.returncode == 0, done.stderr + done.stdout
    assert "adoption verified" in done.stdout
    [root] = left_in(temporary)
    assert sorted(path.name for path in (temporary / root).iterdir()
                  if path.is_dir()) == [PROJECT, f"{PROJECT}-code",
                                        f"{PROJECT}-spec"]
    assert done.stdout.splitlines()[-1] == kept(temporary / root)


# --- a recorded clone that is gone (#457, line 2) ---------------------------

def test_check_and_execute_clone_the_recorded_repository_again(
        adopter, monkeypatch, capsys, tmp_path):
    """While the clone `plan` recorded is there, `check` reads it in place
    and asks `gh` nothing. Once it is gone -- the system cleans its temp
    folder -- `check` and `execute` clone the plan's `source.repository`
    again, as `--source` would, and say so in one NOTE, where on main they
    handed the vanished PATH to `gh repo clone` and refused
    `source-unclonable`."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    plan, calls = str(planned.plan), planned.calls
    capsys.readouterr()
    assert adopter.main([CHECK, PLAN_FLAG, plan]) == 0
    assert GONE not in capsys.readouterr().out
    assert len(calls) == 1
    rmtree(Path(planned.clone))

    checked = adopter.main([CHECK, PLAN_FLAG, plan])
    out = capsys.readouterr().out
    assert checked == 0, out
    assert [line for line in out.splitlines()
            if line.startswith(GONE)] == [gone(planned.clone)]
    executed = adopter.main([EXECUTE, PLAN_FLAG, plan, LOCAL_REMOTE_DIR,
                             str(tmp_path / REMOTES)])
    said = capsys.readouterr()
    assert executed == 2, said.err
    assert "REFUSED adopt-unconfirmed: " in said.err
    assert said.out.count(gone(planned.clone)) == 1
    assert [call[:4] for call in calls[1:]] == [
        ["gh", "repo", "clone", REPOSITORY]] * 2


def test_a_clone_made_again_at_another_commit_is_stale(
        adopter, monkeypatch, capsys, tmp_path):
    """The plan records the commit it classified, and a repository cloned
    again is held to it as one passed with `--source` is: `check` finds
    `plan-stale` and `execute` refuses it before any leg exists, each
    naming both commits."""
    planned = planned_from_github(adopter, monkeypatch, tmp_path)
    plan = str(planned.plan)
    before = str(recorded(planned.plan)["commit"])
    after = moved(planned.origin)
    rmtree(Path(planned.clone))
    capsys.readouterr()

    assert adopter.main([CHECK, PLAN_FLAG, plan]) == 1
    assert (f"FINDING {STALE}: the plan was written against {before[:12]} "
            f"but `main` is now at {after[:12]}.") in capsys.readouterr().err
    remotes = tmp_path / REMOTES
    assert adopter.main([EXECUTE, PLAN_FLAG, plan, YES, LOCAL_REMOTE_DIR,
                         str(remotes)]) == 2
    assert (f"REFUSED {STALE}: the plan was written against {before[:12]} "
            f"and `main` is now at {after[:12]}") in capsys.readouterr().err
    assert not remotes.exists()


# --- the suite's own temporary directory (#461) -----------------------------

def test_the_suite_keeps_its_temporary_directory_in_the_basetemp(
        tmp_path_factory):
    """`TMPDIR` is one directory under the session's basetemp, for this
    process's `tempfile` and for every child, so what a run without
    `--work-dir` leaves is pytest's to keep or remove with the rest."""
    expected = tmp_path_factory.getbasetemp() / "tmpdir"
    assert Path(os.environ.get("TMPDIR", "")) == expected
    assert Path(tempfile.gettempdir()) == expected
    child = subprocess.run(
        [sys.executable, "-c", "import tempfile; print(tempfile.gettempdir())"],
        capture_output=True, text=True, check=True)
    assert Path(child.stdout.strip()) == expected
