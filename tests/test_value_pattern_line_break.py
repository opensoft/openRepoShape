# SPDX-License-Identifier: Apache-2.0
"""An `id:`, a date or a `repository:` read out of a file that ends in a line
break is not well formed (#1139, the follow-up of #1017).

THE DEFECT, measured on main 038dafba (Python 3.12.3). `DATE_RE` and
`QUALIFIED_RE` in both validators, `MEMBER_RE` (`family.py`'s spelling of
`QUALIFIED_RE`), `shape_advisory.py`'s `DATE_RE` and `update-shape.py`'s
`REPOSITORY_RE` ended in `$`, `repo_shape.PROJECT_ID_RE` ends in `$`, and
every caller read them with `.match`. In Python `$` also matches just before
a trailing line feed, and the YAML reader takes a double-quoted `"...\\n"`
(or a block scalar) as the value and a line feed. So, on main:

- `project.yaml`'s `id: "atlas\\n"` was only `FINDING manifest-topic`
  ("expected 'xf-project-atlas\\n'"), exit 1: a finding about the topic,
  not the id;
- its `elected_on: "2026-09-02\\n"`, and a leg's `repository:` so written,
  were `manifest ok`, exit 0;
- `family.yaml`'s `id: "inkrouter\\n"` and `created_on: "2026-09-04\\n"`
  were `family ok`, exit 0;
- a member's `repository: "InkRouter/IRRS\\n"` was `FINDING
  member-repository-name`, of a project "'IRRS\\n'", exit 1;
- `family.py add` of a member whose `project.yaml` read `id: "irqs\\n"`
  mounted it and committed a row with that id, exit 0, and the holder's
  gate, which compares the row with the same manifest, passed it;
- `update-shape.py` with no `--upstream`, over a shape pin whose
  `source_repository:` ended in a line feed, was `REFUSED unsafe-value:
  --upstream is ...`, naming a flag nobody passed.

THE RULE NOW. The seven module-level patterns end in `\\Z`, which matches at
the very end of the value and nowhere else, as #1017 ends `COMMIT_RE` and
`SHA256_RE`. `PROJECT_ID_RE` keeps its `$`: its text is what every id
refusal prints (`must match ^[a-z0-9][a-z0-9-]*$`), and the validators run
against each project's OWN copy of `repo_shape.py`, which a constant moved
there would reach only through `update-shape.py`. So the three callers that
read an id out of a file ask it with `fullmatch`: the two validators, and
`family.py`'s reading of a member's `project.yaml`, which is `member-bad-id`
now. `update-shape.py` names the pin's `source_repository:`, under the codes
it had, where no `--upstream` was passed.

LEFT AS THEY ARE, AND WHY:

- The argv readers of `PROJECT_ID_RE` (`--id` in `scaffold-project.py`,
  `family.py init` and `adopt-project.py`): each holds the id to
  `checked_value` after the pattern, which refuses a line feed as
  `unsafe-value` naming `--id` (`tests/test_derived_id_refusals.py`).
- `adopt-project.py`'s reading of a plan's `id:`: `check` and `execute` hold
  the plan's values to the project's own `validate-manifest.py`, which
  refused it on main in the topic's words and names the id now (the row
  below). It is the same value refused under the same code,
  `plan-manifest-invalid`, before any leg exists.
- `MEMBER_RE` takes `\\Z` because `tests/test_family_member_name.py` holds it
  to the validators' spelling; `--member` is stripped before it is asked, so
  no line feed reached its `$`, and `add` answers as it did.
- `shape_advisory.py`'s `DATE_RE` is followed by `date.fromisoformat`, which
  refused the line feed on main; its row is the pattern's alone.

No network and no GitHub: the projects and the family are the offline ones
of `conftest.py` and `test_family.py`, and every `update-shape.py` row is
refused before the upstream would be cloned.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from conftest import REPO, cloned_just_pushed, git, run_script
from test_adopt_values_as_typed import check as adopt_check
from test_adopt_values_as_typed import planned
from test_family import ORG, SPARE, family, validate  # noqa: F401
from test_family_add_refusals import (  # noqa: F401
    assert_unchanged, holder, offline, snapshot)
from test_family_member_name import pattern_spelled
from test_manifest_validator import validate as validate_manifest

UPDATE = REPO / "update-shape.py"
#: `repo_shape.PROJECT_ID_RE`, as the id refusals print it.
ID_PATTERN = "^[a-z0-9][a-z0-9-]*$"
#: A line feed, as the YAML reader reads a double-quoted `\n`.
LF = chr(10)


def rewritten(path: Path, old: str, new: str) -> None:
    """`path` with its one `old` written as `new`, as a hand edit makes it."""
    text = path.read_text(encoding="utf-8")
    assert text.count(old) == 1, f"fixture drift: {old!r} in {path}"
    path.write_bytes(text.replace(old, new).encode("utf-8"))


def findings(stderr: str) -> list[str]:
    return [line for line in stderr.splitlines()
            if line.startswith("FINDING ")]


# --- the patterns ------------------------------------------------------------

#: `(the module, the name, a value it takes)`: every module-level spelling
#: of a value pattern that this issue ends in `\Z`.
PATTERNS = [
    pytest.param("templates/assembly-root/scripts/validate-manifest.py",
                 "DATE_RE", "2026-09-02", id="manifest-DATE_RE"),
    pytest.param("templates/assembly-root/scripts/validate-manifest.py",
                 "QUALIFIED_RE", "testorg/Atlas", id="manifest-QUALIFIED_RE"),
    pytest.param("templates/family-root/scripts/validate-family.py",
                 "DATE_RE", "2026-09-04", id="family-DATE_RE"),
    pytest.param("templates/family-root/scripts/validate-family.py",
                 "QUALIFIED_RE", "InkRouter/IRRS", id="family-QUALIFIED_RE"),
    pytest.param("scripts/family.py", "MEMBER_RE", "InkRouter/IRQS",
                 id="family.py-MEMBER_RE"),
    pytest.param("scripts/shape_advisory.py", "DATE_RE", "2026-10-22",
                 id="shape_advisory-DATE_RE"),
    pytest.param("update-shape.py", "REPOSITORY_RE", "opensoft/openRepoShape",
                 id="update-shape-REPOSITORY_RE"),
]


def spelled(path: str, name: str) -> re.Pattern:
    """`name` as `path` spells it, READ and never run: the validators import
    a sibling `repo_shape.py` of their own."""
    patterns = pattern_spelled((REPO / path).read_bytes(), name)
    assert len(patterns) == 1, f"{path} spells {name} {len(patterns)} times"
    return re.compile(patterns[0])


def test_every_spelling_of_a_value_pattern_is_in_the_table():
    """A copy written later is in `PATTERNS`, and so gets the rows below, or
    this fails: every tracked module outside `tests/` that spells one of the
    names at module level."""
    names = {"DATE_RE", "QUALIFIED_RE", "MEMBER_RE", "REPOSITORY_RE"}
    listed = git("ls-files", "-z", "--", "*.py", cwd=REPO).stdout
    found = {(path, name)
             for path in listed.split("\0")
             if path and not path.startswith("tests/")
             for name in names
             if pattern_spelled((REPO / path).read_bytes(), name)}
    assert found == {tuple(row.values[:2]) for row in PATTERNS}


@pytest.mark.parametrize("path, name, value", PATTERNS)
def test_a_pattern_takes_its_value(path, name, value):
    """What it took on main, and takes now."""
    assert spelled(path, name).match(value) is not None


@pytest.mark.parametrize("path, name, value", PATTERNS)
def test_a_pattern_refuses_its_value_and_a_line_feed(path, name, value):
    """THE ISSUE'S ROW, one per pattern: `$` took the line feed on main."""
    assert spelled(path, name).match(value + LF) is None


# --- validate-manifest.py ----------------------------------------------------

@pytest.mark.parametrize("old, new, said", [
    pytest.param('id: "atlas"\n', 'id: "atlas\\n"\n',
                 f"FINDING manifest-id: id is 'atlas\\n'; it must match "
                 f"{ID_PATTERN}", id="id"),
    pytest.param('elected_on: "2026-09-02"\n',
                 'elected_on: "2026-09-02\\n"\n',
                 "FINDING manifest-elected-on: elected_on is "
                 "'2026-09-02\\n', expected an ISO date YYYY-MM-DD",
                 id="elected_on"),
    pytest.param("    repository: testorg/Atlas\n",
                 '    repository: "testorg/Atlas\\n"\n',
                 "FINDING manifest-leg-repository: leg 'assembly': "
                 "repository is 'testorg/Atlas\\n', expected `<org>/<Name>`",
                 id="leg-repository"),
])
def test_a_manifest_value_that_ends_in_a_line_break_is_a_finding(
        project, old, new, said):
    """On main the id was a finding about the topic, and the other two were
    `manifest ok`. Each is now the one finding, about the value itself."""
    rewritten(project / "project.yaml", old, new)
    result = validate_manifest(project)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [said], result.stderr


def test_a_leg_repository_double_quoted_is_still_ok(project):
    """The baseline of the leg row: the quotes are not what is refused."""
    rewritten(project / "project.yaml", "    repository: testorg/Atlas\n",
              '    repository: "testorg/Atlas"\n')
    result = validate_manifest(project)
    assert result.returncode == 0, result.stdout + result.stderr


def test_adopt_check_names_a_plan_id_that_ends_in_a_line_break_as_an_id(
        tmp_path):
    """`check` holds a plan's values to the project's own
    `validate-manifest.py`: on main its words for `id: "northwind\\n"` were
    `manifest-topic`'s, a topic "derived from id 'northwind\\n'"; they are the
    id's own now, under the code they had."""
    plan = planned(tmp_path)
    rewritten(plan, "\nid: northwind\n", '\nid: "northwind\\n"\n')
    result = adopt_check(plan)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [
        "FINDING plan-manifest-invalid: id is 'northwind\\n', which the "
        "project's own validate-manifest.py refuses: manifest-id: id is "
        f"'northwind\\n'; it must match {ID_PATTERN}."], result.stderr


# --- validate-family.py ------------------------------------------------------

@pytest.mark.parametrize("old, new, said", [
    pytest.param('id: "inkrouter"\n', 'id: "inkrouter\\n"\n',
                 f"FINDING family-id: id is 'inkrouter\\n'; it must match "
                 f"{ID_PATTERN}", id="id"),
    pytest.param('created_on: "2026-09-04"\n',
                 'created_on: "2026-09-04\\n"\n',
                 "FINDING family-created-on: created_on is '2026-09-04\\n', "
                 "expected an ISO date YYYY-MM-DD", id="created_on"),
    pytest.param("    repository: InkRouter/IRRS\n",
                 '    repository: "InkRouter/IRRS\\n"\n',
                 "FINDING member-repository: IRRS: repository is "
                 "'InkRouter/IRRS\\n', expected `<org>/<Name>`",
                 id="member-repository"),
])
def test_a_family_value_that_ends_in_a_line_break_is_a_finding(
        holder, old, new, said):
    """On main the id and the date were `family ok`, and the repository was
    `member-repository-name`, of a project "'IRRS\\n'"."""
    rewritten(holder / "family.yaml", old, new)
    result = validate(holder)
    assert result.returncode == 1, result.stdout + result.stderr
    assert findings(result.stderr) == [said], result.stderr


def test_a_member_repository_double_quoted_is_still_ok(holder):
    """The baseline of the member row."""
    rewritten(holder / "family.yaml", "    repository: InkRouter/IRRS\n",
              '    repository: "InkRouter/IRRS"\n')
    result = validate(holder)
    assert result.returncode == 0, result.stdout + result.stderr


def a_member_whose_id_is(family, tmp_path: Path, line: str) -> Path:
    """A directory of remotes holding `IRQS.git`: a bare copy of the spare
    member, one commit on, whose `project.yaml` writes its `id:` as `line`.
    The fixture's own remotes are not written to."""
    remotes = tmp_path / "remotes"
    remotes.mkdir()
    bare = cloned_just_pushed(family["remotes"] / f"{SPARE}.git",
                              remotes / f"{SPARE}.git", bare=True)
    work = cloned_just_pushed(bare, tmp_path / "edit")
    rewritten(work / "project.yaml", 'id: "irqs"\n', line)
    git("commit", "-qam", "the id, as a hand edit wrote it", cwd=work)
    git("push", "-q", "origin", "HEAD", cwd=work)
    return remotes


def test_add_refuses_a_member_whose_id_ends_in_a_line_break(
        family, holder, offline, tmp_path):
    """On main `add` mounted it and committed a row `id: "irqs\\n"`, exit 0,
    and the holder's gate, which compares that row with the same manifest,
    passed. It is `member-bad-id` now, before anything is mounted: one line
    on stdout and the holder as it was."""
    remotes = a_member_whose_id_is(family, tmp_path, 'id: "irqs\\n"\n')
    before = snapshot(holder)
    result = offline.add(holder, SPARE, remotes=remotes)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == f"checking {ORG}/{SPARE} before mounting it\n"
    assert result.stderr.splitlines()[0] == (
        f"REFUSED member-bad-id: {ORG}/{SPARE}: project.yaml `id:` is "
        f"'irqs\\n', which does not match {ID_PATTERN}"), result.stderr
    assert_unchanged(holder, before, SPARE)
    offline.assert_left_nothing()


# --- update-shape.py ---------------------------------------------------------

def check_with_source(project: Path, value: str, *extra: str):
    """`update-shape.py check` of `project`, its pin's `source_repository:`
    written double-quoted as `value`."""
    rewritten(project / "contracts" / "shape-pin.yaml",
              "source_repository: opensoft/openRepoShape\n",
              f'source_repository: "{value}"\n')
    return run_script(UPDATE, "check", "--root", str(project), *extra,
                      cwd=project)


def pin_of(project: Path) -> Path:
    return project.resolve() / "contracts" / "shape-pin.yaml"


#: What a pin's `source_repository:` that is no `owner/repo` is told.
WRITE_THE_PIN = (
    "Remediation: write `source_repository:` in the pin as the `owner/repo` "
    "its shape was copied from, `opensoft/openRepoShape` for this "
    "standard's, or pass `--upstream` a path to a clone of openRepoShape.")


@pytest.mark.parametrize("value, read", [
    pytest.param("opensoft/openRepoShape\\n", "'opensoft/openRepoShape\\n'",
                 id="line-feed"),
    pytest.param("opensoft/open Repo", "'opensoft/open Repo'", id="space"),
])
def test_a_pins_source_that_is_no_owner_repo_is_named_as_the_pins(
        project, value, read):
    """THE ISSUE'S ROW, and one the pattern refused on main too. On main the
    line feed passed `REPOSITORY_RE` and was `unsafe-value` of `--upstream`,
    and the space was `update-upstream-unresolvable` of `--upstream`, with
    no `--upstream` passed. Both are that code now, naming the pin."""
    result = check_with_source(project, value)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines() == [
        f"REFUSED update-upstream-unresolvable: {pin_of(project)}: "
        f"`source_repository:` is {read}, which is neither a path on this "
        "machine nor an `owner/repo` name", WRITE_THE_PIN], result.stderr


def test_a_pins_source_checked_value_refuses_is_named_as_the_pins(project):
    """`checked_value`'s refusal, of a value the pattern takes: on main it
    named `--upstream` too."""
    result = check_with_source(project, "-opensoft/openRepoShape")
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[0] == (
        f"REFUSED unsafe-value: {pin_of(project)}: `source_repository:` is "
        "'-opensoft/openRepoShape', which is not a value this tool will put "
        "on a `git` or `gh` command line"), result.stderr


def test_an_upstream_passed_with_a_line_feed_is_named_as_passed(project):
    """`--upstream` itself takes no line feed either: on main the pattern
    took it and `checked_value` refused it as `unsafe-value`; it is not an
    `owner/repo` name now, and is named as passed, whatever the pin says."""
    result = check_with_source(project, "-opensoft/openRepoShape",
                               "--upstream", "opensoft/openRepoShape" + LF)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.splitlines()[0] == (
        "REFUSED update-upstream-unresolvable: --upstream "
        "'opensoft/openRepoShape\\n' is neither a path on this machine nor "
        "an `owner/repo` name"), result.stderr
