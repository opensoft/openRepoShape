# SPDX-License-Identifier: Apache-2.0
"""A test that needs a directory named with a byte that is not UTF-8 asks the
one helper whether this system can carry it, and every other error of the disk
is the test's own (#757, #461).

Five tests and `directory_named` each made the directory themselves and turned
ANY `OSError` into `pytest.skip`, beside `skip_where_a_name_cannot_be_not_utf_8`
(#663), which skips on the two answers that mean "this system cannot carry the
name" -- Windows' `os.fsencode` and macOS's EILSEQ -- and raises the rest. So a
disk that filled up, or a `tmp_path` this user cannot write in, read as SKIPPED
there and as a failure in the helper's own tests, and no run fails on a skip.

Each caller is called here as a plain function, with the disk answering as it
would on the systems this suite does not run on (CI is Linux only, #597), and
asked what it did:

- the PROBE is refused with EILSEQ (macOS): the test skips, on the helper's
  reason;
- the PROBE is refused with EACCES: the test fails with `PermissionError`;
- the test's OWN directory is refused with EACCES, the probe not: the test
  fails with `PermissionError`, where it skipped.

Windows is emulated too, for the one caller whose own question is wider than
the helper's: `directory_named` skips there for a control character, which
Windows refuses in any file name, and for no other name that is text. No
Windows run was made.

The last two groups hold the C-locale half of the same issue. Under
`LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0` the file name encoding is ASCII,
so `make_file` cannot write `caf\\u00e9.yml` and `subprocess` cannot put a
`user.name` of `Jos\\u00e9` into a child's environment: the tests that do it
skip where this system cannot, and are held to it here with an ASCII
`os.fsencode` and a `write_bytes` that raises as it would.
"""

from __future__ import annotations

import errno
import os
import sys
from pathlib import Path

import pytest

import test_adopt_git_reads as git_reads
import test_adopt_plan_escapes as plan_escapes
import test_adopt_template_values as template_values
import test_clone_url_bytes as clone_url_bytes
import test_non_utf8_git_reads as non_utf8_git_reads
import test_stdout_encoding as stdout_encoding
from conftest import NOT_UTF_8_PROBE, skip_message, windows_fsencode
# The fixture of `test_adopt_plan_escapes.py`, `adopt-project.py` loaded as a
# module, which two of its tests ask for.
from test_adopt_plan_escapes import adopter  # noqa: F401 - fixture

#: Where the probe of the helper is: a directory named `probe<U+DCFF>`.
PROBE = "probe"

#: Every caller of the helper, as `(id, the call, whether it makes a directory
#: of its own after the probe)`; the call is given a `tmp_path` and the
#: `adopter` fixture. `directory_named` is called with the name the issue's
#: own row uses, `caf` and byte 0xE9.
CALLERS = [
    pytest.param(
        lambda tmp_path, adopter: stdout_encoding
        .test_a_name_that_is_not_utf8_still_comes_out_as_its_own_bytes(
            tmp_path, "utf-8:surrogateescape"),
        True, id="stdout-encoding"),
    pytest.param(
        lambda tmp_path, adopter: git_reads
        .test_a_utf8_clone_of_a_source_whose_path_is_not_utf8_adopts(tmp_path),
        True, id="adopt-git-reads"),
    pytest.param(
        lambda tmp_path, adopter: template_values
        .test_execute_refuses_a_local_source_directory_that_is_not_utf8(
            tmp_path),
        True, id="adopt-template-values"),
    pytest.param(
        lambda tmp_path, adopter: plan_escapes
        .test_a_source_directory_that_is_not_utf8_is_shown_spelled(
            adopter, tmp_path),
        True, id="adopt-plan-escapes-directory"),
    pytest.param(
        lambda tmp_path, adopter: clone_url_bytes.directory_named(
            tmp_path, b"caf\xe9"),
        True, id="clone-url-bytes"),
    pytest.param(
        lambda tmp_path, adopter: plan_escapes
        .test_a_leg_extracts_a_path_that_is_not_utf8(adopter, tmp_path),
        False, id="adopt-plan-escapes-file"),
]
EVERY_CALLER = [pytest.param(row.values[0], id=row.id) for row in CALLERS]
THOSE_WITH_A_DIRECTORY_OF_THEIR_OWN = [
    pytest.param(row.values[0], id=row.id) for row in CALLERS if row.values[1]]


def refusing(code: int, *, probe: bool):
    """An `os.mkdir` that fails with `code` for the probe (`probe=True`) or
    for every directory but the probe, and makes the rest. `Path.mkdir` calls
    it too."""
    real = os.mkdir

    def mkdir(path, *args, **kwargs):
        name = os.path.basename(os.fsdecode(path))
        if name.startswith(PROBE) is probe:
            raise OSError(code, os.strerror(code), os.fsdecode(path))
        return real(path, *args, **kwargs)
    return mkdir


@pytest.fixture
def a_system_that_carries_the_byte():
    if len(os.fsencode(NOT_UTF_8_PROBE)) != 1:
        pytest.skip("on this system the first question is the one that skips")


# --- the disk's refusals, on the systems CI does not run --------------------

@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("call", EVERY_CALLER)
def test_a_disk_that_refuses_the_name_with_eilseq_skips_the_caller(
        tmp_path, monkeypatch, adopter, call):
    """macOS (emulated): the probe is refused as `Illegal byte sequence`, so
    the test is SKIPPED, on the helper's reason."""
    monkeypatch.setattr(os, "mkdir", refusing(errno.EILSEQ, probe=True))
    reason = skip_message(call, tmp_path, adopter)
    assert reason is not None, "the caller went on past the probe's EILSEQ"
    assert "EILSEQ" in reason, reason


@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("call", EVERY_CALLER)
def test_a_disk_that_refuses_the_probe_with_eacces_fails_the_caller(
        tmp_path, monkeypatch, adopter, call):
    """A folder nobody can write in: the helper raises it, as its own tests
    hold, so the test FAILS, and no run reads it as a skip."""
    monkeypatch.setattr(os, "mkdir", refusing(errno.EACCES, probe=True))
    with pytest.raises(PermissionError):
        reason = skip_message(call, tmp_path, adopter)
        pytest.fail("the caller ended "
                    + (f"SKIPPED: {reason}" if reason else "without an error"))


@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("call", THOSE_WITH_A_DIRECTORY_OF_THEIR_OWN)
def test_a_disk_that_refuses_the_tests_own_directory_fails_the_test(
        tmp_path, monkeypatch, adopter, call):
    """The probe is made and removed, and then the directory the test means
    to use is refused with EACCES: that is the test's own, raised, where it
    was a skip that said "no directory here is named ..."."""
    monkeypatch.setattr(os, "mkdir", refusing(errno.EACCES, probe=False))
    with pytest.raises(PermissionError):
        reason = skip_message(call, tmp_path, adopter)
        pytest.fail("the caller ended "
                    + (f"SKIPPED: {reason}" if reason else "without an error"))


# --- `directory_named`'s own question: Windows, emulated --------------------

def windows_names_it(monkeypatch) -> None:
    """Windows, as far as `skip_where_this_system_cannot_name` can ask it:
    `os.name` is `nt` and `os.fsencode` gives a surrogate three bytes."""
    monkeypatch.setattr(os, "name", "nt")
    monkeypatch.setattr(os, "fsencode", windows_fsencode)


def test_where_windows_cannot_carry_the_byte_directory_named_skips_and_makes_nothing(
        tmp_path, monkeypatch):
    windows_names_it(monkeypatch)
    reason = skip_message(clone_url_bytes.skip_where_this_system_cannot_name,
                          tmp_path, b"caf\xe9")
    assert reason is not None, "a name that is not UTF-8 was not skipped"
    assert "os.fsencode" in reason, reason
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("raw", [b"line\nbreak", b"a\x1bb"],
                         ids=["line-feed", "escape"])
def test_where_windows_refuses_a_control_character_directory_named_skips(
        tmp_path, monkeypatch, raw):
    windows_names_it(monkeypatch)
    reason = skip_message(clone_url_bytes.skip_where_this_system_cannot_name,
                          tmp_path, raw)
    assert reason is not None, f"{raw!r} was not skipped on Windows"
    assert "control character" in reason, reason


def test_where_windows_holds_a_bidi_override_directory_named_does_not_skip(
        tmp_path, monkeypatch):
    """The row #459 names (R433 O5): NTFS holds U+202E, so the `bidi-override`
    row of the clone-URL tests runs on Windows as it does here. Reasoned, and
    asked here only of the skip: no Windows run was made."""
    windows_names_it(monkeypatch)
    raw = "\u202eevil".encode("utf-8")
    assert skip_message(clone_url_bytes.skip_where_this_system_cannot_name,
                        tmp_path, raw) is None


@pytest.mark.skipif(os.name == "nt", reason="Windows is the case above")
@pytest.mark.parametrize("raw", [b"line\nbreak", b"a\x1bb"],
                         ids=["line-feed", "escape"])
def test_a_system_that_is_not_windows_makes_a_control_character_directory(
        tmp_path, raw):
    """The control: a POSIX disk takes the name, so no skip."""
    assert skip_message(clone_url_bytes.skip_where_this_system_cannot_name,
                        tmp_path, raw) is None
    assert os.path.basename(clone_url_bytes.directory_named(
        tmp_path, raw)) == os.fsdecode(raw)


# --- under an ASCII file name encoding (LC_ALL=C PYTHONUTF8=0) --------------

def ascii_fsencode(value):
    """`os.fsencode` where the file name encoding is ASCII, with
    `surrogateescape`: text outside ASCII raises, and a lone surrogate that
    stands for a byte is that byte."""
    value = os.fspath(value)
    if isinstance(value, bytes):
        return value
    return value.encode("ascii", "surrogateescape")


def test_make_files_utf8_name_test_skips_where_the_encoding_is_ascii(
        tmp_path, monkeypatch):
    """`make_file` cannot write `caf\\u00e9.yml` where the file name encoding is
    ASCII, and says so as a skip on `filesystem`. The test about the guard
    reads that skip as it reads it in its neighbour, and is SKIPPED: it failed
    on `assert skip_message(make_file, ...) is None`, on a system that holds
    no defect. Emulated: `write_bytes` raises what the ASCII encoding does."""
    real = Path.write_bytes

    def write_bytes(self, data):
        for index, char in enumerate(self.name):
            if not char.isascii():
                raise UnicodeEncodeError("ascii", self.name, index, index + 1,
                                         "ordinal not in range(128)")
        return real(self, data)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)
    reason = skip_message(
        non_utf8_git_reads
        .test_make_file_writes_a_name_that_is_utf8_where_fsencode_makes_no_byte,
        tmp_path, monkeypatch)
    assert reason is not None, "the test went on past an ASCII encoding"
    assert "filesystem" in reason, reason


@pytest.mark.parametrize("value", ["Jos\u00e9", "Mehr\u200cdad", "\u202eevil"],
                         ids=["accent", "zwnj", "u202e"])
def test_a_user_name_the_encoding_cannot_carry_skips_where_it_is_ascii(
        monkeypatch, value):
    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    reason = skip_message(
        non_utf8_git_reads.skip_where_the_environment_cannot_carry, value)
    assert reason is not None, f"{value!r} was carried by an ASCII encoding"
    assert "environment" in reason, reason


@pytest.mark.parametrize("value", ["Jose", "Jos\udce9", "Ada\nLovelace",
                                   "a\x1bb"],
                         ids=["ascii", "byte", "line-feed", "escape"])
def test_a_user_name_the_encoding_carries_is_not_skipped_even_where_it_is_ascii(
        monkeypatch, value):
    """ASCII text, a lone surrogate that is a byte, and the control characters
    are the environment's own: the tests of them still run."""
    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    assert skip_message(
        non_utf8_git_reads.skip_where_the_environment_cannot_carry,
        value) is None


@pytest.mark.parametrize("test, args", [
    pytest.param("test_a_user_name_that_is_text_still_initialises",
                 ("Jos\u00e9", True), id="text-still-initialises"),
    pytest.param("test_every_other_name_no_file_can_hold_is_refused_the_same_way",
                 ("\u202eevil", "it holds a bidirectional control"),
                 id="every-other-name"),
])
def test_the_two_tests_that_pass_the_name_in_an_environment_skip_where_it_is_ascii(
        tmp_path, monkeypatch, test, args):
    """Both of them fail on the `UnicodeEncodeError` that `subprocess` raises
    in the test (the tool is not reached), under an ASCII encoding."""
    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    reason = skip_message(getattr(non_utf8_git_reads, test), tmp_path, *args)
    assert reason is not None, "the test ran, and raised or passed on ASCII"
    assert "environment" in reason, reason
