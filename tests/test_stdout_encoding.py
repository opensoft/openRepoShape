# SPDX-License-Identifier: Apache-2.0
"""A name stdout cannot encode is printed escaped, never raised on (#214).

`adopt-project.py plan` wrote the plan file and then printed its report with
plain `print`s, so a source file named `日本.md` raised `UnicodeEncodeError`
in the middle of the table on a stdout in cp1252 -- which is what Windows
gives any stdout that is not the console itself: a file, a pipe to `tee`,
CI, an agent running the tool. `plan` exited 1 with a traceback, after the
plan was on disk and before `plan written to` and the questions it exists to
ask. The same raise was in `check`, `shape-doctor.py`, `update-shape.py`,
`scaffold-project.py`, `scripts/family.py`, `scripts/bump-leg.py` and the
`bootstrap` shim at the root of this repository, wherever a path or a
person's text was printed.

Each now calls `shape_materialize.escape_what_stdout_cannot_encode` first:
a `strict` stdout becomes `backslashreplace`, and a `surrogateescape` one
becomes the handler registered beside it, which writes an escaped byte back
as that byte and escapes the rest as `backslashreplace` does. Either one
writes what the old handler would have written and escapes only what it
would have raised on. Every run here is made under three
`PYTHONIOENCODING`s, and answered in BYTES, decoded strictly in the encoding
the run was given, so a byte the stdout could not have held fails the test:
- `cp1252:surrogateescape`, what Windows gives a stdout that is not the
  console: the ANSI code page, and the handler CPython gives every Windows
  stdout by default (`config_get_stdio_errors` in `Python/initconfig.c`).
  Emulated, because CI's own Windows job runs in UTF-8 mode and never sees it.
- `cp1252:strict`, what `PYTHONIOENCODING=cp1252` gives, with no handler named.
- `utf-8:strict`, the control: every name fits.

Those three are emulations: each names its `PYTHONIOENCODING`. Two tests ask
Python itself instead, with NO `PYTHONIOENCODING` at all, and take whatever it
gives a redirected stdout. On POSIX that is `LC_ALL=C PYTHONUTF8=0`, which
gives `ascii:surrogateescape`. On Windows it is `PYTHONUTF8=0`, which gives
the ANSI code page and `surrogateescape`, the default no other test here
reaches (3.15 makes UTF-8 mode the default, and CI's job sets it). A child
first reports what its stdout really is, and the test is SKIPPED, never
failed, when that is not `surrogateescape` or when its code page holds the
name. The Windows one runs only on Windows, so only CI runs it.
"""

from __future__ import annotations

import codecs
import io
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, ORG, PROJECT, REPO, SCAFFOLD,
                      blank_unnamed_pin_sources, git, make_source_repo)

sys.path.insert(0, str(REPO / "scripts"))
import shape_materialize  # noqa: E402
from repo_shape import load_yaml  # noqa: E402

DOCTOR = REPO / "shape-doctor.py"
UPDATE = REPO / "update-shape.py"
FAMILY = REPO / "scripts" / "family.py"
BUMP = REPO / "scripts" / "bump-leg.py"
BOOTSTRAP = REPO / "bootstrap"

#: In no Western code page: cp1252 holds `é` and `—`, and not this.
NAME = "日本"
#: A file `plan` answers (`extension-majority`: spec), so it is in the table.
ANSWERED = f"{NAME}.md"
#: A file `plan` asks about (`ambiguous-notebooks`), so the question list
#: prints it too: the part of the report somebody has to act on.
ASKED = "東京.ipynb"
#: The first words of that question, from `contracts/path-classification.yaml`.
NOTEBOOK_QUESTION = "Is this notebook"
#: Every `PYTHONIOENCODING` the runs below are made under.
ENCODINGS = ("cp1252:surrogateescape", "cp1252:strict", "utf-8:strict")


def shown(text: str, encoding: str) -> str:
    """`text` as a stdout in `encoding` now prints it: as it is where the
    encoding holds it, and `\\uXXXX` where it does not."""
    codec = encoding.split(":")[0]
    return text.encode(codec, "backslashreplace").decode(codec)


def run_tool(script: Path, *args: str, encoding: str, tmp_path: Path,
             cwd: Path | None = None) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run with its stdout in `encoding`.

    BYTES, then decoded STRICTLY in that encoding: `conftest.run_script`
    decodes in the parent's own locale, which is not what the child was
    told to write. Windows writes `\\r\\n`; read as `\\n`.
    """
    code, stdout, stderr = run_tool_bytes(script, *args, encoding=encoding,
                                          tmp_path=tmp_path, cwd=cwd)
    codec = encoding.split(":")[0]
    return (code, stdout.decode(codec).replace("\r\n", "\n"),
            stderr.decode(codec, "replace").replace("\r\n", "\n"))


def child_environ(tmp_path: Path, encoding: str | None,
                  changes: dict[str, str] | None = None) -> dict[str, str]:
    """The environment of one run: `run_script`'s -- no lane, no pin-source
    override, an identity git can commit with -- plus an empty
    `AGENT_PROTOCOL_ROOT`, so a `workspace.yaml` on the machine running the
    suite changes nothing here.

    `encoding` is the `PYTHONIOENCODING` the child is given. None gives it
    NONE, under any spelling of the name, so Python chooses its own stdout
    encoding and handler. `changes` are applied last.
    """
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "",
         "AGENT_PROTOCOL_ROOT": str(tmp_path / "agent-protocol")}, {})
    env = {key: value for key, value in env.items()
           if key.upper() != "PYTHONIOENCODING"}
    if encoding is not None:
        env["PYTHONIOENCODING"] = encoding
    env.update(changes or {})
    for key, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                       ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                       ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                       ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")):
        env.setdefault(key, value)
    (tmp_path / "agent-protocol").mkdir(exist_ok=True)
    return env


def run_tool_bytes(script: Path, *args: str, encoding: str | None,
                   tmp_path: Path, cwd: Path | None = None,
                   changes: dict[str, str] | None = None
                   ) -> tuple[int, bytes, bytes]:
    """`(exit, stdout, stderr)` of one run, as the bytes the child wrote,
    under `child_environ(tmp_path, encoding, changes)`."""
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True,
                          env=child_environ(tmp_path, encoding, changes),
                          cwd=None if cwd is None else str(cwd),
                          stdin=subprocess.DEVNULL, check=False)
    return proc.returncode, proc.stdout, proc.stderr


# --- the repro of #214 -------------------------------------------------------

def plan_arguments(tmp_path: Path) -> tuple[Path, tuple[str, ...]]:
    """`(the plan file, the arguments)` of a `plan` over a source holding
    `日本.md` (answered) and `東京.ipynb` (asked)."""
    source = make_source_repo(tmp_path / "Thing", tree={
        "README.md": "# Thing\n", ANSWERED: "x\n", ASKED: "{}\n",
        "src/main.py": "x = 1\n"}, edits=())
    out = tmp_path / "adoption-plan.yaml"
    return out, ("plan", "--source", str(source), "--project", "Northwind",
                 "--org", ORG, "--elected-by", "Test Human",
                 "--elected-on", "2026-09-02", "--out", str(out))


def assert_plan_reported_every_name(out: Path, code: int, stdout: str,
                                    stderr: str, encoding: str) -> None:
    """Exit 0, `plan written to`, both entries in the plan, and each name in
    the table and in the question list: as it is where the stdout's encoding
    holds it, escaped where it does not."""
    assert code == 0 and "Traceback" not in stderr, stdout + stderr
    assert f"\nplan written to {shown(str(out), encoding)}\n" in stdout, stdout

    rows = {str(e["path"]): e for e in load_yaml(out)["paths"]}
    assert rows[ANSWERED]["leg"] == "spec", rows[ANSWERED]
    assert rows[ASKED]["leg"] is None, rows[ASKED]
    assert rows[ASKED]["review_required"] is True, rows[ASKED]

    table = [line for line in stdout.splitlines()
             if line.startswith(shown(ANSWERED, encoding) + " ")]
    assert len(table) == 1 and " spec " in table[0], stdout
    assert (f"\n  {shown(ASKED, encoding)}\n      {NOTEBOOK_QUESTION}"
            in stdout), stdout
    try:
        NAME.encode(encoding.split(":")[0])
    except UnicodeEncodeError:
        assert "\\u65e5\\u672c.md" in stdout, stdout
        assert NAME not in stdout, stdout


@pytest.mark.parametrize("encoding", ENCODINGS)
def test_plan_reports_every_name_whatever_its_stdout_can_encode(tmp_path,
                                                                encoding):
    """On main both cp1252 runs exited 1 in `_print_entries`, two rows into
    the table, and so did the `surrogateescape` one at 3006303, whose guard
    changed `strict` alone."""
    out, args = plan_arguments(tmp_path)
    code, stdout, stderr = run_tool(ADOPT, *args, encoding=encoding,
                                    tmp_path=tmp_path)
    assert_plan_reported_every_name(out, code, stdout, stderr, encoding)


@pytest.mark.parametrize("encoding", ("utf-8:surrogateescape",
                                      "cp1252:surrogateescape"))
@pytest.mark.skipif(os.name == "nt",
                    reason="Windows file names are UTF-16, and its "
                           "`os.fsencode` and `os.fsdecode` are UTF-8, which "
                           "has no byte 0xff, so the byte path below raises "
                           "before any directory is made")
def test_a_name_that_is_not_utf8_still_comes_out_as_its_own_bytes(tmp_path,
                                                                   encoding):
    """`plan --out` into a directory whose name holds byte 0xff, which is not
    UTF-8: Python reads it in as U+DCFF, and a `surrogateescape` stdout
    writes it back as 0xff. It still does, in the same report that shows
    `日本.md` -- escaped on cp1252 -- where plain `backslashreplace` would
    print `\\udcff` instead. POSIX only: neither Windows nor macOS holds a
    file name that is not UTF-8."""
    parent = os.path.join(os.fsencode(tmp_path), b"b\xffd")
    try:
        os.mkdir(parent)
    except (OSError, UnicodeError) as exc:
        pytest.skip(f"this filesystem holds no name that is not UTF-8: {exc}")
    if b"b\xffd" not in os.listdir(os.fsencode(tmp_path)):
        pytest.skip("this filesystem rewrote a name that is not UTF-8")
    source = make_source_repo(tmp_path / "Thing", tree={
        "README.md": "# Thing\n", ANSWERED: "x\n", "src/main.py": "x = 1\n"},
        edits=())
    out = Path(os.fsdecode(parent)) / "plan.yaml"
    code, stdout, stderr = run_tool_bytes(
        ADOPT, "plan", "--source", str(source), "--project", "Northwind",
        "--org", ORG, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--out", str(out),
        encoding=encoding, tmp_path=tmp_path)
    assert code == 0 and b"Traceback" not in stderr, stdout + stderr
    written = [line for line in stdout.splitlines()
               if line.startswith(b"plan written to ")]
    assert len(written) == 1, stdout
    assert written[0].endswith(b"/b\xffd/plan.yaml"), written
    assert b"\\udcff" not in stdout, stdout
    codec = encoding.split(":")[0]
    assert shown(ANSWERED, encoding).encode(codec) in stdout, stdout


# --- no PYTHONIOENCODING at all: the default Python chooses for itself ------

#: What a child reports its own redirected stdout to be: the codec's name, and
#: its error handler.
STDOUT_PROBE = ("import codecs, sys; "
                "print(codecs.lookup(sys.stdout.encoding).name, "
                "sys.stdout.errors)")


def plan_on_the_default_stdout(tmp_path: Path, changes: dict[str, str]) -> None:
    """`plan` over `日本.md` in a child given NO `PYTHONIOENCODING`, only
    `changes`, so Python chooses its stdout's encoding and handler itself.

    A first child reports what that stdout really is. The test goes on only
    when it is `surrogateescape` over a code page that cannot hold the name:
    anything else is a platform this does not test, and is a skip with its
    reason, never a failure. On 3006303, which left `surrogateescape` alone,
    this run exited 1 in `_print_entries` with `UnicodeEncodeError`.
    """
    probe = subprocess.run(
        [sys.executable, "-c", STDOUT_PROBE], capture_output=True,
        env=child_environ(tmp_path, None, changes),
        stdin=subprocess.DEVNULL, check=True)
    codec, errors = probe.stdout.decode("ascii").split()
    if errors != "surrogateescape":
        pytest.skip(f"this Python gives a redirected stdout {codec} with the "
                    f"{errors} handler, not the surrogateescape default")
    try:
        NAME.encode(codec)
    except UnicodeEncodeError:
        pass
    else:
        pytest.skip(f"this Python gives a redirected stdout {codec}, which "
                    f"holds {NAME!r}, so no name here is one it cannot encode")
    out, args = plan_arguments(tmp_path)
    code, stdout, stderr = run_tool_bytes(ADOPT, *args, encoding=None,
                                          tmp_path=tmp_path, changes=changes)
    assert_plan_reported_every_name(
        out, code, stdout.decode(codec).replace("\r\n", "\n"),
        stderr.decode(codec, "replace").replace("\r\n", "\n"), codec)


@pytest.mark.skipif(os.name == "nt", reason="the C locale is POSIX's")
def test_plan_on_the_posix_default_stdout(tmp_path):
    """`LC_ALL=C PYTHONUTF8=0` is a default POSIX gives itself: stdout in
    `ascii` with `surrogateescape`. `PYTHONUTF8=0` because the C locale turns
    UTF-8 mode on, and so does 3.15 everywhere. A Python that gives anything
    else under it, a C locale that reads UTF-8 for one, skips."""
    plan_on_the_default_stdout(tmp_path, {"LC_ALL": "C", "PYTHONUTF8": "0"})


@pytest.mark.skipif(sys.platform != "win32",
                    reason="the default this is about is Windows' own")
def test_plan_on_the_windows_default_stdout(tmp_path):
    """Windows' own default for a stdout that is not the console: the ANSI
    code page (cp1252 on a Western-European install) with `surrogateescape`,
    which CPython gives every Windows stdout. `PYTHONUTF8=0`, because CI's job
    sets `PYTHONUTF8=1` and 3.15 turns UTF-8 mode on by default. A Windows
    whose code page holds `日本` (cp932 does) skips. Runs only on Windows,
    which here means CI: nothing else reaches Windows' default."""
    plan_on_the_default_stdout(tmp_path, {"PYTHONUTF8": "0"})


# --- the same raise, in every other tool that printed a name ---------------

def _adopt_check(tmp_path: Path, request) -> tuple:
    """`check` names the source path in `WHAT WILL HAPPEN, against`."""
    source = make_source_repo(tmp_path / NAME / "Thing", tree={
        "README.md": "# Thing\n", "src/main.py": "x = 1\n"}, edits=())
    plan = tmp_path / "adoption-plan.yaml"
    code, stdout, stderr = run_tool(
        ADOPT, "plan", "--source", str(source), "--project", "Thing",
        "--org", ORG, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--out", str(plan),
        encoding="utf-8:strict", tmp_path=tmp_path)
    assert code == 0, stdout + stderr
    return ADOPT, ("check", "--plan", str(plan))


def _doctor(tmp_path: Path, request) -> tuple:
    """The doctor's `root` line names the root as it is. (Its rows spell a
    name too since #785: as itself where stdout can show it, escaped in a
    command and `?` in a sentence where it cannot.)"""
    root = tmp_path / NAME
    root.mkdir()
    (root / "README.md").write_text("# here\n", encoding="utf-8")
    return DOCTOR, ("--root", str(root))


def _update_shape_check(tmp_path: Path, request) -> tuple:
    """`check` prints the `--root` it was given as its first line."""
    project = request.getfixturevalue("project")
    root = tmp_path / NAME / project.name
    root.parent.mkdir()
    shutil.move(str(project), str(root))
    return UPDATE, ("check", "--root", str(root), "--upstream", str(REPO))


def _scaffold_dry_run(tmp_path: Path, request) -> tuple:
    """A display name and an elector are a person's text. Local remotes,
    so nothing asks `gh` whether the repositories exist."""
    return SCAFFOLD, ("--org", ORG, "--project", "Borea", "--name", NAME,
                      "--elected-by", NAME, "--elected-on", "2026-09-02",
                      "--local-remote-dir", str(tmp_path / "remotes"),
                      "--dry-run")


def _family_init_dry_run(tmp_path: Path, request) -> tuple:
    """The plan's `created by` line is a person's text. `--name` is not given
    the name: the holder's own `validate-family.py` refuses one that is not a
    CamelCase token (`family.py init` asks it, #307, and refuses before the
    plan prints), so only `--created-by` can carry text no code page holds."""
    return FAMILY, ("init", "--org", ORG, "--family", "Contoso",
                    "--created-by", NAME,
                    "--local-remote-dir", str(tmp_path / "remotes"),
                    "--into", str(tmp_path / "into"), "--dry-run")


def _bump_leg_dry_run(tmp_path: Path, request) -> tuple:
    """The project's display name -- the scaffold's `--name` -- is the first
    line. On a branch, because the tool will not commit onto the tracking
    one; `--to` the commit already pinned, so it has nothing to do and says
    so. `project.yaml` is edited as bytes, whatever line ending the clone
    has."""
    project = request.getfixturevalue("project")
    manifest = project / "project.yaml"
    body = manifest.read_bytes()
    line, renamed = (f'\nname: "{name}"'.encode("utf-8")
                     for name in (PROJECT, NAME))
    assert body.count(line) == 1, body
    manifest.write_bytes(body.replace(line, renamed))
    git("checkout", "-q", "-b", "display-name", cwd=project)
    git("-c", "user.name=t", "-c", "user.email=t@t.invalid", "commit", "-q",
        "-am", "A display name no Western code page holds", cwd=project)
    pinned = git("rev-parse", "HEAD", cwd=project / "spec").stdout.strip()
    return BUMP, ("--root", str(project), "--leg", "spec", "--to", pinned,
                  "--dry-run")


def _bootstrap_shim(tmp_path: Path, request) -> tuple:
    """The `bootstrap` at this repository's root runs the canonical bootstrap
    against the directory it is run FROM, and names that directory first. A
    repository with no manifest, one that has not elected the schema, which
    is what the shim is for. Not a shape copy: no project holds it, so it
    calls the helper the six tools call, before it hands over."""
    root = tmp_path / NAME
    root.mkdir()
    git("init", "-q", cwd=root)
    return BOOTSTRAP, (), root


OTHER_TOOLS = {
    "adopt-check": _adopt_check,
    "bootstrap-shim": _bootstrap_shim,
    "bump-leg-dry-run": _bump_leg_dry_run,
    "shape-doctor": _doctor,
    "update-shape-check": _update_shape_check,
    "scaffold-dry-run": _scaffold_dry_run,
    "family-init-dry-run": _family_init_dry_run,
}


@pytest.mark.parametrize("tool", sorted(OTHER_TOOLS))
def test_every_tool_exits_alike_whatever_its_stdout_can_encode(tmp_path,
                                                               request, tool):
    """The same run under every encoding: the same exit, no traceback, and
    the name printed -- as it is under UTF-8, escaped under cp1252. On main
    every cp1252 run here exited 1 at its first `print` of the name."""
    script, args, *cwd = OTHER_TOOLS[tool](tmp_path, request)
    runs = {encoding: run_tool(script, *args, encoding=encoding,
                               tmp_path=tmp_path, cwd=cwd[0] if cwd else None)
            for encoding in ENCODINGS}
    exits = {encoding: run[0] for encoding, run in runs.items()}
    for encoding, (_code, stdout, stderr) in runs.items():
        assert "Traceback" not in stderr, (encoding, stdout + stderr)
        assert shown(NAME, encoding) in stdout, (encoding, stdout)
    assert len(set(exits.values())) == 1, (exits, runs)


# --- what the helper changes, and what it leaves alone ----------------------

def wrapper(encoding: str, errors: str) -> io.TextIOWrapper:
    return io.TextIOWrapper(io.BytesIO(), encoding=encoding, errors=errors,
                            newline="\n")


def test_a_strict_stdout_escapes_only_what_it_cannot_encode():
    """The encoding is kept: `é` and `—` are cp1252 bytes, as before."""
    stream = wrapper("cp1252", "strict")
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    stream.write(f"{ANSWERED} é —\n")
    stream.flush()
    assert stream.buffer.getvalue() == b"\\u65e5\\u672c.md \xe9 \x97\n"


@pytest.mark.parametrize("encoding, written", (
    ("utf-8", b"caf\xff\xe6\x97\xa5\xe6\x9c\xac.md \xc3\xa9 \xe2\x80\x94\n"),
    ("cp1252", b"caf\xff\\u65e5\\u672c.md \xe9 \x97\n"),
), ids=("utf-8", "cp1252"))
def test_a_surrogateescape_stdout_keeps_its_raw_bytes_and_escapes_the_rest(
        encoding, written):
    """What Windows gives every stdout, and UTF-8 mode and the C locale give
    too. A byte that was not UTF-8 when a name was read in (`caf\\xff`, held
    as U+DCFF) is written back as that byte, as `surrogateescape` writes it;
    a character the encoding cannot hold, right after it, is escaped as
    `backslashreplace` escapes it, where `surrogateescape` raised; and the
    encoding is kept. A second call changes nothing."""
    stream = wrapper(encoding, "surrogateescape")
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    assert stream.encoding == encoding
    assert (stream.errors
            == shape_materialize.SURROGATEESCAPE_THEN_BACKSLASHREPLACE)
    stream.write(f"caf\udcff{ANSWERED} é —\n")
    stream.flush()
    assert stream.buffer.getvalue() == written


def raw(byte: int) -> str:
    """The character `surrogateescape` reads the byte 0x80..0xFF in as."""
    return chr(0xDC00 + byte)


#: `(id, encoding, text, written)`. `surrogateescape` makes U+DC80..U+DCFF and
#: nothing else, so those come out as the bytes 0x80..0xFF, and every other
#: character the encoding cannot hold comes out as `backslashreplace` spells
#: it, however the two are mixed in one run. The codec hands the handler a
#: whole run of characters it cannot encode, and the handler splits it.
HANDLER_CASES = (
    # A raw byte AFTER a character cp1252 cannot hold, in the same run: the
    # stretch the handler escapes must end where the raw byte begins, not
    # where the run does.
    ("unencodable-then-raw-byte", "cp1252", "日" + raw(0xFF),
     b"\\u65e5\xff"),
    ("raw-byte-then-unencodable", "cp1252", raw(0xFF) + "日",
     b"\xff\\u65e5"),
    # The bottom of the range is a raw byte, and U+DC7F right under it is not.
    ("lowest-raw-byte", "cp1252", raw(0x80), b"\x80"),
    ("highest-raw-byte", "cp1252", raw(0xFF), b"\xff"),
    ("just-under-the-range", "cp1252", chr(0xDC7F), b"\\udc7f"),
    ("bottom-of-the-low-surrogates", "cp1252", chr(0xDC00), b"\\udc00"),
    # A range reaching down to U+DC00 writes U+DC41 as the byte 0x41, `A`;
    # `surrogateescape` never makes it, and stdlib raises on it.
    ("a-letter-in-low-surrogate-clothes", "cp1252", chr(0xDC41),
     b"\\udc41"),
    ("just-over-the-range", "cp1252", chr(0xDD00), b"\\udd00"),
    ("high-surrogate", "cp1252", chr(0xD800), b"\\ud800"),
    ("every-kind-in-one-run", "cp1252",
     "caf" + raw(0xFF) + "日本" + raw(0x80) + chr(0xDC7F) + raw(0xFE)
     + chr(0xD800) + "本",
     b"caf\xff\\u65e5\\u672c\x80\\udc7f\xfe\\ud800\\u672c"),
    # UTF-8 holds every character but the surrogates, so its runs are made of
    # surrogates alone: the same boundaries, with nothing else around them.
    ("utf-8-high-surrogate-then-raw-byte", "utf-8",
     chr(0xD800) + raw(0xFF), b"\\ud800\xff"),
    ("utf-8-raw-byte-then-high-surrogate", "utf-8",
     raw(0xFF) + chr(0xD800), b"\xff\\ud800"),
    ("utf-8-lowest-raw-byte", "utf-8", raw(0x80), b"\x80"),
    ("utf-8-raw-byte-then-just-under", "utf-8", raw(0x80) + chr(0xDC7F),
     b"\x80\\udc7f"),
    ("utf-8-just-under-then-raw-byte", "utf-8", chr(0xDC7F) + raw(0x80),
     b"\\udc7f\x80"),
    ("utf-8-a-letter-in-low-surrogate-clothes", "utf-8", chr(0xDC41),
     b"\\udc41"),
    ("utf-8-text-then-raw-byte-then-low-surrogate", "utf-8",
     "日" + raw(0xFF) + chr(0xDC41), b"\xe6\x97\xa5\xff\\udc41"),
)


@pytest.mark.parametrize(
    "encoding, text, written",
    [pytest.param(*case[1:], id=case[0]) for case in HANDLER_CASES])
def test_the_handler_draws_each_run_at_the_range_of_the_bytes_it_escaped(
        encoding, text, written):
    """Every case is one that a boundary drawn a character off, or a run split
    in the wrong place, writes differently: a raw byte after an unencodable
    character (`\\udcff` where the byte belongs), U+DC80 left out of the range
    (`\\udc80`), and U+DC00..U+DC7F let into it (their bytes 0x00..0x7F).
    Through a stream, and through `str.encode`, which asks the same handler."""
    stream = wrapper(encoding, "surrogateescape")
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    stream.write(text)
    stream.flush()
    assert stream.buffer.getvalue() == written
    assert text.encode(
        encoding, shape_materialize.SURROGATEESCAPE_THEN_BACKSLASHREPLACE
    ) == written


def test_the_handler_is_registered_once_under_a_name_of_this_repository(
        monkeypatch):
    """`reconfigure` takes a handler by name. Once it is registered, no
    later call registers it again."""
    shape_materialize.escape_what_stdout_cannot_encode(
        wrapper("cp1252", "surrogateescape"))
    name = shape_materialize.SURROGATEESCAPE_THEN_BACKSLASHREPLACE
    assert name.startswith("openreposhape."), name
    registered = codecs.lookup_error(name)
    calls = []
    monkeypatch.setattr(codecs, "register_error",
                        lambda *args: calls.append(args))
    for _ in range(3):
        shape_materialize.escape_what_stdout_cannot_encode(
            wrapper("cp1252", "surrogateescape"))
    assert calls == []
    assert codecs.lookup_error(name) is registered


@pytest.mark.parametrize("errors", ("replace", "backslashreplace", "ignore",
                                    "xmlcharrefreplace", "namereplace",
                                    "surrogatepass"))
def test_every_other_handler_is_left_as_it_was(errors):
    """Only the two handlers that raise on a name are changed. Any other is
    one somebody chose, and the encoding is never changed."""
    stream = wrapper("cp1252", errors)
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    assert (stream.encoding, stream.errors) == ("cp1252", errors)


class _Unreconfigurable:
    """A stdout a caller replaced, whose `reconfigure` raises `exception`."""

    def __init__(self, errors: str, exception: type) -> None:
        self.errors = errors
        self.exception = exception

    def reconfigure(self, **_changes) -> None:
        raise self.exception("cannot reconfigure this stream")


@pytest.mark.parametrize("errors", ("strict", "surrogateescape"))
@pytest.mark.parametrize("exception", (ValueError, OSError),
                         ids=lambda exception: exception.__name__)
def test_a_reconfigure_that_raises_fails_nothing(errors, exception):
    """`ValueError` and `OSError` each on its own: neither is
    `io.UnsupportedOperation`, which is both and would let a guard that
    caught only one of them pass."""
    assert not (issubclass(exception, ValueError)
                and issubclass(exception, OSError))
    shape_materialize.escape_what_stdout_cannot_encode(
        _Unreconfigurable(errors, exception))


@pytest.mark.parametrize("errors", ("strict", "surrogateescape"))
def test_a_closed_stdout_fails_nothing(errors):
    """A closed wrapper still reports its handler, and its `reconfigure`
    raises `ValueError`."""
    stream = wrapper("cp1252", errors)
    stream.close()
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    assert stream.errors == errors


def test_a_stdout_that_cannot_be_reconfigured_fails_nothing(monkeypatch):
    """A stream a caller replaced, and `pythonw`'s missing stdout."""
    class Replaced:
        errors = "strict"

    shape_materialize.escape_what_stdout_cannot_encode(Replaced())
    Replaced.errors = "surrogateescape"
    shape_materialize.escape_what_stdout_cannot_encode(Replaced())
    monkeypatch.setattr(sys, "stdout", None)
    shape_materialize.escape_what_stdout_cannot_encode()
