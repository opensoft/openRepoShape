# SPDX-License-Identifier: Apache-2.0
"""`.github/workflows/tests.yml` runs on each push to main and to a release
branch, and never lets one landing cancel another's run.

THE FAILURE THIS GUARDS IS SILENT. A `push` run on main has no pull request
number, so a group that fell back to `github.ref` landed on `refs/heads/main`
and every push run on main shared ONE group; with `cancel-in-progress: true`
each landing cancelled the run on the main before it. On 2026-10-15 every
push run from #561 (7d9bec9) to #580 (dd3f23a) ended `cancelled` and nine pull
requests landed with no Linux run over their combination (#592). Nothing in
the suite failed: the runs were simply never finished, so the lanes waited for
main's push run, about 30 minutes a landing.

The fix groups a pull-request run by its number (a new push to the pull
request still cancels its older run) and every other run by its event, its
ref and its own commit. The event is part of the group because a
`workflow_dispatch` run starts on whatever commit main is at, which is also the
commit of that commit's push run: grouped by commit alone, the dispatch would
cancel the push run it sits beside (RV593 SHOULD-1).

#850 ADDS THE RELEASE BRANCHES. A push to `release/v<major>.<minor>` runs the
suite as a push to main does, so each commit a release branch takes has the
push run `release.yml` requires of a tagged commit, with no dispatch by hand.
The ref joined the group with it: a group spans the repository, and a
fast-forward of a release branch to main's commit pushes the very commit main's
push run is testing, so grouped by event and commit alone the release branch's
run would cancel main's.

These tests read the concurrency block as TEXT, like the rest of this suite,
and never touch the network or `gh`. `actionlint` in the workflow itself checks
the expression's syntax; what it cannot check is which fallback was chosen.
The trigger is read with `repo_shape.load_yaml`, the fail-closed reader
`tests/test_release_workflow.py` reads both workflows with.
"""

from __future__ import annotations

import re

import pytest

from conftest import REPO
from repo_shape import load_yaml

WORKFLOW = REPO / ".github" / "workflows" / "tests.yml"

#: A pull request is grouped by its number. Anything else is grouped by its
#: event, its ref and the commit it runs on, so a push run and a dispatch on
#: the same commit stay in two groups, and so do the push runs of main and of
#: a release branch fast-forwarded to main's commit; neither cancels the other.
GROUP = ("${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}-"
         "${{ github.event.pull_request.number || github.sha }}")

#: Spellings the workflow once had, or could be given again, each with a
#: phrase its refusal must carry. `github.ref` is what #592 fixed: every push
#: run on main in one group. The `github.sha` one without the event is this
#: file's own first fix, which stops a landing cancelling the last landing's
#: run but lets a dispatch cancel its commit's push run (RV593 SHOULD-1). The
#: one without the ref is the one #592 closed with, which lets a release
#: branch's push cancel main's run on the same commit (#850). The ref in place
#: of the commit would put every push run on main in one group again.
EARLIER_GROUPS = {
    "ref": ("${{ github.workflow }}-"
            "${{ github.event.pull_request.number || github.ref }}",
            "github.ref"),
    "sha-without-the-event": (
        "${{ github.workflow }}-"
        "${{ github.event.pull_request.number || github.sha }}",
        "github.event_name"),
    "sha-without-the-ref": (
        "${{ github.workflow }}-${{ github.event_name }}-"
        "${{ github.event.pull_request.number || github.sha }}",
        "fast-forwarded"),
    "ref-without-the-commit": (
        "${{ github.workflow }}-${{ github.event_name }}-${{ github.ref }}",
        "github.sha"),
}

#: The branches whose pushes run the suite (#850): `main`, the trunk every
#: change lands on first, and each release branch, `release/v<major>.<minor>`,
#: where a patch is tagged. `release.yml` releases a commit only once a push or
#: dispatch run of this workflow passed `tests` on it.
PUSH_BRANCHES = ["main", "release/v*"]


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
    if group is not None and re.search(r"\|\|\s*github\.ref\b", group):
        return ("it falls back to `github.ref`, which is `refs/heads/main` "
                "for every push run on main, so the next landing cancels the "
                "last one's run (#592)")
    if group is not None and "github.sha" not in group:
        return ("it does not name `github.sha`, so every push run on one "
                "branch shares a group and the next landing cancels the last "
                "one's run (#592)")
    if group is not None and "github.event_name" not in group:
        return ("it does not name `github.event_name`, so a dispatch on a "
                "commit shares a group with that commit's push run and "
                "cancels it (RV593 SHOULD-1)")
    if group is not None and "github.ref" not in group:
        return ("it does not name `github.ref`, so the push run of a release "
                "branch fast-forwarded to main's commit shares a group with "
                "main's push run on that commit and cancels it (#850)")
    return f"it is not {GROUP!r}"


def test_a_run_is_grouped_by_its_event_its_ref_and_its_commit():
    """The group's fallback is `github.sha` (#592), and it names the event
    and the ref beside it (#850).

    `github.ref` is `refs/heads/main` for every push run on main, so in place
    of the commit it puts every landing in one group and the next landing
    cancels the last one. The commit alone is not enough either: a dispatch
    runs on the commit main is at, the same commit as its push run, and would
    cancel it; and a release branch fast-forwarded to main's commit pushes
    that same commit, and its run would cancel main's.
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


def branch_filter_matches(pattern: str, branch: str) -> bool:
    """GitHub's branch filter for the one wildcard this workflow uses: `*`
    matches any characters but `/`. A pattern with any other special
    character is refused here rather than guessed at."""
    assert not set(pattern) & set("?+[]!") and "**" not in pattern, pattern
    return re.fullmatch("[^/]*".join(map(re.escape, pattern.split("*"))),
                        branch) is not None


def test_a_push_to_main_or_to_a_release_branch_runs_the_suite():
    """#850: the push trigger names `main` and `release/v*`, so a commit a
    release branch takes gets the push run `release.yml`'s gate requires of
    the tagged commit; before, each had to be dispatched by hand. A pull
    request and a manual run still run it."""
    on = load_yaml(WORKFLOW)["on"]
    assert on["push"] == {"branches": PUSH_BRANCHES}, on["push"]
    assert set(on) == {"push", "pull_request", "workflow_dispatch"}, set(on)


@pytest.mark.parametrize("branch, runs", [
    ("main", True),
    ("release/v1.1", True),
    ("release/v1.0", True),
    ("l3-850-release-branches", False),
    ("docs/release-notes-v1.0.0", False),
], ids=["main", "release-v1.1", "release-v1.0", "a-pull-requests-branch",
        "a-branch-named-for-a-release"])
def test_which_branchs_push_runs_the_suite(branch, runs):
    """`release/v1.1`, where v1.1.1 is tagged, and `release/v1.0`, where
    v1.0.1 was, run on a push as main does; a pull request's own branch runs
    in its pull request instead, whatever its name says."""
    patterns = load_yaml(WORKFLOW)["on"]["push"]["branches"]
    assert any(branch_filter_matches(pattern, branch)
               for pattern in patterns) is runs, (branch, patterns)
