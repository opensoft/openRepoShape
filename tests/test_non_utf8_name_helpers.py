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

The locale's question is asked between the two (#1196): in a locale of one
byte to a character, Latin-1 say, `os.fsdecode(b"\\xff")` is the character
U+00FF and not the surrogate U+DCFF, so a name that holds the byte is text
there, and a test that expects it spelled as a name that is not UTF-8 would
fail on a tool that is right. `os.fsdecode` is EMULATED too, for one test: no
Latin-1 locale is built here, as `tests/test_adopt_one_byte_locale.py` builds
one for a child.

The two tools the tests below are written with are held here too:
`skip_message`, which every one of them reads a skip with, and
`windows_fsencode`, the emulation itself.
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
                      windows_fsencode)

LINUX_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("linux"),
    reason="Linux stores any byte in a file name; the other systems are "
           "asked by the tests below that emulate them")


def fsdecode_in(encoding: str):
    """`os.fsdecode` as a locale whose file name encoding is `encoding` has
    it: text is returned as it is, and bytes are read in `encoding`, with
    `surrogateescape` for each one it cannot read (a UTF-8 locale gives the
    byte 0xFF as U+DCFF, and a Latin-1 one as U+00FF)."""
    def fsdecode(filename):
        filename = os.fspath(filename)
        if isinstance(filename, str):
            return filename
        return filename.decode(encoding, "surrogateescape")
    return fsdecode


def skip_where_an_earlier_question_skips() -> None:
    """The rows that let the probe through to the real disk ask the system's
    question and the locale's first (#1196), and skip where either would: the
    helper then skips on its own reason, and not on the one they hold."""
    if (len(os.fsencode(NOT_UTF_8_PROBE)) != 1
            or os.fsdecode(b"\xff") != NOT_UTF_8_PROBE):
        pytest.skip("on this system an earlier question is the one that skips")


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
    skip_where_an_earlier_question_skips()
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


@LINUX_ONLY
@pytest.mark.parametrize("encoding", ["utf-8", "ascii"])
def test_a_locale_that_reads_the_byte_as_the_surrogate_is_not_skipped(
        tmp_path, monkeypatch, encoding):
    """The control of the locale's question (#1196): UTF-8 and ASCII give the
    byte 0xFF back as U+DCFF, which is `NOT_UTF_8_PROBE`, so no test that
    asks is skipped, and the probe is removed."""
    monkeypatch.setattr(os, "fsdecode", fsdecode_in(encoding))
    assert os.fsdecode(b"\xff") == NOT_UTF_8_PROBE
    assert skip_message(skip_where_a_name_cannot_be_not_utf_8,
                        tmp_path) is None
    assert list(tmp_path.iterdir()) == []


def test_a_locale_that_reads_the_byte_as_a_character_skips_before_the_disk(
        tmp_path, monkeypatch):
    """Latin-1 (emulated): the byte 0xFF is U+00FF, a printable character,
    so no name holding it is one that is not UTF-8, and the name is skipped.
    THE LOCALE IS ASKED BEFORE THE DISK (#1196), as the system is: the
    directory does not exist, so an `mkdir` under it would be
    FileNotFoundError and not a skip, and the skip is the answer."""
    monkeypatch.setattr(os, "fsdecode", fsdecode_in("iso8859-1"))
    assert os.fsdecode(b"\xff") == "\u00ff"
    reason = skip_message(skip_where_a_name_cannot_be_not_utf_8,
                          tmp_path / "absent")
    assert reason is not None, "the helper went on to ask the disk"
    assert "0xFF" in reason, reason
    assert "'\\xff'" in reason, reason


def test_a_disk_that_answers_eilseq_is_skipped(tmp_path, monkeypatch):
    """macOS (emulated): APFS answers EILSEQ, `Illegal byte sequence`, to a
    file name that is not UTF-8, and no clone can sit at such a path."""
    skip_where_an_earlier_question_skips()
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
    skip_where_an_earlier_question_skips()
    monkeypatch.setattr(Path, "mkdir", mkdir_answers(code, os.strerror(code)))
    with pytest.raises(OSError) as raised:
        skip_message(skip_where_a_name_cannot_be_not_utf_8, tmp_path)
    assert raised.value.errno == code
