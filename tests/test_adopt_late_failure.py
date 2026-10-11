# SPDX-License-Identifier: Apache-2.0
"""`execute` says what failed once a leg repository exists, and what it left
(#188, #177, #184's review).

#171 made `_build_the_legs` report a leg that cannot be built: stdout flushed
first, the exact command and its output, then a notice naming the two leg
repositories and why a re-run is refused. Everything after the legs still had
main's behaviour. On main at f25d805 a split push refused by a pre-receive
hook printed only `REFUSED pushing the split branch`, a split commit refused
by a pre-commit hook printed `main`'s generic `REFUSED a git or gh command
failed`, a merged `> log 2>&1` showed REFUSED on line 0 and the `bare …` lines
after it, and the re-run met `leg-remote-exists` with nothing having said why.

The notice is now printed by every failure once a leg repository exists: the
code leg's repository that cannot be created after the spec leg's was, a leg,
the split, and a verification that fails. It says to fix what failed first,
names the work directory a re-run must not reuse once this run built in it,
and a failed verification names the split branch and the command that
deletes it; an `execute` that meets that branch, or a work directory an
earlier run built in, refuses before it creates anything. A failure that is
not a failed command -- a refusal on the way, a read-only directory, `git`
gone, output that is not UTF-8 -- gets the same report instead of a
traceback.

A refused LEG push printed `RULESET_HINT`, the scaffold's, whose second exit
is `git -C <work> push -u origin main:seed/scaffold` (#177). That cannot run
in a clone `git filter-repo` rewrote, and no seed exit can finish an adoption:
the leg is a repository this run created, with no tracking branch for a pull
request to target. An adoption's hint names its one exit.

The tests that need `git filter-repo` run `adopt-project.py execute` with a
merged stream; the rest call the functions in this process and need no
filter. NO NETWORK AND NO GITHUB: every remote is a bare repository on disk,
or no repository at all.
"""

from __future__ import annotations

import importlib.util
import io
import shlex
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, run_script,
                      write_plan)

SPEC, CODE = "spec", "code"
LEGS = (SPEC, CODE)
ASSEMBLY = "Northwind"
BRANCH = "adopt/three-repo-shape"
REMOTES = "remotes"
WORK = "work"
REFUSED = "REFUSED"
ROLLED_BACK = "NOTHING has been rolled back"
#: The notice's way out once something failed, rather than stopped (#188's
#: review, F2), and its work-directory sentence (#184 P2-1, its N2).
FIX_FIRST = "Once what failed above is fixed, re-run the adoption with"
FRESH_WORK_DIR = "Use a fresh --work-dir as well, or none: "
WORK_DIR_OCCUPIED = "adopt-work-dir-occupied"
#: What `execute` prints once every source path is accounted for.
VERIFIED = "adoption verified"
BOTH_PUSHED = "both legs are pushed"
MAIN_REF = "refs/heads/main"
SPLIT_PUSH = "pushing the split branch"
BRANCH_EXISTS = "adopt-branch-exists"
ORG = "testorg"
SPEC_REPOSITORY = f"{ORG}/{ASSEMBLY}-{SPEC}"
END_OUTPUT = "--- end output ---"
DELETE_COMMAND = "git -C "
NEITHER_PUSHED = "neither leg is pushed"
GIT_FAILED = "git-failed"
#: What the operating system says of a program that is not there.
NO_SUCH_FILE = "No such file or directory"
UTF8 = "utf-8"
README = "README.md"
SOURCE = "Thing"
ROOT = "assembly"
BARE_LINE = "  bare"
#: The names `Stream` records its events under.
STDOUT, STDERR, FLUSH = "stdout", "stderr", "flush"
#: The steps of `execute` the tests below stand in for.
MOUNT = "_mount_the_legs"
MATERIALIZE = "materialize_assembly_root"
EXTRACT = "_extract_leg"
COPY_TREE = "copy_tree"
TREE_OF = "_tree_of"
PLAN_FLAG = "--plan"

#: A source small enough that `plan` asks no question, so `execute` runs on
#: the plan as written.
SMALL_TREE = {README: "# Thing\n", "src/app/util.py": "VALUE = 1\n",
              "specs/001-feature/tasks.md": "- [ ] one\n"}

#: A source with a `contracts/shape-pin.yaml` of its OWN, naming a file the
#: plan sends to the code leg. Kept in the root, it is what the first
#: bootstrap would read, so the verification fails; sent to the spec leg, as
#: `plan` sends it, the adoption verifies.
OWN_PIN = ("schema_version: 1\nkind: pinned_contract_manifest\nfiles:\n"
           + "".join(f"  - path: {path}\n    sha256: \"{'0' * 64}\"\n"
                     for path in (README, "src/app/main.py")))
OWN_PIN_TREE = {README: "# Thing\n", ".gitignore": "__pycache__/\n",
                "specs/001-feature/spec.md": "# The feature\n",
                "src/app/main.py": "import contracts_reader\n",
                "contracts/shape-pin.yaml": OWN_PIN}
CONTRACTS_TO_SPEC = "  - path: contracts/\n    leg: spec\n"
CONTRACTS_KEPT = ("  - path: contracts/\n    leg: root\n"
                  "    resolution: \"kept beside the shape's own\"\n")

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
    """A text stream that records, in one shared list, when it was used, and
    keeps what was written to it."""

    def __init__(self, name: str, events: list):
        self.name = name
        self.events = events
        self.written: list[str] = []

    def write(self, text: str) -> int:
        self.events.append((self.name, "write"))
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        self.events.append((self.name, FLUSH))


def recorded_streams(monkeypatch) -> tuple[list, Stream]:
    """stdout and stderr replaced by `Stream`s: `(events, stderr)`."""
    events: list = []
    stderr = Stream(STDERR, events)
    monkeypatch.setattr(sys, STDOUT, Stream(STDOUT, events))
    monkeypatch.setattr(sys, STDERR, stderr)
    return events, stderr


def flushed_first(events: list) -> bool:
    """stdout was flushed before anything reached stderr."""
    return ((STDOUT, FLUSH) in events
            and events.index((STDOUT, FLUSH))
            < events.index((STDERR, "write")))


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
    with hook.open("w", encoding=UTF8, newline="\n") as handle:
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
                      encoding=UTF8)
    return {"GIT_CONFIG_GLOBAL": str(config)}


def seed_one_file(_template, work, _values) -> list[str]:
    """`copy_tree` for a seeded leg, without the template's placeholders. It
    returns what it wrote, as `copy_tree` does, because `_seed_leg` hands
    that list to `git_init_commit` to force past an ignore rule (#175)."""
    work.mkdir(parents=True, exist_ok=True)
    (work / README).write_text("seeded\n", encoding=UTF8)
    return [README]


def printed_command(text: str, start: str) -> list[str]:
    """The one line of `text` that starts with `start`, as the argv a person
    gets by pasting it into `sh`: through `shlex.split`, so a path the tool
    failed to quote comes back in pieces (#188 N5)."""
    lines = [line.strip() for line in text.splitlines()
             if line.strip().startswith(start)]
    assert len(lines) == 1, text
    return shlex.split(lines[0])


def commit_of(repo: Path, ref: str = "HEAD") -> str | None:
    """The commit `ref` names in `repo`, or None when it names none."""
    found = git("rev-parse", "-q", "--verify", f"{ref}^{{commit}}", cwd=repo,
                check=False)
    return found.stdout.strip() if found.returncode == 0 else None


def source_of(adopter, tmp_path: Path, name: str = SOURCE):
    origin = make_source_repo(tmp_path / name, tree=SMALL_TREE, edits=())
    return adopter.Source(origin, None, "main", commit_of(origin))


def leg_names() -> dict:
    names = {role: f"{ASSEMBLY}-{role}" for role in LEGS}
    names[ROOT] = ASSEMBLY
    return names


def leg_urls(tmp_path: Path, names: dict) -> dict:
    """One bare repository per leg, so a notice that names both is seen to."""
    return {role: str(tmp_path / REMOTES / f"{names[role]}.git")
            for role in LEGS}


def legs_arguments(tmp_path: Path, source=None) -> dict:
    """What `cmd_execute` hands `_build_the_legs`, for two extracted legs."""
    names = leg_names()
    return dict(source=source, names=names,
                repositories={role: f"{ORG}/{names[role]}" for role in LEGS},
                urls=leg_urls(tmp_path, names), values={},
                work_root=tmp_path / WORK,
                paths_for={role: [f"{role}/"] for role in LEGS}, seeded=[],
                branch=BRANCH, tracking="main")


def split_arguments(tmp_path: Path, source) -> dict:
    """What `cmd_execute` hands `_commit_the_split` once both legs are
    pushed. The leg commits are stand-ins: every step that would read them
    is either stubbed or fails before it does."""
    names = leg_names()
    urls = leg_urls(tmp_path, names)
    urls[ROOT] = str(source.path)
    return dict(
        plan={}, source=source, assembly=tmp_path / WORK / ASSEMBLY,
        names=names, urls=urls, values={}, work_root=tmp_path / WORK,
        paths_for={SPEC: ["specs/"], CODE: ["src/"], "root": [README],
                   "drop": []},
        seeded=[], spec_path=SPEC, code_path=CODE, branch=BRANCH,
        leg_commits={SPEC: "a" * 40, CODE: "b" * 40})


def the_notice(err: str) -> str:
    """The notice's one line."""
    lines = [line for line in err.splitlines() if line.startswith(ROLLED_BACK)]
    assert len(lines) == 1, err
    return lines[0]


def work_dir_named(notice: str, work_root: Path, *built: str) -> bool:
    """The notice tells a re-run to leave `work_root` alone, naming what this
    run built there (#184 P2-1); with `built`, exactly those."""
    sentence = f"{FRESH_WORK_DIR}{work_root} holds "
    listed = (" and ".join([", ".join(built[:-1]), built[-1]])
              if len(built) > 1 else "".join(built))
    return sentence in notice and (
        not built or f"{sentence}{listed} from this run" in notice)


def built_by_this_run(work: Path) -> None:
    """What a leg builder or the split's clone leaves in its directory: a
    clone, here one file standing in for it."""
    work.mkdir(parents=True)
    (work / README).write_text("built\n", encoding=UTF8)


# ---- one way for each step of the split to fail -----------------------------

def clone_fails(_adopter, _monkeypatch, arguments) -> None:
    """A work directory reused from an earlier run already holds the
    assembly clone, so `git clone` refuses it. Real git, no stub."""
    arguments[ROOT].mkdir(parents=True)
    (arguments[ROOT] / "left-over.txt").write_text("x\n",
                                                         encoding=UTF8)


def mount_fails(adopter, monkeypatch, arguments) -> None:
    def refused(*_args):
        raise adopter.CommandFailed(
            ["git", "submodule", "add", "-q",
             str(arguments["work_root"] / f"{ASSEMBLY}-{SPEC}"), SPEC],
            arguments[ROOT], 128, "fatal: 'spec' already exists in "
                                        "the index")
    monkeypatch.setattr(adopter, MOUNT, refused)


def commit_fails(adopter, monkeypatch, _arguments) -> None:
    """Nothing is mounted, written or staged, so the real `git commit` finds
    nothing to commit and exits 1."""
    monkeypatch.setattr(adopter, MOUNT, lambda *_args: None)
    monkeypatch.setattr(adopter, MATERIALIZE,
                        lambda *_args, **_kw: adopter.Materialized())
    monkeypatch.setattr(adopter, "_stage_the_split", lambda *_args: None)


def commit_for_real(adopter, monkeypatch) -> None:
    """Mount nothing and write one file, so the split commit is made for
    real and only its push is left to fail."""
    def write_one_file(_shape_root, target, *_args, **_kw):
        (target / "project.yaml").write_text("schema_version: 1\n",
                                             encoding=UTF8)
        materialized = adopter.Materialized()
        materialized.written.append("project.yaml")
        return materialized

    monkeypatch.setattr(adopter, MOUNT, lambda *_args: None)
    monkeypatch.setattr(adopter, MATERIALIZE, write_one_file)


def push_fails(adopter, monkeypatch, arguments) -> None:
    """The split commit is made for real; the source it is pushed back to is
    not there."""
    commit_for_real(adopter, monkeypatch)
    arguments["urls"][ROOT] = str(arguments["work_root"].parent
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
    repositories, both of them pushed, why a re-run is refused, and the work
    directory it must not reuse. Before #188 the mount and the commit fell
    through to `main`'s generic `a git or gh command failed`, and none of the
    four said what was left."""
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
    assert FIX_FIRST in notice
    # Read off the disk: the split's clone is there, and no leg's, because
    # the legs here are stand-ins that were never built in it.
    assert work_dir_named(notice, tmp_path / WORK, ASSEMBLY)
    # The notice is the whole way out. A refused split push used to add a
    # guess about a branch an earlier run left; `execute` now refuses that
    # branch before any leg exists, so this push is never refused for it.
    assert err.rstrip().splitlines()[-1].startswith(ROLLED_BACK)


@pytest.mark.parametrize("failing, state",
                         [(SPEC, NEITHER_PUSHED),
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

    monkeypatch.setattr(adopter, EXTRACT, build)
    arguments = legs_arguments(tmp_path)

    assert adopter._build_the_legs(**arguments) is None

    notice = capsys.readouterr().err.split(END_OUTPUT, 1)[1]
    urls = arguments["urls"]
    assert f"{urls[SPEC]} and {urls[CODE]} exist, and {state}." in notice


# ---- a failure that is not a failed command (#184 P3-1, #188 N3) ------------

def permission_denied(_adopter):
    return PermissionError(13, "Permission denied",
                           f"/read-only/work/{ASSEMBLY}-{CODE}")


def git_not_found(_adopter):
    return FileNotFoundError(2, NO_SUCH_FILE, "git")


def not_utf8(_adopter):
    return UnicodeDecodeError(UTF8, b"\xe9", 0, 1,
                              "invalid continuation byte")


def refused_by_git_out(adopter):
    """`git_out`'s refusal, with the validators' generic remediation."""
    return adopter.Refusal(
        GIT_FAILED, f"`git rev-parse HEAD` in {ASSEMBLY}-{CODE} exited "
                    "128: fatal: ambiguous argument 'HEAD'")


NOT_A_COMMAND = [permission_denied, git_not_found, not_utf8,
                 refused_by_git_out]
NOT_A_COMMAND_IDS = ["read-only", "no-git", "not-utf8", "git-out-refusal"]


def said_as(adopter, exc) -> str:
    """What the REFUSED line says of `exc` after the step."""
    if isinstance(exc, adopter.Refusal):
        return f"{exc.code}: {exc.detail}"
    return f"{type(exc).__name__}: {exc}"


@pytest.mark.parametrize("failure", NOT_A_COMMAND, ids=NOT_A_COMMAND_IDS)
def test_a_leg_that_fails_without_a_command_is_refused_with_the_notice(
        adopter, monkeypatch, tmp_path, failure):
    """These escaped `_build_the_legs` to `main`: a traceback with exit 1, or
    a refusal with no notice, both leg repositories left behind and the spec
    leg already pushed. Now each is a REFUSED block naming the step, after
    stdout is flushed, then the notice, and the build returns None, which
    `execute` turns into exit 2."""
    exc = failure(adopter)

    def build(role, _source, work, *_args):
        if role == CODE:
            raise exc
        built_by_this_run(work)
        return "c" * 40, "d" * 64

    monkeypatch.setattr(adopter, EXTRACT, build)
    events, stderr = recorded_streams(monkeypatch)
    arguments = legs_arguments(tmp_path)

    assert adopter._build_the_legs(**arguments) is None

    err = "".join(stderr.written)
    assert flushed_first(events)
    assert err.count(REFUSED) == 1, err
    assert f"{REFUSED} extracting the {CODE} leg. {said_as(adopter, exc)}" \
        in err
    # `git_out`'s remediation is about pins; the notice is the way out here.
    assert "validate-pins" not in err
    notice = the_notice(err)
    assert f"the {SPEC} leg is pushed" in notice
    assert FIX_FIRST in notice
    assert work_dir_named(notice, tmp_path / WORK, f"{ASSEMBLY}-{SPEC}")


def verify_arguments(tmp_path: Path, source) -> dict:
    """What `cmd_execute` hands `_verify` once the split is pushed: the
    split's own arguments, less what only the split reads, and a split
    commit. The legs and the split are stand-ins, never read: the failure
    comes first."""
    arguments = split_arguments(tmp_path, source)
    for split_only in ("plan", "values", "leg_commits"):
        del arguments[split_only]
    return dict(arguments, split_commit="e" * 40)


def test_a_verification_that_cannot_be_made_is_refused_with_the_notice(
        adopter, monkeypatch, tmp_path):
    """#188's review, N3: a `git` failure inside `_verify` -- here one that
    will not list a leg's tree -- reached `main` as `REFUSED git-failed`
    with the validators' remediation about pins, and said nothing of the two
    pushed legs, the work directory or the split branch. It is reported as
    every late failure is: stdout flushed, the step, the notice and the
    branch with its deletion. `execute` exits 2, as it did."""
    def unlistable(repo, rev):
        raise adopter.Refusal(GIT_FAILED, f"`git ls-tree -r -z {rev}` in "
                                          f"{repo} exited 128: fatal: not a "
                                          "tree object")

    monkeypatch.setattr(adopter, TREE_OF, unlistable)
    events, stderr = recorded_streams(monkeypatch)
    arguments = verify_arguments(tmp_path, source_of(adopter, tmp_path))
    built_by_this_run(arguments[ROOT])

    assert adopter._verify(**arguments) == 2

    err = "".join(stderr.written)
    assert flushed_first(events)
    assert err.count(REFUSED) == 1, err
    assert f"{REFUSED} verifying the split. {GIT_FAILED}: `git ls-tree" in err
    assert "validate-pins" not in err
    notice = the_notice(err)
    assert BOTH_PUSHED in notice
    assert FIX_FIRST in notice
    assert work_dir_named(notice, tmp_path / WORK, ASSEMBLY)
    assert printed_command(err, DELETE_COMMAND)[-2:] == ["--delete", BRANCH]


def test_an_interrupted_verification_still_says_what_the_run_left(
        adopter, monkeypatch, capsys, tmp_path):
    """Ctrl-C in `_verify`: after the split is pushed, so the same notice
    and branch, then the interrupt's own traceback."""
    def interrupted(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(adopter, TREE_OF, interrupted)

    with pytest.raises(KeyboardInterrupt):
        adopter._verify(**verify_arguments(tmp_path,
                                           source_of(adopter, tmp_path)))

    err = capsys.readouterr().err
    assert "STOPPED verifying the split by KeyboardInterrupt." in err
    assert FIX_FIRST not in the_notice(err)
    assert printed_command(err, DELETE_COMMAND)[-2:] == ["--delete", BRANCH]


def test_a_split_the_materializer_cannot_write_is_refused_with_the_notice(
        adopter, monkeypatch, capsys, tmp_path):
    """#188 N3 as lane 2 met it: a root-kept `.github -> .github` passes
    `check`, and the materializer then dies on the loop with an `OSError`,
    inside the step that commits the split, after both legs are pushed. It
    was a traceback with exit 1; it is a REFUSED block naming the step, and
    the notice."""
    loop = OSError(f"[Errno 40] Too many levels of symbolic links: "
                   f"'{tmp_path / WORK / ASSEMBLY / '.github'}'")

    def walk_into_the_loop(*_args, **_kw):
        raise loop

    arguments = split_arguments(tmp_path, source_of(adopter, tmp_path))
    monkeypatch.setattr(adopter, MOUNT, lambda *_args: None)
    monkeypatch.setattr(adopter, MATERIALIZE, walk_into_the_loop)

    assert adopter._commit_the_split(**arguments) is None

    err = capsys.readouterr().err
    assert f"{REFUSED} committing the split. OSError: {loop}" in err
    assert BOTH_PUSHED in the_notice(err)


def test_an_interrupted_leg_still_says_what_it_left(
        adopter, monkeypatch, capsys, tmp_path):
    """Ctrl-C, or a defect: not a refusal, so it is re-raised with its
    traceback, but only after the notice, because both leg repositories
    exist all the same."""
    def interrupted(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(adopter, EXTRACT, interrupted)

    with pytest.raises(KeyboardInterrupt):
        adopter._build_the_legs(**legs_arguments(tmp_path))

    err = capsys.readouterr().err
    assert f"STOPPED extracting the {SPEC} leg by KeyboardInterrupt." in err
    assert REFUSED not in err
    notice = the_notice(err)
    assert NEITHER_PUSHED in notice
    # Nothing failed, so there is nothing to fix before the re-run (F2).
    assert "Re-run the adoption with them deleted or with fresh ones" \
        in notice
    assert FIX_FIRST not in notice


def test_an_interrupted_split_still_says_what_it_left(
        adopter, monkeypatch, capsys, tmp_path):
    """The same for the split: both legs are pushed, so the notice says so,
    with nothing to fix first, and the interrupt is re-raised."""
    def interrupted(*_args):
        raise KeyboardInterrupt

    monkeypatch.setattr(adopter, MOUNT, interrupted)

    with pytest.raises(KeyboardInterrupt):
        adopter._commit_the_split(**split_arguments(
            tmp_path, source_of(adopter, tmp_path)))

    err = capsys.readouterr().err
    assert "STOPPED mounting the legs by KeyboardInterrupt." in err
    notice = the_notice(err)
    assert BOTH_PUSHED in notice
    assert FIX_FIRST not in notice


# ---- a defect is not an interrupt (#188's re-verification, R2) --------------

#: How the notice opens for a run that was interrupted: nothing failed.
RERUN_ONLY = "Re-run the adoption with"


def stand_in(kind: type):
    """A step that raises a NEW `kind` each time it is called, because
    `_report_late` marks the exception it has reported."""
    def raised(*_args, **_kw):
        raise kind()
    return raised


def at_the_code_leg_repository(adopter, monkeypatch, tmp_path, step) -> None:
    """#188 N4's point: the spec leg's repository is made, then the code
    leg's raises. A bare repository on disk stands in for GitHub's."""
    create = adopter._create_leg_remote

    def the_code_legs_raises(*args):
        if args[-1] == CODE:
            step()
        create(*args)

    monkeypatch.setattr(adopter, "_create_leg_remote", the_code_legs_raises)
    names = leg_names()
    adopter._create_leg_remotes({}, names, {}, leg_urls(tmp_path, names),
                                "main", True, tmp_path / WORK)


def in_a_leg(adopter, monkeypatch, tmp_path, step) -> None:
    monkeypatch.setattr(adopter, EXTRACT, step)
    adopter._build_the_legs(**legs_arguments(tmp_path))


def in_the_split(adopter, monkeypatch, tmp_path, step) -> None:
    monkeypatch.setattr(adopter, MOUNT, step)
    adopter._commit_the_split(**split_arguments(
        tmp_path, source_of(adopter, tmp_path)))


def in_the_verification(adopter, monkeypatch, tmp_path, step) -> None:
    monkeypatch.setattr(adopter, TREE_OF, step)
    adopter._verify(**verify_arguments(tmp_path,
                                       source_of(adopter, tmp_path)))


@pytest.mark.parametrize("act, step",
                         [(at_the_code_leg_repository,
                           f"creating the {CODE} leg repository"),
                          (in_a_leg, f"extracting the {SPEC} leg"),
                          (in_the_split, "mounting the legs"),
                          (in_the_verification, "verifying the split")],
                         ids=["code-leg-repository", "leg", "split",
                              "verification"])
@pytest.mark.parametrize("kind, opening",
                         [(TypeError, FIX_FIRST),
                          (KeyboardInterrupt, RERUN_ONLY)],
                         ids=["defect", "interrupt"])
def test_only_an_interrupt_is_told_to_re_run_with_nothing_to_fix(
        adopter, monkeypatch, capsys, tmp_path, act, step, kind, opening):
    """#188's re-verification, R2. What a step does not anticipate is
    re-raised after the notice, and that notice said only "Re-run" for all
    of it, as for Ctrl-C, which failed at nothing. A defect -- this
    `TypeError` -- fails the same way on every re-run, so following that
    made one more pair of leg repositories per attempt. It is told to fix
    what failed first, as a refusal is; only an interrupt is not."""
    with pytest.raises(kind):
        act(adopter, monkeypatch, tmp_path, stand_in(kind))

    err = capsys.readouterr().err
    assert f"STOPPED {step} by {kind.__name__}." in err
    notice = the_notice(err)
    other = RERUN_ONLY if opening == FIX_FIRST else FIX_FIRST
    assert opening in notice and other not in notice, notice


@pytest.mark.parametrize("seeded", [[], [SPEC]],
                         ids=["extracted-leg", "seeded-leg"])
def test_a_leg_is_pushed_last_so_the_notice_cannot_miscount_it(
        adopter, monkeypatch, capsys, tmp_path, seeded):
    """The notice says which legs are pushed from the builders that
    returned. A read that failed AFTER the push would have it call a pushed
    leg unpushed, so both builders read what they need first: here the
    digest fails, and the remote is as the notice says."""
    real_run = adopter.run

    def without_the_filter(args, *rest, **keywords):
        if args[:2] == ["git", "filter-repo"]:
            return ""
        return real_run(args, *rest, **keywords)

    def unreadable(*_args):
        raise adopter.Refusal(GIT_FAILED, "`git ls-tree -r -z HEAD` "
                                          "exited 128: fatal: bad tree")

    monkeypatch.setattr(adopter, "run", without_the_filter)
    monkeypatch.setattr(adopter, "tree_digest", unreadable)
    monkeypatch.setattr(adopter, COPY_TREE, seed_one_file)
    arguments = legs_arguments(tmp_path, source=source_of(adopter, tmp_path))
    arguments["seeded"] = seeded
    for role in LEGS:
        git("init", "-q", "--bare", "-b", "main", arguments["urls"][role],
            cwd=tmp_path)

    assert adopter._build_the_legs(**arguments) is None

    assert NEITHER_PUSHED in the_notice(capsys.readouterr().err)
    assert commit_of(Path(arguments["urls"][SPEC]), MAIN_REF) is None


# ---- the leg repositories, and what `main` is left to report ----------------

def refused_before_any_leg(adopter, monkeypatch, _tmp_path) -> tuple:
    """A refusal no step reports: one raised before any leg repository
    exists, once stdout has printed something (the topic line, say)."""
    def announce_then_refuse(_args):
        print("topics: NOT set (--local-remote-dir)")
        raise adopter.Refusal(
            GIT_FAILED, f"`git ls-tree -r -z HEAD` in {ASSEMBLY} exited "
                        "128: fatal: not a valid object name HEAD")

    monkeypatch.setattr(adopter, "cmd_execute", announce_then_refuse)
    return ["REFUSED git-failed: "], [ROLLED_BACK]


def code_leg_repository_fails(adopter, monkeypatch, tmp_path,
                              failure=None) -> tuple:
    """#188 N4, against GitHub: the spec leg's repository is created and
    announced, then `gh repo create` fails for the code leg's. The re-run
    meets the spec repository, so the failure names it, and only it.
    `failure` is what `run` raises instead of the command failing."""
    names = leg_names()
    repositories = {role: f"{ORG}/{names[role]}" for role in LEGS}
    repositories[ROOT] = f"{ORG}/{ASSEMBLY}"
    urls = {role: f"https://github.com/{ORG}/{name}.git"
            for role, name in names.items()}

    def gh(args, *_rest, **_kw):
        if args[:4] == ["gh", "repo", "create", repositories[CODE]]:
            raise failure or adopter.CommandFailed(
                args, None, 1, "GraphQL: Name already exists on this account")
        return ""

    def create_the_legs(_args):
        adopter._create_leg_remotes({}, names, repositories, urls, "main",
                                    False, tmp_path / WORK)
        return 0

    monkeypatch.setattr(adopter, "run", gh)
    monkeypatch.setattr(adopter, "cmd_execute", create_the_legs)
    said = (f"{type(failure).__name__}: {failure}" if failure
            else "THE EXACT COMMAND WAS:")
    # Nothing was built in the work directory yet, so the notice does not
    # send the re-run away from it (#188's review, N2).
    return ([f"{REFUSED} creating the {CODE} leg repository. {said}",
             f"{ROLLED_BACK}: {urls[SPEC]} exists, and nothing is pushed to "
             f"it. {FIX_FIRST} it deleted or with a fresh one"],
            [urls[CODE], FRESH_WORK_DIR])


def code_leg_gh_cannot_run(adopter, monkeypatch, tmp_path) -> tuple:
    """The same with `gh` gone from PATH between the two: an `OSError`,
    which `_create_leg_remotes` reports as REFUSED with the notice, and on
    which `main` must then exit 2, as it says, and not with a traceback."""
    return code_leg_repository_fails(
        adopter, monkeypatch, tmp_path,
        FileNotFoundError(2, NO_SUCH_FILE, "gh"))


@pytest.mark.parametrize("scenario",
                         [refused_before_any_leg, code_leg_repository_fails,
                          code_leg_gh_cannot_run],
                         ids=["refusal", "command", "gh-cannot-run"])
def test_main_flushes_stdout_before_a_failure_no_step_reported(
        adopter, monkeypatch, tmp_path, scenario):
    """What `main` is handed: a refusal no step reported, which it prints
    after flushing stdout so a merged log keeps the order; or, since #188
    N4, a code leg repository that failed after the spec leg's was created,
    which `_create_leg_remotes` has reported with the notice naming the one
    that exists, and which `main` must not print a second time: a failed
    command or a `gh` that could not be run at all, exit 2 either way."""
    events, stderr = recorded_streams(monkeypatch)
    said, unsaid = scenario(adopter, monkeypatch, tmp_path)

    assert adopter.main(["execute", PLAN_FLAG, "adoption-plan.yaml"]) == 2

    err = "".join(stderr.written)
    assert flushed_first(events)
    assert err.count(REFUSED) == 1, err
    for text in said:
        assert text in err, err
    for text in unsaid:
        assert text not in err, err


def test_stdout_is_flushed_before_a_late_failure_reaches_stderr_split(
        adopter, monkeypatch, tmp_path):
    """The split's own report comes after every line the run announced, in
    a log that merges the two streams."""
    events, _stderr = recorded_streams(monkeypatch)
    arguments = split_arguments(tmp_path, source_of(adopter, tmp_path))
    mount_fails(adopter, monkeypatch, arguments)

    assert adopter._commit_the_split(**arguments) is None

    assert flushed_first(events)


def pull_request_fails(adopter, monkeypatch, failure):
    def refused(args, *_rest, **_kw):
        raise failure(args)
    monkeypatch.setattr(adopter, "run", refused)
    repositories = {role: f"{ORG}/{ASSEMBLY}-{role}" for role in LEGS}
    repositories[ROOT] = f"{ORG}/{ASSEMBLY}"
    names = {role: f"{ASSEMBLY}-{role}" for role in LEGS}
    assert not adopter._open_the_pull_request(repositories, names, "main",
                                              BRANCH, "body")
    return "opening the pull request", "Open the pull request by hand"


def topic_fails(adopter, monkeypatch, failure):
    def refused(args, *_rest, **_kw):
        raise failure(args)
    monkeypatch.setattr(adopter, "run", refused)
    repositories = {role: f"{ORG}/{ASSEMBLY}-{role}"
                    for role in (*LEGS, ROOT)}
    assert not adopter._set_the_topic(repositories, "xf-project-northwind")
    return "setting the project topic", "Set the topic by hand"


def leg_push_fails(adopter, monkeypatch, tmp_path):
    monkeypatch.setattr(adopter, COPY_TREE, seed_one_file)
    with pytest.raises(adopter.CommandFailed):
        adopter._seed_leg(SPEC, tmp_path / WORK / f"{ASSEMBLY}-{SPEC}", {},
                          BRANCH, str(tmp_path / "gone.git"), "main",
                          SPEC_REPOSITORY, ASSEMBLY)


def gh_refused(adopter, args):
    return adopter.CommandFailed(args, None, 1, "HTTP 502")


def gh_not_found(_adopter, _args):
    return FileNotFoundError(2, NO_SUCH_FILE, "gh")


@pytest.mark.parametrize("fail", [pull_request_fails, topic_fails],
                         ids=["pull-request", "topic"])
@pytest.mark.parametrize("failure", [gh_refused, gh_not_found],
                         ids=["refused", "gh-not-found"])
def test_a_gh_step_after_the_split_gets_its_by_hand_exit(
        adopter, monkeypatch, fail, failure):
    """After the split is pushed, `gh` failing is not a re-run: the exit is
    the command that finishes the job by hand. Stdout is flushed before it,
    and a `gh` that cannot be run at all gets the same exit as one that
    refused, rather than a traceback (#188)."""
    events, stderr = recorded_streams(monkeypatch)

    step, by_hand = fail(adopter, monkeypatch,
                         lambda args: failure(adopter, args))

    err = "".join(stderr.written)
    assert flushed_first(events)
    assert f"{REFUSED} {step}." in err
    assert by_hand in err


def test_stdout_is_flushed_before_a_refused_leg_push_reaches_stderr(
        adopter, monkeypatch, tmp_path):
    """A leg builder reports its own refused push, so it flushes first."""
    events, _stderr = recorded_streams(monkeypatch)

    leg_push_fails(adopter, monkeypatch, tmp_path)

    assert flushed_first(events)


def test_a_closed_stdout_does_not_swallow_the_report(
        adopter, monkeypatch, tmp_path):
    """The flush must not cost the human the report: with stdout on a pipe
    nobody reads, flushing raises BrokenPipeError, and the REFUSED block and
    the notice must still reach stderr."""
    err = io.StringIO()
    monkeypatch.setattr(sys, STDOUT, ClosedPipe())
    monkeypatch.setattr(sys, STDERR, err)
    arguments = split_arguments(tmp_path, source_of(adopter, tmp_path))
    mount_fails(adopter, monkeypatch, arguments)

    assert adopter._commit_the_split(**arguments) is None

    assert f"{REFUSED} mounting the legs." in err.getvalue()
    assert ROLLED_BACK in err.getvalue()


def test_a_refused_leg_push_offers_an_adoption_its_one_exit(
        adopter, monkeypatch, capsys, tmp_path):
    """#188 N2. The scaffold's second exit, a seed branch and a pull request,
    cannot finish an adoption: the leg is a repository this run created, its
    first push is the one refused, so it has no `main` for that pull request
    to target, and nothing resumes the adoption from a merged one. The hint
    names the one exit, and no command for the other. A seeded leg, pushed
    to a bare remote whose hook refuses `main` as a ruleset does."""
    monkeypatch.setattr(adopter, COPY_TREE, seed_one_file)
    remote = tmp_path / REMOTES / f"{ASSEMBLY}-{SPEC}.git"
    git("init", "-q", "--bare", "-b", "main", str(remote), cwd=tmp_path)
    write_refusing_hook(remote / "hooks", MAIN_REF)

    with pytest.raises(adopter.CommandFailed):
        adopter._seed_leg(SPEC, tmp_path / WORK / f"{ASSEMBLY}-{SPEC}", {},
                          BRANCH, str(remote), "main", SPEC_REPOSITORY,
                          ASSEMBLY)

    err = capsys.readouterr().err
    assert f"{REFUSED} pushing the seeded {SPEC} leg." in err
    assert "An adoption has ONE legitimate exit: have an operator" in err
    assert f"{SPEC_REPOSITORY} has no main for that pull request" in err
    assert "re-run this scaffold" not in err
    # The notice under the hint says to fix what failed first. Under a
    # ruleset the hint says what that fix is, and that it is not a change to
    # the ruleset, so the two read as one way out (the re-verification, R4).
    assert ("Under such a ruleset, that bypass is the fix the notice below "
            "asks for, never a change to the ruleset.") \
        in " ".join(err.split())
    for command in ("git -C ", "gh pr create"):
        assert not any(line.strip().startswith(command)
                       for line in err.splitlines()), err
    # What the hint says of the leg is so: the refused push left it empty.
    assert git("for-each-ref", cwd=remote).stdout == ""


# ---- the split branch an earlier run left (#188 N1) -------------------------

def execute_args(tmp_path: Path, plan: Path) -> Namespace:
    """What `main` hands `cmd_execute` for `--yes` into fresh remotes."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES, allow_empty_leg=[],
                     yes=True, work_dir=tmp_path / WORK)


def planned(tmp_path: Path, source: Path) -> Path:
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=ASSEMBLY)
    assert written.returncode == 0, written.stderr + written.stdout
    return plan


def no_filter_repo_probe(adopter, monkeypatch) -> None:
    """`cmd_execute` asks for `git filter-repo` first, and the tests that
    call it are about refusals made before it would be used."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


def branch_at(repo: Path, commit: str = "HEAD") -> None:
    """A branch of the split's name in `repo`, at `commit`."""
    git("branch", BRANCH, commit, cwd=repo)


def leave_a_split_branch(source: Path) -> str:
    """What an earlier `execute` leaves on the source, verified or not: its
    split branch, at a commit made on top of the source commit, as a split
    commit is. Returns that commit."""
    tree = git("rev-parse", "HEAD^{tree}", cwd=source).stdout.strip()
    split = git("-c", "user.name=Earlier Run",
                "-c", "user.email=earlier@run.invalid", "commit-tree", tree,
                "-p", "HEAD", "-m", "Adopt the three-repository shape",
                cwd=source).stdout.strip()
    branch_at(source, split)
    return split


def no_leg_exists(tmp_path: Path) -> bool:
    return (not (tmp_path / REMOTES).exists()
            and not any((tmp_path / WORK / f"{ASSEMBLY}-{role}").exists()
                        for role in LEGS))


def test_a_split_branch_left_behind_is_refused_before_any_leg_exists(
        adopter, monkeypatch, tmp_path):
    """A run whose verification failed leaves its split branch, and the
    re-run into fresh legs then made and pushed two more legs before the
    split push was refused as not a fast-forward, every time. `execute` now
    asks the assembly first and refuses before anything exists. Its way out
    is a command, quoted for `sh`: the source's path here has a space in it,
    and the command, pasted, deletes the branch and nothing else."""
    no_filter_repo_probe(adopter, monkeypatch)
    source = make_source_repo(tmp_path / "my source", tree=SMALL_TREE,
                              edits=())
    plan = planned(tmp_path, source)
    split = leave_a_split_branch(source)

    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))

    refusal = caught.value
    assert refusal.code == BRANCH_EXISTS
    assert refusal.detail == (
        f"{source} already has {BRANCH}, the branch this adoption pushes its "
        f"split commit to, at {split[:12]}: neither the source commit "
        f"{commit_of(source)[:12]} nor a commit behind it")
    assert refusal.remediation.startswith(
        "Remediation: no leg repository was created and nothing was pushed.")
    # `adopt_branch:` is a plan value, and may name a branch of the source's
    # own: the way out for that is not its deletion (#188's review, N1).
    assert "give `adopt_branch:` a name no branch has" in refusal.remediation
    assert no_leg_exists(tmp_path)

    deleted = subprocess.run(printed_command(refusal.remediation,
                                             DELETE_COMMAND),
                             capture_output=True, text=True, check=False)
    assert deleted.returncode == 0, deleted.stderr
    assert git("branch", "--format=%(refname:short)",
               cwd=source).stdout.split() == ["main"]
    opened = adopter.Source(source, None, "main", commit_of(source))
    assert adopter._refuse_a_split_branch_left_behind(
        opened, {ROOT: str(source), **leg_urls(tmp_path, leg_names())},
        BRANCH, True) is None


def test_a_live_leg_keeps_its_own_refusal_over_the_split_branch(
        adopter, monkeypatch, tmp_path):
    """After a run that VERIFIED, the legs and the branch are both there.
    `leg-remote-exists` is the older refusal and the one that run meets
    first, so it keeps its precedence: the branch is for a re-run that has
    cleared its legs."""
    no_filter_repo_probe(adopter, monkeypatch)
    source = make_source_repo(tmp_path / SOURCE, tree=SMALL_TREE, edits=())
    plan = planned(tmp_path, source)
    leave_a_split_branch(source)
    (tmp_path / REMOTES / f"{ASSEMBLY}-{SPEC}.git").mkdir(parents=True)

    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))

    assert caught.value.code == "leg-remote-exists"


def test_against_github_the_split_branch_is_asked_of_the_assembly(
        adopter, tmp_path):
    """Against GitHub nothing is on disk to look at, and the leg names are
    taken or not by `gh repo create`; the branch is asked of the URL the
    split is pushed to, which a local path stands in for here."""
    source = source_of(adopter, tmp_path)
    urls = {ROOT: str(source.path),
            **{role: f"https://github.com/{ORG}/{ASSEMBLY}-{role}.git"
               for role in LEGS}}
    assert adopter._refuse_a_split_branch_left_behind(
        source, urls, BRANCH, False) is None
    leave_a_split_branch(source.path)

    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_a_split_branch_left_behind(source, urls, BRANCH,
                                                   False)

    assert caught.value.code == BRANCH_EXISTS


@pytest.mark.parametrize("behind", [0, 2],
                         ids=["at-the-source-commit", "behind-it"])
def test_a_branch_the_split_push_fast_forwards_is_not_refused(
        adopter, tmp_path, behind):
    """#188's review, N1: a branch of that name at the source commit, or
    behind it, is one the split push moves forward without force, and main
    always pushed over it and verified. It was refused, as if it were an
    earlier run's split, with a reason that was false for it."""
    origin = make_source_repo(tmp_path / SOURCE)
    branch_at(origin, f"HEAD~{behind}")
    source = adopter.Source(origin, None, "main", commit_of(origin))

    assert adopter._refuse_a_split_branch_left_behind(
        source, {ROOT: str(origin), **leg_urls(tmp_path, leg_names())},
        BRANCH, True) is None


def test_a_refusal_from_the_substitution_table_leaves_no_leg_repository(
        adopter, monkeypatch, tmp_path):
    """The table can refuse -- an `elected_on` that is not a date, a
    checkout of this standard that is not a git repository -- and it was
    built AFTER the leg repositories were created, leaving both behind with
    nothing saying so. It is built before them now."""
    no_filter_repo_probe(adopter, monkeypatch)
    plan = planned(tmp_path, make_source_repo(tmp_path / SOURCE,
                                              tree=SMALL_TREE, edits=()))

    def refused(*_args):
        raise adopter.Refusal("election-date-invalid",
                              "elected_on 2026-13-45 is not a date")

    monkeypatch.setattr(adopter, "_template_values", refused)

    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))

    assert caught.value.code == "election-date-invalid"
    assert no_leg_exists(tmp_path)


# ---- the work directory an earlier run built in (#188's review, F1) ---------

def listing(work: Path) -> list[str]:
    return sorted(path.relative_to(work).as_posix()
                  for path in work.rglob("*"))


@pytest.mark.parametrize("role, as_file",
                         [(SPEC, False), (CODE, False), (ROOT, False),
                          (SPEC, True)],
                         ids=["spec-leg", "code-leg", "split", "a-file"])
def test_a_work_dir_an_earlier_run_built_in_is_refused_before_any_leg_exists(
        adopter, monkeypatch, tmp_path, role, as_file):
    """`adopt-branch-exists`'s way out, "delete the branch, then run
    `execute` again", kept the `--work-dir` the earlier run had built in, so
    the re-run made a new pair of leg repositories before `git clone`
    refused that directory; against GitHub, two real ones per attempt. A work
    directory holding anything where a run builds a leg or the split is now
    refused before anything exists, and before the split branch the earlier
    run left, so that refusal's own way out meets a free one. A FILE there is
    refused too: `git clone` refuses it as well."""
    no_filter_repo_probe(adopter, monkeypatch)
    plan = planned(tmp_path, make_source_repo(tmp_path / SOURCE,
                                              tree=SMALL_TREE, edits=()))
    leave_a_split_branch(tmp_path / SOURCE)
    work, name = tmp_path / WORK, leg_names()[role]
    if as_file:
        work.mkdir()
        (work / name).write_text("a file\n", encoding=UTF8)
    else:
        built_by_this_run(work / name)
    before = listing(work)

    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(execute_args(tmp_path, plan))

    refusal = caught.value
    assert refusal.code == WORK_DIR_OCCUPIED
    what = "the split" if role == ROOT else f"the {role} leg"
    assert refusal.detail.startswith(
        f"--work-dir {work} already holds {name}, where this run builds "
        f"{what}, and only after it has made both leg repositories")
    assert refusal.remediation == (
        "Remediation: no leg repository was created and nothing was pushed. "
        "Pass a --work-dir that is new or empty, or none: without one, each "
        "run makes a new one.")
    assert not (tmp_path / REMOTES).exists()
    assert listing(work) == before


class ReachedTheConfirmation(Exception):
    """Raised where `_confirm` would ask: every refusal before it passed."""


def no_work_dir(args: Namespace) -> None:
    args.work_dir = None


def a_new_work_dir(args: Namespace) -> None:
    args.work_dir = args.work_dir.parent / "a new work dir"


def empty_directories_where_a_run_builds(args: Namespace) -> None:
    """What `git clone` takes: an empty directory at each name."""
    for name in leg_names().values():
        (args.work_dir / name).mkdir(parents=True)


@pytest.mark.parametrize("arrange", [no_work_dir, a_new_work_dir,
                                     empty_directories_where_a_run_builds],
                         ids=["default", "new", "empty-directories"])
def test_a_default_new_or_empty_work_dir_is_never_refused(
        adopter, monkeypatch, tmp_path, arrange):
    """F1's refusal must never meet a run that could have built: without
    `--work-dir`, `_work_root` makes a new, empty directory (here under this
    test's own temporary directory), a new path holds nothing, and an empty
    directory at a leg's name is one `git clone` clones into."""
    no_filter_repo_probe(adopter, monkeypatch)
    plan = planned(tmp_path, make_source_repo(tmp_path / SOURCE,
                                              tree=SMALL_TREE, edits=()))
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    monkeypatch.setattr(adopter.tempfile, "tempdir", str(temporary))

    def reached(*_args):
        raise ReachedTheConfirmation

    monkeypatch.setattr(adopter, "_confirm", reached)
    args = execute_args(tmp_path, plan)
    arrange(args)

    with pytest.raises(ReachedTheConfirmation):
        adopter.cmd_execute(args)


def test_agents_md_step_7_names_the_exit_the_tool_prints():
    """AGENTS.md step 7 is what an assistant reads when the verification
    fails. It said the exit was "to fix the plan and re-run into fresh
    legs", which `execute` now refuses, as `adopt-branch-exists` or
    `adopt-work-dir-occupied`, before it makes anything (#188's review,
    F3). It names the exit the tool prints: the plan, the split branch, and
    fresh legs with a fresh work directory."""
    agents = (REPO / "AGENTS.md").read_text(encoding=UTF8)
    step = agents.split("7. **Read the verification table back to them.**",
                        1)[1].split("\n\n", 1)[0]
    said = " ".join(step.split())
    for part in ("fix the plan", "delete the split branch",
                 "re-run into fresh legs and a fresh `--work-dir`, or none"):
        assert part in said, said


# ---- end to end, with `git filter-repo` -------------------------------------

def adopt_with_hook(tmp_path: Path, ref_pattern: str):
    """Plan a small source, then execute it with every push meeting a hook
    that refuses `ref_pattern`, stdout and stderr merged into one pipe."""
    source = make_source_repo(tmp_path / SOURCE, tree=SMALL_TREE, edits=())
    plan = planned(tmp_path, source)
    env = hooks_everywhere(tmp_path, ref_pattern)
    result = execute(plan, tmp_path / REMOTES, tmp_path / WORK, env=env,
                     merge_stderr=True)
    return source, plan, result


def execute(plan: Path, remotes: Path, work: Path, env: dict | None = None,
            merge_stderr: bool = False) -> subprocess.CompletedProcess:
    return run_script(ADOPT, "execute", PLAN_FLAG, str(plan), "--yes",
                      "--local-remote-dir", str(remotes), "--work-dir",
                      str(work), env=env, merge_stderr=merge_stderr)


def first_line(lines: list[str], text: str) -> int:
    for index, line in enumerate(lines):
        if text in line:
            return index
    raise AssertionError(f"{text!r} is in no line of:\n" + "\n".join(lines))


@needs_filter_repo
def test_a_refused_split_push_is_logged_after_the_legs_and_its_way_out_runs(
        tmp_path):
    """Lane 2's reproduction (PR #184's review, P3-5): both legs are pushed,
    then a hook refuses the split branch. In the merged log every line that
    announced a leg comes BEFORE the REFUSED block, and the notice after it
    names both pushed legs and the work directory. Then its way out, word
    for word, with the cause gone: a new --local-remote-dir and a fresh
    --work-dir end in `adoption verified` (#184 P2-1)."""
    source, plan, result = adopt_with_hook(tmp_path, "refs/heads/adopt/*")

    assert result.returncode == 2, result.stdout
    lines = result.stdout.splitlines()
    refused = first_line(lines, f"{REFUSED} {SPLIT_PUSH}.")
    announced = [index for index, line in enumerate(lines)
                 if line.startswith((BARE_LINE, "  spec", "  code"))]
    assert len(announced) == 4, result.stdout
    assert max(announced) < refused
    notice = the_notice(result.stdout)
    assert BOTH_PUSHED in notice
    for role in LEGS:
        bare = tmp_path / REMOTES / f"{ASSEMBLY}-{role}.git"
        assert str(bare) in notice
        assert commit_of(bare, MAIN_REF) is not None
    assert work_dir_named(notice, tmp_path / WORK)
    assert commit_of(source, f"refs/heads/{BRANCH}") is None

    rerun = execute(plan, tmp_path / "new remotes", tmp_path / "new work")

    assert rerun.returncode == 0, rerun.stderr + rerun.stdout
    assert VERIFIED in rerun.stdout


@needs_filter_repo
def test_a_branch_at_the_source_commit_is_pushed_over_and_verifies(tmp_path):
    """N1 end to end, as the review of #188 met it (its case F): a branch of
    the split's name at the source commit, as `git branch` leaves one. The
    split push fast-forwards it, onto a split commit whose parent is the
    source commit, and the adoption verifies, as it did on main."""
    source = make_source_repo(tmp_path / SOURCE, tree=SMALL_TREE, edits=())
    plan = planned(tmp_path, source)
    branch_at(source)

    result = execute(plan, tmp_path / REMOTES, tmp_path / WORK)

    assert result.returncode == 0, result.stderr + result.stdout
    assert VERIFIED in result.stdout
    split = commit_of(source, f"refs/heads/{BRANCH}")
    assert commit_of(source, f"{split}^") == commit_of(source)


@needs_filter_repo
def test_a_refused_leg_push_is_logged_after_the_legs_with_one_exit(tmp_path):
    """#177 as the issue found it: the spec leg's push to `main` is refused,
    in a clone `git filter-repo` rewrote. The merged log has the `bare`
    lines before the REFUSED block, and the hint offers no push for that
    clone to run, only the re-run (#188 N2)."""
    _source, _plan, result = adopt_with_hook(tmp_path, MAIN_REF)

    assert result.returncode == 2, result.stdout
    lines = result.stdout.splitlines()
    refused = first_line(lines, f"{REFUSED} pushing the {SPEC} leg.")
    assert max(index for index, line in enumerate(lines)
               if line.startswith(BARE_LINE)) < refused
    assert "ONE legitimate exit" in result.stdout
    assert "push -u origin" not in result.stdout
    assert work_dir_named(the_notice(result.stdout), tmp_path / WORK)


@needs_filter_repo
def test_a_failed_verification_is_flushed_and_its_way_out_runs(tmp_path):
    """#188 N1. A verification that fails is the last late failure: its
    findings came first in a merged log, and its exit -- re-run into fresh
    legs -- made and pushed two more legs and then met the split branch this
    run had pushed. Now the findings come after every line the run printed,
    and the exit names the legs, the work directory and the branch with the
    command that deletes it.

    Then the way out as the review of #188 followed it (F1): the plan fixed
    and fresh legs, but the work directory and the branch kept. That re-run
    is refused for the work directory first, before anything exists; its
    way out, a new one, is refused for the branch; and that refusal's way
    out, followed as written -- the deletion it prints, then `execute`
    again -- ends in `adoption verified`."""
    source = make_source_repo(tmp_path / SOURCE, tree=OWN_PIN_TREE,
                              edits=())
    plan = planned(tmp_path, source)
    answered = plan.read_text(encoding=UTF8)
    assert CONTRACTS_TO_SPEC in answered
    plan.write_text(answered.replace(CONTRACTS_TO_SPEC, CONTRACTS_KEPT, 1),
                    encoding=UTF8)
    checked = run_script(ADOPT, "check", PLAN_FLAG, str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout

    failed = execute(plan, tmp_path / REMOTES, tmp_path / WORK,
                     merge_stderr=True)

    assert failed.returncode == 1, failed.stdout
    lines = failed.stdout.splitlines()
    finding = first_line(lines, "FINDING adopt-shape-file-missing")
    printed = [index for index, line in enumerate(lines)
               if line.startswith((BARE_LINE, "  spec", "  code", "  split",
                                   "  added"))]
    assert max(printed) < finding, failed.stdout
    # The finding's own exit points at the way out below, which "re-run
    # into fresh legs" alone left out the work directory and the branch of.
    assert ("send that path to a leg or `drop` it, and re-run as the end of "
            "this report says") in lines[finding]
    notice = the_notice(failed.stdout)
    assert BOTH_PUSHED in notice
    assert FIX_FIRST in notice
    assert work_dir_named(notice, tmp_path / WORK, f"{ASSEMBLY}-{SPEC}",
                          f"{ASSEMBLY}-{CODE}", ASSEMBLY)
    assert f"The split is pushed to {source} too, as {BRANCH}" \
        in failed.stdout
    delete = printed_command(failed.stdout, DELETE_COMMAND)

    plan.write_text(answered, encoding=UTF8)
    fresh_legs, new_work = tmp_path / "remotes 2", tmp_path / "work 2"
    kept = execute(plan, fresh_legs, tmp_path / WORK)
    assert kept.returncode == 2, kept.stderr + kept.stdout
    assert f"{REFUSED} {WORK_DIR_OCCUPIED}" in kept.stderr
    assert not fresh_legs.exists()

    skipped = execute(plan, fresh_legs, new_work)
    assert skipped.returncode == 2, skipped.stderr + skipped.stdout
    assert f"{REFUSED} {BRANCH_EXISTS}" in skipped.stderr
    assert not fresh_legs.exists()
    assert printed_command(skipped.stderr, DELETE_COMMAND) == delete

    deleted = subprocess.run(delete, capture_output=True, text=True,
                             check=False)
    assert deleted.returncode == 0, deleted.stderr
    rerun = execute(plan, fresh_legs, new_work)

    assert rerun.returncode == 0, rerun.stderr + rerun.stdout
    assert VERIFIED in rerun.stdout
