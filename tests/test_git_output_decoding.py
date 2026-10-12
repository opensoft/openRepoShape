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

TWO TESTS, because the cause is one line repeated in thirty places:

  * `test_run_names_the_path_git_complained_of_under_a_c_locale` drives the
    fixed `run` in a CHILD interpreter started with `LC_ALL=C PYTHONUTF8=0`.
    A codec is fixed when the interpreter starts, so this process (UTF-8 mode
    on, or a UTF-8 locale) cannot reproduce it by setting an environment
    variable afterwards.
  * `test_no_shipped_text_mode_call_decodes_with_the_locale_codec` reads
    every shipped tool's `subprocess` calls and fails on one that asks for
    text without naming the codec, so a thirty-first cannot arrive.
"""

from __future__ import annotations

import ast
import codecs
import json
import os
import subprocess
import sys
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


#: The calls `subprocess` exposes that take `text=` and `encoding=`.
SPAWNERS = {"run", "Popen", "check_output", "check_call", "call"}

#: A call that asks for text must name BOTH, unless it is listed here. Keyed
#: by (file, the function the call is in); the value is what it must still
#: name, and the reason it differs.
EXEMPT = {
    # #196's branch gives this call both arguments; until it lands, the two
    # tools' fixes stay in separate pull requests rather than one conflicting
    # hunk.
    ("scripts/shape_materialize.py", "env_commit"): frozenset(),
    # #216's branch reads this `git grep` as BYTES (a path is bytes, and it
    # spells each one itself), which leaves nothing here to decode; the same
    # two-pull-requests reason as above.
    ("adopt-project.py", "cross_leg_references"): frozenset(),
    # The `gh api` tree listing becomes a digest: UTF-8 yes, `replace` no, for
    # a replaced byte would be a wrong digest with a confident tone. The
    # first is `scaffold-project.py --pin`'s and `adopt-project.py plan
    # --pin`'s, moved out of the scaffold for #273.
    ("scripts/shape_materialize.py", "pin_digest_from_gh"):
        frozenset({"encoding"}),
    ("scripts/repo_shape.py", "tree_digest_from_gh"): frozenset({"encoding"}),
}


def shipped_python() -> list[Path]:
    """Every Python file this standard ships, tests excluded."""
    found = [*REPO.glob("*.py"), *REPO.glob("scripts/*.py"),
             *REPO.glob("templates/**/*.py"), REPO / "bootstrap"]
    return sorted(found)


class TextModeCalls(ast.NodeVisitor):
    """Each `subprocess.<spawner>(..., text=True)` and the keywords it names."""

    def __init__(self) -> None:
        self.found: list[tuple[int, str, set[str]]] = []
        self.scope: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr in SPAWNERS
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"):
            named = {keyword.arg for keyword in node.keywords if keyword.arg}
            asks = [keyword for keyword in node.keywords
                    if keyword.arg in ("text", "universal_newlines")]
            # `text=False` is bytes; anything else (True, a variable) is text.
            if any(not (isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is False) for keyword in asks):
                self.found.append((node.lineno,
                                   self.scope[-1] if self.scope else "",
                                   named))
        self.generic_visit(node)


def test_no_shipped_text_mode_call_decodes_with_the_locale_codec():
    offenders: list[str] = []
    inspected: set[tuple[str, str]] = set()
    for path in shipped_python():
        visitor = TextModeCalls()
        visitor.visit(ast.parse(path.read_text(encoding="utf-8")))
        relative = path.relative_to(REPO).as_posix()
        for line, function, named in visitor.found:
            inspected.add((relative, function))
            need = EXEMPT.get((relative, function),
                              frozenset({"encoding", "errors"}))
            if need - named:
                offenders.append(
                    f"{relative}:{line} ({function or 'module level'}) asks "
                    f"for text and does not name {sorted(need - named)}")
    assert ("scripts/shape_materialize.py", "run") in inspected, (
        "the scan no longer finds `run()`'s call, so it is not reading "
        "what it claims to")
    assert not offenders, (
        "a text-mode `subprocess` call decodes with the LOCALE'S codec, which "
        "is ASCII under a C locale and the ANSI code page on Windows, and git "
        "writes UTF-8 (#217). Add `encoding=\"utf-8\", errors=\"replace\"`:\n  "
        + "\n  ".join(offenders))
