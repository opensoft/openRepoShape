# SPDX-License-Identifier: Apache-2.0
"""The adoption's answers outlive the plan, and a record's row is a person's
to change (#525: #457's N7 and L1-08).

THE DEFECTS, on main 2247dbff:

  * N7. `execute` recorded the plan's answers about submodules only (#189).
    A path the policy cannot call -- `examples/`, rule `ambiguous-examples`
    -- answered `spec` in the plan was asked again by the doctor's
    `placement` row on every run after the split: `spec/examples/` stayed
    `review_required`, and AGENTS.md's doctor step 4 had an assistant ask
    the human the question the human had already answered.
  * L1-08. Nothing said how a `submodules:` row changes. A submodule moved
    to the other leg on purpose -- a pull request on each leg, `bump-leg.py`
    for each pin -- stayed `MISPLACED (1 path)`, exit 1, with a NEXT of
    `--placement-plan`, a plan of the move already made. A row whose
    submodule was removed was silent: COMPLIANT, and `manifest ok`.

THE FIX. `execute` appends `answered_paths:` after `submodules:`, one row
per entry kept in a leg that covers a path the policy's own walk leaves
`leg: null`, and the doctor takes each row as the answer to that question in
that leg -- never in the other, where the path stays a question, and never
as a finding. A submodule whose recorded leg no longer holds it is still
MISPLACED, says it moved, and names no plan: its NEXT is this doctor again,
as the `manifest kinds` row's is for a file only a person can mend, and its
WHY gives both ways out. A row no leg holds is a `note`. AGENTS.md says the
person edits the row in the pull request that bumps the pins.

Most of these run on the doctor's own scaffolded project, a record written
by hand, and the index staged as a leg would hold it, so they need no `git
filter-repo`. The adoptions at the end are the real thing, end to end.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

from conftest import FILE_PROTOCOL, REPO, clone_just_pushed, git, run_script
#: The doctor's own fixtures and helpers, from the module that owns them: a
#: project made any other way would be a different project.
from test_shape_doctor import (  # noqa: F401
    ORG, adoption_module, commit_all, doctor, doctor_module,
    needs_filter_repo, project, record_submodules, rows_of, scaffolded_here,
    stage, stage_gitlink, standard, verdict_line,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402

#: The paths the tests below name again and again.
RULES_PATH = "vendor/rules"
EXAMPLES = "examples/"
ASKED = "spec/examples/"
GITMODULES = ".gitmodules"
README = "README.md"
BLOB = "100644"
COMPLIANT = "COMPLIANT"
#: Why the plans below answered `examples/` into the spec leg.
EXAMPLES_ANSWER = "the specification cites the golden runs"
#: Why they answered the editor rules' submodule into the code leg.
RULES_ANSWER = "editor rules the code leg's tooling reads"
#: A golden run, as two files the policy cannot call (`ambiguous-examples`).
GOLDEN = ("examples/golden/case.json", "examples/golden/case.expected.json")
MOVED_CLAUSE = ("1 submodule(s) moved out of the leg project.yaml's "
                "`submodules:` records for them, which no longer holds them "
                "(#525): spec/vendor/rules (recorded in the code leg)")


def record_answers(project: Path, *rows: tuple) -> None:
    """Append `answered_paths:`, one `(path, leg[, resolution])` row each,
    in the very bytes `record_submodules` writes a `submodules:` row in:
    the two records are one shape."""
    manifest = project / "project.yaml"
    before = manifest.read_bytes()
    record_submodules(project, *rows)
    block = manifest.read_bytes()[len(before):]
    assert block.startswith(b"\nsubmodules:\n"), block
    manifest.write_bytes(before + b"\nanswered_paths:\n"
                         + block[len(b"\nsubmodules:\n"):])


def placement(standard: Path, root: Path) -> tuple:
    """`(result, verdict, the placement row)` from one `--json` run."""
    result = doctor(standard, root, "--json")
    return (result, json.loads(result.stdout)["verdict"],
            rows_of(result)["placement"])


def doctor_again(standard: Path, root: Path) -> str:
    """This doctor's own line for `root`, spelled as `unreadable_next` spells
    it: the NEXT of a row whose way out is a person's."""
    module = doctor_module(standard)
    return (f"{module.PYTHON} "
            f"{module.quote_arg(standard.resolve() / 'shape-doctor.py')} "
            f"--root {module.quote_arg(root.resolve())}")


def golden_run(project: Path, leg: str = "spec") -> None:
    for name in GOLDEN:
        stage(project / leg, name, '{"case": 1}\n')


# --- N7: the doctor takes a recorded answer as the answer -------------------

def test_an_answered_question_is_not_asked_again_in_its_leg(standard,
                                                           project):
    """`spec/examples/` is the policy's question; a row answering it `spec`
    settles it there. The row is `ok`, names where the answer came from,
    and `--json` lists it under `answered`, never under `review_required`.
    """
    golden_run(project)
    asked = placement(standard, project)[2]
    assert [row["path"] for row in asked["detail"]["review_required"]] == [
        ASKED], asked
    record_answers(project, (EXAMPLES, "spec", EXAMPLES_ANSWER))
    result, verdict, row = placement(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == COMPLIANT
    assert rows_of(result)["manifest"]["status"] == "ok"
    assert row["status"] == "ok", row
    assert row["detail"]["review_required"] == [], row["detail"]
    assert row["detail"]["counts"]["answered"] == 1
    [answered] = row["detail"]["answered"]
    assert (answered["path"], answered["rule"], answered["recorded_leg"],
            answered["answered_by"], answered["resolution"],
            answered["review_required"]) == (
        ASKED, "ambiguous-examples", "spec", [EXAMPLES],
        EXAMPLES_ANSWER, False), answered
    assert row["reason"].startswith(
        "every tracked path classifies as the leg it is in or is answered "
        "there; project.yaml's `answered_paths:` answers the question the "
        "policy asks of 1 path(s) (#525): spec/examples/ (rule "
        "ambiguous-examples)  ["), row["reason"]
    assert row["next"] is None, row


def test_an_answer_for_the_other_leg_leaves_the_question_asked(standard,
                                                               project):
    """RECORDS CONFER NOTHING. A row answering `examples/` into the code leg
    is no answer to the spec leg's `examples/`, which is another
    repository's file: the question stands, a `note`, and nothing is
    MISPLACED."""
    golden_run(project)
    record_answers(project, (EXAMPLES, "code", EXAMPLES_ANSWER))
    result, verdict, row = placement(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == COMPLIANT
    assert row["status"] == "note", row
    assert row["detail"]["misplaced"] == []
    assert [item["path"] for item in row["detail"]["review_required"]] == [
        ASKED]
    assert "answered" not in row["detail"], row["detail"]


@pytest.mark.parametrize("rows, answered", [
    ((("examples/golden/case.json", "spec"),
      ("examples/golden/case.expected.json", "spec")), True),
    ((("examples/golden/", "spec"),), True),
    ((("examples/golden/case.json", "spec"),), False),
    ((("examples/golden/case.json", "spec"),
      ("examples/golden/case.expected.json", "code")), False),
], ids=["every-file-its-own-row", "a-directory-row", "one-file-unanswered",
        "one-file-the-other-leg"])
def test_a_question_is_answered_file_by_file(standard, project, rows,
                                             answered):
    """The doctor's walk folds a leg's files as they fall there, not as the
    source's fell, so a question is answered only when every file under it
    is, by exactly one row that names this leg."""
    golden_run(project)
    record_answers(project, *rows)
    row = placement(standard, project)[2]
    asked = [item["path"] for item in row["detail"]["review_required"]]
    assert asked == ([] if answered else [ASKED]), row["detail"]
    assert row["status"] == ("ok" if answered else "note"), row


def test_gitmodules_is_answered_by_the_submodule_record_alone(standard,
                                                              project):
    """`.gitmodules` asks which leg owns the submodules it registers, and
    only `submodules:` answers that, where it places every one (#189). A
    row of `answered_paths:` naming it settles nothing: beside a submodule
    added by hand, the file stays the question it was."""
    stage_gitlink(project / "code", "vendor/lib")
    stage(project / "code", GITMODULES,
          '[submodule "vendor/lib"]\n\tpath = vendor/lib\n'
          "\turl = https://example.invalid/lib.git\n")
    record_answers(project, (GITMODULES, "code", RULES_ANSWER))
    row = placement(standard, project)[2]
    assert [item["path"] for item in row["detail"]["review_required"]] == [
        "code/.gitmodules"], row["detail"]
    assert "answered" not in row["detail"], row["detail"]


def test_an_answer_no_leg_holds_is_silent(standard, project):
    """A recorded answer can only settle a question, never make a finding,
    so one whose path has gone says nothing: the report is the scaffold's
    own, word for word."""
    before = placement(standard, project)[2]
    record_answers(project, (EXAMPLES, "spec", EXAMPLES_ANSWER))
    result, verdict, row = placement(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (verdict, row["status"], row["reason"]) == (
        COMPLIANT, "ok", before["reason"]), row


# --- L1-08: a submodule moved, and one removed ------------------------------

def moved_rules(project: Path, *, gitmodules: bool = False) -> None:
    """`vendor/rules` recorded in the code leg and held by the spec leg
    alone: the move, already made in both legs."""
    stage_gitlink(project / "spec", RULES_PATH)
    if gitmodules:
        stage(project / "spec", GITMODULES,
              '[submodule "vendor/rules"]\n\tpath = vendor/rules\n'
              "\turl = https://example.invalid/rules.git\n")
    record_submodules(project, (RULES_PATH, "code", RULES_ANSWER))


@pytest.mark.parametrize("gitmodules", [False, True],
                         ids=["the-gitlink", "with-its-gitmodules"])
def test_a_submodule_moved_in_both_legs_names_its_row_not_a_plan(
        standard, project, gitmodules):
    """STILL MISPLACED, NO LONGER A PLAN. The record names the code leg,
    which holds no `vendor/rules`, and the spec leg holds it: the move is
    made, and the plan `--placement-plan` writes would be that move again.
    The row says it moved; its NEXT is this doctor again and its WHY gives
    both ways out, the row edited by hand or the move undone. The spec
    leg's `.gitmodules`, a question only because the row names the other
    leg, goes with the move."""
    moved_rules(project, gitmodules=gitmodules)
    result, verdict, row = placement(standard, project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict == "MISPLACED (1 path)"
    assert row["status"] == "FINDING", row
    [moved] = row["detail"]["misplaced"]
    assert (moved["path"], moved["moved"]) == ("spec/vendor/rules", True)
    assert MOVED_CLAUSE in row["reason"], row["reason"]
    assert row["next"] == doctor_again(standard, project), row["next"]
    assert row["why"] == doctor_module(standard).MOVED_BY_HAND
    for said in ("`leg:` to the leg it is in", "`source_commit:` deleted",
                 "in the pull request that bumps the pins",
                 "a pull request on each leg and a pin bump in the root"):
        assert said in row["why"], (said, row["why"])
    text = doctor(standard, project)
    assert verdict_line(text).startswith("MISPLACED (1 path)   (exit 1)")
    assert f"NEXT             {row['next']}" in text.stdout, text.stdout


@pytest.mark.parametrize("also, moved", [
    ("code-holds-it-too", False), ("a-question-beside", True),
    ("code-leg-unread", False)])
def test_a_move_not_made_in_both_legs_keeps_the_plan(standard, project,
                                                     also, moved):
    """WHERE NOT EVERYTHING IS A MOVE ALREADY MADE, THE PLAN STAYS. Both legs
    holding it is a move half made, and a recorded leg nobody could read
    could hold it: neither is said to have moved. A question beside a move
    is the plan's to write, so the plan is the NEXT, and the move is still
    said."""
    moved_rules(project)
    if also == "code-holds-it-too":
        stage_gitlink(project / "code", RULES_PATH)
    elif also == "a-question-beside":
        golden_run(project)
    else:
        shutil.rmtree(project / "code")
        (project / "code").mkdir()
    row = placement(standard, project)[2]
    assert row["status"] == "FINDING", row
    assert row["next"].endswith("--placement-plan placement-plan.yaml"), row
    assert [bool(item.get("moved")) for item in row["detail"]["misplaced"]
            ] == [moved], row["detail"]["misplaced"]
    assert (MOVED_CLAUSE in row["reason"]) == moved, row["reason"]


def test_a_row_no_leg_holds_is_a_note(standard, project):
    """REMOVING A SUBMODULE IS NOT WRONG. Its row lingering is said -- a
    `note`, `detail.unheld` -- and never a finding, with no NEXT."""
    record_submodules(project, (RULES_PATH, "code", RULES_ANSWER))
    result, verdict, row = placement(standard, project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == COMPLIANT
    assert row["status"] == "note", row
    assert row["detail"]["unheld"] == [{
        "path": RULES_PATH, "recorded_leg": "code",
        "resolution": RULES_ANSWER}], row["detail"]
    assert row["detail"]["counts"]["unheld"] == 1
    assert ("project.yaml's `submodules:` records 1 submodule(s) no leg "
            "holds (#525): vendor/rules (recorded in the code leg); one "
            "removed on purpose has its row deleted by hand, in the pull "
            "request that removed it") in row["reason"], row["reason"]
    assert row["next"] is None, row


def test_a_row_is_not_called_unheld_where_a_leg_was_not_read(standard,
                                                             project):
    """A leg nobody could read could hold it: nothing is said."""
    record_submodules(project, (RULES_PATH, "code", RULES_ANSWER))
    shutil.rmtree(project / "code")
    (project / "code").mkdir()
    row = placement(standard, project)[2]
    assert "unheld" not in row["detail"], row["detail"]


def test_agents_md_says_who_edits_a_row_and_when():
    """The way out the doctor's WHY names is the one AGENTS.md gives: a row
    is the human's, edited by hand in the pull request that bumps the pins,
    and that is not the manifest edit Checking 3 forbids."""
    said = " ".join((REPO / "AGENTS.md").read_text(encoding="utf-8").split())
    assert ("A move or removal the human decided is recorded by editing its "
            "row by hand, in the pull request that bumps the pins: that is "
            "not the edit 3 forbids.") in said
    assert "no command rewrites them" in said


# --- the record `execute` writes ---------------------------------------------

def tree_of(*rows: tuple) -> list:
    """`Source.tree()`'s shape: `(path, mode, oid, size)`, sorted."""
    return sorted((path, mode, "0" * 40, 1) for path, mode in rows)


#: A source's tree: what the rules call, what they cannot, and a submodule.
SOURCE_TREE = tree_of(
    (README, BLOB), ("src/app/util.py", BLOB),
    ("docs/index.md", BLOB), ("examples/a/case.json", BLOB),
    ("examples/b/case.json", BLOB), (GITMODULES, BLOB),
    (RULES_PATH, "160000"), ("vendor/data.csv", BLOB))
SOURCE_COMMIT = "ab" * 20


def plan_entries(**legs: str) -> list:
    """Plan entries covering `SOURCE_TREE`, each `path=leg`, with a reason
    on every one; `_` in a keyword stands for `/` and `dot_` for `.`."""
    return [{"path": path.replace("dot_", ".").replace("_", "/"),
             "leg": leg, "resolution": f"why {leg}"}
            for path, leg in legs.items()]


@pytest.mark.parametrize("answers, rows", [
    ({"examples_": "spec"}, [(EXAMPLES, "spec")]),
    ({"examples_": "root"}, []),
    ({"examples_": "drop"}, []),
    ({"examples_a_": "spec", "examples_b_": "code"},
     [("examples/a/", "spec"), ("examples/b/", "code")]),
    ({"examples_": "spec", "docs_": "code"}, [(EXAMPLES, "spec")]),
], ids=["answered-spec", "answered-root", "answered-drop", "split-by-hand",
        "a-confident-rule-overridden"])
def test_execute_records_the_policys_own_questions_answered_into_a_leg(
        standard, answers, rows):
    """ONE ROW PER ENTRY KEPT IN A LEG THAT COVERS A PATH THE POLICY LEAVES
    `leg: null`, read from the policy's own walk and not the plan's edited
    `review_required:`: an entry split by hand is each half its own row.
    `root` and `drop` are in no leg. `.gitmodules` and a gitlink are
    `submodules:`'s, and `vendor/` is recorded only because the policy
    cannot call the file beside its gitlink. A path a confident rule called
    and the plan answered the other way is not a question the policy asked
    (outside #525)."""
    adopt = adoption_module(standard)
    legs = {README: "root", "src_": "code", "docs_": "spec",
            "dot_gitmodules": "code", "vendor_": "code", **answers}
    entries = plan_entries(**{key: leg for key, leg in legs.items()
                              if key != README})
    entries.append({"path": README, "leg": "root"})
    block = adopt.answered_path_record(adopt.PathPolicy.load(
        adopt.PATH_POLICY), entries, SOURCE_TREE, SOURCE_COMMIT)
    recorded = parse_yaml(block)["answered_paths"] if block else []
    expected = sorted(rows + [("vendor/", "code")])
    assert [(row["path"], row["leg"]) for row in recorded] == expected
    assert all(row["resolution"] == f"why {row['leg']}"
               and row["source_commit"] == SOURCE_COMMIT
               for row in recorded), recorded


def test_a_plan_that_answered_no_question_into_a_leg_appends_nothing(
        standard):
    """THE MANIFEST IT ALWAYS GOT. No question of the policy's answered into
    a leg -- only `.gitmodules` and a gitlink, which `submodules:` answers,
    and paths the rules call -- and the record is "", which `execute` adds
    to nothing."""
    adopt = adoption_module(standard)
    tree = [row for row in SOURCE_TREE
            if not row[0].startswith((EXAMPLES, "vendor/data"))]
    entries = plan_entries(src_="code", docs_="spec", dot_gitmodules="code",
                           vendor_="code")
    entries.append({"path": README, "leg": "root"})
    assert adopt.answered_path_record(
        adopt.PathPolicy.load(adopt.PATH_POLICY), entries, tree,
        SOURCE_COMMIT) == ""


# --- end to end: `execute`, then the doctor ---------------------------------

def adopt_source(standard: Path, base: Path, answers: dict) -> dict:
    """A source with a golden run under `examples/` and the editor rules as
    a submodule at `vendor/rules`, planned, answered as `answers` says
    (`{entry: (leg, resolution)}`), executed into local remotes and cloned
    recursively from the split branch."""
    dependency = base / "rules"
    dependency.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=dependency)
    (dependency / "rules.md").write_text("editor rules\n", encoding="utf-8")
    commit_all(dependency, "rules")
    source = base / "Thing"
    source.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=source)
    for name, body in ((README, "# Thing\n"),
                       ("src/app/util.py", "VALUE = 1\n"),
                       ("docs/index.md", "# Docs\n"),
                       *((name, '{"case": 1}\n') for name in GOLDEN)):
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(body, encoding="utf-8")
    commit_all(source, "init")
    git(*FILE_PROTOCOL, "submodule", "add", "-q", str(dependency),
        RULES_PATH, cwd=source)
    commit_all(source, "vendor the editor rules")
    adopt = standard / "adopt-project.py"
    plan = base / "adoption-plan.yaml"
    written = run_script(adopt, "plan", "--source", str(source), "--project",
                         "Northwind", "--org", ORG, "--elected-by", "T",
                         "--elected-on", "2026-10-15", "--out", str(plan))
    assert written.returncode == 0, written.stdout + written.stderr
    text = plan.read_text(encoding="utf-8")
    for path, (leg, why) in answers.items():
        needle = f"  - path: {path}\n    leg: null\n"
        assert needle in text, (path, text)
        text = text.replace(needle, f"  - path: {path}\n    leg: {leg}\n"
                            f'    resolution: "{why}"\n')
    plan.write_bytes(text.encode("utf-8"))
    done = run_script(adopt, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))
    assert done.returncode == 0, done.stdout + done.stderr
    assert "adoption verified" in done.stdout, done.stdout
    clone = base / "clone"
    proc = clone_just_pushed(source, clone, branch="adopt/three-repo-shape")
    assert proc.returncode == 0, proc.stderr
    return {"clone": clone, "dependency": dependency,
            "commit": git("rev-parse", "main", cwd=source).stdout.strip()}


#: Each plan's answers to the submodule question: `.gitmodules` and the
#: entry holding the gitlink, into the code leg.
RULES_IN_CODE = {GITMODULES: ("code", RULES_ANSWER),
                 "vendor/": ("code", RULES_ANSWER)}


@pytest.fixture(scope="module")
def adopted_golden(standard, tmp_path_factory) -> dict:
    """`examples/` answered into the spec leg, the rules into the code leg."""
    return adopt_source(standard, tmp_path_factory.mktemp("answered"),
                        {EXAMPLES: ("spec", EXAMPLES_ANSWER),
                         **RULES_IN_CODE})


@pytest.fixture
def golden_clone(adopted_golden, tmp_path) -> Path:
    """A private, mutable copy of that clone."""
    target = tmp_path / "Northwind"
    shutil.copytree(adopted_golden["clone"], target, symlinks=True)
    return target


@needs_filter_repo
def test_execute_records_the_answer_and_the_doctor_asks_no_more(
        standard, adopted_golden, golden_clone):
    """N7, END TO END. The split's manifest answers `examples/` beside the
    submodule's row, and the doctor, which asked `spec/examples/` on main,
    reads the adoption COMPLIANT with the row `ok`."""
    manifest = parse_yaml((golden_clone / "project.yaml").read_text(
        encoding="utf-8"))
    commit = adopted_golden["commit"]
    assert manifest["answered_paths"] == [{
        "path": EXAMPLES, "leg": "spec", "resolution": EXAMPLES_ANSWER,
        "source_commit": commit}], manifest["answered_paths"]
    assert manifest["submodules"] == [{
        "path": RULES_PATH, "leg": "code", "resolution": RULES_ANSWER,
        "source_commit": commit}], manifest["submodules"]
    result, verdict, row = placement(standard, golden_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == COMPLIANT
    assert row["status"] == "ok", row
    assert row["detail"]["review_required"] == [], row["detail"]
    assert [item["path"] for item in row["detail"]["answered"]] == [
        ASKED]


def the_rules_row(commit: str) -> str:
    """The `submodules:` row `execute` wrote for `vendor/rules`."""
    return ('  - path: "vendor/rules"\n    leg: code\n'
            f'    resolution: "{RULES_ANSWER}"\n'
            f'    source_commit: "{commit}"\n')


def edit_manifest(root: Path, old: str, new: str) -> None:
    """The person's hand edit, in bytes, so the file keeps its LF endings."""
    manifest = root / "project.yaml"
    text = manifest.read_text(encoding="utf-8")
    assert text.count(old) == 1, text
    manifest.write_bytes(text.replace(old, new).encode("utf-8"))


def drop_the_rules(leg: Path) -> None:
    """`git rm` of the submodule, and of the `.gitmodules` it empties."""
    git("rm", "-q", RULES_PATH, cwd=leg)
    if not (leg / GITMODULES).read_text(encoding="utf-8").strip():
        git("rm", "-q", "-f", GITMODULES, cwd=leg)


@needs_filter_repo
def test_a_move_made_in_both_legs_is_finished_by_its_row(
        standard, adopted_golden, golden_clone):
    """L1-08, END TO END. The rules leave the code leg and join the spec
    leg as `git` does it: MISPLACED, the doctor's own line as the NEXT. The
    person then edits the row as the WHY says -- `leg:`, `resolution:`, no
    `source_commit:` -- and the doctor and the project's validator agree."""
    drop_the_rules(golden_clone / "code")
    git(*FILE_PROTOCOL, "submodule", "add", "-q",
        str(adopted_golden["dependency"]), RULES_PATH,
        cwd=golden_clone / "spec")
    result, verdict, row = placement(standard, golden_clone)
    assert result.returncode == 1, result.stdout + result.stderr
    assert verdict == "MISPLACED (1 path)"
    assert MOVED_CLAUSE in row["reason"], row["reason"]
    assert row["next"] == doctor_again(standard, golden_clone), row["next"]
    edit_manifest(golden_clone, the_rules_row(adopted_golden["commit"]),
                  '  - path: "vendor/rules"\n    leg: spec\n'
                  '    resolution: "the spec leg reads the rules now"\n')
    result, verdict, row = placement(standard, golden_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert verdict == COMPLIANT
    assert rows_of(result)["manifest"]["status"] == "ok"
    assert row["status"] == "ok", row


@needs_filter_repo
def test_a_removed_submodule_is_a_note_until_its_row_is_deleted(
        standard, adopted_golden, golden_clone):
    """L1-08's other half, END TO END: the rules removed, the row is a
    `note`, COMPLIANT; the row deleted, the placement row is `ok` again."""
    drop_the_rules(golden_clone / "code")
    result, verdict, row = placement(standard, golden_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (verdict, row["status"]) == (COMPLIANT, "note"), row
    assert [item["path"] for item in row["detail"]["unheld"]] == [
        RULES_PATH]
    edit_manifest(golden_clone, the_rules_row(adopted_golden["commit"]), "")
    result, verdict, row = placement(standard, golden_clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert rows_of(result)["manifest"]["status"] == "ok"
    assert row["status"] == "ok", row


@pytest.fixture(scope="module")
def adopted_unasked(standard, tmp_path_factory) -> dict:
    """The same source with `examples/` kept in the root: no question of
    the policy's answered into a leg."""
    return adopt_source(standard, tmp_path_factory.mktemp("unasked"),
                        {EXAMPLES: ("root", EXAMPLES_ANSWER),
                         **RULES_IN_CODE})


@needs_filter_repo
def test_a_split_with_no_answered_question_gets_the_manifest_it_always_got(
        standard, adopted_unasked):
    """BYTE FOR BYTE. What `execute` appends to `project.yaml` is the #189
    block and nothing after it: no `answered_paths:` key, and the file ends
    on the submodule's row exactly as `submodule_record` writes it."""
    adopt = adoption_module(standard)
    text = (adopted_unasked["clone"] / "project.yaml").read_bytes()
    block = ("\n".join(adopt.SUBMODULE_RECORD_PREAMBLE) + "\n"
             + the_rules_row(adopted_unasked["commit"])).encode("utf-8")
    assert text.endswith(block), text[-600:]
    assert b"answered_paths" not in text
