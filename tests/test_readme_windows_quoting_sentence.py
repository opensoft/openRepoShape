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
    below, each with its number of host-dialect calls, so a fourth tool, or
    a new line in a named one, is a fault here until the sentence names it
    (#665, #759).

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
#: `os.name` is `nt`, `sh`'s elsewhere.
HOST_QUOTERS = {"quote_arg", "shell_quoted", "shell_line", "shell_word"}

#: A tool the sentence names for ALL its lines: any function of it may call
#: a host-dialect quoter.
EVERY_LINE = None

#: The tools the sentence names, which is every shipped file that calls one,
#: and where it names a tool by the lines of particular commands, the
#: functions that print them (`Class.method` where a method does), each with
#: its number of host-dialect uses. A call switched to `"posix"` takes one off
#: its function's count, and a new function that quotes for the host is not
#: one the sentence names: either way the sentence and this table change
#: together.
NAMED = {
    # "`shape-doctor.py`'s lines": every NEXT, fix and command line it prints.
    "shape-doctor.py": EVERY_LINE,
    # "`setup-project.py`'s family lines": the `switch -c` and `add` it prints.
    "setup-project.py": {"family_next_command": 2},
    # "`family.py`'s `NEXT`, `switch -c`, `add` and `git rm -r --cached`
    # lines".
    "scripts/family.py": {
        "_print_next": 1,          # the `NEXT` line: `git push -u origin ...`
        "_switch_command": 1,      # the `git switch -c <branch>` line
        "_add_command": 3,         # the `family.py add --family-root ...` line
        "_print_next_steps": 2,    # `init`'s block: its `switch -c` and `cd`
        "_checked_mount_path": 1,  # the `git rm -r --cached -- <path>` remedy
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
    value (`map(shell_quoted, words)`) is a use as a call is, and is seen
    (`host_values`, #759)."""
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
    return sorted(found + host_values(tree, quoters), key=lambda use: use[1])


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


def host_values(tree: ast.AST, quoters: set) -> list:
    """`(function, line)` for every host quoter handed on as a value and not
    called: an argument or keyword of another call (`map(shell_quoted, w)`,
    `functools.partial(shell_line)`), a list entry, a default or a return
    value. The alias statement `joined = shell_line` is not one: each use of
    `joined` is, and is seen under its own function. A call told `'posix'`
    (`functools.partial(shell_line, platform="posix")`) is `sh`'s (#759)."""
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    found = []
    for node in ast.walk(tree):
        name = node.id if isinstance(node, ast.Name) else getattr(
            node, "attr", None)
        if name not in quoters or not isinstance(node.ctx, ast.Load):
            continue
        parent = parents.get(node)
        while isinstance(parent, (ast.keyword, ast.Starred)):
            parent = parents.get(parent)
        if isinstance(parent, ast.Call):
            handed_on = parent.func is not node and not names_posix(parent)
        else:
            handed_on = not (isinstance(parent, ast.Assign)
                             and parent.value is node
                             and len(parent.targets) == 1
                             and isinstance(parent.targets[0], ast.Name))
        if handed_on:
            found.append((function_of(node, parents), node.lineno))
    return found


def names_posix(call: ast.Call) -> bool:
    """`host_call`'s test of a call, for a call that takes the quoter as an
    argument: a `'posix'` argument, or a `platform=` or `posix=` keyword."""
    return any(isinstance(arg, ast.Constant) and arg.value == "posix"
               for arg in call.args) or any(
        isinstance(kw.value, ast.Constant)
        and (kw.value.value == "posix" or kw.value.value is True)
        for kw in call.keywords if kw.arg in ("platform", "posix"))


def function_of(node: ast.AST, parents: dict) -> str:
    """The innermost `def` (`Class.method` for a method) holding `node`, or
    `<module>`: `host_calls`' own scope, read upward."""
    names = []
    while node in parents:
        node = parents[node]
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            names.append(node.name)
    return ".".join(reversed(names)) or "<module>"


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


def host_use_counts(sources: dict, tool: str) -> dict:
    """`{function: its number of host-dialect uses}` in `tool`."""
    return {function: len(lines) for function, lines in
            host_quoting(sources).get(tool, {}).items()}


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
    commands, not for every line: a call switched to POSIX quoting takes one
    off its function's count (a function of three calls with one switched
    would still be in a set of names, #759), and a new function that calls a
    host-dialect quoter is a line the sentence does not name."""
    counted = host_use_counts(tool_sources(), tool)
    assert counted == NAMED[tool], (
        f"{tool}'s functions that use a host-dialect quoter, with their "
        f"number of uses, are {counted}, and the sentence names "
        f"{NAMED[tool]}: change the sentence in both places, then NAMED here.")


def test_a_quoter_imported_under_another_name_is_a_host_call():
    source = ("from repo_shape import shell_line as joined, shell_quoted\n"
              "spelled = joined\n"
              "def a():\n    return joined(['git'])\n"
              "def b():\n    return spelled(['git'])\n"
              "def c():\n    return shell_quoted('x', 'posix')\n"
              "def d():\n    return joined(['git'], platform='posix')\n")
    assert host_calls(source) == [("a", 4), ("b", 6)]


#: Each way to hand a host quoter on without calling it. The first two are
#: the forms #665's inventory missed (#759); the rest read the same rule.
VALUE_USES = {
    "map": "def f(w):\n    return map(shell_quoted, w)\n",
    "partial": ("import functools\n"
                "def f():\n    return functools.partial(shell_line)\n"),
    "keyword": "def f(w):\n    return sorted(w, key=shell_quoted)\n",
    "attribute": ("import repo_shape\n"
                  "def f(w):\n    return map(repo_shape.shell_word, w)\n"),
    "alias": ("from repo_shape import shell_line as joined\n"
              "def f(w):\n    return list(map(joined, w))\n"),
    "bound alias": ("def f(w):\n    quote = shell_quoted\n"
                    "    return map(quote, w)\n"),
    "list": "def f():\n    return [shell_line, repr]\n",
    "default": "def f(quote=quote_arg):\n    return quote\n",
    "returned": "def f():\n    return shell_line\n",
}

#: What is not a use: `sh`'s dialect asked for, the alias statement, a string
#: and a name no quoter answers to.
NOT_USES = {
    "posix keyword": ("import functools\ndef f():\n    return "
                      "functools.partial(shell_line, platform='posix')\n"),
    "posix argument": ("import functools\ndef f():\n    return "
                       "functools.partial(shell_quoted, 'x', 'posix')\n"),
    "posix=True": ("import functools\ndef f():\n    return "
                   "functools.partial(shell_line, posix=True)\n"),
    "posix keyword beside the quoter in a keyword":
        "def f(w):\n    return sorted(w, key=shell_quoted, posix=True)\n",
    "alias statement": "def f():\n    quote = shell_quoted\n",
    "string": "def f():\n    return 'shell_line'\n",
    "other name": "def f(w):\n    return map(repr, w)\n",
}


@pytest.mark.parametrize("form", sorted(VALUE_USES))
def test_a_quoter_handed_on_as_a_value_is_a_host_use(form):
    """`map(shell_quoted, words)` formats each word for the host as surely as
    a call does: a tool could print a PowerShell line through one and the
    sentence would not have to name it."""
    uses = host_calls(VALUE_USES[form])
    assert [function for function, _ in uses] == ["f"], (form, uses)


@pytest.mark.parametrize("form", sorted(NOT_USES))
def test_what_is_not_a_use_of_a_host_quoter_is_not_one(form):
    assert host_calls(NOT_USES[form]) == [], form


def test_a_value_use_names_its_tool_and_function():
    source = "def _next_line(w):\n    return map(shell_quoted, w)\n"
    assert host_quoting({"update-shape.py": source}) == {
        "update-shape.py": {"_next_line": [2]}}


def test_calls_and_value_uses_come_in_source_order():
    source = ("def c(w):\n    return map(shell_quoted, w)\n"
              "def b():\n    return shell_line(['git'])\n"
              "def a(w):\n    return map(shell_word, w)\n")
    assert host_calls(source) == [("c", 2), ("b", 4), ("a", 6)]


def test_a_use_count_tells_one_call_switched_from_a_whole_function():
    """`_add_command` has three host-dialect calls. With one switched to
    `'posix'` its NAME is still in the set of functions the old pin compared;
    its count is two, not three."""
    three = ("def _add_command(a, b, c):\n"
             "    return shell_quoted(a) + shell_quoted(b) + shell_quoted(c)\n")
    two = three.replace("shell_quoted(c)", "shell_quoted(c, 'posix')")
    tool = "scripts/family.py"
    assert host_use_counts({tool: three}, tool) == {"_add_command": 3}
    assert host_use_counts({tool: two}, tool) == {"_add_command": 2}


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
