# SPDX-License-Identifier: Apache-2.0
"""`--local-remote-dir` is asked, before anything exists, whether the clone URL
it makes is text a file can hold (#433).

Under `--local-remote-dir` the clone URL of a new repository is the bare
repository's own path on disk. `scaffold-project.py` renders it as `CLONE_URL`
and `ASSEMBLY_CLONE_URL` into the READMEs of the assembly root and of each leg,
and `scripts/family.py init` renders the holder's into the holder's README, all
through `write_lf`, which encodes strictly. A directory whose name is not UTF-8
(a path under a directory named in a legacy code page) reaches `sys.argv` as a
string with a lone surrogate, so on main:

  * the scaffold ended in `UnicodeEncodeError`, exit 1, after all three bare
    repositories existed and the work directory was half made, and `family.py
    init` the same after `<Family>.git` existed and the family folder was made;
  * `--dry-run` exited 0 and said nothing;
  * a line break, a control character or a bidi override in the path
    scaffolded, exit 0, and was written into the README raw.

Now each is refused, before a work directory, a folder or a remote exists and
under `--dry-run` alike: the scaffold as `scaffold-unwritable-value` and the
holder as `family-unwritable-value`, in the words `adopt-project.py` uses for
the same case (#255, `adopt-unwritable-value`). The question is
`shape_materialize.unwritable_reason`, the one all three ask. A directory
whose name is text, accented or not, still scaffolds and still creates a
holder.

NO NETWORK AND NO GITHUB: each tool is run in this process under a guard that
fails the test if any process is started (the refusal must come before the
first `git` or `gh`), or as a child into local bare repositories, which never
calls `gh`. A directory name that is not UTF-8 is made from BYTES, so the test
skips where the disk cannot hold one (macOS and Windows name their files in
UTF-8 and UTF-16). Every invisible character in this file is spelled as an
escape: a reader cannot see one typed raw, and a raw bidi control reorders the
line it is on.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ORG, SCAFFOLD, blank_unnamed_pin_sources,
                      skip_where_a_name_cannot_be_not_utf_8)
# Fixtures of the #282 file, on the harness this one shares with it: the
# scaffold loaded as a module, and the guard that no process is started.
from test_scaffold_free_text_values import (  # noqa: F401 - fixtures
    ProcessStarted, no_process, scaffold)
from test_family_init_values import FAMILY, family_module

PROJECT = "Atlas"
HOLDER = "Contoso"

LINE_BREAK = "it holds a line break, and it is written as one line"
NOT_UTF8 = "it holds a byte that is not UTF-8"
CONTROL = "it holds a control character"
BIDI = ("it holds a bidirectional control (an embedding, override or "
        "isolate), which shows the rest of the line in another order than "
        "it is written")

#: `(id, the directory's name as bytes, the reason `unwritable_reason` gives)`.
#: `caf\xe9` is the issue's own: `cafe` with the byte 0xE9 that Latin-1 writes
#: for an e with an acute accent and UTF-8 does not.
BAD_DIRECTORIES = [
    ("not-utf8", b"caf\xe9", NOT_UTF8),
    ("line-feed", b"line\nbreak", LINE_BREAK),
    ("escape", b"a\x1bb", CONTROL),
    ("bidi-override", "\u202eevil".encode("utf-8"), BIDI),
]
BAD_IDS = [row[0] for row in BAD_DIRECTORIES]

#: What the refusal tells a person to do, which is fixed text and is the same
#: in every case: the way out is another directory, or GitHub. Since #693 it
#: says that the URL is the RESOLVED path, so that a path typed as text that
#: leads to one that is not is told where the fault is, and it names a lone
#: surrogate among the reasons, as #282's remedy does.
WHY_IT_IS_REFUSED = (
    "a byte that is not UTF-8 in the path (a directory named in a legacy "
    "code page), or a lone surrogate, cannot be written at all, a line break "
    "or a control character would break or garble the line it is written "
    "into, and a bidirectional embedding, override or isolate control would "
    "show the rest of that line in another order than it is written.")
THE_RESOLVED_PATH = (
    "The clone URL is the path --local-remote-dir resolves to, so where the "
    "path given is text and the URL named above is not, the fault is in what "
    "it leads through: a symbolic link on it whose target is not text, or, "
    "for a relative path, the directory it was given from. Rename or replace "
    "the directory whose name is not text, or pass a path that does not lead "
    "through it; renaming a link changes nothing. ")
#: How a README prints the clone URL since #693: one word of a POSIX shell,
#: in quotes where one is needed, an apostrophe the only character written as
#: something else.
QUOTED_ONE_WORD = ("the clone URL in a `git clone` line, in quotes where a "
                   "shell needs them, every character but an apostrophe "
                   "written as itself: ")
SCAFFOLD_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Pass a --local-remote-dir whose path is one line of UTF-8 text with no "
    "control character in it, a directory renamed or made anew, and run "
    "again; or scaffold against GitHub, without --local-remote-dir, where "
    "the clone URL is `https://github.com/<org>/<name>.git`. "
    + THE_RESOLVED_PATH + "The READMEs print " + QUOTED_ONE_WORD
    + WHY_IT_IS_REFUSED)
FAMILY_REMEDIATION = (
    "Remediation: nothing was created, and `--dry-run` refuses the same. "
    "Pass a --local-remote-dir whose path is one line of UTF-8 text with no "
    "control character in it, a directory renamed or made anew, and run "
    "again; or run `init` against GitHub, without --local-remote-dir, where "
    "the clone URL is `https://github.com/<org>/<Family>.git`. "
    + THE_RESOLVED_PATH + "The holder's `README.md` prints "
    + QUOTED_ONE_WORD + WHY_IT_IS_REFUSED)


@pytest.fixture
def only_the_branch_question(monkeypatch):
    """`init` asks git whether `--tracking-branch` names a branch (#283)
    before it asks about the clone URL, so one process, `git check-ref-format`,
    runs first. While this holds, any other process (`git init`, `git clone`,
    `gh`, `git rev-parse`) fails the test and names it, so a refusal that
    passes came before the holder's repository, its folder or any call to
    GitHub."""
    real = subprocess.Popen

    def guarded(args, *rest, **options):
        if "check-ref-format" not in args:
            raise ProcessStarted(f"a process was started: {args!r}")
        return real(args, *rest, **options)
    monkeypatch.setattr(subprocess, "Popen", guarded)


def scaffold_refusal(url: str, reason: str) -> str:
    """The whole of what the scaffold prints to stderr, for the URL it made."""
    return (
        "REFUSED scaffold-unwritable-value: under --local-remote-dir the "
        "assembly root's clone URL is the bare repository's own path, "
        f"{url!r}, which the scaffold writes into the `README.md` of the "
        f"assembly root and of each leg, and {reason}.\n"
        f"{SCAFFOLD_REMEDIATION}\n")


def family_refusal(url: str, reason: str) -> str:
    """The whole of what `family.py init` prints to stderr."""
    return (
        "REFUSED family-unwritable-value: under --local-remote-dir the "
        "holder's clone URL is the bare repository's own path, "
        f"{url!r}, which `init` writes into the holder's `README.md`, and "
        f"{reason}.\n"
        f"{FAMILY_REMEDIATION}\n")


def skip_where_this_system_cannot_name(tmp_path: Path, raw: bytes) -> None:
    """Skip where `tmp_path/<raw>` cannot be made on this system. Two
    questions, each asked only of the names it is about:

    - a name that is not UTF-8 goes to `skip_where_a_name_cannot_be_not_utf_8`,
      which skips on the two answers that mean "this system cannot carry
      it" (Windows names its files in UTF-16, and macOS answers EILSEQ) and
      raises any other error of the disk;
    - a control character, 0x00 to 0x1F, is refused by Windows in any name,
      and a name that holds one is skipped there.

    Nothing else is skipped: U+202E, which NTFS holds, is a name Windows
    makes as Linux does (#757; reasoned, no Windows run: CI is Linux only).
    `tests/test_non_utf8_name_callers.py` holds the answers by emulation."""
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    if os.name == "nt" and any(byte < 0x20 for byte in raw):
        pytest.skip("Windows refuses a control character in a file name")


def directory_named(tmp_path: Path, raw: bytes) -> Path:
    """`tmp_path/<raw>` made from BYTES, empty; the test is skipped where this
    system cannot hold such a name, and fails on any other error of the disk."""
    skip_where_this_system_cannot_name(tmp_path, raw)
    made = os.fsencode(tmp_path) + os.fsencode(os.sep) + raw
    os.mkdir(made)
    path = Path(os.fsdecode(made))
    assert path.is_dir()
    assert os.listdir(path) == []
    return path


def assert_nothing_was_made(remote_dir: Path, *absent: Path) -> None:
    """The directory the person named is as they made it, empty, and nothing
    else a run makes (the work directory, the family folder) exists."""
    assert os.listdir(remote_dir) == [], "a remote was created"
    for made in absent:
        assert not made.exists(), f"{made.name} was made"


def scaffold_argv(remote_dir, work: Path, *, dry_run: bool) -> list[str]:
    return ["--org", ORG, "--project", PROJECT, "--elected-by", "Test Human",
            "--elected-on", "2026-09-02", "--local-remote-dir",
            str(remote_dir), "--work-dir", str(work),
            *(["--dry-run"] if dry_run else [])]


def family_argv(remote_dir, into: Path, *, dry_run: bool) -> list[str]:
    return ["init", "--org", ORG, "--family", HOLDER, "--created-by", "T H",
            "--created-on", "2026-09-02", "--local-remote-dir",
            str(remote_dir), "--into", str(into),
            *(["--dry-run"] if dry_run else [])]


# --- the scaffold, before anything exists and under `--dry-run` alike -------

@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("label, raw, reason", BAD_DIRECTORIES, ids=BAD_IDS)
def test_a_scaffold_into_a_directory_no_file_can_name_is_refused(
        scaffold, no_process, capsys, tmp_path, label, raw, reason, dry_run):
    """The issue's row, `--local-remote-dir <dir>/caf<e9>`, and the other
    paths `unwritable_reason` refuses. On main the real run made all three
    bare repositories and half a work directory before `write_lf` raised, and
    `--dry-run` exited 0. The refusal names `--local-remote-dir`, the clone
    URL as Python spells it, where it is written and why it cannot be, and
    nothing was printed to stdout (the plan is never reached)."""
    bad = directory_named(tmp_path, raw)
    work = tmp_path / "work"
    code = scaffold.main(scaffold_argv(bad, work, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == scaffold_refusal(str(bad.resolve() / f"{PROJECT}.git"),
                                   reason)
    assert_nothing_was_made(bad, work)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_a_relative_directory_under_a_path_no_file_can_name_is_refused(
        scaffold, no_process, capsys, tmp_path, monkeypatch, dry_run):
    """The URL is the RESOLVED path, so `--local-remote-dir rehearsal` run
    from a directory named in a legacy code page is refused too, naming the
    URL that would have been written and not the flag as typed."""
    bad = directory_named(tmp_path, b"caf\xe9")
    monkeypatch.chdir(bad)
    work = tmp_path / "work"
    code = scaffold.main(scaffold_argv("rehearsal", work, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == scaffold_refusal(
        str(bad.resolve() / "rehearsal" / f"{PROJECT}.git"), NOT_UTF8)
    assert_nothing_was_made(bad, work)
    assert not (bad / "rehearsal").exists()


def test_the_scaffold_asks_only_a_local_url(scaffold):
    """Against GitHub the clone URL is `https://github.com/<org>/<name>.git`,
    ASCII by construction, so there is nothing to ask of it."""
    assert scaffold._refuse_an_unwritable_clone_url(
        False, f"https://github.com/{ORG}/{PROJECT}.git") is None


# --- the holder, before anything exists and under `--dry-run` alike ---------

@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("label, raw, reason", BAD_DIRECTORIES, ids=BAD_IDS)
def test_a_family_into_a_directory_no_file_can_name_is_refused(
        only_the_branch_question, capsys, tmp_path, label, raw, reason,
        dry_run):
    """The issue's second command. On main `init` made `Contoso.git` and the
    family folder before `write_lf` raised, and `--dry-run` exited 0."""
    bad = directory_named(tmp_path, raw)
    into = tmp_path / "into"
    code = family_module().main(family_argv(bad, into, dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == family_refusal(str(bad.resolve() / f"{HOLDER}.git"), reason)
    assert_nothing_was_made(bad, into)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_a_relative_family_directory_under_such_a_path_is_refused(
        only_the_branch_question, capsys, tmp_path, monkeypatch, dry_run):
    """`family.py init --local-remote-dir rehearsal` from such a directory."""
    bad = directory_named(tmp_path, b"caf\xe9")
    monkeypatch.chdir(bad)
    into = tmp_path / "into"
    code = family_module().main(family_argv("rehearsal", into,
                                            dry_run=dry_run))
    out, err = capsys.readouterr()
    assert (code, out) == (2, ""), err
    assert err == family_refusal(
        str(bad.resolve() / "rehearsal" / f"{HOLDER}.git"), NOT_UTF8)
    assert_nothing_was_made(bad, into)
    assert not (bad / "rehearsal").exists()


def test_the_family_asks_only_a_local_url():
    assert family_module()._refuse_an_unwritable_clone_url(
        False, f"https://github.com/{ORG}/{HOLDER}.git") is None


# --- end to end, as the issue ran them --------------------------------------

def child(script: Path, *args: str) -> tuple[int, str, str]:
    """A tool as a child process, answered in BYTES and read with
    `backslashreplace`: on main its plan carries the byte that is not UTF-8,
    which is not text to decode, and the assertion should name the traceback
    and not a decode."""
    env = blank_unnamed_pin_sources({**os.environ, "LANES_LANE": ""}, {})
    for key, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                       ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                       ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                       ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")):
        env.setdefault(key, value)
    done = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)
    def shown(stream: bytes) -> str:
        return stream.replace(b"\r\n", b"\n").decode("utf-8",
                                                     "backslashreplace")
    return done.returncode, shown(done.stdout), shown(done.stderr)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_the_scaffold_as_a_person_runs_it_creates_nothing_and_raises_nothing(
        tmp_path, dry_run):
    """The issue's first command, as a child process whose argv carries the
    byte: exit 2 where main exited 1 with a `UnicodeEncodeError` traceback
    (and 0 under `--dry-run`), and the three remotes, which the real run on
    main had made, are not there."""
    bad = directory_named(tmp_path, b"caf\xe9")
    work = tmp_path / "work"
    code, out, err = child(SCAFFOLD, *scaffold_argv(bad, work,
                                                    dry_run=dry_run))
    assert "Traceback" not in err, err
    assert (code, out) == (2, ""), err
    assert err == scaffold_refusal(str(bad.resolve() / f"{PROJECT}.git"),
                                   NOT_UTF8)
    assert_nothing_was_made(bad, work)


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
def test_a_family_as_a_person_runs_it_creates_nothing_and_raises_nothing(
        tmp_path, dry_run):
    """The issue's second command, as a child process."""
    bad = directory_named(tmp_path, b"caf\xe9")
    into = tmp_path / "into"
    code, out, err = child(FAMILY, *family_argv(bad, into, dry_run=dry_run))
    assert "Traceback" not in err, err
    assert (code, out) == (2, ""), err
    assert err == family_refusal(str(bad.resolve() / f"{HOLDER}.git"),
                                 NOT_UTF8)
    assert_nothing_was_made(bad, into)


# --- what still runs --------------------------------------------------------

def test_a_utf8_directory_still_plans_a_scaffold(scaffold, capsys, tmp_path):
    """The issue's control, `<dir>/café`: text, so the dry run plans it,
    exit 0, and the plan names the clone URL as it stands."""
    cafe = tmp_path / "café"
    cafe.mkdir()
    code = scaffold.main(scaffold_argv(cafe, tmp_path / "work", dry_run=True))
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "--dry-run: nothing was created." in out
    assert str(cafe.resolve() / f"{PROJECT}.git") in out, out
    assert_nothing_was_made(cafe, tmp_path / "work")


def test_a_utf8_directory_still_scaffolds(tmp_path):
    """End to end into local bare remotes under `<dir>/café`: exit 0, all
    three remotes made, and the assembly root's README prints the clone URL
    with every character as it stands (read as the bytes the scaffold
    wrote), in the single quotes `shell_quoted` gives a word holding `é`
    (#693)."""
    cafe = tmp_path / "café"
    cafe.mkdir()
    work = tmp_path / "work"
    code, out, err = child(SCAFFOLD, *scaffold_argv(cafe, work, dry_run=False))
    assert code == 0, err + out
    assert sorted(os.listdir(cafe)) == [f"{PROJECT}-code.git",
                                        f"{PROJECT}-spec.git",
                                        f"{PROJECT}.git"]
    readme = (work / PROJECT / "README.md").read_bytes().decode("utf-8")
    url = str(cafe.resolve() / f"{PROJECT}.git")
    assert f"git clone --recurse-submodules '{url}'\n" in readme


def test_a_utf8_directory_still_plans_a_family(capsys, tmp_path):
    """The same control for the holder."""
    cafe = tmp_path / "café"
    cafe.mkdir()
    code = family_module().main(family_argv(cafe, tmp_path / "into",
                                            dry_run=True))
    out, err = capsys.readouterr()
    assert code == 0, err
    assert "--dry-run: nothing was created." in out
    assert str(cafe.resolve() / f"{HOLDER}.git") in out, out
    assert_nothing_was_made(cafe, tmp_path / "into")


def test_a_utf8_directory_still_creates_a_holder(tmp_path):
    """End to end into a local bare remote under `<dir>/café`: exit 0,
    `Contoso.git` made, and the holder's README prints the clone URL with
    every character as it stands, in single quotes (#693)."""
    cafe = tmp_path / "café"
    cafe.mkdir()
    into = tmp_path / "into"
    code, out, err = child(FAMILY, *family_argv(cafe, into, dry_run=False))
    assert code == 0, err + out
    assert os.listdir(cafe) == [f"{HOLDER}.git"]
    readme = (into / HOLDER / HOLDER / "README.md").read_bytes().decode(
        "utf-8")
    url = str(cafe.resolve() / f"{HOLDER}.git")
    assert f"git clone --recurse-submodules '{url}'\n" in readme
