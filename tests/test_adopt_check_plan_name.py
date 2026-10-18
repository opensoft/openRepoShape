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
  `unsafe-value` in `check`, which asks it first, and, in `execute`,
  `plan-not-the-source` where the plan is held to a repository and
  `unsafe-value` where it is held to none: caught in both, compared only
  by one. The last tests here pin that, so the comments say what the
  commands do.
- RV825's MUST-1: v1.0.0 and v1.0.1 read a path `origin` as its last two
  directories (#521), so a plan they wrote can record `repository:
  clones/Atlas` for a source whose `origin` is `<dir>/clones/Atlas.git`.
  With the right `org:` put back by hand it is a correct plan, and holding
  it to that record refused it and brought back the advice #521 took out
  (`--org clones`). A record that is the path's own last two directories
  holds nothing.

Nothing here reaches GitHub, though `check` does run `gh`: given no
`--local-remote-dir`, it asks `gh repo view` of each leg repository (#798),
twice, and the session's guard answers it as a `gh` with no login does
(`tests/gh_guard.py`). Each source's `origin` is an `https://github.com/` URL
that nothing fetches, and `execute` is run in-process with every `git` and
`gh` command it would run replaced by one that fails the test
(`refused_before_any_remote`).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import ADOPT, git, run_script
from test_adopt_project_is_the_source import (  # noqa: F401 - a fixture
    PLAN, PLAN_NOT_THE_SOURCE, RENAME_FIRST, RETYPE, adopter, check, edited,
    findings, plan, refused_before_any_remote, source_of)
from test_adopt_relative_submodule_url import (
    HTTPS_ORIGIN, SIBLING, THING, planned as planned_with_submodule,
    source_with as source_with_submodule)

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
#: Why the live source names no repository, as the finding says it: it has
#: no `origin` at all, or its `origin` names none (a path, here).
NO_ORIGIN = "it has no `origin`"
NAMES_NONE = "its `origin` names no repository"


def recorded(why: str) -> str:
    """What `check` finds of the plan edited to `Atlsa` where the live
    source names no repository, for `why`, and the plan's record of it is
    the repository."""
    return (f"the plan's `org: {ORG}` with its `legs.assembly: {TYPO}` and "
            f"`project: {TYPO}` names {ORG}/{TYPO}, and the plan records the "
            f"source as {ORG}/{OWN} ({why}): {WHY}")


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

def unreadable_origin(source: Path, origin: str | None = None) -> None:
    """The source as `execute` meets it after `git remote remove origin`, or
    with `origin` instead: no repository named."""
    if origin is None:
        git("remote", "remove", "origin", cwd=source)
    else:
        git("remote", "set-url", "origin", origin, cwd=source)


@pytest.mark.parametrize("origin, why", [
    (None, NO_ORIGIN),
    ("/srv/mirrors/Atlas.git", NAMES_NONE),
    ("Atlas.git", NAMES_NONE),
    ("https://example.invalid/Atlas", NAMES_NONE),
], ids=["no-origin", "path", "one-segment-path", "url-with-no-org"])
def test_a_plan_edited_to_a_typo_is_found_where_the_origin_names_none(
        adopter, tmp_path, monkeypatch, origin, why):
    """The issue's own: a plan for acme/Atlas edited to `Atlsa`, then `git
    remote remove origin`. On main `check` said `plan ok` and `execute` went
    on to ask GitHub about `acme/Atlsa`. Both find `plan-not-the-source`,
    naming what the plan records, and neither says to run `plan` with a
    project that is not a name. A source with no `origin` says it has none
    (RV825's NIT-3); one whose `origin` names no repository, a path or a url
    that ends in no `org/repo`, says that. A record that is not the path's
    own last two directories is held."""
    source = planned_from_origin(tmp_path)
    unreadable_origin(source, origin)
    assert check(tmp_path / PLAN).returncode == 0, "the plan, unedited"
    renamed(tmp_path / PLAN, TYPO, OWN)

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: {recorded(why)}"], checked.stderr
    assert checked.stderr.count(OWN_NAME.format("")) == 1, checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE
    assert refusal.detail == f"{tmp_path / PLAN}: {recorded(why)}"
    assert refusal.remediation.startswith(OWN_NAME.format(
        "no leg repository was created and nothing was pushed. ")), \
        refusal.remediation


@pytest.mark.parametrize("keep_origin, why", [
    (False, NO_ORIGIN),
    (True, NAMES_NONE),
], ids=["no-origin", "origin-is-the-path-it-was-cloned-from"])
def test_a_source_given_by_source_that_names_none_holds_the_plan_too(
        adopter, tmp_path, monkeypatch, keep_origin, why):
    """`--source <a copy>`, which `check` and `execute` both take: a copy
    with no `origin`, or one whose `origin` is the path it was cloned from
    (which names no repository), names none, so the plan's record does. The
    source the plan names has its `origin`, and is not the one read."""
    source = planned_from_origin(tmp_path)
    copy = tmp_path / "copy"
    git("clone", "-q", str(source), str(copy), cwd=tmp_path)
    if not keep_origin:
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
        f"FINDING {PLAN_NOT_THE_SOURCE}: {recorded(why)}"], checked.stderr
    assert (refusal.code, refusal.detail) == (
        PLAN_NOT_THE_SOURCE, f"{tmp_path / PLAN}: {recorded(why)}")


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


# --- RV825's MUST-1: a plan v1.0.0 or v1.0.1 wrote for a path `origin` -------

@pytest.mark.parametrize("origin, record", [
    ("/srv/clones/Atlas.git", "clones/Atlas"),
    ("/srv/clones/Atlas", "clones/Atlas"),
    ("/srv/clones/Atlas.git/", "clones/Atlas"),
    # The record in another case than the path, as a person may retype it,
    # and as v1.0.1's own regex writes it, `Clones/ATLAS`.
    ("/srv/Clones/ATLAS.git", "clones/Atlas"),
    ("/srv/Clones/ATLAS.git", "Clones/ATLAS"),
    ("C:\\srv\\clones\\Atlas.git", "clones/Atlas"),
    ("\\\\server\\clones\\Atlas.git", "clones/Atlas"),
    ("file:///srv/clones/Atlas.git", "clones/Atlas"),
    ("clones/Atlas.git", "clones/Atlas"),
    # Two that v1.0.1 really records an exotic name for: its regex takes a
    # `:` for a separator and drops only the last `.git`.
    ("/srv/clones/Atlas.git.git", "clones/Atlas.git"),
    ("/srv/a:b/Atlas.git", "b/Atlas"),
], ids=["dot-git", "no-dot-git", "trailing-slash", "another-case",
        "v1-0-1-case", "backslashes", "share", "file-url", "relative",
        "two-dot-gits", "colon"])
def test_a_plan_that_v1_0_x_wrote_for_a_path_origin_is_still_a_correct_plan(
        adopter, tmp_path, monkeypatch, origin, record):
    """v1.0.0 and v1.0.1 read a path `origin` as its last two directories
    (#521): `plan --org acme --project Atlas` on a clone of
    `/srv/clones/Atlas.git` was refused as `--org clones`, and the plan
    written all the same recorded `repository: clones/Atlas`. With `org:
    acme` put back by hand it is a correct plan, and `check` said `plan ok`
    and `execute` went on to `acme/Atlas`. Held to that record it was
    refused, with a remedy that brings `--org clones` back; the record is
    the old reader's, not the source's name, so it holds nothing. The plan
    here is the one this version writes, with its null edited to what
    those versions recorded."""
    source = source_of(tmp_path, None)
    git("remote", "add", "origin", origin, cwd=source)
    written = plan(tmp_path, source, "--project", OWN, "--org", ORG)
    assert written.returncode == 0, written.stdout + written.stderr
    edited(tmp_path / PLAN, ("  repository: null",
                             f"  repository: {record}"))

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "\nplan ok\n" in checked.stdout
    with pytest.raises(AssertionError, match=r"execute ran \['git', "
                                             r"'ls-remote', 'https://github"
                                             r"\.com/acme/Atlas\.git'"):
        refused_before_any_remote(adopter, monkeypatch, tmp_path / PLAN,
                                  tmp_path / "work")


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
@pytest.mark.parametrize("held, code", [
    (True, PLAN_NOT_THE_SOURCE),
    (False, "unsafe-value"),
], ids=["held-to-a-repository", "held-to-none"])
def test_an_unsafe_org_is_unsafe_in_check_and_compared_by_execute_if_held(
        adopter, tmp_path, monkeypatch, org, spelled, held, code):
    """L4-48: the comments on #499's `org:` read said any `org:` is caught
    "whatever the file holds". It is caught in both commands, and not by the
    same one: `check` asks `checked_value` first and ends in `unsafe-value`,
    exit 2, never comparing it with the repository. `execute` compares it
    first, so it refuses it as `plan-not-the-source` where the plan is held
    to a repository, and as `unsafe-value` where it is held to none (a source
    that recorded no repository), as `check` does in both."""
    if held:
        planned_from_origin(tmp_path)
    else:
        planned_for(tmp_path, OWN)
    edited(tmp_path / PLAN, ("org: acme", org))

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 2, checked.stdout + checked.stderr
    unsafe = (f"REFUSED unsafe-value: org is {spelled}, which is not a value "
              "this tool will put on a `git` or `gh` command line")
    assert unsafe in checked.stderr.splitlines()
    assert PLAN_NOT_THE_SOURCE not in checked.stderr
    assert refusal.code == code
    if not held:
        assert unsafe[len("REFUSED "):] == f"{refusal.code}: {refusal.detail}"


def test_check_compares_an_unsafe_org_where_no_manifest_is_built(
        tmp_path):
    """Where `check` reaches the comparison with such an `org:`: where the
    plan's own names are refused first, `_manifest_values` builds no
    manifest and never asks `checked_value` (and no kept submodule url is
    relative: the next test), so `check` finds the plan names another
    repository, and the name, and exits 1."""
    planned_from_origin(tmp_path)
    edited(tmp_path / PLAN, ("org: acme", "org: acme labs"))
    renamed(tmp_path / PLAN, "bad_name", OWN)

    checked = check(tmp_path / PLAN)

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line.split(":")[0] for line in findings(checked.stderr)] == [
        f"FINDING {PLAN_NOT_THE_SOURCE}",
        "FINDING naming-unclassified"], checked.stderr
    assert "`org: acme labs`" in findings(checked.stderr)[0]


def test_check_asks_an_unsafe_org_first_where_a_kept_submodule_url_is_relative(
        adopter, tmp_path, monkeypatch):
    """RV825's SHOULD-1(b): `_submodule_findings` asks `checked_value` of
    `org:` earlier than `_manifest_values` does, wherever a kept submodule's
    url is relative. With the plan's names refused and `org: test org`,
    `check` ends in `unsafe-value`, exit 2, and never compares it, as it
    does with no relative url (the test above); `execute` says
    `plan-not-the-source`."""
    source = source_with_submodule(tmp_path, SIBLING, HTTPS_ORIGIN)
    made = planned_with_submodule(source, tmp_path)
    edited(made, ("org: testorg", "org: test org"))
    renamed(made, "bad_name", THING)

    checked = check(made)
    refusal = refused_before_any_remote(adopter, monkeypatch, made,
                                        tmp_path / "work")

    assert checked.returncode == 2, checked.stdout + checked.stderr
    assert checked.stderr.splitlines()[0] == (
        "REFUSED unsafe-value: org is 'test org', which is not a value this "
        "tool will put on a `git` or `gh` command line")
    assert PLAN_NOT_THE_SOURCE not in checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE
