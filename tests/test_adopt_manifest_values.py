# SPDX-License-Identifier: Apache-2.0
"""`adopt-project.py` refuses a value the new project's validator refuses (#261).

`plan`, `check` and `execute` took values the project's own
`scripts/validate-manifest.py` refuses, and `execute` said `adoption verified`
over a project whose first bootstrap then failed, with both legs already
pushed: a blank `--elected-by` or `--reference`, `--elected-on 2026-W41-6` or
`20261011` (which `date.fromisoformat` reads from Python 3.11), `--org
test+org`, and a plan edited to `visibility: secret` or `elected_by: null`
(which `execute` wrote as `elected_by: ""`). The way back was an edit to
`project.yaml`, which AGENTS.md tells an agent never to make to turn a row
green.

`plan` also admitted a `--project` of 251 to 255 characters, which `check` then
refused as `unsafe-value: legs.spec`, because it held `--project` to
`checked_value` and not the names it derives; and under `--local-remote-dir` a
`--project` of 247 to 250 characters died in `Path.exists` with `OSError: File
name too long`, before any leg existed.

Now `plan` refuses before it writes a file, `check` makes a FINDING of each
(`plan-manifest-invalid`), and `execute` refuses every one through `check`'s
own list (#168), before a leg repository exists. All three ask the project's
own validator, loaded from the template it ships, about the `project.yaml` the
plan's values would render.

NO NETWORK AND NO GITHUB. `plan` and `check` read a local source. `execute`
runs only against `--local-remote-dir`, and every `execute` here is a
refusal that comes before the first leg; the tests that run one skip without
`git filter-repo`, as the other `execute` tests do.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, resolve, run_script,
                      write_plan)

sys.path.insert(0, str(REPO / "scripts"))
import repo_shape  # noqa: E402
import shape_materialize  # noqa: E402

PROJECT = "Northwind"
UTF8 = "utf-8"
INVALID = "adopt-manifest-invalid"
FINDING = "FINDING plan-manifest-invalid"
REMOTES, WORK = "remotes", "work"

#: What `execute` needs and `plan` and `check` do not.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))

#: `(extra `plan` flags, what the refusal names)`: values the validator
#: refuses, which `plan` used to write into a plan that `check` passed.
PLAN_REFUSED = [
    pytest.param(["--elected-by= "], (INVALID, "--elected-by is ' '",
                                      "manifest-elected-by"),
                 id="elected-by-blank"),
    pytest.param(["--elected-by=\u3000"], (INVALID, "--elected-by is "
                                           "'\\u3000'", "manifest-elected-by"),
                 id="elected-by-ideographic-space"),
    pytest.param(["--reference= "], (INVALID, "--reference is ' '",
                                     "manifest-reference"),
                 id="reference-blank"),
    pytest.param(["--org=test+org"], (INVALID, "--org is 'test+org'",
                                      "manifest-leg-repository"),
                 id="org-plus"),
    pytest.param(["--org=test@org"], (INVALID, "--org is 'test@org'",
                                      "manifest-leg-repository"),
                 id="org-at"),
    pytest.param(["--elected-on=2026-W41-6"], ("election-date-malformed",
                                               "2026-W41-6"),
                 id="elected-on-iso-week"),
    pytest.param(["--elected-on=20261011"], ("election-date-malformed",
                                             "20261011"),
                 id="elected-on-basic-format"),
]

#: `(old line, new line, what `check` names)`: the same values, edited into a
#: plan by hand, which is what a plan is for.
#: A text value the reader reads as a number (`elected_on: "20261011"`) is
#: not here but in `TEXT_THE_READER_MISREADS` below: where a misread rule is
#: also in the list (#181) it is that rule's finding, and these rows name the
#: validator's.
PLAN_EDITS = [
    pytest.param("visibility: private", "visibility: secret",
                 ("visibility is 'secret'", "manifest-visibility"),
                 id="visibility-secret"),
    pytest.param('elected_by: "Test Human"', "elected_by: null",
                 ("elected_by is ''", "manifest-elected-by"),
                 id="elected-by-null"),
    pytest.param('elected_by: "Test Human"', 'elected_by: " "',
                 ("elected_by is ' '", "manifest-elected-by"),
                 id="elected-by-blank"),
    pytest.param('elected_by: "Test Human"', 'elected_by: ""',
                 ("elected_by is ''", "manifest-elected-by"),
                 id="elected-by-empty"),
    pytest.param('reference: "openxFactory docs/project-repo-schema.md"',
                 'reference: " "', ("reference is ' '", "manifest-reference"),
                 id="reference-blank"),
    pytest.param('elected_on: "2026-09-02"', 'elected_on: "2026-W41-6"',
                 ("elected_on is '2026-W41-6'", "manifest-elected-on"),
                 id="elected-on-iso-week"),
    pytest.param("org: testorg", "org: test+org",
                 ("org is 'test+org'", "manifest-leg-repository"),
                 id="org-plus"),
]


@pytest.fixture(scope="module")
def adopter():
    spec = importlib.util.spec_from_file_location("adopt_manifest_values",
                                                  ADOPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def world(tmp_path):
    """A source, and a plan for it with every question ANSWERED: the plan
    `check` passes. Each test edits its own copy of the text."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "adoption-plan.yaml"
    written = write_plan(source, plan, project=PROJECT)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return {"source": source, "plan": plan, "tmp": tmp_path,
            "text": plan.read_text(encoding=UTF8)}


def edited(world: dict, old: str, new: str) -> Path:
    """The plan with the one line `old` replaced, written beside it."""
    assert old in world["text"], f"{old!r} is not a line of the plan"
    path = world["tmp"] / "edited-plan.yaml"
    with path.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(world["text"].replace(old, new, 1))
    return path


def execute(world: dict, plan: Path):
    return run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                      "--local-remote-dir", str(world["tmp"] / REMOTES),
                      "--work-dir", str(world["tmp"] / WORK))


def no_leg_was_created(world: dict) -> None:
    assert not (world["tmp"] / REMOTES).exists()
    for role in ("spec", "code"):
        assert not (world["tmp"] / WORK / f"{PROJECT}-{role}").exists()


# --- `plan` refuses before it writes anything -----------------------------

@pytest.mark.parametrize("extra, named", PLAN_REFUSED)
def test_plan_refuses_a_value_the_validator_refuses_and_writes_no_plan(
        tmp_path, extra, named):
    source = make_source_repo(tmp_path / "Thing")
    out = tmp_path / "plan.yaml"
    result = write_plan(source, out, extra=tuple(extra))
    assert result.returncode == 2, result.stderr + result.stdout
    for fragment in named:
        assert fragment in result.stderr, result.stderr
    assert not out.exists(), "a refused `plan` wrote a plan"


def test_plan_says_it_in_the_validators_own_words(tmp_path):
    validator = shape_materialize.manifest_validator()
    ((finding,),) = [validator._elected_by_finding({"elected_by": " "})]
    source = make_source_repo(tmp_path / "Thing")
    result = write_plan(source, tmp_path / "plan.yaml",
                        extra=("--elected-by= ",))
    assert finding.split(": ", 1)[1] in result.stderr


def test_plan_still_writes_a_plan_for_values_the_validator_accepts(tmp_path):
    source = make_source_repo(tmp_path / "Thing")
    out = tmp_path / "plan.yaml"
    result = write_plan(source, out, org="my_org.x",
                        extra=("--elected-by=Robert Smith",
                               "--reference=docs/project-repo-schema.md"))
    assert result.returncode == 0, result.stderr + result.stdout
    checked = run_script(ADOPT, "check", "--plan", str(out))
    assert checked.returncode in (0, 1), checked.stderr
    assert FINDING not in checked.stderr


@pytest.mark.parametrize("length", [251, 255])
def test_plan_refuses_a_project_whose_derived_names_check_would_refuse(
        tmp_path, length):
    """`plan` held `--project` to 255 characters and not `<project>-spec`, so
    it wrote a plan that `check` refused as `unsafe-value: legs.spec`. It now
    refuses the same value, in the same words, before the plan exists."""
    source = make_source_repo(tmp_path / "Thing")
    out = tmp_path / "plan.yaml"
    result = write_plan(source, out, project="N" * length)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED unsafe-value: legs.spec is " in result.stderr
    assert not out.exists()


def test_plan_asks_what_check_asks_of_the_same_keys(adopter, tmp_path,
                                                    monkeypatch, capsys):
    """`plan` builds the plan it is about to write from its values, before a
    file exists to read. Held to `render_plan`'s own keys: each key the
    built one carries is what the file `plan` writes then says."""
    built = []
    real = adopter._flag_plan
    monkeypatch.setattr(adopter, "_flag_plan",
                        lambda *a: built.append(real(*a)) or built[-1])
    source = make_source_repo(tmp_path / "Thing")
    out = tmp_path / "plan.yaml"
    code = adopter.main(["plan", "--source", str(source), "--project",
                         PROJECT, "--org", "testorg", "--elected-by",
                         "Test Human", "--elected-on", "2026-09-02",
                         "--visibility", "internal", "--tracking-branch",
                         "trunk", "--pin", "openGlass", "--out", str(out)])
    assert code == 0, capsys.readouterr().err
    (flag_plan,) = built
    written = adopter.Plan.load(out)
    for key, value in flag_plan.data.items():
        if key == "legs":
            for leg, leg_value in value.items():
                assert written.data["legs"][leg] == leg_value, leg
        else:
            assert written.data[key] == value, key


# --- `check` finds, `execute` refuses, both before a leg -------------------

def test_a_plan_with_no_such_edit_still_passes_check(world):
    result = run_script(ADOPT, "check", "--plan", str(world["plan"]))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "plan ok" in result.stdout


@pytest.mark.parametrize("old, new, named", PLAN_EDITS)
def test_check_finds_a_value_the_validator_refuses(world, old, new, named):
    plan = edited(world, old, new)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert [f for f in findings if f.startswith(FINDING)], result.stderr
    for fragment in named:
        assert fragment in result.stderr, result.stderr
    assert "correct each one named here in the plan" in result.stderr


@needs_filter_repo
@pytest.mark.parametrize("old, new, named", PLAN_EDITS)
def test_execute_refuses_it_before_any_leg_exists(world, old, new, named):
    """Each row ended `adoption verified` on main, with both legs pushed and a
    first bootstrap that failed."""
    plan = edited(world, old, new)
    result = execute(world, plan)
    assert result.returncode == 2, result.stderr + result.stdout
    # The refusal wears the code of the FIRST finding in the list (#168). A
    # value another rule also judges (a number-looking `elected_on` is a
    # misread on #181) may be listed before this one, so what is asked is
    # that this finding is in it.
    assert "REFUSED plan-manifest-" in result.stderr
    assert f"{FINDING}: " in result.stderr
    for fragment in named:
        assert fragment in result.stderr, result.stderr
    assert "adoption verified" not in result.stdout
    assert "Traceback" not in result.stderr
    no_leg_was_created(world)
    assert git("branch", "--format=%(refname:short)",
               cwd=world["source"]).stdout.split() == ["main"]


def test_two_bad_values_are_two_findings(world):
    text = world["text"].replace("visibility: private", "visibility: secret")
    text = text.replace('elected_by: "Test Human"', "elected_by: null")
    plan = world["tmp"] / "two.yaml"
    with plan.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1
    found = [line for line in result.stderr.splitlines()
             if line.startswith(FINDING)]
    assert len(found) == 2, result.stderr
    assert "2 finding(s)" in result.stderr


def test_the_org_is_one_finding_not_one_for_each_leg(world):
    """`org: test+org` makes all three repositories `test+org/<Name>`; the
    validator says so three times and the sentence holds them under the one
    value that is wrong."""
    plan = edited(world, "org: testorg", "org: test+org")
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.stderr.count(FINDING) == 1, result.stderr
    for leg in ("assembly", "spec", "code"):
        assert f"leg '{leg}'" in result.stderr


def test_a_plan_the_validator_would_pass_raises_no_refusal(adopter, world):
    """THE CONTRACT THAT MUST NOT BREAK: what `check` passes, `execute`
    runs. (`_refuse_what_check_finds` reads the very list `check` prints.)"""
    plan = adopter.Plan.load(world["plan"])
    source = plan.open_source(str(world["source"]), world["tmp"] / "read")
    assert adopter._refuse_what_check_finds(plan, source) is None


def test_check_and_execute_read_one_list(adopter, world):
    plan_path = edited(world, "visibility: private", "visibility: secret")
    plan = adopter.Plan.load(plan_path)
    source = plan.open_source(str(world["source"]), world["tmp"] / "read")
    findings, remediation = adopter._entry_findings(plan, source)
    assert [f for f in findings if f.startswith(FINDING)]
    with pytest.raises(adopter.Refusal) as caught:
        adopter._refuse_what_check_finds(plan, source)
    assert caught.value.code == "plan-manifest-invalid"
    for finding in findings:
        assert finding in caught.value.detail
    assert remediation[0] in caught.value.remediation


# --- a repository's name is a directory's ----------------------------------

@needs_filter_repo
@pytest.mark.parametrize("length", [247, 250])
def test_execute_refuses_a_name_whose_bare_repository_cannot_be_made(
        tmp_path, length):
    """`plan` cannot know `--local-remote-dir`, so a 247 to 250 character
    project plans and checks; `execute` died in `Path.exists` with `OSError:
    File name too long` and a traceback. It is now refused before a leg."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    written = write_plan(source, plan, project="N" * length)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    checked = run_script(ADOPT, "check", "--plan", str(plan))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / REMOTES),
                        "--work-dir", str(tmp_path / WORK))
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED adopt-name-too-long" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / REMOTES).exists()


def test_one_definition_serves_both_tools(adopter):
    assert adopter.refuse_unstorable_names is (
        shape_materialize.refuse_unstorable_names)
    assert adopter.refuse_manifest_values is (
        shape_materialize.refuse_manifest_values)
    assert adopter.manifest_value_problems is (
        shape_materialize.manifest_value_problems)


def test_the_flags_and_the_plan_keys_name_the_same_values(adopter):
    assert set(adopter.MANIFEST_FLAGS) == set(adopter.MANIFEST_PLAN_KEYS)
    assert adopter.MANIFEST_FLAGS["ELECTED_BY"] == "--elected-by"
    assert adopter.MANIFEST_PLAN_KEYS["ELECTED_BY"] == "elected_by"
    # every value the validator's findings are mapped to is nameable here
    mapped = set(shape_materialize.FINDING_PLACEHOLDER.values())
    assert mapped - {"PROJECT_NAME"} <= set(adopter.MANIFEST_FLAGS)


# --- the question is asked with no git at all -------------------------------
#
# The manifest is rendered here to be ASKED ABOUT and never written: the
# validator the template ships holds `shape.commit` and `shape.digests.
# tree_sha256` to their FORM (`COMMIT_RE`, `SHA256_RE`) and compares neither
# with anything, and neither is a value a tool names to a person, so
# `manifest_misreads` is not asked about them. `plan` and `check` therefore put
# a fixed, well-formed pair into the table they render and run no `git` to read
# the real ones. `execute` still reads the real ones and writes them.

@pytest.fixture(scope="module")
def no_git_standard(tmp_path_factory):
    """The standard as a `git archive` or a downloaded zip holds it: every
    tool, template and contract, and no `.git`, so no revision to read."""
    copy = tmp_path_factory.mktemp("no-git-standard") / "standard"
    shutil.copytree(REPO, copy, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "tests", "docs", "handoffs"))
    assert not (copy / ".git").exists()
    return copy


def verdict_of(result) -> list[str]:
    """What a run said about the values, without the lines git or the host add
    around it."""
    return [line for line in result.stderr.splitlines()
            if line.startswith(("REFUSED ", "FINDING ", "Remediation: "))]


def test_a_checkout_that_cannot_name_its_revision_is_still_asked(
        adopter, world, monkeypatch):
    """`plan` and `check` need no revision, so a checkout that cannot give one
    (or a git that fails) is asked the same question as any other, and a plan
    the validator refuses is found there as it is in a checkout. It skipped
    the whole question and said nothing, so a blank `--elected-by` passed
    `plan` from a tree that had no `.git`."""
    def no_git(*args, **kwargs):
        raise adopter.Refusal("git-failed", "no git here")
    monkeypatch.setattr(adopter, "git_out", no_git)
    monkeypatch.setattr(adopter, "tree_digest", no_git)
    plan = adopter.Plan.load(edited(world, "visibility: private",
                                    "visibility: secret"))
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    assert adopter._manifest_values(plan, naming) is not None
    findings, remediation = adopter._manifest_findings(plan)
    assert len(findings) == 1, findings
    assert findings[0].startswith(FINDING)
    assert "visibility is 'secret'" in findings[0]
    assert remediation
    # and it is no finding for a plan the validator would pass
    good = adopter.Plan.load(world["plan"])
    assert adopter._manifest_findings(good) == ([], [])


def test_the_question_runs_no_process_at_all(adopter, world, monkeypatch):
    """No `git`, no `gh`, no shell: asking what the validator would say of a
    plan's values reads files and runs the validator's own Python, and the
    table it asks about is built by a function that is handed its commit and
    digest. (It ran `git rev-parse HEAD` and then `git ls-tree -r` of the
    whole standard, with `plan` and `check` skipping the question where that
    failed.)"""
    refused = adopter.Plan.load(edited(world, "visibility: private",
                                       "visibility: secret"))
    good = adopter.Plan.load(world["plan"])
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    shape_materialize.manifest_validator()   # its own load is a read as well

    def no_process(*args, **kwargs):
        raise AssertionError(f"a process was started: {args!r}")
    for name in ("run", "Popen", "check_output", "check_call", "call"):
        monkeypatch.setattr(subprocess, name, no_process)
    monkeypatch.setattr(os, "system", no_process)
    assert adopter._manifest_values(good, naming) is not None
    assert adopter._manifest_findings(good) == ([], [])
    assert adopter._manifest_findings(good, misreads_elsewhere=True) == (
        [], [])
    (finding,), remediation = adopter._manifest_findings(refused)
    assert "visibility is 'secret'" in finding
    assert remediation


@pytest.mark.parametrize("flag, value, named", [
    ("--elected-by", " ", "--elected-by is ' '"),
    ("--reference", " ", "--reference is ' '"),
    ("--org", "test+org", "--org is 'test+org'"),
])
def test_plan_refuses_it_from_a_tree_with_no_git_as_in_a_checkout(
        world, tmp_path, no_git_standard, flag, value, named):
    out = tmp_path / "not-written.yaml"
    given = {"--org": "testorg", "--elected-by": "Test Human",
             "--elected-on": "2026-09-02", flag: value}
    args = ["plan", "--source", str(world["source"]), "--project", PROJECT,
            "--out", str(out), *(f"{k}={v}" for k, v in given.items())]
    without_git = run_script(no_git_standard / "adopt-project.py", *args)
    assert without_git.returncode == 2, (without_git.stderr
                                         + without_git.stdout)
    assert f"REFUSED {INVALID}: {named}" in without_git.stderr
    assert "Traceback" not in without_git.stderr
    assert not out.exists(), "a plan was written"
    in_checkout = run_script(ADOPT, *args)
    assert in_checkout.returncode == 2, in_checkout.stderr
    assert verdict_of(without_git) == verdict_of(in_checkout) != []
    assert not out.exists()


def test_plan_and_check_pass_a_good_plan_from_a_tree_with_no_git(
        world, tmp_path, no_git_standard):
    """The question is asked and not skipped, and asking it makes no refusal
    of a plan the validator accepts."""
    out = tmp_path / "plan.yaml"
    planned = run_script(
        no_git_standard / "adopt-project.py", "plan", "--source",
        str(world["source"]), "--project", PROJECT, "--org", "testorg",
        "--elected-by", "Test Human", "--elected-on", "2026-09-02", "--out",
        str(out))
    assert planned.returncode == 0, planned.stderr + planned.stdout
    assert out.is_file()
    for path, leg in ANSWERS:
        resolve(out, path, leg)
    checked = run_script(no_git_standard / "adopt-project.py", "check",
                         "--plan", str(out))
    assert checked.returncode == 0, checked.stderr + checked.stdout
    assert "plan ok" in checked.stdout
    assert FINDING not in checked.stderr


@pytest.mark.parametrize("old, new, named", PLAN_EDITS)
def test_check_finds_it_from_a_tree_with_no_git_as_in_a_checkout(
        world, no_git_standard, old, new, named):
    plan = edited(world, old, new)
    without_git = run_script(no_git_standard / "adopt-project.py", "check",
                             "--plan", str(plan))
    assert without_git.returncode == 1, (without_git.stderr
                                         + without_git.stdout)
    assert FINDING in without_git.stderr, without_git.stderr
    for fragment in named:
        assert fragment in without_git.stderr, without_git.stderr
    in_checkout = run_script(ADOPT, "check", "--plan", str(plan))
    assert in_checkout.returncode == 1
    assert verdict_of(without_git) == verdict_of(in_checkout) != []


def test_what_plan_and_check_put_in_the_table_is_a_well_formed_pair(
        adopter, world):
    """A fixed commit and digest in the form the validator holds the real ones
    to, which the project's YAML reader reads as text whether the template
    quotes it or not (forty digits would be one number, and `12345e6789...`
    another)."""
    commit, digest = (adopter._VALIDATION_SHAPE_COMMIT,
                      adopter._VALIDATION_SHAPE_DIGEST)
    assert re.fullmatch(r"[0-9a-f]{40}", commit)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)
    for value in (commit, digest):
        assert re.search(r"[a-f]", value)
        for line in (f"k: {value}\n", f'k: "{value}"\n'):
            assert shape_materialize.parse_yaml(line) == {"k": value}
    plan = adopter.Plan.load(world["plan"])
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    values = adopter._manifest_values(plan, naming)
    assert values["SHAPE_COMMIT"] == commit
    assert values["SHAPE_TREE_SHA256"] == digest
    # it is not this checkout's own: no claim about it is made
    assert commit != git("rev-parse", "HEAD", cwd=REPO).stdout.strip()


def test_the_validator_compares_the_shape_commit_with_nothing_and_no_tool_names_it(
        adopter, world):
    """What the fixed pair rests on, asked of the validator itself: any
    well-formed commit and digest give the same sentences for the same values,
    a malformed one is refused for its FORM, and neither value is one a tool
    names to a person (so `manifest_misreads` is never asked about it)."""
    plan = adopter.Plan.load(edited(world, "visibility: private",
                                    "visibility: secret"))
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    values = adopter._manifest_values(plan, naming)
    keys = adopter.MANIFEST_PLAN_KEYS
    asked = shape_materialize.manifest_invalid(values, naming, keys)
    assert len(asked) == 1, asked
    assert "visibility is 'secret'" in asked[0]
    head = git("rev-parse", "HEAD", cwd=REPO).stdout.strip()
    for other in ({"SHAPE_COMMIT": head, "SHAPE_TREE_SHA256": "f" * 64},
                  {"SHAPE_COMMIT": "A" * 40, "SHAPE_TREE_SHA256": "0" * 64},
                  {"SHAPE_COMMIT": "1" * 39 + "e",
                   "SHAPE_TREE_SHA256": "e" * 64}):
        assert shape_materialize.manifest_invalid(
            {**values, **other}, naming, keys) == asked
    malformed = shape_materialize.manifest_invalid(
        {**values, "SHAPE_COMMIT": "not-a-commit"}, naming, keys)
    assert any("shape.commit is 'not-a-commit', not 40 hex" in sentence
               for sentence in malformed), malformed
    for table in (adopter.MANIFEST_FLAGS, keys):
        assert "SHAPE_COMMIT" not in table
        assert "SHAPE_TREE_SHA256" not in table
    # and were it asked, the fixed pair reads back as the text it is
    assert shape_materialize.manifest_misreads(
        values, {"SHAPE_COMMIT": "--shape-commit",
                 "SHAPE_TREE_SHA256": "--shape-digest"}) == []


@needs_filter_repo
def test_execute_still_renders_the_real_commit_and_digest(
        adopter, world, monkeypatch, capsys):
    """`execute` reads the standard's own revision and the digest of its tree
    and writes THEM into the files it makes: the fixed pair is for the
    question only. Stopped where the legs would be built, with the table
    `execute` hands them in hand."""
    seen = []

    def stop_before_the_legs(source, names, repositories, urls, values, *rest):
        seen.append(dict(values))
        return None
    monkeypatch.setattr(adopter, "_build_the_legs", stop_before_the_legs)
    code = adopter.main(["execute", "--plan", str(world["plan"]), "--yes",
                         "--local-remote-dir", str(world["tmp"] / REMOTES),
                         "--work-dir", str(world["tmp"] / WORK)])
    capsys.readouterr()
    assert code == 2
    (values,) = seen
    head = git("rev-parse", "HEAD", cwd=REPO).stdout.strip().lower()
    assert values["SHAPE_COMMIT"] == head
    assert values["SHAPE_TREE_SHA256"] == repo_shape.tree_digest(REPO, head)
    assert values["SHAPE_COMMIT"] != adopter._VALIDATION_SHAPE_COMMIT
    assert values["SHAPE_TREE_SHA256"] != adopter._VALIDATION_SHAPE_DIGEST


def test_a_placement_plan_names_no_repository_so_nothing_is_asked(adopter):
    """The doctor's placement plan writes `legs:` as a LIST of the mounted
    legs it audited and is handed to `Plan` by `shape-doctor.py`; it has no
    `legs.spec` to hold to anything, and `.get` on a list is an
    `AttributeError`, not an answer."""
    plan = adopter.Plan(Path("placement.yaml"), {
        "kind": adopter.PLAN_KIND, "mode": "in-place",
        "legs": [{"role": "spec", "path": "spec"}]})
    naming = adopter.NamingPolicy.load(adopter.NAMING_POLICY)
    assert adopter._manifest_values(plan, naming) is None
    assert adopter._manifest_findings(plan) == ([], [])


def test_a_plan_whose_names_do_not_classify_is_the_naming_findings_not_a_crash(
        world):
    """The manifest cannot be rendered from names the naming policy does not
    classify, and `check` reports those in its own words. The question asked
    of the values must not turn that finding into a traceback, or into a
    second finding about a manifest nobody could write."""
    plan = edited(world, "  assembly: Northwind\n", "  assembly: north_wind\n")
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    assert "FINDING naming-unclassified" in result.stderr
    assert FINDING not in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("value", ["../spec", "/spec", ".", '""', "spec/"])
def test_a_bad_leg_path_is_one_finding_in_the_words_of_its_own_rule(world,
                                                                    value):
    """The validator also refuses such a `path:` (`manifest-leg-path`), and the
    plan's `legs.spec_path` is already `plan-bad-leg-path` in the same list:
    said twice would be two findings for one value."""
    plan = edited(world, "  spec_path: spec\n", f"  spec_path: {value}\n")
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    assert "FINDING plan-bad-leg-path" in result.stderr
    assert FINDING not in result.stderr
    assert "1 finding(s)" in result.stderr


@pytest.mark.parametrize("old, new", [
    ("visibility: private", "visibility: [secret]"),
    ('elected_on: "2026-09-02"', "elected_on: 20260902"),
    ("id: northwind", "id: 007"),
])
def test_a_value_the_reader_reads_as_another_kind_is_not_this_questions(
        world, old, new):
    """`id: 007` is the number 7, `elected_on: 20260902` another number and
    `visibility: [secret]` a list: what the template would write is `str` of
    what was read, which the plan never said, so a finding about it would
    echo text nobody typed. That is a misread and is judged as one; the
    validator is asked about the values the plan holds as text, and as no
    value at all."""
    plan = edited(world, old, new)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert FINDING not in result.stderr, result.stderr


# --- a text value the reader misreads: judged once, not twice ---------------

#: `(old line, new line, what the validator says of it)`: TEXT in the plan,
#: which the template writes bare and the project's reader reads as a number
#: or a boolean. The validator refuses each; where a misread rule is also in
#: the list (#181) it refuses the same value, and the sentence should be one.
TEXT_THE_READER_MISREADS = [
    pytest.param("id: northwind", 'id: "007"', "manifest-id: id is 7",
                 id="id-007"),
    pytest.param("visibility: private", 'visibility: "true"',
                 "manifest-visibility: visibility is True",
                 id="visibility-true"),
    pytest.param('elected_on: "2026-09-02"', 'elected_on: "20261011"',
                 "manifest-elected-on: elected_on is 20261011",
                 id="elected-on-basic-format"),
]


@pytest.mark.parametrize("old, new, named", TEXT_THE_READER_MISREADS)
def test_check_refuses_a_text_value_the_reader_misreads(world, old, new,
                                                        named):
    """Whichever rule says it: the validator's finding here, or a misread
    rule's (#181) where one is in the list. What is asked is that `check`
    finds the value, and names it."""
    plan = edited(world, old, new)
    result = run_script(ADOPT, "check", "--plan", str(plan))
    assert result.returncode == 1, result.stderr + result.stdout
    value = new.split(": ", 1)[1].strip('"')
    findings = [line for line in result.stderr.splitlines()
                if line.startswith("FINDING ")]
    assert findings, result.stderr
    assert any(value in f for f in findings), result.stderr


@needs_filter_repo
@pytest.mark.parametrize("old, new, named", TEXT_THE_READER_MISREADS)
def test_execute_refuses_a_text_value_the_reader_misreads_before_any_leg(
        world, old, new, named):
    plan = edited(world, old, new)
    result = execute(world, plan)
    assert result.returncode == 2, result.stderr + result.stdout
    assert "REFUSED plan-manifest-" in result.stderr
    assert new.split(": ", 1)[1].strip('"') in result.stderr
    assert "adoption verified" not in result.stdout
    assert "Traceback" not in result.stderr
    no_leg_was_created(world)


@pytest.mark.parametrize("old, new, named", TEXT_THE_READER_MISREADS)
def test_a_text_value_the_reader_misreads_is_one_finding_on_this_rule_alone(
        adopter, world, old, new, named):
    """With nothing else asking the misread question the validator's finding
    is the only one, so `check` and `execute` still refuse the value: it must
    not be dropped for want of a rule that is not here."""
    plan = adopter.Plan.load(edited(world, old, new))
    findings, remediation = adopter._manifest_findings(plan)
    assert len(findings) == 1, findings
    assert findings[0].startswith(FINDING)
    assert named in findings[0]
    assert remediation


@pytest.mark.parametrize("old, new, named", TEXT_THE_READER_MISREADS)
def test_where_a_misread_rule_judges_it_the_validator_is_not_asked_again(
        adopter, world, old, new, named):
    """`misreads_elsewhere`: a list that holds the misread rule's finding for
    such a value (#181's `plan-manifest-misread`) is not given a second one
    about the same value, in the validator's words and with the retyped text
    (`id is 7`) that the misread finding exists to avoid."""
    plan = adopter.Plan.load(edited(world, old, new))
    assert adopter._manifest_findings(plan, misreads_elsewhere=True) == (
        [], [])


def test_a_value_that_is_not_a_misread_is_still_asked_where_one_judges_the_rest(
        adopter, world):
    """Only what the reader misreads is left out. `visibility: secret` is text
    to the reader and the validator refuses it, so it is still a finding, and
    so is a blank `elected_by`; `id: "007"` beside them is not."""
    text = world["text"].replace("id: northwind", 'id: "007"')
    text = text.replace("visibility: private", "visibility: secret")
    text = text.replace('elected_by: "Test Human"', 'elected_by: " "')
    path = world["tmp"] / "mixed.yaml"
    with path.open("w", encoding=UTF8, newline="\n") as handle:
        handle.write(text)
    plan = adopter.Plan.load(path)
    alone, _ = adopter._manifest_findings(plan)
    shared, _ = adopter._manifest_findings(plan, misreads_elsewhere=True)
    assert len(alone) == 3, alone
    assert len(shared) == 2, shared
    assert any("visibility is 'secret'" in f for f in shared)
    assert any("elected_by is ' '" in f for f in shared)
    assert not any("manifest-id" in f for f in shared)


@pytest.mark.parametrize("old, new, named", TEXT_THE_READER_MISREADS)
def test_a_text_value_the_reader_misreads_is_one_finding_in_the_list_check_prints(
        adopter, world, old, new, named):
    """NOT ZERO AND NOT TWO, whatever rules the list holds. This rule alone,
    `_entry_findings` does not pass `misreads_elsewhere`, and the validator's
    finding is the one. With #181 in the list as well, the call there must pass
    it, or this is the pair the two rules each make of one value: this test
    fails on a merge that has not."""
    plan = adopter.Plan.load(edited(world, old, new))
    source = plan.open_source(str(world["source"]), world["tmp"] / "read")
    findings, _ = adopter._entry_findings(plan, source)
    value = new.split(": ", 1)[1].strip('"')
    about = [f for f in findings if value in f]
    assert len(about) == 1, findings


# --- a validator that cannot be asked ---------------------------------------

def a_copy_of_the_standard(base: Path, remake) -> Path:
    """The standard, as its own git checkout (the tools name their revision),
    with its template's `validate-manifest.py` made over by `remake`, which is
    given the real text and returns the text to put there, or None to remove
    the file."""
    copy = base / "standard"
    shutil.copytree(REPO, copy, symlinks=True, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", ".pytest_cache", "tests", "docs", "handoffs"))
    git("init", "-q", cwd=copy)
    git("add", "-A", cwd=copy)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
        "--no-gpg-sign", "-m", "a copy of the standard", cwd=copy)
    path = copy / "templates" / "assembly-root" / "scripts" / (
        "validate-manifest.py")
    remade = remake(path.read_text(encoding=UTF8))
    if remade is None:
        path.unlink()
    else:
        with path.open("w", encoding=UTF8, newline="\n") as handle:
            handle.write(remade)
    return copy


BROKEN_VALIDATORS = [
    pytest.param(lambda real: None, "could not be loaded: FileNotFoundError",
                 id="missing"),
    pytest.param(lambda real: real + "\n\ndef _findings(manifest, policy, "
                                    "other):\n    raise KeyError('boom')\n",
                 "raised when it was asked: KeyError: 'boom'",
                 id="raises-when-asked"),
]


@pytest.mark.parametrize("remake, said", BROKEN_VALIDATORS)
def test_plan_and_check_name_a_validator_that_cannot_be_asked(
        world, tmp_path, remake, said):
    """The validator the template ships is asked of the values in `plan`,
    `check` and `execute`; one that is missing or raises was a traceback and
    exit 1. `plan` writes no plan and `check` reads none, and both say that the
    defect is the copy's."""
    copy = a_copy_of_the_standard(tmp_path, remake)
    out = tmp_path / "not-written.yaml"
    planned = run_script(
        copy / "adopt-project.py", "plan", "--source", str(world["source"]),
        "--project", PROJECT, "--org", "testorg", "--elected-by", "Test Human",
        "--elected-on", "2026-09-02", "--out", str(out))
    checked = run_script(copy / "adopt-project.py", "check", "--plan",
                         str(world["plan"]))
    for result in (planned, checked):
        assert result.returncode == 2, result.stderr + result.stdout
        assert "REFUSED manifest-validator-unusable" in result.stderr
        assert said in result.stderr, result.stderr
        assert "a defect in the copy of this standard you ran" in result.stderr
        assert "Traceback" not in result.stderr
    assert not out.exists(), "a plan was written"
