# SPDX-License-Identifier: Apache-2.0
"""The `reference:` a project records is chosen by the DATE it was elected.

The doctrine ratified on 2026-09-02; before that day it existed only as the
staged fragment. So one default cannot serve both eras: writing the ratified
`docs/project-repo-schema.md` into a project dated 2026-08-30 makes its
manifest claim the election followed a document that did not yet exist, which
is the one thing the `reference:` field is for. These tests are that rule —
the unit boundary, and both tools writing it end to end.

NO NETWORK AND NO GITHUB, like the rest of the suite: `--local-remote-dir`
makes bare repositories on disk, and `adopt-project.py plan` only READS a
local source repository.
"""

from __future__ import annotations

import sys

import pytest

from conftest import ADOPT, ORG, REPO, SCAFFOLD, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, load_yaml  # noqa: E402
from shape_materialize import (  # noqa: E402
    DEFAULT_REFERENCE, RATIFICATION_DATE, STAGED_REFERENCE, default_reference,
)

PROJECT = "Northwind"

#: An explicit `--reference` a default could never produce, so a test that
#: sees it knows the flag won rather than that the date happened to agree.
EXPLICIT = "x.md"


# --- the boundary itself ---------------------------------------------------

def test_the_two_references_are_the_two_documents_and_not_each_other():
    """A guard on the constants: `DEFAULT_REFERENCE` keeps its name and its
    ratified value because other modules import it, and the staged path is
    the fragment openxFactory ratified FROM."""
    assert DEFAULT_REFERENCE == "openxFactory docs/project-repo-schema.md"
    assert STAGED_REFERENCE == ("openxFactory ideation/staging/"
                                "project-repo-schema/project-repo-schema.md")
    assert RATIFICATION_DATE.isoformat() == "2026-09-02"


@pytest.mark.parametrize("elected_on,expected", [
    ("2026-08-30", STAGED_REFERENCE),
    ("2026-09-01", STAGED_REFERENCE),   # the day before: still the fragment
    ("2026-09-02", DEFAULT_REFERENCE),  # ratification day: the document
    ("2026-09-03", DEFAULT_REFERENCE),
])
def test_the_default_reference_turns_on_the_ratification_date(elected_on,
                                                              expected):
    """Strictly before the ratification date is the staged fragment; ON it
    and after is the ratified document. The boundary is the interesting part,
    so both sides of it are named here rather than inferred."""
    assert default_reference(elected_on) == expected


@pytest.mark.parametrize("value", ["2026-9-2", "yesterday", "", "2026-13-01"])
def test_an_unreadable_election_date_is_refused_and_never_guessed(value):
    """A date the tool cannot parse would pick the reference on the reader's
    behalf, and the reference is a claim about which document a human read.
    The refusal names the flag, the form and the value seen, so the message
    is the remedy."""
    with pytest.raises(Refusal) as caught:
        default_reference(value)
    assert caught.value.code == "election-date-malformed"
    assert "--elected-on" in caught.value.detail
    assert "YYYY-MM-DD" in caught.value.detail
    assert repr(value) in caught.value.detail


# --- the scaffold ----------------------------------------------------------

def scaffold(tmp_path, *extra: str):
    """One real scaffold into bare repositories on disk, and its manifest."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"), *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    return result, (tmp_path / "work" / PROJECT / "project.yaml").read_text(
        encoding="utf-8")


@pytest.mark.parametrize("elected_on,expected", [
    ("2026-08-30", STAGED_REFERENCE),
    ("2026-09-02", DEFAULT_REFERENCE),
])
def test_the_scaffold_writes_the_reference_the_election_date_chooses(
        tmp_path, elected_on, expected):
    """END TO END, and asserted on the manifest TEXT: the rendered
    `reference:` line is what a reader of the project sees, and what
    `validate-manifest.py` reads. The printed plan says the same thing before
    anything is created, and says that the date is what chose it."""
    result, manifest = scaffold(tmp_path, "--elected-on", elected_on)
    assert f'reference: "{expected}"' in manifest
    assert f"elected_on: {elected_on}" in manifest
    assert f"reference    {expected}" in result.stdout
    assert "(chosen by the election date)" in result.stdout


@pytest.mark.parametrize("elected_on", ["2026-08-30", "2026-09-02"])
def test_an_explicit_reference_wins_on_either_side_of_ratification(
        tmp_path, elected_on):
    """The date chooses the DEFAULT and nothing more. A project electing
    against some third document — a fork's own copy, say — says so with
    `--reference`, and neither era's path may leak in beside it."""
    result, manifest = scaffold(tmp_path, "--elected-on", elected_on,
                                "--reference", EXPLICIT)
    assert f'reference: "{EXPLICIT}"' in manifest
    assert STAGED_REFERENCE not in manifest
    assert DEFAULT_REFERENCE not in manifest
    assert "(chosen by the election date)" not in result.stdout


def test_a_malformed_election_date_refuses_before_anything_is_created(tmp_path):
    """The date is parsed at the top of the scaffold, with the other flags:
    a refusal after the two legs exist would cost three repositories and a
    delete, which is the whole reason the naming check runs there too."""
    remotes = tmp_path / "remotes"
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-9-2",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "election-date-malformed" in result.stderr
    assert not remotes.exists(), (
        "the date is validated before the remotes are created, so a bad one "
        "leaves nothing behind")


def test_an_explicit_reference_does_not_excuse_an_unreadable_date(tmp_path):
    """`--reference` overriding the default must not turn `--elected-on` into
    an unchecked field: `elected_on:` is recorded in the manifest either way,
    and a date no reader can parse is not a record of anything."""
    result = run_script(SCAFFOLD, "--org", ORG, "--project", PROJECT,
                        "--elected-by", "Test Human",
                        "--elected-on", "yesterday",
                        "--reference", EXPLICIT,
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2
    assert "election-date-malformed" in result.stderr


# --- adopt: the same rule, at plan time ------------------------------------

def test_the_adoption_plan_records_the_reference_its_own_date_chose(
        source_repo, tmp_path):
    """`plan` writes the file a human then edits, so the reference has to be
    IN it — resolved from the plan's own `elected_on`, not left for `execute`
    to resolve against the calendar of the machine running the split."""
    out = tmp_path / "adoption-plan.yaml"
    result = run_script(ADOPT, "plan", "--source", str(source_repo),
                        "--project", PROJECT, "--org", ORG,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-08-30", "--out", str(out))
    assert result.returncode == 0, result.stderr + result.stdout
    text = out.read_text(encoding="utf-8")
    assert f'reference: "{STAGED_REFERENCE}"' in text
    assert 'elected_on: "2026-08-30"' in text
    assert load_yaml(out)["reference"] == STAGED_REFERENCE


def test_an_adoption_plan_dated_after_ratification_records_the_document(
        source_repo, tmp_path):
    out = tmp_path / "adoption-plan.yaml"
    result = run_script(ADOPT, "plan", "--source", str(source_repo),
                        "--project", PROJECT, "--org", ORG,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-09-02", "--out", str(out))
    assert result.returncode == 0, result.stderr + result.stdout
    assert load_yaml(out)["reference"] == DEFAULT_REFERENCE


def test_an_adoption_plan_with_an_unreadable_date_is_refused(source_repo,
                                                             tmp_path):
    out = tmp_path / "adoption-plan.yaml"
    result = run_script(ADOPT, "plan", "--source", str(source_repo),
                        "--project", PROJECT, "--org", ORG,
                        "--elected-by", "Test Human",
                        "--elected-on", "2026-9-2", "--out", str(out))
    assert result.returncode == 2
    assert "election-date-malformed" in result.stderr
    assert not out.exists(), "no plan is written from a date nobody can read"
