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
request still cancels its older run) and every other run by its own commit.
These tests read the workflow as TEXT, like the rest of this suite, and never
touch the network or `gh`. `actionlint` in the workflow itself checks the
expression's syntax; what it cannot check is which fallback was chosen.
"""

from __future__ import annotations

import re

from conftest import REPO

WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"

#: The one spelling #592 asks for. A pull request is grouped by its number and
#: anything else, a push or a manual dispatch, by the commit it runs on.
GROUP = ("${{ github.workflow }}-"
         "${{ github.event.pull_request.number || github.sha }}")


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


def test_a_push_or_dispatch_run_is_grouped_by_its_commit():
    """The group's fallback is `github.sha`, never `github.ref` (#592).

    `github.ref` is `refs/heads/main` for every push run on main, so it puts
    every landing in one group and the next landing cancels the last one.
    """
    group = top_level_concurrency().get("group")
    assert group == GROUP, (
        f"the concurrency group is {group!r}, not {GROUP!r}. A run with no "
        "pull request number must be grouped by its own commit, or the next "
        "landing on main cancels this one's run (#592)")
    assert "github.ref" not in group


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
