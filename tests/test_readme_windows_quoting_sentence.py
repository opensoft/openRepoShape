# SPDX-License-Identifier: Apache-2.0
"""README's sentence about which printed commands are quoted for PowerShell,
and what keeps it true (#532).

"Windows, natively" tells a person where to paste what the tools print: into
Git Bash, because the tools quote for a POSIX shell, except for the lines of
the tools that quote for the shell they run in, which on Windows is
PowerShell. A person who follows the sentence and pastes a PowerShell-quoted
line into Git Bash gets a different command (`git -C C:\\work\\Orbit` reads as
`C:workOrbit`), so the sentence is a promise, and two things hold it:

  * the handbook's Windows panel says the same words as README does, so the
    page cannot drift from the file it quotes (#519 holds each section's
    HASH of the README, not what the two say);
  * the tools that call a quoter that follows the host (`quote_arg`,
    `shell_quoted`, `shell_line`, `shell_word`) are exactly the three the
    sentence names, and for the two it names by the lines of particular
    commands, the functions that print those lines are the ones pinned
    below, so a fourth tool, or a new line in a named one, is a fault here
    until the sentence names it (#665).

Nothing runs a tool: the first reads two files, the second reads every
shipped Python file with `ast`, the files `git ls-files` lists (a `.py`
suffix, or a `python` shebang, as the root `bootstrap` has).
"""

from __future__ import annotations

import ast
import html
import re
import subprocess

import pytest

from conftest import REPO

#: The sentence, cut out of README by its first and last words.
SENTENCE = re.compile(r"Printed commands are quoted for a POSIX shell.*?, "
                      r"on Windows\.")

#: The quoters whose answer follows the host: PowerShell's dialect where
#: `host_shell_dialect` answers `nt` (Windows, no `MSYSTEM`), `sh`'s
#: elsewhere, Git Bash included (#711).
HOST_QUOTERS = {"quote_arg", "shell_quoted", "shell_line", "shell_word"}

#: A tool the sentence names for ALL its lines: any function of it may call
#: a host-dialect quoter.
EVERY_LINE = None

#: The tools the sentence names, which is every shipped file that calls one,
#: and where it names a tool by the lines of particular commands, the
#: functions that print them (`Class.method` where a method does). A call
#: switched to `"posix"` in one of these leaves its function out of what the
#: file calls, and a new function that quotes for the host is not one the
#: sentence names: either way the sentence and this table change together.
NAMED = {
    # "`shape-doctor.py`'s lines": every NEXT, fix and command line it prints.
    "shape-doctor.py": EVERY_LINE,
    # "`setup-project.py`'s family lines": the `switch -c` and `add` it prints.
    "setup-project.py": {"family_next_command"},
    # "`family.py`'s `NEXT`, `switch -c`, `add` and `git rm -r --cached`
    # lines".
    "scripts/family.py": {
        "_print_next",          # the `NEXT` line: `git push -u origin ...`
        "_switch_command",      # the `git switch -c <branch>` line
        "_add_command",         # the `family.py add --family-root ...` line
        "_print_next_steps",    # `init`'s block: its `switch -c` and `cd`
        "_checked_mount_path",  # the `git rm -r --cached -- <path>` remedy
    },
}

#: The quoters' own home is not a tool, and only these two bodies are what the
#: sentence need not name: `shell_line` spells each word by `shell_quoted`, and
#: `shell_quoted` is the host-dialect rule itself. Any other function of
#: `scripts/repo_shape.py` that calls a host-dialect quoter is a tool's line.
QUOTERS_OWN_BODIES = {"scripts/repo_shape.py": {"shell_quoted", "shell_line"}}


def squashed(text: str) -> str:
    """`text` with every run of whitespace one space: README wraps a line
    where the handbook wraps another."""
    return " ".join(text.split())


def readme_section() -> str:
    """README's "Windows, natively" section, without its Markdown."""
    text = (REPO / "README.md").read_text(encoding="utf-8")
    start = text.index("<summary><b>Windows, natively</b></summary>")
    section = text[start:text.index("</details>", start)]
    return squashed(section.replace("`", ""))


def handbook_panel() -> str:
    """The handbook's Windows panel as text: its tags gone, its entities
    read, and the typographic apostrophe the page writes (`&rsquo;`) the
    ASCII one README writes."""
    text = (REPO / "docs" / "handbook.html").read_text(encoding="utf-8")
    start = text.index('id="panel-windows"')
    panel = text[start:text.index("<!-- WSL2 -->", start)]
    plain = html.unescape(re.sub(r"<[^>]*>", "", panel))
    return squashed(plain.replace("\u2019", "'"))


def test_the_sentence_is_in_readmes_windows_section_once():
    found = SENTENCE.findall(readme_section())
    assert len(found) == 1, found


def test_the_handbooks_windows_panel_says_the_same_words():
    sentence = SENTENCE.findall(readme_section())[0]
    panel = handbook_panel()
    assert panel.count(sentence) == 1, (
        "docs/handbook.html's Windows panel (`panel-windows`) must say, word "
        "for word once its tags are gone and its whitespace is one space, "
        f"what README's \"Windows, natively\" says:\n  {sentence}")


def quoter_names(tree: ast.AST) -> set:
    """The names a host-dialect quoter answers to in this module: the four of
    `HOST_QUOTERS`, and every other name bound to one, by `from repo_shape
    import shell_line as joined` or by `joined = shell_line` (or
    `... = repo_shape.shell_line`), however many steps it takes (#665)."""
    names = set(HOST_QUOTERS)
    while True:
        before = len(names)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                names.update(alias.asname for alias in node.names
                             if alias.asname and alias.name in names)
            elif (isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Name)):
                value = node.value
                bound = value.id if isinstance(value, ast.Name) else getattr(
                    value, "attr", None)
                if bound in names:
                    names.add(node.targets[0].id)
        if len(names) == before:
            return names


def host_calls(source: str, filename: str = "<tool>") -> list:
    """`(function, line)` for every call in `source` to a quoter that follows
    the host: not one that forces `sh`'s dialect with a `'posix'` argument or
    a `posix=True` keyword. `function` is the innermost `def` the call is
    in (`Class.method` for a method), or `<module>`. A quoter handed on as a
    value (`map(shell_quoted, words)`) is not a call and is not seen."""
    tree = ast.parse(source, filename=filename)
    quoters = quoter_names(tree)
    found = []

    def walk(node, scope):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                  ast.ClassDef)):
                walk(child, scope + [child.name])
            else:
                if isinstance(child, ast.Call) and host_call(child, quoters):
                    found.append((".".join(scope) or "<module>",
                                  child.lineno))
                walk(child, scope)

    walk(tree, [])
    return found


def host_call(node: ast.Call, quoters: set) -> bool:
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(
        func, "attr", None)
    if name not in quoters:
        return False
    forced = any(isinstance(arg, ast.Constant) and arg.value == "posix"
                 for arg in node.args[1:]) or any(
        isinstance(kw.value, ast.Constant)
        and (kw.value.value == "posix" or kw.value.value is True)
        for kw in node.keywords if kw.arg in ("platform", "posix"))
    return not forced


def is_python_source(relative: str, first_line: bytes) -> bool:
    """A `.py` file, or a file whose first line is a shebang naming `python`:
    the root `bootstrap` is a shipped tool with no suffix (#665)."""
    return relative.endswith(".py") or (
        first_line.startswith(b"#!") and b"python" in first_line)


def tool_sources() -> dict:
    """`{relative path: text}` of every shipped Python file: what `git
    ls-files` lists (tracked, or new and not ignored), outside `tests/` and
    the dot-directories, that is a `.py` file or has a `python` shebang."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others",
         "--exclude-standard"],
        cwd=str(REPO), capture_output=True, check=True).stdout
    sources = {}
    for raw in sorted(set(listed.split(b"\0"))):
        relative = raw.decode("utf-8")
        parts = relative.split("/")
        if not raw or parts[0] == "tests" or parts[0].startswith("."):
            continue
        path = REPO / relative
        if not path.is_file():
            continue                    # a gitlink, or deleted and not staged
        data = path.read_bytes()
        if is_python_source(relative, data.split(b"\n", 1)[0]):
            sources[relative] = data.decode("utf-8")
    return sources


def host_quoting(sources: dict) -> dict:
    """`{relative path: {function: [lines]}}` of the tools that call a quoter
    that follows the host, the quoters' own bodies left out."""
    quoting = {}
    for relative, source in sources.items():
        own = QUOTERS_OWN_BODIES.get(relative, set())
        for function, line in host_calls(source, relative):
            if function not in own:
                quoting.setdefault(relative, {}).setdefault(
                    function, []).append(line)
    return quoting


def test_the_tools_that_quote_for_the_host_are_the_ones_the_sentence_names():
    quoting = host_quoting(tool_sources())
    assert set(quoting) == set(NAMED), (
        "README's \"Windows, natively\" and the handbook's Windows panel name "
        "the tools whose printed lines are quoted for PowerShell on Windows. "
        f"The files that call a host-dialect quoter are {sorted(quoting)}: "
        "change the sentence in both places, then NAMED here.")


@pytest.mark.parametrize("tool", sorted(
    tool for tool, functions in NAMED.items() if functions is not EVERY_LINE))
def test_the_functions_that_quote_for_the_host_are_the_ones_the_sentence_names(
        tool):
    """`family.py` and `setup-project.py` are named for the lines of certain
    commands, not for every line: a call switched to POSIX quoting leaves its
    function out, and a new function that calls a host-dialect quoter is a
    line the sentence does not name."""
    calling = set(host_quoting(tool_sources()).get(tool, {}))
    assert calling == NAMED[tool], (
        f"{tool}'s functions that call a host-dialect quoter are "
        f"{sorted(calling)}, and the sentence names {sorted(NAMED[tool])}: "
        "change the sentence in both places, then NAMED here.")


def test_a_quoter_imported_under_another_name_is_a_host_call():
    source = ("from repo_shape import shell_line as joined, shell_quoted\n"
              "spelled = joined\n"
              "def a():\n    return joined(['git'])\n"
              "def b():\n    return spelled(['git'])\n"
              "def c():\n    return shell_quoted('x', 'posix')\n"
              "def d():\n    return joined(['git'], platform='posix')\n")
    assert host_calls(source) == [("a", 4), ("b", 6)]


def test_a_method_is_named_with_its_class():
    source = ("import repo_shape\n"
              "class Plan:\n    def line(self):\n"
              "        return repo_shape.shell_line(['git'])\n")
    assert host_calls(source) == [("Plan.line", 4)]


def test_only_the_two_quoter_bodies_of_repo_shape_are_exempt():
    own = ("def shell_quoted(value, platform=None):\n    return value\n"
           "def shell_line(words, platform=None):\n"
           "    return ' '.join(shell_quoted(w, platform) for w in words)\n")
    assert host_quoting({"scripts/repo_shape.py": own}) == {}
    third = own + "def next_line():\n    return shell_line(['git'])\n"
    assert host_quoting({"scripts/repo_shape.py": third}) == {
        "scripts/repo_shape.py": {"next_line": [6]}}
    assert host_quoting({"scripts/other.py": own}) != {}, (
        "the exemption is for repo_shape.py's bodies, not for any file that "
        "defines functions of those names")


def test_a_suffixless_python_file_is_scanned_and_another_language_is_not():
    assert is_python_source("bootstrap", b"#!/usr/bin/env python3\n")
    assert is_python_source("scripts/x.py", b"")
    assert not is_python_source("openRepoShape", b"#!/usr/bin/env bash\n")
    assert not is_python_source("README.md", b"# Title\n")
    assert "bootstrap" in tool_sources()


# --- the one question, asked by every quoter that follows the host (#711) ---

#: The functions that call a host-dialect quoter and still read `os.name`,
#: each for something that is not the shell. Any other such function has
#: skipped `host_shell_dialect`, the question every host-dialect quoter asks
#: (`scripts/repo_shape.py`'s, and `setup-project.py`'s copy), and under Git
#: Bash, where `os.name` is `nt` too, it chooses PowerShell's dialect.
READS_OS_NAME_FOR_THE_MACHINE = {
    # The entry point and the interpreter: `python setup-project.py` on a
    # Windows machine, from PowerShell and from Git Bash alike. Its quoting
    # asks the question.
    "shape-doctor.py": {"scaffold_command"},
}


def os_name_readers(tree: ast.AST) -> set:
    """The functions of `tree` that read `os.name`, each named as
    `host_calls` names one: the innermost `def`, `Class.method` for a
    method, `<module>` outside any."""
    scope = {tree: ""}
    for node in ast.walk(tree):         # breadth first: a parent comes first
        inner = scope[node]
        for child in ast.iter_child_nodes(node):
            named = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))
            scope[child] = (f"{inner}.{child.name}" if inner else
                            child.name) if named else inner
    return {scope[node] or "<module>" for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "name"
            and isinstance(node.value, ast.Name) and node.value.id == "os"}


def skips_the_question(relative: str, source: str) -> set:
    """The functions of `source` that quote for the host, or are a
    host-dialect quoter, and read `os.name` themselves, less the ones
    `READS_OS_NAME_FOR_THE_MACHINE` names for `relative`."""
    tree = ast.parse(source, filename=relative)
    quoting = {function for function, _ in host_calls(source, relative)}
    quoting |= {node.name for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef)
                and node.name in HOST_QUOTERS}
    return (quoting & os_name_readers(tree)) - \
        READS_OS_NAME_FOR_THE_MACHINE.get(relative, set())


def test_every_host_dialect_quoter_and_caller_asks_the_one_question():
    """A function that quotes for the host, or is a quoter that follows it,
    reads which shell that is from `host_shell_dialect`, never from
    `os.name` (#711): a new caller that branched on `os.name`, or passed it
    as the `platform`, would hand Git Bash PowerShell's quoting. It sees
    what `host_calls` sees, so a branch on `os.name` in a function that
    calls no quoter is not seen."""
    skipping = {}
    for relative, source in tool_sources().items():
        found = skips_the_question(relative, source)
        if found:
            skipping[relative] = sorted(found)
    assert skipping == {}, (
        "these functions quote for the host and read `os.name` themselves: "
        f"{skipping}. Ask `host_shell_dialect()` (`scripts/repo_shape.py`, or "
        "`setup-project.py`'s copy) for the shell, or, where `os.name` "
        "answers something else, name the function and what in "
        "READS_OS_NAME_FOR_THE_MACHINE.")


def test_reading_os_name_beside_a_host_quoter_skips_the_question():
    source = ("import os\n"
              "from repo_shape import host_shell_dialect, shell_line\n"
              "def a(w):\n    return shell_line(w, os.name)\n"
              "def b(w):\n    return shell_line(w, host_shell_dialect())\n"
              "def c():\n    return os.name\n"
              "def shell_word(v):\n    return v if os.name == 'nt' else v\n"
              "class Plan:\n    def line(self, w):\n"
              "        target = 'nt' if os.name == 'nt' else 'posix'\n"
              "        return shell_line(w, target)\n"
              "def scaffold_command(w):\n"
              "    return shell_line(w) if os.name == 'nt' else ''\n")
    assert skips_the_question("scripts/x.py", source) == {
        "a", "shell_word", "Plan.line", "scaffold_command"}
    assert skips_the_question("shape-doctor.py", source) == {
        "a", "shell_word", "Plan.line"}
