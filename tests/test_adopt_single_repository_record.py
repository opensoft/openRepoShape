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

Ruled 2026-10-12 (the A7 line of #457): a path-policy rule names the file and
asks drop or root, defaulting to drop. That is `ambiguous-single-repository-
record`, above `ambiguous-top-level-yaml`. Its default is the question's own
words: `plan` still writes `leg: null` and `execute` still refuses while it is
open, because an unanswered question is never an implicit anything, and
nothing is dropped that a person did not answer `drop`.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from argparse import Namespace

import pytest

from conftest import (ADOPT, REPO, findings, git, make_source_repo, planned,
                      run_script, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
from path_classify import PathPolicy  # noqa: E402
from repo_shape import load_yaml  # noqa: E402
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


def test_the_record_is_asked_a_question_of_its_own():
    verdict = PathPolicy.load(POLICY).classify_file(RECORD_FILE)
    assert verdict.rule == RULE
    assert verdict.leg is None and verdict.review_required
    assert verdict.confidence == "review"
    assert "`single-repository.yaml`" in verdict.reason
    assert "Triad" in verdict.reason and "reversed" in verdict.reason


def test_the_question_offers_drop_and_root_and_drops_by_default():
    question = PathPolicy.load(POLICY).classify_file(RECORD_FILE).question
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
        assert "(spec)" in verdict.question and "(root)" in verdict.question
    assert policy.classify_file("config/single-repository.yaml").rule != RULE


# --- the question `plan` asks -------------------------------------------------

def test_plan_asks_the_record_its_own_question(source, tmp_path):
    out = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, out, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    entry = entry_of(out, RECORD_FILE)
    assert entry["leg"] is None and entry["review_required"] is True
    assert entry["rule"] == RULE
    assert entry["question"] \
        == PathPolicy.load(POLICY).classify_file(RECORD_FILE).question
    other = entry_of(out, "release.yaml")
    assert other["rule"] == GENERAL
    assert "(spec)" in other["question"]


def test_the_default_is_not_an_answer_check_says_so(source, tmp_path):
    """Drop is the question's default and nothing more: a plan nobody
    answered is unresolved, and the question is in the finding."""
    plan = planned(source, tmp_path, {"release.yaml": "spec"})
    (code, detail), = findings(plan)
    assert code == "plan-unresolved"
    assert detail.startswith("`single-repository.yaml` still has `leg: "
                             "null`. The question was: ")
    assert PathPolicy.load(POLICY).classify_file(RECORD_FILE).question \
        in detail


def test_execute_refuses_it_unanswered_before_any_leg_exists(
        adopter, source, tmp_path, monkeypatch):
    plan = planned(source, tmp_path, {"release.yaml": "spec"})
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)
    args = Namespace(plan=str(plan), source=None,
                     local_remote_dir=tmp_path / "remotes",
                     allow_empty_leg=[], yes=True, work_dir=tmp_path / "work")
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(args)
    assert caught.value.code == "plan-unresolved"
    assert caught.value.detail \
        == "1 path(s) still have `leg: null`: `single-repository.yaml`"
    assert not (tmp_path / "remotes").exists()


@pytest.mark.parametrize("leg", ["drop", "root"])
def test_both_answers_the_question_offers_check_ok(source, tmp_path, leg):
    plan = planned(source, tmp_path, {"release.yaml": "spec",
                                      RECORD_FILE: leg})
    assert findings(plan) == []


# --- what each answer does ----------------------------------------------------

def adopted(source, tmp_path, leg: str):
    plan = planned(source, tmp_path, {"release.yaml": "spec",
                                      RECORD_FILE: leg})
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
def test_dropped_it_is_in_no_repository_of_the_assembly(source, tmp_path):
    remotes = adopted(source, tmp_path, "drop")
    assert RECORD_FILE not in files_of(source, SPLIT_BRANCH)
    for role in ("spec", "code"):
        leg = remotes / f"{PROJECT}-{role}.git"
        assert RECORD_FILE not in files_of(leg, "main")


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
