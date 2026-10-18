# SPDX-License-Identifier: Apache-2.0
"""A test that needs a directory, or a branch, named with a byte that is not
UTF-8 asks the system once whether it can carry the name, and a failure of the
git call that follows fails the test (#853, #461).

Six places turned a failure of git into `pytest.skip`. The issue's scan of
`tests/*.py` found five; the sixth, `remembered_on`, came with #830 (#797)
after it:

- `refused_then_moved` (`tests/test_adopt_template_values.py`),
  `test_a_utf8_clone_of_a_source_whose_path_is_not_utf8_adopts`
  (`tests/test_adopt_git_reads.py`) and
  `test_a_source_directory_that_is_not_utf8_is_shown_spelled`
  (`tests/test_adopt_plan_escapes.py`) skipped "git will not work under ..."
  on an `AssertionError` of `make_source_repo` under the directory `caf` and
  byte 0xE9;
- `with_default_branch`, `moved_to_a_branch_that_is_not_utf8` and
  `remembered_on` (`tests/test_adopt_git_reads.py`) skipped "no branch here
  is named ..." on an `AssertionError`, a `UnicodeError` or an `OSError` of
  the git calls that make the branch, and the first and the last are called
  with a name that is text too (`main` and U+00A0, `ma`, U+2028 and `in`).

A git process that fails raises `AssertionError` (`conftest.git`, and
`make_source_repo`'s own commits), so a disk that filled after the `mkdir`, or
a directory git could no longer write in, read as SKIPPED, and no run fails
on a skip. The answers that mean "this system cannot carry the name" are
asked before git now, and every git call after them is unguarded: for a
directory, `skip_where_a_name_cannot_be_not_utf_8`, which the three tests
already asked (#757); for a branch, `skip_where_no_ref_can_be_named`, which
asks that helper for a name that is not UTF-8 and the file name encoding for
a name that is text. The skip after `git symbolic-ref` stays: whether git
gives the name back as it was written is the system's answer, and no
exception is behind it.

#854 is the C-locale half: under `PYTHONUTF8=0 LC_ALL=C PYTHONCOERCECLOCALE=0`
the file name encoding is ASCII, and the U+202E test's `mkdir` raised
`UnicodeEncodeError`, a `ValueError` its old `except OSError` never caught,
so the test ended in an error. It asks the encoding before the `mkdir` now.
The six tests of `tests/test_adopt_template_values.py` that ask it before
`make_source_repo` (a flag, an elector or a directory that ASCII cannot
spell) are held for CI, which runs UTF-8, by rows that emulate ASCII.

Each place is called here as a plain function, with git made to fail as a
full disk makes `git commit` fail, or with a system emulated that CI does not
run (CI is Linux only, #597; no Windows or macOS run was made):

- git fails: the test FAILS with git's error, for a name that is not UTF-8
  and for one that is text;
- Windows' `os.fsencode` (a surrogate is three bytes): the three tests of the
  byte directory are skipped on the helper's reason before their `mkdir` and
  before git, and make nothing (macOS's EILSEQ on the probe is held for them
  by #757's rows in `tests/test_non_utf8_name_callers.py`);
- macOS's EILSEQ on the probe, or Windows' `os.fsencode`: a branch that is
  not UTF-8 is skipped on the helper's reason before git is called and
  before anything is made; a branch that is text asks neither and goes on
  to git;
- an ASCII file name encoding: a branch that is text, and the U+202E test, are
  skipped on the encoding's reason, before git and before the `mkdir`; so
  are the six tests of `tests/test_adopt_template_values.py` that ask the
  encoding first, before `make_source_repo` (which would fail here) and
  before anything is made under `tmp_path`;
- every `tests/*.py`, read as #853's scan reads it and wider: no `except`
  that catches an `AssertionError` (one that names it, `Exception` or
  `BaseException`, or a bare one) holds a `pytest.skip`.
"""

from __future__ import annotations

import ast
import errno
import os
from textwrap import dedent

import pytest

import test_adopt_git_reads as git_reads
import test_adopt_plan_escapes as plan_escapes
import test_adopt_template_values as template_values
from conftest import (REPO, skip_message,
                      skip_where_the_environment_cannot_carry,
                      windows_fsencode)
# The fixture of `test_adopt_plan_escapes.py`, `adopt-project.py` loaded as a
# module, which its directory test asks for.
from test_adopt_plan_escapes import adopter  # noqa: F401 - fixture
# The fixtures and the emulations of #757's callers file, and the failure of
# git and the way of asking for an error of #834's sites file.
from test_non_utf8_name_callers import (  # noqa: F401 - fixtures
    a_disk_that_takes_the_probe, a_system_that_carries_the_byte,
    ascii_fsencode, refusing)
from test_non_utf8_oserror_sites import (BIDI_TEST, GIT_FAILED,
                                         a_source_git_cannot_make,
                                         the_error_of)

# --- a source repository under a directory that is not UTF-8 ----------------

#: The three tests that make a source repository under the directory `caf` and
#: byte 0xE9, each with the module whose `make_source_repo` it calls, called
#: with a `tmp_path` and the `adopter` fixture.
UNDER_A_BYTE_DIRECTORY = [
    pytest.param(
        template_values,
        lambda tmp_path, adopter: template_values
        .test_execute_refuses_a_local_source_directory_that_is_not_utf8(
            tmp_path),
        id="adopt-template-values"),
    pytest.param(
        git_reads,
        lambda tmp_path, adopter: git_reads
        .test_a_utf8_clone_of_a_source_whose_path_is_not_utf8_adopts(tmp_path),
        id="adopt-git-reads"),
    pytest.param(
        plan_escapes,
        lambda tmp_path, adopter: plan_escapes
        .test_a_source_directory_that_is_not_utf8_is_shown_spelled(
            adopter, tmp_path),
        id="adopt-plan-escapes"),
]


@pytest.mark.usefixtures("a_disk_that_takes_the_probe")
@pytest.mark.parametrize("module, call", UNDER_A_BYTE_DIRECTORY)
def test_a_failure_of_git_under_the_byte_directory_fails_the_test(
        tmp_path, monkeypatch, adopter, module, call):
    """The directory is made, and then git cannot make the source repository
    in it, as on a disk that filled after the `mkdir`: the test FAILS with
    git's error, where it was SKIPPED as "git will not work under ...". The
    rows ask the real disk for the probe first, and skip where it answers
    EILSEQ, as the test does before git is reached."""
    monkeypatch.setattr(module, "make_source_repo", a_source_git_cannot_make)
    error = the_error_of(AssertionError, call, tmp_path, adopter)
    assert str(error) == GIT_FAILED


@pytest.mark.parametrize("module, call", UNDER_A_BYTE_DIRECTORY)
def test_where_fsencode_makes_no_byte_the_byte_directory_test_skips_first(
        tmp_path, monkeypatch, adopter, module, call):
    """Windows (emulated): `os.fsencode` gives the surrogate three bytes, so
    the test skips on the helper's reason before it makes its directory or
    asks git (which would fail here), and nothing is made under `tmp_path`.
    A test that asked after its `mkdir` would leave the directory here, and
    on Windows raise at `os.fsdecode` of the name instead of skipping."""
    monkeypatch.setattr(module, "make_source_repo", a_source_git_cannot_make)
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(call, tmp_path, adopter)
    assert reason is not None, "the test went on where fsencode makes none"
    assert "os.fsencode" in reason, reason
    assert list(tmp_path.iterdir()) == []


# --- a branch or a ref that is not UTF-8, or is text ------------------------

#: The three helpers of `tests/test_adopt_git_reads.py` that make a branch or a
#: ref with git, given a name that is not UTF-8 (`BRANCH`, `caf` and byte
#: 0xE9), each called with a `tmp_path`. The source is `tmp_path / "Thing"`;
#: only `moved_to_a_branch_that_is_not_utf8` makes it itself.
NOT_UTF_8_NAMES = [
    pytest.param(
        lambda base: git_reads.with_default_branch(base / "Thing",
                                                   git_reads.ORIGIN_HEAD),
        id="with-default-branch-origin-head"),
    pytest.param(
        lambda base: git_reads.with_default_branch(base / "Thing", "head"),
        id="with-default-branch-head"),
    pytest.param(git_reads.moved_to_a_branch_that_is_not_utf8,
                 id="moved-to-a-branch-that-is-not-utf8"),
    pytest.param(
        lambda base: git_reads.remembered_on(base / "Thing", git_reads.BRANCH),
        id="remembered-on"),
]
#: The two of them that are also given a name that is text, with that name.
TEXT_NAMES = [
    pytest.param(
        lambda base: git_reads.with_default_branch(
            base / "Thing", git_reads.ORIGIN_HEAD, git_reads.NBSP_BRANCH),
        git_reads.NBSP_BRANCH, id="with-default-branch-nbsp"),
    pytest.param(
        lambda base: git_reads.remembered_on(base / "Thing",
                                             git_reads.LINE_SEPARATED),
        git_reads.LINE_SEPARATED, id="remembered-on-u2028"),
]


def git_fails(monkeypatch) -> None:
    """From here on every git call the module makes itself fails as
    `conftest.git` fails where `git commit` cannot write an object. Only the
    module's own name is replaced: `make_source_repo` and the tool's runs
    still reach the real git."""
    monkeypatch.setattr(git_reads, "git", a_source_git_cannot_make)


@pytest.mark.usefixtures("a_disk_that_takes_the_probe")
@pytest.mark.parametrize("call", NOT_UTF_8_NAMES)
def test_a_failure_of_git_making_a_branch_that_is_not_utf8_fails_the_test(
        tmp_path, monkeypatch, call):
    """The system carries the name, so the helper goes on to git, and git's
    failure reaches the test as a failure, where it was SKIPPED as "no
    branch here is named ...". The rows ask the real disk for the probe
    first, as the helper does."""
    git_fails(monkeypatch)
    error = the_error_of(AssertionError, call, tmp_path)
    assert str(error) == GIT_FAILED


@pytest.mark.parametrize("call, name", TEXT_NAMES)
def test_a_failure_of_git_making_a_branch_that_is_text_fails_the_test(
        tmp_path, monkeypatch, call, name):
    """No system refuses a name that is text, so every skip there hid a
    failure. Skipped where this system's file name encoding cannot spell the
    name (ASCII under `LC_ALL=C`): the helper skips there first."""
    skip_where_the_environment_cannot_carry(name)
    git_fails(monkeypatch)
    error = the_error_of(AssertionError, call, tmp_path)
    assert str(error) == GIT_FAILED


@pytest.mark.usefixtures("a_system_that_carries_the_byte")
@pytest.mark.parametrize("call", NOT_UTF_8_NAMES)
def test_a_disk_that_refuses_the_probe_with_eilseq_skips_before_git(
        tmp_path, monkeypatch, call):
    """macOS (emulated): the probe is `Illegal byte sequence`, so the helper
    skips, on its reason, before any git call (each would fail here) and
    before anything is made under `tmp_path`."""
    git_fails(monkeypatch)
    monkeypatch.setattr(os, "mkdir", refusing(errno.EILSEQ, probe=True))
    reason = skip_message(call, tmp_path)
    assert reason is not None, "the helper went on past the probe's EILSEQ"
    assert "EILSEQ" in reason, reason
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("call", NOT_UTF_8_NAMES)
def test_where_fsencode_makes_no_byte_of_the_surrogate_the_branch_skips_first(
        tmp_path, monkeypatch, call):
    """Windows (emulated): `os.fsencode` gives the surrogate three bytes, so
    no argument can carry the byte. The helper skips on that reason before
    the disk and git are asked, and nothing is made under `tmp_path`."""
    git_fails(monkeypatch)
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(call, tmp_path)
    assert reason is not None, "the helper went on where fsencode makes none"
    assert "os.fsencode" in reason, reason
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("call, name", TEXT_NAMES)
def test_a_branch_that_is_text_asks_nothing_of_a_byte(
        tmp_path, monkeypatch, call, name):
    """Neither macOS's EILSEQ to a name that is not UTF-8 nor Windows'
    `os.fsencode` of a surrogate is the answer for a name that is text, so
    with both in place the helper goes on to git, and git's failure is the
    test's. Skipped where the file name encoding cannot spell the name, as
    the test above is."""
    skip_where_the_environment_cannot_carry(name)
    git_fails(monkeypatch)
    monkeypatch.setattr(os, "mkdir", refusing(errno.EILSEQ, probe=True))
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    error = the_error_of(AssertionError, call, tmp_path)
    assert str(error) == GIT_FAILED


@pytest.mark.parametrize("call, name", TEXT_NAMES)
def test_where_the_file_name_encoding_is_ascii_a_branch_that_is_text_skips(
        tmp_path, monkeypatch, call, name):
    """`LC_ALL=C` (emulated): `subprocess` puts each argument through
    `os.fsencode`, which cannot spell U+00A0 or U+2028 in ASCII, so the
    helper skips on the encoding's reason before git is called, where the
    git call raised `UnicodeEncodeError` in the test."""
    git_fails(monkeypatch)
    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    reason = skip_message(call, tmp_path)
    assert reason is not None, f"{name!r} went on to git under ASCII"
    assert "file name encoding" in reason, reason


# --- the U+202E directory under an ASCII file name encoding (#854) ----------

def test_where_the_file_name_encoding_cannot_spell_u202e_the_bidi_test_skips(
        tmp_path, monkeypatch):
    """`LC_ALL=C` (emulated as the real one answers): `os.fsencode` is ASCII,
    and `os.mkdir` raises `UnicodeEncodeError` for a name ASCII cannot
    encode. The test asks the encoding before its `mkdir` and skips on the
    encoding's reason, worded as `make_file`'s is, and makes nothing; it
    ended in that `UnicodeEncodeError`."""
    real_mkdir = os.mkdir

    def mkdir(path, *args, **kwargs):
        ascii_fsencode(path)
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    monkeypatch.setattr(os, "mkdir", mkdir)
    reason = skip_message(BIDI_TEST, tmp_path)
    assert reason is not None, "the test went on past an ASCII encoding"
    assert "this system's file name encoding" in reason, reason
    assert "cannot spell" in reason, reason
    assert list(tmp_path.iterdir()) == []


#: The six tests of `tests/test_adopt_template_values.py` that skip where the
#: file name encoding cannot spell their value (#854), each called with a
#: `tmp_path`: the flag test with the three values ASCII cannot spell (U+2028,
#: U+202E and U+2066), the elector test with `Jos\u00e9` and a name joined
#: with U+200C, and the test of a source under a directory `caf\u00e9`.
WHERE_ASCII_CANNOT_SPELL = [
    pytest.param(
        lambda base: template_values.test_plan_refuses_a_flag_no_file_can_hold(
            base, "--elected-by", "Jos\u2028e"),
        id="flag-u2028"),
    pytest.param(
        lambda base: template_values.test_plan_refuses_a_flag_no_file_can_hold(
            base, "--elected-by", "\u202eevil"),
        id="flag-u202e"),
    pytest.param(
        lambda base: template_values.test_plan_refuses_a_flag_no_file_can_hold(
            base, "--reference", "ref \u2066x\u2069 y"),
        id="flag-u2066"),
    pytest.param(
        lambda base: template_values
        .test_a_valid_non_ascii_elector_still_adopts(base, "Jos\u00e9"),
        id="elector-accented"),
    pytest.param(
        lambda base: template_values
        .test_a_valid_non_ascii_elector_still_adopts(base, "Ali\u200cReza"),
        id="elector-zwnj"),
    pytest.param(
        template_values
        .test_a_utf8_source_directory_still_adopts_with_local_remotes,
        id="cafe-directory"),
]


@pytest.mark.parametrize("call", WHERE_ASCII_CANNOT_SPELL)
def test_where_the_file_name_encoding_is_ascii_the_template_values_tests_skip(
        tmp_path, monkeypatch, call):
    """`LC_ALL=C` (emulated): `os.fsencode` is ASCII, so each test skips on
    the encoding's reason before `make_source_repo` (which fails here, as git
    fails on a full disk) and before any directory is made, and makes nothing
    under `tmp_path`. CI runs UTF-8, where a test that asked after either
    would still pass; these rows fail it there, as the real `LC_ALL=C` run
    does."""
    monkeypatch.setattr(template_values, "make_source_repo",
                        a_source_git_cannot_make)
    monkeypatch.setattr(os, "fsencode", ascii_fsencode)
    reason = skip_message(call, tmp_path)
    assert reason is not None, "the test went on under an ASCII encoding"
    assert "file name encoding" in reason, reason
    assert list(tmp_path.iterdir()) == []


# --- no test skips on an `AssertionError` -----------------------------------

def names_in(node: ast.expr | None) -> set[str]:
    """The names an `except` clause catches: one, or each of a tuple."""
    if isinstance(node, ast.Tuple):
        return {name for element in node.elts for name in names_in(element)}
    if isinstance(node, ast.Name):
        return {node.id}
    if isinstance(node, ast.Attribute):
        return {node.attr}
    return set()


def is_pytest_skip(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "skip"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "pytest")


#: What an `except` that catches an `AssertionError` names: the error itself
#: or a class above it. A bare `except` catches it too.
CATCH_AN_ASSERTION_ERROR = {"AssertionError", "Exception", "BaseException"}


def catches_an_assertion_error(handler: ast.ExceptHandler) -> bool:
    """A bare `except`, or one that names `AssertionError`, `Exception` or
    `BaseException`, alone or in a tuple."""
    return (handler.type is None
            or bool(names_in(handler.type) & CATCH_AN_ASSERTION_ERROR))


def skips_that_catch_an_assertion_error(source: str) -> list[int]:
    """The line of each `except` in `source` that catches an
    `AssertionError` and holds a call of `pytest.skip` anywhere in its body:
    #853's scan, of an `except` that names `AssertionError`, and with it one
    that catches the error without naming it (`Exception`, `BaseException`
    or a bare `except`), which would hide a failed git call as well."""
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ExceptHandler)
            and catches_an_assertion_error(node)
            and any(is_pytest_skip(inner) for inner in ast.walk(node))]


def test_no_test_skips_on_an_assertion_error():
    """`conftest.git` and `make_source_repo` raise `AssertionError` for a git
    process that fails, whatever made it fail, so an `except` that catches it
    and skips turns a full disk into SKIPPED, whether it names the error,
    `Exception` or `BaseException`, or nothing. Where a system cannot carry a
    name, a test asks it first and skips on that answer; the git call after
    it is unguarded. Every `tests/*.py`, this file and `conftest.py`
    included."""
    found = {}
    for path in sorted((REPO / "tests").glob("*.py")):
        lines = skips_that_catch_an_assertion_error(
            path.read_text(encoding="utf-8"))
        if lines:
            found[path.name] = lines
    assert found == {}, found


@pytest.mark.parametrize("source, lines", [
    pytest.param("""
        try:
            make()
        except AssertionError as exc:
            pytest.skip(f"git will not work here: {exc}")
        """, [4], id="alone"),
    pytest.param("""
        try:
            make()
        except (AssertionError, UnicodeError, OSError) as exc:
            pytest.skip(f"no branch here is named: {exc!r}")
        """, [4], id="in-a-tuple"),
    pytest.param("""
        try:
            make()
        except AssertionError:
            if not asked:
                raise
            pytest.skip("git will not work here")
        """, [4], id="behind-a-raise"),
    pytest.param("""
        try:
            make()
        except Exception as exc:
            pytest.skip(f"no branch here is named: {exc!r}")
        """, [4], id="exception"),
    pytest.param("""
        try:
            make()
        except (OSError, BaseException):
            pytest.skip("anything at all")
        """, [4], id="base-exception-in-a-tuple"),
    pytest.param("""
        try:
            make()
        except:
            pytest.skip("anything at all")
        """, [4], id="bare"),
    pytest.param("""
        try:
            make()
        except AssertionError:
            raise
        """, [], id="no-skip"),
    pytest.param("""
        try:
            make()
        except Exception:
            raise
        """, [], id="exception-no-skip"),
    pytest.param("""
        try:
            make()
        except OSError:
            pytest.skip("another error")
        """, [], id="another-error"),
    pytest.param("""
        if not read.endswith(written):
            pytest.skip("git here does not give the name back")
        """, [], id="a-skip-on-an-answer"),
])
def test_the_scan_finds_a_skip_on_an_assertion_error_and_nothing_else(
        source, lines):
    """A skip behind an `if` in the `except` is found too, as #845's
    `skip_where_git_fails` had it, and so is one in an `except` that catches
    the error without naming it: `Exception`, `BaseException`, or a bare
    `except`. An `except` that does not skip, one of another error, and the
    skip after `git symbolic-ref`, which answers a question and catches
    nothing, are not."""
    assert skips_that_catch_an_assertion_error(dedent(source)) == lines
