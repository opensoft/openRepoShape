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

NO NETWORK, NO GITHUB, AND NO `git filter-repo` except in the end-to-end tests
at the bottom. The rest load `adopt-project.py` through importlib and call
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
import re
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
#: finding must carry, every path in it `_spelled` (#212). `EDITS` below makes
#: the plan that has each one.
CLASSES = {
    UNCOVERED: "`src/app/main.py` is in the source tree and in no plan",
    "plan-bad-leg": "`specs/` declares leg 'Spec'",
    "plan-covered-twice": "`src/app/main.py` is covered by",
    "plan-duplicate-path": "`src/` appears 2 times",
    "plan-empty-entry": "`nonexistent/` covers nothing",
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
    assert "FINDING plan-uncovered: `specs/" in refusal.detail
    no_leg_was_created(world.tmp)


# --- plan values `execute` read late ---------------------------------------

#: `follow_ups:` and every item under it, as `plan` writes the block; the
#: edits below replace the whole of it.
FOLLOW_UPS_BLOCK = re.compile(r"^follow_ups:\n(?:  - .*\n)*", re.M)
BAD_FOLLOW_UPS_CODE = "plan-bad-follow-ups"

#: What a hand edit can leave `follow_ups:` holding that is not a list of
#: text, by test id: the block it is written as, and what the finding must say
#: of it (#293). The scalars ended `check` in `TypeError: ... is not iterable`
#: with no FINDING, and on main ended `execute` the same way after both legs
#: were pushed; `abc` went into the split commit's message as three
#: follow-ups, `a`, `b` and `c`, and an item `true` as `True`.
BAD_FOLLOW_UPS = {
    "int": ("follow_ups: 5\n", "`follow_ups:` is the number 5, not a list"),
    "true": ("follow_ups: true\n",
             "`follow_ups:` is the boolean true, not a list"),
    "false": ("follow_ups: false\n",
              "`follow_ups:` is the boolean false, not a list"),
    "float": ("follow_ups: 1.5\n",
              "`follow_ups:` is the number 1.5, not a list"),
    "text": ("follow_ups: abc\n",
             "`follow_ups:` is the text 'abc', not a list"),
    "mapping": ("follow_ups: {a: 1}\n",
                "`follow_ups:` is a mapping of 1 key(s), not a list"),
    "item-int": ("follow_ups:\n  - 5\n",
                 "item 1 of `follow_ups:` is the number 5, not text"),
    "item-true": ('follow_ups:\n  - "keep"\n  - true\n',
                  "item 2 of `follow_ups:` is the boolean true, not text"),
    "item-null": ("follow_ups:\n  - null\n",
                  "item 1 of `follow_ups:` is null, not text"),
}

#: What `check` and `execute` still take, by test id, and the follow-ups each
#: reads: an empty list, a bare key, and a list of text as `plan` writes it.
GOOD_FOLLOW_UPS = {
    "empty-list": ("follow_ups: []\n", []),
    "bare-key": ("follow_ups:\n", []),
    "text-items": ('follow_ups:\n  - "Re-point CI at code/"\n'
                   '  - "merge shape/README.md"\n',
                   ["Re-point CI at code/", "merge shape/README.md"]),
}


def with_follow_ups(text: str, block: str) -> str:
    """`text` with its `follow_ups:` block replaced by `block`."""
    edited, done = FOLLOW_UPS_BLOCK.subn(lambda _: block, text, count=1)
    assert done == 1, "the plan has no `follow_ups:` block to edit"
    return edited


def assert_no_traceback(result) -> None:
    for output in (result.stdout, result.stderr):
        assert "Traceback" not in output, output


#: What `execute`'s refusal says of a plan `check` rejects, made before any
#: leg exists, and the first words of the notice #445 prints after a failure
#: once one does.
NO_LEG_MADE = "no leg repository was created and nothing was pushed"
LATE_NOTICE = "NOTHING has been rolled back"


def assert_refused_before_any_leg(result) -> None:
    """The refusal is `_refuse_what_check_finds`', made before any leg
    exists: it says no leg was made, and no notice of what the run left
    follows it, as one does a failure once a leg exists (#445)."""
    assert NO_LEG_MADE in result.stderr, result.stderr
    assert LATE_NOTICE not in result.stderr, result.stderr


def findings_of(result) -> list[str]:
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


@pytest.mark.parametrize("edit", sorted(BAD_FOLLOW_UPS))
def test_check_finds_a_follow_ups_that_is_not_a_list_of_text(world, edit):
    """#293: a FINDING that names the key and what it holds, exit 1, and no
    traceback. At #270's head `check` read the value in `_plan_values` and
    ended in `TypeError: 'int' object is not iterable`; on main it did so in
    `_print_what_will_happen`. `abc` printed three follow-ups, `a`, `b` and
    `c`, which the summary no longer reads."""
    block, said = BAD_FOLLOW_UPS[edit]
    result = run_check(write_edited(world,
                                    with_follow_ups(world.answered, block)))
    assert result.returncode == 1, result.stderr + result.stdout
    assert_no_traceback(result)
    found = findings_of(result)
    assert len(found) == 1, found
    assert found[0].startswith(f"FINDING {BAD_FOLLOW_UPS_CODE}: {said}: "), \
        found
    assert "Remediation: write `follow_ups:` in the plan file" in \
        result.stderr
    shown = [line for line in result.stdout.splitlines()
             if line.startswith("  follow-up: ")]
    assert shown == (["  follow-up: keep"] if '"keep"' in block else []), \
        shown


@pytest.mark.parametrize("edit", sorted(BAD_FOLLOW_UPS))
def test_execute_refuses_a_follow_ups_that_is_not_a_list_of_text_and_creates_no_leg(  # noqa: E501
        adopter, world, edit):
    """Through `_refuse_what_check_finds`, before any leg exists, under the
    finding's own code. At #270's head this was the same `TypeError` raised
    from the same list; on main it was raised in `_commit_the_split`, after
    both legs were pushed."""
    block, said = BAD_FOLLOW_UPS[edit]
    world.plan.write_text(with_follow_ups(world.answered, block),
                          encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == BAD_FOLLOW_UPS_CODE
    assert f"FINDING {BAD_FOLLOW_UPS_CODE}: {said}" in refusal.detail
    assert "write `follow_ups:` in the plan file" in refusal.remediation
    no_leg_was_created(world.tmp)
    assert source_branches(world.source) == ["main"]


@pytest.mark.parametrize("edit", sorted(GOOD_FOLLOW_UPS))
def test_a_list_of_text_an_empty_list_and_a_bare_key_still_pass(adopter,
                                                                world, edit):
    """The controls: what `plan` writes, and the two ways of writing none,
    pass `check` and `execute`'s refusal, and the follow-ups read are the
    items as written."""
    block, items = GOOD_FOLLOW_UPS[edit]
    text = with_follow_ups(world.answered, block)
    checked = run_check(write_edited(world, text))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    for item in items:
        assert f"  follow-up: {item}" in checked.stdout
    plan, source = open_plan(adopter, world, text)
    assert adopter._refuse_what_check_finds(plan, source) is None


DATE_CODE = "election-date-malformed"
DATE_FLAG = "--elected-on"

#: An `elected_on:` that `election_date` refuses on every Python, by test id:
#: as the plan holds it, as the reader reads it, and whether the plan keeps
#: its `reference:` (#294). Without one, `execute` made both legs and only
#: then refused, naming `--elected-on`; with one it never read the date and
#: wrote the word into the manifest. `empty-text` is falsy and not null: only
#: `elected_on:` ABSENT or null is "no date" (`execute` fills in today's), so
#: `""` is a date `election_date` cannot read and is refused like any other.
BAD_DATES = {
    "word": ("someday", "someday", False),
    "notadate": ("notadate", "notadate", False),
    "unpadded": ('"2026-9-2"', "2026-9-2", False),
    "not-a-day": ('"2026-02-30"', "2026-02-30", False),
    "empty-text": ('""', "", False),
    "word-reference-kept": ("someday", "someday", True),
}
ONE_PER_BAD_DATE = pytest.mark.parametrize("edit", sorted(BAD_DATES))


def with_elected_on(text: str, value: str, reference: bool) -> str:
    """`text` with `elected_on:` set to `value` by hand, and its `reference:`
    line deleted unless `reference`."""
    if not reference:
        text, done = re.subn(r"^reference:.*\n", "", text, count=1,
                             flags=re.M)
        assert done == 1, "the plan has no `reference:` line to delete"
    edited, done = re.subn(r"^elected_on: .*$",
                           lambda _: f"elected_on: {value}", text, count=1,
                           flags=re.M)
    assert done == 1, "the plan has no `elected_on:` line to edit"
    return edited


@ONE_PER_BAD_DATE
def test_check_finds_an_elected_on_it_cannot_read_under_the_plans_key(world,
                                                                      edit):
    """#294: a FINDING `election-date-malformed` that names the plan's
    `elected_on:` and no flag, whether or not the plan has a `reference:`.
    `check` used to say `plan ok`: it never read the date."""
    value, read, reference = BAD_DATES[edit]
    result = run_check(write_edited(
        world, with_elected_on(world.answered, value, reference)))
    assert result.returncode == 1, result.stderr + result.stdout
    assert_no_traceback(result)
    found = findings_of(result)
    assert len(found) == 1, found
    assert found[0].startswith(
        f"FINDING {DATE_CODE}: the plan's `elected_on:` is the text "
        f"{read!r}, which is not a day written YYYY-MM-DD"), found
    assert ("the plan naming no `reference:`" in found[0]) is not reference
    # the claim is about what `execute` WRITES, not "the one form it reads":
    # on Python 3.11+ `election_date` reads `20261011` too, until #314 lands
    assert ", the form `execute` writes into the project's `project.yaml`" in \
        found[0], found
    assert "the one form" not in found[0], found
    assert "Remediation: edit `elected_on:` in the plan file" in \
        result.stderr
    assert DATE_FLAG not in result.stderr + result.stdout


@pytest.mark.parametrize("value,read_as", [
    ("false", "the boolean false"), ("0", "the number 0"),
    ("[]", "a list of 0 item(s)"), ("{}", "a mapping of 0 key(s)")])
def test_check_finds_a_falsy_elected_on_that_is_not_null(world, value,
                                                         read_as):
    """#294: only an `elected_on:` that is absent or null is "no date". Any
    other falsy value is a date `election_date` cannot read, so it is a
    FINDING that says what the plan holds; `if not elected_on:` in place of
    `is None` would skip it and `check` would say `plan ok`. It is not a
    `BAD_DATES` row because that test says "the text"."""
    result = run_check(write_edited(
        world, with_elected_on(world.answered, value, False)))
    assert result.returncode == 1, result.stderr + result.stdout
    assert_no_traceback(result)
    found = findings_of(result)
    assert len(found) == 1, found
    assert found[0].startswith(
        f"FINDING {DATE_CODE}: the plan's `elected_on:` is {read_as}, which "
        "is not a day written YYYY-MM-DD"), found


@ONE_PER_BAD_DATE
def test_execute_refuses_an_elected_on_it_cannot_read_before_any_leg(
        adopter, world, edit):
    """The same finding, refused through `_refuse_what_check_finds` before
    `_create_leg_remotes`. With no `reference:`, `execute` used to create
    both legs and then refuse from `default_reference`, in words that named
    `--elected-on`; with one, it went on and wrote the word into the
    manifest."""
    value, read, reference = BAD_DATES[edit]
    world.plan.write_text(with_elected_on(world.answered, value, reference),
                          encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == DATE_CODE
    no_leg_was_created(world.tmp)
    assert source_branches(world.source) == ["main"]
    assert f"the plan's `elected_on:` is the text {read!r}" in refusal.detail
    assert "edit `elected_on:` in the plan file" in refusal.remediation
    assert DATE_FLAG not in str(refusal)


#: An `org:` or `id:` the plan refuses in its own words, by test id: the line
#: `plan` writes, the hand edit, and the code `check` and `execute` both
#: refuse it under. Beside an `elected_on:` that is a finding, the date's
#: guard in `_manifest_values` used to return before either was asked, so
#: the two commands named different first problems.
REFUSED_BESIDE_A_BAD_DATE = {
    "org-unsafe": ("org: testorg", 'org: "-evil"', "unsafe-value"),
    "id-bad": ("id: northwind", 'id: "North Wind"', "plan-bad-id"),
}


@pytest.mark.parametrize("reference", [True, False],
                         ids=["reference-kept", "no-reference"])
@pytest.mark.parametrize("edit", sorted(REFUSED_BESIDE_A_BAD_DATE))
def test_a_bad_date_does_not_change_what_check_and_execute_refuse_first(
        adopter, world, edit, reference):
    """A plan with `elected_on: someday` AND an `org:` or `id:` it refuses:
    `check` and `execute` refuse it under the same code, the organisation's
    or the id's, as they do with no date guard, and no leg is created. With
    both asked after the guard, `check` listed only the date (exit 1) where
    `execute` refused `unsafe-value`, and `check` refused `plan-bad-id` where
    `execute` refused the date."""
    line, edited, code = REFUSED_BESIDE_A_BAD_DATE[edit]
    text = with_elected_on(world.answered, "someday", reference)
    assert line in text, f"`plan` wrote no `{line}` line"
    plan = write_edited(world, text.replace(line, edited, 1))

    checked = run_check(plan)
    assert checked.returncode == 2, checked.stderr + checked.stdout
    assert_no_traceback(checked)
    first = next((said for said in checked.stderr.splitlines()
                  if said.startswith("REFUSED ")), "")
    assert first.startswith(f"REFUSED {code}: "), checked.stderr

    refusal = refused_by(adopter, execute_args(world.tmp, plan))
    assert refusal.code == code
    no_leg_was_created(world.tmp)
    assert source_branches(world.source) == ["main"]


@pytest.mark.parametrize("value,reference", [
    ('"2026-09-02"', False), ('"2026-06-01"', False), ('"2026-09-02"', True),
    ("null", False)])
def test_an_elected_on_election_date_reads_still_passes(adopter, world, value,
                                                        reference):
    """The controls: a date, with or without the `reference:` it chooses, and
    no date at all, which `execute` fills with today's."""
    text = with_elected_on(world.answered, value, reference)
    checked = run_check(write_edited(world, text))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    plan, source = open_plan(adopter, world, text)
    assert adopter._refuse_what_check_finds(plan, source) is None


@pytest.mark.parametrize("value", ["2026-W41-6", "20261011", "2026-09-02",
                                   "someday"])
def test_check_asks_election_date_itself_of_the_plans_date(adopter, world,
                                                           value):
    """ONE QUESTION, `plan`'s. `check` asks the plan's `elected_on:` what
    `plan` asks `--elected-on`, `election_date` on this interpreter, and
    nothing of its own: `2026-W41-6` and `20261011` are dates to
    `date.fromisoformat` from Python 3.11 and not to the project's own
    validator, which is #261's to rule on. Whatever `election_date` answers,
    `check` answers the same, so `plan`, `check` and `execute` cannot
    disagree about one value."""
    try:
        adopter.election_date(value)
        refused = False
    except adopter.Refusal:
        refused = True
    result = run_check(write_edited(
        world, with_elected_on(world.answered, f'"{value}"', False)))
    assert result.returncode == (1 if refused else 0), \
        result.stderr + result.stdout
    assert (f"FINDING {DATE_CODE}:" in result.stderr) is refused


def test_a_tighter_election_date_is_asked_with_no_edit(adopter, world,
                                                       monkeypatch):
    """`election_date` held to `YYYY-MM-DD` on every Python, as #261 asks of
    it, stood in for here: `check`'s list follows it, and `execute` refuses
    `2026-W41-6` before any leg. The stand-in's own words name
    `--elected-on`; the refusal says the plan's key and not them."""
    real = adopter.election_date

    def held_to_the_form(elected_on):
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(elected_on)):
            raise adopter.Refusal(
                DATE_CODE, f"{DATE_FLAG} {elected_on!r} is not YYYY-MM-DD")
        return real(elected_on)

    monkeypatch.setattr(adopter, "election_date", held_to_the_form)
    world.plan.write_text(
        with_elected_on(world.answered, '"2026-W41-6"', False), encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == DATE_CODE
    assert "the plan's `elected_on:` is the text '2026-W41-6'" in \
        refusal.detail
    assert DATE_FLAG not in str(refusal)
    no_leg_was_created(world.tmp)


def test_another_refusal_from_election_date_is_not_a_date_finding(
        adopter, world, monkeypatch):
    """Only `election-date-malformed` is a finding about the date. Anything
    else `election_date` raises -- a rule it could not ask, as when the
    validator it may consult is missing -- is raised as it is, and a date it
    never judged is not reported as malformed."""
    def cannot_ask(elected_on):
        raise adopter.Refusal("rule-unusable", "the rule could not be asked")

    monkeypatch.setattr(adopter, "election_date", cannot_ask)
    plan, source = open_plan(adopter, world, world.answered)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    assert caught.value.code == "rule-unusable"


def test_both_findings_are_listed_and_the_code_is_the_first(adopter, world):
    """Both keys wrong at once: one list, the date first, as `plan` writes the
    two keys, and each remediation once."""
    text = with_follow_ups(with_elected_on(world.answered, "someday", False),
                           "follow_ups: 5\n")
    printed = check_findings(write_edited(world, text))
    assert [line.split(":", 1)[0] for line in printed] == [
        f"FINDING {DATE_CODE}", f"FINDING {BAD_FOLLOW_UPS_CODE}"]
    plan, source = open_plan(adopter, world, text)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    assert caught.value.code == DATE_CODE
    for finding in printed:
        assert finding in caught.value.detail
    assert caught.value.remediation.count("Remediation: edit `elected_on:`") \
        == 1
    assert caught.value.remediation.count(
        "Remediation: write `follow_ups:`") == 1


# --- the keys a plan is opened by (#386) -------------------------------------

#: The finding codes, one per key, as #293's is `plan-bad-follow-ups`.
BAD_SOURCE, BAD_LEGS = "plan-bad-source", "plan-bad-legs"
BAD_ALLOW, BAD_PATHS = "plan-bad-allow-empty-legs", "plan-bad-paths"
#: `pins:` is #273's: a `pins:` that is no list is `_read_pins`' own
#: `plan-pin-malformed`, asked here first, and each entry of a list is
#: `plan-pin-unrecorded` or `plan-pin-malformed` beside the entries.
PIN_MALFORMED, PIN_UNRECORDED = "plan-pin-malformed", "plan-pin-unrecorded"

#: What a hand edit can leave a key `Plan` reads holding, by test id: the key,
#: the block written in place of its own, the code, and what the finding must
#: begin with (#386). On #356's head (5a5011d) the scalars ended `check` and
#: `execute` in `TypeError: ... is not iterable` (`pins:`, `paths:`,
#: `allow_empty_legs:`) or `AttributeError: ... has no attribute 'get'`
#: (`legs:`, `source:`), exit 1; `pins: openGlass` passed `check` and adopted
#: with eight one-letter pins, and `allow_empty_legs: code` consented for four
#: legs, `c`, `o`, `d` and `e`. Since #273 a pin is a mapping, so one pin
#: written as the mapping itself, with no list around it, is a row too.
BAD_KEYS = {
    "pins-int": ("pins", "pins: 5\n", PIN_MALFORMED,
                 "`pins:` is 5, not a list of pins"),
    "pins-true": ("pins", "pins: true\n", PIN_MALFORMED,
                  "`pins:` is True, not a list of pins"),
    "pins-text": ("pins", "pins: openGlass\n", PIN_MALFORMED,
                  "`pins:` is 'openGlass', not a list of pins"),
    "pins-mapping": ("pins", "pins: {product: openGlass}\n", PIN_MALFORMED,
                     "`pins:` is {'product': 'openGlass'}, not a list of "
                     "pins"),
    "allow-int": ("allow_empty_legs", "allow_empty_legs: 5\n", BAD_ALLOW,
                  "`allow_empty_legs:` is the number 5, not a list"),
    "allow-true": ("allow_empty_legs", "allow_empty_legs: true\n", BAD_ALLOW,
                   "`allow_empty_legs:` is the boolean true, not a list"),
    "allow-text": ("allow_empty_legs", "allow_empty_legs: code\n", BAD_ALLOW,
                   "`allow_empty_legs:` is the text 'code', not a list"),
    "allow-item-case": ("allow_empty_legs", "allow_empty_legs: [Code]\n",
                        BAD_ALLOW, "item 1 of `allow_empty_legs:` is the text "
                        "'Code', not a leg `execute` can seed"),
    "allow-item-int": ("allow_empty_legs", "allow_empty_legs: [code, 5]\n",
                       BAD_ALLOW, "item 2 of `allow_empty_legs:` is the "
                       "number 5, not a leg `execute` can seed"),
    "paths-int": ("paths", "paths: 5\n", BAD_PATHS,
                  "`paths:` is the number 5, not a list"),
    "paths-true": ("paths", "paths: true\n", BAD_PATHS,
                   "`paths:` is the boolean true, not a list"),
    "paths-text": ("paths", "paths: src/\n", BAD_PATHS,
                   "`paths:` is the text 'src/', not a list"),
    "legs-int": ("legs", "legs: 5\n", BAD_LEGS,
                 "`legs:` is the number 5, not a mapping"),
    "legs-list": ("legs", "legs: [spec, code]\n", BAD_LEGS,
                  "`legs:` is a list of 2 item(s), not a mapping"),
    "source-int": ("source", "source: 5\n", BAD_SOURCE,
                   "`source:` is the number 5, not a mapping"),
    "source-text": ("source", "source: Thing\n", BAD_SOURCE,
                    "`source:` is the text 'Thing', not a mapping"),
}
ONE_PER_BAD_KEY = pytest.mark.parametrize("edit", sorted(BAD_KEYS))

#: The line each key's remediation begins with, said once after its findings.
KEY_REMEDIATION = {key: f"Remediation: write `{key}:` in the plan file"
                   for key in ("source", "legs", "allow_empty_legs")}
KEY_REMEDIATION["paths"] = ("Remediation: `paths:` is the list of entries "
                            "`plan` wrote")
KEY_REMEDIATION["pins"] = ("Remediation: `pins:` is the list of pins `plan` "
                           "wrote, one mapping per pin")

#: What `execute`'s refusal of them says first: #445's words for a refusal
#: before any leg exists (`NO_LEG_MADE`), and that it came earlier still.
NOTHING_MADE = (f"{NO_LEG_MADE}: the plan was refused before the work "
                "directory was made or the source was opened")


def with_key(text: str, key: str, block: str) -> str:
    """`text` with the top-level `key:` and the block under it replaced by
    `block`, or deleted when `block` is empty, as a hand edit would."""
    edited, done = re.subn(rf"^{key}:.*\n(?:[ \t]+.*\n)*", lambda _: block,
                           text, count=1, flags=re.M)
    assert done == 1, f"the plan has no `{key}:` to edit"
    return edited


def bad_key_text(world: World, edit: str) -> str:
    key, block, _, _ = BAD_KEYS[edit]
    return with_key(world.answered, key, block)


@ONE_PER_BAD_KEY
def test_check_finds_a_key_plan_reads_that_is_not_what_plan_writes(world,
                                                                   edit):
    """#386 (a): a FINDING that names the key and what the reader gave it,
    exit 1, no traceback and no `plan ok`; and nothing else is reported,
    because every other finding is read from these keys. On 5a5011d each was
    a traceback naming Python's error, or `plan ok`."""
    key, _, code, said = BAD_KEYS[edit]
    result = run_check(write_edited(world, bad_key_text(world, edit)))
    assert result.returncode == 1, result.stderr + result.stdout
    assert_no_traceback(result)
    assert "plan ok" not in result.stdout
    found = findings_of(result)
    assert len(found) == 1, found
    assert found[0].startswith(f"FINDING {code}: {said}"), found
    assert result.stderr.count(KEY_REMEDIATION[key]) == 1, result.stderr
    assert "1 finding(s) in" in result.stderr


@ONE_PER_BAD_KEY
def test_execute_refuses_a_key_plan_reads_before_anything_is_made(
        adopter, world, edit):
    """#386 (c): the same finding, refused under its own code before the
    work directory, the source's reading or a leg; on 5a5011d each ended in
    the traceback `check` printed, or, for the text rows of `pins:` and the
    text and item rows of `allow_empty_legs:`, adopted."""
    key, _, code, said = BAD_KEYS[edit]
    world.plan.write_text(bad_key_text(world, edit), encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == code
    assert f"  FINDING {code}: {said}" in refusal.detail
    assert refusal.detail.startswith(f"1 finding(s) in {world.plan}, as "
                                     "`check` prints them:")
    assert NOTHING_MADE in refusal.remediation
    assert refusal.remediation.count(KEY_REMEDIATION[key]) == 1
    no_leg_was_created(world.tmp)
    assert not (world.tmp / WORK).exists(), "not even the work directory"
    assert source_branches(world.source) == ["main"]


def test_every_key_that_is_wrong_is_named_in_one_run(adopter, world):
    """#386 (b): three of the five keys wrong at once, and #293's beside
    them: one list, in the order `plan` writes the keys, then #293's, which
    `check` would otherwise report only once these were corrected. `execute`
    wears the first one's code and names every one, each remediation once."""
    text = with_key(world.answered, "pins", "pins: openGlass\n")
    text = with_key(text, "legs", "legs: 5\n")
    text = with_key(text, "paths", "paths: true\n")
    text = with_follow_ups(text, "follow_ups: 5\n")
    printed = check_findings(write_edited(world, text))
    assert [line.split(":", 1)[0] for line in printed] == [
        f"FINDING {BAD_LEGS}", f"FINDING {PIN_MALFORMED}",
        f"FINDING {BAD_PATHS}", f"FINDING {BAD_FOLLOW_UPS_CODE}"], printed
    world.plan.write_text(text, encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == BAD_LEGS
    for finding in printed:
        assert f"  {finding}" in refusal.detail
    for key in ("legs", "pins", "paths"):
        assert refusal.remediation.count(KEY_REMEDIATION[key]) == 1
    assert refusal.remediation.count("Remediation: write `follow_ups:`") == 1
    no_leg_was_created(world.tmp)


def test_a_wrong_source_is_named_when_source_says_where_to_read_it(world):
    """`--source` says where to read the repository, so the plan's `source:`
    is not read to open it; it is still the plan's record of the repository,
    and its `commit:` is what `check` holds the tree to. On 5a5011d this was
    `AttributeError` from `source_commit`."""
    text = with_key(world.answered, "source", "source: 5\n")
    result = run_script(ADOPT, "check", "--plan",
                        str(write_edited(world, text)),
                        "--source", str(world.source))
    assert result.returncode == 1, result.stderr + result.stdout
    assert_no_traceback(result)
    [found] = findings_of(result)
    assert found.startswith(
        f"FINDING {BAD_SOURCE}: `source:` is the number 5, not a mapping"), \
        found


def test_a_spec_only_plan_that_consents_in_text_is_not_four_legs(adopter,
                                                                 tmp_path):
    """#386's `allow_empty_legs: code`, where it matters: a source with no
    code, whose plan `plan` wrote with `--allow-empty-leg code`. Text on the
    key's own line was read as four legs, `c`, `o`, `d` and `e`, so on
    5a5011d `check` said `plan ok` while `execute` refused
    `adopt-empty-leg-unconsented` for the leg the person had named; both now
    name the key."""
    repo = spec_only_source(tmp_path)
    plan_path = tmp_path / "plan.yaml"
    written = write_plan(repo, plan_path, project=PROJECT,
                         extra=("--allow-empty-leg", CODE))
    assert written.returncode == 0, written.stderr + written.stdout
    text = with_key(plan_path.read_text(encoding=UTF8), "allow_empty_legs",
                    "allow_empty_legs: code\n")
    plan_path.write_text(text, encoding=UTF8)
    found = check_findings(plan_path)
    assert found == [f"FINDING {BAD_ALLOW}: `allow_empty_legs:` is the text "
                     "'code', not a list: each item of a list names one leg "
                     "`execute` may seed from the shape's template"], found
    refusal = refused_by(adopter, execute_args(tmp_path, plan_path))
    assert refusal.code == BAD_ALLOW
    no_leg_was_created(tmp_path)


def a_whole_pin(product: str) -> str:
    """One `pins:` entry as `plan --pin <product>@<commit>` writes it since
    #273: a mapping of the five values `execute` writes the pin file from.
    `check` and `execute` read no network for a pin, so the commit and the
    digest need only be of the form `plan` records them in."""
    return (f"  - product: {product}\n"
            f"    repository: opensoft/{product}\n"
            f'    commit: "{"a" * 40}"\n'
            f'    tree_sha256: "{"b" * 64}"\n'
            f'    digest_source: "local-clone ({product})"\n')


#: What `check` and `execute` still take, by test id: the key, the block
#: written in place of its own ("" deletes the key), and whether `check`
#: then passes. A `paths:` with no entries is valid as a TYPE and leaves every
#: source path uncovered, which is `plan-uncovered`'s to say, as it was. A
#: `pins:` is a list of mappings, as `plan` writes it since #273.
GOOD_KEYS = {
    "pins-empty": ("pins", "pins: []\n", True),
    "pins-bare": ("pins", "pins:\n", True),
    "pins-absent": ("pins", "", True),
    "pins-one": ("pins", "pins:\n" + a_whole_pin("openGlass"), True),
    "pins-two": ("pins", "pins:\n" + a_whole_pin("openGlass")
                 + a_whole_pin("openPane"), True),
    "allow-empty": ("allow_empty_legs", "allow_empty_legs: []\n", True),
    "allow-bare": ("allow_empty_legs", "allow_empty_legs:\n", True),
    "allow-absent": ("allow_empty_legs", "", True),
    "allow-both": ("allow_empty_legs", "allow_empty_legs: [spec, code]\n",
                   True),
    "paths-empty": ("paths", "paths: []\n", False),
    "paths-bare": ("paths", "paths:\n", False),
    "paths-absent": ("paths", "", False),
}


@pytest.mark.parametrize("edit", sorted(GOOD_KEYS))
def test_a_list_an_empty_list_a_bare_key_and_no_key_are_not_findings(
        adopter, world, edit):
    """#386 (d): what `plan` writes, and the ways of writing none, are not
    findings of this kind; a plan with no entries is `plan-uncovered`, as it
    was, and never `plan-bad-paths`."""
    key, block, passes = GOOD_KEYS[edit]
    text = with_key(world.answered, key, block)
    checked = run_check(write_edited(world, text))
    assert_no_traceback(checked)
    assert "FINDING plan-bad-" not in checked.stderr, checked.stderr
    if passes:
        assert checked.returncode == 0, checked.stderr + checked.stdout
        plan, source = open_plan(adopter, world, text)
        assert adopter._refuse_what_check_finds(plan, source) is None
    else:
        assert checked.returncode == 1, checked.stderr + checked.stdout
        assert {line.split(":", 1)[0] for line in findings_of(checked)} == {
            f"FINDING {UNCOVERED}"}


#: #386's rows for an ENTRY of `pins:`, by test id: the block, and each
#: finding `check` prints, `(code, what it begins with)`. On 5a5011d each
#: was adopted as written: the pins `openGlass` and `True`, `2026`, none, and
#: `{'a': 1}`. Since #273 every entry of a list is `_read_pins`' to judge,
#: beside the entries, in its own words: a name alone is `plan-pin-
#: unrecorded`, anything else `plan` never writes there `plan-pin-malformed`.
PIN_ENTRIES = {
    "name-and-true": ("pins: [openGlass, true]\n", [
        (PIN_UNRECORDED, "`pins:` entry 1, 'openGlass', is a name with no "
                         "commit and no digest"),
        (PIN_MALFORMED, "`pins:` entry 2 is True, not a pin")]),
    "number": ("pins:\n  - 2026\n", [
        (PIN_MALFORMED, "`pins:` entry 1 is 2026, not a pin")]),
    "null": ("pins: [null]\n", [
        (PIN_MALFORMED, "`pins:` entry 1 is None, not a pin")]),
    "mapping": ("pins: [{a: 1}]\n", [
        (PIN_UNRECORDED, "`pins:` entry 1 records no `commit:` and no "
                         "`tree_sha256:`")]),
}


@pytest.mark.parametrize("edit", sorted(PIN_ENTRIES))
def test_an_entry_of_pins_is_judged_by_the_pin_reader_not_first(adopter,
                                                                world, edit):
    """A `pins:` that IS a list is not this gate's: `_plan_key_findings`
    says nothing of it, and each entry `plan` would not write is named by
    `_read_pins` beside the entries, with no traceback and none of this
    gate's remediation; `execute` refuses it under the first one's code
    before any leg exists."""
    block, expected = PIN_ENTRIES[edit]
    text = with_key(world.answered, "pins", block)
    checked = run_check(write_edited(world, text))
    assert checked.returncode == 1, checked.stderr + checked.stdout
    assert_no_traceback(checked)
    found = findings_of(checked)
    assert len(found) == len(expected), found
    for line, (code, said) in zip(found, expected):
        assert line.startswith(f"FINDING {code}: {said}"), line
    assert KEY_REMEDIATION["pins"] not in checked.stderr, checked.stderr
    assert adopter._plan_key_findings(
        adopter.Plan.load(world.tmp / EDITED)) == ([], [])
    world.plan.write_text(text, encoding=UTF8)
    refusal = refused_by(adopter, execute_args(world.tmp, world.plan))
    assert refusal.code == expected[0][0]
    no_leg_was_created(world.tmp)


def test_the_readers_ask_the_type_of_what_they_read(adopter, world):
    """#386 (3): no `TypeError` or `AttributeError` from the reads themselves,
    whoever constructs the plan: each takes only what `plan` writes, and of
    `pins:` the products, out of the mappings `plan` writes since #273 or an
    old plan's names. On 5a5011d the constructor raised on `pins: 5` and
    `paths: 5`, `allowed_empty_legs` on `allow_empty_legs: 5`, `names` on
    `legs: 5`, and `source_commit` and `open_source` on `source: 5`; text was
    read one character at a time."""
    base = {"kind": adopter.PLAN_KIND, "mode": "in-place"}
    for value in (5, True, 1.5, "openGlass", {"a": 1}):
        plan = adopter.Plan(Path("p.yaml"), {
            **base, "pins": value, "paths": value,
            "allow_empty_legs": value, "source": value})
        assert plan.pins == [] and plan.entries == []
        assert plan.allowed_empty_legs() == set()
        assert plan.source_commit == ""
        with pytest.raises(adopter.Refusal) as caught:
            plan.open_source(None, world.tmp / "read")
        assert caught.value.code == "plan-no-source"
        assert plan.open_source(str(world.source),
                                world.tmp / "read").commit
    plan = adopter.Plan(Path("p.yaml"), {
        **base, "pins": ["openGlass", True, None, "", 5,
                         {"product": "openPane"}, {"product": 5}, {"a": 1}],
        "allow_empty_legs": ["code", None, 5, "Spec"]})
    assert plan.pins == ["openGlass", "openPane"]
    assert plan.allowed_empty_legs() == {"code", "Spec"}
    no_legs = adopter.Plan(Path("p.yaml"), dict(base)).names()
    for legs in (5, "Northwind", [{"role": "spec"}]):
        plan = adopter.Plan(Path("p.yaml"), {**base, "legs": legs})
        assert plan.legs == legs, "the doctor's list is kept as it stands"
        assert plan.names() == no_legs, "read as no `legs:` at all"


def test_a_placement_plans_list_of_legs_still_constructs(adopter):
    """#386's constraint: `shape-doctor.py --placement-plan` writes `legs:` as
    a LIST and `tests/test_shape_doctor.py` hands it to `Plan` and
    `_leg_findings`. The constructor refuses no `legs:`; only `check` and
    `execute`, reading a plan FILE, name one that is not a mapping."""
    plan = adopter.Plan(Path("placement-plan.yaml"), {
        "kind": adopter.PLAN_KIND, "mode": "in-place",
        "legs": [{"role": "spec", "path": "spec"}],
        "paths": [{"path": "spec/tool.py", "leg": "spec"}]})
    assert [entry["path"] for entry in plan.entries] == ["spec/tool.py"]
    assert plan.legs == [{"role": "spec", "path": "spec"}]
    assert adopter._leg_findings(plan, None) == []


def test_the_refusal_comes_before_anyone_is_asked_to_say_yes_for_a_key(
        adopter, world, monkeypatch):
    """WITHOUT `--yes`, on a stream that is not a terminal: the refusal is
    still the key's own, and not `adopt-unconfirmed`."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    world.plan.write_text(bad_key_text(world, "pins-text"), encoding=UTF8)
    refusal = refused_by(adopter,
                         execute_args(world.tmp, world.plan, yes=False))
    assert refusal.code == PIN_MALFORMED
    no_leg_was_created(world.tmp)


#: Products `plan --pin <product>@<commit>` takes (`PIN_ARG_RE`) that the
#: plan's reader would take for a number written bare, `2026`, `7` and
#: `1.5`, and `openGlass`, the control.
PIN_NAMES_PLAN_WRITES = ("2026", "007", "1.5", "openGlass")


def stand_in_product(path: Path) -> str:
    """A clone of a neutral product on this machine, with one commit, which
    `plan --pin <product>@<commit> --pin-source <path>` reads the digest
    from with no network (#273); its commit. The file is written as bytes,
    so the tree is the same on every platform."""
    path.mkdir(parents=True)
    git("init", "-q", "-b", "main", cwd=path)
    (path / "README.md").write_bytes(b"# a neutral product\n")
    git("add", "-A", cwd=path)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "README.md", cwd=path)
    return git("rev-parse", "HEAD", cwd=path).stdout.strip()


def write_pinned_plan(source: Path, plan: Path, product: str, base: Path):
    """`plan` for `source` with `--pin <product>@<commit>`, read from a
    stand-in under `base`, as `plan` writes such a plan since #273."""
    clone = base / "pin-source"
    commit = stand_in_product(clone)
    return write_plan(source, plan, project=PROJECT,
                      extra=("--pin", f"{product}@{commit}",
                             "--pin-source", str(clone)))


@pytest.mark.parametrize("name", PIN_NAMES_PLAN_WRITES)
def test_the_pins_plan_writes_are_what_the_gate_takes(adopter, tmp_path,
                                                      name):
    """`plan --pin` writes `pins:` as a list of MAPPINGS since #273, and
    this gate takes exactly that: no finding of this kind and none of
    `_read_pins`', `check` passes the plan `plan` wrote, and the reader
    reads back the product it was given. With #386's item check as it was,
    which took only text, every plan `plan --pin` wrote was `plan-bad-pins`
    in its own `check`."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_pinned_plan(source, plan, name, tmp_path)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    [pin] = adopter.load_yaml(plan)["pins"]
    assert isinstance(pin, dict) and pin["product"] == name, pin
    loaded = adopter.Plan.load(plan)
    assert adopter._plan_key_findings(loaded) == ([], [])
    assert adopter._read_pins(loaded)[1] == []
    checked = run_check(plan)
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    assert loaded.pins == [name]


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


@needs_filter_repo
def test_a_follow_ups_that_is_not_a_list_creates_no_leg_and_the_corrected_plan_runs(  # noqa: E501
        world):
    """#293 as a person met it, through `main`: exit 2, a REFUSED line, no
    traceback and no leg, so the corrected plan does not meet
    `leg-remote-exists`."""
    remotes, work = world.tmp / REMOTES, world.tmp / WORK
    flags = ("--plan", str(world.plan), "--yes", "--local-remote-dir",
             str(remotes), "--work-dir", str(work))
    world.plan.write_text(with_follow_ups(world.answered, "follow_ups: 5\n"),
                          encoding=UTF8)
    refused = run_script(ADOPT, "execute", *flags)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {BAD_FOLLOW_UPS_CODE}: " in refused.stderr
    assert_no_traceback(refused)
    assert_refused_before_any_leg(refused)
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists(), "not even the directory the legs go in"
    assert source_branches(world.source) == ["main"]

    world.plan.write_text(world.answered, encoding=UTF8)
    corrected = run_script(ADOPT, "execute", *flags)
    assert corrected.returncode == 0, corrected.stderr + corrected.stdout
    assert "adoption verified" in corrected.stdout


@needs_filter_repo
def test_an_elected_on_it_cannot_read_creates_no_leg_and_the_corrected_plan_runs(  # noqa: E501
        adopter, world):
    """#294 as a person met it, through `main`: exit 2, a REFUSED line that
    names no flag, no traceback and no leg, so the corrected plan does not
    meet `leg-remote-exists`. The corrected plan has no `reference:`, and the
    manifest records the one its date chooses."""
    remotes, work = world.tmp / REMOTES, world.tmp / WORK
    flags = ("--plan", str(world.plan), "--yes", "--local-remote-dir",
             str(remotes), "--work-dir", str(work))
    world.plan.write_text(with_elected_on(world.answered, "someday", False),
                          encoding=UTF8)
    refused = run_script(ADOPT, "execute", *flags)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {DATE_CODE}: " in refused.stderr
    assert_no_traceback(refused)
    assert_refused_before_any_leg(refused)
    assert DATE_FLAG not in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists(), "not even the directory the legs go in"
    assert source_branches(world.source) == ["main"]

    world.plan.write_text(
        with_elected_on(world.answered, '"2026-09-02"', False), encoding=UTF8)
    corrected = run_script(ADOPT, "execute", *flags)
    assert corrected.returncode == 0, corrected.stderr + corrected.stdout
    assert "adoption verified" in corrected.stdout
    manifest = adopter.load_yaml(work / PROJECT / "project.yaml")
    assert manifest["reference"] == adopter.default_reference("2026-09-02")
    assert str(manifest["elected_on"]) == "2026-09-02"


@needs_filter_repo
def test_pins_written_as_text_creates_no_leg_and_the_corrected_plan_runs(
        adopter, world):
    """#386 (e) as a person met it, through `main`: `pins: openGlass` is exit 2
    and a REFUSED line, with no work directory, no leg and no split branch,
    and no notice of what the run left, which #445 prints only once a leg
    exists. On 5a5011d it adopted, said `adoption verified`, and wrote eight
    pins, `G`, `a`, `e`, `l`, `n`, `o`, `p` and `s`. The corrected plan, with
    the `pins:` block `plan --pin openGlass@<commit>` writes, adopts with the
    one pin and writes its file (#273)."""
    remotes, work = world.tmp / REMOTES, world.tmp / WORK
    flags = ("--plan", str(world.plan), "--yes", "--local-remote-dir",
             str(remotes), "--work-dir", str(work))
    world.plan.write_text(bad_key_text(world, "pins-text"), encoding=UTF8)
    refused = run_script(ADOPT, "execute", *flags)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert f"REFUSED {PIN_MALFORMED}: " in refused.stderr
    assert "`pins:` is 'openGlass', not a list of pins" in refused.stderr
    assert_no_traceback(refused)
    assert_refused_before_any_leg(refused)
    assert "adoption verified" not in refused.stdout
    assert not remotes.exists(), "not even the directory the legs go in"
    assert not work.exists(), "and no work directory"
    assert source_branches(world.source) == ["main"]

    pinned = world.tmp / "pinned-plan.yaml"
    written = write_pinned_plan(world.source, pinned, "openGlass", world.tmp)
    assert written.returncode == 0, written.stderr + written.stdout
    block = re.search(r"^pins:.*\n(?:[ \t]+.*\n)*",
                      pinned.read_text(encoding=UTF8), re.M).group(0)
    world.plan.write_text(with_key(world.answered, "pins", block),
                          encoding=UTF8)
    corrected = run_script(ADOPT, "execute", *flags)
    assert corrected.returncode == 0, corrected.stderr + corrected.stdout
    assert "adoption verified" in corrected.stdout
    manifest = adopter.load_yaml(work / PROJECT / "project.yaml")
    assert manifest["neutral_product_pins"] == ["openGlass"]
    assert (work / PROJECT / "contracts" / "openglass-pin.yaml").is_file()
