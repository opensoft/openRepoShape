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

Each row runs `check` and then `execute --yes` on one hand-edited plan, both
with the same `--local-remote-dir`, so no `gh` runs and no remote is asked,
and asserts that no leg was made. `execute` refuses every plan here before
it reads a remote: it asks for `git filter-repo` first, so the rows skip
where it is not installed.

THE LEG QUESTION BESIDE ANOTHER REPOSITORY (#1232). The rows of #1232 are
the exception to the paragraph above: each runs `check`, and `execute`
where it is refused first, given no `--local-remote-dir` or one that holds
a leg's bare repository, with a `gh` of its own ahead of the session's
guard that logs each call and exits 97. On 791106c2 `check`, given no
`--local-remote-dir`, ran `gh repo view` of both legs of a plan for another
repository, and its NOTE said `execute` asks again, where `execute` refuses
`plan-not-the-source` first and asks nothing. Now it asks GitHub nothing
there. The source's own plan is asked as before, and under
`--local-remote-dir` the disk still is, beside `plan-not-the-source`: a
leg's bare repository is `<dir>/<name>.git`, which no `org:` is part of.
"""

from __future__ import annotations

import os

import pytest

from conftest import ADOPT, git, run_script
from test_adopt_plan_value_order import (
    ANOTHER_ORG, BAD_TRACKING_BRANCH, PLAN_FILE, REFUSED_NAME, both_on,
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
#: makes it, and an unsafe `tracking_branch:` is a hand edit.
ORDINARY = {
    TAKEN: ((), {"taken"}),
    TRACKING: ((BAD_TRACKING_BRANCH,), set()),
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
    return text


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


#: How `check` names, in a NOTE on stdout, a question about a leg's
#: repository that gh could not answer (#798).
COULD_NOT_ASK = "NOTE `check` could not ask GitHub whether "
#: A leg's bare repository already there, under `--local-remote-dir`.
LEG_TAKEN = "leg-remote-exists"
#: The two ways a plan names another repository than its source's (#499):
#: an `org:` other than the source's, and a `legs.assembly:` other than its
#: name, which keeps the source's `org:` and the legs' names, so `check`
#: asked GitHub about the very legs the plan the remedy writes names.
ANOTHER_REPOSITORY = {
    "org": ANOTHER_ORG,
    "assembly": ("\n  assembly: Northwind\n", "\n  assembly: Elsewhere\n"),
}

needs_a_posix_gh = pytest.mark.skipif(
    os.name == "nt", reason="the logging gh is a #! script")


def with_a_logging_gh(log, *args: str):
    """`adopt-project.py <args>` with a `gh` first on PATH, ahead of the
    session's guard, that appends each call's arguments to `log`, one line
    each, and exits 97, as #1232 measured: `(the run, each call it made)`."""
    stub = log.parent / "logging-gh"
    stub.mkdir(exist_ok=True)
    (stub / "gh").write_bytes(
        b'#!/bin/sh\necho "$*" >> "$GH_STUB_LOG"\nexit 97\n')
    (stub / "gh").chmod(0o755)
    ran = run_script(ADOPT, *args, env={
        "PATH": f"{stub}{os.pathsep}{os.environ['PATH']}",
        "GH_STUB_LOG": str(log)})
    return ran, (log.read_text(encoding="utf-8").splitlines()
                 if log.exists() else [])


@needs_filter_repo
@needs_a_posix_gh
@pytest.mark.parametrize("case", sorted(ANOTHER_REPOSITORY))
def test_check_asks_github_nothing_about_another_repositorys_legs(tmp_path,
                                                                 case):
    """#1232: given no `--local-remote-dir`, `check` on a plan for another
    repository runs no `gh` and prints no NOTE about a leg's repository, as
    `execute` asks nothing before it refuses `plan-not-the-source` (#499),
    and both still name that first, `check` exit 1 and `execute` exit 2. On
    791106c2 `check` ran `gh repo view` of each leg, under the plan's
    `org:`, and its NOTE said `execute` asks again."""
    plan = tmp_path / PLAN_FILE
    plan.write_bytes(edited(planned_with(tmp_path, {"held"}),
                            ANOTHER_REPOSITORY[case]).encode("utf-8"))
    checked, check_asked = with_a_logging_gh(
        tmp_path / "check.log", "check", "--plan", str(plan))
    executed, execute_asked = with_a_logging_gh(
        tmp_path / "execute.log", "execute", "--plan", str(plan), "--yes",
        "--work-dir", str(tmp_path / "work"))
    assert (check_asked, execute_asked) == ([], []), checked.stdout
    assert COULD_NOT_ASK not in checked.stdout, checked.stdout
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert (code_of(named_first(checked)),
            code_of(named_first(executed))) == (ANOTHER, ANOTHER), (
        checked.stderr + executed.stderr)
    assert named_first(executed).startswith(f"REFUSED {ANOTHER}: "), (
        executed.stderr)


@needs_a_posix_gh
def test_a_local_remote_dir_is_still_asked_beside_another_repository(
        tmp_path):
    """THE CHOICE UNDER `--local-remote-dir` (#1232), as on 791106c2: the
    disk is still asked beside `plan-not-the-source`. It asks no remote,
    and a leg's bare repository is `<dir>/<name>.git`, which no `org:` is
    part of: with the spec leg's taken, `check` lists `leg-remote-exists`
    after `plan-not-the-source`, the very finding it lists for the
    source's own plan, the one the remedy writes, under the same
    directory. Neither run asks `gh` anything."""
    remotes = tmp_path / "remotes"
    (remotes / "Northwind-spec.git").mkdir(parents=True)
    own = planned_with(tmp_path, {"held"})
    runs = {}
    for name, text in (("own", own), ("another", edited(own, ANOTHER_ORG))):
        plan = tmp_path / f"{name}.yaml"
        plan.write_bytes(text.encode("utf-8"))
        runs[name] = with_a_logging_gh(
            tmp_path / f"{name}.log", "check", "--plan", str(plan),
            "--local-remote-dir", str(remotes))
    (own_checked, own_asked), (checked, asked) = runs["own"], runs["another"]
    assert (own_asked, asked) == ([], []), (own_asked, asked)
    assert (own_checked.returncode, checked.returncode) == (1, 1), (
        own_checked.stderr + checked.stderr)
    assert [code_of(line) for line in findings_of(checked)] == [
        ANOTHER, LEG_TAKEN], checked.stderr
    assert findings_of(checked)[1:] == findings_of(own_checked), (
        own_checked.stderr + checked.stderr)


@needs_a_posix_gh
def test_check_still_asks_github_about_the_sources_own_legs(tmp_path):
    """THE CONTROL, which passes on 791106c2 too (#1232): the source's own
    plan, given no `--local-remote-dir`, is asked `gh repo view` of each
    leg under its `org:`, and where gh cannot answer, `check` prints a NOTE
    for each that says `execute` asks again, and passes."""
    plan = tmp_path / PLAN_FILE
    plan.write_bytes(planned_with(tmp_path, {"held"}).encode("utf-8"))
    checked, asked = with_a_logging_gh(tmp_path / "check.log", "check",
                                       "--plan", str(plan))
    views = [f"repo view testorg/Northwind-{leg} --json nameWithOwner"
             for leg in ("spec", "code")]
    assert asked == views, asked
    assert [line for line in checked.stdout.splitlines()
            if line.startswith(COULD_NOT_ASK)] == [
        f"{COULD_NOT_ASK}testorg/Northwind-{leg}, the {leg} leg's "
        f"repository, already exists: `gh {view}` exited 97. It is no "
        "finding here, so that `check` stays usable offline; `execute` asks "
        "again before it makes either leg, and refuses as "
        "`adopt-remote-unreadable` while gh cannot answer."
        for leg, view in zip(("spec", "code"), views)], checked.stdout
    assert checked.returncode == 0, checked.stdout + checked.stderr


#: The rule's problem beside an ordinary finding, by test id: `(the rule's
#: problem, the ordinary finding)`. Both commands name the rule's problem
#: first. `unanswered-and-taken` is left out: `check` lists an unanswered
#: entry with the entries, after the split branch, and `execute` refuses it
#: first, so the two disagree on it before and after this fix (#1197).
WITH_AN_ORDINARY_FINDING = {
    "another-and-taken": (ANOTHER, TAKEN),
    "name-and-taken": (NAME, TAKEN),
    "moved-and-taken": (MOVED, TAKEN),
    "another-and-tracking": (ANOTHER, TRACKING),
    "name-and-tracking": (NAME, TRACKING),
    "moved-and-tracking": (MOVED, TRACKING),
    "unanswered-and-tracking": (UNANSWERED, TRACKING),
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
