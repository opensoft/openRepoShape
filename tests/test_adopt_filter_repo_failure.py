# SPDX-License-Identifier: Apache-2.0
"""`execute` says why a leg failed and what it left behind (#171).

`run` (`scripts/shape_materialize.py`) only RAISES `CommandFailed`; it prints
nothing. `_build_the_legs` caught that exception and returned None on the
premise that `run` had already said which command failed and why, so an
`execute` whose `git filter-repo` failed ended with both bare leg repositories
created, exit 2 and an EMPTY stderr, and the corrected re-run met
`leg-remote-exists`. On main at b18cca9 the end-to-end test below produces
exactly that, with a `.gitmodules` that git's `--list` reads and git's
submodule reader dies on: a second section whose `path` has no value.

Everything but the last test needs no `git filter-repo`: the unit tests stub
the leg builders, or run a real leg builder against a remote that does not
exist (the extraction skips only the filter itself), and call
`_build_the_legs` in this process. The last runs `adopt-project.py execute`
for real and is skipped on a machine without the tool.

NO NETWORK AND NO GITHUB: every remote is a bare repository on disk, or no
repository at all.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, git, make_source_repo, resolve,
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

#: One case per way a leg is built: what `_build_the_legs` is told is seeded,
#: the verb it should name, and the command that leg's builder would die on.
LEG_FAILURES = [([], "extracting", FILTER_REPO),
                ([SPEC], "seeding", SEEDING_COMMIT)]
LEG_FAILURE_IDS = ["extracted-leg", "seeded-leg"]

#: A second section whose `path` has no value. `git config --list` accepts the
#: file, and git's submodule reader, which `git filter-repo` runs through
#: `git fast-export`, does not.
BARE_PATH_SECTION = '[submodule "b"]\n\tpath\n'

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
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
        self.events.append((self.name, "flush"))


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
    human reads the failure, fixes the plan and re-runs; the re-run is refused
    by `_create_leg_remotes`, so the notice says so BEFORE it happens, for
    both kinds of remote, and names the two repositories to delete or to
    replace."""
    refuse_every_leg(adopter, monkeypatch, command, tmp_path)
    arguments = legs_arguments(tmp_path, seeded)

    assert adopter._build_the_legs(**arguments) is None

    notice = capsys.readouterr().err.split("--- end output ---", 1)[1]
    assert ROLLED_BACK in notice
    for role in UNIT_ROLES:
        assert arguments["urls"][role] in notice
    assert "--local-remote-dir" in notice
    assert "leg-remote-exists" in notice
    assert "gh repo create" in notice
    assert "already taken" in notice
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
                                    arguments["urls"], "main", True)

    assert refused.value.code == "leg-remote-exists"


def test_a_rerun_against_github_has_gh_repo_create_refused(
        adopter, monkeypatch, tmp_path):
    """The second half: against GitHub the first thing a re-run does is
    `gh repo create` for the spec leg, and `run` raises when `gh` finds the
    name taken. Nothing in `_create_leg_remotes` catches it, so the run stops
    there, before the code leg is touched."""
    arguments = legs_arguments(tmp_path, [])
    arguments["repositories"]["assembly"] = f"testorg/{ASSEMBLY}"
    calls: list = []

    def name_taken(args, *_rest, **_keywords):
        calls.append(args)
        raise adopter.CommandFailed(args, None, 1, "name already exists")

    monkeypatch.setattr(adopter, "run", name_taken)

    with pytest.raises(adopter.CommandFailed):
        adopter._create_leg_remotes({}, arguments["names"],
                                    arguments["repositories"],
                                    arguments["urls"], "main", False)

    assert [call[:4] for call in calls] == [
        ["gh", "repo", "create", arguments["repositories"][SPEC]]]


def test_stdout_is_flushed_before_the_failure_is_written_to_stderr(
        adopter, monkeypatch, tmp_path):
    """`execute` announces each bare leg repository on stdout. Piped, that is
    block-buffered, so without a flush a log that merges the two streams shows
    the failure BEFORE the lines that explain what it is about."""
    events: list = []
    monkeypatch.setattr(sys, "stdout", Stream("stdout", events))
    monkeypatch.setattr(sys, "stderr", Stream("stderr", events))
    refuse_every_leg(adopter, monkeypatch, FILTER_REPO, tmp_path)

    assert adopter._build_the_legs(**legs_arguments(tmp_path, [])) is None

    assert ("stdout", "flush") in events
    assert (events.index(("stdout", "flush"))
            < events.index(("stderr", "write")))


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
        (work / "README.md").write_text("seeded\n", encoding="utf-8")
        return ["README.md"]

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
    assert err.index("legitimate exits") < err.index(ROLLED_BACK)


@needs_filter_repo
def test_a_failed_git_filter_repo_names_itself_on_stderr(tmp_path):
    """The issue's reproduction: a source whose `.gitmodules` carries a section
    with a bare `path`. `check` passes, both leg remotes are created, the
    extraction fails, and `execute` must say which command and why."""
    dependency = make_source_repo(
        tmp_path / "dependency", tree={"value.txt": "first\n"},
        edits=(("value.txt", "second\n", "Update dependency"),))
    dependency_remote = tmp_path / "dependency.git"
    git("clone", "-q", "--bare", str(dependency), str(dependency_remote),
        cwd=tmp_path)
    source = make_source_repo(tmp_path / "Thing")
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency_remote),
        "upstream/dependency", cwd=source)
    # Append to what `git submodule add` wrote rather than writing the url
    # again: a Windows path in a hand-written `.gitmodules` needs git's own
    # escaping for the backslash. LF, as git wrote it, on every platform.
    with (source / ".gitmodules").open("a", encoding="utf-8",
                                       newline="\n") as handle:
        handle.write(BARE_PATH_SECTION)
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qam",
        "Pin existing dependency", cwd=source)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in (("examples/", SPEC), (".claude/", "root"),
                      ("release.yaml", "root"),
                      (".gitmodules", CODE), ("upstream/", CODE)):
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout

    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        "--work-dir", str(tmp_path / "work"))

    assert result.returncode == 2, result.stderr + result.stdout
    assert REFUSED in result.stderr, result.stdout
    assert "git filter-repo --paths-from-file" in result.stderr
    for role in UNIT_ROLES:
        bare = f"{ASSEMBLY}-{role}.git"
        assert (tmp_path / REMOTES / bare).is_dir()
        assert bare in result.stderr
    assert "leg-remote-exists" in result.stderr
