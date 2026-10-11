# SPDX-License-Identifier: Apache-2.0
"""A name the plan writer quotes is ONE line the plan's loader reads back as
that same name, whatever characters it holds (#199).

macOS writes a folder's custom icon as a file named `Icon\\r`, and it is
tracked in plenty of repositories. `y()` quoted such a name but escaped only
a backslash and a double quote, so the carriage return went into the plan
raw; `repo_shape`'s reader takes a file line by line (`str.splitlines`, which
also ends a line at `\\x0b`, `\\x0c`, `\\x1c`-`\\x1e`, `\\x85`, `\\u2028` and
`\\u2029`), so `plan` exited 0 and `check` refused the whole plan as
`yaml-unparsable`, with no entry anybody could edit. A name that is not UTF-8
(a surrogate, as `Source.tree` keeps it) did worse: `plan` raised mid-write
and left the plan empty.

ONE TABLE, SHARED. `repo_shape.DOUBLE_QUOTED_ESCAPES` and
`CODE_POINT_ESCAPES` are read by the reader (`_unescape`) and by the writer
(`double_quoted`, which `y` calls), so the two cannot disagree. The tests
below prove the round trip for the names that broke it, for every code point
up to U+02FF and a sample above, and for seeded random strings of them.
"""

from __future__ import annotations

import importlib.util
import os
import random
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, blank_unnamed_pin_sources, git,
                      make_source_repo, resolve, write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
from repo_shape import (  # noqa: E402
    CODE_POINT_ESCAPES, DOUBLE_QUOTED_ESCAPES, double_quoted, load_yaml,
    parse_yaml,
)

PATHS = "paths"
PLAN_FILE = "adoption-plan.yaml"
#: Ends a name in `-z` output, and in what `update-index -z` is given.
NUL = b"\x00"


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module: `y` has no command line."""
    module_spec = importlib.util.spec_from_file_location(
        "adopt_plan_escapes", ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


def reads_back(written: str, value: str) -> bool:
    """The brief's two equalities: `written` after `key: ` and as a `- `
    item gives `value` back."""
    return (parse_yaml(f"k: {written}\n") == {"k": value}
            and parse_yaml(f"- {written}\n") == [value])


# --- the names that broke the plan -----------------------------------------

#: `(name, how the plan spells it)`. The spelling is pinned, so the escape
#: each class gets is a decision on the page and not an accident: a
#: backslash and a double quote as before, `\\n` `\\r` `\\t` by name, and every
#: other character `str.isprintable` refuses by code point, in the shortest
#: of `\\xNN`, `\\uNNNN`, `\\UNNNNNNNN` that holds it.
NAMED = [
    ("Icon\r", '"Icon\\r"'),
    # `_PLAIN_RE` ended at `$`, which matches before a FINAL newline, so this
    # one was written bare over two lines; it ends at `\Z` now.
    ("Icon\n", '"Icon\\n"'),
    ("a\nb", '"a\\nb"'),
    ("a\r\nb", '"a\\r\\nb"'),
    ("t\tab", '"t\\tab"'),
    ("\x00", '"\\x00"'),
    ("\x01", '"\\x01"'),
    ("\x1b[31m", '"\\x1b[31m"'),
    ("\x7f", '"\\x7f"'),
    ("\u0085", '"\\x85"'),
    ("\u00a0", '"\\xa0"'),
    ("\u2028", '"\\u2028"'),
    ("\u2029", '"\\u2029"'),
    ("\u202e", '"\\u202e"'),
    ("\ufeff", '"\\ufeff"'),
    ("\U000e0001", '"\\U000e0001"'),
    (" ", '" "'),
    ('a\\"b\\', '"a\\\\\\"b\\\\"'),
    ("D:\\a\\_temp\\t", '"D:\\\\a\\\\_temp\\\\t"'),
    ("\\x41", '"\\\\x41"'),
    # Not UTF-8: `Source.tree` keeps the byte 0xE9 as this surrogate, which
    # no UTF-8 file can hold raw; `\udce9` reads back as the same surrogate.
    ("caf\udce9", '"caf\\udce9"'),
    # Printable is written as it is, inside the quotes.
    ("café 日本", '"café 日本"'),
]


@pytest.mark.parametrize("name, spelled", NAMED,
                         ids=[ascii(name) for name, _ in NAMED])
def test_a_name_is_one_line_the_loader_reads_back(adopter, name, spelled):
    written = adopter.y(name)
    assert written == spelled
    assert written.isprintable(), "one line of printable text"
    assert reads_back(written, name)
    entry: list[str] = []
    adopter.Entry(name, adopter.Verdict("spec", "r", "why", "high"), 1,
                  1).write(entry)
    assert parse_yaml(f"{PATHS}:\n" + "\n".join(entry) + "\n") == {PATHS: [{
        "path": name, "leg": "spec", "confidence": "high", "rule": "r",
        "reason": "why", "files": 1, "bytes": 1, "review_required": False}]}


# --- every string ----------------------------------------------------------

#: Above U+02FF, the characters a name or a plan is likeliest to meet and
#: least likely to be seen in: separators, zero-width and bidirectional
#: controls, the BOM, both surrogate halves and the `surrogateescape` range,
#: private use, the edges of the BMP, astral letters and the last code point.
ABOVE = [0x0300, 0x0378, 0x061C, 0x1680, 0x180E, 0x2000, 0x200B, 0x200E,
         0x2028, 0x2029, 0x202E, 0x205F, 0x2066, 0x2069, 0x3000, 0x65E5,
         0xD800, 0xDBFF, 0xDC00, 0xDC80, 0xDCE9, 0xDCFF, 0xDFFF, 0xE000,
         0xF8FF, 0xFEFF, 0xFFFD, 0xFFFE, 0xFFFF, 0x10000, 0x1F600, 0xE0001,
         0xE007F, 0xF0000, 0x10FFFF]


def generated() -> list[str]:
    """Every code point from U+0000 to U+02FF alone, `ABOVE` alone, and
    seeded random strings of up to eight of them, plus a random sample of
    the rest of the code space."""
    rng = random.Random(199)
    alphabet = ([chr(code) for code in range(0x300)]
                + [chr(code) for code in ABOVE]
                + [chr(rng.randrange(0x300, 0x110000)) for _ in range(200)])
    strings = list(alphabet)
    strings += ["".join(rng.choice(alphabet)
                        for _ in range(rng.randint(0, 8)))
                for _ in range(5000)]
    return strings


def test_every_generated_string_reads_back(adopter):
    """`parse_yaml(f"k: {y(v)}\\n") == {"k": v}` and
    `parse_yaml(f"- {y(v)}\\n") == [v]`, for `y` and for its quoted spelling
    alone (`double_quoted`, which is what `y` falls back to for anything it
    does not write plain)."""
    failures = []
    for value in generated():
        for writer in (adopter.y, double_quoted):
            written = writer(value)
            if not (written.isprintable() and reads_back(written, value)):
                failures.append((value, written))
    assert not failures, failures[:10]


# --- the table the writer and the reader share -----------------------------

def test_each_named_escape_is_written_and_read_from_the_one_table():
    for letter, char in DOUBLE_QUOTED_ESCAPES.items():
        assert double_quoted(char) == f'"\\{letter}"'
        assert parse_yaml(f'k: "\\{letter}"\n') == {"k": char}


#: Characters `str.isprintable` refuses, at each width: C0 and C1 controls,
#: a soft hyphen, an unassigned code point, a separator, a surrogate, a
#: noncharacter, an astral format control, private use, the last code point.
UNPRINTABLE = [0x01, 0x85, 0x9F, 0xAD, 0x0378, 0x2028, 0xDCE9, 0xFFFF,
               0x1D173, 0xE0001, 0xF0000, 0x10FFFF]


@pytest.mark.parametrize("code", UNPRINTABLE, ids=hex)
def test_a_code_point_takes_the_shortest_escape_that_holds_it(code):
    assert not chr(code).isprintable()
    letter, digits = next((letter, digits)
                          for letter, digits in CODE_POINT_ESCAPES.items()
                          if code < 16 ** digits)
    spelled = f"\\{letter}{code:0{digits}x}"
    assert double_quoted(chr(code)) == f'"{spelled}"'
    assert parse_yaml(f'k: "{spelled}"\n') == {"k": chr(code)}


@pytest.mark.parametrize("body, read", [
    ("\\q", "\\q"),
    ("\\x4", "\\x4"),
    ("\\xZZ", "\\xZZ"),
    ("\\x+1", "\\x+1"),
    ("\\x 1", "\\x 1"),
    ("\\u12", "\\u12"),
    ("\\u0_41", "\\u0_41"),
    ("\\U00110000", "\\U00110000"),
    ("\\X41", "\\X41"),
    ("\\x41", "A"),
    ("\\x4142", "A42"),
    ("\\u00E9", "é"),
    ("\\\\x41", "\\x41"),
    ("\\\\\\x41", "\\A"),
], ids=lambda value: ascii(value))
def test_the_reader_resolves_exactly_what_the_writer_writes(body, read):
    """An escape the table does not hold keeps its backslash, as `\\q`
    always has; a code-point escape is exactly its count of ASCII hex digits
    (`int(..., 16)` would take `+1`, ` 1` and `0_41`); and the reader is one
    pass, so a written backslash is never the start of an escape."""
    assert parse_yaml(f'k: "{body}"\n') == {"k": read}


def test_a_value_spelled_as_an_escape_is_not_read_as_one(adopter):
    """The writer doubles a backslash, so a NAME that is the text `\\r` or
    `\\udce9` comes back as that text, not as the character."""
    for text in ("\\r", "\\udce9", "\\U0001F600", "Icon\\r"):
        assert reads_back(adopter.y(text), text)


# --- end to end: `plan`, then `check`, on a source that holds the name -----

#: `(the name as git records it, as the plan spells it, whether `plan` asks
#: about it)`. The SAME name is put at the top level, where it is an entry of
#: its own, and under `docs/`, which the rules send to the spec leg as one
#: entry. A name with no extension no rule places, so `plan` asks; `.txt` is
#: code by the extension table.
ODD_NAMES = [
    pytest.param(b"Icon\r", '"Icon\\r"', True, id="carriage-return"),
    pytest.param(b"caf\xe9.txt", '"caf\\udce9.txt"', False, id="not-utf8"),
    pytest.param("n\u0085el".encode(), '"n\\x85el"', True, id="next-line"),
    pytest.param("l\u2028s".encode(), '"l\\u2028s"', True,
                 id="line-separator"),
]


def git_bytes(source: Path, *args: str, stdin: bytes) -> bytes:
    """`git <args>` in `source`, fed and answering BYTES."""
    done = subprocess.run(["git", *args], cwd=str(source), input=stdin,
                          capture_output=True, check=False)
    if done.returncode:
        pytest.skip(f"git {args[0]} refuses it here: {done.stderr!r}")
    return done.stdout


def odd_source(base: Path, name: bytes) -> Path:
    """`conftest.SYNTHETIC_TREE` with a file `name` at the top level and
    under `docs/`, added to git's index and committed WITHOUT A CHECKOUT, so
    no filesystem has to hold the name (Windows refuses `\\r` in one): `plan`
    reads the commit with `git ls-tree`. Skipped where git does not keep the
    name in the tree, which only git can say: `update-index` ignores a path
    it will not record, and exits 0."""
    source = make_source_repo(base / "Thing")
    blob = git_bytes(source, "hash-object", "-w", "--stdin",
                     stdin=b"an icon\n").strip()
    names = [name, b"docs/" + name]
    git_bytes(source, "update-index", "-z", "--index-info", stdin=b"".join(
        b"100644 " + blob + b"\t" + each + NUL for each in names))
    git("-c", "user.name=Source Human", "-c",
        "user.email=source@invalid.example", "commit", "-qm",
        "Add a folder icon", cwd=source)
    held = git_bytes(source, "ls-tree", "-r", "-z", "--name-only", "HEAD",
                     stdin=b"").split(NUL)
    missing = [each for each in names if each not in held]
    if missing:
        pytest.skip(f"git does not keep {missing!r} in a tree here")
    return source


def checked(plan: Path) -> subprocess.CompletedProcess:
    """`check`, answered in BYTES: a FINDING that names `Icon\\r` raw would
    read as `Icon\\n` through text mode, which turns a lone `\\r` into one."""
    env = blank_unnamed_pin_sources({**os.environ, "LANES_LANE": ""}, {})
    return subprocess.run(
        [sys.executable, str(ADOPT), "check", "--plan", str(plan)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)


#: The coverage findings, any one of which would mean the escaped entry did
#: not come back as the name in the tree.
COVERAGE = (b"plan-uncovered", b"plan-empty-entry", b"plan-covered-twice",
            b"plan-duplicate-path")
#: The entries of `SYNTHETIC_TREE` that `plan` asks about, answered.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))


#: Each of `SYNTHETIC_TREE`'s three questions is one such FINDING.
UNRESOLVED = b"FINDING plan-unresolved: "


@pytest.mark.parametrize("name, spelled, asks", ODD_NAMES)
def test_plan_writes_the_name_as_one_entry_check_parses(adopter, tmp_path,
                                                        name, spelled, asks):
    """The repro of #199. `plan` exited 0 and `check` refused the plan as
    `yaml-unparsable`; for the name that is not UTF-8, `plan` raised and left
    the plan empty. Now the plan holds the name on ONE line, `check` reads
    it, every path in the tree is covered once, and an entry still to be
    answered is a FINDING naming it. `plan ok` is not asserted: whether
    `check` accepts such a path is #196's question."""
    source = odd_source(tmp_path, name)
    text_name = name.decode("utf-8", "surrogateescape")
    plan = tmp_path / PLAN_FILE
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    assert "Traceback" not in written.stderr
    # Printed in the terminal report the way a question spells it.
    assert adopter._spelled(text_name) in written.stdout

    raw = plan.read_bytes()
    assert raw.count(f"\n  - path: {spelled}\n".encode()) == 1
    assert all(line.isprintable()
               for line in raw.decode("utf-8").split("\n")), (
        "every line of the plan is printable text")
    rows = {row["path"]: row for row in load_yaml(plan)[PATHS]}
    assert text_name in rows and f"docs/{text_name}" not in rows
    assert rows["docs/"]["leg"] == "spec"

    result = checked(plan)
    said = result.stdout + result.stderr
    assert result.returncode in (0, 1), said
    assert b"yaml-unparsable" not in said and b"Traceback" not in said
    assert not [code for code in COVERAGE if code in said], said
    assert (rows[text_name]["leg"] is None) == asks
    assert said.count(UNRESOLVED) == len(ANSWERS) + asks, said
    if name == b"Icon\r":
        # Bytes, and ASCII on every platform's stderr: the FINDING names it.
        assert UNRESOLVED + b"Icon\r still has `leg: null`" in said
    if asks:
        resolve(plan, spelled, "root")
    for path, leg in ANSWERS:
        resolve(plan, path, leg)

    answered = checked(plan)
    said = answered.stdout + answered.stderr
    assert answered.returncode in (0, 1), said
    assert b"yaml-unparsable" not in said
    assert b"plan-unresolved" not in said
    assert not [code for code in COVERAGE if code in said], said
    assert {row["path"]: row for row in load_yaml(plan)[PATHS]}[
        text_name]["leg"] == ("root" if asks else "code")


def test_the_reader_module_is_the_one_the_writer_imports(adopter):
    """`y` quotes with `repo_shape.double_quoted` itself, not a copy."""
    assert adopter.double_quoted is repo_shape.double_quoted
