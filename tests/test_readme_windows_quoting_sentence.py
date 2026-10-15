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
    sentence names, so a fourth is a fault here until the sentence names it.

Nothing runs a tool and nothing touches git: the first reads two files, the
second reads every shipped `.py` file with `ast`.
"""

from __future__ import annotations

import ast
import html
import re

from conftest import REPO

#: The sentence, cut out of README by its first and last words.
SENTENCE = re.compile(r"Printed commands are quoted for a POSIX shell.*?, "
                      r"on Windows\.")

#: The quoters whose answer follows the host: PowerShell's dialect where
#: `os.name` is `nt`, `sh`'s elsewhere.
HOST_QUOTERS = {"quote_arg", "shell_quoted", "shell_line", "shell_word"}

#: The tools the sentence names, which is every shipped file that calls one.
NAMED = {"shape-doctor.py", "scripts/family.py", "setup-project.py"}


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


def host_calls(path) -> list[int]:
    """The lines of every call in `path` to a quoter that follows the host:
    not one that forces `sh`'s dialect with a `'posix'` argument or a
    `posix=True` keyword."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(
            func, "attr", None)
        if name not in HOST_QUOTERS:
            continue
        forced = any(isinstance(arg, ast.Constant) and arg.value == "posix"
                     for arg in node.args[1:]) or any(
            isinstance(kw.value, ast.Constant)
            and (kw.value.value == "posix" or kw.value.value is True)
            for kw in node.keywords if kw.arg in ("platform", "posix"))
        if not forced:
            lines.append(node.lineno)
    return lines


def test_the_tools_that_quote_for_the_host_are_the_ones_the_sentence_names():
    quoting = {}
    for path in REPO.rglob("*.py"):
        relative = path.relative_to(REPO)
        if (relative.parts[0] == "tests" or relative.parts[0].startswith(".")
                or relative.as_posix() == "scripts/repo_shape.py"):
            continue                    # the quoters' own home is not a tool
        lines = host_calls(path)
        if lines:
            quoting[relative.as_posix()] = lines
    assert set(quoting) == NAMED, (
        "README's \"Windows, natively\" and the handbook's Windows panel name "
        "the tools whose printed lines are quoted for PowerShell on Windows. "
        f"The files that call a host-dialect quoter are {sorted(quoting)}: "
        "change the sentence in both places, then NAMED here.")
