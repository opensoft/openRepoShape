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

THE HOLDER'S OWN DOCS (#763). The holder's README and its pinned
`AGENTS-shape.md` said the parent folder was "not named after the family",
which reads as a match that ignores case, where `siblings.py` compares the
name exactly and has a separate branch for a folder that differs only in
case. Both now say the standard's words: named EXACTLY after its repository,
case included, on every disk.

THE HAND REPAIR OF A ROW (#763). `AGENTS.md` and the holder's
`AGENTS-shape.md` say never to hand-edit `family.yaml`'s `members:` block,
and `validate-family.py` has two remedies that tell a person to: `RESTORE_ROW`
(a row deleted, or its `path:` edited, by hand is put back as git last had
it) and `member-gitlink-absent`'s (the row of a member that is to go is taken
out by hand). The never is true of the normal path, where `add`, `bump` and
`remove` rewrite the block; the remedies are for a holder already in a repair
state. So each doc keeps its never and names the validator's repair beside
it, and says whose commit that is; the shape doc, which has the room, names
both cases. The validator's remedies are read from the validator, so a remedy
that stops telling the person to edit a row fails here and takes the docs'
exception with it.
"""

from __future__ import annotations

import ast
import functools
import html
import re

import pytest

from conftest import REPO, load_without_bytecode

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

HOLDER_README = "templates/family-root/README.md"
SHAPE_DOC = "templates/family-root/AGENTS-shape.md"
HOLDER_DOCS = [HOLDER_README, SHAPE_DOC]

#: What the holder's docs said of the folder before #763: a match that reads
#: as case-insensitive, where `siblings.py` compares the name exactly.
BEFORE_763 = "not named after the family"

#: The sentence each doc says the normal path in: the tool rewrites the block.
NEVER_HAND_EDIT = {
    "AGENTS.md": "Never hand-edit `family.yaml`'s `members:` block",
    SHAPE_DOC: "Do not hand-edit the `members:` block",
}

#: How both docs end the clause that names the validator's repair.
WHOSE_COMMIT = "the commit is then the person's"

#: The longest a doc may take between its never and whose commit a repair is
#: for the two to be one passage and not a never with a stray phrase far below.
PASSAGE_LIMIT = 700

#: The validator's two remedies that tell a person to edit a row by hand, and
#: the words of each that the shape doc takes its two cases from. `RESTORE_ROW`
#: is printed by `member-gitlink-unnamed`; the other is the remedy of
#: `member-gitlink-absent` (#681), whose code the shape doc names.
RESTORE_ROW_CASE = "as git last had it"
ROW_OUT_CASE = "is to go"
GITLINK_ABSENT = "member-gitlink-absent"
VALIDATOR = (REPO / "templates" / "family-root" / "scripts" /
             "validate-family.py")

#: The sentence of each remedy that tells a person to edit a row by hand, as a
#: pattern. `member-gitlink-absent`'s remedy says "by hand" of a `.gitmodules`
#: section too, so the phrase alone would not show that the row's is there.
REMEDY_SENTENCES = {
    "RESTORE_ROW": r"edited by hand, put the row back as git last had it",
    GITLINK_ABSENT: r"If it is to go, take its row out of \S+ by hand",
}


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


@pytest.mark.parametrize("path", HOLDER_DOCS)
def test_the_holders_own_docs_say_the_folder_is_named_exactly(path):
    assert NAMED_EXACTLY in shown(path)


@pytest.mark.parametrize("path", HOLDER_DOCS)
def test_the_holders_own_docs_no_longer_say_not_named_after_the_family(path):
    assert BEFORE_763 not in shown(path)


@functools.cache
def validator():
    """`validate-family.py` as a holder carries it, loaded with no bytecode."""
    return load_without_bytecode(VALIDATOR, "validate_family_hand_repair_docs")


def hand_edit_passage(path: str) -> str:
    """What `path` says from its never to whose commit a repair is, on one
    line: the passage that has to hold the validator's repair, found by the
    words of the never and the words that close the clause."""
    said = shown(path)
    start = said.find(NEVER_HAND_EDIT[path])
    assert start >= 0, f"{path} no longer says never to hand-edit `members:`"
    end = said.find(WHOSE_COMMIT, start)
    assert end >= 0, (
        f"{path} says never to hand-edit `members:` and not whose commit "
        f"a repair the validator names is ({WHOSE_COMMIT!r})")
    passage = said[start:end + len(WHOSE_COMMIT)]
    assert len(passage) <= PASSAGE_LIMIT, (
        f"{path}: the never and {WHOSE_COMMIT!r} are {len(passage)} "
        f"characters apart, more than one passage")
    return passage


@pytest.mark.parametrize("path", NEVER_HAND_EDIT)
def test_each_doc_keeps_its_never_for_the_tool_rewriting_the_block(path):
    assert "wholesale" in hand_edit_passage(path)


@pytest.mark.parametrize("path", NEVER_HAND_EDIT)
def test_the_never_names_the_repair_the_validator_makes_of_a_row(path):
    passage = hand_edit_passage(path)
    assert "validate-family.py" in passage
    assert "repair" in passage


@pytest.mark.parametrize("case", [RESTORE_ROW_CASE, ROW_OUT_CASE,
                                  GITLINK_ABSENT])
def test_the_shape_doc_names_both_of_the_validators_cases(case):
    assert case in hand_edit_passage(SHAPE_DOC)


@pytest.fixture
def remedies(tmp_path, monkeypatch) -> dict[str, str]:
    """The text of the validator's two remedies, as it prints them: the
    constant `RESTORE_ROW`, and what `member-gitlink-absent` is given for a
    row whose gitlink is not there (no repository is needed: HEAD's
    `.gitmodules` is then unreadable, and the remedy writes the section)."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    module = validator()
    put_back = module._gitlink_put_back(tmp_path, "members/IRQS", "0" * 40,
                                        "acme/IRQS")
    return {"RESTORE_ROW": module.RESTORE_ROW,
            GITLINK_ABSENT: put_back}


@pytest.mark.parametrize("remedy, case", [("RESTORE_ROW", RESTORE_ROW_CASE),
                                          (GITLINK_ABSENT, ROW_OUT_CASE)])
def test_each_remedy_still_tells_the_person_to_edit_a_row_by_hand(
        remedies, remedy, case):
    text = " ".join(remedies[remedy].split())
    assert re.search(REMEDY_SENTENCES[remedy], text), (
        f"{remedy} no longer tells a person to edit a row by hand: the "
        "docs' exception for the validator's repair goes with it")
    assert case in text


def test_member_gitlink_absent_is_a_code_the_validator_prints():
    source = VALIDATOR.read_text(encoding="utf-8")
    held = {node.value for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert GITLINK_ABSENT in held
