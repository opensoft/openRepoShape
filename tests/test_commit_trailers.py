# SPDX-License-Identifier: Apache-2.0
"""The commit trailers both writing tools take, and the lane a printed next
command offers (#111).

`update-shape.py apply --branch` and `scripts/family.py bump` compose their
own commit messages, so a `Lane:` line — which the lane-collision protocol
wants on every artifact a lane produces, the COMMIT included — reaches one
only through `--trailer`. What a trailer IS, whether this host's git takes the
commit option, and which environment variable names the lane are one
implementation in `scripts/shape_materialize.py`, imported by both tools;
those rules are what this file holds. Each tool's own end-to-end run is in
`tests/test_update_shape.py` and `tests/test_family.py`, and the doctor's
printed row is in `tests/test_shape_doctor.py`.

NO NETWORK, like the rest of the suite: the one test that makes real commits
makes them in a repository `git init` creates in a temporary directory.
"""

from __future__ import annotations

import argparse
import os
import shlex
import shutil
import subprocess
import sys

import pytest

from conftest import REPO, git

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import Refusal  # noqa: E402
from shape_materialize import (  # noqa: E402
    LANE_NAME_RE, TRAILER_OPTION_SINCE, commit_trailers,
    git_takes_trailer_option, is_trailer, lane_trailer, lane_trailer_argument,
    one_printable_line, trailer_line,
)

#: Every character that is a LINE BOUNDARY to something without being `\n`.
#: `str.splitlines()` breaks on all of them, so a value carrying one is two
#: lines to anything that reads the commit message back that way — and an
#: ASCII character class in a regex names none of them (Copilot, PR #112).
LINE_BOUNDARIES = ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85",
                   "\u2028", "\u2029"]

#: Invisible WITHOUT being a break: the C1 block above the ASCII controls,
#: and the `Cf` formatting characters. Two trailers differing only by one of
#: these look identical to a reader and are not, which is the confusion a
#: trailer exists to avoid.
INVISIBLES = ["\x80", "\x9f", "\u200b", "\u200d", "\ufeff", "\u00ad"]

#: NOT TEXT AT ALL: a lone surrogate, which is what a byte the locale could
#: not decode becomes in `sys.argv`. `splitlines()` is content with one and
#: every encoder refuses it, so it is `Cs` in `UNPRINTABLE_CATEGORIES` that
#: keeps it out of a commit message.
NOT_TEXT = ["\udcff", "\ud800"]

#: The two lines a lane's run lands, exactly as the protocol spells them.
LANE = "openreposhape-2 (openRepoShape-2)"
TRAILERS = (f"Lane: {LANE}",
            "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>")

#: A trailer a person types who is not writing ASCII (#322): a two-byte, a
#: three-byte and a three-byte-pair character, spelled with escapes so this
#: file means the same thing in any editor. The bytes are what a commit must
#: carry, whatever locale the tool that writes it was started in.
NON_ASCII_TRAILER = ("Co-Authored-By: Jos\u00e9 N\u00fa\u00f1ez "
                     "\u65e5\u672c <jose@example.invalid>")
NON_ASCII_BYTES = NON_ASCII_TRAILER.encode("utf-8")

#: The two interpreters a tool under test can be started as. `LC_ALL=C` with
#: UTF-8 mode off decodes `sys.argv` as ASCII with `surrogateescape`, so the
#: two bytes of `\u00e9` arrive as two lone surrogates; UTF-8 mode reads them
#: as the character. `PYTHONIOENCODING` keeps what the tool prints ASCII in both,
#: so the harness can read it whatever ITS OWN locale is; it changes nothing
#: about how the tool reads its arguments or writes a commit.
C_LOCALE = {"LC_ALL": "C", "PYTHONUTF8": "0",
            "PYTHONIOENCODING": "ascii:backslashreplace"}
UTF8_MODE = {"LC_ALL": "C", "PYTHONUTF8": "1",
             "PYTHONIOENCODING": "ascii:backslashreplace"}

#: One base message shaped like the two the tools compose: a subject, a blank
#: line, two prose paragraphs, and a trailing newline. The last paragraph is
#: PROSE on purpose — that is what makes the trailers a new block rather than
#: additions to one git already recognises.
BASE = ("Re-sync the shape copies to opensoft/openRepoShape @ 32450eb5c5d1\n"
        "\n1 copied file(s) re-copied from the upstream.\n"
        "\nWritten by a tool; the digests are recomputed, not adjusted.\n")


def message_of(root) -> str:
    """The commit message of HEAD, with the newline `git log` adds removed.

    `--format=%B` prints the message, which itself ends in a newline, and
    then git ends the record with one of its own. Dropping exactly that one
    is what lets a test compare the message to the bytes the tool composed —
    the property this whole file is about is a message ENDING in particular
    lines, which a test that strips whitespace cannot see at all.
    """
    out = git("log", "-1", "--format=%B", cwd=root).stdout
    return out[:-1] if out.endswith("\n") else out


def trailers_of(root) -> list[str]:
    """The trailer block AS GIT READS IT, which is the claim that matters: a
    line that merely looks like a trailer in the message text is not one to
    `git interpret-trailers`, and `Co-Authored-By:` is read by forges off
    exactly this.

    The block git prints ends in a newline and git ends the record with one
    of its own, so a bare `splitlines()` reports an empty trailer that is
    really the format's own punctuation — and a commit with NO trailers is
    `[""]` rather than `[]`, which is a list a test would read as one line.
    """
    out = git("log", "-1", "--format=%(trailers:only=true)", cwd=root).stdout
    return out.strip("\n").splitlines() if out.strip() else []


def argv_of(raw: bytes) -> str:
    """The bytes a terminal sent, as the ONE string `subprocess` turns back
    into exactly those bytes: the way to hand a child a command-line argument
    this process's own locale might not be able to spell.

    On POSIX that is `os.fsdecode`, which under a UTF-8 locale is the text and
    under a `C` locale is the same bytes as lone surrogates, and
    `subprocess` runs `os.fsencode` over either. It is what
    `tests/test_git_output_decoding.py` does for a file name. Windows has no
    byte command line (`CreateProcessW` takes UTF-16), and a byte that is not
    UTF-8 has no spelling there at all, which is why those tests skip.
    """
    return os.fsdecode(raw)


def message_bytes_of(root) -> bytes:
    """`message_of`, as the BYTES git stored: a test about what a commit
    carries cannot read it back through a codec, least of all the locale's."""
    out = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=str(root),
                         capture_output=True, check=True).stdout
    return out[:-1] if out.endswith(b"\n") else out


def trailer_bytes_of(root) -> list[bytes]:
    """`trailers_of`, as bytes: the trailer block AS GIT READS IT."""
    out = subprocess.run(
        ["git", "log", "-1", "--format=%(trailers:only=true)"],
        cwd=str(root), capture_output=True, check=True).stdout
    return out.strip(b"\n").splitlines() if out.strip() else []


#: The git every one of these tests can be asked to be: this host's, or one
#: that predates `commit --trailer`.
OLD_GIT_VERSION = "git version 2.31.1"

POSIX_ONLY = pytest.mark.skipif(
    os.name == "nt",
    reason="needs a POSIX shell script on PATH and a byte command line; "
           "Windows has neither (a command line there is UTF-16 text)")

#: A byte the locale could not read is a lone surrogate in `sys.argv` only
#: where argv is bytes: Windows hands over UTF-16, so there is no such value
#: to recover and `escaped` below describes nothing.
ESCAPED_ARGV = pytest.mark.skipif(
    os.name == "nt",
    reason="a command line is UTF-16 text on Windows, so no byte of it is "
           "ever kept as a lone surrogate for `os.fsencode` to give back")


def old_git(tmp_path) -> dict:
    """The environment of a host whose git is 2.31: the PATH that finds this
    stand-in first.

    NOT A MOCK OF THE CODE UNDER TEST: a real git behind a shell script that
    does what 2.31 did. `git --version` says 2.31.1, which is all
    `git_takes_trailer_option` reads, and `--trailer` is an unknown option
    (exit 129, the usage git prints), so a tool that passed the option to a
    git that does not take it would FAIL here, where a probe that only
    printed a number would let it through. Everything else goes to the real
    git untouched. Emulated, not run: the real one is whatever this machine
    has, and CI's is newer than 2.32 on all three systems.
    """
    shim = tmp_path / "old-git-bin"
    shim.mkdir()
    real = shutil.which("git")
    assert real, "no git on PATH"
    script = shim / "git"
    script.write_text(
        "#!/bin/sh\n"
        f'if [ "$1" = "--version" ]; then echo "{OLD_GIT_VERSION}"; '
        "exit 0; fi\n"
        'for arg in "$@"; do\n'
        '    if [ "$arg" = "--trailer" ]; then\n'
        "        echo \"error: unknown option \\`trailer'\" >&2\n"
        "        exit 129\n"
        "    fi\n"
        "done\n"
        f'exec {shlex.quote(real)} "$@"\n', encoding="utf-8")
    script.chmod(0o755)
    return {"PATH": str(shim) + os.pathsep + os.environ["PATH"]}


#: Every way a tool is run that decides what a non-ASCII trailer becomes: the
#: interpreter's locale (what `sys.argv` and the commit helpers' stdin see)
#: crossed with the git (which takes the trailer as an argument, or has it
#: appended to the message text). The `C` locale with the old git is the case
#: #322 is about; the other three are the ones that already worked and must
#: go on working.
ENVIRONMENTS = pytest.mark.parametrize("git_kind, locale", [
    pytest.param("old", "c", id="old-git-c-locale"),
    pytest.param("old", "utf8", id="old-git-utf8-mode"),
    pytest.param("host", "c", id="host-git-c-locale"),
    pytest.param("host", "utf8", id="host-git-utf8-mode"),
])


def environment(tmp_path, git_kind: str, locale: str) -> dict:
    """The `env=` for `run_script` of one `ENVIRONMENTS` row."""
    if locale == "c" and os.name == "nt":
        pytest.skip("a C locale is a POSIX idea: Windows decodes with the "
                    "ANSI code page, and its job sets PYTHONUTF8=1 "
                    "(.github/workflows/tests.yml)")
    env = dict(C_LOCALE if locale == "c" else UTF8_MODE)
    if git_kind == "old":
        if os.name == "nt":
            pytest.skip("the stand-in for a git without `--trailer` is a "
                        "POSIX shell script")
        env.update(old_git(tmp_path))
    return env


# --- the grammar ------------------------------------------------------------

@pytest.mark.parametrize("value", [
    "Lane: xfactory-1",
    f"Lane: {LANE}",
    "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>",
    "Signed-off-by: A Human <human@example.invalid>",
    "X: y",
    "Reviewed-By: someone, and someone else",
])
def test_the_grammar_accepts_a_trailer_somebody_would_actually_write(value):
    """Git's own trailer shape: a token, a colon, one space, a value."""
    assert trailer_line(value) == value


@pytest.mark.parametrize("value", [
    "Lane xfactory-1",          # no colon at all
    "Lane:xfactory-1",          # no space after the colon
    "Lane : xfactory-1",        # a space BEFORE the colon
    "Lane: ",                   # no value
    "Lane:",
    "",
    ": xfactory-1",             # no token
    "-Lane: xfactory-1",        # a token that does not start with a letter
    "Lane: trailing ",          # trailing whitespace in the value
    "Lane: two\nlines",         # a second line, which would forge a trailer
    # THE `.match` + `$` HOLE (Copilot, PR #112). A pattern ending in `$`
    # stops just before a FINAL newline, so this was accepted whole and the
    # newline went into the commit message and into argv.
    "Lane: x\n",
    "Lane: x\r\n",
    # AND "one line" IS NOT "no `\n`". Each of these is a line break to some
    # reader, and `[^\n]` in the middle of the pattern admitted all of them.
    "Lane: a\rb",
    "Lane: a\x0bb",
    "Lane: a\x0cb",
    "Lane: a\tb",
    "Lane: x\x7f",
    "Lane: a\x00b",
    # Every line boundary, every invisible and every lone surrogate, in the
    # middle of a value and at the end of one — the two places a regex was
    # asked to notice them and could not (Copilot, PR #112).
    *[f"Lane: a{char}b" for char in LINE_BOUNDARIES + INVISIBLES + NOT_TEXT],
    *[f"Lane: x{char}" for char in LINE_BOUNDARIES + INVISIBLES + NOT_TEXT],
])
def test_the_grammar_refuses_a_line_that_is_not_a_trailer(value):
    """Refused where argparse can say so, with the usage line beside it.

    THE NEWLINE CASES ARE THE ONES WITH TEETH: a value carrying one puts a
    line of its own into somebody else's commit message, which is a trailer
    nobody passed — and the trailing one got through `re.match` entirely,
    because `$` matches just before a final newline (Copilot, PR #112; the
    same lesson `shape-doctor.py`'s `quote_arg` took on PR #102 against
    `"Atlas\\n"`). Both halves of the fix are asserted here: `.fullmatch`,
    and classes that admit no control character.
    """
    with pytest.raises(argparse.ArgumentTypeError):
        trailer_line(value)


# --- which git this is ------------------------------------------------------

@pytest.mark.parametrize("line,takes", [
    ("git version 2.43.0", True),
    ("git version 2.32.0", True),               # the release that gained it
    ("git version 2.31.1", False),              # the one before
    ("git version 2.45.1.windows.1", True),
    ("git version 2.39.3 (Apple Git-146)", True),
    ("git version 3.0.0", True),
    ("git version 1.9.5", False),
    ("git version", False),                     # nothing to read
    ("", False),
    ("not a git at all", False),
    ("2.43.0", False),                          # unanchored would match this
])
def test_the_version_probe_reads_the_commit_option_off_the_version_line(
        line, takes):
    """Conservative both ways: anything unparseable reads as "no", and "no"
    is the path that works on every git there is."""
    assert git_takes_trailer_option(line) is takes


def test_the_probe_asked_for_a_version_touches_no_cache():
    """`version=` is the parse, exposed — the same thing
    `shape-doctor.py`'s `platform=` does for its quoter, and for the same
    reason: a branch that can only run on one machine is a branch nothing
    checks. Asking for one must not decide the answer for this process."""
    before = git_takes_trailer_option()
    assert git_takes_trailer_option("git version 1.0.0") is False
    assert git_takes_trailer_option("git version 9.9.9") is True
    assert git_takes_trailer_option() is before


def test_the_option_arrived_in_2_32():
    """Spelled here rather than imported into the assertion: 2.32 is a fact
    about git (2021-06-06), and a test that read the constant would agree
    with a typo in it."""
    assert TRAILER_OPTION_SINCE == (2, 32)


# --- what the tools are handed ---------------------------------------------

def test_no_trailers_is_the_message_unchanged_and_no_arguments():
    """The byte-identity that keeps every commit these tools have already
    written exactly as it was: passed nothing, this returns the message it
    was given and an empty argument list, so the `git commit` argv is the
    one the tool always built."""
    assert commit_trailers(BASE) == (BASE, [])
    assert commit_trailers(BASE, []) == (BASE, [])
    assert commit_trailers(BASE, ()) == (BASE, [])


def test_the_commit_option_is_used_where_git_has_it(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    message, args = commit_trailers(BASE, list(TRAILERS))
    assert message == BASE, "git appends them; the message is untouched"
    assert args == ["--trailer", TRAILERS[0], "--trailer", TRAILERS[1]]


def test_the_text_fallback_appends_the_lines_after_one_blank_line(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    message, args = commit_trailers(BASE, list(TRAILERS))
    assert args == [], "a git without the option is asked for nothing"
    assert message == BASE + "\n" + "\n".join(TRAILERS) + "\n"
    assert message.endswith(f"\n{TRAILERS[0]}\n{TRAILERS[1]}\n")


def test_the_fallback_supplies_the_newline_a_message_is_missing(monkeypatch):
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    message, _args = commit_trailers("No trailing newline", ["Lane: x"])
    assert message == "No trailing newline\n\nLane: x\n"


@pytest.mark.skipif(not git_takes_trailer_option(),
                    reason="this host's git predates `commit --trailer` "
                           "(2.32), so only the fallback path can run here")
def test_both_paths_write_the_same_commit_message(tmp_path, monkeypatch):
    """THE CLAIM THE FALLBACK RESTS ON, asserted rather than believed.

    `commit --trailer` runs the message through `interpret-trailers`, which
    knows where a trailer block goes; appending the lines to the text is this
    module doing that job for a git that cannot. The two are only
    interchangeable if the commit that comes out is the same one — so both
    are written here, into one real repository, and compared.
    """
    root = tmp_path / "either-way"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    identity = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]

    def commit(name: str, message: str, extra: list[str]) -> str:
        (root / name).write_text("x\n", encoding="utf-8")
        git("add", "--", name, cwd=root)
        proc = subprocess.run(
            ["git", *identity, "commit", "-q", "-F", "-", *extra, "--", name],
            cwd=str(root), input=message, capture_output=True, text=True,
            check=False)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        return message_of(root)

    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    option_message, option_args = commit_trailers(BASE, list(TRAILERS))
    through_git = commit("a", option_message, option_args)

    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    text_message, text_args = commit_trailers(BASE, list(TRAILERS))
    by_hand = commit("b", text_message, text_args)

    assert through_git == by_hand
    assert by_hand.endswith(f"\n{TRAILERS[0]}\n{TRAILERS[1]}\n")
    assert trailers_of(root) == list(TRAILERS), (
        "and git reads them back as the trailer block, in order")


# --- a trailer that is not ASCII (#322) --------------------------------------
#
# `Co-Authored-By: José` typed where `sys.argv` is decoded as ASCII (a POSIX
# `C` locale with UTF-8 mode off) is `Jos\udcc3\udca9` to Python: the two
# bytes, kept as lone surrogates so `os.fsencode` can give them back. The
# commit helpers write the message on stdin as UTF-8 with `errors="replace"`
# (#230), which writes a lone surrogate as `?`; on a git without `commit
# --trailer` the trailer travels in that message, so the commit said
# `Jos??`. The rules below are the ones that make it the bytes typed or a
# refusal that names the trailer, for every caller at once.

def escaped(text: str) -> str:
    """`text` as a `C` locale's `sys.argv` holds it: each byte of its UTF-8 a
    lone surrogate for every byte ASCII cannot read."""
    return text.encode("utf-8").decode("ascii", "surrogateescape")


#: Characters of one, two, three and four UTF-8 bytes, so a recovery that read
#: only the two-byte case would not pass.
TEXTS = ["Jos\u00e9", "\u65e5\u672c", "na\u00efve \u2603", "\U0001f642"]


@ESCAPED_ARGV
@pytest.mark.parametrize("text", TEXTS)
def test_bytes_the_locale_could_not_read_are_the_text_they_were_typed_as(text):
    """`os.fsencode` gives the bytes back and they are UTF-8, so the value is
    the SAME STRING a UTF-8 locale would have handed over: one trailer,
    whatever the locale, rather than one for each codec."""
    line = f"Co-Authored-By: {text} <a@example.invalid>"
    assert escaped(line) != line, ("the fixture is only interesting while "
                                   "the locale's reading is not the text")
    assert trailer_line(escaped(line)) == line, (
        "a trailer the grammar refused as `Cs` is the one typed now")
    assert trailer_line(line) == line, "text the locale read is left alone"
    assert trailer_line("Lane: x") == "Lane: x"


@ESCAPED_ARGV
@pytest.mark.parametrize("raw", [
    b"Co-Authored-By: Jos\xe9",          # Latin-1 and cp1252's é
    b"Co-Authored-By: Jos\xc3",          # a UTF-8 lead byte, cut short
    b"Co-Authored-By: a\xffb",           # a byte UTF-8 never uses
    b"Co-Authored-By: \xe6\x97 x",       # a three-byte character, cut short
])
def test_a_byte_that_is_not_utf8_stays_a_refusal_and_names_the_trailer(raw):
    """NOT RECOVERED AND NOT GUESSED: which code page wrote the byte is a fact
    about somebody's terminal, and `?` is what the commit helpers would have
    made of it. The refusal says which bytes, in a spelling every stdout can
    print."""
    value = raw.decode("ascii", "surrogateescape")
    with pytest.raises(argparse.ArgumentTypeError) as caught:
        trailer_line(value)
    said = str(caught.value)
    assert "not UTF-8 text" in said
    assert repr(raw) in said, "the trailer is named by the bytes typed"
    assert said.isascii()


@ESCAPED_ARGV
@pytest.mark.parametrize("char", LINE_BOUNDARIES + INVISIBLES)
def test_bytes_that_spell_a_forbidden_character_are_judged_as_that_character(
        char):
    """Recovered BEFORE the grammar is asked, so the `Cs` check that used to
    stand in front of them cannot be the only thing between a line separator
    typed in UTF-8 and a commit message."""
    value = f"Lane: a{char}b"
    with pytest.raises(argparse.ArgumentTypeError):
        trailer_line(escaped(value))


@pytest.mark.parametrize("spelling", [
    pytest.param("as-a-c-locale-holds-it", marks=ESCAPED_ARGV),
    "as-text"])
def test_the_text_fallback_carries_a_non_ascii_trailer_exactly(
        monkeypatch, spelling):
    """THE MEASURED CASE: a git without `--trailer`, the trailer's bytes as a
    `C` locale holds them, and `?` where each of them was."""
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    typed = (escaped(NON_ASCII_TRAILER) if spelling == "as-a-c-locale-holds-it"
             else NON_ASCII_TRAILER)
    message, args = commit_trailers(BASE, [typed])
    assert args == []
    assert message == BASE + "\n" + NON_ASCII_TRAILER + "\n"
    assert message.encode("utf-8").endswith(b"\n\n" + NON_ASCII_BYTES + b"\n")
    assert "?" not in message and "\ufffd" not in message


@POSIX_ONLY
@pytest.mark.parametrize("spelling", ["as-a-c-locale-holds-it", "as-text"])
def test_the_commit_option_is_given_the_bytes_typed_under_any_codec(
        monkeypatch, spelling):
    """The other path, where the value is an ARGUMENT: what git is handed is
    what `subprocess` encodes, and under a `C` locale the text of an accented
    letter has no ASCII spelling, so it is the surrogate form that turns back
    into the UTF-8 bytes. Asserted as the BYTES the child gets, which is the
    claim, in whichever codec this process runs."""
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    typed = (escaped(NON_ASCII_TRAILER) if spelling == "as-a-c-locale-holds-it"
             else NON_ASCII_TRAILER)
    message, args = commit_trailers(BASE, [typed, TRAILERS[0]])
    assert message == BASE, "git appends them; the message is untouched"
    assert args[0] == "--trailer" and args[2] == "--trailer"
    assert os.fsencode(args[1]) == NON_ASCII_BYTES
    assert args[3] == TRAILERS[0], "ASCII is spelled as it always was"


@ESCAPED_ARGV
@pytest.mark.parametrize("available", [True, False])
@pytest.mark.parametrize("raw", [b"Co-Authored-By: Jos\xe9", b"Lane: a\xffb"])
def test_a_trailer_that_is_no_text_is_refused_before_a_commit_is_made(
        monkeypatch, available, raw):
    """BOTH PATHS, because the option path would have handed git the stray
    byte and written a commit message that is not UTF-8, and the text path
    would have written `?`. Either is the trailer altered without a word, so
    a caller that reaches here without the command line's own check (a
    direct call) gets a `Refusal` naming it instead."""
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: available)
    value = raw.decode("ascii", "surrogateescape")
    with pytest.raises(Refusal) as caught:
        commit_trailers(BASE, [TRAILERS[0], value])
    assert caught.value.code == "trailer-not-utf8"
    assert repr(raw) in str(caught.value)
    assert "nothing was committed" in str(caught.value)


@POSIX_ONLY
def test_the_old_git_stand_in_refuses_the_option_and_reads_as_2_31(tmp_path):
    """The stand-in the tool-level tests rely on is what it says it is: if it
    let `--trailer` through, every one of them would be passing on a git that
    takes the option."""
    env = {**os.environ, **old_git(tmp_path)}
    version = subprocess.run(["git", "--version"], env=env,
                             capture_output=True, text=True, check=False)
    assert version.stdout.strip() == OLD_GIT_VERSION
    assert git_takes_trailer_option(version.stdout) is False
    refused = subprocess.run(["git", "commit", "--trailer", "Lane: x"],
                             env=env, cwd=str(tmp_path), capture_output=True,
                             text=True, check=False)
    assert refused.returncode == 129 and "unknown option" in refused.stderr
    assert subprocess.run(["git", "init", "-q", str(tmp_path / "r")], env=env,
                          capture_output=True, check=False).returncode == 0, (
        "and everything else is the real git")


@pytest.mark.skipif(not git_takes_trailer_option(),
                    reason="this host's git predates `commit --trailer` "
                           "(2.32), so only the fallback path can run here")
@pytest.mark.parametrize("spelling", [
    pytest.param("as-a-c-locale-holds-it", marks=ESCAPED_ARGV),
    "as-text"])
def test_both_paths_write_the_same_commit_for_a_non_ascii_trailer(
        tmp_path, monkeypatch, spelling):
    """`test_both_paths_write_the_same_commit_message`, for the bytes this one
    is about: the fallback is only a stand-in for `--trailer` if the commit
    that comes out is the same, and the same is the UTF-8 the person typed.

    The message is written the way the commit helpers write it: text mode,
    UTF-8, `errors="replace"`, so a character that did not survive would show
    as a `?` and fail here."""
    root = tmp_path / "either-way"
    root.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=root)
    identity = ["-c", "user.name=t", "-c", "user.email=t@t.invalid"]

    def commit(name: str, message: str, extra: list[str]) -> bytes:
        (root / name).write_text("x\n", encoding="utf-8")
        git("add", "--", name, cwd=root)
        proc = subprocess.run(
            ["git", *identity, "commit", "-q", "-F", "-", *extra, "--", name],
            cwd=str(root), input=message, capture_output=True, text=True,
            encoding="utf-8", errors="replace", check=False)
        assert proc.returncode == 0, proc.stderr + proc.stdout
        return message_bytes_of(root)

    typed = (escaped(NON_ASCII_TRAILER) if spelling == "as-a-c-locale-holds-it"
             else NON_ASCII_TRAILER)
    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: True)
    option_message, option_args = commit_trailers(BASE, [typed, TRAILERS[0]])
    through_git = commit("a", option_message, option_args)
    assert trailer_bytes_of(root) == [NON_ASCII_BYTES, TRAILERS[0].encode()]

    monkeypatch.setattr("shape_materialize.git_takes_trailer_option",
                        lambda: False)
    text_message, text_args = commit_trailers(BASE, [typed, TRAILERS[0]])
    by_hand = commit("b", text_message, text_args)

    assert through_git == by_hand
    assert by_hand.endswith(b"\n\n" + NON_ASCII_BYTES + b"\n"
                            + TRAILERS[0].encode() + b"\n")
    assert trailer_bytes_of(root) == [NON_ASCII_BYTES, TRAILERS[0].encode()]


# --- the lane a printed next command offers --------------------------------

def test_the_lane_comes_from_the_environment_and_is_a_trailer():
    assert lane_trailer({"LANES_LANE": LANE}) == f"Lane: {LANE}"
    assert trailer_line(lane_trailer({"LANES_LANE": LANE}))


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_an_unset_or_blank_lane_is_no_lane(value):
    """And the caller then prints nothing, which is what keeps every line
    this standard printed yesterday byte-identical for everybody who is not
    in a lane."""
    assert lane_trailer({"LANES_LANE": value}) is None
    assert lane_trailer({}) is None
    assert lane_trailer_argument(env={"LANES_LANE": value}) == ""
    assert lane_trailer_argument(env={}) == ""


@pytest.mark.parametrize("value", [
    'say "hello"',          # the quote the default spelling uses
    "O'Brien",              # the quote both of the doctor's spellings use
    "back`tick",
    "dollar$sign",
    "back\\slash",
    "two\nlines",
])
def test_a_lane_name_that_could_not_be_pasted_is_not_offered(value):
    """A next command is a line somebody copies into a shell, and the
    trailer inside it is quoted by whoever prints it — so a name carrying
    that quote character would break the very quoting it sits inside, in
    front of whoever pasted it. Offering nothing is the honest answer;
    `--trailer` typed by hand still takes anything the grammar accepts."""
    assert lane_trailer({"LANES_LANE": value}) is None
    assert lane_trailer_argument(env={"LANES_LANE": value}) == ""


@pytest.mark.parametrize("char", LINE_BOUNDARIES)
def test_one_printable_line_asks_python_what_a_line_boundary_is(char):
    """The half no character class should be asked to enumerate.

    `[^\\x00-\\x1f\\x7f]` reads as "no control character" and is not one:
    U+0085, U+2028 and U+2029 sit above it, and `str.splitlines()` — which
    IS this interpreter's definition of a line boundary — breaks on every
    one of them. So the guard asks it directly instead of approximating it.
    """
    assert f"a{char}b".splitlines() != [f"a{char}b"], (
        "the fixture is only interesting while Python calls this a break")
    assert one_printable_line(f"a{char}b") is False
    assert one_printable_line("a b") is True


@pytest.mark.parametrize("char", INVISIBLES)
def test_one_printable_line_refuses_what_is_invisible_without_breaking(char):
    """A zero-width joiner between two words makes two trailers that look
    identical to a reader and are not. `unicodedata.category` catches those;
    `splitlines()` never would."""
    assert f"a{char}b".splitlines() == [f"a{char}b"], (
        "these are NOT line boundaries, which is why they need the second "
        "check")
    assert one_printable_line(f"a{char}b") is False


@pytest.mark.parametrize("char", NOT_TEXT)
def test_one_printable_line_refuses_what_is_not_text_at_all(char):
    """A byte the locale could not decode arrives in `sys.argv` as a lone
    surrogate, and a commit message cannot carry one: git is handed the
    undecodable byte straight back, or — on the pre-2.32 path that appends
    trailers to the MESSAGE text — `subprocess` raises encoding a value
    `--trailer` had already accepted. Neither check would catch it alone:
    `splitlines()` sees one line, and it took `Cs` in the category list."""
    assert f"a{char}b".splitlines() == [f"a{char}b"], (
        "a surrogate is no line boundary; the second check is what refuses "
        "it")
    with pytest.raises(UnicodeEncodeError):
        f"a{char}b".encode("utf-8")
    assert one_printable_line(f"a{char}b") is False


@pytest.mark.parametrize("char", LINE_BOUNDARIES + INVISIBLES + NOT_TEXT)
def test_the_lane_alphabet_already_excludes_every_one_of_them(char):
    """`LANE_NAME_RE` is a POSITIVE alphabet of printable ASCII, so it needs
    no guard bolted on: nothing in either list can be in it. Asserted rather
    than reasoned about, because the day somebody widens that alphabet is
    the day this needs to be said out loud."""
    assert not LANE_NAME_RE.fullmatch(f"x{char}y")
    assert lane_trailer({"LANES_LANE": f"x{char}y"}) is None
    assert lane_trailer_argument(env={"LANES_LANE": f"x{char}y"}) == ""


def test_the_two_checks_are_one_predicate_both_callers_use():
    """`is_trailer` is the whole rule, so the invariant holds by
    construction rather than by two checks that agree today: what
    `--trailer` refuses, no printed next command offers."""
    assert is_trailer("Lane: x") is True
    assert is_trailer("Lane: a\u2028b") is False
    assert is_trailer("Lane: a\udcffb") is False
    assert is_trailer("Lane:x") is False
    for raw in ["xfactory-1", LANE]:
        assert is_trailer(lane_trailer({"LANES_LANE": raw}))


@pytest.mark.parametrize("raw", [
    "xfactory-1\n",            # the shape `LANES_LANE=$(cat …)` produces
    "xfactory-1\r\n",
    "xfactory-1 ",
    " xfactory-1",
    "xfactory-1\t",
])
def test_a_lane_name_with_whitespace_around_it_is_not_a_lane_name(raw):
    """CHECKED RAW, NOT STRIPPED (Copilot, PR #112).

    Asking the alphabet about a `.strip()`ed name meant
    `LANES_LANE="xfactory-1\\n"` was offered as `Lane: xfactory-1`: a name
    the contract says is not offered, trimmed into one that is, with nothing
    said. It is decided the other way on purpose — a value with whitespace
    around it is not a lane name — because `TRAILER_RE` refuses a value that
    starts or ends in whitespace, and a printed line offering a trailer this
    tool's own `--trailer` would then refuse is worse than one offering none.
    """
    assert lane_trailer({"LANES_LANE": raw}) is None
    assert lane_trailer_argument(env={"LANES_LANE": raw}) == ""


def test_a_lane_that_is_offered_is_a_trailer_the_tool_would_accept():
    """THE INVARIANT THE TWO RULES EXIST TO KEEP, asserted directly: every
    lane line a printed next command offers must be one `--trailer` would
    take, or the line hands somebody a command that refuses itself."""
    for raw in ["xfactory-1", LANE, "openreposhape-2", "a/b (c) @ d",
                "x" * 200]:
        offered = lane_trailer({"LANES_LANE": raw})
        assert offered is not None, raw
        assert trailer_line(offered) == offered


def test_the_printed_argument_is_spelled_by_the_callers_own_quoter():
    """`quote` is passed in rather than chosen here: `shape-doctor.py` hands
    over its platform-aware `quote_arg`, because every other value on those
    rows is spelled by that one function and a line half-quoted by two rules
    is a line no shell reads the way its writer meant."""
    env = {"LANES_LANE": LANE}
    assert lane_trailer_argument(env=env) == \
        f' --trailer "Lane: {LANE}"'
    assert lane_trailer_argument(lambda value: "<" + value + ">", env) == \
        f" --trailer <Lane: {LANE}>"


def test_the_lane_line_is_the_only_thing_derived_from_the_environment():
    """`Co-Authored-By:` names a person or a model, which no environment
    variable knows — so a tool that added one would be putting a name nobody
    chose on somebody else's commit. It is the caller's to pass."""
    offered = lane_trailer_argument(env={"LANES_LANE": LANE})
    assert offered.count("--trailer") == 1
    assert "Co-Authored-By" not in offered
