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
#: `host_shell_dialect` answers `nt` (Windows, no `MSYSTEM`), `sh`'s
#: elsewhere, Git Bash included (#711).
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
    # "`family.py`'s `NEXT`, `switch -c`, `add`, `cd`, `git rm -r --cached`,
    # `bump` and `remove` lines".
    "scripts/family.py": {
        "_print_next": 1,          # the `NEXT` line: `git push -u origin ...`
        "_switch_command": 1,      # the `git switch -c <branch>` line
        "_add_command": 3,         # the `family.py add --family-root ...` line
        "_print_next_steps": 2,    # `init`'s block: its `switch -c` and `cd`
        "_checked_mount_path": 1,  # the `git rm -r --cached -- <path>` remedy
        "_checked_add_target": 1,  # `member-already-present`'s `bump` line
        # `add`'s `member-duplicate-id`: its `bump` line (#927) and its
        # `remove` line (#1005)
        "_checked_member_id": 2,
        "_checked_bumped_id": 1,   # `bump`'s `member-duplicate-id`: `remove`
        "cmd_bump": 1,             # `bump`'s `member-unknown`: its `add` line
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


def alias_of(node: ast.AST):
    """`(name, value)` for `name = value` and `name: type = value`, the two
    statements that give a name to what `value` is (`value` is None in a
    bare `name: type`, which names nothing); None for any other node. A
    chained, tuple or walrus assignment is not one (#759)."""
    if (isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)):
        return node.targets[0].id, node.value
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        return node.target.id, node.value
    return None


def quoter_names(tree: ast.AST) -> set:
    """The names a host-dialect quoter answers to in this module: the four of
    `HOST_QUOTERS`, and every other name bound to one, by `from repo_shape
    import shell_line as joined` or by `joined = shell_line` (or
    `joined: object = shell_line`, or `... = repo_shape.shell_line`), however
    many steps it takes (#665, #759)."""
    names = set(HOST_QUOTERS)
    while True:
        before = len(names)
        for node in ast.walk(tree):
            statement = alias_of(node)
            if isinstance(node, ast.ImportFrom):
                names.update(alias.asname for alias in node.names
                             if alias.asname and alias.name in names)
            elif statement is not None:
                name, value = statement
                bound = value.id if isinstance(value, ast.Name) else getattr(
                    value, "attr", None)
                if bound in names:
                    names.add(name)
        if len(names) == before:
            return names


def host_calls(source: str, filename: str = "<tool>") -> list:
    """`(function, line)` for every call in `source` to a quoter that follows
    the host: not one that forces `sh`'s dialect with a `'posix'` argument or
    a `posix=True` keyword. `function` is the innermost `def` the call is
    in (`Class.method` for a method), or `<module>`. A quoter handed on as a
    value (`map(shell_quoted, words)`) is a use as a call is, and is seen
    (`host_values`, #759).

    WHAT IT DOES NOT SEE: a name given to a quoter by a tuple (`a, b =
    shell_line, shell_word`), a chained assignment (`a = b = shell_line`), a
    walrus (`(q := shell_line)`) or a conditional (`q = shell_line if x else
    repr`). The quoter is counted at that statement, once, and the calls of
    the new name are not seen, so `q(x) + q(y)` is one use and not two. A
    plain or annotated assignment (`q = shell_line`, `q: object =
    shell_line`) is followed instead, and each call of `q` is the use. A
    quoter named by `getattr(repo_shape, "shell_line")` or
    `globals()["shell_line"]` is a string here, not a name."""
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
            handed_on = (parent.func is not node
                         and not names_posix(parent, node))
        else:
            alias = alias_of(parent)
            handed_on = alias is None or alias[1] is not node
        if handed_on:
            found.append((function_of(node, parents), node.lineno))
    return found


def names_posix(call: ast.Call, quoter: ast.AST) -> bool:
    """`host_call`'s test of a call, for a call that takes `quoter` as an
    argument: a `'posix'` argument after the one the quoter would quote (the
    quoter, its value, then its platform: `functools.partial(shell_quoted,
    'x', 'posix')`), or a `platform=` or `posix=` keyword. `functools.partial(
    quote_arg, 'posix')` binds the VALUE `'posix'` and quotes it for the host.
    A quoter handed as a keyword (`key=shell_quoted`) has no place among the
    arguments, so each of them is read."""
    placed = next((at for at, arg in enumerate(call.args) if arg is quoter),
                  None)
    after = call.args if placed is None else call.args[placed + 2:]
    return any(isinstance(arg, ast.Constant) and arg.value == "posix"
               for arg in after) or any(
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
    # The alias statement is not a use only where `quoter_names` follows it:
    # one that stores the quoter on an object, or names it twice, is the use.
    "stored on an object": "def f(self):\n    self.quote = shell_line\n",
    "chained alias": "def f():\n    a = b = shell_quoted\n    return a, b\n",
    # `partial(quote_arg, 'posix')` binds the VALUE 'posix', not the platform.
    "partial of the value 'posix'": (
        "import functools\n"
        "def f():\n    return functools.partial(quote_arg, 'posix')\n"),
    # A name read in an annotation is still a read; only the VALUE a statement
    # assigns is the alias.
    "annotation": "def f():\n    quote: shell_quoted = None\n",
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
    "posix argument beside the quoter in a keyword":
        "def f(w):\n    return apply(w, 'posix', key=shell_quoted)\n",
    "alias statement": "def f():\n    quote = shell_quoted\n",
    "annotated alias statement":
        "def f():\n    quote: object = shell_quoted\n",
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


def test_a_quoter_aliased_with_an_annotation_is_counted_at_each_call():
    """`q: object = shell_quoted` names the quoter as `q = shell_quoted`
    does, so each call of `q` is the use and the statement is not: a count
    of two is two, and one of the two switched to `'posix'` is one."""
    source = ("def f(x, y):\n    q: object = shell_quoted\n"
              "    a = q(x)\n    return a + q(y)\n")
    assert host_calls(source) == [("f", 3), ("f", 4)]
    assert host_calls(source.replace("q(y)", "q(y, 'posix')")) == [("f", 3)]


#: The names a quoter is given that `quoter_names` does not follow, and the
#: uses it counts instead: the statement, once for each quoter it names
#: (`host_calls`' docstring says what it does not see).
NOT_FOLLOWED = {
    "a tuple": ("def f(x, y):\n    a, b = shell_line, shell_word\n"
                "    return a(x) + b(y)\n", [("f", 2), ("f", 2)]),
    "a chained assignment": (
        "def f(x, y):\n    a = b = shell_line\n    return a(x) + b(y)\n",
        [("f", 2)]),
    "a walrus": ("def f(x, y):\n    return (q := shell_line)(x) + q(y)\n",
                 [("f", 2)]),
    "a conditional": (
        "def f(x, y):\n    q = shell_line if x else repr\n"
        "    return q(x) + q(y)\n", [("f", 2)]),
}


@pytest.mark.parametrize("form", sorted(NOT_FOLLOWED))
def test_an_alias_the_walk_does_not_follow_is_counted_at_its_statement(form):
    source, uses = NOT_FOLLOWED[form]
    assert host_calls(source) == uses, form


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


def test_a_value_use_in_a_method_is_named_with_its_class():
    """A value use in a method is named as a call in it is, `Plan.line` and
    not `line` (`test_a_method_is_named_with_its_class`)."""
    source = ("class Plan:\n    def line(self, w):\n"
              "        return map(shell_quoted, w)\n")
    assert host_calls(source) == [("Plan.line", 3)]


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


def scopes(tree: ast.AST) -> dict:
    """Every node of `tree` mapped to the function it is in, named as
    `host_calls` names one: the innermost `def`, `Class.method` for a
    method, `""` outside any. A `def` maps to its own name."""
    scope = {tree: ""}
    for node in ast.walk(tree):         # breadth first: a parent comes first
        inner = scope[node]
        for child in ast.iter_child_nodes(node):
            named = isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef,
                                       ast.ClassDef))
            scope[child] = (f"{inner}.{child.name}" if inner else
                            child.name) if named else inner
    return scope


def os_name_readers(tree: ast.AST, scope: dict) -> set:
    """The functions of `tree` that read `os.name`, `<module>` outside
    any."""
    return {scope[node] or "<module>" for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "name"
            and isinstance(node.value, ast.Name) and node.value.id == "os"}


def calls_to(tree: ast.AST, scope: dict, names: set) -> set:
    """The functions of `tree` that use one of `names` the way `host_calls`
    counts a use: a call that does not force `sh`'s dialect, or the name
    handed on as a value (`map(shell_quoted, w)`, `host_values`), which
    names its function as `scopes` does (#808's review, NIT 6)."""
    called = {scope[node] or "<module>" for node in ast.walk(tree)
              if isinstance(node, ast.Call) and host_call(node, names)}
    return called | {function for function, _ in host_values(tree, names)}


def line_builders(tree: ast.AST, scope: dict) -> set:
    """The names of the functions of `tree` that take a `platform` and hand
    it on to a host-dialect quoter, or to another such function: the
    doctor's `copy_command`, `scaffold_command`, `validator_command` and
    the rest of the lines it builds (#711). Given no `platform`, each
    answers for the host, so a caller that hands one `os.name` skips the
    question as surely as one that hands it to `quote_arg`. Found within one
    file: a builder imported from another is not one here."""
    taking = [(node.name, scope[node]) for node in ast.walk(tree)
              if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
              and "platform" in {arg.arg for arg in (
                  *node.args.posonlyargs, *node.args.args,
                  *node.args.kwonlyargs)}]
    builders = set()
    while True:
        calling = calls_to(tree, scope, quoter_names(tree) | builders)
        found = {name for name, where in taking if where in calling}
        if found <= builders:
            return builders
        builders |= found


def skips_the_question(relative: str, source: str) -> set:
    """The functions of `source` that quote for the host, are a host-dialect
    quoter, call a line builder (`line_builders`) or are one, and read
    `os.name` themselves, less the ones `READS_OS_NAME_FOR_THE_MACHINE`
    names for `relative`."""
    tree = ast.parse(source, filename=relative)
    scope = scopes(tree)
    builders = line_builders(tree, scope)
    quoting = calls_to(tree, scope, quoter_names(tree) | builders)
    quoting |= {scope[node] for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name in HOST_QUOTERS | builders}
    return (quoting & os_name_readers(tree, scope)) - \
        READS_OS_NAME_FOR_THE_MACHINE.get(relative, set())


def test_every_host_dialect_quoter_and_caller_asks_the_one_question():
    """A function that quotes for the host, is a quoter that follows it, or
    builds or calls a line that does (`line_builders`), reads which shell
    that is from `host_shell_dialect`, never from `os.name` (#711): a new
    caller that branched on `os.name`, or passed it as the `platform`, would
    hand Git Bash PowerShell's quoting.

    WHAT IT DOES NOT SEE, each a way to choose the dialect without reading
    `os.name` as an attribute in such a function: a branch on
    `sys.platform`; `from os import name`, or `os.name` under any other
    spelling; a module constant built from `os.name` (`WINDOWS = os.name ==
    "nt"`) and read in the function; a line builder imported from another
    file; and a branch on `os.name` in a function that calls no quoter and
    no builder. A quoter that is a method is seen, by its `Class.method`
    name."""
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
              "    return shell_line(w) if os.name == 'nt' else ''\n"
              "class Q:\n    def quote_arg(self, v):\n"
              "        return v if os.name == 'nt' else v\n")
    assert skips_the_question("scripts/x.py", source) == {
        "a", "shell_word", "Plan.line", "scaffold_command", "Q.quote_arg"}
    assert skips_the_question("shape-doctor.py", source) == {
        "a", "shell_word", "Plan.line", "Q.quote_arg"}


def test_a_quoter_handed_on_as_a_value_beside_os_name_skips_the_question():
    """A quoter handed on as a value is a use here as it is in `host_calls`
    (#759): `map(shell_quoted, w)` beside a branch on `os.name` skips the
    question as the same line written as a generator of calls does (#808's
    review, NIT 6). One told `'posix'` is `sh`'s and is not a use."""
    handed = ("import os\ndef a(w):\n"
              "    return ' '.join(map(shell_quoted, w)) "
              "if os.name == 'nt' else ''\n")
    called = handed.replace("map(shell_quoted, w)",
                            "shell_quoted(x) for x in w")
    posix = handed.replace(
        "map(shell_quoted, w)",
        "map(functools.partial(shell_quoted, platform='posix'), w)")
    assert skips_the_question("scripts/x.py", called) == {"a"}
    assert skips_the_question("scripts/x.py", handed) == {"a"}
    assert skips_the_question("scripts/x.py", posix) == set()


def test_os_name_handed_to_a_line_builder_skips_the_question():
    """`copy_command(s, d, os.name)` hands Git Bash `Copy-Item`: a line
    builder is a quoter here, and so is a function that hands its
    `platform` on to one. A call that forces `"posix"` is not a host call,
    and a builder this file does not define is not one."""
    row = "import os\ndef a(s, d):\n    return copy_command(s, d, os.name)\n"
    builders = ("def copy_command(source, target, platform=None):\n"
                "    return quote_arg(source, platform)\n"
                "def notes(s, platform=None):\n"
                "    return copy_command(s, s, platform)\n"
                "def b(s):\n    return notes(s, os.name)\n"
                "def c(s):\n"
                "    return notes(s, 'posix') if os.name == 'nt' else ''\n")
    assert skips_the_question("scripts/x.py", row) == set()
    assert skips_the_question("scripts/x.py", row + builders) == {"a", "b"}
    doctor = (REPO / "shape-doctor.py").read_text(encoding="utf-8")
    tree = ast.parse(doctor)
    assert {"restore_from_head", "validator_command", "bump_leg_command",
            "checkout_notes", "kept_branch_line", "submodule_update_next",
            "lane_trailer_command", "copy_command", "scaffold_command"} <= \
        line_builders(tree, scopes(tree))
    assert skips_the_question(
        "shape-doctor.py", doctor + "\n\n" + row.replace("a(", "a_row(")) \
        == {"a_row"}
