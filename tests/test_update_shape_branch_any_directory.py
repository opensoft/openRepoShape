# SPDX-License-Identifier: Apache-2.0
"""`--branch` is judged the same from any directory (#431).

`checked_branch` asked `git check-ref-format --branch <name>` with no `cwd`
and no `--git-dir`, so git set up whatever repository surrounded the person's
directory, and read its own failure as the name's fault. From three kinds of
directory a good name was refused as `update-branch-invalid`: a `.git` file
naming a gitdir that is gone (a linked worktree whose main repository was
moved), a `.git/config` with a syntax error, and a directory removed under
the shell. `--root` names the repository `apply` works on and has nothing to
do with where the person stands, which is why the answer must not depend on
it.

The question is now `shape_materialize._ask_git_branch`'s, the helper #355
wrote for the scaffold and the family holder: an empty temporary directory is
the `--git-dir` and the working directory, so no repository is in play. THE
VERDICT IS TOLD APART FROM A FAILURE OF GIT'S OWN, as `_branch_verdict` does
it: a git that refuses `main` too could not answer for any name, and says
"could not be checked" with the remedy for that, never "pick another name".

THE CLAIM IS MADE TWICE. End to end, `apply --branch` against an upstream that
has no change, from each directory, is `nothing to do` and exit 0; and
in-process, `checked_branch` itself, whose arms (a refusal by git, an
expansion, a git that cannot answer, a git that cannot be run) need a git
this suite does not have to break.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, run_script
from test_update_shape import PROJECT, scaffold_upstream_and_project

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import Refusal  # noqa: E402

UPDATE = REPO / "update-shape.py"
BRANCH = "shape/update-x"

#: What git says of a name it refuses, which the refusal carries.
GIT_SAYS = "`git check-ref-format --branch` refuses it"
#: The first words of each remedy: about the NAME, and about GIT.
ABOUT_THE_NAME = "Remediation: pass a branch name such as `shape/update-<sha>`"
ABOUT_GIT = "Remediation: the name was not judged"


@pytest.fixture(scope="module")
def update_shape():
    """`update-shape.py` as a module, so `checked_branch` is called in-process."""
    spec = importlib.util.spec_from_file_location("branch_any_dir_update",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def project(tmp_path_factory) -> dict:
    """A project at A and an upstream that has not moved from it, so every
    `apply` that gets past the branch question says `nothing to do`."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "update-shape-branch-any-directory")
    return {"upstream": upstream, "clone": clone, "a": commit_a}


@pytest.fixture
def root(project, tmp_path) -> Path:
    """A private copy of the project: the repository `--root` names."""
    target = tmp_path / PROJECT
    shutil.copytree(project["clone"], target, symlinks=True)
    return target


# --- the directories git cannot open ------------------------------------------


def ordinary(tmp_path: Path) -> Path:
    """The control: a directory no repository surrounds."""
    where = tmp_path / "ordinary"
    where.mkdir()
    return where


def gitfile_to_a_missing_gitdir(tmp_path: Path) -> Path:
    """A linked worktree whose main repository was moved or deleted: a `.git`
    FILE naming a gitdir that is not there."""
    where = tmp_path / "gitfile"
    where.mkdir()
    (where / ".git").write_bytes(
        b"gitdir: " + os.fsencode(tmp_path / "no-such-gitdir") + b"\n")
    return where


def malformed_git_config(tmp_path: Path) -> Path:
    """A repository whose `.git/config` has a syntax error."""
    where = tmp_path / "badconfig"
    where.mkdir()
    git("init", "-q", cwd=where)
    (where / ".git" / "config").write_bytes(b"[core\n\tthis is not config\n")
    return where


#: The directories a person may stand in that make a bare `git` die.
BROKEN = {"a-gitfile-to-a-missing-gitdir": gitfile_to_a_missing_gitdir,
          "a-malformed-git-config": malformed_git_config}


def apply_from(where: Path, root: Path, project: dict, branch: str = BRANCH,
               env: dict | None = None):
    """`apply --branch <branch>` against the unmoved upstream, run from
    `where`. `--branch=` so a value that starts with a dash is still a value."""
    return run_script(UPDATE, "apply", "--root", str(root), "--upstream",
                      str(project["upstream"]), "--yes",
                      f"--branch={branch}", cwd=where, env=env)


def apply_from_a_removed_directory(tmp_path: Path, root: Path, project: dict,
                                   branch: str = BRANCH):
    """The same, from a directory removed under the shell: a shell enters it,
    removes it, and runs the tool from where it WAS. POSIX only: a Windows
    process holds its directory open, so the removal is refused."""
    gone = tmp_path / "gone"
    gone.mkdir()
    return subprocess.run(
        ["sh", "-c", 'cd "$1" && rmdir "$1" && shift && exec "$@"', "sh",
         str(gone), sys.executable, str(UPDATE), "apply", "--root", str(root),
         "--upstream", str(project["upstream"]), "--yes",
         f"--branch={branch}"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        stdin=subprocess.DEVNULL, check=False,
        env={**os.environ, "LANES_LANE": ""})


def assert_nothing_to_do(result) -> None:
    assert result.returncode == 0, result.stdout + result.stderr
    assert "nothing to do" in result.stdout, result.stdout
    assert "update-branch-invalid" not in result.stderr, result.stderr


def test_the_control_is_nothing_to_do_from_an_ordinary_directory(
        project, root, tmp_path):
    """THE ISSUE'S CONTROL: the premise of every comparison below."""
    assert_nothing_to_do(apply_from(ordinary(tmp_path), root, project))


@pytest.mark.parametrize("name", BROKEN)
def test_a_good_name_is_taken_from_a_directory_git_cannot_open(
        project, root, tmp_path, name):
    """The first two of the issue's three: a `.git` file naming a missing
    gitdir and a malformed `.git/config`. Each exits as an ordinary directory
    does, `nothing to do`, and never says the name was refused."""
    assert_nothing_to_do(apply_from(BROKEN[name](tmp_path), root, project))


@WINDOWS_SKIP
def test_a_good_name_is_taken_from_a_directory_removed_under_the_shell(
        project, root, tmp_path):
    """The third: git cannot even read the current working directory."""
    assert_nothing_to_do(
        apply_from_a_removed_directory(tmp_path, root, project))


# --- a name git refuses is still refused, from there --------------------------


@pytest.mark.parametrize("branch", ["a..b", "x.lock", "a/"])
@pytest.mark.parametrize("name", [*BROKEN, "ordinary"])
def test_a_name_git_refuses_is_still_refused_as_the_names_fault(
        project, root, tmp_path, name, branch):
    """`a..b`, `x.lock` and `a/` are inside the alphabet and refused by git,
    which is what the question is for. The code, the line's own prefix and
    the remedy about the NAME are what they were; it is not said to be
    unchecked."""
    where = ({**BROKEN, "ordinary": ordinary})[name](tmp_path)

    result = apply_from(where, root, project, branch)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED update-branch-invalid: --branch {branch!r} "), result.stderr
    assert GIT_SAYS in result.stderr
    assert ABOUT_THE_NAME in result.stderr
    assert "could not be checked" not in result.stderr
    assert result.stdout == "", "refused before anything was read or written"


@WINDOWS_SKIP
@pytest.mark.parametrize("branch", ["a..b", "x.lock", "a/"])
def test_a_name_git_refuses_is_refused_from_a_removed_directory_too(
        project, root, tmp_path, branch):
    result = apply_from_a_removed_directory(tmp_path, root, project, branch)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED update-branch-invalid: --branch {branch!r} "), result.stderr
    assert GIT_SAYS in result.stderr
    assert "could not be checked" not in result.stderr


def test_an_expansion_is_refused_in_a_repository_with_a_reflog(
        project, root, tmp_path):
    """`@{-1}` is `the branch checked out before this one` to a git that has
    a repository. Run from one whose previous checkout was another branch, it
    is still refused, and not by a git that lent it that reflog."""
    where = tmp_path / "with-a-reflog"
    where.mkdir()
    git("init", "-q", "-b", "main", cwd=where)
    (where / "a.txt").write_text("a\n", encoding="utf-8")
    git("add", "--", "a.txt", cwd=where)
    git("commit", "-q", "-m", "a", cwd=where)
    git("checkout", "-q", "-b", "other", cwd=where)
    git("checkout", "-q", "main", cwd=where)
    assert git("rev-parse", "--abbrev-ref", "@{-1}",
               cwd=where).stdout.strip() == "other", "fixture: a reflog"

    result = apply_from(where, root, project, "@{-1}")

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        "REFUSED update-branch-invalid: --branch '@{-1}' "), result.stderr
    assert ABOUT_THE_NAME in result.stderr
    assert result.stdout == ""


# --- a git that could not answer ----------------------------------------------


def a_global_config_git_cannot_read(tmp_path: Path) -> dict:
    """An environment under which `git` fails for EVERY name, `main` too:
    its global config does not parse."""
    broken = tmp_path / "broken-gitconfig"
    broken.write_bytes(b"[core\n\tthis is not config\n")
    return {"GIT_CONFIG_GLOBAL": str(broken), "GIT_CONFIG_NOSYSTEM": "1"}


@pytest.mark.parametrize("branch", [BRANCH, "a..b"])
def test_a_git_that_cannot_answer_says_the_name_could_not_be_checked(
        project, root, tmp_path, branch):
    """A GIT THAT REFUSES `main` TOO JUDGED NOTHING, so it is not the name's
    fault, for the good name and for the one git would have refused: the
    sentence says "could not be checked", and the remedy is about git."""
    env = a_global_config_git_cannot_read(tmp_path)

    result = apply_from(ordinary(tmp_path), root, project, branch, env=env)

    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(
        f"REFUSED update-branch-invalid: --branch {branch!r} "), result.stderr
    assert "could not be checked" in result.stderr
    assert "so git could not answer" in result.stderr
    assert "bad config" in result.stderr, "git's own words are quoted"
    assert ABOUT_GIT in result.stderr
    assert ABOUT_THE_NAME not in result.stderr
    assert "is not a branch name git will create" not in result.stderr
    assert result.stdout == ""


# --- `checked_branch`, in-process ---------------------------------------------


def test_the_question_is_the_one_helper_shape_materialize_asks_it_with(
        update_shape):
    """NOT A SECOND COPY: the name `update-shape.py` asks with is the object
    `shape_materialize` defines, and so are the control name and the remedy
    for a git that could not answer."""
    assert update_shape._ask_git_branch is shape_materialize._ask_git_branch
    assert update_shape.BRANCH_CONTROL == shape_materialize.BRANCH_CONTROL
    assert (update_shape.BRANCH_UNCHECKED_REMEDIATION
            is shape_materialize.BRANCH_UNCHECKED_REMEDIATION)


@pytest.mark.parametrize("name", [*BROKEN, "ordinary"])
def test_checked_branch_takes_a_good_name_from_any_directory(
        update_shape, tmp_path, monkeypatch, name):
    monkeypatch.chdir(({**BROKEN, "ordinary": ordinary})[name](tmp_path))
    assert update_shape.checked_branch(BRANCH) == BRANCH


@WINDOWS_SKIP
def test_checked_branch_takes_a_good_name_from_a_removed_directory(
        update_shape, tmp_path, monkeypatch):
    gone = tmp_path / "gone"
    gone.mkdir()
    monkeypatch.chdir(gone)
    gone.rmdir()
    assert update_shape.checked_branch(BRANCH) == BRANCH


def test_a_name_outside_the_alphabet_never_reaches_git(update_shape,
                                                       monkeypatch):
    """The alphabet check comes first and is kept: nothing that reads as an
    option, or holds a space or a brace, is put to git at all."""
    def asked(name):
        raise AssertionError(f"git was asked about {name!r}")

    monkeypatch.setattr(update_shape, "_ask_git_branch", asked)
    for value in ("-x", "--upload-pack=touch", "a b", "@{-1}", "/a", ".a"):
        with pytest.raises(Refusal) as caught:
            update_shape.checked_branch(value)
        assert caught.value.code == "update-branch-invalid"
        assert "will put on a `git` or `gh` command line" in \
            caught.value.detail
        assert caught.value.remediation == update_shape.BRANCH_REMEDIATION


def test_a_name_git_would_expand_is_refused_as_the_names_fault(
        update_shape, monkeypatch):
    """A spelling git answers with ANOTHER name is refused too, because
    `apply` names the branch it creates: the alphabet admits none today, so a
    git that expands one is stood in for."""
    monkeypatch.setattr(update_shape, "_ask_git_branch",
                        lambda name: "main")

    with pytest.raises(Refusal) as caught:
        update_shape.checked_branch("shape/x")

    assert caught.value.code == "update-branch-invalid"
    assert caught.value.detail.startswith("--branch 'shape/x' ")
    assert "reads it as 'main', not as written" in caught.value.detail
    assert caught.value.remediation == update_shape.BRANCH_REMEDIATION


def test_a_git_that_cannot_be_run_is_unchecked_and_not_the_names_fault(
        update_shape, monkeypatch):
    """`git` missing from PATH, or no empty directory to ask it from: the
    answer is not git's, so the remedy is the one for a git that could not
    answer."""
    def missing(name):
        raise FileNotFoundError(2, "No such file or directory", "git")

    monkeypatch.setattr(update_shape, "_ask_git_branch", missing)

    with pytest.raises(Refusal) as caught:
        update_shape.checked_branch(BRANCH)

    assert caught.value.code == "update-branch-invalid"
    assert caught.value.detail.startswith(f"--branch {BRANCH!r} ")
    assert "could not be checked" in caught.value.detail
    assert "could not be run" in caught.value.detail
    assert caught.value.remediation == update_shape.BRANCH_UNCHECKED_REMEDIATION


def test_a_refusal_by_git_is_asked_about_the_control_name_before_it_is_blamed(
        update_shape, monkeypatch):
    """The control is asked only after git refused the person's name, and a
    git that answers it is judging: the name is the fault."""
    asked = []

    def refuses_everything_but_main(name):
        asked.append(name)
        if name != update_shape.BRANCH_CONTROL:
            raise update_shape.CommandFailed(
                ["git", "check-ref-format"], None, 1, "fatal: not valid")
        return name

    monkeypatch.setattr(update_shape, "_ask_git_branch",
                        refuses_everything_but_main)

    with pytest.raises(Refusal) as caught:
        update_shape.checked_branch("a..b")

    assert asked == ["a..b", update_shape.BRANCH_CONTROL]
    assert GIT_SAYS in caught.value.detail
    assert "(fatal: not valid)" in caught.value.detail
    assert caught.value.remediation == update_shape.BRANCH_REMEDIATION
