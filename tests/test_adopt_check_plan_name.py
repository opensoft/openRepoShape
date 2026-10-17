# SPDX-License-Identifier: Apache-2.0
"""`check` says what `execute` says of a plan's name and of its source (#716).

#499 made an in-place adoption keep the source's own name, and told
`check` and `execute` to say so alike. Two lines of that work were left,
both about a plan edited by hand, both refused by `execute` already, so that
nothing was lost, and `check` is the command that tells a person before any
leg exists:

- L4-38: `check` asked `_check_names` about the plan's names without the
  source, so a plan in the source's own name that the naming policy refuses
  (`billing-service`) was `naming-unclassified` with no remedy, where
  `execute` says that the source cannot be adopted in place under that name
  and that renaming it on GitHub comes first. `check` now hands the source to
  `_check_names` where `execute` does, and prints that remedy, once, after
  its findings.
- L4-40: where the live source names no repository, the plan's own
  `source: repository:` was asked nothing. A plan for acme/Atlas edited to
  `Atlsa`, with `origin` then removed from the source, or run against a copy
  that has none (`--source`), checked `plan ok`, and `execute` went on to ask
  GitHub about `acme/Atlsa`. The plan's record holds it now, in both.
- L4-48: the comments on #499's `org:` read said that a hand edit is caught
  "whatever `org:` then holds". An `org:` that `checked_value` refuses is
  `unsafe-value` in `check`, which asks it first, and `plan-not-the-source`
  in `execute`, which compares first: caught in both, compared only by one.
  The last test here pins that, so the comments say what the commands do.

Nothing here reaches GitHub or runs `gh`: each source's `origin` is an
`https://github.com/` URL that nothing fetches, and `execute` is run
in-process with every `git` and `gh` command it would run replaced by one
that fails the test (`refused_before_any_remote`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import ADOPT, git, run_script
from test_adopt_project_is_the_source import (  # noqa: F401 - a fixture
    PLAN, PLAN_NOT_THE_SOURCE, RENAME_FIRST, RETYPE, adopter, check, edited,
    findings, plan, refused_before_any_remote, source_of)

#: The organisation, the source's own name, and a typo of it.
ORG, OWN, TYPO = "acme", "Atlas", "Atlsa"
#: The remedy `plan-not-the-source` gives, up to where it names the source's
#: own name and no more. `{}` is what it says first, as `check` does not.
OWN_NAME = ("Remediation: {}Run `plan` again with `--project Atlas --org "
            "acme`, the source's own name,")
#: Why `plan-not-the-source` refuses, after what the plan names and the
#: source is.
WHY = ("an in-place adoption keeps the source's own name, and `execute` acts "
       "on the repository `org:` and `legs.assembly:` name")
#: What `check` finds of the plan edited to `Atlsa` where the source's
#: `origin` is gone and the plan's record of it is the repository.
RECORDED = (f"the plan's `org: {ORG}` with its `legs.assembly: {TYPO}` and "
            f"`project: {TYPO}` names {ORG}/{TYPO}, and the plan records the "
            f"source as {ORG}/{OWN} (its `origin` names no repository): {WHY}")


def renamed(plan_path: Path, name: str, was: str = "Northwind") -> None:
    """The plan with `name` for its project and the three names that carry
    it, as a hand edit makes them."""
    edited(plan_path, *[(f"{key}: {was}{suffix}", f"{key}: {name}{suffix}")
                        for key, suffix in (("project", ""),
                                            ("  assembly", ""),
                                            ("  spec", "-spec"),
                                            ("  code", "-code"))])


def planned_for(base: Path, project: str, org: str = ORG) -> Path:
    """A source with no `origin`, and the plan `plan` writes for it as
    `project`, which the plan then records no repository for."""
    source = source_of(base, None)
    written = plan(base, source, "--project", project, "--org", org)
    assert written.returncode == 0, written.stdout + written.stderr
    return source


def planned_from_origin(base: Path, repository: str = f"{ORG}/{OWN}") -> Path:
    """A source whose `origin` is `repository` and the plan for it, which
    records `repository` as the source's. Returns the source."""
    source = source_of(base, repository)
    written = plan(base, source, "--project", repository.split("/")[1])
    assert written.returncode == 0, written.stdout + written.stderr
    return source


# --- L4-38: `check` says what `execute` says of the source's own name -------

@pytest.mark.parametrize("repository, code", [
    ("acme/billing-service", "naming-unclassified"),
    ("acme/Tools-Install", "naming-role-mismatch"),
], ids=["no-family", "not-a-project-leg"])
def test_check_and_execute_say_the_same_remedy_of_the_sources_own_name(
        adopter, tmp_path, monkeypatch, repository, code):
    """A plan whose names are the source's own, in a name the policy
    refuses, as `plan` wrote it before the source had an `origin` and a
    hand edit made it: `execute` says the source cannot be adopted in place
    under that name and that renaming it comes first. `check` said only
    that the name matched no family; it says that too, once, and never to
    retype `--project`."""
    org, _, name = repository.partition("/")
    source = planned_for(tmp_path, "Northwind", org)
    renamed(tmp_path / PLAN, name)
    git("remote", "add", "origin", f"https://github.com/{repository}.git",
        cwd=source)

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line.split(":")[0] for line in findings(checked.stderr)] == [
        f"FINDING {code}"], checked.stderr
    assert refusal.code == code
    assert refusal.remediation == f"Remediation: {repository} {RENAME_FIRST}"
    # Said as `execute` says it, as a line of its own, after the findings.
    assert checked.stderr.splitlines().count(refusal.remediation) == 1, \
        checked.stderr
    assert RETYPE not in checked.stderr


def test_check_says_nothing_of_renaming_a_leg_whose_name_is_the_plans_own(
        tmp_path):
    """A leg's name is the plan's own to edit, and `_check_names` keeps the
    remedy it gave for one, which `check` never printed: a leg the policy
    refuses is a finding with no rename-first text, though the source is
    named."""
    planned_from_origin(tmp_path)
    edited(tmp_path / PLAN, (f"  spec: {OWN}-spec", "  spec: bad_name"))

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        "FINDING naming-unclassified: 'bad_name' matches no family in the "
        "naming policy"], checked.stderr
    assert "Remediation:" not in checked.stderr
    assert "gh repo rename" not in checked.stderr


def test_check_does_not_tell_the_source_to_be_renamed_for_another_name(
        adopter, tmp_path, monkeypatch):
    """Where the plan names ANOTHER repository, `execute` stops at
    `plan-not-the-source` and never asks the naming policy, and the name
    the policy would refuse is not the source's. `check` finds both, and its
    one remedy is `plan-not-the-source`'s; it does not tell a source named
    `Atlas`, a name the policy takes, that it cannot be adopted under it."""
    planned_from_origin(tmp_path)
    renamed(tmp_path / PLAN, "bad_name", OWN)

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line.split(":")[0] for line in findings(checked.stderr)] == [
        f"FINDING {PLAN_NOT_THE_SOURCE}",
        "FINDING naming-unclassified"], checked.stderr
    remedies = [line for line in checked.stderr.splitlines()
                if line.startswith("Remediation:")]
    assert len(remedies) == 1, checked.stderr
    assert remedies[0].startswith(OWN_NAME.format("")), remedies
    assert "cannot be adopted in place" not in checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE


# --- L4-40: the plan's record holds it where the source names none ----------

def unreadable_origin(source: Path) -> None:
    """The source as `execute` meets it after `git remote remove origin`:
    no repository named."""
    git("remote", "remove", "origin", cwd=source)


def test_a_plan_edited_to_a_typo_is_found_where_the_origin_is_gone(
        adopter, tmp_path, monkeypatch):
    """The issue's own: a plan for acme/Atlas edited to `Atlsa`, then `git
    remote remove origin`. On main `check` said `plan ok` and `execute` went
    on to ask GitHub about `acme/Atlsa`. Both find `plan-not-the-source`,
    naming what the plan records, and neither says to run `plan` with a
    project that is not a name."""
    source = planned_from_origin(tmp_path)
    unreadable_origin(source)
    assert check(tmp_path / PLAN).returncode == 0, "the plan, unedited"
    renamed(tmp_path / PLAN, TYPO, OWN)

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: {RECORDED}"], checked.stderr
    assert checked.stderr.count(OWN_NAME.format("")) == 1, checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE
    assert refusal.detail == f"{tmp_path / PLAN}: {RECORDED}"
    assert refusal.remediation.startswith(OWN_NAME.format(
        "no leg repository was created and nothing was pushed. ")), \
        refusal.remediation


def test_a_source_given_by_source_that_has_no_origin_holds_the_plan_too(
        adopter, tmp_path, monkeypatch):
    """`--source <a copy with no origin>`, which `check` and `execute` both
    take: the copy names no repository, so the plan's record does. The
    source the plan names has its `origin`, and is not the one read."""
    source = planned_from_origin(tmp_path)
    copy = tmp_path / "copy"
    git("clone", "-q", str(source), str(copy), cwd=tmp_path)
    unreadable_origin(copy)
    renamed(tmp_path / PLAN, TYPO, OWN)

    checked = run_script(ADOPT, "check", "--plan", str(tmp_path / PLAN),
                         "--source", str(copy))
    real = adopter.Plan.open_source
    # `refused_before_any_remote` passes no `--source`: every open of the
    # source is handed the copy as one.
    monkeypatch.setattr(adopter.Plan, "open_source",
                        lambda self, _, *rest, **keywords: real(
                            self, str(copy), *rest, **keywords))
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: {RECORDED}"], checked.stderr
    assert (refusal.code, refusal.detail) == (
        PLAN_NOT_THE_SOURCE, f"{tmp_path / PLAN}: {RECORDED}")


@pytest.mark.parametrize("held", ["acme/Atlas", "ACME/atlas",
                                  "acme/Atlas.git"],
                         ids=["exact", "another-case", "dot-git"])
def test_a_plan_that_names_the_recorded_repository_is_not_refused(
        adopter, tmp_path, monkeypatch, held):
    """Control: a record that the plan's names are, as GitHub resolves them
    (without case, with or without `.git`), holds nothing against it. `check`
    says `plan ok`, and `execute` goes on to the first command it runs
    against GitHub, which the stand-in turns into the test's own failure."""
    source = planned_from_origin(tmp_path)
    unreadable_origin(source)
    edited(tmp_path / PLAN, ("  repository: acme/Atlas",
                             f"  repository: {held}"))

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "\nplan ok\n" in checked.stdout
    with pytest.raises(AssertionError, match=r"execute ran \['git', "
                                             r"'ls-remote', 'https://github"
                                             r"\.com/acme/Atlas\.git'"):
        refused_before_any_remote(adopter, monkeypatch, tmp_path / PLAN,
                                  tmp_path / "work")


def test_a_plan_that_recorded_no_repository_holds_nothing(
        adopter, tmp_path, monkeypatch):
    """Control: a source with no `origin` when `plan` read it has no
    repository to record (`repository: null`), so the plan's names are its
    own, as ever: edited to another, `check` still says `plan ok`, and
    `execute` goes on to ask about the name it was given."""
    planned_for(tmp_path, "Northwind")
    renamed(tmp_path / PLAN, "Northwnd")

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "\nplan ok\n" in checked.stdout
    with pytest.raises(AssertionError, match=r"execute ran \['git', "
                                             r"'ls-remote', 'https://github"
                                             r"\.com/acme/Northwnd\.git'"):
        refused_before_any_remote(adopter, monkeypatch, tmp_path / PLAN,
                                  tmp_path / "work")


@pytest.mark.parametrize("held", ["[acme, Atlas]", "Atlas", "2026", "~",
                                  "acme/a/b"],
                         ids=["list", "no-owner", "number", "null",
                              "three-segments"])
def test_a_record_that_names_no_repository_holds_nothing_and_raises_none(
        tmp_path, held):
    """A record that is no text, or that names no `owner/repo`, is read as
    none, as `_github_name` reads a name: `check` says `plan ok` for the
    plan edited to a typo, with no traceback, as it did."""
    source = planned_from_origin(tmp_path)
    unreadable_origin(source)
    edited(tmp_path / PLAN, ("  repository: acme/Atlas",
                             f"  repository: {held}"))
    renamed(tmp_path / PLAN, TYPO, OWN)

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "Traceback" not in checked.stderr
    assert "\nplan ok\n" in checked.stdout


def test_the_sources_own_origin_is_asked_before_the_plans_record(tmp_path):
    """Control: where the source names a repository, that is the one the
    plan is held to, as #499 made it; the plan's record of an older one is
    never asked. A plan for the source as it is checks ok, though the record
    names another."""
    planned_from_origin(tmp_path)
    edited(tmp_path / PLAN, ("  repository: acme/Atlas",
                             "  repository: acme/Elsewhere"))

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "\nplan ok\n" in checked.stdout


# --- L4-48: what `check` does with an `org:` `checked_value` refuses --------

#: The value `execute` spells, and `check` asks `checked_value` about.
UNSAFE_ORGS = [("org: acme labs", "'acme labs'"),
               ("org: [acme, labs]", "\"['acme', 'labs']\""),
               ('org: ""', "''"),
               ("org: -acme", "'-acme'"),
               ("org: \u00e1cme", "'\u00e1cme'"),
               ("org: {a: b}", "\"{'a': 'b'}\"")]


@pytest.mark.parametrize("org, spelled", UNSAFE_ORGS,
                         ids=["space", "list", "empty", "leading-dash",
                              "not-ascii", "mapping"])
def test_an_unsafe_org_is_unsafe_in_check_and_compared_in_execute(
        adopter, tmp_path, monkeypatch, org, spelled):
    """L4-48: the comments on #499's `org:` read said any `org:` is caught
    "whatever the file holds". It is caught in both commands, and not by the
    same one: `check` asks `checked_value` first and ends in `unsafe-value`,
    exit 2, never comparing it with the repository; `execute` compares it
    first and refuses it as `plan-not-the-source`."""
    planned_from_origin(tmp_path)
    edited(tmp_path / PLAN, ("org: acme", org))

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert f"REFUSED unsafe-value: org is {spelled}, which is not a value " \
        "this tool will put on a `git` or `gh` command line" in \
        checked.stderr.splitlines()
    assert PLAN_NOT_THE_SOURCE not in checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE


def test_check_compares_an_unsafe_org_where_no_manifest_is_built(
        tmp_path):
    """The one place `check` reaches the comparison with such an `org:`:
    where the plan's own names are refused first, `_manifest_values` builds
    no manifest and never asks `checked_value`, so `check` finds the plan
    names another repository, and the name, and exits 1."""
    planned_from_origin(tmp_path)
    edited(tmp_path / PLAN, ("org: acme", "org: acme labs"))
    renamed(tmp_path / PLAN, "bad_name", OWN)

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line.split(":")[0] for line in findings(checked.stderr)] == [
        f"FINDING {PLAN_NOT_THE_SOURCE}",
        "FINDING naming-unclassified"], checked.stderr
    assert "`org: acme labs`" in findings(checked.stderr)[0]
