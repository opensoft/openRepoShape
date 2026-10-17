# SPDX-License-Identifier: Apache-2.0
"""An in-place adoption keeps the source's own name (#499).

`--project` names all three repositories, and without `--local-remote-dir`
`execute` acts on `https://github.com/<org>/<project>.git`: the split branch it
asks for and pushes, the pull request it opens and the topic it sets. In place
that repository IS the source, and nothing compared the two. A source named
`billing-service` was refused `naming-unclassified` with "--project takes one
CamelCase token"; the `--project BillingService` that steered to planned and
checked `plan ok` against `acme/billing-service`, and `execute` then asked
GitHub about `acme/BillingService`. A typo (`Atlsa`) and an `--org` that is not
the source's did the same.

Brett Heap's ruling, 2026-10-13: "Casefold; rename first". Where the source
names a repository, `plan` refuses an `--org` and a `--project` that name
another, compared without case (`adopt-not-the-source`), before it writes
anything; `check` finds, and `execute` refuses before it asks anything else, a
plan edited to name another (`plan-not-the-source`). Where the source's own
name is one the naming policy refuses, every one of those refusals says that
it cannot be adopted in place under that name and that renaming it on GitHub
comes first, and none says to retype `--project`. A source that names no
repository is asked nothing, as before; an `origin` that is a path names none
since #521 (`tests/test_adopt_origin_repository.py`).

Nothing here reaches GitHub or runs `gh`: each source's `origin` is an
`https://github.com/` URL that nothing fetches, `plan` and `check` read it
from the source's own config, and `execute` is run in-process with every
`git` and `gh` command it would run replaced by one that fails the test.
"""

from __future__ import annotations

import importlib.util
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, git, make_source_repo, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

NOT_THE_SOURCE = "adopt-not-the-source"
PLAN_NOT_THE_SOURCE = "plan-not-the-source"
#: The hint `naming-unclassified` gives where `--project` is the person's to
#: choose. In place it is not, and none of these refusals may give it.
RETYPE = "--project takes one CamelCase token"
#: What every refusal of a source's own name says instead.
RENAME_FIRST = (
    "cannot be adopted in place under that name: an in-place adoption keeps "
    "the source's own name, and `--project` cannot rename it. Whether to "
    "rename it is a human's decision, made first on GitHub (`gh repo "
    "rename`); then run `plan` again against the renamed repository "
    "(`--source <org>/<new name>`, or a clone whose `origin` names it), with "
    "its new name as `--project`.")
#: The rule `naming-unclassified` gives for `--project`, which a derived
#: id's remedy names too (#658, rv699).
NAME_RULE = "one CamelCase token with no hyphen, underscore, dot or space"
#: What `adopt-bad-id` says of an id derived from the source's own name,
#: before the repository and `RENAME_FIRST` (#658).
DERIVED_OWN_NAME = ("the id is --project lowercased, and --project is the "
                    f"source's own name, which must be {NAME_RULE}.")
#: A source small enough that `plan` asks no question.
TREE = {"README.md": "# here\n", "src/app.py": "print(1)\n",
        "specs/001/spec.md": "# Spec\n"}
PLAN = "adoption-plan.yaml"
WHY = ("an in-place adoption keeps the source's own name, and `execute` "
       "pushes the split to the repository they name, opens its pull request "
       "there and sets its topic on it")
#: How the refusal names an organisation nobody passed (#427).
OF_ORIGIN = ("with the organisation of the source's `origin` (`--org` not "
             "given)")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_is_the_source",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_of(base: Path, repository: str | None,
              directory: str = "source") -> Path:
    """A one-commit source whose `origin` is `repository` on GitHub, or
    which has none. Nothing fetches it: `plan` reads the URL alone."""
    source = make_source_repo(base / directory, tree=TREE, edits=())
    if repository is not None:
        git("remote", "add", "origin", f"https://github.com/{repository}.git",
            cwd=source)
    return source


def plan(base: Path, source: Path, *flags: str):
    """`plan` of `source` into `base`, with the flags given and no others
    but the ones every run here shares."""
    return run_script(ADOPT, "plan", "--source", str(source),
                      "--elected-by", "Test Human", "--elected-on",
                      "2026-10-13", "--out", str(base / PLAN), *flags)


def check(plan_path: Path):
    return run_script(ADOPT, "check", "--plan", str(plan_path))


def edited(plan_path: Path, *changes: tuple[str, str | None]) -> None:
    """The plan with each whole line `old` replaced by `new`, or deleted
    where `new` is None, as a hand edit makes it, LF as `plan` wrote it."""
    text = plan_path.read_text(encoding="utf-8")
    for old, new in changes:
        assert f"\n{old}\n" in text, text
        text = text.replace(f"\n{old}\n",
                            "\n" if new is None else f"\n{new}\n", 1)
    with plan_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def findings(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines()
            if line.startswith("FINDING ")]


# --- `plan` ---------------------------------------------------------------

@pytest.mark.parametrize("repository, flags, named, own", [
    # The issue's own: the hint `plan` gave for the source's name, followed.
    # No `--org`: it is the source's, and named so, not as a flag (#427).
    ("acme/billing-service", ("--project", "BillingService"),
     f"--project BillingService, {OF_ORIGIN}, names acme/BillingService",
     None),
    # A typo of a name the policy accepts.
    ("acme/Atlas", ("--project", "Atlsa"),
     f"--project Atlsa, {OF_ORIGIN}, names acme/Atlsa", "Atlas"),
    # The right name in another organisation.
    ("acme/Atlas", ("--project", "Atlas", "--org", "acme-labs"),
     "--org acme-labs and --project Atlas name acme-labs/Atlas", "Atlas"),
], ids=["hyphenated-source-retyped", "typo", "another-org"])
def test_plan_refuses_a_name_that_is_not_the_sources(tmp_path, repository,
                                                     flags, named, own):
    """Exit 2 before any plan is written, naming both repositories. Where
    the source's own name is one `plan` would take, it says to pass that;
    where it is not, that renaming comes first; never to retype
    `--project`."""
    source = source_of(tmp_path, repository)

    refused = plan(tmp_path, source, *flags)

    assert refused.returncode == 2, refused.stdout + refused.stderr
    detail, remediation = refused.stderr.splitlines()[:2]
    assert detail == (f"REFUSED {NOT_THE_SOURCE}: {named}, and the source is "
                      f"{repository}: {WHY}"), refused.stderr
    assert remediation.startswith("Remediation: no plan was written. "), \
        remediation
    if own:
        # The source's own name, straight after what was done: a url
        # names its repository, and only a url's or `--source`'s is
        # compared (#521).
        assert remediation.startswith(
            "Remediation: no plan was written. Run `plan` again with "
            f"`--project {own} --org acme`, the source's own name"), \
            remediation
        assert RENAME_FIRST not in remediation
    else:
        assert remediation.endswith(
            "The source's own name is no remedy either: 'billing-service' "
            "matches no family in the naming policy. acme/billing-service "
            f"{RENAME_FIRST}"), remediation
    assert RETYPE not in refused.stderr
    assert not (tmp_path / PLAN).exists()


@pytest.mark.parametrize("repository, code", [
    ("acme/billing-service", "naming-unclassified"),
    ("acme/Tools-Install", "naming-role-mismatch"),
], ids=["no-family", "not-a-project-leg"])
def test_the_sources_own_name_the_policy_refuses_is_renamed_first(
        tmp_path, repository, code):
    """`--project` as the source's own name, which the naming policy refuses:
    the policy's own finding, and in place of its hint to retype
    `--project`, that the source cannot be adopted in place under that name
    and that renaming it on GitHub comes first."""
    source = source_of(tmp_path, repository)

    refused = plan(tmp_path, source, "--project", repository.split("/")[1])

    assert refused.returncode == 2, refused.stdout + refused.stderr
    detail, remediation = refused.stderr.splitlines()[:2]
    assert detail.startswith(f"REFUSED {code}: "), refused.stderr
    assert remediation == f"Remediation: {repository} {RENAME_FIRST}"
    assert RETYPE not in refused.stderr
    assert not (tmp_path / PLAN).exists()


def test_a_name_in_another_case_is_the_source(tmp_path):
    """GitHub resolves `acme/atlas` and `ACME/Atlas` to one repository, so
    they are the source, and `plan` and `check` pass."""
    source = source_of(tmp_path, "acme/atlas")

    written = plan(tmp_path, source, "--project", "Atlas", "--org", "ACME")

    assert written.returncode == 0, written.stdout + written.stderr
    recorded = load_yaml(tmp_path / PLAN)
    assert (recorded["org"], recorded["project"]) == ("ACME", "Atlas")
    assert recorded["source"]["repository"] == "acme/atlas"
    checked = check(tmp_path / PLAN)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert "\nplan ok\n" in checked.stdout


@pytest.mark.parametrize("origin", [None, "repo.git"],
                         ids=["no-origin", "no-org-repo-in-it"])
def test_a_source_that_names_no_repository_is_asked_nothing(tmp_path,
                                                            origin):
    """No `origin`, or one that ends in no `org/repo`: there is no name to
    compare, and `plan` takes `--org` and `--project` as it always did."""
    source = source_of(tmp_path, None)
    if origin is not None:
        git("remote", "add", "origin", origin, cwd=source)

    written = plan(tmp_path, source, "--project", "Northwind", "--org",
                   "acme")

    assert written.returncode == 0, written.stdout + written.stderr
    assert load_yaml(tmp_path / PLAN)["source"]["repository"] is None


def cloned_from(adopter, monkeypatch, local: Path) -> None:
    """`gh repo clone` replaced by `git clone` of the local repository
    `local`, the one command the run is let make."""
    real = adopter.run

    def cloned(args, *rest, **keywords):
        assert args[:3] == ["gh", "repo", "clone"], args
        return real(["git", "clone", "-q", str(local), args[4]], *rest,
                    **keywords)

    monkeypatch.setattr(adopter, "run", cloned)


def test_an_org_repo_source_is_the_repository_it_names(adopter, tmp_path,
                                                       monkeypatch, capsys):
    """`--source acme/Atlas` names the repository it clones, and is compared
    as an `origin` is. `git clone` of a local repository stands in for `gh
    repo clone`."""
    cloned_from(adopter, monkeypatch, source_of(tmp_path, None, "Atlas"))
    code = adopter.main(["plan", "--source", "acme/Atlas", "--project",
                         "Atlsa", "--elected-by", "Test Human",
                         "--elected-on", "2026-10-13", "--out",
                         str(tmp_path / PLAN), "--work-dir",
                         str(tmp_path / "work")])

    assert code == 2
    err = capsys.readouterr().err
    assert err.startswith(
        f"REFUSED {NOT_THE_SOURCE}: --project Atlsa, with the organisation of "
        "`--source` (`--org` not given), names acme/Atlsa, and the source is "
        "acme/Atlas: "), err
    assert not (tmp_path / PLAN).exists()


def test_a_derived_id_of_a_cloned_sources_own_name_says_rename_first(
        adopter, tmp_path, monkeypatch, capsys):
    """#658, rv699: `--source testorg/North_Wind` names the repository it
    clones as an `origin` does, so the id derived from that name is told to
    rename it first, as for a local clone, and not to change `--project`."""
    cloned_from(adopter, monkeypatch, source_of(tmp_path, None, "North_Wind"))
    code = adopter.main(["plan", "--source", "testorg/North_Wind",
                         "--project", "North_Wind", "--elected-by",
                         "Test Human", "--elected-on", "2026-10-13", "--out",
                         str(tmp_path / PLAN), "--work-dir",
                         str(tmp_path / "work")])

    assert code == 2
    err = capsys.readouterr().err
    assert err.splitlines()[:2] == [
        "REFUSED adopt-bad-id: --id (not given, so --project lowercased) is "
        "'north_wind', which must match ^[a-z0-9][a-z0-9-]*$",
        f"Remediation: {DERIVED_OWN_NAME} testorg/North_Wind {RENAME_FIRST}"
    ], err
    assert not (tmp_path / PLAN).exists()


# --- `check` and `execute` --------------------------------------------------

@pytest.mark.parametrize("changes, said", [
    ((("project: Atlas", "project: Atlsa"),),
     "the plan's `org: acme` with its `project: Atlsa` names acme/Atlsa"),
    ((("  assembly: Atlas", "  assembly: Atlsa"),),
     "the plan's `org: acme` with its `legs.assembly: Atlsa` names "
     "acme/Atlsa"),
    ((("project: Atlas", "project: Atlsa"),
      ("  assembly: Atlas", "  assembly: Northwind")),
     "the plan's `org: acme` with its `legs.assembly: Northwind` and "
     "`project: Atlsa` names acme/Atlsa and acme/Northwind"),
    ((("org: acme", "org: acme-labs"),),
     "the plan's `org: acme-labs` with its `legs.assembly: Atlas` and "
     "`project: Atlas` names acme-labs/Atlas"),
], ids=["project", "legs-assembly", "both-apart", "org"])
def test_check_finds_a_plan_edited_to_name_another_repository(
        tmp_path, changes, said):
    """A plan `plan` wrote for the source checks ok; edited to name another
    repository, by its `project:`, its `legs.assembly:` or its `org:`, it is
    one finding naming what the plan names and what the source is, with
    the way back printed once after the findings."""
    source = source_of(tmp_path, "acme/Atlas")
    written = plan(tmp_path, source, "--project", "Atlas")
    assert written.returncode == 0, written.stdout + written.stderr
    assert check(tmp_path / PLAN).returncode == 0

    edited(tmp_path / PLAN, *changes)
    result = check(tmp_path / PLAN)

    assert result.returncode == 1, result.stdout + result.stderr
    assert [line for line in findings(result.stderr)
            if PLAN_NOT_THE_SOURCE in line] == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: {said}, and the source is "
        "acme/Atlas: an in-place adoption keeps the source's own name, and "
        "`execute` acts on the repository `org:` and `legs.assembly:` name"]
    assert result.stderr.count(
        "Remediation: Run `plan` again with `--project Atlas --org acme`, "
        "the source's own name,") == 1, result.stderr


def refused_before_any_remote(adopter, monkeypatch, plan_path: Path,
                              work: Path):
    """`execute --yes` without `--local-remote-dir`, in-process, with every
    command it runs through `run` -- `git ls-remote`, `gh repo create`, a
    push -- failing the test. Returns the refusal it raised."""
    monkeypatch.setattr(adopter, "_require_filter_repo", lambda: None)

    def nothing_is_run(args, *rest, **keywords):
        raise AssertionError(f"execute ran {args}")

    monkeypatch.setattr(adopter, "run", nothing_is_run)
    with pytest.raises(adopter.Refusal) as caught:
        adopter.cmd_execute(Namespace(
            plan=str(plan_path), source=None, local_remote_dir=None,
            allow_empty_leg=[], yes=True, work_dir=work))
    return caught.value


def test_execute_refuses_a_plan_edited_to_another_repository_first(
        adopter, tmp_path, monkeypatch):
    """On main the first thing such a plan's `execute` did was `git
    ls-remote` of the repository the plan names. It is refused as `check`
    finds it, before anything is run."""
    source = source_of(tmp_path, "acme/Atlas")
    written = plan(tmp_path, source, "--project", "Atlas")
    assert written.returncode == 0, written.stdout + written.stderr
    edited(tmp_path / PLAN, ("project: Atlas", "project: Atlsa"),
           ("  assembly: Atlas", "  assembly: Atlsa"),
           ("  spec: Atlas-spec", "  spec: Atlsa-spec"),
           ("  code: Atlas-code", "  code: Atlsa-code"))

    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert refusal.code == PLAN_NOT_THE_SOURCE
    assert refusal.detail == (
        f"{tmp_path / PLAN}: the plan's `org: acme` with its `legs.assembly: "
        "Atlsa` and `project: Atlsa` names acme/Atlsa, and the source is "
        "acme/Atlas: an in-place adoption keeps the source's own name, and "
        "`execute` acts on the repository `org:` and `legs.assembly:` name")
    assert refusal.remediation.startswith(
        "Remediation: no leg repository was created and nothing was pushed. "
        "Run `plan` again with `--project Atlas --org acme`"), \
        refusal.remediation


@pytest.mark.parametrize("new, held, spelled", [
    ("org: 2026", "the number 2026", "2026"),
    ("org: true", "the boolean true", "True"),
    ("org: ~", "null", "None"),
    (None, "absent", "None"),
], ids=["number", "boolean", "null", "deleted"])
def test_an_org_that_is_not_text_is_read_as_execute_reads_it(
        adopter, tmp_path, monkeypatch, new, held, spelled):
    """#513's review, SHOULD-1: `org:` was compared only when it was text,
    and `execute` reads it with `str()` (`_repository_urls`). A plan edited
    to `org: 2026`, `org: true` or `org: ~`, or with its `org:` line deleted,
    checked `plan ok`, and `execute` ran `git ls-remote` on
    `https://github.com/2026/Atlas.git`, `.../True/...` or `.../None/...`.
    Each is the repository `execute` would act on, and not the source:
    `check` finds it and `execute` refuses it, before anything is run."""
    source = source_of(tmp_path, "acme/Atlas")
    written = plan(tmp_path, source, "--project", "Atlas")
    assert written.returncode == 0, written.stdout + written.stderr
    edited(tmp_path / PLAN, ("org: acme", new))
    said = (f"the plan's `org:` ({held}, which `execute` spells {spelled}) "
            "with its `legs.assembly: Atlas` and `project: Atlas` names "
            f"{spelled}/Atlas, and the source is acme/Atlas: an in-place "
            "adoption keeps the source's own name, and `execute` acts on the "
            "repository `org:` and `legs.assembly:` name")

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert [line for line in findings(checked.stderr)
            if PLAN_NOT_THE_SOURCE in line] == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: {said}"], checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE
    assert refusal.detail == f"{tmp_path / PLAN}: {said}"
    assert refusal.remediation.startswith(
        "Remediation: no leg repository was created and nothing was pushed. "
        "Run `plan` again with `--project Atlas --org acme`"), \
        refusal.remediation
    # The comparison above is only as good as its read of `org:` being the one
    # `execute` acts on (#513's review, NIT-B): the URL `_repository_urls`
    # hands to the pushes spells the owner as `check` compared it. A later
    # edit that gives it a default of its own (`plan.get("org", ...)`) answers
    # `null` and `deleted` differently, and reopens SHOULD-1 for a source
    # whose repository the plan can then reach.
    loaded = adopter.Plan.load(tmp_path / PLAN)
    urls = adopter._repository_urls(
        Namespace(local_remote_dir=None), loaded, loaded.names(),
        loaded.open_source(None, tmp_path / "work"))[2]
    assert urls["assembly"] == f"https://github.com/{spelled}/Atlas.git"


def test_a_plan_older_than_its_sources_origin_is_caught_by_check_and_execute(
        adopter, tmp_path, monkeypatch):
    """The issue's plan, as `plan` wrote it on main: `BillingService` for a
    source named `billing-service`, here planned while the source had no
    `origin` and given its `origin` afterwards. `check` finds it and
    `execute` refuses it, each saying that renaming comes first, and
    neither says to retype `--project`."""
    source = source_of(tmp_path, None)
    written = plan(tmp_path, source, "--project", "BillingService", "--org",
                   "acme")
    assert written.returncode == 0, written.stdout + written.stderr
    git("remote", "add", "origin",
        "https://github.com/acme/billing-service.git", cwd=source)

    checked = check(tmp_path / PLAN)
    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert checked.returncode == 1, checked.stdout + checked.stderr
    assert findings(checked.stderr) == [
        f"FINDING {PLAN_NOT_THE_SOURCE}: the plan's `org: acme` with its "
        "`legs.assembly: BillingService` and `project: BillingService` names "
        "acme/BillingService, and the source is acme/billing-service: an "
        "in-place adoption keeps the source's own name, and `execute` acts "
        "on the repository `org:` and `legs.assembly:` name"]
    rename = (" The source's own name is no remedy either: 'billing-service' "
              f"matches no family in the naming policy. acme/billing-service "
              f"{RENAME_FIRST}")
    assert f"Remediation:{rename}\n" in checked.stderr, checked.stderr
    assert refusal.code == PLAN_NOT_THE_SOURCE
    assert refusal.remediation == (
        "Remediation: no leg repository was created and nothing was "
        f"pushed.{rename}")
    assert RETYPE not in checked.stderr + refusal.remediation


def test_execute_says_rename_first_of_the_sources_own_name(adopter, tmp_path,
                                                           monkeypatch):
    """A plan for `billing-service` itself, which `plan` refuses, is what an
    edit makes of one planned before the source had an `origin`: `execute`
    refuses the name the policy refuses, saying renaming comes first, before
    anything is run."""
    source = source_of(tmp_path, None)
    written = plan(tmp_path, source, "--project", "BillingService", "--org",
                   "acme")
    assert written.returncode == 0, written.stdout + written.stderr
    edited(tmp_path / PLAN, ("project: BillingService", "project: "
                             "billing-service"),
           ("  assembly: BillingService", "  assembly: billing-service"),
           ("  spec: BillingService-spec", "  spec: billing-service-spec"),
           ("  code: BillingService-code", "  code: billing-service-code"))
    git("remote", "add", "origin",
        "https://github.com/acme/billing-service.git", cwd=source)

    refusal = refused_before_any_remote(adopter, monkeypatch,
                                        tmp_path / PLAN, tmp_path / "work")

    assert refusal.code == "naming-unclassified"
    assert refusal.remediation == \
        f"Remediation: acme/billing-service {RENAME_FIRST}"


def test_a_source_with_no_origin_executes_past_the_comparison(
        adopter, tmp_path, monkeypatch):
    """Control: with no `origin` the plan is not compared, and `execute`
    goes on to the first command it runs against GitHub, which the stand-in
    turns into the test's own failure."""
    source = source_of(tmp_path, None)
    written = plan(tmp_path, source, "--project", "Northwind", "--org",
                   "acme")
    assert written.returncode == 0, written.stdout + written.stderr
    with pytest.raises(AssertionError, match=r"execute ran \['git', "
                                             r"'ls-remote', 'https://github"
                                             r"\.com/acme/Northwind\.git'"):
        refused_before_any_remote(adopter, monkeypatch, tmp_path / PLAN,
                                  tmp_path / "work")
