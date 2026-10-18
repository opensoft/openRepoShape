# SPDX-License-Identifier: Apache-2.0
"""An indicator opens no plain scalar, and no flow entry is empty (#392, #393).

YAML lets no plain scalar open with an indicator: `]`, `}`, `,`, `@`, a
backtick, `%`, a `#`, and `?`, `:` or `-` where they are indicators. The
reader's one test of a scalar's first character was `&*!`, so the rest was
read as text where PyYAML refuses the document:

- #393, a BLOCK value or item: `k: ]`, `k: }`, `- ]`, `k: ,`, `k: @a`,
  ``k: `a` ``, `k: %a`, and a lone `k: ?`, `k: -` or `k: :`. `_scalar` refuses
  each, and `_parse_mapping` the lone `-`, which `[-]` reads as text.
- #392, a FLOW entry, an item or a mapping entry's key: `k: [:]`, `k: [: a]`,
  `k: {:":}`, `k: {: a}`, `k: [#a]`, `k: {#a: 1}`, `k: [- a]` and
  `k: [? a]`, refused by `_refuse_entry_indicator`.
- #392, an EMPTY flow entry: `k: [,a]`, `k: [a,,b]`, `k: [,]`, `k: [a,,]`,
  `k: {,}` and `k: {a: 1,,b: 2}` read as if the comma were not there.
  `_split_flow` refuses each, and keeps the one trailing comma YAML allows.
- #392, a SINGLE PAIR in a flow sequence: `k: [a: b]` read the string
  `'a: b'` where YAML reads `[{'a': 'b'}]`. It is refused, not read as YAML
  reads it, because no file this reader serves can hold one (`_flow_value`
  says why).

Each refusal is a `YamlError`, so `load_yaml` turns it into `REFUSED
yaml-unparsable` naming the file, and a project's own `validate-manifest.py`
exits 2 on it. The same character later in a scalar, every quoted scalar, and
the indicators PyYAML reads as text (`[-]`, `[-a]`, `{a: -}`, `k: -a`,
`k: ?a`, `k: :a`) read as before.

PyYAML is the ORACLE ONLY, never a dependency: where it is installed, every
row is compared with it and a seeded fuzz checks the two readers agree; where
it is not, those comparisons are skipped and this reader's answers are still
asserted. NOT IN THESE ISSUES, and not asserted here: `?`, `:` or `-` with a
space and more text as a VALUE (`k: - a`, `{x: ? a}`), which PyYAML refuses
and `tests/test_yaml_flow_mappings.py` pins as each form's twin; a flow `?a`,
which #252 keeps as text; `|` and `>`, block scalar headers; and a block KEY.
The empty key of `- :` was one, left out of the fuzz while it read
`[{'': None}]`; #715 refuses it, as PyYAML does, so the fuzz draws it again
(`tests/test_yaml_reader_spaces.py` holds its rows).

NO NETWORK AND NO GITHUB: strings, a temporary file, one scaffolded project
over local bare remotes, and an import.
"""

from __future__ import annotations

import random
import sys

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal, YamlError, load_yaml, parse_yaml  # noqa: E402

try:
    import yaml as pyyaml  # the oracle only: nothing shipped imports it
except ImportError:  # pragma: no cover - depends on the machine
    pyyaml = None

NEEDS_PYYAML = pytest.mark.skipif(
    pyyaml is None,
    reason="PyYAML is not installed here, so the comparison with a stock "
           "reader is skipped; this reader's own answers are asserted by the "
           "tests beside this one")

#: The phrases each kind of refusal is made with.
OPENS = "a plain scalar cannot open with"
EMPTY = ("a flow collection holds an empty entry, which YAML allows only "
         "after its last comma")
PAIR = "a single-pair mapping in a flow sequence is not supported"
EXPLICIT_KEY = "explicit keys are not supported"


def ours(text: str):
    """This reader's answer: the value, or the `YamlError` it raised."""
    try:
        return parse_yaml(text + "\n")
    except YamlError as exc:
        return exc


def stock(text: str):
    """PyYAML's answer: the value, or the `YAMLError` it raised."""
    try:
        return pyyaml.safe_load(text + "\n")
    except pyyaml.YAMLError as exc:
        return exc


def refused(answer) -> bool:
    return isinstance(answer, Exception)


# --- #393: a block value or item -------------------------------------------

#: #393's own rows, raw, each with the phrase it is refused with.
BLOCK_ROWS = [
    pytest.param("k: ]", OPENS, id="closer-as-a-value"),
    pytest.param("k: }", OPENS, id="brace-closer-as-a-value"),
    pytest.param("- ]", OPENS, id="closer-as-an-item"),
    pytest.param("- }", OPENS, id="brace-closer-as-an-item"),
    pytest.param("k:\n  j: ]", OPENS, id="closer-as-a-nested-value"),
    pytest.param("k: ]x", OPENS, id="closer-opening-a-word"),
    pytest.param("k: ] a", OPENS, id="closer-and-a-space"),
    pytest.param("k: ,", OPENS, id="comma"),
    pytest.param("k: @a", OPENS, id="at-sign"),
    pytest.param("k: `a`", OPENS, id="backtick"),
    pytest.param("k: %a", OPENS, id="percent"),
    pytest.param("k: ?", EXPLICIT_KEY, id="lone-question-mark"),
    pytest.param("k: -", OPENS, id="lone-dash"),
    pytest.param("k: :", OPENS, id="lone-colon"),
    # The same, where else a block plain scalar stands.
    pytest.param("- ,a", OPENS, id="comma-as-an-item"),
    pytest.param("- @a", OPENS, id="at-sign-as-an-item"),
    pytest.param("- %a", OPENS, id="percent-as-an-item"),
    pytest.param("k:\n  - `a`", OPENS, id="backtick-as-a-nested-item"),
    pytest.param("- k: ]", OPENS, id="closer-in-a-sequence-of-mappings"),
    pytest.param("- k: -", OPENS, id="lone-dash-in-a-sequence-of-mappings"),
    pytest.param("k: } # a comment", OPENS, id="closer-before-a-comment"),
]


@pytest.mark.parametrize("text, phrase", BLOCK_ROWS)
def test_a_block_scalar_opening_with_an_indicator_is_refused(text, phrase):
    with pytest.raises(YamlError, match=phrase):
        parse_yaml(text + "\n")


@NEEDS_PYYAML
@pytest.mark.parametrize("text, phrase", BLOCK_ROWS)
def test_pyyaml_refuses_each_block_row_too(text, phrase):
    assert refused(stock(text)), f"PyYAML reads {text!r} as {stock(text)!r}"


#: A lone `?` as a block ITEM: PyYAML reads it as an explicit key with no key
#: and no value, `[{None: None}]`, a construct this reader refuses by name.
def test_a_lone_question_mark_item_is_refused_as_an_explicit_key():
    with pytest.raises(YamlError, match=EXPLICIT_KEY):
        parse_yaml("- ?\n")


#: What must NOT change: the character later in the scalar, a quoted scalar,
#: and `-`, `?` or `:` with a character after it, each as PyYAML reads it.
BLOCK_STILL_READ = [
    pytest.param("k: a]", {"k": "a]"}, id="closer-after-a-letter"),
    pytest.param("k: x}", {"k": "x}"}, id="brace-closer-after-a-letter"),
    pytest.param("- see [1]", ["see [1]"], id="bracket-pair-in-an-item"),
    pytest.param('k: "]"', {"k": "]"}, id="double-quoted-closer"),
    pytest.param("k: ']'", {"k": "]"}, id="single-quoted-closer"),
    pytest.param("k: a[0]", {"k": "a[0]"}, id="index"),
    pytest.param("k: a, b", {"k": "a, b"}, id="comma-inside"),
    pytest.param("k: a@b", {"k": "a@b"}, id="at-sign-inside"),
    pytest.param("k: 50%", {"k": "50%"}, id="percent-at-the-end"),
    pytest.param("k: a`b`", {"k": "a`b`"}, id="backtick-inside"),
    pytest.param("k: -a", {"k": "-a"}, id="dash-and-a-letter"),
    pytest.param("k: -1", {"k": -1}, id="negative-number"),
    pytest.param("k: ?a", {"k": "?a"}, id="question-mark-and-a-letter"),
    pytest.param("k: :a", {"k": ":a"}, id="colon-and-a-letter"),
    pytest.param("k: a?", {"k": "a?"}, id="question-mark-at-the-end"),
    pytest.param('k: "@a"', {"k": "@a"}, id="quoted-at-sign"),
    pytest.param("k: '%a'", {"k": "%a"}, id="quoted-percent"),
    pytest.param('k: "-"', {"k": "-"}, id="quoted-dash"),
]


@pytest.mark.parametrize("text, expected", BLOCK_STILL_READ)
def test_what_does_not_open_with_an_indicator_still_reads(text, expected):
    assert parse_yaml(text + "\n") == expected


@NEEDS_PYYAML
@pytest.mark.parametrize("text, expected", BLOCK_STILL_READ)
def test_pyyaml_reads_each_block_control_the_same(text, expected):
    assert stock(text) == expected


# --- #392: an empty flow entry ----------------------------------------------

#: #392's own six rows, and the same wherever a flow collection stands.
EMPTY_ENTRIES = [
    pytest.param("k: [,a]", id="leading-comma"),
    pytest.param("k: [a,,b]", id="doubled-comma"),
    pytest.param("k: [,]", id="lone-comma"),
    pytest.param("k: [a,,]", id="doubled-trailing-comma"),
    pytest.param("k: {,}", id="lone-comma-in-a-mapping"),
    pytest.param("k: {a: 1,,b: 2}", id="doubled-comma-in-a-mapping"),
    pytest.param("k: [a, , b]", id="doubled-comma-spaced"),
    pytest.param("k: [ , ]", id="lone-comma-spaced"),
    pytest.param("k: {,a: 1}", id="leading-comma-in-a-mapping"),
    pytest.param("k: [[,a]]", id="nested-in-a-sequence"),
    pytest.param("k: {a: [b,,c]}", id="nested-in-a-mapping"),
    pytest.param("- [,a]", id="block-sequence-flow-item"),
]


@pytest.mark.parametrize("text", EMPTY_ENTRIES)
def test_an_empty_flow_entry_is_refused(text):
    with pytest.raises(YamlError, match=EMPTY):
        parse_yaml(text + "\n")


@NEEDS_PYYAML
@pytest.mark.parametrize("text", EMPTY_ENTRIES)
def test_pyyaml_refuses_each_empty_entry_too(text):
    assert refused(stock(text)), f"PyYAML reads {text!r} as {stock(text)!r}"


#: One comma after the last entry is YAML, and so is an empty collection.
TRAILING_COMMAS = [
    pytest.param("k: [a,]", {"k": ["a"]}, id="trailing-comma"),
    pytest.param("k: [a, ]", {"k": ["a"]}, id="trailing-comma-spaced"),
    pytest.param("k: {a: 1,}", {"k": {"a": 1}}, id="trailing-comma-mapping"),
    pytest.param("k: [[a,],]", {"k": [["a"]]}, id="trailing-commas-nested"),
    pytest.param("k: []", {"k": []}, id="empty-sequence"),
    pytest.param("k: [ ]", {"k": []}, id="empty-sequence-spaced"),
    pytest.param("k: {}", {"k": {}}, id="empty-mapping"),
    pytest.param('k: ["", b]', {"k": ["", "b"]}, id="quoted-empty-item"),
]


@pytest.mark.parametrize("text, expected", TRAILING_COMMAS)
def test_one_trailing_comma_and_an_empty_collection_still_read(text,
                                                               expected):
    assert parse_yaml(text + "\n") == expected


@NEEDS_PYYAML
@pytest.mark.parametrize("text, expected", TRAILING_COMMAS)
def test_pyyaml_reads_each_trailing_comma_the_same(text, expected):
    assert stock(text) == expected


# --- #392: a flow entry opening with an indicator ---------------------------

#: #392's own rows, each with the phrase it is refused with, then the same
#: indicators in the other places a flow entry stands.
FLOW_ENTRY_ROWS = [
    pytest.param("k: [:]", OPENS, id="lone-colon-item"),
    pytest.param("k: [: a]", OPENS, id="colon-space-item"),
    pytest.param('k: {:":}', OPENS, id="colon-opening-a-key"),
    pytest.param("k: {: a}", OPENS, id="empty-key"),
    pytest.param("k: [#a]", OPENS, id="hash-item"),
    pytest.param("k: {#a: 1}", OPENS, id="hash-key"),
    pytest.param("k: [- a]", OPENS, id="dash-space-item"),
    pytest.param("k: [? a]", EXPLICIT_KEY, id="question-space-item"),
    pytest.param("k: [:a]", OPENS, id="colon-and-a-letter-item"),
    pytest.param("k: [a, :b]", OPENS, id="colon-item-after-another"),
    pytest.param("k: [a,#b]", OPENS, id="hash-item-after-a-comma"),
    pytest.param("k: {- a: 1}", OPENS, id="dash-space-key"),
    pytest.param("k: [-\ta]", OPENS, id="dash-tab-item"),
    pytest.param("k: [?]", EXPLICIT_KEY, id="lone-question-mark-item"),
    pytest.param("k: {?}", EXPLICIT_KEY, id="lone-question-mark-entry"),
    pytest.param("k: [@a]", OPENS, id="at-sign-item"),
    pytest.param("k: [`a`]", OPENS, id="backtick-item"),
    pytest.param("k: [%a]", OPENS, id="percent-item"),
    pytest.param("k: {@a: 1}", OPENS, id="at-sign-key"),
    pytest.param("k: {%a: 1}", OPENS, id="percent-key"),
    pytest.param("k: {a: @b}", OPENS, id="at-sign-value"),
    pytest.param("k: {a: :}", OPENS, id="lone-colon-value"),
    pytest.param("k: [[: a]]", OPENS, id="nested-in-a-sequence"),
    pytest.param("k: {a: [#b]}", OPENS, id="nested-in-a-mapping"),
    pytest.param("- [- a]", OPENS, id="block-sequence-flow-item"),
]


@pytest.mark.parametrize("text, phrase", FLOW_ENTRY_ROWS)
def test_a_flow_entry_opening_with_an_indicator_is_refused(text, phrase):
    with pytest.raises(YamlError, match=phrase):
        parse_yaml(text + "\n")


@NEEDS_PYYAML
@pytest.mark.parametrize("text, phrase", [
    row for row in FLOW_ENTRY_ROWS
    # PyYAML READS these three as an explicit key, `[{'a': None}]`,
    # `[{None: None}]` and `{None: None}`: a construct this reader refuses by
    # name (#252).
    if row.id not in ("question-space-item", "lone-question-mark-item",
                      "lone-question-mark-entry")])
def test_pyyaml_refuses_each_flow_entry_row_too(text, phrase):
    assert refused(stock(text)), f"PyYAML reads {text!r} as {stock(text)!r}"


#: The issue's controls, which PyYAML reads the same: `-` with nothing or a
#: letter after it, `?` with a letter after it as a key (#252), the indicator
#: inside an entry, and every quoted entry.
FLOW_STILL_READ = [
    pytest.param("k: [-]", {"k": ["-"]}, id="lone-dash-item"),
    pytest.param("k: [-a]", {"k": ["-a"]}, id="dash-and-a-letter-item"),
    pytest.param("k: {-: 1}", {"k": {"-": 1}}, id="lone-dash-key"),
    pytest.param("k: {a: -}", {"k": {"a": "-"}}, id="lone-dash-value"),
    pytest.param("k: [-, a]", {"k": ["-", "a"]}, id="lone-dash-then-another"),
    pytest.param("k: [-1]", {"k": [-1]}, id="negative-number"),
    pytest.param("k: [a:b]", {"k": ["a:b"]}, id="colon-inside"),
    pytest.param("k: [a#b, c-d, e@f]", {"k": ["a#b", "c-d", "e@f"]},
                 id="indicators-inside"),
    pytest.param("k: [{a: b}]", {"k": [{"a": "b"}]},
                 id="a-flow-mapping-item"),
    pytest.param('k: [":", "#a", "- a", "? a", "@a"]',
                 {"k": [":", "#a", "- a", "? a", "@a"]},
                 id="quoted-items"),
    pytest.param("k: {'- a': 1, \"#b\": 2}", {"k": {"- a": 1, "#b": 2}},
                 id="quoted-keys"),
    pytest.param("k: [a] # ]", {"k": ["a"]}, id="a-comment-after-the-flow"),
]


@pytest.mark.parametrize("text, expected", FLOW_STILL_READ)
def test_a_flow_entry_that_opens_with_no_indicator_still_reads(text,
                                                               expected):
    assert parse_yaml(text + "\n") == expected


@NEEDS_PYYAML
@pytest.mark.parametrize("text, expected", FLOW_STILL_READ)
def test_pyyaml_reads_each_flow_control_the_same(text, expected):
    assert stock(text) == expected


def test_a_question_mark_and_a_letter_is_still_the_key_252_kept():
    """#252 kept `{?a: b}` as the key `?a`, and #392 claims neither way; the
    entry check leaves it, and PyYAML's reading differs (`{'a': 'b'}`)."""
    assert parse_yaml("k: {?a: b}\n") == {"k": {"?a": "b"}}


# --- #392: a single pair in a flow sequence ---------------------------------

#: `(text, what PyYAML reads it as)`. YAML reads each item as a one-pair
#: mapping; this reader refuses it (see `_flow_value` for why).
SINGLE_PAIRS = [
    pytest.param("k: [a: b]", {"k": [{"a": "b"}]}, id="the-issue-row"),
    pytest.param("k: [a: b, c]", {"k": [{"a": "b"}, "c"]},
                 id="before-another-item"),
    pytest.param("k: [c, a: b]", {"k": ["c", {"a": "b"}]},
                 id="after-another-item"),
    pytest.param("k: [a:]", {"k": [{"a": None}]}, id="no-value"),
    pytest.param('k: ["a": b]', {"k": [{"a": "b"}]}, id="a-quoted-key"),
    pytest.param("neutral_product_pins: [openGlass: x]",
                 {"neutral_product_pins": [{"openGlass": "x"}]},
                 id="a-pin-list-typo"),
]


@pytest.mark.parametrize("text, pyyaml_reads", SINGLE_PAIRS)
def test_a_single_pair_in_a_flow_sequence_is_refused(text, pyyaml_reads):
    with pytest.raises(YamlError, match=PAIR):
        parse_yaml(text + "\n")


@NEEDS_PYYAML
@pytest.mark.parametrize("text, pyyaml_reads", SINGLE_PAIRS)
def test_pyyaml_reads_each_single_pair_as_a_mapping(text, pyyaml_reads):
    """What is refused: valid YAML, a one-pair mapping, which no file this
    reader serves can hold. A refusal replaces the string `'a: b'`."""
    assert stock(text) == pyyaml_reads


def test_a_bracket_in_a_single_pair_keeps_301s_words():
    """#301 refused `[a: [b]]` first, for its bracket, and still does."""
    with pytest.raises(YamlError,
                       match="a plain scalar in a flow collection holds"):
        parse_yaml("k: [a: [b]]\n")


# --- the words, whole -------------------------------------------------------

@pytest.mark.parametrize("text, words", [
    pytest.param("k: ]", f"{OPENS} `]`, which closes a flow sequence in YAML: "
                 "']'", id="closer"),
    pytest.param("k: }", f"{OPENS} `}}`, which closes a flow mapping in YAML: "
                 "'}'", id="brace-closer"),
    pytest.param("k: ,", f"{OPENS} `,`, which separates flow entries in YAML: "
                 "','", id="comma"),
    pytest.param("k: @a", f"{OPENS} `@`, which is reserved in YAML: '@a'",
                 id="at-sign"),
    pytest.param("k: `a`", f"{OPENS} a backtick, which is reserved in YAML: "
                 "'`a`'", id="backtick"),
    pytest.param("k: %a", f"{OPENS} `%`, which opens a directive in YAML: "
                 "'%a'", id="percent"),
    pytest.param("k: -", f"{OPENS} `-`, which opens a sequence entry in YAML: "
                 "'-'", id="lone-dash"),
    pytest.param("k: :", f"{OPENS} `:`, which opens a value in YAML: ':'",
                 id="lone-colon"),
    pytest.param("k: ?", f"{EXPLICIT_KEY}: '?'", id="lone-question-mark"),
    pytest.param("k: {: a}", f"{OPENS} `:`, which opens a value in YAML: "
                 "': a'", id="empty-key"),
    pytest.param("k: [#a]", f"{OPENS} `#`, which opens a comment in YAML: "
                 "'#a'", id="hash"),
    pytest.param("k: [- a]", f"{OPENS} `-`, which opens a sequence entry in "
                 "YAML: '- a'", id="dash-space"),
    pytest.param("k: [? a]", f"{EXPLICIT_KEY}: '? a'", id="question-space"),
    pytest.param("k: [a,,b]", f"{EMPTY}: 'a,,b'", id="empty-entry"),
    pytest.param("k: [a: b]", f"{PAIR}: 'a: b'", id="single-pair"),
])
def test_each_refusal_names_the_indicator_and_the_text(text, words):
    with pytest.raises(YamlError) as caught:
        parse_yaml(text + "\n")
    assert str(caught.value) == words


@pytest.mark.parametrize("body, words", [
    pytest.param(b"id: atlas\nneutral_product_pins: [,openGlass]\n",
                 f"{EMPTY}: ',openGlass'",
                 id="a-pin-list-with-its-first-name-cut"),
    pytest.param(b"id: atlas\ntracking_branch: ]\n",
                 f"{OPENS} `]`, which closes a flow sequence in YAML: ']'",
                 id="a-stray-closer-left-as-a-value"),
    pytest.param(b"id: atlas\nneutral_product_pins: [openGlass: x]\n",
                 f"{PAIR}: 'openGlass: x'", id="a-pair-typed-into-a-pin-list"),
])
def test_a_file_holding_one_is_yaml_unparsable_naming_the_file(tmp_path, body,
                                                              words):
    """Read the way every caller reads a file. Bytes, so LF everywhere."""
    path = tmp_path / "project.yaml"
    path.write_bytes(body)
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    # An opener's refusal names its line, the second, since #708.
    where = "line 2: " if words.startswith(OPENS) else ""
    assert caught.value.detail == f"{path}: {where}{words}"


@pytest.mark.parametrize("old, new, words", [
    pytest.param(b"neutral_product_pins: []",
                 b"neutral_product_pins: [,openChart]",
                 f"{EMPTY}: ',openChart'", id="empty-entry"),
    pytest.param(b"neutral_product_pins: []",
                 b"neutral_product_pins: [openChart: x]",
                 f"{PAIR}: 'openChart: x'", id="single-pair"),
    pytest.param(b'tracking_branch: "main"', b"tracking_branch: ]",
                 f"{OPENS} `]`, which closes a flow sequence in YAML: ']'",
                 id="stray-closer"),
])
def test_the_projects_own_validator_refuses_it(project, old, new, words):
    """THE COPY A PROJECT CARRIES: `scripts/repo_shape.py` is copied into
    every root and pinned there, so a project's own `validate-manifest.py`
    reads `project.yaml` with this reader. It exits 2 on the refusal, names
    the file, and reads nothing as data: no `manifest ok`, no traceback, and
    the file is as the edit left it."""
    manifest = project / "project.yaml"
    data = manifest.read_bytes()
    assert old in data, f"fixture drift: {old!r} not in project.yaml"
    edited = data.replace(old, new, 1)
    manifest.write_bytes(edited)
    result = run_script(project / "scripts" / "validate-manifest.py",
                        cwd=project)
    assert result.returncode == 2, result.stderr
    # An opener's refusal names its line since #708.
    line = edited[:edited.index(new)].count(b"\n") + 1
    where = f"line {line}: " if words.startswith(OPENS) else ""
    assert (f"REFUSED yaml-unparsable: {manifest}: {where}{words}\n"
            in result.stderr)
    assert "Traceback" not in result.stderr
    assert "manifest ok" not in result.stdout
    assert manifest.read_bytes() == edited


# --- a seeded fuzz, PyYAML the oracle ---------------------------------------

#: The seeds, so a failure here is the same failure on every machine. The
#: first is the writer's. Seeds 1 and 3 are the two on which the table below
#: draws `- :`, the empty block key, which was left out of the fuzz until #715
#: refused it; all three stay in, so that every draw of the table is held in
#: place.
FUZZ_SEED = 392393
FUZZ_SEEDS = [FUZZ_SEED, 1, 3]

#: Plain words that read as text in both readers: no number, bool or null.
WORDS = ["a", "b", "ab", "x"]

#: What a BLOCK value or item may open with, and the tails after it. A tail
#: holds no space, ends in no `:`, and opens with no `&*!` (anchors and
#: tags, refused by design). `:` as an item is the empty block key, `- :`,
#: which #715 refuses.
BLOCK_OPENERS = ["]", "}", ",", "@", "`", "%", "?", ":", "-", "a", "x"]
BLOCK_TAILS = ["", "a", "ab", "]", "}", "[0]", ",b", "@", "%", "`", "?", "-",
               ":b", "#b", "]x", "a]"]

#: What a FLOW item may be: words, quoted words, the empty entry, and every
#: indicator #392 names, alone and before a word. `?a` is left out: #252
#: keeps it as text, and PyYAML reads an explicit key.
FLOW_ITEMS = WORDS + ['"a"', "'b'", "", ":", ":a", ": a", "#a", "- a", "-",
                      "-a", "? a", "?", "@a", "`a", "%a", "a: b", "a:",
                      "a:b", "[a]", "[]", "{a: b}"]
FLOW_KEYS = WORDS + ['"a"', ":a", "#a", "- a", "-", "-a", "@a", "%a", "? a"]
FLOW_VALUES = WORDS + ['"a"', "", "-", "-a", "@a", "`a", "%a", "?", ":",
                       "[a]", "[]"]


def fuzz_documents(seed: int) -> list[str]:
    """A few hundred small documents, drawn from the seed: block values and
    items, flow sequences and flow mappings, with every indicator these
    issues name in every place it can open a scalar or an entry, and the
    empty block key `- :`, which #715 refuses."""
    rng = random.Random(seed)
    docs: list[str] = []
    for _ in range(120):
        value = rng.choice(BLOCK_OPENERS) + rng.choice(BLOCK_TAILS)
        docs.append(rng.choice(["k: {}", "- {}", "k:\n  j: {}",
                                "- k: {}"]).format(value))
    for _ in range(140):
        items = [rng.choice(FLOW_ITEMS) for _ in range(rng.randint(1, 3))]
        body = rng.choice([", ", ","]).join(items) + rng.choice(["", ","])
        docs.append(f"k: [{body}]")
    for _ in range(140):
        entries = [f"{rng.choice(FLOW_KEYS)}: {rng.choice(FLOW_VALUES)}"
                   for _ in range(rng.randint(1, 2))]
        docs.append("k: {" + ", ".join(entries) + rng.choice(["", ","]) + "}")
    return sorted(set(docs))


#: The two refusals this reader makes of a document PyYAML reads, by design:
#: an explicit key (#252) and a single pair in a flow sequence (#392).
BY_DESIGN = (EXPLICIT_KEY, PAIR)


@NEEDS_PYYAML
@pytest.mark.parametrize("seed", FUZZ_SEEDS,
                         ids=[f"seed-{seed}" for seed in FUZZ_SEEDS])
def test_the_fuzz_finds_no_document_read_where_pyyaml_refuses_or_misread(seed):
    """Where PyYAML refuses, this reader refuses; where both read, they read
    the same; and where only PyYAML reads, the refusal is one this reader
    makes by design. Every disagreement is listed, not just the first."""
    docs = fuzz_documents(seed)
    assert len(docs) >= 300, "the fuzz must stay a few hundred documents"
    read_not_refused, misread, undesigned = [], [], []
    tally = {"both refuse": 0, "both read": 0, "by design": 0}
    for doc in docs:
        mine, theirs = ours(doc), stock(doc)
        if refused(theirs) and not refused(mine):
            read_not_refused.append((doc, mine))
        elif not refused(theirs) and not refused(mine):
            tally["both read"] += 1
            if mine != theirs:
                misread.append((doc, mine, theirs))
        elif refused(theirs):
            tally["both refuse"] += 1
        elif str(mine).startswith(BY_DESIGN):
            tally["by design"] += 1
        else:
            undesigned.append((doc, str(mine), theirs))
    assert not read_not_refused, read_not_refused
    assert not misread, misread
    assert not undesigned, undesigned
    # Not vacuous: each kind of answer is drawn many times.
    assert min(tally.values()) >= 20, tally
