# SPDX-License-Identifier: Apache-2.0
"""A free-text value between a YAML template's double quotes reads back.

`project.yaml`, `family.yaml`, the pins and `single-repository.yaml` quote
their free-text fields: `elected_by: "{{ELECTED_BY}}"`. `render` pasted the
value raw, so `--elected-by 'Robert "Bob" Smith'` wrote
`elected_by: "Robert "Bob" Smith"`, which is not YAML. The reader took it
by accident while it read any text that starts and ends with a quote as one
quoted scalar; once it learned where a quoted scalar ends (#250) it refused
the manifest, after the scaffold had created and pushed three repositories.
A name ending in a backslash closed no quote at all, and `C:\\new` or
`x" # y` were misread even then: an escape, and a comment.

`render` now spells such a value with `double_quoted`, the writer the reader
takes back unchanged. For any value with no quote, no backslash and no
character `str.isprintable` refuses -- every commit, digest, date and
ordinary name -- the spelling is the value, so no template changes by a byte.

NO NETWORK AND NO GITHUB: templates rendered in memory, and one scaffold
into local bare remotes (`--local-remote-dir`), which never calls `gh`.
"""

from __future__ import annotations

import re
import sys

import pytest

from conftest import ORG, REPO, SCAFFOLD, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, parse_yaml  # noqa: E402
from shape_materialize import render  # noqa: E402

PLACEHOLDER = re.compile(r"\{\{([A-Z_]+)\}\}")
QUOTED_PLACEHOLDER = re.compile(r'"\{\{([A-Z_]+)\}\}"')

#: Every YAML template that quotes a placeholder. Found, not listed, so a
#: template that gains a quoted field is covered without an edit here.
QUOTING_TEMPLATES = sorted(
    path.relative_to(REPO).as_posix()
    for pattern in ("*.yaml", "*.yml")
    for path in (REPO / "templates").rglob(pattern)
    if QUOTED_PLACEHOLDER.search(path.read_text(encoding="utf-8")))

#: Free text a person can pass as `--elected-by`, `--name`, `--reference`,
#: `--created-by` or put in an adoption plan. The first is the one main read
#: by accident and a stricter reader refuses; the rest it misread or refused.
FREE_TEXT = [
    pytest.param('Robert "Bob" Smith', id="double-quotes"),
    pytest.param("Jane\\", id="trailing-backslash"),
    pytest.param("C:\\new", id="backslash-letter"),
    pytest.param('x" # y', id="quote-then-comment"),
    pytest.param("\\x41", id="code-point-escape-spelled"),
    pytest.param("tab\there", id="tab"),
    pytest.param("O'Brien # it's", id="apostrophes-and-hash"),
]


def rendered(template: str, free_text: str) -> tuple[str, int]:
    """The template with `free_text` in every quoted placeholder and a
    harmless stand-in everywhere else, and how many quoted fields it has."""
    text = (REPO / template).read_text(encoding="utf-8")
    quoted = set(QUOTED_PLACEHOLDER.findall(text))
    values = {}
    for key in set(PLACEHOLDER.findall(text)):
        if key in quoted:
            values[key] = free_text
        elif re.search(r"^\{\{" + key + r"\}\}", text, re.M):
            values[key] = f"    stand_in_{key.lower()}: 1"  # a block placeholder
        else:
            values[key] = f"v-{key.lower()}"
    return render(text, values, template), len(QUOTED_PLACEHOLDER.findall(text))


def scalars(node) -> list:
    if isinstance(node, dict):
        return [s for value in node.values() for s in scalars(value)]
    if isinstance(node, list):
        return [s for value in node for s in scalars(value)]
    return [node]


def test_the_templates_that_quote_a_placeholder_are_found():
    """The free-text fields of the manifest, the family and the
    single-repository record, and the quoted hex of every pin."""
    assert "templates/assembly-root/project.yaml" in QUOTING_TEMPLATES
    assert "templates/family-root/family.yaml" in QUOTING_TEMPLATES
    assert ("templates/single-repository/single-repository.yaml"
            in QUOTING_TEMPLATES)


@pytest.mark.parametrize("free_text", FREE_TEXT)
@pytest.mark.parametrize("template", QUOTING_TEMPLATES)
def test_a_quoted_free_text_field_reads_back_exactly(template, free_text):
    text, fields = rendered(template, free_text)
    assert scalars(parse_yaml(text)).count(free_text) == fields, text


@pytest.mark.parametrize("template", QUOTING_TEMPLATES)
def test_an_ordinary_value_renders_byte_for_byte_as_before(template):
    """A commit, a digest, a date and a name without a quote or a backslash
    are written exactly as a plain substitution writes them."""
    text = (REPO / template).read_text(encoding="utf-8")
    values = {key: ("0123456789abcdef" * 4 if "SHA256" in key else
                    "c0ffee" * 6 + "abcd" if "COMMIT" in key else
                    "2026-09-02" if key.endswith("_ON") else "Brett Heap — é")
              for key in set(PLACEHOLDER.findall(text))}
    plain = text
    for key, value in values.items():
        plain = plain.replace("{{" + key + "}}", value)
    assert render(text, values, template) == plain


def test_a_template_that_is_not_yaml_keeps_the_value_raw():
    """A README or AGENTS.md is read by a person, not the YAML reader: a
    quote there is a quote, and escaping it would print a backslash."""
    text = 'Elected by "{{ELECTED_BY}}".\n'
    values = {"ELECTED_BY": 'Robert "Bob" Smith'}
    assert render(text, values, "README.md") == (
        'Elected by "Robert "Bob" Smith".\n')
    assert render(text, values, "templates/assembly-root/README.md") == (
        'Elected by "Robert "Bob" Smith".\n')


def test_a_scaffold_with_quotes_and_backslashes_writes_a_manifest_it_reads(
        tmp_path):
    """The scaffold itself, end to end into local bare remotes: the
    manifest it writes passes its own validator and holds what was typed."""
    remotes, work = tmp_path / "remotes", tmp_path / "work"
    elected_by = 'Robert "Bob" Smith'
    reference = "docs\\notes # 1"
    name = 'Atlas "the" Project'
    result = run_script(SCAFFOLD, "--org", ORG, "--project", "Atlas",
                        "--name", name, "--elected-by", elected_by,
                        "--reference", reference,
                        "--elected-on", "2026-09-02",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(work))
    assert result.returncode == 0, result.stderr + result.stdout
    root = work / "Atlas"
    check = run_script(root / "scripts" / "validate-manifest.py", cwd=root)
    assert check.returncode == 0, check.stderr + check.stdout
    manifest = load_yaml(root / "project.yaml")
    assert manifest["elected_by"] == elected_by
    assert manifest["reference"] == reference
    assert manifest["name"] == name
