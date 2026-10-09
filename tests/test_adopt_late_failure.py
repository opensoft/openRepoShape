# SPDX-License-Identifier: Apache-2.0
"""`execute` says what failed after both legs exist, and what it left (#188).

#171 made `_build_the_legs` report a leg that cannot be built: stdout flushed
first, the exact command and its output, then a notice naming the two leg
repositories and why a re-run is refused. Everything after the legs still had
main's behaviour. On main at f25d805 a split push refused by a pre-receive
hook printed only `REFUSED pushing the split branch`, a split commit refused
by a pre-commit hook printed `main`'s generic `REFUSED a git or gh command
failed`, a merged `> log 2>&1` showed REFUSED on line 0 and the `bare …` lines
after it, and the re-run met `leg-remote-exists` with nothing having said why.

A refused LEG push printed `RULESET_HINT`, the scaffold's, whose second exit
is `git -C <work> push -u origin main:seed/scaffold` (#177). `git filter-repo`
removes `origin` from the clone it rewrites, and a seeded leg is a fresh
`git init` that never had one, so that command exits 128 with `'origin' does
not appear to be a git repository`. Two tests here RUN the command the
adoption prints, against a remote whose hook refuses only `main`, as a
pull-request ruleset does.

The tests that need `git filter-repo` run `adopt-project.py execute` with a
merged stream; the rest call the functions in this process and need no
filter. NO NETWORK AND NO GITHUB: every remote is a bare repository on disk,
or no repository at all.
"""

from __future__ import annotations

import importlib.util
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, run_script, write_plan

SPEC, CODE = "spec", "code"
LEGS = (SPEC, CODE)
ASSEMBLY = "Northwind"
BRANCH = "adopt/three-repo-shape"
REMOTES = "remotes"
WORK = "work"
REFUSED = "REFUSED"
ROLLED_BACK = "NOTHING has been rolled back"
BOTH_PUSHED = "both legs are pushed"
EARLIER_RUN = "If an earlier run left"
SEED_BRANCH = "refs/heads/seed/adopt"
MAIN_REF = "refs/heads/main"
SPLIT_PUSH = "pushing the split branch"
ORG = "testorg"
SPEC_REPOSITORY = f"{ORG}/{ASSEMBLY}-{SPEC}"
END_OUTPUT = "--- end output ---"

#: A source small enough that `plan` asks no question, so `execute` runs on
#: the plan as written.
SMALL_TREE = {"README.md": "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_late_failure", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class ClosedPipe(io.StringIO):
    """A stdout whose reader has gone away, as under `… | true`."""

    def flush(self) -> None:
        raise BrokenPipeError(32, "Broken pipe")


def write_refusing_hook(hooks: Path, ref_pattern: str) -> None:
    """A `pre-receive` hook that refuses any ref matching `ref_pattern`, the
    way an organisation ruleset refuses a direct push to the default branch.
    LF, because `sh` reads it on every platform."""
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-receive"
    with hook.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("#!/bin/sh\n"
                     "while read old new ref; do\n"
                     f'  case "$ref" in {ref_pattern})\n'
                     '    echo "ruleset: changes must arrive by pull request" '
                     ">&2; exit 1;;\n"
                     "  esac\n"
                     "done\n"
                     "exit 0\n")
    hook.chmod(0o755)


def hooks_everywhere(tmp_path: Path, ref_pattern: str) -> dict:
    """An environment whose git runs the refusing hook in EVERY repository a
    push reaches, through a global `core.hooksPath`, so the subprocess under
    test meets it at the leg remotes and at the source alike."""
    hooks = tmp_path / "hooks"
    write_refusing_hook(hooks, ref_pattern)
    config = tmp_path / "gitconfig"
    config.write_text(f"[core]\n\thooksPath = {hooks.as_posix()}\n",
                      encoding="utf-8")
    return {"GIT_CONFIG_GLOBAL": str(config)}


def seed_one_file(_template, work, _values) -> list[str]:
    """`copy_tree` for a seeded leg, without the template's placeholders. It
    returns what it wrote, as `copy_tree` does, because `_seed_leg` hands
    that list to `git_init_commit` to force past an ignore rule (#175)."""
    work.mkdir(parents=True, exist_ok=True)
    (work / "README.md").write_text("seeded\n", encoding="utf-8")
    return ["README.md"]


def printed_push(err: str) -> list[str]:
    """The `git -C <work> push …` line of the ruleset hint, as argv."""
    lines = [line.split() for line in err.splitlines()
             if line.strip().startswith("git -C ")]
    assert len(lines) == 1, err
    return lines[0]


def commit_of(repo: Path, ref: str = "HEAD") -> str | None:
    """The commit `ref` names in `repo`, or None when it names none."""
    found = git("rev-parse", "-q", "--verify", f"{ref}^{{commit}}", cwd=repo,
                check=False)
    return found.stdout.strip() if found.returncode == 0 else None


def source_of(adopter, tmp_path: Path):
    origin = make_source_repo(tmp_path / "Thing", tree=SMALL_TREE, edits=())
    return adopter.Source(origin, None, "main", commit_of(origin))


def leg_names() -> dict:
    names = {role: f"{ASSEMBLY}-{role}" for role in LEGS}
    names["assembly"] = ASSEMBLY
    return names


def leg_urls(tmp_path: Path, names: dict) -> dict:
    """One bare repository per leg, so a notice that names both is seen to."""
    return {role: str(tmp_path / REMOTES / f"{names[role]}.git")
            for role in LEGS}


def split_arguments(tmp_path: Path, source) -> dict:
    """What `cmd_execute` hands `_commit_the_split` once both legs are
    pushed. The leg commits are stand-ins: every step that would read them
    is either stubbed or fails before it does."""
    names = leg_names()
    urls = leg_urls(tmp_path, names)
    urls["assembly"] = str(source.path)
    return dict(
        plan={}, source=source, assembly=tmp_path / WORK / ASSEMBLY,
        names=names, urls=urls, values={}, work_root=tmp_path / WORK,
        paths_for={SPEC: ["specs/"], CODE: ["src/"], "root": ["README.md"],
                   "drop": []},
        seeded=[], spec_path=SPEC, code_path=CODE, branch=BRANCH,
        leg_commits={SPEC: "a" * 40, CODE: "b" * 40})


# ---- one way for each step of the split to fail -----------------------------

def clone_fails(_adopter, _monkeypatch, arguments) -> None:
    """A work directory reused from an earlier run already holds the
    assembly clone, so `git clone` refuses it. Real git, no stub."""
    arguments["assembly"].mkdir(parents=True)
    (arguments["assembly"] / "left-over.txt").write_text("x\n",
                                                         encoding="utf-8")


def mount_fails(adopter, monkeypatch, arguments) -> None:
    def refused(*_args):
        raise adopter.CommandFailed(
            ["git", "submodule", "add", "-q",
             str(arguments["work_root"] / f"{ASSEMBLY}-{SPEC}"), SPEC],
            arguments["assembly"], 128, "fatal: 'spec' already exists in "
                                        "the index")
    monkeypatch.setattr(adopter, "_mount_the_legs", refused)


def commit_fails(adopter, monkeypatch, _arguments) -> None:
    """Nothing is mounted, written or staged, so the real `git commit` finds
    nothing to commit and exits 1."""
    monkeypatch.setattr(adopter, "_mount_the_legs", lambda *_args: None)
    monkeypatch.setattr(adopter, "materialize_assembly_root",
                        lambda *_args, **_kw: adopter.Materialized())
    monkeypatch.setattr(adopter, "_stage_the_split", lambda *_args: None)


def commit_for_real(adopter, monkeypatch) -> None:
    """Mount nothing and write one file, so the split commit is made for
    real and only its push is left to fail."""
    def write_one_file(_shape_root, target, *_args, **_kw):
        (target / "project.yaml").write_text("schema_version: 1\n",
                                             encoding="utf-8")
        materialized = adopter.Materialized()
        materialized.written.append("project.yaml")
        return materialized

    monkeypatch.setattr(adopter, "_mount_the_legs", lambda *_args: None)
    monkeypatch.setattr(adopter, "materialize_assembly_root", write_one_file)


def push_fails(adopter, monkeypatch, arguments) -> None:
    """The split commit is made for real; the source it is pushed back to is
    not there."""
    commit_for_real(adopter, monkeypatch)
    arguments["urls"]["assembly"] = str(arguments["work_root"].parent
                                        / "gone.git")


SPLIT_FAILURES = [(clone_fails, "cloning the source for the split"),
                  (mount_fails, "mounting the legs"),
                  (commit_fails, "committing the split"),
                  (push_fails, SPLIT_PUSH)]
SPLIT_FAILURE_IDS = ["clone", "mount", "commit", "push"]


@pytest.mark.parametrize("arrange, step", SPLIT_FAILURES,
                         ids=SPLIT_FAILURE_IDS)
def test_a_split_that_fails_names_its_step_and_both_pushed_legs(
        adopter, monkeypatch, capsys, tmp_path, arrange, step):
    """Each step of the split, failing for real or through a stub, ends with
    one REFUSED block naming the step, then the notice: both leg
    repositories, both of them pushed, and why a re-run is refused. Before
    #188 the mount and the commit fell through to `main`'s generic `a git or
    gh command failed`, and none of the four said what was left."""
    arguments = split_arguments(tmp_path, source_of(adopter, tmp_path))
    arrange(adopter, monkeypatch, arguments)

    assert adopter._commit_the_split(**arguments) is None

    err = capsys.readouterr().err
    assert err.count(REFUSED) == 1, err
    assert f"{REFUSED} {step}. THE EXACT COMMAND WAS:" in err
    notice = err.split(END_OUTPUT, 1)[1]
    assert ROLLED_BACK in notice
    for role in LEGS:
        assert arguments["urls"][role] in notice
    assert BOTH_PUSHED in notice
    assert "leg-remote-exists" in notice
    assert (EARLIER_RUN in notice) == (step == SPLIT_PUSH)


@pytest.mark.parametrize("failing, state",
                         [(SPEC, "neither leg is pushed"),
                          (CODE, f"the {SPEC} leg is pushed")],
                         ids=["first-leg", "second-leg"])
def test_the_notice_says_which_legs_are_pushed(
        adopter, monkeypatch, capsys, tmp_path, failing, state):
    """The one notice is shared by a leg that cannot be built and a split
    that cannot be made, so it says how far the run got rather than "one leg
    may already be pushed": none, the first, or (the split cases) both."""
    def build(role, *_args):
        if role == failing:
            raise adopter.CommandFailed(["git", "filter-repo", "--force"],
                                        None, 1, "Error: fast-export failed")
        return "c" * 40, "d" * 64

    monkeypatch.setattr(adopter, "_extract_leg", build)
    names = leg_names()
    urls = leg_urls(tmp_path, names)

    assert adopter._build_the_legs(
        source=None, names=names,
        repositories={role: f"{ORG}/{names[role]}" for role in LEGS},
        urls=urls, values={}, work_root=tmp_path / WORK,
        paths_for={role: [f"{role}/"] for role in LEGS}, seeded=[],
        branch=BRANCH, tracking="main") is None

    notice = capsys.readouterr().err.split(END_OUTPUT, 1)[1]
    assert f"{urls[SPEC]} and {urls[CODE]} exist, and {state}." in notice


def test_a_split_push_refused_as_not_a_fast_forward_says_why(
        adopter, monkeypatch, capsys, tmp_path):
    """A verification that failed leaves the split branch on the source, and
    the re-run AGENTS.md step 7 then prescribes, into fresh legs, makes and
    pushes two more legs and is refused at this push: the new split commit is
    not a fast-forward of the old one. Fresh legs alone would loop, so the
    report says the branch must go too."""
    source = source_of(adopter, tmp_path)
    earlier = git("-c", "user.name=Earlier Run",
                  "-c", "user.email=earlier@invalid.example",
                  "commit-tree", "-p", source.commit, "-m",
                  "an earlier run's split", f"{source.commit}^{{tree}}",
                  cwd=source.path).stdout.strip()
    git("update-ref", f"refs/heads/{BRANCH}", earlier, cwd=source.path)
    arguments = split_arguments(tmp_path, source)
    commit_for_real(adopter, monkeypatch)

    assert adopter._commit_the_split(**arguments) is None

    err = capsys.readouterr().err
    assert f"{REFUSED} {SPLIT_PUSH}." in err
    assert f"{EARLIER_RUN} {BRANCH} on {source.path}" in err


def pull_request_fails(adopter, monkeypatch, _tmp_path):
    def refused(args, *_rest, **_kw):
        raise adopter.CommandFailed(args, None, 1, "HTTP 502")
    monkeypatch.setattr(adopter, "run", refused)
    repositories = {role: f"{ORG}/{ASSEMBLY}-{role}" for role in LEGS}
    repositories["assembly"] = f"{ORG}/{ASSEMBLY}"
    names = {role: f"{ASSEMBLY}-{role}" for role in LEGS}
    assert not adopter._open_the_pull_request(repositories, names, "main",
                                              BRANCH, "body")


def topic_fails(adopter, monkeypatch, _tmp_path):
    def refused(args, *_rest, **_kw):
        raise adopter.CommandFailed(args, None, 1, "HTTP 403")
    monkeypatch.setattr(adopter, "run", refused)
    repositories = {role: f"{ORG}/{ASSEMBLY}-{role}"
                    for role in (*LEGS, "assembly")}
    assert not adopter._set_the_topic(repositories, "xf-project-northwind")


def split_mount_fails(adopter, monkeypatch, tmp_path):
    arguments = split_arguments(tmp_path, source_of(adopter, tmp_path))
    mount_fails(adopter, monkeypatch, arguments)
    assert adopter._commit_the_split(**arguments) is None


def leg_push_fails(adopter, monkeypatch, tmp_path):
    monkeypatch.setattr(adopter, "copy_tree", seed_one_file)
    with pytest.raises(adopter.CommandFailed):
        adopter._seed_leg(SPEC, tmp_path / WORK / f"{ASSEMBLY}-{SPEC}", {},
                          BRANCH, str(tmp_path / "gone.git"), "main",
                          SPEC_REPOSITORY, ASSEMBLY)


@pytest.mark.parametrize("fail", [split_mount_fails, leg_push_fails,
                                  pull_request_fails, topic_fails],
                         ids=["split", "leg-push", "pull-request", "topic"])
def test_stdout_is_flushed_before_a_late_failure_reaches_stderr(
        adopter, monkeypatch, tmp_path, fail):
    """Every failure after the leg repositories exist is written to stderr
    AFTER stdout is flushed, so a merged log keeps the order things ran in."""
    events: list = []
    monkeypatch.setattr(sys, "stdout", Stream("stdout", events))
    monkeypatch.setattr(sys, "stderr", Stream("stderr", events))

    fail(adopter, monkeypatch, tmp_path)

    assert ("stdout", "flush") in events
    assert (events.index(("stdout", "flush"))
            < events.index(("stderr", "write")))


def test_a_closed_stdout_does_not_swallow_the_report(
        adopter, monkeypatch, tmp_path):
    """The flush must not cost the human the report: with stdout on a pipe
    nobody reads, flushing raises BrokenPipeError, and the REFUSED block and
    the notice must still reach stderr."""
    err = io.StringIO()
    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    monkeypatch.setattr(sys, "stderr", err)

    split_mount_fails(adopter, monkeypatch, tmp_path)

    assert f"{REFUSED} mounting the legs." in err.getvalue()
    assert ROLLED_BACK in err.getvalue()


def a_refusal(adopter):
    return adopter.Refusal(
        "git-failed", f"`git ls-tree -r -z HEAD` in {ASSEMBLY}-{SPEC} exited "
                      "128: fatal: not a valid object name HEAD")


def a_command_failure(adopter):
    return adopter.CommandFailed(
        ["gh", "repo", "create", f"{ORG}/{ASSEMBLY}-{CODE}", "--private"],
        None, 1, "GraphQL: Name already exists on this account")


@pytest.mark.parametrize("failure", [a_refusal, a_command_failure],
                         ids=["refusal", "command"])
def test_main_flushes_stdout_before_a_failure_no_step_reported(
        adopter, monkeypatch, failure):
    """What no step reports itself, `main` prints: a `Refusal` from
    `git_out` once the legs exist, or a `gh repo create` that fails for the
    code leg after the spec leg was created and announced. Stdout is flushed
    first, so a merged log has the announcement before the report."""
    events: list = []
    monkeypatch.setattr(sys, "stdout", Stream("stdout", events))
    monkeypatch.setattr(sys, "stderr", Stream("stderr", events))

    def announce_then_fail(_args):
        print(f"  gh    {SPEC_REPOSITORY}")
        raise failure(adopter)

    monkeypatch.setattr(adopter, "cmd_execute", announce_then_fail)

    assert adopter.main(["execute", "--plan", "adoption-plan.yaml"]) == 2
    assert ("stdout", "flush") in events
    assert (events.index(("stdout", "flush"))
            < events.index(("stderr", "write")))


def test_the_printed_seed_push_runs_from_a_seeded_leg(
        adopter, monkeypatch, capsys, tmp_path):
    """#177 with no `git filter-repo`: a seeded leg is a fresh `git init` with
    no `origin` either. Its push to `main` is refused by a hook standing in
    for a ruleset; the command the hint prints is then RUN, and it lands the
    leg's commit on the seed branch the hook allows."""
    monkeypatch.setattr(adopter, "copy_tree", seed_one_file)
    remote = tmp_path / REMOTES / f"{ASSEMBLY}-{SPEC}.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    write_refusing_hook(remote / "hooks", MAIN_REF)
    work = tmp_path / WORK / f"{ASSEMBLY}-{SPEC}"

    with pytest.raises(adopter.CommandFailed):
        adopter._seed_leg(SPEC, work, {}, BRANCH, str(remote), "main",
                          SPEC_REPOSITORY, ASSEMBLY)

    err = capsys.readouterr().err
    assert "re-run this scaffold" not in err
    pushed = run_git(printed_push(err), {})
    assert pushed.returncode == 0, pushed.stderr
    assert commit_of(remote, SEED_BRANCH) == commit_of(work)
    assert commit_of(remote, MAIN_REF) is None


# ---- end to end, with `git filter-repo` -------------------------------------

def adopt_with_hook(tmp_path: Path, ref_pattern: str):
    """Plan a small source, then execute it with every push meeting a hook
    that refuses `ref_pattern`, stdout and stderr merged into one pipe."""
    source = make_source_repo(tmp_path / "Thing", tree=SMALL_TREE, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=ASSEMBLY)
    assert written.returncode == 0, written.stderr + written.stdout
    env = hooks_everywhere(tmp_path, ref_pattern)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        "--work-dir", str(tmp_path / WORK), env=env,
                        merge_stderr=True)
    return source, env, result


def first_line(lines: list[str], text: str) -> int:
    for index, line in enumerate(lines):
        if text in line:
            return index
    raise AssertionError(f"{text!r} is in no line of:\n" + "\n".join(lines))


def run_git(argv: list[str], env: dict) -> subprocess.CompletedProcess:
    """`argv` as a person pastes it, with `env` over this process's own."""
    assert argv[0] == "git", argv
    return subprocess.run(argv, capture_output=True, text=True, check=False,
                          env={**os.environ, **env})


@needs_filter_repo
def test_a_refused_split_push_is_logged_after_the_legs_it_left(tmp_path):
    """Lane 2's reproduction (PR #184's review, P3-5): both legs are pushed,
    then a hook refuses the split branch. In the merged log every line that
    announced a leg comes BEFORE the REFUSED block, and the notice after it
    names both pushed legs."""
    source, _env, result = adopt_with_hook(tmp_path, "refs/heads/adopt/*")

    assert result.returncode == 2, result.stdout
    lines = result.stdout.splitlines()
    refused = first_line(lines, f"{REFUSED} {SPLIT_PUSH}.")
    announced = [index for index, line in enumerate(lines)
                 if line.startswith(("  bare", "  spec", "  code"))]
    assert len(announced) == 4, result.stdout
    assert max(announced) < refused
    notice = lines[first_line(lines, ROLLED_BACK)]
    assert BOTH_PUSHED in notice
    for role in LEGS:
        bare = tmp_path / REMOTES / f"{ASSEMBLY}-{role}.git"
        assert str(bare) in notice
        assert commit_of(bare, MAIN_REF) is not None
    assert commit_of(source, f"refs/heads/{BRANCH}") is None


@needs_filter_repo
def test_the_printed_seed_push_runs_from_an_extracted_leg(tmp_path):
    """#177 as the issue found it: the spec leg's push to `main` is refused,
    and the command the adoption prints is RUN from the clone `git filter-repo`
    rewrote. It lands the extracted leg's HEAD on the seed branch. The merged
    log also has the `bare` lines before the REFUSED block."""
    _source, env, result = adopt_with_hook(tmp_path, MAIN_REF)

    assert result.returncode == 2, result.stdout
    lines = result.stdout.splitlines()
    refused = first_line(lines, f"{REFUSED} pushing the {SPEC} leg.")
    assert max(index for index, line in enumerate(lines)
               if line.startswith("  bare")) < refused
    argv = printed_push(result.stdout)
    pushed = run_git(argv, env)
    assert pushed.returncode == 0, pushed.stderr
    work = tmp_path / WORK / f"{ASSEMBLY}-{SPEC}"
    bare = tmp_path / REMOTES / f"{ASSEMBLY}-{SPEC}.git"
    assert commit_of(bare, SEED_BRANCH) == commit_of(work)
