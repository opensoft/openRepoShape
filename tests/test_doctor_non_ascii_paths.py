# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py` prints a path that is not ASCII as THAT path, in every
command it hands a reader (#785).

THE DEFECT. `ascii_text` ended in `encode("ascii", "replace")`, and both
`quote_arg` and `Row` ran it, so each character of a path that is not ASCII
printed as `?`, on every console, in the table and in `--json` alike. A
holder under `Projets/Équipe` was handed `--root '.../Projets/?quipe/...'`
and the keep line `git -C '.../?quipe/InkRouter/members/IRRS' branch NAME`;
no such directory is there, so the pasted line failed -- under a UTF-8
locale, whose terminal shows `é`, as much as under `LC_ALL=C`. A name that
is not UTF-8 at all (`\\xc9quipe`, a legacy code page) fared the same.

WHAT IT DOES NOW. `quote_arg` spells such a value as itself where the
report's encoding writes the bytes the path holds, and escapes it whole
where it does not: `$'...'` with octal escapes for `sh`, a `[char]`
expression for PowerShell. `ascii_text` replaces only what the report cannot
show. Each line is asserted here as a reader uses it: the table's bytes and
the `--json` value, pasted into bash -- `sh` on Ubuntu is dash, which has no
`$'...'` -- under a UTF-8 locale, under `LC_ALL=C`, and under `LC_ALL=C`
with Python's UTF-8 mode off, where its filesystem encoding is ASCII, for a
directory named in UTF-8 and one named in Latin-1. The NEXT is also read
with stdout in cp1252 and in ASCII, an encoding that is not the filesystem's
(review S3 on PR #792), and run in dash where the report shows the name as
itself, which is what README says dash can run.

The spellings are asserted on every OS. The runs are `WINDOWS_SKIP`: a
Windows command line is text and cannot carry the byte 0xC9 alone. No
PowerShell is run here; its spelling is read back by `powershell_value`.

THE FIXTURES ARE `test_shape_doctor`'s, imported rather than rebuilt.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, blank_unnamed_pin_sources
from test_doctor_gitmodules_not_utf8 import listed_locale
from test_doctor_legs_members_next import (
    PASTE_ENV, commit_in, detached_member, emptied_with_its_repository_kept,
)
from test_family_printed_quoting import powershell_words
from test_shape_doctor import (  # noqa: F401
    DOCTOR, FAMILY_MEMBER, FAMILY_NAME, doctor_module, holder, standard,
)

#: A byte of a name that is not UTF-8, as `surrogateescape` reads it in.
LATIN_1_E_ACUTE = chr(0xDCC9)
#: The apostrophe this repository's own prose is written with, which
#: `ascii_text` flattens, so a value holding it is always escaped.
CURLY = chr(0x2019)

#: `id: (value, encoding, spelling, bytes)` for `sh`: what `quote_arg`
#: prints for `value` to a report in `encoding`, and the bytes a shell makes
#: of that spelling.
POSIX_CASES = {
    "utf-8-shown": ("/srv/Équipe", "utf-8", "'/srv/Équipe'",
                    "/srv/Équipe".encode("utf-8")),
    "ascii-escaped": ("/srv/Équipe", "ascii", r"$'/srv/\303\211quipe'",
                      "/srv/Équipe".encode("utf-8")),
    # cp1252 holds `É`, as the byte 0xC9: not the bytes this path holds.
    "cp1252-escaped": ("/srv/Équipe", "cp1252", r"$'/srv/\303\211quipe'",
                       "/srv/Équipe".encode("utf-8")),
    "latin-1-byte": (f"/srv/{LATIN_1_E_ACUTE}quipe", "utf-8",
                     r"$'/srv/\311quipe'", b"/srv/\xc9quipe"),
    "curly-apostrophe": (f"/srv/Dana{CURLY}s work", "utf-8",
                         r"$'/srv/Dana\342\200\231s work'",
                         f"/srv/Dana{CURLY}s work".encode("utf-8")),
    "apostrophe-and-backslash": ("/srv/l'Équipe\\x", "ascii",
                                 r"$'/srv/l\047\303\211quipe\134x'",
                                 "/srv/l'Équipe\\x".encode("utf-8")),
    "outside-cp1252": ("/srv/日本", "cp1252",
                       r"$'/srv/\346\227\245\346\234\254'",
                       "/srv/日本".encode("utf-8")),
    # `é` as `os.fsdecode` reads it with an ASCII filesystem encoding: two
    # `surrogateescape` bytes, read again as the UTF-8 they spell.
    "utf-8-read-byte-by-byte": (f"/srv/caf{chr(0xDCC3)}{chr(0xDCA9)}",
                                "utf-8", "'/srv/café'",
                                "/srv/café".encode("utf-8")),
    # A surrogate `surrogateescape` never makes: escaped, never raised on.
    "stray-surrogate": (f"/srv/a{chr(0xD800)}", "utf-8",
                        r"$'/srv/a\355\240\200'", b"/srv/a\xed\xa0\x80"),
}

#: The same cases, as `pytest` parameters: the first three, or the last.
SPELLED = [pytest.param(*case[:3], id=name)
           for name, case in POSIX_CASES.items()]
SPELLED_AND_RUN = [pytest.param(*case[1:], id=name)
                   for name, case in POSIX_CASES.items()]

#: `(value, encoding, spelling)` for PowerShell, which compares no bytes:
#: a Windows path is text.
WINDOWS_CASES = [
    pytest.param("C:\\Équipe", "utf-8", "'C:\\Équipe'", id="utf-8-shown"),
    pytest.param("C:\\Équipe", "cp1252", "'C:\\Équipe'", id="cp1252-shown"),
    pytest.param("C:\\Équipe", "ascii",
                 "('C:\\' + [char]0x00C9 + 'quipe')", id="ascii-escaped"),
    pytest.param("Équipe", "ascii", "('' + [char]0x00C9 + 'quipe')",
                 id="first-operand-a-string"),
    pytest.param("C:\\日本", "cp1252",
                 "('C:\\' + [char]0x65E5 + [char]0x672C)",
                 id="outside-cp1252"),
    pytest.param(f"C:\\Dana{CURLY}s", "utf-8",
                 "('C:\\Dana' + [char]0x2019 + 's')", id="curly-apostrophe"),
    pytest.param("C:\\" + chr(0x1F600), "cp1252",
                 "('C:\\' + [char]0xD83D + [char]0xDE00)",
                 id="two-code-units"),
    pytest.param("C:\\l'É" + chr(0x201A), "utf-8",
                 "'C:\\l''É" + chr(0x201A) * 2 + "'",
                 id="quotes-doubled"),
]


@pytest.fixture(scope="module")
def module():
    return doctor_module(REPO)


@pytest.mark.parametrize(("value", "encoding", "spelling"), SPELLED)
def test_785_a_value_is_spelled_for_sh(module, value, encoding, spelling):
    assert module.quote_arg(value, "posix", encoding=encoding) == spelling


#: A legacy multibyte filesystem encoding, and a character it holds that a
#: directory may be named in UTF-8 instead: the joined character would be
#: written in that encoding, as other bytes (review M1 on PR #792).
LEGACY = [pytest.param("euc_jp", "日", id="euc-jp"),
          pytest.param("big5", "日", id="big5"),
          pytest.param("euc_kr", "€", id="euc-kr")]


@pytest.mark.parametrize("report", ["filesystem", "utf-8"])
@pytest.mark.parametrize(("filesystem", "char"), LEGACY)
def test_785_a_utf_8_name_under_a_legacy_filesystem_keeps_its_bytes(
        module, monkeypatch, report, filesystem, char):
    """The UTF-8 bytes of `char`, read in as escaped bytes under that
    filesystem encoding, stay those bytes in the table (written in that
    encoding) and in `--json` (in UTF-8): never `char` itself, whose
    `path_bytes` there are another directory's."""
    monkeypatch.setattr(sys, "getfilesystemencoding", lambda: filesystem)
    raw = char.encode("utf-8")
    value = "/srv/" + raw.decode(filesystem, "surrogateescape")
    escaped = "".join(f"\\{byte:03o}" for byte in raw)
    encoding = filesystem if report == "filesystem" else report
    assert module.quote_arg(value, "posix", encoding=encoding) == (
        f"$'/srv/{escaped}'")


@pytest.mark.parametrize(("value", "encoding", "spelling"), WINDOWS_CASES)
def test_785_a_value_is_spelled_for_powershell(module, value, encoding,
                                               spelling):
    assert module.quote_arg(value, "nt", encoding=encoding) == spelling


@pytest.mark.parametrize(("value", "encoding", "spelling"), SPELLED)
def test_785_the_rows_own_pass_leaves_a_spelling_whole(module, value,
                                                       encoding, spelling):
    """`Row.__init__` runs `ascii_text` over every command and `why`, after
    the values in it are quoted: it must find nothing in one to change."""
    spelled = module.quote_arg(value, "posix", encoding=encoding)
    assert module.ascii_text(spelled, encoding) == spelling


def powershell_value(spelling: str) -> str:
    """The value a PowerShell spelling of `quote_arg`'s stands for: one
    verbatim string, or an expression of verbatim strings and `[char]`
    code units joined by `+`. A reader of those two forms, not of
    PowerShell."""
    if not spelling.startswith("("):
        return powershell_words(spelling)[0]
    units = bytearray()
    for part in re.findall(r"'(?:[^']|'')*'|\[char\]0x[0-9A-F]{4}",
                           spelling[1:-1]):
        if part.startswith("'"):
            units += powershell_words(part)[0].encode("utf-16-le")
        else:
            units += int(part[8:], 16).to_bytes(2, "little")
    return units.decode("utf-16-le")


@pytest.mark.parametrize(("value", "encoding", "spelling"), WINDOWS_CASES)
def test_785_a_powershell_spelling_stands_for_the_value(module, value,
                                                        encoding, spelling):
    assert powershell_value(module.quote_arg(value, "nt",
                                             encoding=encoding)) == value


def test_785_a_sentence_keeps_what_the_report_can_show(module):
    assert module.ascii_text("members/café: ok", "utf-8") == (
        "members/café: ok")


@pytest.mark.parametrize(("text", "encoding", "shown"), [
    pytest.param("members/café", "ascii", "members/caf?", id="ascii"),
    pytest.param(f"caf{LATIN_1_E_ACUTE}", "utf-8", "caf?", id="not-utf-8"),
    pytest.param(f"a{chr(0x202E)}b", "utf-8", "a?b", id="bidi-control"),
    # The mark a lossy read leaves, printed as `?` since #385.
    pytest.param(f"caf{chr(0xFFFD)}", "utf-8", "caf?", id="lossy-read"),
    pytest.param(f"a {chr(0x2014)} {CURLY}b{CURLY}", "utf-8", "a -- 'b'",
                 id="typography"),
])
def test_785_a_sentence_replaces_what_the_report_cannot_show(module, text,
                                                             encoding, shown):
    assert module.ascii_text(text, encoding) == shown


@WINDOWS_SKIP
@pytest.mark.parametrize("shell", ["bash", "zsh"])
@pytest.mark.parametrize(("encoding", "spelling", "expected"),
                         SPELLED_AND_RUN)
def test_785_a_shell_turns_the_spelling_back_into_the_paths_bytes(
        shell, encoding, spelling, expected):
    """The spelling as a report in `encoding` printed it, as bytes, so the
    one that shows `É` hands the shell the bytes a terminal would; and
    `expected`, the bytes of the path it was spelled from."""
    if shutil.which(shell) is None:
        pytest.skip(f"no {shell} here")
    line = f"printf '%s\\0' {spelling}".encode(encoding)
    printed = subprocess.run([shell, "-c", line],
                             capture_output=True, check=True,
                             stdin=subprocess.DEVNULL)
    assert printed.stdout == expected + b"\0"


# --- the doctor's own lines, pasted -----------------------------------------

#: The directory a holder sits in, named in UTF-8 and in Latin-1.
PARENTS = [pytest.param("Équipe".encode("utf-8"), id="utf-8-name"),
           pytest.param(b"\xc9quipe", id="latin-1-name")]

#: The locales the doctor and the pasted line run under: a UTF-8 one, `C`
#: (where Python turns its UTF-8 mode on), and `C` with it off.
LOCALES = [pytest.param("UTF-8", {}, id="utf-8-locale"),
           pytest.param("C", {}, id="C"),
           pytest.param("C", {"PYTHONUTF8": "0"}, id="C-ascii-fs")]

#: Those, and a UTF-8 locale whose stdout is in cp1252 or in ASCII: Linux's
#: stand-in for a Windows stdout redirected in the ANSI code page, an
#: encoding that is not the filesystem's (review S3 on PR #792).
STDOUTS = [*LOCALES,
           pytest.param("UTF-8", {"PYTHONIOENCODING": "cp1252"},
                        id="cp1252-stdout"),
           pytest.param("UTF-8", {"PYTHONIOENCODING": "ascii"},
                        id="ascii-stdout")]

#: Where a line is read from: the table's bytes, or the `--json` value,
#: which a reader's UTF-8 terminal hands the shell as UTF-8.
SOURCES = ["table", "json"]

#: A keep line naming a real directory: `git -C <member> branch NAME`, or
#: `git <--git-dir=...> [<--work-tree=...>] branch NAME <commit>`.
KEEP = re.compile(rb"git (?:-C )?\S+(?: \S+)? branch NAME(?: [0-9a-f]{40})?")


def environ(codeset: str, changes: dict) -> dict:
    """`PASTE_ENV` under `codeset`, with no locale or Python encoding the
    person running the suite set, no lane and no pin-source override."""
    env = {key: value for key, value in PASTE_ENV.items()
           if not key.startswith(("LC_", "LANG", "PYTHONIO", "PYTHONUTF8"))}
    env.update(LANES_LANE="", LC_ALL=listed_locale(codeset), **changes)
    return blank_unnamed_pin_sources(env, {})


def holder_under(holder, tmp_path: Path, parent: bytes) -> Path:
    """A copy of the holder at `<tmp>/<parent>/InkRouter`, the directory
    named in `parent`'s own bytes, its member detached."""
    where = Path(os.fsdecode(os.path.join(os.fsencode(tmp_path), parent)))
    where.mkdir()
    root = where / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    detached_member(root)
    return root


def members_line(standard, root: Path, env: dict, source: str,
                 field: str) -> bytes:
    """The members row's NEXT or WHY (`field`), as the bytes a reader
    pastes: the table's line, or the `--json` value in UTF-8."""
    if source == "json":
        rows = json.loads(run_doctor(standard, root, env, "--json"))["rows"]
        row = next(row for row in rows if row["id"] == "members")
        return row[field.lower()].encode("utf-8")
    label = None
    for line in run_doctor(standard, root, env).splitlines():
        if re.match(rb"  \S", line):
            label = line.split()[1]
        elif label == b"members" and line.split()[:1] == [field.encode()]:
            return line.split(field.encode(), 1)[1].strip()
    raise AssertionError(f"no {field} on the members row")


def run_doctor(standard, root: Path, env: dict, *args: str) -> bytes:
    result = subprocess.run(
        [sys.executable, os.fsencode(standard / DOCTOR), "--root",
         os.fsencode(root), *args], capture_output=True, env=env,
        stdin=subprocess.DEVNULL, check=False)
    assert b"Traceback" not in result.stderr, result.stderr
    return result.stdout


def bash(line: bytes, env: dict, cwd: Path,
         shell: str = "bash") -> subprocess.CompletedProcess:
    """`line` pasted into bash, or `shell`, from a directory that is not
    the root."""
    cwd.mkdir(exist_ok=True)
    return subprocess.run([shell, "-c", line], cwd=str(cwd), env=env,
                          capture_output=True, check=False,
                          stdin=subprocess.DEVNULL)


def next_root(standard, holder, tmp_path: Path, parent: bytes, env: dict,
              source: str, shell: str = "bash") -> tuple[bytes, bytes]:
    """`(the --root word as `shell` reads the members row's NEXT, the root's
    own bytes)`, for a holder under `parent` whose member is detached with
    a commit on it: `printf` in place of the interpreter prints each word."""
    root = holder_under(holder, tmp_path, parent)
    commit_in(root / "members" / FAMILY_MEMBER)
    line = members_line(standard, root, env, source, "NEXT")
    words = bash(b"printf '%s\\0' " + line.split(b" ", 1)[1], env,
                 tmp_path / "away", shell).stdout.split(b"\0")
    return words[words.index(b"--root") + 1], os.fsencode(root.resolve())


@WINDOWS_SKIP
@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("state", ["detached", "emptied"])
@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize(("codeset", "changes"), LOCALES)
def test_785_a_keep_line_naming_the_path_keeps_the_commit_as_printed(
        standard, holder, tmp_path, source, state, parent, codeset,
        changes):
    """A commit on the member's detached HEAD, in its mount (`git -C`,
    #413 b) or in the repository git kept when the mount was emptied
    (`--git-dir`, #413 a): the keep line the row's WHY names keeps it on a
    branch, run as printed."""
    root = holder_under(holder, tmp_path, parent)
    mount = f"members/{FAMILY_MEMBER}"
    commit = (commit_in(root / mount) if state == "detached"
              else emptied_with_its_repository_kept(root, mount))
    env = environ(codeset, changes)
    keeps = [line for line in KEEP.findall(
        members_line(standard, root, env, source, "WHY"))
        if b"LEG" not in line and b"REPO" not in line]
    assert len(keeps) == 1, keeps
    kept = bash(keeps[0].replace(b"NAME", b"kept"), env, tmp_path / "away")
    assert kept.returncode == 0, kept.stderr
    branch = subprocess.run(
        ["git", "--git-dir", os.fsencode(root / ".git" / "modules" / mount),
         "rev-parse", "--verify", "-q", "refs/heads/kept"],
        capture_output=True, check=False)
    assert branch.stdout.decode().strip() == commit


@WINDOWS_SKIP
@pytest.mark.parametrize("source", SOURCES)
@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize(("codeset", "changes"), STDOUTS)
def test_785_the_members_next_names_the_real_root(standard, holder, tmp_path,
                                                  source, parent, codeset,
                                                  changes):
    """The NEXT's `--root`, as bash reads it, is the root's own bytes, and
    with stdout in cp1252 or ASCII too: a table that printed `É` in
    cp1252 would hand the shell 0xC9, which is not the byte this path
    holds."""
    word, root = next_root(standard, holder, tmp_path, parent,
                           environ(codeset, changes), source)
    assert word == root


#: The cells dash can run, which are the ones that show a UTF-8 name as
#: itself: the table under a UTF-8 locale and under `C`, where Python's UTF-8
#: mode is on, and `--json` under every stdout (review N1 on PR #792, both
#: rounds).
DASH_CELLS = [*(pytest.param("table", *cell.values, id=f"table-{cell.id}")
                for cell in LOCALES[:2]),
              *(pytest.param("json", *cell.values, id=f"json-{cell.id}")
                for cell in STDOUTS)]


@WINDOWS_SKIP
@pytest.mark.parametrize(("source", "codeset", "changes"), DASH_CELLS)
def test_785_dash_runs_a_next_that_shows_the_name_as_itself(
        standard, holder, tmp_path, source, codeset, changes):
    """dash has no `$'...'`, as README says, so the lines it can run are
    the ones that show a name as itself: a UTF-8 name, in the table where
    stdout can show it, and in `--json` whatever stdout is."""
    if shutil.which("dash") is None:
        pytest.skip("no dash here")
    word, root = next_root(standard, holder, tmp_path,
                           "Équipe".encode("utf-8"),
                           environ(codeset, changes), source, "dash")
    assert word == root


@WINDOWS_SKIP
@pytest.mark.parametrize(("codeset", "changes"), STDOUTS)
def test_785_json_holds_a_utf_8_name_as_itself_whatever_stdout_holds(
        standard, holder, tmp_path, codeset, changes):
    """`--json` is written for a reader who decodes it, so its `next`
    holds a UTF-8 name as itself whatever stdout's encoding is, and under
    `LC_ALL=C` with Python's UTF-8 mode off, where the name is read in as
    bytes (review S2 on PR #792)."""
    root = holder_under(holder, tmp_path, "Équipe".encode("utf-8"))
    commit_in(root / "members" / FAMILY_MEMBER)
    line = members_line(standard, root, environ(codeset, changes), "json",
                        "NEXT")
    assert b"--root '" + os.fsencode(root.resolve()) + b"'" in line


@WINDOWS_SKIP
@pytest.mark.parametrize("parent", PARENTS)
@pytest.mark.parametrize(("codeset", "changes"), LOCALES)
def test_785_the_members_next_runs_as_printed_and_cures_the_row(
        standard, holder, tmp_path, parent, codeset, changes):
    """The holder's own bootstrap, pasted from the table, brings the
    detached member back to its pin, and the row is asked again."""
    root = holder_under(holder, tmp_path, parent)
    commit_in(root / "members" / FAMILY_MEMBER)
    env = environ(codeset, changes)
    result = bash(members_line(standard, root, env, "table", "NEXT"), env,
                  tmp_path / "away")
    assert result.returncode == 0, result.stdout + result.stderr
    rows = json.loads(run_doctor(standard, root, env, "--json"))["rows"]
    assert next(row for row in rows if row["id"] == "members")[
        "status"] == "ok"
