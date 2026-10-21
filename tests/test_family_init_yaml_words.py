# SPDX-License-Identifier: Apache-2.0
"""`family.py init`: where the holder's own YAML reader refuses the manifest
`init` would write, the refusal names the value on the line it refuses and
gives the reader's remedy (#929, #459's U119 and U151).

#817 (#708) did this for the scaffold and `adopt-project.py`. The family half
was left: the reader refuses `repository: @x/<Family>`, so `init --org @x
--local-remote-dir <dir>` said only "the manifest this run would write is a
file the holder's own YAML reader refuses", named no value, and its remedy
said "the words after each value are the validator's own", when the words
were the reader's and the validator was never asked. Without
`--local-remote-dir`, `--org @x` is refused first as `family-bad-org` (#871),
so this wording is reached where no GitHub repository is made, or by a value
that passes GitHub's checks and that the reader still refuses.

`init` now asks `shape_materialize._unread_sentences`, the scaffold's and
`adopt-project.py`'s since #708, of `family.yaml`, with `--org` carried by
the holder's `repository:`, and gives the reader's remedy, which opens with
the sentence the project's does (`UNREADABLE_CHOICE`). The code is
`family-manifest-invalid` still, as #708 kept `-manifest-invalid` for the
other two. A finding of the validator's keeps the validator's remedy.

NO NETWORK AND NO GITHUB: `--local-remote-dir`, a template copy and the
suite's `gh` guard.
"""

from __future__ import annotations

import re
import sys

import pytest

from conftest import REPO
from test_family_init_values import (
    HOLDER, TEMPLATE, family_module, given, init, nothing_was_created, table,
    template_copy,
)
from test_reader_refusals_named import NOT_THE_VALIDATORS, OPENS

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402

#: The code all three cases are refused under.
INVALID = "family-manifest-invalid"

#: The reader's remedy, as `init` gives it, before the sentence it ends with.
READER_REMEDY = (
    "Remediation: choose another value for each one named; where none is "
    "named, the text the reader's words quote holds it. The words are the "
    "holder's own YAML reader's, which refuses the manifest this run would "
    "write before its validate-family.py can be asked. A holder whose "
    "manifest it refuses is red from its first commit, because `make "
    "validate` and the `validate` workflow run that validator first, and "
    "`init` cannot be run again over a pushed holder: there is no --force.")

#: The validator's remedy, as `init` gives it, before the sentence it ends
#: with: what a finding of the validator's is told.
VALIDATOR_REMEDY = (
    "Remediation: choose a value the holder's own validate-family.py "
    "accepts; the words after each value are the validator's own. A holder "
    "it refuses is red from its first commit, because `make validate` and "
    "the `validate` workflow run it first, and `init` cannot be run again "
    "over a pushed holder: there is no --force.")

#: What the manifest that is not a mapping is told (#1059): the defect of the
#: standard, aimed at the template's own `family.yaml`, and not the
#: validator's remedy above, which it was told until #1059 (lane 5's review
#: of #960, NIT 3, asked a test to hold its kind and remedy; lane 5 agreed on
#: #473 that this was the better remedy, as no value reaches it).
NOT_A_MAPPING_REMEDY = (
    "Remediation: this is a defect in the copy of this standard you ran, "
    "not in your values: templates/family-root/family.yaml is broken "
    "there, as the holder's own YAML reader makes no mapping of it. Restore "
    "it from the standard's repository, or reinstall the standard, and run "
    "again.")

#: The misread remedy, as `init` gives it, before the sentence it ends with.
MISREAD_REMEDY = (
    "Remediation: choose another value for each one named, as nothing here "
    "will retype it for you. family.yaml writes a value like these unquoted, "
    "so the holder's own YAML reader takes `null` and `~` for no value, "
    "`true` and `false` for booleans, and `007`, `2026` or `20261011` for "
    "numbers: what it reads back is not what was typed. A value the reader "
    "takes for text (`contoso`, `release-2026`, `v2`) passes. A branch `007` "
    "reads back as the branch `7`, and `2026` happens to work today because "
    "the tools that read it turn the number back into text, but it is still "
    "a number to the holder's reader and not a name.")

#: The sentence every `init` remedy ends with, nothing having been made.
NOTHING = " Nothing was created, and `--dry-run` refuses the same."

#: How the reader's words begin where they are the holder's.
HOLDERS_READER_REFUSES = "which the holder's own YAML reader refuses: "


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "run"])
@pytest.mark.parametrize("org", ["@x", "@opensoft"])
def test_init_names_org_with_the_readers_remedy(tmp_path, org, dry_run):
    """The issue's probe, both runs: `--org` is named, with the reader's
    words for the holder's `repository:` line, under the reader's remedy,
    and nothing is created."""
    result = init(tmp_path, "--org", org, dry_run=dry_run,
                  without=("--org",))
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == ""
    assert (f"REFUSED {INVALID}: --org is {org!r}, {HOLDERS_READER_REFUSES}"
            f"{OPENS} `@`, which is reserved in YAML: '{org}/{HOLDER}'.\n"
            f"{READER_REMEDY}{NOTHING}\n") in result.stderr
    assert NOT_THE_VALIDATORS not in result.stderr
    nothing_was_created(tmp_path)


def test_a_refused_line_that_carries_no_value_names_the_whole_file(
        tmp_path):
    """Where the reader refuses a line that carries none of the values, the
    sentence is its refusal of the whole file, as it was, and the remedy is
    the reader's, which says where none is named, the text its words quote
    holds it."""
    template = template_copy(tmp_path, "unreadable", quoted=True)
    manifest = template / "family.yaml"
    manifest.write_bytes(manifest.read_bytes() + b"notes: @nobody\n")
    module = family_module()
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(), table(), template)
    assert caught.value.code == INVALID
    assert caught.value.detail == (
        "the manifest this run would write is a file the holder's own YAML "
        f"reader refuses: {OPENS} `@`, which is reserved in YAML: "
        "'@nobody'.")
    assert caught.value.remediation == READER_REMEDY + NOTHING


def test_a_finding_of_the_validator_keeps_the_validators_remedy():
    """The control: `--created-by ' '` reaches the validator, whose finding
    is named in its own words under its own remedy, as before."""
    module = family_module()
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(created_by=" "),
                                          table(CREATED_BY=" "), TEMPLATE)
    assert caught.value.code == INVALID
    assert caught.value.detail.startswith(
        "--created-by is ' ', which the holder's own validate-family.py "
        "refuses: family-created-by: "), caught.value.detail
    assert caught.value.remediation == VALIDATOR_REMEDY + NOTHING


def test_a_manifest_that_is_not_a_mapping_keeps_its_kind_and_remedy(
        tmp_path):
    """LANE 5'S REVIEW OF #960, NIT 3, MOVED BY #1059. The manifest that is
    not a mapping keeps its code, `family-manifest-invalid`, and its words,
    and its kind is `not-a-mapping`, whose remedy is the defect of the
    standard and names `templates/family-root/family.yaml`. The existing
    test of it (`test_family_init_values.py`) holds only the sentence; this
    holds the remedy too, so a change of its kind (#960's mutant M2 made it
    `unreadable`) fails a test, and so does a return to the validator's
    remedy, which sends a person to retype a value that was never wrong."""
    template = template_copy(tmp_path, "list", quoted=True)
    (template / "family.yaml").write_bytes(b"- one\n- two\n")
    module = family_module()
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(), table(), template)
    assert caught.value.code == INVALID
    assert caught.value.detail == (
        "the manifest this run would write is not a mapping, which is what "
        "the holder's own YAML reader makes of it.")
    assert caught.value.remediation == NOT_A_MAPPING_REMEDY + NOTHING


def test_the_not_a_mapping_remedy_names_each_manifests_own_template():
    """#1059: the remedy is one sentence, built once, for both manifests, and
    each names the template file its own reader reads (`family.yaml` under
    `family-root`, `project.yaml` under `assembly-root`) and no other; the
    file it names is there. Every kind of problem has a remedy in each
    manifest's table, so a kind added to one and not the other is a
    `KeyError` where a person was to be told what to do."""
    family = family_module()
    project = shape_materialize.PROJECT_MANIFEST
    holder = family.HOLDER_MANIFEST
    kinds = {shape_materialize.KIND_MISREAD, shape_materialize.KIND_INVALID,
             shape_materialize.KIND_UNREADABLE,
             shape_materialize.KIND_NOT_A_MAPPING}
    assert set(project.remediations) == kinds
    assert set(holder.remediations) == kinds
    assert family.KIND_NOT_A_MAPPING is shape_materialize.KIND_NOT_A_MAPPING
    assert holder.remediations[family.KIND_NOT_A_MAPPING] == (
        NOT_A_MAPPING_REMEDY)
    assert project.remediations[shape_materialize.KIND_NOT_A_MAPPING] == (
        "Remediation: this is a defect in the copy of this standard you ran, "
        "not in your values: templates/assembly-root/project.yaml is broken "
        "there, as the project's own YAML reader makes no mapping of it. "
        "Restore it from the standard's repository, or reinstall the "
        "standard, and run again.")
    for each, template, manifest in (
            (holder, "family-root", "family.yaml"),
            (project, "assembly-root", "project.yaml")):
        remedy = each.remediations[shape_materialize.KIND_NOT_A_MAPPING]
        named = re.findall(r"templates/[A-Za-z0-9./_-]+?(?=\s)", remedy)
        assert named == [f"templates/{template}/{manifest}"], remedy
        assert (REPO / named[0]).is_file(), named
        assert (each.template, each.manifest) == (template, manifest)


def test_the_projects_remedy_keeps_its_words():
    """The project's remedy is built from the sentence the holder's opens
    with now, and says what it said under #708, byte for byte."""
    assert shape_materialize.MANIFEST_UNREADABLE_REMEDIATION == (
        "Remediation: choose another value for each one named; where none is "
        "named, the text the reader's words quote holds it. The words are the "
        "project's own YAML reader's, which refuses the manifest this run "
        "would write before its validate-manifest.py can be asked, and a "
        "project whose manifest it refuses is one whose first bootstrap would "
        "fail.")


def test_a_misread_keeps_its_words_and_its_remedy(tmp_path):
    """#925: the misread question and the refusal are `shape_materialize`'s,
    the scaffold's, asked of `family.yaml`. The sentence and the remedy are
    the family's, byte for byte, and the remedy ends with the sentence every
    `init` remedy ends with."""
    template = template_copy(tmp_path, "bare", quoted=False)
    module = family_module()
    with pytest.raises(module.Refusal) as caught:
        module.refuse_unholdable_manifest(given(id="null"),
                                          table(FAMILY_ID="null"), template)
    assert caught.value.code == "family-manifest-misread"
    assert caught.value.detail == (
        "--id is 'null', which is written into family.yaml as `id: null`, "
        "where the holder's own YAML reader reads it back as no value at all "
        "and not as that text.")
    assert caught.value.remediation == MISREAD_REMEDY + NOTHING
