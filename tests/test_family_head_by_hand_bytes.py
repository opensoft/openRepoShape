# SPDX-License-Identifier: Apache-2.0
"""`scripts/family.py`: the by-hand line that puts a member back on its branch
keeps the bytes of a branch name that is not UTF-8 (#1079).

WHAT WAS WRONG. A rollback that cannot check a member out prints the line to
type, from `_head_by_hand`: `git -C members/Thing checkout -q <branch> --`.
The branch is read from git with `surrogateescape`, and `shlex.quote` of a
name that holds a byte which is not UTF-8 quotes the SURROGATE: the line read
`checkout -q 'caf\\udce9' --`, where the stream the line is printed on
(`backslashreplace`, `repo_shape.py`) writes the escape as those six
characters. Typed, they name a branch that is not there, and git refuses them
as an invalid reference. The line appears only once the rollback's own
checkout has failed, so it is the person's one way back.

NOW a name that is not UTF-8 is printed as `"$(printf '<escapes>')"`: each
byte that is not printable ASCII is a three-digit octal escape (`\\351`), and
so are `'`, `\\`, `%` and `!`, so any POSIX shell hands git the exact bytes and
no shell's history scanner reads the line. A UTF-8 name is `shlex.quote`d as
before, byte for byte.

`_head_by_hand` is asked directly: on this tree `_member_head` still raises on
a branch that is not UTF-8 (#1072 fixes that), so the rollback is not run end
to end. The line is run through a shell as the person types it (`sh`, `dash`,
`bash` and `zsh`, macOS's default), text as the printing stream writes it, in
a repository that really holds the branch.
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (IDENTITY_CONFIG, REPO, WINDOWS_SKIP,
                      load_without_bytecode,
                      skip_where_a_name_cannot_be_not_utf_8)

SHELLS = [pytest.param(name, id=name)
          for name in ("sh", "dash", "bash", "zsh")]

#: `caf` and the Latin-1 byte for `e` with an acute: not UTF-8, so git holds
#: it as the bytes `63 61 66 e9` and Python reads it as `caf` and U+DCE9.
LATIN_1 = b"caf\xe9"

#: A name git CAN hold that is full of what a shell or `printf` reads as
#: something: the apostrophe, `%` twice (`%s` and `%d` are conversions), the
#: double quote, `$`, backticks, and braces; and one byte that is not UTF-8.
#: (`\\` is not a ref name character, so it has its own row below.)
ODD_REF = b"it's%s%d-50%-\"$HOME`x`-{1,2}-;&|<>()!#-" + b"\xe9"

#: Every byte but NUL, which no name holds, and with the newline in the
#: middle: `$(...)` strips a trailing one, which no ref name can end in. Not a
#: name git would create (controls, space, `\\`, `~`, `^`, `:`, `?`, `*`, `[`
#: are refused), but the line has to hold for any bytes it is given.
EVERY_BYTE = bytes(range(1, 256)) + b"\n" + b"z"

#: What the person's shell makes of `word`, as the bytes of `printf %s`.
ECHO = "printf %s "


def family_module():
    """`scripts/family.py` as a module, no bytecode written beside it."""
    return load_without_bytecode(REPO / "scripts" / "family.py",
                                 "family_head_by_hand_under_test")


def read_as_the_module_does(raw: bytes) -> str:
    """A branch name as `family.py` reads git's bytes: `surrogateescape`, so
    the byte that is not UTF-8 is a lone surrogate U+DC80 to U+DCFF."""
    return raw.decode("utf-8", "surrogateescape")


def printed(line: str) -> bytes:
    """What the person reads on the screen and types: the line as the
    stream `repo_shape` leaves on stdout writes it, with
    `errors="backslashreplace"`. A surrogate no UTF-8 stream can write comes
    out as its escape, `\\udce9`; every other character as itself."""
    return line.encode("utf-8", "backslashreplace")


def shell_or_skip(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        pytest.skip(f"no `{name}` on this system")
    return path


def run_typed(shell: str, typed: bytes,
              cwd: Path) -> subprocess.CompletedProcess:
    """`typed`, given to `<shell> -c` as one command, as bytes."""
    return subprocess.run([shell, "-c", typed], cwd=str(cwd),
                          capture_output=True, check=False)


def git_in(repo: Path, *args: str) -> subprocess.CompletedProcess:
    """`git <args>` in `repo` under the suite's identity, output as BYTES: a
    branch that is not UTF-8 cannot be read back as text."""
    return subprocess.run(["git", *IDENTITY_CONFIG, "-C", str(repo), *args],
                          capture_output=True, check=True)


def repo_on_main_holding(tmp_path: Path, branch: str) -> Path:
    """A repository with a commit, a branch called `branch` (the name git is
    given as `os.fsencode` makes it) and HEAD on `main`, as a rollback that
    failed to check the member out leaves it."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    repo = tmp_path / "Thing"
    repo.mkdir()
    git_in(repo, "init", "-q", "-b", "main")
    git_in(repo, "commit", "-q", "--allow-empty", "-m", "first")
    git_in(repo, "branch", branch)
    git_in(repo, "switch", "-q", branch)
    git_in(repo, "switch", "-q", "main")
    assert git_in(repo, "symbolic-ref", "HEAD").stdout == b"refs/heads/main\n"
    return repo


@WINDOWS_SKIP
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("raw", [
    pytest.param(LATIN_1, id="caf-e9"),
    pytest.param(ODD_REF, id="apostrophe-percent-and-more"),
])
def test_the_printed_line_puts_the_member_back_on_a_branch_that_is_not_utf8(
        tmp_path, shell, raw):
    """The row of the issue, and the row whose name is full of what `printf`
    and the shell read as syntax: typed, the line leaves git ON the branch,
    by the bytes `symbolic-ref` reports."""
    shell = shell_or_skip(shell)
    branch = read_as_the_module_does(raw)
    repo = repo_on_main_holding(tmp_path, branch)
    line = family_module()._head_by_hand(str(repo), "0" * 40, branch)

    done = run_typed(shell, printed(line), tmp_path)

    assert done.returncode == 0, done.stderr
    assert git_in(repo, "symbolic-ref", "HEAD").stdout == (
        b"refs/heads/" + raw + b"\n")


def test_the_line_for_the_issues_branch_is_spelled_exactly():
    """The text a person is shown for `caf` and the byte E9: ASCII, with the
    byte as an octal escape inside `printf`'s quotes, in double quotes."""
    line = family_module()._head_by_hand(
        "members/Thing", "0" * 40, read_as_the_module_does(LATIN_1))

    assert line == ("git -C members/Thing checkout -q "
                    "\"$(printf 'caf\\351')\" --")
    assert line.isascii()


def test_a_name_that_is_not_utf8_never_prints_the_surrogate():
    """The line is ASCII, so it reads the same on any stream and never holds
    the text `\\udce9`, which names no branch."""
    line = family_module()._head_by_hand(
        "members/Thing", "0" * 40, read_as_the_module_does(ODD_REF))

    assert line.isascii()
    assert "udce9" not in line
    assert printed(line) == line.encode("ascii")


def test_each_byte_the_format_or_its_quotes_would_read_is_an_octal_escape():
    """`'` closes the quotation, `\\` starts an escape and `%` starts a
    conversion: each is `\\` and three octal digits, and the printable ASCII
    around them is passed through."""
    word = family_module()._branch_by_hand(
        read_as_the_module_does(b"a'b\\c%d" + b"\xe9"))

    assert word == "\"$(printf 'a\\047b\\134c\\045d\\351')\""


def test_the_bang_is_an_octal_escape_so_no_history_scanner_reads_the_line():
    """A shell with history on reads a `!` it finds in a typed line, and the
    line's word is double-quoted, where bash and zsh expand `"fix!ec"`;
    whether a `!` inside the `printf '...'` is read is each shell's own
    scanner's matter. Spelled `\\041`, the line holds none, whatever else the
    name holds. A UTF-8 name keeps `shlex.quote`, as before."""
    family = family_module()
    word = family._branch_by_hand(
        read_as_the_module_does(b"fix!ec!" + b"\xe9"))
    line = family._head_by_hand(
        "members/Thing", "0" * 40, read_as_the_module_does(b"x!" + b"\xe9"))

    assert word == "\"$(printf 'fix\\041ec\\041\\351')\""
    assert "!" not in word
    assert "!" not in line


def test_the_word_holds_printable_ascii_only_whatever_the_bytes():
    """Every control byte, DEL included, and every byte above 0x7E is an
    escape, so what is printed and typed is the characters of ASCII that
    show: none a terminal acts on, none a stream may change."""
    word = family_module()._branch_by_hand(read_as_the_module_does(EVERY_BYTE))

    assert all(" " <= char <= "~" for char in word)
    assert "\\177" in word and "\\012" in word and "\\377" in word


@WINDOWS_SKIP
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("raw", [
    pytest.param(LATIN_1, id="caf-e9"),
    pytest.param(ODD_REF, id="apostrophe-percent-and-more"),
    pytest.param(b"a'b\\n\\t\\x41\\0%d\\\\" + b"\xe9",
                 id="apostrophe-backslash-percent"),
    pytest.param(b"%s%%\xff%d", id="percent-conversions"),
    pytest.param(b"fix!ec!!\xe9", id="bang"),
    pytest.param(b"\xc3", id="a-lead-byte-alone"),
    pytest.param(b"caf\xc3\xa9-\xe9", id="utf8-letter-and-a-stray-byte"),
    pytest.param(EVERY_BYTE, id="every-byte"),
])
def test_the_shell_hands_git_the_exact_bytes(shell, raw, tmp_path):
    """The word, read by a shell as the person's shell reads it: what
    `printf %s <word>` writes is the name's bytes, whatever they are. Git
    cannot hold some of these names (`\\`, controls), so the word is asked
    for itself."""
    shell = shell_or_skip(shell)
    word = family_module()._branch_by_hand(read_as_the_module_does(raw))

    done = run_typed(shell, (ECHO + word).encode("ascii"), tmp_path)

    assert done.returncode == 0, done.stderr
    assert done.stdout == raw


@pytest.mark.parametrize("branch", [
    "main",
    "feature/x-1.2",
    "release@v1",
    "café",
    "中文",
    "it's",
    "100%",
    "a\\b",
    "a b",
    "$HOME",
    "x;rm",
    "café'%\\",
    "fix!ec",
    "café!",
])
def test_a_utf8_name_is_quoted_exactly_as_shlex_quote_has_always_done(branch):
    """A branch that is UTF-8 text, however odd, prints as it did before:
    `shlex.quote`'s word, and the line around it unchanged."""
    family = family_module()

    assert family._branch_by_hand(branch) == shlex.quote(branch)
    assert family._head_by_hand("members/Thing", "0" * 40, branch) == (
        f"git -C members/Thing checkout -q {shlex.quote(branch)} --")


def test_no_branch_prints_the_commit_and_the_path_is_quoted_as_before():
    """The two other parts of the line are not touched: a member that was on
    no branch is put back at its commit, and the path keeps `shlex.quote`."""
    family = family_module()

    assert family._head_by_hand("members/Thing", "ab" * 20, None) == (
        "git -C members/Thing checkout -q " + "ab" * 20)
    assert family._head_by_hand("my dir/Thing", "ab" * 20, "main") == (
        "git -C 'my dir/Thing' checkout -q main --")


def test_surrogateescape_reads_the_issues_branch_as_caf_and_u_dce9():
    """The premise of the rows above, checked on Python's own decode and not
    on `family.py`: a branch git holds as `caf` and the byte E9, read with
    `surrogateescape`, is `caf` and the surrogate U+DCE9, which is also what
    `os.fsdecode` gives where the file system encoding is UTF-8. The
    module's own read of such a branch is `_member_head`, #1072's, which this
    file does not test: on this tree it still raises on a name that is not
    UTF-8, so the rows above ask `_head_by_hand` directly."""
    branch = read_as_the_module_does(LATIN_1)

    assert branch == "caf" + chr(0xDCE9)
    if os.fsencode(chr(0xDCE9)) == b"\xe9":
        assert os.fsdecode(LATIN_1) == branch
