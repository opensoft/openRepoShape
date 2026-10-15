# SPDX-License-Identifier: Apache-2.0
"""A scaffold refuses a value the new project's manifest cannot hold (#258, #261).

`scaffold-project.py` wrote `--id` and `--tracking-branch` into
`project.yaml` bare, so `--id null` and `--id true` scaffolded a project whose
first bootstrap failed `manifest-id`, and `--tracking-branch true`, `007` or
`null` pushed every repository on the branch as typed while bootstrap read the
manifest back as `True`, `7` or `main` and put each leg on a local branch the
remotes do not have, with no upstream. It exited 0 and said nothing (#258).

THE TEMPLATE NOW QUOTES THEM (#259). `project.yaml` writes `id`,
`elected_on`, `visibility` and `tracking_branch` between double quotes, so
the reader reads each of those values back as typed, and the misread question,
which is asked of the TEMPLATE, refuses none of them: `--id null` and
`--tracking-branch 007` scaffold, and the manifest holds `"null"` and `"007"`.
The question is still asked. A template line that writes such a value bare is
refused again, with no edit to the rule: the tests below show it on a copy of
this standard whose `project.yaml` writes those four lines bare, as it did
before #259. `--tracking-branch=~` now reads back as `~`, which git refuses
as a branch name; that is #283's, whose fix (PR #355) refuses it before
anything is created as `scaffold-bad-tracking-branch`.

It also accepted what the project's own `validate-manifest.py` refuses -- a
blank `--elected-by`, `--reference` or `--name`, `--elected-on 2026-W41-6` or
`20261011` (which `date.fromisoformat` reads from Python 3.11), `--org
test+org` -- and exited 0 over a project whose first bootstrap failed (#261).
A `--project` of 247 to 250 characters died in `Path.exists` with `OSError:
File name too long` under `--local-remote-dir`, and one of 251 or more in the
work directory.

The rule applied elsewhere in this repository (#179, #225, #251) is applied
here: REFUSE what the result cannot hold, BEFORE anything is created, under
`--dry-run` alike, naming the value and why. The questions are asked of the
programs the new project will use -- its YAML reader and the validator the
template ships -- not of a copy of either rule.

NO NETWORK AND NO GITHUB. Every run uses `--local-remote-dir`, which makes
bare repositories on disk, or `--dry-run`, which makes nothing; the two tests
that ask whether `gh` is reached put a fake one on PATH.
"""

from __future__ import annotations

import importlib.util
import os
import random
import re
import shutil
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import (ORG, REPO, SCAFFOLD, WINDOWS_SKIP, cloned_just_pushed,
                      git, run_script, scaffold_dry_run_on_github)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml, parse_yaml  # noqa: E402

MISREAD = "REFUSED scaffold-manifest-misread"
INVALID = "REFUSED scaffold-manifest-invalid"
TOO_LONG = "REFUSED scaffold-name-too-long"
BAD_DATE = "REFUSED election-date-malformed"
#: A free-text value no file can hold as one line of text is refused in
#: `_identity`, before the manifest is rendered (#282), so a blank that is
#: also a control character or a line break is refused there.
UNWRITABLE = "REFUSED scaffold-unwritable-value"

#: Where a test's scaffold writes, under `tmp_path`: the bare remotes, the
#: tool's work directory, and the temporary directory the tool would
#: otherwise make that work directory in.
REMOTES, WORK, SCRATCH = "remotes", "work", "tmp"

#: Everything but the flags under test. A flag given again after these wins,
#: because argparse takes the last: `--elected-by=<value>` below replaces the
#: one here.
IDENTITY = ["--org", ORG, "--project", "Atlas", "--elected-by", "Test Human",
            "--elected-on", "2026-09-02"]

#: `(flag, value, what the project's reader makes of it bare)`. Each is a
#: legal git branch name or a legal id that the reader takes for something
#: else where a line writes it bare, as `project.yaml` did before #259. The
#: template quotes both fields now, so the manifest holds each one as typed.
ONCE_MISREAD_VALUES = [
    pytest.param("--id", "null", "no value at all", id="id-null"),
    pytest.param("--id", "true", "the boolean true", id="id-true"),
    pytest.param("--id", "false", "the boolean false", id="id-false"),
    pytest.param("--id", "007", "the number 7", id="id-007"),
    pytest.param("--id", "2026", "the number 2026", id="id-2026"),
    pytest.param("--tracking-branch", "true", "the boolean true",
                 id="branch-true"),
    pytest.param("--tracking-branch", "True", "the boolean true",
                 id="branch-True"),
    pytest.param("--tracking-branch", "TRUE", "the boolean true",
                 id="branch-TRUE"),
    pytest.param("--tracking-branch", "false", "the boolean false",
                 id="branch-false"),
    pytest.param("--tracking-branch", "False", "the boolean false",
                 id="branch-False"),
    pytest.param("--tracking-branch", "null", "no value at all",
                 id="branch-null"),
    pytest.param("--tracking-branch", "Null", "no value at all",
                 id="branch-Null"),
    pytest.param("--tracking-branch", "NULL", "no value at all",
                 id="branch-NULL"),
    pytest.param("--tracking-branch", "007", "the number 7", id="branch-007"),
    pytest.param("--tracking-branch", "2026", "the number 2026",
                 id="branch-2026"),
    pytest.param("--tracking-branch", "1.5", "the number 1.5", id="branch-1.5"),
    pytest.param("--tracking-branch", "1.50", "the number 1.5",
                 id="branch-1.50"),
    pytest.param("--tracking-branch", "0", "the number 0", id="branch-0"),
]

#: `(flag, value)`: a value the misread rule refused while the template wrote
#: it bare (`~` is no value at all to the reader) that reads back as typed now,
#: and is still no name git gives a branch. Refusing it is not this file's
#: rule: it is #283's, which asks `git check-ref-format --branch` (PR #355,
#: on main as 6c2a3712) and refuses it as `scaffold-bad-tracking-branch`
#: before anything exists. Without that rule the scaffold passed it and died
#: at `git init -b ~`, which against GitHub is after `gh repo create` has made
#: all three repositories; this row was an expected failure until #355 landed.
NOT_A_BRANCH = [
    pytest.param("--tracking-branch", "~", id="branch-tilde"),
]

#: The placeholder each flag of `ONCE_MISREAD_VALUES` fills.
PLACEHOLDER_OF = {"--id": "PROJECT_ID", "--tracking-branch": "TRACKING_BRANCH"}

#: The `project.yaml` lines #259 quoted that this file's rules name, as
#: `(key, placeholder)`. `written_bare` writes them bare again, as the
#: template did before #259.
QUOTED_BY_259 = (("id", "PROJECT_ID"), ("elected_on", "ELECTED_ON"),
                 ("visibility", "VISIBILITY"),
                 ("tracking_branch", "TRACKING_BRANCH"))

#: Values the reader takes for text, so the manifest holds what was typed.
#: `yes` and `on` are YAML 1.1 booleans and this reader reads them as text;
#: `0x1F` and `1e3` are numbers elsewhere and text here. They are not
#: refused: the reader is asked, not a list of its words.
TEXT_BRANCHES = ["trunk", "release-1", "feature/x", "v1.2.3", "1.5.2", "yes",
                 "on", "0x1F", "1e3"]
TEXT_IDS = ["atlas-2", "v2", "null-island", "truelove", "yes", "on", "1e3"]

#: `(flag args, code, what the refusal names)`: values the new project's own
#: validator refuses, which the scaffold used to accept.
INVALID_VALUES = [
    pytest.param(["--elected-by= "], INVALID, ("--elected-by is ' '",
                                              "manifest-elected-by"),
                 id="elected-by-blank"),
    pytest.param(["--elected-by=\t"], UNWRITABLE, ("--elected-by is '\\t'",
                                                  "it holds a control character"),
                 id="elected-by-tab"),
    pytest.param(["--reference= "], INVALID, ("--reference is ' '",
                                             "manifest-reference"),
                 id="reference-blank"),
    pytest.param(["--name= "], INVALID, ("--name is ' '", "manifest-name"),
                 id="name-blank"),
    pytest.param(["--org=test+org"], INVALID, ("--org is 'test+org'",
                                              "manifest-leg-repository"),
                 id="org-plus"),
    pytest.param(["--org=test@org"], INVALID, ("--org is 'test@org'",
                                              "manifest-leg-repository"),
                 id="org-at"),
    pytest.param(["--org=test~org"], INVALID, ("--org is 'test~org'",
                                              "manifest-leg-repository"),
                 id="org-tilde"),
    pytest.param(["--elected-on=2026-W41-6"], BAD_DATE, ("2026-W41-6",),
                 id="elected-on-iso-week"),
    pytest.param(["--elected-on=20261011"], BAD_DATE, ("20261011",),
                 id="elected-on-basic-format"),
    pytest.param(["--elected-on=2026-9-2"], BAD_DATE, ("2026-9-2",),
                 id="elected-on-unpadded"),
]

#: Whitespace that `str.strip` takes off and a human cannot see: the
#: validator's `.strip()` decides, so the scaffold must agree on every one of
#: them rather than on a space and a tab.
INVISIBLE = ["\u00a0", "\u2003", "\u3000"]

#: And the ones that are also LINE BREAKS to `str.splitlines`: no file can
#: hold one as one line of text, so `_identity` refuses each as
#: `scaffold-unwritable-value` before the manifest is rendered (#282).
LINE_BREAKS = ["\x0b", "\x1c", "\u2028"]


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def scaffolder():
    return load("scaffold_for_manifest_values", SCAFFOLD)


@pytest.fixture(scope="module")
def adopter():
    return load("adopt_for_scaffold_manifest_values", REPO / "adopt-project.py")


def scaffold(tmp_path: Path, *args: str, work: bool = False,
             local: bool = True, tool: Path = SCAFFOLD):
    """One scaffold of `Atlas` into local bare remotes under `tmp_path`, by
    this standard's `scaffold-project.py` or, as `tool`, a copy's.

    Without `work` no `--work-dir` is given, so the tool would make its own in
    a temporary directory; `TMPDIR` (and Windows' `TEMP` and `TMP`) point at
    an empty `tmp_path/tmp` instead, which is how a test sees whether one was
    made.
    """
    scratch = tmp_path / SCRATCH
    scratch.mkdir(exist_ok=True)
    flags = [*IDENTITY, *args]
    if local:
        flags += ["--local-remote-dir", str(tmp_path / REMOTES)]
    if work:
        flags += ["--work-dir", str(tmp_path / WORK)]
    return run_script(tool, *flags, env={
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)})


def assert_nothing_was_created(tmp_path: Path) -> None:
    """No bare remote, no work directory of the tool's own and none of ours."""
    found = sorted(p.name for p in tmp_path.iterdir())
    assert found == [SCRATCH], (
        f"a scaffold that makes nothing created something: {found}")
    assert list((tmp_path / SCRATCH).iterdir()) == [], (
        "a scaffold that makes nothing made a temporary work directory")


def assert_refused(result, code: str) -> None:
    assert result.returncode == 2, result.stderr + result.stdout
    assert code in result.stderr, result.stderr
    assert result.stdout == "", "a plan was printed for a refused scaffold"


def manifest_in(tmp_path: Path, project: str = "Atlas") -> dict:
    """The `project.yaml` a scaffold under `tmp_path` pushed, as git holds it
    in the bare remote, read by the project's own reader."""
    bare = tmp_path / REMOTES / f"{project}.git"
    return parse_yaml(git("show", "HEAD:project.yaml", cwd=bare).stdout)


def heads(bare: Path) -> list[str]:
    """The branches a bare remote holds."""
    return git("for-each-ref", "--format=%(refname:short)", "refs/heads",
               cwd=bare).stdout.split()


def written_bare(text: str) -> str:
    """`project.yaml`'s text with the lines #259 quoted (`QUOTED_BY_259`)
    written bare again, as the template wrote them before it."""
    for key, placeholder in QUOTED_BY_259:
        quoted = f'\n{key}: "{{{{{placeholder}}}}}"\n'
        assert text.count(quoted) == 1, f"{quoted!r} is not one line of it"
        text = text.replace(quoted, f"\n{key}: {{{{{placeholder}}}}}\n")
    return text


@pytest.fixture(scope="module")
def bare_standard(tmp_path_factory):
    """This standard as its own checkout, with `project.yaml` writing the
    four lines #259 quoted bare again. The misread rule is asked of the
    template, so there it refuses what it refused before #259, and its tools
    run from there to show it."""
    return a_copy_of_the_standard(tmp_path_factory.mktemp("bare"),
                                  written_bare, "project.yaml")


def bare_template(standard: Path) -> Path:
    """The assembly-root template of a copy of the standard."""
    return standard / "templates" / "assembly-root"


# --- #258: a value the project's reader turned into something else --------

@pytest.mark.parametrize("flag, value, reading", ONCE_MISREAD_VALUES)
def test_a_value_the_reader_once_misread_is_held_as_typed(
        tmp_path, bare_standard, flag, value, reading):
    """The misread rule refused each of these while `project.yaml` wrote it
    bare, and it still refuses each where a template line does (asked here of
    the copy of the standard that writes them bare). The template quotes them
    now (#259), so this standard scaffolds each one, the manifest it pushes
    holds the value as the text that was typed, and a branch is the one every
    repository is created on."""
    placeholder = PLACEHOLDER_OF[flag]
    (sentence,) = shape_materialize.manifest_misreads(
        {placeholder: value}, {placeholder: flag},
        bare_template(bare_standard))
    assert f"{flag} is {value!r}" in sentence
    assert f"reads it back as {reading} and not as that text" in sentence
    assert shape_materialize.manifest_misreads(
        {placeholder: value}, {placeholder: flag}) == []
    # `=` form, so a value that begins with `~` or `-` reaches the tool as a
    # value and argparse does not take it for another option.
    result = scaffold(tmp_path, f"{flag}={value}")
    assert result.returncode == 0, result.stderr + result.stdout
    manifest = manifest_in(tmp_path)
    if flag == "--id":
        assert manifest["id"] == value
        assert manifest["topic"] == f"xf-project-{value}"
    else:
        assert manifest["tracking_branch"] == value
        for name in ("Atlas", "Atlas-spec", "Atlas-code"):
            assert heads(tmp_path / REMOTES / f"{name}.git") == [value], name


@pytest.mark.parametrize("flag, value", NOT_A_BRANCH)
def test_a_value_git_refuses_as_a_branch_is_refused_before_anything_is_made(
        tmp_path, flag, value):
    """No longer a misread, and still not a branch: it must be refused before
    anything exists, by the rule that asks git (#283), and not die at the
    first `git init -b` as `a git or gh command failed`."""
    result = scaffold(tmp_path, f"{flag}={value}")
    assert_refused(result, "REFUSED scaffold-bad-tracking-branch: ")
    assert "a git or gh command failed" not in result.stderr
    assert flag in result.stderr
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value", [("--id", "null"),
                                         ("--tracking-branch", "007")])
def test_a_dry_run_accepts_a_value_once_misread_as_the_real_run_does(
        tmp_path, flag, value):
    """`--dry-run` is a rehearsal, and it answers as the real run does. It
    refused these as the real run did while the template wrote them bare; the
    template quotes them now (#259), so it prints the plan the real run
    carries out, and makes nothing."""
    result = scaffold(tmp_path, "--dry-run", f"{flag}={value}")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "--dry-run: nothing was created." in result.stdout
    if flag == "--id":
        assert f"Atlas ({value})" in result.stdout
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value", [
    ("--tracking-branch", "2026"), ("--tracking-branch", "1.5"),
    ("--tracking-branch", "007"), ("--id", "2026"), ("--id", "null"),
])
def test_the_remediation_says_what_is_true_of_every_value_it_refuses(
        tmp_path, bare_standard, flag, value):
    """`--tracking-branch 2026` and `1.5` are the values this refusal newly
    took from people: they scaffolded, bootstrapped and got their upstream,
    because every reader of `tracking_branch` does `str()` and `str(2026)` is
    `2026` again. The remediation once said the first bootstrap would fail or
    put the legs on a branch the remotes lack, which is false of exactly
    those, so it now says only what holds of all of them -- the project's
    reader reads back something other than what was typed -- names the
    failures that do hold, says plainly that a number which survives `str()`
    is a number all the same, and gives the way forward: a value that is text
    to the reader.

    The template quotes `id:` and `tracking_branch:` now (#259), so this
    standard refuses none of them and the remediation is not said; it is
    asked of the copy whose template writes them bare, where it is."""
    accepted = scaffold(tmp_path, "--dry-run", f"{flag}={value}")
    assert accepted.returncode == 0, accepted.stderr + accepted.stdout
    assert "Remediation" not in accepted.stderr
    result = scaffold(tmp_path, "--dry-run", f"{flag}={value}",
                      tool=bare_standard / "scaffold-project.py")
    assert_refused(result, MISREAD)
    assert_nothing_was_created(tmp_path)
    said = result.stderr
    assert "what it reads back is not what was typed" in said
    assert ("an id that is not text fails the project's own "
            "validate-manifest.py") in said
    assert ("`2026` or `1.5` as a branch happens to work today, because the "
            "tools that read it turn the number back into text, but it is "
            "still a number to the project's reader and not a name") in said
    assert ("A value the reader takes for text (`atlas`, `release-2026`, "
            "`v2`) passes.") in said
    assert "first bootstrap would fail" not in said
    assert "branch the remotes do not have" not in said


@pytest.mark.parametrize("typed, read_back", [
    ("2026", "2026"), ("1.5", "1.5"),
    ("007", "7"), ("1.50", "1.5"),
])
def test_the_remediations_claim_about_str_is_what_the_reader_does(
        typed, read_back):
    """The remediation says a branch that is a number survives `str()` only
    when `str()` of the number is the text typed. That is a claim about the
    project's own reader, so it is asked of the reader: `2026` and `1.5` come
    back as typed, `007` and `1.50` as another branch."""
    value = parse_yaml(f"tracking_branch: {typed}\n")["tracking_branch"]
    assert not isinstance(value, str), "the reader takes it for text"
    assert str(value) == read_back


@pytest.mark.parametrize("project, derived, reading", [
    ("True", "true", "the boolean true"),
    ("Null", "null", "no value at all"),
])
def test_an_id_derived_from_the_project_name_is_held_as_typed_too(
        tmp_path, bare_standard, project, derived, reading):
    """With no `--id` the id is the project name lowercased, so `--project
    Null` is the id `null`. Where a template line writes `id:` bare it is
    refused, and the sentence says where the id came from, so it does not
    point at a flag nobody typed (asked of the copy that writes it bare). The
    template quotes it now (#259), so this standard scaffolds the project and
    the manifest holds the id as that text."""
    refused = scaffold(tmp_path, "--project", project,
                       tool=bare_standard / "scaffold-project.py")
    assert_refused(refused, MISREAD)
    assert (f"--id (not given, so --project lowercased) is {derived!r}"
            in refused.stderr)
    assert reading in refused.stderr
    assert_nothing_was_created(tmp_path)
    result = scaffold(tmp_path, "--project", project)
    assert result.returncode == 0, result.stderr + result.stdout
    manifest = manifest_in(tmp_path, project)
    assert manifest["id"] == derived
    assert manifest["topic"] == f"xf-project-{derived}"


def test_an_explicit_id_is_the_way_round_for_such_a_project_name(tmp_path):
    result = scaffold(tmp_path, "--project", "Null", "--id", "null-project",
                      "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "project      Null (null-project)" in result.stdout


@pytest.mark.parametrize("branch", TEXT_BRANCHES)
def test_a_branch_the_reader_takes_for_text_is_still_accepted(tmp_path,
                                                              branch):
    result = scaffold(tmp_path, "--dry-run", f"--tracking-branch={branch}")
    assert result.returncode == 0, result.stderr + result.stdout


@pytest.mark.parametrize("project_id", TEXT_IDS)
def test_an_id_the_reader_takes_for_text_is_still_accepted(tmp_path,
                                                           project_id):
    result = scaffold(tmp_path, "--dry-run", f"--id={project_id}")
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"({project_id})" in result.stdout


@pytest.mark.parametrize("branch, project_id", [
    ("release-1", "null-island"),
    ("v1.2.3", "atlas-2"),
])
def test_what_is_typed_is_what_the_project_holds_and_bootstrap_agrees(
        tmp_path, branch, project_id):
    """The whole round trip, with the project's own tools: the manifest holds
    the branch and the id as typed, its validator passes, and bootstrap puts
    each leg on that branch with an upstream. On main `--tracking-branch
    true` was the opposite of every one of these."""
    result = scaffold(tmp_path, f"--tracking-branch={branch}",
                      f"--id={project_id}", work=True)
    assert result.returncode == 0, result.stderr + result.stdout
    clone = cloned_just_pushed(tmp_path / REMOTES / "Atlas.git",
                               tmp_path / "Atlas")
    manifest = load_yaml(clone / "project.yaml")
    assert manifest["id"] == project_id
    assert manifest["tracking_branch"] == branch
    assert manifest["topic"] == f"xf-project-{project_id}"
    booted = run_script(clone / "scripts" / "bootstrap.py", cwd=clone)
    assert booted.returncode == 0, booted.stderr + booted.stdout
    for leg in ("spec", "code"):
        on = git("rev-parse", "--abbrev-ref", "HEAD", cwd=clone / leg)
        assert on.stdout.strip() == branch
        upstream = git("rev-parse", "--abbrev-ref", "@{u}", cwd=clone / leg,
                       check=False)
        assert upstream.stdout.strip() == f"origin/{branch}", upstream.stderr
    for name in ("Atlas", "Atlas-spec", "Atlas-code"):
        heads = git("for-each-ref", "--format=%(refname:short)", "refs/heads",
                    cwd=tmp_path / REMOTES / f"{name}.git").stdout.split()
        assert heads == [branch]


# --- #261: a value the project's own validator refuses --------------------

@pytest.mark.parametrize("args, code, named", INVALID_VALUES)
def test_a_value_the_validator_refuses_is_refused_before_anything_is_made(
        tmp_path, args, code, named):
    result = scaffold(tmp_path, *args)
    assert_refused(result, code)
    for fragment in named:
        assert fragment in result.stderr
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("args, code, named", INVALID_VALUES[:3])
def test_a_dry_run_refuses_what_the_validator_refuses(tmp_path, args, code,
                                                      named):
    result = scaffold(tmp_path, "--dry-run", *args)
    assert_refused(result, code)
    assert_nothing_was_created(tmp_path)


def test_the_refusal_says_it_in_the_validators_own_words(tmp_path):
    """Not a sentence that happens to agree: the words after the value are the
    validator's own finding, read from the validator the template ships."""
    validator = shape_materialize.manifest_validator()
    expected = {
        "elected_by": validator._elected_by_finding({"elected_by": " "}),
        "reference": validator._reference_finding({"reference": " "}),
        "name": validator._name_finding({"name": " "}),
    }
    for key, flag in (("elected_by", "--elected-by"),
                      ("reference", "--reference"), ("name", "--name")):
        (finding,) = expected[key]
        detail = finding.split(": ", 1)[1]
        result = scaffold(tmp_path, "--dry-run", f"{flag}= ")
        assert detail in result.stderr, (detail, result.stderr)


@pytest.mark.parametrize("blank", INVISIBLE)
def test_whitespace_a_person_cannot_see_is_judged_as_the_validator_judges_it(
        tmp_path, blank):
    """`"\\u3000".strip()` is empty, so the validator refuses an `elected_by`
    of it. The scaffold agrees on each, because the validator is asked and no
    second definition of blank is kept."""
    result = scaffold(tmp_path, "--dry-run", f"--elected-by={blank}")
    assert_refused(result, INVALID)
    assert "manifest-elected-by" in result.stderr


@pytest.mark.parametrize("blank", LINE_BREAKS)
def test_a_blank_that_is_also_a_line_break_is_refused_too(tmp_path, blank):
    """It cannot be written into the manifest as it stands: the reader splits
    the file at it. Refused either way, before anything is made, and never
    scaffolded into a project whose every reader refuses `project.yaml`."""
    result = scaffold(tmp_path, "--dry-run", f"--elected-by={blank}")
    assert result.returncode == 2, result.stderr + result.stdout
    assert f"{UNWRITABLE}: --elected-by is " in result.stderr
    assert "it holds a line break" in result.stderr
    assert result.stdout == ""
    assert_nothing_was_created(tmp_path)


def test_an_organisation_the_validator_accepts_is_still_accepted(tmp_path):
    """`_` and `.` are in the validator's `QUALIFIED_RE`: the scaffold does
    not refuse more than the project does."""
    result = scaffold(tmp_path, "--dry-run", "--org=my_org.x")
    assert result.returncode == 0, result.stderr + result.stdout


def test_an_elector_and_a_reference_with_text_in_them_still_scaffold(tmp_path):
    result = scaffold(tmp_path, "--dry-run", "--elected-by=Robert Smith",
                      "--reference=docs/project-repo-schema.md")
    assert result.returncode == 0, result.stderr + result.stdout


# --- the election date: the validator's form, on every Python -------------

def test_the_election_date_is_read_in_the_validators_form_only():
    """`date.fromisoformat` reads an ISO week date and the basic format from
    Python 3.11 and the validator refuses both; a date is read only when the
    validator's own `DATE_RE` admits it AND it is a real day."""
    for text in ("2026-W41-6", "2026W416", "2026-W41", "20261011",
                 "2026-9-2", "2026-13-45", "2026-09-02\n", " 2026-09-02",
                 "\u0662\u0660\u0662\u0666-\u0660\u0669-\u0660\u0662", ""):
        with pytest.raises(shape_materialize.Refusal) as caught:
            shape_materialize.election_date(text)
        assert caught.value.code == "election-date-malformed", repr(text)
    assert str(shape_materialize.election_date("2026-09-02")) == "2026-09-02"


def test_the_election_date_never_accepts_what_the_validator_refuses():
    """Seeded: any string over the alphabet of dates and their ISO variants.
    Whatever `election_date` reads, `DATE_RE` admits."""
    date_re = shape_materialize.manifest_validator().DATE_RE
    rng = random.Random(41)
    alphabet = "0123456789-WT:/ ."
    for _ in range(4000):
        text = "".join(rng.choice(alphabet)
                       for _ in range(rng.randint(6, 11)))
        try:
            shape_materialize.election_date(text)
        except shape_materialize.Refusal:
            continue
        assert date_re.match(text), repr(text)
    # Dates are rare in noise, so the ones that must be read are planted.
    for text in ("2026-09-02", "2026-01-31", "1999-12-31", "2024-02-29"):
        assert date_re.match(text)
        shape_materialize.election_date(text)


def test_the_election_date_asks_the_validator_not_a_copy_of_its_rule(
        monkeypatch):
    """Make the validator's rule stricter and the answer follows: nothing in
    `election_date` holds a second `YYYY-MM-DD` pattern to keep in step."""
    validator = shape_materialize.manifest_validator()
    monkeypatch.setattr(validator, "DATE_RE",
                        re.compile(r"^2027-\d\d-\d\d$"))
    with pytest.raises(shape_materialize.Refusal):
        shape_materialize.election_date("2026-09-02")
    assert str(shape_materialize.election_date("2027-09-02")) == "2027-09-02"


# --- a repository's name is a directory's ---------------------------------

@pytest.mark.parametrize("length", [247, 248, 250])
def test_a_project_whose_bare_repository_name_is_too_long_is_refused(
        tmp_path, length):
    """`<project>-spec.git` is `length + 9` bytes: 256 and more fails on every
    disk. On main this was `OSError: File name too long` and a traceback."""
    result = scaffold(tmp_path, "--project", "N" * length)
    assert_refused(result, TOO_LONG)
    assert "Traceback" not in result.stderr
    assert ".git is" in result.stderr
    assert "--local-remote-dir" in result.stderr
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("length", [251, 255])
def test_a_project_whose_work_directory_name_is_too_long_is_refused_too(
        tmp_path, length):
    """`<project>-spec` alone is over 255 bytes from 251 characters, so the
    work directory cannot hold it, with or without local remotes."""
    for local in (True, False):
        result = scaffold(tmp_path, "--project", "N" * length, local=local,
                          work=True)
        assert_refused(result, TOO_LONG)
        assert "Traceback" not in result.stderr
        assert "work directory" in result.stderr
        assert not (tmp_path / WORK).exists()


def test_the_longest_name_a_disk_keeps_is_still_accepted(tmp_path, monkeypatch,
                                                         capsys):
    """246 characters is `<project>-spec.git` at exactly 255 bytes. A dry run
    only: a real tree this deep is a Windows path the OS will not open.
    Without `--local-remote-dir` the dry run asks GitHub whether the three
    exist (#537), so that half runs in process and asks a stand-in."""
    result = scaffold(tmp_path, "--project", "N" * 246, "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    code, _out, err, asked = scaffold_dry_run_on_github(
        monkeypatch, capsys, *IDENTITY, "--project", "N" * 250)
    assert code == 0, err
    assert asked == [f"{ORG}/{'N' * 250}{tail}" for tail in
                     ("", "-spec", "-code")]


def test_the_name_rule_is_the_same_bytes_the_tools_make():
    refuse = shape_materialize.refuse_unstorable_names
    assert refuse("r", ["a" * 255], []) is None
    assert refuse("r", ["a" * 251], ["a" * 251]) is None
    with pytest.raises(shape_materialize.Refusal):
        refuse("r", ["a" * 256], [])
    with pytest.raises(shape_materialize.Refusal) as caught:
        refuse("r", ["a" * 252], ["a" * 252])
    assert caught.value.code == "r"
    assert "256 bytes" in caught.value.detail


def test_the_names_a_refusal_shows_are_told_apart_by_their_tails():
    """The three repositories are `<Project>`, `<Project>-spec` and
    `<Project>-code`. Cut at the front, `-spec` and `-code` were lost and two
    of the sentences read the same; each name is shown at both ends."""
    name = "N" * 251
    with pytest.raises(shape_materialize.Refusal) as caught:
        shape_materialize.refuse_unstorable_names(
            "r", [name, f"{name}-spec", f"{name}-code"])
    sentences = caught.value.detail.rstrip(".").split("; ")
    assert len(sentences) == 2, sentences
    assert len(set(sentences)) == 2, sentences
    assert sentences[0].startswith("NNNNNNNNNNNN...NNNNNNN-spec is 256 bytes")
    assert sentences[1].startswith("NNNNNNNNNNNN...NNNNNNN-code is 256 bytes")
    # the bare repository's directory adds `.git`, after the tail
    with pytest.raises(shape_materialize.Refusal) as caught:
        shape_materialize.refuse_unstorable_names("r", [], [f"{name}-code"])
    assert caught.value.detail.startswith(
        "NNNNNNNNNNNN...NNNNNNN-code.git is 260 bytes")


# --- never GitHub ----------------------------------------------------------

def scaffold_against_a_fake_gh(tmp_path: Path, flag: str):
    """A scaffold with no `--local-remote-dir`, so it goes to the forge, with
    a fake `gh` first on PATH that logs each call and answers no. Returns the
    run and the log's path, which exists only if `gh` was asked."""
    bin_dir, log = tmp_path / "bin", tmp_path / "gh.log"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_text(textwrap.dedent("""\
        #!/bin/sh
        echo "$@" >> "$FAKE_GH_LOG"
        echo "fake gh: no network here" >&2
        exit 1
        """), encoding="utf-8")
    shim.chmod(shim.stat().st_mode | stat.S_IXUSR)
    result = run_script(
        SCAFFOLD, *IDENTITY, flag, "--work-dir", str(tmp_path / WORK),
        env={"PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
             "FAKE_GH_LOG": str(log)})
    return result, log


@WINDOWS_SKIP  # the `gh` below is a `#!` script, which Windows does not run
@pytest.mark.parametrize("flag", ["--elected-by= ", "--org=test+org"])
def test_a_refused_value_never_reaches_gh(tmp_path, flag):
    """Local remotes are the test path; the real one calls `gh repo create`.
    Each refusal comes before the first `gh` call, so no repository is made
    on the forge for a project that was never going to scaffold."""
    result, log = scaffold_against_a_fake_gh(tmp_path, flag)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED" in result.stderr
    assert not log.exists(), f"gh was asked: {log.read_text()}"
    assert not (tmp_path / WORK).exists()


@WINDOWS_SKIP  # the `gh` below is a `#!` script, which Windows does not run
@pytest.mark.parametrize("flag", ["--id=null", "--tracking-branch=true"])
def test_a_value_once_misread_reaches_gh_as_an_accepted_one_does(tmp_path,
                                                                 flag):
    """These two were refused before the first `gh` call while the template
    wrote them bare. It quotes them now (#259), so they pass every question
    the scaffold asks, and the run goes on to the forge as an accepted value's
    does: the fake `gh` is asked to create the first leg and says no. That is
    also the fake answering where `test_a_refused_value_never_reaches_gh`
    would have seen a call."""
    result, log = scaffold_against_a_fake_gh(tmp_path, flag)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "manifest-misread" not in result.stderr
    assert log.exists(), "gh was never asked"
    assert f"repo create {ORG}/Atlas-spec " in log.read_text()
    assert f"gh repo create {ORG}/Atlas-spec " in result.stderr


# --- one definition, two readers ------------------------------------------

def test_both_tools_ask_the_one_definition(scaffolder, adopter):
    for name in ("refuse_manifest_values", "refuse_unstorable_names"):
        defined = getattr(shape_materialize, name)
        assert defined.__module__ == "shape_materialize"
        assert getattr(scaffolder, name) is defined
    assert adopter.refuse_unstorable_names is (
        shape_materialize.refuse_unstorable_names)
    assert adopter.manifest_value_problems is (
        shape_materialize.manifest_value_problems)


def test_the_validator_asked_is_the_one_the_template_ships():
    module = shape_materialize.manifest_validator()
    assert Path(module.__file__).resolve() == (
        REPO / "templates" / "assembly-root" / "scripts"
        / "validate-manifest.py")
    assert shape_materialize.manifest_validator() is module, (
        "it is loaded once")


def test_loading_the_validator_leaves_sys_path_as_it_found_it(tmp_path):
    """The validator puts its own directory first on `sys.path` for the
    sibling modules it imports (`bootstrap`, `validate-pins` live there too),
    and that must not outlive the load. A copy of the template is a path not
    loaded yet, so this loads for real."""
    copy = tmp_path / "assembly-root"
    shutil.copytree(REPO / "templates" / "assembly-root", copy,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    before = list(sys.path)
    module = shape_materialize.manifest_validator(copy)
    assert Path(module.__file__).resolve().parent.parent == (
        copy.resolve()), "the copy was not what was loaded"
    assert sys.path == before
    assert not list(copy.rglob("__pycache__")), (
        "loading the validator wrote bytecode into the template tree")


def test_every_name_a_refusal_uses_is_a_value_the_tools_hold(scaffolder,
                                                              adopter):
    """The placeholders each tool names, and the ones the validator's findings
    are mapped to, are all keys of the substitution table: a key that no
    longer existed would be a value asked about nothing."""
    template = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (REPO / "templates" / "assembly-root").rglob("*")
        if path.is_file() and path.suffix in (".yaml", ".md"))
    known = set(re.findall(r"\{\{([A-Z_]+)\}\}", template))
    known.add("ORG")  # a key of both tools' tables, in no template
    for table in (scaffolder.MANIFEST_FLAGS, adopter.MANIFEST_FLAGS,
                  adopter.MANIFEST_PLAN_KEYS):
        assert set(table) <= known, set(table) - known
    assert set(shape_materialize.FINDING_PLACEHOLDER.values()) <= known
    assert set(adopter.MANIFEST_FLAGS) == set(adopter.MANIFEST_PLAN_KEYS)


def test_the_template_quotes_them_so_the_misread_rule_refuses_nothing_there(
        scaffolder, bare_standard):
    """#259 quoted `id:` and `tracking_branch:` in the template, and
    `elected_on:` and `visibility:` with them. The question is asked of the
    TEMPLATE, so since it did, no value of any field the scaffold names is
    read back as anything but itself, and the rule refuses none, with no edit
    to it. Written bare again, the same lines are refused again."""
    text = (REPO / "templates" / "assembly-root" / "project.yaml").read_text(
        encoding="utf-8")
    for key, placeholder in QUOTED_BY_259:
        assert f'\n{key}: "{{{{{placeholder}}}}}"\n' in text, key
    once_misread = {param.values[1] for param in ONCE_MISREAD_VALUES}
    # and `~`, a basic-format date, and line breaks `render` spells escaped
    also = {"~", "20261011", "a\x0bb", "a\u2028b"}
    for value in sorted(once_misread | also):
        values = dict.fromkeys(scaffolder.MANIFEST_FLAGS, value)
        assert shape_materialize.manifest_misreads(
            values, scaffolder.MANIFEST_FLAGS) == [], repr(value)
    values = {"PROJECT_ID": "null", "TRACKING_BRANCH": "007"}
    what = {"PROJECT_ID": "--id", "TRACKING_BRANCH": "--tracking-branch"}
    assert shape_materialize.manifest_misreads(values, what) == []
    assert len(shape_materialize.manifest_misreads(
        values, what, bare_template(bare_standard))) == 2
    # and what the quoted line holds is the text, through the project's reader
    assert parse_yaml('tracking_branch: "007"\n') == {"tracking_branch": "007"}


# --- one alphabet for a placeholder ----------------------------------------

def test_a_placeholder_is_what_render_calls_one(tmp_path, monkeypatch):
    """The question counts the placeholders of a template line with the
    pattern `render` finds them by, not with a second spelling of its
    alphabet. #260 widens `PLACEHOLDER_RE` to admit digits
    (`{{SPEC_TREE_SHA256}}`); a line holding one asked placeholder and one
    with a digit must then count as two and not be asked, as a line that is
    asked is rendered with a one-key table and refused as
    `template-unsubstituted`. The template quotes `id:` (#259), which the
    reader then reads back, so the copy writes it bare again to have a line
    whose value is refused."""
    monkeypatch.setattr(shape_materialize, "PLACEHOLDER_RE",
                        re.compile(r"\{\{[A-Z0-9_]+\}\}"))
    assert shape_materialize._placeholders_of(
        "x: {{PROJECT_ID}}-{{SPEC_TREE_SHA256}}") == [
            "PROJECT_ID", "SPEC_TREE_SHA256"]
    copy = tmp_path / "assembly-root"
    shutil.copytree(REPO / "templates" / "assembly-root", copy,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = copy / "project.yaml"
    manifest.write_text(
        written_bare(manifest.read_text(encoding="utf-8"))
        + "extra: {{PROJECT_ID}}-{{SPEC_TREE_SHA256}}\n", encoding="utf-8")
    values = {"PROJECT_ID": "null", "SPEC_TREE_SHA256": "0" * 64}
    what = {"PROJECT_ID": "--id"}
    # only the line that holds the one placeholder is asked, and nothing raises
    sentences = shape_materialize.manifest_misreads(values, what, copy)
    assert len(sentences) == 1
    assert "id: null" in sentences[0]
    assert "extra" not in sentences[0]


# --- what is shown of a line ----------------------------------------------

def test_a_line_a_terminal_would_show_as_something_else_is_quoted_by_python():
    """A character a terminal shows as something else (a vertical tab, a
    line separator) is spelled the way Python does, so that one sentence stays
    one line and the character can be seen; a printable line is in
    backticks."""
    shown = shape_materialize._line_shown
    assert shown("id: atlas") == "`id: atlas`"
    assert shown("tracking_branch: a\x0bb") == "'tracking_branch: a\\x0bb'"
    assert shown("id: a\u2028b") == "'id: a\\u2028b'"


@pytest.mark.parametrize("char", ["\x0b", "\x1c", "\u2028"])
def test_a_misread_sentence_holding_a_line_break_is_one_printable_line(
        bare_standard, char):
    """Where a template line writes the value bare, the manifest is split at
    the break, so the reader refuses it; the sentence says so without printing
    the break itself. The template quotes `tracking_branch:` now (#259), and
    `render` spells the break as an escape between the quotes, so the reader
    reads it back and the rule refuses nothing; the sentence is asked of the
    copy that writes the line bare."""
    what = {"TRACKING_BRANCH": "--tracking-branch"}
    assert shape_materialize.manifest_misreads(
        {"TRACKING_BRANCH": f"a{char}b"}, what) == []
    bare = bare_template(bare_standard)
    (sentence,) = shape_materialize.manifest_misreads(
        {"TRACKING_BRANCH": f"a{char}b"}, what, bare)
    assert len(sentence.splitlines()) == 1
    assert sentence.isprintable()
    assert "into project.yaml as 'tracking_branch: a\\" in sentence
    # a printable misread is quoted in backticks, as before
    (plain,) = shape_materialize.manifest_misreads(
        {"TRACKING_BRANCH": "007"}, what, bare)
    assert "into project.yaml as `tracking_branch: 007`" in plain


# --- the placeholders a misread rule would refuse ---------------------------

def test_the_misread_placeholders_are_the_ones_the_misread_rule_refuses(
        bare_standard):
    """What a caller that leaves misreads to a rule of its own asks of the
    validator is whatever `manifest_misreads` would refuse, as an answer of
    the project's reader and not a list of values: none on this standard's
    template, which quotes all three (#259), and the three where a template
    writes them bare."""
    what = {"PROJECT_ID": "--id", "TRACKING_BRANCH": "--tracking-branch",
            "ELECTED_BY": "--elected-by", "ELECTED_ON": "--elected-on",
            "VISIBILITY": "--visibility", "ORG": "--org"}
    values = {"PROJECT_ID": "007", "TRACKING_BRANCH": "2026",
              "ELECTED_BY": " ", "ELECTED_ON": "2026-09-02",
              "VISIBILITY": "true", "ORG": "acme"}
    assert shape_materialize.misread_placeholders(values, what) == ()
    assert shape_materialize.manifest_misreads(values, what) == []
    bare = bare_template(bare_standard)
    asked = shape_materialize.misread_placeholders(values, what, bare)
    assert sorted(asked) == ["PROJECT_ID", "TRACKING_BRANCH", "VISIBILITY"]
    assert len(shape_materialize.manifest_misreads(values, what, bare)) == (
        len(asked))
    assert shape_materialize.misread_placeholders(
        {"PROJECT_ID": "atlas"}, what, bare) == ()


# --- a validator that cannot be asked -------------------------------------

#: `(how the template's validator is made over, what the refusal says)`: the
#: function is given the real file's text and returns the new text, or None to
#: remove the file.
BROKEN_VALIDATORS = [
    pytest.param(lambda real: None, "could not be loaded: FileNotFoundError",
                 id="missing"),
    pytest.param(lambda real: "def (:\n",
                 "could not be loaded: SyntaxError", id="syntax"),
    pytest.param(lambda real: "raise RuntimeError('boom at import')\n",
                 "could not be loaded: RuntimeError: boom at import",
                 id="raises-at-import"),
    pytest.param(lambda real: "ANSWER = 42\n",
                 "could not be used: it has no `DATE_RE`",
                 id="lacks-what-is-asked"),
    pytest.param(lambda real: real + "\n\ndef _findings(manifest, policy, "
                                    "other):\n    raise KeyError('boom')\n",
                 "raised when it was asked: KeyError: 'boom'",
                 id="raises-when-asked"),
]


def a_copy_of_the_standard(base: Path, remake,
                           rel: str = "scripts/validate-manifest.py") -> Path:
    """The standard, as its own git checkout (the tools name their revision),
    with its template's `validate-manifest.py`, or the template file `rel`,
    made over by `remake`, which is given the real text and returns the text
    to put there, or None to remove the file."""
    copy = base / "standard"
    shutil.copytree(REPO, copy, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "tests", "docs", "handoffs"))
    git("init", "-q", cwd=copy)
    git("add", "-A", cwd=copy)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--no-gpg-sign", "-m", "a copy of the standard", cwd=copy)
    path = copy / "templates" / "assembly-root" / rel
    remade = remake(path.read_text(encoding="utf-8"))
    if remade is None:
        path.unlink()
    else:
        with path.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(remade)
    return copy


@pytest.mark.parametrize("remake, said", BROKEN_VALIDATORS)
def test_a_validator_that_cannot_be_asked_is_a_named_refusal_not_a_traceback(
        tmp_path, remake, said):
    """The validator the template ships is loaded and asked, so a copy of the
    standard that lost it, or holds one that raises, would have been a
    traceback and exit 1 from deep inside the tool. Nothing is created
    either way; it is now a refusal that names the file and says the defect is
    the copy's, not the values'."""
    copy = a_copy_of_the_standard(tmp_path, remake)
    run = tmp_path / "run"
    (run / SCRATCH).mkdir(parents=True)
    result = run_script(
        copy / "scaffold-project.py", *IDENTITY,
        "--local-remote-dir", str(run / REMOTES),
        "--work-dir", str(run / WORK),
        env={"TMPDIR": str(run / SCRATCH), "TMP": str(run / SCRATCH),
             "TEMP": str(run / SCRATCH)})
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED manifest-validator-unusable" in result.stderr
    assert "validate-manifest.py" in result.stderr
    assert said in result.stderr, result.stderr
    assert "a defect in the copy of this standard you ran" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stdout == "", "a plan was printed for a refused scaffold"
    assert sorted(p.name for p in run.iterdir()) == [SCRATCH]
    assert list((run / SCRATCH).iterdir()) == []
    assert not list((copy / "templates").rglob("__pycache__")), (
        "bytecode was written into the template tree")


def test_a_validator_that_failed_to_load_is_not_remembered(tmp_path):
    """A failed load is not cached: the file put right, the next ask loads
    it."""
    copy = tmp_path / "assembly-root"
    shutil.copytree(REPO / "templates" / "assembly-root", copy,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    validator = copy / "scripts" / "validate-manifest.py"
    good = validator.read_bytes()
    validator.write_text("def (:\n", encoding="utf-8")
    with pytest.raises(shape_materialize.Refusal) as caught:
        shape_materialize.manifest_validator(copy)
    assert caught.value.code == "manifest-validator-unusable"
    validator.write_bytes(good)
    assert hasattr(shape_materialize.manifest_validator(copy), "_findings")
