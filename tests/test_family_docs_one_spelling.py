# SPDX-License-Identifier: Apache-2.0
"""The family docs say what `init`, `make siblings` and `members/` do (#695).

Three sentences had fallen behind the tools, and one rule had no sentence:

- `init` lands where you stand, and refuses that default inside a checkout of
  this standard (`family-landing-in-standard`, #488). README and the
  handbook gave the default and not the refusal.
- `make siblings` stops before it clones anything, and a family folder
  reached through a link of the family's name passes (#578). README and the
  handbook still said it WARNS and prints the `mv`. They now also say the
  folder is named EXACTLY after the repository on every disk, and where the
  printed move puts the family folder for a holder straight in a folder.
- A holder keeps `members/` in ONE spelling on every disk, and `add`
  refuses `family-members-dir-variant` (`member-path-taken` for a variant of
  the member's own path) until a human renames the entries (#574). No doc
  said so.

THE SAME WORDS IN FIVE PLACES. The one-spelling sentence is the same text in
AGENTS.md, README.md, the handbook, the holder's README and the holder's
pinned `AGENTS-shape.md`, so a reader meets one rule however they came. The
handbook spells it in HTML, so it is read as the text a browser shows, with
`<code>` as backticks.

The printed move itself is pinned by `test_family_siblings_placement.py`
(`~/projects/InkRouter` becomes `~/InkRouter/InkRouter`): this file holds the
sentences that describe it.
"""

from __future__ import annotations

import ast
import html
import re

import pytest

from conftest import REPO

ONE_SPELLING = (
    "A holder keeps `members/` in ONE spelling on every disk: `add` refuses "
    "`family-members-dir-variant` (`member-path-taken` for a variant of the "
    "member's own path) until a human renames what sits under another "
    "spelling.")

INTO_REFUSED = (
    "(the directory you are standing in, by default; refused inside a "
    "checkout of this standard, `family-landing-in-standard`)")

STOPS_BEFORE_CLONING = (
    "When it is not, and no link of that name beside it leads to it, "
    "`make siblings` WARNS, prints the exact `mv` for a human to run and "
    "clones nothing until it is run, so the next run clones each member "
    "once.")

NAMED_EXACTLY = (
    "named EXACTLY after its repository, case included, on every disk")

STRAIGHT_IN_A_FOLDER = (
    "For a holder straight in a folder (`~/projects/InkRouter`) the move "
    "makes the family folder `~/InkRouter`, beside `~/projects`, and the "
    "holder `~/InkRouter/InkRouter`, not `~/projects/InkRouter/InkRouter`.")

#: What README and the handbook said before #578, which `make siblings` no
#: longer does.
BEFORE_578 = "`make siblings` WARNS and prints the exact `mv`"

HANDBOOK = "docs/handbook.html"
README = "README.md"
THE_FIVE = [
    "AGENTS.md", README, HANDBOOK, "templates/family-root/README.md",
    "templates/family-root/AGENTS-shape.md"]
README_AND_HANDBOOK = [README, HANDBOOK]


def shown(path: str) -> str:
    """The text a reader sees in `path`, on one line.

    A page is read as a browser shows it: `<code>` is a backtick, any other
    tag is nothing, entities are their characters and a curly apostrophe is
    a straight one. Every other file is its own text. Runs of white space,
    and so every wrap, are one space."""
    text = (REPO / path).read_text(encoding="utf-8")
    if path == HANDBOOK:
        text = re.sub(r"</?code>", "`", text)
        text = html.unescape(re.sub(r"<[^>]+>", "", text))
        text = text.replace("’", "'")
    return " ".join(text.split())


@pytest.mark.parametrize("path", THE_FIVE)
def test_each_doc_names_the_one_spelling_rule_in_the_same_words(path):
    assert ONE_SPELLING in shown(path)


@pytest.mark.parametrize("code", ["family-members-dir-variant",
                                  "member-path-taken"])
def test_the_codes_the_rule_names_are_codes_family_py_prints(code):
    source = (REPO / "scripts" / "family.py").read_text(encoding="utf-8")
    held = {node.value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert code in held


@pytest.mark.parametrize("path", README_AND_HANDBOOK)
def test_the_into_sentence_gives_the_refusal_with_the_default(path):
    assert INTO_REFUSED in shown(path)


@pytest.mark.parametrize("path", README_AND_HANDBOOK)
def test_make_siblings_is_described_as_it_stops_before_cloning(path):
    assert STOPS_BEFORE_CLONING in shown(path)


@pytest.mark.parametrize("path", README_AND_HANDBOOK)
def test_the_stale_warns_and_prints_sentence_is_gone(path):
    assert BEFORE_578 not in shown(path)


@pytest.mark.parametrize("path", README_AND_HANDBOOK)
def test_the_folder_is_named_exactly_after_the_repository(path):
    assert NAMED_EXACTLY in shown(path)


@pytest.mark.parametrize("path", README_AND_HANDBOOK)
def test_the_move_for_a_holder_straight_in_a_folder_is_one_level_up(path):
    assert STRAIGHT_IN_A_FOLDER in shown(path)
