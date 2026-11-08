# SPDX-License-Identifier: Apache-2.0
"""`execute` extracts a leg from a source whose path `git filter-repo` could
not print (#1247).

`_extract_leg` clones the source and runs `git filter-repo` in the clone, and
the clone's `remote.origin.url` is the source's path, byte for byte.
filter-repo prints that url as it removes `origin` (`NOTICE: Removing
'origin' remote ... (was <url>)`), decoded as UTF-8 with `errors='replace'`.
Under a Latin-1 locale a directory `caf` plus U+00E9 is named with the byte
0xE9, the decode makes it U+FFFD, and a Latin-1 stdout cannot hold U+FFFD.
MEASURED ON MAIN AT b1f45fa7 (2026-11-08), git 2.43, git-filter-repo 2.47.0
from pip, Python 3.12, a Latin-1 locale built as below and no `PYTHON*`
variable set: `plan` and `check` passed, and `execute` made both bare leg
repositories and ended `REFUSED extracting the spec leg`, exit 2, with
filter-repo's `UnicodeEncodeError` from `_migrate_origin_to_heads`: the
'latin-1' codec cannot encode U+FFFD.

Now `_extract_leg` unsets the clone's `remote.origin.url` before filter-repo
runs, and filter-repo, finding no url, prints nothing of `origin`. It still
makes each of the clone's remote-tracking branches a branch first, so it
rewrites every branch of the source as before, and the legs are the ones
main made.

WHY NO TEST ELSEWHERE SAW IT. CI and the bench run UTF-8, where the decode
replaces nothing. And `test_adopt_template_values.py`'s
`test_a_utf8_source_directory_still_adopts_with_local_remotes` runs every
child under `PYTHONIOENCODING=utf-8:strict`, which reaches
filter-repo through `execute`'s environment wherever its launcher passes it
on: pip's does, so that row passed on main under Latin-1 with pip's
filter-repo, and failed only beside a launcher that runs `python -E` (the
pipx one #1247 quotes). So the Latin-1 row here sets no `PYTHON*` variable
but `PYTHONUTF8=0`, as a person in that locale runs `execute`, and the row
beside it asks what filter-repo is handed under any locale.

THE LOCALE IS BUILT HERE, as #1106's `test_adopt_one_byte_locale.py` builds
one: a charmap and a locale source this file writes, `localedef -c`, and
`LOCPATH`. The Latin-1 row skips, by name and with `localedef`'s words, where
no such locale can be built, and on Windows.
"""

from __future__ import annotations

import codecs
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from conftest import (ADOPT, blank_unnamed_pin_sources, git, make_source_repo,
                      resolve, skip_where_a_name_cannot_be_not_utf_8)
from test_adopt_git_rm_bytes import LOCALE_KEYS

needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

PROJECT = "Northwind"
PLAN_FILE = "adoption-plan.yaml"
REMOTES = "remotes"
WORK = "work"
#: The entries of `SYNTHETIC_TREE` that `plan` asks about, answered.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))
#: What the git that `execute` runs needs, as `conftest.run_script` sets it.
IDENTITY = {"GIT_AUTHOR_NAME": "openRepoShape tests",
            "GIT_AUTHOR_EMAIL": "tests@openreposhape.invalid",
            "GIT_COMMITTER_NAME": "openRepoShape tests",
            "GIT_COMMITTER_EMAIL": "tests@openreposhape.invalid"}
VERIFIED = b"adoption verified"
TRACEBACK = b"Traceback"
#: A branch of the source beside its default one, which filter-repo makes a
#: branch of the leg's clone from `refs/remotes/origin/`.
BESIDE = "beside"
ORIGIN_URL = "remote.origin.url"
#: How filter-repo begins the line that printed the url.
REMOVING_ORIGIN = "Removing 'origin' remote"

#: The locale #1247 names, as `LC_ALL` names the one built here.
LATIN1_NAME = "en_US.ISO-8859-1"
#: `codecs.lookup(...).name` of Latin-1, which a child in it must report.
LATIN1 = codecs.lookup("iso8859-1").name
#: A child's file name encoding and its preferred encoding, one per line.
ASK_ENCODINGS = ("import codecs, locale, sys; "
                 "print(codecs.lookup(sys.getfilesystemencoding()).name); "
                 "print(codecs.lookup(locale.getpreferredencoding(False))"
                 ".name)")


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_origin_url", ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def charmap() -> str:
    """ISO-8859-1 as `localedef -f` reads a charmap: each byte, 0x00 to
    0xFF, the code point of the same number. The line ends are `chr(10)`,
    and the escape character is the slash, as the charmap declares."""
    end = chr(10)
    return end.join(
        ["<code_set_name> ISO-8859-1", "<comment_char> %",
         "<escape_char> /", "<mb_cur_min> 1", "<mb_cur_max> 1", "CHARMAP"]
        + [f"<U{byte:04X}> /x{byte:02x}" for byte in range(256)]
        + ["END CHARMAP", ""])


@pytest.fixture(scope="module")
def latin1(tmp_path_factory) -> dict:
    """What a child's environment adds to run in a Latin-1 locale built
    here: `LOCPATH`, `LC_ALL` naming it, and `PYTHONUTF8=0`. Built by
    `localedef -c`, which writes a locale whose categories other than
    `LC_CTYPE` are empty and says so (exit 1, warnings); a child started in
    it must report Latin-1 as its file name encoding and its preferred
    encoding, or the row skips with `localedef`'s words."""
    if os.name == "nt":
        pytest.skip("a locale of one byte to a character is a POSIX idea: "
                    "Windows hands a command line to CreateProcessW as UTF-16")
    localedef = shutil.which("localedef")
    if localedef is None:
        pytest.skip(f"no `localedef` here to build {LATIN1_NAME} with")
    kit = tmp_path_factory.mktemp("latin1")
    (kit / "ISO-8859-1").write_text(charmap(), encoding="ascii")
    (kit / "latin1").write_text(chr(10).join(["LC_CTYPE", "END LC_CTYPE", ""]),
                                encoding="ascii")
    (kit / "locales").mkdir()
    built = subprocess.run(
        [localedef, "-c", "-i", str(kit / "latin1"), "-f",
         str(kit / "ISO-8859-1"), str(kit / "locales" / LATIN1_NAME)],
        capture_output=True, text=True, errors="replace",
        stdin=subprocess.DEVNULL, check=False)
    locale = {"LOCPATH": str(kit / "locales"), "LC_ALL": LATIN1_NAME,
              "PYTHONUTF8": "0"}
    asked = subprocess.run([sys.executable, "-c", ASK_ENCODINGS],
                           capture_output=True, text=True, errors="replace",
                           env={**outside_any_locale(), **locale},
                           stdin=subprocess.DEVNULL, check=False)
    if asked.stdout.split() != [LATIN1, LATIN1]:
        words = " ".join(line for line in built.stderr.splitlines()
                         if not line.startswith("[warning]"))
        pytest.skip(f"localedef could not build {LATIN1_NAME} here (exit "
                    f"{built.returncode}: {words[-300:]!r}); a child in it "
                    f"reports {asked.stdout.split()}")
    return locale


def outside_any_locale() -> dict:
    """This environment without a variable that sets a locale or Python's
    stdout encoding (`LOCALE_KEYS`): `PYTHONIOENCODING` among them, which a
    launcher without `-E` would hand filter-repo."""
    return {key: value for key, value in os.environ.items()
            if not key.startswith(LOCALE_KEYS)}


def adopted(locale: dict, *args: str) -> subprocess.CompletedProcess:
    """`adopt-project.py <args>` in `locale`, answered in bytes."""
    env = blank_unnamed_pin_sources(
        {**IDENTITY, **outside_any_locale(), "LANES_LANE": "", **locale}, {})
    return subprocess.run([sys.executable, str(ADOPT), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)


def said(run: subprocess.CompletedProcess) -> str:
    """A run's output, readable in an assertion message."""
    return (run.stdout + run.stderr).decode("utf-8", "backslashreplace")


@needs_filter_repo
def test_filter_repo_starts_with_no_origin_url_and_every_branch(
        adopter, tmp_path, monkeypatch):
    """`_extract_leg` itself, over an ASCII source with a second branch,
    under any locale: when `git filter-repo` starts, the clone has no
    `remote.origin.url`, so filter-repo prints none, and it still has the
    source's remote-tracking branches, which filter-repo then makes
    branches of the clone, as on main. On main the url was there and
    filter-repo printed it. `git remote remove origin` passes the first two
    and fails the third: it took the remote-tracking branches with it."""
    origin = make_source_repo(tmp_path / "Thing")
    git("switch", "-q", "-c", BESIDE, cwd=origin)
    (origin / "src" / "app" / "util.py").write_text("VALUE = 2", "utf-8")
    git("commit", "-q", "-am", "Raise the value", cwd=origin)
    git("switch", "-q", "main", cwd=origin)
    head = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    leg = tmp_path / f"{PROJECT}-code.git"
    git("init", "-q", "--bare", "-b", "main", str(leg), cwd=tmp_path)
    real_run = adopter.run
    started = []

    def spied(args, *rest, **keywords):
        if args[:2] != ["git", "filter-repo"]:
            return real_run(args, *rest, **keywords)
        work = Path(keywords["cwd"])
        started.append({
            "url": git("config", "--get", ORIGIN_URL, cwd=work,
                       check=False).stdout.strip(),
            "tracking": git("for-each-ref", "--format=%(refname)",
                            "refs/remotes/origin/", cwd=work).stdout.split()})
        started[-1]["said"] = real_run(args, *rest, **keywords)
        return started[-1]["said"]

    monkeypatch.setattr(adopter, "run", spied)
    work = tmp_path / "work"
    adopter._extract_leg(
        "code", SimpleNamespace(path=origin, commit=head), work, ["src/"],
        tmp_path / "code-paths.txt", "adopt", str(leg), "main",
        f"testorg/{PROJECT}-code")

    assert len(started) == 1, started
    assert started[0]["url"] == "", started[0]
    assert REMOVING_ORIGIN not in started[0]["said"], started[0]["said"]
    assert str(origin) not in started[0]["said"], started[0]["said"]
    assert {f"refs/remotes/origin/{BESIDE}",
            "refs/remotes/origin/main"} <= set(started[0]["tracking"]), (
        started[0])
    branches = git("for-each-ref", "--format=%(refname)", "refs/heads/",
                   cwd=work).stdout.split()
    assert f"refs/heads/{BESIDE}" in branches, branches
    assert git("rev-parse", "main", cwd=leg).stdout.strip() == git(
        "rev-parse", "HEAD", cwd=work).stdout.strip()


@needs_filter_repo
def test_execute_adopts_a_source_named_in_latin1_under_latin1(tmp_path,
                                                              latin1):
    """#1247's own case: `plan`, `check` and `execute` with local remotes,
    in the Latin-1 locale built here, for a source under a directory `caf`
    plus U+00E9, made as the byte 0xE9, as a Latin-1 system names it. No
    `PYTHON*` variable is set but `PYTHONUTF8=0`, so filter-repo writes its
    stdout in Latin-1 whatever its launcher. `execute` exits 0 and says
    `adoption verified`; on main it ended `REFUSED extracting the spec leg`
    with filter-repo's `UnicodeEncodeError` on U+FFFD, both legs made."""
    skip_where_a_name_cannot_be_not_utf_8(tmp_path)
    parent = Path(os.fsdecode(os.fsencode(tmp_path / "caf")
                              + bytes([0xE9])))
    source = make_source_repo(parent / "Thing")
    plan, work = tmp_path / PLAN_FILE, tmp_path / WORK
    runs = {"plan": adopted(latin1, "plan", "--source", str(source),
                            "--project", PROJECT, "--org", "testorg",
                            "--elected-by", "Test Human",
                            "--elected-on", "2026-09-02", "--out", str(plan),
                            "--work-dir", str(work))}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    runs["check"] = adopted(latin1, "check", "--plan", str(plan),
                            "--work-dir", str(work))
    runs["execute"] = adopted(latin1, "execute", "--plan", str(plan), "--yes",
                              "--local-remote-dir", str(tmp_path / REMOTES),
                              "--work-dir", str(work))
    for name, run in runs.items():
        assert TRACEBACK not in run.stderr, f"{name}:{os.linesep}{said(run)}"
    assert runs["check"].returncode == 0, said(runs["check"])
    done = runs["execute"]
    assert done.returncode == 0, said(done)
    assert VERIFIED in done.stdout, said(done)
