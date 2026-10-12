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
import shutil
import sys
from argparse import Namespace
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, resolve, run_script,
                      write_plan)

sys.path.insert(0, str(REPO / "scripts"))
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


def test_a_checkout_that_cannot_name_its_revision_skips_the_question(
        adopter, world, monkeypatch):
    """`plan` and `check` never needed a revision and are not made to: where
    this tool's own checkout cannot give one (`execute` could not run either,
    and says so where it reads one), the manifest cannot be rendered and
    nothing is asked, rather than `check` dying where it succeeded."""
    def no_revision(*args, **kwargs):
        raise adopter.Refusal("not-a-checkout", "no git here")
    monkeypatch.setattr(adopter, "git_out", no_revision)
    plan = adopter.Plan.load(edited(world, "visibility: private",
                                    "visibility: secret"))
    assert adopter._manifest_findings(plan) == ([], [])


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
    assert findings and any(value in f for f in findings), result.stderr


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
    assert findings[0].startswith(FINDING) and named in findings[0]
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
