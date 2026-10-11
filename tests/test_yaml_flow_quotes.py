# SPDX-License-Identifier: Apache-2.0
"""A double-quoted scalar reads the same in a flow collection as in a block.

`_strip_comment` and `_split_key` take the character after a backslash
inside double quotes WITH the backslash, so `\\"` neither ends the scalar
nor lets what follows it read as structure, and `_scalar` resolves it to a
quote. The two scanners of a flow collection did not (#213): `_split_flow`
ended a double-quoted item at the escaped quote, so the `,` or `]` after it
was read as structure, and `_split_key_flow` -- `_split_key` spelled again,
minus that one step -- did the same to a flow mapping's key. One item read as
two, two items read as one garbled item, and a valid document was refused.

Nothing this repository writes puts a quote in a flow item today; a person
editing the adoption plan, or `json.dumps` of a list, does, and the reader
says it raises rather than guessing.

A single-quoted scalar has no backslash escape. Its one escape is `''`, which
both scanners read by toggling twice, and that is unchanged.

NO NETWORK AND NO GITHUB: strings, two temporary files and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml, parse_yaml  # noqa: E402

#: The issue's observed table, each row with the read it should have had.
#: The text is raw: every backslash here is a backslash in the YAML.
ESCAPED_QUOTE_IN_A_FLOW = [
    pytest.param(r'pins: ["x\",y"]', {"pins": ['x",y']},
                 id="one-item-read-as-two"),
    pytest.param(r'pins: ["a\"]", "b"]', {"pins": ['a"]', "b"]},
                 id="two-items-read-as-one"),
    pytest.param(r'pins: [["x\",y"], z]', {"pins": [['x",y'], "z"]},
                 id="nested-sequence-refused"),
    pytest.param(r'pins: {k: "x\",y", j: 2}', {"pins": {"k": 'x",y', "j": 2}},
                 id="mapping-value-refused"),
    pytest.param(r'pins: {"a\": b": 1}', {"pins": {'a": b': 1}},
                 id="mapping-key-misread"),
]


@pytest.mark.parametrize("text, expected", ESCAPED_QUOTE_IN_A_FLOW)
def test_an_escaped_quote_does_not_end_a_double_quoted_flow_item(text,
                                                                 expected):
    assert parse_yaml(text) == expected


def test_a_flow_item_reads_as_its_block_twin(tmp_path):
    """The issue's own reproduction: the same item, once in a flow sequence
    and once in a block sequence, read from files the way every caller
    reads them. Written as bytes, so the file is LF on every platform."""
    flow = tmp_path / "flow.yaml"
    block = tmp_path / "block.yaml"
    flow.write_bytes(b'pins: ["x\\",y"]\n')
    block.write_bytes(b'pins:\n  - "x\\",y"\n')
    assert load_yaml(block) == {"pins": ['x",y']}
    assert load_yaml(flow) == load_yaml(block)


def test_an_escaped_backslash_still_ends_the_item():
    """`\\\\` is one escape, so the quote after it ENDS the item. A fix that
    asked "is this quote preceded by a backslash?" instead of taking the
    character after each backslash would read past it and swallow `b`."""
    assert parse_yaml(r'pins: ["a\\", b]') == {"pins": ["a\\", "b"]}
    assert parse_yaml(r'pins: {"a\\": b}') == {"pins": {"a\\": "b"}}


@pytest.mark.parametrize("text, expected", [
    pytest.param(r"pins: ['x\', 'it''s, a]']", {"pins": ["x\\", "it's, a]"]},
                 id="sequence"),
    pytest.param(r"pins: {'a\': 'it''s: b'}", {"pins": {"a\\": "it's: b"}},
                 id="mapping"),
])
def test_a_single_quoted_flow_item_keeps_its_toggle(text, expected):
    """A backslash in single quotes is a backslash: the quote after it ends
    the item. `''` is a quote, and the `,`, `]` or `:` after it is still
    inside the item."""
    assert parse_yaml(text) == expected
