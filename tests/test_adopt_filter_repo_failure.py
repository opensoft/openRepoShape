# SPDX-License-Identifier: Apache-2.0
"""`execute` says why a leg could not be built, after both leg remotes exist (#171).

`run` (`scripts/shape_materialize.py`) only RAISES `CommandFailed`; it prints
nothing. `_build_the_legs` caught that exception and returned None on the
premise that `run` had already said which command failed and why, so an
`execute` whose `git filter-repo` failed ended with both bare leg repositories
created, exit 2 and an EMPTY stderr, and the corrected re-run met
`leg-remote-exists`. On main at b18cca9 the end-to-end test below produces
exactly that, with a `.gitmodules` that git's `--list` reads and git's
submodule reader dies on: a second section whose `path` has no value.

The first three tests need no `git filter-repo`: they stub the extraction, or
run a real seeded leg against a remote that does not exist, and call
`_build_the_legs` in this process. The last runs `adopt-project.py execute`
for real and is skipped on a machine without the tool.

NO NETWORK AND NO GITHUB: every remote is a bare repository on disk, or no
repository at all.
"""

from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path

import pytest

from conftest import (ADOPT, FILE_PROTOCOL, git, make_source_repo, resolve,
                      run_script, write_plan)

SPEC, CODE = "spec", "code"
UNIT_ROLES = (SPEC, CODE)
ASSEMBLY = "Northwind"
REMOTES = "remotes"
REFUSED = "REFUSED"
FILTER_REPO = ["git", "filter-repo", "--paths-from-file", "spec-paths.txt",
               "--force"]
FILTER_REPO_LINE = " ".join(FILTER_REPO)
GIT_COMPLAINT = "fatal: bad config line 5 in file .gitmodules"

#: A second section whose `path` has no value. `git config --list` accepts the
#: file, and git's submodule reader, which `git filter-repo` runs through
#: `git fast-export`, does not.
BARE_PATH_SECTION = '[submodule "b"]\n\tpath\n'

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_filter_repo_failure",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legs_arguments(tmp_path: Path, seeded: list, remote: Path | None = None):
    """What `cmd_execute` hands `_build_the_legs`, for two legs and no plan.

    `remote` is where every leg would be pushed; the unit tests that stub the
    leg builders never reach it.
    """
    url = str(remote or tmp_path / REMOTES / "leg.git")
    names = {role: f"{ASSEMBLY}-{role}" for role in UNIT_ROLES}
    names["assembly"] = ASSEMBLY
    return dict(
        source=None,
        names=names,
        repositories={role: f"testorg/{names[role]}" for role in UNIT_ROLES},
        urls={role: url for role in UNIT_ROLES},
        values={},
        work_root=tmp_path / "work",
        paths_for={role: [f"{role}/file.md"] for role in UNIT_ROLES},
        seeded=seeded,
        branch="adopt/three-repo-shape",
        tracking="main")


@pytest.mark.parametrize("seeded, verb", [([], "extracting"),
                                          ([SPEC], "seeding")])
def test_a_failed_leg_is_printed_with_its_command_and_its_output(
        adopter, monkeypatch, capsys, tmp_path, seeded, verb):
    """`run` raised and printed nothing, so this function is the only place
    that can say what the human is waiting to read."""
    def refused(*_args):
        raise adopter.CommandFailed(FILTER_REPO, tmp_path, 1, GIT_COMPLAINT)

    monkeypatch.setattr(adopter, "_extract_leg", refused)
    monkeypatch.setattr(adopter, "_seed_leg", refused)

    legs = adopter._build_the_legs(**legs_arguments(tmp_path, seeded))

    assert legs is None
    err = capsys.readouterr().err
    assert f"{REFUSED} {verb} the {SPEC} leg." in err
    assert FILTER_REPO_LINE in err
    assert "exit 1" in err
    assert GIT_COMPLAINT in err


def test_a_refused_push_is_reported_once_with_its_ruleset_hint(
        adopter, monkeypatch, capsys, tmp_path):
    """A refused push is the one failure `_seed_leg` (and `_extract_leg`)
    already print, with `RULESET_HINT`, before they re-raise it. A second
    block for the same command is noise that buries the hint, so the leg
    builder's own report is the only one."""
    def write_one_file(_template, work, _values):
        work.mkdir(parents=True, exist_ok=True)
        (work / "README.md").write_text("seeded\n", encoding="utf-8")

    monkeypatch.setattr(adopter, "copy_tree", write_one_file)
    nowhere = tmp_path / REMOTES / "does-not-exist.git"

    legs = adopter._build_the_legs(
        **legs_arguments(tmp_path, [SPEC], remote=nowhere))

    assert legs is None
    err = capsys.readouterr().err
    assert err.count(REFUSED) == 1
    assert f"{REFUSED} pushing the seeded {SPEC} leg" in err
    assert "NOTHING has been rolled back" in err


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
    (source / ".gitmodules").write_text(
        f'[submodule "a"]\n\tpath = upstream/dependency\n'
        f"\turl = {dependency_remote}\n{BARE_PATH_SECTION}",
        encoding="utf-8")
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
    assert (tmp_path / REMOTES / f"{ASSEMBLY}-{SPEC}.git").is_dir()
