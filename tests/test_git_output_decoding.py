# SPDX-License-Identifier: Apache-2.0
"""A child's words are read as UTF-8, whatever the locale (#217).

`shape_materialize.run` carries most of the `git` and `gh` calls `execute`
makes, and it used to decode what they wrote with the LOCALE'S codec: ASCII
under a POSIX `C` locale with UTF-8 mode off, the ANSI code page on Windows
without `PYTHONUTF8=1`. Git writes a path as UTF-8, so a message that named
`Übersicht.md` raised `UnicodeDecodeError` out of `subprocess.run` before
`CommandFailed` was built, and the person got a traceback and exit 1 where
`REFUSED pushing the spec leg` and the ruleset hint belong, with both leg
remotes already created.

THE CAUSE IS ONE LINE REPEATED IN THIRTY PLACES, so there are two kinds of test
and the second is the one that keeps a thirty-first from arriving:

  * `test_run_names_the_path_git_complained_of_under_a_c_locale` drives the
    fixed `run` in a CHILD interpreter started with `LC_ALL=C PYTHONUTF8=0`.
    A codec is fixed when the interpreter starts, so this process (UTF-8 mode
    on, or a UTF-8 locale) cannot reproduce it by setting an environment
    variable afterwards.
  * `test_no_shipped_text_mode_call_decodes_with_the_locale_codec` reads
    every shipped tool's `subprocess` calls and fails on one that asks for
    text without naming the codec.

The reader is `TextModeCalls`, and #321 widened what it sees. It reads a call
spelled `subprocess.run(...)` AND the spellings that used to walk past it:
`from subprocess import run` (also `as`, also `*`), `import subprocess as sp`,
`sp = subprocess` (also `sp: object = subprocess`) and
`other_module.subprocess.run`; a call that names only `encoding=` or only
`errors=` (text mode, with the locale's codec for the half it left out);
`getoutput` and `getstatusoutput` (always text, with no codec to name before
Python 3.11); a call that hands its keywords over as `**options`; and a
spawner passed around uncalled (`functools.partial(subprocess.run, ...)`).
Each has a synthetic module the guard must flag and the same module fixed,
which it must pass (`SYNTHETIC`), so a form dropped from the reader fails by
name.

What a syntax tree cannot resolve stays outside it: `getattr(subprocess, name)`,
an import made by `importlib`, and the module held by a walrus, an unpacking or
a `for` target. A wrapper that is not `subprocess` is read where it calls
`subprocess` (`shape_materialize.run` names its own `encoding=`).
"""

from __future__ import annotations

import ast
import codecs
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from conftest import REPO, git

#: What the child does, as a program rather than a function here, because it
#: has to run in an interpreter this one is not. Every argument it reads is
#: ASCII (the name travels as hex), and it prints ONE line of ASCII JSON, so a
#: stdout that cannot encode `Ü` is not what the test is measuring.
#: `os.fsdecode` turns the name's bytes into the `str` that `subprocess` turns
#: back into exactly those bytes on the command line, whatever the codec.
CHILD = r"""
import json, locale, os, sys
sys.path.insert(0, sys.argv[1])
import shape_materialize
repo, name = sys.argv[2], os.fsdecode(bytes.fromhex(sys.argv[3]))
answer = {"codec": locale.getpreferredencoding(False)}
try:
    shape_materialize.run(["git", "-C", repo, "add", "--", name])
except shape_materialize.CommandFailed as exc:
    answer["refused"] = exc.loudly("staging the file")
except Exception as exc:
    answer["raised"] = type(exc).__name__ + ": " + str(exc)
print(json.dumps(answer))
"""

#: The name as git wrote it (UTF-8 bytes) and as `run` must hand it back. The
#: second is NOT valid UTF-8: git writes the bytes it was given, `errors=
#: "replace"` turns the one it cannot read into U+FFFD, and a strict UTF-8
#: decode would have been the same traceback again.
NAMES = [
    pytest.param("Übersicht.md".encode("utf-8"), "Übersicht.md", id="utf-8"),
    pytest.param(b"caf\xe9.md", "caf�.md", id="not-utf-8"),
]


@pytest.mark.skipif(
    os.name == "nt",
    reason="a C locale is a POSIX idea: Windows decodes with the ANSI code "
           "page, and its job sets PYTHONUTF8=1 (.github/workflows/tests.yml)")
@pytest.mark.parametrize("written, expected", NAMES)
def test_run_names_the_path_git_complained_of_under_a_c_locale(
        tmp_path, written, expected):
    repo = tmp_path / "repo"
    repo.mkdir()
    git("init", "-q", ".", cwd=repo)
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("LC_", "LANG", "PYTHONUTF8",
                                  "PYTHONIOENCODING", "PYTHONCOERCE"))}
    env.update({"LC_ALL": "C", "PYTHONUTF8": "0"})
    proc = subprocess.run(
        [sys.executable, "-c", CHILD, str(REPO / "scripts"), str(repo),
         written.hex()],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, f"the child died:\n{stderr}"
    answer = json.loads(proc.stdout.decode("ascii"))
    if codecs.lookup(answer["codec"]).name == "utf-8":
        pytest.skip(f"this platform reads a child's output as {answer['codec']} "
                    "under LC_ALL=C PYTHONUTF8=0, so there is no non-UTF-8 "
                    "locale to reproduce the failure in")
    assert "raised" not in answer, (
        f"run() raised in place of a refusal under {answer['codec']}: "
        f"{answer['raised']}")
    assert answer["refused"].startswith("REFUSED staging the file."), answer
    assert f"pathspec '{expected}' did not match any files" in answer["refused"]
    assert "UnicodeDecodeError" not in answer["refused"] + stderr


#: The calls `subprocess` exposes that take `text=`, `encoding=` and `errors=`.
SPAWNERS = {"run", "Popen", "check_output", "check_call", "call"}

#: The calls `subprocess` ALWAYS runs as text and, before Python 3.11, gives no
#: way to name a codec for (`encoding=` and `errors=` arrived in 3.11; this
#: standard supports 3.9), so they decode with the locale's. No spelling of
#: one is fine: a call is refused unless EXEMPT lists the function.
ALWAYS_TEXT = {"getoutput", "getstatusoutput"}

#: A call that asks for text must name BOTH, unless it is listed here. Keyed
#: by (file, the function the call is in); the value is what it must still
#: name, and the reason it differs.
EXEMPT = {
    # The `gh api` tree listing becomes a digest: UTF-8 yes, `replace` no, for
    # a replaced byte would be a wrong digest with a confident tone.
    ("scaffold-project.py", "pin_digest_from_gh"): frozenset({"encoding"}),
    ("scripts/repo_shape.py", "tree_digest_from_gh"): frozenset({"encoding"}),
}

#: A call the guard cannot read the keywords of: one that expands `**options`
#: (the expansion may carry `text=True`), or a spawner that is passed around
#: without being called (`functools.partial(subprocess.run, ...)`, an alias, a
#: base class). Refused unless the function is listed here, keyed like EXEMPT,
#: with the REASON it cannot ask for text; a blank reason is refused. A call
#: that names `encoding=` and `errors=` itself needs no row, because Python
#: rejects a keyword given twice, so the expansion cannot change either.
OPAQUE: dict[tuple[str, str], str] = {}


def shipped_python() -> list[Path]:
    """Every Python file this standard ships, tests excluded."""
    found = [*REPO.glob("*.py"), *REPO.glob("scripts/*.py"),
             *REPO.glob("templates/**/*.py"), REPO / "bootstrap"]
    return sorted(found)


def is_constant(node: ast.expr, value: object) -> bool:
    return isinstance(node, ast.Constant) and node.value is value


def names_utf8(node: ast.expr) -> bool:
    """`encoding=` names UTF-8, or names something this file cannot read.

    A literal is read: `None` is the locale's codec, and a codec that is not
    UTF-8 is not what git writes. A variable is taken at its word, because a
    syntax tree cannot say what one holds (the shipped code has none).
    """
    if isinstance(node, ast.Constant):
        try:
            return (isinstance(node.value, str)
                    and codecs.lookup(node.value).name == "utf-8")
        except LookupError:
            return False
    return True


class TextModeCalls(ast.NodeVisitor):
    """What a module's `subprocess` calls ask for, and what it hides.

    * `found`: (line, function, keywords named) for each spawner call that
      asks for text. `text=` and `universal_newlines=` ask unless they are the
      literal `False`; `encoding=` and `errors=` ask unless they are the
      literal `None`, because each puts the child's pipes in text mode on its
      own. An `encoding=None`, an `encoding=` that is not UTF-8 and an
      `errors=None` are not counted as NAMED: each leaves the locale's codec
      or its strict handler where it was.
    * `always_text`: (line, function, name) for `getoutput` and
      `getstatusoutput`.
    * `opaque`: (line, function, what) for a call whose keywords are out of
      sight (an expansion that does not name both codecs itself) and for a
      spawner referred to without being called.

    A call is a spawner call however it is spelled: `subprocess.run`, the
    module under another name (`import subprocess as sp`, `sp = subprocess`,
    `sp: object = subprocess`), the module reached through another
    (`shape_materialize.subprocess.run`), or a bare name from `from subprocess
    import run [as read]` / `import *`.
    Names are read across the whole file, so a name bound in one function
    counts in the next: that can only make the guard stricter. Only a plain or
    annotated assignment of a bare name is followed; a walrus, an unpacking or
    a `for` target that holds the module is not.
    """

    def __init__(self) -> None:
        self.found: list[tuple[int, str, set[str]]] = []
        self.always_text: list[tuple[int, str, str]] = []
        self.opaque: list[tuple[int, str, str]] = []
        self.scope: list[str] = []
        self.modules: set[str] = set()
        self.spawners: dict[str, str] = {}
        self.annotations: set[int] = set()

    def visit_Module(self, node: ast.Module) -> None:
        self.bind(node)
        self.generic_visit(node)

    def bind(self, tree: ast.AST) -> None:
        watched = SPAWNERS | ALWAYS_TEXT
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "subprocess":
                        self.modules.add(alias.asname or alias.name)
            elif (isinstance(node, ast.ImportFrom)
                  and node.module == "subprocess" and node.level == 0):
                for alias in node.names:
                    if alias.name == "*":
                        self.spawners.update({name: name for name in watched})
                    elif alias.name in watched:
                        self.spawners[alias.asname or alias.name] = alias.name
            # A type annotation names `subprocess.Popen` without spawning one.
            annotation = (node.returns if isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef))
                else getattr(node, "annotation", None))
            if isinstance(annotation, ast.expr):
                self.annotations.update(id(n) for n in ast.walk(annotation))
        changed = True
        while changed:  # `sp = subprocess`, `sp: object = subprocess`, `a = sp`
            changed = False
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    targets = node.targets
                elif (isinstance(node, ast.AnnAssign)
                      and node.value is not None):
                    targets = [node.target]
                else:
                    continue
                if (isinstance(node.value, ast.Name)
                        and node.value.id in self.modules):
                    for target in targets:
                        if (isinstance(target, ast.Name)
                                and target.id not in self.modules):
                            self.modules.add(target.id)
                            changed = True

    def spawner_of(self, node: ast.expr) -> str | None:
        """Which `subprocess` function `node` names, spelled however it is."""
        watched = SPAWNERS | ALWAYS_TEXT
        if isinstance(node, ast.Attribute) and node.attr in watched:
            owner = node.value
            # `subprocess.run`, `sp.run`, and `other_module.subprocess.run`.
            if ((isinstance(owner, ast.Name) and owner.id in self.modules)
                    or (isinstance(owner, ast.Attribute)
                        and owner.attr == "subprocess")):
                return node.attr
        if isinstance(node, ast.Name):
            return self.spawners.get(node.id)
        return None

    def here(self) -> str:
        return self.scope[-1] if self.scope else ""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        spawner = self.spawner_of(node.func)
        if spawner is None:
            self.generic_visit(node)
            return
        if spawner in ALWAYS_TEXT:
            self.always_text.append((node.lineno, self.here(), spawner))
        else:
            self.judge(node, spawner)
        # The callee is the call, not a reference to it.
        for child in (*node.args, *node.keywords):
            self.visit(child)

    def judge(self, node: ast.Call, spawner: str) -> None:
        named: set[str] = set()
        asks = expands = False
        for keyword in node.keywords:
            if keyword.arg is None:
                expands = True
            elif keyword.arg in ("text", "universal_newlines"):
                # `text=False` is bytes; anything else (True, a name) is text.
                asks = asks or not is_constant(keyword.value, False)
                named.add(keyword.arg)
            elif keyword.arg in ("encoding", "errors"):
                asks = asks or not is_constant(keyword.value, None)
                if (names_utf8(keyword.value) if keyword.arg == "encoding"
                        else not is_constant(keyword.value, None)):
                    named.add(keyword.arg)
            else:
                named.add(keyword.arg)
        if asks:
            self.found.append((node.lineno, self.here(), named))
        elif expands:
            self.opaque.append((
                node.lineno, self.here(),
                f"expands `**` into `subprocess.{spawner}(...)`"))

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self.spawner_of(node) is not None:
            self.refer(node, node.attr)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in self.spawners:
            self.refer(node, self.spawners[node.id])

    def refer(self, node: ast.expr, spawner: str) -> None:
        if id(node) not in self.annotations:
            self.opaque.append((node.lineno, self.here(),
                                f"refers to `subprocess.{spawner}` without "
                                "calling it"))


def judge_module(source: str, relative: str, exempt=EXEMPT, opaque=OPAQUE,
                 ) -> tuple[list[str], set[tuple[str, str]]]:
    """The offences in one module's `source`, and the (file, function) pairs
    whose text-mode calls were inspected. `relative` is the key EXEMPT and
    OPAQUE are read by."""
    visitor = TextModeCalls()
    visitor.visit(ast.parse(source))
    offenders: list[str] = []
    inspected: set[tuple[str, str]] = set()

    def where(line: int, function: str) -> str:
        return f"{relative}:{line} ({function or 'module level'})"

    for line, function, named in visitor.found:
        inspected.add((relative, function))
        need = exempt.get((relative, function),
                          frozenset({"encoding", "errors"}))
        if need - named:
            offenders.append(
                f"{where(line, function)} asks for text and does not name "
                f"{sorted(need - named)}")
    for line, function, name in visitor.always_text:
        if (relative, function) not in exempt:
            offenders.append(
                f"{where(line, function)} calls `subprocess.{name}`, which is "
                "always text and takes no `encoding=` before Python 3.11: "
                "call `subprocess.run` with `encoding=\"utf-8\", "
                "errors=\"replace\"` and read `.stdout`")
    for line, function, what in visitor.opaque:
        if not opaque.get((relative, function), "").strip():
            offenders.append(
                f"{where(line, function)} {what}, so the guard cannot see "
                "whether it asks for text: spell the call where it can, with "
                "`encoding=\"utf-8\", errors=\"replace\"`, or list the "
                "function in OPAQUE with the reason it cannot")
    return offenders, inspected


def test_no_shipped_text_mode_call_decodes_with_the_locale_codec():
    offenders: list[str] = []
    inspected: set[tuple[str, str]] = set()
    for path in shipped_python():
        relative = path.relative_to(REPO).as_posix()
        found, seen = judge_module(path.read_text(encoding="utf-8"), relative)
        offenders += found
        inspected |= seen
    assert ("scripts/shape_materialize.py", "run") in inspected, (
        "the scan no longer finds `run()`'s call, so it is not reading "
        "what it claims to")
    assert not offenders, (
        "a text-mode `subprocess` call decodes with the LOCALE'S codec, which "
        "is ASCII under a C locale and the ANSI code page on Windows, and git "
        "writes UTF-8 (#217). Add `encoding=\"utf-8\", errors=\"replace\"`: "
        "a literal `None` or another codec names nothing, and `encoding=` or "
        "`errors=` alone is text mode too (#321):\n  "
        + "\n  ".join(offenders))


def module_case(name: str, bad: str, fixed: str, needle: str):
    return pytest.param(textwrap.dedent(bad), textwrap.dedent(fixed), needle,
                        id=name)


#: One synthetic module per form the guard did not used to read: the module
#: the guard must flag, the same module fixed, and what the finding says.
SYNTHETIC = [
    module_case("from-import", """
        from subprocess import run

        def read(argv):
            return run(argv, capture_output=True, text=True).stdout
        """, """
        from subprocess import run

        def read(argv):
            return run(argv, capture_output=True, text=True,
                       encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding', 'errors']"),
    module_case("from-import-as", """
        from subprocess import check_output as capture

        def read(argv):
            return capture(argv, text=True)
        """, """
        from subprocess import check_output as capture

        def read(argv):
            return capture(argv, text=True, encoding="utf-8", errors="replace")
        """, "does not name ['encoding', 'errors']"),
    module_case("star-import", """
        from subprocess import *

        def read(argv):
            return check_output(argv, universal_newlines=True)
        """, """
        from subprocess import *

        def read(argv):
            return check_output(argv, universal_newlines=True,
                                encoding="utf-8", errors="replace")
        """, "does not name ['encoding', 'errors']"),
    module_case("module-under-another-name", """
        import subprocess as sp

        def read(argv):
            return sp.run(argv, capture_output=True, text=True).stdout
        """, """
        import subprocess as sp

        def read(argv):
            return sp.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding', 'errors']"),
    module_case("module-assigned-to-a-name", """
        import subprocess
        sp = subprocess
        again = sp

        def read(argv):
            return again.Popen(argv, stdout=sp.PIPE, text=True)
        """, """
        import subprocess
        sp = subprocess
        again = sp

        def read(argv):
            return again.Popen(argv, stdout=sp.PIPE, text=True,
                               encoding="utf-8", errors="replace")
        """, "does not name ['encoding', 'errors']"),
    module_case("module-assigned-with-an-annotation", """
        import subprocess
        sp: object = subprocess

        def read(argv):
            return sp.run(argv, capture_output=True, text=True).stdout
        """, """
        import subprocess
        sp: object = subprocess

        def read(argv):
            return sp.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding', 'errors']"),
    module_case("module-annotated-after-a-plain-alias", """
        import subprocess
        sp = subprocess
        again: "ModuleType" = sp

        def read(argv):
            return again.Popen(argv, stdout=sp.PIPE, text=True)
        """, """
        import subprocess
        sp = subprocess
        again: "ModuleType" = sp

        def read(argv):
            return again.Popen(argv, stdout=sp.PIPE, text=True,
                               encoding="utf-8", errors="replace")
        """, "does not name ['encoding', 'errors']"),
    module_case("spawner-assigned-with-an-annotation", """
        import subprocess
        from typing import Callable

        run: Callable = subprocess.run
        """, """
        import subprocess

        def run(argv):
            return subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        """, "refers to `subprocess.run` without calling it"),
    module_case("imported-spawner-assigned-with-an-annotation", """
        from subprocess import check_output
        from typing import Callable

        read: Callable = check_output
        """, """
        from subprocess import check_output

        def read(argv):
            return check_output(argv, text=True, encoding="utf-8",
                                errors="replace")
        """, "refers to `subprocess.check_output` without calling it"),
    module_case("module-reached-through-another", """
        import shape_materialize

        def read(argv):
            return shape_materialize.subprocess.run(
                argv, capture_output=True, text=True).stdout
        """, """
        import shape_materialize

        def read(argv):
            return shape_materialize.subprocess.run(
                argv, capture_output=True, text=True,
                encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding', 'errors']"),
    module_case("encoding-alone", """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8").stdout
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8", errors="replace").stdout
        """, "does not name ['errors']"),
    module_case("errors-alone", """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  errors="replace").stdout
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding']"),
    module_case("encoding-none", """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True, text=True,
                                  encoding=None, errors="replace").stdout
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace").stdout
        """, "does not name ['encoding']"),
    module_case("encoding-not-utf-8", """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True, text=True,
                                  encoding="cp1252", errors="replace").stdout
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True, text=True,
                                  encoding="UTF8", errors="replace").stdout
        """, "does not name ['encoding']"),
    module_case("errors-none", """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8", errors=None).stdout
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8", errors="replace").stdout
        """, "does not name ['errors']"),
    module_case("keyword-expansion", """
        import subprocess

        def read(argv, **options):
            return subprocess.run(argv, capture_output=True, **options).stdout
        """, """
        import subprocess

        def read(argv, **options):
            return subprocess.run(argv, capture_output=True,
                                  encoding="utf-8", errors="replace",
                                  **options).stdout
        """, "expands `**` into `subprocess.run(...)`"),
    module_case("keyword-expansion-into-popen", """
        import subprocess

        def start(argv, options):
            with subprocess.Popen(argv, stdout=subprocess.PIPE,
                                  **options) as child:
                return child.stdout.read()
        """, """
        import subprocess

        def start(argv, options):
            with subprocess.Popen(argv, stdout=subprocess.PIPE) as child:
                return child.stdout.read()
        """, "expands `**` into `subprocess.Popen(...)`"),
    module_case("getoutput", """
        import subprocess

        def read():
            return subprocess.getoutput("git status")
        """, """
        import subprocess

        def read():
            return subprocess.run(["git", "status"], capture_output=True,
                                  text=True, encoding="utf-8",
                                  errors="replace").stdout
        """, "calls `subprocess.getoutput`"),
    module_case("getstatusoutput", """
        import subprocess

        def read():
            return subprocess.getstatusoutput("git status")
        """, """
        import subprocess

        def read():
            proc = subprocess.run(["git", "status"], capture_output=True,
                                  text=True, encoding="utf-8",
                                  errors="replace")
            return proc.returncode, proc.stdout
        """, "calls `subprocess.getstatusoutput`"),
    module_case("getoutput-from-import", """
        from subprocess import getoutput

        def read():
            return getoutput("git status")
        """, """
        from subprocess import run

        def read():
            return run(["git", "status"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace").stdout
        """, "calls `subprocess.getoutput`"),
    module_case("partial", """
        import functools
        import subprocess

        read = functools.partial(subprocess.run, text=True)
        """, """
        import subprocess

        def read(argv):
            return subprocess.run(argv, text=True, encoding="utf-8",
                                  errors="replace")
        """, "refers to `subprocess.run` without calling it"),
    module_case("alias-of-a-spawner", """
        import subprocess

        runner = subprocess.check_output
        """, """
        import subprocess

        def runner(argv):
            return subprocess.check_output(argv, text=True, encoding="utf-8",
                                           errors="replace")
        """, "refers to `subprocess.check_output` without calling it"),
    module_case("bare-spawner-passed-on", """
        from subprocess import run

        def read_all(argvs):
            return list(map(run, argvs))
        """, """
        from subprocess import run

        def read_all(argvs):
            return [run(argv, capture_output=True) for argv in argvs]
        """, "refers to `subprocess.run` without calling it"),
    module_case("base-class", """
        import subprocess

        class Child(subprocess.Popen):
            pass
        """, """
        import subprocess

        class Child:
            def start(self, argv):
                return subprocess.Popen(argv, stdout=subprocess.PIPE)
        """, "refers to `subprocess.Popen` without calling it"),
]


@pytest.mark.parametrize("bad, fixed, needle", SYNTHETIC)
def test_the_guard_flags_each_call_form_it_used_to_walk_past(
        bad, fixed, needle):
    offenders, _ = judge_module(bad, "synthetic.py")
    assert offenders, "the guard read this module and found nothing wrong"
    assert needle in "\n".join(offenders), offenders


@pytest.mark.parametrize("bad, fixed, needle", SYNTHETIC)
def test_the_guard_passes_the_same_module_once_it_is_fixed(
        bad, fixed, needle):
    offenders, _ = judge_module(fixed, "synthetic.py")
    assert not offenders, offenders


#: What the guard read before #321 and still reads the same: a text-mode call
#: with no codec named is refused; everything else here is let through.
UNCHANGED_REFUSED = [
    pytest.param("subprocess.run(argv, text=True)",
                 "does not name ['encoding', 'errors']", id="text"),
    pytest.param("subprocess.Popen(argv, universal_newlines=True)",
                 "does not name ['encoding', 'errors']",
                 id="universal-newlines"),
    pytest.param("subprocess.check_output(argv, text=True, errors='replace')",
                 "does not name ['encoding']", id="errors-with-text"),
    pytest.param("subprocess.check_call(argv, text=True, encoding='utf-8')",
                 "does not name ['errors']", id="encoding-with-text"),
]

UNCHANGED_ALLOWED = [
    pytest.param("subprocess.run(argv, capture_output=True)", id="bytes"),
    pytest.param("subprocess.run(argv, capture_output=True, text=False)",
                 id="text-false"),
    pytest.param("subprocess.run(argv, capture_output=True, "
                 "universal_newlines=False)", id="universal-newlines-false"),
    pytest.param("subprocess.run(argv, capture_output=True, encoding=None, "
                 "errors=None)", id="no-codec-asked-for"),
    pytest.param("subprocess.run(argv, text=True, encoding='utf-8', "
                 "errors='replace')", id="both-named"),
    pytest.param("subprocess.run(argv, text=True, encoding='utf-8', "
                 "errors='replace', **options)",
                 id="expansion-after-both-named"),
    pytest.param("subprocess.run(argv, stdout=subprocess.PIPE, "
                 "stdin=subprocess.DEVNULL)", id="constants-are-not-calls"),
    pytest.param("run(argv, text=True)", id="a-run-of-its-own"),
]


@pytest.mark.parametrize("call, needle", UNCHANGED_REFUSED)
def test_what_the_guard_refused_before_it_still_refuses(call, needle):
    source = f"import subprocess\n\n\ndef read(argv):\n    return {call}\n"
    offenders, inspected = judge_module(source, "synthetic.py")
    assert needle in "\n".join(offenders), offenders
    assert ("synthetic.py", "read") in inspected


@pytest.mark.parametrize("call", UNCHANGED_ALLOWED)
def test_what_the_guard_let_through_before_it_still_lets_through(call):
    source = (f"import subprocess\n\n\ndef run(*a, **k):\n    return a\n\n\n"
              f"def read(argv, options=None):\n    return {call}\n")
    offenders, _ = judge_module(source, "synthetic.py")
    assert not offenders, offenders


def test_an_annotation_is_not_a_spawner_it_refers_to():
    source = textwrap.dedent("""
        import subprocess
        from subprocess import Popen, CompletedProcess

        def start(argv) -> subprocess.Popen:
            child: subprocess.Popen = None
            pending: subprocess.Popen
            return child

        def finish(proc: "subprocess.Popen", other: Popen) -> CompletedProcess:
            return other
        """)
    offenders, _ = judge_module(source, "synthetic.py")
    assert not offenders, offenders


def test_a_listed_function_may_call_what_the_guard_refuses():
    source = textwrap.dedent("""
        import subprocess

        def read():
            return subprocess.getoutput("git status")
        """)
    assert judge_module(source, "synthetic.py")[0]
    listed = {("synthetic.py", "read"): frozenset()}
    assert judge_module(source, "synthetic.py", exempt=listed)[0] == []
    other = {("synthetic.py", "somewhere_else"): frozenset()}
    assert judge_module(source, "synthetic.py", exempt=other)[0]


def test_an_opaque_call_is_listed_with_a_reason_or_not_at_all():
    source = textwrap.dedent("""
        import subprocess

        def read(argv, **options):
            return subprocess.run(argv, capture_output=True, **options)
        """)
    here = ("synthetic.py", "read")
    assert judge_module(source, "synthetic.py")[0]
    why = {here: "the options are `cwd` and `env`; none can ask for text"}
    assert judge_module(source, "synthetic.py", opaque=why)[0] == []
    for blank in ("", "   "):
        assert judge_module(source, "synthetic.py", opaque={here: blank})[0]
    assert judge_module(source, "synthetic.py",
                        opaque={("synthetic.py", "elsewhere"): "no"})[0]


def test_every_opaque_row_gives_its_reason():
    assert all(reason.strip() for reason in OPAQUE.values())
