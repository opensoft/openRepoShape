# SPDX-License-Identifier: Apache-2.0
"""The two helpers a test asks whether a name that is not UTF-8 can be
carried here (#663, #461's L2-52).

`skip_where_a_name_cannot_be_not_utf_8` was two helpers with one body
(`tests/test_adopt_pins.py` and `tests/test_pin_source_unreadable.py`), and
`make_file` and the `--branch a\\udcffb` test each asked a smaller question of
their own, or none: on Windows the disk takes the name, so no probe of the
disk skips there. Now `tests/conftest.py` holds both questions once, the
system's first (`os.fsencode`) and the disk's second (EILSEQ), and this file
holds them to it.

CI runs the suite on Linux only (#597), so what Windows answers is EMULATED:
`os.fsencode` is replaced for one test by `windows_fsencode`, which gives a
surrogate three bytes, as Windows' does. No Windows run was made. macOS's
EILSEQ is emulated the same way, by a `mkdir` that answers it.

The two tools the tests below are written with are held here too:
`skip_message`, which every one of them reads a skip with, and
`windows_fsencode`, the emulation itself.

A third helper, `skip_where_the_locale_does_not_spell_it_as_utf_8` (#1214),
asks three questions of a locale through `os`, and the tests at the end hold
its answers for UTF-8, Latin-1 and ASCII, each EMULATED the same way: CI runs
UTF-8, and a helper that skipped where it should not would turn every row
that asks it into a silent skip, which no run fails on.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

from conftest import (NOT_UTF_8_PROBE, skip_message,
                      skip_where_a_name_cannot_be_not_utf_8,
                      skip_where_fsencode_gives_a_surrogate_no_byte,
                      skip_where_the_locale_does_not_spell_it_as_utf_8,
                      windows_fsencode)

LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux stores any byte in a file name; the other systems are "
           "asked by the tests below that emulate them")


def mkdir_answers(code: int, said: str):
    """A `Path.mkdir` that fails as the disk would with `code`."""
    def refuse(self, *args, **kwargs):
        raise OSError(code, said, str(self))
    return refuse


# --- `skip_message`: how every test below reads a skip -----------------------
#
# A skip that ESCAPES a helper ends its test SKIPPED, and no run fails on a
# skip: a `skip_message` that let one out would turn every assertion below
# that expects a skip, or expects none, into a silent skip. So the first test
# catches the escape and fails it.

def test_skip_message_returns_the_reason_a_call_skips_with():
    try:
        reason = skip_message(lambda: pytest.skip("x"))
    except pytest.skip.Exception:
        pytest.fail("the skip escaped skip_message, which would end the test "
                    "SKIPPED, and no run fails on that")
    assert reason == "x"


def test_skip_message_returns_none_where_the_call_does_not_skip():
    assert skip_message(lambda: None) is None


def test_skip_message_lets_any_other_exception_go_on():
    def not_a_skip():
        raise ZeroDivisionError("not a skip")

    with pytest.raises(ZeroDivisionError):
        skip_message(not_a_skip)


# --- `windows_fsencode`: the emulation is Windows' `os.fsencode` --------------

def test_windows_fsencode_makes_three_bytes_of_a_surrogate_and_utf_8_of_text():
    assert windows_fsencode("\udcff") == b"\xed\xb3\xbf"
    assert windows_fsencode("caf\u00e9.yml") == "caf\u00e9.yml".encode("utf-8")


def test_windows_fsencode_passes_bytes_through_as_os_fsencode_does():
    """`os.fsencode` takes bytes on every system and gives them back; the
    emulation that stands in for it must not fail on them."""
    data = b"caf\xe9.yml"
    assert os.fsencode(data) == data
    assert windows_fsencode(data) == data


def test_windows_fsencode_takes_a_path_as_os_fsencode_does():
    """`os.fsencode` takes a path-like object (`os.fspath` first), and a test
    asks it for one (`os.fsencode(tmp_path)`), so the emulation must not fail
    on a `Path` with an `AttributeError`, which would end such a test before
    the question it is written to hold. A surrogate in a path is the three
    bytes of one in text."""
    assert windows_fsencode(Path("caf\udcff")) == b"caf\xed\xb3\xbf"


# --- the system's question: what `os.fsencode` makes of the surrogate --------

@LINUX_ONLY
def test_a_system_that_carries_the_byte_is_not_skipped():
    """The control: Linux's `os.fsencode` gives U+DCFF back as the one byte
    0xFF, so no text is skipped."""
    assert os.fsencode(NOT_UTF_8_PROBE) == b"\xff"
    assert skip_message(skip_where_fsencode_gives_a_surrogate_no_byte,
                        f"caf{NOT_UTF_8_PROBE}.yml") is None


def test_where_fsencode_makes_three_bytes_of_the_surrogate_the_name_is_skipped(
        monkeypatch):
    """Windows' `os.fsencode` (emulated): U+DCFF is the three bytes of a
    sequence that is not UTF-8, none of them 0xFF, so a name that holds a
    byte-carrying surrogate is skipped, and each one from U+DC80 to U+DCFF."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    assert len(os.fsencode(NOT_UTF_8_PROBE)) == 3
    for surrogate in ("\udc80", "\udce9", "\udcff"):
        reason = skip_message(skip_where_fsencode_gives_a_surrogate_no_byte,
                              f"a{surrogate}b")
        assert reason is not None, f"U+{ord(surrogate):04X} was not skipped"
        assert "os.fsencode" in reason, reason


@pytest.mark.parametrize("text", [
    "plain", "café.yml", "feature/日本", "", "a\ud83db"],
    ids=["ascii", "text", "cjk", "empty", "surrogate-without-a-byte"])
def test_where_fsencode_makes_three_bytes_a_name_that_is_text_is_not_skipped(
        monkeypatch, text):
    """The guard is for the surrogates that stand for a byte (U+DC80 to
    U+DCFF) and no wider: text is the same on every system, and a surrogate
    that stands for no byte is not this helper's to judge (`_argument_fault`
    refuses it, as `bootstrap.py`'s tests hold)."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    assert skip_message(skip_where_fsencode_gives_a_surrogate_no_byte,
                        text) is None


# --- the shared helper: the system, then the disk ----------------------------

@LINUX_ONLY
def test_a_disk_that_takes_the_name_is_not_skipped_and_the_probe_is_removed(
        tmp_path):
    """The control: no skip, and nothing is left in the directory."""
    assert skip_message(skip_where_a_name_cannot_be_not_utf_8,
                        tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_where_fsencode_makes_three_bytes_the_disk_is_not_asked(
        tmp_path, monkeypatch):
    """THE SYSTEM IS ASKED FIRST (#663): on Windows the disk would take the
    name, so a skip that waited for the disk would never come. The directory
    does not exist, so an `mkdir` under it would be FileNotFoundError and not
    a skip: the skip is the answer, and the disk was not touched."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(skip_where_a_name_cannot_be_not_utf_8,
                          tmp_path / "absent")
    assert reason is not None, "the helper went on to ask the disk"
    assert "os.fsencode" in reason, reason


def test_a_disk_that_answers_eilseq_is_skipped(tmp_path, monkeypatch):
    """macOS (emulated): APFS answers EILSEQ, `Illegal byte sequence`, to a
    file name that is not UTF-8, and no clone can sit at such a path."""
    if len(os.fsencode(NOT_UTF_8_PROBE)) != 1:
        pytest.skip("on this system the first question is the one that skips")
    monkeypatch.setattr(Path, "mkdir",
                        mkdir_answers(errno.EILSEQ, "Illegal byte sequence"))
    reason = skip_message(skip_where_a_name_cannot_be_not_utf_8, tmp_path)
    assert reason is not None, "EILSEQ was not a skip"
    assert "EILSEQ" in reason, reason


@pytest.mark.parametrize("code", [errno.EACCES, errno.ENOSPC, errno.EEXIST],
                         ids=["EACCES", "ENOSPC", "EEXIST"])
def test_any_other_error_from_the_disk_is_the_tests_own(
        tmp_path, monkeypatch, code):
    """Only EILSEQ is the filesystem's refusal of the name: a full disk, a
    folder nobody can write in or a probe left by an earlier run is a
    failure of the test, raised as it was, and never a skip that hides it."""
    if len(os.fsencode(NOT_UTF_8_PROBE)) != 1:
        pytest.skip("on this system the first question is the one that skips")
    monkeypatch.setattr(Path, "mkdir", mkdir_answers(code, os.strerror(code)))
    with pytest.raises(OSError) as raised:
        skip_message(skip_where_a_name_cannot_be_not_utf_8, tmp_path)
    assert raised.value.errno == code


# --- the locale's question: does it spell the text as UTF-8 does (#1214) ------
#
# `skip_where_the_locale_does_not_spell_it_as_utf_8(text, premise)` asks three
# questions, in this order, each through the `os` module at call time: can
# `os.fsencode` spell `text`; does it give UTF-8's bytes; does `os.fsdecode`
# read those bytes back as `text`. The reason it skips with names the question
# that said no, so a helper that dropped, reordered or inverted one is told
# from one that did not: a text that fails two questions is skipped by the
# first of them.
#
# The three encodings are the ones `sys.getfilesystemencoding()` names, each
# with `surrogateescape` as POSIX has it, EMULATED for one test by replacing
# `os.fsencode`, `os.fsdecode` and `sys.getfilesystemencoding`. No Latin-1 or
# ASCII run is needed to hold them; the last test holds the emulation to the
# real locale of the run.

UTF_8, LATIN_1, ASCII = "utf-8", "iso8859-1", "ascii"

#: The questions, by the words the reason says them in.
CANNOT_SPELL, WRITES_OTHER_BYTES, READS_OTHER_TEXT = (
    "cannot spell", "writes", "reads")

#: The premise a row names to the helper: the reason ends with it, whole.
PREMISE = "the row needs this text spelled as UTF-8 spells it"

#: Texts, built from code points: `caf` and the byte E9 that is not UTF-8,
#: read in as a surrogate; `caf` and U+00E9, which Latin-1 writes as the byte
#: E9 and ASCII cannot spell; U+202E and U+2026, which neither spells; and
#: plain ASCII.
TEXTS = {
    "plain": "plain",
    "byte-e9": "caf" + chr(0xDCE9),
    "e-acute": "caf" + chr(0xE9),
    "bidi-override": "a" + chr(0x202E) + "b",
    "ellipsis": "(abc" + chr(0x2026) + ")",
}

#: For each text, the question that skips it in UTF-8, Latin-1 and ASCII, in
#: that order (None: none does). UTF-8 skips nothing. Latin-1 reads the byte E9
#: as U+00E9, writes U+00E9 as that byte and has no character for U+202E or
#: U+2026. ASCII reads the byte E9 as the surrogate and cannot spell the rest.
ANSWERS = {
    "plain": (None, None, None),
    "byte-e9": (None, READS_OTHER_TEXT, None),
    "e-acute": (None, WRITES_OTHER_BYTES, CANNOT_SPELL),
    "bidi-override": (None, CANNOT_SPELL, CANNOT_SPELL),
    "ellipsis": (None, CANNOT_SPELL, CANNOT_SPELL),
}
ENCODINGS = (UTF_8, LATIN_1, ASCII)
ASKED = [pytest.param(encoding, TEXTS[name], question,
                      id=f"{encoding}-{name}")
         for name, answered in ANSWERS.items()
         for encoding, question in zip(ENCODINGS, answered)]


def fsencode_in(encoding: str):
    """`os.fsencode` as a POSIX locale of `encoding` has it: that codec, with
    `surrogateescape`, so U+DC80 to U+DCFF are the bytes 0x80 to 0xFF. A path
    is taken as the real one takes it (`os.fspath` first), and bytes go
    through as they are."""
    def fsencode(name):
        name = os.fspath(name)
        if isinstance(name, bytes):
            return name
        return name.encode(encoding, "surrogateescape")
    return fsencode


def fsdecode_in(encoding: str):
    """`os.fsdecode` as a POSIX locale of `encoding` has it: that codec, with
    `surrogateescape`, so a byte it has no character for is U+DC80 to U+DCFF.
    A str goes through as it is, as on every system."""
    def fsdecode(name):
        name = os.fspath(name)
        if isinstance(name, str):
            return name
        return name.decode(encoding, "surrogateescape")
    return fsdecode


def locale_of(monkeypatch, encoding: str) -> None:
    """A locale whose file system encoding is `encoding`, as far as the
    helper can ask it: `os.fsencode`, `os.fsdecode` and the name the reason
    gives it."""
    monkeypatch.setattr(os, "fsencode", fsencode_in(encoding))
    monkeypatch.setattr(os, "fsdecode", fsdecode_in(encoding))
    monkeypatch.setattr(sys, "getfilesystemencoding", lambda: encoding)


def what_the_reason_says(question: str, encoding: str, text: str) -> str:
    """How the reason opens, for the question that skipped."""
    as_utf_8 = text.encode("utf-8", "surrogateescape")
    said = {CANNOT_SPELL: f"cannot spell {ascii(text)}: ",
            WRITES_OTHER_BYTES: f"writes {ascii(text)} as ",
            READS_OTHER_TEXT: f"reads {as_utf_8!r} as "}[question]
    return f"this locale's encoding ({encoding}) {said}"


@pytest.mark.parametrize(("encoding", "text", "question"), ASKED)
def test_the_helper_skips_what_the_locale_does_not_spell_as_utf_8_does(
        monkeypatch, encoding, text, question):
    """UTF-8 spells every text as itself, so nothing is skipped. A locale of
    one byte to a character skips a text it writes as other bytes, or reads
    back as other text, or cannot spell, and the reason says which, in the
    encoding's own name and with the row's premise at its end."""
    locale_of(monkeypatch, encoding)
    reason = skip_message(skip_where_the_locale_does_not_spell_it_as_utf_8,
                          text, PREMISE)
    if question is None:
        assert reason is None, (
            f"{encoding} spells {ascii(text)} as UTF-8 does, and it was "
            f"skipped: {reason}")
        return
    assert reason is not None, (
        f"{encoding} does not spell {ascii(text)} as UTF-8 does, and the row "
        "ran")
    opening = what_the_reason_says(question, encoding, text)
    assert reason.startswith(opening), reason
    assert reason.endswith(f": {PREMISE}"), reason
    assert reason.isascii(), reason


@LINUX_ONLY
@pytest.mark.parametrize("text", [pytest.param(text, id=name)
                                  for name, text in TEXTS.items()])
def test_the_emulation_of_this_runs_locale_answers_as_the_real_one_does(
        monkeypatch, text):
    """The emulation is held to the locale this run really has: the helper
    answers the same in the emulation of its file system encoding as with
    the real `os`, reason and all. A run in a locale that is none of the
    three has nothing to hold it to."""
    encoding = sys.getfilesystemencoding()
    if encoding not in ENCODINGS:
        pytest.skip(f"no emulation of {encoding} here")
    real = skip_message(skip_where_the_locale_does_not_spell_it_as_utf_8,
                        text, PREMISE)
    locale_of(monkeypatch, encoding)
    emulated = skip_message(skip_where_the_locale_does_not_spell_it_as_utf_8,
                            text, PREMISE)
    assert emulated == real
