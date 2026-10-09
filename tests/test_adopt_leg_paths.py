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
is a value nobody chose. Everything here but the one end-to-end test runs on
a machine with no `git filter-repo`.
"""

from __future__ import annotations

import importlib.util
import re
import shutil
from pathlib import Path

import pytest

from conftest import (ADOPT, git, make_source_repo, resolve, run_script,
                      write_plan)

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
    pytest.param("", None, id="empty"),
]

#: Spelled the way Git records them. `a..b` and `.github` carry the dots a
#: naive substring test would trip on: only a WHOLE segment of `.` or `..`
#: is not a path.
CANONICAL = ["spec", "code", "legs/spec", "impl/code", "a/b/c", "spec-v2",
             "a..b", ".github", "..x"]

#: The same pairs `plan` takes as flags and a plan file carries as `legs:`.
BAD_PAIRS = [
    pytest.param("spec", "spec", "are both 'spec'", id="equal"),
    pytest.param("legs", "legs/spec", "is inside", id="code-inside-spec"),
    pytest.param("legs/spec", "legs", "is inside", id="spec-inside-code"),
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
    editing it. The value is double-quoted and escaped so that any spelling
    survives the YAML reader; None removes the key, which is the default."""
    text = plan.read_text(encoding="utf-8")
    for role, value in paths.items():
        pattern = re.compile(rf"^  {role}_path: .*\n", re.MULTILINE)
        assert pattern.search(text), f"no `{role}_path:` line in the plan"
        escaped = None if value is None else (
            value.replace("\\", "\\\\").replace('"', '\\"'))
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


@pytest.mark.parametrize("value", [5, True, 1.5, ["spec"]])
def test_a_value_that_is_not_text_is_a_problem(adopter, value):
    assert "not text" in adopter.leg_path_problem("legs.spec_path", value)


@pytest.mark.parametrize("spec, code, said", BAD_PAIRS)
def test_equal_and_nested_paths_are_problems(adopter, spec, code, said):
    problems = adopter.leg_path_problems(("--spec-path", spec),
                                         ("--code-path", code))
    assert len(problems) == 1 and said in problems[0]


@pytest.mark.parametrize("spec, code", [
    ("spec", "code"), ("legs/spec", "impl/code"), ("legs/spec", "legs/code"),
    ("spec", "spec2"), ("legs/spec", "legs/specification"), ("a", "ab")])
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
