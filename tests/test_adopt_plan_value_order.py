# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` name the same first problem in a hand-edited plan,
and name each bad value once, in words that say what `execute` does (#901,
which groups five lines of #457).

ON MAIN AT c7a3ff16, with a stub `gh`, an empty `GH_CONFIG_DIR` and local
remotes, as the issue measured at 5017830:
- ONE ORDER. `check` asked the plan's `org:` and `id:` first, in
  `_manifest_values`, and refused either, exit 2, before it listed any
  finding; `execute` asked the two leg paths and the two branch names first,
  in `_checked_plan_values`. A plan edited to `id: "North Wind"` and
  `legs.spec_path: "../spec"` was `REFUSED plan-bad-id` to `check` and
  `REFUSED plan-bad-leg-path` to `execute`; `org: "-evil"` beside the same
  path was `unsafe-value` about the organisation to the one and
  `plan-bad-leg-path` to the other. Both now ask the organisation and the
  id first (`_checked_org_and_id`): they say which project the plan is
  about, which is the most basic thing a plan can get wrong.

Each test runs `check` and then `execute --yes`, both with the same
`--local-remote-dir`, on one hand-edited plan, as the issue measured, and
asserts that the directory the legs go in was never made. `execute` stops
before `git filter-repo` would run, but asks for it first, so the tests skip
where it is not installed. No `gh` runs: given `--local-remote-dir`, `check`
asks the disk whether each leg repository exists.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from conftest import ADOPT, make_source_repo, planned, run_script
from test_adopt_pins import ANSWERS

UTF8 = "utf-8"
PLAN_FILE = "adoption-plan.yaml"

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: Each hand edit below: `(the line as `plan` writes it, the line edited)`.
BAD_ID = ("\nid: northwind\n", '\nid: "North Wind"\n')
BAD_ORG = ("\norg: testorg\n", '\norg: "-evil"\n')
BAD_LEG_PATH = ("\n  spec_path: spec\n", '\n  spec_path: "../spec"\n')
BAD_SPLIT_BRANCH = ("\nadopt_branch: adopt/three-repo-shape\n",
                    '\nadopt_branch: "a b"\n')
BAD_TRACKING_BRANCH = ("\ntracking_branch: main\n",
                       '\ntracking_branch: "a b"\n')
BAD_DATE = ('\nelected_on: "2026-09-02"\n', '\nelected_on: "someday"\n')

#: What both commands name first about a bad `id:` and a bad `org:`.
ID_REFUSED = "REFUSED plan-bad-id: "
ID_SAID = "`id:` is 'North Wind' and must match ^[a-z0-9][a-z0-9-]*$"
ORG_REFUSED = ("REFUSED unsafe-value: org is '-evil', which is not a value "
               "this tool will put on a `git` or `gh` command line")


@pytest.fixture(scope="module")
def answered(tmp_path_factory) -> str:
    """The text of the plan `plan` writes for the synthetic source, every
    question answered: each test edits a copy of it. `check` and `execute`
    only read the source, so the tests share it."""
    base = tmp_path_factory.mktemp("answered")
    source = make_source_repo(base / "Thing")
    return planned(source, base, dict(ANSWERS)).read_text(encoding=UTF8)


def edited(text: str, *edits: tuple[str, str]) -> str:
    """`text` with each `(line, edited line)` replaced, each line being in
    the plan exactly once, as a hand edit would leave it."""
    for line, edit in edits:
        assert text.count(line) == 1, line
        text = text.replace(line, edit, 1)
    return text


def both_on(text: str, base: Path):
    """`check` and then `execute --yes` on the plan `text`, written at
    `base`, each given the same `--local-remote-dir`: `(check's run,
    execute's run)`. Neither makes the directory the legs go in."""
    plan = base / PLAN_FILE
    plan.write_bytes(text.encode(UTF8))
    remotes = base / "remotes"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--local-remote-dir", str(remotes))
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(base / "work"))
    assert not remotes.exists(), executed.stdout + executed.stderr
    return checked, executed


def named_first(result) -> str:
    """The first problem a run named: its first `REFUSED` or `FINDING`
    line on stderr."""
    return next((line for line in result.stderr.splitlines()
                 if line.startswith(("REFUSED ", "FINDING "))), "")


# --- one order: the organisation and the id first ---------------------------

#: `(the edits, what both commands refuse first)`, by test id. The id and
#: the organisation beside a leg path are the issue's two measurements; a
#: branch name `checked_value` refuses was asked by `execute` before them
#: too, and a bad date beside them is what `_manifest_values`' docstring
#: speaks of.
FIRST = {
    "id-and-leg-path": ((BAD_ID, BAD_LEG_PATH), ID_REFUSED),
    "org-and-leg-path": ((BAD_ORG, BAD_LEG_PATH), ORG_REFUSED),
    "id-and-split-branch": ((BAD_ID, BAD_SPLIT_BRANCH), ID_REFUSED),
    "org-and-tracking-branch": ((BAD_ORG, BAD_TRACKING_BRANCH), ORG_REFUSED),
    "date-id-and-leg-path": ((BAD_DATE, BAD_ID, BAD_LEG_PATH), ID_REFUSED),
    "date-org-and-leg-path": ((BAD_DATE, BAD_ORG, BAD_LEG_PATH),
                              ORG_REFUSED),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(FIRST))
def test_check_and_execute_refuse_the_org_or_the_id_first(answered,
                                                           tmp_path, case):
    """Both commands ask the plan's `org:` and `id:` before its leg paths
    and its branch names, so a plan wrong in both is refused for the same
    value by each, exit 2, in the same words, and no leg is made."""
    edits, refused = FIRST[case]
    checked, executed = both_on(edited(answered, *edits), tmp_path)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked).startswith(refused), checked.stderr
    assert named_first(executed) == named_first(checked), executed.stderr


@needs_filter_repo
def test_the_id_is_named_in_the_same_words_by_both(answered, tmp_path):
    """The issue's first measurement, whole: `id: "North Wind"` beside
    `legs.spec_path: "../spec"` is `plan-bad-id`, naming the plan and the
    rule, to both, and neither says anything of the leg path."""
    checked, executed = both_on(edited(answered, BAD_ID, BAD_LEG_PATH),
                                tmp_path)
    said = f"{ID_REFUSED}{tmp_path / PLAN_FILE}: {ID_SAID}"
    assert named_first(checked) == said, checked.stderr
    assert named_first(executed) == said, executed.stderr
    assert "plan-bad-leg-path" not in executed.stderr, executed.stderr
