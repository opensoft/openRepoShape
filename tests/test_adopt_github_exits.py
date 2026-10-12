# SPDX-License-Identifier: Apache-2.0
"""AGENTS.md step 7 names the two exits `execute` has in GitHub mode alone (#304).

Step 7 said that a non-zero exit of `adopt-project.py execute` is to fix the
plan and re-run into fresh legs. That is the way out of a failed verification,
exit 1. A GitHub run has two exits more, and both come AFTER both legs and the
split branch are pushed: `gh pr create` refused, and the topic that will not
set. Each is exit 2, each prints the command that finishes the job by hand,
and following the old sentence abandoned a pushed adoption for a second pair
of legs beside it.

No test reached either exit: `--local-remote-dir`, the path every test takes,
skips both (`if not local:` in `cmd_execute`). The two runs here are the
issue's own reproduction, with no network and nothing created anywhere: a `gh`
that refuses one command and makes the other repositories as bare ones under
the test's directory, and every `https://github.com/` URL rewritten to that
directory by a throwaway global git config.

THE SHIM IS A `#!` SCRIPT, so the runs are `WINDOWS_SKIP`ped, and they need
`git filter-repo` as every `execute` test does. Reading step 7, and the
module's own EXIT CODES paragraph, runs everywhere.

`adopt-project.py`'s own two messages are asserted here WORD FOR WORD, and the
anchors step 7 gives (`IS pushed`, `gh pr create`, the topic) are asserted
against them, so rewording either side alone fails a test instead of leaving
an assistant a sentence about a message that no longer exists.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, WINDOWS_SKIP, git, make_source_repo,
                      run_script, write_plan)

#: `execute` REQUIRES `git filter-repo`; without it the two runs below are
#: skipped, as every `execute` test in this suite is.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

ORG = "testorg"
NORTHWIND = "Northwind"
TOPIC = "xf-project-northwind"
SPLIT_BRANCH = "adopt/three-repo-shape"
#: A source small enough that `plan` asks no question, so `execute` runs on
#: the plan as written.
SOURCE_TREE = {"README.md": "# Northwind\n", "src/app.py": "print(1)\n",
               "docs/spec.md": "# Spec\n"}

#: The heading of step 7, which the point runs from to the next blank line.
STEP_7 = "7. **Read the verification table back to them.**"

#: What a refused `gh pr create` prints after the REFUSED block, and what a
#: topic that will not set prints. Both are `adopt-project.py`'s own words.
BRANCH_IS_PUSHED = (
    "The branch IS pushed. Open the pull request by hand:\n"
    f"    gh pr create --repo {ORG}/{NORTHWIND} --base main "
    f"--head {SPLIT_BRANCH}")
SPLIT_IS_PUSHED = (
    "The split IS pushed and the pull request IS open. Set the topic by "
    "hand:\n" + "\n".join(
        f"    gh repo edit {ORG}/{name} --add-topic {TOPIC}"
        for name in (NORTHWIND, f"{NORTHWIND}-spec", f"{NORTHWIND}-code")))

#: `gh` with no network. `repo create` makes a bare repository under
#: $FAKE_GH_ROOT, which is what the rewritten `https://github.com/` URL then
#: names, and the one command named in $FAKE_GH_REFUSES is refused the way a
#: token without the permission is.
GH_SHIM = textwrap.dedent("""\
    #!/bin/sh
    case "$1 $2" in
      "$FAKE_GH_REFUSES")
        echo "HTTP 403: Resource not accessible by integration" >&2; exit 1;;
      "repo create")
        git init -q --bare -b main "$FAKE_GH_ROOT/$3.git" && echo "https://github.com/$3";;
      "pr create") echo "https://github.com/testorg/Northwind/pull/1";;
      "repo edit") ;;
      *) exit 1;;
    esac
    """)


@pytest.fixture
def adopter():
    """`adopt-project.py` as a module, to read its EXIT CODES paragraph."""
    module_spec = importlib.util.spec_from_file_location("adopt_github_exits",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def step_7() -> str:
    """Step 7 of AGENTS.md, from its heading to the blank line after it, as
    one line of single-spaced text."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    return " ".join(agents.split(STEP_7, 1)[1].split("\n\n", 1)[0].split())


def github_run(tmp_path: Path, refuses: str):
    """Plan a small source and `execute` it in GitHub mode, with a `gh` that
    refuses `refuses`. Returns `(result, github)`: the run, and the directory
    that stands for github.com, with `testorg/<name>.git` in it."""
    github = tmp_path / "github"
    (github / ORG).mkdir(parents=True)
    source = make_source_repo(tmp_path / NORTHWIND, tree=SOURCE_TREE, edits=())
    # The assembly root is the repository the source was cloned from: the
    # split branch is pushed back to it.
    git("clone", "-q", "--bare", ".", str(github / ORG / f"{NORTHWIND}.git"),
        cwd=source)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_text(GH_SHIM, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    config = tmp_path / "gitconfig"
    config.write_text(f'[url "{github.as_posix()}/"]\n'
                      "\tinsteadOf = https://github.com/\n", encoding="utf-8")

    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    result = run_script(
        ADOPT, "execute", "--plan", str(plan), "--yes",
        "--work-dir", str(tmp_path / "work"),
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "GIT_CONFIG_GLOBAL": str(config), "GIT_ALLOW_PROTOCOL": "file",
             "FAKE_GH_ROOT": str(github), "FAKE_GH_REFUSES": refuses})
    return result, github


def heads(repository: Path) -> list[str]:
    """The branches `repository` (a bare one) holds."""
    listed = git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                 cwd=repository).stdout
    return sorted(listed.split())


# --- AGENTS.md step 7 --------------------------------------------------------

def test_step_7_keys_its_advice_to_the_exit_and_not_to_non_zero():
    """Exit 1 is the failed verification and keeps its way out; exit 2 saying
    `IS pushed` is the GitHub run's two exits after the push, and its way out
    is the command the tool prints, never a re-run into a second pair of legs.

    Each phrase is one the sentence cannot be true without. The exit 1 half
    is read as `fix the plan` and `fresh legs` only, so a rewording of how the
    failed verification is left (#188 asks for the split branch deleted too)
    does not fail a test about the two exits after the push.
    """
    said = step_7()
    assert "If it exits non-zero, STOP and relay it" in said, said
    assert "Exit 1, a failed verification:" in said, said
    assert "fix the plan" in said and "fresh legs" in said, said
    assert "Exit 2 saying `IS pushed`" in said, said
    assert "GitHub only" in said, said
    assert "`gh pr create`" in said and "the topic" in said, said
    assert "finish with the command it prints" in said, said
    assert "never re-run into fresh legs" in said, said
    assert "prints no table" in said, said
    # The order is the reading order: the failed verification first, and the
    # exit-2 case read AS the exception to it, not under it.
    assert said.index("Exit 1") < said.index("Exit 2 saying"), said


def test_the_modules_exit_codes_paragraph_names_the_exits_after_the_push(
        adopter):
    """The EXIT CODES paragraph gave exit 2 one meaning, "the question could
    not be asked". It says what comes after the push, in the tool's own
    words, so the file and the messages it describes cannot part."""
    codes = " ".join(adopter.__doc__.split("EXIT CODES:", 1)[1].split())
    assert "two more exit 2s" in codes, codes
    assert "AFTER both legs and the split branch are pushed" in codes, codes
    assert "`gh pr create` refused (`The branch IS pushed`" in codes, codes
    assert ("the topic would not set (`The split IS pushed and the pull "
            "request IS open`") in codes, codes
    assert "no table is printed" in codes, codes
    assert "a re-run into fresh legs abandons the pushed pair" in codes, codes


# --- the two exits, run -----------------------------------------------------

@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
@pytest.mark.parametrize("refuses, refused, by_hand, verified", [
    pytest.param("pr create", "REFUSED opening the pull request.",
                 BRANCH_IS_PUSHED, False, id="gh-pr-create-refused"),
    pytest.param("repo edit", "REFUSED setting the project topic.",
                 SPLIT_IS_PUSHED, True, id="the-topic-will-not-set"),
])
def test_each_exit_after_the_push_is_exit_2_with_a_command_to_finish_by_hand(
        tmp_path, refuses, refused, by_hand, verified):
    result, github = github_run(tmp_path, refuses)

    # The exit, and what it prints: the REFUSED block, then the command.
    assert result.returncode == 2, result.stdout + result.stderr
    assert refused in result.stderr, result.stderr
    assert by_hand in result.stderr, result.stderr

    # Both legs and the split branch ARE pushed, which is why a re-run is not
    # the way out: it would push a second pair beside these.
    for leg in ("spec", "code"):
        assert heads(github / ORG / f"{NORTHWIND}-{leg}.git") == ["main"]
    assert SPLIT_BRANCH in heads(github / ORG / f"{NORTHWIND}.git")

    # Whether there is a table. A refused `gh pr create` returns before
    # `_verify` runs; a refused topic is reported after it. If `execute` ever
    # verifies before it exits on the first, step 7's "prints no table" is
    # the sentence to change with it.
    if verified:
        assert f"  pull request https://github.com/{ORG}/{NORTHWIND}/pull/1" \
            in result.stdout, result.stdout
        assert "VERIFICATION" in result.stdout, result.stdout
        assert ("adoption verified: every source path is in exactly one "
                "place") in result.stdout, result.stdout
    else:
        assert "VERIFICATION" not in result.stdout, result.stdout
        assert "adoption verified" not in result.stdout, result.stdout
        assert "  split " in result.stdout, result.stdout

    # What step 7 says of it is what the tool printed: the marker words and
    # the command it names.
    said = step_7()
    assert "IS pushed" in said and "IS pushed" in by_hand
    assert "gh pr create" in said and "gh pr create" in BRANCH_IS_PUSHED
    assert "the topic" in said and "--add-topic" in SPLIT_IS_PUSHED
