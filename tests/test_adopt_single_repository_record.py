# SPDX-License-Identifier: Apache-2.0
"""The source's own `single-repository.yaml`, asked about by name (#528).

`plan` asked about it under `ambiguous-top-level-yaml`, whose question offers
`spec`, `code` and `root` for "a declaration the project has DECIDED,
configuration the implementation reads, or project-level wiring". The file is
none of those: it is this standard's optional record that a project STAYS one
repository (`contracts/single-repository-record.yaml`), and a repository being
adopted into the Triad holds a record of the decision the adoption reverses.
Its one reader is the Triad advisory, which is silent in an assembly root
whatever the file holds, so neither leg has any use for it.

Ruled 2026-10-12 by Brett Heap, "Ask; default drop": a path-policy rule names
the file and asks drop or root, and "the default answer is drop". That is
`ambiguous-single-repository-record`, above `ambiguous-top-level-yaml`, with
`default: drop`. `plan` writes `leg: drop` and keeps `review_required: true`
and the question beside it; `check` passes it, and `execute` drops the file
unless a person writes `root`. The verdict keeps `leg` None, so the doctor,
which walks a leg with the same `walk`, still reads a leg's copy as a
question.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from argparse import Namespace

import pytest

from conftest import (ADOPT, REPO, findings, git, load_without_bytecode,
                      make_source_repo, planned, run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from path_classify import PathPolicy  # noqa: E402
from repo_shape import Refusal, load_yaml  # noqa: E402
from shape_advisory import RECORD_FILE  # noqa: E402

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
RULE = "ambiguous-single-repository-record"
GENERAL = "ambiguous-top-level-yaml"
POLICY = REPO / "contracts" / "path-classification.yaml"
SPLIT_BRANCH = "adopt/three-repo-shape"
#: A record as the schema's own example writes one.
RECORD = ("schema_version: 1\nkind: single-repository-record\n"
          'decided_by: "Dana Okafor"\ndecided_on: 2026-10-06\n'
          'reason: "A dotfiles repository."\n')
#: The source: a spec, the code, a README the root keeps, the record, and
#: another top-level YAML file that keeps the general question.
TREE = {"src/app.py": "print(1)\n", "docs/spec.md": "# Spec\n",
        "README.md": "# Thing\n", RECORD_FILE: RECORD,
        "release.yaml": "name: release\n"}


@pytest.fixture(scope="module")
def adopter():
    module_spec = importlib.util.spec_from_file_location(
        "adopt_single_repository_record", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture
def source(tmp_path):
    return make_source_repo(tmp_path / "Thing", tree=TREE, edits=())


def entry_of(plan, path: str) -> dict:
    """The plan's entry for `path`, as the loader reads it."""
    entry, = [row for row in load_yaml(plan)["paths"] if row["path"] == path]
    return entry


def record_question() -> str:
    return PathPolicy.load(POLICY).classify_file(RECORD_FILE).question


def one_rule_policy(**rule) -> PathPolicy:
    """A policy holding `rule` alone, as the classifier loads one."""
    return PathPolicy({"kind": "path-classification-policy",
                       "rules": [{"id": "t", "paths": ["x", "notes/**"],
                                  "reason": "why", "question": "Keep it?",
                                  **rule}]})


# --- the rule ---------------------------------------------------------------

def test_the_rule_names_the_file_the_advisory_reads():
    """One name in two places: the rule asks about the file the advisory is
    the only reader of, so a rename there is caught here."""
    rules = {rule["id"]: rule for rule, _ in PathPolicy.load(POLICY).rules}
    assert rules[RULE]["paths"] == [RECORD_FILE] == ["single-repository.yaml"]


def test_the_rule_comes_before_the_general_question():
    """First match wins, so the order is the answer."""
    ids = [rule["id"] for rule, _ in PathPolicy.load(POLICY).rules]
    assert ids.index(RULE) < ids.index(GENERAL)


def test_the_record_is_asked_a_question_with_drop_as_its_default():
    """The default rides beside the question and never fills `leg`: the
    verdict is still one the rules could not call."""
    verdict = PathPolicy.load(POLICY).classify_file(RECORD_FILE)
    assert verdict.rule == RULE
    assert verdict.leg is None
    assert verdict.review_required
    assert verdict.default == "drop"
    assert verdict.confidence == "review"
    assert "`single-repository.yaml`" in verdict.reason
    assert "Triad" in verdict.reason and "reversed" in verdict.reason


def test_the_question_offers_drop_and_root_and_drops_by_default():
    question = record_question()
    drop, root = question.index("(drop"), question.index("(root)")
    assert drop < root, "the default is asked first"
    assert "the default" in question[drop:root]
    assert "stays a single repository" in question
    assert "adopting it makes the project a Triad" in question
    for general in ("(spec)", "(code)", "project-level wiring"):
        assert general not in question, f"the general question's {general}"


def test_every_other_top_level_data_file_is_asked_as_before():
    """Only the record's name: `release.yaml` and a record spelled `.yml`,
    which the advisory does not read, keep the question that offers `spec`
    and `code`, and a nested record is not the project's."""
    policy = PathPolicy.load(POLICY)
    for name in ("release.yaml", "single-repository.yml"):
        verdict = policy.classify_file(name)
        assert verdict.rule == GENERAL, name
        assert verdict.default is None, name
        assert "(spec)" in verdict.question and "(root)" in verdict.question
    assert policy.classify_file("config/single-repository.yaml").rule != RULE


# --- a default the classifier takes, and one it refuses -----------------------

def test_a_rule_that_asks_may_name_drop_as_its_default():
    verdict = one_rule_policy(leg="ambiguous", default="drop").classify_file(
        "x")
    assert (verdict.leg, verdict.default) == (None, "drop")
    assert verdict.review_required


@pytest.mark.parametrize("rule", [
    {"leg": "ambiguous", "default": "root"},
    {"leg": "ambiguous", "default": "spec"},
    {"leg": "ambiguous", "default": "code"},
    {"leg": "ambiguous", "default": None},
    {"leg": "spec", "default": "drop"},
    {"leg": "root", "default": "drop"},
], ids=["root", "spec", "code", "empty", "beside-spec", "beside-root"])
def test_any_other_default_is_refused_when_the_policy_loads(rule):
    """`root` unanswered would keep a path in the assembly root nobody chose
    to keep, a rule that answers says so in `leg:`, and a rule that does
    not ask has no question for a default to answer."""
    with pytest.raises(Refusal) as caught:
        one_rule_policy(**rule)
    assert caught.value.code == "path-policy-default"
    assert "'t'" in caught.value.detail


def test_a_directory_the_rule_covers_whole_keeps_its_default(adopter):
    """`walk` folds a directory whose files one rule asks about into one
    entry; the default goes with the question, and `leg` stays None."""
    policy = one_rule_policy(leg="ambiguous", default="drop")
    entry, = adopter.walk(policy, [("notes/a.md", 1), ("notes/b.md", 2)])
    assert (entry.path, entry.leg, entry.default) == ("notes/", None, "drop")
    assert entry.review_required


# --- what `plan` writes --------------------------------------------------------

def test_plan_writes_drop_and_still_asks_the_question(source, tmp_path):
    out = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, out, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    entry = entry_of(out, RECORD_FILE)
    assert entry["leg"] == "drop"
    assert entry["review_required"] is True
    assert entry["confidence"] == "review"
    assert entry["rule"] == RULE
    assert entry["question"] == record_question()
    other = entry_of(out, "release.yaml")
    assert other["rule"] == GENERAL
    assert other["leg"] is None
    assert "(spec)" in other["question"]


def test_plan_prints_the_default_with_its_question_and_not_as_unresolved(
        source, tmp_path):
    written = write_plan(source, tmp_path / "adoption-plan.yaml",
                         project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    tail = written.stdout.split("\nplan written to ", 1)[1]
    proposed, unresolved = tail.split(
        " path(s) need a human or an AI to answer a question", 1)
    assert ("1 path(s) carry their rule's default answer, which `execute` "
            "takes as written unless it is changed:\n"
            f"  {RECORD_FILE} (leg: drop)\n      {record_question()}\n"
            ) in proposed
    assert RECORD_FILE not in unresolved
    assert "release.yaml" in unresolved


def test_check_passes_the_default_nobody_changed(source, tmp_path):
    """The default is an answer `check` takes: only the general question
    beside it was answered."""
    plan = planned(source, tmp_path, {"release.yaml": "spec"})
    assert entry_of(plan, RECORD_FILE)["leg"] == "drop"
    assert findings(plan) == []


@pytest.mark.parametrize("leg", ["drop", "root"])
def test_both_answers_the_question_offers_check_ok(source, tmp_path, leg):
    plan = planned(source, tmp_path, {"release.yaml": "spec",
                                      RECORD_FILE: leg})
    assert findings(plan) == []


# --- a question asked in place of the rule's carries no default ----------------

def test_a_path_execute_will_not_extract_is_asked_with_no_default(adopter):
    """`ask_about_refused_paths` asks why the name cannot go into a leg, and
    the rule's default answers nothing there."""
    asked = adopter.Entry("-notes.md", adopter.Verdict(
        None, "t", "why", "high", "Keep it?", "drop"), 1, 1)
    out, = adopter.ask_about_refused_paths([asked], [])
    assert (out.leg, out.default) == (None, None)
    assert out.review_required
    assert adopter.with_defaults([out])[0].leg is None


def test_a_record_that_is_a_submodule_is_asked_with_no_default(adopter):
    """`ask_about_submodules` asks the `.gitmodules` question of a gitlink
    whatever rule matched its path, and that question has no default."""
    policy = PathPolicy.load(POLICY)
    ruled = [adopter.Entry(RECORD_FILE, policy.classify_file(RECORD_FILE), 1,
                           0)]
    tree = [(RECORD_FILE, adopter.GITLINK_MODE, "c" * 40, 0)]
    out, = adopter.ask_about_submodules(policy, ruled, tree)
    assert out.rule == "ambiguous-gitmodules"
    assert (out.leg, out.default) == (None, None)
    assert adopter.with_defaults([out])[0].leg is None


def test_plan_writes_a_default_only_where_no_question_replaced_it(tmp_path):
    """In `plan` itself: a rule's default over a name `execute` will not
    extract is not written in, because `ask_about_refused_paths` asks first
    and passes over a path already answered `drop`."""
    policy = tmp_path / "policy.yaml"
    policy.write_bytes(
        b"schema_version: 1\nkind: path-classification-policy\nrules:\n"
        b"  - id: test-asked-with-a-default\n    paths:\n"
        b"      - \"-notes.md\"\n    leg: ambiguous\n    default: drop\n"
        b"    reason: A test rule.\n    question: Keep it?\n"
        b"  - id: test-everything-else\n    paths:\n      - \"**\"\n"
        b"    leg: spec\n    reason: Everything else.\n")
    here = make_source_repo(tmp_path / "Thing",
                            tree={"-notes.md": "# N\n", "src/a.py": "1\n"},
                            edits=())
    out = tmp_path / "adoption-plan.yaml"
    written = write_plan(here, out, extra=("--path-policy", str(policy)))
    assert written.returncode == 0, written.stderr + written.stdout
    entry = entry_of(out, "-notes.md")
    assert entry["rule"] == "test-asked-with-a-default"
    assert entry["leg"] is None
    assert "`execute` will not extract" in entry["question"]


# --- the doctor still reads a leg's copy as a question -----------------------

def test_the_doctor_reads_a_legs_copy_as_a_question_and_not_misplaced(
        adopter):
    """The placement row walks a leg with `adopt-project.py`'s own `walk`
    and calls a path misplaced when its `leg` is another one. The default
    never fills `leg` there, so a copy in the spec leg is a question."""
    doctor = load_without_bytecode(REPO / "shape-doctor.py",
                                   "shape_doctor_single_repository_record")
    walked = adopter.walk(PathPolicy.load(POLICY), [(RECORD_FILE, 100)])
    misplaced, review, settled = doctor.walked_findings(walked, "spec",
                                                        "spec", None)
    assert (misplaced, settled) == ([], [])
    row, = review
    assert row["path"] == f"spec/{RECORD_FILE}"
    assert (row["rule"], row["classified_as"]) == (RULE, None)
    assert row["review_required"] is True


# --- what each answer does ----------------------------------------------------

def adopted(source, tmp_path, leg: str | None):
    """`execute` on the plan with the general question answered and the
    record's left as `plan` wrote it (`None`), or answered `leg`."""
    answers = {"release.yaml": "spec"}
    if leg is not None:
        answers[RECORD_FILE] = leg
    plan = planned(source, tmp_path, answers)
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "adoption verified" in result.stdout
    return remotes


def files_of(repo, ref: str) -> list[str]:
    return git("ls-tree", "-r", "--name-only", ref,
               cwd=repo).stdout.splitlines()


@needs_filter_repo
def test_the_default_nobody_changed_drops_it_from_every_repository(
        source, tmp_path):
    """`execute` takes the default as written, and the split commit names
    the record among the paths it dropped."""
    remotes = adopted(source, tmp_path, None)
    assert RECORD_FILE not in files_of(source, SPLIT_BRANCH)
    for role in ("spec", "code"):
        leg = remotes / f"{PROJECT}-{role}.git"
        assert RECORD_FILE not in files_of(leg, "main")
    message = git("log", "-1", "--format=%B", SPLIT_BRANCH,
                  cwd=source).stdout
    dropped = message.split("DROPPED (in no leg and no longer here):\n", 1)[1]
    assert dropped.split("\n\n", 1)[0].splitlines() == [f"  {RECORD_FILE}"]


def test_execute_takes_the_default_without_asking_again(
        adopter, source, tmp_path, monkeypatch):
    """No `plan-unresolved` for the record: `execute` gets past every
    refusal of the plan to the confirmation, which `--yes` gives, and is
    stopped there, before any leg exists."""
    plan = planned(source, tmp_path, {"release.yaml": "spec"})

    def stop(*_args):
        raise adopter.Refusal("confirm-reached", "past every plan refusal")

    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    monkeypatch.setattr(adopter, "_confirm", stop)
    args = Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / "remotes",
                     allow_empty_leg=[], yes=True, work_dir=tmp_path / "work")
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    assert caught.value.code == "confirm-reached"
    assert not (tmp_path / "remotes").exists()


@needs_filter_repo
def test_kept_it_is_the_assembly_roots_with_the_sources_bytes(
        source, tmp_path):
    """Kept in the root, the record is the source's blob there, beside the
    shape's manifest, and in neither leg."""
    remotes = adopted(source, tmp_path, "root")
    ours = git("rev-parse", f"main:{RECORD_FILE}", cwd=source).stdout
    assert git("rev-parse", f"{SPLIT_BRANCH}:{RECORD_FILE}",
               cwd=source).stdout == ours
    assert "project.yaml" in files_of(source, SPLIT_BRANCH)
    for role in ("spec", "code"):
        leg = remotes / f"{PROJECT}-{role}.git"
        assert RECORD_FILE not in files_of(leg, "main")
