# SPDX-License-Identifier: Apache-2.0
"""What #635 left in the YAML reader, and three texts about it (#715).

- L4-150, YAML'S WHITE SPACE IS THE SPACE AND THE TAB. The reader stripped
  with `str.strip()`, which also takes U+001F and sixteen Unicode spaces that
  YAML keeps as text. So `k: \\u3000]`, `k: \\u2003@a` and `k: \\xa0%a` were
  refused quoting `']'`, `'@a'` and `'%a'`, texts the file does not hold,
  and `k: [a,\\u3000,b]` was refused as an empty entry, where PyYAML reads
  each whole; `k: \\xa0` read as no value, `- \\u3000` as `[None]` and
  `k: [a, \\xa0]` as `['a']`. Every strip now names `_YAML_WHITE`.
- L4-148, THE EMPTY BLOCK KEY. `- :` read `[{'': None}]` and `: a` read
  `{'': 'a'}`, where PyYAML refuses both. Each is refused by its line, and
  the fuzz of `tests/test_yaml_indicator_openers.py` draws `- :` again.
- L4-149, A KEY THAT IS A LONE `?`. `k: {?: 1}` read the key `'?'`, where
  PyYAML reads an explicit key with no key, while `[?]` and `{?}` were
  refused as explicit keys. It is refused with them.
- L4-155, `k: [a: b: c]` was refused as a single pair, which it is not:
  PyYAML refuses it as invalid YAML, and the words now say so.
- L4-153, `_read_back` raised the reader's `YamlError` for a template line
  the reader refuses, a bare leg-path line holding `@x`: the refusal is now
  the reading, and the value is refused in the leg-path rule's words.
- L4-154, `_neutral_pin_entry`'s docstring gave `id: -` as "the text",
  which the reader refuses since #393; its example is now one it reads.

PyYAML is the ORACLE ONLY, as in `tests/test_yaml_indicator_openers.py`,
whose helpers this file uses: where it is not installed, the comparisons
are skipped and this reader's answers are still asserted.

NO NETWORK AND NO GITHUB: strings, a temporary file, one scaffolded project
over local bare remotes, one dry run, and imports.
"""

from __future__ import annotations

import importlib.util
import re
import shlex
import shutil
import sys
import unicodedata

import pytest

from conftest import PROJECT, REPO, cloned_just_pushed, git, run_script
from test_bootstrap_branch_bytes import (ADVICE, ENCODING, leg_branch,
                                         legs_state, tracking, validator_of)
from test_bootstrap_spelling import bootstrap_of, pin12, run
from test_bump_leg import bump
from test_leg_path_yaml_scalars import (  # noqa: F401 - `bare_lines`
    OFFER, SPEC, assert_nothing_was_created, bare_lines, scaffold, sentence)
from test_scaffold_pin_and_reuse import scaffolder  # noqa: F401 - a fixture
from test_update_shape import (CHANGED_SOURCE, UPDATE,
                               scaffold_upstream_and_project)
from test_yaml_indicator_openers import (EXPLICIT_KEY, NEEDS_PYYAML, OPENS,
                                         PAIR, fuzz_documents, ours, refused,
                                         stock)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import (SAFE_ARG_RE, Refusal, YamlError,  # noqa: E402
                        checked_value, double_quoted, load_yaml, parse_yaml)

#: The three spaces the issue names. Every row of the tables below is asked
#: with each of them.
ISSUE_SPACES = [pytest.param("\u3000", id="ideographic-space"),
                pytest.param("\u2003", id="em-space"),
                pytest.param("\xa0", id="no-break-space")]

#: Every character `str.strip()` takes from inside a line that YAML keeps:
#: U+001F and the sixteen Unicode spaces. Found, not trusted, by the first
#: test below.
KEPT_BY_YAML = ("\x1f\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006"
                "\u2007\u2008\u2009\u200a\u202f\u205f\u3000")


def filled(value, space: str):
    """`value` with every `{s}` in its text, its keys too, made `space`."""
    if isinstance(value, str):
        return value.replace("{s}", space)
    if isinstance(value, list):
        return [filled(item, space) for item in value]
    if isinstance(value, dict):
        return {filled(key, space): filled(item, space)
                for key, item in value.items()}
    return value


def refusal_words(text: str) -> str:
    """The words this reader refuses `text` with."""
    with pytest.raises(YamlError) as caught:
        parse_yaml(text + "\n")
    return str(caught.value)


# --- L4-150: a Unicode space is text ----------------------------------------

def test_the_table_is_every_character_strip_takes_and_yaml_keeps():
    found = "".join(char for char in map(chr, range(sys.maxunicode + 1))
                    if char.isspace() and char not in " \t"
                    and len(f"a{char}b".splitlines()) == 1)
    assert found == KEPT_BY_YAML


@pytest.mark.parametrize("char", KEPT_BY_YAML,
                         ids=lambda char: f"U+{ord(char):04X}")
def test_every_one_is_text_where_a_value_an_entry_or_a_key_holds_it(char):
    assert parse_yaml(f"k: {char}]\n") == {"k": f"{char}]"}
    assert parse_yaml(f"k: [a,{char},b]\n") == {"k": ["a", char, "b"]}
    assert parse_yaml(f"{char}k: a{char}\n") == {f"{char}k": f"a{char}"}
    assert parse_yaml(f"- {char}\n") == [char]


def test_a_unit_separator_is_text_as_an_escape_is():
    """U+001F is a control character, which YAML forbids raw and PyYAML
    refuses. This reader takes a raw control as text, as `k: \\x1b]` shows,
    and since #715 U+001F alike, which `str.strip()` used to take."""
    assert parse_yaml("k: \x1b]\n") == {"k": "\x1b]"}
    assert parse_yaml("k: \x1f]\n") == {"k": "\x1f]"}


#: `(document, what it reads as)`, `{s}` standing for the space. The issue's
#: four first: on main each was refused, quoting the text left once the
#: space was stripped. Then the same strip wherever else it stood, which on
#: main read less than the file holds, or something else.
READ_WHOLE = [
    pytest.param("k: {s}]", {"k": "{s}]"}, id="closer"),
    pytest.param("k: {s}@a", {"k": "{s}@a"}, id="at-sign"),
    pytest.param("k: {s}%a", {"k": "{s}%a"}, id="percent"),
    pytest.param("k: [a,{s},b]", {"k": ["a", "{s}", "b"]}, id="flow-entry"),
    pytest.param("k: {s}", {"k": "{s}"}, id="alone-as-a-value"),
    pytest.param("k: a{s}", {"k": "a{s}"}, id="after-a-value"),
    pytest.param("k: {s}a", {"k": "{s}a"}, id="before-a-value"),
    pytest.param("{s}k: a", {"{s}k": "a"}, id="before-a-key"),
    pytest.param("k{s}: a", {"k{s}": "a"}, id="after-a-key"),
    pytest.param("- {s}", ["{s}"], id="alone-as-an-item"),
    pytest.param("k: [{s}]", {"k": ["{s}"]}, id="alone-as-a-flow-item"),
    pytest.param("k: [a, {s}]", {"k": ["a", "{s}"]}, id="the-last-flow-item"),
    pytest.param("k: {a: {s}b}", {"k": {"a": "{s}b"}}, id="flow-value"),
    pytest.param("k: {{s}a: b}", {"k": {"{s}a": "b"}}, id="flow-key"),
    pytest.param("k: {s}[a]", {"k": "{s}[a]"}, id="before-a-bracket"),
    pytest.param('k: {s}"a"', {"k": '{s}"a"'}, id="before-a-quote"),
    pytest.param('k: [{s}"a"]', {"k": ['{s}"a"']}, id="before-a-quote-item"),
    pytest.param("k: {s}|", {"k": "{s}|"}, id="before-a-block-header"),
    pytest.param("k: {s}-", {"k": "{s}-"}, id="before-a-lone-dash"),
    pytest.param("k: {s}&a", {"k": "{s}&a"}, id="before-an-anchor"),
    pytest.param("k: a{s} # c", {"k": "a{s}"}, id="before-a-comment"),
    pytest.param("k: |\n  a\n  {s}\n  b", {"k": "a\n{s}\nb\n"},
                 id="a-literal-body-line"),
    pytest.param("k: >\n  a\n  {s}\n  b", {"k": "a {s} b\n"},
                 id="a-folded-body-line"),
]


@pytest.mark.parametrize("space", ISSUE_SPACES)
@pytest.mark.parametrize("text, expected", READ_WHOLE)
def test_a_unicode_space_is_read_as_the_text_it_is(text, expected, space):
    assert parse_yaml(filled(text, space) + "\n") == filled(expected, space)


@NEEDS_PYYAML
@pytest.mark.parametrize("space", ISSUE_SPACES)
@pytest.mark.parametrize("text, expected", READ_WHOLE)
def test_pyyaml_reads_each_the_same(text, expected, space):
    assert stock(filled(text, space)) == filled(expected, space)


#: `(document, the words it is refused with)`: refusals that now quote the
#: text the file holds, where PyYAML refuses the document too.
QUOTED_WHOLE = [
    pytest.param("k: ]{s}", OPENS + " `]`, which closes a flow sequence in "
                 "YAML: {q}", "]{s}", id="after-a-closer"),
    pytest.param('k: "a"{s}', "quoted scalar with text after its closing "
                 "quote: {q}", '"a"{s}', id="after-a-quoted-value"),
    pytest.param('"k"{s}: a', "quoted scalar with text after its closing "
                 "quote: {q}", '"k"{s}', id="after-a-quoted-key"),
    pytest.param('k: ["a"{s}]', "quoted scalar with text after its closing "
                 "quote: {q}", '"a"{s}', id="after-a-quoted-item"),
    pytest.param("a: 1\n{s}\nb: 2", "line 2: expected `key: value`, got {q}",
                 "{s}", id="a-line-of-it"),
    pytest.param("k: [a]{s}", "not a flow collection: {q}", "[a]{s}",
                 id="after-a-flow-sequence"),
    pytest.param("- {a: b}{s}", "not a flow collection: {q}", "{a: b}{s}",
                 id="after-a-flow-mapping-item"),
]


@pytest.mark.parametrize("space", ISSUE_SPACES)
@pytest.mark.parametrize("text, words, quoted", QUOTED_WHOLE)
def test_a_refusal_quotes_the_text_the_file_holds(text, words, quoted,
                                                  space):
    assert refusal_words(filled(text, space)) == words.replace(
        "{q}", repr(filled(quoted, space)))


@NEEDS_PYYAML
@pytest.mark.parametrize("space", ISSUE_SPACES)
@pytest.mark.parametrize("text, words, quoted", QUOTED_WHOLE)
def test_pyyaml_refuses_each_quoted_row_too(text, words, quoted, space):
    assert refused(stock(filled(text, space)))


#: What main READ, as less than the file holds, and is refused now, where
#: PyYAML reads it: a document that is a plain scalar (`\\u3000- a`, which
#: main read as the list `['a']`) and a key holding a bracket are outside
#: the subset (#249), and a flow mapping entry with no `: ` is refused as
#: `{a}` is.
NO_LONGER_MISREAD = [
    pytest.param("{s}- a", "line 1: expected `key: value`, got {q}",
                 "{s}- a", id="before-a-dash"),
    pytest.param("-{s}a", "line 1: expected `key: value`, got {q}", "-{s}a",
                 id="after-a-dash"),
    pytest.param("{s}a[b]: c", "a key holding `[` or `{` is not supported: "
                 "{q}", "{s}a[b]", id="a-key-holding-a-bracket"),
    pytest.param("k: {{s}}", "flow mapping entry without a key: {q}", "{s}",
                 id="alone-in-a-flow-mapping"),
]


@pytest.mark.parametrize("space", ISSUE_SPACES)
@pytest.mark.parametrize("text, words, quoted", NO_LONGER_MISREAD)
def test_what_main_misread_is_refused_by_its_text(text, words, quoted, space):
    assert refusal_words(filled(text, space)) == words.replace(
        "{q}", repr(filled(quoted, space)))


@pytest.mark.parametrize("space", ISSUE_SPACES)
def test_a_tab_after_a_unicode_space_is_in_the_key_not_the_indentation(
        space):
    """The indentation is the spaces and tabs that open the line, so a tab
    after a Unicode space is inside the plain scalar, as YAML reads it and
    as this reader reads `k: a\\tb`; PyYAML refuses a tab there, in both.
    A tab before any text is still refused as indentation."""
    assert parse_yaml(f"{space}\tk: a\n") == {f"{space}\tk": "a"}
    assert parse_yaml("k: a\tb\n") == {"k": "a\tb"}
    assert refusal_words(" \tk: a") == "line 1: tab used for indentation"


# --- L4-148: the empty block key --------------------------------------------

#: `(document, the line it is refused on)`.
EMPTY_BLOCK_KEYS = [
    pytest.param("- :", 1, id="the-fuzz-row"),
    pytest.param(": a", 1, id="with-a-value"),
    pytest.param("- : a", 1, id="an-item-with-a-value"),
    pytest.param("a:\n  - :", 2, id="a-nested-item"),
    pytest.param(":", 1, id="alone"),
    pytest.param(":\t a", 1, id="a-tab-after-the-colon"),
    pytest.param("- - :", 1, id="an-item-of-an-item"),
    pytest.param(": # c", 1, id="before-a-comment"),
    pytest.param("a: 1\n: b", 2, id="after-a-key"),
]


@pytest.mark.parametrize("text, line", EMPTY_BLOCK_KEYS)
def test_an_empty_block_key_is_refused_by_its_line(text, line):
    assert refusal_words(text) == f"line {line}: empty keys are not supported"


@NEEDS_PYYAML
@pytest.mark.parametrize("text, line", EMPTY_BLOCK_KEYS)
def test_pyyaml_refuses_each_empty_block_key_too(text, line):
    assert refused(stock(text)), f"PyYAML reads {text!r} as {stock(text)!r}"


#: A quoted empty key is the key `''` to PyYAML too, and a `:` with a letter
#: after it opens no value.
EMPTY_KEY_STILL_READ = [
    pytest.param('"": a', {"": "a"}, id="double-quoted"),
    pytest.param("'': a", {"": "a"}, id="single-quoted"),
    pytest.param('- "": a', [{"": "a"}], id="double-quoted-in-an-item"),
    pytest.param("- :a", [":a"], id="a-colon-and-a-letter"),
]


@pytest.mark.parametrize("text, expected", EMPTY_KEY_STILL_READ)
def test_a_quoted_empty_key_still_reads(text, expected):
    assert parse_yaml(text + "\n") == expected


@NEEDS_PYYAML
@pytest.mark.parametrize("text, expected", EMPTY_KEY_STILL_READ)
def test_pyyaml_reads_each_quoted_empty_key_the_same(text, expected):
    assert stock(text) == expected


@pytest.mark.parametrize("seed", [1, 3])
def test_the_fuzz_draws_the_empty_block_key_again(seed):
    """The two seeds on which the fuzz drew `- :` and left it out."""
    assert "- :" in fuzz_documents(seed)


def test_a_file_holding_one_is_yaml_unparsable_naming_the_file(tmp_path):
    path = tmp_path / "project.yaml"
    path.write_bytes(b"id: atlas\n: main\n")
    with pytest.raises(Refusal) as caught:
        load_yaml(path)
    assert caught.value.code == "yaml-unparsable"
    assert caught.value.detail == (f"{path}: line 2: empty keys are not "
                                   "supported")


def test_the_projects_own_validator_refuses_it(project):
    """The copy a project carries reads `project.yaml`: its own
    `validate-manifest.py` exits 2, names the file and the line, and reads
    nothing as data."""
    manifest = project / "project.yaml"
    data = manifest.read_bytes()
    old = b'tracking_branch: "main"'
    assert old in data, f"fixture drift: {old!r} not in project.yaml"
    edited = data.replace(old, b': "main"', 1)
    manifest.write_bytes(edited)
    line = edited[:edited.index(b': "main"')].count(b"\n") + 1
    result = run_script(project / "scripts" / "validate-manifest.py",
                        cwd=project)
    assert result.returncode == 2, result.stderr
    assert (f"REFUSED yaml-unparsable: {manifest}: line {line}: empty keys "
            "are not supported\n") in result.stderr
    assert "Traceback" not in result.stderr
    assert "manifest ok" not in result.stdout
    assert manifest.read_bytes() == edited


# --- L4-149: a key that is a lone `?` ---------------------------------------

#: `(document, the entry refused, what PyYAML reads)`: an explicit key with
#: no key, `None`, where this reader read the key `'?'`, or refused the
#: sequence item as a single pair.
LONE_QUESTION_KEYS = [
    pytest.param("k: {?: 1}", "?: 1", {"k": {None: 1}}, id="the-issue-row"),
    pytest.param("k: {?:}", "?:", {"k": {None: None}}, id="no-value"),
    pytest.param("k: {?: }", "?:", {"k": {None: None}},
                 id="a-space-and-no-value"),
    pytest.param("k: {b: 2, ?: 1}", "?: 1", {"k": {"b": 2, None: 1}},
                 id="after-another-entry"),
    pytest.param("k: [?: 1]", "?: 1", {"k": [{None: 1}]},
                 id="a-flow-sequence-item"),
    pytest.param("k: [?:]", "?:", {"k": [{None: None}]},
                 id="an-item-with-no-value"),
]


@pytest.mark.parametrize("text, entry, pyyaml_reads", LONE_QUESTION_KEYS)
def test_a_key_that_is_a_lone_question_mark_is_refused_as_an_explicit_key(
        text, entry, pyyaml_reads):
    assert refusal_words(text) == f"{EXPLICIT_KEY}: {entry!r}"


@NEEDS_PYYAML
@pytest.mark.parametrize("text, entry, pyyaml_reads", LONE_QUESTION_KEYS)
def test_pyyaml_reads_each_as_an_explicit_key_with_no_key(text, entry,
                                                          pyyaml_reads):
    assert stock(text) == pyyaml_reads


def test_a_tab_after_the_colon_is_refused_too():
    """PyYAML refuses the tab there; this reader refuses the key first."""
    assert refusal_words("k: {?:\t1}") == f"{EXPLICIT_KEY}: '?:\\t1'"


#: What is no lone `?` key: a quoted one, a block key (the key `'?'` to
#: PyYAML as well), and a `?` with text after it, which #252 keeps.
QUESTION_MARK_STILL_READ = [
    pytest.param('k: {"?": 1}', {"k": {"?": 1}}, id="a-quoted-key"),
    pytest.param("?: 1", {"?": 1}, id="a-block-key"),
    pytest.param("k: {?a: 1}", {"k": {"?a": 1}}, id="a-letter-after-it"),
    pytest.param("k: [?:a]", {"k": ["?:a"]}, id="a-colon-and-a-letter"),
]


@pytest.mark.parametrize("text, expected", QUESTION_MARK_STILL_READ)
def test_what_is_no_lone_question_mark_key_still_reads(text, expected):
    assert parse_yaml(text + "\n") == expected


# --- L4-155: a flow sequence entry with a second `:` ------------------------

NOT_A_PAIR = [
    pytest.param("k: [a: b: c]", "a: b: c", id="the-issue-row"),
    pytest.param("k: [a: b:]", "a: b:", id="a-second-colon-at-the-end"),
    pytest.param("k: [a: b: c: d]", "a: b: c: d", id="three-colons"),
    pytest.param("k: [a: b:\tc]", "a: b:\tc", id="a-tab-after-the-second"),
    pytest.param('k: ["a": b: c]', '"a": b: c', id="a-quoted-key"),
    pytest.param("k: [a: 'b': c]", "a: 'b': c", id="a-quoted-second-key"),
    pytest.param("k: [x, a: b: c]", "a: b: c", id="after-another-item"),
]


@pytest.mark.parametrize("text, entry", NOT_A_PAIR)
def test_an_entry_with_a_second_colon_is_refused_as_invalid_yaml(text,
                                                                 entry):
    assert refusal_words(text) == (
        "a flow sequence entry with a second `:` opening a value is not "
        f"valid YAML: {entry!r}")


@NEEDS_PYYAML
@pytest.mark.parametrize("text, entry", NOT_A_PAIR)
def test_pyyaml_refuses_each_as_invalid_too(text, entry):
    assert refused(stock(text)), f"PyYAML reads {text!r} as {stock(text)!r}"


#: `(document, the entry, what PyYAML reads)`: single pairs, which keep the
#: single-pair words (`_flow_value` says why one is refused).
STILL_A_PAIR = [
    pytest.param("k: [a:b: c]", "a:b: c", {"k": [{"a:b": "c"}]},
                 id="a-colon-inside-the-key"),
    pytest.param('k: [a: "b: c"]', 'a: "b: c"', {"k": [{"a": "b: c"}]},
                 id="a-quoted-value"),
    pytest.param("k: [a: b:c]", "a: b:c", {"k": [{"a": "b:c"}]},
                 id="a-colon-inside-the-value"),
]


@pytest.mark.parametrize("text, entry, pyyaml_reads", STILL_A_PAIR)
def test_a_single_pair_keeps_its_words(text, entry, pyyaml_reads):
    assert refusal_words(text) == f"{PAIR}: {entry!r}"


@NEEDS_PYYAML
@pytest.mark.parametrize("text, entry, pyyaml_reads", STILL_A_PAIR)
def test_pyyaml_reads_each_as_a_single_pair(text, entry, pyyaml_reads):
    assert stock(text) == pyyaml_reads


@pytest.mark.parametrize("text, value, held", [
    pytest.param('k: ["a": b[: c]', "b[: c", "[", id="a-bracket"),
    pytest.param('k: ["a": b{: c]', "b{: c", "{", id="a-brace"),
])
def test_a_quoted_items_value_holding_a_bracket_keeps_301s_words(
        text, value, held):
    """RV823's NIT-1: a QUOTED item skips the bracket test its plain twin
    gets, so the value was split again and named as a key holding `[`."""
    assert refusal_words(text) == (
        f"a plain scalar in a flow collection holds `{held}`, which ends it "
        f"in YAML: {value!r}")


#: `(document, the item, what PyYAML reads)`: a quoted key whose value is a
#: flow collection, a single pair to YAML.
OPENS_A_COLLECTION = [
    pytest.param('k: ["a": [b]]', '"a": [b]', {"k": [{"a": ["b"]}]},
                 id="a-sequence"),
    pytest.param('k: ["a": {b: c}]', '"a": {b: c}',
                 {"k": [{"a": {"b": "c"}}]}, id="a-mapping"),
    pytest.param("k: ['a': [b, c]]", "'a': [b, c]",
                 {"k": [{"a": ["b", "c"]}]}, id="single-quoted"),
]


@pytest.mark.parametrize("text, entry, pyyaml_reads", OPENS_A_COLLECTION)
def test_a_quoted_items_value_that_opens_a_collection_keeps_the_pair_words(
        text, entry, pyyaml_reads):
    """RV823's round-1 NIT-1: the bracket test asked of a quoted item's
    value named `[b]` as a plain scalar holding `[`. It is a flow sequence,
    so the item is the single pair YAML reads, refused in the words main
    gives it, which this reader does not support."""
    assert refusal_words(text) == f"{PAIR}: {entry!r}"


@NEEDS_PYYAML
@pytest.mark.parametrize("text, entry, pyyaml_reads", OPENS_A_COLLECTION)
def test_pyyaml_reads_a_quoted_key_and_a_collection_as_one_pair(
        text, entry, pyyaml_reads):
    assert stock(text) == pyyaml_reads


# --- L4-153: a template line the reader refuses -----------------------------

#: What the leg-path rule says the project's reader makes of a bare `@x`.
AT_X_READ = ("nothing at all, because it refuses the line (a plain scalar "
             "cannot open with `@`, which is reserved in YAML: '@x')")


def test_of_the_alphabet_only_an_at_sign_opens_what_a_bare_line_refuses():
    """`_misread_reason`'s docstring, measured: `checked_value` passes a leg
    path that opens with `@`, the one character of its alphabet that a bare
    line cannot open with, and a quoted line reads it back."""
    openers = [char for char in map(chr, range(0x21, 0x7f))
               if SAFE_ARG_RE.fullmatch(f"{char}x")]
    assert [char for char in openers
            if refused(ours(f"path: {char}x"))] == ["@"]
    assert checked_value(SPEC, "@x") == "@x"
    assert parse_yaml('path: "@x"\n') == {"path": "@x"}


@pytest.mark.parametrize("what", [SPEC, "--code-path", "legs.spec_path"])
def test_a_bare_line_the_reader_refuses_is_a_refusal_of_the_value(
        bare_lines, what):  # noqa: F811
    """Over templates whose leg-path lines are bare: the reader's refusal of
    `path: @x` was a traceback out of `leg_path_problem`."""
    assert shape_materialize.leg_path_problem(what, "@x") == sentence(
        what, "@x", AT_X_READ)


def test_the_scaffold_refuses_it_in_its_own_words(bare_lines):  # noqa: F811
    with pytest.raises(Refusal) as caught:
        shape_materialize.refuse_bad_leg_paths(
            "scaffold-bad-leg-path", (SPEC, "@x"), ("--code-path", "code"))
    assert caught.value.code == "scaffold-bad-leg-path"
    assert caught.value.detail == sentence(SPEC, "@x", AT_X_READ)
    assert caught.value.remediation == shape_materialize.LEG_PATH_REMEDIATION


def test_no_spelling_is_offered_that_a_bare_line_refuses(
        bare_lines):  # noqa: F811
    """`@x/` is not answered `Write '@x'.`: `_canonical_spelling` asks the
    same reading, which was a traceback too."""
    problem = shape_materialize.leg_path_problem(SPEC, "@x/")
    assert problem.startswith(
        "--spec-path is '@x/', which is not a canonical leg path"), problem
    assert OFFER not in problem


def test_the_real_templates_read_it_back_and_a_dry_run_plans_it(tmp_path):
    """The four leg-path lines are quoted (#259), so `@x` is a path."""
    assert shape_materialize.leg_path_problem(SPEC, "@x") is None
    result = scaffold(tmp_path, "--dry-run", SPEC, "@x")
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr
    assert_nothing_was_created(tmp_path)


# --- L4-154: `_neutral_pin_entry`'s example ---------------------------------

def test_the_docstrings_example_is_one_the_reader_reads(
        scaffolder):  # noqa: F811
    """Its example, read out of the docstring and asked of the reader: the
    list entry is a list of its own, the `id:` line is the text, so the
    entry is asked and double-quoted. `id: -`, its old example, is refused
    since #393."""
    found = re.search(r"`  - (?P<entry>[^`]+)` is a list of its own, where "
                      r"`id: (?P<value>[^`]+)`\s+is the text",
                      scaffolder._neutral_pin_entry.__doc__)
    assert found, scaffolder._neutral_pin_entry.__doc__
    entry, value = found["entry"], found["value"]
    assert entry == value
    listed = parse_yaml(f"neutral_product_pins:\n  - {entry}\n")
    assert isinstance(listed["neutral_product_pins"][0], list), listed
    assert parse_yaml(f"id: {value}\n") == {"id": value}
    assert scaffolder._neutral_pin_entry(entry) == double_quoted(entry)
    assert refused(ours("id: -"))


# --- RV823 MUST-1: a branch no person can tell from another ------------------
#
# The reader now reads `tracking_branch: main` followed by U+00A0 as PyYAML
# reads it, `'main\xa0'`, where main read `'main'`. git takes that name, so
# the four readers of a branch refuse a character that does not print or is
# white space, the rule of `validate-manifest.py`'s `_branch_finding`
# (`siblings.py` asks `isprintable` alone). bump-leg and update-shape refuse
# nothing else (Brett Heap's option A on RV823's SHOULD-1, 2026-10-17): a
# name git creates and the root's gate passes is read as it is.

#: `(the YAML line's value, bare as a person types it, the code point named)`.
UNSEEN_BRANCHES = [
    pytest.param("main\xa0", "U+00A0", id="main-and-a-no-break-space"),
    pytest.param("\xa0", "U+00A0", id="a-no-break-space-alone"),
    pytest.param("main\N{IDEOGRAPHIC SPACE}", "U+3000",
                 id="main-and-an-ideographic-space"),
    pytest.param("a\N{ZERO WIDTH JOINER}b", "U+200D",
                 id="a-zero-width-joiner"),
    # The one character `isspace` adds to `isprintable` (RV823's MR3): git
    # refuses `a b` too, so the refusal costs no name git would make.
    pytest.param("a b", "U+0020", id="an-ascii-space"),
]

#: Names git creates and the root's own gate passes, which bump-leg and
#: update-shape read as they are (option A). #823's first fix round read
#: them through `checked_value`, whose pattern refused each, exit 2.
READABLE_BRANCHES = [
    pytest.param("feature/\N{CJK UNIFIED IDEOGRAPH-65E5}"
                 "\N{CJK UNIFIED IDEOGRAPH-672C}", id="cjk"),
    pytest.param("d\N{LATIN SMALL LETTER E WITH ACUTE}veloppement",
                 id="an-accent-nfc"),
    pytest.param("de\N{COMBINING ACUTE ACCENT}veloppement",
                 id="an-accent-nfd"),
    pytest.param("a&b", id="an-ampersand"),
]


def test_the_two_spellings_of_the_accent_are_two_names():
    """NFC and NFD are both asked because git keeps the bytes it is given:
    the two are one word to a reader and two branches to git."""
    nfc, nfd = (row.values[0] for row in READABLE_BRANCHES[1:3])
    assert nfc != nfd
    assert unicodedata.normalize("NFC", nfd) == nfc


def unseen_refusal(value: str, point: str) -> str:
    """How bump-leg and update-shape refuse such a name (`readable_branch`),
    in `validate-manifest.py`'s words."""
    return (f"REFUSED unseen-branch: tracking_branch is {value!r}, which "
            f"holds {point}, a character that does not print or is white "
            "space: a person reading the name cannot tell it from the name "
            "without it")

#: What `validate-manifest.py` says after the code point.
UNSEEN_WHY = ("a character that does not print or is white space: a person "
              "reading the name cannot tell it from the name without it.")


def unseen_finding(code: str, what: str, value: str, point: str) -> str:
    return (f"FINDING {code}: {what} is {value!r}, which holds {point}, "
            f"{UNSEEN_WHY} {ADVICE}")


@pytest.mark.parametrize("value, point", UNSEEN_BRANCHES)
def test_the_validator_names_a_tracking_branch_no_person_can_see(
        project, tmp_path, value, point):
    tracking(project, value)
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert (code, out) == (1, ""), out + err
    assert err.split("\n") == [
        unseen_finding("manifest-tracking-branch", "tracking_branch", value,
                       point),
        "", f"1 finding(s) in {project / 'project.yaml'}", ""], err


def test_the_validator_names_a_legs_branch_no_person_can_see(
        project, tmp_path):
    leg_branch(project, "spec", "main\xa0")
    code, out, err = run(validator_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert (code, out) == (1, ""), out + err
    assert err.split("\n")[0] == unseen_finding(
        "manifest-leg-branch", "leg 'spec': branch", "main\xa0", "U+00A0"), err


def not_placed(leg: str, value: str, point: str) -> list[str]:
    """Step (a)'s two lines for a leg whose branch no person can see. The
    name is printed as `spelled` prints it, which leaves a no-break or an
    ideographic space as it is (#391), so the line names its code point."""
    return [f"  [{leg}] {leg}: could not create branch "
            f"{value}: it holds {point}, a character that does "
            "not print or is white space, which no person can tell from the "
            "name without it; the leg is left as it is",
            "          the branch is the leg's `branch:`, else `--branch`, "
            "else `tracking_branch`. Give that one a name with no such "
            "character and run bootstrap again."]


def step_a(out: str) -> list[str]:
    lines = out.split("\n")
    return lines[lines.index("(a) legs on tracking branches, pins untouched")
                 + 1:lines.index("(b) neutral validators") - 1]


@pytest.mark.parametrize("value, point", UNSEEN_BRANCHES[:3])
def test_bootstrap_makes_no_ref_of_a_tracking_branch_no_person_can_see(
        project, tmp_path, value, point):
    """On #823's first head each leg gained `refs/heads/main` followed by
    U+00A0 beside `main`, checked out, and the run ended `bootstrap ok`."""
    tracking(project, value)
    before = legs_state(project)
    code, out, err = run(bootstrap_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert "Traceback" not in err, err
    assert step_a(out) == (not_placed("spec", value, point)
                           + not_placed("code", value, point)), out
    assert "bootstrap FAILED: manifest (exit 1)" in err, err
    assert legs_state(project) == before


def test_bootstrap_makes_no_ref_of_a_legs_branch_no_person_can_see(
        project, tmp_path):
    leg_branch(project, "spec", "main\xa0")
    before = legs_state(project)
    code, out, err = run(bootstrap_of(project), encoding=ENCODING,
                         tmp_path=tmp_path, cwd=project)
    assert code == 1, out + err
    assert "Traceback" not in err, err
    assert step_a(out) == not_placed("spec", "main\xa0", "U+00A0") + [
        f"  [code] code: on main at {pin12(project, 'code')} "
        "(branch tip == pin)"], out
    assert legs_state(project)["spec"] == before["spec"]


def committed_tracking(root, value: str) -> str:
    """`tracking_branch: <value>` hand-edited into the root and committed, as
    RV823's scenario has it; the root's new HEAD."""
    tracking(root, value)
    git("add", "--", "project.yaml", cwd=root)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "hand-edit the tracking branch", cwd=root)
    return git("rev-parse", "HEAD", cwd=root).stdout.strip()


#: Where this module's advanced spec commit is pushed. Not `test_bump_leg.py`'s
#: branch: both modules share the session's bare remotes, and a second,
#: different commit pushed to the same branch name is refused as
#: non-fast-forward, which errors every test of whichever module runs second.
ADVANCE_BRANCH = "yaml-reader-spaces-advance"


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-spaces") / f"{PROJECT}-spec")
    (work / "SPACES-CONTRACT.md").write_text("# a contract the leg gained\n")
    git("add", "--", "SPACES-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg for the #715 tests", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


@pytest.mark.parametrize("dry_run", [(), ("--dry-run",)],
                         ids=["real-run", "dry-run"])
@pytest.mark.parametrize("value, point", UNSEEN_BRANCHES[:3])
def test_bump_leg_refuses_a_tracking_branch_no_person_can_see(
        project, scaffolded, advanced, value, point,
        dry_run):
    """On #823's first head, on `main`: exit 0, a commit on `main`, and a
    NEXT line pushing it, where `bump-leg-on-tracking-branch` was owed.
    `readable_branch` refuses it now, before anything is fetched or
    written."""
    head = committed_tracking(project, value)
    pin = git("rev-parse", "HEAD:spec", cwd=project).stdout
    result = bump(project, scaffolded, advanced, *dry_run)
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stderr.startswith(unseen_refusal(value, point)), (
        result.stderr)
    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == head
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout == pin
    assert git("status", "--porcelain", cwd=project).stdout == ""


@pytest.mark.parametrize("dry_run", [(), ("--dry-run",)],
                         ids=["real-run", "dry-run"])
@pytest.mark.parametrize("value", READABLE_BRANCHES)
def test_bump_leg_takes_a_tracking_branch_a_person_can_read(
        project, scaffolded, advanced, value, dry_run):
    """Option A: only what no person can see is refused. Read through
    `checked_value` (#823's first fix round) each of these was `unsafe-value`,
    exit 2, though bump-leg only compares and prints the name. On `main`,
    which is not the tracking branch, the bump goes ahead: the dry run
    changes nothing, and the real run moves the pin in a commit on `main`."""
    head = committed_tracking(project, value)
    result = bump(project, scaffolded, advanced, *dry_run)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "REFUSED" not in result.stderr, result.stderr
    now = git("rev-parse", "HEAD", cwd=project).stdout.strip()
    if dry_run:
        assert now == head
    else:
        assert git("rev-parse", "HEAD^", cwd=project).stdout.strip() == head
        assert git("rev-parse", "HEAD:spec",
                   cwd=project).stdout.strip() == advanced


@pytest.fixture(scope="module")
def older_validator(tmp_path_factory) -> dict:
    """A project scaffolded at A, and B: an upstream commit whose manifest
    validator asks a branch for a NUL alone, as one older than #715 does.
    So the root's own validators pass a hand-edited `main` followed by
    U+00A0 after `apply`, and update-shape's own guard is what is asked."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "w715-older-validator")
    source = upstream / CHANGED_SOURCE
    text = source.read_text(encoding="utf-8")
    asked = "if not c.isprintable() or c.isspace()),"
    assert text.count(asked) == 1, "the validator no longer asks this"
    source.write_text(text.replace(asked, 'if c == "\\x00"),'),
                      encoding="utf-8")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m",
        "An older manifest validator", "--", CHANGED_SOURCE, cwd=upstream)
    commit_b = git("rev-parse", "HEAD", cwd=upstream).stdout.strip()
    return {"upstream": upstream, "clone": clone, "a": commit_a,
            "b": commit_b}


def test_update_shape_never_commits_onto_a_tracking_branch_no_one_can_see(
        older_validator, tmp_path):
    """`apply --branch main` on `main`, `tracking_branch: main` followed by
    U+00A0. On #823's first head the guard compared `'main'` with
    `'main\xa0'`, found them different, and committed the shape update onto
    `main`. Now `readable_branch` refuses the value, and the ledger rolls
    the rewrite back: the pin, HEAD and the tree are as they were."""
    root = tmp_path / "Atlas"
    shutil.copytree(older_validator["clone"], root, symlinks=True)
    head = committed_tracking(root, "main\xa0")
    result = run_script(UPDATE, "apply", "--root", str(root), "--yes",
                        "--upstream", str(older_validator["upstream"]),
                        "--at", older_validator["b"], "--branch", "main")
    assert result.returncode == 2, result.stdout + result.stderr
    assert unseen_refusal("main\xa0", "U+00A0") in result.stderr, (
        result.stderr)
    assert git("rev-parse", "HEAD", cwd=root).stdout.strip() == head
    pinned = load_yaml(root / "contracts" / "shape-pin.yaml")["commit"]
    assert pinned.lower() == older_validator["a"]
    assert git("status", "--porcelain", cwd=root).stdout == ""


@pytest.mark.parametrize("value", READABLE_BRANCHES)
def test_update_shape_takes_a_tracking_branch_a_person_can_read(
        older_validator, tmp_path, value):
    """Option A, on a root: `apply --branch shape/x` commits the update on
    `shape/x` and hands a person a `gh pr create` whose base, as a shell
    reads it, is the name the manifest holds. Read through `checked_value`
    (#823's first fix round) each was `unsafe-value` and rolled back."""
    root = tmp_path / "Atlas"
    shutil.copytree(older_validator["clone"], root, symlinks=True)
    committed_tracking(root, value)
    result = run_script(UPDATE, "apply", "--root", str(root), "--yes",
                        "--upstream", str(older_validator["upstream"]),
                        "--at", older_validator["b"], "--branch", "shape/x")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "\n  committed on shape/x: " in result.stdout, result.stdout
    assert git("rev-parse", "--abbrev-ref", "HEAD",
               cwd=root).stdout.strip() == "shape/x"
    line = next(line for line in result.stdout.split("\n")
                if line.startswith("NEXT  "))
    words = shlex.split(line.partition(" && ")[2])
    assert words[words.index("--base") + 1] == value, line


@pytest.fixture(scope="module")
def update_shape_module():
    """`update-shape.py` as a module, so `tracking_branch_of` is asked in
    this process, under a name of its own."""
    spec = importlib.util.spec_from_file_location("update_shape_spaces",
                                                  UPDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("value", READABLE_BRANCHES)
def test_tracking_branch_of_reads_a_name_a_person_can_read_as_it_is(
        update_shape_module, value):
    manifest = {"tracking_branch": value}
    assert update_shape_module.tracking_branch_of(manifest) == value


@pytest.mark.parametrize("value, point", UNSEEN_BRANCHES)
def test_tracking_branch_of_refuses_a_name_no_person_can_see(
        update_shape_module, value, point):
    with pytest.raises(update_shape_module.Refusal) as refused:
        update_shape_module.tracking_branch_of({"tracking_branch": value})
    assert str(refused.value).startswith(unseen_refusal(value, point)), (
        refused.value)


def test_tracking_branch_of_refuses_a_leading_dash(update_shape_module):
    """`gh pr create --base` is handed the name as one argument, where one
    that begins with `-` could be read as an option; git creates no branch
    whose name begins with one."""
    with pytest.raises(update_shape_module.Refusal) as refused:
        update_shape_module.tracking_branch_of({"tracking_branch": "-x"})
    assert str(refused.value).startswith(
        "REFUSED unsafe-value: tracking_branch is '-x', which begins with "
        "`-`, and git creates no branch whose name begins with one\n"), (
            refused.value)


@pytest.mark.parametrize("value, words", [
    pytest.param("a\udcffb", "U+DCFF, a lone surrogate: no UTF-8 file or "
                 "console can hold it, so no branch name is spelled with one",
                 id="a-lone-surrogate"),
    pytest.param("a\x00b", "U+0000, a NUL: no argument, file name or ref "
                 "name can hold one", id="a-nul"),
])
def test_tracking_branch_of_names_a_nul_and_a_surrogate_as_the_validator_does(
        update_shape_module, value, words):
    """RV823's round-2 NIT-2: a byte-carrying U+DCFF is "a lone surrogate",
    as `validate-manifest.py` names it (#280), and a NUL is a NUL."""
    with pytest.raises(update_shape_module.Refusal) as refused:
        update_shape_module.tracking_branch_of({"tracking_branch": value})
    assert str(refused.value).startswith(
        f"REFUSED unseen-branch: tracking_branch is {value!r}, which holds "
        f"{words}\n"), refused.value
