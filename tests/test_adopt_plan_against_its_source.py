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

Each row runs `check` and then `execute --yes` on one hand-edited plan, both
with the same `--local-remote-dir`, so no `gh` runs and no remote is asked,
and asserts that no leg was made. `execute` refuses every plan here before
it reads a remote: it asks for `git filter-repo` first, so the rows skip
where it is not installed.
"""

from __future__ import annotations

import pytest

from test_adopt_plan_value_order import (
    ANOTHER_ORG, REFUSED_NAME, both_on, edited, named_first,
    needs_filter_repo, planned_with)

ANOTHER = "plan-not-the-source"
NAME = "naming-unclassified"
MOVED = "plan-stale"
UNANSWERED = "plan-unresolved"

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


def holding(base, *problems: str) -> str:
    """The text of a plan for a new source at `base` that holds each of
    `problems`, and nothing else wrong with it."""
    edits = [edit for problem in problems for edit in PROBLEM[problem][0]]
    holds = set().union(*(PROBLEM[problem][1] for problem in problems))
    return edited(planned_with(base, holds), *edits)


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
