# SPDX-License-Identifier: Apache-2.0
"""AGENTS.md step 7 names the two exits `execute` has in GitHub mode alone (#304).

Step 7 said that a non-zero exit of `adopt-project.py execute` is to fix the
plan and re-run into fresh legs. That is the way out of a failed verification,
exit 1. A GitHub run has two exits more, and both come AFTER both legs and the
split branch are pushed: `gh pr create` refused, and the topic that will not
set. Each is exit 2, each prints the command that finishes the job by hand,
and following the old sentence abandoned a pushed adoption for a second pair
of legs beside it.

A refused `gh pr create` used to end the run before the verification, so the
pull request the person was told to open by hand was for a split nothing had
checked. `execute` now verifies on that path too, as it always did when the
topic would not set, and says what the verification found: a split that passes
gets the command to open its pull request AFTER the table, and one that fails
is exit 1 with no such command.

No test reached either exit: `--local-remote-dir`, the path every test takes,
skips both (`if not local:` in `cmd_execute`). The runs here are the issue's
own reproduction, with no network and nothing created anywhere: a `gh` that
refuses one command and makes the other repositories as bare ones under the
test's directory, and every `https://github.com/` URL rewritten to that
directory by a throwaway global git config.

THE SHIM IS A `#!` SCRIPT, so the runs are `WINDOWS_SKIP`ped, and they need
`git filter-repo` as every `execute` test does. Reading step 7, and the
module's own EXIT CODES paragraph, runs everywhere.

THE REAL `gh` MUST NOT BE REACHABLE FROM A RUN. The shim is first on PATH, but
`subprocess` goes on to the next directory when the program it found cannot be
executed, and a `gh` there would be the operator's. So the run's environment
also carries an unauthenticated token and an empty config directory, and takes
every directory that holds a `gh` out of PATH where it can (`without_a_real_gh`).

The command a refused `gh pr create` leaves to do by hand is the command that
was refused, title and body included, because `gh` will not take a pull
request without them where there is no terminal to ask on. The tests parse it
and compare it with what the shim was run with; none of them runs it.

`adopt-project.py`'s own two messages are asserted here WORD FOR WORD, and the
anchors step 7 gives (`IS pushed`, `gh pr create`, the topic) are asserted
against them, so rewording either side alone fails a test instead of leaving
an assistant a sentence about a message that no longer exists.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, WINDOWS_SKIP, a_hook_that_unstages, git,
                      make_source_repo, run_script, write_plan)
from test_adopt_tracking_branch import OPEN_THE_SPLIT, PULL_REQUEST_FOLLOW_UP

#: `execute` REQUIRES `git filter-repo`; without it the runs below are
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
# A failing verification is a REAL failure of `_verify`, with nothing in the
# tool replaced: a `pre-commit` hook takes a file the shape's pin names out
# of the split commit (`conftest.a_hook_that_unstages`, `github_run`'s
# `failing`), and the verification fails (`adopt-shape-file-missing`). The
# source's own `contracts/shape-pin.yaml` kept in the root stood for it until
# #524, which refuses that plan before any leg exists.

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
#: What a refused `gh pr create` says INSTEAD when the split failed the
#: verification: the refusal above names the exact command that was tried.
NOT_BY_HAND = ("No pull request was opened, and none should be: the split "
               "above did not pass verification.")
#: What a failed verification says of what the run put in place on GitHub
#: BEFORE it verified (#523, auA-12): the pull request it opened, which the
#: branch deletion the way out names closes, and the topic, on each
#: repository that took it.
STILL_OPEN = (f"A pull request for that branch IS open on {ORG}/{NORTHWIND}, "
              "for a split that did not pass verification: deleting the "
              "branch, as above, closes it.")
TOPIC_STAYS = (f"The topic {TOPIC} stays set on {ORG}/{NORTHWIND}, "
               f"{ORG}/{NORTHWIND}-spec and {ORG}/{NORTHWIND}-code: the "
               "re-run sets it again on the root and the legs it makes, and "
               "a leg left behind keeps it.")
VERIFIED = "adoption verified: every source path is in exactly one place"
FINDING = "FINDING adopt-shape-file-missing:"
#: What `_verify` used to say after every pass, whether or not a pull request
#: existed to review.
NEXT = f"NEXT: review the pull request on {NORTHWIND}"
BY_HAND = "Open the pull request by hand:"

#: `gh` with no network. `repo create` makes a bare repository under
#: $FAKE_GH_ROOT, which is what the rewritten `https://github.com/` URL then
#: names, and `repo view <repository> --json nameWithOwner`, which `execute`
#: asks of each leg before it makes either (#798), finds one there and gives
#: gh's not-found answer for any other. Each command $FAKE_GH_REFUSES names
#: (`|` between them; `pr create`, or `repo edit <repository>` for one
#: repository alone) is refused the way a token without the permission is, after writing
#: the arguments it was given, NUL-separated, to
#: $FAKE_GH_ROOT/refused-arguments. `pr create` is refused as GitHub refuses a
#: base that is no branch of the repository (#479), and records `<repository>
#: <base>` in $FAKE_GH_ROOT/opened when it opens one. Every call records the
#: token and the config directory it was run with in $FAKE_GH_ROOT/environment,
#: which are what a real `gh` would have been run with, and its first three
#: arguments, a line each, in $FAKE_GH_ROOT/calls.
GH_SHIM = textwrap.dedent("""\
    #!/bin/sh
    printf '%s\\n%s\\n' "$GH_TOKEN" "$GH_CONFIG_DIR" > "$FAKE_GH_ROOT/environment"
    printf '%s %s %s\\n' "$1" "$2" "$3" >> "$FAKE_GH_ROOT/calls"
    refused=no
    old_ifs=$IFS; IFS='|'
    for one in $FAKE_GH_REFUSES; do
      case "$one" in "$1 $2"|"$1 $2 $3") refused=yes;; esac
    done
    IFS=$old_ifs
    if [ "$refused" = yes ]; then
      : > "$FAKE_GH_ROOT/refused-arguments"
      for argument in "$@"; do
        printf '%s\\0' "$argument" >> "$FAKE_GH_ROOT/refused-arguments"
      done
      echo "HTTP 403: Resource not accessible by integration" >&2; exit 1
    fi
    case "$1 $2 $4 $5" in
      "repo view --json nameWithOwner")
        if [ -d "$FAKE_GH_ROOT/$3.git" ]; then
          printf '{"nameWithOwner": "%s"}\\n' "$3"
        else
          said="GraphQL: Could not resolve to a Repository"
          echo "$said with the name '$3'. (repository)" >&2
          exit 1
        fi
        exit 0;;
    esac
    case "$1 $2" in
      "repo create")
        git init -q --bare -b main "$FAKE_GH_ROOT/$3.git" && echo "https://github.com/$3";;
      "pr create")
        repo=; base=
        while [ $# -gt 0 ]; do
          case "$1" in --repo) repo=$2; shift;; --base) base=$2; shift;; esac
          shift
        done
        if ! git --git-dir="$FAKE_GH_ROOT/$repo.git" rev-parse -q --verify \\
            "refs/heads/$base" > /dev/null; then
          echo "pull request create failed: GraphQL: Base ref must be a branch" >&2
          exit 1
        fi
        printf '%s %s\\n' "$repo" "$base" > "$FAKE_GH_ROOT/opened"
        echo "https://github.com/$repo/pull/1";;
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


#: What a run needs to find on PATH besides the shim: `git`, the `git
#: filter-repo` it dispatches to, the interpreter that script names, and what
#: git's own shell helpers call.
NEEDED_ON_PATH = ("git", "git-filter-repo", "python3", "python", "sh", "env",
                  "sed", "tr", "uname", "cat")


def without_a_real_gh(path: str, needed=NEEDED_ON_PATH) -> str:
    """`path` with every directory that holds a `gh` taken out, so that a run
    whose shim cannot be executed has no operator's `gh` to fall through to.

    Taken out only when nothing is lost: each program in `needed` must be found
    at the same place without those directories as with them. `/usr/bin` on
    Linux holds `gh` beside `git` and `sed`, and Homebrew's `bin` holds a `gh`
    beside the `git` a run is meant to use, so on those `path` comes back
    whole, and what keeps the real `gh` from acting is the unauthenticated
    token and the empty config directory the environment also carries."""
    kept = os.pathsep.join(
        directory for directory in path.split(os.pathsep)
        if not any(os.path.isfile(os.path.join(directory, name))
                   for name in ("gh", "gh.exe")))
    if all(shutil.which(program, path=kept) == shutil.which(program, path=path)
           for program in needed):
        return kept
    return path


def step_7() -> str:
    """Step 7 of AGENTS.md, from its heading to the blank line after it, as
    one line of single-spaced text."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    return " ".join(agents.split(STEP_7, 1)[1].split("\n\n", 1)[0].split())


def github_run(tmp_path: Path, refuses: str, tree: dict = SOURCE_TREE,
               failing: bool = False, merge_stderr: bool = False,
               stdout_closed: bool = False, branch: str = "main",
               plan_flags: tuple = (), before_plan=None):
    """Plan a small source and `execute` it in GitHub mode, with a `gh` that
    refuses `refuses`. Returns `(result, github)`: the run, and the directory
    that stands for github.com, with `testorg/<name>.git` in it.

    `failing` gives git the hook that takes a file the shape's pin names
    out of the split commit, which fails the verification. `merge_stderr`
    runs with both streams in one pipe, as a person redirecting a log has
    them: stdout is then block-buffered, and the order the lines arrive in
    is the order the tool flushed them. `stdout_closed` gives the run a
    stdout whose reading end is already closed, as `| head` leaves it once
    `head` has quit, so that `result.stdout` is None. `branch` is the source's own (default) branch,
    and `plan_flags` go to `plan` after the ones `write_plan` passes.
    `before_plan`, when given, is called with the source and the directory
    that stands for github.com once the assembly is there, before `plan`."""
    github = tmp_path / "github"
    (github / ORG).mkdir(parents=True)
    source = make_source_repo(tmp_path / NORTHWIND, tree=tree, edits=(),
                              branch=branch)
    # The assembly root is the repository the source was cloned from: the
    # split branch is pushed back to it.
    git("clone", "-q", "--bare", ".", str(github / ORG / f"{NORTHWIND}.git"),
        cwd=source)
    if before_plan is not None:
        before_plan(source, github)

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_text(GH_SHIM, encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    config = tmp_path / "gitconfig"
    hooks = (a_hook_that_unstages(tmp_path / "commit-hooks") if failing
             else None)
    config.write_text(f'[url "{github.as_posix()}/"]\n'
                      "\tinsteadOf = https://github.com/\n"
                      + (f"[core]\n\thooksPath = {hooks.as_posix()}\n"
                         if hooks else ""), encoding="utf-8")
    # The operator's `gh` must not be reachable from here: no token it would
    # accept, no config to read a login from, and (where it can be done
    # without losing `git`) no directory that holds one on PATH.
    gh_config = tmp_path / "gh-config"
    gh_config.mkdir()

    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, extra=plan_flags)
    assert written.returncode == 0, written.stderr + written.stdout
    stdout = subprocess.PIPE
    if stdout_closed:
        read_end, stdout = os.pipe()
        os.close(read_end)
    try:
        result = subprocess.run(
            [sys.executable, str(ADOPT), "execute", "--plan", str(plan),
             "--yes", "--work-dir", str(tmp_path / "work")],
            stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=subprocess.STDOUT if merge_stderr else subprocess.PIPE,
            text=True, check=False,
            env={**os.environ, "LANES_LANE": "",
                 "GIT_AUTHOR_NAME": "openRepoShape tests",
                 "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
                 "GIT_COMMITTER_NAME": "openRepoShape tests",
                 "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid",
                 "PATH": os.pathsep.join(
                     [str(bin_dir), without_a_real_gh(os.environ["PATH"])]),
                 "GH_TOKEN": "bogus-token-for-tests",
                 "GH_CONFIG_DIR": str(gh_config),
                 "GIT_CONFIG_GLOBAL": str(config),
                 "GIT_ALLOW_PROTOCOL": "file",
                 "FAKE_GH_ROOT": str(github), "FAKE_GH_REFUSES": refuses})
    finally:
        if stdout_closed:
            os.close(stdout)
    return result, github


def refused_arguments(github: Path) -> list[str]:
    """The arguments the shim was run with when it refused: the command
    `adopt-project.py` tried, after `gh`."""
    recorded = (github / "refused-arguments").read_bytes().decode("utf-8")
    return recorded.split("\0")[:-1]


def printed_command(text: str) -> list[str]:
    """The command printed after `Open the pull request by hand:`, as the
    arguments a shell would give it. Everything after that line is the command,
    for it is the last thing the run says. It is parsed and never run."""
    return shlex.split(text.split(BY_HAND, 1)[1])


def heads(repository: Path) -> list[str]:
    """The branches `repository` (a bare one) holds."""
    listed = git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                 cwd=repository).stdout
    return sorted(listed.split())


def assert_pushed(github: Path, branch: str = "main") -> None:
    """Both legs and the split branch ARE pushed, which is why a re-run is
    not the way out: it would push a second pair beside these. Each leg is
    pushed to the tracking branch, `branch`."""
    for leg in ("spec", "code"):
        assert heads(github / ORG / f"{NORTHWIND}-{leg}.git") == [branch]
    assert SPLIT_BRANCH in heads(github / ORG / f"{NORTHWIND}.git")


def gh_calls(github: Path) -> list[str]:
    """The `gh` commands a run made, in order, each by its first three
    arguments (`repo edit testorg/Northwind`, `pr create --repo`)."""
    calls = github / "calls"
    if not calls.exists():
        return []
    return [line.strip() for line in
            calls.read_text(encoding="utf-8").splitlines()]


def topic_and_pull_request(github: Path) -> list[str]:
    """The `gh repo edit` and `gh pr create` calls a run made, in order."""
    return [call for call in gh_calls(github)
            if call.startswith(("repo edit", "pr create"))]


#: The three topic calls `execute` makes, one per repository, in its order.
TOPIC_CALLS = [f"repo edit {ORG}/{name}" for name in
               (NORTHWIND, f"{NORTHWIND}-spec", f"{NORTHWIND}-code")]


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
    assert "pushed and verified" in said, said
    assert "finish with the command it prints" in said, said
    assert "never re-run into fresh legs" in said, said
    # A refused `gh pr create` used to return before the verification, and
    # the point said it printed no table. It prints one now.
    assert "no table" not in said, said
    # The order is the reading order: the failed verification first, and the
    # exit-2 case read AS the exception to it, not under it.
    assert said.index("Exit 1") < said.index("Exit 2 saying"), said


def test_step_7_says_what_a_failed_verification_leaves_on_github():
    """Exit 1 said "the source is untouched". Against GitHub `execute` sets
    the topic and opens the pull request BEFORE it verifies, so a failed
    verification leaves the pull request open on the source and the topic
    set, unless `gh` refused them, and deleting the split branch, as the way
    out says, closes that pull request (#523, auA-12)."""
    said = step_7()
    assert "untouched" not in said, said
    assert ("Exit 1, a failed verification: nothing is deleted and `main` is "
            "where it was, but the split branch is pushed and, on GitHub, its "
            "pull request may be open and the topic set") in said, said
    assert "delete the split branch (closing that pull request)" in said, said


def test_the_modules_exit_codes_paragraph_names_the_exits_after_the_push(
        adopter):
    """The EXIT CODES paragraph gave exit 2 one meaning, "the question could
    not be asked". It says what comes after the push, in the tool's own
    words, so the file and the messages it describes cannot part."""
    codes = " ".join(adopter.__doc__.split("EXIT CODES:", 1)[1].split())
    # Not every exit 2 is the question that could not be asked, and not every
    # other one is GitHub's: two of them are.
    assert "other exit 2s, once the leg repositories exist" in codes, codes
    assert "Two of them are GitHub mode's alone" in codes, codes
    assert "two more exit 2s" not in codes, codes
    assert "AFTER both legs and the split branch are pushed" in codes, codes
    assert "the verification has passed" in codes, codes
    assert "`gh pr create` refused (`The branch IS pushed`" in codes, codes
    assert ("the topic would not set (`The split IS pushed and the pull "
            "request IS open`") in codes, codes
    assert "a re-run into fresh legs abandons the pushed pair" in codes, codes
    assert ("A verification that fails outranks both, with exit 1 and no "
            "command to open the pull request") in codes, codes


# --- the two exits, run -----------------------------------------------------

@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
@pytest.mark.parametrize("refuses, refused, by_hand, opened", [
    pytest.param("pr create", "REFUSED opening the pull request.",
                 BRANCH_IS_PUSHED, False, id="gh-pr-create-refused"),
    pytest.param("repo edit", "REFUSED setting the project topic.",
                 SPLIT_IS_PUSHED, True, id="the-topic-will-not-set"),
])
def test_each_exit_after_the_push_is_exit_2_with_a_command_to_finish_by_hand(
        tmp_path, refuses, refused, by_hand, opened):
    result, github = github_run(tmp_path, refuses)

    # The exit, and what it prints: the REFUSED block, then the command.
    assert result.returncode == 2, result.stdout + result.stderr
    assert refused in result.stderr, result.stderr
    assert by_hand in result.stderr, result.stderr
    assert_pushed(github)

    # BOTH have a table: the split is verified before the person is told to
    # finish by hand, and the pull request line is there only when there is
    # one. (A refused `gh pr create` returned before `_verify` until #304.)
    assert "VERIFICATION" in result.stdout, result.stdout
    assert VERIFIED in result.stdout, result.stdout
    assert (f"  pull request https://github.com/{ORG}/{NORTHWIND}/pull/1"
            in result.stdout) is opened, result.stdout
    assert "  split " in result.stdout, result.stdout
    assert NOT_BY_HAND not in result.stderr, result.stderr
    # The topic is tried BEFORE the pull request (#481), so a refused pull
    # request no longer leaves it unset: the stub lets it through, and it is
    # set on all three. It used not to be tried after a refused pull request
    # at all, and the way out never said so. The way out names what is left
    # and nothing else: the pull request's command, or the topic's.
    topic_set = refuses != "repo edit"
    assert ("set on all three" in result.stdout) is topic_set, result.stdout
    assert ("Set the topic by hand" in result.stderr) is not topic_set, \
        result.stderr
    # `NEXT: review the pull request` is said where there is one to review,
    # and not after a refused `gh pr create`, where the command to open it is
    # the next step.
    assert (NEXT in result.stdout) is opened, result.stdout

    # What step 7 says of it is what the tool printed: the marker words and
    # the command it names.
    said = step_7()
    assert "IS pushed" in said and "IS pushed" in by_hand
    assert "gh pr create" in said and "gh pr create" in BRANCH_IS_PUSHED
    assert "the topic" in said and "--add-topic" in SPLIT_IS_PUSHED


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_the_command_to_open_a_refused_pull_request_comes_after_the_table(
        tmp_path):
    """The by-hand command depends on the table, so it is the LAST thing the
    run says. With both streams in one pipe, stdout holds the table in a
    block buffer until the tool flushes it; a command printed to stderr
    without that flush came first, ahead of the table it depends on."""
    result, github = github_run(tmp_path, "pr create", merge_stderr=True)

    assert result.returncode == 2, result.stdout
    table = result.stdout.index("VERIFICATION")
    verified = result.stdout.index(VERIFIED)
    by_hand = result.stdout.index(BRANCH_IS_PUSHED)
    assert table < verified < by_hand, result.stdout
    assert result.stdout.count(BY_HAND) == 1
    # Nothing follows the command: the whole of what comes after it parses as
    # the command, whose last argument is the body.
    printed = printed_command(result.stdout)
    assert printed[:3] == ["gh", "pr", "create"], printed
    assert printed[-2] == "--body", printed
    assert NEXT not in result.stdout, result.stdout
    assert_pushed(github)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_the_command_printed_for_a_refused_pull_request_is_the_one_refused(
        tmp_path):
    """The printed command has its title and body. `gh pr create` without
    them asks for them, and where there is no terminal it refuses instead
    (`must provide --title and --body ... when not running interactively`), so
    an assistant told to finish with the command it prints could not. It is the
    command `adopt-project.py` ran, argument for argument: what the shim was
    run with is read back, and the printed command is parsed and compared with
    it. Nothing here runs the printed command."""
    result, github = github_run(tmp_path, "pr create")

    assert result.returncode == 2, result.stdout + result.stderr
    refused = refused_arguments(github)
    printed = printed_command(result.stderr)
    assert refused[:2] == ["pr", "create"], refused
    assert "--title" in refused and "--body" in refused, refused
    assert printed == ["gh", *refused], (printed, refused)
    # The title names the two legs, and is the first line of the body: the
    # split's commit message, which says what moved where.
    title = refused[refused.index("--title") + 1]
    body = refused[refused.index("--body") + 1]
    assert title == ("Adopt the three-repository shape: "
                     f"{NORTHWIND}-spec and {NORTHWIND}-code"), title
    assert body.split("\n", 1)[0] == title, body
    assert "MOVED TO THE CODE LEG" in body and "\n" in body, body
    # The body lists the FOLLOW-UPS the split does not do, and the last is a
    # review of the pull request this run opens itself, never one telling
    # the reviewer to open it, or calling the extracted legs seeded (#523).
    follow_ups = body.split("FOLLOW-UPS, which this commit does NOT do:\n",
                            1)[1]
    assert follow_ups.endswith(f"  - {PULL_REQUEST_FOLLOW_UP}\n"), follow_ups
    assert OPEN_THE_SPLIT not in body, body
    assert "seeded" not in follow_ups, follow_ups


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_closed_stdout_does_not_lose_the_command_to_open_the_pull_request(
        tmp_path):
    """`execute ... | head`, once `head` has quit, leaves a stdout nobody reads.
    The command is on stderr, so it is still printed: flushing stdout first,
    which the order test needs, raised BrokenPipeError there and ended the run
    in a traceback with no command, where it was printed before #304 and
    the exit was Python's own 120 for a stdout it cannot flush at exit."""
    result, github = github_run(tmp_path, "pr create", stdout_closed=True)

    assert "Traceback" not in result.stderr, result.stderr
    assert BRANCH_IS_PUSHED in result.stderr, result.stderr
    # 2 is the tool's own exit; 120 is what Python makes of it when it cannot
    # flush the closed stdout as it exits, and what this run gave before.
    assert result.returncode in (2, 120), result.stderr
    assert_pushed(github)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_failed_verification_outranks_a_refused_pull_request(tmp_path):
    """The split fails the verification, and `gh pr create` and the topic are
    refused too: exit 1, the finding and its footer, and NO command to open
    the pull request or to set the topic. The refusal above names the exact
    command that was tried, so the run says that none is to be opened; it
    used to print the by-hand command and exit 2 without ever having verified
    the split. The topic's way out is the verification's too: the re-run it
    names sets the topic (#481)."""
    result, github = github_run(tmp_path, "pr create|repo edit",
                                failing=True)

    assert result.returncode == 1, result.stdout + result.stderr
    assert FINDING in result.stderr, result.stderr
    assert "1 verification finding(s)." in result.stderr, result.stderr
    # What gh refused is still said, and so is what that leaves.
    assert "REFUSED opening the pull request." in result.stderr, result.stderr
    assert NOT_BY_HAND in result.stderr, result.stderr
    # Nothing tells the person to open one, to set the topic by hand, or that
    # the adoption is done.
    assert "Open the pull request by hand" not in result.stderr + result.stdout
    assert "Set the topic by hand" not in result.stderr + result.stdout
    assert "IS pushed" not in result.stderr + result.stdout
    assert NEXT not in result.stdout, result.stdout
    assert VERIFIED not in result.stdout, result.stdout
    assert "VERIFICATION" in result.stdout, result.stdout
    # The legs and the branch exist, as the footer says, and no re-run into
    # fresh legs is pretended to be the same as a command by hand.
    assert_pushed(github)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
@pytest.mark.parametrize("refuses, said", [
    pytest.param("never", (STILL_OPEN, TOPIC_STAYS), id="both-in-place"),
    pytest.param("pr create", (NOT_BY_HAND, TOPIC_STAYS), id="topic-only"),
    pytest.param("repo edit", (STILL_OPEN,), id="pull-request-only"),
])
def test_a_failed_verification_says_what_it_left_in_place(tmp_path, refuses,
                                                          said):
    """The split fails the verification after `execute` has set the topic
    and opened the pull request, whichever of the two `gh` took. The way out
    said NOTHING was deleted from the source, which is true, and nothing of
    the pull request open for the failed split, or of the topic (#523,
    auA-12). The last thing the run says now names each one it left, after
    the command that deletes the split branch, which closes the pull
    request; and still no command to open one or to set the topic, and no
    NEXT. Both refused is
    `test_a_failed_verification_outranks_a_refused_pull_request`."""
    result, github = github_run(tmp_path, refuses, failing=True)

    assert result.returncode == 1, result.stdout + result.stderr
    assert FINDING in result.stderr, result.stderr
    assert result.stderr.rstrip("\n").rsplit("\n", 1)[1] == " ".join(said), \
        result.stderr
    assert result.stderr.index(f"--delete {SPLIT_BRANCH}") \
        < result.stderr.index(said[0]), result.stderr
    assert (github / "opened").exists() is (STILL_OPEN in said)
    for unsaid in ("Open the pull request by hand", "Set the topic by hand",
                   "IS pushed", NEXT, VERIFIED):
        assert unsaid not in result.stderr + result.stdout, unsaid
    assert_pushed(github)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_the_same_source_verifies_when_gh_opens_the_pull_request(tmp_path):
    """The control for the test above: it is the split the hook leaves that
    fails the verification, not the refused pull request. Without the hook,
    the same source verifies and the run is exit 0."""
    result, github = github_run(tmp_path, "never")

    assert result.returncode == 0, result.stdout + result.stderr
    assert VERIFIED in result.stdout, result.stdout
    assert NEXT in result.stdout, result.stdout
    assert "Open the pull request by hand" not in result.stderr
    assert_pushed(github)


# --- the topic comes first, and what is left is said once (#481) ------------

@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_refused_pull_request_no_longer_leaves_the_topic_unset(tmp_path):
    """The issue's own run: `gh pr create` refused. The stub's log showed two
    `repo create` calls, one `pr create` and no `repo edit`, so none of the
    three repositories carried the topic `project.yaml` claims, and the way
    out named only the pull request. The topic is now set on each of the
    three BEFORE the pull request is tried, and the way out names the one
    thing left."""
    result, github = github_run(tmp_path, "pr create")

    assert result.returncode == 2, result.stdout + result.stderr
    assert topic_and_pull_request(github) == [*TOPIC_CALLS, "pr create --repo"]
    assert f"  topic     {TOPIC} set on all three" in result.stdout
    assert BRANCH_IS_PUSHED in result.stderr, result.stderr
    assert "Set the topic by hand" not in result.stderr, result.stderr


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_refused_pull_request_and_topic_are_one_notice_after_the_table(
        tmp_path):
    """Both refused: each refusal is printed as it happens, and what is left
    is ONE notice after the table, `IS pushed` as step 7 reads it, naming
    the `gh repo edit` for each repository and then the command that opens
    the pull request, which is still the last thing the run says."""
    result, github = github_run(tmp_path, "pr create|repo edit",
                                merge_stderr=True)
    said = result.stdout

    assert result.returncode == 2, said
    notice = ("The branch IS pushed. Set the topic by hand:\n"
              + "".join(f"    gh {call} --add-topic {TOPIC}\n"
                        for call in TOPIC_CALLS)
              + "Open the pull request by hand:\n"
              f"    gh pr create --repo {ORG}/{NORTHWIND} --base main "
              f"--head {SPLIT_BRANCH}")
    assert said.index("VERIFICATION") < said.index(VERIFIED) \
        < said.index(notice), said
    assert said.count("REFUSED setting the project topic.") == 3, said
    assert said.count("REFUSED opening the pull request.") == 1, said
    assert said.count(BY_HAND) == 1 and said.count("IS pushed") == 1, said
    printed = printed_command(said)
    assert printed[:3] == ["gh", "pr", "create"] and printed[-2] == "--body"
    assert "  topic " not in said and NEXT not in said, said
    assert topic_and_pull_request(github) == [*TOPIC_CALLS, "pr create --repo"]
    assert_pushed(github)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_topic_refused_on_one_repository_names_that_one_alone(tmp_path):
    """Each repository is asked, whatever the one before it answered, and the
    way out names the command for the one left without the topic and for no
    repository that has it. The first refusal used to end the topic step and
    name all three."""
    result, github = github_run(tmp_path, f"repo edit {ORG}/{NORTHWIND}-spec")

    assert result.returncode == 2, result.stdout + result.stderr
    assert topic_and_pull_request(github) == [*TOPIC_CALLS, "pr create --repo"]
    assert (f"  topic     {TOPIC} set on {ORG}/{NORTHWIND} and "
            f"{ORG}/{NORTHWIND}-code only") in result.stdout, result.stdout
    assert result.stderr.count("REFUSED setting the project topic.") == 1
    by_hand = result.stderr.split("Set the topic by hand:\n", 1)[1]
    assert by_hand == (f"    gh repo edit {ORG}/{NORTHWIND}-spec "
                       f"--add-topic {TOPIC}\n"), result.stderr
    assert ("The split IS pushed and the pull request IS open. "
            "Set the topic by hand:") in result.stderr
    assert NEXT in result.stdout and VERIFIED in result.stdout


# --- the pull request's base is a branch the source has (#479) --------------

TRACKING_MISSING = "plan-tracking-branch-missing"
#: The assembly's url, as `execute` names it.
ASSEMBLY_URL = f"`https://github.com/{ORG}/{NORTHWIND}.git`"


def assert_refused_before_any_repository(result, github: Path,
                                         code: str) -> None:
    """`execute` refused as `code`, saying it had made nothing, and it had
    not: no `gh` was run and no leg repository is on the fake GitHub."""
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {code}: " in result.stderr, result.stderr
    assert "no leg repository was created" in result.stderr, result.stderr
    assert gh_calls(github) == []
    assert not (github / ORG / f"{NORTHWIND}-spec.git").exists()


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
@pytest.mark.parametrize("branch", ["master", "trunk"])
def test_a_source_on_another_branch_opens_its_pull_request_against_it(
        tmp_path, branch):
    """A `master` or `trunk` source: `plan` records that branch as the
    tracking branch, both legs are pushed to it, the root's `project.yaml`
    tracks it, and the pull request opens against it. With `main` as the
    tracking branch whatever the source used, all of it was pushed and then
    GitHub refused the pull request (`Base ref must be a branch`), and the
    printed way out was the same command."""
    result, github = github_run(tmp_path, "never", branch=branch)

    assert result.returncode == 0, result.stdout + result.stderr
    assert VERIFIED in result.stdout and NEXT in result.stdout
    assert (github / "opened").read_text(encoding="utf-8") == \
        f"{ORG}/{NORTHWIND} {branch}\n"
    assert_pushed(github, branch)
    root = git("show", f"{SPLIT_BRANCH}:project.yaml",
               cwd=github / ORG / f"{NORTHWIND}.git").stdout
    assert f'\ntracking_branch: "{branch}"\n' in root, root
    assert "Base ref must be a branch" not in result.stderr


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_base_the_source_lacks_is_refused_before_any_repository(tmp_path):
    """`--tracking-branch main` on a `master` source still wins in the plan,
    and `execute` refuses it before it makes anything, as `check` finds it:
    no `gh` is run at all, where both legs and the split used to be pushed
    before GitHub refused the pull request."""
    result, github = github_run(tmp_path, "never", branch="master",
                                plan_flags=("--tracking-branch", "main"))

    assert_refused_before_any_repository(result, github, TRACKING_MISSING)
    assert ("`tracking_branch` is `main`, which is no branch of the source "
            "(its branches: `master`; the source's default branch is "
            "`master`)") in result.stderr, result.stderr


# --- the remote is asked, before any repository (#493's review, F1) ---------

def renamed_on_github(source: Path, github: Path) -> None:
    """The source becomes a clone made while its repository's default branch
    was `master`, and GitHub then renames `master` to `main`. An ordinary
    `git fetch` does not prune, so the clone keeps `origin/master`, and
    `origin/HEAD` still names it, beside the `origin/main` the fetch brings."""
    assembly = github / ORG / f"{NORTHWIND}.git"
    git("remote", "add", "origin", str(assembly), cwd=source)
    git("fetch", "-q", "origin", cwd=source)
    git("remote", "set-head", "origin", "master", cwd=source)
    git("branch", "-m", "master", "main", cwd=assembly)
    git("symbolic-ref", "HEAD", "refs/heads/main", cwd=assembly)
    git("fetch", "-q", "origin", cwd=source)


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_branch_the_clone_remembers_and_github_renamed_is_refused_first(
        tmp_path):
    """`check` reads the branches the source's clone remembers, and passes
    `master`, which `plan` took from `origin/HEAD`. `execute` asks the
    remote itself before it makes anything, and refuses: it used to push
    both legs and the split, and then GitHub refused the pull request,
    `Base ref must be a branch`, where before #479 the same clone planned
    `main` and adopted. The way out it names, the clone pruned and told its
    remote's default branch, and its own branch renamed to match, makes a
    plan that tracks `main` and checks ok."""
    result, github = github_run(tmp_path, "never", branch="master",
                                before_plan=renamed_on_github)

    assert_refused_before_any_repository(result, github, TRACKING_MISSING)
    assert (f"`tracking_branch` is `master`, which {ASSEMBLY_URL}, the "
            "repository the split is pushed to, does not have as `git "
            "ls-remote` reads it now") in result.stderr, result.stderr
    said = " ".join(result.stderr.split())
    assert ("run `git fetch --prune origin` and `git remote set-head origin "
            "--auto`, and where the default branch was renamed, rename the "
            "clone's own to match, as GitHub's notice of the rename says (`git "
            "branch -m <old> <new>`). Then re-run `plan`") in said, said

    source = tmp_path / NORTHWIND
    git("fetch", "-q", "--prune", "origin", cwd=source)
    git("remote", "set-head", "origin", "--auto", cwd=source)
    git("branch", "-m", "master", "main", cwd=source)
    replanned = tmp_path / "replanned.yaml"
    written = write_plan(source, replanned)
    assert written.returncode == 0, written.stdout + written.stderr
    assert "\ntracking_branch: main\n" in replanned.read_text(encoding="utf-8")
    checked = run_script(ADOPT, "check", "--plan", str(replanned))
    assert checked.returncode == 0, checked.stdout + checked.stderr


def moved_off_github(source: Path, github: Path) -> None:
    """The assembly is no longer at the url `execute` pushes the split to."""
    assembly = github / ORG / f"{NORTHWIND}.git"
    assembly.rename(assembly.with_name("Elsewhere.git"))


@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_remote_that_cannot_be_asked_is_refused_before_any_repository(
        tmp_path):
    """The question fails closed: a remote `git ls-remote` cannot read is
    refused as such, before any leg exists, since the split push needs the
    same remote."""
    result, github = github_run(tmp_path, "never",
                                before_plan=moved_off_github)

    assert_refused_before_any_repository(result, github,
                                         "adopt-remote-unreadable")
    assert (f"`git ls-remote` could not read {ASSEMBLY_URL}, the repository "
            "the split is pushed to, to ask whether it has `main`, the "
            "plan's `tracking_branch`: exit ") in result.stderr, result.stderr


# --- the real `gh` stays out of reach ---------------------------------------

@WINDOWS_SKIP  # the `gh` is a `#!` script, which Windows does not run
@needs_filter_repo
def test_a_run_gives_gh_no_token_it_would_accept_and_no_config(tmp_path):
    """Whatever `gh` the run reaches is run with what the shim was run with: a
    token no organisation knows, and a config directory with nothing in it, so
    that the operator's login is not there to be used if the shim ever cannot
    be executed and the next `gh` on PATH answers instead."""
    result, github = github_run(tmp_path, "pr create")

    assert result.returncode == 2, result.stdout + result.stderr
    token, config, _ = (github / "environment").read_text(
        encoding="utf-8").split("\n")
    assert token == "bogus-token-for-tests", token
    assert Path(config) == tmp_path / "gh-config", config
    assert list(Path(config).iterdir()) == [], config


def program(directory: Path, *names: str) -> None:
    """Executable files called `names` in `directory`."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        (directory / name).chmod(0o755)


@WINDOWS_SKIP  # `shutil.which` reads PATHEXT there, and nothing here runs
def test_the_directory_that_holds_a_real_gh_is_taken_off_path_only_when_free(
        tmp_path):
    """A directory with a `gh` and nothing the run needs goes; one that holds
    `gh` beside `git`, or whose going changes which `git` is found, stays,
    because losing `git` fails the run and swapping it changes what is
    tested. Then the token and the config directory are what is left."""
    system, extra, only_gh = (tmp_path / "system", tmp_path / "extra",
                              tmp_path / "only-gh")
    program(system, "git", "sed")
    program(only_gh, "gh")
    path = os.pathsep.join(map(str, (only_gh, system)))
    needed = ("git", "sed")
    assert without_a_real_gh(path, needed) == str(system)

    # `gh` beside `git`: removing the directory would lose `git`.
    program(extra, "gh", "git", "sed")
    shared = os.pathsep.join(map(str, (extra, system)))
    assert without_a_real_gh(shared, needed) == shared
    # `gh` beside the `git` that comes first: the other `git` would be used.
    program(extra, "gh", "git")
    program(system, "git")
    assert without_a_real_gh(shared, ("git",)) == shared
    # No `gh` anywhere, and nothing to take out.
    assert without_a_real_gh(str(system), needed) == str(system)
