# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` name the same first problem of a plan against its
source (#1113): a plan for another repository (`plan-not-the-source`), a
name the naming policy refuses (`naming-unclassified`), a source that has
moved on since `plan` (`plan-stale`) and an unanswered entry
(`plan-unresolved`).

ON #1125'S HEAD 9549006f, with a stub `gh` and local remotes, as #1113
measured them on main at 16f9a0e81, `check` listed a moved source first,
then the plan's entries, then another repository and then the names, and
`execute` refused another repository, then a refused name, then an
unanswered entry and then a moved source. So five of the six pairs of these
four were named differently by the two commands, `check`'s first finding
against `execute`'s refusal:
- a moved source and an unanswered entry: `plan-stale` against
  `plan-unresolved`;
- another repository and an unanswered entry: `plan-unresolved` against
  `plan-not-the-source`;
- another repository and a moved source: `plan-stale` against
  `plan-not-the-source`;
- a refused name and an unanswered entry: `plan-unresolved` against
  `naming-unclassified`;
- a refused name and a moved source: `plan-stale` against
  `naming-unclassified`.

The first four are #1113's table; the fifth is not in it, and the same rule
decides it. The sixth pair, another repository beside a refused name, was
`plan-not-the-source` to both, and still is.

ONE RULE, `_against_its_source`, read by both commands: `execute` refuses
the first of its problems, and `check` lists each of them, in its order,
before the split branch and the entries. The order is the one a person
mends them in: another repository, a refused name, a moved source, an
unanswered entry. Each of the first three is mended by running `plan` again,
and a fresh plan takes back every answer given before, so an unanswered
entry, mended by an answer in the plan, comes last.

WHERE THE RULE SITS AMONG THE OTHER FINDINGS. `check` lists the rule's
problems before the split branch and the entries, and `execute` asks the
rule before every refusal `check` lists after it and before the plan's
values (`_checked_plan_values`, #499). A row beside an ordinary finding pins
each: the source keeps a branch `adopt`, which `check` finds as
`plan-split-branch-taken` after the rule's problems (`check` lists it
before the entries), or the plan's `tracking_branch:` is a value `execute`
refuses as `unsafe-value` once the rule's problem is not in the way.

AN UNANSWERED ENTRY, TOO (#1197). On #1210's head 791106c2, `execute`
refused an unanswered entry with the rule, before all of these, and `check`
listed it with the entries, after the split branch taken, the source's own
paths, the coverage, the leg paths and a bad `leg:` on an entry before it.
So beside any of those the two named different problems first:
`plan-uncovered` against `plan-unresolved`, and the same for
`plan-split-branch-taken`, `plan-unsafe-path`, `plan-empty-entry`,
`plan-duplicate-path`, `plan-covered-twice`, `plan-bad-leg-path`,
`plan-leg-path-collides`, `plan-bad-leg` and `plan-empty-symlink`. `check`
now lists an unanswered entry with the rule's other problems, so both name
it first. Each of those findings alone is named by both, as before.

Each row runs `check` and then `execute --yes` on one plan, hand-edited in
every row but the empty link's, which `plan` writes as it is (#1197), both
with the same `--local-remote-dir`, so no `gh` runs and no remote is asked,
and asserts that no leg was made. `execute` refuses every plan here before
it reads a remote: it asks for `git filter-repo` first, so the rows skip
where it is not installed.
"""

from __future__ import annotations

import re

import pytest

from conftest import git, make_source_repo, planned
from test_adopt_pins import ANSWERS
from test_adopt_plan_value_order import (
    ANOTHER_ORG, BAD_LEG_PATH, BAD_TRACKING_BRANCH, REFUSED_NAME, both_on,
    edited, findings_of, named_first, needs_filter_repo, planned_with)

ANOTHER = "plan-not-the-source"
NAME = "naming-unclassified"
MOVED = "plan-stale"
UNANSWERED = "plan-unresolved"
#: Two ordinary findings, which `check` lists after the rule's problems and
#: `execute` refuses only once none of them is in the way: the split branch
#: taken, and an unsafe `tracking_branch:`.
TAKEN = "plan-split-branch-taken"
TRACKING = "unsafe-value"
#: More ordinary findings, each of which `check` listed before an
#: unanswered entry on 791106c2 (#1197).
UNCOVERED = "plan-uncovered"
BAD_LEG = "plan-bad-leg"
EMPTY_ENTRY = "plan-empty-entry"
UNSAFE_PATH = "plan-unsafe-path"
LEG_PATH = "plan-bad-leg-path"
DUPLICATE = "plan-duplicate-path"
COVERED_TWICE = "plan-covered-twice"
COLLIDES = "plan-leg-path-collides"
EMPTY_LINK = "plan-empty-symlink"

#: The order both commands name the four in, the order a person mends them
#: in (#1113).
MENDED_FIRST = (ANOTHER, NAME, MOVED, UNANSWERED)

#: Each problem: `(the hand edits it takes, what the source and the plan
#: hold for it)`, as `planned_with` reads `holds`. Another repository is an
#: `org:` other than the source's, in a plan held to `testorg/Northwind` by
#: the source's `origin`; a refused name is `legs.spec: bad_name`; a moved
#: source is a commit made after `plan`; an unanswered entry is `examples/`
#: left at `leg: null`.
PROBLEM = {
    ANOTHER: ((ANOTHER_ORG,), {"held"}),
    NAME: ((REFUSED_NAME,), set()),
    MOVED: ((), {"moved"}),
    UNANSWERED: ((), {"unanswered"}),
}

#: Each ordinary finding, as `PROBLEM` reads it. The split branch taken is
#: a branch `adopt` the source keeps, made as `test_adopt_split_branch.py`
#: makes it, an uncovered path is `release.yaml` with its entry taken out,
#: and each other is a hand edit: `.claude/`, an entry sorted before
#: `examples/`, answered `banana`; an entry for a path the source does not
#: hold; `docs/` respelled `-docs/`, a path that is a `git` option; a leg
#: mounted at `../spec`; `LICENSE`'s entry written twice; an entry for a
#: file `docs/` covers; and a leg mounted at `README.md`, which the root
#: keeps.
ORDINARY = {
    TAKEN: ((), {"taken"}),
    TRACKING: ((BAD_TRACKING_BRANCH,), set()),
    UNCOVERED: ((), {"uncovered"}),
    BAD_LEG: ((("  - path: .claude/\n    leg: root\n",
                "  - path: .claude/\n    leg: banana\n"),), set()),
    EMPTY_ENTRY: ((("  - path: openspec/\n",
                    "  - path: nothing.md\n    leg: root\n"
                    "  - path: openspec/\n"),), set()),
    UNSAFE_PATH: ((("  - path: docs/\n", "  - path: -docs/\n"),), set()),
    LEG_PATH: ((BAD_LEG_PATH,), set()),
    DUPLICATE: ((("  - path: Makefile\n",
                  "  - path: LICENSE\n    leg: root\n  - path: Makefile\n"),),
                set()),
    COVERED_TWICE: ((("  - path: examples/\n",
                      "  - path: docs/architecture.md\n    leg: spec\n"
                      "  - path: examples/\n"),), set()),
    COLLIDES: ((("\n  spec_path: spec\n", "\n  spec_path: README.md\n"),),
               set()),
}


def holding(base, *problems: str) -> str:
    """The text of a plan for a new source at `base` that holds each of
    `problems`, and nothing else wrong with it."""
    held = {**PROBLEM, **ORDINARY}
    edits = [edit for problem in problems for edit in held[problem][0]]
    holds = set().union(*(held[problem][1] for problem in problems))
    text = edited(planned_with(base, holds), *edits)
    if "taken" in holds:
        # `planned_with` makes the source at `base / "Thing"`; the branch
        # comes after `plan`, which would find it taken itself.
        git("branch", "adopt", cwd=base / "Thing")
    if "uncovered" in holds:
        # #1197's edit: `release.yaml` is in the source and in no entry.
        entry = re.search(r"  - path: release\.yaml\n(    .*\n)*", text)
        text = text.replace(entry[0], "", 1)
    return text


def an_empty_link(base) -> str:
    """The text of the plan `plan` writes for a new source at `base` that
    keeps `dangling`, a symlink whose target is empty (#303), made in the
    index as `test_adopt_empty_symlinks.py` makes it, with every question
    answered but the link's own: `plan` leaves it at `leg: null` itself."""
    source = make_source_repo(base / "Thing")
    empty = base / "empty-target"
    empty.write_bytes(b"")
    blob = git("hash-object", "-w", str(empty), cwd=source).stdout.strip()
    git("update-index", "--add", "--cacheinfo", f"120000,{blob},dangling",
        cwd=source)
    git("commit", "-q", "-m", "an empty link", cwd=source)
    return planned(source, base, dict(ANSWERS)).read_text(encoding="utf-8")


def code_of(line: str) -> str:
    """The code of a `REFUSED <code>: ...` or `FINDING <code>: ...` line."""
    return line.split()[1].rstrip(":") if line else ""


def listed(checked) -> list[str]:
    """The codes of `MENDED_FIRST` that `check` listed, each once, in the
    order it listed them first."""
    codes = [code_of(line) for line in checked.stderr.splitlines()
             if line.startswith("FINDING ")]
    return list(dict.fromkeys(code for code in codes if code in MENDED_FIRST))


#: The pairs, and the four together, by test id: `(the problems the plan
#: holds, what both commands name first)`. Each but `another-and-name`
#: was named differently by the two commands on 9549006f.
PAIRS = {
    "moved-and-unanswered": ((MOVED, UNANSWERED), MOVED),
    "another-and-unanswered": ((ANOTHER, UNANSWERED), ANOTHER),
    "another-and-moved": ((ANOTHER, MOVED), ANOTHER),
    "name-and-unanswered": ((NAME, UNANSWERED), NAME),
    "name-and-moved": ((NAME, MOVED), NAME),
    "another-and-name": ((ANOTHER, NAME), ANOTHER),
    "all-four": (MENDED_FIRST, ANOTHER),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(PAIRS))
def test_check_and_execute_name_the_same_first_problem(tmp_path, case):
    """`check` names first the problem `execute` refuses first, the first
    of `MENDED_FIRST` the plan holds: `check` lists every one the plan
    holds, exit 1, in that order, and `execute` refuses the first, exit 2,
    before any leg exists."""
    problems, first = PAIRS[case]
    checked, executed = both_on(holding(tmp_path, *problems), tmp_path)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert (code_of(named_first(checked)),
            code_of(named_first(executed))) == (first, first), (
        checked.stderr + executed.stderr)
    assert named_first(executed).startswith(f"REFUSED {first}: "), (
        executed.stderr)
    assert listed(checked) == [problem for problem in MENDED_FIRST
                               if problem in problems], checked.stderr


@needs_filter_repo
@pytest.mark.parametrize("problem", MENDED_FIRST)
def test_each_problem_alone_is_named_by_its_own_code(tmp_path, problem):
    """THE CONTROLS, which pass on 9549006f too: a plan that holds one of
    the four is that one finding to `check`, exit 1, and that one refusal
    to `execute`, exit 2, as before."""
    checked, executed = both_on(holding(tmp_path, problem), tmp_path)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked).startswith(f"FINDING {problem}: "), (
        checked.stderr)
    assert named_first(executed).startswith(f"REFUSED {problem}: "), (
        executed.stderr)
    assert listed(checked) == [problem], checked.stderr


#: The rule's problem beside an ordinary finding, by test id: `(the rule's
#: problem, the ordinary finding)`. Both commands name the rule's problem
#: first. On 791106c2 `check` listed an unanswered entry with the entries,
#: so each `unanswered-and-` row but `unanswered-and-tracking` was named
#: differently by the two commands: `check` named the ordinary finding
#: first (#1197).
WITH_AN_ORDINARY_FINDING = {
    "another-and-taken": (ANOTHER, TAKEN),
    "name-and-taken": (NAME, TAKEN),
    "moved-and-taken": (MOVED, TAKEN),
    "another-and-tracking": (ANOTHER, TRACKING),
    "name-and-tracking": (NAME, TRACKING),
    "moved-and-tracking": (MOVED, TRACKING),
    "unanswered-and-tracking": (UNANSWERED, TRACKING),
    "unanswered-and-taken": (UNANSWERED, TAKEN),
    "unanswered-and-uncovered": (UNANSWERED, UNCOVERED),
    "unanswered-and-bad-leg": (UNANSWERED, BAD_LEG),
    "unanswered-and-empty-entry": (UNANSWERED, EMPTY_ENTRY),
    "unanswered-and-unsafe-path": (UNANSWERED, UNSAFE_PATH),
    "unanswered-and-bad-leg-path": (UNANSWERED, LEG_PATH),
    "unanswered-and-duplicate-path": (UNANSWERED, DUPLICATE),
    "unanswered-and-covered-twice": (UNANSWERED, COVERED_TWICE),
    "unanswered-and-collides": (UNANSWERED, COLLIDES),
}

#: The first `Remediation:` line `check` prints, where a row pins it: the
#: remediation lines follow the findings' order, so the rule's come first.
FIRST_REMEDIATION = {
    "another-and-taken": "Remediation: Run `plan` again with `--project",
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(WITH_AN_ORDINARY_FINDING))
def test_the_rules_problem_is_named_before_an_ordinary_finding(tmp_path,
                                                               case):
    """`check` lists the rule's problem before the split branch taken or an
    unsafe `tracking_branch:`, and lists that finding too, and `execute`
    refuses the rule's problem before it: both name it first, `check` exit
    1 and `execute` exit 2, before any leg exists. Where `FIRST_REMEDIATION`
    names one, `check`'s first `Remediation:` line is the rule's."""
    problem, ordinary = WITH_AN_ORDINARY_FINDING[case]
    checked, executed = both_on(holding(tmp_path, problem, ordinary),
                                tmp_path)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert (code_of(named_first(checked)),
            code_of(named_first(executed))) == (problem, problem), (
        checked.stderr + executed.stderr)
    assert named_first(executed).startswith(f"REFUSED {problem}: "), (
        executed.stderr)
    assert ordinary in [code_of(line) for line in findings_of(checked)][1:], (
        checked.stderr)
    assert listed(checked) == [problem], checked.stderr
    if case in FIRST_REMEDIATION:
        fixes = [line for line in checked.stderr.splitlines()
                 if line.startswith("Remediation:")]
        assert fixes[0].startswith(FIRST_REMEDIATION[case]), checked.stderr


@needs_filter_repo
def test_an_empty_link_plan_leaves_unanswered_is_named_unanswered_by_both(
        tmp_path):
    """A PLAN AS `plan` WROTE IT, NO HAND EDIT (#1197): `plan` leaves the
    entry of a symlink whose target is empty at `leg: null`, and `check`
    finds the link too (#303). On 791106c2 `check` named
    `plan-empty-symlink` first and `execute` refused `plan-unresolved`; both
    now name the unanswered entry first, and `check` still lists the link,
    with its remediation, in the same run."""
    checked, executed = both_on(an_empty_link(tmp_path), tmp_path)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert (code_of(named_first(checked)),
            code_of(named_first(executed))) == (UNANSWERED, UNANSWERED), (
        checked.stderr + executed.stderr)
    assert named_first(executed).startswith(
        f"REFUSED {UNANSWERED}: 1 path(s) still have `leg: null`: "
        "`dangling`"), executed.stderr
    assert [code_of(line) for line in findings_of(checked)] == [
        UNANSWERED, EMPTY_LINK], checked.stderr


@needs_filter_repo
@pytest.mark.parametrize("ordinary", sorted(ORDINARY))
def test_each_ordinary_finding_alone_is_named_by_both(tmp_path, ordinary):
    """THE CONTROLS, which pass on 791106c2 too: a plan that holds one
    ordinary finding, every entry answered, is that finding first to
    `check`, exit 1, and to `execute`, exit 2, before any leg exists, so
    each hand edit above makes the finding it is named for."""
    checked, executed = both_on(holding(tmp_path, ordinary), tmp_path)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert (code_of(named_first(checked)),
            code_of(named_first(executed))) == (ordinary, ordinary), (
        checked.stderr + executed.stderr)
    assert listed(checked) == [], checked.stderr
