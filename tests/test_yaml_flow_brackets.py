# SPDX-License-Identifier: Apache-2.0
"""A plain scalar in a flow collection holds no `[`, `]`, `{` or `}` (#301).

In YAML a plain scalar inside a flow collection ENDS at any of `[ ] { } ,`.
`_split_flow` splits a flow body at its top-level commas by counting brackets,
and never asked whether the count went below zero or ended above it, so a body
that closes a bracket it never opened, or opens one inside an item, was read
with the stray bracket kept as text: `pins: [a, b]]` read as the pin `b]`,
`k: [x [a, b]]` as the one item `x [a, b]`, and since #284, which reads a
quote only where a scalar begins, `k: {a"]:}` as the key `a"]`. PyYAML
refuses each. `_refuse_flow_indicator` now refuses a plain item, key or value
of a flow collection that holds one, as a `YamlError`, which `load_yaml` turns
into `REFUSED yaml-unparsable`. A QUOTED scalar's brackets are text, and a
bracket in a BLOCK plain scalar (`k: a[b]`) is a character of it, as before.

Every refused document below is one PyYAML 6.0.3 refuses, except three:
- `k: {a:}#}: b}` and `k: {}#":}`, which PyYAML reads as `{'k': {'a': None}}`
  and `{'k': {}}` only because it takes a `#` with no space before it for a
  comment, which YAML forbids; the subset refuses them as it refuses
  `k: "a"#c`;
- `k: [a: [b]]`, a single-pair mapping in a flow sequence, which PyYAML reads
  as `[{'a': ['b']}]` and this reader read as the string `'a: [b]'`; a
  refusal replaces that misread.
Every expected read is PyYAML's. PyYAML is not imported here; nothing in this
suite depends on it.

NO NETWORK AND NO GITHUB: strings, one temporary file and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (Refusal, YamlError, double_quoted,  # noqa: E402
                        load_yaml, parse_yaml)

#: The phrase every refusal here is made with.
REFUSAL = "a plain scalar in a flow collection holds"

#: #301's own ten documents: the stray closer in an item, in a key and in a
#: key `#284` stopped hiding behind a quote, the opener in an item, and the
#: two PyYAML reads through its `#` leniency. The text is raw.
ISSUE_ROWS = [
    pytest.param("pins: [a, b]]", id="closer-after-the-last-item"),
    pytest.param('k: {a"]:}', id="closer-in-a-key-after-a-quote"),
    pytest.param("k: {a]x:}", id="closer-in-a-key"),
    pytest.param("k: {]:}", id="closer-as-the-key"),
    pytest.param("k: [a]]", id="closer-after-the-only-item"),
    pytest.param("k: [a}]", id="brace-closer-in-an-item"),
    pytest.param("k: [x [a, b]]", id="opener-in-an-item"),
    pytest.param("k: [a[]", id="opener-never-closed"),
    pytest.param("k: {a:}#}: b}", id="pyyaml-reads-a-hash-comment"),
    pytest.param('k: {}#":}', id="pyyaml-reads-an-empty-mapping"),
]


@pytest.mark.parametrize("text", ISSUE_ROWS)
def test_the_issue_rows_are_refused(text):
    with pytest.raises(YamlError, match=REFUSAL):
        parse_yaml(text + "\n")


#: The same defect wherever a plain flow scalar stands: in a value, nested
#: one or two levels down, in a block sequence's flow item, after another
#: entry, an item that is only a bracket, and two collections where one was
#: meant. The text is raw.
EVERYWHERE_ELSE = [
    pytest.param("k: {a: b}}", id="closer-in-a-value"),
    pytest.param("k: {a: b, c: d]}", id="closer-in-a-later-value"),
    pytest.param("k: {a: [b]]}", id="closer-in-a-nested-sequence"),
    pytest.param("k: [[a]]]", id="closer-after-a-nested-sequence"),
    pytest.param("k: [{a: b}}]", id="closer-after-a-nested-mapping"),
    pytest.param("k: [a, ]]", id="an-item-that-is-a-closer"),
    pytest.param("k: [a], [b]", id="two-sequences-on-one-line"),
    pytest.param("k: {a: b}, {c: d}", id="two-mappings-on-one-line"),
    pytest.param("- [a]]", id="block-sequence-flow-item"),
    pytest.param("k:\n  - {a: b}}", id="nested-block-sequence-flow-item"),
    pytest.param("k: {t-'':  x{}", id="a-value-opening-a-brace"),
    pytest.param("k: {a: x{y}}", id="a-value-holding-braces"),
    pytest.param("k: [see [1]]", id="an-item-holding-a-bracket-pair"),
    pytest.param("k: {a b]: c}", id="closer-in-a-key-with-a-space"),
    pytest.param("k: {x: 1, a}: 2}", id="closer-in-a-later-key"),
    # PyYAML READS this one, as a single-pair mapping, `[{'a': ['b']}]`; the
    # subset reads no single-pair mapping and read it as the string `a: [b]`.
    pytest.param("k: [a: [b]]", id="single-pair-mapping-once-misread"),
]


@pytest.mark.parametrize("text", EVERYWHERE_ELSE)
def test_a_bracket_in_a_plain_flow_scalar_is_refused_wherever_it_stands(text):
    with pytest.raises(YamlError, match=REFUSAL):
        parse_yaml(text + "\n")


@pytest.mark.parametrize("text, held, scalar", [
    pytest.param("pins: [a, b]]", "]", "b]", id="item"),
    pytest.param('k: {a"]:}', "]", 'a"]', id="key"),
    pytest.param("k: {a: b}}", "}", "b}", id="value"),
    pytest.param("k: [x [a, b]]", "[", "x [a, b]", id="opener"),
])
def test_the_refusal_names_the_bracket_and_the_scalar(text, held, scalar):
    with pytest.raises(YamlError) as caught:
        parse_yaml(text + "\n")
    assert str(caught.value) == (f"{REFUSAL} `{held}`, which ends it in YAML: "
                                 f"{scalar!r}")


def test_a_stray_bracket_in_a_file_is_a_refusal_naming_the_file(tmp_path):
    """The issue's case, read the way every caller reads one: a stray `]`
    typed into a pin list. Bytes, so the file is LF on every platform."""
    path = tmp_path / "project.yaml"
    path.write_bytes(b"id: atlas\nneutral_product_pins: [openGlass, openDox]]\n")
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    assert str(path) in caught.value.detail
    assert f"{REFUSAL} `]`, which ends it in YAML: 'openDox]'" in \
        caught.value.detail


#: What must NOT change: a bracket inside a quoted flow scalar, nested and
#: empty flow collections, a bracket in a BLOCK plain scalar, a bracket in a
#: comment after a flow, and the other characters a plain flow item may hold.
STILL_READ = [
    pytest.param('k: ["a]", \'b[\', {"c}": "d{"}]',
                 {"k": ["a]", "b[", {"c}": "d{"}]}, id="quoted-brackets"),
    pytest.param("k: {'x]y': \"[z]\"}", {"k": {"x]y": "[z]"}},
                 id="quoted-key-and-value"),
    pytest.param("k: {a: [b, c], d: {e: f}}",
                 {"k": {"a": ["b", "c"], "d": {"e": "f"}}}, id="nested-flows"),
    pytest.param("k: [[a, [b]], {c: [d, {e: f}]}]",
                 {"k": [["a", ["b"]], {"c": ["d", {"e": "f"}]}]},
                 id="deeply-nested-flows"),
    pytest.param("k: [[], {}, [ ], { }]", {"k": [[], {}, [], {}]},
                 id="empty-flows"),
    pytest.param("k: [ ]", {"k": []}, id="an-empty-sequence-with-a-space"),
    pytest.param("k: a]", {"k": "a]"}, id="block-value-closer"),
    pytest.param("k: a[b", {"k": "a[b"}, id="block-value-opener"),
    pytest.param("k: a, b]", {"k": "a, b]"}, id="block-value-comma-closer"),
    pytest.param("k: x {y} z", {"k": "x {y} z"}, id="block-value-braces"),
    pytest.param("- see [1]", ["see [1]"], id="block-item-bracket-pair"),
    pytest.param("k: [a] # ]", {"k": ["a"]}, id="closer-in-a-comment"),
    pytest.param("k: {a: b} # }", {"k": {"a": "b"}},
                 id="brace-in-a-comment"),
    pytest.param("k: [a#b, c:d, e-f]", {"k": ["a#b", "c:d", "e-f"]},
                 id="other-characters-in-plain-items"),
    pytest.param("k: {a: b, c: }", {"k": {"a": "b", "c": None}},
                 id="an-empty-value"),
]


@pytest.mark.parametrize("text, expected", STILL_READ)
def test_what_is_not_a_bracket_in_a_plain_flow_scalar_still_reads(text,
                                                                  expected):
    assert parse_yaml(text + "\n") == expected


@pytest.mark.parametrize("value", ["]", "[", "}", "{", "a]b", "x [a, b]",
                                   "{a: b}", 'a"]', "]: x"])
def test_the_writer_spells_a_bracket_so_a_flow_reads_it_back(value):
    """`double_quoted` is the subset's writer. A value holding a bracket is
    always written QUOTED, so it reads back as an item, a key and a value of
    a flow collection, where the refusal never looks."""
    spelled = double_quoted(value)
    assert parse_yaml(f"k: [{spelled}, b]\n") == {"k": [value, "b"]}
    assert parse_yaml(f"k: {{{spelled}: {spelled}}}\n") == {"k": {value: value}}
