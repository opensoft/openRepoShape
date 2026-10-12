# SPDX-License-Identifier: Apache-2.0
"""A code AGENTS.md spells is a code a tool prints (#348).

`AGENTS.md` is the procedure an assistant reads before it acts, and since #288
(PR #309) section 2 names two refusals by their codes, `scaffold-leg-path-
collides` and `scaffold-pin-collides`, so that the assistant can foresee them
from the flags it was given and RELAY them rather than choose another value.
An assistant matches the sentence it was briefed with against the refusal in
front of it; a code spelt in the brief the way no tool prints it is a
sentence it cannot match. Nothing tied the two. The only other test that
opens this repository's `AGENTS.md` asserts its line cap and a few fixed
phrases, and the tests that assert the codes read them from the tool's own
output, so a misspelling in `AGENTS.md` passed every test (the review of #309
misspelt both and got 63 passed), and so did renaming either code in
`scaffold-project.py` and fixing its own tests' constants.

This is the guard, in both directions, and it is the kind this repository
already keeps for other copied facts: the Windows two-liner's file names, the
handbook's README blob, and `docs/cli.md` against `--help`
(`tests/test_cli_reference.py`).

WHICH NAMES. Every backticked token in the document whose whole text matches
`CODE_SHAPE` (`[a-z]+(-[a-z0-9]+)+`), never a pattern read out of a refusal
site and never a list of two: a code added to `AGENTS.md` tomorrow is held to
the tools without anybody remembering to add it here. The verdict words
`update-shape.py` and the doctor print (`upstream-changed`, `upstream-added`,
`locally-modified`) match the shape and are checked exactly like refusal
codes, because AGENTS.md copies them for the same reason. A token the shape
matches that is NOT a code a tool prints goes on `NOT_A_CODE_A_TOOL_PRINTS`
with its reason, and the test keeps that list honest: an entry that a tool
DOES print, or that no document names any more, fails the run as stale.

WHICH SPANS ARE BACKTICKED, AND WHY THIS IS NOT ONE REGEX. A backtick that
Markdown renders literally must not blind the scan, and in a document-wide
pairing it does: one stray backtick pairs with the opener of the next real
span, every span after it is paired off by one and read as the text between
two spans, and a misspelt code is simply not seen (the review of #396 made two
such backticks turn a misspelt `upstream-changed` into 22 passed). The
standard library has no Markdown parser and CI installs pytest and nothing
else, so `prose_blocks` and `code_spans` are a SUBSET of CommonMark, and this
is the whole of it:
- Backticks pair only inside one block. A blank line, an ATX heading, a
  thematic break or setext underline, a table row, a list marker (bullets
  always; an ordered marker other than `1.` only when a list is open, as it
  cannot interrupt a paragraph), a fence and an HTML comment each end the
  block before them. A wrapped paragraph is one block; a table CELL is one.
  A table is a header row with a pipe and a delimiter row of as many cells
  under it; any other line with a pipe is a paragraph line. A table row
  directly after a list item's paragraph line is that paragraph's lazy
  continuation, not a table.
- A run of N backticks opens a span that the next run of EXACTLY N closes,
  and a run nothing closes is literal. A backslash before an ASCII
  punctuation character is an escape, so `\\`` never opens a span; a backslash
  inside a span escapes nothing.
- Fenced blocks are not read: three or more backticks or tildes, indented at
  most three spaces, a backtick fence's info string holding no backtick. A
  fence closes only on a line of the SAME character with at least the opening
  length; an unterminated fence runs to the end, except that one inside a list
  item ends where the item does.
- Indented code (four columns, with no paragraph open and no list open),
  HTML comments (as a block, which runs to the line holding `-->`, and
  inline) and autolinks (`<scheme:...>`, `<name@host>`) are not read, and a
  backtick in any of them is literal.
NOT implemented: block quotes as containers, link reference definitions,
entity references, raw HTML other than comments, empty list items, and the
finer rules of nested lists, so a document that leans on those can read
differently from CommonMark. A list is "open" while a line indented two or
more columns follows it, a tab is expanded to a multiple of four columns
whatever it stands in, and a fence or indented code inside a NESTED item is
read by that approximation. Checked by hand against markdown-it-py, which is
no dependency and is not in CI: on 2026-10-12 this extracts from `AGENTS.md`
the same 270 spans CommonMark does, in the same order, and every case below
that spells a CommonMark fact holds in markdown-it-py too.

WHAT "PRINTS IT" MEANS. The token is an exact `str` constant somewhere in a
shipped tool's Python source, found with `ast` - never a grep, so a comment
cannot satisfy it, and never by running a tool, so it needs no process and no
git, holds on Windows, and cannot reach a network. A docstring does not count
(the doctor's module docstring names `prefer-triad-project-shape` and prints
it nowhere), and neither does a fragment of an f-string, which is a piece of a
computed string and not a string anybody can print whole. A longer constant
that merely CONTAINS the token does not count either: "prints it" is "holds
it as one value", which is how every refusal site holds its code
(`Refusal("scaffold-pin-collides", ...)`) and how `update-shape.py` holds its
verdict words (`UPSTREAM_CHANGED = "upstream-changed"`). The tests in this
repository are NOT tools: they hold the same strings, and counting them would
let a rename in the tool pass by editing a test's constant, which is the case
this exists to catch.

WHICH TOOLS. The Python tools `tests/test_repo_hygiene.py::SHIPPED` names,
read from that constant and not listed again here: a second list of the
shipped tools would be a second place to forget one, and `SHIPPED` already
carries the one that no glob finds (`bootstrap`, a Python file with no
extension). NOT checked: `setup.sh`, the `openRepoShape` wrapper and the
template Makefiles. A code printed only by one of those is a code this test
cannot see, and the natural response to its failure would be to allow-list it,
after which nothing would check its spelling; whoever adds one there needs to
read this paragraph.

WHICH DOCUMENTS. `AGENTS.md` alone (`DOCUMENTS`); #309 deliberately put the
codes there and nowhere else. `README.md` and `docs/handbook.html` are a
possible extension, not a free one: on 2026-10-12 the same shape matched a
dozen names in the README and as many `<code>` elements in the handbook, and
several of each are not codes (`macos-latest`, `export-ignore`,
`xf-project-atlas`, `setup-openspeckit`), so either wants its own allowlist
and, for the handbook, an extractor that reads `<code>` rather than backticks.
"""

from __future__ import annotations

import ast
import difflib
import functools
import re
from collections.abc import Mapping

import pytest

from conftest import REPO

#: The documents whose backticked tokens are held to the tools, by name
#: relative to the repository root. One today; see the module docstring.
DOCUMENTS = ("AGENTS.md",)

#: What a refusal code or a verdict word looks like: lowercase words joined
#: by hyphens, at least two of them. `fullmatch`ed against a whole span, so
#: `--org`, `contracts/spec-pin.yaml`, `single-repository.yaml` and
#: `<user>-wip` are not names and never need an entry below.
CODE_SHAPE = re.compile(r"[a-z]+(-[a-z0-9]+)+")

#: A code-shaped name `AGENTS.md` spells that is NOT a code a tool prints,
#: each with its reason. Verdict words a tool prints are checked, never
#: listed here. The test fails an entry that a tool does print and an entry
#: no document names any more, so the list cannot rot into a place where a
#: misspelling hides. It may be EMPTY: the day `AGENTS.md` stops citing the
#: ruling id below, the entry goes and the dict is `{}`.
NOT_A_CODE_A_TOOL_PRINTS = {
    "prefer-triad-project-shape": (
        "an openxFactory ruling id (Brett Heap, 2026-10-06), cited so a "
        "reader can find the ruling; the tools name it in comments and "
        "docstrings and print it nowhere"),
}

#: Where a failure says to put a name that is no code, so the three messages
#: that mention the list cannot name two different places.
ALLOWLIST_NAME = "NOT_A_CODE_A_TOOL_PRINTS in tests/test_agents_md_codes.py"

#: Tools this test must be reading, whatever `SHIPPED` is refactored into: the
#: ones that print the codes `AGENTS.md` spells today, one of each kind of
#: place a tool lives (root, `scripts/`, each root template's `scripts/`),
#: and the extensionless one. A tool dropped from `SHIPPED` (or a filter that
#: forgot a kind of place) fails here by name instead of making every code it
#: printed look unprinted, or, worse, an allow-list entry look right.
KNOWN_TOOLS = (
    "adopt-project.py",
    "bootstrap",
    "scaffold-project.py",
    "shape-doctor.py",
    "update-shape.py",
    "scripts/bump-leg.py",
    "scripts/family.py",
    "templates/assembly-root/scripts/validate-pins.py",
    "templates/family-root/scripts/validate-family.py",
)


# --- which backticks are code spans: a subset of CommonMark ----------------

#: A fence: three or more backticks or tildes, indented at most three spaces,
#: then an info string. A backtick fence's info string holds no backtick,
#: which `prose_blocks` checks, or the line is prose with a span in it.
FENCE_OPEN = re.compile(r" {0,3}(`{3,}|~{3,})(.*)")
FENCE_CLOSE = re.compile(r" {0,3}(`{3,}|~{3,})[ \t]*")
HEADING = re.compile(r" {0,3}#{1,6}(?:[ \t]|$)")
#: A thematic break (`---`, `* * *`, `___`), and a setext underline (`===`
#: or `---` under a paragraph): each ends the block it follows, with no
#: blank line needed.
RULE = re.compile(r" {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*")
UNDERLINE = re.compile(r" {0,3}[-=]+[ \t]*")
#: A list marker and some text after it, at any indent: whether the indent is
#: allowed is `prose_blocks`'s decision, because it depends on an open list.
LIST_ITEM = re.compile(r" *(?:[-+*]|(\d{1,9})[.)])[ \t]+\S")

#: A table's delimiter row (`|---|:--:|`), which must have a pipe in it and
#: as many cells as the header row above it, or the lines are a paragraph.
TABLE_DELIMITER = re.compile(
    r" {0,3}\|?[ \t]*:?-+:?[ \t]*(?:\|[ \t]*:?-+:?[ \t]*)*\|?[ \t]*")

#: What the inline scan skips whole, because a backtick inside it is literal:
#: a backslash escape of an ASCII punctuation character, an HTML comment, a
#: URI autolink, an email autolink; and, last, a run of backticks, which is
#: what the scan is looking for. The first alternative to match at the
#: leftmost position wins, so a backtick that follows a backslash is consumed
#: with it, and what is left of its run opens a span.
INLINE = re.compile(
    r"\\[!-/:-@\[-`{-~]"
    r"|<!--[\s\S]*?-->"
    r"|<[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*>"
    r"|<[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9]"
    r"(?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*>"
    r"|`+")


def indentation(line: str) -> int:
    """The width of `line`'s leading spaces and tabs, a tab to the next
    multiple of four, as Markdown counts it."""
    width = 0
    for char in line:
        if char == " ":
            width += 1
        elif char == "\t":
            width += 4 - width % 4
        else:
            break
    return width


def table_cells(row: str) -> list[str]:
    """A table row's cells: its text between unescaped pipes, the outer pipes
    dropped. A pipe inside a code span still splits, as GFM says."""
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|") and not row.endswith("\\|"):
        row = row[:-1]
    return re.split(r"(?<!\\)\|", row)


def prose_blocks(text: str) -> list[str]:
    """`text` as the blocks whose backticks can pair with one another, with
    everything Markdown does not parse for spans left out.

    One string per block, wrapped lines joined with a newline; a cell of a
    table row is a block of its own (a row of `| a | b |` is two). Fenced and
    indented code, HTML comment blocks and a table's delimiter row are not in
    the result. See the module docstring for the subset this is, and for why
    it exists: a document-wide pairing lets one literal backtick blind every
    span after it.
    """
    lines = text.splitlines()
    blocks: list[str] = []
    window: list[str] = []
    fence: tuple[str, int] | None = None
    fence_floor = item_offset = 0
    comment = code = in_list = table = False
    after_blank = True

    def flush() -> None:
        if window:
            blocks.append("\n".join(window))
            window.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        stripped = line.strip()
        if fence is not None:
            closer = FENCE_CLOSE.fullmatch(line)
            if closer and closer.group(1)[0] == fence[0] and (
                    len(closer.group(1)) >= fence[1]):
                fence = None
                continue
            if not stripped or indentation(line) >= fence_floor:
                continue
            fence, in_list = None, False
        if comment:
            comment = "-->" not in stripped
            continue
        if not stripped:
            flush()
            after_blank = True
            table = False
            continue
        indent = indentation(line)
        after_blank, was_blank = False, after_blank
        if code:
            if indent >= 4:
                continue
            code = False
        table = table and indent < 4
        item = None if RULE.fullmatch(line) else LIST_ITEM.match(line)
        if was_blank and indent < 2 and not item:
            in_list = False
        starts_item = bool(item) and (indent < 4 or in_list) and (
            not window or in_list or item.group(1) in (None, "1"))
        opener = FENCE_OPEN.fullmatch(line)
        if opener and not (opener.group(1)[0] == "`"
                           and "`" in opener.group(2)):
            flush()
            table = False
            in_list = in_list and indent >= 2
            fence = (opener.group(1)[0], len(opener.group(1)))
            fence_floor = min(indent, item_offset) if in_list else 0
            continue
        if stripped.startswith("<!--") and indent < 4:
            flush()
            table = False
            in_list = in_list and indent >= 2
            comment = "-->" not in stripped
            continue
        if HEADING.match(line):
            flush()
            table = False
            blocks.append(stripped)
            in_list = in_list and indent >= 2
            continue
        if RULE.fullmatch(line) or (window and UNDERLINE.fullmatch(line)
                                    and not (in_list and indent < 2)):
            flush()
            table = False
            in_list = in_list and indent >= 2
            continue
        if starts_item:
            table = False
        elif table:
            blocks.extend(table_cells(line))
            continue
        elif indent >= 4 and not window and not in_list:
            code = True
            continue
        elif "|" in line and i < len(lines) and not (
                in_list and window and indent < 2) and (
                TABLE_DELIMITER.fullmatch(lines[i]) and "|" in lines[i]
                and len(table_cells(line)) == len(table_cells(lines[i]))):
            flush()
            table = True
            blocks.extend(table_cells(line))
            i += 1
            continue
        if starts_item:
            flush()
            in_list = True
            item_offset = item.end() - 1
        window.append(line)
    flush()
    return blocks


def code_spans(block: str) -> list[str]:
    """The code spans of one block, left to right, as CommonMark pairs them.

    A run of N backticks opens a span that the next run of EXACTLY N closes;
    a run nothing closes is literal. Closers are looked for in the raw text,
    because a backslash inside a span escapes nothing; openers are found by
    `INLINE`, which steps over what makes a backtick literal.
    """
    runs = [(m.start(), m.end()) for m in re.finditer(r"`+", block)]
    spans: list[str] = []
    position = 0
    while True:
        found = INLINE.search(block, position)
        if found is None:
            return spans
        position = found.end()
        if not found.group().startswith("`"):
            continue
        width = found.end() - found.start()
        for start, end in runs:
            if start >= found.end() and end - start == width:
                spans.append(block[found.end():start])
                position = end
                break


def code_shaped_tokens(text: str) -> list[str]:
    """Every backticked token in `text` whose whole text is `CODE_SHAPE`,
    once each, in the order the document first spells it."""
    found: dict[str, None] = {}
    for block in prose_blocks(text):
        for span in code_spans(block):
            token = span.strip()
            if CODE_SHAPE.fullmatch(token):
                found.setdefault(token)
    return list(found)


# --- which strings a tool holds -------------------------------------------

def printed_strings(source: bytes) -> frozenset[str]:
    """Every `str` constant in `source` that a tool could print whole.

    By `ast`: a comment is not in the tree, a docstring is excluded by
    position (the first statement of a module, class or function), and the
    constants inside an f-string are excluded as fragments of a computed
    string. Adjacent literals are one constant, which a grep would miss. Bytes
    in, so the file's own coding declaration decides how it decodes and a
    Windows default codec never does.
    """
    tree = ast.parse(source)
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                             ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if isinstance(first, ast.Expr):
                skipped.add(id(first.value))
        elif isinstance(node, ast.JoinedStr):
            skipped.update(id(part) for part in node.values)
    return frozenset(
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and id(node) not in skipped)


def shipped_tool_sources() -> dict[str, bytes]:
    """The shipped Python tools' sources, by path relative to the root, as
    POSIX: `tests/test_repo_hygiene.py::SHIPPED`, kept to Python (a `.py`
    file, or one whose first line is a Python shebang, like `bootstrap`).

    `SHIPPED` is imported here and not at the top of the module so that a
    refactor of that constant fails the tests that read the tools, not the
    collection of the file that holds the checker's own cases. A sibling test
    module is imported by name elsewhere in this suite
    (`from test_commit_trailers import ...`), and only the constant is taken,
    never a `test_*` function.
    """
    from test_repo_hygiene import SHIPPED

    sources: dict[str, bytes] = {}
    for path in SHIPPED:
        source = path.read_bytes()
        first = source.split(b"\n", 1)[0]
        if path.suffix == ".py" or (first.startswith(b"#!")
                                    and b"python" in first):
            sources[path.relative_to(REPO).as_posix()] = source
    return dict(sorted(sources.items()))


@functools.cache
def tool_strings() -> dict[str, frozenset[str]]:
    """What each shipped tool holds, parsed once for the whole module. A
    function and not a fixture: a failing test prints its fixtures' values,
    and these are every string in every shipped tool."""
    return {path: printed_strings(source)
            for path, source in shipped_tool_sources().items()}


# --- the comparison -------------------------------------------------------

def unprinted_names(documents: Mapping[str, str],
                    tools: Mapping[str, frozenset[str]],
                    allowlist: Mapping[str, str]) -> list[str]:
    """Everything wrong between the names `documents` spell and the strings
    `tools` hold, one sentence each, naming the token and the document."""
    problems: list[str] = []
    printed = sorted({string for strings in tools.values()
                      for string in strings if CODE_SHAPE.fullmatch(string)})
    named: set[str] = set()
    for document, text in documents.items():
        for token in code_shaped_tokens(text):
            named.add(token)
            printers = sorted(path for path, strings in tools.items()
                              if token in strings)
            if token in allowlist and printers:
                problems.append(
                    f"{document} names `{token}`, which {ALLOWLIST_NAME} "
                    f"says is no code a tool prints ({allowlist[token]}), "
                    f"but {', '.join(printers)} prints it as an exact string "
                    f"constant: the allowlist entry is stale, so delete it "
                    f"and let `{token}` be held to the tool.")
            elif token not in allowlist and not printers:
                close = difflib.get_close_matches(token, printed, n=3,
                                                  cutoff=0.8)
                hint = "."
                if close:
                    hint = ("; did you mean "
                            + " or ".join(f"`{c}`" for c in close) + "?")
                problems.append(
                    f"{document} names `{token}`, and no shipped tool holds "
                    f"it as an exact string constant{hint} An assistant "
                    f"briefed from {document} would relay a code no tool "
                    f"prints. Spell it as the tool does, or, if it is no code "
                    f"a tool prints, add it to {ALLOWLIST_NAME} with its "
                    f"reason.")
    for token in sorted(allowlist):
        if token not in named:
            problems.append(
                f"{ALLOWLIST_NAME} lists `{token}`, but "
                f"{' and '.join(documents)} no longer names it: the "
                f"allowlist entry is stale, so delete it.")
    return problems


def documents_on_disk() -> dict[str, str]:
    return {name: (REPO / name).read_bytes().decode("utf-8")
            for name in DOCUMENTS}


def test_every_code_shaped_name_in_agents_md_is_a_code_a_tool_prints():
    """The guard itself, on this repository's own bytes (#348).

    Both directions are in it. A misspelling in `AGENTS.md` fails because the
    misspelt token is held by no tool; a code renamed in a tool fails because
    the old spelling is held by no tool any more, and `AGENTS.md` still
    spells it. Either way the message names the token and the document.
    """
    problems = unprinted_names(documents_on_disk(), tool_strings(),
                               NOT_A_CODE_A_TOOL_PRINTS)
    assert not problems, "\n".join(problems)


def test_the_scan_reads_the_tools_and_is_not_vacuous():
    """A scan that read no tool, or found no name, would pass the test above
    for ever.

    The tools it must read are named (`KNOWN_TOOLS`), none of them is a test,
    and the document yields at least one name that a tool prints, so "no
    problems" means something was compared.
    """
    tools = tool_strings()
    missing = [name for name in KNOWN_TOOLS if name not in tools]
    assert not missing, (
        f"the shipped tools read are {sorted(tools)}; {missing} are not "
        f"among them. If a tool was removed from SHIPPED on purpose, take it "
        f"off KNOWN_TOOLS; if SHIPPED was refactored, the filter in "
        f"shipped_tool_sources is the thing to fix")
    assert not [name for name in tools if name.startswith("tests/")]
    names = [token for text in documents_on_disk().values()
             for token in code_shaped_tokens(text)]
    checked = [token for token in names
               if any(token in strings for strings in tools.values())]
    assert checked, (
        f"none of the code-shaped names in {DOCUMENTS} ({names}) is held by "
        f"any tool: the extraction or the tool list have gone vacuous")


def test_the_extraction_reads_the_names_agents_md_spells_today():
    """A sentinel for the extraction on the real document, not a cap: a name
    added to it needs no change here. If `AGENTS.md` rightly stopped
    spelling one of these, delete it from the tuple; if it did not, the
    extraction has lost a span, which is the failure this file exists for."""
    names = code_shaped_tokens(documents_on_disk()["AGENTS.md"])
    for token in ("scaffold-leg-path-collides", "scaffold-pin-collides",
                  "upstream-changed", "upstream-added", "locally-modified",
                  "prefer-triad-project-shape"):
        assert token in names, (token, names)


def test_every_allowlist_entry_has_a_reason():
    """An empty allowlist is a pass: the loop has nothing to say."""
    for token, reason in NOT_A_CODE_A_TOOL_PRINTS.items():
        assert CODE_SHAPE.fullmatch(token), (
            f"`{token}` is not code-shaped, so it can never be one the "
            f"scan names and needs no entry")
        assert reason.strip(), f"`{token}` has no reason on the allowlist"


# --- the checker, on small cases of its own -------------------------------
# The mutants of the issue (a misspelt AGENTS.md, a renamed tool code, a
# listed token) are real runs against scratch copies; these are the same
# properties on in-memory input, so they run on every platform with nothing
# to set up.

TOOL = b'''"""A tool."""
def refuse():
    raise Refusal("scaffold-pin-collides", "why")
VERDICT = "upstream-changed"
'''

DOC = ("Two refusals: `scaffold-pin-collides` and `upstream-changed`. "
       "An id: `some-ruling-id`.\n")


def held(source: bytes) -> dict[str, frozenset[str]]:
    return {"tool.py": printed_strings(source)}


def test_a_misspelt_code_fails_naming_the_token_and_the_document():
    doc = DOC.replace("scaffold-pin-collides", "scaffold-pin-collision")
    problems = unprinted_names({"AGENTS.md": doc}, held(TOOL),
                               {"some-ruling-id": "an id"})
    assert len(problems) == 1, problems
    assert "AGENTS.md" in problems[0] and "`scaffold-pin-collision`" in (
        problems[0])
    assert "did you mean `scaffold-pin-collides`" in problems[0], problems[0]


def test_a_code_renamed_in_the_tool_fails_naming_the_old_spelling():
    renamed = TOOL.replace(b"scaffold-pin-collides", b"scaffold-pin-clash")
    problems = unprinted_names({"AGENTS.md": DOC}, held(renamed),
                               {"some-ruling-id": "an id"})
    assert len(problems) == 1, problems
    assert "AGENTS.md" in problems[0] and "`scaffold-pin-collides`" in (
        problems[0])


def test_a_longer_constant_holding_the_token_does_not_satisfy_the_document():
    """The tool holds `an upstream-changed row` and nothing else: the match
    is by equality, not by substring."""
    longer = b'MESSAGE = "an upstream-changed row"\n'
    problems = unprinted_names(
        {"AGENTS.md": "A verdict: `upstream-changed`.\n"}, held(longer), {})
    assert len(problems) == 1, problems
    assert "`upstream-changed`" in problems[0]


def test_an_allowlisted_name_no_tool_prints_does_not_fail():
    assert unprinted_names({"AGENTS.md": DOC}, held(TOOL),
                           {"some-ruling-id": "an id"}) == []


def test_an_empty_allowlist_is_a_pass_when_every_name_is_printed():
    doc = "Both: `scaffold-pin-collides` and `upstream-changed`.\n"
    assert unprinted_names({"AGENTS.md": doc}, held(TOOL), {}) == []


def test_an_allowlisted_name_a_tool_prints_is_a_stale_entry():
    problems = unprinted_names({"AGENTS.md": DOC}, held(TOOL),
                               {"some-ruling-id": "an id",
                                "upstream-changed": "was not printed"})
    assert len(problems) == 1, problems
    assert "`upstream-changed`" in problems[0] and "AGENTS.md" in problems[0]
    assert "stale" in problems[0] and "tool.py" in problems[0]


def test_an_allowlisted_name_no_document_names_is_a_stale_entry():
    problems = unprinted_names({"AGENTS.md": DOC}, held(TOOL),
                               {"some-ruling-id": "an id",
                                "gone-ruling-id": "no longer cited"})
    assert len(problems) == 1, problems
    assert "`gone-ruling-id`" in problems[0] and "stale" in problems[0]


@pytest.mark.parametrize("source", [
    b'"""upstream-changed"""\nx = 1\n',
    b'def f():\n    """upstream-changed"""\n',
    b'class C:\n    """upstream-changed"""\n',
    b'# upstream-changed\nx = 1\n',
    b'x = "an upstream-changed row"\n',
    b'x = f"upstream-changed{n}"\n',
    b'x = f"{n}-upstream-changed"\n',
    b'x = b"upstream-changed"\n',
], ids=["module docstring", "function docstring", "class docstring",
        "comment", "longer constant", "f-string head", "f-string tail",
        "bytes"])
def test_what_a_tool_does_not_print_does_not_count(source):
    assert "upstream-changed" not in printed_strings(source)


@pytest.mark.parametrize("source", [
    b'x = "upstream-changed"\n',
    b'COUNTS = {"upstream-changed": 0}\n',
    b'x = "upstream-" "changed"\n',
    b'def f():\n    """Docs."""\n    return "upstream-changed"\n',
    b'def f(n):\n    return ["upstream-changed", f"{n} rows"]\n',
], ids=["assignment", "dict key", "adjacent literals", "after a docstring",
        "beside an f-string"])
def test_what_a_tool_holds_whole_counts(source):
    assert "upstream-changed" in printed_strings(source)


# --- the extraction, on small cases of its own ----------------------------

def test_only_backticked_code_shaped_spans_are_names():
    text = (
        "Plain `scaffold-pin-collides` and `--org` and `contracts/spec-pin."
        "yaml` and `single-repository.yaml` and `<user>-wip` and `Foo-bar` "
        "and `a b-c` and `make-it` and `ls-tree-v1`, twice: "
        "`scaffold-pin-collides`.\n"
        "``double-tick-name`` and ` padded-name ` and an unclosed `` run.\n"
        "```sh\nin-a-fence --flag `in-a-fence-too`\n```\n"
        "~~~\nin-a-tilde-fence\n~~~\n"
        "after-the-fences is not backticked, `after-fences-name` is.\n")
    assert code_shaped_tokens(text) == [
        "scaffold-pin-collides", "make-it", "ls-tree-v1", "double-tick-name",
        "padded-name", "after-fences-name"]


def test_a_fence_closes_on_its_own_character_and_at_least_its_length():
    """A tilde line is not the end of a backtick fence, nor a short run the
    end of a long one, and a name spelt inside any of them is not read. A
    scan that did not strip fences at all would read all three."""
    text = (
        "```text\n~~~ not a closer\n`inside-backtick-fence`\n```\n\n"
        "~~~md\n```sh not a closer\n`inside-tilde-fence`\n~~~\n\n"
        "````\n```\n`inside-long-fence`\n````\n\n"
        "After them, `after-the-fences`.\n")
    assert code_shaped_tokens(text) == ["after-the-fences"]


def test_a_fence_nothing_closes_runs_to_the_end():
    text = "Before `before-name`.\n\n```\n`inside-open-fence` for ever\n"
    assert code_shaped_tokens(text) == ["before-name"]


def test_a_wrapped_paragraph_is_one_block_and_a_span_may_cross_its_lines():
    text = "A span that `wraps\nacross` two lines, then `after-wrap-name`.\n"
    assert code_shaped_tokens(text) == ["after-wrap-name"]


def test_no_span_crosses_a_heading_a_table_row_a_cell_or_a_list_item():
    text = (
        "# A ` heading\n`after-heading` and ` here.\n\n"
        "| a ` b | `first-cell` |\n|---|---|\n| `second-row` | c ` d |\n\n"
        "- one ` literal\n- `bullet-name` here\n- another ` literal\n"
        "1. x ` y\n2. `second-item-name`\n")
    assert code_shaped_tokens(text) == [
        "after-heading", "first-cell", "second-row", "bullet-name",
        "second-item-name"]


def test_an_escaped_backtick_is_literal_and_a_backslash_in_a_span_is_not():
    text = (
        "A literal \\` here, then `escaped-name` follows.\n\n"
        "A backslash itself, \\\\`double-slash-name`.\n\n"
        "A span `ends\\` with a backslash, then `after-slash-name`.\n")
    assert code_shaped_tokens(text) == [
        "escaped-name", "double-slash-name", "after-slash-name"]


def test_indented_code_is_not_read_but_indented_prose_is():
    """Four spaces after a blank line with nothing open is code; four spaces
    in a list item's second paragraph, or on the line after a paragraph's
    first, is prose and a name in it is read."""
    text = (
        "Before.\n\n    echo `in-code-name`\n\n"
        "A paragraph\n    still `paragraph-name`.\n\n"
        "1. A step:\n\n    continued `list-name` text.\n\n"
        "After `after-code-name`.\n")
    assert code_shaped_tokens(text) == [
        "paragraph-name", "list-name", "after-code-name"]


def test_html_comments_and_autolinks_hold_literal_backticks():
    text = (
        "<!--\nhidden ` backtick, `hidden-name`\n-->\n\n"
        "<!-- one line ` -->\n\n"
        "Inline <!-- ` --> then `inline-name` and <https://e.com/a`b> and "
        "<me@example.com> and `tail-name`.\n")
    assert code_shaped_tokens(text) == ["inline-name", "tail-name"]


def test_only_an_ordered_marker_of_one_interrupts_a_paragraph():
    """`2.` at the start of a wrapped line is text, so the lines are one
    paragraph and the span crosses them; `1.` and a bullet start an item."""
    wrapped = ("A wrapped ` line\n2. that only looks like a marker "
               "`two-name` end.\n\nThen `after-name`.\n")
    assert code_shaped_tokens(wrapped) == ["after-name"]
    started = "A wrapped ` line\n1. a real list `one-name` end.\n"
    assert code_shaped_tokens(started) == ["one-name"]


def test_a_rule_or_a_setext_underline_ends_the_block_without_a_blank():
    text = (
        "A ` literal\n---\n`after-rule` ` x\n\n"
        "A title ` here\n===\n`after-underline` ` y\n\n"
        "* * *\n`after-star-rule`\n")
    assert code_shaped_tokens(text) == [
        "after-rule", "after-underline", "after-star-rule"]


def test_pipe_lines_are_a_table_only_with_a_delimiter_row():
    """Without a delimiter row, or with one whose cell count is not the
    header's, the lines are a paragraph and a span may cross them; with one,
    each cell is a block."""
    text = (
        "| a ` b | `not-a-cell-name` |\nplain ` text\n\n"
        "| h1 | h2 |\n|:--|--:|\n| `row-name` | x ` y |\n\n"
        "| one | two | three |\n|---|---|\n| a ` b | `mismatch-name` |\n")
    assert code_shaped_tokens(text) == ["row-name"]


def test_a_table_row_after_a_list_paragraph_line_is_a_lazy_continuation():
    """CommonMark reads the four lines as one paragraph of the item, so the
    backtick of `item` pairs with the one before `y-name` and nothing is a
    name; an indented table is a table of the item, and its cells are read."""
    lazy = "- item ` x\n| a | b |\n|---|---|\n| c | `y-name` |\n"
    assert code_shaped_tokens(lazy) == []
    indented = "- item ` x\n  | a | b |\n  |---|---|\n  | c | `y-name` |\n"
    assert code_shaped_tokens(indented) == ["y-name"]


def test_a_fence_inside_a_list_item_ends_with_the_item():
    closed = ("1. Step:\n\n   ```sh\n   echo `\n   ```\n\n"
              "   after `item-name` text.\n")
    assert code_shaped_tokens(closed) == ["item-name"]
    unterminated = ("1. Step:\n\n   ```sh\n   echo hi\n\n"
                    "After the list `after-item-name`.\n")
    assert code_shaped_tokens(unterminated) == ["after-item-name"]


# THE VECTORS of the review of #396. Each is Markdown that CommonMark renders
# harmlessly, put BEFORE a paragraph that misspells a code. The guard has to
# name the misspelling in every one; until the extraction paired backticks
# per block, the first six (and `two literal backticks` below) read nothing
# after the construct, and the misspelling passed.
VECTORS = {
    "a backtick alone in its paragraph (V1)":
        "Type one backtick (`) where a span would start.",
    "an escaped backtick (V2)": "A literal \\` backtick, escaped.",
    "a four-backtick fence holding a three-backtick line (V3)":
        "````md\n```sh\nmake park\n```\n````",
    "a backtick fence holding a tilde line (V4)":
        "```text\n~~~ a tilde rule in an example\n```",
    "a tilde fence holding a backtick fence (V5)":
        "~~~md\n```sh\nmake park\n```\n~~~",
    "an indented code block holding a backtick (V6)":
        "Before.\n\n    echo `pwd`\n    echo ` one",
    "a fence in a nested list item (V7)":
        "1. A step.\n   - a sub-step:\n\n     ```sh\n     echo `\n     ```",
    "an HTML comment holding a backtick (V8)": "<!-- a ` in a comment -->",
    "an autolink holding a backtick (V9)": "<https://example.com/a`b>",
}

MISSPELT = "A refusal: `scaffold-pin-collision`, and `upstream-changed`.\n"


@pytest.mark.parametrize("vector", list(VECTORS.values()),
                         ids=list(VECTORS))
def test_a_construct_with_a_literal_backtick_does_not_blind_the_scan(vector):
    doc = vector + "\n\n" + MISSPELT
    assert code_shaped_tokens(doc) == ["scaffold-pin-collision",
                                       "upstream-changed"], vector
    problems = unprinted_names({"AGENTS.md": doc}, held(TOOL), {})
    assert len(problems) == 1, problems
    assert "`scaffold-pin-collision`" in problems[0]
    assert "did you mean `scaffold-pin-collides`" in problems[0]


def test_two_literal_backticks_around_a_misspelling_do_not_blind_the_scan():
    """Mutant S2 of that review: a literal backtick in one paragraph and
    another a section later, the misspelling between them. Paired across the
    document they swallowed it, and every test passed."""
    doc = ("A literal backtick (`) is how Markdown opens a span.\n\n"
           "A refusal: `scaffold-pin-collision`.\n\n"
           "Close it with another (`).\n\n"
           "A verdict: `upstream-changed`.\n")
    problems = unprinted_names({"AGENTS.md": doc}, held(TOOL), {})
    assert len(problems) == 1, problems
    assert "`scaffold-pin-collision`" in problems[0]
