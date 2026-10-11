# SPDX-License-Identifier: Apache-2.0
"""A name stdout cannot encode is printed escaped, never raised on (#214).

`adopt-project.py plan` wrote the plan file and then printed its report with
plain `print`s, so a source file named `日本.md` raised `UnicodeEncodeError`
in the middle of the table on a stdout in cp1252 -- which is what Windows
gives any stdout that is not the console itself: a file, a pipe to `tee`,
CI, an agent running the tool. `plan` exited 1 with a traceback, after the
plan was on disk and before `plan written to` and the questions it exists to
ask. The same raise was in `check`, `shape-doctor.py`, `update-shape.py`,
`scaffold-project.py`, `scripts/family.py` and `scripts/bump-leg.py`,
wherever a path or a person's text was printed.

Each now calls `shape_materialize.escape_what_stdout_cannot_encode` first:
a `strict` stdout becomes `backslashreplace`, which writes what `strict`
would have written and escapes only what it would have raised on. Every run
here is made twice, under `PYTHONIOENCODING=cp1252:strict` (the Windows code
page, emulated: CI's own Windows job runs in UTF-8 mode and never sees it)
and `utf-8:strict`, and answered in BYTES, decoded strictly in the encoding
the run was given, so a byte the stdout could not have held fails the test.
"""

from __future__ import annotations

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
ENCODINGS = ("cp1252:strict", "utf-8:strict")


def shown(text: str, encoding: str) -> str:
    """`text` as a stdout in `encoding` now prints it: as it is where the
    encoding holds it, and `\\uXXXX` where it does not."""
    codec = encoding.split(":")[0]
    return text.encode(codec, "backslashreplace").decode(codec)


def run_tool(script: Path, *args: str, encoding: str,
             tmp_path: Path) -> tuple[int, str, str]:
    """`(exit, stdout, stderr)` of one run with its stdout in `encoding`.

    BYTES, then decoded STRICTLY in that encoding: `conftest.run_script`
    decodes in the parent's own locale, which is not what the child was
    told to write. The environment is `run_script`'s -- no lane, no
    pin-source override, an identity git can commit with -- plus an empty
    `AGENT_PROTOCOL_ROOT`, so a `workspace.yaml` on the machine running the
    suite changes nothing here. Windows writes `\\r\\n`; read as `\\n`.
    """
    env = blank_unnamed_pin_sources(
        {**os.environ, "LANES_LANE": "", "PYTHONIOENCODING": encoding,
         "AGENT_PROTOCOL_ROOT": str(tmp_path / "agent-protocol")}, {})
    for key, value in (("GIT_AUTHOR_NAME", "openRepoShape tests"),
                       ("GIT_AUTHOR_EMAIL", "tests@openreposhape.invalid"),
                       ("GIT_COMMITTER_NAME", "openRepoShape tests"),
                       ("GIT_COMMITTER_EMAIL", "tests@openreposhape.invalid")):
        env.setdefault(key, value)
    (tmp_path / "agent-protocol").mkdir(exist_ok=True)
    proc = subprocess.run([sys.executable, str(script), *args],
                          capture_output=True, env=env,
                          stdin=subprocess.DEVNULL, check=False)
    codec = encoding.split(":")[0]
    stdout = proc.stdout.decode(codec).replace("\r\n", "\n")
    stderr = proc.stderr.decode(codec, "replace").replace("\r\n", "\n")
    return proc.returncode, stdout, stderr


# --- the repro of #214 -------------------------------------------------------

@pytest.mark.parametrize("encoding", ENCODINGS)
def test_plan_reports_every_name_whatever_its_stdout_can_encode(tmp_path,
                                                                encoding):
    """Exit 0, `plan written to`, both entries in the plan, and each name in
    the table and in the question list: as it is on a UTF-8 stdout, escaped
    on a cp1252 one. On main the cp1252 run exited 1 in `_print_entries`,
    two rows into the table."""
    source = make_source_repo(tmp_path / "Thing", tree={
        "README.md": "# Thing\n", ANSWERED: "x\n", ASKED: "{}\n",
        "src/main.py": "x = 1\n"}, edits=())
    out = tmp_path / "adoption-plan.yaml"
    code, stdout, stderr = run_tool(
        ADOPT, "plan", "--source", str(source), "--project", "Northwind",
        "--org", ORG, "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--out", str(out),
        encoding=encoding, tmp_path=tmp_path)
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
    if encoding.startswith("cp1252"):
        assert "\\u65e5\\u672c.md" in stdout, stdout
        assert NAME not in stdout, stdout


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
    """The doctor's rows are ASCII already; its `root` line was not."""
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
    return FAMILY, ("init", "--org", ORG, "--family", "Contoso",
                    "--name", NAME, "--created-by", NAME,
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


OTHER_TOOLS = {
    "adopt-check": _adopt_check,
    "bump-leg-dry-run": _bump_leg_dry_run,
    "shape-doctor": _doctor,
    "update-shape-check": _update_shape_check,
    "scaffold-dry-run": _scaffold_dry_run,
    "family-init-dry-run": _family_init_dry_run,
}


@pytest.mark.parametrize("tool", sorted(OTHER_TOOLS))
def test_every_tool_exits_alike_whatever_its_stdout_can_encode(tmp_path,
                                                               request, tool):
    """The same run under both encodings: the same exit, no traceback, and
    the name printed -- as it is under UTF-8, escaped under cp1252. On main
    every cp1252 run here exited 1 at its first `print` of the name."""
    script, args = OTHER_TOOLS[tool](tmp_path, request)
    runs = {encoding: run_tool(script, *args, encoding=encoding,
                               tmp_path=tmp_path)
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


def test_a_handler_that_does_not_raise_is_left_as_it_was():
    """UTF-8 mode and the POSIX locale give stdout `surrogateescape`, which
    writes a name that is not UTF-8 back as its own bytes; turning it into
    `\\udcff` would change what a run that worked prints."""
    stream = wrapper("utf-8", "surrogateescape")
    shape_materialize.escape_what_stdout_cannot_encode(stream)
    assert stream.errors == "surrogateescape"
    stream.write("caf\udcff\n")
    stream.flush()
    assert stream.buffer.getvalue() == b"caf\xff\n"


def test_a_stdout_that_cannot_be_reconfigured_fails_nothing(monkeypatch):
    """A stream a caller replaced, and `pythonw`'s missing stdout."""
    class Replaced:
        errors = "strict"

    shape_materialize.escape_what_stdout_cannot_encode(Replaced())
    monkeypatch.setattr(sys, "stdout", None)
    shape_materialize.escape_what_stdout_cannot_encode()
