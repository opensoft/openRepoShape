# SPDX-License-Identifier: Apache-2.0
"""The project's own validators are told what to write in (#254).

`bump-leg.py` (a real bump) and `update-shape.py apply` run the PROJECT'S
`scripts/validate-pins.py` and `scripts/validate-manifest.py` as child
processes after they rewrite the pin. Those are digest-pinned shape copies: they
print the display name with a plain `print` (`manifest ok: 日本 ...`), and a
child takes its stdout CONFIGURATION from its environment, not from the
`reconfigure` its parent did (#214). So on a stdout whose code page cannot hold
the name -- `PYTHONIOENCODING=cp1252`, or Windows' own default for any stdout
that is not the console, which is cp1252 with `surrogateescape` on a
Western-European install -- the validator raised `UnicodeEncodeError`, exited 1,
and the tool refused and rolled back a bump that was fine. The refusal blamed
the validators (`bump-leg-validators-red`, `update-validators-red`).

The fix is in the two callers and not in the validators, which are shape copies:
each now hands its child an explicit `PYTHONIOENCODING`.
- `bump-leg.py` CAPTURES the output, so the child writes UTF-8 and the tool
  reads the pipe as UTF-8, and then prints it through its own (escaped) stdout.
- `update-shape.py` lets the child INHERIT stdout, so the child writes in the
  parent's own encoding with a handler that cannot raise, built-in names only.

Three kinds of test, the first two against local bare remotes and never GitHub:
- the real tools, on a project whose display name is `日本`, under every stdout
  below. Answered in BYTES, so a byte the stdout could not have held is a byte
  the test sees;
- the same two runs under a POSIX C locale with no `PYTHONIOENCODING` at all,
  where the stdout is ASCII and the codec the tool reads a pipe with by default
  is not UTF-8;
- the environment helpers themselves, each one handed to a real child that
  prints the name, so a handler a child does not know fails here; and a guard
  that no tool runs the interpreter without one.

One name no stdout can hold at all, a lone surrogate (#280), is refused by the
validator as a finding, and the two tools, the doctor and `make validate` are
each run on it.
"""

from __future__ import annotations

import ast
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PROJECT, REPO, git
from test_stdout_encoding import NAME, child_environ, run_tool_bytes
from test_update_shape import (CHANGED, CHANGED_SOURCE, UPSTREAM_FIX_LINE,
                               commit_upstream_changes,
                               scaffold_upstream_and_project)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

BUMP = REPO / "scripts" / "bump-leg.py"
UPDATE = REPO / "update-shape.py"

#: Where the advanced spec commit is pushed: a branch of its own, so no other
#: module's view of the session-scoped bare remote changes (`test_bump_leg.py`
#: does the same under its own name).
ADVANCE_BRANCH = "validator-child-encoding-advance"
#: The branch the display-name commit and the bump land on. The bump refuses to
#: commit onto the tracking branch.
WORKING_BRANCH = "display-name"
#: The branch `update-shape.py apply --branch` creates for its commit.
UPDATE_BRANCH = "update/shape"

#: The `PYTHONIOENCODING` a run is made under, and how a stdout under it must
#: show `NAME`. `shape_materialize`'s own helper made the parent's stdout safe
#: (#214); what is new is that the CHILD's words arrive through it too.
#: - `cp1252:surrogateescape` is Windows' default for a stdout that is not the
#:   console, and `cp1252:strict` is `PYTHONIOENCODING=cp1252`: neither holds
#:   the name, which is escaped.
#: - `cp1252:replace` is an operator's own lenient handler, left as chosen.
#: - `cp932:strict` is a Japanese Windows, whose code page holds the name, and
#:   `utf-8:strict` the control: both written as they are. (The cp932 BUMP
#:   also fails on 60d08a1 when this runs on Linux, but only as an artefact of
#:   the emulation: the child wrote cp932 and a UTF-8 locale cannot read it,
#:   where Windows' own locale could. It is not the defect, and it passes now
#:   because the child writes UTF-8 and is read as UTF-8.)
STDOUTS = {
    "cp1252:surrogateescape": "\\u65e5\\u672c",
    "cp1252:strict": "\\u65e5\\u672c",
    "cp1252:replace": "??",
    "cp932:strict": NAME,
    "utf-8:strict": NAME,
}

#: `PYTHONIOENCODING=<one of these>` is what the tests below write.
ENCODINGS = pytest.mark.parametrize("encoding", sorted(STDOUTS))


def printed(encoding: str, text: str) -> bytes:
    """`text` as bytes a stdout in `encoding` writes it."""
    return text.encode(encoding.split(":")[0])


def run_in(script: Path, *args: str, encoding: str | None, tmp_path: Path,
           cwd: Path | None = None, changes: dict | None = None):
    """`(exit code, stdout bytes, stderr bytes)` of one run, the validators'
    words in the stdout. `cwd` is the project, because `update-shape.py` is
    run from where it is and a validator is run from the root it names."""
    return run_tool_bytes(script, *args, encoding=encoding, tmp_path=tmp_path,
                          cwd=cwd, changes=changes)


# --- the projects -----------------------------------------------------------

def rename_to_a_name_no_western_code_page_holds(project: Path) -> str:
    """Rename the project's display name to `NAME` and commit it on its own
    branch; returns the sha it left HEAD at. `project.yaml` is edited as bytes,
    whatever line ending the clone has."""
    manifest = project / "project.yaml"
    body = manifest.read_bytes()
    line, renamed = (f'\nname: "{name}"'.encode("utf-8")
                     for name in (PROJECT, NAME))
    assert body.count(line) == 1, body
    manifest.write_bytes(body.replace(line, renamed))
    git("checkout", "-q", "-b", WORKING_BRANCH, cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q",
        "-am", "A display name no Western code page holds", cwd=project)
    return git("rev-parse", "HEAD", cwd=project).stdout.strip()


@pytest.fixture(scope="module")
def advanced(scaffolded, tmp_path_factory) -> str:
    """A real new commit on the spec leg's bare remote; returns its sha."""
    work = tmp_path_factory.mktemp("validator-child-spec") / f"{PROJECT}-spec"
    proc = subprocess.run(
        ["git", "clone", "-q",
         str(scaffolded["remotes"] / f"{PROJECT}-spec.git"), str(work)],
        capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    (work / "NEW-CONTRACT.md").write_text("# a contract the leg gained\n")
    git("add", "--", "NEW-CONTRACT.md", cwd=work)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm",
        "Advance the spec leg", cwd=work)
    git("push", "-q", "origin", f"HEAD:refs/heads/{ADVANCE_BRANCH}", cwd=work)
    return git("rev-parse", "HEAD", cwd=work).stdout.strip()


@pytest.fixture(scope="module")
def upstream_and_project(tmp_path_factory) -> dict:
    """A clone of this repository at A, a project scaffolded from it, and B,
    which changes `scripts/validate-manifest.py` -- the validator that prints
    the display name -- so `apply` has a copy to rewrite and then to run."""
    _base, upstream, commit_a, clone = scaffold_upstream_and_project(
        tmp_path_factory, "validator-child-update")
    commit_b = commit_upstream_changes(
        upstream, "Fix the manifest validator",
        {CHANGED_SOURCE: UPSTREAM_FIX_LINE})
    assert commit_a != commit_b
    return {"upstream": upstream, "clone": clone, "a": commit_a, "b": commit_b}


def bump_arguments(project: Path, scaffolded: dict, to: str) -> tuple:
    return ("--root", str(project), "--leg", "spec", "--to", to,
            "--local-remote-dir", str(scaffolded["remotes"]))


def update_arguments(project: Path, shape: dict) -> tuple:
    return ("apply", "--root", str(project), "--yes",
            "--upstream", str(shape["upstream"]), "--at", shape["b"],
            "--branch", UPDATE_BRANCH)


# --- a real bump -------------------------------------------------------------

def assert_the_bump_landed(project: Path, before: str, advanced: str,
                           code: int, stdout: bytes, stderr: bytes) -> None:
    """Exit 0, ONE commit, the gitlink at the new commit, the working tree
    clean. Not the words: a bump that exits 0 and wrote nothing is no pass."""
    shown = (stdout + stderr).decode("utf-8", "replace")
    assert code == 0, shown
    assert b"Traceback" not in stderr and b"UnicodeEncodeError" not in stdout, \
        shown
    assert git("rev-list", "--count", f"{before}..HEAD",
               cwd=project).stdout.strip() == "1", shown
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == \
        advanced
    assert load_yaml(project / "contracts" / "spec-pin.yaml")["commit"] == \
        advanced
    assert git("status", "--porcelain", cwd=project).stdout == ""


@ENCODINGS
def test_a_real_bump_of_a_project_named_in_japanese_lands_under_any_stdout(
        project, scaffolded, advanced, tmp_path, encoding):
    """On 60d08a1 the two cp1252 runs exited 2 with `REFUSED
    bump-leg-validators-red` and `UnicodeEncodeError: 'charmap' codec can't
    encode characters`, every byte rolled back, the pins never at fault.

    The validator's `manifest ok: <name>` reaches the stdout the tool was run
    on: as it is where that stdout holds the name, escaped where it does not."""
    before = rename_to_a_name_no_western_code_page_holds(project)
    code, stdout, stderr = run_in(
        BUMP, *bump_arguments(project, scaffolded, advanced),
        encoding=encoding, tmp_path=tmp_path)
    assert_the_bump_landed(project, before, advanced, code, stdout, stderr)
    shown = printed(encoding, f"manifest ok: {STDOUTS[encoding]}")
    assert shown in stdout, stdout
    assert b"pins ok" in stdout, stdout
    assert b"bump-leg-validators-red" not in stdout + stderr


@ENCODINGS
def test_a_dry_run_bump_is_unchanged_by_it(project, scaffolded, tmp_path,
                                           encoding):
    """`--dry-run` runs no validator, so there is no child and nothing here to
    change; the run still exits the way it did and names the project."""
    before = rename_to_a_name_no_western_code_page_holds(project)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    code, stdout, stderr = run_in(
        BUMP, *bump_arguments(project, scaffolded, pinned), "--dry-run",
        encoding=encoding, tmp_path=tmp_path)
    assert b"Traceback" not in stderr, stderr
    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == before
    assert printed(encoding, STDOUTS[encoding]) in stdout, stdout


# --- update-shape.py apply ---------------------------------------------------

def assert_the_update_landed(project: Path, shape: dict, before: str,
                             code: int, stdout: bytes, stderr: bytes) -> None:
    """Exit 0, the copy rewritten, the pin at B, ONE commit on the branch."""
    shown = (stdout + stderr).decode("utf-8", "replace")
    assert code == 0, shown
    assert b"Traceback" not in stderr and b"UnicodeEncodeError" not in stdout, \
        shown
    assert git("symbolic-ref", "--short", "HEAD",
               cwd=project).stdout.strip() == UPDATE_BRANCH
    assert git("rev-list", "--count", f"{before}..HEAD",
               cwd=project).stdout.strip() == "1", shown
    # The COMMITTED blob, not the upstream's working-tree file: `apply` writes
    # the blob, and a Windows checkout converts that file to CRLF
    # (`test_update_shape.py` compares the same way).
    upstream_copy = subprocess.run(
        ["git", "show", f"{shape['b']}:{CHANGED_SOURCE}"],
        cwd=str(shape["upstream"]), capture_output=True, check=True).stdout
    assert (project / CHANGED).read_bytes() == upstream_copy
    assert shape["b"] in (project / "contracts" / "shape-pin.yaml"
                          ).read_text(encoding="utf-8")


@pytest.fixture
def shape_root(upstream_and_project, tmp_path) -> Path:
    """A private, mutable copy of the project as it was scaffolded at A."""
    target = tmp_path / PROJECT
    shutil.copytree(upstream_and_project["clone"], target, symlinks=True)
    return target


@ENCODINGS
def test_an_apply_on_a_project_named_in_japanese_lands_under_any_stdout(
        upstream_and_project, shape_root, tmp_path, encoding):
    """On 60d08a1 the two cp1252 runs exited 2 with `REFUSED
    update-validators-red: after the rewrite, scripts/validate-manifest.py
    refused.` and the child's `UnicodeEncodeError` above it, every byte rolled
    back. The child writes into the stdout the tool is run on, so each name is
    in the encoding that stdout was told."""
    before = rename_to_a_name_no_western_code_page_holds(shape_root)
    code, stdout, stderr = run_in(
        UPDATE, *update_arguments(shape_root, upstream_and_project),
        encoding=encoding, tmp_path=tmp_path)
    assert_the_update_landed(shape_root, upstream_and_project, before, code,
                             stdout, stderr)
    shown = printed(encoding, f"manifest ok: {STDOUTS[encoding]}")
    assert shown in stdout, stdout
    assert b"pins ok" in stdout, stdout
    assert b"update-validators-red" not in stdout + stderr


# --- a stdout that is ASCII, and a locale that is not UTF-8 -----------------

def c_locale() -> dict:
    """What gives a redirected stdout `ascii` with `surrogateescape` on POSIX,
    and a locale whose codec is not UTF-8: `LC_ALL=C PYTHONUTF8=0`.
    `PYTHONUTF8=0` because the C locale turns UTF-8 mode on, and so does 3.15
    everywhere."""
    return {"LC_ALL": "C", "PYTHONUTF8": "0"}


def c_locale_or_skip(tmp_path: Path) -> dict:
    """`c_locale()`, once a child has said that it really gives a redirected
    stdout `ascii` with `surrogateescape` and reads with a codec that is not
    UTF-8. A platform that reads UTF-8 under those variables (macOS) has no
    such locale to reproduce this in, and skips -- as `test_git_output_decoding`
    does -- rather than failing."""
    proc = subprocess.run(
        [sys.executable, "-c",
         "import codecs, locale, sys; "
         "print(codecs.lookup(sys.stdout.encoding).name, sys.stdout.errors, "
         "codecs.lookup(locale.getpreferredencoding(False)).name)"],
        capture_output=True, env=child_environ(tmp_path, None, c_locale()),
        stdin=subprocess.DEVNULL, check=True)
    codec, errors, locale_codec = proc.stdout.decode("ascii").split()
    if locale_codec == "utf-8":
        pytest.skip("this platform reads a child's output as UTF-8 under "
                    "LC_ALL=C PYTHONUTF8=0, so there is no non-UTF-8 locale")
    if (codec, errors) != ("ascii", "surrogateescape"):
        pytest.skip(f"this Python gives a redirected stdout {codec} with the "
                    f"{errors} handler, not ascii with surrogateescape")
    return c_locale()


@pytest.mark.skipif(os.name == "nt", reason="the C locale is POSIX's")
def test_a_real_bump_reads_the_validators_as_utf_8_whatever_the_locale_is(
        project, scaffolded, advanced, tmp_path):
    """No `PYTHONIOENCODING` at all: Python chooses. Under `LC_ALL=C
    PYTHONUTF8=0` a stdout is `ascii` with `surrogateescape`, which cannot hold
    the name -- and cannot hold the `…` (U+2026) `validate-pins.py` prints
    either, so on 60d08a1 this bump was refused at the PINS validator,
    whatever the project is called (the first of the two to run).

    The child writes UTF-8 now, so the words must be READ as UTF-8 and not with
    the locale's codec, which is ASCII here and which `errors="replace"` would
    turn into U+FFFD six times over: the name arrives as the two characters it
    is, and only then is escaped by the tool's own stdout."""
    changes = c_locale_or_skip(tmp_path)
    before = rename_to_a_name_no_western_code_page_holds(project)
    code, stdout, stderr = run_in(
        BUMP, *bump_arguments(project, scaffolded, advanced),
        encoding=None, tmp_path=tmp_path, changes=changes)
    assert_the_bump_landed(project, before, advanced, code, stdout, stderr)
    assert b"manifest ok: \\u65e5\\u672c" in stdout, stdout
    assert b"\\ufffd" not in stdout and b"\xef\xbf\xbd" not in stdout, stdout


@pytest.mark.skipif(os.name == "nt", reason="the C locale is POSIX's")
def test_an_apply_under_a_c_locale_lands(upstream_and_project, shape_root,
                                         tmp_path):
    """The same stdout, for the child that INHERITS it: told `ascii` and a
    handler that does not raise, it writes `…` (U+2026) and the name escaped,
    as the tool's own stdout does."""
    changes = c_locale_or_skip(tmp_path)
    before = rename_to_a_name_no_western_code_page_holds(shape_root)
    code, stdout, stderr = run_in(
        UPDATE, *update_arguments(shape_root, upstream_and_project),
        encoding=None, tmp_path=tmp_path, changes=changes)
    assert_the_update_landed(shape_root, upstream_and_project, before, code,
                             stdout, stderr)
    assert b"manifest ok: \\u65e5\\u672c" in stdout, stdout
    assert b"pins ok" in stdout, stdout


# --- a display name no UTF-8 text can hold (#280) ---------------------------
#
# The escape `"a\ud83db"` reads as a string holding the lone surrogate U+D83D,
# as PyYAML's own Python reader reads it. No UTF-8 stream can hold one, so the
# validator's `manifest ok` line raised: `make validate` and the doctor met a
# traceback, while the two callers above, which hand their child
# `backslashreplace` (#254), passed the project. The validator now reports the
# name as a finding, and all four launchers stop at it.

#: The display name as the YAML spells it, and the finding the project's own
#: validator reports for it.
SURROGATE_ESCAPE = "a\\ud83db"
SURROGATE_FINDING = (b"FINDING manifest-name: name is 'a\\ud83db', which "
                     b"holds U+D83D, a lone surrogate")


def rename_to_a_lone_surrogate(project: Path) -> str:
    """Rename the display name to `SURROGATE_ESCAPE` and commit it on its own
    branch; returns the sha it left HEAD at. Edited as bytes."""
    manifest = project / "project.yaml"
    body = manifest.read_bytes()
    line = f'\nname: "{PROJECT}"'.encode("ascii")
    assert body.count(line) == 1, body
    manifest.write_bytes(body.replace(
        line, f'\nname: "{SURROGATE_ESCAPE}"'.encode("ascii")))
    git("checkout", "-q", "-b", WORKING_BRANCH, cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q",
        "-am", "A display name holding a lone surrogate", cwd=project)
    return git("rev-parse", "HEAD", cwd=project).stdout.strip()


def assert_stopped_at_the_finding(code: int, stdout: bytes, stderr: bytes,
                                  exit_code: int, refusal: bytes = b"") -> None:
    """The launcher exits `exit_code` with the validator's finding in its
    output, `refusal` named where it has one, and no traceback anywhere."""
    both = stdout + stderr
    shown = both.decode("utf-8", "backslashreplace")
    assert code == exit_code, shown
    assert SURROGATE_FINDING in both, shown
    assert refusal in both, shown
    assert b"Traceback" not in both and b"UnicodeEncodeError" not in both, \
        shown
    assert b"manifest ok" not in both, shown


def test_a_real_bump_of_a_project_whose_name_holds_a_surrogate_is_refused(
        project, scaffolded, advanced, tmp_path):
    """On c7c02fa this bump exited 0: its child printed `manifest ok:
    a\\ud83db`, and the commit it made read `Bump spec leg to <sha> in a?b`,
    the name lost to the `replace` its message is written with. It is the
    validator's finding now, and every byte is rolled back."""
    before = rename_to_a_lone_surrogate(project)
    pinned = git("rev-parse", "HEAD:spec", cwd=project).stdout.strip()
    code, stdout, stderr = run_in(
        BUMP, *bump_arguments(project, scaffolded, advanced),
        encoding="utf-8:strict", tmp_path=tmp_path)
    assert_stopped_at_the_finding(code, stdout, stderr, 2,
                                  b"bump-leg-validators-red")
    assert git("rev-parse", "HEAD", cwd=project).stdout.strip() == before
    assert git("rev-parse", "HEAD:spec", cwd=project).stdout.strip() == pinned
    assert git("status", "--porcelain", cwd=project).stdout == ""


def test_an_apply_on_a_project_whose_name_holds_a_surrogate_is_refused(
        upstream_and_project, shape_root, tmp_path):
    """On c7c02fa `apply` exited 0 and printed `manifest ok: a\\ud83db`. The
    validator it runs is the one B wrote, which carries the finding."""
    before = rename_to_a_lone_surrogate(shape_root)
    copy = (shape_root / CHANGED).read_bytes()
    code, stdout, stderr = run_in(
        UPDATE, *update_arguments(shape_root, upstream_and_project),
        encoding="utf-8:strict", tmp_path=tmp_path)
    assert_stopped_at_the_finding(code, stdout, stderr, 2,
                                  b"update-validators-red")
    assert git("rev-parse", "HEAD", cwd=shape_root).stdout.strip() == before
    assert (shape_root / CHANGED).read_bytes() == copy, "rolled back"
    assert git("status", "--porcelain", cwd=shape_root).stdout == ""


def test_the_doctor_quotes_the_finding_for_a_name_holding_a_surrogate(
        project, tmp_path):
    """On c7c02fa the `manifest` row quoted the traceback's last line,
    `UnicodeEncodeError: 'utf-8' codec can't encode character '\\ud83d'`."""
    rename_to_a_lone_surrogate(project)
    code, stdout, stderr = run_in(
        REPO / "shape-doctor.py", "--root", str(project),
        encoding="utf-8:strict", tmp_path=tmp_path)
    assert_stopped_at_the_finding(code, stdout, stderr, 1)
    row = [line for line in stdout.splitlines() if SURROGATE_FINDING in line]
    assert len(row) == 1 and row[0].split()[:2] == [b"FINDING", b"manifest"], \
        stdout.decode("utf-8", "backslashreplace")
    assert b"INVALID (manifest)" in stdout


@pytest.mark.skipif(shutil.which("make") is None, reason="needs `make` on PATH")
def test_make_validate_stops_at_the_finding_for_a_surrogate(project, tmp_path):
    """On c7c02fa `make validate` stopped on the validator's traceback."""
    rename_to_a_lone_surrogate(project)
    proc = subprocess.run(["make", "validate"], cwd=str(project),
                          capture_output=True, stdin=subprocess.DEVNULL,
                          env=child_environ(tmp_path, None), check=False)
    assert_stopped_at_the_finding(proc.returncode, proc.stdout, proc.stderr, 2)


# --- the environment each tool builds ---------------------------------------

#: What a child prints: `manifest ok: 日本`, spelled with `chr` so the program
#: is ASCII whatever it travels in. A child whose stdout cannot encode it
#: raises, exits 1 and leaves the traceback on stderr, as `validate-manifest.py`
#: did.
CHILD = ("import sys; sys.stdout.write('manifest ok: ' + chr(0x65e5) + "
         "chr(0x672c) + '\\n'); sys.stdout.flush()")


def child_writes(env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", CHILD], env=env,
                          capture_output=True, stdin=subprocess.DEVNULL,
                          check=False)


def stream_for(encoding: str, errors: str):
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors=errors,
                            newline="\n")


def test_a_captured_child_is_told_utf_8_whatever_the_operator_set(monkeypatch):
    """The pipe is the tool's, and an operator's `PYTHONIOENCODING` describes
    their own stdout. Replaced, and nothing else touched."""
    monkeypatch.setenv("PYTHONIOENCODING", "cp1252:strict")
    monkeypatch.setenv("SHAPE_TEST_ONLY", "kept")
    before = dict(os.environ)
    env = shape_materialize.captured_child_environment()
    assert env["PYTHONIOENCODING"] == "utf-8:backslashreplace"
    assert env["PYTHONIOENCODING"] == \
        shape_materialize.CAPTURED_CHILD_IOENCODING
    assert env["SHAPE_TEST_ONLY"] == "kept"
    assert dict(os.environ) == before, "this process's own environment"
    assert {key for key in env if key != "PYTHONIOENCODING"} == \
        {key for key in before if key != "PYTHONIOENCODING"}


def test_a_captured_child_is_told_utf_8_when_nothing_was_set(monkeypatch):
    monkeypatch.delenv("PYTHONIOENCODING", raising=False)
    assert shape_materialize.captured_child_environment()[
        "PYTHONIOENCODING"] == "utf-8:backslashreplace"


#: `(stream encoding, the handler its stdout has now, what the child is told)`.
#: A handler that never raises is kept; every other one is `backslashreplace`:
#: `strict` and `surrogateescape` raise on the name, and the handler
#: `escape_what_stdout_cannot_encode` registers is one the child does not have.
INHERITED = (
    ("cp1252", "strict", "cp1252:backslashreplace"),
    ("cp1252", "surrogateescape", "cp1252:backslashreplace"),
    ("cp1252", "surrogatepass", "cp1252:backslashreplace"),
    ("cp1252", "replace", "cp1252:replace"),
    ("cp1252", "ignore", "cp1252:ignore"),
    ("cp1252", "backslashreplace", "cp1252:backslashreplace"),
    ("cp1252", "xmlcharrefreplace", "cp1252:xmlcharrefreplace"),
    ("cp1252", "namereplace", "cp1252:namereplace"),
    ("cp932", "strict", "cp932:backslashreplace"),
    ("utf-8", "strict", "utf-8:backslashreplace"),
    ("utf-8", "surrogateescape", "utf-8:backslashreplace"),
    ("utf-8", "replace", "utf-8:replace"),
    # What CPython calls the locale's codec under a C locale; the child is
    # given the name the codec registry knows it by.
    ("ANSI_X3.4-1968", "strict", "ascii:backslashreplace"),
    ("latin-1", "backslashreplace", "iso8859-1:backslashreplace"),
)


@pytest.mark.parametrize("encoding, errors, told", INHERITED)
def test_an_inherited_child_is_told_the_stdouts_own_encoding(
        monkeypatch, encoding, errors, told):
    monkeypatch.setenv("PYTHONIOENCODING", "something-the-operator-set")
    stream = stream_for(encoding, errors)
    env = shape_materialize.inherited_child_environment(stream)
    assert env["PYTHONIOENCODING"] == told
    assert dict(os.environ)["PYTHONIOENCODING"] == \
        "something-the-operator-set", "this process's own environment"


def test_the_stdout_the_tool_has_reconfigured_is_what_the_child_is_told():
    """The order the tools run in: `main()` calls the helper first, and the
    child is built long after. A `strict` stdout is `backslashreplace` by then,
    and a `surrogateescape` one holds a handler registered in THIS process,
    which a child must not be asked to find."""
    for errors in ("strict", "surrogateescape"):
        stream = stream_for("cp1252", errors)
        shape_materialize.escape_what_stdout_cannot_encode(stream)
        assert (shape_materialize.inherited_child_environment(stream)
                ["PYTHONIOENCODING"] == "cp1252:backslashreplace"), errors


@pytest.mark.parametrize("encoding, errors, told", [
    case for case in INHERITED if case[0] in ("cp1252", "cp932", "utf-8")])
def test_a_child_given_that_environment_can_print_the_name(
        encoding, errors, told):
    """What the strings above are FOR: a real child, in that environment,
    writes the name without raising, in the stdout's encoding. A handler this
    process registered and the child does not know would still START the child
    and fail here, at the first character it cannot encode."""
    env = shape_materialize.inherited_child_environment(
        stream_for(encoding, errors))
    proc = child_writes(env)
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    codec = told.split(":")[0]
    handler = told.split(":")[1]
    expected = f"manifest ok: {NAME}\n".encode(codec, handler)
    assert proc.stdout == expected.replace(b"\n", os.linesep.encode("ascii"))


def test_a_stdout_that_is_not_there_leaves_the_environment_alone(monkeypatch):
    """`pythonw` has no stdout, and a replaced stream may have no encoding.
    Nothing is inherited, so nothing is told."""
    monkeypatch.setenv("PYTHONIOENCODING", "kept")
    monkeypatch.setattr(sys, "stdout", None)
    assert shape_materialize.inherited_child_environment()[
        "PYTHONIOENCODING"] == "kept"

    class Replaced:
        encoding = None
        errors = "strict"

    assert shape_materialize.inherited_child_environment(Replaced())[
        "PYTHONIOENCODING"] == "kept"
    Replaced.encoding = "not-a-codec"
    assert shape_materialize.inherited_child_environment(Replaced())[
        "PYTHONIOENCODING"] == "kept"


def test_the_inherited_environment_is_read_from_stdout_when_none_is_given(
        monkeypatch):
    monkeypatch.setattr(sys, "stdout", stream_for("cp1252", "replace"))
    assert shape_materialize.inherited_child_environment()[
        "PYTHONIOENCODING"] == "cp1252:replace"


def test_the_handler_a_child_would_not_know_is_never_passed_on():
    """A handler this process registered is not in the child, which still
    starts under `PYTHONIOENCODING=<encoding>:<it>` and fails at the first
    character it cannot encode -- the failure this whole change is about,
    one level down. Asserted on the real child, so the claim is the one made."""
    handler = shape_materialize.SURROGATEESCAPE_THEN_BACKSLASHREPLACE
    env = {**os.environ, "PYTHONIOENCODING": f"cp1252:{handler}"}
    broken = child_writes(env)
    assert broken.returncode != 0 and b"LookupError" in broken.stderr, \
        broken.stderr
    stream = stream_for("cp1252", "surrogateescape")
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    assert stream.errors == handler
    told = shape_materialize.inherited_child_environment(stream)
    assert handler not in told["PYTHONIOENCODING"]
    assert child_writes(told).returncode == 0


# --- no third caller goes without ------------------------------------------

#: The shipped tools that run a Python child of the standard's own, and so
#: build its environment. `shape-doctor.py` sets UTF-8 itself (it reads the
#: pipe as UTF-8 too); the other two use the helpers above.
LAUNCHERS = {
    "scripts/bump-leg.py": "captured_child_environment",
    "update-shape.py": "inherited_child_environment",
}


def interpreter_runs(tree: ast.AST) -> list[ast.Call]:
    """Every `subprocess.run([sys.executable, ...])` in `tree`."""
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "run"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "subprocess" and node.args):
            continue
        argv = node.args[0]
        if (isinstance(argv, ast.List) and argv.elts
                and ast.unparse(argv.elts[0]) == "sys.executable"):
            found.append(node)
    return found


@pytest.mark.parametrize("tool", sorted(LAUNCHERS))
def test_the_tools_that_run_the_projects_validators_give_them_an_environment(
        tool):
    """The next validator a tool runs gets the same environment or fails here:
    a bare `subprocess.run([sys.executable, ...])` takes whatever the operator's
    shell holds, which is the defect."""
    tree = ast.parse((REPO / tool).read_text(encoding="utf-8"))
    runs = interpreter_runs(tree)
    assert runs, f"{tool} no longer runs the interpreter; this guard reads nothing"
    for call in runs:
        env = [keyword.value for keyword in call.keywords
               if keyword.arg == "env"]
        assert env and LAUNCHERS[tool] in ast.unparse(env[0]), (
            f"{tool}:{call.lineno} runs the interpreter without "
            f"`env={LAUNCHERS[tool]}()`")
