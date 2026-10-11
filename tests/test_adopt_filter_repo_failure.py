# SPDX-License-Identifier: Apache-2.0
"""`execute` says why a leg failed and what it left behind (#171).

`run` (`scripts/shape_materialize.py`) only RAISES `CommandFailed`; it prints
nothing. `_build_the_legs` caught that exception and returned None on the
premise that `run` had already said which command failed and why, so an
`execute` whose `git filter-repo` failed ended with both bare leg repositories
created, exit 2 and an EMPTY stderr, and the corrected re-run met
`leg-remote-exists`. On main at b18cca9 the issue's own source produced
exactly that: a `.gitmodules` that git's `--list` reads and git's submodule
reader dies on, a second section whose `path` has no value. Since #166
`check` refuses that source before any leg exists, so the end-to-end tests
below fail the extraction the way `check` can never foresee: a
`git-filter-repo` first on PATH that exits 1 (#184 P1-1).

The unit tests need no `git filter-repo`: they stub the leg builders, or run
a real leg builder against a remote that does not exist (the extraction
skips only the filter itself), and call `_build_the_legs` in this process.
The stub is a `#!/bin/sh` script, so the tests that put it on PATH skip on
Windows; the one that then follows the notice into a real adoption needs the
real tool as well.

NO NETWORK AND NO GITHUB: every remote is a bare repository on disk, or no
repository at all.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, WINDOWS_SKIP, git, make_source_repo, rmtree,
                      run_script, write_plan)

SPEC, CODE = "spec", "code"
UNIT_ROLES = (SPEC, CODE)
ASSEMBLY = "Northwind"
REMOTES = "remotes"
REFUSED = "REFUSED"
ROLLED_BACK = "NOTHING has been rolled back"
FILTER_REPO = ["git", "filter-repo", "--paths-from-file", "spec-paths.txt",
               "--force"]
SEEDING_COMMIT = ["git", "commit", "-q", "-F", "-"]
GIT_COMPLAINT = "fatal: bad config line 5 in file .gitmodules"
LIVE_LEG = "leg-remote-exists"
README = "README.md"
FILTER_REPO_TOOL = "git-filter-repo"
#: The names `Stream` records its events under.
STDOUT, STDERR, FLUSH = "stdout", "stderr", "flush"

#: One case per way a leg is built: what `_build_the_legs` is told is seeded,
#: the verb it should name, and the command that leg's builder would die on.
LEG_FAILURES = [([], "extracting", FILTER_REPO),
                ([SPEC], "seeding", SEEDING_COMMIT)]
LEG_FAILURE_IDS = ["extracted-leg", "seeded-leg"]

#: What the stub `git-filter-repo` says before it exits 1: the line the human
#: must be shown, because `run` itself prints nothing.
STUB_COMPLAINT = "fatal: stub git-filter-repo refuses this source"

#: A source small enough that `plan` asks no question, so `execute` runs on
#: the plan as written.
SMALL_TREE = {README: "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}

#: The notice's first sentence once both legs exist and neither is pushed:
#: the two repositories it names, which a re-run must not meet again.
NAMED = re.compile(r"rolled back: (?P<spec>.+?) and (?P<code>.+?) exist, and "
                   r"neither leg is pushed\.")

needs_filter_repo = pytest.mark.skipif(
    shutil.which(FILTER_REPO_TOOL) is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


class Stream:
    """A text stream that records, in one shared list, when it was used."""

    def __init__(self, name: str, events: list):
        self.name = name
        self.events = events

    def write(self, text: str) -> int:
        self.events.append((self.name, "write"))
        return len(text)

    def flush(self) -> None:
        self.events.append((self.name, FLUSH))


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_filter_repo_failure",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legs_arguments(tmp_path: Path, seeded: list, source=None,
                   remote: Path | None = None):
    """What `cmd_execute` hands `_build_the_legs`, for two legs and no plan.

    Each leg has its own URL, because the notice for a failed leg must name
    both. `remote`, when given, is where EVERY leg would be pushed; the unit
    tests that stub the leg builders never reach it.
    """
    urls = {role: str(remote or tmp_path / REMOTES / f"{ASSEMBLY}-{role}.git")
            for role in UNIT_ROLES}
    names = {role: f"{ASSEMBLY}-{role}" for role in UNIT_ROLES}
    names["assembly"] = ASSEMBLY
    return dict(
        source=source,
        names=names,
        repositories={role: f"testorg/{names[role]}" for role in UNIT_ROLES},
        urls=urls,
        values={},
        work_root=tmp_path / "work",
        paths_for={role: [f"{role}/file.md"] for role in UNIT_ROLES},
        seeded=seeded,
        branch="adopt/three-repo-shape",
        tracking="main")


def refuse_every_leg(adopter, monkeypatch, command: list, cwd: Path) -> None:
    """Make both leg builders raise what `run` raises, and print nothing."""
    def refused(*_args):
        raise adopter.CommandFailed(command, cwd, 1, GIT_COMPLAINT)

    monkeypatch.setattr(adopter, "_extract_leg", refused)
    monkeypatch.setattr(adopter, "_seed_leg", refused)


@pytest.mark.parametrize("seeded, verb, command", LEG_FAILURES,
                         ids=LEG_FAILURE_IDS)
def test_a_failed_leg_is_printed_with_its_command_and_its_output(
        adopter, monkeypatch, capsys, tmp_path, seeded, verb, command):
    """`run` raised and printed nothing, so this function is the only place
    that can say what the human is waiting to read."""
    refuse_every_leg(adopter, monkeypatch, command, tmp_path)

    legs = adopter._build_the_legs(**legs_arguments(tmp_path, seeded))

    assert legs is None
    err = capsys.readouterr().err
    assert f"{REFUSED} {verb} the {SPEC} leg." in err
    assert " ".join(command) in err
    assert "exit 1" in err
    assert GIT_COMPLAINT in err


@pytest.mark.parametrize("seeded, command",
                         [(seeded, command) for seeded, _, command
                          in LEG_FAILURES], ids=LEG_FAILURE_IDS)
def test_a_failed_leg_names_both_leg_repositories_and_what_to_do(
        adopter, monkeypatch, capsys, tmp_path, seeded, command):
    """Both leg repositories exist by now, and one may even be pushed. The
    human reads the failure, fixes it and re-runs; the re-run is refused by
    `_create_leg_remotes`, so the notice says so BEFORE it happens, for both
    kinds of remote, and names the two repositories to delete or to
    replace. It says to fix what failed first: a cause that is still there
    fails the re-run the same way, after two more leg repositories (#188's
    review, F2)."""
    refuse_every_leg(adopter, monkeypatch, command, tmp_path)
    arguments = legs_arguments(tmp_path, seeded)
    # What the spec leg's builder leaves when its filter or its commit
    # fails: its clone, or the template it seeded, in the work directory.
    spec_work = arguments["work_root"] / f"{ASSEMBLY}-{SPEC}"
    spec_work.mkdir(parents=True)
    (spec_work / README).write_text("built\n", encoding="utf-8")

    assert adopter._build_the_legs(**arguments) is None

    notice = capsys.readouterr().err.split("--- end output ---", 1)[1]
    assert ROLLED_BACK in notice
    for role in UNIT_ROLES:
        assert arguments["urls"][role] in notice
    assert "--local-remote-dir" in notice
    assert LIVE_LEG in notice
    assert "gh repo create" in notice
    assert "already taken" in notice
    assert "Once what failed above is fixed, re-run the adoption" in notice
    # The work directory too, which holds what this run built: a re-run that
    # kept it looped (#184 P2-1), and `execute` now refuses it.
    assert (f"Use a fresh --work-dir as well, or none: "
            f"{arguments['work_root']} holds {ASSEMBLY}-{SPEC} from this "
            "run") in notice
    assert len(notice.strip().splitlines()) == 1


def test_a_rerun_under_a_local_remote_dir_meets_leg_remote_exists(
        adopter, tmp_path):
    """The first half of what the notice promises, from the code that makes
    it true: a leg repository that is already there is refused by name."""
    arguments = legs_arguments(tmp_path, [])
    Path(arguments["urls"][SPEC]).mkdir(parents=True)

    with pytest.raises(adopter.Refusal) as refused:
        adopter._create_leg_remotes({}, arguments["names"],
                                    arguments["repositories"],
                                    arguments["urls"], "main", True,
                                    arguments["work_root"])

    assert refused.value.code == LIVE_LEG
    # Its own way out names the work directory as well: an empty
    # --local-remote-dir alone met the clone the earlier run left (#184 P2-1).
    assert "choose an empty --local-remote-dir, and a --work-dir" in \
        refused.value.remediation


def test_a_rerun_against_github_has_gh_repo_create_refused(
        adopter, monkeypatch, tmp_path):
    """The second half: against GitHub the first thing a re-run does is
    `gh repo create` for the spec leg, and `run` raises when `gh` finds the
    name taken. Nothing in `_create_leg_remotes` catches it, so the run stops
    there, before the code leg is touched."""
    arguments = legs_arguments(tmp_path, [])
    repositories = arguments["repositories"]
    repositories["assembly"] = f"testorg/{ASSEMBLY}"
    calls: list = []

    def name_taken(args, *_rest, **_keywords):
        calls.append(args)
        raise adopter.CommandFailed(args, None, 1, "name already exists")

    monkeypatch.setattr(adopter, "run", name_taken)

    with pytest.raises(adopter.CommandFailed):
        adopter._create_leg_remotes({}, arguments["names"], repositories,
                                    arguments["urls"], "main", False,
                                    arguments["work_root"])

    assert [call[:4] for call in calls] == [
        ["gh", "repo", "create", repositories[SPEC]]]


def test_stdout_is_flushed_before_the_failure_is_written_to_stderr(
        adopter, monkeypatch, tmp_path):
    """`execute` announces each bare leg repository on stdout. Piped, that is
    block-buffered, so without a flush a log that merges the two streams shows
    the failure BEFORE the lines that explain what it is about."""
    events: list = []
    monkeypatch.setattr(sys, STDOUT, Stream(STDOUT, events))
    monkeypatch.setattr(sys, STDERR, Stream(STDERR, events))
    refuse_every_leg(adopter, monkeypatch, FILTER_REPO, tmp_path)

    assert adopter._build_the_legs(**legs_arguments(tmp_path, [])) is None

    assert (STDOUT, FLUSH) in events
    assert (events.index((STDOUT, FLUSH))
            < events.index((STDERR, "write")))


@pytest.mark.parametrize("seeded", [[], [SPEC]],
                         ids=["extracted-leg-push", "seeded-leg-push"])
def test_a_refused_push_is_reported_once_with_its_ruleset_hint(
        adopter, monkeypatch, capsys, tmp_path, seeded):
    """A refused push is the one failure `_extract_leg` and `_seed_leg` print
    themselves, with the adoption's ruleset hint, before they re-raise it. A
    second block for the same command is noise that buries the hint, so the
    leg builder's own report is the only one. The notice still follows the
    hint, once, because the hint no longer says what exists (#177). Real leg
    builders, real `git`, a remote that does not exist; the extraction skips
    only `git filter-repo`, which this test is not about."""
    def write_one_file(_template, work, _values):
        # What it wrote, as `copy_tree` returns it since #175.
        work.mkdir(parents=True, exist_ok=True)
        (work / README).write_text("seeded\n", encoding="utf-8")
        return [README]

    real_run = adopter.run

    def without_the_filter(args, *rest, **keywords):
        if args[:2] == ["git", "filter-repo"]:
            return ""
        return real_run(args, *rest, **keywords)

    monkeypatch.setattr(adopter, "copy_tree", write_one_file)
    monkeypatch.setattr(adopter, "run", without_the_filter)
    origin = make_source_repo(tmp_path / "Thing")
    head = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    source = adopter.Source(origin, None, "main", head)
    nowhere = tmp_path / REMOTES / "does-not-exist.git"

    legs = adopter._build_the_legs(**legs_arguments(
        tmp_path, seeded, source=source, remote=nowhere))

    assert legs is None
    err = capsys.readouterr().err
    pushing = f"pushing the {'seeded ' if seeded else ''}{SPEC} leg"
    assert err.count(REFUSED) == 1
    assert f"{REFUSED} {pushing}" in err
    assert err.count(ROLLED_BACK) == 1
    assert err.index("ONE legitimate exit") < err.index(ROLLED_BACK)


@pytest.fixture
def failing_filter_repo(tmp_path) -> dict:
    """The environment of an `execute` whose `git filter-repo` fails: a
    `git-filter-repo` FIRST on PATH that prints `STUB_COMPLAINT` and exits
    1, which `check` never runs and so can never foresee (#184 P1-1).

    `git <command>` looks in git's own exec-path before PATH, so a tool
    installed THERE would shadow the stub and extract for real; the test is
    skipped rather than allowed to pass or fail for that reason. A `#!` line
    is a POSIX kernel convention, so the tests that use it carry
    `WINDOWS_SKIP`, as `tests/test_free_plan_hint.py`'s stub `gh` does.
    """
    exec_path = Path(git("--exec-path", cwd=tmp_path).stdout.strip())
    if (exec_path / FILTER_REPO_TOOL).exists():
        pytest.skip(f"{exec_path} holds a git-filter-repo, which a stub on "
                    "PATH cannot shadow")
    binary = tmp_path / "stub-bin"
    binary.mkdir()
    stub = binary / FILTER_REPO_TOOL
    with stub.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"#!/bin/sh\necho '{STUB_COMPLAINT}' >&2\nexit 1\n")
    stub.chmod(0o755)
    return {"PATH": f"{binary}{os.pathsep}{os.environ['PATH']}"}


def small_plan(tmp_path: Path) -> Path:
    """A plan for a source with no submodule and no question to answer."""
    source = make_source_repo(tmp_path / "Thing", tree=SMALL_TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=ASSEMBLY)
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    return plan


def execute(plan: Path, remotes: Path, work: Path, env: dict | None = None):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(remotes), "--work-dir",
                      str(work), env=env)


@WINDOWS_SKIP
def test_a_failed_git_filter_repo_names_itself_on_stderr(
        tmp_path, failing_filter_repo):
    """The issue, end to end: `check` passes, both leg remotes are created,
    the extraction fails, and `execute` must say which command, where it
    ran, its exit and its output, and then what it left behind. On main at
    b18cca9 this was exit 2 and an empty stderr."""
    plan = small_plan(tmp_path)
    work = tmp_path / "work"

    result = execute(plan, tmp_path / REMOTES, work, failing_filter_repo)

    assert result.returncode == 2, result.stderr + result.stdout
    err = result.stderr
    assert err.count(REFUSED) == 1, err
    assert f"{REFUSED} extracting the {SPEC} leg." in err
    listing = work / f"{SPEC}-paths.txt"
    assert f"git filter-repo --paths-from-file {listing} --force" in err
    assert f"(in {work / f'{ASSEMBLY}-{SPEC}'})" in err
    assert "exit 1" in err
    assert STUB_COMPLAINT in err
    for role in UNIT_ROLES:
        bare = tmp_path / REMOTES / f"{ASSEMBLY}-{role}.git"
        assert bare.is_dir()
        assert str(bare) in err
    assert LIVE_LEG in err
    assert "neither leg is pushed" in err


@WINDOWS_SKIP
@needs_filter_repo
def test_following_the_notice_after_a_failed_leg_ends_adoption_verified(
        tmp_path, failing_filter_repo):
    """#184 P2-1: the notice's way out, followed word for word, must reach
    `adoption verified`. It used to name the leg repositories alone, and a
    re-run that deleted them and kept `--work-dir` met `destination path
    .../Northwind-spec already exists` at the spec leg's clone, after making
    both leg repositories again. The work directory here has a space in it,
    as a person's often does, and the notice names it whole."""
    plan = small_plan(tmp_path)
    remotes, work = tmp_path / REMOTES, tmp_path / "my work"
    failed = execute(plan, remotes, work, failing_filter_repo)
    assert failed.returncode == 2, failed.stderr + failed.stdout
    notice = next(line for line in failed.stderr.splitlines()
                  if line.startswith(ROLLED_BACK))
    named = NAMED.search(notice)
    assert named, notice
    assert [named["spec"], named["code"]] == [
        str(remotes / f"{ASSEMBLY}-{role}.git") for role in UNIT_ROLES]
    assert (f"Use a fresh --work-dir as well, or none: {work} holds "
            f"{ASSEMBLY}-{SPEC} from this run") in notice

    # What it says: delete the two repositories it names, and a fresh
    # --work-dir. The --local-remote-dir is the same one.
    for role in UNIT_ROLES:
        rmtree(Path(named[role]))
    rerun = execute(plan, remotes, tmp_path / "fresh work")

    assert rerun.returncode == 0, rerun.stderr + rerun.stdout
    assert "adoption verified" in rerun.stdout
