# SPDX-License-Identifier: Apache-2.0
"""A test that makes a directory or a file named with a byte that is not UTF-8
(or with U+202E) skips on the system's answer and on no other error of the
disk (#834, #461).

Five more places beside the ones #757 moved onto `skip_where_a_name_cannot_be_
not_utf_8` (#663) turned ANY `OSError` into `pytest.skip`, so a disk that
filled up, a read-only `tmp_path` or a folder this user cannot write in read as
SKIPPED, and no run fails on a skip:

- `test_a_checkout_whose_path_is_not_utf8_is_a_checkout`
  (`tests/test_cli_reference.py`) and
  `test_a_name_that_is_not_utf8_is_never_an_exception_quoted_as_a_finding`
  (`tests/test_doctor_validator_verdicts.py`) made their own directory;
- `test_a_branch_whose_name_is_not_utf8_is_read_back_on_every_run`
  (`tests/test_bootstrap_leg_moves.py`) probed the disk with `write_bytes`;
- `make_file` (`tests/test_non_utf8_git_reads.py`) skipped on any `OSError` of
  its `write_bytes`, so each of its callers inherited the skip;
- the U+202E directory of `tests/test_adopt_template_values.py` is valid text,
  which no system known here refuses, so it skipped for nothing but a fault.

The first three now ask the helper, which skips on the two answers that mean
"this system cannot carry the name" (Windows' `os.fsencode` and macOS's EILSEQ)
and raises the rest. `make_file` skips on EILSEQ and on a `UnicodeError` (an
ASCII file name encoding, #757) and raises the rest, and the U+202E test makes
its directory with no guard.

Each is called here as a plain function, with the disk answering as it would on
a system this suite does not run on (CI is Linux only, #597), and asked what
it did. No Windows or macOS run was made:

- a disk that refuses the PROBE with EILSEQ (macOS): the test skips, on the
  helper's reason;
- a disk that refuses the probe, or the test's own name, with EACCES, ENOSPC
  or EROFS: the test raises it, where it skipped;
- Windows, by an `os.fsencode` that gives a surrogate three bytes: the three
  tests that ask the helper skip before the disk is touched.
"""

from __future__ import annotations

import errno
import os
from pathlib import Path

import pytest

import test_adopt_template_values as template_values
import test_bootstrap_leg_moves as leg_moves
import test_cli_reference as cli_reference
import test_doctor_validator_verdicts as doctor_verdicts
import test_non_utf8_git_reads as non_utf8_git_reads
from conftest import skip_message, windows_fsencode
# The fixtures and the two functions of #757's callers file, which ask the same
# questions of the same helper.
from test_non_utf8_name_callers import (  # noqa: F401 - fixtures
    PROBE, a_disk_that_takes_the_probe, a_system_that_carries_the_byte,
    fail_where_the_caller_ends)

#: The three tests that ask `skip_where_a_name_cannot_be_not_utf_8` for the
#: name of a directory under their `tmp_path`, each called with that and, for
#: the two that take a fixture of the project, `None`: they raise or skip
#: before they use it.
ASK_THE_HELPER = [
    pytest.param(
        lambda tmp_path: cli_reference
        .test_a_checkout_whose_path_is_not_utf8_is_a_checkout(tmp_path),
        id="cli-reference"),
    pytest.param(
        lambda tmp_path: doctor_verdicts
        .test_a_name_that_is_not_utf8_is_never_an_exception_quoted_as_a_finding(
            None, tmp_path),
        id="doctor-validator-verdicts"),
    pytest.param(
        lambda tmp_path: leg_moves
        .test_a_branch_whose_name_is_not_utf8_is_read_back_on_every_run(
            None, tmp_path),
        id="bootstrap-leg-moves"),
]
#: Those of them that go on to make a directory of their own after the probe.
THEN_MAKE_THEIR_OWN = [row for row in ASK_THE_HELPER
                       if row.id != "bootstrap-leg-moves"]

#: What the disk refuses with, and the exception Python raises for it.
REFUSALS = [pytest.param(errno.EACCES, PermissionError, id="EACCES"),
            pytest.param(errno.ENOSPC, OSError, id="ENOSPC"),
            pytest.param(errno.EROFS, OSError, id="EROFS")]


def the_probe(name: str) -> bool:
    return name.startswith(PROBE)


def anything_but_the_probe(name: str) -> bool:
    return not the_probe(name)


def the_error_of(kind, call, *args) -> OSError:
    """The `kind` of error `call(*args)` raises. A call that skips or ends
    without one FAILS the test, as `fail_where_the_caller_ends` has it."""
    with pytest.raises(kind) as raised:
        fail_where_the_caller_ends(call, *args)
    return raised.value


def a_disk_that_refuses(monkeypatch, code: int, names=None) -> None:
    """From here on a disk that answers `code` to every directory (`os.mkdir`,
    which `Path.mkdir` calls) and every file (`Path.write_bytes`) whose last
    part `names` accepts, to all of them where it is None, and makes the
    rest."""
    real_mkdir = os.mkdir
    real_write_bytes = Path.write_bytes

    def refused(name: str) -> bool:
        return names is None or names(name)

    def mkdir(path, *args, **kwargs):
        if refused(os.path.basename(os.fsdecode(path))):
            raise OSError(code, os.strerror(code), os.fsdecode(path))
        return real_mkdir(path, *args, **kwargs)

    def write_bytes(self, data):
        if refused(self.name):
            raise OSError(code, os.strerror(code), str(self))
        return real_write_bytes(self, data)

    monkeypatch.setattr(os, "mkdir", mkdir)
    monkeypatch.setattr(Path, "write_bytes", write_bytes)


# --- the three tests that ask the helper ------------------------------------

@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("call", ASK_THE_HELPER)
def test_a_disk_that_refuses_the_probe_with_eilseq_skips_the_test(
        tmp_path, monkeypatch, call):
    """macOS (emulated): the probe is `Illegal byte sequence`, so the test is
    SKIPPED, on the helper's reason, and nothing else is asked of the disk."""
    a_disk_that_refuses(monkeypatch, errno.EILSEQ, the_probe)
    reason = skip_message(call, tmp_path)
    assert reason is not None, "the test went on past the probe's EILSEQ"
    assert "EILSEQ" in reason, reason


@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("code, kind", REFUSALS)
@pytest.mark.parametrize("call", ASK_THE_HELPER)
def test_a_disk_that_refuses_the_probe_for_any_other_reason_fails_the_test(
        tmp_path, monkeypatch, call, code, kind):
    """A full disk, a read-only one or a folder nobody can write in: the
    helper raises it, so the test FAILS, and no run reads it as a skip."""
    a_disk_that_refuses(monkeypatch, code, the_probe)
    assert the_error_of(kind, call, tmp_path).errno == code


@pytest.mark.usefixtures("a_disk_that_takes_the_probe")
@pytest.mark.parametrize("code, kind", REFUSALS)
@pytest.mark.parametrize("call", THEN_MAKE_THEIR_OWN)
def test_a_disk_that_refuses_the_tests_own_directory_fails_the_test(
        tmp_path, monkeypatch, call, code, kind):
    """The probe is made and removed, and then the directory the test means
    to use is refused: that is the test's own, raised, where it was a skip. The
    rows ask the real disk for the probe first, and skip where it answers
    EILSEQ: they would FAIL there on a system that holds no defect."""
    a_disk_that_refuses(monkeypatch, code, anything_but_the_probe)
    assert the_error_of(kind, call, tmp_path).errno == code


@pytest.mark.parametrize("call", ASK_THE_HELPER)
def test_where_fsencode_makes_no_byte_of_the_surrogate_the_test_skips_first(
        tmp_path, monkeypatch, call):
    """Windows (emulated): the helper is asked BEFORE the disk, which would
    take the name, so the test skips on the system's reason and nothing is
    made under `tmp_path`: a test that made its directory first, or probed
    the disk and went on, ends without a skip here."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(call, tmp_path)
    assert reason is not None, "the test went on where fsencode gives no byte"
    assert "os.fsencode" in reason, reason
    assert list(tmp_path.iterdir()) == []


# --- `make_file` ------------------------------------------------------------

@pytest.mark.usefixtures("a_system_that_carries_the_byte")
def test_make_file_skips_where_the_disk_answers_eilseq(tmp_path, monkeypatch):
    """macOS (emulated): APFS refuses a file name that is not UTF-8 with
    `Illegal byte sequence`, which is the disk's answer, so the file is not
    written and the test that asked is skipped."""
    a_disk_that_refuses(monkeypatch, errno.EILSEQ)
    target = tmp_path / non_utf8_git_reads.NOT_UTF8
    reason = skip_message(non_utf8_git_reads.make_file, target)
    assert reason is not None, "make_file went on past the disk's EILSEQ"
    assert "filesystem" in reason, reason


def test_make_file_skips_where_the_file_name_encoding_cannot_spell_the_name(
        tmp_path, monkeypatch):
    """ASCII under `LC_ALL=C` (#757): the write raises `UnicodeEncodeError`
    before the disk is asked, which is the system's answer."""
    def write_bytes(self, data):
        raise UnicodeEncodeError("ascii", self.name, 0, 1,
                                 "ordinal not in range(128)")
    monkeypatch.setattr(Path, "write_bytes", write_bytes)
    target = tmp_path / non_utf8_git_reads.UTF8
    reason = skip_message(non_utf8_git_reads.make_file, target)
    assert reason is not None, "make_file raised where the encoding says no"
    assert "filesystem" in reason, reason


@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("name", [non_utf8_git_reads.NOT_UTF8,
                                  non_utf8_git_reads.UTF8],
                         ids=["not-utf-8", "utf-8"])
@pytest.mark.parametrize("code, kind", REFUSALS)
def test_make_file_raises_any_other_error_of_the_disk(
        tmp_path, monkeypatch, code, kind, name):
    """A full disk (ENOSPC), a read-only one (EROFS) or a folder nobody can
    write in (EACCES) is the test's own, for a name that is not UTF-8 and for
    one that is: raised as it was, and never a skip that hides it."""
    a_disk_that_refuses(monkeypatch, code)
    error = the_error_of(kind, non_utf8_git_reads.make_file, tmp_path / name)
    assert error.errno == code


# --- the U+202E directory ---------------------------------------------------

@pytest.mark.parametrize("code, kind", REFUSALS)
def test_a_disk_that_refuses_the_bidi_directory_fails_the_test(
        tmp_path, monkeypatch, code, kind):
    """U+202E is valid text: no probe is asked, and the directory is made with
    no guard, so what the disk answers to it is raised. It was a skip that said
    "no directory here is named ..." for a full disk or a read-only one."""
    a_disk_that_refuses(monkeypatch, code)
    error = the_error_of(
        kind, template_values
        .test_execute_refuses_a_local_source_directory_holding_a_bidi_control,
        tmp_path)
    assert error.errno == code
