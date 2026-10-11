# SPDX-License-Identifier: Apache-2.0
"""A flow mapping's entry reads as its block twin does, or is refused as it is.

Two edges of the reader's flow-mapping entry that #213 did not touch (#252):

1. An EXPLICIT KEY. The block reader refuses `? ` by name, and the reader's
   header lists explicit keys as REFUSED: an explicit key has a meaning the
   reader would have to invent, and an invented meaning in a validator is a
   wrong answer with a confident tone. `_refuse_unsupported` runs on block
   lines only, so in a flow mapping `? a: b` was the literal key `? a`.
2. An EMPTY VALUE. `_flow_value` asked `text[:1] in "[{"`, which is True for
   the empty string, so `{a: }` and `{a:}` ran `_flow('')` and were refused as
   `not a flow collection: ''`, naming a text nobody wrote. The block twin
   `a:` reads `{'a': None}`, and so does YAML. The question is whether the
   text OPENS a flow collection, and an empty one opens nothing.

No writer in this repository emits either form: the four that write a flow
collection emit sequences of bare words and `[]`. So both show only in a file
a person edits, such as `naming: {form: }` left half filled in `project.yaml`.

NO NETWORK AND NO GITHUB: strings, a few temporary files and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, YamlError, load_yaml, parse_yaml  # noqa: E402

#: The one phrase the block reader refuses an explicit key with, after its
#: `line N:` prefix. The flow reader has no line to name, and says the same.
EXPLICIT_KEY_REFUSAL = "explicit keys are not supported"

#: An explicit key in each place a flow mapping entry can stand: first, after
#: another entry, with no value, with an empty key, with a flow collection for
#: a key, nested in a flow mapping and in a flow sequence, and as the item of a
#: block sequence. Each is the text raw.
EXPLICIT_KEYS_IN_A_FLOW_MAPPING = [
    pytest.param("k: {? a: b}", id="the-issue-row"),
    pytest.param("k: {x: 1, ? a: b}", id="after-another-entry"),
    pytest.param("k: {? a}", id="with-no-value"),
    pytest.param("k: {? : b}", id="with-an-empty-key"),
    pytest.param("k: {?   a: b}", id="with-more-than-one-space"),
    pytest.param("k: { ? a: b }", id="with-the-braces-spaced"),
    pytest.param("k: {? [a]: b}", id="with-a-flow-sequence-for-a-key"),
    pytest.param("k: {a: {? b: c}}", id="nested-in-a-flow-mapping"),
    pytest.param("k: [{? a: b}]", id="nested-in-a-flow-sequence"),
    pytest.param("- {? a: b}", id="in-a-block-sequence-item"),
    pytest.param("- k: {? a: b}", id="in-a-block-sequence-mapping"),
    pytest.param('k: {"x": 1, ? "a": b}', id="with-a-quoted-key"),
]


@pytest.mark.parametrize("text", EXPLICIT_KEYS_IN_A_FLOW_MAPPING)
def test_an_explicit_key_in_a_flow_mapping_is_refused(text):
    with pytest.raises(YamlError, match=EXPLICIT_KEY_REFUSAL):
        parse_yaml(text + "\n")


@pytest.mark.parametrize("text", [
    pytest.param("k:\n  ? a\n  : b\n", id="two-lines"),
    pytest.param("k:\n  ? a: b\n", id="one-line"),
    pytest.param("- ? a\n", id="in-a-block-sequence"),
])
def test_an_explicit_key_in_a_block_is_refused_the_same_way(text):
    """The twin the flow refusal is written to match: the same phrase. The
    block one names its line first, which a flow collection has none to."""
    with pytest.raises(YamlError, match=EXPLICIT_KEY_REFUSAL):
        parse_yaml(text)


def test_the_refusal_names_the_entry_it_stopped_at():
    with pytest.raises(YamlError) as caught:
        parse_yaml("k: {x: 1, ? a: b}\n")
    assert "'? a: b'" in str(caught.value)


def test_an_explicit_key_in_a_file_is_a_refusal_with_the_file_named(tmp_path):
    """Read from a file the way every caller reads it: `yaml-unparsable`, the
    file named, the phrase in the detail. Bytes, so LF on every platform."""
    path = tmp_path / "project.yaml"
    path.write_bytes(b"naming: {? form: x}\n")
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    assert str(path) in caught.value.detail
    assert EXPLICIT_KEY_REFUSAL in caught.value.detail


#: What stays a KEY that merely holds a `?`, which the refusal must not touch.
#: `?` opens an explicit key only when a space follows it and it OPENS the
#: entry, so a quoted key, a `?` inside a key and a `?` the key starts with
#: and a letter follows all read as the text they are. The block twin of each
#: reads the same, and that is what each pins.
A_QUESTION_MARK_THAT_IS_NOT_AN_EXPLICIT_KEY = [
    pytest.param('k: {"? a": b}', 'k:\n  "? a": b\n', {"k": {"? a": "b"}},
                 id="double-quoted"),
    pytest.param("k: {'? a': b}", "k:\n  '? a': b\n", {"k": {"? a": "b"}},
                 id="single-quoted"),
    pytest.param("k: {?a: b}", "k:\n  ?a: b\n", {"k": {"?a": "b"}},
                 id="no-space-after-it"),
    pytest.param("k: {a?: b}", "k:\n  a?: b\n", {"k": {"a?": "b"}},
                 id="inside-the-key"),
    pytest.param("k: {a: b?}", "k:\n  a: b?\n", {"k": {"a": "b?"}},
                 id="at-the-end-of-a-value"),
]


@pytest.mark.parametrize("flow, block, expected",
                         A_QUESTION_MARK_THAT_IS_NOT_AN_EXPLICIT_KEY)
def test_a_question_mark_that_is_not_an_explicit_key_is_read(flow, block,
                                                             expected):
    assert parse_yaml(flow + "\n") == expected
    assert parse_yaml(block) == expected, "its block twin reads the same"


def test_a_question_mark_in_a_value_is_not_a_key_in_a_flow_or_a_block():
    """`? ` where a VALUE stands is not the explicit-key indicator the block
    reader refuses, which looks at the start of a line. The flow reader reads
    it as its block twin does; PyYAML refuses both, and that is a different
    change, the same one for the two forms if it is made."""
    assert parse_yaml("k: {x: ? a}\n") == parse_yaml("k:\n  x: ? a\n")


#: The issue's rows 3 to 5 and the other places an empty value can stand.
#: Each is the flow text, its block twin where one exists, and the read both
#: must give. The text is raw.
EMPTY_VALUE_IN_A_FLOW_MAPPING = [
    pytest.param("k: {a: }", "k:\n  a:\n", {"k": {"a": None}},
                 id="the-issue-row-colon-space"),
    pytest.param("k: {a:}", "k:\n  a:\n", {"k": {"a": None}},
                 id="the-issue-row-colon-only"),
    pytest.param("k: {a: , b: 1}", "k:\n  a:\n  b: 1\n",
                 {"k": {"a": None, "b": 1}}, id="before-another-entry"),
    pytest.param("k: {b: 1, a: }", "k:\n  b: 1\n  a:\n",
                 {"k": {"b": 1, "a": None}}, id="after-another-entry"),
    pytest.param("k: {a: , }", "k:\n  a:\n", {"k": {"a": None}},
                 id="before-a-trailing-comma"),
    pytest.param("k: { a : }", "k:\n  a:\n", {"k": {"a": None}},
                 id="with-the-spaces-around-it"),
    pytest.param("k: {a:   }", "k:\n  a:   \n", {"k": {"a": None}},
                 id="with-more-than-one-space"),
    pytest.param('k: {"a": }', 'k:\n  "a":\n', {"k": {"a": None}},
                 id="a-double-quoted-key"),
    pytest.param("k: {'a':}", "k:\n  'a':\n", {"k": {"a": None}},
                 id="a-single-quoted-key"),
    pytest.param("k: {a: , b: , c: }", "k:\n  a:\n  b:\n  c:\n",
                 {"k": {"a": None, "b": None, "c": None}},
                 id="every-entry"),
    pytest.param("k: {a: {b: }}", "k:\n  a:\n    b:\n",
                 {"k": {"a": {"b": None}}}, id="nested-in-a-flow-mapping"),
    pytest.param("k: {a: [x, ], b: }", "k:\n  a:\n    - x\n  b:\n",
                 {"k": {"a": ["x"], "b": None}},
                 id="after-a-flow-sequence"),
    pytest.param("k: [{a: }]", "k:\n  - a:\n", {"k": [{"a": None}]},
                 id="nested-in-a-flow-sequence"),
    pytest.param("- {a: }", "- a:\n", [{"a": None}],
                 id="a-block-sequence-item"),
    pytest.param("- k: {a: }", "- k:\n    a:\n", [{"k": {"a": None}}],
                 id="a-block-sequence-mapping"),
]


@pytest.mark.parametrize("flow, block, expected",
                         EMPTY_VALUE_IN_A_FLOW_MAPPING)
def test_an_empty_value_in_a_flow_mapping_is_null(flow, block, expected):
    assert parse_yaml(flow + "\n") == expected
    assert parse_yaml(block) == expected, "its block twin reads the same"


@pytest.mark.parametrize("flow, block", [
    pytest.param("k: {a: ~}", "k:\n  a: ~\n", id="tilde"),
    pytest.param("k: {a: null}", "k:\n  a: null\n", id="null"),
    pytest.param("k: {a: Null}", "k:\n  a: Null\n", id="Null"),
    pytest.param("k: {a: NULL}", "k:\n  a: NULL\n", id="NULL"),
])
def test_an_empty_value_reads_as_the_spelled_nulls_do(flow, block):
    """What `a:` reads in a block and `a: ~` and `a: null` read in either:
    one value, so the empty one is not a fourth kind of absence."""
    expected = {"k": {"a": None}}
    assert parse_yaml(flow + "\n") == expected
    assert parse_yaml(block) == expected
    assert parse_yaml("k: {a: }\n") == expected


@pytest.mark.parametrize("flow, block", [
    pytest.param('k: {a: ""}', 'k:\n  a: ""\n', id="double-quoted"),
    pytest.param("k: {a: ''}", "k:\n  a: ''\n", id="single-quoted"),
])
def test_a_quoted_empty_value_is_the_empty_string_and_not_null(flow, block):
    """The distinction the fix must keep: an empty value is null, and a value
    someone wrote as two quotes is the empty string, in a flow and a block."""
    assert parse_yaml(flow + "\n") == {"k": {"a": ""}}
    assert parse_yaml(block) == {"k": {"a": ""}}


def test_an_empty_value_in_a_file_is_read_as_null(tmp_path):
    """The shape a person leaves behind: `naming: {form: }`, half filled in.
    Read from a file the way every caller reads it; bytes, so LF everywhere."""
    path = tmp_path / "project.yaml"
    path.write_bytes(b"naming: {form: }\nid: atlas\n")
    assert load_yaml(path) == {"naming": {"form": None}, "id": "atlas"}


def test_a_flow_collection_that_opens_is_still_a_flow_collection():
    """The test is whether the text OPENS a flow collection, and one that does
    still has to close: the fix must not make `[` or `{` optional. A nested
    collection that never closes is refused as it was."""
    assert parse_yaml("k: {a: [1, 2], b: {c: 3}, d: [], e: {}}\n") == {
        "k": {"a": [1, 2], "b": {"c": 3}, "d": [], "e": {}}}
    for text in ("k: {a: [b}\n", "k: {a: {b}\n", "k: [a, [b]\n"):
        with pytest.raises(YamlError, match="not a flow collection"):
            parse_yaml(text)
