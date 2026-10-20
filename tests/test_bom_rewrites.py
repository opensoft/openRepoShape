# SPDX-License-Identifier: Apache-2.0
"""A pin or a manifest whose first line is its key after a byte-order mark
is rewritten, and the mark is kept (#933).

THE DEFECT, measured on main dc7cd49b7 by calling the three line rewriters
in process. Since #855 `parse_yaml` takes off every U+FEFF the text starts
with, so `check`, `load_yaml` and both validators read such a file. The
rewriters found their key at column 0 of the raw text, which their tools
read as `utf-8`, so the mark was the key's first character and each said
the key was not there:

- `update-shape.py`'s `rewrite_shape_pin`, on a shape pin whose first line
  is `commit:`: `update-pin-unrecognised`, "0 `commit` line(s)";
- its `rewrite_manifest`, on a `project.yaml` whose first line is
  `shape:`, through `_shape_block_bounds` and `_is_block_header`:
  `update-manifest-no-shape`, "has no `shape:` block";
- `scripts/bump-leg.py`'s `rewrite_pin`, on a leg pin whose first line is
  `commit:`: `bump-leg-pin-unrecognised`, "0 `commit` line(s)".

THE RULE NOW. Each takes the marks off the start of the text, as the reader
does, finds its key, and puts the marks back in front of what it returns,
so they are written back byte for byte. A file with no mark is rewritten
as it always was. A mark anywhere else is text, to the reader and to the
finders, and keeps today's answer.

Every mark is written by this file as bytes (`codecs.BOM_UTF8`), never
typed. Each file is the scaffold's rendering
(`tests/test_pin_rewrite_layout.py`) with the key moved to line 1, where
no template puts it.
"""

from __future__ import annotations

import codecs
from typing import NamedTuple

import pytest

from test_pin_rewrite_layout import MANIFEST as MANIFEST_TEXT
from test_pin_rewrite_layout import (  # noqa: F401
    NEW_COMMIT, NEW_ROWS, NEW_TREE, OLD_COMMIT, OLD_ROWS, OLD_TREE, make_pin,
    refusal_code, rewrite, tools,
)

from repo_shape import Refusal
from shape_materialize import pin_values_in

MARK = codecs.BOM_UTF8
#: The mark as the one character the reader reads it as, U+FEFF.
MARK_TEXT = MARK.decode("utf-8")
#: A line a person may put above the first key before saving the file.
COMMENT = "# saved by hand\n"
#: The leg's own `commit:` in the manifest, above its `shape:` block.
MEMBER = "e" * 40


class Finder(NamedTuple):
    #: The key its file's line 1 holds here.
    key: str
    #: The block the validator reads the pin under.
    within: tuple
    #: The scaffold's pin kind, or None for the manifest.
    kind: str | None
    #: What it says of a file it finds no key in.
    refused: str


FINDERS = {
    "shape-pin-commit": Finder("commit", (), "assembly shape pin",
                               "has 0 `commit` line(s)"),
    "manifest-shape-header": Finder("shape", ("shape",), None,
                                    "has no `shape:` block"),
    "leg-pin-commit": Finder("commit", (), "spec pin",
                             "has 0 `commit` line(s)"),
}


def key_first(text: str, key: str) -> str:
    """`text` with its column-0 `<key>:` line, and the block under it, moved
    to line 1: an order the reader ignores and no template writes."""
    lines = text.split("\n")
    start = next(index for index, line in enumerate(lines)
                 if line.startswith(f"{key}:"))
    end = next((index for index in range(start + 1, len(lines))
                if lines[index] and not lines[index].startswith(" ")),
               len(lines))
    return "\n".join(lines[start:end] + lines[:start] + lines[end:])


def the_file(finder: str, commit: str, tree: str, rows) -> str:
    """The finder's file pinned at `commit` and `tree`, its key on line 1."""
    key, _within, kind, _refused = FINDERS[finder]
    if kind is None:
        text = MANIFEST_TEXT.format(member=MEMBER, commit=commit, tree=tree)
    else:
        text = make_pin(kind, commit, tree, rows)
    return key_first(text, key)


def rewritten(loaded, finder: str, text: str) -> str:
    """The finder's rewriter onto the target, called as its tool calls it;
    `loaded` is the `tools` fixture."""
    kind = FINDERS[finder].kind
    if kind is None:
        return loaded.update_shape.rewrite_manifest(
            text, NEW_COMMIT, NEW_TREE, loaded.update_shape.PROJECT_KIND)
    return rewrite(loaded, kind, text, NEW_COMMIT, NEW_TREE)


def read(finder: str, text: str) -> tuple[str, str]:
    """`commit` and `digests.tree_sha256`, where the validator reads them."""
    return pin_values_in(text, FINDERS[finder].within)


@pytest.mark.parametrize("marks", [1, 2], ids=["mark", "two-marks"])
@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_first_key_after_the_mark_is_rewritten_and_the_mark_kept(
        tools, finder, marks):  # noqa: F811
    """THE ISSUE'S THREE LINES. The file every reader reads is rewritten:
    its first bytes are the marks it had, every byte after them is the
    rewrite of the same file without them, and the validator reads the
    target. Two marks are taken off and put back as one is, as the reader
    takes off every mark the text starts with."""
    before = MARK_TEXT * marks + the_file(finder, OLD_COMMIT, OLD_TREE,
                                          OLD_ROWS)
    assert read(finder, before) == (OLD_COMMIT, OLD_TREE), (
        "fixture: the reader reads the marked file")

    new = rewritten(tools, finder, before)

    assert new.encode("utf-8") == MARK * marks + the_file(
        finder, NEW_COMMIT, NEW_TREE, NEW_ROWS).encode("utf-8")
    assert read(finder, new) == (NEW_COMMIT, NEW_TREE)


@pytest.mark.parametrize("finder", list(FINDERS))
def test_the_same_file_without_the_mark_is_rewritten_as_before(
        tools, finder):  # noqa: F811
    """THE CONTROL, which passes on main as well: with no mark, what is
    returned is the file at the target, with not a byte in front of it."""
    before = the_file(finder, OLD_COMMIT, OLD_TREE, OLD_ROWS)

    new = rewritten(tools, finder, before)

    assert new == the_file(finder, NEW_COMMIT, NEW_TREE, NEW_ROWS)
    assert read(finder, new) == (NEW_COMMIT, NEW_TREE)


@pytest.mark.parametrize("finder", list(FINDERS))
def test_a_mark_after_line_1_keeps_todays_answer(tools, finder):  # noqa: F811
    """LINE 1 ONLY. A mark on line 2, in front of the key, is the key's
    first character to the reader, which reads no pin there; each finder
    refuses the file as it did before, in its own words."""
    before = COMMENT + MARK_TEXT + the_file(finder, OLD_COMMIT, OLD_TREE,
                                            OLD_ROWS)
    with pytest.raises(ValueError):
        read(finder, before)

    with pytest.raises(Refusal) as refused:
        rewritten(tools, finder, before)

    kind = FINDERS[finder].kind
    assert refused.value.code == (
        "update-manifest-no-shape" if kind is None else refusal_code(kind))
    assert FINDERS[finder].refused in refused.value.detail
