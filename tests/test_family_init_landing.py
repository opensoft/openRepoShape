# SPDX-License-Identifier: Apache-2.0
"""`family.py init` run as AGENTS.md spells it: where it lands, and the next
command it prints (#488).

AGENTS.md spelled the command `python3 scripts/family.py init --org <org>
--family <Name>`, a path that runs from the standard's root, and `--into`
defaults to where the person stands. Followed exactly, it printed `landing
<standard>/Orbit/Orbit` and would have made the family inside the checkout of
openRepoShape, where `make siblings` then clones every member too. README's
example passed `--into ..`; AGENTS.md's did not. And the NEXT STEPS block
printed `python3 family.py add ...`, built from `Path(__file__).name`, which
from the root fails `can't open file`, exit 2.

So: with neither `--into` nor `--work-dir`, `init` refuses to land inside a
checkout of the standard (`family-landing-in-standard`) and names `--into ..`;
an explicit `--into` or `--work-dir` is somebody's choice and is not
second-guessed; AGENTS.md's command passes `--into ..`; and NEXT names this
file by the path that reaches it from where the person stood.

A RUN THAT COULD LAND INSIDE THIS CHECKOUT IS ONLY EVER A `--dry-run`, which
creates nothing whatever the answer. The real runs stand in a FAKE checkout
under the test's own temporary directory (the two paths the detection reads,
and nothing else), so a regression writes there and never into the
repository under test. NO NETWORK: every remote is `--local-remote-dir`.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

from conftest import REPO, run_script

sys.path.insert(0, str(REPO / "scripts"))
from repo_shape import PYTHON  # noqa: E402

FAMILY = REPO / "scripts" / "family.py"
ORG = "testorg"
NAME = "Orbit"
CODE = "family-landing-in-standard"


def init(cwd, tmp_path, *extra: str) -> subprocess.CompletedProcess:
    """`init` as AGENTS.md spelled it before #488, with `extra` appended:
    run from `cwd`, the remote a bare repository under `tmp_path`."""
    return run_script(FAMILY, "init", "--org", ORG, "--family", NAME,
                      "--created-by", "Test Human",
                      "--created-on", "2026-10-12",
                      "--local-remote-dir", str(tmp_path / "remotes"),
                      *extra, cwd=cwd)


def fake_checkout(path):
    """A directory a checkout of openRepoShape is recognised by: a
    `scripts/family.py` beside a `templates/family-root/`, and nothing else.
    The tool under test is still this repository's own `family.py`."""
    (path / "scripts").mkdir(parents=True)
    (path / "scripts" / "family.py").write_bytes(b"")
    (path / "templates" / "family-root").mkdir(parents=True)
    return path


def landing(stdout: str) -> str:
    """The holder path the plan's `landing` line names."""
    found = re.search(r"^landing\s+(.+?)\s{3}", stdout, re.M)
    assert found, stdout
    return found.group(1)


def test_the_old_agents_md_command_from_the_root_is_refused(tmp_path):
    """THE ISSUE'S ROW: from the standard's root, with no `--into`, the plan
    used to say `landing <standard>/Orbit/Orbit` and exit 0. Now it is
    refused before the plan, naming the checkout, the place it would have
    landed and the flag that lands it beside the checkout."""
    result = init(REPO, tmp_path, "--dry-run")
    assert result.returncode == 2, result.stdout + result.stderr
    assert result.stdout == ""
    holder = REPO.resolve() / NAME / NAME
    # Searched for, not read off the first line: a checkout with uncommitted
    # changes is warned about on stderr first, by `_shape_snapshot`.
    assert (f"REFUSED {CODE}: with neither --into nor --work-dir the holder "
            f"lands where you are standing, at {holder}, which is inside "
            f"{REPO.resolve()}, a checkout of openRepoShape itself"
            in result.stderr), result.stderr
    assert ("Remediation: pass `--into ..` to land it beside this checkout, "
            f"at {REPO.resolve().parent / NAME / NAME}, or `--into <dir>`"
            in result.stderr), result.stderr
    assert "Nothing was created, and `--dry-run` refuses the same." \
        in result.stderr
    assert not (REPO / NAME).exists()
    assert not (tmp_path / "remotes").exists()


def test_the_real_run_is_refused_before_anything_is_created(tmp_path):
    """The same refusal without `--dry-run`, from a checkout's root: no
    family folder, no holder and no remote."""
    checkout = fake_checkout(tmp_path / "std")
    result = init(checkout, tmp_path)
    assert result.returncode == 2, result.stdout + result.stderr
    assert f"REFUSED {CODE}:" in result.stderr
    assert "`--into ..`" in result.stderr
    assert sorted(path.name for path in checkout.iterdir()) == [
        "scripts", "templates"]
    assert not (tmp_path / "remotes").exists()


def test_deeper_inside_the_checkout_the_remedy_reaches_its_parent(tmp_path):
    """`--into ..` from a subdirectory would land inside the checkout
    still, so the remedy names the relative path that reaches the
    checkout's parent from where the person stands."""
    checkout = fake_checkout(tmp_path / "std")
    deeper = checkout / "docs" / "notes"
    deeper.mkdir(parents=True)
    result = init(deeper, tmp_path, "--dry-run")
    assert result.returncode == 2, result.stdout + result.stderr
    up = os.path.join("..", "..", "..")
    assert f"Remediation: pass `--into {up}` to land it beside this " \
        "checkout" in result.stderr, result.stderr
    assert f"at {tmp_path.resolve() / NAME / NAME}," in result.stderr


@pytest.mark.parametrize("flag", ["--into", "--work-dir"])
def test_an_explicit_place_inside_the_checkout_is_not_second_guessed(
        tmp_path, flag):
    """`--into .` or `--work-dir .` names the place on purpose: the plan is
    printed, as before, and the dry run exits 0."""
    checkout = fake_checkout(tmp_path / "std")
    result = init(checkout, tmp_path, flag, ".", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert CODE not in result.stderr
    wanted = (checkout.resolve() / NAME / NAME if flag == "--into" else
              checkout.resolve() / NAME)
    assert landing(result.stdout) == str(wanted)


def test_outside_any_checkout_the_default_still_lands_where_you_stand(
        tmp_path):
    """The default is unchanged everywhere else: `<cwd>/Orbit/Orbit`."""
    here = tmp_path / "projects"
    here.mkdir()
    result = init(here, tmp_path, "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert landing(result.stdout) == str(here.resolve() / NAME / NAME)


def test_agents_md_init_command_lands_beside_the_checkout(tmp_path):
    """AGENTS.md's own line, as it is written now, run from the root: it
    passes `--into ..`, so the family lands BESIDE the checkout. A dry run,
    because the real one would write outside the test's directory."""
    agents = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    lines = [line for line in agents.splitlines()
             if line.startswith("python3 scripts/family.py init ")]
    assert len(lines) == 1, lines
    words = lines[0].split()
    assert words[words.index("--into") + 1] == "..", lines[0]
    result = init(REPO, tmp_path, "--into", "..", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert landing(result.stdout) == str(REPO.resolve().parent / NAME / NAME)
    assert not (REPO.parent / NAME).exists()


def next_add_line(stdout: str) -> str:
    """The NEXT STEPS `add` command, its continuation lines joined."""
    block = stdout.split("NEXT STEPS", 1)[1].replace("\\\n", " ")
    lines = [line.strip() for line in block.splitlines()
             if " add --family-root " in line]
    assert len(lines) == 1, stdout
    return " ".join(lines[0].split())


@pytest.mark.parametrize("where", ["the standard's root", "elsewhere"])
def test_the_printed_next_runs_from_where_init_was_run(tmp_path, where):
    """THE SECOND HALF OF THE ISSUE: NEXT used to print `python3 family.py
    add`, which no directory but `scripts/` can run. It names this file by
    the path that reaches it from the directory `init` ran in:
    `scripts/family.py` from the root, as every other place spells it, and
    the relative path from anywhere else. That path, run from there, is
    this repository's `family.py`."""
    cwd = REPO if where == "the standard's root" else tmp_path / "elsewhere"
    cwd.mkdir(exist_ok=True)
    result = init(cwd, tmp_path, "--into", str(tmp_path / "fam"))
    assert result.returncode == 0, result.stdout + result.stderr
    script = os.path.relpath(FAMILY.resolve(), cwd.resolve())
    if where == "the standard's root":
        assert script == os.path.join("scripts", "family.py")
    line = next_add_line(result.stdout)
    assert line.startswith(f"{PYTHON} {script} add --family-root "), line
    assert "family.py add" not in line.replace(script, ""), line
    assert os.path.samefile(cwd / script, FAMILY)
    helped = subprocess.run([sys.executable, script, "add", "--help"],
                            cwd=str(cwd), capture_output=True, text=True,
                            check=False)
    assert helped.returncode == 0, helped.stderr
    assert helped.stdout.startswith("usage: family.py add"), helped.stdout
