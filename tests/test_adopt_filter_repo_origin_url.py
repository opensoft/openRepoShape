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

THE UNSET NAMES THE CLONE'S OWN CONFIG FILE (`--file`), and goes on from a
clone that has no url to unset. Without `--file`, `GIT_CONFIG` in the
environment names the file `git config` writes, and the unset took
`remote.origin.url` out of a file of the person's, outside the clone
(RV1251's SHOULD-1); `--local` is no way round it, since git 2.43 exits 129
with `GIT_CONFIG` set. And a global `clone.defaultRemoteName` gives the clone
a remote that is not `origin`, so there is no url and git exits 5: the unset
goes on from that exit and from no other, so that `execute` fails where main
fails (`mounting the legs`, `No such remote 'origin'`, both legs pushed), not
earlier and with no words (RV1251's NIT-1). That setting is its own defect,
not this file's.

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
#: What `git config --unset` exits with when the key is not there.
KEY_ABSENT = 5
#: A remote name other than `origin`, for a global `clone.defaultRemoteName`.
ELSEWHERE = "upstream"
#: The leg repository `extract_the_code_leg` pushes to.
CODE_LEG = f"{PROJECT}-code.git"

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


def config_lines(path: Path, *lines: str) -> bytes:
    """A git config file written to `path` from `lines`, one per line, with
    a tab before the ones that are not a section: the bytes written."""
    body = (chr(10).join(
        line if line.startswith("[") else chr(9) + line for line in lines)
        + chr(10)).encode("ascii")
    path.write_bytes(body)
    return body


def extract_the_code_leg(adopter, tmp_path, origin) -> tuple:
    """`_extract_leg` itself for the code leg of `origin` (its `src/`), pushed
    to a bare repository made beside it: (the clone, the leg)."""
    head = git("rev-parse", "HEAD", cwd=origin).stdout.strip()
    leg = tmp_path / CODE_LEG
    git("init", "-q", "--bare", "-b", "main", str(leg), cwd=tmp_path)
    work = tmp_path / WORK
    adopter._extract_leg(
        "code", SimpleNamespace(path=origin, commit=head), work, ["src/"],
        tmp_path / "code-paths.txt", "adopt", str(leg), "main",
        f"testorg/{PROJECT}-code")
    return work, leg


def adopt_each_step(tmp_path, source, locale: dict,
                    executing: dict | None = None) -> dict:
    """`plan`, the plan answered, `check` and `execute` with local remotes
    for `source`, each as `adopted` runs it in `locale`, and `execute` with
    `executing` added to its environment: each run there was, by name."""
    plan, work = tmp_path / PLAN_FILE, tmp_path / WORK
    runs = {"plan": adopted(locale, "plan", "--source", str(source),
                            "--project", PROJECT, "--org", "testorg",
                            "--elected-by", "Test Human",
                            "--elected-on", "2026-09-02", "--out", str(plan),
                            "--work-dir", str(work))}
    assert runs["plan"].returncode == 0, said(runs["plan"])
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    runs["check"] = adopted(locale, "check", "--plan", str(plan),
                            "--work-dir", str(work))
    runs["execute"] = adopted({**locale, **(executing or {})}, "execute",
                              "--plan", str(plan), "--yes",
                              "--local-remote-dir", str(tmp_path / REMOTES),
                              "--work-dir", str(work))
    return runs


def assert_adopted(runs: dict) -> None:
    """No run raised a traceback, `check` and `execute` exited 0, and
    `execute` said `adoption verified`."""
    for name, run in runs.items():
        assert TRACEBACK not in run.stderr, f"{name}:{os.linesep}{said(run)}"
    assert runs["check"].returncode == 0, said(runs["check"])
    done = runs["execute"]
    assert done.returncode == 0, said(done)
    assert VERIFIED in done.stdout, said(done)


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
    work, leg = extract_the_code_leg(adopter, tmp_path, origin)

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
    assert_adopted(adopt_each_step(tmp_path, source, latin1))


@needs_filter_repo
def test_execute_leaves_the_file_git_config_names_alone(tmp_path):
    """`GIT_CONFIG` in the environment names the file a bare `git config`
    writes, and the unset named no file: `execute` took the url out of the
    person's file, outside the clone, and refused. Now the unset names the
    clone's own config, so with `GIT_CONFIG` naming a file that holds a
    `[remote "origin"]` url, `execute` says `adoption verified` and that
    file is byte for byte as it was. `adopted` hands the child none of the
    gate's locale variables, so the row runs alike under a UTF-8 gate and a
    Latin-1 one."""
    kept = tmp_path / "kept.gitconfig"
    body = config_lines(kept, '[remote "origin"]',
                        "url = https://example.invalid/keep-me.git")
    source = make_source_repo(tmp_path / "Thing")
    runs = adopt_each_step(tmp_path, source, {}, {"GIT_CONFIG": str(kept)})
    assert kept.read_bytes() == body, said(runs["execute"])
    assert_adopted(runs)


@needs_filter_repo
def test_a_clone_with_no_origin_url_goes_on_to_filter_repo(
        adopter, tmp_path, monkeypatch):
    """A global `clone.defaultRemoteName` gives the clone a remote that is
    not `origin`, so `git config --unset remote.origin.url` has no key and
    exits 5. `_extract_leg` goes on from that, as main went on, and the leg
    is made and pushed: `execute` then fails where main fails, at `mounting
    the legs`, not here before any leg is pushed, with nothing said. The
    unset's exit is recorded as it is raised, so that the row says what it
    saw: 5, and the url of the other remote."""
    origin = make_source_repo(tmp_path / "Thing")
    config_lines(tmp_path / "global.gitconfig", "[clone]",
                 f"defaultRemoteName = {ELSEWHERE}")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "global.gitconfig"))
    real_run = adopter.run
    exits = []

    def spied(args, *rest, **keywords):
        try:
            return real_run(args, *rest, **keywords)
        except adopter.CommandFailed as exc:
            if "--unset" in args:
                exits.append(exc.code)
            raise

    monkeypatch.setattr(adopter, "run", spied)
    work, leg = extract_the_code_leg(adopter, tmp_path, origin)

    assert exits == [KEY_ABSENT], exits
    assert git("config", "--get", f"remote.{ELSEWHERE}.url",
               cwd=work).stdout.strip() == str(origin)
    assert git("rev-parse", "main", cwd=leg).stdout.strip() == git(
        "rev-parse", "HEAD", cwd=work).stdout.strip()


def test_an_unset_that_fails_for_any_other_reason_stops_the_leg(
        adopter, tmp_path, monkeypatch):
    """Only exit 5 is gone on from. Another exit of the unset is refused as
    any failed command is, before `git filter-repo` runs and before anything
    is pushed: here a `config.lock` in the clone, which git cannot take
    (exit 255)."""
    origin = make_source_repo(tmp_path / "Thing")
    real_run = adopter.run

    def locked(args, *rest, **keywords):
        if "--unset" in args:
            (Path(keywords["cwd"]) / ".git" / "config.lock").write_bytes(b"")
        return real_run(args, *rest, **keywords)

    monkeypatch.setattr(adopter, "run", locked)
    with pytest.raises(adopter.CommandFailed) as refused:
        extract_the_code_leg(adopter, tmp_path, origin)

    assert "--unset" in refused.value.args_list, refused.value.args_list
    assert refused.value.code not in (0, KEY_ABSENT), refused.value.code
    assert git("for-each-ref", cwd=tmp_path / CODE_LEG).stdout == ""
