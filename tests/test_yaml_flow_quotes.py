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

No writer in this repository quotes a flow item: three of the four that
write a flow list emit only names a pattern or a choice list admits, and the
fourth, the `referent_chain` writer in `shape_materialize.py`, writes the
operator's chain links as given. A person editing the adoption plan, or
`json.dumps` of a list, does put quotes there, and the reader says it raises
rather than guessing.

A single-quoted scalar has no backslash escape. Its one escape is `''`, which
both scanners read by toggling twice, and that is unchanged.

A backslash that is the last character of a double-quoted flow item's text has
no character after it to take. That is not valid YAML, and the reader must say
so as a `YamlError` or read it as its block twin does, never die with a
`StopIteration` out of the scanner (the `""` default of `next(chars, "")` in
`_split_flow`).

NO NETWORK AND NO GITHUB: strings, a few temporary files and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, YamlError, load_yaml, parse_yaml  # noqa: E402

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


#: A double-quoted flow item whose last character is a backslash. The closing
#: bracket right after it belongs to the collection, so the scanner reaches
#: the end of the body with an escape still open. Each is the read at the head
#: of this change, and each equals what the block twin reads: the backslash is
#: kept, and the quote is not closed, so the item is plain text. The text is
#: raw: the one backslash in each is one backslash in the YAML.
#:
#: These are not valid YAML (PyYAML refuses every one), so what they pin is
#: that the reader does not crash. If a later change refuses an unterminated
#: double-quoted scalar, in a block as well as in a flow, these become
#: refusals together with their block twins, and that is the change to make
#: here, not a regression.
DANGLING_BACKSLASH_BEFORE_THE_CLOSER = [
    pytest.param(r'k: ["a\]', {"k": ['"a\\']}, 'k:\n  - "a\\',
                 id="sequence"),
    pytest.param(r'k: ["\]', {"k": ['"\\']}, 'k:\n  - "\\',
                 id="sequence-the-quote-and-the-backslash-only"),
    pytest.param(r'k: {a: "x\}', {"k": {"a": '"x\\'}}, 'k:\n  a: "x\\',
                 id="mapping-value"),
    pytest.param(r'k: [["\]]', {"k": [['"\\']]}, 'k:\n  - - "\\',
                 id="nested-sequence"),
]


@pytest.mark.parametrize("text, expected, block_twin",
                         DANGLING_BACKSLASH_BEFORE_THE_CLOSER)
def test_a_dangling_backslash_before_the_closer_reads_as_plain_text(
        text, expected, block_twin):
    """With `next(chars)` for `next(chars, "")` these die with a bare
    `StopIteration` out of `parse_yaml`, and `load_yaml` would let it through
    as a traceback rather than a `REFUSED` line."""
    assert parse_yaml(text) == expected
    assert parse_yaml(block_twin) == expected, "its block twin reads the same"


#: The same backslash where nothing follows it. At the very end of the text
#: the closing bracket is missing, so `_flow` refuses the text before any
#: scanner runs (`not a flow collection`); those two are plain strings, as a
#: raw string cannot end in a backslash. A mapping KEY ending in the backslash,
#: before the closing brace, reaches `_split_flow` with the escape open and is
#: refused one step later, as an entry with no key.
DANGLING_BACKSLASH_REFUSED = [
    pytest.param('k: ["a\\', "not a flow collection",
                 id="sequence-at-the-end-of-the-text"),
    pytest.param('k: {a: "x\\', "not a flow collection",
                 id="mapping-at-the-end-of-the-text"),
    pytest.param(r'k: {"a\}', "flow mapping entry without a key",
                 id="mapping-key-before-the-closer"),
]


@pytest.mark.parametrize("text, message", DANGLING_BACKSLASH_REFUSED)
def test_a_dangling_backslash_with_no_closer_or_key_is_a_yaml_error(
        text, message):
    with pytest.raises(YamlError, match=message):
        parse_yaml(text)


def test_a_dangling_backslash_in_a_file_is_a_refusal_not_a_traceback(
        tmp_path):
    """Read from a file the way every caller reads it: `yaml-unparsable`
    with the file named, and no bare exception. Bytes, so LF everywhere."""
    path = tmp_path / "plan.yaml"
    path.write_bytes(b'k: {"a\\}\n')
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    assert str(path) in caught.value.detail
