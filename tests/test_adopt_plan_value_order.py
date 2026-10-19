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
- ONE FINDING PER VALUE. A pin edited to `product: "a\\t"` and `repository:
  "opensoft/a\\t"` was three findings about one value: `plan-pin-malformed`,
  `plan-unwritable-value` and the validator's `plan-manifest-invalid`. A
  `pins:` entry `_read_pins` names is now that finding alone: #255 asks only
  the pins `execute` writes, and the validator's word on such an entry is
  left out.
- `pins: true` was "`pins:` is True", Python's spelling, where each other
  key a plan is opened by is said as `_read_as` says what the plan's reader
  read: "the boolean true".
- A finding about a pin's `digest_source:` ended "`execute` writes the pin
  file from the commit and the digest `plan` records, and nothing else",
  though the pin file `execute` writes says how the digest was read too
  (`_digest_source_written`). It ends "..., and how it was read, and
  nothing else" now.

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
from test_adopt_pins import ANSWERS, pin_entry

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


def findings_of(result) -> list[str]:
    """Each `FINDING` line `check` printed."""
    return [line for line in result.stderr.splitlines()
            if line.startswith("FINDING ")]


def refused_with(executed, plan: Path, found: list[str]) -> str:
    """The code `execute` refused the plan at `plan` under, where it said
    every one of `found`, `check`'s findings, as `check` prints them."""
    lines = executed.stderr.splitlines()
    head = named_first(executed)
    assert head.endswith(f": {len(found)} finding(s) in {plan}, as `check` "
                         "prints them:"), executed.stderr
    assert lines[lines.index(head) + 1:][:len(found)] == [
        f"  {finding}" for finding in found], executed.stderr
    return head.split()[1].rstrip(":")


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


# --- one finding per value: a pin `_read_pins` names is its alone ----------

#: A commit and a digest of the form `plan` records, for pins whose digest
#: nobody reads here: `gh-api-tree-recursive` says the forge read it, and
#: `check` reads no network.
COMMIT = "0123456789abcdef" * 2 + "01234567"
DIGEST = "0123456789abcdef" * 4


def a_pin(product: str, repository: str) -> str:
    """One `pins:` mapping as `plan` writes it, its `product:` and its
    `repository:` spelled as given."""
    return pin_entry(product=product, repository=repository, commit=COMMIT,
                     digest=DIGEST, source="gh-api-tree-recursive")


def pinned(text: str, *entries: str) -> str:
    """`text` with its `pins: []` replaced by a list of `entries`."""
    return edited(text, ("\npins: []\n", "\npins:\n" + "".join(entries)))


#: The issue's own edit: a product and a repository holding a tab.
TAB_PIN = a_pin('"a\\t"', '"opensoft/a\\t"')
TAB_SAID = ("records `product: 'a\\t'` and `repository: 'opensoft/a\\t'`, "
            "and `plan` records the repository as `<owner>/<openProduct>`")

#: `(the plan's `pins:` entries, how its one finding begins)`, by test id.
ONE_FINDING = {
    "product-tab": ((TAB_PIN,),
                    f"FINDING plan-pin-malformed: `pins:` entry 1 ('a\\t') "
                    f"{TAB_SAID}"),
    "product-line-break": ((a_pin('"a\\nb"', '"opensoft/a\\nb"'),),
                           "FINDING plan-pin-malformed: `pins:` entry 1 "
                           "('a\\nb') records `product: 'a\\nb'`"),
    "name-with-an-escape": (('  - "open\\x1bGlass"\n',),
                            "FINDING plan-pin-unrecorded: `pins:` entry 1, "
                            "'open\\x1bGlass', is a name with no commit and "
                            "no digest."),
    "beside-a-whole-pin": ((a_pin("openGlass", "opensoft/openGlass"),
                            TAB_PIN),
                           f"FINDING plan-pin-malformed: `pins:` entry 2 "
                           f"('a\\t') {TAB_SAID}"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(ONE_FINDING))
def test_a_pin_its_own_rule_names_is_one_finding(answered, tmp_path, case):
    """A `pins:` entry `_read_pins` names is that finding alone: neither
    `plan-unwritable-value` nor the validator's `plan-manifest-invalid`
    names its product again, a whole pin beside it is named by nothing, and
    `execute` refuses the plan with that one finding, as `check` prints it,
    before any leg exists."""
    entries, said = ONE_FINDING[case]
    checked, executed = both_on(pinned(answered, *entries), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(said), found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    code = refused_with(executed, tmp_path / PLAN_FILE, found)
    assert code == said.split()[1].rstrip(":")


# --- a `pins:` that is no list, said as the plan's reader read it -----------

#: `(the plan's `pins:` line, what was read, as `_read_as` says it)`.
NOT_A_LIST = {
    "text": ("pins: openGlass", "the text 'openGlass'"),
    "number": ("pins: 5", "the number 5"),
    "boolean": ("pins: true", "the boolean true"),
    "mapping": ("pins: {product: openGlass}", "a mapping of 1 key(s)"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(NOT_A_LIST))
def test_a_pins_that_is_no_list_is_said_as_its_reader_read_it(
        answered, tmp_path, case):
    """`_read_pins` spelled a `pins:` that is no list as Python spells it,
    `True` or `{'product': 'openGlass'}`, where each other key a plan is
    opened by is said as `_read_as` says what the plan's reader read
    (#386): `check` finds it in those words, and `execute` refuses it in
    them, before the source is opened."""
    line, read = NOT_A_LIST[case]
    checked, executed = both_on(
        edited(answered, ("\npins: []\n", f"\n{line}\n")), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(
        f"FINDING plan-pin-malformed: `pins:` is {read}, not a list of pins: "
        "re-run `plan` with `--pin <openProduct>@<40 hex commit>`"), found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert refused_with(executed, tmp_path / PLAN_FILE,
                        found) == "plan-pin-malformed"


# --- a `digest_source:` finding says `execute` writes how it was read -------

#: The rest of a finding about a pin's `digest_source:`, after its `why`:
#: the pin file `execute` writes says how the digest was read too (#901).
WRITTEN_FROM_AND_HOW = (
    "`execute` writes the pin file from the commit and the digest `plan` "
    "records, and how it was read, and nothing else: re-run `plan` with "
    "`--pin opensoft/openGlass@<40 hex commit>`")
#: A whole pin on `openGlass`, as `plan` records it, but its source.
NO_SOURCE = pin_entry(commit=COMMIT, digest=DIGEST, omit=("digest_source",))

#: `(the plan's one `pins:` entry, what its finding says of it)`, by test id.
SOURCE_FINDINGS = {
    "not-a-spelling": (pin_entry(commit=COMMIT, digest=DIGEST,
                                 source="read by hand"),
                       "records `digest_source: 'read by hand'`, and `plan` "
                       "records `gh-api-tree-recursive`, or `local-clone "
                       "(<the clone's path>)` on one printable line, and "
                       "nothing else"),
    "absent": (NO_SOURCE, "records no `digest_source:`"),
    "not-text": (NO_SOURCE + "    digest_source: 7\n",
                 "records `digest_source: 7`, which is not text"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(SOURCE_FINDINGS))
def test_a_digest_source_finding_says_execute_writes_how_it_was_read(
        answered, tmp_path, case):
    """The pin file `execute` writes says how the digest was read
    (`_digest_source_written`), so a finding about an entry's
    `digest_source:` no longer says `execute` writes the file from the
    commit and the digest and nothing else: `check` says what it does
    write, and `execute` refuses the plan in the same words."""
    entry, why = SOURCE_FINDINGS[case]
    checked, executed = both_on(pinned(answered, entry), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(
        "FINDING plan-pin-malformed: `pins:` entry 1 ('openGlass') "
        f"{why}. {WRITTEN_FROM_AND_HOW}"), found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert refused_with(executed, tmp_path / PLAN_FILE,
                        found) == "plan-pin-malformed"
