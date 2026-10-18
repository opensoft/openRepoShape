# SPDX-License-Identifier: Apache-2.0
"""`shape-doctor.py`'s `members` row reads `.gitmodules` as bytes (#432).

THE DEFECT. For a family holder the `members` row asks where each member is
mounted from, and the answer is the member's `url` in the holder's
`.gitmodules`, read by `submodule_config` through `git_out`, which decodes
strictly. git keeps a url as the bytes it was given, so a member mounted
from a directory named in a legacy code page (`caf\\xe9`), or a hand-edited
`.gitmodules`, has one that is not UTF-8, and the strict decode raised a
`UnicodeDecodeError`. It is a `ValueError`, neither a `Refusal` nor an
`OSError`, which are the only two the `except` beside it names and the only
two `run_checks` catches. So `--root` ended in a traceback, exit 1 -- also the
code of a finding, so a script could not tell this crash from `INVALID` --
with no verdict and no rows.

WHAT IT DOES NOW. The bytes are read and the one that is not UTF-8 is
replaced, as `siblings.py::submodule_urls` reads the same file for `make
siblings` and as `origin_url` reads a remote since #385. The row says what
it found, quoting the url with the replacement character, and the run
reaches the verdict a holder with an ASCII url gets.

AND THE WHOLE FILE IS READ AS GIT READS IT (#668). `submodule_config` split
git's plain `--get-regexp` listing at the first space and at every line break
`str.splitlines` knows, and a UTF-8 locale kept that regexp from matching a
byte that is not UTF-8. So a section named `members/My IRRS`, a url holding
NEL or U+2028, or a section named in Latin-1 gave the doctor no url or a url
cut short, where git and `make siblings` read the whole one, and the
member's clone beside the holder was called a stranger. `gitmodules_entry`
had the Latin-1 half. Both now read `git config -z --list`, and the corpus
at the end asks each case the same four questions.

THE FIXTURES ARE `test_shape_doctor`'s, imported rather than rebuilt: a
holder made any other way would be a different one. The `.gitmodules` is
written as BYTES (a Windows command line is text), with forward slashes so
git's escaping of a backslash never changes what is compared.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess

from pathlib import Path

import pytest

from conftest import git, run_script
from test_shape_advisory import with_origin
from test_shape_doctor import (  # noqa: F401
    DOCTOR, FAMILY_MEMBER, FAMILY_NAME, commit_all, doctor, doctor_module,
    holder, member_beside, rows_of, siblings, standard,
)

SECTION = f"members/{FAMILY_MEMBER}"
REPOSITORY = f"{FAMILY_NAME}/{FAMILY_MEMBER}"

#: The directory the member's mount url runs through, in #432's own three
#: rows: the harness's own bare repository (the control), a directory named
#: in UTF-8 (`café`), and one named in Latin-1 (`caf\xe9`), which is not
#: UTF-8. `None` leaves `.gitmodules` as `family.py add` wrote it.
DIRECTORIES = [
    pytest.param(None, id="ascii-control"),
    pytest.param("café".encode("utf-8"), id="utf-8"),
    pytest.param(b"caf\xe9", id="not-utf-8"),
]


def holder_copy(holder: dict, tmp_path: Path) -> Path:
    """A private copy of the session's holder, in a folder of its own."""
    base = tmp_path / "fam"
    base.mkdir()
    root = base / FAMILY_NAME
    shutil.copytree(holder["root"], root, symlinks=True)
    return root


def mount_through(holder: dict, root: Path, directory: bytes | None) -> bytes:
    """`root`'s member mounted from `<remotes>/<directory>/IRRS.git`, and
    that url as the BYTES now in `.gitmodules`.

    The file's `url` line is rewritten as bytes and committed, so the
    working tree is clean as a person's would be. Skipped where git does not
    hand the value back as written. No directory is made: the doctor
    fetches nothing, so the url need not lead anywhere.
    """
    remotes = (holder["base"] / "remotes").as_posix().encode("utf-8")
    if directory is None:
        return remotes + f"/{FAMILY_MEMBER}.git".encode("ascii")
    url = remotes + b"/" + directory + f"/{FAMILY_MEMBER}.git".encode("ascii")
    config = root / ".gitmodules"
    rewritten, count = re.subn(rb"(?m)^([ \t]*url[ \t]*=[ \t]*)[^\r\n]*",
                               lambda found: found.group(1) + url,
                               config.read_bytes())
    assert count == 1, config.read_bytes()
    config.write_bytes(rewritten)
    read = subprocess.run(["git", "config", "-f", str(config), "--get",
                           f"submodule.{SECTION}.url"],
                          capture_output=True, check=False)
    if read.stdout.rstrip(b"\r\n") != url:
        pytest.skip(f"`git config` here reads the url as {read.stdout!r}, "
                    f"not {url!r}")
    commit_all(root, "Mount the member from another directory")
    return url


def members_line(text: str) -> str:
    """The `members` row of a printed report, as one line."""
    return next(line for line in text.splitlines()
                if line.split()[1:2] == ["members"])


@pytest.mark.parametrize("directory", DIRECTORIES)
def test_the_run_reaches_a_verdict_whatever_bytes_the_mount_url_holds(
        standard, holder, tmp_path, directory):
    """#432's table, row by row, through `--json` and the printed report.

    On the base the third row ended in `UnicodeDecodeError` out of
    `submodule_config`, exit 1, and no verdict. Now every row is
    `COMPLIANT`, exit 0, the `members` row names the member it found, and
    the url it quotes is the one in `.gitmodules` with the byte replaced
    where it is not UTF-8. The other two rows are the control: this is
    not a test that passes by refusing every url.
    """
    root = holder_copy(holder, tmp_path)
    url = mount_through(holder, root, directory)
    quoted = url.decode("utf-8", "replace")

    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    payload = json.loads(result.stdout)
    assert (payload["verdict"], result.returncode) == ("COMPLIANT", 0), \
        payload
    row = rows_of(result)["members"]
    assert row["status"] == "ok", row
    entry = row["detail"]["members"][0]
    assert entry["project"] == FAMILY_MEMBER, entry
    assert entry["path"] == SECTION, entry
    assert entry["mounted_from"].replace("\\", "/") == quoted, entry
    assert FAMILY_MEMBER in row["reason"], row["reason"]

    text = doctor(standard, root)
    assert "Traceback" not in text.stderr, text.stderr
    assert text.returncode == 0, text.stdout + text.stderr
    assert text.stdout.rstrip().endswith("COMPLIANT   (exit 0)"), text.stdout
    assert SECTION in members_line(text.stdout), text.stdout


@pytest.mark.parametrize("directory", DIRECTORIES)
def test_submodule_config_keeps_the_url_as_text_it_can_compare(
        standard, holder, tmp_path, siblings, directory):
    """The unit #432 names: `submodule_config(root)` returns the section.

    The url is kept, as the string `make siblings` reads out of the same
    file (`siblings.submodule_urls`), so the two tools hold one answer
    about where the member is mounted from, and it is text the row can
    compare: a byte that is not UTF-8 is U+FFFD, never dropped, and never
    a lone surrogate no UTF-8 stream can write.
    """
    root = holder_copy(holder, tmp_path)
    url = mount_through(holder, root, directory)
    quoted = url.decode("utf-8", "replace")

    config = doctor_module(standard).submodule_config(root)
    assert list(config) == [SECTION], config
    assert config[SECTION]["path"] == SECTION, config
    assert config[SECTION]["url"].replace("\\", "/") == quoted, config
    assert ("�" in config[SECTION]["url"]) is (directory == b"caf\xe9")
    assert config[SECTION]["url"] == siblings.submodule_urls(root)[SECTION]
    assert config[SECTION]["url"].encode("utf-8")


def test_a_clone_made_from_the_same_bytes_is_the_working_clone(
        standard, holder, tmp_path, siblings):
    """THE ROW AGREES WITH `make siblings` ABOUT ONE DIRECTORY (#146).

    A clone beside the holder whose own `origin` is the same bytes as the
    member's mount url reads back as the same string through `origin_url`
    and through `submodule_config`, so the mount comparison accepts it, as
    `verify_sibling` does. A reading that dropped the url and fell back to
    the `repository:` guess would call this clone a stranger, and the two
    tools would disagree about the directory.
    """
    root, sibling = member_beside(holder, tmp_path)
    url = mount_through(holder, root, b"caf\xe9")
    git("remote", "remove", "origin", cwd=sibling)
    with_origin(sibling, url)

    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    assert (json.loads(result.stdout)["verdict"], result.returncode) == \
        ("COMPLIANT", 0), result.stdout
    entry = rows_of(result)["members"]["detail"]["members"][0]
    assert entry["working_clone"] == sibling.as_posix(), entry
    assert entry["other_origin"] is None, entry

    member = siblings.Sibling(FAMILY_MEMBER, sibling)
    assert siblings.verify_sibling(
        {"project": FAMILY_MEMBER, "id": siblings.project_id(sibling),
         "repository": REPOSITORY},
        sibling, siblings.submodule_urls(root)[SECTION], REPOSITORY,
        member) is True, member.finding


def test_a_clone_from_another_remote_is_still_a_stranger_beside_such_a_mount(
        standard, holder, tmp_path, siblings):
    """And the other direction, so the test above cannot pass by accepting
    every clone: the member's own clone, at the harness's real remote, is
    not a clone of the directory the holder now mounts it from, and `make
    siblings` calls the same directory `WRONG ORIGIN`.

    The row reports it and never refuses it, as for any stranger (#146): the
    verdict is the one a holder with no clone beside it gets, and the printed
    row says which origin it found.
    """
    root, sibling = member_beside(holder, tmp_path)
    mount_through(holder, root, b"caf\xe9")
    origin = subprocess.run(["git", "remote", "get-url", "origin"],
                            cwd=str(sibling), capture_output=True, text=True,
                            check=True).stdout.strip()

    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    assert (json.loads(result.stdout)["verdict"], result.returncode) == \
        ("COMPLIANT", 0), result.stdout
    row = rows_of(result)["members"]
    entry = row["detail"]["members"][0]
    assert entry["working_clone"] is None, entry
    assert entry["other_origin"] == origin, entry
    assert row["status"] == "ok", row
    assert f"{FAMILY_MEMBER}: {sibling} is a clone of {origin}" in \
        row["reason"], row["reason"]

    member = siblings.Sibling(FAMILY_MEMBER, sibling)
    assert siblings.verify_sibling(
        {"project": FAMILY_MEMBER, "id": siblings.project_id(sibling),
         "repository": REPOSITORY},
        sibling, siblings.submodule_urls(root)[SECTION], REPOSITORY,
        member) is False
    assert member.state == "WRONG ORIGIN", member.state

    # The url the holder mounts the member from is quoted in the printed
    # row, with the replacement printed as `?` (#385), on an ASCII console
    # as on any other.
    for env in ({}, {"PYTHONIOENCODING": "ascii"}):
        text = run_script(standard / DOCTOR, "--root", str(root), env=env)
        assert "Traceback" not in text.stderr, text.stderr
        assert text.returncode == 0, text.stdout + text.stderr
        assert "caf?/IRRS.git, so it is not counted as its working clone" \
            in members_line(text.stdout), text.stdout


# --- #668: a section name and a url git reads whole --------------------------

#: Section NAMES, as the bytes between the header's quotes, each holding a
#: character a reading of git's listing has cut at: a space (the doctor's
#: old split), a dot, a quote (escaped in the header) and an `=`.
NAMES = [
    pytest.param(b"members/My IRRS", id="space"),
    pytest.param(b"members/IRRS.v2", id="dot"),
    pytest.param(b'members/\\"IRRS\\"', id="quote"),
    pytest.param(b"members/My=IRRS", id="equals"),
]

#: A url through a directory holding each line break `str.splitlines` knows
#: besides `\n` and `\r`, all of which git keeps in a value: VT, FF, FS, GS,
#: RS, NEL, U+2028 and U+2029, in UTF-8.
BREAKS = [pytest.param(f"caf{char}e".encode("utf-8"),
                       id=f"U+{ord(char):04X}")
          for char in "\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029"]


def name_section(root: Path, written: bytes) -> bytes:
    """`root`'s member section renamed, `written` between its header's
    quotes and committed, and the name git reads it under: `written` with a
    quote's escape read."""
    config = root / ".gitmodules"
    header = f'[submodule "{SECTION}"]'.encode("ascii")
    before = config.read_bytes()
    assert before.count(header) == 1, before
    config.write_bytes(before.replace(header,
                                      b'[submodule "' + written + b'"]'))
    commit_all(root, "Name the member's section otherwise")
    return written.replace(b'\\"', b'"')


def gits_url(root: Path, name: bytes) -> str:
    """The url git reads for the section NAMED `name`, asked by its exact
    key as `git submodule` asks, and decoded as the doctor decodes one."""
    read = subprocess.run(["git", "config", "--file", ".gitmodules", "--get",
                           b"submodule." + name + b".url"],
                          cwd=str(root), capture_output=True, check=False)
    assert read.returncode == 0, read.stderr
    return read.stdout.rstrip(b"\r\n").decode("utf-8", "replace")


def assert_read_as_git_reads(standard: Path, root: Path, sibling: Path,
                             name: bytes) -> None:
    """#668's four questions of a holder whose member section is NAMED
    `name`, with a clone of that section's url beside it: the doctor mounts
    the member from the url git reads, makes up no section, finds the url
    in the section git finds it in, and calls the clone the member's working
    clone, as `make siblings` does. The section's name comes back as git's
    own bytes, which is how it is handed to git again (#732)."""
    module = doctor_module(standard)
    url = gits_url(root, name)
    assert module.mounted_from(root, SECTION, REPOSITORY) == url
    assert "" not in module.submodule_config(root)
    assert module.gitmodules_entry(root, SECTION) == (
        name.decode("utf-8", "surrogateescape"), url)
    result = doctor(standard, root, "--json")
    assert "Traceback" not in result.stderr, result.stderr
    entry = rows_of(result)["members"]["detail"]["members"][0]
    assert entry["working_clone"] == sibling.as_posix(), entry


@pytest.mark.parametrize("written", NAMES)
def test_a_section_name_git_reads_whole_is_read_whole(standard, holder,
                                                      tmp_path, written):
    """A section NAMED with a space was split at it: the doctor read no url
    for the member, mounted it from the `repository:` guess, and called its
    clone a stranger, where `make siblings` fetches into it."""
    root, sibling = member_beside(holder, tmp_path)
    assert_read_as_git_reads(standard, root, sibling,
                             name_section(root, written))


@pytest.mark.parametrize("directory", BREAKS)
def test_a_url_holding_a_line_break_git_keeps_is_read_whole(
        standard, holder, tmp_path, directory):
    """A url holding a line break git keeps was cut short at it, and the
    rest made up a section named `''`."""
    root, sibling = member_beside(holder, tmp_path)
    url = mount_through(holder, root, directory)
    git("remote", "remove", "origin", cwd=sibling)
    with_origin(sibling, url)
    assert_read_as_git_reads(standard, root, sibling, SECTION.encode())


def listed_locale(codeset: str) -> str:
    """`C`, or for `UTF-8` any UTF-8 locale `locale -a` lists (`C.UTF-8`
    first where it is one), so the test runs wherever one is installed. The
    test is skipped where `locale -a` lists none."""
    try:
        listed = subprocess.run(["locale", "-a"], capture_output=True,
                                text=True, check=False).stdout.split()
    except OSError:
        pytest.skip("no `locale` here to list the locales")
    if codeset == "C":
        found = [name for name in listed if name == "C"]
    else:
        found = sorted((name for name in listed
                        if name.lower().replace("-", "").endswith(".utf8")),
                       key=lambda name: not name.lower().startswith("c."))
    if not found:
        pytest.skip(f"`locale -a` lists no {codeset} locale here")
    return found[0]


@pytest.mark.parametrize("codeset", ["UTF-8", "C"])
def test_a_section_name_in_latin_1_is_read_under_either_locale(
        standard, holder, tmp_path, monkeypatch, codeset):
    """A section NAMED in Latin-1 was read under `LC_ALL=C` and not under a
    UTF-8 locale, where the regexp matched no byte that is not UTF-8: no
    url, and the member's clone a stranger. Skipped on Windows, whose
    command line is text and cannot carry the byte to `gits_url`."""
    if os.name == "nt":
        pytest.skip("a Windows command line cannot carry the byte 0xE9")
    monkeypatch.setenv("LC_ALL", listed_locale(codeset))
    root, sibling = member_beside(holder, tmp_path)
    assert_read_as_git_reads(standard, root, sibling,
                             name_section(root, b"members/caf\xe9"))


def test_of_two_sections_giving_the_mount_the_last_is_read(
        standard, holder, tmp_path, siblings):
    """Two sections give the member's path, and git, `gitmodules_entry` and
    `make siblings` all take the LAST, as git reads the file. `mounted_from`
    took the first, and called the clone of the url git fetches from a
    stranger (#668)."""
    root, sibling = member_beside(holder, tmp_path)
    config = root / ".gitmodules"
    remotes = (holder["base"] / "remotes").as_posix().encode("utf-8")
    config.write_bytes(b'[submodule "members/Old"]\n\tpath = '
                       + SECTION.encode() + b"\n\turl = " + remotes
                       + b"/Old.git\n" + config.read_bytes())
    commit_all(root, "Give the member's path an earlier section too")
    assert_read_as_git_reads(standard, root, sibling, SECTION.encode())
    assert siblings.submodule_urls(root)[SECTION] == gits_url(
        root, SECTION.encode())
