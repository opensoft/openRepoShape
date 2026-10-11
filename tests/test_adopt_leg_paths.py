# SPDX-License-Identifier: Apache-2.0
"""A leg's mount path is canonical, or `adopt-project.py` refuses it (#169).

`plan --spec-path spec/` used to be accepted, and `check` said `plan ok`.
`execute` then mounted the leg at `spec` (Git drops the slash) but wrote its
`.gitmodules` URL to a SECOND section literally named `spec/`, so the mount's
real registration kept pointing at the operator's local work directory and the
run still ended `adoption verified`.

The rule is ONE helper asked in three places -- `plan` refuses the flag,
`check` reports a finding, `execute` refuses the plan -- and nothing rewrites
a value on the way: a plan is edited by a person, and a value quietly changed
is a value nobody chose. Everything here but the end-to-end tests runs on a
machine with no `git filter-repo`.

The same helper also refuses what no spelling fixes (the review of #169):

  * a path Git cannot mount a leg at. `--spec-path legs/.git` planned, checked
    and executed to `adoption verified` with NO spec gitlink on the split
    branch, and `.GIT` died at `git submodule add` AFTER both leg repositories
    existed. `.git`, `git~1`, `.gitmodules` in any case, a segment Windows
    strips or reserves (`spec.`, `CON`), are refused;
  * a value `execute`'s `checked_value` refuses (whitespace, non-ASCII, a
    leading `-`, `C:spec`, a shell metacharacter), which `check` used to pass;
  * two paths that differ only in case (`Spec` and `spec`), which a macOS or
    Windows disk keeps as one.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
import sys
from pathlib import Path

import pytest

from conftest import (ADOPT, REPO, git, make_source_repo, resolve,
                      run_script, write_plan)

#: What the end-to-end tests need and nothing else here does.
needs_filter_repo = pytest.mark.skipif(
    shutil.which("git-filter-repo") is None,
    reason="git filter-repo is not installed: `pip install git-filter-repo`")

#: Every non-canonical spelling, with the canonical one the refusal must name
#: (None where none exists: an absolute path and a `..` name another place,
#: and picking it for the person is exactly the silent rewrite this refuses).
NON_CANONICAL = [
    pytest.param("spec/", "spec", id="trailing-slash"),
    pytest.param("./spec", "spec", id="leading-dot-slash"),
    pytest.param("legs//spec", "legs/spec", id="doubled-slash"),
    pytest.param("legs/./spec", "legs/spec", id="dot-segment"),
    pytest.param("legs\\spec", "legs/spec", id="backslash"),
    pytest.param("/spec", None, id="absolute"),
    pytest.param("C:/spec", None, id="drive-letter"),
    pytest.param("C:\\spec", None, id="drive-letter-backslash"),
    pytest.param("../spec", None, id="leading-dotdot"),
    pytest.param("legs/../spec", None, id="inner-dotdot"),
    pytest.param("..", None, id="bare-dotdot"),
    pytest.param(".", None, id="bare-dot"),
    pytest.param("./", None, id="bare-dot-slash"),
    pytest.param("", None, id="empty"),
]

#: Spelled the way Git records them. `a..b` and `.github` carry the dots a
#: naive substring test would trip on: only a WHOLE segment of `.` or `..`
#: is not a path.
CANONICAL = ["spec", "code", "legs/spec", "impl/code", "a/b/c", "spec-v2",
             "a..b", ".github", "..x",
             # Lookalikes of a reserved name are paths: only the WHOLE segment
             # `.git`, `git~1`, `.gitmodules`, or a device name, is refused.
             ".gitignore", "git~2", "my.git", "gitmodules", "spec.d",
             "COM0", "COM10", "LPT0", "console", "auxiliary", "nullable",
             # `checked_value` allows up to 255 characters, and no fewer.
             "x" * 255]

#: Canonical, and still a path a leg cannot be mounted at, with what the
#: sentence must say. No spelling is offered for any of them: they name no
#: place Git can record, and picking another is the silent rewrite refused.
GIT_NAME = "one of Git's own names"
STRIPPED = "ends in a dot or a space"
DEVICE = "a Windows device name"
UNMOUNTABLE = [
    pytest.param(".git", GIT_NAME, id="dot-git"),
    pytest.param("legs/.git", GIT_NAME, id="nested-dot-git"),
    pytest.param(".GIT", GIT_NAME, id="dot-git-upper"),
    pytest.param("legs/.Git/x", GIT_NAME, id="dot-git-mid-path"),
    pytest.param("git~1", GIT_NAME, id="short-name"),
    pytest.param("GIT~1", GIT_NAME, id="short-name-upper"),
    pytest.param("legs/git~1", GIT_NAME, id="nested-short-name"),
    pytest.param(".gitmodules", GIT_NAME, id="dot-gitmodules"),
    pytest.param(".GitModules", GIT_NAME, id="dot-gitmodules-mixed"),
    pytest.param("legs/.gitmodules", GIT_NAME, id="nested-dot-gitmodules"),
    pytest.param("spec.", STRIPPED, id="trailing-dot"),
    pytest.param("legs./spec", STRIPPED, id="trailing-dot-mid-path"),
    pytest.param("spec ", STRIPPED, id="trailing-space"),
    pytest.param("CON", DEVICE, id="con"),
    pytest.param("prn", DEVICE, id="prn-lower"),
    pytest.param("Aux", DEVICE, id="aux-mixed"),
    pytest.param("NUL", DEVICE, id="nul"),
    pytest.param("com1", DEVICE, id="com1"),
    pytest.param("COM9", DEVICE, id="com9"),
    pytest.param("lpt1", DEVICE, id="lpt1"),
    pytest.param("LPT9", DEVICE, id="lpt9"),
    pytest.param("con.txt", DEVICE, id="device-with-extension"),
    pytest.param("legs/nul.tar.gz", DEVICE, id="nested-device-extension"),
]

#: One of each rule, for the places that start a process per value.
UNMOUNTABLE_AT_THE_SITES = [
    pytest.param("legs/.git", GIT_NAME, id="nested-dot-git"),
    pytest.param(".GIT", GIT_NAME, id="dot-git-upper"),
    pytest.param("git~1", GIT_NAME, id="short-name"),
    pytest.param(".gitmodules", GIT_NAME, id="dot-gitmodules"),
    pytest.param("spec.", STRIPPED, id="trailing-dot"),
    pytest.param("CON", DEVICE, id="con"),
]

#: Values `execute`'s `checked_value` refuses and `check` used to pass. A leg
#: path is named only through this helper now, so `plan`, `check` and
#: `execute` all say so, with the same words `checked_value` uses.
NOT_A_COMMAND_LINE_VALUE = "which is not a value this tool will put on a"
ALPHABET = [
    pytest.param("sp ec", id="inner-space"),
    pytest.param(" spec", id="leading-space"),
    pytest.param("spec\t", id="tab"),
    pytest.param("spec\n", id="newline"),
    pytest.param("sp\u00e9c", id="non-ascii"),
    pytest.param("-x", id="leading-dash"),
    pytest.param("C:", id="bare-drive"),
    pytest.param("C:spec", id="drive-relative"),
    pytest.param("spec;rm", id="semicolon"),
    pytest.param("$HOME/x", id="dollar"),
    pytest.param("a b/c", id="space-in-a-segment"),
    pytest.param("x" * 256, id="256-characters"),
]
ALPHABET_AT_THE_SITES = [
    pytest.param("sp ec", id="inner-space"),
    pytest.param("sp\u00e9c", id="non-ascii"),
    pytest.param("-x", id="leading-dash"),
    pytest.param("C:spec", id="drive-relative"),
    pytest.param("spec;rm", id="semicolon"),
]

#: The same pairs `plan` takes as flags and a plan file carries as `legs:`.
BAD_PAIRS = [
    pytest.param("spec", "spec", "are both 'spec'", id="equal"),
    pytest.param("legs", "legs/spec", "is inside", id="code-inside-spec"),
    pytest.param("legs/spec", "legs", "is inside", id="spec-inside-code"),
    # macOS and Windows disks compare names without regard to case, so these
    # are the same collisions with a capital letter in the way.
    pytest.param("Spec", "spec", "differ only in case", id="equal-but-case"),
    pytest.param("Legs/spec", "legs", "once case is ignored",
                 id="spec-inside-code-but-case"),
    pytest.param("Legs", "legs/code", "once case is ignored",
                 id="code-inside-spec-but-case"),
]

#: Answered the way `test_adopt_plan.py` answers them, so `check` can pass.
ANSWERS = (("examples/", "spec"), (".claude/", "root"),
           ("release.yaml", "root"))

ROLES = pytest.mark.parametrize("role", ["spec", "code"])


@pytest.fixture(scope="module")
def adopter():
    """`adopt-project.py` loaded as a module, for the functions that have no
    command line of their own."""
    module_spec = importlib.util.spec_from_file_location("adopt_leg_paths",
                                                         ADOPT)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    """One source repository and one ANSWERED plan against it.

    `plan` and `check` only read the source, so every test below may share
    them; a test that edits the plan edits a copy (`edited`)."""
    root = tmp_path_factory.mktemp("leg-paths")
    source = make_source_repo(root / "Thing")
    plan = root / "adoption-plan.yaml"
    written = write_plan(source, plan)
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    return {"source": source, "plan": plan}


def set_leg_paths(plan: Path, **paths) -> None:
    """Rewrite `legs.spec_path` and `legs.code_path` in a plan, like a person
    editing it. The value is double-quoted and escaped (a backslash, a quote,
    a tab and a newline) so that any spelling survives the YAML reader; None
    removes the key, which is the default."""
    text = plan.read_text(encoding="utf-8")
    for role, value in paths.items():
        pattern = re.compile(rf"^  {role}_path: .*\n", re.MULTILINE)
        assert pattern.search(text), f"no `{role}_path:` line in the plan"
        escaped = None if value is None else (
            value.replace("\\", "\\\\").replace('"', '\\"')
            .replace("\t", "\\t").replace("\n", "\\n"))
        line = "" if escaped is None else f'  {role}_path: "{escaped}"\n'
        text = pattern.sub(lambda _match: line, text, count=1)
    plan.write_text(text, encoding="utf-8")


@pytest.fixture
def edited(world, tmp_path) -> Path:
    """A private copy of the answered plan, for a test to edit."""
    copy = tmp_path / "plan.yaml"
    shutil.copy(world["plan"], copy)
    return copy


def plan_values(adopter, **legs):
    """A `Plan` carrying these `legs:`, with no source and no file."""
    return adopter.Plan(Path("plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place", "legs": legs})


# --- the one helper -------------------------------------------------------

@pytest.mark.parametrize("value", CANONICAL)
def test_a_canonical_path_has_no_problem(adopter, value):
    assert adopter.leg_path_problem("--spec-path", value) is None


@pytest.mark.parametrize("value, spelling", NON_CANONICAL)
def test_a_non_canonical_path_is_named_with_its_canonical_spelling(
        adopter, value, spelling):
    problem = adopter.leg_path_problem("--spec-path", value)
    assert problem is not None
    assert problem.startswith(f"--spec-path is {value!r}, which is not a "
                              "canonical leg path")
    if spelling is None:
        assert "Write '" not in problem
    else:
        assert problem.endswith(f"Write {spelling!r}.")


#: What the YAML reader makes of `spec_path: 5`, `true`, `1.50`, `[spec]` and a
#: block mapping. The reader keeps no raw text, so the sentence names the KIND
#: and never echoes Python's repr of the parsed value: `007` is read as 7,
#: `true` as True and `1.50` as 1.5, none of which the file ever said.
NOT_TEXT = [
    pytest.param(5, "a number", id="int"),
    pytest.param(True, "true or false", id="bool"),
    pytest.param(1.5, "a number", id="float"),
    pytest.param(["spec"], "a list", id="list"),
    pytest.param({"a": "b"}, "a mapping", id="mapping"),
]


@pytest.mark.parametrize("value, kind", NOT_TEXT)
def test_a_value_that_is_not_text_is_a_problem_that_does_not_echo_it(
        adopter, value, kind):
    problem = adopter.leg_path_problem("legs.spec_path", value)
    assert problem.startswith("legs.spec_path is not text: ")
    assert f"was read as {kind}," in problem and "so quote it" in problem
    assert repr(value) not in problem, "the parsed value is not what was written"


@pytest.mark.parametrize("value, said", UNMOUNTABLE)
def test_a_name_git_or_windows_keeps_is_refused_with_no_spelling_offered(
        adopter, value, said):
    problem = adopter.leg_path_problem("--spec-path", value)
    assert problem is not None
    assert problem.startswith(f"--spec-path is {value!r}, which a leg cannot "
                              "be mounted at: ")
    assert said in problem
    assert "Write '" not in problem


@pytest.mark.parametrize("value", [
    pytest.param("./.git", id="dot-slash-git"),
    pytest.param("legs//CON", id="doubled-slash-device"),
    pytest.param(".git/", id="git-trailing-slash")])
def test_a_spelling_that_would_name_a_reserved_path_is_not_offered(adopter, value):
    """`./.git` is a spelling problem, and its canonical form `.git` is not a
    path anyone can mount: naming it would send the person from one refusal
    to the next."""
    problem = adopter.leg_path_problem("--spec-path", value)
    assert "not a canonical leg path" in problem
    assert "Write '" not in problem


@pytest.mark.parametrize("value", ALPHABET)
def test_a_value_execute_would_refuse_is_a_problem_here_too(adopter, value):
    problem = adopter.leg_path_problem("--spec-path", value)
    assert problem is not None
    assert problem.startswith(f"--spec-path is {value!r}, "
                              f"{NOT_A_COMMAND_LINE_VALUE}")
    assert "Write '" not in problem


@pytest.mark.parametrize("value", ["legs/../spec", "spec/..", "../spec", ".."])
def test_a_dotdot_is_said_to_name_another_place_not_always_to_climb_out(
        adopter, value):
    """`legs/../spec` is `spec` and `spec/..` is the assembly root: neither
    climbs out of it, so the sentence must not say they do."""
    problem = adopter.leg_path_problem("--spec-path", value)
    assert "names a different place than it spells" in problem
    assert "which climbs out" not in problem


@pytest.mark.parametrize("value", [".", "./", ".//."])
def test_dot_and_dot_slash_are_said_to_name_the_assembly_root_itself(
        adopter, value):
    """Git dies on them (`empty string is not a valid pathspec`) because the
    value IS the assembly root; "two different paths" was the wrong reason."""
    problem = adopter.leg_path_problem("--spec-path", value)
    assert "names the assembly root itself" in problem
    assert "two different paths" not in problem
    assert "Write '" not in problem


def test_a_drive_letter_is_called_absolute_only_where_that_is_true(adopter):
    problem = adopter.leg_path_problem("--spec-path", "C:/spec")
    assert "`C:/spec` on Windows" in problem
    assert "`/spec` on every platform" in problem


@pytest.mark.parametrize("spec, code, said", BAD_PAIRS)
def test_equal_and_nested_paths_are_problems(adopter, spec, code, said):
    problems = adopter.leg_path_problems(("--spec-path", spec),
                                         ("--code-path", code))
    assert len(problems) == 1 and said in problems[0]


@pytest.mark.parametrize("spec, code", [
    ("spec", "code"), ("legs/spec", "impl/code"), ("legs/spec", "legs/code"),
    ("spec", "spec2"), ("legs/spec", "legs/specification"), ("a", "ab"),
    ("Legs/spec", "legs/code"), ("Spec", "specs"), ("a", "Ab")])
def test_two_distinct_unnested_paths_are_no_problem(adopter, spec, code):
    assert adopter.leg_path_problems(("--spec-path", spec),
                                     ("--code-path", code)) == []


def test_the_pair_is_compared_only_when_each_path_is_canonical(adopter):
    """`spec/` twice is two spelling problems, not "both the same path": a
    comparison of two strings that are not paths would say a second, wrong
    thing about a value the first sentence already condemns."""
    problems = adopter.leg_path_problems(("--spec-path", "spec/"),
                                         ("--code-path", "spec/"))
    assert len(problems) == 2
    assert all("not a canonical leg path" in p for p in problems)


# --- `plan` ----------------------------------------------------------------

@ROLES
@pytest.mark.parametrize("value, spelling", NON_CANONICAL)
def test_plan_refuses_a_non_canonical_path_and_writes_nothing(
        world, tmp_path, role, value, spelling):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out,
                        extra=(f"--{role}-path", value))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED adopt-bad-leg-path" in result.stderr
    assert f"--{role}-path is {value!r}" in result.stderr
    if spelling is None:
        assert "Write '" not in result.stderr
    else:
        assert f"Write {spelling!r}." in result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"


@pytest.mark.parametrize("spec, code, said", BAD_PAIRS)
def test_plan_refuses_equal_and_nested_legs(world, tmp_path, spec, code, said):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out,
                        extra=("--spec-path", spec, "--code-path", code))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "adopt-bad-leg-path" in result.stderr
    assert said in result.stderr
    assert not out.exists()


@ROLES
@pytest.mark.parametrize("value, said", UNMOUNTABLE_AT_THE_SITES)
def test_plan_refuses_a_name_git_or_windows_keeps_and_writes_nothing(
        world, tmp_path, role, value, said):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out, extra=(f"--{role}-path={value}",))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED adopt-bad-leg-path" in result.stderr
    assert f"--{role}-path is {value!r}, which a leg cannot be mounted at" in (
        result.stderr)
    assert said in result.stderr and "Write '" not in result.stderr
    assert not out.exists(), "a refused plan must leave no file behind"


@ROLES
@pytest.mark.parametrize("value", ALPHABET_AT_THE_SITES)
def test_plan_refuses_a_value_execute_would_refuse_under_the_same_code(
        world, tmp_path, role, value):
    """`check` and `plan` used to disagree with `execute` about these: the
    flag was refused as `unsafe-value`, the plan file passed `check`."""
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out, extra=(f"--{role}-path={value}",))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED adopt-bad-leg-path" in result.stderr
    assert (f"--{role}-path is {value!r}, {NOT_A_COMMAND_LINE_VALUE}"
            in result.stderr)
    assert not out.exists(), "a refused plan must leave no file behind"


def test_the_remediation_names_every_rule_a_person_could_trip(world, tmp_path):
    """The refusal's trailer is the whole rule, so a person who retypes a value
    meets no rule that was never said: Git's names, Windows's, the alphabet
    (`checked_value`'s own pattern, read from where it lives) and case."""
    sys.path.insert(0, str(REPO / "scripts"))
    from repo_shape import SAFE_ARG_RE
    result = write_plan(world["source"], tmp_path / "plan.yaml",
                        extra=("--spec-path=legs/.git",))
    assert result.returncode == 2
    remediation = result.stderr[result.stderr.index("Remediation:"):]
    for phrase in ("`.git`, `git~1`, `.gitmodules`", "ends in a dot or a space",
                   "Windows device name", "`COM1`-`COM9`", SAFE_ARG_RE.pattern,
                   "whatever the case"):
        assert phrase in remediation, phrase


def test_plan_names_every_bad_path_and_not_only_the_first(world, tmp_path):
    result = write_plan(world["source"], tmp_path / "plan.yaml",
                        extra=("--spec-path", "spec/", "--code-path",
                               "./code"))
    assert result.returncode == 2
    assert "Write 'spec'." in result.stderr
    assert "Write 'code'." in result.stderr


@pytest.mark.parametrize("spec, code", [
    ("spec", "code"), ("legs/spec", "impl/code")], ids=["defaults", "nested"])
def test_plan_still_records_a_canonical_path_exactly_as_given(
        world, tmp_path, spec, code):
    out = tmp_path / "plan.yaml"
    result = write_plan(world["source"], out,
                        extra=("--spec-path", spec, "--code-path", code))
    assert result.returncode == 0, result.stderr + result.stdout
    text = out.read_text(encoding="utf-8")
    assert f"\n  spec_path: {spec}\n  code_path: {code}\n" in text


# --- `check` ---------------------------------------------------------------

@ROLES
@pytest.mark.parametrize("value, spelling", NON_CANONICAL)
def test_check_reports_a_non_canonical_path_as_a_finding(
        edited, role, value, spelling):
    set_leg_paths(edited, **{role: value})
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"FINDING plan-bad-leg-path: legs.{role}_path is {value!r}"
            in result.stderr)
    if spelling is not None:
        assert f"Write {spelling!r}." in result.stderr
    assert "1 finding(s)" in result.stderr
    assert "plan ok" not in result.stdout


@ROLES
@pytest.mark.parametrize("value, said", UNMOUNTABLE_AT_THE_SITES)
def test_check_reports_a_name_git_or_windows_keeps_as_a_finding(
        edited, role, value, said):
    set_leg_paths(edited, **{role: value})
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"FINDING plan-bad-leg-path: legs.{role}_path is {value!r}, "
            "which a leg cannot be mounted at") in result.stderr
    assert said in result.stderr and "Write '" not in result.stderr
    assert "plan ok" not in result.stdout


@ROLES
@pytest.mark.parametrize("value", ALPHABET_AT_THE_SITES)
def test_check_reports_a_value_execute_would_refuse_as_a_finding(
        edited, role, value):
    """The review's SHOULD-FIX 1: `check` said `plan ok` for `spec ` and the
    like, and `execute` then refused with `unsafe-value`."""
    set_leg_paths(edited, **{role: value})
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 1, result.stdout + result.stderr
    assert (f"FINDING plan-bad-leg-path: legs.{role}_path is {value!r}, "
            f"{NOT_A_COMMAND_LINE_VALUE}") in result.stderr
    assert "plan ok" not in result.stdout


#: `spec_path: 007` and the like, written the way a person types them: UNQUOTED.
#: What the finding must not show is what the reader made of them.
RAW_NON_TEXT = [
    pytest.param("007", "a number", "7", id="leading-zeros"),
    pytest.param("true", "true or false", "True", id="true"),
    pytest.param("1.50", "a number", "1.5", id="trailing-zero"),
    pytest.param("[spec]", "a list", "'spec'", id="flow-list"),
]


@ROLES
@pytest.mark.parametrize("raw, kind, misleading", RAW_NON_TEXT)
def test_check_reports_a_non_text_value_without_echoing_what_the_reader_made_of_it(
        edited, role, raw, kind, misleading):
    text = edited.read_text(encoding="utf-8")
    pattern = re.compile(rf"^  {role}_path: .*$", re.MULTILINE)
    assert pattern.search(text)
    edited.write_text(pattern.sub(lambda _m: f"  {role}_path: {raw}", text,
                                  count=1), encoding="utf-8")
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 1, result.stdout + result.stderr
    finding = next(line for line in result.stderr.splitlines()
                   if line.startswith("FINDING plan-bad-leg-path"))
    assert f"legs.{role}_path is not text: its value was read as {kind}" in (
        finding)
    assert misleading not in finding


@pytest.mark.parametrize("spec, code, said", BAD_PAIRS)
def test_check_reports_equal_and_nested_legs_as_a_finding(
        edited, spec, code, said):
    set_leg_paths(edited, spec=spec, code=code)
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 1, result.stdout + result.stderr
    assert "FINDING plan-bad-leg-path" in result.stderr
    assert said in result.stderr


@pytest.mark.parametrize("spec, code", [
    ("spec", "code"), ("legs/spec", "impl/code"), (None, None)],
    ids=["defaults", "nested", "keys-absent"])
def test_check_still_passes_a_canonical_or_defaulted_path(edited, spec, code):
    set_leg_paths(edited, spec=spec, code=code)
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 0, result.stderr
    assert "plan ok" in result.stdout


def test_check_names_the_default_mount_paths_when_the_plan_has_no_keys(edited):
    """`check` read `plan.legs.get(...)` raw and printed `mount the legs at
    None/ and None/` for a plan that carries neither key, though `execute`
    mounts them at `spec` and `code`."""
    set_leg_paths(edited, spec=None, code=None)
    result = run_script(ADOPT, "check", "--plan", str(edited))
    assert result.returncode == 0, result.stderr
    assert "mount the legs at spec/ and code/" in result.stdout
    assert "None" not in result.stdout


@pytest.mark.parametrize("legs", [
    [{"role": "spec", "path": "spec", "state": "audited"},
     {"role": "code", "path": "code", "state": "audited"}],
    ["spec", "code"],
    "spec",
], ids=["records", "strings", "scalar"])
def test_a_plan_whose_legs_is_not_a_mapping_gets_no_leg_path_finding(
        adopter, legs):
    """The doctor's PLACEMENT plan writes `legs:` as a LIST, and
    `tests/test_shape_doctor.py` hands it to `Plan` and `_leg_findings` to
    prove its entries are adoption-plan entries. `plan.legs.get(...)` on that
    list was an `AttributeError`; a list has no mount paths, so the leg-path
    check reads nothing and says nothing, and the entries are still judged.
    There is no source tree here, and `None` says so: `_leg_findings` takes
    no default for it (#172's merge with #166)."""
    plan = adopter.Plan(Path("placement-plan.yaml"), {
        "kind": "adoption-plan", "mode": "in-place", "legs": legs,
        "paths": [{"path": "spec/examples/", "leg": None,
                   "question": "is this acceptance evidence?"}]})
    findings = adopter._leg_findings(plan, None)
    assert [f.split(":")[0] for f in findings] == ["FINDING plan-unresolved"], \
        findings
    assert adopter._plan_leg_paths(plan) == (("legs.spec_path", "spec"),
                                             ("legs.code_path", "code"))
    plan.entries[0]["leg"] = "spec"
    assert adopter._leg_findings(plan, None) == []


# --- `_checked_plan_values`, which is what `execute` asks ------------------

@ROLES
@pytest.mark.parametrize("value, spelling", NON_CANONICAL)
def test_checked_plan_values_refuses_a_non_canonical_path(
        adopter, role, value, spelling):
    plan = plan_values(adopter, **{f"{role}_path": value})
    with pytest.raises(adopter.Refusal) as raised:
        adopter._checked_plan_values(plan)
    assert raised.value.code == "plan-bad-leg-path"
    assert f"legs.{role}_path is {value!r}" in raised.value.detail
    if spelling is not None:
        assert f"Write {spelling!r}." in raised.value.detail


@ROLES
@pytest.mark.parametrize("value, said", UNMOUNTABLE)
def test_checked_plan_values_refuses_a_name_git_or_windows_keeps(
        adopter, role, value, said):
    plan = plan_values(adopter, **{f"{role}_path": value})
    with pytest.raises(adopter.Refusal) as raised:
        adopter._checked_plan_values(plan)
    assert raised.value.code == "plan-bad-leg-path"
    assert said in raised.value.detail and "Write '" not in raised.value.detail


@ROLES
@pytest.mark.parametrize("value", ALPHABET)
def test_checked_plan_values_refuses_a_value_checked_value_refuses_under_one_code(
        adopter, role, value):
    """The code is the helper's, `plan-bad-leg-path`, not `unsafe-value`: the
    three places now say the same thing about the same value."""
    plan = plan_values(adopter, **{f"{role}_path": value})
    with pytest.raises(adopter.Refusal) as raised:
        adopter._checked_plan_values(plan)
    assert raised.value.code == "plan-bad-leg-path"
    assert NOT_A_COMMAND_LINE_VALUE in raised.value.detail


@pytest.mark.parametrize("value, kind", NOT_TEXT)
def test_checked_plan_values_refuses_a_value_that_is_not_text(
        adopter, value, kind):
    with pytest.raises(adopter.Refusal) as raised:
        adopter._checked_plan_values(plan_values(adopter, spec_path=value))
    assert raised.value.code == "plan-bad-leg-path"
    assert f"was read as {kind}," in raised.value.detail


@pytest.mark.parametrize("spec, code, said", BAD_PAIRS)
def test_checked_plan_values_refuses_equal_and_nested_legs(
        adopter, spec, code, said):
    plan = plan_values(adopter, spec_path=spec, code_path=code)
    with pytest.raises(adopter.Refusal) as raised:
        adopter._checked_plan_values(plan)
    assert raised.value.code == "plan-bad-leg-path"
    assert said in raised.value.detail


@pytest.mark.parametrize("legs, expected", [
    ({}, ("spec", "code")),
    ({"spec_path": "spec", "code_path": "code"}, ("spec", "code")),
    ({"spec_path": "legs/spec", "code_path": "impl/code"},
     ("legs/spec", "impl/code")),
], ids=["keys-absent", "defaults", "nested"])
def test_checked_plan_values_still_returns_a_canonical_path_untouched(
        adopter, legs, expected):
    assert adopter._checked_plan_values(
        plan_values(adopter, **legs))[:2] == expected


# --- `execute`, end to end -------------------------------------------------

def registered_sections(source: Path) -> set[str]:
    """Every submodule NAME the split branch's `.gitmodules` registers."""
    listing = git("config", "--blob", "adopt/three-repo-shape:.gitmodules",
                  "--list", cwd=source).stdout.splitlines()
    return {key[len("submodule."):key.rindex(".")]
            for key in (line.split("=", 1)[0] for line in listing)}


@needs_filter_repo
def test_execute_refuses_a_slash_terminated_path_before_any_leg_exists(
        tmp_path):
    """The repro from #169: `spec/` in the plan. `main` ran it to `adoption
    verified`; now it is refused before a leg repository is created."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    assert write_plan(source, plan).returncode == 0
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    set_leg_paths(plan, spec="spec/")
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED plan-bad-leg-path" in result.stderr
    assert "Write 'spec'." in result.stderr
    assert "adoption verified" not in result.stdout
    assert not remotes.exists(), "no leg repository may exist after a refusal"
    assert not list((tmp_path / "work").glob("Northwind-*")), (
        "no leg may have been extracted")
    assert git("branch", "--list", "adopt/three-repo-shape",
               cwd=source).stdout == "", "the source got no split branch"


@needs_filter_repo
@pytest.mark.parametrize("value", ["legs/.git", ".GIT"])
def test_execute_refuses_a_name_git_keeps_before_any_leg_exists(tmp_path, value):
    """The review's SHOULD-FIX 2, both ways it failed on the branch: `legs/.git`
    ran to `adoption verified` with NO spec gitlink on the split branch, and
    `.GIT` died at `git submodule add` AFTER both leg repositories existed."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    assert write_plan(source, plan).returncode == 0
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    set_leg_paths(plan, spec=value)
    remotes = tmp_path / "remotes"
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(remotes),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 2, result.stdout + result.stderr
    assert "REFUSED plan-bad-leg-path" in result.stderr
    assert "one of Git's own names" in result.stderr
    assert "adoption verified" not in result.stdout
    assert not remotes.exists(), "no leg repository may exist after a refusal"
    assert not list((tmp_path / "work").glob("Northwind-*")), (
        "no leg may have been extracted")
    assert git("branch", "--list", "adopt/three-repo-shape",
               cwd=source).stdout == "", "the source got no split branch"


@needs_filter_repo
def test_execute_still_adopts_at_nested_canonical_paths(tmp_path):
    """The other half of the rule: `legs/spec` and `impl/code` are canonical,
    and the split registers exactly those two mounts and no other section."""
    source = make_source_repo(tmp_path / "Thing")
    plan = tmp_path / "plan.yaml"
    written = write_plan(source, plan, extra=("--spec-path", "legs/spec",
                                              "--code-path", "impl/code"))
    assert written.returncode == 0, written.stderr + written.stdout
    for path, leg in ANSWERS:
        resolve(plan, path, leg)
    result = run_script(ADOPT, "execute", "--plan", str(plan), "--yes",
                        "--local-remote-dir", str(tmp_path / "remotes"),
                        "--work-dir", str(tmp_path / "work"))
    assert result.returncode == 0, result.stderr + result.stdout
    assert "adoption verified" in result.stdout
    assert registered_sections(source) == {"legs/spec", "impl/code"}
