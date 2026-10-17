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

Three things beside the first-space split, from the review of the fix: a url
holding a line break or a carriage return is skipped in all three steps, since
printed it could be a workflow command of its own; each repository is named
once however many sections or paths give it; and a url key outside a
`submodule` section, even `[-x] url`, is read without git's usage dump.

And the rules the doctor and `siblings.py` read the same file by (#786, from
#733): `RULES` holds one row per rule, each a `.gitmodules` and the urls git
registers for it. Three things check a row. `git submodule init` itself says
what git registers, a `siblings.submodule_urls` that has #775's rules agrees
(it skips until they are in main), and each of the three steps in both
templates names or lists exactly that, or fails with the cause where git
refuses the whole file.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from conftest import REPO, WINDOWS_SKIP, git, load_without_bytecode
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

#: Section name -> url, in the order the file lists them; each section mounts
#: at `mounts/<its name>`. The first three are names git allows and
#: `--get-regexp`'s `key value` line cannot hold: a space, a tab, and a
#: leading `-` with `#` and `;`. The fourth is a url, not a name, with the
#: same bytes in it (a space, a tab, `#`, `;` and a trailing space); it names
#: no repository, so the names step skips it.
SECTIONS = {
    "members/My IRRS": "https://github.com/acme/IRRS.git",
    "tab\there": "git@github.com:acme/Tabbed.git",
    "-lead #hash;semi": "https://github.com/acme/Odd.git",
    "plain": "odd url\twith #hash;semi ",
}
THE_LEGS = "IRRS,Tabbed,Odd"
#: Urls the steps skip, given by git's `\n` escape and a raw carriage return:
#: each holds a line that a runner would read as a workflow command.
LINE_BREAKS = {
    "nl": "https://github.com/acme/A.git\n::error title=x::injected",
    "cr": "https://github.com/acme/B.git\r::error title=y::injected",
}
#: What a step prints of its own: its summary line, and the `  <url>` lines.
OWN_COMMAND = re.compile(r"::(warning|error)::(  |submodule checkout failed|A )")
EACH_STEP = pytest.mark.parametrize("step", ["names", "fetch", "fail"])


def acme(name: str) -> str:
    return f"https://github.com/acme/{name}.git"


def section(name: str, *keys: str) -> str:
    """A `[submodule "name"]` with each of `keys` on a line of its own."""
    return f'[submodule "{name}"]\n' + "".join(f"\t{key}\n" for key in keys)


def mounted(name: str, url: str, *keys: str, at: str = "") -> str:
    """`section`, mounted at `at`, or at a path named for it, giving `url`."""
    return section(name, f"path = {at or name}", f"url = {url}", *keys)


#: Each case a repository could be named twice, as a `.gitmodules` text and
#: the repositories the names step names for it: once each, first seen first.
DUPLICATES = {
    "a url given twice in one section": (
        mounted("m", acme("Stale"), f"url = {acme('A')}"), "A"),
    "a section reopened further down": (
        mounted("m", acme("Stale")) + mounted("n", acme("B"))
        + section("m", f"url = {acme('A')}"), "A,B"),
    "two paths mounting one repository": (
        mounted("m", acme("A")) + mounted("n", "git@github.com:acme/A.git"),
        "A"),
}


def workflow_text(template: str) -> str:
    path = (REPO / "templates" / template / ".github" / "workflows"
            / "validate.yml")
    return path.read_text(encoding="utf-8")


@pytest.fixture
def holder(tmp_path: Path) -> Path:
    """A repository whose `.gitmodules` is `SECTIONS` and then `LINE_BREAKS`,
    written by git so that its quoting is git's."""
    work = tmp_path / "holder"
    work.mkdir()
    git("init", "-q", cwd=work)
    for name, url in {**SECTIONS, **LINE_BREAKS}.items():
        git("config", "--file", ".gitmodules", f"submodule.{name}.path",
            f"mounts/{name}", cwd=work)
        git("config", "--file", ".gitmodules", f"submodule.{name}.url", url,
            cwd=work)
    return work


@dataclass(frozen=True)
class Rule:
    """One row of `RULES`: a `.gitmodules`, the paths `git submodule init` is
    asked about, and what git registers for it.

    `urls` are the urls git registers, in the order of the file; none where it
    reads none of the file. `refused` is the cause the steps name where git
    refuses the whole file, and `named` what that message names of the file:
    the key git stops at as the step prints it (`%` escaped), or its line.
    `unmerged` leaves `.gitmodules` unmerged in the index with the file in the
    working tree as it is, and a `gitmodules` of None writes no file at all.
    """
    gitmodules: str | None
    paths: tuple
    urls: tuple
    refused: str = ""
    named: str = ""
    unmerged: bool = False


GITLINK = "1234567890123456789012345678901234567890"


def holder_of(tmp_path: Path, gitmodules: str, paths=(), unmerged=False,
              name: str = "holder") -> Path:
    """A repository whose `.gitmodules` is `gitmodules`, as written, with a
    gitlink at each of `paths` and, for `unmerged`, `.gitmodules` in
    conflict in the index."""
    work = tmp_path / name
    work.mkdir()
    git("init", "-q", cwd=work)
    if gitmodules is not None:
        (work / ".gitmodules").write_bytes(gitmodules.encode("utf-8"))
    for path in paths:
        git("update-index", "--add", "--cacheinfo", f"160000,{GITLINK},{path}",
            cwd=work)
    if unmerged:
        stages = ""
        for stage, body in ((1, b"base\n"), (2, b"ours\n"), (3, b"theirs\n")):
            blob = subprocess.run(
                ["git", "hash-object", "-w", "--stdin"], cwd=work, input=body,
                capture_output=True, check=True).stdout.decode().strip()
            stages += f"100644 {blob} {stage}\t.gitmodules\n"
        subprocess.run(["git", "update-index", "--index-info"], cwd=work,
                       input=stages.encode(), check=True)
    return work


OK_URL = acme("Ok")
OK = mounted("ok", OK_URL)


def accepted(*keys: str) -> Rule:
    """A mounted section for each of `keys`, which it holds, and `ok`: git
    reads every one of them."""
    names = [f"s{n}" for n in range(len(keys))]
    text = "".join(mounted(name, acme(name.upper()), key)
                   for name, key in zip(names, keys))
    return Rule(text + OK, (*names, "ok"),
                (*(acme(name.upper()) for name in names), OK_URL))


def refusing(cause: str, *keys: str, named: str, name: str = "q",
             at: str = "") -> Rule:
    """`ok`, then a section named `name` and mounted at `at`, or at a path
    named for it, holding `keys`: git refuses the whole file for them, `ok`
    and all, and the steps say `cause`, naming `named`."""
    return Rule(OK + mounted(name, acme("Q"), *keys, at=at),
                ("ok", at or name), (), cause, named)


NO_VALUE = " key with no value"
UPDATE = "an update that is not none, checkout, rebase or merge"
SHALLOW = "a shallow that is not a boolean"
FETCH = "a fetchRecurseSubmodules that is neither a boolean nor on-demand"

#: One row per rule, each measured against `git submodule init` by
#: `test_git_registers_what_each_row_says`. Every row but the refusals keeps
#: `ok`, so a rule that drops too much shows.
RULES = {
    "a url key outside a submodule section": Rule(
        '[remote "origin"]\n\turl = ' + acme("Other") + "\n[-x]\n\turl = "
        + acme("Dash") + "\n[submodule]\n\turl = " + acme("Bare") + "\n" + OK,
        ("ok",), (OK_URL,)),
    "an empty section name": Rule(
        mounted("", acme("Empty"), at="e") + OK, ("e", "ok"), (OK_URL,)),
    "a name holding a .. component": Rule(
        mounted("../a", acme("DotA"), at="d1")
        + mounted("a/../b", acme("DotB"), at="d2")
        + mounted("..\\\\c", acme("DotC"), at="d3")
        + mounted("..", acme("DotD"), at="d4")
        + mounted("a/..", acme("DotE"), at="d5")
        + mounted("a..b", acme("Dots"), at="d6") + OK,
        ("d1", "d2", "d3", "d4", "d5", "d6", "ok"), (acme("Dots"), OK_URL)),
    "a url beginning with a dash": Rule(
        mounted("d", "-oProxyCommand=x") + OK, ("d", "ok"), (OK_URL,)),
    "a path beginning with a dash": Rule(
        section("p", "path = -p", f"url = {acme('P')}") + OK, ("-p", "ok"),
        (OK_URL,)),
    "a section with no path": Rule(
        section("np", f"url = {acme('Nowhere')}") + OK, ("np", "ok"),
        (OK_URL,)),
    "a url given twice, the later beginning with a dash": Rule(
        mounted("later", acme("Early"), "url = -x") + OK, ("later", "ok"),
        (acme("Early"), OK_URL)),
    "a path given twice, the later beginning with a dash": Rule(
        section("lp", "path = lp", f"url = {acme('LP')}", "path = -p") + OK,
        ("lp", "ok"), (acme("LP"), OK_URL)),
    "no gitmodules at all": Rule(None, (), ()),
    "a gitmodules left unmerged": Rule(OK, ("ok",), (), unmerged=True),
    "a bare ignore in a section named with a backslash": Rule(
        section("..\\\\x", "ignore") + OK, ("ok",), (OK_URL,)),
    "a bare key where git ignores the section": Rule(
        section("", "url") + section("../x", "path") + '[remote "r"]\n\turl\n'
        + OK, ("ok",), (OK_URL,)),
    "a file git cannot parse": Rule(
        OK + '[submodule "x"\n', ("ok",), (), "a line git cannot parse",
        "bad config line 5 in file .gitmodules"),
    "a path with no value": refusing(
        "a path" + NO_VALUE, "path", named="submodule.q.path"),
    "a url with no value": refusing(
        "a url" + NO_VALUE, "url", named="submodule.q.url"),
    "an ignore with no value": refusing(
        "an ignore" + NO_VALUE, "ignore", named="submodule.q.ignore"),
    "an update with no value": refusing(
        "an update" + NO_VALUE, "update", named="submodule.q.update"),
    "a branch with no value": refusing(
        "a branch" + NO_VALUE, "branch", named="submodule.q.branch"),
    "an update git dies on": refusing(
        UPDATE, "update = bogus", named="submodule.q.update"),
    "an update that is a command": refusing(
        UPDATE, "update = !echo hi", named="submodule.q.update"),
    "an update in a section named with a percent sign": refusing(
        UPDATE, "update = bogus", name="p%q", named="submodule.p%25q.update"),
    "an update in a section named with a carriage return": refusing(
        UPDATE, "update = bogus", name="q\rx", at="q",
        named="submodule.q%0Dx.update"),
    "each update git accepts": accepted(
        "update = checkout", "update = merge", "update = rebase",
        "update = none"),
    "a shallow git dies on": refusing(
        SHALLOW, "shallow = maybe", named="submodule.q.shallow"),
    "each shallow git accepts": accepted(
        "shallow = true", "shallow = no", "shallow = 1", "shallow = 0x10",
        "shallow = ", "shallow"),
    "a fetchRecurseSubmodules git dies on": refusing(
        FETCH, "fetchRecurseSubmodules = sometimes",
        named="submodule.q.fetchrecursesubmodules"),
    "a fetchRecurseSubmodules spelt On-Demand": refusing(
        FETCH, "fetchRecurseSubmodules = On-Demand",
        named="submodule.q.fetchrecursesubmodules"),
    "each fetchRecurseSubmodules git accepts": accepted(
        "fetchRecurseSubmodules = on-demand", "fetchRecurseSubmodules = true",
        "fetchRecurseSubmodules = 2", "fetchRecurseSubmodules"),
}
EACH_RULE = pytest.mark.parametrize("rule_id", sorted(RULES))
#: Each step with each row, but for the failing step with a file git refuses:
#: the fetch step exits 1 on one, so the failing step is never reached with
#: it, and it carries no refusal of its own.
EACH_STEP_AND_RULE = pytest.mark.parametrize("step, rule_id", [
    (step, rule_id) for rule_id in sorted(RULES)
    for step in ("names", "fetch", "fail")
    if not (step == "fail" and RULES[rule_id].refused)])


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


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_STEP
@EACH_TEMPLATE
def test_a_url_holding_a_line_break_prints_no_workflow_command_of_its_own(
        template, step, holder, tmp_path):
    result, _ = run_step(template, step, holder, tmp_path)
    commands = [line for line in result.stdout.split("\n")
                if line.startswith("::") and not OWN_COMMAND.match(line)]
    assert commands == []


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_STEP
@EACH_TEMPLATE
def test_a_url_holding_a_line_break_writes_only_key_value_lines_to_the_output(
        template, step, holder, tmp_path):
    _, output = run_step(template, step, holder, tmp_path)
    stray = [line for line in output.split("\n")
             if line and not re.match(r"[a-z_]+=", line)]
    assert stray == []


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@pytest.mark.parametrize("case", sorted(DUPLICATES))
@EACH_TEMPLATE
def test_the_names_step_names_a_repository_once(template, case, tmp_path):
    gitmodules, names = DUPLICATES[case]
    work = holder_of(tmp_path, gitmodules)
    _, output = run_step(template, "names", work, tmp_path)
    assert output.splitlines() == [f"{TEMPLATES[template]['output']}={names}"]


def registered(work: Path, paths) -> list:
    """The urls `git submodule init` registers, asked of each of `paths` in
    turn, since it stops at the first it can name no url for. It says so on
    stderr."""
    urls = []
    for path in paths:
        proc = subprocess.run(
            ["git", "submodule", "init", "--", path], cwd=work,
            capture_output=True, text=True, encoding="utf-8", check=False)
        urls += re.findall(r"^Submodule '.*' \((.*)\) registered for path ",
                           proc.stdout + proc.stderr, re.MULTILINE)
    return urls


@EACH_RULE
def test_git_registers_what_each_row_says(rule_id, tmp_path):
    rule = RULES[rule_id]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths, rule.unmerged)
    assert registered(work, rule.paths) == list(rule.urls)


@pytest.fixture
def siblings(monkeypatch):
    """The TEMPLATE's `siblings.py`, once it has #775's rules; skipped until
    they are in main. Loaded as `test_family_siblings_placement.py` loads it."""
    scripts = REPO / "templates" / "family-root" / "scripts"
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.setitem(sys.modules, "bootstrap", load_without_bytecode(
        scripts / "bootstrap.py", "ci_rules_family_bootstrap"))
    module = load_without_bytecode(scripts / "siblings.py",
                                   "ci_rules_family_siblings")
    if not hasattr(module, "DOTDOT_COMPONENT"):
        pytest.skip("siblings.py has no #733 rules until #775 is in main")
    return module


@pytest.mark.parametrize("rule_id", sorted(
    rule_id for rule_id, rule in RULES.items()
    if not rule.unmerged and "\r" not in (rule.gitmodules or "")))
def test_siblings_reads_what_each_row_says(rule_id, siblings, tmp_path):
    """`siblings.submodule_urls` reads the file in the working tree, so a row
    that leaves it unmerged in the index is not asked. Nor is a row with a
    carriage return in it: `siblings.py` cuts `--list` at `splitlines`, which
    ends a line at one, so it reads the key `submodule.q` and `x.update` and
    never the refused `update` (a defect beside its split at the first `=`,
    which lane 3 files)."""
    rule = RULES[rule_id]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths)
    assert sorted(siblings.submodule_urls(work).values()) == sorted(rule.urls)


def read_by(template: str, step: str, result, output: str) -> list:
    """What one step named (its repositories) or listed (its urls)."""
    if step == "names":
        key = TEMPLATES[template]["output"]
        [named] = [line[len(key) + 1:] for line in output.splitlines()
                   if line.startswith(f"{key}=")] or [""]
        return named.split(",") if named else []
    prefix = {"fetch": "::warning::  ", "fail": "::error::  "}[step]
    return [line[len(prefix):] for line in result.stdout.split("\n")
            if line.startswith(prefix)]


def expected_of(step: str, rule: Rule) -> list:
    """What git's urls come to in one step: repository names in the names step,
    the urls themselves in the two that list them."""
    if step != "names":
        return list(rule.urls)
    return [url.rsplit("/", 1)[-1].removesuffix(".git") for url in rule.urls]


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_STEP_AND_RULE
@EACH_TEMPLATE
def test_each_step_reads_what_git_reads(template, step, rule_id, tmp_path):
    rule = RULES[rule_id]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths, rule.unmerged)
    result, output = run_step(template, step, work, tmp_path)
    assert read_by(template, step, result, output) == expected_of(step, rule)


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_STEP_AND_RULE
@EACH_TEMPLATE
def test_each_step_exits_as_expected_and_prints_nothing_on_stderr(
        template, step, rule_id, tmp_path):
    """Only a file git refuses whole fails a step that would not fail anyway:
    the failing step fails always, and nothing reaches stderr."""
    rule = RULES[rule_id]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths, rule.unmerged)
    result, _ = run_step(template, step, work, tmp_path)
    failed = bool(rule.refused) or step == "fail"
    assert result.returncode == int(failed)
    assert result.stderr == ""


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@pytest.mark.parametrize("rule_id", sorted(
    rule_id for rule_id, rule in RULES.items() if rule.refused))
@pytest.mark.parametrize("step", ["names", "fetch"])
@EACH_TEMPLATE
def test_a_file_git_refuses_whole_is_named_with_its_cause_and_its_key(
        template, step, rule_id, tmp_path):
    rule = RULES[rule_id]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths)
    result, _ = run_step(template, step, work, tmp_path)
    causes = [line for line in result.stdout.split("\n")
              if line.startswith("::error::") and rule.refused in line]
    assert len(causes) == 1
    assert rule.named in causes[0]


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_TEMPLATE
def test_the_fetch_step_gives_no_credential_advice_for_a_file_git_refuses(
        template, tmp_path):
    rule = RULES["a url with no value"]
    work = holder_of(tmp_path, rule.gitmodules, rule.paths)
    result, _ = run_step(template, "fetch", work, tmp_path)
    assert "submodule checkout failed" not in result.stdout


@WINDOWS_SKIP  # it runs the step's `run:` body as the REAL bash it is
@EACH_TEMPLATE
def test_the_fetch_step_gives_its_credential_advice_before_it_lists_the_urls(
        template, holder, tmp_path):
    result, _ = run_step(template, "fetch", holder, tmp_path)
    lines = result.stdout.split("\n")
    advice = next(n for n, line in enumerate(lines)
                  if line.startswith("::warning::submodule checkout failed"))
    first = next(n for n, line in enumerate(lines)
                 if line.startswith("::warning::  "))
    assert advice < first
