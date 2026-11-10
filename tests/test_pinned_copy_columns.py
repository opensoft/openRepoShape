# SPDX-License-Identifier: Apache-2.0
"""The two pinned scripts that pad a person's text in a table pad it by the
columns a terminal gives it, each with its own copy of the rule (#1216,
#1217).

`templates/family-root/scripts/siblings.py`'s layout table and
`scripts/validate-repository-naming.py`'s plain listing padded a name with a
format width, which counts code points: on main 50ce8ab1 a name of three
wide characters stood 3 columns right of every other row's, one with a
combining acute 1 left, and an ASCII stdout, which writes each as its
escapes, put them further right still. `--explain`'s family rows padded a
policy's family id the same way, and nothing checks an id is ASCII. Each now
pads by `_columns`, the rule #1034 gives `adopt-project.py`'s `plan` table,
counted over the text as stdout writes it (`_printed`).

THE RULE IS WRITTEN IN EACH FILE, NOT IMPORTED, by the skew rule
`tests/test_pinned_copy_text.py` holds every pinned script to: a holder or a
root may keep a `scripts/repo_shape.py` older than the script beside it
(`update-shape.py apply --accept-local`), and a name new to the library
would end `make siblings`, `park` and `resume`, or the naming gate, in an
`ImportError`. So the rows here ask each copy the same questions, and the
two copies to answer alike for every character.

The tables' own rows are in `tests/test_siblings_family_name.py` (#1216)
and `tests/test_chain_link_fold.py` (#1217). The `--explain` rows, which
pad what a policy names, are here.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

from conftest import REPO, load_without_bytecode
from test_bootstrap_spelling import NARROW
from test_stdout_encoding import run_tool, shown

FAMILY_SCRIPTS = REPO / "templates" / "family-root" / "scripts"
NAMING = REPO / "scripts" / "validate-repository-naming.py"
#: Each copy of the rule, by the file it is written in.
COPIES = ("siblings", "naming")

#: Three wide characters, and a name whose acute is a combining mark.
WIDE = "\u65e5\u672c\u8a9e"
COMBINING = "e\u0301cole"

#: Each text and the columns a terminal gives it, counted by hand: two for a
#: wide or fullwidth character, none for a non-spacing or enclosing mark, a
#: format character or a Hangul medial vowel or final consonant, and one for
#: any other, a halfwidth, an ambiguous one or a spacing mark among them.
#: #1034's table for `adopt-project.py`, with the two names of #1216 and
#: #1217 and the escapes an ASCII stdout writes for the first.
COLUMNS = {
    "Atlas": 5,
    WIDE: 6,
    COMBINING: 5,
    "\uff21\uff22.md": 7,
    "\uff76.md": 4,
    "\u00e9.md": 4,
    "\u0e17\u0e35.md": 4,
    "\u0915\u093f.md": 5,
    "\u304b\u3099.md": 5,
    "\u1112\u1161\u11ab.md": 5,
    "\u1100\ud7b0\ud7cb.md": 5,
    "a\u20ddb": 2,
    "a\u200bb": 2,
    "\\u65e5\\u672c\\u8a9e": 18,
}
COLUMN_IDS = ["ascii", "wide", "combining-acute", "fullwidth", "halfwidth",
              "ambiguous", "thai-mark-of-class-0", "spacing-mark",
              "wide-voiced-mark", "conjoining-jamo",
              "conjoining-jamo-extended-b", "enclosing-mark",
              "zero-width-space", "as-an-ascii-stdout-escapes-it"]


@pytest.fixture(scope="module")
def copies() -> dict:
    """Each file's copy, loaded by path with no bytecode written under
    `templates/`. `siblings.py`'s `bootstrap` import is answered by the
    template's `bootstrap.py`, the copy beside it in a holder; `sys.path`,
    which both files extend, and `sys.modules` are put back once both are
    loaded."""
    saved_path, saved_module = list(sys.path), sys.modules.get("bootstrap")
    try:
        sys.modules["bootstrap"] = load_without_bytecode(
            FAMILY_SCRIPTS / "bootstrap.py", "pinned_columns_bootstrap")
        return {
            "siblings": load_without_bytecode(
                FAMILY_SCRIPTS / "siblings.py", "pinned_columns_siblings"),
            "naming": load_without_bytecode(NAMING, "pinned_columns_naming"),
        }
    finally:
        sys.path[:] = saved_path
        if saved_module is None:
            sys.modules.pop("bootstrap", None)
        else:
            sys.modules["bootstrap"] = saved_module


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("text", list(COLUMNS), ids=COLUMN_IDS)
def test_each_copy_counts_the_columns_a_terminal_gives(copies, copy, text):
    """`_columns`, which each table pads by. The Thai vowel sign U+0E35 is a
    mark whose combining class is 0, and the voiced sound mark U+3099 a mark
    East Asian width calls wide: each takes no column. The Devanagari vowel
    sign U+093F is a spacing mark, which takes one. The jamo after a
    syllable's first are letters of width N a terminal draws inside the
    syllable: none."""
    assert copies[copy]._columns(text) == COLUMNS[text]


def test_the_two_copies_count_every_character_alike(copies):
    """THE COPIES AGREE: one answer from each for every code point Unicode
    has, the surrogates and the unassigned ones among them, so the rule
    cannot drift in one file while the table above still passes in the
    other."""
    siblings, naming = (copies[copy]._columns for copy in COPIES)
    differ = [f"U+{point:04X}" for point in range(sys.maxunicode + 1)
              if siblings(chr(point)) != naming(chr(point))]
    assert differ == []


@pytest.mark.parametrize("copy", COPIES)
def test_a_text_is_padded_to_its_columns_and_never_cut(copies, copy):
    """`_padded`: an ASCII name as `:<18` pads it, a wide and a combining
    name to 18 columns, and a name of 24 columns, wider than the field,
    with no space added and nothing cut, as `:<18` leaves one."""
    padded = copies[copy]._padded
    assert padded("Atlas", 18) == f"{'Atlas':<18}"
    assert padded(WIDE, 18) == WIDE + " " * 12
    assert padded(COMBINING, 18) == COMBINING + " " * 13
    assert padded(WIDE * 4, 18) == WIDE * 4


class NoEncoding:
    """A stdout a caller replaced, which names no encoding and no handler."""


def stdout_of(spec: str | None):
    """A stdout as `PYTHONIOENCODING` spells one, `encoding:errors`, or,
    for None, one that names neither."""
    if spec is None:
        return NoEncoding()
    encoding, errors = spec.split(":")
    return io.TextIOWrapper(io.BytesIO(), encoding, errors)


@pytest.mark.parametrize("copy", COPIES)
@pytest.mark.parametrize("spec, text, printed", [
    pytest.param(NARROW[0], WIDE, WIDE, id="utf-8-holds-it"),
    pytest.param("ascii:backslashreplace", WIDE,
                 "\\u65e5\\u672c\\u8a9e", id="ascii-escapes-it"),
    pytest.param("ascii:backslashreplace", COMBINING, "e\\u0301cole",
                 id="ascii-escapes-the-mark"),
    pytest.param("utf-8:backslashreplace", "Atl\udcffas", "Atl\\udcffas",
                 id="a-lone-surrogate"),
    pytest.param("ascii:replace", WIDE, "???",
                 id="a-handler-somebody-chose"),
    pytest.param(NARROW[1], WIDE, WIDE,
                 id="a-handler-that-cannot-write-it"),
    pytest.param(None, WIDE, WIDE, id="no-encoding"),
])
def test_a_text_is_measured_as_stdout_writes_it(copies, copy, monkeypatch,
                                                spec, text, printed):
    """`_printed`: what is padded is what stdout will write. An ASCII
    stdout's `backslashreplace` writes each character it lacks as its
    escape, and a UTF-8 one a lone surrogate, which a name read from a byte
    that is not UTF-8 holds. A handler somebody chose writes its own
    replacement. Where the handler cannot write the text, or stdout names no
    encoding, the text is measured as it is."""
    monkeypatch.setattr(sys, "stdout", stdout_of(spec))
    assert copies[copy]._printed(text) == printed


# --- `--explain`'s family rows ---------------------------------------------

def renamed_policy(tmp_path: Path, family_id: str) -> Path:
    """The standard's own naming policy with its `workspace` family's id
    written as `family_id`, a YAML scalar."""
    body = (REPO / "contracts" / "repository-naming.yaml").read_bytes()
    line = b"  - id: workspace\n"
    assert body.count(line) == 1
    path = tmp_path / "repository-naming.yaml"
    path.write_bytes(body.replace(
        line, f"  - id: {family_id}\n".encode("utf-8")))
    return path


def explained(tmp_path: Path, family_id: str, name: str,
              encoding: str) -> tuple[int, list[str]]:
    """`(exit, stdout's lines)` of `--explain name` under the renamed
    policy, its stdout in `encoding`."""
    code, out, err = run_tool(
        NAMING, "--policy", str(renamed_policy(tmp_path, family_id)),
        "--explain", name, encoding=encoding, tmp_path=tmp_path,
        cwd=tmp_path)
    assert "Traceback" not in err, err
    return code, out.split("\n")


#: What the renamed family's pattern is, so its row can be found.
WIP_PATTERN = "^[a-z0-9]+(?:-[a-z0-9]+)*-wip$"


@pytest.mark.parametrize("encoding", NARROW)
@pytest.mark.parametrize("family_id", [WIDE, COMBINING],
                         ids=["wide", "combining"])
@pytest.mark.parametrize("name, prefix, column", [
    pytest.param("zz-wip", "    MATCH ", 29, id="the-family-row"),
    pytest.param("z z", "    ", 23, id="the-no-family-list"),
])
def test_a_family_id_is_padded_by_its_columns(tmp_path, encoding, family_id,
                                              name, prefix, column):
    """A policy may name a family's id in any characters: the rows that pad
    it, a family's row under a name it matches (`_family_row`) and the list
    under a name no family matches (`_no_family_lines`), began the pattern 3
    columns right for the wide id and 1 left for the combining one on a
    UTF-8 stdout, and 15 and 5 right on an ASCII one. Each begins where an
    ASCII id's does now."""
    code, lines = explained(tmp_path, family_id, name, encoding)
    assert code == (0 if name == "zz-wip" else 1), lines
    written = shown(family_id, encoding)
    if written not in COLUMNS:
        assert written.isascii(), written
    takes = COLUMNS.get(written, len(written))
    rows = [line for line in lines if line.endswith(f" {WIP_PATTERN}")]
    assert len(rows) == 1, lines
    assert rows[0].startswith(f"{prefix}{written} "), rows
    pad = len(rows[0]) - len(prefix) - len(written) - len(WIP_PATTERN)
    assert len(prefix) + takes + pad == column, rows


@pytest.mark.parametrize("scalar, printed", [("5", "5"), ("true", "1")],
                         ids=["a-number", "a-boolean"])
def test_an_id_that_is_not_text_is_padded_as_it_always_was(tmp_path, scalar,
                                                           printed):
    """An id YAML reads as a number or a boolean is no text to measure: its
    row is the one `format` always padded it to, byte for byte, `true`
    printed as `1` as `f"{True:<18}"` prints it."""
    code, lines = explained(tmp_path, scalar, "zz-wip", NARROW[0])
    assert code == 0, lines
    assert f"    MATCH {printed:<18} {WIP_PATTERN}" in lines, lines
