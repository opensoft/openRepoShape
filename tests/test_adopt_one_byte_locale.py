# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py check`: a plan written in UTF-8 is read under a locale
of one byte to a character, Latin-1 say, where its `source.local_path` is
asked as written and, where that names nothing, as the plan's UTF-8 bytes
too (#1078, found in the review of #1072).

ON 2a119f28 (2026-10-21), Python 3.12.3, a Latin-1 locale built with
`localedef` (`sys.getfilesystemencoding()` `iso8859-1`), `PYTHONUTF8=0`: a
plan written in UTF-8 mode for a source directory `Thing\\u00e9` was
`plan-source-gone`, "names nothing that exists", exit 2, of a source that
is there; recorded as a clone `plan` made, it "no longer exists" and `gh
repo clone` was asked. `os.fsencode` spells the recorded text in Latin-1,
the last character as the one byte 0xE9, but the name on the disk is the
two bytes 0xC3 0xA9 `plan` read. Under C and POSIX the same plan was `plan
ok` (#1072, which asks the UTF-8 bytes where the locale cannot spell the
text).

Now `check` reads the source, `plan ok`, under Latin-1 as under C and
POSIX. The spelling as written is still asked first, and where neither
names anything the refusal is word for word as before.

THE LOCALE IS BUILT HERE, in the module's temporary directory, from a
charmap and a locale source this file writes, so it needs only `localedef`
and a C library that reads `LOCPATH` (glibc): a host without the `locales`
package has no `en_US` source and no charmaps to build one from. ISO-8859-1
maps each byte to the code point of the same number. The tests skip, with
`localedef`'s own words, where no such locale can be built, and on Windows,
which hands a command line to `CreateProcessW` as UTF-16.
"""

from __future__ import annotations

import codecs
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import ADOPT, blank_unnamed_pin_sources, spelled
from test_adopt_git_rm_bytes import C_LOCALE, LOCALE_KEYS, c_locale_or_skip
from test_adopt_temp_work_roots import recorded
from test_adopt_unenterable_source_and_locale import (
    ACCENTED, KEEP_THE_CLONE, written_in_utf8_mode,
)

#: The locale #1078 names, as `LC_ALL` names the one built here.
LATIN1_NAME = "en_US.ISO-8859-1"
#: `codecs.lookup(...).name` of Latin-1, which a child in it must report.
LATIN1 = codecs.lookup("iso8859-1").name
#: The POSIX locale, Python's UTF-8 mode off, as #1072 kept it.
POSIX_LOCALE = {"LC_ALL": "POSIX", "PYTHONUTF8": "0"}
#: A child's file name encoding and its preferred encoding, one per line.
ASK_ENCODINGS = ("import codecs, locale, sys; "
                 "print(codecs.lookup(sys.getfilesystemencoding()).name); "
                 "print(codecs.lookup(locale.getpreferredencoding(False))"
                 ".name)")
#: The child of `test_the_record_is_asked_as_written_then_as_utf8`:
#: `_recorded_path` of the record in argv[2], a JSON string. It prints one
#: line of ASCII JSON: the hex of the path's bytes, whether it is there,
#: `said`, and this locale's file name encoding.
RECORDED_PATH = r"""
import importlib.util, json, os, sys
sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location(
    "adopt_recorded_path", os.fsdecode(bytes.fromhex(sys.argv[1])))
adopter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adopter)
path, there, said = adopter._recorded_path(json.loads(sys.argv[2]))
print(json.dumps({"path": os.fsencode(path).hex(), "there": there,
                  "said": said, "encoding": sys.getfilesystemencoding()}))
"""


def charmap() -> str:
    """ISO-8859-1 as `localedef -f` reads a charmap: each byte, `/x00` to
    `/xff`, the code point of the same number."""
    return ("<code_set_name> ISO-8859-1\n<comment_char> %\n<escape_char> /\n"
            "<mb_cur_min> 1\n<mb_cur_max> 1\nCHARMAP\n"
            + "".join(f"<U{byte:04X}> /x{byte:02x}\n" for byte in range(256))
            + "END CHARMAP\n")


@pytest.fixture(scope="module")
def latin1(tmp_path_factory) -> dict:
    """What a child's environment adds to run in a Latin-1 locale built
    here: `LOCPATH`, `LC_ALL` naming it, and `PYTHONUTF8=0`. Built by
    `localedef -c`, which writes a locale whose categories other than
    `LC_CTYPE` are empty and says so (exit 1, warnings); a child started in
    it must report Latin-1 as its file name encoding and its preferred
    encoding, or every test here skips with `localedef`'s words."""
    if os.name == "nt":
        pytest.skip("a locale of one byte to a character is a POSIX idea: "
                    "Windows hands a command line to CreateProcessW as UTF-16")
    localedef = shutil.which("localedef")
    if localedef is None:
        pytest.skip("no `localedef` here to build a Latin-1 locale with")
    kit = tmp_path_factory.mktemp("latin1")
    (kit / "ISO-8859-1").write_text(charmap(), encoding="ascii")
    (kit / "latin1").write_text("LC_CTYPE\nEND LC_CTYPE\n", encoding="ascii")
    (kit / "locales").mkdir()
    built = subprocess.run(
        [localedef, "-c", "-i", str(kit / "latin1"), "-f",
         str(kit / "ISO-8859-1"), str(kit / "locales" / LATIN1_NAME)],
        capture_output=True, text=True, errors="replace",
        stdin=subprocess.DEVNULL, check=False)
    locale = {"LOCPATH": str(kit / "locales"), "LC_ALL": LATIN1_NAME,
              "PYTHONUTF8": "0"}
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(LOCALE_KEYS)}
    asked = subprocess.run([sys.executable, "-c", ASK_ENCODINGS],
                           capture_output=True, text=True, errors="replace",
                           env={**env, **locale}, stdin=subprocess.DEVNULL,
                           check=False)
    if asked.stdout.split() != [LATIN1, LATIN1]:
        words = " ".join(line for line in built.stderr.splitlines()
                         if not line.startswith("[warning]"))
        pytest.skip(f"localedef could not build a Latin-1 locale here (exit "
                    f"{built.returncode}: {words[-300:]!r}); a child in it "
                    f"reports {asked.stdout.split()}")
    return locale


def checked(plan: Path, tmp_path: Path, name: str, env: dict):
    """`check --plan <plan>` in a child in the locale `env` names, its
    output read as Latin-1, which reads every byte: a child in that locale
    writes `\\u00e9` as the one byte 0xE9, and a child under C or POSIX
    writes ASCII."""
    asked = {**env, "LANES_LANE": ""}
    return subprocess.run(
        [sys.executable, str(ADOPT), "check", "--plan", str(plan),
         "--work-dir", str(tmp_path / name), "--local-remote-dir",
         str(tmp_path / "remotes")],
        capture_output=True, encoding=LATIN1,
        env=blank_unnamed_pin_sources({**os.environ, **asked}, asked),
        stdin=subprocess.DEVNULL, check=False)


def said(proc) -> str:
    """What a child printed, stdout then stderr."""
    return proc.stdout + proc.stderr


@pytest.mark.parametrize("cloned", [False, True], ids=["given", "cloned"])
def test_a_plan_written_in_utf8_is_read_under_a_one_byte_locale(
        latin1, monkeypatch, tmp_path, cloned):
    """#1078's measurement: on 2a119f28 `plan-source-gone`, "names nothing
    that exists", under Latin-1, and, recorded as a clone `plan` made, "no
    longer exists" and `gh repo clone` asked. Now `plan ok`, exit 0, under
    Latin-1, and under C and POSIX as #1072 left them; `gh` is never
    asked."""
    _, plan, log, env = written_in_utf8_mode(monkeypatch, tmp_path, cloned)

    for name, locale in (("latin1", latin1), ("c", C_LOCALE),
                         ("posix", POSIX_LOCALE)):
        proc = checked(plan, tmp_path, f"{name}-work", {**env, **locale})

        assert proc.returncode == 0, (name, said(proc))
        assert "plan ok" in proc.stdout, name
        assert "Traceback" not in proc.stderr, name
        assert "plan-source-gone" not in said(proc), name
        assert "no longer exists" not in said(proc), name
    assert log.read_bytes() == b""


def test_where_neither_spelling_names_anything_the_words_are_as_before(
        latin1, monkeypatch, tmp_path):
    """The source moved away after `plan`: under Latin-1 neither the
    spelling as written nor the UTF-8 bytes name anything, and
    `plan-source-gone` is word for word what it was, the path named as the
    plan records it; nothing says a second spelling was asked."""
    source, plan, log, env = written_in_utf8_mode(monkeypatch, tmp_path,
                                                  False)
    local_path = str(recorded(plan)["local_path"])
    source.rename(tmp_path / "moved")

    proc = checked(plan, tmp_path, "latin1-work", {**env, **latin1})

    assert proc.returncode == 2, said(proc)
    assert ("REFUSED plan-source-gone: the plan's `source.local_path`, "
            f"{spelled(local_path)}, names nothing that exists, and the plan "
            "does not record it as a clone `plan` made (`source.cloned` is "
            "not `true`), so nothing clones it again") in proc.stderr
    assert "UTF-8" not in said(proc)
    assert "Traceback" not in proc.stderr
    assert log.read_bytes() == b""


@pytest.mark.parametrize("locale", ["latin1", "c"])
@pytest.mark.parametrize("present", ["utf8", "both", "neither"])
def test_the_record_is_asked_as_written_then_as_utf8(
        latin1, tmp_path, locale, present):
    """`_recorded_path` of `<tmp>/Thing\\u00e9`, as a plan written in UTF-8
    records it, with a directory at its UTF-8 bytes, at its Latin-1 byte as
    well, or at neither. Under Latin-1 the spelling as written (0xE9) is
    asked first, and the UTF-8 bytes (0xC3 0xA9) only where it names
    nothing; where neither is there the path is the spelling as written.
    Under C, which cannot spell the text, only the UTF-8 bytes are asked
    and `said` names them, as #1072 left it."""
    env = c_locale_or_skip()
    if locale == "latin1":
        env.update(latin1)
    base = os.fsencode(os.path.realpath(tmp_path))
    utf8 = base + b"/" + ACCENTED.encode("utf-8")
    one_byte = base + b"/" + ACCENTED.encode(LATIN1)
    for made in {"utf8": [utf8], "both": [utf8, one_byte],
                 "neither": []}[present]:
        os.mkdir(made)

    child = subprocess.run(
        [sys.executable, "-c", RECORDED_PATH, os.fsencode(ADOPT).hex(),
         json.dumps(os.fsdecode(base) + "/" + ACCENTED)],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)

    assert child.returncode == 0, child.stderr.decode("utf-8", "replace")
    answer = json.loads(child.stdout.decode("ascii"))
    first = one_byte if locale == "latin1" else utf8
    assert bytes.fromhex(answer["path"]) == (
        utf8 if present == "utf8" else first), answer
    assert answer["there"] is (present != "neither"), answer
    assert answer["said"] == ("" if locale == "latin1" else
                              f" as UTF-8 spells it (this locale's file "
                              f"names, {answer['encoding']}, cannot spell "
                              "it)"), answer


def test_the_clone_at_the_record_is_kept_under_a_one_byte_locale(
        latin1, tmp_path):
    """`_keep_the_clone_at_the_record` (#803, #918) under Latin-1, which
    spells `Thing\\u00e9` as written: the record asked only so names a path
    that is not there, so the clone this run made at the plan's UTF-8 bytes
    stayed on the list of clones to remove, #803's bug again. Asked as
    `_recorded_source` asks it, that one clone is taken off, and a clone
    made elsewhere stays."""
    env = {**c_locale_or_skip(), **latin1}
    base = Path(os.path.realpath(tmp_path))
    clone = base / ACCENTED / "source-readonly" / "Thing"
    elsewhere = base / "work" / "source-readonly" / "Thing"
    for directory in (clone, elsewhere):
        directory.mkdir(parents=True)

    child = subprocess.run(
        [sys.executable, "-c", KEEP_THE_CLONE, os.fsencode(ADOPT).hex(),
         json.dumps(str(clone)), os.fsencode(clone).hex(),
         os.fsencode(elsewhere).hex()],
        capture_output=True, env=env, stdin=subprocess.DEVNULL, check=False)

    assert child.returncode == 0, child.stderr.decode("utf-8", "replace")
    answer = json.loads(child.stdout.decode("ascii"))
    assert answer["spells"] is True, "premise: Latin-1 spells the record"
    left = [os.fsdecode(bytes.fromhex(held)) for held in answer["left"]]
    assert left == [str(elsewhere)], (
        f"the clone at the record is not taken off: {left}")
