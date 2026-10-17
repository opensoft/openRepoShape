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
both cases. Each passage is held WHOLE (`PASSAGES`), as `ONE_SPELLING` is: the
words a never needs to be an exception, "but for a row repair", are the ones a
one-word edit turns back into the contradiction. The validator's remedies are
read from the validator, `member-gitlink-absent` as the refusal it raises, so
a remedy that stops telling the person to edit a row fails here and takes the
docs' exception with it, and so does a copy of `RESTORE_ROW`'s words that no
longer says what the constant does.
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

#: How the shape doc's layout paragraph names the folder (#763): after the
#: holder's repository, which the holder's README says at `:66-70` is what
#: `{{FAMILY}}` is, and not "the family", which `--name` makes a display name.
SHAPE_LAYOUT = "a plain folder named after this holder's repository"

#: What the holder's docs said of the folder before #763: a match that reads
#: as case-insensitive, where `siblings.py` compares the name exactly.
BEFORE_763 = "not named after the family"

#: The folder rule's owner, its subject and its "must", with the words every
#: place says it in: the standard's README and the handbook, and the holder's
#: README and `AGENTS-shape.md` (#763). "named EXACTLY ..." alone would pass a
#: doc that said the folder "need not be" named so, and "parent folder must be"
#: one that gave it to a member's.
FOLDER_RULE = "holder's parent folder must be " + NAMED_EXACTLY

#: Each doc's whole passage on hand-editing `members:`, from its never to
#: whose commit a repair is (#763). A WHOLE SENTENCE, as `ONE_SPELLING` is: the
#: never is an exception, for a row repair `validate-family.py` names, and a
#: doc that kept every word of it but turned the "but for" into "not even for",
#: or the repair into another thing, would say what the validator's remedies
#: say not to do. `AGENTS.md` is at its line cap, so its passage is the
#: shorter; the shape doc names both of the validator's cases.
PASSAGES = {
    "AGENTS.md": (
        "Never hand-edit `family.yaml`'s `members:` block, which the tool "
        "rewrites wholesale, but for a row repair `validate-family.py` "
        "names; the commit is then the person's."),
    SHAPE_DOC: (
        "Do not hand-edit the `members:` block — the tool rewrites it "
        "wholesale — but for a row repair that `validate-family.py` names "
        "in a holder already in a repair state: put back, as git last had "
        "it, a row deleted or whose `path:` was edited by hand (`git log -p "
        "-- family.yaml` shows the change), or take out the row of a member "
        "that is to go (`member-gitlink-absent`); the commit is then the "
        "person's."),
}

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


@pytest.mark.parametrize("path", README_AND_HANDBOOK + HOLDER_DOCS)
def test_the_four_places_say_the_folder_rule_in_the_same_words(path):
    assert FOLDER_RULE in shown(path)


@pytest.mark.parametrize("path", HOLDER_DOCS)
def test_the_holders_own_docs_no_longer_say_not_named_after_the_family(path):
    assert BEFORE_763 not in shown(path)


def test_the_shape_docs_layout_names_the_folder_after_the_repository():
    assert SHAPE_LAYOUT in shown(SHAPE_DOC)


@functools.cache
def validator():
    """`validate-family.py` as a holder carries it, loaded with no bytecode."""
    return load_without_bytecode(VALIDATOR, "validate_family_hand_repair_docs")


@pytest.mark.parametrize("path", PASSAGES)
def test_each_doc_says_its_hand_edit_passage_whole(path):
    assert PASSAGES[path] in shown(path)


@pytest.mark.parametrize("case", [RESTORE_ROW_CASE, ROW_OUT_CASE,
                                  GITLINK_ABSENT])
def test_the_shape_doc_passage_names_both_of_the_validators_cases(case):
    assert case in PASSAGES[SHAPE_DOC]


@pytest.fixture
def refusal(tmp_path, monkeypatch):
    """The refusal the validator raises for a row whose gitlink is not there,
    through `_check_member_gitlink`, which gives it its code and its remedy
    (no repository is needed: HEAD is then unlistable, `recorded_gitlink`
    finds none and the remedy writes the `.gitmodules` section)."""
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    module = validator()
    with pytest.raises(module.Refusal) as caught:
        module._check_member_gitlink(tmp_path, "members/IRQS", "0" * 40,
                                     "IRQS", "acme/IRQS", {}, None, "rule")
    return caught.value


def test_member_gitlink_absent_is_raised_telling_the_person_to_edit_the_row(
        refusal):
    assert refusal.code == GITLINK_ABSENT
    text = " ".join(str(refusal).split())
    assert re.search(REMEDY_SENTENCES[GITLINK_ABSENT], text), (
        f"{GITLINK_ABSENT} no longer tells a person to edit a row by hand: "
        "the docs' exception for the validator's repair goes with it")
    assert ROW_OUT_CASE in text


def test_restore_row_still_tells_the_person_to_edit_a_row_by_hand():
    text = " ".join(validator().RESTORE_ROW.split())
    assert re.search(REMEDY_SENTENCES["RESTORE_ROW"], text), (
        "RESTORE_ROW no longer tells a person to edit a row by hand: the "
        "docs' exception for the validator's repair goes with it")
    assert RESTORE_ROW_CASE in text


def test_every_inline_copy_of_restore_rows_words_is_what_the_constant_says():
    """`gitmodules-path-unnamed` spells the first words of `RESTORE_ROW` out in
    its own text, not through the constant, so a change to one that missed the
    other would send a person two ways. Each string the validator holds that
    begins as `RESTORE_ROW` does is read against it."""
    source = VALIDATOR.read_text(encoding="utf-8")
    constant = " ".join(validator().RESTORE_ROW.split())
    opening = constant[:len("If its row was deleted")]
    copies = [" ".join(node.value.split())
              for node in ast.walk(ast.parse(source))
              if isinstance(node, ast.Constant)
              and isinstance(node.value, str)
              and node.value.strip().startswith(opening)]
    assert len(copies) >= 2, "the constant and its inline copy"
    for copy in copies:
        assert constant.startswith(copy.rstrip("."))
