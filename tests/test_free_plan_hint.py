# SPDX-License-Identifier: Apache-2.0
"""The Free-plan repository-secret hint.

THE FAILURE THIS GUARDS IS SILENT AND GREEN. On the GitHub Free plan an
ORGANISATION Actions secret is not delivered to a PRIVATE repository — no
error, no warning, `secrets.SHAPE_LEGS_APP_ID` is simply the empty string. The
App-token steps skip, the legs go unfetched, and `validate` reports SUCCESS
with the lockstep pin check degraded away. Measured on InkRouter, 2026-09-04:
the App was installed on every repository and the org secrets existed at
`visibility: all`, and both split pull requests still fetched no legs.

So the hint has to be right in BOTH directions, and the tests below pin both:
it appears on `free`, and it stays silent on every other answer — a paid plan,
no `gh` on PATH, a failed call, an unparseable one. A wrong hint about
credentials is worse than none.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP

sys.path.insert(0, str(REPO / "scripts"))

from repo_shape import free_plan_secret_hint  # noqa: E402


def stub_gh(tmp_path: Path, body: str) -> dict:
    """A `gh` on PATH that is a shell script, returning `body` verbatim.

    A `#!` line is a POSIX kernel convention, so every test that installs one
    of these carries `WINDOWS_SKIP`: on Windows CreateProcess reads no
    shebang and the stub is not a program at all. `free_plan_secret_hint`
    itself is exercised on both platforms by the no-`gh`-on-PATH case below,
    which needs no stub.
    """
    binary = tmp_path / "bin"
    binary.mkdir(exist_ok=True)
    script = binary / "gh"
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ)
    env["PATH"] = f"{binary}{os.pathsep}{env['PATH']}"
    return env


@pytest.fixture
def gh(tmp_path, monkeypatch):
    def install(body: str):
        env = stub_gh(tmp_path, body)
        monkeypatch.setenv("PATH", env["PATH"])
    return install


@WINDOWS_SKIP
def test_a_free_org_gets_the_repository_secret_hint(gh):
    gh("#!/bin/sh\necho free\n")
    hint = free_plan_secret_hint("InkRouter", "InkRouter/IRRS", "the legs are")
    assert hint is not None
    assert "FREE plan" in hint
    assert "--repo InkRouter/IRRS" in hint, "the hint must name the repository"
    assert "SHAPE_LEGS_APP_ID" in hint and "SHAPE_LEGS_APP_PRIVATE_KEY" in hint
    assert "the legs are" in hint, "the caller's subject is interpolated"


@WINDOWS_SKIP
@pytest.mark.parametrize("plan", ["team", "enterprise", "business", "Free "])
def test_a_paid_org_gets_nothing(gh, plan):
    """`Free ` with a trailing space is still free; the others are not.

    The last case is the parse, not the plan: `.plan.name` is compared after
    a strip and a casefold, so whitespace from `gh --jq` never turns a free
    org into a silent pass.
    """
    gh(f"#!/bin/sh\necho '{plan}'\n")
    hint = free_plan_secret_hint("MedxSoft", "MedxSoft/MedxEHR", "the legs are")
    if plan.strip().lower() == "free":
        assert hint is not None
    else:
        assert hint is None


@WINDOWS_SKIP
def test_a_failed_gh_call_is_silent(gh):
    """An org the token cannot read is not evidence of anything."""
    gh("#!/bin/sh\necho 'HTTP 404' >&2\nexit 1\n")
    assert free_plan_secret_hint("Nope", "Nope/Thing", "the legs are") is None


@WINDOWS_SKIP
def test_an_empty_answer_is_silent(gh):
    """`--jq .plan.name` prints nothing when the field is absent."""
    gh("#!/bin/sh\nexit 0\n")
    assert free_plan_secret_hint("X", "X/Y", "the legs are") is None


def test_no_gh_on_path_is_silent(tmp_path, monkeypatch):
    """OFFLINE AND LOCAL MODES MUST PRINT NOTHING, not crash and not guess."""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert free_plan_secret_hint("X", "X/Y", "the legs are") is None


@pytest.mark.parametrize("tool,call", [
    ("scaffold-project.py", "args.org"),
    ("adopt-project.py", 'plan.get("org", "")'),
    ("scripts/family.py", "args.org"),
])
def test_every_creating_tool_calls_the_hint(tool, call):
    """All three creators, or the next org on Free hits it in the one place
    that was missed."""
    source = (REPO / tool).read_text()
    assert "free_plan_secret_hint" in source, f"{tool} does not import it"
    assert f"free_plan_secret_hint(\n            {call}" in source, \
        f"{tool} does not call it with its own org"


@pytest.mark.parametrize("doc", [
    "README.md",
    "templates/assembly-root/README.md",
    "templates/family-root/README.md",
])
def test_the_documents_say_it_too(doc):
    """A tool hint reaches whoever ran the tool; the README reaches whoever
    inherits the repository afterwards."""
    text = (REPO / doc).read_text()
    assert "Free plan" in text or "FREE plan" in text
    assert "--repo" in text
