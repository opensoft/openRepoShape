# SPDX-License-Identifier: Apache-2.0
"""`execute` refuses every finding `check` reports, before a leg exists (#168).

It used to refuse only `plan-unresolved` and `plan-stale`. A plan `check`
rejects as uncovered, with a bad leg, covered twice, with a duplicated path or
with an empty entry ran on into `_create_leg_remotes`, pushed BOTH legs and
failed only at the verification as `adopt-lost` -- and the corrected plan then
met `leg-remote-exists`, which has no `--force`.

NO NETWORK, NO GITHUB, AND NO `git filter-repo` except in the one end-to-end
test at the bottom. The rest load `adopt-project.py` through importlib and call
`cmd_execute` in this process. Its probe for `git filter-repo` is stubbed,
because every refusal under test is raised BEFORE the tool would be used; a
`cmd_execute` that stopped refusing would carry on to create the legs, return
an exit code instead of raising, and fail these tests the same way on a machine
that has the tool and on one that has not.
"""

from __future__ import annotations

import importlib.util
import shutil
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, git, make_source_repo, resolve, run_script,
                      write_plan)

PROJECT = "Northwind"
ANSWERS = (("examples/", "spec"), (".claude/", "root"), ("release.yaml", "root"))

#: The entries the edits below work on: `src/` is one directory, two files, the
#: code leg; `specs/` is the specification, and `Spec` is not one of the four
#: words a `leg:` may be.
SRC_ENTRY = "  - path: src/\n"
SPECS_ENTRY = "  - path: specs/\n    leg: spec\n"
SPECS_WRONG_CASE = "  - path: specs/\n    leg: Spec\n"

#: Where a test writes the plan it has edited, so that `check` can be asked
#: about it and `Plan.load` can read it.
EDITED = "edited-plan.yaml"

#: What `execute` needs and the rest of this file does not. Written out here
#: rather than imported from a sibling test module, which is not a thing this
#: suite does.
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
def world(tmp_path) -> dict:
    """A source, and a plan for it with every question ANSWERED: the plan
    `check` passes. Each test edits its own copy of the text."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    unanswered = plan.read_text(encoding="utf-8")
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return {"source": source, "plan": plan, "answered": plan.read_text(
        encoding="utf-8"), "unanswered": unanswered, "tmp": tmp_path}


def without_entry(text: str, path: str) -> str:
    """`text` with the plan entry for `path` deleted, as a bad edit would."""
    lines = text.splitlines(keepends=True)
    start = lines.index(f"  - path: {path}\n")
    end = start + 1
    while lines[end].startswith("    "):
        end += 1
    return "".join(lines[:start] + lines[end:])


def execute_args(tmp_path: Path, plan: Path, *allowed: str) -> Namespace:
    """What `main` hands `cmd_execute`: nothing but the plan, `--yes`, a local
    remote directory that does not exist yet and a work directory."""
    return Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / "remotes",
                     allow_empty_leg=list(allowed), yes=True,
                     work_dir=tmp_path / "work")


def refused_by(adopter, args):
    """The `Refusal` `cmd_execute` raises for `args`. Failing to raise one
    means it carried on, and then it returned an exit code instead."""
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    return caught.value


def nothing_was_created(tmp_path: Path) -> None:
    """The strongest statement a refused run can make that is still true: the
    directory the legs would have gone in was never even made, and no leg was
    cloned for extraction. (`work/` itself is made first, empty, because the
    source is opened inside it.)"""
    assert not (tmp_path / "remotes").exists()
    for role in ("spec", "code"):
        assert not (tmp_path / "work" / f"{PROJECT}-{role}").exists()


def write_edited(world, text: str) -> Path:
    """`text` as a plan file beside the world's own, which it leaves alone."""
    path = world["tmp"] / EDITED
    path.write_text(text, encoding="utf-8")
    return path


def open_plan(adopter, world, text: str):
    """`(plan, source)` for `text`, the way `cmd_execute` opens them."""
    plan = adopter.Plan.load(write_edited(world, text))
    return plan, plan.open_source(str(world["source"]), world["tmp"] / "read")


def check_findings(plan: Path) -> list[str]:
    """Every `FINDING` line `check` prints for `plan`, which must fail it."""
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


#: The five finding classes `execute` did not refuse, each with a fragment its
#: finding must carry. `EDITS` below makes the plan that has each one.
CLASSES = {
    "plan-uncovered": "src/app/main.py is in the source tree and in no plan",
    "plan-bad-leg": "specs/ declares leg 'Spec'",
    "plan-covered-twice": "src/app/main.py is covered by",
    "plan-duplicate-path": "src/ appears 2 times",
    "plan-empty-entry": "nonexistent/ covers nothing",
}

EDITS = {
    "plan-uncovered": lambda text: without_entry(text, "src/"),
    "plan-bad-leg": lambda text: text.replace(SPECS_ENTRY,
                                              SPECS_WRONG_CASE, 1),
    "plan-covered-twice": lambda text: text.replace(
        SRC_ENTRY, "  - path: src/app/\n    leg: code\n" + SRC_ENTRY, 1),
    "plan-duplicate-path": lambda text: text.replace(
        SRC_ENTRY, SRC_ENTRY + "    leg: code\n" + SRC_ENTRY, 1),
    "plan-empty-entry": lambda text: text.replace(
        SRC_ENTRY, "  - path: nonexistent/\n    leg: code\n" + SRC_ENTRY, 1),
}


def broken_text(world, code: str) -> str:
    text = EDITS[code](world["answered"])
    assert text != world["answered"], f"the {code} edit changed nothing"
    return text


# --- the function itself ---------------------------------------------------

def test_a_plan_check_passes_raises_no_refusal(adopter, world):
    """THE CONTRACT THAT MUST NOT BREAK: what `check` passes, `execute` runs."""
    checked = run_script(ADOPT, "check", "--plan", str(world["plan"]))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    plan, source = open_plan(adopter, world, world["answered"])
    assert adopter._refuse_what_check_finds(plan, source) is None


@pytest.mark.parametrize("code", sorted(CLASSES))
def test_each_class_check_reports_is_refused_under_its_own_code(adopter, world,
                                                                code):
    plan, source = open_plan(adopter, world, broken_text(world, code))
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    refusal = caught.value
    assert refusal.code == code
    assert CLASSES[code] in refusal.detail
    assert f"FINDING {code}:" in refusal.detail


@pytest.mark.parametrize("code", sorted(CLASSES))
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
    plan, source = open_plan(adopter, world, broken_text(world, "plan-uncovered"))
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    said = str(caught.value)
    assert said.startswith("REFUSED plan-uncovered: ")
    assert "no repository was created" in said
    assert "run `check` until it prints `plan ok`" in said
    assert "leg-remote-exists" in said


def test_the_code_is_the_first_findings_own(adopter, world):
    """Two classes at once: the refusal wears the first one `check` lists and
    still names the other, so nothing a plan is wrong about is left unsaid."""
    text = without_entry(world["answered"].replace(SPECS_ENTRY,
                                                   SPECS_WRONG_CASE, 1), "src/")
    plan, source = open_plan(adopter, world, text)
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    assert caught.value.code == "plan-uncovered"
    assert "FINDING plan-bad-leg:" in caught.value.detail


def test_a_long_list_of_findings_is_capped_with_a_count(adopter, world):
    text = world["answered"]
    for path in ("contracts/", "docker/", "docs/", "openspec/", "pkg_core/",
                 "specs/", "src/", "tests/"):
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
    source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                              edits=SPEC_ONLY_EDITS)
    plan_path = tmp_path / "plan.yaml"
    written = write_plan(source, plan_path, project=PROJECT,
                         extra=("--allow-empty-leg", "code"))
    assert written.returncode == 0, written.stderr + written.stdout
    checked = run_script(ADOPT, "check", "--plan", str(plan_path))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "WARNING the code leg will be SEEDED" in checked.stdout
    plan = adopter.Plan.load(plan_path)
    seeded = plan.open_source(str(source), tmp_path / "read")
    assert adopter._refuse_what_check_finds(plan, seeded) is None


# --- the wiring in `cmd_execute`, and what it leaves undone -----------------

@pytest.mark.parametrize("code", sorted(CLASSES))
def test_execute_refuses_each_class_and_creates_nothing(adopter, world, code):
    world["plan"].write_text(broken_text(world, code), encoding="utf-8")
    refusal = refused_by(adopter,
                         execute_args(world["tmp"], world["plan"]))
    assert refusal.code == code
    nothing_was_created(world["tmp"])
    branches = git("branch", "--format=%(refname:short)",
                   cwd=world["source"]).stdout.split()
    assert branches == ["main"], "nothing was pushed to the source either"


def test_a_leg_with_no_path_is_still_refused_without_consent(adopter, tmp_path):
    """The seeding refusal is where it was: this one passes the plan on to it."""
    source = make_source_repo(tmp_path / "IRRS", SPEC_ONLY_TREE,
                              edits=SPEC_ONLY_EDITS)
    plan_path = tmp_path / "plan.yaml"
    assert write_plan(source, plan_path, project=PROJECT).returncode == 0
    refusal = refused_by(adopter, execute_args(tmp_path, plan_path))
    assert refusal.code == "adopt-empty-leg-unconsented"
    nothing_was_created(tmp_path)


# --- the order of the refusals ---------------------------------------------

def test_an_unresolved_question_is_still_reported_as_unresolved(adopter, world):
    """THE TWO ARE NOT REPORTED TWICE. This plan is unanswered AND uncovered;
    `_refuse_an_unrunnable_plan` speaks first, in its own words, and the
    coverage finding is what `check` will say once the questions are
    answered."""
    world["plan"].write_text(without_entry(world["unanswered"], "src/"),
                             encoding="utf-8")
    refusal = refused_by(adopter,
                         execute_args(world["tmp"], world["plan"]))
    assert refusal.code == "plan-unresolved"
    assert "still have `leg: null`" in refusal.detail
    assert "never an implicit `root`" in refusal.remediation
    nothing_was_created(world["tmp"])


def test_a_stale_plan_is_still_reported_as_stale(adopter, world):
    """A plan written against an older commit is judged `plan-stale`, whatever
    the tree that moved has gained: `late/` is covered by NO entry, and the
    plan did not omit it, it never saw it."""
    (world["source"] / "late").mkdir()
    (world["source"] / "late" / "work.txt").write_text("later\n")
    git("add", "-A", cwd=world["source"])
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "later work", cwd=world["source"])
    world["plan"].write_text(world["answered"], encoding="utf-8")
    refusal = refused_by(adopter,
                         execute_args(world["tmp"], world["plan"]))
    assert refusal.code == "plan-stale"
    nothing_was_created(world["tmp"])


def test_a_path_that_is_a_git_option_is_still_unsafe_not_uncovered(adopter,
                                                                    world):
    """THE PLAN IS UNTRUSTED INPUT and its paths are checked as `git`
    arguments first. This plan is also uncovered -- `specs/` has no entry --
    and would be refused as that, losing the reason it is dangerous, if the
    coverage refusal ran before them. (`test_adopt_e2e.py` has the same case
    behind `git filter-repo`; this one runs everywhere.)"""
    world["plan"].write_text(world["answered"].replace(
        "  - path: specs/\n", "  - path: --output=never-written\n", 1),
        encoding="utf-8")
    refusal = refused_by(adopter,
                         execute_args(world["tmp"], world["plan"]))
    assert refusal.code == "unsafe-value"
    nothing_was_created(world["tmp"])


# --- end to end ------------------------------------------------------------

@needs_filter_repo
def test_an_uncovered_plan_creates_no_leg_and_the_corrected_plan_then_runs(
        world):
    """THE HARM, as a person met it: no leg is created, so the corrected plan
    does not meet `leg-remote-exists` and the adoption goes through."""
    tmp_path = world["tmp"]
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    flags = ("--plan", str(world["plan"]), "--yes",
             "--local-remote-dir", str(remotes), "--work-dir", str(work))
    world["plan"].write_text(without_entry(world["answered"], "src/"),
                             encoding="utf-8")
    refused = run_script(ADOPT, "execute", *flags)
    assert refused.returncode == 2, refused.stderr + refused.stdout
    assert "REFUSED plan-uncovered" in refused.stderr
    assert "src/app/main.py" in refused.stderr
    assert "creating the leg repositories" not in refused.stdout
    assert not remotes.exists(), "not even the directory the legs go in"
    for role in ("spec", "code"):
        assert not (work / f"{PROJECT}-{role}").exists()
    assert git("branch", "--format=%(refname:short)",
               cwd=world["source"]).stdout.split() == ["main"]

    world["plan"].write_text(world["answered"], encoding="utf-8")
    corrected = run_script(ADOPT, "execute", *flags)
    assert corrected.returncode == 0, corrected.stderr + corrected.stdout
    assert "adoption verified" in corrected.stdout
    for role in ("spec", "code"):
        assert (remotes / f"{PROJECT}-{role}.git").is_dir()
