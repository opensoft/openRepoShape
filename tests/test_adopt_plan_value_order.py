# SPDX-License-Identifier: Apache-2.0
"""`check` and `execute` name the same first problem in a hand-edited plan,
and name each bad value once, in words that say what `execute` does (#901,
which groups five lines of #457).

ON MAIN AT c7a3ff16, with a stub `gh`, an empty `GH_CONFIG_DIR` and local
remotes, as the issue measured at 5017830:
- ONE ORDER. `check` asked the plan's `org:` and `id:` after its three
  repository names, in `_manifest_values`, and refused either, exit 2,
  before it listed any finding; `execute` asked the two leg paths and the
  two branch names before them, in `_checked_plan_values`. A plan edited to
  `id: "North Wind"` and `legs.spec_path: "../spec"` was `REFUSED
  plan-bad-id` to `check` and `REFUSED plan-bad-leg-path` to `execute`;
  `org: "-evil"` beside the same path was `unsafe-value` about the
  organisation to the one and `plan-bad-leg-path` to the other. Both now ask
  the organisation and the id before the leg paths and the branch names,
  after the three repository names (`_checked_org_and_id`): they say which
  project the plan is about, which is a more basic thing for a plan to get
  wrong than a path or a branch inside it.
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
  nothing else" now, and no finding about another key of a pin says so.

AND BEFORE WHAT `check` LISTS (#1020), on main at 6da757cb, measured the
same way. `check` refuses a bad `org:` or `id:` outright, exit 2, and lists
none of its findings, but `execute` asked the two only after refusing a plan
for another repository, a name the naming policy refuses, an unanswered
entry or a source that has moved on, each a finding of `check`'s: a bad id
beside an unanswered entry was `plan-bad-id` to `check` and
`plan-unresolved` to `execute`, and so on. `check` asked them only where the
policy took the plan's names, so an unsafe `org:` beside a refused name was
a finding about the name, or about another repository, to `check`. Both
commands now ask the two first of what they read of the plan, right after
its keys and its three repository names and before `_work_root`
(`_checked_org_and_id`): before an unwritable `--work-dir` too, which `check`
lists as a finding and `execute` refused before it opened the source
(RV1125's SHOULD-1). That decides #716's L4-48 as well: an unsafe `org:` held
to a repository is `unsafe-value` to both, where `execute` said
`plan-not-the-source`. And a `pins:` ENTRY that is no pin is said as `pins:`
itself is (`_read_as`): the number 7, not `7`.

AND BEFORE `_work_root`'S OTHER REFUSALS AND A GONE SOURCE (#1179, RV1125b's
NIT-A). The one row that pinned that position against the work directory
used a directory `chmod` made unwritable. `_work_root` refuses two more
things before it makes anything, a `--work-dir` that is a file and one every
user can write in, and both commands refuse a plan whose source is gone: a
bad `id:` or `org:` beside any of them is the value's refusal, in both.

Each test runs `check` and then `execute --yes`, both with the same
`--local-remote-dir`, on one hand-edited plan, as the issue measured, and
asserts that the directory the legs go in was never made. `execute` stops
before `git filter-repo` would run, but asks for it first, so the tests skip
where it is not installed. No `gh` runs: given `--local-remote-dir`, `check`
asks the disk whether each leg repository exists.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, WINDOWS_SKIP, git, make_source_repo,
                      planned, run_script)
from test_adopt_pins import ANSWERS, pin_entry
from test_adopt_root_symlinks import unwritable_work  # noqa: F401 - a fixture
from test_adopt_template_values import with_line

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import double_quoted  # noqa: E402

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


def both_on(text: str, base: Path, work: Path | None = None):
    """`check` and then `execute --yes` on the plan `text`, written at
    `base`, each given the same `--local-remote-dir`: `(check's run,
    execute's run)`. Neither makes the directory the legs go in. A `work`
    is the `--work-dir` of both; without one, `execute` is given `base /
    "work"` and `check` none."""
    plan = base / PLAN_FILE
    plan.write_bytes(text.encode(UTF8))
    remotes = base / "remotes"
    checked = run_script(ADOPT, "check", "--plan", str(plan),
                         "--local-remote-dir", str(remotes),
                         *(("--work-dir", str(work)) if work else ()))
    executed = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                          "--local-remote-dir", str(remotes),
                          "--work-dir", str(work or base / "work"))
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


# --- one order: the organisation and the id before paths and branches -------

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


# --- ... and only a `digest_source:` finding says it ------------------------

#: The rest of a finding about any other key of a pin, after its `why`: the
#: pin file says how the digest was read, but such a finding is not about
#: that field, so it ends as it did (#901).
WRITTEN_FROM = (
    "`execute` writes the pin file from the commit and the digest `plan` "
    "records, and nothing else: re-run `plan` with "
    "`--pin opensoft/openGlass@<40 hex commit>`")

#: `(the plan's one `pins:` entry, its code, what its finding says of it)`,
#: by test id. `short-commit` is a finding whose ending `_pin_row_problem`
#: gives itself, `no-commit` one whose ending is `_pin_written_from`'s, from
#: the keys it names: a row of each, for each is a way the ending could say
#: "how it was read" of a key that is not `digest_source:`.
OTHER_FINDINGS = {
    "short-commit": (pin_entry(commit=COMMIT[:12], digest=DIGEST,
                               source="gh-api-tree-recursive"),
                     "plan-pin-malformed",
                     "records `commit: '0123456789ab'`, which is not 40 hex: "
                     "a tag, a branch or an abbreviated oid can be moved, "
                     "and a commit cannot"),
    "no-commit": (pin_entry(digest=DIGEST, source="gh-api-tree-recursive",
                            omit=("commit",)),
                  "plan-pin-unrecorded", "records no `commit:`"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(OTHER_FINDINGS))
def test_a_finding_about_another_key_does_not_say_how_it_was_read(
        answered, tmp_path, case):
    """Only a finding about an entry's `digest_source:` says `execute`
    writes how the digest was read: one about its `commit:` ends "records,
    and nothing else:" as it did, in `check` and in `execute`'s refusal."""
    entry, code, why = OTHER_FINDINGS[case]
    checked, executed = both_on(pinned(answered, entry), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(
        f"FINDING {code}: `pins:` entry 1 ('openGlass') {why}. "
        f"{WRITTEN_FROM}"), found[0]
    assert "records, and nothing else:" in found[0], found[0]
    assert "how it was read" not in found[0], found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert refused_with(executed, tmp_path / PLAN_FILE, found) == code


# --- the organisation and the id before what `check` lists (#1020) ---------

#: The answers `planned` gives, but `examples/`'s: its entry keeps `leg:
#: null`, an unanswered question.
UNANSWERED = tuple(answer for answer in ANSWERS if answer[0] != "examples/")
#: More hand edits: a leg name the naming policy refuses, another
#: organisation than the source's, and a plan with no `id:` whose assembly
#: name gives a bad derived id, which the policy refuses too.
REFUSED_NAME = ("\n  spec: Northwind-spec\n", "\n  spec: bad_name\n")
ANOTHER_ORG = ("\norg: testorg\n", "\norg: acme\n")
DERIVED_BAD_ID = (("\nid: northwind\n", "\n"),
                  ("\n  assembly: Northwind\n", "\n  assembly: north_wind\n"))
#: The repository the source's `origin` names, which `plan` records and a
#: plan for it is held to (`_held_repository`).
HELD = "testorg/Northwind"
#: What both commands name first about the derived id.
DERIVED_ID_REFUSED = ("REFUSED plan-bad-id: {plan}: id (not set in the plan, "
                      "so legs.assembly lowercased) is 'north_wind', which "
                      "must match ^[a-z0-9][a-z0-9-]*$")

#: `(the edits, what else the plan holds, what both commands refuse first)`,
#: by test id. What else: `unanswered` leaves `examples/` unanswered,
#: `moved` commits to the source after `plan`, and `held` gives the source
#: an `origin` naming `HELD`. On 6da757cb `execute` named first, row by
#: row: `plan-unresolved`, `plan-stale`, `naming-unclassified`,
#: `plan-not-the-source`, `naming-unclassified`, `plan-not-the-source`
#: (L4-48), `plan-unresolved`, `plan-stale`, `naming-unclassified` and
#: `plan-not-the-source`; in the last two rows `check` named the same, as a
#: finding, exit 1, and in the others it refused the organisation or the id.
BESIDE = {
    "id-and-unanswered": ((BAD_ID,), {"unanswered"}, ID_REFUSED),
    "id-and-moved-on": ((BAD_ID,), {"moved"}, ID_REFUSED),
    "id-and-refused-name": ((BAD_ID, REFUSED_NAME), set(), ID_REFUSED),
    "id-and-another-repository": ((BAD_ID, ANOTHER_ORG), {"held"},
                                  ID_REFUSED),
    "derived-id-and-its-refused-name": (DERIVED_BAD_ID, set(),
                                        DERIVED_ID_REFUSED),
    "org-held-to-a-repository": ((BAD_ORG,), {"held"}, ORG_REFUSED),
    "org-and-unanswered": ((BAD_ORG,), {"unanswered"}, ORG_REFUSED),
    "org-and-moved-on": ((BAD_ORG,), {"moved"}, ORG_REFUSED),
    "org-and-refused-name": ((BAD_ORG, REFUSED_NAME), set(), ORG_REFUSED),
    "org-held-and-refused-name": ((BAD_ORG, REFUSED_NAME), {"held"},
                                  ORG_REFUSED),
}


def planned_with(base: Path, holds: set) -> str:
    """The text of the plan `plan` writes for a new source at `base`, with
    what `holds` names (`BESIDE`): each needs a source of its own."""
    source = make_source_repo(base / "Thing")
    if "held" in holds:
        git("remote", "add", "origin", f"https://github.com/{HELD}.git",
            cwd=source)
    text = planned(source, base, dict(
        UNANSWERED if "unanswered" in holds else ANSWERS)).read_text(
            encoding=UTF8)
    if "moved" in holds:
        (source / "later.txt").write_text("later\n", encoding=UTF8)
        git("add", "later.txt", cwd=source)
        git("commit", "-q", "-m", "later work", cwd=source)
    return text


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(BESIDE))
def test_the_org_or_the_id_is_named_before_what_check_lists(tmp_path,
                                                            case):
    """`check` refuses a bad `org:` or `id:` before it lists a finding, so
    `execute` asks the two before it refuses anything `check` lists: an
    unanswered entry, a source that has moved on, a name the policy
    refuses, a plan for another repository. Each such plan is refused for
    the organisation or the id by both, exit 2, in the same words, and no
    leg is made."""
    edits, holds, refused = BESIDE[case]
    text = edited(planned_with(tmp_path, holds), *edits)
    checked, executed = both_on(text, tmp_path)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked).startswith(
        refused.format(plan=tmp_path / PLAN_FILE)), checked.stderr
    assert named_first(executed) == named_first(checked), executed.stderr


#: A leg's repository name `checked_value` refuses.
UNSAFE_LEG_NAME = ("\n  spec: Northwind-spec\n", '\n  spec: "-spec"\n')
#: What both commands name first about it.
LEG_NAME_REFUSED = ("REFUSED unsafe-value: legs.spec is '-spec', which is not "
                    "a value this tool will put on a `git` or `gh` command "
                    "line")


@needs_filter_repo
@pytest.mark.parametrize("edit", [BAD_ID, BAD_ORG], ids=["id", "org"])
def test_the_three_repository_names_are_still_asked_first(answered,
                                                          tmp_path, edit):
    """A GUARD, which passes on 6da757cb too: the organisation and the id
    are asked right AFTER the plan's three repository names, by `check` at
    its head as by `execute` (`plan.names()`), so a leg name
    `checked_value` refuses beside a bad `id:` or `org:` is that name's
    `unsafe-value` to both, as it was, and not the other value's."""
    checked, executed = both_on(edited(answered, UNSAFE_LEG_NAME, edit),
                                tmp_path)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked) == LEG_NAME_REFUSED, checked.stderr
    assert named_first(executed) == LEG_NAME_REFUSED, executed.stderr


@needs_filter_repo
@pytest.mark.parametrize(("edit", "refused"),
                         [(BAD_ID, ID_REFUSED), (BAD_ORG, ORG_REFUSED)],
                         ids=["id", "org"])
def test_the_org_or_the_id_is_named_before_an_unwritable_work_dir(
        answered, tmp_path, unwritable_work, edit, refused):
    """RV1125's SHOULD-1: `check` lists a `--work-dir` this user cannot write
    in as a finding (#524), and `execute` refuses it before it opens the
    source, so both asked the plan's `org:` and `id:` after it, and a bad
    `id:` or `org:` beside one was `plan-bad-id` or `unsafe-value` to
    `check` and `adopt-work-dir-unwritable` to `execute`. Both ask the two
    right after the plan's keys and its three repository names, before
    `_work_root`, so each is refused for the organisation or the id, exit 2,
    in the same words, and neither says a word of the directory. The tests
    skip where `chmod` cannot keep this user from writing a directory."""
    checked, executed = both_on(edited(answered, edit), tmp_path,
                                unwritable_work)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked).startswith(refused), checked.stderr
    assert named_first(executed) == named_first(checked), executed.stderr
    for run in (checked, executed):
        assert "adopt-work-dir-unwritable" not in run.stderr, run.stderr


#: What a bad `id:` or `org:` is refused beside what `_work_root` and the
#: source refuse: none of the three codes is said by either command (#1179).
NOT_SAID_BESIDE_A_VALUE = ("adopt-work-dir-unwritable",
                           "adopt-work-dir-shared", "plan-source-gone")
BAD_ID_OR_ORG = pytest.mark.parametrize(
    ("edit", "refused"), [(BAD_ID, ID_REFUSED), (BAD_ORG, ORG_REFUSED)],
    ids=["id", "org"])


def named_before_a_refusal(text: str, base: Path, edit: tuple[str, str],
                           refused: str, control: str,
                           work: Path | None = None) -> None:
    """The plan `text` is one both commands refuse, exit 2, with the first
    line `control` (the control: `check` asks the source and the directory
    as `execute` does). Edited by `edit`, a bad `id:` or `org:` that
    `refused` begins, it is refused for that value by both, exit 2, in the
    same words, and neither says a word of the directory or the source."""
    for run in both_on(text, base, work):
        assert run.returncode == 2, run.stdout + run.stderr
        assert named_first(run) == control, run.stderr
    checked, executed = both_on(edited(text, edit), base, work)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert named_first(checked).startswith(refused), checked.stderr
    assert named_first(executed) == named_first(checked), executed.stderr
    for run in (checked, executed):
        for code in NOT_SAID_BESIDE_A_VALUE:
            assert code not in run.stderr, run.stderr


@needs_filter_repo
@BAD_ID_OR_ORG
def test_the_org_or_the_id_is_named_before_a_work_dir_that_is_a_file(
        answered, tmp_path, edit, refused):
    """RV1125b's NIT-A (#1179): `_work_root` refuses a `--work-dir` that is
    a file, `adopt-work-dir-unwritable`, before anything is made, so the
    two asks sit before it in both commands, as before an unwritable one:
    a bad `id:` or `org:` beside the file is that value's refusal to each,
    and the plan unedited beside the same file is the control."""
    a_file = tmp_path / "a-file"
    a_file.write_text("mine\n", encoding=UTF8)
    control = ("REFUSED adopt-work-dir-unwritable: --work-dir "
               f"`{os.path.realpath(a_file)}` cannot be made: making it a "
               "directory failed (File exists)")
    named_before_a_refusal(answered, tmp_path, edit, refused, control, a_file)


@needs_filter_repo
@WINDOWS_SKIP
@BAD_ID_OR_ORG
def test_the_org_or_the_id_is_named_before_a_shared_work_dir(
        answered, tmp_path, edit, refused):
    """RV1125b's NIT-A (#1179): `_work_root` refuses a `--work-dir` every
    user can write in, without the sticky bit, `adopt-work-dir-shared`,
    before anything is made in it, so the two asks sit before it in both
    commands: a bad `id:` or `org:` beside one is that value's refusal to
    each, and the plan unedited beside the same directory is the control.
    The shared test is never asked on Windows."""
    work = tmp_path / "shared-work"
    work.mkdir()
    os.chmod(work, 0o777)
    control = ("REFUSED adopt-work-dir-shared: --work-dir "
               f"`{os.path.realpath(work)}` can be written in by every user, "
               "without the sticky bit, so another user could rename or "
               "replace what this run makes in it")
    named_before_a_refusal(answered, tmp_path, edit, refused, control, work)


@needs_filter_repo
@BAD_ID_OR_ORG
def test_the_org_or_the_id_is_named_before_a_source_that_is_gone(
        answered, tmp_path, edit, refused):
    """RV1125b's NIT-A (#1179): both commands refuse a plan whose
    `source.local_path` names nothing, which `plan` did not clone,
    `plan-source-gone`, once the source is opened, so the two asks sit
    before it: a bad `id:` or `org:` beside a gone source is that value's
    refusal to each, `check` asking it before it opens the source, and the
    plan unedited beside the same path is the control."""
    gone = tmp_path / "Gone"
    text = with_line(answered, f"  local_path: {double_quoted(str(gone))}")
    control = ("REFUSED plan-source-gone: the plan's `source.local_path`, "
               f"`{gone}`, names nothing that exists, and the plan does not "
               "record it as a clone `plan` made (`source.cloned` is not "
               "`true`), so nothing clones it again")
    named_before_a_refusal(text, tmp_path, edit, refused, control)


@pytest.mark.parametrize(("edit", "refused"),
                         [(BAD_ID, ID_REFUSED), (BAD_ORG, ORG_REFUSED)],
                         ids=["id", "org"])
def test_check_asks_the_org_and_the_id_before_it_says_anything_else(
        answered, tmp_path, edit, refused):
    """RV1125's NIT-2: `check` prints its findings only at its end, so none
    of them tells a refusal asked at its head from one asked later, and the
    first row of this section could not. What it does print is the Triad
    advisory, on stdout, once it has made the work directory and opened the
    source, so a refusal asked after that comes after the advisory. Asked at
    its head, a bad `id:` or `org:` is refused before anything is read, made
    or said: nothing is on stdout, and stderr starts with the refusal. The plan
    unedited is the control: it says the advisory first."""
    plan = tmp_path / PLAN_FILE
    remotes = ("--local-remote-dir", str(tmp_path / "remotes"))
    plan.write_bytes(answered.encode(UTF8))
    said = run_script(ADOPT, "check", "--plan", str(plan), *remotes)
    assert said.returncode == 0, said.stdout + said.stderr
    assert said.stdout.startswith("triad "), said.stdout
    plan.write_bytes(edited(answered, edit).encode(UTF8))
    checked = run_script(ADOPT, "check", "--plan", str(plan), *remotes)
    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert checked.stdout == "", checked.stdout
    assert named_first(checked).startswith(refused), checked.stderr


# --- a `pins:` entry that is no pin, said as its reader read it -------------

#: `(the plan's `pins:` block, what entry 1 was read as, as `_read_as` says
#: it)`, by test id. On 6da757cb each was `repr`'s: `7`, `True`, `None`,
#: `[1, 2]`.
NOT_A_PIN = {
    "number": ("pins:\n  - 7\n", "the number 7"),
    "boolean": ("pins:\n  - true\n", "the boolean true"),
    "null": ("pins:\n  - ~\n", "null"),
    "list": ("pins:\n  - [1, 2]\n", "a list of 2 item(s)"),
}


@needs_filter_repo
@pytest.mark.parametrize("case", sorted(NOT_A_PIN))
def test_an_entry_that_is_no_pin_is_said_as_its_reader_read_it(
        answered, tmp_path, case):
    """An entry of `pins:` that is neither a name nor a mapping was spelled
    as Python spells it, `True` or `None`, where `pins:` itself is said as
    `_read_as` says what the plan's reader read (#901): `check` finds it in
    those words now, and `execute` refuses it in them."""
    block, read = NOT_A_PIN[case]
    checked, executed = both_on(
        edited(answered, ("\npins: []\n", f"\n{block}")), tmp_path)
    found = findings_of(checked)
    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert len(found) == 1, checked.stderr
    assert found[0].startswith(
        f"FINDING plan-pin-malformed: `pins:` entry 1 is {read}, not a pin: "
        "re-run `plan` with `--pin <openProduct>@<40 hex commit>`"), found[0]
    assert executed.returncode == 2, executed.stdout + executed.stderr
    assert refused_with(executed, tmp_path / PLAN_FILE,
                        found) == "plan-pin-malformed"
