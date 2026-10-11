# SPDX-License-Identifier: Apache-2.0
"""Where a quoted scalar starts and where it ends (#249, #250).

A QUOTE OPENS A QUOTED SCALAR ONLY WHERE A SCALAR BEGINS: at the start of a
value, an item, a key or a flow entry, after optional spaces. In the middle
of a plain scalar (`it's`, `a"b`) it is an ordinary character. The reader's
three scanners -- `_strip_comment`, `_split_key` and `_split_flow` -- each
toggled a quote at ANY `"` or `'`, so `k: [it's, a]` read as the one item
`it's, a` where its block twin reads two, and `k: it's fine # note` kept the
comment in the value (#249). They now ask one definition, `_unquoted`.

A QUOTED SCALAR ENDS AT ITS CLOSING QUOTE, and nothing but a comment or the
structure that ends the node may follow it. `_scalar` took any text that
starts and ends with a quote for a quoted scalar and anything else for plain
text, so an unclosed `"abc` read as `"abc`, `- "a\\"` as `a\\`, and
`"a" b "c"` as `a" b "c` (#250). Each is now a `YamlError` by name, which
`load_yaml` turns into `REFUSED yaml-unparsable`.

Every expected read below is PyYAML 6.0.3's, and every refused document is
one PyYAML refuses, except `k: "a"#c`: PyYAML reads `a`, but YAML requires a
space before a comment, and the subset refuses rather than guess. PyYAML is
not imported here; nothing in this suite depends on it.

NO NETWORK AND NO GITHUB: strings, one temporary file and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (Refusal, YamlError, double_quoted,  # noqa: E402
                        load_yaml, parse_yaml)

#: #249's table, and the neighbours that share its cause. The text is raw:
#: every backslash here is a backslash in the YAML.
QUOTE_IN_A_PLAIN_SCALAR = [
    pytest.param("k: [it's, a]", {"k": ["it's", "a"]},
                 id="flow-sequence-two-items-read-as-one"),
    pytest.param("k: {a: it's, b: 1}", {"k": {"a": "it's", "b": 1}},
                 id="flow-mapping-two-entries-read-as-one"),
    pytest.param("k: it's fine # note", {"k": "it's fine"},
                 id="comment-kept-in-the-value"),
    pytest.param("k: [it's, a] # note", {"k": ["it's", "a"]},
                 id="flow-then-comment-refused"),
    pytest.param("it's: 1", {"it's": 1}, id="key-refused"),
    pytest.param('k: [a"b, c]', {"k": ['a"b', "c"]},
                 id="double-quote-mid-item"),
    pytest.param(r'k: [a"b\", c]', {"k": ['a"b\\"', "c"]},
                 id="double-quote-and-backslash-mid-item"),
    pytest.param("- it's # c", ["it's"], id="sequence-item-then-comment"),
    pytest.param("k: {it's: a, b: c}", {"k": {"it's": "a", "b": "c"}},
                 id="flow-mapping-key"),
    pytest.param("k: x'y'", {"k": "x'y'"}, id="plain-scalar-ending-in-quotes"),
    pytest.param("k: [-'a', b]", {"k": ["-'a'", "b"]},
                 id="a-dash-with-no-space-is-plain"),
    # On a block line a `,` or `[` in the middle of a plain scalar is a
    # character of it, not structure, so the quote after it opens nothing.
    pytest.param("k: a, 'b # c'", {"k": "a, 'b"},
                 id="block-comma-is-not-a-flow-separator"),
    pytest.param("k: a[b, 'c # d']", {"k": "a[b, 'c"},
                 id="block-bracket-mid-scalar-opens-no-flow"),
]


@pytest.mark.parametrize("text, expected", QUOTE_IN_A_PLAIN_SCALAR)
def test_a_quote_in_the_middle_of_a_plain_scalar_is_a_character(text,
                                                                 expected):
    assert parse_yaml(text + "\n") == expected


def test_a_flow_sequence_reads_as_its_block_twin():
    """#249's own comparison: the same two items, flow and block."""
    assert parse_yaml("k:\n  - it's\n  - a\n") == {"k": ["it's", "a"]}
    assert parse_yaml("k: [it's, a]\n") == parse_yaml("k:\n  - it's\n  - a\n")


#: #250's table, then the same defect in a key, a flow mapping and a
#: comment written with no space before it. The text is raw.
NOT_ONE_WHOLE_QUOTED_SCALAR = [
    pytest.param('created_by: "Brett Heap', "without a closing quote",
                 id="closing-quote-missing"),
    pytest.param('k: "abc', "without a closing quote", id="double-unclosed"),
    pytest.param('k:\n  - "a\\"', "without a closing quote",
                 id="only-closing-quote-escaped"),
    pytest.param(r'k: "a\", b', "without a closing quote",
                 id="escaped-quote-then-more"),
    pytest.param('k: "a" b "c"', "with text after its closing quote",
                 id="text-after-the-closing-quote"),
    pytest.param('k: "a"b', "with text after its closing quote",
                 id="text-right-after-the-closing-quote"),
    pytest.param("k: 'abc", "without a closing quote", id="single-unclosed"),
    pytest.param("k: 'a' b 'c'", "with text after its closing quote",
                 id="single-text-after-the-closing-quote"),
    pytest.param(r'k: ["a\", b]', "without a closing quote",
                 id="flow-escaped-quote"),
    pytest.param('k: ["a, b]', "without a closing quote",
                 id="flow-unclosed"),
    pytest.param("k: '''", "without a closing quote",
                 id="single-doubled-quote-then-nothing"),
    pytest.param('"a" b: 1', "with text after its closing quote",
                 id="key-text-after-the-closing-quote"),
    pytest.param(r'- "a\": b', "without a closing quote",
                 id="sequence-item-escaped-quote"),
    pytest.param('k: {a: "x" y, b: 1}', "with text after its closing quote",
                 id="flow-mapping-value"),
    pytest.param('k: "a"#c', "with text after its closing quote",
                 id="comment-with-no-space-before-it"),
]


@pytest.mark.parametrize("text, message", NOT_ONE_WHOLE_QUOTED_SCALAR)
def test_a_scalar_that_begins_with_a_quote_is_one_whole_quoted_scalar(
        text, message):
    with pytest.raises(YamlError, match=f"quoted scalar {message}"):
        parse_yaml(text + "\n")


def test_everything_after_an_unclosed_quote_is_inside_it():
    """A `#` or `,` after a quote that never closes is text of the scalar,
    not a comment or a separator, so the refusal quotes all of it."""
    with pytest.raises(YamlError, match=r"""closing quote: '"a # b, c'$"""):
        parse_yaml('k: "a # b, c\n')
    with pytest.raises(YamlError, match=r"""closing quote: '"a, b # c'$"""):
        parse_yaml('k: ["a, b # c]\n')


#: What must NOT change: whole quoted scalars, the `''` escape, a quote of
#: one kind inside the other, comments after a closing quote, flow items
#: with spaces around them.
STILL_READ = [
    pytest.param('k: "a" # c', {"k": "a"}, id="double-then-comment"),
    pytest.param("k: 'a, b # c' # d", {"k": "a, b # c"},
                 id="hash-and-comma-inside-a-quoted-value"),
    pytest.param("k: 'it''s'", {"k": "it's"}, id="single-doubled-quote"),
    pytest.param("k: ''''", {"k": "'"}, id="single-only-a-quote"),
    pytest.param(r'k: "\""', {"k": '"'}, id="double-only-a-quote"),
    pytest.param(r'k: "a\\"', {"k": "a\\"}, id="double-escaped-backslash"),
    pytest.param("k: \"it's\"", {"k": "it's"}, id="single-inside-double"),
    pytest.param("k: 'say \"hi\"'", {"k": 'say "hi"'},
                 id="double-inside-single"),
    pytest.param("k: ['it''s, a', b]", {"k": ["it's, a", "b"]},
                 id="flow-single-doubled-quote-and-comma"),
    pytest.param("k: [ 'a' , \"b\" ]", {"k": ["a", "b"]},
                 id="flow-items-with-spaces"),
    pytest.param("k: [\"a\", b] # c", {"k": ["a", "b"]},
                 id="flow-then-comment"),
    pytest.param("k: {\"a\": 'b', 'c': \"d\"}", {"k": {"a": "b", "c": "d"}},
                 id="flow-mapping-quoted-keys-and-values"),
    pytest.param("- \"a\" # c", ["a"], id="sequence-item-then-comment"),
    pytest.param("- - 'a # b'", [["a # b"]], id="nested-sequence-item"),
    pytest.param('"a b": c', {"a b": "c"}, id="double-quoted-key"),
    pytest.param("'a': 1", {"a": 1}, id="single-quoted-key"),
]


@pytest.mark.parametrize("text, expected", STILL_READ)
def test_a_whole_quoted_scalar_still_reads(text, expected):
    assert parse_yaml(text + "\n") == expected


@pytest.mark.parametrize("value", [
    'a"b', "x\\", "it's, a", '" # ', "\\\"", "]", "a: b",
])
def test_the_writer_still_round_trips_beside_a_plain_quote(value):
    """`double_quoted` is the subset's writer. Its output must read back
    wherever a scalar begins, including after a plain item that holds a
    quote of its own, in a flow and in a block."""
    spelled = double_quoted(value)
    assert parse_yaml(f"k: [it's, {spelled}]\n") == {"k": ["it's", value]}
    assert parse_yaml(f"k: {{it's: {spelled}}}\n") == {"k": {"it's": value}}
    assert parse_yaml(f"k:\n  - it's\n  - {spelled}  # c\n") == {
        "k": ["it's", value]}


def test_an_unclosed_quote_in_a_file_is_a_refusal_naming_it(tmp_path):
    """#250's first row, read from a file the way every caller reads one:
    a `created_by` whose closing quote was lost in a hand edit. Bytes, so
    the file is LF on every platform."""
    path = tmp_path / "family.yaml"
    path.write_bytes(b'created_by: "Brett Heap\n')
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    assert str(path) in caught.value.detail
    assert "quoted scalar without a closing quote" in caught.value.detail
    assert "Brett Heap" in caught.value.detail
