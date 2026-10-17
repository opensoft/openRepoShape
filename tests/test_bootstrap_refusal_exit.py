# SPDX-License-Identifier: Apache-2.0
"""A validator that REFUSES ends the assembly root's `bootstrap.py` as a
refusal, exit 2; one that FINDS still ends it `bootstrap FAILED`, exit 1
(#764, C2, option B, Brett Heap's ruling of 2026-10-17T13:01:10Z: "take B for
#764's C2").

THE DEFECT, measured on lane 5's #815 head (271710ba) in a PLAIN clone, which
is any person who forgot `--recurse-submodules`, and not only a machine with
no git: `validate-pins.py` refuses `pin-submodule-uninitialized`, exit 2, and
bootstrap said `bootstrap FAILED: pins (exit 2)` and exited 1, as it does for
a finding. Exit 1 is a finding's code and exit 2 is the code every other
refusal here ends with (`git-not-runnable`, a root that cannot be found), so
a script or a setup run that read the code could not tell "this project is
wrong" from "nothing could be checked".

THE RULE NOW.
- A validator's exit 2 prints `bootstrap REFUSED: <name> (exit 2)`, and
  bootstrap exits 2.
- Any other non-zero exit, a finding, prints `bootstrap FAILED: <name> (exit
  <code>)` and bootstrap exits 1, as it did.
- A run where one validator finds and another refuses prints both lines, the
  findings first, and exits 2: a check that could not run outranks a finding.

`make bootstrap` exits 2 for any failing recipe, as the Makefile's own comment
says, so only its `Error <code>` line changes, from `Error 1` to `Error 2`.
What changes for a person is the exit of `bootstrap.py` run directly, as
`setup-project.py` step (7) and `siblings.py` run it.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import (PROJECT, REPO, clone_just_pushed, load_without_bytecode,
                      run_script)

FAILED = "bootstrap FAILED: manifest (exit 1)"
REFUSED = "bootstrap REFUSED: pins (exit 2)"
#: What the pins validator says first, in a plain clone.
PINS_CODE = "pin-submodule-uninitialized"


def bootstrap(root: Path):
    """`scripts/bootstrap.py` in `root`, the validators included, with no
    upstream clone named."""
    return run_script(root / "scripts" / "bootstrap.py", cwd=root,
                      env={"SHAPE_UPSTREAM_PATH": ""})


def a_finding(root: Path) -> None:
    """A manifest the manifest validator FINDS wrong, exit 1, and which
    steps (a) and the pins validator read no differently."""
    manifest = root / "project.yaml"
    text = manifest.read_text(encoding="utf-8")
    found = re.sub(r'(?m)^visibility: ".*"$', 'visibility: "hidden"', text)
    assert found != text, text
    manifest.write_bytes(found.encode("utf-8"))


@pytest.fixture
def plain(scaffolded, tmp_path) -> Path:
    """A PLAIN clone of the scaffold's root: no `--recurse-submodules`, so
    both legs' mounts are empty and `validate-pins.py` refuses."""
    clone = tmp_path / PROJECT
    made = clone_just_pushed(scaffolded["remotes"] / f"{PROJECT}.git", clone,
                             recurse=False)
    assert made.returncode == 0, made.stderr
    return clone


def ends(result, code: int, *lines: str) -> None:
    """The run's exit, no traceback, and stderr ending on `lines`."""
    assert result.returncode == code, result.stderr + result.stdout
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stderr.splitlines()[-len(lines):] == list(lines), (
        result.stderr)
    assert "bootstrap ok" not in result.stdout, result.stdout


def test_a_refusing_validator_ends_the_run_refused_with_exit_2(plain):
    """On #815's head: `bootstrap FAILED: pins (exit 2)`, exit 1."""
    result = bootstrap(plain)
    ends(result, 2, REFUSED)
    assert PINS_CODE in result.stderr, result.stderr
    assert "bootstrap FAILED" not in result.stderr, result.stderr
    # The run still goes on to step (c): only its end changed.
    assert "(c) review authority" in result.stdout, result.stdout


def test_findings_alone_still_end_the_run_failed_with_exit_1(project):
    """The same line and the same code as before, in a recursive clone whose
    pins are in order."""
    a_finding(project)
    result = bootstrap(project)
    ends(result, 1, FAILED)
    assert "manifest-visibility" in result.stderr, result.stderr
    assert "bootstrap REFUSED" not in result.stderr, result.stderr


def test_a_finding_and_a_refusal_say_both_and_exit_2(plain):
    """The manifest validator finds and the pins validator refuses: both
    lines, the finding first, and exit 2."""
    a_finding(plain)
    result = bootstrap(plain)
    ends(result, 2, FAILED, REFUSED)
    assert "manifest-visibility" in result.stderr, result.stderr
    assert PINS_CODE in result.stderr, result.stderr


@pytest.mark.skipif(shutil.which("make") is None or
                    shutil.which("python3") is None,
                    reason="the Makefile runs `python3` under `make`")
def test_make_bootstrap_says_refused_and_make_names_error_2(plain):
    """GNU make exits 2 for any failing recipe, so its exit is what it was;
    its own line now carries the recipe's code, 2."""
    proc = subprocess.run(["make", "bootstrap"], cwd=str(plain),
                          env={**os.environ, "SHAPE_UPSTREAM_PATH": ""},
                          capture_output=True, stdin=subprocess.DEVNULL,
                          encoding="utf-8", errors="replace", check=False)
    assert proc.returncode == 2, proc.stderr + proc.stdout
    assert REFUSED in proc.stderr, proc.stderr
    assert re.search(r"\] Error 2\b", proc.stderr), proc.stderr
    assert "Error 1" not in proc.stderr, proc.stderr


# --- the ending itself, asked of each mix of codes --------------------------

@pytest.fixture(scope="module")
def ending():
    """The assembly root's `_end_of_run`, loaded by path."""
    module = load_without_bytecode(
        REPO / "templates" / "assembly-root" / "scripts" / "bootstrap.py",
        "bootstrap_refusal_exit")
    return module._end_of_run


@pytest.mark.parametrize("failed, code, said", [
    ([], 0, []),
    ([("manifest", 1)], 1, ["bootstrap FAILED: manifest (exit 1)"]),
    ([("naming", 1), ("manifest", 1)], 1,
     ["bootstrap FAILED: naming (exit 1), manifest (exit 1)"]),
    ([("pins", 2)], 2, ["bootstrap REFUSED: pins (exit 2)"]),
    ([("naming", 2), ("pins", 2)], 2,
     ["bootstrap REFUSED: naming (exit 2), pins (exit 2)"]),
    ([("pins", 3)], 1, ["bootstrap FAILED: pins (exit 3)"]),
    ([("pins", 127)], 1, ["bootstrap FAILED: pins (exit 127)"]),
    ([("pins", 2), ("manifest", 1)], 2,
     ["bootstrap FAILED: manifest (exit 1)",
      "bootstrap REFUSED: pins (exit 2)"]),
    ([("naming", 3), ("manifest", 1), ("pins", 2)], 2,
     ["bootstrap FAILED: naming (exit 3), manifest (exit 1)",
      "bootstrap REFUSED: pins (exit 2)"]),
], ids=["none", "one finding", "two findings", "one refusal",
        "two refusals", "an exit 3", "an exit 127", "refusal first",
        "all three"])
def test_the_ending_says_each_kind_and_exits_by_the_worst(ending, capsys,
                                                          failed, code, said):
    assert ending(failed) == code
    seen = capsys.readouterr()
    assert seen.err.splitlines() == said
    assert seen.out == ("bootstrap ok\n" if code == 0 else "")
