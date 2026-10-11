# SPDX-License-Identifier: Apache-2.0
"""`execute` refuses every finding `check` reports, before a leg exists (#168).

Of `check`'s findings, `execute` used to refuse `plan-unresolved`,
`plan-stale` and the naming findings. A plan `check` rejects as uncovered,
with a bad leg, covered twice, with a duplicated path or with an empty entry
went on and made both legs. On main at 7f84ca4 it then ended one of three
ways:

- uncovered and bad leg, on a source with no submodule: the run VERIFIED and
  exited 0, with the uncovered paths, or the paths whose `leg:` is not one of
  the four words, left in the assembly root;
- covered twice, duplicated path and empty entry: the run died at `git rm`
  of the offending entry, after both legs were pushed;
- a source with a submodule, which is #168's own three cases: the
  verification failed as `adopt-lost`.

In every one the legs existed afterwards, so the corrected plan met them:
`leg-remote-exists` under `--local-remote-dir`, which has no `--force`. This
file builds a source with no submodule, so it holds the five classes
themselves; #168's submodule cases are refused by the same function under the
same two codes, `plan-uncovered` and `plan-bad-leg`.

NO NETWORK, NO GITHUB, AND NO `git filter-repo` except in the one end-to-end
test at the bottom. The rest load `adopt-project.py` through importlib and call
`cmd_execute` in this process. Its probe for `git filter-repo` is stubbed,
because every refusal under test is raised BEFORE the tool would be used. A
`cmd_execute` that stopped refusing would carry on and make the legs, then
either return an exit code or fail inside `git`; neither is the `Refusal` the
tests below wait for, so they fail on a machine that has the tool and on one
that has not.
"""

from __future__ import annotations

import importlib.util
import io
import shutil
import sys
from argparse import Namespace
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import (ADOPT, git, make_source_repo, resolve, run_script,
                      write_plan)

PROJECT = "Northwind"
UTF8 = "utf-8"
UNCOVERED = "plan-uncovered"
REMOTES = "remotes"
WORK = "work"
SPEC, CODE = "spec", "code"
ROLES = (SPEC, CODE)
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))

#: The entries the edits below work on: `src/` is one directory, two files, the
#: code leg; `specs/` is the specification, and `Spec` is not one of the four
#: words a `leg:` may be.
SRC_DIR = "src/"
SRC_ENTRY = f"  - path: {SRC_DIR}\n"
SPECS_ENTRY = "  - path: specs/\n    leg: spec\n"
SPECS_WRONG_CASE = "  - path: specs/\n    leg: Spec\n"

#: Where a test writes the plan it has edited, so that `check` can be asked
#: about it and `Plan.load` can read it.
EDITED = "edited-plan.yaml"

#: What `execute` needs and the rest of this file does not.
#: `test_adopt_e2e.py`, `test_adopt_spec_only.py` and
#: `test_adopt_submodules.py` each declare the same skip in their own file,
#: and so does this one.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: A repository with a specification and NO code, which `plan` can classify
#: without a single question: the case `--allow-empty-leg` exists for.
SPEC_ONLY_TREE = {
    "specs/001-render/spec.md": "# Render\n",
    "contracts/routing.yaml": "schema_version: 1\nkind: policy\n",
    "README.md": "# IRRS\n",
}

#: `make_source_repo`'s default later commits edit `src/app/main.py`, which
#: this repository has not got: its second commit touches the specification.
SPEC_ONLY_EDITS = (("specs/001-render/spec.md",
                    "# Render\n\nA second paragraph.\n",
                    "Extend the specification"),)


@dataclass(frozen=True)
class World:
    """A source and the plan for it, with every question ANSWERED."""

    source: Path
    plan: Path
    answered: str      # the plan `check` passes; each test edits a copy
    unanswered: str    # the same plan as `plan` wrote it
    tmp: Path


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_execute_refusals",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_filter_repo_probe(adopter, monkeypatch):
    """`cmd_execute` asks for `git filter-repo` first, and no test here gets
    as far as using it: the probe is answered, and the refusal that follows is
    what is under test."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)


@pytest.fixture
def world(tmp_path) -> World:
    """A source, and a plan for it with every question ANSWERED: the plan
    `check` passes. Each test edits its own copy of the text."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    unanswered = plan.read_text(encoding=UTF8)
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return World(source=source, plan=plan, unanswered=unanswered,
                 answered=plan.read_text(encoding=UTF8), tmp=tmp_path)


def without_entry(text: str, path: str) -> str:
    """`text` with the plan entry for `path` deleted, as a bad edit would."""
    lines = text.splitlines(keepends=True)
    start = lines.index(f"  - path: {path}\n")
    end = start + 1
    while lines[end].startswith("    "):
        end += 1
    return "".join(lines[:start] + lines[end:])


def execute_args(tmp_path: Path, plan: Path, *allowed: str,
                 yes: bool = True) -> Namespace:
    """What `main` hands `cmd_execute`: the plan, `--yes` unless `yes` is
    False, a local remote directory that does not exist yet and a work
    directory."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / REMOTES,
                     allow_empty_leg=list(allowed), yes=yes,
                     work_dir=tmp_path / WORK)


def refused_by(adopter, args):
    """The `Refusal` `cmd_execute` raises for `args`. Failing to raise one
    means it carried on, and then it returned an exit code instead."""
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    return caught.value


def source_branches(source: Path) -> list[str]:
    """The source's local branches: a split branch would be one more."""
    return git("branch", "--format=%(refname:short)",
               cwd=source).stdout.split()


def no_leg_was_created(tmp_path: Path) -> None:
    """What a refused run leaves undone: the directory the legs would have
    gone in was never made, and no leg was cloned for extraction. (`work/`
    itself is made first, whatever is refused, by `_work_root`; a source given
    as `org/repo` is cloned into it and a local path is read in place. Neither
    is a leg.)"""
    assert not (tmp_path / REMOTES).exists()
    for role in ROLES:
        assert not (tmp_path / WORK / f"{PROJECT}-{role}").exists()


def write_edited(world: World, text: str) -> Path:
    """`text` as a plan file beside the world's own, which it leaves alone."""
    path = world.tmp / EDITED
    path.write_text(text, encoding=UTF8)
    return path


def open_plan(adopter, world: World, text: str):
    """`(plan, source)` for `text`, the way `cmd_execute` opens them."""
    plan = adopter.Plan.load(write_edited(world, text))
    return plan, plan.open_source(str(world.source), world.tmp / "read")


def run_check(plan: Path):
    """`check --plan <plan>`, run as a person would."""
    return run_script(ADOPT, "check", "--plan", str(plan))


def check_findings(plan: Path) -> list[str]:
    """Every `FINDING` line `check` prints for `plan`, which must fail it."""
    result = run_check(plan)
    assert result.returncode == 1, result.stderr + result.stdout
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def spec_only_source(tmp_path: Path) -> Path:
    """The repository `--allow-empty-leg code` exists for."""
    return make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                            edits=SPEC_ONLY_EDITS)


#: The five finding classes `execute` did not refuse, each with a fragment its
#: finding must carry. `EDITS` below makes the plan that has each one.
CLASSES = {
    UNCOVERED: "src/app/main.py is in the source tree and in no plan",
    "plan-bad-leg": "specs/ declares leg 'Spec'",
    "plan-covered-twice": "src/app/main.py is covered by",
    "plan-duplicate-path": "src/ appears 2 times",
    "plan-empty-entry": "nonexistent/ covers nothing",
}

EDITS = {
    UNCOVERED: lambda text: without_entry(text, SRC_DIR),
    "plan-bad-leg": lambda text: text.replace(SPECS_ENTRY,
                                              SPECS_WRONG_CASE, 1),
    "plan-covered-twice": lambda text: text.replace(
        SRC_ENTRY, "  - path: src/app/\n    leg: code\n" + SRC_ENTRY, 1),
    "plan-duplicate-path": lambda text: text.replace(
        SRC_ENTRY, SRC_ENTRY + "    leg: code\n" + SRC_ENTRY, 1),
    "plan-empty-entry": lambda text: text.replace(
        SRC_ENTRY, "  - path: nonexistent/\n    leg: code\n" + SRC_ENTRY, 1),
}


#: One test per finding class, the class's code as the test's `code`.
ONE_PER_CLASS = pytest.mark.parametrize("code", sorted(CLASSES))


def broken_text(world: World, code: str) -> str:
    text = EDITS[code](world.answered)
    assert text != world.answered, f"the {code} edit changed nothing"
    return text


# --- the function itself ---------------------------------------------------

def test_a_plan_check_passes_raises_no_refusal(adopter, world):
    """THE CONTRACT THAT MUST NOT BREAK: what `check` passes, `execute`
    runs."""
    checked = run_check(world.plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    plan, source = open_plan(adopter, world, world.answered)
    assert adopter._refuse_what_check_finds(plan, source) is None


@ONE_PER_CLASS
def test_each_class_check_reports_is_refused_under_its_own_code(adopter, world,
                                                                code):
    plan, source = open_plan(adopter, world, broken_text(world, code))
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    refusal = caught.value
    assert refusal.code == code
    assert CLASSES[code] in refusal.detail
    assert f"FINDING {code}:" in refusal.detail


@ONE_PER_CLASS
def test_the_refusal_carries_the_findings_check_prints(adopter, world, code):
    """Not a reading of `check` that happens to agree: every line `check`
    prints for the plan is in the refusal, word for word."""
    text = broken_text(world, code)
    printed = check_findings(write_edited(world, text))
    assert printed, "check must reject the plan this test is about"
    plan, source = open_plan(adopter, world, text)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    for finding in printed:
        assert finding in caught.value.detail
    assert f"{len(printed)} finding(s) in" in caught.value.detail


def test_the_refusal_names_the_exit(adopter, world):
    plan, source = open_plan(adopter, world, broken_text(world, UNCOVERED))
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    said = str(caught.value)
    assert said.startswith(f"REFUSED {UNCOVERED}: ")
    assert "no leg repository was created and nothing was pushed" in said
    assert "run `check` until it prints `plan ok`" in said
    assert "leg-remote-exists" in said


def test_the_code_is_the_first_findings_own(adopter, world):
    """Two classes at once: the refusal wears the first one `check` lists and
    still names the other, so nothing a plan is wrong about is left unsaid."""
    wrong_case = world.answered.replace(SPECS_ENTRY, SPECS_WRONG_CASE, 1)
    plan, source = open_plan(adopter, world,
                             without_entry(wrong_case, SRC_DIR))
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    assert caught.value.code == UNCOVERED
    assert "FINDING plan-bad-leg:" in caught.value.detail


def test_a_long_list_of_findings_is_capped_with_a_count(adopter, world):
    text = world.answered
    for path in ("contracts/", "docker/", "docs/", "openspec/", "pkg_core/",
                 "specs/", SRC_DIR, "tests/"):
        text = without_entry(text, path)
    total = len(check_findings(write_edited(world, text)))
    assert total > adopter.REFUSED_FINDINGS_SHOWN
    plan, source = open_plan(adopter, world, text)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    shown = [line for line in caught.value.detail.splitlines()
             if line.startswith("  FINDING ")]
    assert len(shown) == adopter.REFUSED_FINDINGS_SHOWN
    assert caught.value.detail.splitlines()[-1] == (
        f"  and {total - adopter.REFUSED_FINDINGS_SHOWN} more")
    assert f"{total} finding(s) in" in caught.value.detail


def test_a_leg_with_no_path_is_not_a_finding(adopter, tmp_path):
    """`--allow-empty-leg` seeding is unaffected: a leg no entry assigns a path
    to is a WARNING in `check` and a consent in `execute`, never a finding."""
    repo = spec_only_source(tmp_path)
    plan_path = tmp_path / "plan.yaml"
    written = write_plan(repo, plan_path, project=PROJECT,
                         extra=("--allow-empty-leg", CODE))
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_check(plan_path)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "WARNING the code leg will be SEEDED" in checked.stdout
    plan = adopter.Plan.load(plan_path)
    opened = plan.open_source(str(repo), tmp_path / "read")
    assert adopter._refuse_what_check_finds(plan, opened) is None


# --- the wiring in `cmd_execute`, and what it leaves undone -----------------

@ONE_PER_CLASS
def test_execute_refuses_each_class_and_creates_no_leg(adopter, world, code):
    world.plan.write_text(broken_text(world, code), encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == code
    no_leg_was_created(world.tmp)
    assert source_branches(world.source) == ["main"], (
        "nothing was pushed to the source either")


@ONE_PER_CLASS
def test_the_refusal_comes_before_anyone_is_asked_to_say_yes(
        adopter, world, monkeypatch, code):
    """WITHOUT `--yes`, on a stream that is not a terminal, the refusal is
    still the finding's own. `_confirm` would answer `adopt-unconfirmed` (or
    put a person through "Type yes to proceed" for a plan that is then
    refused), so a call moved past it fails here."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    world.plan.write_text(broken_text(world, code), encoding=UTF8)
    refusal = refused_by(adopter,
                         execute_args(world.tmp, world.plan, yes=False))
    assert refusal.code == code
    no_leg_was_created(world.tmp)


def test_a_leg_with_no_path_is_still_refused_without_consent(adopter,
                                                             tmp_path):
    """The seeding refusal is where it was: this one passes the plan on to
    it."""
    repo = spec_only_source(tmp_path)
    plan_path = tmp_path / "plan.yaml"
    assert write_plan(repo, plan_path, project=PROJECT).returncode == 0
    refusal = refused_by(adopter, execute_args(tmp_path, plan_path))
    assert refusal.code == "adopt-empty-leg-unconsented"
    no_leg_was_created(tmp_path)


# --- the order of the refusals ---------------------------------------------

def test_an_unresolved_question_is_still_reported_as_unresolved(adopter,
                                                                world):
    """THE TWO ARE NOT REPORTED TWICE. This plan is unanswered AND uncovered;
    `_refuse_an_unrunnable_plan` speaks first, in its own words, and the
    coverage finding is what `check` will say once the questions are
    answered."""
    world.plan.write_text(without_entry(world.unanswered, SRC_DIR),
                          encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == "plan-unresolved"
    assert "still have `leg: null`" in refusal.detail
    assert "never an implicit `root`" in refusal.remediation
    no_leg_was_created(world.tmp)


def test_a_stale_plan_is_still_reported_as_stale(adopter, world):
    """A plan written against an older commit is judged `plan-stale`, whatever
    the tree that moved has gained: `late/` is covered by NO entry, and the
    plan did not omit it, it never saw it."""
    (world.source / "late").mkdir()
    (world.source / "late" / "work.txt").write_text("later\n")
    git("add", "-A", cwd=world.source)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "later work", cwd=world.source)
    world.plan.write_text(world.answered, encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == "plan-stale"
    no_leg_was_created(world.tmp)


def test_a_path_that_is_a_git_option_is_still_unsafe_not_uncovered(adopter,
                                                                    world):
    """THE PLAN IS UNTRUSTED INPUT and its paths are judged first. This plan
    is also uncovered -- `specs/` has no entry -- and would be refused as
    that, losing the reason it is dangerous, if the coverage finding came
    before them. Since #196 an entry's path is `check`'s own finding,
    `plan-unsafe-path`, listed first, where it used to be `_leg_paths`'
    `unsafe-value`; the uncovered files are named beside it.
    (`test_adopt_e2e.py` has the same case behind `git filter-repo`; this one
    runs everywhere.)"""
    world.plan.write_text(world.answered.replace(
        "  - path: specs/\n", "  - path: --output=never-written\n", 1),
        encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == "plan-unsafe-path"
    assert "`--output=never-written` has leg: spec" in refusal.detail
    assert "FINDING plan-uncovered: specs/" in refusal.detail
    no_leg_was_created(world.tmp)


# --- a plan that is not UTF-8 (#192) ----------------------------------------

#: The byte `0xff` is in no UTF-8 text, so wherever it lands the file cannot be
#: decoded. Three places, each a way a hand edit or a foreign writer puts one
#: there: inside a value (the leg path of the issue's own probe), in a comment
#: the parser would skip, and last in the file with no newline after it. The
#: whole file is decoded before any of it is parsed, so all three are the same
#: refusal.
BAD_BYTE = b"\xff"
NOT_UTF8_PLANS = {
    "in-a-value": lambda data: data.replace(b"spec_path: spec",
                                            b"spec_path: sp\xffec", 1),
    "in-a-comment": lambda data: b"# caf" + BAD_BYTE + b"\n" + data,
    "at-the-end": lambda data: data + b"# end" + BAD_BYTE,
}
ONE_PER_PLACE = pytest.mark.parametrize("place", sorted(NOT_UTF8_PLANS))


def not_utf8_plan(world: World, place: str) -> tuple[Path, int]:
    """`(path, offset)`: the world's answered plan with one `0xff` put in at
    `place`, and the offset the refusal must name for it."""
    data = world.answered.encode(UTF8)
    broken = NOT_UTF8_PLANS[place](data)
    assert broken != data, f"the {place} edit changed nothing"
    assert broken.count(BAD_BYTE) == 1
    path = world.tmp / EDITED
    path.write_bytes(broken)
    return path, broken.index(BAD_BYTE)


def assert_refused_as_unreadable(result, path: Path, offset: int) -> None:
    """The refusal a missing file already gets: a `REFUSED` line that names the
    file and the byte, a remediation, exit 2, and no traceback."""
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"REFUSED yaml-unreadable: {path}: " in result.stderr
    assert f"not UTF-8 at byte {offset}" in result.stderr
    assert "Remediation: " in result.stderr
    assert "must be UTF-8" in result.stderr
    for output in (result.stderr, result.stdout):
        assert "Traceback" not in output
        assert "UnicodeDecodeError" not in output


@ONE_PER_PLACE
def test_check_refuses_a_plan_that_is_not_utf8(world, place):
    """On main at f25d805 this was exit 1 and a `UnicodeDecodeError`
    traceback, with no `FINDING` or `REFUSED` line to read."""
    path, offset = not_utf8_plan(world, place)
    assert_refused_as_unreadable(run_check(path), path, offset)


@ONE_PER_PLACE
def test_execute_refuses_a_plan_that_is_not_utf8_and_makes_nothing(world,
                                                                    place):
    """Refused where the plan is first read, so before the work directory, the
    local remotes or a branch of the source exist. `--yes` is passed: nobody is
    asked, and nothing is made."""
    path, offset = not_utf8_plan(world, place)
    remotes, work = world.tmp / REMOTES, world.tmp / WORK
    result = run_script(ADOPT, "execute", "--plan", str(path), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert_refused_as_unreadable(result, path, offset)
    assert not remotes.exists(), "not even the directory the legs go in"
    assert not work.exists(), "and nothing was cloned or read into a work dir"
    no_leg_was_created(world.tmp)
    assert source_branches(world.source) == ["main"]


def test_execute_raises_the_refusal_not_the_decode_error(adopter, world):
    """In process, the exception `main` turns into exit 2: a `Refusal`, which
    is what the tests above wait for through the process boundary."""
    path, offset = not_utf8_plan(world, "in-a-value")
    refusal = refused_by(adopter, execute_args(world.tmp, path))
    assert refusal.code == "yaml-unreadable"
    assert f"not UTF-8 at byte {offset}" in refusal.detail
    no_leg_was_created(world.tmp)


# --- end to end ------------------------------------------------------------

@needs_filter_repo
def test_an_uncovered_plan_creates_no_leg_and_the_corrected_plan_then_runs(
        world):
    """THE HARM, as a person met it: no leg is created, so the corrected plan
    does not meet `leg-remote-exists` and the adoption goes through. The
    refused run has no `--yes` and stdin is closed, so it also shows the
    refusal is the finding's and not `adopt-unconfirmed`."""
    remotes, work = world.tmp / REMOTES, world.tmp / WORK
    flags = ("--plan", str(world.plan), "--local-remote-dir", str(remotes),
             "--work-dir", str(work))
    world.plan.write_text(without_entry(world.answered, SRC_DIR),
                          encoding=UTF8)
    refused = run_script(ADOPT, "execute", *flags)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {UNCOVERED}" in refused.stderr
    assert "src/app/main.py" in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists(), "not even the directory the legs go in"
    for role in ROLES:
        assert not (work / f"{PROJECT}-{role}").exists()
    assert source_branches(world.source) == ["main"]

    world.plan.write_text(world.answered, encoding=UTF8)
    corrected = run_script(ADOPT, "execute", "--yes", *flags)
    assert corrected.returncode == 0, corrected.stderr + corrected.stdout
    assert "adoption verified" in corrected.stdout
    for role in ROLES:
        assert (remotes / f"{PROJECT}-{role}.git").is_dir()
