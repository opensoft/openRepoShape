# SPDX-License-Identifier: Apache-2.0
"""A block scalar's key reads as the same key does over a plain value.

`_tokenise` keeps a block scalar (`key: |` or `key: >`) as ONE record. That
record used to carry its key and its body as one string, a NUL-delimited
marker + key + NUL + body, which `_parse_mapping` split again at the NULs
(#248). A key holding a NUL added a field: it was cut short at the NUL, and
the rest of it was read into the body. YAML allows a NUL in a key, spelled
`\\x00`, `\\u0000` or `\\U00000000` inside double quotes, and since #199 the
reader resolves those, so `"a\\x00b": |` read as the key `a` with the body
`b<NUL>text`. A raw NUL in a key, which YAML forbids and this reader takes,
was misread the same way before #199. And the marker was only a prefix of
the text: an ordinary line whose text began with it, a raw NUL first, was
read as a block scalar it never was. Read as a key and a value nobody wrote,
or, as a sequence item with one NUL too few, a bare `ValueError` out of
`parse_yaml` that `load_yaml` let through as a traceback.

The record now carries the pair as two strings. Nothing a key holds can be
mistaken for structure, so the reads below are whatever the same key reads
as over a plain value, and for every escaped spelling that is what PyYAML
6.0.3 reads too (it was asked once, as an oracle; nothing here imports it).

No writer in this repository emits a block scalar with a key built from
data, or a line that opens with a raw NUL: the plan writer writes no block
scalar, and every key it writes is a literal. A file a person edits, or
another tool writes, can hold one, and every YAML file every tool reads goes
through this reader.

NO NETWORK AND NO GITHUB: strings, a few temporary files and an import.
"""

from __future__ import annotations

import sys

import pytest

from conftest import REPO

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import (  # noqa: E402
    YamlError, double_quoted, load_yaml, parse_yaml)

NUL = "\x00"

#: The issue's four rows, each with the read it should have. The first is
#: the report. The second is not one: `\^@` is no escape this reader (or
#: YAML) resolves, so it keeps its backslash and the key is that text -- it
#: is pinned as the issue spelled it, and reads the same before and after.
#: The third is the first row's key over a plain value, which always read
#: right. The fourth is a RAW NUL, read as the reader reads a raw NUL in any
#: key (see `PLAIN_TWIN_SPELLINGS`).
ISSUE_ROWS = [
    pytest.param('"a\\x00b": |\n  text\n', {"a\x00b": "text\n"},
                 id="escaped-nul-literal"),
    pytest.param('"a\\^@b": >\n  text\n', {"a\\^@b": "text\n"},
                 id="caret-is-no-escape-folded"),
    pytest.param('"a\\x00b": text\n', {"a\x00b": "text"},
                 id="the-same-key-over-a-plain-value"),
    pytest.param(f"a{NUL}b: |\n  text\n", {"a\x00b": "text\n"},
                 id="raw-nul-literal"),
]


@pytest.mark.parametrize("text, expected", ISSUE_ROWS)
def test_the_issue_rows_read_the_key_whole(text, expected):
    assert parse_yaml(text) == expected


#: An escaped NUL in each spelling, at each place in the key, under each
#: header. Every expected read is PyYAML 6.0.3's read of the same text.
ESCAPED_NUL_KEYS = [
    pytest.param('"a\\u0000b": |\n  text\n', {"a\x00b": "text\n"},
                 id="u0000"),
    pytest.param('"a\\U00000000b": |\n  text\n', {"a\x00b": "text\n"},
                 id="U00000000"),
    pytest.param('"a\\x00b": >\n  one\n  two\n', {"a\x00b": "one two\n"},
                 id="folded"),
    pytest.param('"a\\x00b\\x00c": |-\n  text\n', {"a\x00b\x00c": "text"},
                 id="two-nuls-strip-chomping"),
    pytest.param('"\\x00": |\n  text\n', {"\x00": "text\n"},
                 id="the-key-is-a-nul"),
    pytest.param('"a\\x00": |\n  text\n', {"a\x00": "text\n"},
                 id="the-key-ends-in-a-nul"),
    pytest.param('"\\x00BLOCK\\x00k": |\n  text\n',
                 {"\x00BLOCK\x00k": "text\n"},
                 id="the-key-spells-the-old-marker"),
]


@pytest.mark.parametrize("text, expected", ESCAPED_NUL_KEYS)
def test_an_escaped_nul_in_a_block_key_is_part_of_the_key(text, expected):
    assert parse_yaml(text) == expected


#: Keys spelled every way that puts a NUL, or the old marker, into them:
#: escaped, raw, raw inside either quote, and the marker inside double
#: quotes. A RAW NUL is not YAML (PyYAML refuses one anywhere in a file),
#: but this reader takes it over a plain value, and a block scalar's key is
#: read by the same `_split_key`. If a later change refuses a raw NUL, it
#: refuses it over a plain value as well, and these rows become refusals
#: together with their plain twins: that is the change to make here, not a
#: regression.
PLAIN_TWIN_SPELLINGS = [
    pytest.param('"a\\x00b"', id="escaped"),
    pytest.param(f"a{NUL}b", id="raw-plain"),
    pytest.param(f"'a{NUL}b'", id="raw-single-quoted"),
    pytest.param(f'"a{NUL}b"', id="raw-double-quoted"),
    pytest.param(f'"{NUL}BLOCK{NUL}k{NUL}v"', id="raw-marker-double-quoted"),
    pytest.param("plain", id="no-nul-at-all"),
]


@pytest.mark.parametrize("header", ["|", ">", "|-", ">+", "|+", ">-"])
@pytest.mark.parametrize("spelled", PLAIN_TWIN_SPELLINGS)
def test_a_block_key_reads_as_its_plain_twin(spelled, header):
    (key,) = parse_yaml(f"{spelled}: text\n")
    assert parse_yaml(f"{spelled}: {header}\n  text\n") == {
        key: "text" if header.endswith("-") else "text\n"}


@pytest.mark.parametrize("header", ["|2", ">-2", "|2+"])
@pytest.mark.parametrize("spelled", PLAIN_TWIN_SPELLINGS)
def test_a_block_key_over_an_indentation_digit_is_refused_by_its_line(
        spelled, header):
    """`|2` was one of the headers above, read with its digit ignored, which
    over `  text` is what YAML reads. The digit is refused now (#1004),
    whatever the key, by the header's line."""
    with pytest.raises(YamlError) as caught:
        parse_yaml(f"{spelled}: {header}\n  text\n")
    assert str(caught.value) == (
        "line 1: a block scalar's indentation indicator is not supported: "
        f"{header!r}")


#: Above the first 0x300 code points, every one of which is checked: a
#: separator, zero-width and bidirectional controls, the BOM, a lone
#: surrogate, private use, a noncharacter, an astral letter and the last
#: code point.
HIGH_CODE_POINTS = [0x061C, 0x2028, 0x200B, 0x202E, 0xFEFF, 0xDCE9, 0xE000,
                    0xFFFF, 0x1F600, 0x10FFFF]


def test_every_character_in_a_written_block_key_reads_back():
    """The writer's half and the reader's half of a block key: whatever
    `double_quoted` makes of a key, the reader takes back as that key over
    a `|` and a `>`. Listed rather than parametrized, so one failure names
    every character it failed for."""
    misread = []
    for code in [*range(0x300), *HIGH_CODE_POINTS]:
        key = f"a{chr(code)}b"
        for header in ("|", ">"):
            text = f"{double_quoted(key)}: {header}\n  text\n"
            if parse_yaml(text) != {key: "text\n"}:
                misread.append((hex(code), header, parse_yaml(text)))
    assert misread == []


def test_a_nul_keyed_block_scalar_keeps_its_place():
    """As the first key of a sequence item and as a nested key, with a
    sibling after it and a key after the nesting: the record is one record,
    so nothing shifts. Each read is PyYAML 6.0.3's."""
    assert parse_yaml('- "a\\x00b": |\n    text\n  c: 1\n- d\n') == [
        {"a\x00b": "text\n", "c": 1}, "d"]
    assert parse_yaml(
        'outer:\n  "a\\x00b": |\n    text\n  c: 1\nd: 2\n') == {
        "outer": {"a\x00b": "text\n", "c": 1}, "d": 2}
    assert parse_yaml('"\\x00": |\n  one\n"\\x00\\x00": >-\n  two\n') == {
        "\x00": "one\n", "\x00\x00": "two"}


#: The old marker, spelled out: a line that is NOT a block scalar but whose
#: text begins with these characters was read as one. Each row is now read
#: as the same line is read with any other text in its place -- a key, a
#: sequence item, and a bare line under a key, which this reader refuses
#: (`k:\n  xyz` is refused the same way).
MARKER = f"{NUL}BLOCK{NUL}"
MARKER_PREFIXED_LINES = [
    pytest.param(f"{MARKER}k{NUL}v: 1\n", {f"{MARKER}k{NUL}v": 1},
                 id="a-key-read-as-k-with-value-v"),
    pytest.param(f"- {MARKER}x{NUL}y\n", [f"{MARKER}x{NUL}y"],
                 id="a-sequence-item-read-as-a-mapping"),
    pytest.param(f"- {MARKER}x\n", [f"{MARKER}x"],
                 id="a-sequence-item-that-raised-valueerror"),
]


@pytest.mark.parametrize("text, expected", MARKER_PREFIXED_LINES)
def test_a_line_that_begins_with_the_old_marker_is_an_ordinary_line(
        text, expected):
    assert parse_yaml(text) == expected


def test_a_bare_line_that_begins_with_the_old_marker_is_refused_as_any():
    """It was read as the mapping `{'x': 'y'}`. Under a key, a line with no
    `key:` in it is refused whatever it says, and so is this one."""
    with pytest.raises(YamlError, match="expected `key: value`"):
        parse_yaml("k:\n  xyz\n")
    with pytest.raises(YamlError, match="expected `key: value`"):
        parse_yaml(f"k:\n  {MARKER}x{NUL}y\n")


def test_files_read_through_load_yaml_take_the_key_whole(tmp_path):
    """The way every caller reads: from a file, as bytes so it is LF on
    every platform. The second file was a bare `ValueError` out of
    `load_yaml`, a traceback where a caller expects data or a `Refusal`."""
    escaped = tmp_path / "escaped.yaml"
    escaped.write_bytes(b'"a\\x00b": |\n  text\nc: 1\n')
    assert load_yaml(escaped) == {"a\x00b": "text\n", "c": 1}
    marker = tmp_path / "marker.yaml"
    marker.write_bytes(b"- \x00BLOCK\x00x\n")
    assert load_yaml(marker) == ["\x00BLOCK\x00x"]


@pytest.mark.parametrize("text, expected", [
    pytest.param(f"k: |\n  a{NUL}b\n  c\n", {"k": f"a{NUL}b\nc\n"},
                 id="a-raw-nul-in-the-body"),
    pytest.param("k: |\n  a\\x00b\n", {"k": "a\\x00b\n"},
                 id="an-escape-in-the-body-is-text"),
    pytest.param("k: |\n  text\nj: >-\n  x\n  y\n",
                 {"k": "text\n", "j": "x y"},
                 id="no-nul-anywhere"),
])
def test_a_block_body_is_unchanged(text, expected):
    """The BODY was never split (the old split stopped at three NULs), and
    a block scalar has no escapes, so `\\x00` in one is four characters."""
    assert parse_yaml(text) == expected
