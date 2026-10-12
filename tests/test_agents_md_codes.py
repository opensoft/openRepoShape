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

#: The shipped tools, as globs under the repository root: the top-level
#: `*.py` tools, every `scripts/*.py`, and every `scripts/*.py` of every root
#: template (`templates/assembly-root/scripts/` and `templates/family-root/
#: scripts/` today, and any template added later, which is why the pattern
#: has a `**` rather than two names). `tests/` is not here on purpose.
TOOL_GLOBS = ("*.py", "scripts/*.py", "templates/**/scripts/*.py")

#: A code-shaped name `AGENTS.md` spells that is NOT a code a tool prints,
#: each with its reason. Verdict words a tool prints are checked, never
#: listed here. The test fails an entry that a tool does print and an entry
#: no document names any more, so the list cannot rot into a place where a
#: misspelling hides.
NOT_A_CODE_A_TOOL_PRINTS = {
    "prefer-triad-project-shape": (
        "an openxFactory ruling id (Brett Heap, 2026-10-06), cited so a "
        "reader can find the ruling; the tools name it in comments and "
        "docstrings and print it nowhere"),
}

#: Where a failure says to put a name that is no code, so the three messages
#: that mention the list cannot name two different places.
ALLOWLIST_NAME = "NOT_A_CODE_A_TOOL_PRINTS in tests/test_agents_md_codes.py"


def without_fences(text: str) -> str:
    """`text` with every fenced code block removed.

    A fenced block holds commands, and what a command line spells is not a
    token the prose names. A fence is a line that starts, after up to three
    spaces, with three backticks or three tildes; the next such line closes
    it. An unterminated fence runs to the end, as Markdown reads it.
    """
    kept: list[str] = []
    inside = False
    for line in text.splitlines():
        if re.match(r" {0,3}(```|~~~)", line):
            inside = not inside
            continue
        if not inside:
            kept.append(line)
    return "\n".join(kept)


def code_spans(text: str) -> list[str]:
    """The inline code spans of `text`, the way CommonMark pairs backticks.

    A run of N backticks opens a span that the next run of EXACTLY N closes;
    a run nothing closes is literal. A span may cross a line, so the match is
    over the whole text, not line by line - which is also why this is not a
    one-line regex: `` `` a ` b `` `` would be read wrongly by one.
    """
    runs = [(m.start(), m.end()) for m in re.finditer(r"`+", text)]
    spans: list[str] = []
    i = 0
    while i < len(runs):
        start, end = runs[i]
        for j in range(i + 1, len(runs)):
            if runs[j][1] - runs[j][0] == end - start:
                spans.append(text[end:runs[j][0]])
                i = j + 1
                break
        else:
            i += 1
    return spans


def code_shaped_tokens(text: str) -> list[str]:
    """Every backticked token in `text` whose whole text is `CODE_SHAPE`,
    once each, in the order the document first spells it."""
    found: dict[str, None] = {}
    for span in code_spans(without_fences(text)):
        token = span.strip()
        if CODE_SHAPE.fullmatch(token):
            found.setdefault(token)
    return list(found)


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
    """The shipped tools' sources, by path relative to the root, as POSIX."""
    paths = {path for pattern in TOOL_GLOBS for path in REPO.glob(pattern)
             if path.is_file()}
    return {path.relative_to(REPO).as_posix(): path.read_bytes()
            for path in sorted(paths)}


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


@functools.cache
def tool_strings() -> dict[str, frozenset[str]]:
    """What each shipped tool holds, parsed once for the whole module. A
    function and not a fixture: a failing test prints its fixtures' values,
    and these are every string in every shipped tool."""
    return {path: printed_strings(source)
            for path, source in shipped_tool_sources().items()}


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


def test_the_scan_reads_tools_and_names_and_is_not_vacuous():
    """A pattern that matched nothing would pass the test above for ever.

    The tools are found (the two that hold the codes AGENTS.md spells are
    among them) and the document yields at least one name that a tool prints,
    so "no problems" means something was compared.
    """
    tools = tool_strings()
    assert "scaffold-project.py" in tools and "update-shape.py" in tools, (
        f"the tool globs {TOOL_GLOBS} found {sorted(tools)}")
    assert all(path.endswith(".py") and "tests/" not in path for path in tools)
    names = [token for text in documents_on_disk().values()
             for token in code_shaped_tokens(text)]
    checked = [token for token in names
               if any(token in strings for strings in tools.values())]
    assert checked, (
        f"none of the code-shaped names in {DOCUMENTS} ({names}) is held by "
        f"any tool: the extraction or the tool globs have gone vacuous")


def test_every_allowlist_entry_has_a_reason():
    assert NOT_A_CODE_A_TOOL_PRINTS
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


def test_an_allowlisted_name_no_tool_prints_does_not_fail():
    assert unprinted_names({"AGENTS.md": DOC}, held(TOOL),
                           {"some-ruling-id": "an id"}) == []


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


def test_only_backticked_code_shaped_spans_are_names():
    text = (
        "Plain `scaffold-pin-collides` and `--org` and `contracts/spec-pin."
        "yaml` and `single-repository.yaml` and `<user>-wip` and `Foo-bar` "
        "and `a b-c` and `make-it`, twice: `scaffold-pin-collides`.\n"
        "``double-tick-name`` and ` padded-name ` and an unclosed `` run.\n"
        "```sh\nin-a-fence --flag `in-a-fence-too`\n```\n"
        "~~~\nin-a-tilde-fence\n~~~\n"
        "after-the-fences is not backticked, `after-fences-name` is.\n")
    assert code_shaped_tokens(text) == [
        "scaffold-pin-collides", "make-it", "double-tick-name", "padded-name",
        "after-fences-name"]

