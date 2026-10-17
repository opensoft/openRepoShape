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

import re
import sys

import pytest

from conftest import REPO, run_script
from test_leg_path_yaml_scalars import (  # noqa: F401 - `bare_lines`
    OFFER, SPEC, assert_nothing_was_created, bare_lines, scaffold, sentence)
from test_scaffold_pin_and_reuse import scaffolder  # noqa: F401 - a fixture
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
