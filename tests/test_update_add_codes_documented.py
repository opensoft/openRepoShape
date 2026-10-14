# SPDX-License-Identifier: Apache-2.0
"""The `update-add-*` codes the documents name are the ones `apply --add` gives (#429).

`update-shape.py apply --add <path>` refuses in five ways, each with a code of
its own that a person meets on stderr as `REFUSED update-add-...`:
`update-add-already-pinned`, `update-add-not-upstream`, `update-add-symlink`
(#239), `update-add-not-a-directory` (#285) and `update-add-would-overwrite`.
README.md and `docs/handbook.html` list them in one sentence each, and for
months that sentence named three: #269 and #346 each added a refusal and left
both documents alone, so a reader who met `update-add-symlink` or
`update-add-not-a-directory` found no sentence for it, and the list read as
complete (#429). Nothing tied the sentence to the tool.

This is the guard, in both directions, and it is the kind this repository
already keeps for AGENTS.md's codes (`tests/test_agents_md_codes.py`):

- every `update-add-*` code the tool raises is named in README.md, in
  backticks, and in `docs/handbook.html`, in `<code>`: a refusal added
  tomorrow fails here until both documents say so;
- every `update-add-*` token either document spells is a code the tool raises:
  a misspelt or renamed one fails here, naming the token and the document.

WHICH CODES THE TOOL RAISES. An exact `str` constant in `update-shape.py`'s
syntax tree whose whole text is `update-add-` followed by lowercase words, found
with `ast` and never a grep, so a comment or a docstring that merely names a
code cannot satisfy it, and nothing runs: no process, no git, no network, the
same on every platform. `FLOOR` is the five the tool raises today, so a scan
that stopped finding them (a rename, a code built from pieces) fails by name
here and does not turn into a test that checks nothing.

WHICH TOKENS A DOCUMENT SPELLS. Any `update-add-` followed by lowercase words
joined by hyphens, anywhere in its text. A new document naming a code is held
to the tool without anybody adding it to a list here.
"""

from __future__ import annotations

import ast
import re

from conftest import REPO

#: What an `update-add-*` code looks like: the prefix, then lowercase words
#: joined by hyphens. `fullmatch`ed against a constant, `findall`ed in a
#: document.
CODE = r"update-add-[a-z]+(?:-[a-z]+)*"

#: The codes the tool raises today. The scan must find at least these.
FLOOR = frozenset({
    "update-add-already-pinned",
    "update-add-not-upstream",
    "update-add-symlink",
    "update-add-not-a-directory",
    "update-add-would-overwrite",
})

#: The documents that list the refusals, each with how it spells a code: a
#: backticked span in the README, a `<code>` element in the handbook.
DOCUMENTS = {
    "README.md": "`{}`",
    "docs/handbook.html": "<code>{}</code>",
}


def raised_codes() -> frozenset[str]:
    """The `update-add-*` codes `update-shape.py` holds as whole constants."""
    tree = ast.parse((REPO / "update-shape.py").read_bytes())
    return frozenset(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and re.fullmatch(CODE, node.value))


def document_text(name: str) -> str:
    """A document's text, read as bytes and decoded as UTF-8, so a Windows
    checkout's locale cannot change what is read."""
    return (REPO / name).read_bytes().decode("utf-8")


def unnamed(raised: frozenset[str], documents: dict[str, str]) -> list[str]:
    """One line per code in `raised` that a document does not spell its way."""
    return [f"{name} does not name {code} (as {DOCUMENTS[name].format(code)})"
            for name, text in sorted(documents.items())
            for code in sorted(raised)
            if DOCUMENTS[name].format(code) not in text]


def not_raised(raised: frozenset[str], documents: dict[str, str]) -> list[str]:
    """One line per `update-add-*` token a document spells that is no code in
    `raised`."""
    return [f"{name} spells {token}, which update-shape.py does not raise"
            for name, text in sorted(documents.items())
            for token in sorted(set(re.findall(CODE, text)) - raised)]


def test_the_scan_finds_the_codes_the_tool_raises():
    missing = sorted(FLOOR - raised_codes())
    assert not missing, (
        f"update-shape.py no longer holds {missing} as a whole string "
        "constant. If a refusal was renamed, rename it in README.md, in "
        "docs/handbook.html and in FLOOR here; a code built from pieces "
        "cannot be found, and a refusal nobody can search for is the gap "
        "this test exists to close (#429)")


def test_every_add_refusal_code_the_tool_raises_is_named_in_both_documents():
    documents = {name: document_text(name) for name in DOCUMENTS}
    problems = unnamed(raised_codes(), documents)
    assert not problems, (
        "\n".join(problems) + "\n`apply --add` gives each of these refusals; "
        "README.md's and the handbook's sentence about them must name every "
        "one with what it refuses, so a reader who meets one finds it (#429)")


def test_every_add_refusal_code_a_document_spells_is_one_the_tool_raises():
    documents = {name: document_text(name) for name in DOCUMENTS}
    problems = not_raised(raised_codes(), documents)
    assert not problems, "\n".join(problems)


def test_a_code_the_tool_raises_and_a_document_omits_is_named_with_its_document():
    raised = frozenset({"update-add-symlink", "update-add-brand-new"})
    documents = {
        "README.md": "`update-add-symlink` and `update-add-brand-new`",
        "docs/handbook.html": "<code>update-add-symlink</code> only",
    }
    assert unnamed(raised, documents) == [
        "docs/handbook.html does not name update-add-brand-new "
        "(as <code>update-add-brand-new</code>)"]


def test_a_misspelt_code_fails_naming_the_token_and_the_document():
    raised = frozenset({"update-add-symlink"})
    documents = {
        "README.md": "`update-add-symlink` and `update-add-symlnk`",
        "docs/handbook.html": "<code>update-add-symlink</code>",
    }
    assert not_raised(raised, documents) == [
        "README.md spells update-add-symlnk, which update-shape.py does not "
        "raise"]


def test_a_code_that_is_only_a_prefix_of_a_longer_one_does_not_satisfy_it():
    raised = frozenset({"update-add-symlink"})
    documents = {"README.md": "`update-add-symlink-loop`",
                 "docs/handbook.html": "<code>update-add-symlink-loop</code>"}
    assert unnamed(raised, documents) != []
    assert not_raised(raised, documents) != []
