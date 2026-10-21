# SPDX-License-Identifier: Apache-2.0
"""`scripts/family.py`: the by-hand lines that check a member's legs out again
keep the bytes of a leg's path that is not UTF-8 (#1086).

WHAT WAS WRONG. A `remove` whose rollback cannot check the member out again
prints the lines to type (`PinRollback._work_tree_by_hand`). Two of them name
a leg: `git -C members/<P> ... submodule update --init --no-fetch -- <leg>`,
and `git -C members/<P>/<leg> checkout -q <branch> --` for a leg that was on
a branch. A leg's path is read from the member's `ls-files -z` with
`surrogateescape`, and `shlex.quote` of a path that holds a byte which is not
UTF-8 quotes the SURROGATE, which the printing stream (`backslashreplace`,
`repo_shape.py`) writes as the six characters `\\udce9`. Typed, those name no
path: the `update` refuses its pathspec and the `checkout` cannot change into
the directory. The member's own path comes from `family.yaml`, UTF-8 text,
and is not touched.

NOW such a path is printed as `"$(printf '<escapes>/')"`, the form #1079 gave a
branch (`_branch_by_hand`), for two things a path can hold and a ref name
cannot. A path can END IN A NEWLINE, which `$(...)` strips, so the format ends
in a `/`: `git -C <dir>/` changes into `<dir>`, and `git submodule update --
<leg>/` updates the gitlink at `<leg>`. A path can START WITH `-`, which the
`printf` of sh, dash and bash reads as an option, so a leading `-` is an
escape too. Each
line stays one line, ASCII, with no variable. A UTF-8 path keeps
`shlex.quote`'s word, byte for byte.

MEASURED, NOT ASSUMED. Each line `_work_tree_by_hand` prints is run as the
person types it in `sh`, `dash`, `bash` and `zsh`, in a real holder whose
member has a leg mounted at such a path and checked out on a branch, after
`git submodule deinit -f` has emptied the member as `remove` does: each exits
0, and the leg is read back as BYTES, checked out at its commit and on its
branch. The rest of `remove`'s by-hand list (the gitlink, `.gitmodules`, the
registration) names the member's path only, so `deinit` alone leaves what
these lines are for.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from pathlib import Path

import pytest

from conftest import (FILE_PROTOCOL, IDENTITY_CONFIG, WINDOWS_SKIP,
                      skip_where_a_name_cannot_be_not_utf_8)
from test_family_head_by_hand_bytes import (ECHO, SHELLS, family_module,
                                            printed, read_as_the_module_does,
                                            run_typed, shell_or_skip)

MEMBER = "members/Thing"

#: `caf` and the Latin-1 byte for `e` with an acute: not UTF-8. The issue's
#: row.
LATIN_1 = b"caf\xe9"

#: Every byte but NUL, which no path holds, ending in the newline `$(...)`
#: strips: what the word has to keep, whatever a leg is called.
EVERY_BYTE = bytes(range(1, 256)) + b"\n"

#: The update line's head, typed in the holder.
UPDATE = (f"git -C {MEMBER} -c protocol.allow=never submodule update --init "
          "--no-fetch -- ")


def git_in(cwd, *args, check: bool = True) -> subprocess.CompletedProcess:
    """`git <args>` in `cwd` (a path as str, `Path` or bytes) under the
    suite's identity, local clones allowed, output as BYTES."""
    return subprocess.run(["git", *IDENTITY_CONFIG, *FILE_PROTOCOL, *args],
                          cwd=cwd, capture_output=True, check=check)


def under(directory: Path, raw: bytes) -> bytes:
    """`directory`/`raw`, as the bytes the file system is given."""
    return os.path.join(os.fsencode(directory), raw)


def repository(path: Path, message: str) -> Path:
    path.mkdir()
    git_in(path, "init", "-q", "-b", "main")
    git_in(path, "commit", "-q", "--allow-empty", "-m", message)
    return path


def holder_with_a_leg_at(tmp_path: Path, leg: bytes, branch: bytes) -> Path:
    """A holder with ONE member at `members/Thing`, on its branch `main`,
    whose legs `spec` and `leg` are both checked out inside the mount, as
    the holder's bootstrap leaves them: `spec` detached at its gitlink, as
    `git submodule update` leaves a leg, and `leg` on a branch `branch` at
    its gitlink, as a person who went on working in it leaves it."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    source = repository(tmp_path / "leg-source", "leg")
    member = repository(tmp_path / "member-source", "member")
    git_in(member, "submodule", "add", "-q", "--name", "spec", str(source),
           "spec")
    git_in(member, "submodule", "add", "-q", "--name", "odd", str(source),
           leg)
    git_in(member, "commit", "-q", "-m", "legs")
    holder = repository(tmp_path / "holder", "holder")
    git_in(holder, "submodule", "add", "-q", str(member), MEMBER)
    git_in(holder, "commit", "-q", "-m", "member")
    git_in(holder / MEMBER, "submodule", "update", "-q", "--init")
    git_in(under(holder / MEMBER, leg), "switch", "-q", "-c", branch)
    return holder


def leg_as_it_stands(holder: Path, leg: bytes) -> tuple[bool, bytes, bytes]:
    """`(a checkout there, its commit, its HEAD's ref)`, as BYTES; the ref
    is empty where HEAD is detached."""
    there = under(holder / MEMBER, leg)
    if not os.path.exists(os.path.join(there, b".git")):
        return False, b"", b""
    return (True, git_in(there, "rev-parse", "HEAD").stdout,
            git_in(there, "symbolic-ref", "-q", "HEAD", check=False).stdout)


def lines_after_the_unmount(holder: Path) -> list[str]:
    """The lines a `remove` whose rollback could not check the member out
    again prints, recorded before the first write as `remove` records them,
    once `git submodule deinit -f` has emptied the member."""
    rollback = family_module().PinRollback(holder, MEMBER, "remove",
                                           (".gitmodules",), unmount=True)
    git_in(holder, "submodule", "deinit", "-q", "-f", "--", MEMBER)
    assert list((holder / MEMBER).iterdir()) == [], "premise: emptied"
    return rollback._work_tree_by_hand()


@WINDOWS_SKIP
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize(("leg", "branch"), [
    pytest.param(LATIN_1, b"side", id="caf-e9"),
    pytest.param(b"caf\xe9\n", b"side", id="a-trailing-newline"),
    pytest.param(b"it's 100%!\\\xe9\n\n", b"side",
                 id="apostrophe-percent-bang-backslash-two-newlines"),
    pytest.param(b"sub/caf\xe9 \x01\x7f\xff", b"caf\xe9",
                 id="nested-space-controls-and-a-branch-not-utf8"),
    pytest.param("caf\u00e9's leg".encode("utf-8"), b"side",
                 id="utf8-keeps-shlex-quote"),
])
def test_each_printed_line_puts_the_leg_back_by_its_bytes(
        tmp_path, shell, leg, branch):
    """THE ISSUE'S ROW, AND THE BYTES ITS FORM HAS TO KEEP. Every line the
    rollback prints, typed as printed in `shell`, exits 0, and the leg is
    checked out again at the gitlink's commit, on its branch, read back as
    the bytes git holds. Each line is one line; a line naming a path that is
    not UTF-8 is ASCII and holds no `\\udcXX`, and a UTF-8 leg's words are
    `shlex.quote`'s."""
    shell = shell_or_skip(shell)
    holder = holder_with_a_leg_at(tmp_path, leg, branch)
    before = leg_as_it_stands(holder, leg)
    assert before == (True, git_in(holder / MEMBER, "rev-parse",
                                   b"HEAD:" + leg).stdout,
                      b"refs/heads/" + branch + b"\n"), "premise"
    path = read_as_the_module_does(leg)
    words = sorted([(b"spec", "spec"), (leg, path)])

    lines = lines_after_the_unmount(holder)

    assert lines[:2] == [
        f"git -c protocol.allow=never submodule update --init --no-fetch -- "
        f"{MEMBER}", f"git -C {MEMBER} checkout -q main --"]
    assert len(lines) == 4, lines
    assert lines[2].startswith(UPDATE)
    assert lines[3].startswith("git -C ")
    assert lines[3].endswith(" --")
    assert not any("\n" in line for line in lines), lines
    if leg.decode("utf-8", "replace").encode("utf-8") == leg:
        assert lines[2] == UPDATE + " ".join(
            shlex.quote(word) for _, word in words)
        assert lines[3] == (f"git -C {shlex.quote(MEMBER + '/' + path)} "
                            f"checkout -q {shlex.quote(branch.decode())} --")
    else:
        assert all(line.isascii() for line in lines), lines
        assert not any("\\udc" in line for line in lines), lines
        assert lines[3].startswith("git -C \"$(printf 'members/Thing/")

    for line in lines:
        done = run_typed(shell, printed(line), holder)
        assert done.returncode == 0, (line, done.stderr)

    assert leg_as_it_stands(holder, leg) == before
    assert leg_as_it_stands(holder, b"spec")[:2] == (
        True, git_in(holder / MEMBER, "rev-parse", "HEAD:spec").stdout)
    assert git_in(holder / MEMBER, "symbolic-ref", "HEAD").stdout == (
        b"refs/heads/main\n")


@WINDOWS_SKIP
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("raw", [
    pytest.param(LATIN_1, id="caf-e9"),
    pytest.param(b"caf\xe9\n", id="a-trailing-newline"),
    pytest.param(b"\n\n\xe9\n\n", id="newlines-at-both-ends"),
    pytest.param(b"-caf\xe9", id="a-leading-dash"),
    pytest.param(b"--\xe9\n", id="two-dashes-and-a-newline"),
    pytest.param(b"a'b\\c%d!e\xe9", id="apostrophe-backslash-percent-bang"),
    pytest.param(b"%s%%\xff%d\n", id="percent-conversions"),
    pytest.param(b"\xc3", id="a-lead-byte-alone"),
    pytest.param(EVERY_BYTE, id="every-byte"),
    pytest.param(b"-" + EVERY_BYTE, id="every-byte-after-a-dash"),
])
def test_the_shell_reads_the_word_as_the_paths_bytes_and_a_slash(
        shell, raw, tmp_path):
    """The word alone, as a shell reads it: what `printf %s <word>` writes is
    the path's bytes and the `/` that keeps a trailing newline, whatever the
    bytes. Git cannot hold some of these paths (a leading `-`), so the word
    is asked for itself."""
    shell = shell_or_skip(shell)
    word = family_module()._path_by_hand(read_as_the_module_does(raw))

    done = run_typed(shell, (ECHO + word).encode("ascii"), tmp_path)

    assert done.returncode == 0, done.stderr
    assert done.stdout == raw + b"/"


def test_the_issues_leg_is_spelled_exactly():
    """The text a person is shown for `caf` and the byte E9, in both lines:
    the byte as an octal escape inside `printf`'s quotes, then the `/`."""
    family = family_module()
    leg = read_as_the_module_does(LATIN_1)

    assert family._path_by_hand(leg) == "\"$(printf 'caf\\351/')\""
    assert family._head_by_hand(f"{MEMBER}/{leg}", "0" * 40, "side") == (
        "git -C \"$(printf 'members/Thing/caf\\351/')\" checkout -q side --")


def test_a_trailing_newline_is_an_escape_before_the_slash():
    """`$(...)` strips the newlines a substitution ENDS with; the `/` after
    the escape is the last byte, so none is stripped."""
    word = family_module()._path_by_hand(
        read_as_the_module_does(b"caf\xe9\n\n"))

    assert word == "\"$(printf 'caf\\351\\012\\012/')\""


def test_a_leading_dash_is_an_escape_so_printf_reads_no_option():
    """`printf -caf...` is an unknown option to the `printf` of sh, dash and
    bash (zsh's prints it); only the FIRST byte is at risk, so a `-` after it
    is itself."""
    word = family_module()._path_by_hand(
        read_as_the_module_does(b"-caf-\xe9"))

    assert word == "\"$(printf '\\055caf-\\351/')\""


def test_the_bang_is_an_octal_escape_as_in_a_branch():
    """The word is double-quoted, where a shell with history on reads a `!`
    as #1079 says for a branch; spelled `\\041`, no line holds one."""
    family = family_module()
    leg = read_as_the_module_does(b"fix!ec!\xe9")

    assert family._path_by_hand(leg) == (
        "\"$(printf 'fix\\041ec\\041\\351/')\"")
    assert "!" not in family._head_by_hand(f"{MEMBER}/{leg}", "0" * 40,
                                           "side")


def test_the_word_is_one_line_of_printable_ascii_whatever_the_bytes():
    """Every control byte, the newline and DEL included, and every byte
    above 0x7E is an escape, so the line is one line a person can paste."""
    word = family_module()._path_by_hand(read_as_the_module_does(EVERY_BYTE))

    assert all(" " <= char <= "~" for char in word)
    assert "\\012/')" in word and "\\177" in word and "\\377" in word


@pytest.mark.parametrize("path", [
    "spec",
    "legs/code",
    "caf\u00e9",
    "\u4e2d\u6587",
    "a b",
    "it's",
    "-leg",
    "100%",
    "a\\b",
    "fix!",
    "$HOME",
    "x\n",
    "\n",
])
def test_a_utf8_path_is_quoted_exactly_as_shlex_quote_has_always_done(path):
    """A leg whose path is UTF-8 text, however odd, prints as it did before:
    `shlex.quote`'s word, and the `git -C` line around it unchanged."""
    family = family_module()

    assert family._path_by_hand(path) == shlex.quote(path)
    assert family._head_by_hand(f"{MEMBER}/{path}", "0" * 40, "main") == (
        f"git -C {shlex.quote(MEMBER + '/' + path)} checkout -q main --")
