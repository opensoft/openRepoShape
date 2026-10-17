# SPDX-License-Identifier: Apache-2.0
"""A directory split by hand is recorded as each leg's own walk reads it,
so the doctor's first run after `adoption verified` reads it COMPLIANT
(#801: #457's L1-83).

THE DEFECT, on main bf1f099b. The source's `engine/` holds `a.py`, `b.py`,
`c.py` and `x.md`: 3 of 4 files `.py`, exactly the policy's
`extension_majority: 0.75`, so `plan` proposes `engine/` -> code. Split by
hand -- `engine/c.py` into the spec leg, the other three into the code leg,
each with a `resolution:` -- the plan passed `check`, and `execute` said
`adoption verified`. The doctor's first run then said `MISPLACED (1 path)`,
exit 1: `code/engine/x.md: spec by rule extension-majority`.
`answered_path_record` walked the whole source, where `engine/` folds to
code and `x.md` needs no row. The doctor walks the code leg, where
`engine/` is 2 of 3 `.py` (67%), and reads each file by its own extension.

The same split reaches the same disagreement with `engine/c.py` dropped or
kept in the root, in a directory the majority groups to spec, nested one
directory down, and as a question where the file left over has an
extension no class names: a `note` there, and not `ok`.

THE FIX. `answered_path_record` also walks each leg's own files, as the
doctor walks that leg, and records each entry kept in a leg that covers a
path that walk puts elsewhere. The doctor is unchanged, and a plan left as
`plan` wrote it gets the record main writes, byte for byte.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from conftest import REPO, clone_just_pushed, git, run_script
from test_doctor_recorded_answers import placement, tree_of
from test_shape_doctor import (  # noqa: F401
    ORG, adoption_module, commit_all, needs_filter_repo, standard,
)

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import parse_yaml  # noqa: E402

BLOB = "100644"
COMPLIANT = "COMPLIANT"
SOURCE_COMMIT = "ef" * 20
#: The `resolution:` every entry split out of a directory carries.
BY_HAND = "split by hand"
ENGINE = "engine/"
A_PY = "engine/a.py"
B_PY = "engine/b.py"
C_PY = "engine/c.py"
X_MD = "engine/x.md"
#: Beside every source below: a front door the root keeps and a
#: requirement the spec leg keeps, so that neither leg is seeded.
BESIDE = {"README.md": "# Thing\n", "requirements/r.md": "# Requirement\n"}
#: The issue's `engine/`: 3 of 4 files `.py`, exactly the 75% majority.
ENGINE_FILES = {A_PY: "A = 1\n", B_PY: "B = 1\n", C_PY: "C = 1\n",
                X_MD: "# Notes\n"}
#: The two `.py` files the split leaves in the code leg.
KEPT = ((A_PY, "code"), (B_PY, "code"))

#: `{case: (the source's files beside BESIDE, the entry `plan` writes for
#: them, the entries a person splits it into, the rows `answered_paths:`
#: needs)}`. Each split is one the doctor's first run disputed on main.
SPLITS = {
    "the-issue": (ENGINE_FILES, ENGINE,
                  (*KEPT, (C_PY, "spec"), (X_MD, "code")),
                  [(C_PY, "spec"), (X_MD, "code")]),
    "the-other-file-dropped": (ENGINE_FILES, ENGINE,
                               (*KEPT, (C_PY, "drop"), (X_MD, "code")),
                               [(X_MD, "code")]),
    "the-other-file-in-the-root": (ENGINE_FILES, ENGINE,
                                   (*KEPT, (C_PY, "root"), (X_MD, "code")),
                                   [(X_MD, "code")]),
    # 3 of 4 `.md`, so `notes/` goes to spec; one `.md` taken to code
    # leaves `notes/y.py` read as code in the spec leg.
    "a-spec-majority-split": (
        {"notes/a.md": "# A\n", "notes/b.md": "# B\n", "notes/c.md": "# C\n",
         "notes/y.py": "Y = 1\n"}, "notes/",
        (("notes/a.md", "spec"), ("notes/b.md", "spec"),
         ("notes/c.md", "code"), ("notes/y.py", "spec")),
        [("notes/c.md", "code"), ("notes/y.py", "spec")]),
    # One directory down: the row the code leg needs is the directory's.
    "a-nested-split": (
        {A_PY: "A = 1\n", B_PY: "B = 1\n", C_PY: "C = 1\n",
         "engine/notes/x.md": "# Notes\n"}, ENGINE,
        (*KEPT, (C_PY, "spec"), ("engine/notes/", "code")),
        [(C_PY, "spec"), ("engine/notes/", "code")]),
    # An extension no class names is a question once it is outvoted no
    # more: a `note` on main, not MISPLACED.
    "a-question-left-over": (
        {A_PY: "A = 1\n", B_PY: "B = 1\n", C_PY: "C = 1\n",
         "engine/q.zzz": "q\n"}, ENGINE,
        (*KEPT, (C_PY, "spec"), ("engine/q.zzz", "code")),
        [(C_PY, "spec"), ("engine/q.zzz", "code")]),
}

#: The controls, which main records the same way: a split whose rest still
#: clears 75%, and `engine/` as `plan` wrote it.
CONTROLS = {
    "the-rest-clears-the-majority": (
        {**ENGINE_FILES, "engine/d.py": "D = 1\n"}, ENGINE,
        (*KEPT, (C_PY, "spec"), ("engine/d.py", "code"), (X_MD, "code")),
        [(C_PY, "spec")]),
    "left-as-plan-wrote-it": (ENGINE_FILES, ENGINE, ((ENGINE, "code"),), []),
}
CASES = {**SPLITS, **CONTROLS}


def record_of(adopt, files: dict, parts: tuple) -> str:
    """`answered_path_record` over BESIDE and `files`, for a plan keeping
    the README in the root, `requirements/` in the spec leg, and each
    `(path, leg)` of `parts` with BY_HAND as its `resolution:`."""
    entries = [{"path": "README.md", "leg": "root"},
               {"path": "requirements/", "leg": "spec"}]
    entries += [{"path": path, "leg": leg, "resolution": BY_HAND}
                for path, leg in parts]
    tree = tree_of(*((path, BLOB) for path in {**BESIDE, **files}))
    return adopt.answered_path_record(
        adopt.PathPolicy.load(adopt.PATH_POLICY), entries, tree,
        SOURCE_COMMIT)


def rows_of(text: str) -> list:
    """`(path, leg)` for each `answered_paths:` row `text` holds, or []."""
    return [(row["path"], row["leg"])
            for row in ((parse_yaml(text) or {}).get("answered_paths") or [])]


# --- the record `execute` writes ---------------------------------------------

def test_the_issues_split_records_the_file_the_code_legs_walk_disputes(
        standard):
    """#801's LINE, THE RECORD. In the code leg `engine/` is 2 of 3 `.py`,
    so `engine/x.md` reads as spec there: it is recorded in the code leg
    with the plan's reason and commit, beside `engine/c.py` in the spec
    leg, which main already recorded."""
    block = record_of(adoption_module(standard), ENGINE_FILES,
                      SPLITS["the-issue"][2])
    assert parse_yaml(block)["answered_paths"] == [
        {"path": path, "leg": leg, "resolution": BY_HAND,
         "source_commit": SOURCE_COMMIT}
        for path, leg in ((C_PY, "spec"), (X_MD, "code"))], block


@pytest.mark.parametrize("case", list(CASES))
def test_each_entry_a_legs_own_walk_puts_elsewhere_is_recorded(standard,
                                                               case):
    """ONE ROW PER ENTRY KEPT IN A LEG THAT COVERS A PATH THAT LEG'S OWN
    WALK PUTS ELSEWHERE, as the doctor walks the leg: a file left outvoted
    no more, a directory one level down, a question. Where the rest still
    clears the majority, or `engine/` is kept whole, the record is main's.
    """
    files, _, parts, rows = CASES[case]
    assert rows_of(record_of(adoption_module(standard), files, parts)) == rows


def test_a_plan_left_as_plan_wrote_it_gets_mains_record_byte_for_byte(
        standard):
    """BYTE FOR BYTE. `engine/` kept whole beside a question answered
    (`examples/`) and an answer against a rule (`docs/`, #655): the block
    is main's, its comment and those two rows and nothing for `engine/`;
    and `engine/` alone gets "", so the `project.yaml` it always got."""
    adopt = adoption_module(standard)
    files = {**ENGINE_FILES, "docs/index.md": "# Docs\n",
             "examples/golden/case.json": '{"case": 1}\n'}
    answered = (("docs/", "code"), ("examples/", "spec"))
    block = record_of(adopt, files, ((ENGINE, "code"), *answered))
    assert block == "\n".join(adopt.ANSWER_RECORD_PREAMBLE) + "\n" + "".join(
        f'  - path: "{path}"\n    leg: {leg}\n    resolution: "{BY_HAND}"\n'
        f'    source_commit: "{SOURCE_COMMIT}"\n' for path, leg in answered)
    assert record_of(adopt, ENGINE_FILES, ((ENGINE, "code"),)) == ""


# --- end to end: `execute`, then the doctor ---------------------------------

def split_by_hand(text: str, entry: str, parts: tuple) -> str:
    """The plan `text` with `entry`'s block -- its `- path:` line and every
    line indented under it -- replaced by one entry per `(path, leg)` of
    `parts`, each with BY_HAND as its `resolution:`."""
    entries = "".join(f'  - path: {path}\n    leg: {leg}\n'
                      f'    resolution: "{BY_HAND}"\n' for path, leg in parts)
    out, count = re.subn(rf"(?m)^  - path: {re.escape(entry)}\n(?:    .*\n)*",
                         lambda _: entries, text)
    assert count == 1, text
    return out


def adopt_split(standard: Path, base: Path, case: str) -> dict:
    """CASES[case]'s source committed, planned, its entry split by hand --
    or, where the case keeps it whole, left exactly as `plan` wrote it --
    executed into local remotes, and cloned from the split branch."""
    files, entry, parts, _ = CASES[case]
    source = base / "Thing"
    for name, body in {**BESIDE, **files}.items():
        (source / name).parent.mkdir(parents=True, exist_ok=True)
        (source / name).write_text(body, encoding="utf-8")
    git("init", "-q", "-b", "main", ".", cwd=source)
    commit_all(source, "a directory its extensions fold")
    tool = standard / "adopt-project.py"
    plan = base / "plan.yaml"
    planned = run_script(tool, "plan", "--out", str(plan), "--source",
                         str(source), "--org", ORG, "--project", "Northwind",
                         "--elected-on", "2026-10-17", "--elected-by", "T")
    assert planned.returncode == 0, planned.stderr
    text = plan.read_text(encoding="utf-8")
    if [path for path, _ in parts] == [entry]:
        assert f"  - path: {entry}\n    leg: {parts[0][1]}\n" in text, text
    else:
        plan.write_bytes(split_by_hand(text, entry, parts).encode("utf-8"))
    executed = run_script(tool, "execute", "--yes", "--plan", str(plan),
                          "--work-dir", str(base / "work"),
                          "--local-remote-dir", str(base / "remotes"))
    assert (executed.returncode, "adoption verified" in executed.stdout) == (
        0, True), executed.stdout + executed.stderr
    cloned = clone_just_pushed(source, base / "clone",
                               branch="adopt/three-repo-shape")
    assert cloned.returncode == 0, cloned.stderr
    return {"clone": base / "clone",
            "commit": git("rev-parse", "HEAD", cwd=source).stdout.strip()}


@pytest.fixture(scope="module")
def adopted_the_issue(standard, tmp_path_factory) -> dict:
    """The issue's split, adopted."""
    return adopt_split(standard, tmp_path_factory.mktemp("the-issue"),
                       "the-issue")


@needs_filter_repo
def test_the_issues_split_is_compliant_on_the_doctors_first_run(
        standard, adopted_the_issue):
    """#801's LINE, END TO END. The split's manifest records `engine/x.md`
    in the code leg beside `engine/c.py` in the spec leg, and the doctor's
    first run, which said `MISPLACED (1 path)` on main, reads the adoption
    COMPLIANT with the row `ok`, the code leg's `engine/x.md` answered by
    its row."""
    clone = adopted_the_issue["clone"]
    manifest = parse_yaml((clone / "project.yaml").read_text(encoding="utf-8"))
    assert manifest["answered_paths"] == [
        {"path": path, "leg": leg, "resolution": BY_HAND,
         "source_commit": adopted_the_issue["commit"]}
        for path, leg in ((C_PY, "spec"), (X_MD, "code"))], manifest
    result, verdict, row = placement(standard, clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (verdict, row["status"], row["detail"]["misplaced"]) == (
        COMPLIANT, "ok", []), row
    assert [(item["path"], item["answered_by"])
            for item in row["detail"]["answered_paths"]] == [
        ("spec/engine/", [C_PY]), ("code/engine/x.md", [X_MD])], row["detail"]


@pytest.fixture(scope="module", params=[case for case in CASES
                                        if case not in (
                                            "the-issue",
                                            "the-other-file-in-the-root")])
def adopted_by_hand(request, standard, tmp_path_factory) -> dict:
    """Each other case but the root's, which differs from the drop's only
    in the root, adopted."""
    return {"case": request.param,
            **adopt_split(standard, tmp_path_factory.mktemp(request.param),
                          request.param)}


@needs_filter_repo
def test_each_split_by_hand_is_compliant_on_the_doctors_first_run(
        standard, adopted_by_hand):
    """END TO END, EVERY OTHER WAY IN. Each manifest holds the rows its
    legs' walks need, and no `answered_paths:` at all where none is
    needed; the doctor's first run reads each adoption COMPLIANT with the
    row `ok`."""
    clone = adopted_by_hand["clone"]
    text = (clone / "project.yaml").read_text(encoding="utf-8")
    rows = CASES[adopted_by_hand["case"]][3]
    assert (rows_of(text), "answered_paths" in text) == (rows, bool(rows)), \
        text
    result, verdict, row = placement(standard, clone)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (verdict, row["status"]) == (COMPLIANT, "ok"), row
