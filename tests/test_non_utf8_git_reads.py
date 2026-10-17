# SPDX-License-Identifier: Apache-2.0
"""What git prints that this repository did not write is read as bytes, not
as UTF-8 text (#423, #426).

`repo_shape.git_out` decodes git's answer strictly, `proc.stdout.decode(
"utf-8")`, and `UnicodeDecodeError` is a `ValueError`, not a `Refusal`, so a
caller that does not ask for bytes ends in a traceback, exit 1, when git
prints a byte that is not UTF-8. Nobody did anything wrong: git keeps a
config value and, under `core.quotePath=false`, a file name as the bytes it
was given, and a name saved under a legacy code page is not UTF-8.

#423, three readers of `git status --porcelain`:

  * `bump-leg.py` `_ensure_root_clean` owes `bump-leg-root-dirty`, exit 2,
    `--dry-run` alike, and the name of the file. It is the first read
    `cmd_bump` makes after its arguments, so nothing has moved yet;
  * `scaffold-project.py` `_shape_revision` and `family.py` `_shape_snapshot`
    ask the standard's OWN checkout whether it is dirty, to print a WARNING
    and go on. Only whether the answer is empty is used, but a traceback
    came first, before any remote existed, so a dirty standard's checkout
    holding one such file blocked every scaffold and every `family.py init`
    run from it.

#426, one reader of `git config user.name`: `family.py init` `_creator_name`
refuses a name that is not text BY NAME, as the scaffold refuses the same
setting (#282, `scaffold-unwritable-value`) and `adopt-project.py plan` does
(#292): `family-unwritable-value`, exit 2, naming the setting and the flag
(`--created-by`) that gets past it, before anything exists and under
`--dry-run` alike. `--created-by`, or a GIT_AUTHOR_NAME, is read first and
wins, so neither asks git at all.

NO NETWORK AND NO GITHUB. The scaffold and `family.py init` here are run as
child processes into LOCAL bare remotes (`--local-remote-dir`), which never
calls `gh`. A name that is not UTF-8 is made by `os.fsdecode` of its bytes, so
a POSIX filesystem takes it as it is; where the system cannot carry the byte
the test skips (`make_file`: Windows' `os.fsencode` makes no byte of it, and
macOS's disk refuses it), and where the ENVIRONMENT cannot carry a byte
(Windows') the `user.name` rows skip. The checkout under test for
`_shape_revision` and `_shape_snapshot` is a COPY of the standard in a
repository of its own (`standard`), made dirty one test at a time, never this
checkout.
"""

from __future__ import annotations

import errno
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ORG, PROJECT, REPO, cloned_just_pushed, git, run_script,
                      skip_message,
                      skip_where_fsencode_gives_a_surrogate_no_byte,
                      windows_fsencode)
from test_bump_leg import branched, bump

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import load_yaml  # noqa: E402

SCAFFOLD = REPO / "scaffold-project.py"
FAMILY = REPO / "scripts" / "family.py"
HOLDER = "Contoso"

#: Where the advanced spec commit is pushed. Not another module's branch: the
#: bare remotes are session-scoped, and a second, different commit pushed to
#: a name already taken is refused as non-fast-forward.
ADVANCE_BRANCH = "non-utf8-git-reads-advance"

WORKFLOWS = Path(".github") / "workflows"

#: `caf<e9>.yml`: Latin-1 e-acute is the single byte 0xE9, a UTF-8 lead byte
#: with no continuation after it. Python keeps that byte of a file name as
#: the lone surrogate `\udce9` (`os.fsdecode`'s `surrogateescape`), and a
#: POSIX filesystem takes it back as the byte. It is spelled as that string
#: and not made by `os.fsdecode(b"...")`, which RAISES on Windows, where this
#: module must still import: `make_file` skips there.
NOT_UTF8 = "caf\udce9.yml"
#: The same name as text.
UTF8 = "caf\u00e9.yml"

#: `core.quotePath=false`, as command-line config: it outranks every config
#: file, and a test needs no config file of its own to say it.
QUOTE_PATH_OFF = {"GIT_CONFIG_COUNT": "1",
                  "GIT_CONFIG_KEY_0": "core.quotePath",
                  "GIT_CONFIG_VALUE_0": "false"}


def make_file(path: Path, data: bytes = b"on: [push]\n") -> None:
    """Write `data` at `path`, or skip: a name that is not UTF-8 needs a
    system that carries the byte and a filesystem that stores it (Linux does;
    APFS refuses it, and on Windows `os.fsencode` makes no byte of it, which
    is asked FIRST: NTFS most likely takes the surrogate, and the file would
    then not be the one the test means). A name that is UTF-8 is written.

    Two answers are the system's, each skipped on a reason of its own: a
    file name encoding that cannot spell the name (`UnicodeError`: ASCII
    under `LC_ALL=C`) and a disk that refuses the name (EILSEQ: macOS).
    Every other `OSError`, a full disk (ENOSPC), a read-only one (EROFS)
    or a folder nobody can write in (EACCES), is the test's own and is
    raised (#834)."""
    skip_where_fsencode_gives_a_surrogate_no_byte(path.name)
    try:
        path.write_bytes(data)
    except UnicodeError as exc:
        pytest.skip("this system's file name encoding cannot spell "
                    f"{path.name!r}: {exc}")
    except OSError as exc:
        if exc.errno != errno.EILSEQ:
            raise
        pytest.skip("this filesystem refuses a file name that is not "
                    f"UTF-8 (EILSEQ): {exc}")


def test_make_file_skips_where_fsencode_makes_no_byte_and_writes_nothing(
        tmp_path, monkeypatch):
    """THE WINDOWS GUARD, EMULATED (#663, R423 N1): where `os.fsencode` gives
    a surrogate three bytes, NTFS most likely takes `caf\\udce9.yml` anyway
    and git for Windows would see another name, so `make_file` skips BEFORE it
    writes, and nothing is on the disk. Linux takes the name, so a file
    standing there would be the failure."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    target = tmp_path / NOT_UTF8
    reason = skip_message(make_file, target)
    assert reason is not None, "make_file wrote the name instead of skipping"
    assert "os.fsencode" in reason, reason
    assert not target.exists(), "the file was written before the skip"


def test_make_file_writes_a_name_that_is_utf8_where_fsencode_makes_no_byte(
        tmp_path, monkeypatch):
    """The guard is for the byte and no wider: Windows holds `caf\\u00e9.yml`
    as text, and the tests that use it must run there. Skipped, before the
    Windows `os.fsencode` is put in, where this system's own file name
    encoding cannot write `caf\\u00e9.yml` (ASCII); and for nothing else, so a
    write the disk refuses fails the test (#757)."""
    skip_where_the_environment_cannot_carry(UTF8)
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    target = tmp_path / UTF8
    assert skip_message(make_file, target, b"on: [pull_request]\n") is None
    assert target.read_bytes() == b"on: [pull_request]\n"


def test_make_file_writes_the_name_that_is_not_utf8_where_the_system_has_it(
        tmp_path):
    """The control: where `os.fsencode` carries the byte and the disk takes it
    (Linux), the file is written under the name that is not UTF-8, so the
    guard skipped nothing."""
    if len(os.fsencode("\udce9")) != 1:
        pytest.skip("this system's `os.fsencode` makes no byte of U+DCE9")
    target = tmp_path / NOT_UTF8
    reason = skip_message(make_file, target, b"on: [push]\n")
    if reason is not None and "filesystem" in reason:
        pytest.skip(reason)
    assert reason is None, reason
    assert os.fsencode(target.name) == b"caf\xe9.yml"
    assert target.read_bytes() == b"on: [push]\n"


def assert_shown_without_hex_escapes(shown: str, output: str) -> None:
    """Assert that the refusal's line for `caf\u00e9.yml` holds no literal
    `\\x`, or skip where this system's file name encoding is not UTF-8.

    On a Latin-1 host `make_file` writes the one byte 0xE9 for it, and the
    tool, which decodes git's bytes as UTF-8, rightly prints `caf\\xe9.yml`:
    the assertion would fail though the tool is right (#663, NIT-1). So it
    is asked after the system's encoding is, and a system whose encoding is
    not UTF-8 skips. (Where `make_file` could not write the name at all, an
    ASCII host, it skipped already.)"""
    if os.fsencode(UTF8) != UTF8.encode("utf-8"):
        pytest.skip("this system's file name encoding is not UTF-8, so a "
                    "UTF-8 name is not written as the bytes the tool decodes")
    assert "\\x" not in shown, output


def test_the_hex_escape_check_skips_where_the_file_name_encoding_is_not_utf_8(
        monkeypatch):
    """THE LATIN-1 HOST, EMULATED (#663, NIT-1): `os.fsencode` gives the name
    `caf\u00e9.yml` as the one byte 0xE9, the line holds a `\\x`, and the
    check skips, where it would otherwise fail on a tool that is right."""
    monkeypatch.setattr(os, "fsencode", lambda name: name.encode("latin-1"))
    reason = skip_message(assert_shown_without_hex_escapes,
                          r"    M .github/workflows/caf\xe9.yml", "output")
    assert reason is not None, "the check asserted instead of skipping"
    assert "UTF-8" in reason, reason


def test_the_hex_escape_check_asserts_where_the_file_name_encoding_is_utf_8(
        monkeypatch):
    """The control: Windows' `os.fsencode` (emulated), like Linux's and
    macOS's, is UTF-8 for text, so the check is not skipped, and it still
    fails a line that holds a `\\x` and passes one that does not."""
    monkeypatch.setattr(os, "fsencode", windows_fsencode)
    reason = skip_message(assert_shown_without_hex_escapes,
                          "    M .github/workflows/caf\u00e9.yml", "output")
    assert reason is None, reason
    with pytest.raises(AssertionError):
        skip_message(assert_shown_without_hex_escapes,
                     r"    M .github/workflows/caf\xc3\xa9.yml", "output")


def git_bytes(*args: str, cwd: Path) -> bytes:
    """`git <args>` in `cwd`, stdout as the bytes git wrote. `conftest.git`
    decodes as text, which is the failure under test."""
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          check=True).stdout


# ---------------------------------------------------------------------------
# #423, `bump-leg.py`: the root's own status
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = cloned_just_pushed(
        scaffolded["remotes"] / f"{PROJECT}-spec.git",
        tmp_path_factory.mktemp("spec-advance-non-utf8") / f"{PROJECT}-spec")
    (work / "NON-UTF8-CONTRACT.md").write_text("# a contract gained\n")
    git("add", "--", "NON-UTF8-CONTRACT.md", cwd=work)
    git("commit", "-qm", "Advance the spec leg for the non-UTF-8 tests",
        cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


def dirty_root(project: Path, name: str, *, quote_path: bool) -> Path:
    """A root on a bump branch whose tracked workflow `name` is committed and
    then edited, with `core.quotePath` as asked, in the clone's own config
    (the issue's own set-up). Returns the file. A tracked file with an
    uncommitted edit is the one dirt `_ensure_root_clean` refuses."""
    branched(project)
    target = project / WORKFLOWS / name
    make_file(target)
    git("add", "--", (WORKFLOWS / name).as_posix(), cwd=project)
    git("commit", "-qm", f"Add {WORKFLOWS.as_posix()}/<name>", cwd=project)
    target.write_bytes(target.read_bytes() + b"# edited\n")
    if not quote_path:
        git("config", "core.quotePath", "false", cwd=project)
    return target


def found(project: Path) -> dict:
    """Everything a refusal promises not to have moved, as BYTES: `status -z`
    is never quoted, so it reads the same whatever `core.quotePath` says, and
    `conftest.git`'s text decode would be the failure under test."""
    return {
        "head": git_bytes("rev-parse", "HEAD", cwd=project),
        "branch": git_bytes("symbolic-ref", "HEAD", cwd=project),
        "status": git_bytes("status", "--porcelain", "-z", cwd=project),
        "index": git_bytes("ls-files", "-s", "-z", cwd=project),
        "staged": git_bytes("diff", "--cached", "--name-only", "-z",
                            cwd=project),
        "pin": (project / "contracts" / "spec-pin.yaml").read_bytes(),
        "leg": git_bytes("rev-parse", "HEAD", cwd=project / "spec"),
    }


def refused_dirty(project: Path, scaffolded: dict, to: str, shown: str,
                  extra: tuple) -> str:
    """Bump, and assert what the issue's table asks of the row: exit 2,
    `bump-leg-root-dirty`, the file named on a line of its own, no traceback,
    and nothing moved. Returns stderr."""
    before = found(project)
    result = bump(project, scaffolded, to, *extra)
    output = result.stderr + result.stdout
    assert result.returncode == 2, output
    assert "REFUSED bump-leg-root-dirty: " in result.stderr, output
    assert f"{project} has uncommitted changes:\n" in result.stderr, output
    assert f"    M {shown}" in result.stderr.splitlines(), output
    assert "Remediation: commit or stash them first." in result.stderr
    assert "Traceback" not in output, output
    assert "UnicodeDecodeError" not in output, output
    assert result.stdout == "", "nothing but the refusal is printed"
    assert found(project) == before, "the root is as it was found"
    return result.stderr


MODES = pytest.mark.parametrize("extra", [(), ("--dry-run",)],
                                ids=["bump", "dry-run"])


@MODES
def test_a_name_that_is_not_utf8_under_quote_path_false_is_a_refusal_not_a_traceback(
        project, scaffolded, advanced, extra):
    """THE ISSUE'S FIRST ROW: a tracked `caf<e9>.yml` with an uncommitted
    edit, `core.quotePath=false`. git prints the raw byte, and `git_out`
    raised `UnicodeDecodeError` out of `_ensure_root_clean`, exit 1, with
    `--dry-run` alike. Now it is the refusal the control row gives, exit 2,
    and the file is named by the byte as `backslashreplace` shows it."""
    dirty_root(project, NOT_UTF8, quote_path=False)
    refused_dirty(project, scaffolded, advanced,
                  r".github/workflows/caf\xe9.yml", extra)


@MODES
def test_the_same_name_under_the_default_quoting_is_still_refused_and_quoted(
        project, scaffolded, advanced, extra):
    """THE CONTROL ROW: with the default `core.quotePath` git prints the name
    C-quoted, `".github/workflows/caf\\351.yml"`, which decoded on main as
    well. It reads as it did."""
    dirty_root(project, NOT_UTF8, quote_path=True)
    refused_dirty(project, scaffolded, advanced,
                  r'".github/workflows/caf\351.yml"', extra)


@MODES
def test_a_name_that_is_utf8_under_quote_path_false_is_still_refused(
        project, scaffolded, advanced, extra):
    """THE SECOND CONTROL ROW: `caf\u00e9.yml` as text, `core.quotePath=false`.
    Its bytes decode, and it was refused on main; it still is, and the
    refusal still prints it as git did. (The name is matched on its ASCII
    ends: a child's stderr is decoded by the locale here, which is not UTF-8
    on every platform. What the middle of the name is NOT is held instead, in
    any locale: the tool decodes git's bytes as UTF-8, so `\\u00e9` is one
    character, where a decode as ASCII would show its two bytes as `\\xc3\\xa9`,
    and a locale's decode of what the child printed is mojibake at worst and
    never a `\\x`: #423's mutant R1, #663.)"""
    dirty_root(project, UTF8, quote_path=False)
    before = found(project)
    result = bump(project, scaffolded, advanced, *extra)
    output = result.stderr + result.stdout
    assert result.returncode == 2, output
    assert "REFUSED bump-leg-root-dirty: " in result.stderr, output
    [shown] = [line for line in result.stderr.splitlines()
               if line.startswith("    M .github/workflows/caf")]
    assert shown.endswith(".yml"), output
    assert "Traceback" not in output, output
    assert found(project) == before
    assert_shown_without_hex_escapes(shown, output)


def test_the_refusal_names_every_dirty_file_whatever_its_bytes(
        project, scaffolded, advanced):
    """A second dirty file beside the one that is not UTF-8: both are named,
    one per line, and neither line is lost to the other's bytes. The
    refusal's lines are git's own, in git's own order."""
    dirty_root(project, NOT_UTF8, quote_path=False)
    (project / "README.md").write_text("edited\n", encoding="utf-8")
    result = bump(project, scaffolded, advanced)
    lines = result.stderr.splitlines()
    assert result.returncode == 2, result.stderr
    assert r"    M .github/workflows/caf\xe9.yml" in lines, result.stderr
    assert any(line.rstrip().endswith("M README.md") for line in lines), (
        result.stderr)
    assert "Traceback" not in result.stderr


@MODES
def test_the_remedy_the_refusal_names_works(project, scaffolded, advanced,
                                            extra):
    """THE REFUSAL IS NOT A DEAD END: committing the edit, as it says, and
    running the same command bumps (or, under `--dry-run`, says it would),
    over a root that still holds the name that is not UTF-8."""
    target = dirty_root(project, NOT_UTF8, quote_path=False)
    assert bump(project, scaffolded, advanced, *extra).returncode == 2
    git("add", "--", (WORKFLOWS / NOT_UTF8).as_posix(), cwd=project)
    git("commit", "-qm", "Commit the edit", cwd=project)
    assert target.exists()
    was = git_bytes("rev-parse", "HEAD", cwd=project)
    result = bump(project, scaffolded, advanced, *extra)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    moved = git_bytes("rev-parse", "HEAD", cwd=project) != was
    assert moved is (not extra), "a dry run commits nothing, a real run one"


# ---------------------------------------------------------------------------
# #423, the scaffold and `family.py init`: the standard's own checkout
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def standard(tmp_path_factory) -> Path:
    """The standard as a git checkout of its own, committed and CLEAN: every
    tool, template and contract, and no test, so the tools under test read
    `SHAPE_ROOT` as this copy. Each test that wants it dirty adds a file and
    takes it away again (`untracked`)."""
    copy = tmp_path_factory.mktemp("standard-non-utf8") / "standard"
    shutil.copytree(REPO, copy, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "tests", "docs", "handoffs"))
    git("init", "-q", cwd=copy)
    git("add", "-A", cwd=copy)
    git("commit", "-q", "--no-gpg-sign", "-m", "a copy of the standard",
        cwd=copy)
    assert git_bytes("status", "--porcelain", "-z", cwd=copy) == b""
    return copy


@pytest.fixture
def untracked(standard):
    """Leave one untracked file in the copy, named by the test, and take it
    away at the end; returns the function that does."""
    made: list[Path] = []

    def leave(name: str) -> Path:
        target = standard / name
        make_file(target)
        made.append(target)
        return target

    yield leave
    for target in made:
        target.unlink()
    assert git_bytes("status", "--porcelain", "-z", cwd=standard) == b""


def tool_env(**extra: str) -> dict:
    """The environment a tool under test runs in: no bytecode written into
    the copy (an untracked `__pycache__` would be dirt, though the standard's
    own `.gitignore` names it), and `extra` on top."""
    return {"PYTHONDONTWRITEBYTECODE": "1", **extra}


def revision_of(standard: Path) -> str:
    return git("rev-parse", "HEAD", cwd=standard).stdout.strip()


def scaffold_from(standard: Path, tmp_path, env: dict, *, dry_run: bool):
    return run_script(
        standard / "scaffold-project.py", "--org", ORG, "--project", PROJECT,
        "--elected-by", "Test Human", "--elected-on", "2026-09-02",
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"),
        *(["--dry-run"] if dry_run else []), env=env)


def init_from(standard: Path, tmp_path, env: dict, *, dry_run: bool):
    return run_script(
        standard / "scripts" / "family.py", "init", "--org", ORG,
        "--family", HOLDER, "--created-by", "T H",
        "--created-on", "2026-09-02",
        "--local-remote-dir", str(tmp_path / "remotes"),
        "--work-dir", str(tmp_path / "work"),
        *(["--dry-run"] if dry_run else []), env=env)


#: The first words of each tool's warning, up to the revision it names.
SCAFFOLD_WARNING = ("WARNING the openRepoShape checkout is DIRTY. `commit:` "
                    "and `tree_sha256` in the shape pin will record ")
FAMILY_WARNING = ("WARNING the openRepoShape checkout is DIRTY. `commit:` "
                  "and `tree_sha256` will record ")

#: `(tool, how it is run, the warning it prints)`.
TOOLS = [
    pytest.param(scaffold_from, SCAFFOLD_WARNING, id="scaffold"),
    pytest.param(init_from, FAMILY_WARNING, id="family-init"),
]

#: The issue's rows for the two: `core.quotePath=false` with a name that is
#: not UTF-8; and its two controls, which passed on main.
DIRTY_ROWS = [
    pytest.param(NOT_UTF8, QUOTE_PATH_OFF, id="not-utf8-quote-path-false"),
    pytest.param(NOT_UTF8, {}, id="not-utf8-default-quoting"),
    pytest.param(UTF8, QUOTE_PATH_OFF, id="utf8-quote-path-false"),
]


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("run, warning", TOOLS)
@pytest.mark.parametrize("name, config", DIRTY_ROWS)
def test_a_dirty_standard_is_warned_about_whatever_its_file_is_named(
        standard, untracked, tmp_path, run, warning, name, config, dry_run):
    """THE ISSUE'S ROWS: the standard's checkout holds an untracked
    `caf<e9>.yml` and git is told `core.quotePath=false`. `_shape_revision`
    (the scaffold) and `_shape_snapshot` (`family.py init`) asked
    `status --porcelain` through `git_out` and died in `UnicodeDecodeError`,
    exit 1, before a remote existed. Now each prints its DIRTY warning, for
    the revision the copy is at, and goes on: exit 0, and a real run makes
    the remotes, which the traceback never reached."""
    untracked(name)
    result = run(standard, tmp_path, tool_env(**config), dry_run=dry_run)
    assert result.returncode == 0, result.stderr + result.stdout
    assert f"{warning}{revision_of(standard)[:12]}" in result.stderr, (
        result.stderr)
    assert "Traceback" not in result.stderr, result.stderr
    assert "UnicodeDecodeError" not in result.stderr, result.stderr
    assert (tmp_path / "remotes").exists() is (not dry_run), (
        "a dry run creates no remote and a real run does")


@pytest.mark.parametrize("config", [QUOTE_PATH_OFF, {}],
                         ids=["quote-path-false", "default-quoting"])
@pytest.mark.parametrize("run, warning", TOOLS)
def test_a_clean_standard_prints_no_warning(standard, tmp_path, run, warning,
                                            config):
    """THE LAST ROW: the standard's checkout is clean, `core.quotePath=false`,
    and the run is exit 0 with no warning. `bool(...)` of git's bytes must
    still be false for an empty answer."""
    result = run(standard, tmp_path, tool_env(**config), dry_run=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "DIRTY" not in result.stderr, result.stderr


# ---------------------------------------------------------------------------
# #426, `family.py init`: `git config user.name`
# ---------------------------------------------------------------------------

#: The bytes of `Jos<e9>` as an environment carries them. Windows' environment
#: is UTF-16, and git for Windows converts it itself, so no byte that is not
#: UTF-8 reaches `git config` there.
POSIX_ENVIRONMENT_ONLY = pytest.mark.skipif(
    os.name == "nt",
    reason="a POSIX environment's bytes; Windows' is UTF-16 and git for "
           "Windows converts it")
LEGACY_NAME = "Jos\udce9"


def skip_where_the_environment_cannot_carry(value: str) -> None:
    """Skip where this system's file name encoding cannot encode `value`, as
    under `LC_ALL=C PYTHONUTF8=0 PYTHONCOERCECLOCALE=0` (ASCII). It is asked of
    a file name (`make_file` cannot write `caf\\u00e9.yml`) and of an
    environment value: `subprocess` puts each one through `os.fsencode`
    before it starts the child, so a `user.name` of `Jos\\u00e9` raises
    `UnicodeEncodeError` in the test and not in the tool (#757). Text that is
    ASCII, or a lone surrogate that `os.fsencode` gives back as its byte, is
    carried."""
    try:
        os.fsencode(value)
    except UnicodeEncodeError:
        pytest.skip(f"this system's file name encoding "
                    f"({sys.getfilesystemencoding()}) cannot carry {value!r}")


REFUSED = "REFUSED family-unwritable-value: "
#: How the refusal names the creator when no flag supplied it: `_manifest_flags`
#: (#307), so that the two refusals agree on who is meant.
CREATOR_NOT_GIVEN = ("--created-by (not given, so GIT_AUTHOR_NAME or "
                     "`git config user.name`)")
WRITTEN_INTO = "which `init` records in the holder's `family.yaml`, and "
REMEDIATION = ("Remediation: nothing was created, and `--dry-run` refuses "
               "the same. `init` read the creator from `git config "
               "user.name`, because no --created-by was given and "
               "GIT_AUTHOR_NAME names nobody: pass --created-by 'Your "
               "Name', or correct that setting. ")

NOT_UTF8_REASON = "it holds a byte that is not UTF-8"
LINE_BREAK = "it holds a line break, and it is written as one line"
CONTROL = "it holds a control character"
BIDI = ("it holds a bidirectional control (an embedding, override or "
        "isolate), which shows the rest of the line in another order than "
        "it is written")


def user_name(value: str, **extra: str) -> dict:
    """The environment in which `git config user.name` answers `value`, given
    as command-line config (git 2.31), which no config file overrides, so the
    checkout's own config cannot outrank it; and GIT_AUTHOR_NAME is EMPTY, which
    `_creator_name` passes over (and `env_commit` replaces with its own
    fallback, where a name of whitespace alone would reach git as it is and be
    refused by `git commit`)."""
    return {"GIT_AUTHOR_NAME": "", "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "user.name", "GIT_CONFIG_VALUE_0": value,
            **extra}


def init(tmp_path, env: dict, *flags: str, landing: str = "--work-dir",
         dry_run: bool = False):
    """`family.py init` of this checkout into local bare remotes under
    `tmp_path`, with no `--created-by` unless `flags` gives one."""
    where = tmp_path / ("work" if landing == "--work-dir" else "into")
    return run_script(
        FAMILY, "init", "--org", ORG, "--family", HOLDER,
        "--created-on", "2026-09-02",
        "--local-remote-dir", str(tmp_path / "remotes"), landing, str(where),
        *flags, *(["--dry-run"] if dry_run else []), env=env)


def nothing_was_created(tmp_path) -> None:
    for made in ("remotes", "work", "into"):
        assert not (tmp_path / made).exists(), f"{made} was created"


@pytest.mark.parametrize("landing", ["--work-dir", "--into"])
@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@POSIX_ENVIRONMENT_ONLY
def test_a_user_name_that_is_not_utf8_is_refused_by_name_before_anything_exists(
        tmp_path, landing, dry_run):
    """THE ISSUE'S ROW: no `--created-by`, no GIT_AUTHOR_NAME, and a
    `git config user.name` of `Jos<e9>`. `_creator_name` read it through
    `git_out`, whose strict decode raised `UnicodeDecodeError`: a traceback,
    exit 1, under `--dry-run` too, naming neither the setting nor the flag.
    Now it is `family-unwritable-value`, exit 2, in the scaffold's words
    (`scaffold-unwritable-value`, #282), naming where the creator came from
    and the flag that gets past it, and no remote, work directory or family
    folder exists."""
    result = init(tmp_path, user_name(LEGACY_NAME), landing=landing,
                  dry_run=dry_run)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stdout == "", "the plan is never printed"
    assert result.stderr.startswith(
        f"{REFUSED}{CREATOR_NOT_GIVEN} is {LEGACY_NAME!r}, {WRITTEN_INTO}"
        f"{NOT_UTF8_REASON}.\n{REMEDIATION}"), result.stderr
    assert "Traceback" not in result.stderr
    assert "UnicodeDecodeError" not in result.stderr
    nothing_was_created(tmp_path)


@POSIX_ENVIRONMENT_ONLY
def test_the_refusal_is_the_scaffolds_in_the_same_words_for_the_same_name(
        tmp_path):
    """THE ISSUE'S TWIN ROW: `scaffold-project.py` refuses the same
    `user.name` as `scaffold-unwritable-value`, naming the same byte in the
    same sentence, and the family holder is its third reader. The reason
    clause is `unwritable_reason`'s, the one both ask."""
    scaffolded = run_script(
        SCAFFOLD, "--org", ORG, "--project", PROJECT,
        "--elected-on", "2026-09-02", "--dry-run",
        "--local-remote-dir", str(tmp_path / "scaffold-remotes"),
        "--work-dir", str(tmp_path / "scaffold-work"),
        env=user_name(LEGACY_NAME))
    family = init(tmp_path, user_name(LEGACY_NAME), dry_run=True)
    assert (scaffolded.returncode, family.returncode) == (2, 2)
    twin = scaffolded.stderr.splitlines()[0]
    assert "REFUSED scaffold-unwritable-value: " in twin, scaffolded.stderr
    assert f"is {LEGACY_NAME!r}, which the scaffold writes" in twin
    assert twin.endswith(f"and {NOT_UTF8_REASON}.")
    assert family.stderr.splitlines()[0].endswith(f"and {NOT_UTF8_REASON}.")


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@POSIX_ENVIRONMENT_ONLY
def test_created_by_wins_and_git_is_not_asked_for_a_name_it_overrides(
        tmp_path, dry_run):
    """THE ISSUE'S FIRST CONTROL: `--created-by 'T H'` with the same bad
    setting still initialises, exit 0, and records `T H`. The flag is read
    first, so the setting is not asked, and is not refused."""
    result = init(tmp_path, user_name(LEGACY_NAME), "--created-by", "T H",
                  dry_run=dry_run)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "created by   T H on 2026-09-02" in result.stdout, result.stdout
    assert (tmp_path / "remotes").exists() is (not dry_run)
    if not dry_run:
        manifest = (tmp_path / "work" / HOLDER / "family.yaml").read_text(
            encoding="utf-8")
        assert 'created_by: "T H"' in manifest, manifest


@POSIX_ENVIRONMENT_ONLY
def test_git_author_name_wins_over_a_user_name_that_is_not_utf8(tmp_path):
    """GIT_AUTHOR_NAME answers before `git config user.name`, as it did, so a
    bad setting it overrides is neither read nor refused."""
    result = init(tmp_path, user_name(LEGACY_NAME, GIT_AUTHOR_NAME="Ada"),
                  dry_run=True)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "created by   Ada on 2026-09-02" in result.stdout, result.stdout


@pytest.mark.parametrize("dry_run", [True, False], ids=["dry-run", "real"])
@pytest.mark.parametrize("value", ["Jose", "Jos\u00e9", "Mehr\u200cdad",
                                   "CORP\\nick", 'Joe "JJ" Smith'],
                         ids=["ascii", "accent", "zwnj", "backslash", "quote"])
def test_a_user_name_that_is_text_still_initialises(tmp_path, value, dry_run):
    """THE ISSUE'S SECOND CONTROL: `user.name` `Jose`, no `--created-by`,
    exit 0, `created_by: "Jose"`. Text a file holds is not refused: an
    accent, a U+200C ZERO WIDTH NON-JOINER, a backslash and a quote, which
    the scaffold lets through as well."""
    skip_where_the_environment_cannot_carry(value)
    result = init(tmp_path, user_name(value), dry_run=dry_run)
    assert result.returncode == 0, result.stderr + result.stdout
    assert "REFUSED" not in result.stderr, result.stderr
    assert (tmp_path / "remotes").exists() is (not dry_run)
    if not dry_run:
        manifest = load_yaml(tmp_path / "work" / HOLDER / "family.yaml")
        assert manifest["created_by"] == value


@pytest.mark.parametrize("value, reason", [
    pytest.param("Ada\nLovelace", LINE_BREAK, id="lf"),
    pytest.param("\u202eevil", BIDI, id="u202e"),
    pytest.param("a\x1bb", CONTROL, id="esc"),
])
def test_every_other_name_no_file_can_hold_is_refused_the_same_way(
        tmp_path, value, reason):
    """THE QUESTION IS THE SHARED ONE (`unwritable_reason`), as the scaffold
    asks it of the same setting: a line break, a bidi control and a control
    character in `git config user.name` are refused in its words, where the
    byte that is not UTF-8 is the case the issue lists."""
    skip_where_the_environment_cannot_carry(value)
    result = init(tmp_path, user_name(value), dry_run=True)
    assert result.returncode == 2, result.stderr + result.stdout
    assert result.stderr.startswith(
        f"{REFUSED}{CREATOR_NOT_GIVEN} is {value!r}, {WRITTEN_INTO}"
        f"{reason}.\n{REMEDIATION}"), result.stderr
    nothing_was_created(tmp_path)


def test_a_user_name_of_whitespace_alone_is_still_no_creator(tmp_path):
    """Nothing in the setting is `family-no-creator`, as it was: the empty
    name is text a file holds, and the refusal that names a missing creator
    is the one that applies."""
    result = init(tmp_path, user_name("   "), dry_run=True)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED family-no-creator: " in result.stderr, result.stderr
    nothing_was_created(tmp_path)
