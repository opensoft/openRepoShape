# SPDX-License-Identifier: Apache-2.0
"""A scaffold refuses a value the new project's manifest cannot hold (#258, #261).

`scaffold-project.py` writes `--id` and `--tracking-branch` into
`project.yaml` bare, so `--id null` and `--id true` scaffolded a project whose
first bootstrap failed `manifest-id`, and `--tracking-branch true`, `007` or
`null` pushed every repository on the branch as typed while bootstrap read the
manifest back as `True`, `7` or `main` and put each leg on a local branch the
remotes do not have, with no upstream. It exited 0 and said nothing (#258).

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
bare repositories on disk, or `--dry-run`, which makes nothing; the one test
that proves `gh` is never asked puts a fake one on PATH.
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

from conftest import (FILE_PROTOCOL, ORG, REPO, SCAFFOLD, WINDOWS_SKIP, git,
                      run_script)

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

#: `(flag, value, what the project's reader makes of it)`. Each is a legal git
#: branch name or a legal id, the reader takes it for something else, and the
#: manifest writes it bare.
MISREAD_VALUES = [
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
    pytest.param("--tracking-branch", "~", "no value at all", id="branch-tilde"),
    pytest.param("--tracking-branch", "007", "the number 7", id="branch-007"),
    pytest.param("--tracking-branch", "2026", "the number 2026",
                 id="branch-2026"),
    pytest.param("--tracking-branch", "1.5", "the number 1.5", id="branch-1.5"),
    pytest.param("--tracking-branch", "1.50", "the number 1.5",
                 id="branch-1.50"),
    pytest.param("--tracking-branch", "0", "the number 0", id="branch-0"),
]

#: Values the reader takes for text, so the manifest holds what was typed.
#: `yes` and `on` are YAML 1.1 booleans and this reader reads them as text;
#: `0x1F`, `1e3` and `.inf` are numbers elsewhere and text here. They are not
#: refused: the reader is asked, not a list of its words.
TEXT_BRANCHES = ["trunk", "release-1", "feature/x", "v1.2.3", "1.5.2", "yes",
                 "on", "0x1F", "1e3", ".inf"]
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
             local: bool = True):
    """One scaffold of `Atlas` into local bare remotes under `tmp_path`.

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
    return run_script(SCAFFOLD, *flags, env={
        "TMPDIR": str(scratch), "TMP": str(scratch), "TEMP": str(scratch)})


def assert_nothing_was_created(tmp_path: Path) -> None:
    """No bare remote, no work directory of the tool's own and none of ours."""
    found = sorted(p.name for p in tmp_path.iterdir())
    assert found == [SCRATCH], f"a refused scaffold created something: {found}"
    assert list((tmp_path / SCRATCH).iterdir()) == [], (
        "a refused scaffold made a temporary work directory")


def assert_refused(result, code: str) -> None:
    assert result.returncode == 2, result.stderr + result.stdout
    assert code in result.stderr, result.stderr
    assert result.stdout == "", "a plan was printed for a refused scaffold"


# --- #258: a value the project's reader turns into something else ---------

@pytest.mark.parametrize("flag, value, reading", MISREAD_VALUES)
def test_a_value_the_reader_misreads_is_refused_before_anything_is_made(
        tmp_path, flag, value, reading):
    # `=` form, so a value that begins with `~` or `-` reaches the tool as a
    # value and argparse does not take it for another option.
    result = scaffold(tmp_path, f"{flag}={value}")
    assert_refused(result, MISREAD)
    assert f"{flag} is {value!r}" in result.stderr
    assert f"reads it back as {reading} and not as that text" in result.stderr
    assert "Remediation: choose another value" in result.stderr
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value", [("--id", "null"),
                                         ("--tracking-branch", "007")])
def test_a_dry_run_refuses_a_misread_value_as_the_real_run_would(
        tmp_path, flag, value):
    """`--dry-run` is a rehearsal: it must not print a plan for a scaffold the
    real run refuses (the issue's own `--dry-run` accepted every one)."""
    result = scaffold(tmp_path, "--dry-run", f"{flag}={value}")
    assert_refused(result, MISREAD)
    assert_nothing_was_created(tmp_path)


@pytest.mark.parametrize("flag, value", [
    ("--tracking-branch", "2026"), ("--tracking-branch", "1.5"),
    ("--tracking-branch", "007"), ("--id", "2026"), ("--id", "null"),
])
def test_the_remediation_says_what_is_true_of_every_value_it_refuses(
        tmp_path, flag, value):
    """`--tracking-branch 2026` and `1.5` are the values this refusal newly
    takes from people: they scaffolded, bootstrapped and got their upstream,
    because every reader of `tracking_branch` does `str()` and `str(2026)` is
    `2026` again. The remediation once said the first bootstrap would fail or
    put the legs on a branch the remotes lack, which is false of exactly
    those, so it now says only what holds of all of them -- the project's
    reader reads back something other than what was typed -- names the
    failures that do hold, says plainly that a number which survives `str()`
    is a number all the same, and gives the way forward: a value that is text
    to the reader."""
    result = scaffold(tmp_path, "--dry-run", f"{flag}={value}")
    assert_refused(result, MISREAD)
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
def test_an_id_derived_from_the_project_name_is_asked_too(
        tmp_path, project, derived, reading):
    """With no `--id` the id is the project name lowercased, so `--project
    Null` is `id: null`; the sentence says where the id came from, so it does
    not point at a flag nobody typed."""
    result = scaffold(tmp_path, "--project", project)
    assert_refused(result, MISREAD)
    assert (f"--id (not given, so --project lowercased) is {derived!r}"
            in result.stderr)
    assert reading in result.stderr
    assert_nothing_was_created(tmp_path)


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
    clone = tmp_path / "Atlas"
    cloned = git(*FILE_PROTOCOL, "clone", "-q", "--recurse-submodules",
                 str(tmp_path / REMOTES / "Atlas.git"), str(clone),
                 cwd=tmp_path, check=False)
    assert cloned.returncode == 0, cloned.stderr
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


def test_the_longest_name_a_disk_keeps_is_still_accepted(tmp_path):
    """246 characters is `<project>-spec.git` at exactly 255 bytes. A dry run
    only: a real tree this deep is a Windows path the OS will not open."""
    result = scaffold(tmp_path, "--project", "N" * 246, "--dry-run")
    assert result.returncode == 0, result.stderr + result.stdout
    without_remotes = scaffold(tmp_path, "--project", "N" * 250, "--dry-run",
                               local=False)
    assert without_remotes.returncode == 0, without_remotes.stderr


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

@WINDOWS_SKIP  # the `gh` below is a `#!` script, which Windows does not run
@pytest.mark.parametrize("flag", ["--id=null", "--tracking-branch=true",
                                  "--elected-by= ", "--org=test+org"])
def test_a_refused_value_never_reaches_gh(tmp_path, flag):
    """Local remotes are the test path; the real one calls `gh repo create`.
    Each refusal comes before the first `gh` call, so no repository is made
    on the forge for a project that was never going to scaffold."""
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
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED" in result.stderr
    assert not log.exists(), f"gh was asked: {log.read_text()}"
    assert not (tmp_path / WORK).exists()


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


def test_quoting_the_template_would_make_the_refusal_go_away(tmp_path):
    """#259 proposes quoting `id:` and `tracking_branch:` in the template. The
    question is asked of the TEMPLATE, so the day it does, those values read
    back and nothing here refuses them, with no edit to this rule."""
    copy = tmp_path / "assembly-root"
    shutil.copytree(REPO / "templates" / "assembly-root", copy,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    manifest = copy / "project.yaml"
    text = manifest.read_text(encoding="utf-8")
    quoted = (text.replace("id: {{PROJECT_ID}}", 'id: "{{PROJECT_ID}}"')
              .replace("tracking_branch: {{TRACKING_BRANCH}}",
                       'tracking_branch: "{{TRACKING_BRANCH}}"'))
    assert quoted != text
    manifest.write_text(quoted, encoding="utf-8")
    values = {"PROJECT_ID": "null", "TRACKING_BRANCH": "007"}
    what = {"PROJECT_ID": "--id", "TRACKING_BRANCH": "--tracking-branch"}
    assert len(shape_materialize.manifest_misreads(values, what)) == 2
    assert shape_materialize.manifest_misreads(values, what, copy) == []
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
    `template-unsubstituted`."""
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
        manifest.read_text(encoding="utf-8")
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
def test_a_misread_sentence_holding_a_line_break_is_one_printable_line(char):
    """The manifest is split at the break, so the reader refuses it; the
    sentence says so without printing the break itself."""
    what = {"TRACKING_BRANCH": "--tracking-branch"}
    (sentence,) = shape_materialize.manifest_misreads(
        {"TRACKING_BRANCH": f"a{char}b"}, what)
    assert len(sentence.splitlines()) == 1
    assert sentence.isprintable()
    assert "into project.yaml as 'tracking_branch: a\\" in sentence
    # a printable misread is quoted in backticks, as before
    (plain,) = shape_materialize.manifest_misreads(
        {"TRACKING_BRANCH": "007"}, what)
    assert "into project.yaml as `tracking_branch: 007`" in plain


# --- the placeholders a misread rule would refuse ---------------------------

def test_the_misread_placeholders_are_the_ones_the_misread_rule_refuses():
    """What a caller that leaves misreads to a rule of its own asks of the
    validator is whatever `manifest_misreads` would refuse, as an answer of
    the project's reader and not a list of values."""
    what = {"PROJECT_ID": "--id", "TRACKING_BRANCH": "--tracking-branch",
            "ELECTED_BY": "--elected-by", "ELECTED_ON": "--elected-on",
            "VISIBILITY": "--visibility", "ORG": "--org"}
    values = {"PROJECT_ID": "007", "TRACKING_BRANCH": "2026",
              "ELECTED_BY": " ", "ELECTED_ON": "2026-09-02",
              "VISIBILITY": "true", "ORG": "acme"}
    asked = shape_materialize.misread_placeholders(values, what)
    assert sorted(asked) == ["PROJECT_ID", "TRACKING_BRANCH", "VISIBILITY"]
    assert len(shape_materialize.manifest_misreads(values, what)) == len(asked)
    assert shape_materialize.misread_placeholders(
        {"PROJECT_ID": "atlas"}, what) == ()


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


def a_copy_of_the_standard(base: Path, remake) -> Path:
    """The standard, as its own git checkout (the tools name their revision),
    with its template's `validate-manifest.py` made over by `remake`, which is
    given the real text and returns the text to put there, or None to remove
    the file."""
    copy = base / "standard"
    shutil.copytree(REPO, copy, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "tests", "docs", "handoffs"))
    git("init", "-q", cwd=copy)
    git("add", "-A", cwd=copy)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--no-gpg-sign", "-m", "a copy of the standard", cwd=copy)
    path = copy / "templates" / "assembly-root" / "scripts" / (
        "validate-manifest.py")
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
