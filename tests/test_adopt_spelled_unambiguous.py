# SPDX-License-Identifier: Apache-2.0
"""A name a finding or a question prints reads one way only (#329).

On main at 71b58a1 `_spelled` wrote a raw byte that is not UTF-8 -- which
`Source.tree` keeps as the surrogate U+DC00 plus the byte -- as `\\xNN`, and
a character that is not printable and lies below U+0100 the same way. So the
byte 0x85 and the character U+0085 both read `\\x85`, and so did 32 more
pairs: the 32 C1 controls U+0080 to U+009F, U+00A0 and U+00AD. A question
that said `caf\\x85` could not say which entry of the plan it meant, and in
YAML, where the plan is written, `\\x85` is the character: the byte's own
entry is `"caf\\udc85"`.

Now a name is spelled as the plan's writer spells it, by the one table of
escapes (`repo_shape.double_quoted`) that its reader resolves: the character
U+0085 is `\\x85` and the byte 0x85 is `\\udc85`. Asked here of the function,
of the finding and the question that print a name, of every code point, of
the plan's own writer and reader, and of `plan` and `check` run on a source
that holds the byte and the character side by side.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, REPO, make_source_repo, run_script, write_plan

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import double_quoted, parse_yaml  # noqa: E402

PROJECT = "Northwind"
UTF8 = "utf-8"
#: The bytes 0x80 to 0xFF that are not printable as the characters of the
#: same value: the 32 C1 controls, U+00A0 (a no-break space) and U+00AD (a
#: soft hyphen). The issue's 34 pairs; a byte of 0xA1 to 0xFF is printable as
#: its character, which is not what `_spelled` calls it.
AMBIGUOUS = [*range(0x80, 0xA1), 0xAD]
EACH = pytest.mark.parametrize("byte", AMBIGUOUS,
                               ids=[f"0x{byte:02X}" for byte in AMBIGUOUS])


def as_byte(value: int) -> str:
    """The raw byte `value`, as `Source.tree` keeps one that is not UTF-8."""
    return chr(0xDC00 + value)


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_spelled", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- the function ----------------------------------------------------------

def test_the_ambiguous_names_are_the_issues_34():
    """32 C1 controls, U+00A0 and U+00AD: the bytes of 0x80 to 0xFF whose
    character is not printable. Pinned apart from the rest, so that a change
    to what counts as printable here moves this test and not a count."""
    assert len(AMBIGUOUS) == 34
    assert AMBIGUOUS == [byte for byte in range(0x80, 0x100)
                         if not chr(byte).isprintable()]


@EACH
def test_a_byte_and_the_character_of_its_value_are_spelled_apart(adopter,
                                                                 byte):
    """Each of the 34 pairs: the byte as the plan's `path:` writes it, the
    character as the plan writes it."""
    assert adopter._spelled(as_byte(byte)) == f"`\\udc{byte:02x}`"
    assert adopter._spelled(chr(byte)) == f"`\\x{byte:02x}`"


def test_a_byte_that_is_not_utf8_is_always_spelled_as_that_byte(adopter):
    """Every byte of 0x80 to 0xFF, the printable characters' too: a byte is
    `\\udcNN` and never the character of its value, which a name may hold
    beside it."""
    for byte in range(0x80, 0x100):
        assert adopter._spelled(as_byte(byte)) == f"`\\udc{byte:02x}`"
    assert adopter._spelled(chr(0xE9)) == f"`{chr(0xE9)}`"
    assert adopter._spelled(as_byte(0xE9)) == "`\\udce9`"


def test_no_two_characters_are_spelled_alike(adopter):
    """What the 34 pairs broke, over every code point of the BMP, lone
    surrogates included, and a few beyond it: no spelling is another
    character's."""
    seen: dict[str, int] = {}
    beyond = [0x10000, 0x1F600, 0xE0001, 0xFFFFF, 0x10FFFF]
    for code in [*range(0x10000), *beyond]:
        spelled = adopter._spelled(chr(code))
        assert spelled not in seen, (
            f"U+{seen[spelled]:04X} and U+{code:04X} both read {spelled}")
        seen[spelled] = code


def test_a_character_is_spelled_as_the_plan_writes_it(adopter):
    """The finding and the plan spell one name the same way, character by
    character: the plan's writer is the table, and `_spelled` asks it. A
    backslash and a double quote are the plan's own escapes since #900, and
    a backtick, which delimits the finding's name, is left out: it is
    `\\x60`, a code point the plan's reader resolves, where the plan writes
    it as it is."""
    for code in [*range(0x10000), 0x10000, 0x1F600, 0xE0001, 0x10FFFF]:
        char = chr(code)
        if char == "`":
            continue
        assert adopter._spelled_character(char) == double_quoted(char)[1:-1], (
            f"U+{code:04X}")


def test_a_backslash_and_a_backtick_are_escaped(adopter):
    """A backslash as before, and a backtick as `\\x60`, the plan's code
    point for one, which holds no backtick (#900): the backslash that went
    before it was no escape the plan's reader resolves."""
    assert adopter._spelled("a\\b`c") == "`a\\\\b\\x60c`"


def test_a_spelled_name_is_the_entry_the_plan_holds(adopter):
    """The failure, read as the reader does: a person who copies a spelled
    name into the plan between double quotes gets THAT name back, byte for
    byte, for each of the 256 characters and each of the 128 bytes. On main
    `\\x85` for the byte read back as the character; until #900 a backtick
    read back with a backslash before it, and a double quote ended the
    quoting, so none is left out."""
    names = [chr(code) for code in range(0x100)]
    names += [as_byte(byte) for byte in range(0x80, 0x100)]
    for name in names:
        body = adopter._spelled("caf" + name + "x")[1:-1]
        assert parse_yaml(f'path: "{body}"\n') == {
            "path": "caf" + name + "x"}, (body, name)


# --- a finding and a question ----------------------------------------------

@EACH
def test_plan_uncovered_names_a_byte_and_its_character_differently(adopter,
                                                                   byte):
    findings = adopter._coverage_findings(
        ["README.md"],
        ["README.md", f"Icon{as_byte(byte)}", f"Icon{chr(byte)}"])
    assert findings == [
        f"FINDING plan-uncovered: `Icon\\udc{byte:02x}` is in the source "
        "tree and in no plan entry",
        f"FINDING plan-uncovered: `Icon\\x{byte:02x}` is in the source tree "
        "and in no plan entry"]


@EACH
def test_a_question_names_a_byte_and_its_character_differently(adopter, byte):
    """`_listed` is how a question names the paths it asks about, and the
    plan carries the question."""
    listed = adopter._listed([f"a{as_byte(byte)}", f"a{chr(byte)}"])
    assert listed == f"`a\\udc{byte:02x}`, `a\\x{byte:02x}`"


# --- the messages that name a value, not a path (#255) --------------------

#: The C1 controls: the characters of 0x80 to 0x9F, which a file refuses
#: (`unwritable_reason`), so that a byte and its character can both be named.
C1 = list(range(0x80, 0xA0))


@pytest.mark.parametrize("byte", C1, ids=[f"0x{byte:02X}" for byte in C1])
def test_an_unwritable_value_names_a_byte_and_its_character_apart(adopter,
                                                                  byte):
    """`unwritable_values` names the value as Python's `repr` does, which
    spells by code point: a byte as `\\udcNN`, a character as `\\xNN`, so
    the two sentences differ, as the plan's own `elected_by:` entries do."""
    byte_said, character_said = adopter.unwritable_values(
        [("elected_by", f"a{as_byte(byte)}", "the manifest"),
         ("elected_by", f"a{chr(byte)}", "the manifest")])
    assert byte_said.startswith(f"elected_by is 'a\\udc{byte:02x}', ")
    assert character_said.startswith(f"elected_by is 'a\\x{byte:02x}', ")


def test_a_clone_url_that_is_not_text_is_named_as_the_plan_spells_it(adopter):
    """`_refuse_an_unwritable_clone_url` names the source's own path, whose
    byte 0xE9 is `\\udce9` and not the character U+00E9 a `\\xe9` is."""
    with pytest.raises(adopter.Refusal) as refused:
        adopter._refuse_an_unwritable_clone_url(f"/src/caf{as_byte(0xE9)}")
    assert "'/src/caf\\udce9'" in refused.value.detail
    assert "\\xe9" not in refused.value.detail


def test_python_repr_and_a_spelled_name_agree_on_every_character(adopter):
    """Why the two messages above need no table of their own: `repr` and
    `_spelled` escape every character alike, a backslash included. Only the
    backtick and the double quote differ, which `_spelled` escapes because
    backticks delimit the name and double quotes the plan's entry (#900),
    and `repr` does not."""
    for code in [*range(0x10000), 0x10000, 0x1F600, 0xE0001, 0x10FFFF]:
        char = chr(code)
        if char in '`"':
            continue
        assert repr(char)[1:-1] == adopter._spelled(char)[1:-1], (
            f"U+{code:04X}")


# --- plan and check, on a source that holds both ---------------------------

def source_with_both(tmp_path: Path, byte: int) -> Path:
    """A source whose head holds `Icon<byte>` and `Icon<character>`. Both go
    into git's index as `git add` would record them, so no file system has to
    hold a name it cannot (APFS refuses the first). Skipped where git will
    not record them or keep them in a tree, which only git can say."""
    source = make_source_repo(tmp_path / "Thing", {"README.md": "# Thing\n"},
                              edits=())
    names = [b"Icon" + bytes([byte]), b"Icon" + chr(byte).encode(UTF8)]
    blob = subprocess.run(["git", "hash-object", "-w", "--stdin"],
                          cwd=str(source), input=b"latin1\n",
                          capture_output=True, check=True).stdout.strip()
    added = subprocess.run(
        ["git", "update-index", "--add", "-z", "--index-info"],
        cwd=str(source), capture_output=True, check=False,
        input=b"".join(b"100644 " + blob + b"\t" + name + b"\0"
                       for name in names))
    if added.returncode:
        pytest.skip(f"git update-index refuses {names!r} here: "
                    f"{added.stderr!r}")
    committed = subprocess.run(
        ["git", "-c", "user.name=Source Human",
         "-c", "user.email=human@source.invalid",
         "commit", "-q", "-m", "A byte and a character of one value"],
        cwd=str(source), capture_output=True, check=False)
    assert committed.returncode == 0, committed.stderr
    held = subprocess.run(["git", "ls-tree", "-r", "-z", "--name-only",
                           "HEAD"], cwd=str(source), capture_output=True,
                          check=True).stdout.split(b"\0")
    if not set(names) <= set(held):
        pytest.skip(f"git does not keep {names!r} in a tree here")
    return source


@pytest.mark.parametrize("byte", [0x85, 0xA0, 0xAD],
                         ids=["next-line", "no-break-space", "soft-hyphen"])
def test_plan_and_check_name_a_byte_and_its_character_as_the_plan_does(
        tmp_path, byte):
    """THE ISSUE END TO END. `plan` writes both entries into the plan, one
    spelled `\\xNN` and one `\\udcNN`; its own table, and `check`'s findings,
    name them the same two ways. On main both read `\\xNN` in the table and in
    every finding, though the plan file held two spellings."""
    source = source_with_both(tmp_path, byte)
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    character, raw = f"Icon\\x{byte:02x}", f"Icon\\udc{byte:02x}"
    in_the_plan = re.findall(r'^  - path: "(Icon[^"]*)"$',
                             plan.read_text(encoding=UTF8), re.MULTILINE)
    assert sorted(in_the_plan) == sorted([character, raw])
    in_the_table = re.findall(r"^`(Icon[^`]*)` ", written.stdout,
                              re.MULTILINE)
    assert sorted(in_the_table) == sorted([character, raw]), written.stdout

    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    unresolved = re.findall(r"^FINDING plan-unresolved: `(Icon[^`]*)` ",
                            result.stderr, re.MULTILINE)
    assert sorted(unresolved) == sorted([character, raw]), result.stderr
    assert unresolved == in_the_plan
