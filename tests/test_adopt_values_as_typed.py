# SPDX-License-Identifier: Apache-2.0
"""`plan` and `check` take a value as it was typed, or refuse it by name (#902).

Lane 3 grouped seven lines of #457 into #902, each measured at `5017830` and
again on main before this change:

- L1-K3. A hand-edited plan's bare `id: 007`, `tracking_branch: true` or
  `adopt_branch: 007`, which the plan's reader reads as a number or a boolean,
  was `str` of what was read: `check` said `plan ok`, `execute` said
  `adoption verified`, and `project.yaml` said `id: "7"`, or both legs and the
  split were on the branch `True`. `check` now refuses an `id:` read so, as
  `plan-bad-id`, and finds a branch read so under the key's own code, saying
  what was read; `execute` refuses both before any leg exists, in the same
  words (`tracking_branch: -007` too: `execute` asked `checked_value` first,
  so it said `unsafe-value` of the `-7` nobody typed where `check` said
  `plan-bad-tracking-branch`).
- L2-86 and L2-87. `--org ''`, `--elected-on ''` and `--reference ''` were read
  as not passed: the organisation of the source's `origin` was planned and
  named once as `--org is '~x'`, today's date was recorded, and the default
  reference. Each is a value passed now, refused by name by its own rule, as
  `--tracking-branch ''` is.
- L2-88. `check`'s `plan-bad-id` of a plan with no `id:` said "`id:` is
  'north_wind'" and sent the person to `--id`. It names the id as derived
  from `legs.assembly`, and that as the remedy.
- L2-89. In place, `naming-unclassified` and `adopt-not-the-source` gave the
  way out, renaming the source, and no rule for the new name. Both say it.
- L2-90 and L2-82 (adopt's half of #459's). A passed `--id` that is no id was
  refused before a `--project` the naming policy refuses, and was told "pass
  an explicit lowercase --id" though `foo_bar` is both. The naming refusal
  speaks first, and the id's remedy says what an id may hold, in the words
  the scaffold and `family.py init` use (#911).

Nothing here reaches GitHub: every source is local, `check` is run against a
plan whose names it asks `gh repo view` about only once they pass (the
session's guard answers, `tests/gh_guard.py`), and `execute` runs under
`--local-remote-dir`.
"""

from __future__ import annotations

import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, git, make_source_repo, run_script, write_plan
from test_adopt_plan_flag_refusals_first import Harness
from test_adopt_project_is_the_source import (NAME_RULE, RENAME_FIRST, TREE,
                                              findings, in_place_remedy,
                                              source_of)

#: `repo_shape.PROJECT_ID_RE`, as the refusals print it.
PATTERN = "^[a-z0-9][a-z0-9-]*$"
#: What a passed `--id` that is no id is told (#902), in the scaffold's and
#: `family.py init`'s words (#911).
WHAT_AN_ID_HOLDS = ("Remediation: pass an --id of lowercase letters, digits "
                    "and hyphens, starting with a letter or digit.")
#: And a plan's `id:` the pattern refuses.
PLAN_ID_HOLDS = (
    "Remediation: set `id:` in the plan to lowercase letters, digits and "
    "hyphens, starting with a letter or digit, or re-run `plan` with an --id "
    "of that form. The GitHub topic is derived from it.")
#: What a plan with no `id:` is told: the name its id comes from.
LEGS_ASSEMBLY = (
    f"Remediation: change `legs.assembly` in the plan to {NAME_RULE}, or "
    "re-run `plan` with a --project of that form. The id is legs.assembly "
    "lowercased, and an `id:` would leave `legs.assembly`, the assembly "
    "root's name, as it is. The GitHub topic is derived from the id.")
#: What a value read as a number or a boolean is told.
QUOTE_IT = (
    "Remediation: write each value named between double quotes in the plan, "
    'as typed (`"007"`, `"true"`), so that the plan\'s reader takes it as '
    "text, and run `check` again; or re-run `plan`, which writes every value "
    "so that it is read back as typed.")
#: `checked_value`'s words for an empty value, as `--tracking-branch ''`
#: has them.
EMPTY_ORG = ("REFUSED unsafe-value: --org is '', which is not a value this "
             "tool will put on a `git` or `gh` command line")

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")


def first_two(result) -> list[str]:
    """The refusal and its remedy, the first two lines on stderr, once the
    run exited 2."""
    assert result.returncode == 2, result.stdout + result.stderr
    return result.stderr.splitlines()[:2]


def planned(tmp_path: Path, *flags: str, branches: tuple = ()) -> Path:
    """A plan of a small source with no `origin`, written by `plan` with
    `flags`, and the source given `branches` besides `main` first."""
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    for branch in branches:
        git("branch", branch, cwd=source)
    out = tmp_path / "adoption-plan.yaml"
    result = write_plan(source, out, extra=flags)
    assert result.returncode == 0, result.stdout + result.stderr
    return out


def set_line(plan: Path, key: str, value: str | None) -> None:
    """The plan's top-level `key:` line set to `value`, or deleted where it
    is None, as a hand edit makes it, LF as `plan` wrote it."""
    text = plan.read_text(encoding="utf-8")
    pattern = re.compile(rf"^{re.escape(key)}: .*\n", re.M)
    assert len(pattern.findall(text)) == 1, text
    text = pattern.sub("" if value is None else f"{key}: {value}\n", text)
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def check(plan: Path):
    return run_script(ADOPT, "check", "--plan", str(plan))


def execute(plan: Path, base: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(base / "remotes"),
                      "--work-dir", str(base / "work"))


def not_text(key: str, read: str, text: str) -> str:
    return (f"`{key}:` was read out of the plan as {read}, not as text, so "
            f"`execute` would take it as the text `{text}`")


# --- L1-K3: a bare value the plan's reader reads as a number or a boolean ---

@pytest.mark.parametrize("key, typed, branch, read, text", [
    ("tracking_branch", "007", "7", "the number 7", "7"),
    ("tracking_branch", "true", "True", "the boolean true", "True"),
    ("tracking_branch", "1.50", "1.5", "the number 1.5", "1.5"),
    ("adopt_branch", "007", None, "the number 7", "7"),
    ("adopt_branch", "true", None, "the boolean true", "True"),
], ids=["tracking-007", "tracking-true", "tracking-1.50", "split-007",
        "split-true"])
def test_check_finds_a_branch_read_as_a_number_or_a_boolean(
        tmp_path, key, typed, branch, read, text):
    """L1-K3 and L1-15: with a branch `7` in the source, `tracking_branch:
    007` checked ok and was adopted onto `7`. It is a finding under the key's
    own code, saying what the plan's reader made of it and the text
    `execute` would have taken, and no other finding names it."""
    plan = planned(tmp_path, branches=(branch,) if branch else ())
    set_line(plan, key, typed)

    checked = check(plan)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    code = key.replace("_", "-")
    assert findings(checked.stderr) == [
        f"FINDING plan-bad-{code}: {not_text(key, read, text)}"], \
        checked.stderr
    assert QUOTE_IT in checked.stderr.splitlines(), checked.stderr


@pytest.mark.parametrize("typed, read, text", [
    ("007", "the number 7", "7"),
    ("true", "the boolean true", "True"),
    ("2026", "the number 2026", "2026"),
], ids=["007", "true", "2026"])
def test_check_refuses_an_id_read_as_a_number_or_a_boolean(tmp_path, typed,
                                                           read, text):
    """L1-K3: `id: 007` was the id `7`, which the pattern takes, so `check`
    said `plan ok` and `execute` wrote `id: "7"`. It is `plan-bad-id`, where
    `check` and `execute` refuse an id, saying what was read; `2026`, whose
    text is the same, is refused too, because what was typed is not known."""
    plan = planned(tmp_path)
    set_line(plan, "id", typed)

    assert first_two(check(plan)) == [
        f"REFUSED plan-bad-id: {plan}: {not_text('id', read, text)}",
        QUOTE_IT]


@pytest.mark.parametrize("key, quoted, branches", [
    ("id", '"007"', ()),
    ("tracking_branch", '"007"', ("007",)),
    ("adopt_branch", '"true"', ()),
], ids=["id", "tracking-branch", "split-branch"])
def test_the_same_values_quoted_check_ok(tmp_path, key, quoted, branches):
    """Control: the remedy, typed. Between double quotes each is text, as
    typed, and `check` says `plan ok`."""
    plan = planned(tmp_path, branches=branches)
    set_line(plan, key, quoted)

    checked = check(plan)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "plan ok" in checked.stdout


@needs_filter_repo
@pytest.mark.parametrize("key, typed, branch, code", [
    ("id", "007", None, "plan-bad-id"),
    ("tracking_branch", "true", "True", "plan-bad-tracking-branch"),
    ("adopt_branch", "007", None, "plan-bad-adopt-branch"),
], ids=["id", "tracking-branch", "split-branch"])
def test_execute_refuses_each_before_any_leg_exists(tmp_path, key, typed,
                                                    branch, code):
    """L1-K3: `execute` of each ended `adoption verified`, exit 0. It refuses
    under `check`'s code before a leg repository is made or anything is
    pushed: the remote directory holds no leg, and the source no split."""
    plan = planned(tmp_path, branches=(branch,) if branch else ())
    set_line(plan, key, typed)

    done = execute(plan, tmp_path)

    assert done.returncode == 2, done.stdout + done.stderr
    assert done.stderr.startswith(f"REFUSED {code}: "), done.stderr
    assert "adoption verified" not in done.stdout
    remotes = tmp_path / "remotes"
    assert not any(remotes.glob("*.git")), list(remotes.iterdir())
    branches = git("branch", "--list", cwd=tmp_path / "Thing").stdout
    assert "adopt/three-repo-shape" not in branches
    assert not re.search(r"^\s*7$", branches, re.M), branches


@needs_filter_repo
@pytest.mark.parametrize("key, code", [
    ("tracking_branch", "plan-bad-tracking-branch"),
    ("adopt_branch", "plan-bad-adopt-branch"),
], ids=["tracking-branch", "split-branch"])
def test_execute_refuses_a_negative_number_in_checks_words(tmp_path, key,
                                                           code):
    """L1-K3: `tracking_branch: -007` is the number -7, and `-7` is a value
    `checked_value` refuses, so `execute`, which asked it first, said
    `unsafe-value` of a `-7` nobody typed while `check` said what was read
    (#520: the two refuse a branch name in the same words). It asks the
    number-or-boolean question first, as `check` does, and refuses under the
    key's own code with `check`'s sentence and remedy, before any leg
    exists."""
    plan = planned(tmp_path)
    set_line(plan, key, "-007")
    sentence = not_text(key, "the number -7", "-7")

    checked = check(plan)
    done = execute(plan, tmp_path)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [f"FINDING {code}: {sentence}"], \
        checked.stderr
    assert first_two(done) == [f"REFUSED {code}: {sentence}", QUOTE_IT]
    assert "unsafe-value" not in done.stderr
    assert not any((tmp_path / "remotes").glob("*.git"))


# --- L2-86 and L2-87: a flag passed empty is a value ------------------------

@pytest.mark.parametrize("origin", [
    "https://example.invalid/~x/Thing.git",
    "https://github.com/testorg/Atlas.git",
    None,
], ids=["origin-org-the-validator-refuses", "another-repository",
        "no-origin"])
def test_an_empty_org_is_refused_as_passed(tmp_path, origin):
    """L2-86: `--org ''` was counted passed for its label and read as not
    given for its value, so the organisation of the source's `origin` was
    planned: one refusal said `--org is '~x'`, which nobody typed, and
    `adopt-not-the-source` said `--org` was not given; with no `origin` it
    was `adopt-no-org`. It is a value passed, refused by name as
    `--tracking-branch ''` is, before the source's own organisation is
    read."""
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    if origin is not None:
        git("remote", "add", "origin", origin, cwd=source)
    out = tmp_path / "adoption-plan.yaml"

    refused = write_plan(source, out, project="Thing", org="")

    assert first_two(refused)[0] == EMPTY_ORG, refused.stderr
    assert "not given" not in refused.stderr, refused.stderr
    assert not out.exists()


def test_an_empty_election_date_is_refused_by_name(tmp_path):
    """L2-87: `--elected-on ''` recorded today's date, exit 0. It is the
    date passed, and `election_date` refuses it by name."""
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    out = tmp_path / "adoption-plan.yaml"

    refused = write_plan(source, out, extra=("--elected-on", ""))

    assert first_two(refused)[0] == (
        "REFUSED election-date-malformed: --elected-on '' is not a "
        "YYYY-MM-DD date (and a plan file's `elected_on:` carries the same "
        "form)"), refused.stderr
    assert not out.exists()


def test_an_empty_reference_is_refused_in_the_validators_words(tmp_path):
    """L2-87: `--reference ''` recorded the default reference, exit 0. It is
    the reference passed, and the project's own validator refuses it, named
    as the flag, as the scaffold's is (#911)."""
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    out = tmp_path / "adoption-plan.yaml"

    refused = write_plan(source, out, extra=("--reference", ""))

    assert first_two(refused)[0] == (
        "REFUSED adopt-manifest-invalid: --reference is '', which the "
        "project's own validate-manifest.py refuses: manifest-reference: "
        "reference is ''; drop the key or name the document the election "
        "followed."), refused.stderr
    assert not out.exists()


def test_check_finds_an_empty_reference_in_the_plan(tmp_path):
    """And `reference: ""` in a plan is that value too: `execute` wrote the
    default reference in its place without a word. `check` asks the
    validator of it, by the plan's key."""
    plan = planned(tmp_path)
    set_line(plan, "reference", '""')

    checked = check(plan)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        "FINDING plan-manifest-invalid: reference is '', which the project's "
        "own validate-manifest.py refuses: manifest-reference: reference is "
        "''; drop the key or name the document the election followed."], \
        checked.stderr


@pytest.mark.parametrize("reference, chosen", [
    (None, True), ('""', False)], ids=["no-reference", "empty-reference"])
def test_a_bad_date_says_it_chooses_the_reference_only_where_none_is_set(
        tmp_path, reference, chosen):
    """With `reference: ""` a value, the date chooses no reference: #294's
    finding of a bad `elected_on:` says it does only where the plan sets
    none, as `execute` now reads it."""
    plan = planned(tmp_path)
    set_line(plan, "elected_on", '"someday"')
    set_line(plan, "reference", reference)

    checked = check(plan)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    said = [line for line in findings(checked.stderr)
            if line.startswith("FINDING election-date-malformed: ")]
    assert len(said) == 1, checked.stderr
    assert said[0].endswith("chooses the reference by it") == chosen, said


# --- L2-88: a plan with no `id:` ---------------------------------------------

def test_a_plan_with_no_id_names_its_id_as_derived_from_legs_assembly(
        tmp_path):
    """L2-88: rv699's plan, its `id:` deleted and its `legs.assembly` edited
    to `North_Wind`. The refusal named "`id:`", which the plan has none of,
    and sent the person to `--id`; it names the id as `DERIVED_ID` does and
    sends them to `legs.assembly`."""
    plan = planned(tmp_path, "--project", "NorthWind", "--id", "northwind")
    set_line(plan, "id", None)
    text = plan.read_text(encoding="utf-8")
    with plan.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\n  assembly: NorthWind\n",
                                  "\n  assembly: North_Wind\n", 1))

    assert first_two(check(plan)) == [
        f"REFUSED plan-bad-id: {plan}: id (not set in the plan, so "
        f"legs.assembly lowercased) is 'north_wind', which must match "
        f"{PATTERN}", LEGS_ASSEMBLY]


@pytest.mark.parametrize("typed", ["foo_bar", '"North Wind"'])
def test_a_plans_id_the_pattern_refuses_is_told_what_an_id_may_hold(
        tmp_path, typed):
    """L2-82's sentence, for the plan's own key: `id: foo_bar` was told to
    re-run `plan` "with an explicit lowercase --id", and it is both."""
    plan = planned(tmp_path)
    set_line(plan, "id", typed)
    held = typed.strip('"')

    assert first_two(check(plan)) == [
        f"REFUSED plan-bad-id: {plan}: `id:` is {held!r} and must match "
        f"{PATTERN}", PLAN_ID_HOLDS]


# --- L2-89, L2-90 and L2-82: the name before a passed id ---------------------

def test_in_place_the_naming_refusal_says_the_rule_before_renaming(tmp_path):
    """L2-89: the source's own name, `North_Wind`, is refused in place with
    `_rename_first`'s way out, which said no rule for the new name. It says
    the rule first, as the derived id's refusal does (L2-54)."""
    source = source_of(tmp_path, "testorg/North_Wind")

    refused = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", "North_Wind", "--id", "north-wind",
                         "--elected-by", "Test Human", "--out",
                         str(tmp_path / "plan.yaml"))

    assert first_two(refused) == [
        "REFUSED naming-unclassified: 'North_Wind' matches no family in the "
        "naming policy",
        in_place_remedy("testorg/North_Wind", "naming-unclassified")]


def test_not_the_source_says_the_rule_its_own_name_breaks(tmp_path):
    """L2-89: `--project NorthWind` over `testorg/North_Wind` is
    `adopt-not-the-source`, and the source's own name is no remedy; the way
    out said no rule for the new name, and says it now."""
    source = source_of(tmp_path, "testorg/North_Wind")

    refused = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", "NorthWind", "--id", "north-wind",
                         "--elected-by", "Test Human", "--out",
                         str(tmp_path / "plan.yaml"))

    remedy = first_two(refused)[1]
    assert remedy == (
        "Remediation: no plan was written. The source's own name is no "
        "remedy either: 'North_Wind' matches no family in the naming policy. "
        f"The name must be {NAME_RULE}. testorg/North_Wind {RENAME_FIRST}"), \
        refused.stderr


NOT_IN_PLACE_RULE = f"Remediation: --project takes {NAME_RULE}."


@pytest.mark.parametrize("origin, project, passed, code, remedy", [
    (None, "North_Wind", "north_wind", "naming-unclassified",
     NOT_IN_PLACE_RULE),
    (None, "North_Wind", "", "naming-unclassified", NOT_IN_PLACE_RULE),
    ("testorg/Atlas", "North_Wind", "north_wind", "naming-unclassified",
     NOT_IN_PLACE_RULE),
    ("testorg/North_Wind", "North_Wind", "north_wind", "naming-unclassified",
     in_place_remedy("testorg/North_Wind", "naming-unclassified")),
    (None, "Tools-Install", "tools_install", "naming-role-mismatch",
     "Remediation: --project takes one CamelCase token. Two forms beyond "
     "the bare one MAY be the assembly root"),
], ids=["no-origin", "empty-id", "another-repository", "in-place",
        "not-a-project-leg"])
def test_a_refused_name_speaks_before_a_passed_id(tmp_path, origin, project,
                                                  passed, code, remedy):
    """L2-90: `--project North_Wind --id north_wind` was told "pass an
    explicit lowercase --id", and its retype, `--id north-wind`, then met
    `naming-unclassified`, which no `--id` mends. The naming refusal speaks
    first, as the scaffold's and `family.py init`'s do (#911), in the words
    it has where it speaks later: in place, the source's own name is
    renamed first; another repository's name is the person's to retype."""
    source = source_of(tmp_path, origin)

    refused = run_script(ADOPT, "plan", "--source", str(source),
                         "--project", project, "--org", "testorg",
                         f"--id={passed}", "--elected-by", "Test Human",
                         "--out", str(tmp_path / "plan.yaml"))

    detail, said = first_two(refused)
    assert detail.startswith(f"REFUSED {code}: {project!r} "), refused.stderr
    assert said.startswith(remedy), refused.stderr
    assert "adopt-bad-id" not in refused.stderr


@pytest.mark.parametrize("passed", ["foo_bar", "Foo-Bar", "-north",
                                    "north wind", ""])
def test_a_passed_id_is_told_what_an_id_may_hold(tmp_path, passed):
    """L2-82, adopt's half: `--project NorthWind --id foo_bar` was told
    "pass an explicit lowercase --id", though it is explicit and lowercase:
    its fault is the underscore. The remedy says what an id may hold, in
    the scaffold's words (#911); the name passes, so the id is refused."""
    source = make_source_repo(tmp_path / "Thing", tree=TREE, edits=())
    out = tmp_path / "adoption-plan.yaml"

    refused = write_plan(source, out, extra=(f"--id={passed}",))

    assert first_two(refused) == [
        f"REFUSED adopt-bad-id: --id {passed!r} must match {PATTERN}",
        WHAT_AN_ID_HOLDS]
    assert not out.exists()


@pytest.mark.skipif(sys.platform == "win32",
                    reason="the `gh` stub is a `#!/bin/sh` script")
def test_an_org_repo_sources_own_name_speaks_before_a_passed_id_uncloned(
        tmp_path):
    """L2-90 with an `org/repo` source, which `plan` clones: since #903 a
    passed `--id` is refused with the flags, before the clone, and the
    naming refusal after it. A passed id beside a name the policy refuses
    is left to where the source is known, and that is before the clone for
    an `org/repo` one: the name is refused, in place, and `gh` never runs."""
    harness = Harness(tmp_path)

    refused = harness.plan(
        "testorg/North_Wind", "--id", "north_wind", work=True,
        planned=("--project", "North_Wind", "--org", "testorg",
                 "--elected-by", "Test Human", "--elected-on", "2026-09-02"))

    assert first_two(refused) == [
        "REFUSED naming-unclassified: 'North_Wind' matches no family in the "
        "naming policy",
        in_place_remedy("testorg/North_Wind", "naming-unclassified")]
    assert harness.gh_calls() == []
    assert not harness.work.exists()
