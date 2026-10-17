# SPDX-License-Identifier: Apache-2.0
"""The `validate.yml` templates read each url out of `.gitmodules` as git
does (#741).

Both templates (`templates/assembly-root/` and `templates/family-root/`) read
the urls three times: the step that names the repositories the GitHub App
token is minted for, the step that fetches the submodules and lists the urls
where it cannot, and the step that fails the job and lists them again. Each
used to split `git config --get-regexp '\\.url$'`'s `key value` lines at the
first space, so a section named `members/My IRRS` gave the url `IRRS.url
<url>`: the names step matched it to neither form and left the repository out
of the token, and the other two printed it.

Like `tests/test_scaffold_e2e.py::test_the_leg_name_extraction_...`, these run
each step's `run:` body UNMODIFIED, as the real bash it is, so the shell is
what is tested and not a Python reading of it. The one thing a runner does
that a test cannot is reach the legs: `git submodule update` is a stub that
exits 1, which is how the two printing steps are reached, and every other
`git` is the real one.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git
from test_scaffold_e2e import _step_run_script

#: What each template calls its steps. The names step's output is `legs=` in
#: the assembly root and `members=` in the family root, which names members.
TEMPLATES = {
    "assembly-root": {
        "names": "id: leg-names",
        "output": "legs",
        "fetch": "id: submodules",
        "fail": "fail — a leg credential is configured but the legs still",
    },
    "family-root": {
        "names": "id: member-names",
        "output": "members",
        "fetch": "id: submodules",
        "fail": "fail — a credential is configured but the members still",
    },
}
EACH_TEMPLATE = pytest.mark.parametrize("template", sorted(TEMPLATES))

#: Section name -> url, in the order the file lists them. The first three are
#: names git allows and `--get-regexp`'s `key value` line cannot hold: a
#: space, a tab, and a leading `-` with `#` and `;`. The fourth is a url, not
#: a name, with the same bytes in it (a leading `-`, a space, a tab, `#`, `;`
#: and a trailing space); it names no repository, so the names step skips it.
SECTIONS = {
    "members/My IRRS": "https://github.com/acme/IRRS.git",
    "tab\there": "git@github.com:acme/Tabbed.git",
    "-lead #hash;semi": "https://github.com/acme/Odd.git",
    "plain": "-odd url\twith #hash;semi ",
}
THE_LEGS = "IRRS,Tabbed,Odd"


def workflow_text(template: str) -> str:
    path = (REPO / "templates" / template / ".github" / "workflows"
            / "validate.yml")
    return path.read_text(encoding="utf-8")


@pytest.fixture
def holder(tmp_path: Path) -> Path:
    """A folder whose `.gitmodules` is `SECTIONS`, written by git so that its
    quoting is git's."""
    work = tmp_path / "holder"
    work.mkdir()
    for name, url in SECTIONS.items():
        git("config", "--file", ".gitmodules", f"submodule.{name}.url", url,
            cwd=work)
    return work


def run_step(template: str, step: str, holder: Path, tmp_path: Path):
    """`(completed process, the step's $GITHUB_OUTPUT)` for one step's `run:`
    body in `holder`, under `bash -e` as the runner starts it.

    The `${{ ... }}` expressions are the runner's to fill in, and bash reads
    them as a bad substitution, so each becomes a word.
    """
    spec = TEMPLATES[template]
    body = _step_run_script(workflow_text(template), spec[step])
    script = re.sub(r"\$\{\{.*?\}\}", "EXPRESSION", body)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    stub = stubs / "git"
    stub.write_bytes(b'#!/bin/sh\n[ "$1" = submodule ] && exit 1\n'
                     b'exec "$REAL_GIT" "$@"\n')
    stub.chmod(0o755)
    output = tmp_path / "github_output"
    output.write_bytes(b"")
    env = {**os.environ, "REAL_GIT": shutil.which("git"),
           "PATH": str(stubs) + os.pathsep + os.environ["PATH"],
           "GITHUB_OUTPUT": str(output), "REPO_OWNER": "acme"}
    result = subprocess.run(["bash", "-e", "-c", script], cwd=holder, env=env,
                            capture_output=True, text=True, encoding="utf-8",
                            check=False)
    return result, output.read_text(encoding="utf-8")


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_TEMPLATE
def test_the_names_step_keeps_a_repository_whose_section_name_is_not_a_word(
        template, holder, tmp_path):
    result, output = run_step(template, "names", holder, tmp_path)
    assert result.returncode == 0, result.stderr
    output_key = TEMPLATES[template]["output"]
    assert output.splitlines() == [f"{output_key}={THE_LEGS}"]


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_TEMPLATE
def test_the_fetch_step_lists_each_url_as_it_is_when_the_fetch_fails(
        template, holder, tmp_path):
    result, _ = run_step(template, "fetch", holder, tmp_path)
    assert result.returncode == 0, result.stderr
    listed = [line for line in result.stdout.split("\n")
              if line.startswith("::warning::  ")]
    assert listed == [f"::warning::  {url}" for url in SECTIONS.values()]


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_TEMPLATE
def test_the_failing_step_lists_each_url_as_it_is(template, holder, tmp_path):
    result, _ = run_step(template, "fail", holder, tmp_path)
    assert result.returncode == 1, result.stderr
    listed = [line for line in result.stdout.split("\n")
              if line.startswith("::error::  ")]
    assert listed == [f"::error::  {url}" for url in SECTIONS.values()]


@EACH_TEMPLATE
def test_no_step_reads_a_listing_that_a_section_name_can_split(template):
    """The class of defect, not only its three instances: `--get-regexp`
    without `--name-only` prints `key value` lines, and a line holding a
    section name with a space cannot be split back into the two."""
    reads = [line for line in workflow_text(template).splitlines()
             if "--get-regexp" in line and not line.lstrip().startswith("#")]
    assert reads
    for line in reads:
        assert "--name-only" in line, line
