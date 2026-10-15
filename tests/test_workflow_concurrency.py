# SPDX-License-Identifier: Apache-2.0
"""`.github/workflows/tests.yml` never lets one landing cancel another's run.

THE FAILURE THIS GUARDS IS SILENT. A `push` run on main has no pull request
number, so a group that fell back to `github.ref` landed on `refs/heads/main`
and every push run on main shared ONE group; with `cancel-in-progress: true`
each landing cancelled the run on the main before it. On 2026-10-15 every
push run from #561 (7d9bec9) to #580 (dd3f23a) ended `cancelled` and nine pull
requests landed with no Linux run over their combination (#592). Nothing in
the suite failed: the runs were simply never finished, so the lanes waited for
main's push run, about 30 minutes a landing.

The fix groups a pull-request run by its number (a new push to the pull
request still cancels its older run) and every other run by its event and its
own commit. The event is part of the group because a `workflow_dispatch` run
starts on whatever commit main is at, which is also the commit of that commit's
push run: grouped by commit alone, the dispatch would cancel the push run it
sits beside (RV593 SHOULD-1).

These tests read the workflow as TEXT, like the rest of this suite, and never
touch the network or `gh`. `actionlint` in the workflow itself checks the
expression's syntax; what it cannot check is which fallback was chosen.
"""

from __future__ import annotations

import re

import pytest

from conftest import REPO

WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"

#: A pull request is grouped by its number. Anything else is grouped by its
#: event and the commit it runs on, so a push run and a dispatch on the same
#: commit stay in two groups and neither cancels the other.
GROUP = ("${{ github.workflow }}-${{ github.event_name }}-"
         "${{ github.event.pull_request.number || github.sha }}")

#: Spellings the workflow once had, or could be given again, each with a
#: phrase its refusal must carry. `github.ref` is what #592 fixed: every push
#: run on main in one group. The `github.sha` one without the event is this
#: file's own first fix, which stops a landing cancelling the last landing's
#: run but lets a dispatch cancel its commit's push run (RV593 SHOULD-1).
EARLIER_GROUPS = {
    "ref": ("${{ github.workflow }}-"
            "${{ github.event.pull_request.number || github.ref }}",
            "github.ref"),
    "sha-without-the-event": (
        "${{ github.workflow }}-"
        "${{ github.event.pull_request.number || github.sha }}",
        "github.event_name"),
}


def workflow_lines() -> list[str]:
    """The workflow's lines, comments dropped, whatever the checkout's EOL."""
    text = WORKFLOW.read_bytes().decode("utf-8")
    return [line for line in text.splitlines()
            if not line.lstrip().startswith("#")]


def top_level_concurrency() -> dict[str, str]:
    """The `key: value` pairs under the top-level `concurrency:` mapping."""
    lines = workflow_lines()
    starts = [i for i, line in enumerate(lines)
              if re.fullmatch(r"concurrency:\s*", line)]
    assert len(starts) == 1, (
        f"{WORKFLOW.name} must carry exactly one top-level `concurrency:` "
        f"block, found {len(starts)}")
    block = {}
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith(" "):
            break
        pair = re.fullmatch(r"\s+([\w-]+):\s*(.*?)\s*", line)
        if pair:
            block[pair.group(1)] = pair.group(2)
    return block


def group_problem(group: str | None) -> str | None:
    """Why `group` is not the expression this workflow must carry, or None."""
    if group == GROUP:
        return None
    if group is not None and "github.ref" in group:
        return ("it falls back to `github.ref`, which is `refs/heads/main` "
                "for every push run on main, so the next landing cancels the "
                "last one's run (#592)")
    if group is not None and "github.event_name" not in group:
        return ("it does not name `github.event_name`, so a dispatch on a "
                "commit shares a group with that commit's push run and "
                "cancels it (RV593 SHOULD-1)")
    return f"it is not {GROUP!r}"


def test_a_run_is_grouped_by_its_event_and_its_commit():
    """The group's fallback is `github.sha` and it names the event (#592).

    `github.ref` is `refs/heads/main` for every push run on main, so it puts
    every landing in one group and the next landing cancels the last one. The
    commit alone is not enough either: a dispatch runs on the commit main is
    at, the same commit as its push run, and would cancel it.
    """
    group = top_level_concurrency().get("group")
    problem = group_problem(group)
    assert problem is None, (
        f"the concurrency group is {group!r}, not {GROUP!r}: {problem}")


@pytest.mark.parametrize("earlier", EARLIER_GROUPS)
def test_the_group_check_refuses_each_earlier_spelling(earlier):
    """The check above fails on the expressions this file once had."""
    group, phrase = EARLIER_GROUPS[earlier]
    problem = group_problem(group)
    assert problem is not None and phrase in problem


def test_a_new_push_to_a_pull_request_still_cancels_its_older_run():
    """`cancel-in-progress: true` stays: the per-PR group is what it acts on."""
    assert top_level_concurrency().get("cancel-in-progress") == "true"


def test_no_job_carries_a_concurrency_of_its_own():
    """A job-level `concurrency:` would put its runs back in a shared group,
    and this file's check of the workflow-level one would say nothing of it."""
    nested = [line for line in workflow_lines()
              if re.fullmatch(r"\s+concurrency:.*", line)]
    assert nested == [], (
        "a job in tests.yml sets `concurrency:` itself, which the group "
        f"checked above does not govern: {nested}")
